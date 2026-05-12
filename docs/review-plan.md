# Multi-Agent Review Plan

Date: 2026-05-12

## Project Read

Prashna is a compact FastAPI and vanilla-JS application for live audience sessions. It supports anonymous Q&A, delegated moderation through a per-session moderator key, projector display, and moderator-run quizzes. The backend is mostly concentrated in `app/main.py`, with SQLAlchemy models in `app/models.py`, cookie auth in `app/auth.py`, SQLite setup in `app/db.py`, and an in-memory WebSocket hub in `app/ws.py`. The frontend is organized as one static HTML/JS page per role under `static/`. The authoritative product behavior is captured in `docs/specs.md`; frontend conventions are captured in `docs/UX.md`.

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
   - Scope: `static/common.js`, `static/index.html`, `static/quizzes.html`, `static/moderator.html`, `static/participant.html`, `static/projector.html`, `static/app.css`, and `tests/ui`.
   - Focus: browser-side correctness, live refresh behavior, stale state, unsafe DOM/URL handling, moderator key handling, accessibility gaps, and UI test coverage.

## Output Files

- `docs/design-review-report.md`
- `docs/critical-code-review-report.md`
- `docs/frontend-live-review-report.md`

## Severity Convention

- High: can leak private/correctness-sensitive data, corrupt historical results, break authorization boundaries, or create production-operability risk.
- Medium: likely correctness, reliability, or maintainability issue with a narrower trigger or lower blast radius.
- Low: important polish or accessibility gap that does not usually compromise core correctness.
