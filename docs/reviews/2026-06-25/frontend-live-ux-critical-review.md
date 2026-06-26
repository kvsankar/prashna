# Frontend/Live/UX Critical Review - 2026-06-25

## Resolution status

Fixed in the follow-up TDD pass:

- Moderator, participant, and projector live refresh paths now use monotonic
  sequence guards so older responses cannot repaint newer state.
- Projector QR caching now keys on the full participant URL.
- README/spec/UX/current tracker docs now point reviewers at the Vite
  `frontend/` source tree.

## Scope and verification performed

Reviewed the current Vite/TypeScript frontend and live-client behavior using:

- Planning/spec inputs: `critical-code-review-plan.md`,
  `exploration-frontend-and-ux.md`, `docs/UX.md`, `docs/specs.md`, and
  `CLAUDE.md`.
- Frontend code: `frontend/*.html`, `frontend/src/common.ts`,
  `frontend/src/moderator.ts`, `frontend/src/participant.ts`,
  `frontend/src/projector.ts`, `frontend/src/quizzes.ts`,
  `frontend/src/index.ts`, `frontend/src/app.css`, and `tests/ui`.
- Relevant backend live contract: `app/main.py` WebSocket/broadcast routes.

Verification completed by the parent review pass:

```bash
npm run build
npm run lint
uv run pytest tests/ui/
uv run pytest tests/api/
```

Results:

- `npm run build` passed.
- `npm run lint` passed.
- `uv run pytest tests/ui/` passed: `112 passed, 2 skipped`.
- `uv run pytest tests/api/` passed: `291 passed, 3 skipped`.

Note: the first frontend execution subagent stalled without writing a report;
this report was completed from the finished frontend exploration and parent
review/verification pass.

## Findings

### Medium - Overlapping live refreshes can still paint stale state after rapid events

**Evidence:** `openLiveSocket()` calls each page callback directly for every
message and reconnect (`frontend/src/common.ts:88-117`). Moderator refresh
starts independent async loads without a request version or cancellation
(`frontend/src/moderator.ts:385-390`). Participant routes live messages into
independent `loadSession()`, `loadQueries()`, and `loadQuiz()` calls
(`frontend/src/participant.ts:284-309`). Projector coalesces messages for
400 ms, but each `loadAll()` still races as an unversioned `Promise.all()`
(`frontend/src/projector.ts:9-33`, `frontend/src/projector.ts:99-103`).

**Failure mode:** During a rapid quiz sequence, such as start -> reveal ->
next or several submissions while live counts are enabled, an older slower
HTTP response can resolve after a newer one and overwrite the DOM with stale
quiz, count, lifecycle, or invite state. The current tests wait for final
expected DOM and do not inject delayed responses, so this class of bug can
remain hidden while API/UI suites are green.

**Suggested fix/test:** Add a per-surface monotonically increasing refresh
token or `AbortController` around live-refresh loads, and only paint the most
recent response. Add a Playwright route-interception test that delays an
older `/quiz_runs` or `/api/sessions/{code}` response, triggers a newer
state change, and asserts the stale response cannot repaint the page.

### Medium - Projector QR does not refresh if the session code/url changes under the same base

**Evidence:** Projector caches only `lastBase` and rerenders the QR when the
base changes (`frontend/src/projector.ts:7`, `frontend/src/projector.ts:16-23`).
The encoded URL also includes `s.code` (`frontend/src/projector.ts:17`), but
that value is not part of the cache key.

**Failure mode:** Session codes are currently immutable for normal flows, so
this is not a user-facing bug today. It becomes a quiet display defect if a
future admin repair tool, import/restore path, or alias feature changes the
join code while keeping the same public base URL: the visible code/title can
update while the QR still encodes the previous participant URL.

**Suggested fix/test:** Cache the full QR URL rather than only `base`.
The change is tiny and removes the hidden assumption. Add a unit or UI test
that changes the session payload from `/s/OLD` to `/s/NEW` with unchanged
base and verifies `renderQR()` is called again.

### Low - Current docs still route frontend reviewers to stale `static/` paths

**Evidence:** `docs/UX.md:14` says visual tokens are in `static/app.css`,
while current tokens live in `frontend/src/app.css`. `README.md:112-124`
still lists `static/` as the vanilla frontend directory. Older root review
docs also continue to cite `static/*.html`, while current source is
`frontend/*.html` and `frontend/src/*.ts`.

**Failure mode:** The app itself builds and tests correctly, but future
reviewers can inspect or patch the wrong files, especially when trying to
enforce the UX system. This is already visible in prior review docs and makes
stale findings harder to distinguish from current defects.

**Suggested fix/test:** Update `README.md` and `docs/UX.md` to name
`frontend/src/app.css` and the Vite page layout. Leave old dated review docs
as historical artifacts, or add a short note that they predate the Vite move.

## Non-findings / verified OK

- **Delegate moderator Base URL editing is now hidden.** The moderator page
  detects owner context through `/api/admin/status` (`frontend/src/moderator.ts:392-396`)
  and hides the Base URL field when `isOwner` is false
  (`frontend/src/moderator.ts:71-78`). The backend remains owner-only for
  `POST /api/sessions/{code}/participant_base_url`.
- **Closed-run live-count controls are hidden.** `buildRunMenu()` returns
  `null` for closed runs (`frontend/src/moderator.ts:281-283`), matching the
  backend rejection for closed live-count changes.
- **Reconnect now refetches on first connect and reconnect.** `openLiveSocket()`
  invokes the callback with `{type: "reconnect"}` on every open
  (`frontend/src/common.ts:96-100`). This is stronger than the older spec text
  but reduces missed-broadcast risk.
- **Mutating quiz-run buttons use `guardClick`.** The moderator run actions
  are built through `actBtn()` and `guardClick()` (`frontend/src/moderator.ts:303-305`).
- **Current UI verification is green.** Chromium UI coverage is broad across
  landing/admin, moderator, participant, projector, and quiz library flows.

## Test gaps / residual risks

- UI tests run Chromium only; there is no Firefox/WebKit coverage for
  `details`/`summary`, native file inputs, clipboard, or mobile behavior.
- There is no small-viewport table/header/projector framing coverage.
- The reconnect browser test remains skipped because the shared uvicorn
  process is hard to restart inside the existing Playwright fixture.
- Accessibility coverage is manual only. The star rating uses ARIA radio
  roles without a full roving-tabindex/arrow-key pattern
  (`frontend/src/participant.ts:206-225`), and quiz images do not have
  authored alt text.
- Stale-response ordering is not tested; this is the main live-client
  residual risk despite the green suite.
