# Backend/Data/Auth/Deploy Critical Review - 2026-06-25

## Resolution status

Fixed in the follow-up TDD pass:

- Additive SQLite migration bridge now covers the reviewed old-shape DB gaps
  and has an old-schema regression test.
- `DELETE /api/sessions/{code}` now broadcasts `session_deleted`.
- README/CLAUDE/todo migration guidance now describes the supported additive
  bridge and remaining Alembic boundary.

## Scope and verification performed

Reviewed the current checkout for the backend/data/auth/deploy lane, using:

- Planning/spec inputs: `docs/reviews/2026-06-25/critical-code-review-plan.md`, `docs/reviews/2026-06-25/exploration-backend-and-data.md`, `docs/specs.md`, `CLAUDE.md`.
- Backend code: `app/main.py`, `app/auth.py`, `app/db.py`, `app/models.py`, `app/ws.py`, `app/oauth.py`, `app/ratelimit.py`.
- Tests/docs: `tests/api/*`, `README.md`, `deploy/README.md`, `deploy/docker-compose.yml`, `deploy/env.example`, `deploy/nginx-prashna.conf`.

Commands attempted:

```bash
uv run pytest tests/api/
```

Subagent result: failed before running tests because sandboxed `uv` could not write its cache:

```text
error: Could not acquire lock
  Caused by: Could not create temporary file
  Caused by: Read-only file system (os error 30) at path "/home/sankar/.cache/uv/.tmpoTrG3x"
```

Parent verification after the subagent pass reran the same command with
escalation for the uv cache write:

```bash
uv run pytest tests/api/
```

Result: `291 passed, 3 skipped` in 60.33s.

## Findings

### High - Persisted SQLite deploys can still break on additive schema changes not covered by the startup bridge

**Evidence:** `app/db.py:56-59` calls `Base.metadata.create_all()` and then `_apply_additive_migrations()`. The bridge only adds `users.session_version`, `users.github_id`, `quiz_questions.graded`, `quiz_version_questions.graded`, and `ix_users_github_id` (`app/db.py:70-83`). Current models require other deploy-relevant columns/indexes/invariants, including `sessions.participant_base_url` (`app/models.py:54-56`), `quiz_runs.show_live_counts` and `uq_session_live_run` (`app/models.py:263-282`), and `ix_qsub_run_question` (`app/models.py:301-305`). Deploy docs explicitly persist `/opt/prashna/data/prashna.db` (`deploy/README.md:57-62`, `deploy/docker-compose.yml:14-16`).

**Failure mode:** An existing deployed SQLite database created before one of these model additions may start successfully but fail at runtime when ORM routes select/insert missing columns, or silently miss storage-level invariants/indexes that `create_all()` will not retrofit. For example, an old DB missing `quiz_runs.show_live_counts` can fail quiz-run serialization/update paths; an old DB missing the partial unique index can lose the one-live-run storage invariant under race.

**Suggested fix/test:** Either adopt a real migration path or make the additive bridge comprehensive for every supported post-deploy additive change: columns plus indexes/constraints where SQLite can support them. Add a regression test that creates an old-shape SQLite file, runs `init_db()`, checks `PRAGMA table_info`/`PRAGMA index_list`, and exercises admin status, session listing, quiz launch/start, live-count toggling, and GitHub lookup.

### Medium - Session deletion is the only audited session mutation that does not broadcast a live-update hint

**Evidence:** `CLAUDE.md:183-185` says every state-changing route ends with `broadcast_session(s, "<kind>")`. Most session/query/quiz/feedback mutations do so after commit, e.g. title/base URL (`app/main.py:768-795`), lifecycle (`app/main.py:810-832`), query deletion (`app/main.py:1211-1214`), and quiz-run deletion (`app/main.py:1814-1817`). `DELETE /api/sessions/{code}` deletes and commits without any broadcast (`app/main.py:836-854`). Broadcast tests cover many mutations in `tests/api/test_system.py:23-143`, but not full session deletion.

**Failure mode:** A participant/projector/moderator page already connected to a session that the owner deletes receives no hint to refetch/redirect. It can remain on stale local state until the next polling/manual refresh path, even though API reads for the session now 404.

**Suggested fix/test:** Decide the expected product behavior for deleted active pages. If deletion should be live-observable, make the route async, broadcast a `session_deleted` or existing `session_state` hint before/after commit as appropriate, and add a WebSocket contract test. If deletion intentionally has no live contract, document that exception in `CLAUDE.md`/`docs/specs.md`.

### Medium - Operator docs contradict the current persisted-data and migration reality

**Evidence:** `README.md:135-143` says the app is pre-launch, has "no migrations yet", and suggests deleting `prashna.db` for incompatible model changes; `CLAUDE.md:195-199` says the same. Current code has a partial additive migration bridge (`app/db.py:62-94`). Deploy docs instruct operators to back up the persistent SQLite DB and uploads (`deploy/README.md:57-62`), and compose mounts `/opt/prashna/data` to `/data` (`deploy/docker-compose.yml:14-16`).

**Failure mode:** Reviewers/operators get mixed instructions: preserve production data, but also delete the DB when models drift, while the code offers a partial migration bridge that may create false confidence. That increases release risk around any model change touching persisted SQLite data.

**Suggested fix/test:** Align `README.md`, `CLAUDE.md`, `deploy/README.md`, and `app/db.py` around one supported policy: either "additive bridge is part of deploy support; update it and test old DBs for every model addition" or "DB reset is required for specific releases; document the breaking release and backup/restore path."

## Non-findings / verified OK

- **Moderator auth matrix:** Owner-only routes for session title/base URL and hard query delete use `auth.current_admin` plus `require_session_owner` (`app/main.py:750-783`, `app/main.py:1196-1214`); moderator routes use `require_mod_or_owner` (`app/main.py:197-211`). Tests cover owner cookie and mod-key behavior in `tests/api/test_moderator_auth.py:10-57` and `tests/api/test_sessions.py:197-213`.
- **Public queued-run payload safety:** `serialize_quiz_run()` keeps `current_question` null for non-moderator queued runs (`app/main.py:365-370`), matching the spec at `docs/specs.md:1187-1189`.
- **Correct-answer leakage controls:** Non-mod live runs omit `is_correct` until reveal/close, and poll questions never expose correctness (`app/main.py:347-385`, `tests/api/test_quiz_submissions.py:221-282`).
- **Submit-after-reveal:** Participant submissions are blocked after reveal (`app/main.py:1861-1865`), matching `docs/specs.md:1225`.
- **Rate limiting and trusted proxy basics:** Client IP extraction uses trusted hop count from the right side of `X-Forwarded-For` (`app/main.py:76-90`), nginx sets `X-Forwarded-For` (`deploy/nginx-prashna.conf:28-31`), deploy example sets `PRASHNA_TRUSTED_PROXY_HOPS=1` (`deploy/env.example:5-7`), and tests cover the main buckets (`tests/api/test_ratelimit.py:77-193`).
- **Upload safety baseline:** Uploads are admin-only, extension/size capped, stored under UUID filenames, and served with strict `/uploads` headers (`app/main.py:111-138`, `app/main.py:1488-1508`, `tests/api/test_system.py:177-228`). Content sniffing remains an acknowledged deferred product/security decision.

## Test gaps / residual risks

- API verification is green for the current checkout (`291 passed, 3 skipped`), but the initial sandboxed `uv` invocation failed on cache writes; future automated review runs need either a writable uv cache or approved escalation.
- Missing old-SQLite-shape migration smoke tests are the largest backend deploy gap.
- Broadcast coverage is strong for most mutation routes but omits full session deletion.
- Existing rate-limit tests re-enable the limiter selectively; the suite default disables it in `tests/api/conftest.py:25-28`, so new guarded routes need explicit rate-limit tests.
- WebSocket hub and rate limiter are in-process only. This is consistent with current single-process docs, but remains a deploy risk if uvicorn workers/replicas are introduced.
