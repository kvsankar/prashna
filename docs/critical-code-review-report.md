# Critical Code Review Report

Date: 2026-05-12

## Findings

### High: Queued quizzes leak questions before start — **DONE**

**Fix:** `serialize_quiz_run` now exposes `current_question` only when the caller is a moderator/owner, or the run is `live`/`closed`. Queued runs return `current_question: null` for non-mods. Test: `tests/api/test_quizzes.py` covers the redaction.



`GET /api/sessions/{code}/quiz_runs` returns every run to non-moderators, including `queued` runs (`app/main.py:1226`). `serialize_quiz_run` serializes `current_question` and answer text whenever the run has a current index (`app/main.py:277`). A participant who knows the session code can call this endpoint before the moderator starts the quiz and preview the first queued question and answers.

The spec intentionally returns queued runs for the projector lobby (`docs/specs.md:1029`), but the current payload is too detailed for a pre-start public view.

Recommendation: for non-moderators and queued runs, return only lobby-safe metadata such as quiz title/version/status, with `current_question: null` and no answer list. Add an API test for queued public payload redaction.

### High: Participants can change answers after reveal — **DONE**

**Fix:** `submit_quiz_run` now rejects with 400 "Voting closed — results have been revealed" when `run.reveal_current` is true. Test in `tests/api/test_quiz_submissions.py`.



`submit_quiz_run` only requires `run.status == "live"` (`app/main.py:1475`). It does not reject submissions after `run.reveal_current` becomes true (`app/main.py:1398`). A participant can view the correct answer after reveal, then resubmit before the run is closed and alter final tallies.

Recommendation: reject submissions when `run.reveal_current` is true, or introduce an explicit `accepting_answers` phase flag. Add a test that submit-after-reveal returns a controlled 400/409 and does not mutate submissions.

### High: Password changes do not invalidate existing admin cookies — **DONE**

**Fix:** Added `User.session_version` (int). Signed cookie payload is now `"{user_id}:{session_version}"`. `current_admin` rejects when versions don't match. `admin_change_password` bumps the counter. Backward-compat shim in `_parse_cookie` allows old uid-only cookies during transition (will phase out after redeploy).



`admin_change_password` updates the password and reissues a cookie (`app/main.py:480`), but cookie validation only checks signer and age (`app/auth.py:67`). Any old admin cookie remains valid for up to 30 days after a password change.

Recommendation: include a session version, password-changed timestamp, or per-user session secret in signed cookies and verify it on every request. Add a regression test that captures the old `prashna_admin` cookie, changes the password, and proves the old cookie can no longer access admin routes.

### High: First-run admin setup is raceable — **DONE**

**Fix:** `admin_setup` now wraps the insert in try/except `IntegrityError`, re-checks `admin_exists()` after commit, and returns deterministic 409 on conflict. Singleton invariant enforced at the app level (no DB-level "only-one-row" constraint added — singleton is a deployment-state notion, not a domain truth).



`admin_setup` checks `admin_exists()` before inserting (`app/main.py:438`), but there is no singleton invariant on `User` (`app/models.py:13`) and `admin_exists()` is only a read (`app/auth.py:96`). Two concurrent setup calls with different usernames can both pass the check and create multiple admins. Two calls with the same username can surface an uncaught database integrity error.

Recommendation: enforce a singleton bootstrap invariant, for example a deployment settings row or a fixed singleton admin slot, and handle insert conflicts as deterministic `409` responses. Add concurrent setup tests.

### Medium-High: Quiz-run transitions can mutate queued or closed history — **DONE**

**Fix:** Added source-state guards. `advance`, `reveal`, `close` now require `status == "live"`. `live_counts` is allowed on queued+live (a moderator may pre-configure ahead of Start) and blocked on closed. Tests in `tests/api/test_quiz_run_lifecycle.py`.



`advance`, `live_counts`, `reveal`, and `close` do not validate source status (`app/main.py:1353`, `app/main.py:1382`, `app/main.py:1398`, `app/main.py:1413`). A moderator can close a never-started queued run, reveal a queued run, or advance/toggle a closed run after it should be historical.

Recommendation: require `status == "live"` for advance/reveal/live-counts/close unless the product intentionally allows a specific queued operation. Closed runs should be immutable except for owner-only administrative repair paths.

### Medium: Participant write paths can surface database conflicts as 500s — **DONE**

**Fix:** `submit_quiz_run` now dedupes `answer_ids` via `list(dict.fromkeys(...))`. Vote toggle wraps both insert and delete in try/except `IntegrityError` and re-resolves the row state. Tests cover duplicate IDs and same-participant repeat-vote.



Vote toggling uses a check-then-insert flow without conflict handling (`app/main.py:779`) over a unique constraint (`app/models.py:82`). Quiz submissions delete old rows and insert new rows without deduping `answer_ids` (`app/main.py:1507`) over a unique constraint (`app/models.py:238`). Duplicate multi-choice IDs, same-cookie concurrent submissions, or concurrent vote toggles can trigger database integrity errors.

Recommendation: dedupe `answer_ids` before insert, wrap write conflicts into controlled responses, and consider idempotent upsert/delete semantics for votes and submissions. Add tests for duplicate answer IDs and concurrent same-participant writes.

### Medium: SQLite foreign-key enforcement is not enabled — **DONE**

**Fix:** Added a `@event.listens_for(Engine, "connect")` hook in `app/db.py` that issues `PRAGMA foreign_keys=ON` on every connection.



The SQLite engine is created without `PRAGMA foreign_keys=ON` (`app/db.py:10`). SQLAlchemy model declarations include `ondelete="CASCADE"` on many relationships (`app/models.py:29` and similar), but SQLite does not enforce those constraints unless the pragma is enabled per connection. ORM cascades cover some normal object deletes, but direct/bulk operations and invalid inserts can leave orphaned rows.

Recommendation: add a SQLAlchemy connection event to enable foreign keys for SQLite. Add tests that assert `PRAGMA foreign_keys` is `1`, invalid FK inserts fail, and parent deletes cascade at the DB layer.

### Medium: Upload validation trusts filename extension rather than image content — **DEFERRED**

**Reason:** Already flagged in spec's "Deferred (decision needed)" appendix. Adds Pillow as a hard runtime dep — wants a product call before doing it. Current mitigations (auth-only path, 5 MB cap, extension allowlist excluding SVG, strict `Content-Type`/`nosniff`/CORP headers on `/uploads`) leave the residual risk to authenticated admins only, which is acceptable until decision is made.



`upload_image` accepts files based on suffix (`app/main.py:1125`) and writes arbitrary bytes to `/uploads` (`app/main.py:1139`). The upload headers reduce browser execution risk, but the system is still authenticated arbitrary file hosting under image-looking names.

Recommendation: verify image content with a decoder such as Pillow, reject mismatched content, and keep SVG excluded. Add tests for invalid bytes with allowed extensions.

### Medium: WebSocket broadcast can block API responses behind a slow client — **DONE**

**Fix:** `Hub.broadcast` now uses `asyncio.gather` with per-send `asyncio.wait_for(timeout=2.0)`. Failed/timed-out sockets are evicted from the room. Sequential delivery replaced with concurrent fan-out.



`Hub.broadcast` sends to each WebSocket sequentially without a timeout (`app/ws.py:18`), and API handlers await broadcasts after committing. One slow or stalled connection can delay state-changing API responses for the room.

Recommendation: add per-send timeouts, gather sends concurrently, or move broadcast delivery to a background task with bounded failure handling.

## Test Gaps

- Public queued quiz payload redaction.
- Submit-after-reveal rejection.
- Old admin cookie invalidation after password change.
- Concurrent first-run setup.
- Invalid quiz-run source-state transitions.
- Duplicate multi-choice answer IDs and concurrent vote/submit races.
- SQLite foreign-key enforcement.
- Upload content sniffing.
- Slow WebSocket client broadcast behavior.
