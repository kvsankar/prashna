# Multi-Agent Review Plan

Date: 2026-05-12

## Project Read

Prashna is a compact FastAPI and Vite/TypeScript application for live audience sessions. It supports anonymous Q&A, delegated moderation through a per-session moderator key, projector display, and moderator-run quizzes. The backend is mostly concentrated in `app/main.py`, with SQLAlchemy models in `app/models.py`, cookie auth in `app/auth.py`, SQLite setup in `app/db.py`, and an in-memory WebSocket hub in `app/ws.py`. The frontend is organized as one Vite HTML entrypoint per role under `frontend/`, with page logic in `frontend/src/*.ts`. The authoritative product behavior is captured in `docs/specs.md`; frontend conventions are captured in `docs/UX.md`.

## Review Scheme

The review was split into four roles:

1. Coordinator
   - Built the initial project map.
   - Reconciled findings across reviewers.
   - Wrote the markdown artifacts in `docs/`.

2. Design reviewer
   - Scope: `README.md`, `docs/specs.md`, `docs/UX.md`, `app/models.py`, high-level `app/main.py`, and deployment files.
   - Focus: product lifecycles, role boundaries, persistence/versioning strategy, live update architecture, deployment assumptions.

3. Backend critical reviewer
   - Scope: `app/main.py`, `app/models.py`, `app/auth.py`, `app/db.py`, `app/ws.py`, and `tests/api`.
   - Focus: auth, authorization, data integrity, race conditions, upload handling, lifecycle bugs, WebSocket behavior, and SQLite edge cases.

4. Frontend/live-client reviewer
   - Scope: `frontend/*.html`, `frontend/src/common.ts`, `frontend/src/{index,quizzes,moderator,participant,projector}.ts`, `frontend/src/app.css`, and `tests/ui`.
   - Focus: browser-side correctness, live refresh behavior, stale state, unsafe DOM/URL handling, moderator key handling, accessibility gaps, and UI test coverage.

## Round 2 Re-Review Scheme

The second pass re-used the same review lanes and focused on validating the addressed findings rather than re-reading the entire project from scratch:

1. Fix validation
   - Checked whether prior "DONE" annotations were actually complete in code, tests, and operational behavior.

2. Regression review
   - Looked for places where backend fixes changed contracts that specs or browser pages still assumed.

3. Deployability review
   - Checked whether the security and persistence fixes survive the current SQLite `create_all()` deployment model and an existing local database.

4. Verification
   - Ran the test suite and recorded new uncovered paths in the report test-gap sections.

## Output Files

- `docs/design-review-report.md`
- `docs/critical-code-review-report.md`
- `docs/frontend-live-review-report.md`

## Severity Convention

- High: can leak private/correctness-sensitive data, corrupt historical results, break authorization boundaries, or create production-operability risk.
- Medium: likely correctness, reliability, or maintainability issue with a narrower trigger or lower blast radius.
- Low: important polish or accessibility gap that does not usually compromise core correctness.
