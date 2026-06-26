# Exploration: Frontend, UX, Live Clients

Date: 2026-06-25

Scope: planning artifact for critical review. This pass did not implement product or code fixes. It maps the current Vite/TypeScript frontend against `docs/specs.md`, `docs/UX.md`, role-specific browser clients, live WebSocket behavior, and UI tests.

## Source Map

Authoritative product and UX sources:

- `docs/specs.md:7` defines the five roles and their auth model: Admin, Moderator, Participant, Projector/Display, and System.
- `docs/specs.md:51` says UI test selectors should be real IDs/classes and status assertions should prefer badge classes over friendly labels.
- `docs/specs.md:1525` defines live updates: state-changing routes broadcast short message types and each frontend treats them as refresh hints.
- `docs/UX.md:12` defines visual tokens, but says they live in `static/app.css`; current implementation is `frontend/src/app.css`.
- `docs/UX.md:41` defines three density modes: Work, Read, and Display.
- `docs/UX.md:91` defines the moderator "Set up" disclosure rule.
- `docs/UX.md:118` defines the overflow menu pattern.
- `docs/UX.md:353` requires `guardClick` for non-idempotent mutating buttons.
- `docs/UX.md:394` defines keyboard expectations.
- `docs/UX.md:441` says to hide controls the current role cannot use.

Build and serving path:

- `package.json:5` describes Vite + TypeScript, HMR proxying `/api`, `/ws`, and `/uploads` to FastAPI.
- `package.json:6` exposes `dev`, `build`, `preview`, `typecheck`, JS lint, CSS lint, and aggregate lint commands.
- `vite.config.ts:4` sets `frontend` as Vite root.
- `vite.config.ts:9` maps clean URLs in dev so `/m/<code>`, `/s/<code>`, `/p/<code>`, `/quizzes`, and `/` load the same pages as production.
- `vite.config.ts:31` builds multiple HTML entrypoints to `frontend/dist` with base `/static/`.
- `app/main.py:43` and `app/main.py:141` serve the built frontend only when `frontend/dist` exists.
- `app/main.py:504` serves page HTML from the Vite build; `app/main.py:522`, `app/main.py:529`, and `app/main.py:536` redirect bad session codes back to `/?bad_code=...`.

## Frontend Architecture Map

Shared frontend layer:

- `frontend/src/common.ts:15` provides `$` and `$$` DOM helpers; missing selectors fail at runtime because `$` casts without null checking.
- `frontend/src/common.ts:28` provides `el()`, including a special `html` attr that assigns `innerHTML`.
- `frontend/src/common.ts:59` wraps `fetch` in `api()`, adds JSON bodies and same-origin credentials, surfaces JSON `detail`, and redirects 401s off non-root pages to `/`.
- `frontend/src/common.ts:78` stores moderator keys in `localStorage` under `mod_key:<CODE>`.
- `frontend/src/common.ts:88` implements `openLiveSocket`.
- `frontend/src/common.ts:159` lazy-loads the vendored QR library and renders QR SVGs.
- `frontend/src/common.ts:189` creates toast notifications.
- `frontend/src/common.ts:213` implements `guardClick`.
- `frontend/src/types.ts` centralizes API response shapes but uses broad `string` status types rather than literal unions, so invalid status use will not be caught by TypeScript.

HTML entrypoints:

- `frontend/index.html` is the root admin and anonymous join page. It contains first-run setup, login, admin session list, session detail, typed-title delete confirmation, quiz library entry, and change-password card.
- `frontend/quizzes.html` is the admin quiz authoring and global quiz-runs report page.
- `frontend/moderator.html` is the session operation page for owner-admins and delegated moderators.
- `frontend/participant.html` is the anonymous audience client.
- `frontend/projector.html` is the public read-only display client.

Page modules:

- `frontend/src/index.ts` owns root page auth state, session CRUD, inline admin moderation, moderator URL sharing, participant base URL QR rendering, and password change.
- `frontend/src/quizzes.ts` owns quiz authoring, upload UI, publish/unpublish, quiz-run report browsing, and result rendering.
- `frontend/src/moderator.ts` owns moderator key capture, setup disclosure, lifecycle actions, participant invite/base URL, question moderation, quiz-run operation, feedback summary, presence polling, and live refresh.
- `frontend/src/participant.ts` owns anonymous identity, display name, question ask/vote, live quiz answering, session feedback, and targeted WebSocket refresh.
- `frontend/src/projector.ts` owns display title/code/QR, top unanswered questions, quiz lobby/current/closed rendering, and debounced WebSocket refresh.

Styling:

- `frontend/src/app.css:1` defines token variables.
- `frontend/src/app.css:22` defines top chrome.
- `frontend/src/app.css:30` defines the card primitive.
- `frontend/src/app.css:52` styles questions.
- `frontend/src/app.css:76` styles feedback stars and summary views.
- `frontend/src/app.css:102` styles quiz answer options and result bars.
- `frontend/src/app.css:124` defines projector display scale.
- `frontend/src/app.css:137` styles the moderator setup disclosure.
- `frontend/src/app.css:152` styles overflow menus.
- `frontend/src/app.css:176` styles compact admin tables.
- `frontend/src/app.css:231` styles QR lightbox behavior.

## Role And Client Responsibilities

Admin root, `/`:

- `frontend/src/index.ts:43` switches between setup, login/join, and authenticated admin views based on `/api/admin/status`.
- `frontend/src/index.ts:74` lets anonymous users join by code, redirecting to `/s/<CODE>`.
- `frontend/src/index.ts:83` handles first-run setup.
- `frontend/src/index.ts:97` handles login.
- `frontend/src/index.ts:109` creates sessions through a guarded button.
- `frontend/src/index.ts:124` renders owned sessions as a compact table with status, counts, and action links.
- `frontend/src/index.ts:169` paints the session detail card with lifecycle state, participant URL, QR, and feedback summary.
- `frontend/src/index.ts:213` provides inline Start/End moderation for admin owners.
- `frontend/src/index.ts:278` and `frontend/src/index.ts:294` persist base URL and title changes.
- `frontend/src/index.ts:333` implements live-session delete blocking and typed-title delete confirmation.

Admin quiz library, `/quizzes`:

- `frontend/src/quizzes.ts:12` loads quiz templates.
- `frontend/src/quizzes.ts:41` loads global quiz-run rows.
- `frontend/src/quizzes.ts:95` creates new quiz templates.
- `frontend/src/quizzes.ts:138` opens the quiz editor.
- `frontend/src/quizzes.ts:147` renders the editor.
- `frontend/src/quizzes.ts:177` renders a question editor block.
- `frontend/src/quizzes.ts:239` renders answer editor rows.
- `frontend/src/quizzes.ts:299` uploads images with raw `fetch`, outside `api()`.
- `frontend/src/quizzes.ts:309` opens a quiz-run result.
- `frontend/src/quizzes.ts:318` renders per-question results.

Moderator, `/m/<code>`:

- `frontend/src/moderator.ts:9` consumes `#k=<mod_key>` URL fragments and stores the key in localStorage, then removes the fragment from history.
- `frontend/src/moderator.ts:23` toggles all work surfaces behind the key gate.
- `frontend/src/moderator.ts:34` submits a moderator key and reboots the page.
- `frontend/src/moderator.ts:55` loads public session state and header links.
- `frontend/src/moderator.ts:71` renders participant invite URL and hides owner-only base URL editing when `isOwner` is false.
- `frontend/src/moderator.ts:97` renders session lifecycle actions.
- `frontend/src/moderator.ts:130` polls live presence.
- `frontend/src/moderator.ts:137` loads moderator-visible questions.
- `frontend/src/moderator.ts:157` renders response/remove/restore controls.
- `frontend/src/moderator.ts:205` loads ready quizzes for staging.
- `frontend/src/moderator.ts:216` loads quiz runs.
- `frontend/src/moderator.ts:231` renders each run with inline primary actions and an overflow menu.
- `frontend/src/moderator.ts:281` builds the run overflow menu.
- `frontend/src/moderator.ts:385` starts the multi-fetch refresh path.
- `frontend/src/moderator.ts:387` debounces WebSocket refreshes by 400 ms.
- `frontend/src/moderator.ts:392` boots auth, setup open state, initial data, socket, and presence interval.

Participant, `/s/<code>`:

- `frontend/src/participant.ts:12` loads session state, hides Ask when ended, and renders invite QR.
- `frontend/src/participant.ts:25` loads anonymous identity.
- `frontend/src/participant.ts:30` persists display name on `change`.
- `frontend/src/participant.ts:37` loads visible questions.
- `frontend/src/participant.ts:56` renders questions with a real vote button and ARIA pressed state.
- `frontend/src/participant.ts:76` toggles a question vote.
- `frontend/src/participant.ts:82` submits new questions.
- `frontend/src/participant.ts:101` chooses the active live quiz run.
- `frontend/src/participant.ts:114` renders the current live quiz.
- `frontend/src/participant.ts:182` submits quiz answers.
- `frontend/src/participant.ts:206` renders star feedback controls.
- `frontend/src/participant.ts:229` autosaves feedback after a rating exists.
- `frontend/src/participant.ts:267` loads existing feedback.
- `frontend/src/participant.ts:294` routes WebSocket message types to selective refetches.

Projector, `/p/<code>`:

- `frontend/src/projector.ts:9` loads session, questions, and quiz runs in parallel.
- `frontend/src/projector.ts:16` updates the participant base URL and QR only when the base changes.
- `frontend/src/projector.ts:25` enforces display priority: live, then queued lobby, then closed, then hidden.
- `frontend/src/projector.ts:35` renders the queued lobby.
- `frontend/src/projector.ts:45` renders top unanswered questions.
- `frontend/src/projector.ts:65` renders live or closed quiz state.
- `frontend/src/projector.ts:99` debounces socket-driven full reloads by 400 ms.

Backend live contract:

- `app/main.py:498` broadcasts `{"type": kind}` to `session:<code>`.
- `app/ws.py:24` fans out concurrently and evicts failed sockets.
- `app/ws.py:42` applies a 2 second send timeout per client.
- `app/main.py:1921` handles `/ws/sessions/{code}`.
- `app/main.py:1923` rejects cross-origin upgrades with 4403.
- `app/main.py:1929` rejects missing sessions with 4404.

## UX And Design-System Drift Risks

Current implementation mostly follows the card/table/detail vocabulary, but review should target these drift areas:

1. Documentation path drift. `docs/UX.md:14` says tokens live in `static/app.css`, and `README.md:115` still describes `static/` as the vanilla frontend location. Current code is Vite/TypeScript in `frontend/src/app.css` and `frontend/*.html`. This matters because future reviewers may inspect or update the wrong place.

2. Static wording drift. `app/main.py:111` still says "no-build pages rely on inline module scripts", but pages are now Vite entrypoints with external `script type="module"` tags. This is not a product bug by itself, but it is a spec/comment drift risk around CSP decisions.

3. Density mixing. `docs/UX.md:54` says a page never mixes densities. Moderator work surfaces use `section.card` rather than `section.card compact` in `frontend/moderator.html:32`, `frontend/moderator.html:46`, `frontend/moderator.html:66`, `frontend/moderator.html:77`, `frontend/moderator.html:83`, and `frontend/moderator.html:88`, despite being a Work surface. The quiz-run rows also return nested `section.card` from `frontend/src/moderator.ts:278`, which may violate the "no cards inside cards" intent if expanded.

4. Native dialogs. `docs/UX.md:328` bans raw `alert()` for new code but still allows native `confirm()` for delete until a modal pattern exists. Current code uses `confirm()` in session ending/deletion and quiz deletion paths (`frontend/src/index.ts:225`, `frontend/src/index.ts:340`, `frontend/src/moderator.ts:112`, `frontend/src/moderator.ts:339`, `frontend/src/quizzes.ts:110`, `frontend/src/quizzes.ts:203`). Confirm dialogs are expected today for delete, but session ending and quiz close/delete flows should be reviewed for whether they still match the allowed exception.

5. Setup disclosure lifecycle. `docs/UX.md:111` says the setup section should be defaulted open/closed once on load and not reset on every refresh. `frontend/src/moderator.ts:398` sets it in `boot()`, while socket refresh calls `refresh()` and not `boot()`, so this looks aligned. Review should still test wrong-key -> boot retry and session planning/live transitions for unexpected disclosure resets.

6. Owner-only controls. `docs/UX.md:441` says hide controls the current role cannot use. `frontend/src/moderator.ts:76` hides the base URL field for delegates based on `isOwner`, but the surrounding explanatory text in `frontend/moderator.html:48` remains visible and still discusses overriding the base URL. That is a UX-role mismatch risk for delegated moderators.

7. Error surface consistency. `api()` redirects all 401s away from non-root pages (`frontend/src/common.ts:70`). That is correct for admin auth expiry, but moderator delegates with a bad or expired localStorage key often receive 403, not 401, so they rely on caller-specific catch behavior. Review should verify every mod-key failure path returns users to `#modkey-card` rather than leaving hidden surfaces or stale stored keys.

8. Inline styles bypassing the design system. The HTML files and render functions contain many inline style attributes for layout, QR sizes, typography, and spacing. This increases the risk of token/spacing drift from `docs/UX.md:31`.

9. Participant feedback card as `details.card`. `frontend/participant.html:21` uses `<details class="card">` with a `<summary class="card-head">`; CSS gives `details#feedback-card` a separate panel treatment at `frontend/src/app.css:88`. This is likely intentional, but review should check whether keyboard/focus semantics and density still feel like a standard read surface.

10. Status status-label drift. `docs/specs.md:51` warns tests should assert badge class, not text. UI code uses `statusLabel()` from `frontend/src/common.ts:201`. Any new status must update labels, badge CSS, and tests together.

## Live Refresh And WebSocket State Risks

High-priority review targets:

1. Initial socket connect causes an extra refresh. `docs/specs.md:1536` says every reconnect after the first fires synthetic `{type: "reconnect"}`. `frontend/src/common.ts:96` fires `{type: "reconnect"}` on every open, including the first. The comment says this prevents a broadcast race between page load and socket readiness. That behavior may be good, but it is now stronger than the spec and means first paint can duplicate API loads on participant/moderator/projector pages.

2. No cancellation or monotonic versioning for concurrent refreshes. Moderator `refresh()` starts independent `loadSession`, `loadQueries`, `loadQuizRuns`, `loadPresence`, and `loadFeedback` calls (`frontend/src/moderator.ts:385`). Projector `loadAll()` fetches three resources in parallel (`frontend/src/projector.ts:9`). Participant selective refreshes can overlap (`frontend/src/participant.ts:294`). There is no sequence guard, abort controller, or version check, so a slower older response can overwrite newer DOM state.

3. Socket lifecycle duplication. `frontend/src/moderator.ts:401`, `frontend/src/participant.ts:318`, and `frontend/src/projector.ts:106` call `openLiveSocket` but do not keep the returned `LiveSocket`. That is fine for single page load, but `boot()` in moderator can be called again after key submission (`frontend/src/moderator.ts:39`). If a prior `boot()` partially succeeded before a later retry, review should rule out multiple active sockets and intervals.

4. Reconnect backoff spec drift. `docs/specs.md:1446` says exponential backoff capped around 32 seconds; `frontend/src/common.ts:107` caps retry count at 6, calculates `500 * 2 ** retry`, and adds +/- 50% jitter. Max delay range is roughly 16 to 32 seconds, not a stable 32 second cap. This is probably acceptable, but tests should encode the intended jittered range.

5. Reconnect test gap. `tests/ui/test_projector.py:157` explicitly skips UC-D-05 because Playwright cannot reliably simulate a WebSocket server restart. That leaves the spec's reconnect invariant (`docs/specs.md:1442`, `docs/specs.md:1525`) mostly unverified in browser tests.

6. Participant live-count refresh is state-dependent. `frontend/src/participant.ts:303` ignores peer `quiz_submission` unless `activeQuiz.results` is already present. This prevents O(N^2) refreshes, but review should target the transition where a moderator enables live counts after submissions already happened, plus reconnect while live counts are on, to ensure clients eventually show current counts.

7. Projector full reload is debounced, not message-aware. `frontend/src/projector.ts:100` coalesces all messages into one `loadAll()`. This is simple and correct if final state wins, but stale response ordering and rapid queue/start/advance/reveal sequences can show brief wrong display state.

8. Moderator pending response text is protected only for Q&A response text. `frontend/src/moderator.ts:21` and `frontend/src/moderator.ts:158` preserve unsaved response drafts across query re-renders, but there is no equivalent protection for base URL edits, quiz selection, or other in-progress controls if a socket refresh arrives.

9. QR refresh is base-only on projector. `frontend/src/projector.ts:19` only rerenders the QR when base changes. Session code is fixed per page, so this is fine. If future clean URL aliases or code edits become possible, this assumption must be revisited.

10. Broadcast type coverage is asymmetric. Moderator refreshes everything for any message (`frontend/src/moderator.ts:387` ignores message kind). Participant has selective handling (`frontend/src/participant.ts:294`). Projector reloads everything. This means bugs may show up only in participant, where message routing is more complex.

11. WebSocket connect is not rate-limited. `docs/specs.md:1700` says this is out of scope for the in-process limiter. Review should consider whether reconnect storms from a classroom network could affect server health, especially because `openLiveSocket` has jitter but no max retry stop.

12. Slow socket eviction relies on API handlers awaiting broadcast. `app/ws.py:24` and `app/ws.py:42` protect API latency with concurrent sends and a 2 second timeout, but every mutation still awaits the broadcast. Stress tests should cover many connected projector/participant clients and a wedged socket.

## Browser And Accessibility Failure Modes To Target

1. Mobile overflow in tables. Admin and quiz-library tables use `width: 100%` with multiple columns and no horizontal overflow wrapper (`frontend/src/app.css:176`). Root admin has 7 columns (`frontend/index.html:56`), quiz-runs has 7 (`frontend/quizzes.html:36`), and row actions use `white-space: nowrap` (`frontend/src/app.css:183`). Narrow screens are likely to overflow.

2. Header wrapping and dense meta controls. The top header is a single flex row (`frontend/src/app.css:22`). Participant puts name input in header meta (`frontend/participant.html:11`), moderator puts multiple links and badges in header meta (`frontend/moderator.html:11`). Small screens may compress or overlap.

3. Projector fixed display scale. Projector uses large fixed font sizes and padding (`frontend/src/app.css:124`) plus inline quiz heading sizes (`frontend/src/projector.ts:41`, `frontend/src/projector.ts:73`). Test long titles, long questions, image-heavy questions, and low-height projectors.

4. Keyboard-only overflow menu. UX requires outside-click and Esc handling (`docs/UX.md:146`), implemented at `frontend/src/moderator.ts:44`. Review should test Tab order into the menu panel, Shift+Tab out, Esc close, and whether focus lands somewhere sensible after row re-render.

5. Star rating radiogroup lacks arrow-key behavior. `frontend/participant.html:27` declares `role="radiogroup"` and `frontend/src/participant.ts:212` creates `role="radio"` buttons with `aria-checked`, but there is no roving tabindex or arrow key support. Native buttons are reachable, but the ARIA radio pattern is incomplete.

6. Icon-only and symbol controls. The overflow summary is labelled (`frontend/src/moderator.ts:299`), QR targets get role/label (`frontend/src/common.ts:178`), and delete answer has an aria-label (`frontend/src/quizzes.ts:270`). Review should audit every symbol-only control, especially star buttons and `xsmall` deletes.

7. Toast announcements. Toasts use `role="status"` and `aria-live` (`frontend/src/common.ts:189`), but they auto-remove after a timeout. Screen reader timing and focus after errors should be checked for form failures.

8. Color contrast and color-only meaning. Correct/wrong/selected states rely heavily on border color and subtle background (`frontend/src/app.css:110`, `frontend/src/app.css:111`, `frontend/src/app.css:112`). Some text markers exist (`frontend/src/projector.ts:87`, `frontend/src/quizzes.ts:347`), but participant correctness may be largely class-driven.

9. Disabled quiz options after reveal. Participant disables option buttons when locked (`frontend/src/participant.ts:146`). Disabled controls may be skipped by assistive tech; if result detail is important, correctness and selected state may need non-interactive text equivalents.

10. File inputs in compact editor rows. `frontend/src/quizzes.ts:212` and `frontend/src/quizzes.ts:252` use native file inputs inside dense flex rows. They are likely to overflow and have browser-specific rendering differences.

11. Image alt text. User-uploaded quiz images are rendered as content images in question/answer displays (`frontend/src/participant.ts:128`, `frontend/src/participant.ts:158`, `frontend/src/projector.ts:74`, `frontend/src/projector.ts:86`) without meaningful `alt`. Thumbnails sometimes use empty alt (`frontend/src/quizzes.ts:251`). Accessibility review should decide whether images are decorative or need authored alt text.

12. Details/summary semantics. Moderator setup and feedback card use `details`/`summary`. This is good for native keyboard support, but custom CSS hides markers and injects glyphs (`frontend/src/app.css:146`, `frontend/src/app.css:147`, `frontend/src/app.css:90`). Verify Safari, Firefox, and Chromium rendering.

13. Clipboard fallback. Copy actions catch clipboard failures and toast guidance (`frontend/src/index.ts:244`, `frontend/src/moderator.ts:91`, `frontend/src/index.ts:309`). Test insecure origins, denied permissions, and iOS Safari.

14. Bad-code redirect. All bad role URLs redirect to `/` with `bad_code` (`app/main.py:518`), and the root page reads it (`frontend/src/index.ts:5`). Verify that `/m/BAD` and `/p/BAD` copy is not misleading as a participant-only error.

15. Hidden surfaces vs focus. Many cards are hidden by `style.display = "none"`. When a surface disappears after live updates, focus may remain on a removed or hidden button.

## Test Coverage Observed

Current UI tests are broad and useful:

- `tests/conftest.py:32` builds the frontend once before tests.
- `tests/ui/conftest.py:28` starts a real uvicorn subprocess with isolated DB and uploads.
- `tests/ui/conftest.py:104` launches Chromium only.
- `tests/ui/test_landing_admin.py` covers root admin session CRUD, inline moderation, moderator link, copy URL, and password card.
- `tests/ui/test_landing_anon.py` covers setup/login/join/bad-code flows.
- `tests/ui/test_moderator.py` covers owner/delegate key gate, lifecycle, ready quiz filtering, queue/start/reveal/close/delete, overflow menu outside click, query response/remove, feedback, live count text, and invite QR/base URL.
- `tests/ui/test_participant.py` covers feedback autosave/clear, voter token persistence, name persistence, ask/vote/sorting, live quiz, submit/reveal, QR lightbox, ended sessions, and live counts.
- `tests/ui/test_projector.py` covers projector basics, bad-code redirect, QR lightbox and keyboard open, live query via WS, planning/live/quiz state, lobby, display priority, and live-count toggles.
- `tests/ui/test_quizzes.py` covers quiz authoring, editor persistence, uploads, publish/unpublish, quiz-run report rows, and result card.

Important gaps for critical review:

- No cross-browser UI run. Fixtures use Chromium only.
- No small viewport or mobile viewport coverage.
- No automated accessibility scan or keyboard-only journey coverage beyond selected Escape/Enter cases.
- No direct reconnect/backoff test; UC-D-05 is skipped.
- Limited stale async response testing. Tests generally wait for final expected DOM but do not inject delayed API responses.
- Limited live multi-client tests. Projector live query via WS is covered, but participant/moderator/projector simultaneous behavior under rapid broadcasts is not deeply exercised.
- No visual regression or screenshot checks for projector framing, long text, tables, or image-heavy quizzes.

## Recommended Verification Commands

Baseline commands:

```bash
npm run build
npm run typecheck
npm run lint:js
npm run lint:css
npm run lint
uv run pytest tests/ui/
uv run pytest tests/api/
uv run pytest
```

Focused commands for this review:

```bash
uv run pytest tests/ui/test_moderator.py tests/ui/test_participant.py tests/ui/test_projector.py
uv run pytest tests/ui/test_landing_admin.py tests/ui/test_quizzes.py
uv run pytest tests/api/test_quiz_runs.py tests/api/test_queries.py tests/api/test_feedback.py
uv run pytest tests/api/test_system.py
```

Manual or new-test verification targets:

- Run Vite dev proxy and FastAPI together:

```bash
uv run uvicorn app.main:app --reload --port 8000
npm run dev
```

- Exercise clean URLs through Vite dev server: `/`, `/quizzes`, `/m/<code>`, `/s/<code>`, `/p/<code>`.
- Repeat the UI suite or selected tests with Firefox and WebKit if Playwright browsers are installed.
- Add viewport passes around 375x667, 390x844, 768x1024, 1366x768, and a projector-like 1920x1080.
- Add a keyboard-only script for admin session detail, moderator run menu, participant feedback stars, quiz answers, and QR lightbox.
- Add a reconnect/backoff test around `openLiveSocket` using a fake WebSocket unit test if browser-level server restart remains unreliable.
- Add stale-response tests with Playwright route interception: delay an older `/quiz_runs` or `/queries` response, trigger a newer state, then release the older response and assert final DOM remains current.
- Add multi-client tests: one moderator page, one participant page, one projector page; drive queue/start/submit/live-count/reveal/close and assert all surfaces converge.

## Review Questions To Answer

1. Should `openLiveSocket` refetch on first connect be treated as the new spec, or should the implementation match the current "after the first reconnect" wording?

2. Is selective participant live refresh acceptable as written, or should participants also coalesce/refetch on every quiz event like the projector?

3. Does the moderator page intentionally use read-density cards for operational controls, or should it be converted to the compact work surface pattern from `docs/UX.md`?

4. Are native confirms still acceptable for session End and quiz-run deletion, or only for Delete flows as currently documented?

5. Should `types.ts` use literal status unions to catch frontend/backend status drift earlier?

6. Should accessibility be raised to an explicit acceptance layer in `docs/specs.md`, especially for radiogroup stars, quiz answer buttons, image alt text, and keyboard menus?

7. Should stale async response ordering be solved generally, or only tested around high-risk live quiz and moderator paths?

## Suggested Critical Review Order

1. Contract drift pass: compare `docs/specs.md`, `docs/UX.md`, `README.md`, comments in `app/main.py`, and current Vite frontend paths.

2. Live state pass: inspect `openLiveSocket`, participant selective refresh, moderator/projector debouncing, reconnect behavior, and backend broadcast guarantees.

3. Role/auth pass: admin-owner vs delegate moderator vs public projector vs anonymous participant, especially hidden controls, localStorage mod keys, and 401/403 UX.

4. Accessibility and browser pass: keyboard, ARIA, small screens, projector framing, native dialog/clipboard behavior, and image alt semantics.

5. Test design pass: add or recommend narrowly targeted tests for stale refresh, reconnect, multi-client convergence, mobile overflow, and keyboard-only workflows.

## Highest-Risk Anchors

- `frontend/src/common.ts:88` - `openLiveSocket`, reconnect, synthetic reconnect, jittered backoff.
- `frontend/src/participant.ts:294` - selective live message routing.
- `frontend/src/moderator.ts:385` - multi-fetch refresh without sequencing.
- `frontend/src/projector.ts:9` - full display state fetch.
- `frontend/src/projector.ts:25` - quiz display priority.
- `frontend/src/moderator.ts:281` - overflow menu actions and destructive separation.
- `frontend/src/moderator.ts:392` - boot path, setup disclosure, socket, presence timer.
- `frontend/src/index.ts:169` - admin session detail and QR/base URL rendering.
- `frontend/src/quizzes.ts:147` - editor render, inline mutation patterns.
- `frontend/src/app.css:176` - compact tables and mobile overflow risk.
- `tests/ui/test_projector.py:157` - skipped reconnect coverage.
- `app/ws.py:24` - concurrent broadcast fanout.
- `app/main.py:1921` - WebSocket upgrade validation.

