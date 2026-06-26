# Backend/Data/Auth/Test Exploration - 2026-06-25

Scope: exploration and planning only. I did not implement product/code fixes.

Repo surfaces read: `README.md`, `docs/specs.md`, `CLAUDE.md`, `app/main.py`, `app/auth.py`, `app/db.py`, `app/models.py`, `app/ws.py`, `app/oauth.py`, `app/ratelimit.py`, `tests/api/*`, `pyproject.toml`, `Dockerfile`, and `deploy/*`.

## Architecture Map

### Runtime shape

- FastAPI app entrypoint: `app/main.py`.
  - Startup runs `init_db()` through the FastAPI lifespan at `app/main.py:96`.
  - Security headers are injected by `SecurityHeaders` at `app/main.py:111`.
  - Uploads are served by `StaticFiles` from `UPLOADS` at `app/main.py:138`.
  - Vite build output is served only when `frontend/dist` exists at `app/main.py:141`.
- Backend is intentionally mostly one file. `CLAUDE.md` still describes `app/main.py` as "all FastAPI routes + WebSocket endpoint"; current file is 1,942 lines and owns admin, session, participant, feedback, query, quiz, upload, quiz-run, and WebSocket routes.
- Persistence is sync SQLAlchemy 2 over SQLite:
  - Engine and `SessionLocal`: `app/db.py:12`, `app/db.py:41`.
  - Per-connection SQLite pragmas: foreign keys, WAL, busy timeout, and `synchronous=NORMAL` at `app/db.py:27`.
  - `init_db()` calls `Base.metadata.create_all()` and then a local additive migration bridge at `app/db.py:56`.
- Deploy shape:
  - Docker runtime uses `PRASHNA_DB_PATH=/data/prashna.db` and serves through uvicorn at `Dockerfile:47`.
  - Compose binds `/opt/prashna/data` and `/opt/prashna/uploads` at `deploy/docker-compose.yml:15`.
  - `deploy/env.example` sets `PRASHNA_TRUSTED_PROXY_HOPS=1` for nginx-fronted rate limiting.

### Data model

- `User`: admin identity with `username`, bcrypt `password_hash`, optional `github_id`, and `session_version` for cookie invalidation (`app/models.py:25`).
- `Session`: live event with `code`, `mod_key`, owner, lifecycle status, participant base URL, and cascaded children (`app/models.py:43`).
- `Participant`: anonymous per-session identity keyed by `(session_id, voter_token)` (`app/models.py:68`).
- `Query` and `QueryVote`: Q&A entries, soft removal, response state, and one vote per participant (`app/models.py:83`, `app/models.py:138`).
- `SessionFeedback` and `SessionFeedbackVersion`: current feedback row plus append-only versions (`app/models.py:102`, `app/models.py:120`).
- `Quiz`, `Question`, `Answer`: mutable quiz template tree owned by a user (`app/models.py:151`, `app/models.py:173`, `app/models.py:195`).
- `QuizVersion*`: immutable snapshot captured lazily on launch (`app/models.py:210`, `app/models.py:227`, `app/models.py:246`).
- `QuizRun`: playthrough inside a session. Storage enforces at most one live run per session via partial unique index `uq_session_live_run` (`app/models.py:260`).
- `QuizSubmission`: per-answer rows, with unique `(quiz_run_id, question_id, answer_id, participant_id)` and an index for tallying (`app/models.py:292`).

### Auth paths

- Admin password auth:
  - Cookie name is `prashna_admin` (`app/auth.py:21`).
  - `issue_session()` signs `user_id:session_version`, sets `HttpOnly`, `SameSite=Lax`, and conditional `Secure` (`app/auth.py:65`).
  - `current_admin()` and `optional_admin()` reject stale cookies when `User.session_version` no longer matches (`app/auth.py:105`, `app/auth.py:119`).
  - First-run setup is guarded by `_setup_lock` around check-plus-insert (`app/main.py:621`, `app/main.py:629`).
  - Password change bumps `session_version` and reissues a cookie (`app/main.py:673`).
- GitHub OAuth admin auth:
  - Enabled only when client id, client secret, and allowlist are all configured (`app/oauth.py:46`).
  - Signed state uses the same app secret and expires after 10 minutes (`app/oauth.py:56`).
  - Callback find-or-creates by immutable GitHub id in `app/main.py:573` and `_create_github_admin()` at `app/main.py:599`.
- Moderator auth:
  - Per-session `mod_key` is generated from a UUID token prefix when creating a session (`app/main.py:731`).
  - Moderator-gated routes call `require_mod_or_owner()`; either owner admin cookie or `X-Mod-Key` succeeds (`app/main.py:197`).
  - Owner-only session metadata paths call `require_session_owner()` (`app/main.py:214`), including title update and participant base URL (`app/main.py:750`, `app/main.py:773`).
- Participant auth:
  - Anonymous `voter_token` cookie is intentionally non-HttpOnly for frontend "mine" checks (`app/main.py:169`).
  - `current_participant()` creates or reuses a `(session, voter_token)` row and handles concurrent first-touch integrity races (`app/main.py:219`).

### Live update path

- State-changing routes call `broadcast_session(s, "<kind>")` (`app/main.py:498`).
- WebSocket endpoint is `/ws/sessions/{code}` at `app/main.py:1921`.
  - Origin must match `Host` if an Origin header is present (`app/main.py:1923`).
  - Unknown session codes close with 4404 (`app/main.py:1929`).
  - Room key is `session:{CODE}` (`app/main.py:1933`).
- `app/ws.py` is an in-memory room hub:
  - `Hub.rooms` is a `defaultdict(set)` (`app/ws.py:11`).
  - Broadcast fans out concurrently and drops sockets that error or exceed a 2s send timeout (`app/ws.py:24`).
- Clients receive hint payloads such as `{"type": "query_new"}` and refetch; README documents this at `README.md:77`.

## Highest-Risk Seams To Review Critically

### 1. Auth boundary drift across owner, moderator delegate, and public reads

Primary anchors:

- `require_mod_or_owner()` at `app/main.py:197`.
- `require_session_owner()` at `app/main.py:214`.
- Public `get_session()` at `app/main.py:738`.
- Session title/base URL owner-only routes at `app/main.py:750` and `app/main.py:773`.
- Moderator query actions at `app/main.py:1151`, `app/main.py:1172`.
- Quiz run launch/control routes at `app/main.py:1644`, `app/main.py:1686`, `app/main.py:1713`, `app/main.py:1743`, `app/main.py:1766`, `app/main.py:1784`, `app/main.py:1803`.

Why this is high-risk:

- The spec explicitly says admin is a strict superset of moderator and moderator delegates use `mod_key`, but some operations are intentionally owner-only. This creates a subtle matrix rather than a single auth rule.
- Public participant/projector reads should not leak `mod_key`, quiz correctness, removed queries, or queued question detail.
- `list_queries()` and `list_quiz_runs()` both create/refresh participant identity even for read paths (`app/main.py:1048`, `app/main.py:1595`); this is correct by current design but should be stress-reviewed for unintended row growth and rate-limit behavior.

Execution targets:

- Verify every route that mutates session metadata rejects delegate `mod_key`.
- Verify every moderator route accepts owner cookie without `X-Mod-Key`.
- Verify non-owner admins get 403 or 404 consistently as documented.
- Verify public session reads expose only safe metadata.
- Verify frontend/moderator behavior matches owner-only base URL rules in `docs/specs.md` around UC-M-11.

### 2. SQLite schema evolution and deployment docs

Primary anchors:

- `init_db()` and additive migration bridge: `app/db.py:56`, `app/db.py:62`.
- Additive columns/indexes list: `app/db.py:70`.
- README still says "no migrations yet" and delete `prashna.db` if models change incompatibly at `README.md:135`.
- `CLAUDE.md` still says "Database migrations: None" while code has an additive bridge.
- Deploy persists SQLite and uploads under `/opt/prashna` (`deploy/README.md:55`, `deploy/docker-compose.yml:15`).

Why this is high-risk:

- `create_all()` does not provide a complete migration story for existing DBs, and the local bridge covers only a small list of additive columns and one index.
- New tables, missing indexes, changed nullability, changed constraints, and data backfills need explicit review. Existing persistent deployments are now part of the supported reality because deploy docs instruct backing up `/opt/prashna/data/prashna.db`.
- Documentation disagrees on whether operators should expect migrations. This matters for release safety even if the current additive bridge is adequate.

Execution targets:

- Start from an older SQLite DB shape if possible and verify `init_db()` upgrades it without ORM failures.
- Inspect whether storage-level indexes/constraints expected by `models.py` exist on an existing DB after `init_db()`.
- Compare `README.md`, `CLAUDE.md`, `deploy/README.md`, and `app/db.py` for operator-facing consistency.
- Add a smoke test that creates an old-style DB missing known additive columns, imports the app, runs lifespan/init, and exercises auth/quiz paths.

### 3. Quiz versioning, live-run concurrency, and historical correctness

Primary anchors:

- Publish validation: `_validate_quiz_publishable()` at `app/main.py:421`.
- Lazy snapshot: `_ensure_current_version()` at `app/main.py:453`.
- Create run: `create_quiz_run()` at `app/main.py:1644`.
- Start run and partial unique index catch: `start_quiz_run()` at `app/main.py:1686`.
- Result serialization: `serialize_quiz_run()` at `app/main.py:337`, `quiz_run_results()` at `app/main.py:1552`.
- Storage invariant: `QuizRun.__table_args__` at `app/models.py:260`.

Why this is high-risk:

- The product promise is that editing a quiz template never mutates historical runs (`README.md:12`, `README.md:69`).
- `_ensure_current_version()` catches an `IntegrityError`, rolls back, and returns the latest version. That should be reviewed under concurrent launches and concurrent edits so it does not attach a run to a stale or partially captured version.
- The one-live-run rule depends on both application checks and a partial unique index. SQLite concurrency, transactions, and route-level async/sync mixing should be exercised.

Execution targets:

- Concurrently queue the same edited ready quiz and verify one or more runs all point to the intended immutable version.
- Concurrently start two queued runs for one session and verify exactly one live run plus a stable 409 response.
- Verify edit-after-run does not alter `quiz_run_results()` payload.
- Verify poll questions (`graded=False`) never leak correctness on participant/projector paths.

### 4. Live-update reliability and stale UI failure modes

Primary anchors:

- `broadcast_session()` at `app/main.py:498`.
- `Hub.broadcast()` at `app/ws.py:24`.
- WebSocket endpoint at `app/main.py:1921`.
- Broadcast contract tests in `tests/api/test_system.py:23`.

Why this is high-risk:

- The WebSocket carries only refetch hints, so correctness depends on every state-changing route broadcasting the right kind.
- The hub is process-local. It is compatible with the current single-process guidance, but a deploy/runtime change to multiple workers would silently split rooms.
- Broadcasts happen after DB commits on most paths. Any missed broadcast yields stale moderator/projector/participant views even if the API state is correct.

Execution targets:

- Audit every route that mutates `Session`, `Participant`, `Query`, `SessionFeedback`, `QuizRun`, or `QuizSubmission` for a matching broadcast.
- Verify client-visible state changes still refresh when multiple sockets are connected and one socket is slow or disconnects.
- Verify WebSocket rejection behavior behind nginx/Vite proxy: same-origin, no-origin, and mismatched-origin cases.
- Decide whether process-local WebSocket hub needs an explicit deployment guard against uvicorn worker count > 1.

### 5. Upload safety and static serving

Primary anchors:

- Upload constraints constants: `MAX_UPLOAD_BYTES` and `ALLOWED_IMAGE_EXTS` in `app/main.py:34`.
- `upload_image()` at `app/main.py:1488`.
- Upload security headers in `SecurityHeaders` at `app/main.py:111`.
- Tests for upload headers and filename constraints at `tests/api/test_system.py:175`.
- Deferred spec item for content sniffing: `docs/specs.md` deferred appendix.

Why this is high-risk:

- Upload validation is extension and size based. Content sniffing is explicitly deferred.
- Files are served back under `/uploads` with a stricter CSP and `nosniff`, which is good, but should be verified in the real built/deployed path too.
- `file.size` is checked when present, but runtime safety relies on chunked reading and the 5 MB cap.

Execution targets:

- Upload files with mismatched content types/extensions and verify current accepted/rejected behavior matches the product decision.
- Verify no path traversal is possible through filename because storage name is generated from UUID.
- Verify nginx does not override or weaken upload response headers.
- Verify large upload behavior under both TestClient and deployed uvicorn/nginx limits.

### 6. Rate limiting and trusted proxy assumptions

Primary anchors:

- `_client_ip()` at `app/main.py:76`.
- Limiter construction and route constants at `app/main.py:50`.
- `TokenBucketLimiter` at `app/ratelimit.py:34`.
- Deploy env `PRASHNA_TRUSTED_PROXY_HOPS=1` in `deploy/env.example`.
- Rate-limit tests in `tests/api/test_ratelimit.py`.

Why this is high-risk:

- Rate limiting is in-memory and single-process by design. It does not protect across multiple workers or multiple app instances.
- Client IP extraction is secure only if `TRUSTED_PROXY_HOPS` matches the actual proxy topology.
- Tests disable rate limiting globally by default in `tests/api/conftest.py`, so routes can regress unless dedicated rate-limit tests cover them.

Execution targets:

- Verify nginx sets the forwarded headers that uvicorn/FastAPI actually expose to `_client_ip()`.
- Verify spoofed `X-Forwarded-For` prefixes are ignored with one trusted hop.
- Exercise login, new participant, ask, vote, quiz submit, and feedback buckets with limiter enabled.
- Decide whether WebSocket connects remaining unthrottled is acceptable.

### 7. Documentation/spec drift that affects review confidence

Primary anchors:

- README project layout still lists `static/` even current repo uses `frontend/` and Vite (`README.md:112`).
- README status says "no migrations yet" even `app/db.py` applies additive migrations (`README.md:135`, `app/db.py:62`).
- README deferred list still names rate limiting and upload content-sniffing together; rate limiting is implemented while content sniffing remains deferred (`README.md:140`, `docs/specs.md:1674`).
- `CLAUDE.md` has current Vite/frontend guidance but still says no migrations.

Why this is high-risk:

- The API tests are mapped to `docs/specs.md`, so stale docs can make reviewers target the wrong behavior.
- Deployment docs drive operator action. Schema and rate-limit drift there can turn otherwise correct code into production failure.

Execution targets:

- Treat `docs/specs.md` as the primary behavior source, but explicitly flag any README/CLAUDE/deploy drift found during execution.
- Use tests as the executable spec only after checking that test names still map to the current UC bullets.

## Likely Failure Modes To Target

- Wrong auth class on a route: delegate mod can perform owner-only action, or owner admin is blocked from moderator action.
- Public read leaks: queued quiz question/answers, correctness, removed queries, or session `mod_key` appear on unauthenticated paths.
- Participant row amplification: polling `/queries`, `/quiz_runs`, `/presence`, or `/me` with rotating cookies creates unbounded rows or bypasses intended throttles.
- Existing DB upgrade failure: old SQLite DB imports fine but later auth/quiz route hits missing column/index/constraint.
- Schema bridge false confidence: additive columns are covered, but unique/partial indexes or new tables are absent on old DBs.
- Race at first-run setup, participant first-touch, feedback upsert, query vote toggle, quiz version creation, or live-run start.
- Missed WebSocket broadcast after a successful write, causing stale projector/moderator/participant UI.
- Broadcast-before-refresh mismatch: API returns stale relationship data after commit/rollback or clients refetch before committed state is visible.
- Session lifecycle mismatch: ending a session while a run is live, submitting after reveal, deleting closed run, or deleting live session has wrong status/error contract.
- Upload accepted by extension but rendered dangerously in browser or through nginx; headers differ between TestClient and deployment.
- OAuth fallback failure: GitHub-created admin with empty password hash breaks password-login assumptions, session status, or multi-admin ownership filters.
- Trusted proxy misconfiguration collapses all clients to one IP or accepts spoofed forwarded headers.
- Test fixture masking: `tests/api/conftest.py` disables rate limiting and truncates tables, so behavior relying on lifespan/init/deploy env may need dedicated tests.

## Recommended Verification Commands

Baseline local checks:

```bash
uv run pytest tests/api/
uv run pytest tests/api/test_admin_auth.py tests/api/test_moderator_auth.py tests/api/test_sessions.py
uv run pytest tests/api/test_quiz_runs.py tests/api/test_quiz_submissions.py tests/api/test_system.py
uv run pytest tests/api/test_ratelimit.py tests/api/test_github_auth.py
uv run pytest
npm run typecheck
npm run lint
```

Focused commands for execution review:

```bash
uv run pytest tests/api/test_system.py -q
uv run pytest tests/api/test_ratelimit.py -q
uv run pytest tests/api/test_admin_auth.py::test_uc_a_01_concurrent_setup_different_usernames -q
uv run pytest tests/api/test_participants.py::test_uc_p_02_concurrent_first_touch_single_row -q
uv run pytest tests/api/test_quiz_runs.py::test_uc_x_06_concurrent_race -q
uv run pytest tests/api/test_quiz_runs.py::test_uc_m_04_another_live_409 -q
```

Manual/deploy-oriented probes to add or run carefully:

```bash
PRASHNA_DB_PATH=/tmp/prashna-old-shape.db uv run python -c 'from app.db import init_db; init_db(); print("init ok")'
sqlite3 /tmp/prashna-old-shape.db '.schema users'
sqlite3 /tmp/prashna-old-shape.db '.schema quiz_runs'
docker build -t prashna-review .
docker run --rm -p 8000:8000 -e PRASHNA_SECRET_KEY=review-secret prashna-review
```

Notes:

- I did not run these commands during this exploration pass; they are recommended for the execution reviewer.
- UI smoke is still useful because many backend risks manifest as stale live UI:

```bash
npm run build
uv run pytest tests/ui/
```

## Test Surface Map

- `tests/api/test_admin_auth.py`: setup/login/logout/password change, including concurrent setup.
- `tests/api/test_moderator_auth.py`: mod-key and owner-cookie authorization plus session start/end.
- `tests/api/test_sessions.py`: create/list/update/base URL/delete/session inline moderation paths.
- `tests/api/test_participants.py`: participant identity, concurrent first-touch, presence, ended-session restrictions.
- `tests/api/test_queries.py`: ask/vote/list/respond/remove/hard-delete.
- `tests/api/test_feedback.py`: feedback upsert/versioning/summary/auth/broadcast.
- `tests/api/test_quizzes.py`: quiz template CRUD, publish validation, upload.
- `tests/api/test_quiz_runs.py`: queue/start/advance/live counts/reveal/close/delete/results/versioning races.
- `tests/api/test_quiz_submissions.py`: participant quiz visibility, answer submission, reveal/closed results, live counts.
- `tests/api/test_system.py`: WebSocket broadcasts, WS rejections, security headers, upload constraints, storage invariants, secret-key lifecycle.
- `tests/api/test_ratelimit.py`: limiter internals and route throttles with limiter enabled.
- `tests/api/test_github_auth.py`: optional GitHub OAuth configuration, state, allowlist, user creation, password fallback coexistence.

## Suggested Execution Review Order

1. Run the focused API tests for auth, sessions, quiz runs, submissions, system, rate limiting, and GitHub auth.
2. Audit route-by-route auth classes against `docs/specs.md` conventions, especially owner-only versus mod-or-owner paths.
3. Build an old-shape SQLite DB test for additive migrations and inspect indexes/constraints after `init_db()`.
4. Stress concurrency seams: first setup, participant first-touch, feedback upsert, vote toggle, quiz version capture, and live-run start.
5. Audit every mutating route for the correct `broadcast_session()` hint and verify the frontend refetches the affected state.
6. Run a built frontend/UI pass to catch stale live-update behavior that API tests cannot see.
7. Reconcile docs drift after code findings are known; do not let stale README/CLAUDE wording decide product behavior without checking `docs/specs.md`.
