# Critical Code Review Plan - 2026-06-25

This review follows the live checkout, not only prior reports. The planning
pass used two subagents:

- `exploration-backend-and-data.md` for backend, data, auth, deployment, and
  API test surfaces.
- `exploration-frontend-and-ux.md` for Vite frontend, UX-system alignment,
  browser clients, live refresh, and UI tests.

## Review Standard

Findings must be actionable defects or release risks, with file/function
anchors and a concrete failure mode. Prefer current evidence from code,
tests, docs, or local verification. Avoid listing deferred product decisions
as defects unless the current code/docs make the shipped behavior ambiguous or
unsafe.

Severity guide:

- **Critical**: data loss, auth bypass, public secret/correct-answer leak, or
  deploy blocker with no reasonable workaround.
- **High**: likely production failure, broken role contract, stale live UI
  under normal use, or existing-data incompatibility.
- **Medium**: real behavioral drift, important missing verification, or
  accessibility/browser issue that can block a meaningful audience segment.
- **Low**: cleanup/documentation drift that can mislead maintainers but does
  not directly break the app.

## Execution Lanes

### 1. Backend, Data, Auth, And Deploy

Owned report: `backend-data-auth-critical-review.md`.

Focus areas:

- Route auth matrix: owner-only vs moderator delegate vs public reads.
- Public payload safety: `mod_key`, removed queries, queued quiz content,
  correct answers, feedback author data.
- SQLite additive migration bridge and consistency with persisted deploy data.
- Quiz versioning and one-live-run invariants under race or stale state.
- Broadcast coverage for all mutating routes.
- Upload safety, rate limiting, trusted proxy assumptions, and deployment docs.

Recommended verification:

```bash
uv run pytest tests/api/
uv run pytest tests/api/test_admin_auth.py tests/api/test_moderator_auth.py tests/api/test_sessions.py
uv run pytest tests/api/test_quiz_runs.py tests/api/test_quiz_submissions.py tests/api/test_system.py
uv run pytest tests/api/test_ratelimit.py tests/api/test_github_auth.py
```

### 2. Frontend, Live Refresh, UX, And Browser Behavior

Owned report: `frontend-live-ux-critical-review.md`.

Focus areas:

- Moderator owner/delegate UI contract, especially hidden or disabled controls.
- Participant/projector correctness around live counts, reveal, stale refresh,
  and reconnect behavior.
- Design-system drift from `docs/UX.md`, including density, cards, destructive
  actions, and raw dialogs.
- Mobile/table overflow, projector framing, keyboard-only paths, ARIA patterns,
  and image alt text.
- TypeScript API-shape risk and frontend test coverage gaps.

Recommended verification:

```bash
npm run build
npm run lint
uv run pytest tests/ui/
```

## Final Integration

After both execution reports land:

1. Run or collect the verification commands that fit the current sandbox.
2. Check that reports cite current paths and do not duplicate stale prior
   findings that have already been fixed.
3. Summarize the highest-severity open issues and list all markdown artifacts.
