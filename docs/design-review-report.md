# Design Review Report

Date: 2026-05-12

## Project Understanding

Prashna is a self-hosted live Q&A and quiz tool for sessions with an audience. The core product shape is role-based: admin, delegated moderator, anonymous participant, and public projector. The main domain objects are lifecycle-driven: `Session` moves `planning -> live -> ended`, `Quiz` moves `draft -> ready`, and `QuizRun` moves `queued -> live -> closed`. Quiz templates are mutable, while `QuizVersion` snapshots preserve historical run reports.

The design is intentionally simple: SQLite persistence, a single FastAPI process, static role-specific browser clients, and WebSocket refresh hints that cause clients to refetch.

## Round 2 Re-Review (2026-05-12)

### High: Schema evolution is now blocking a security fix rollout — **DONE**

**Fix:** Lightweight additive migrator in `app/db.py` (`_apply_additive_migrations`) runs after `create_all` and adds missing columns via `ALTER TABLE`. Targeted at `users.session_version` for now; the same list grows as we add columns. Alembic still deferred.



The earlier migration concern was deferred because Prashna is pre-launch and can recreate `prashna.db`. The second-pass code review found this is no longer just a future production concern: the password-cookie invalidation fix added `users.session_version`, but existing SQLite databases are not upgraded by `create_all()`. A database created before the fix can fail admin auth/status paths after deploy.

Design decision needed: either keep the pre-launch "delete and recreate the DB" workflow and document this change as a breaking local-data reset, or add a tiny startup migration path for additive SQLite columns until Alembic is adopted. The current middle ground is fragile because the app claims backward cookie compatibility while the schema is not backward compatible.

### Medium-High: Role-boundary fix is not reflected across product surfaces — **DONE**

**Fix:** Moderator page hides the Base URL editor for delegates (boot detects admin-owner via `/api/admin/status`). UC-M-11 rewritten in `docs/specs.md` to describe the two-tier view (owner edits, delegate reads).



The backend now treats session rename, participant base URL changes, and hard-delete as owner-only. That matches the design direction, but the moderator experience and spec are still split: `docs/specs.md:629` and `docs/specs.md:888` still describe moderator-key access for now-owner-only operations, and the moderator page still exposes the base URL editor to delegates.

Recommendation: make the product rule explicit in one place and drive both API tests and UI from it. If delegated moderators are intentionally narrower, hide owner-only controls when the page is opened with only `X-Mod-Key`.

### High: Public first-run setup still needs a real bootstrap invariant — **DEFERRED**

**Reason:** Same answer as the unchanged D5: per the localhost+ngrok workflow, the public-setup window isn't a real risk today. The hosted/SaaS distribution path will need a proper DB-level singleton + setup-token. Tracked together in `docs/todo.md`.



The first-run setup race fix improved conflict handling but did not establish a database-level singleton. Combined with the intentionally deferred public-claim workflow, setup remains the main operational footgun before any public or shared deployment.

Recommendation: before public hosting, solve this at the workflow and invariant levels: private/local bootstrap is acceptable for the current ngrok workflow, but a hosted service should require a setup token, CLI bootstrap, or locked bootstrap row.

## Findings

### High: Quiz-run and session lifecycles are not enforced centrally — **PARTIALLY DONE**

**Fix:** Added per-transition source-state guards on `advance`/`reveal`/`close`/`live_counts`. `end_session` now refuses (400) while any QuizRun is still `live` — moderator must explicitly close the run before ending the session (rather than auto-closing, which we judged surprising for live audiences). **Deferred** the broader "extract a central state-machine service" recommendation — `app/main.py` is still a single file by design and the per-route guards cover the correctness gap.



The spec treats closed quiz runs as historical records and says ended sessions should keep the last quiz result visible read-only (`docs/specs.md:770`, `docs/specs.md:1196`). In code, ending a session only sets `Session.status = "ended"` (`app/main.py:609`) and does not close, freeze, or reject a still-live `QuizRun`.

The individual quiz-run transition routes also lack a common state machine. `advance`, `live_counts`, `reveal`, and `close` can be called against statuses that should not accept them (`app/main.py:1344`, `app/main.py:1372`, `app/main.py:1389`, `app/main.py:1405`). This lets moderator-capable callers mutate queued or closed runs after the fact, weakening the permanent-record model.

Recommendation: add a central transition layer for `Session` and `QuizRun`. Explicitly decide whether ending a session blocks while a quiz is live, auto-closes the live quiz, or marks it abandoned. Then enforce allowed source states for every route.

### High: Delegated moderator authority is too broad — **DONE**

**Fix:** Tightened `PATCH /api/sessions/{code}` (rename), `PATCH /api/sessions/{code}/base_url`, and `DELETE /api/sessions/{code}/queries/{id}` (hard-delete) to `require_session_owner` — admin cookie only. `mod_key` no longer carries those capabilities. Tests updated (e.g. `test_uc_m_01_patch_session_is_owner_only`).



The docs define moderator as a subset role with no quiz authoring, session create/delete, or global reports (`docs/specs.md:13`). In implementation, the same `require_mod_or_owner` helper gates broad session operations (`app/main.py:127`). A moderator-key holder can change the session title, change participant base URL, and hard-delete queries (`app/main.py:543`, `app/main.py:565`, `app/main.py:832`).

The hard-delete route is documented as an admin escape hatch with no standard UI (`docs/specs.md:1434`), but it is available to any valid moderator key.

Recommendation: split "moderator operation" from "owner/admin operation." Make session metadata, hard-delete, moderator-key rotation, and historical/report-impacting actions owner-only unless the product explicitly grants them to delegates.

### High: Production persistence has no migration path — **DEFERRED / ACTIVE ROLLOUT RISK**

**Reason:** Product call. Prashna is still pre-launch; the README explicitly says "delete `prashna.db` and recreate" is fine until real user data exists. Alembic introduces a new dep, a new workflow (migrations as commits), and onboarding cost. Round 2 found the new `users.session_version` column turns this into an immediate rollout risk for any existing local DB unless the operator resets the database or the app performs a small additive migration.



The README says schema changes currently require deleting `prashna.db` (`README.md:137`). The app initializes with `Base.metadata.create_all()` only (`app/db.py:30`), while deployment persists SQLite and uploads on volumes (`deploy/docker-compose.yml:14`, `deploy/README.md:57`).

That is workable pre-launch, but it is the main blocker to safe open-source or hosted operation with real user data.

Recommendation: introduce Alembic migrations before production data matters. Pair deploy updates with database backup guidance and prefer tagged container versions over unconditional `latest` rollouts.

### Medium: Live updates are single-process and can miss recovery after reconnect — **PARTIALLY DONE**

**Fix:** `openLiveSocket` now forces a refetch on every reconnect after the first (`everConnected` flag in `static/common.js`), via a synthetic `{type: "reconnect"}` callback. The multi-worker / Redis pub-sub recommendation is **deferred** — single-process is intentional for the current single-container deploy.



The WebSocket hub is in-memory (`app/ws.py:5`), matching the current single-container deployment but not multiple workers or replicas. The client reconnect helper reopens the socket but does not force a full refetch after reconnect (`static/common.js:59`). The docs describe recovery as waiting for the next broadcast (`docs/specs.md:1213`), which means a projector or participant page can remain stale indefinitely after the only relevant broadcast was missed.

Recommendation: refetch immediately after every successful reconnect. Document that the current hub is single-process only, and move to Redis/Postgres pub-sub before enabling multiple workers or replicas.

### Medium: First-run admin setup is operationally fragile — **DEFERRED**

**Reason:** Open product question. Options are (a) one-time setup token printed at container startup, (b) CLI bootstrap, (c) require running app in a "private bootstrap" mode. Picked none yet — needs user decision. Tracking as open question for the wrap-up. Round 2 found the same-username conflict path is safer, but the different-username concurrent setup race is still not fully closed (see C4 in critical review).



The first visitor creates the admin account (`README.md:30`). If the public service is reachable before the intended operator claims it, the setup endpoint becomes a public account-claim path.

Recommendation: require a one-time setup token, offer a CLI/admin bootstrap command, or keep the service private until setup completes.

## Maintainability Notes

- `app/main.py` currently owns routing, serialization, lifecycle logic, upload handling, WebSocket endpoint handling, and quiz version capture. This makes route-by-route drift likely as features grow.
- Statuses are raw strings in models and routes (`app/models.py:31`, `app/models.py:97`, `app/models.py:212`). CHECK constraints are already listed as deferred in the spec (`docs/specs.md:1448`).
- `_ensure_current_version` validates, snapshots, handles conflicts, and commits inside one helper (`app/main.py:338`). That makes atomic composition with quiz-run creation harder.

## Recommended Next Design Moves

1. Extract domain services for session lifecycle, quiz-run lifecycle, and quiz version capture.
2. Add explicit permission helpers for owner-only, moderator-action, and public-read operations.
3. Introduce migrations and a basic operational backup/restore story.
4. Make reconnect refetch mandatory and document the single-process WebSocket limit.
5. Add setup-token or private bootstrap support before public deployment.
