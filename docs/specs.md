# Prashna — specs

Use cases and acceptance tests for the five surfaces of the system.
Each use case has a stable ID (`UC-<ROLE>-NN`) so tests, PRs, and bug
reports can cite it. Acceptance tests are Given/When/Then.

**Roles** (and their UC prefixes)
- **Admin** (`UC-A-*`) — a signed-in `User`: the password admin created
  at first-run setup (UC-A-01).
  Owns sessions and quiz templates and sees only their own.
  **Capabilities are a strict superset of Moderator.** Authenticates
  via signed cookie; reaches all moderator routes on owned sessions
  without needing the mod_key.
- **Moderator** (`UC-M-*`) — anyone holding the `mod_key` for a
  session. Used for *delegation*: the owner can hand the moderator
  URL to a TA / co-host who has no admin account. Capabilities are
  the moderation subset of Admin (no quiz authoring, no session
  create/delete, no global reports).
- **Participant** (`UC-P-*`) — anonymous audience member. Identified
  by a `voter_token` cookie that resolves to a per-session
  `Participant` row.

**Anonymity.** Questions, quiz answers and feedback are anonymous. The
attendee profile (UC-P-03) is a separate contact card for the moderator.
No page, API response or export links a profile to a person's questions,
quiz answers or feedback, and no export carries a key that joins them.
The only name ever shown with a question is one the asker typed for that
question with **Show my name** (UC-P-04). Internally one `Participant`
row still owns all of these, because voting once, answering once per
quiz question and marking "your question" need it; that link is never
shown.
- **Projector / Display** (`UC-D-*`) — the big-screen view at the
  front of the room (`/p/<code>`). Public, read-only, no chrome,
  updates live via WebSocket.
- **System** (`UC-X-*`) — cross-cutting backend invariants, broadcast
  contracts, security headers, and storage-level constraints. Not a
  user action; the substrate every other UC silently depends on.

**What each role needs.** Participants need to ask and support questions
anonymously, answer the current quiz question, optionally share a profile,
and rate the session with little effort. Moderators need one page to run the
room: lifecycle, Q&A triage, quiz playback, attendee profiles, and feedback.
Admins need first-run access, session setup with owner-only controls,
reusable quizzes, and reports that stay stable. The room needs join
information and the live state on the projector. Operators need repeatable
install, deployment, backup, and safe configuration. Developers need a spec
that stays aligned with the tests.

**Authorization model.** Every moderator-gated route accepts *either*
the admin owner cookie *or* an `X-Mod-Key` header. Reads that branch
on "is this caller a moderator?" (e.g., showing removed queries, or
queued runs) use the same rule. This means the admin gets the moderator
UI seamlessly; the mod_key path stays available for delegates.

---

## Conventions used by the Tests blocks

To avoid repeating the same auth-error bullet on every UC, the
following standard responses apply across all routes of a given auth
class. Individual UC tests only assert per-route specifics on top of
these.

| Route auth class               | No / invalid auth → response                                                   |
| ------------------------------ | ------------------------------------------------------------------------------ |
| `auth.current_admin` (admin)   | `401 "Not authenticated"`                                                      |
| `auth.optional_admin` (optional) | route handler decides (usually returns 404 to non-owners on owned reads)     |
| `require_mod_or_owner`         | `403 "Not authorized — moderator key or admin login required"` when neither    |
| Owner-only (`require_session_owner`) | `401 "Not authenticated"` if no cookie; `403 "Not your session"` if logged in but wrong owner |
| Participant (cookie-issued)    | Never errors on auth — a fresh `voter_token` is created on first interaction   |

Selectors cited in `**Tests (UI)**` blocks are real IDs / classes in
`frontend/*.html` and `frontend/src/*.ts`. Some elements are JS-rendered (badges, quiz-run rows,
query rows); test authors should rely on the documented class names
(`.badge-live`, `.question`, etc.) and text content rather than DOM
positions. **Status badges** (Session + QuizRun lifecycle) keep the raw
status in their CSS class (`badge-planning`, `badge-queued`, …) but
*display* a friendly label ("Not started", "Queued", "Live", "Closed",
"Ended" — see `statusLabel` in `frontend/src/common.ts`). Assert lifecycle on the
class, never the badge text.

**UI copy vs. entity names.** The `Query` entity is internal vocabulary.
On the participant, projector, and moderator surfaces the user-facing
copy says **"question" / "questions"** (audiences ask questions, not
"queries"). Element IDs, CSS classes, API routes, and DB columns keep the
`query` name (`#queries`, `#query-text`, `/api/sessions/{code}/queries`,
`query_count`). When a `**Tests (UI)**` bullet pins visible text it uses
the displayed wording ("question"); when it pins a selector or route it
uses the `query` name. This split is intentional — don't rename the
entity to match the copy.

When a bullet writes `"a"*201` or similar, it's Python `str * int`
notation (a 201-character string).

**Value types.** A text field in a JSON body (a title, question or answer
text, a URL, a password, a feedback comment, a profile field) accepts a
string or `null`. Any other JSON type returns `400 "<field> must be
text"` and changes nothing, never `500`
(`test_uc_x_05_text_fields_reject_other_json_types`). An `order_index`
must be an integer, also on create (`400 "order_index must be an
integer"`).

**Error responses.** An error's `detail` is a plain sentence that starts
with a capital letter, because the frontend shows it as received.
- A `404` names the missing thing ("Question not found", "Quiz not
  found", "Quiz run not found", "Session not found"), never the bare
  "Not Found" (`test_404s_name_the_missing_thing`).
- `400` refuses a request that the current state or the input doesn't
  allow ("Session has ended"). `409` is kept for two requests competing
  for one slot, where only one can win: first-run setup ("Admin already
  initialized") and a second live quiz run in a session.
- A route addressed by session code answers a signed-in admin who
  doesn't own the session with `403 "Not your session"`. A route
  addressed by an id (a quiz, a quiz question or answer, a quiz run)
  answers with that id's `404`, so it doesn't reveal that the id exists.
  Admin-only id routes answer a signed-out caller with `401 "Not
  authenticated"` first, so an expired sign-in redirects to `/`.

**Route names.** Path segments are lower-case `snake_case` nouns
(`quiz_runs`, `participant_base_url`, `question_order`), and an action
on a resource is the last segment (`/start`, `/reveal`, `/export`). The
role bootstraps (`participant-bootstrap`, `moderator-bootstrap`,
`display-bootstrap`) and `/api/export/all` predate this rule and keep
their names, because existing clients use them. New routes follow the
rule.

**Timestamps.** Every timestamp in an API response is UTC in ISO 8601
with a `Z` suffix and whole seconds (`2026-10-11T04:30:00Z`), the same
form as the exports, so a browser shows it in the viewer's own time zone
(`test_uc_a_04_timestamps_are_utc_with_z`).

---

## Admin

### UC-A-01: First-run admin setup

A fresh installation has no admin. Only someone who can see the server's
output may create the first one, so an install whose address is already
public can't be claimed by its first visitor.

- **Given** no user rows exist when the server starts
- **Then** it holds a one-time **setup token**: the value of
  `PRASHNA_SETUP_TOKEN` if the operator set one, otherwise a random token
  starting with `prashna_st_`, saved as `setup-token` (mode `0600`) beside
  the database and reused across restarts until an admin exists. The prefix
  lets a scanner recognise a leaked token in any file
- **And** it logs a `WARNING` with the setup link `/#setup=<token>`
  ("open it on this server's address"), so it appears in the terminal or
  in `docker compose logs`
- **When** someone opens the landing page with `#setup=<token>` in the
  address
- **Then** the setup form is shown; submitting a username and a password
  of ≥ 8 chars calls `POST /api/admin/setup` with
  `{username, password, setup_token}`
- **And** with the right token the admin is created, a session cookie is
  issued, the `setup-token` file is deleted, and the link stops working
- **And** without the link, the landing page explains that the server
  log holds a one-time setup link instead of a setup form
- **And** any subsequent `POST /api/admin/setup` returns `409 Admin
  already initialized`
- **And** passwords shorter than 8 chars return `400` with a length
  message
- **And** a password is the only admin sign-in method: the status payload
  reports only whether an admin exists, whether the visitor is signed in,
  and the signed-in username; there are no third-party sign-in routes; and
  neither the first-run page nor the sign-in page offers another sign-in
  option

**Tests (API)**
- `GET /api/admin/status` on a fresh DB → `200 {initialized: false, authenticated: false, username: null}`. Auth: none.
- The `GET /api/admin/status` payload has exactly the keys `initialized`, `authenticated`, and `username`, both before setup and when signed in.
- `GET /api/auth/github/login` and `GET /api/auth/github/callback` → `404`, also when the environment sets `PRASHNA_GITHUB_CLIENT_ID`, `PRASHNA_GITHUB_CLIENT_SECRET`, and `PRASHNA_GITHUB_ADMINS`; the server reads none of them, and the status payload keeps the same three keys.
- A database created before this version whose `users` table still has a nullable `github_id` column starts, accepts first-run setup, and lets the password admin log in; the column's data is left unchanged.
- `POST /api/admin/setup` with `{"username": "alice", "password": "longenough", "setup_token": <token>}` → `200 {username: "alice"}` and sets the `prashna_admin` cookie. Auth: the setup token.
- The same request without `setup_token`, or with a wrong one → `403 "Open the one-time setup link from the server log to create the first admin"`; no user is created.
- `GET /api/admin/status` immediately after setup (with cookie) → `200 {initialized: true, authenticated: true, username: "alice"}`.
- `POST /api/admin/setup` a second time → `409 "Admin already initialized"`.
- Race: two concurrent setup calls with **different usernames** — exactly one returns `200`, the other returns `409`. Serialized by a process-wide `threading.Lock` around the check+insert (Prashna is single-process, see `docs/architecture.md`, so this is a real invariant). Test: `test_uc_a_01_concurrent_setup_different_usernames`.
- Same-username conflict path is also caught via `try/except IntegrityError` and surfaces as `409`.
- `POST /api/admin/setup` with `{"username": "alice", "password": "short", ...}` → `400 "Password must be at least 8 characters"`.
- `POST /api/admin/setup` with `{"username": "", "password": "longenough", ...}` → `400 "Username is required"`.
- Starting the server on a fresh database without `PRASHNA_SETUP_TOKEN` writes `setup-token` (mode `0600`, value starting `prashna_st_`) beside the database, logs `/#setup=<that token>`, and reuses the same token after a restart; a successful setup deletes the file.

**Tests (UI)**
- On `/` with no admin and no `#setup=` in the address, `#setup-needed-card` is visible and explains the server-log link; `#setup-card`, `#login-card`, and `#sessions-card` are hidden.
- Pasting `/#setup=<token>` into a tab that already shows `/` loads it: the tab reloads and shows `#setup-card` (`test_uc_a_01_setup_link_pasted_into_an_open_tab`). The landing page reloads only for a `#setup=` link; its section links (`#sessions-card`) stay ordinary jumps.
- On `/#setup=<token>` with no admin, `#setup-card` is visible; filling `#su-user`, `#su-pass`, `#su-pass2` (matching) and clicking `#su-btn` swaps the page to the authed view (`#sessions-card` visible).
- Mismatched `#su-pass`/`#su-pass2` shows an error toast without an API call.
- A password shorter than 8 chars surfaces a `400` toast and leaves `#setup-card` visible.
- Neither the first-run page (`/` with no admin, with or without `#setup=`) nor the signed-out sign-in page shows any text mentioning GitHub or any element whose id contains `github`.

### UC-A-02: Login / Logout

- **Given** an admin exists and the visitor is logged out
- **When** they submit valid credentials to `POST /api/admin/login`
- **Then** a signed cookie is issued and the landing page swaps to the
  authed view
- **When** they `POST /api/admin/logout`
- **Then** the cookie is cleared and the landing page reverts to the
  login view
- **And** invalid credentials return `401 Invalid username or password`
- **And** Enter on the password field submits the form

**Tests (API)**
- `POST /api/admin/login` with valid `{username, password}` → `200 {username}` and sets the `prashna_admin` cookie. Auth: none.
- `POST /api/admin/login` with wrong password → `401 "Invalid username or password"`.
- `POST /api/admin/login` with unknown username → `401 "Invalid username or password"`.
- `POST /api/admin/logout` → `200 {ok: true}` and clears the `prashna_admin` cookie.
- `GET /api/admin/status` after logout → `200 {initialized: true, authenticated: false}`.

**Tests (UI)**
- On `/` with an admin existing and no session cookie, `#login-card` is visible.
- While `GET /api/admin/status` is delayed, the static `#join-card` and
  `#login-card` shell is already visible and usable; authentication
  reconciliation must not leave the landing page blank.
- Filling `#li-user` and `#li-pass`, clicking `#li-btn`, swaps to the authed view (`#sessions-card` visible).
- Pressing Enter inside `#li-pass` submits (same effect as clicking `#li-btn`).
- Invalid credentials produce an error toast "Invalid username or password" and `#login-card` stays visible.
- Clicking the logout control returns the page to the `#login-card` view.

### UC-A-03: Create a session

- **Given** the admin is logged in
- **When** they enter a non-empty title in the "+ New session" composer
  and click the button (or press Enter)
- **Then** `POST /api/sessions` creates a Session in `planning` status
  with `owner_user_id = me.id`, a random 6-char code, a random 16-char
  mod_key, and `participant_base_url = null`
- **And** an empty or whitespace-only title returns `400 Session title
  is required`
- **And** the new row appears in the list with a "Not started" badge
  (class `badge-planning`)

**Tests (API)**
- `POST /api/sessions` with `{"title": "Test"}` → `200 {code, title: "Test", mod_key, status: "planning"}`. Auth: admin cookie.
- `POST /api/sessions` with `{"title": ""}` → `400 "Session title is required"`.
- `POST /api/sessions` with `{"title": "   "}` → `400 "Session title is required"`.
- `POST /api/sessions` with `{"title": "a"*201}` → `400 "Session title is too long (max 200 chars)"`.
- `POST /api/sessions` with no admin cookie → `401`.
- Two consecutive creates → both succeed with distinct `code` values.

**Tests (UI)**
- On `/` (authed), typing a title in `#new-session-title` and clicking `#new-session-btn` adds a row to `#session-rows` with `.badge-planning`.
- Pressing Enter in `#new-session-title` submits.
- Pressing Enter twice in quick succession in `#new-session-title` creates one session: the key submits by clicking `#new-session-btn`, so its double-submit guard applies (`test_uc_a_03_double_enter_creates_one_session`).
- Empty title shows an error toast "Session title is required" and the input keeps focus.
- The new row appears at the top of `#session-rows`.

### UC-A-04: See my sessions

- **Given** the admin owns sessions
- **When** they `GET /api/sessions`
- **Then** they see only sessions where `owner_user_id = me.id`,
  ordered by `created_at desc`, with status, query count, quiz-run
  count, feedback count, attendee-profile count, mod_key, and
  participant_base_url
- **And** `feedback_count` counts the participants who submitted
  feedback, and `profile_count` counts the participants who filled in
  any attendee profile field or added a photograph (UC-P-03). The counts
  are separate totals: feedback and questions are anonymous, so nothing
  links them to a profile
- **And** the Created column shows `created_at` in the viewer's own time
  zone (the API sends UTC with `Z`, see "Timestamps" in the conventions)

**Tests (API)**
- `GET /api/sessions` → `200 [{code, title, status, mod_key, participant_base_url, created_at, started_at, ended_at, query_count, quiz_run_count, feedback_count, profile_count}, ...]`. Auth: admin cookie.
- A session where one participant saved a profile and submitted feedback, and another only opened the page, reports `feedback_count: 1` and `profile_count: 1` (`test_uc_a_04_counts_feedback_and_profiles`).
- `created_at`, `started_at` and `ended_at` here, and the timestamps of `GET /api/quiz_runs`, end in `Z` and parse as UTC (`test_uc_a_04_timestamps_are_utc_with_z`).
- Rows include only sessions where `owner_user_id = me.id` (a second admin's session is not returned).
- Order is `created_at desc` — the most recently created session appears first.
- `GET /api/sessions` with no admin cookie → `401`.

**Tests (UI)**
- On `/` (authed), `#session-rows` lists each owned session with title, status badge, query count, and quiz-run count.
- Most-recently-created session appears at the top.
- In a browser whose time zone is `Asia/Kolkata`, a session's Created cell shows its creation time in that zone (UTC + 5 h 30 min), within a minute of when it was created (`test_uc_a_04_created_time_uses_the_viewer_time_zone`).
- Authenticated admin chrome shows `#admin-page-nav` with an Admin breadcrumb and links to Sessions and Quiz library.
- Clicking a row in `#session-rows` opens the session page `/m/<code>` (UC-A-08). Each row's title is a link to the same URL. The Actions column has, in order, the links Participant (`/s/<code>`) and Projector (`/p/<code>`, a new tab), then the extra-small buttons **Start** (while the session is not started) and Delete. The views are plain links and the actions are buttons (UX.md §10) (`test_uc_a_04_row_actions_and_title_link`).
- Clicking **Start** on a not-started row starts the session (`POST /api/sessions/{code}/start`, UC-M-01) without leaving the list; the row then shows the Live badge and no Start button. Start is guarded against repeat clicks (`test_uc_a_04_start_from_the_list`).
- Opening `/?session=<owned-code>` as an authenticated admin redirects to `/m/<code>` (older bookmarks keep working).

### UC-A-05: Edit session title

- **Given** the admin owner opens the session page `/m/<code>`
- **When** they change the Title input in the Session settings card and
  blur
- **Then** `PATCH /api/sessions/{code}` updates the title; the page
  header and the session list reflect the change
- **And** an empty new title returns `400` and the input reverts to
  the old value

**Tests (API)**
- `PATCH /api/sessions/{code}` with `{"title": "New"}` → `200 {code, title: "New", status}`. Auth: **admin cookie only** (owner-only — `mod_key` cannot rename).
- `PATCH /api/sessions/{code}` with `{"title": ""}` → `400 "Session title is required"`.
- `PATCH /api/sessions/{code}` with `{"title": "a"*201}` → `400 "Session title is too long (max 200 chars)"`.
- `PATCH /api/sessions/{code}` with no auth → `401`.
- `PATCH /api/sessions/{code}` with a valid `mod_key` (no admin cookie) → `401` (delegated mods cannot rename).
- After success, a WebSocket `{type: "session_state"}` is broadcast on `session:{code}`.

**Tests (UI)**
- On `/m/<code>` as the admin owner, `#settings-card` shows `#set-title` populated with the current title.
- Editing `#set-title` and blurring updates `#title` in the page header; the row title in `#session-rows` on `/` shows the new title.
- Blurring with an empty value shows error toast and reverts `#set-title` to the prior title.

### UC-A-06: Set per-session participant base URL

- **Given** the admin owner is on the session page `/m/<code>` (the Base
  URL field in the Invite card is shown only to the owner)
- **When** the admin types a URL into the Base URL input and blurs
- **Then** `POST /api/sessions/{code}/participant_base_url` saves the
  value (with trailing slash stripped); the QR and copy-URL widgets
  refresh
- **And** a URL not starting with `http://` or `https://` returns
  `400`
- **And** an empty submission (or Use default click) sets the field to
  `null` and the frontend falls back to the default address
- **And** every page builds participant links, QR codes, and the copied
  moderator URL from the first of: the session's base URL; the server's
  default public address (`default_base_url` in each serialized session,
  set while `prashna --tunnel …` runs, otherwise `null`; UC-X-15); the
  page's own `location.origin`

**Tests (API)**
- `POST /api/sessions/{code}/participant_base_url` with `{"url": "https://example.com/"}` → `200 {participant_base_url: "https://example.com"}` (trailing slash stripped). Auth: **admin cookie only** (owner-only).
- `POST /api/sessions/{code}/participant_base_url` with `{"url": "ftp://x"}` → `400 "URL must start with http:// or https://"`.
- `POST /api/sessions/{code}/participant_base_url` with `{"url": "http://" + "a"*600}` → `400 "URL is too long"`.
- `POST /api/sessions/{code}/participant_base_url` with `{"url": ""}` → `200 {participant_base_url: null}`.
- `POST /api/sessions/{code}/participant_base_url` with no auth → `401`.
- With a valid `mod_key` but no admin cookie → `401`.
- After success, broadcasts `{type: "session_state"}`.
- A serialized session carries `default_base_url: null` normally, and the tunnel address while one is running (`test_uc_a_06_default_base_url_follows_the_tunnel`).

**Tests (UI)**
- On `/m/<code>` as the admin owner, typing into `#base-url` and blurring updates `#invite-url` text and re-renders `#invite-qr`.
- Clicking `#base-url-clear` clears `#base-url`, and the page falls back to `location.origin` for the QR/URL widgets.
- With no session base URL and a `default_base_url` in the session payload, `/m/<code>` shows `#invite-url` and `/p/<code>` shows `#origin` with that address, not `location.origin` (`test_uc_a_06_pages_use_the_default_base_url`).
- Entering an invalid URL (no `http(s)://`) shows an error toast.

### UC-A-07: Delete a session

- **Given** the admin clicks Delete on a session row, or **Delete
  session…** in the session page's Session settings card (which opens
  `/?delete=<code>` and runs the same flow on the list)
- **When** the session is `live` → the action is refused with
  "End the session before deleting it" (toast)
- **And** the session has no data (0 queries, 0 quiz runs, 0 feedback
  and 0 attendee profiles) → a native `confirm()` followed by `DELETE`
  deletes it
- **And** the session has data (any of those) → a confirm card opens
  below the table warning what will be lost (each count:
  questions, quiz runs, feedback responses, attendee profiles), with a
  typed-title input that must match `session.title` exactly to enable the
  Delete button. The server applies the same rule: it asks for the typed
  title whenever any of the four counts is non-zero
- **Then** on success, the session is removed; cascade-deletes its
  queries, votes, participants, quiz_runs, submissions, and feedback, and
  deletes its participants' profile photograph files from the uploads
  folder.
  QuizVersions are NOT touched (they belong to Quiz templates).

**Tests (API)**
- `DELETE /api/sessions/{code}` on a `planning` session with 0 queries/quiz_runs (no body) → `200 {ok: true}`. Auth: admin cookie.
- `DELETE /api/sessions/{code}` on a `live` session → `400 "End the session before deleting it"`.
- `DELETE /api/sessions/{code}` on a session with queries/quiz_runs but missing `confirm_title` → `400 "Type the session title exactly to confirm deletion"`.
- The same `400` for a session whose only data is feedback, and for one whose only data is an attendee profile; a participant who only opened the page doesn't count as data (`test_uc_a_07_feedback_or_profile_needs_typed_title`).
- `DELETE /api/sessions/{code}` with `{"confirm_title": "Wrong"}` → `400 "Type the session title exactly to confirm deletion"`.
- `DELETE /api/sessions/{code}` with `{"confirm_title": <exact title>}` → `200 {ok: true}`; cascade removes the session's Queries, QueryVotes, Participants, QuizRuns, QuizSubmissions, and feedback (current and history rows); QuizVersions for the underlying Quiz and other sessions' rows remain (`test_uc_a_07_delete_cascades_to_session_data`).
- `DELETE /api/sessions/{code}` on a session where a participant uploaded a profile photograph → `200`; the photograph's file is gone from the uploads folder and `GET` of its URL → `404` (`test_uc_a_07_delete_session_removes_profile_photos`).
- `DELETE /api/sessions/{code}` by a non-owner admin → `403 "Not your session"`.
- `DELETE /api/sessions/{code}` with no auth → `401`.

**Tests (UI)**
- On `/`, clicking Delete on a `live` row shows toast "End the session before deleting it" and no row is removed.
- Clicking Delete on a `planning` row with no data fires a native `confirm()`; accepting removes the row from `#session-rows`.
- Clicking Delete on a row with data opens `#confirm-delete-card` below the table with the warning text in `#cd-warn`.
- Clicking Delete on a row whose only data is an attendee profile and feedback opens `#confirm-delete-card` (no native `confirm()`), and `#cd-warn` names "1 feedback response" and "1 attendee profile" (`test_uc_a_07_profile_and_feedback_open_the_confirm_card`).
- `#cd-go` is disabled until `#cd-confirm` exactly matches `session.title`.
- Typing the exact title enables `#cd-go`; clicking it removes the row.
- Clicking `#cd-go` twice in quick succession sends one `DELETE` and shows no error toast (`test_uc_a_07_double_click_delete_sends_once`).
- `#cd-cancel` closes the confirm card without deleting.
- On `/m/<code>` as the admin owner, clicking `#set-delete` on an empty `planning` session opens `/?delete=<code>`, fires the native `confirm()`, and, once accepted, the row is gone from `#session-rows`.
- On `/m/<code>` of a `live` session, clicking `#set-delete` shows the toast "End the session before deleting it." in place and stays on the session page (`test_uc_a_07_delete_on_a_live_session_page_stays_put`).

### UC-A-08: The admin session page

Because Admin ⊇ Moderator, the admin and delegate moderators share one
session page, `/m/<code>`. The admin owner sees every moderator facility
(lifecycle, invite, quiz runs, questions, profiles, feedback) plus the
owner-only controls; a delegate sees the same page without them.

- **Given** the admin clicks a session row on `/`
- **Then** `/m/<code>` loads the full moderator surface without a key
  gate (admin owners authenticate via cookie)
- **And** the owner sees a **Session settings** card (`#settings-card`)
  inside Set up, with the Title input (UC-A-05), a "Share moderator
  URL" copy button for delegation, and **Delete session…** (UC-A-07)
- **And** the owner sees the whole-session **Export ▾** (UC-A-30) in the
  Session lifecycle card, in every state
- **And** the owner sees the Base URL field in the Invite card (UC-A-06)
- **And** a delegate (mod_key, no admin cookie) sees neither the
  Session settings card nor the Base URL field, nor the sentence that
  explains the field (`#base-url-help`)
- **And** "Share moderator URL" fetches the key on click from
  `GET /api/sessions` (owner-only) and copies `<origin>/m/<code>#k=<mod_key>`;
  the key is never rendered into the DOM

**Tests (API)**
- `POST /api/sessions/{code}/start` with admin cookie on a `planning` session → `200 {status: "live"}`; sets `started_at`. Auth: mod-key OR admin cookie.
- `POST /api/sessions/{code}/end` with admin cookie → `200 {status: "ended"}`; sets `ended_at`.
- `POST /api/sessions/{code}/start` on an `ended` session → `400 "Session has ended"`.

**Tests (UI)**
- On `/` (authed), clicking a row in `#session-rows` navigates to `/m/<code>`; the moderator surface loads with no `#modkey-card` gate, and `#settings-card` is visible.
- Clicking `#set-share-mod` copies the moderator URL (with `#k=<mod_key>` fragment) to clipboard and toasts confirmation.
- Opening `/m/<code>#k=<mod_key>` as a delegate (no admin cookie) hides `#settings-card`, `#base-url`, and `#base-url-help`; the owner sees `#base-url-help` and the `#base-url` placeholder "e.g. https://quiz.example.org" (`test_uc_a_08_base_url_help_follows_the_field`).
- Start and End on the session page are covered by UC-M-02.

---

**Quiz authoring** (UC-A-09 through UC-A-22, and UC-A-27 through UC-A-29). Each operation gets its
own use case so tests and PRs can cite one ID per behavior.

### UC-A-09: Create a quiz template

- **Given** the admin clicks **+ New** on `/quizzes` with a title
- **When** `POST /api/quizzes` is called
- **Then** a Quiz is created with `owner_user_id = me.id`, status =
  `draft`, `last_edited_at = now`; the new quiz opens in the editor

**Tests (API)**
- `POST /api/quizzes` with `{"title": "Trivia"}` → `200 {id, title: "Trivia", status: "draft"}`. Auth: admin cookie.
- `POST /api/quizzes` with `{"title": ""}` → `200 {id, title: "Untitled quiz", status: "draft"}` (default applied).
- `POST /api/quizzes` with no auth → `401`.

**Tests (UI)**
- On `/quizzes` (authed), typing a title in `#new-quiz-title` and clicking `#create-quiz` adds a row to `#quiz-rows` and opens `#editor-card` with that quiz.
- Pressing Enter in `#new-quiz-title` submits.
- Clicking `#create-quiz` with an empty title shows the error toast "Quiz title is required" and creates nothing (`test_uc_a_09_empty_title_says_title_is_required`).
- Pressing Enter twice in quick succession in `#new-quiz-title` creates one quiz (`test_uc_a_09_double_enter_creates_one_quiz`).

### UC-A-10: Browse the quiz library

- **Given** the admin is on `/quizzes`
- **When** `GET /api/quizzes` (optionally `?ready_only=true`) is called
- **Then** the response includes only quizzes owned by the admin,
  ordered by `created_at desc`, with `status` and `question_count`
- **And** moderator dropdowns use `ready_only=true`; the quiz library
  table uses the full list
- **And** editing a Ready quiz keeps it Ready (UC-A-14), even when the
  edit breaks a publish rule (UC-A-21), for example deleting its only
  question. Such a quiz carries `problem`, the first failing rule's
  message, and can't be added to a session until it is fixed. Its row
  shows a **Needs fixing** badge (`.badge-needs-fixing`) beside the Ready
  badge. Every other quiz, including every draft, has `problem: null`

**Tests (API)**
- `GET /api/quizzes` → `200 [{id, title, status, question_count, sessions, problem}, ...]` ordered `created_at desc`. Auth: admin cookie.
- A Ready quiz whose only question is then deleted stays `status: "ready"` and reports `problem: "Quiz needs at least one question"`; adding a question with two answers and a correct one sets `problem` back to `null`. A draft reports `problem: null` (`test_uc_a_10_ready_quiz_edited_into_an_invalid_state_reports_problem`).
- `sessions` lists each session that holds a run of the quiz: `{code, title, session_status, run_status, run_count}`, where `run_status` is the most relevant state of its runs there (`live` over `queued` over `closed`). A quiz never run has `sessions: []`. The same server function produces `in_session` for UC-M-03, so the library and the session page always agree.
- A quiz owned by another admin is not in the response.
- `GET /api/quizzes?ready_only=true` returns only quizzes with `status: "ready"`.
- `GET /api/quizzes` with no auth → `401`.

**Tests (UI)**
- On `/quizzes` (authed), `#quiz-rows` contains a row per owned quiz with title, status badge, and question count.
- A Ready quiz with a `problem` shows `.badge-ready` and `.badge-needs-fixing` ("Needs fixing") in its row; a valid Ready quiz shows no `.badge-needs-fixing` (`test_uc_a_10_needs_fixing_badge`).
- The open editor says the same, so the author sees it while editing: after an edit that breaks a publish rule (for example inserting a blank question into a Ready quiz, or clearing a question's text), `#editor-body` shows `.badge-needs-fixing` beside the Ready badge, the affected question carries its inline problem notes, and the editor's problem navigator shows the count (UC-A-21); fixing or removing the cause hides the badge, the notes and the navigator (`test_uc_a_10_editor_warns_when_an_edit_breaks_a_publish_rule`).
- Order: most recently created first.

### UC-A-11: Open a quiz for editing

- **Given** the admin clicks a row in the library
- **When** `GET /api/quizzes/{id}?include_correct=true` is called
- **Then** the editor pane shows the title, questions, answers, and
  per-answer correctness
- **And** the route returns `404` for a non-owner (no read access
  across owners)

**Tests (API)**
- `GET /api/quizzes/{id}?include_correct=true` → `200 {id, title, status, questions: [{id, text, image_url, qtype, order_index, answers: [{id, text, image_url, order_index, is_correct}]}], problems: [{question_id, answer_id, field, message}]}`. Auth: admin cookie. `problems` lists every failing publish rule (UC-A-21) for drafts and Ready quizzes alike, and is `[]` when the quiz can be published.
- `include_correct=false` (default) omits `is_correct` from answer objects.
- `GET /api/quizzes/{id}` for a quiz owned by another admin → `404`.
- `GET /api/quizzes/{id}` for a non-existent id → `404`.
- `GET /api/quizzes/{id}` with no auth → `401 "Not authenticated"`, as for the other quiz routes, so an expired sign-in in the editor redirects to `/` (`test_uc_a_11_get_quiz_signed_out_is_401`).

The editor card sits directly below the quiz list and scrolls into view
when it opens, so on a phone the editor appears where the admin is
looking. Every editor control has an accessible name ("Question 1 text",
"Question 1 type", "Answer 1 text", "Answer 1 is correct"), and images
are added with an **Add image** button rather than a bare file input.
Controls whose meaning matters on a touch screen carry visible words,
not only a tooltip: each answer's checkbox reads "Correct", the Poll
checkbox reads "Poll (no correct answer)", and the question type reads
"Single choice" or "Multiple choice". The hint under the badge says
"Changes apply the next time you add this quiz to a session; past
results stay as they were."

**Tests (UI)**
- On `/quizzes`, clicking a row in `#quiz-rows` opens `#editor-card`, populates `#editor-title`, and `#editor-body` lists each question with its answers and a correctness marker per answer.
- `#editor-card` immediately follows `#quiz-library-card` in the page and is in the viewport after opening, at desktop and phone widths.
- The first question's text box is reachable by role as "Question 1 text", its first answer as "Answer 1 text", and that answer's checkbox as "Answer 1 is correct".
- Each answer row of a graded question shows the visible word "Correct" beside its checkbox; the Poll toggle reads "Poll (no correct answer)"; the type select offers "Single choice" and "Multiple choice"; the hint doesn't mention "Launch" (`test_uc_a_11_editor_controls_have_visible_words`).

### UC-A-12: Rename a quiz

- **Given** the editor is open
- **When** the admin edits the title input and blurs
- **Then** `PATCH /api/quizzes/{id}` updates the title and advances
  `last_edited_at`
- **And** an empty title is refused with `400 "Quiz title is required"`
  (as for sessions, UC-A-05); the existing title is kept, and the editor
  shows the message and puts the saved title back in the field
- **And** status does **not** auto-revert from `ready` → `draft`
  (versioning protects history)

**Tests (API)**
- `PATCH /api/quizzes/{id}` with `{"title": "New"}` (different from current) → `200 {ok: true, status}`; updates `title` and advances `last_edited_at`. Auth: admin cookie.
- `PATCH /api/quizzes/{id}` with `{"title": ""}` or `{"title": "   "}` → `400 "Quiz title is required"`; title stays unchanged AND `last_edited_at` does NOT advance.
- `PATCH /api/quizzes/{id}` with `{"title": "<same as current>"}` → `200`; same no-op behavior (no change, no edit bump).
- After PATCH on a `ready` quiz, `GET /api/quizzes/{id}` still returns `status: "ready"`.
- `PATCH /api/quizzes/{id}` for a non-owner quiz → `404`.

**Tests (UI)**
- In `#editor-card`, editing the title input and blurring updates the row's title in `#quiz-rows`.
- Clearing the title and blurring shows the error toast "Quiz title is required", puts the saved title back in the field and in `#editor-title`, and leaves the row unchanged (`test_uc_a_12_empty_title_is_refused_and_restored`).

### UC-A-13: Delete a quiz template

- **Given** the admin clicks Delete in a quiz row's ⋯ menu
- **When** no QuizVersion of this quiz has been used in any run
- **Then** `DELETE /api/quizzes/{id}` cascades to items, options, and
  versions
- **And** if any version has been used, returns `400 Quiz has been
  used in a session run and cannot be deleted` (preserves session
  data)

**Tests (API)**
- `DELETE /api/quizzes/{id}` for an unused quiz → `200 {ok: true}`; cascade deletes Questions, Answers, and any QuizVersions. Auth: admin cookie.
- `DELETE /api/quizzes/{id}` for a quiz with at least one QuizRun → `400 "Quiz has been used in a session run and cannot be deleted"`.
- `DELETE /api/quizzes/{id}` for a non-owner quiz → `404`.

**Tests (UI)**
- On `/quizzes`, opening a row's ⋯ menu (`details.menu`) in `#quiz-rows` and clicking Delete (after native confirm) removes the row.
- Clicking Delete on a quiz that has been run shows an error toast and the row stays.

### UC-A-27: Duplicate a quiz template

- **Given** the admin clicks **Duplicate** in a quiz row's ⋯ menu
- **When** `POST /api/quizzes/{id}/duplicate` is called
- **Then** a new Quiz is created with `owner_user_id = me.id`, title
  `"<source title> (copy)"`, status = `draft`, and `last_edited_at = now`
- **And** every Question (text, image, `qtype`, `graded`, order) and
  every Answer (text, image, correctness, order) is copied into the new
  quiz; image files are shared by URL, not re-uploaded
- **And** the copy has no QuizVersions and no runs; the source quiz,
  its versions, and its runs are unchanged
- **And** the copy opens in the editor, where it is edited like any
  other quiz (UC-A-12 … UC-A-19) without affecting the source
- **And** a source title too long for the 200-character column is
  truncated so that the `" (copy)"` suffix still fits

**Tests (API)**
- `POST /api/quizzes/{id}/duplicate` → `200 {id, title: "<title> (copy)", status: "draft"}` with a new `id`. Auth: admin cookie.
- `GET /api/quizzes/{new_id}?include_correct=true` returns the same questions and answers as the source (text, `image_url`, `qtype`, `graded`, `order_index`, `is_correct`), with new ids.
- Duplicating a `ready` quiz leaves the source `ready` and returns the copy as `draft`.
- Editing a question or answer of the copy does not change the source.
- Duplicating a quiz that has been used in a run succeeds; the copy has no runs and can be deleted (UC-A-13).
- A source title of 200 characters yields a copy title of at most 200 characters ending in `" (copy)"`.
- `POST /api/quizzes/{id}/duplicate` for a non-owner quiz → `404`; for a non-existent id → `404`.
- `POST /api/quizzes/{id}/duplicate` with no auth → `401`.

**Tests (UI)**
- On `/quizzes`, opening a row's ⋯ menu in `#quiz-rows` and clicking Duplicate adds a `"<title> (copy)"` row with a Draft badge and opens `#editor-card` on the copy.

### UC-A-14: Add a quiz question

- **Given** the quiz editor is open
- **And** the editor shows an **insertion point** before the first
  question, between every two questions, and after the last (an empty
  quiz shows one); the one after the last is the only way to add at
  the end, so there is no separate add button
- **When** the admin clicks an insertion point
- **Then** `POST /api/quizzes/{id}/questions` with `position` (the
  0-based index the new question takes) adds a blank question there in
  one transaction: questions at or after that index move down by one
  and every question's `order_index` is renumbered `0..n`
- **And** the editor re-renders with the cursor in the new question's
  text field, ready to type
- **And** without `position` the question is added at the end
  (`order_index = max + 1`); `position` equal to the question count
  also adds at the end
- **And** a `position` that is negative or greater than the question
  count returns `400 "position out of range"`; a non-integer returns
  `400 "position must be an integer"`; nothing changes
- **And** the parent's `last_edited_at` advances, as for any edit:
  past runs keep their frozen QuizVersion and a `ready` quiz stays
  `ready`
- **And** a `qtype` not in `("single", "multi")` returns `400`
- **And** an explicit `order_index` (without `position`) must be an
  integer; anything else returns `400 "order_index must be an integer"`
- **And** `graded` (default `true`) marks whether the question has a
  correct answer; `graded: false` is a **poll/survey** question (options
  but no correct answer — e.g. age / experience range)

**Tests (API)**
- `POST /api/quizzes/{id}/questions` with `{}` → `200 {id}`; new Question appended with `order_index = max+1`, `text = ""` (empty), `qtype = "single"`, `graded = true`, parent `last_edited_at` advances. Auth: admin cookie. Note: the **backend** defaults `text` to empty string; the UI passes `{"text": "New question"}` so users see a sensible placeholder, but that string is a frontend choice.
- `POST /api/quizzes/{id}/questions` with `{"text": "X", "qtype": "multi"}` → `200`; created with `text: "X"`, `qtype: "multi"`.
- `POST /api/quizzes/{id}/questions` with `{"graded": false}` → `200`; created as a poll question (`graded: false`), surfaced by `GET /api/quizzes/{id}`.
- `POST /api/quizzes/{id}/questions` with `{"qtype": "bogus"}` → `400 "qtype must be single or multi"`.
- With `{"order_index": "abc"}` → `400 "order_index must be an integer"`; nothing is added and the next append succeeds (`test_uc_x_05_order_index_must_be_an_integer_on_create`).
- On a quiz with questions A, B, C: `{"text": "N", "position": 0}` → `GET /api/quizzes/{id}` lists N, A, B, C with `order_index` `0..3`; `{"position": 1}` lists A, N, B, C; `{"position": 3}` lists A, B, C, N; omitting `position` lists A, B, C, N.
- `{"position": -1}` or `{"position": 4}` on a three-question quiz → `400 "position out of range"`; `{"position": "x"}` → `400 "position must be an integer"`; the questions and their order are unchanged.
- Inserting with `position` advances `last_edited_at` and leaves a `ready` quiz `ready`; a run launched before the insert keeps its questions, a run launched after includes the new one.
- For a non-owner quiz → `404`; with no auth → `401`.

**Tests (UI)**
- In `#editor-body`, a quiz with N questions shows N+1 insertion points (`button.insert-point`): "Insert a question before question 1" … "Insert a question before question N", then "Add a question at the end". An empty quiz shows one, "Add the first question". No other button adds a question.
- Clicking "Insert a question before question 2" adds a question in second place; its text field shows "New question" and has focus. Inserting before question 1 and at the end puts the new question first and last. The order persists after reopening the quiz. The frontend submits `{"text": "New question", "qtype": "single", "position": <index>}`.
- At 390 px wide on a touch device, the insertion points are visible without hover and at least 32 px tall.
- Each question row has a **Poll** checkbox next to the type selector; ticking it PATCHes `{graded: false}` and re-renders the row so the per-answer "correct" checkboxes disappear (a poll has no correct answer). Unticking restores them.

### UC-A-15: Edit a quiz question

- **Given** the admin focuses a question's text, type, image, or order
- **When** `PATCH /api/quiz_questions/{id}` is called with any subset of
  `text` / `qtype` / `graded` / `image_url` / `order_index`
- **Then** the fields update; parent quiz `last_edited_at` advances
- **And** invalid `qtype` returns `400`; non-int `order_index`
  returns `400`
- **And** `graded` toggles whether the question is scored (has a correct
  answer) or a poll/survey question

**Tests (API)**
- `PATCH /api/quiz_questions/{qid}` with `{"text": "Why?"}` → `200 {ok: true}` and updates text + parent `last_edited_at`. Auth: admin cookie.
- With `{"qtype": "multi"}` → updates qtype.
- With `{"graded": false}` → marks the question as a poll; `GET /api/quizzes/{id}` then reports `graded: false` for it.
- With `{"qtype": "bogus"}` → `400 "qtype must be single or multi"`.
- With `{"order_index": "x"}` → `400 "order_index must be an integer"`.
- With `{"image_url": null}` → clears image_url; with `{"image_url": "/uploads/x.png"}` → sets it.
- For a question whose quiz is owned by another admin → `404`.

**Tests (UI)**
- In `#editor-body`, blurring a question text input PATCHes and updates the editor state.
- Switching the qtype dropdown PATCHes and re-renders the answer list constraints (single vs multi correctness UI).

### UC-A-16: Delete a quiz question

- **Given** the admin clicks Delete on a question (with `confirm()`)
- **When** `DELETE /api/quiz_questions/{id}` is called
- **Then** the question and its answers are removed via cascade; parent
  quiz `last_edited_at` advances

**Tests (API)**
- `DELETE /api/quiz_questions/{qid}` → `200 {ok: true}`; cascade deletes its Answers; parent quiz `last_edited_at` advances. Auth: admin cookie.
- For a question whose quiz is owned by another admin → `404`.

**Tests (UI)**
- In `#editor-body`, clicking Delete on a question (after native confirm) removes its row.

### UC-A-17: Add an answer to a question

- **Given** the admin clicks **+ Answer** under a question
- **When** `POST /api/quiz_questions/{id}/answers` is called
- **Then** an `Answer` is added at the end with
  `is_correct = false`; parent quiz `last_edited_at` advances
- **And** an explicit `order_index` must be an integer; anything else
  returns `400 "order_index must be an integer"`

**Tests (API)**
- `POST /api/quiz_questions/{qid}/answers` with `{"order_index": "abc"}` → `400 "order_index must be an integer"`; nothing is added and the next append succeeds (`test_uc_x_05_order_index_must_be_an_integer_on_create`).
- `POST /api/quiz_questions/{qid}/answers` with `{}` → `200 {id}`; new Answer at `order_index = max+1`, `text = ""` (empty), `is_correct: false`; parent quiz `last_edited_at` advances. Auth: admin cookie. Note: backend default `text` is empty string; the UI passes `"New answer"` as a sensible starting value.
- For a question owned by another admin → `404`.

**Tests (UI)**
- In `#editor-body`, clicking `+ Answer` under a question appends an answer row. The frontend submits `{"text": "New answer"}`, so the row shows "New answer" as the editable starting value and the correctness checkbox is unchecked.

### UC-A-18: Edit an answer

- **Given** the admin changes an answer's text, correctness, image,
  or order
- **When** `PATCH /api/quiz_answers/{id}` is called
- **Then** the fields update; parent quiz `last_edited_at` advances
- **And** non-int `order_index` returns `400`

**Tests (API)**
- `PATCH /api/quiz_answers/{aid}` with `{"text": "Right"}` → `200 {ok: true}`. Auth: admin cookie.
- With `{"is_correct": true}` → updates flag.
- With `{"order_index": "x"}` → `400 "order_index must be an integer"`.
- With `{"image_url": "/uploads/x.png"}` → sets image_url; `{"image_url": null}` → clears.
- For an answer in a non-owner quiz → `404`.

**Tests (UI)**
- In `#editor-body`, blurring an answer text input PATCHes; toggling the correct checkbox PATCHes.

### UC-A-19: Delete an answer

- **Given** the admin clicks ✕ on an answer
- **When** `DELETE /api/quiz_answers/{id}` is called
- **Then** the answer is removed; parent quiz `last_edited_at`
  advances

**Tests (API)**
- `DELETE /api/quiz_answers/{aid}` → `200 {ok: true}`; parent quiz `last_edited_at` advances. Auth: admin cookie.
- For an answer in a non-owner quiz → `404`.

**Tests (UI)**
- In `#editor-body`, clicking ✕ on an answer removes its row.
- When the delete fails (the server answers with an error), the editor shows the server's message in an error toast and keeps the row; no error goes unhandled. Title changes, question deletes, and **+ Answer** behave the same way (`test_uc_a_19_failed_answer_delete_shows_the_error`).

### UC-A-28: Reorder questions and answers

- **Given** the quiz editor is open
- **When** the admin drags a question by its handle (`.drag-handle`) to a
  new position, or clicks its **Move up** / **Move down** button
- **Then** `PUT /api/quizzes/{id}/question_order` saves the full new
  order in one request; every question's `order_index` is renumbered
  `0..n-1` and the parent's `last_edited_at` advances
- **And** answers within a question reorder the same way, saved by
  `PUT /api/quiz_questions/{id}/answer_order`
- **And** the body must list every id of the quiz's questions (or the
  question's answers) exactly once; anything else returns `400` and
  changes nothing
- **And** the editor labels questions by position (`Q1`, `Q2`, …), so
  numbering has no gaps after deletes
- **And** reordering is an ordinary edit: past runs keep their frozen
  QuizVersion; the next Launch captures the new order
- **And** drag uses pointer events, so it works with a mouse and on
  touch screens; Move up / Move down cover keyboard use

**Tests (API)**
- `PUT /api/quizzes/{id}/question_order` with `{"question_ids": [<ids in new order>]}` → `200 {ok: true}`; `GET /api/quizzes/{id}` returns questions in that order with `order_index` `0..n-1`; `last_edited_at` advances. Auth: admin cookie.
- A list that omits an id, repeats an id, or contains another quiz's question id → `400 "question_ids must list every question in this quiz exactly once"`; order unchanged.
- A non-list `question_ids` → same `400`.
- A list of the right length whose entries are not integers (`[{"a": 1}]`, `["1"]`, `[true]`) → same `400`, not `500` (`test_uc_a_28_reorder_rejects_non_integer_ids`).
- For a non-owner quiz → `404`; with no auth → `401`.
- `PUT /api/quiz_questions/{qid}/answer_order` with `{"answer_ids": [...]}` → `200 {ok: true}`; answers come back in that order with `order_index` `0..n-1`; parent `last_edited_at` advances.
- A bad `answer_ids` list → `400 "answer_ids must list every answer of this question exactly once"`.
- `answer_order` for a non-owner question → `404`.
- A run launched before a reorder keeps its question order; a run launched after uses the new order.

**Tests (UI)**
- In `#editor-body`, clicking a question's "Move question down" button moves it below the next question; the order persists after reopening the quiz.
- Dragging a question's `.drag-handle` above the previous question reorders the questions; the order persists after reopening.
- "Move question up" is disabled on the first question and "Move question down" on the last.
- Clicking an answer's "Move answer up" button moves it above the previous answer; the order persists after reopening.

### UC-A-20: Upload an image

Used by question and answer editors to set `image_url`.

- **Given** the admin picks a file via a file input
- **When** `POST /api/uploads` is called (multipart) by the admin
- **Then** the server enforces extension ∈ `{.png, .jpg, .jpeg, .gif,
  .webp}` (SVG explicitly excluded), Content-Length ≤ 5 MB, and a
  streaming 5 MB cap; saves under a fresh UUID name; returns
  `{url: "/uploads/<uuid>.<ext>"}`
- **And** the calling page then `PATCH`es the question or answer with
  the new `image_url`

**Tests (API)**
- `POST /api/uploads` (multipart `file`) with a valid `.png` ≤ 5 MB → `200 {url: "/uploads/<uuid>.png"}`. Auth: admin cookie.
- `.jpg`, `.jpeg`, `.gif`, `.webp` are also accepted.
- `.svg` → `400 "Images must be PNG, JPEG, GIF or WebP"`.
- `.exe` or no extension → `400 "Images must be PNG, JPEG, GIF or WebP"`.
- 6 MB file (Content-Length header set) → `400 "Images must be 5 MB or smaller"`.
- 6 MB streamed payload (no Content-Length) → `400 "Images must be 5 MB or smaller"`.
- `POST /api/uploads` with no auth → `401`.
- In the editor, each question and answer offers an **Add image** button (**Change image** once set) that opens the hidden file input.

**Tests (UI)**
- In `#editor-body`, picking an image file via the question's file input uploads, then PATCHes the question with the new `image_url`, then re-renders the thumbnail.
- Same flow under each answer row updates its thumbnail.
- Picking a file the server refuses (for example a `.txt`) shows the server's message as an error toast ("Images must be PNG, JPEG, GIF or WebP"), not a generic "Upload failed"; the upload goes through `api()`, so an expired sign-in redirects to `/` (`test_uc_a_20_refused_upload_shows_the_reason`).

### UC-A-21: Publish a quiz

- **Given** a Draft quiz
- **When** the admin clicks Publish (`POST /api/quizzes/{id}/publish`)
- **Then** validation runs: ≥ 1 question; each question with non-empty text;
  each question with ≥ 2 answers; for **graded** questions, each `single`
  with exactly one `is_correct` answer and each `multi` with ≥ 1 correct
  answer; each answer with non-empty text OR `image_url`
- **And** a **poll** question (`graded: false`) is exempt from the
  correct-answer rules — it needs only text + ≥ 2 non-empty answers
- **And** on pass, status → `ready`
- **And** on fail, returns `400` with the first failing rule's message
  ("Question 2 (single choice) needs exactly one correct answer")
- **And** the quiz detail (`GET /api/quizzes/{id}`, UC-A-11) lists every
  failing rule in `problems`, in quiz order. Each entry has
  `question_id` (`null` for the quiz-level rule), `answer_id` (`null`
  unless the rule is about one answer), `field` (`questions`, `text`,
  `answers`, `correct` or `answer`) and `message`, a short instruction
  written for its place in the editor: "Add at least one question",
  "Add the question text", "Add at least 2 answers", "Mark exactly one
  correct answer", "Mark at least one correct answer", "Add answer text
  or an image"
- **And** a failed Publish shows every problem in the editor, not one
  message: the quiz's editor opens if it was closed, each question with a
  problem gets a thin warning-coloured stripe, and each problem's note
  sits next to the field it is about (under the question text for the
  text, answer-count and correct-answer rules; under the answer for an
  empty answer; beside **Add the first question** for an empty quiz).
  A short toast says "Not published: fix the marked problems". A
  navigator in the editor header reads "N to fix"; its **↑** and **↓**
  buttons ("Previous problem", "Next problem") scroll to each problem in
  turn, focus its field, wrap at the ends and show the position ("2 of
  3"). Each note is the field's accessible description
- **And** once shown for a quiz, the notes update after every edit and
  disappear as each problem is fixed; the navigator disappears with the
  last one. A Ready quiz that an edit broke shows its notes and the
  navigator without a Publish (UC-A-10). A draft that hasn't failed a
  Publish shows no notes while it is being written

**Tests (API)**
- `POST /api/quizzes/{id}/publish` on a quiz with ≥ 1 question, each having text, ≥ 2 answers, valid correctness, and non-empty answers → `200 {status: "ready"}`. Auth: admin cookie.
- On a quiz with 0 questions → `400 "Quiz needs at least one question"`.
- Question 1 with empty text → `400 "Question 1 is missing text"`.
- Question 1 with 1 answer → `400 "Question 1 needs at least 2 answers"`.
- `single` question with 0 or 2 correct answers → `400 "Question N (single choice) needs exactly one correct answer"`.
- `multi` question with 0 correct answers → `400 "Question N (multiple choice) needs at least one correct answer"`.
- A **poll** question (`graded: false`) with text + 2 non-empty answers and **no correct answer** → publish `200 {status: "ready"}` (correct-answer rules skipped). On a launched run the serialized current question reports `graded: false` and its answers carry **no** `is_correct` even after reveal/close; `GET /api/quiz_runs/{id}/results` reports `is_correct: false` for every poll answer.
- Answer with empty text and no `image_url` → `400 "Question N, answer M is empty"`.
- For a non-owner quiz → `404`.
- For a draft with a question missing text, a question with one answer, a graded single-choice question with two correct answers, a question with an empty answer, and a poll with no correct answer, `GET /api/quizzes/{id}` lists one problem per broken rule with its `question_id`, `answer_id`, `field` and `message`, and none for the poll; Publish still returns `400` with the first numbered message (`test_uc_a_21_quiz_detail_lists_every_problem`).
- A quiz with no questions lists one quiz-level problem `{question_id: null, answer_id: null, field: "questions", message: "Add at least one question"}`; a publishable draft or Ready quiz lists `problems: []` (`test_uc_a_21_quiz_level_and_empty_problem_lists`).

**Tests (UI)**
- In `#quiz-rows`, clicking a valid draft quiz's Publish button flips its status badge to `.badge-ready`.
- Clicking a draft's Publish in `#quiz-rows` while its editor is closed, when three questions break rules, opens `#editor-card`; the three questions carry `.has-problem` and one `.problem-note` each, `#editor-problem-count` reads "3 to fix", and the toast says "Not published: fix the marked problems" (no error toast). **Next problem** focuses each problem's field in turn and wraps to the first; **Previous problem** goes back; `#editor-problem-pos` shows the position. Fixing one problem updates the count; fixing all hides the notes and the navigator, and Publish then flips the badge to `.badge-ready` (`test_uc_a_21_failed_publish_marks_every_problem_inline`).
- Publishing an empty quiz from its row keeps it `draft` and shows "Add at least one question" beside **Add the first question**, with the navigator reading "1 to fix" (`test_uc_a_21_publish_empty_quiz_marks_where_questions_are_added`).
- A draft with problems that hasn't failed a Publish shows no `.problem-note`, no `.has-problem` and no navigator, also after an edit (`test_uc_a_21_draft_shows_no_problems_before_publish`).

### UC-A-22: Unpublish a quiz

- **Given** a Ready quiz
- **When** `POST /api/quizzes/{id}/unpublish` is called
- **Then** status → `draft`
- **And** quiz versions already captured for prior runs are NOT
  affected (history preserved)

**Tests (API)**
- `POST /api/quizzes/{id}/unpublish` on a `ready` quiz → `200 {status: "draft"}`. Auth: admin cookie.
- Pre-existing QuizVersion rows for this quiz are unchanged afterward.
- For a non-owner quiz → `404`.

**Tests (UI)**
- In `#quiz-rows`, clicking a ready quiz's Unpublish button flips its status badge from `.badge-ready` to `.badge-draft`.

---

**Reports**

### UC-A-29: Add a quiz to a session from the library

- **Given** the admin is on `/quizzes`
- **When** they open a quiz row's **Add to session** menu
- **Then** the menu lists the admin's sessions that have not ended:
  `live` first, then `planning`, newest first within each group
- **When** they click a session
- **Then** the quiz is queued in that session
  (`POST /api/sessions/{code}/quiz_runs`, UC-M-03) and a toast names the
  session
- **And** for a draft quiz the request sends `publish: true`, so a valid
  draft is published and queued in one step; an invalid draft shows the
  publish validation message and nothing is queued
- **And** with no open sessions, the menu says so and links to `/`
- **And** for a Ready quiz with a `problem` (UC-A-10), the menu lists no
  sessions; it says "Can't be added to a session yet:" followed by the
  problem and "Open the quiz to fix it.", so nothing is sent that would
  fail
- **And** a session that already holds a run of this quiz (from the
  quiz's `sessions`, UC-A-10) says so on its menu item ("Already added ·
  Queued", "· Live", or "· Closed", the shared status labels). Clicking it asks for confirmation
  before adding another run (repeating a quiz is allowed but usually a
  mistake); declining adds nothing

**Tests (UI)**
- On `/quizzes`, opening a ready quiz row's Add to session menu lists a `planning` session and a `live` session (live first) but not an `ended` one; clicking the planning session toasts its title, and `GET /api/sessions/{code}/quiz_runs` returns one queued run.
- Doing the same for a valid draft quiz flips the row's badge to Ready and queues a run.
- Doing the same for an invalid draft (no questions) shows an error toast; the badge stays Draft and no run is queued.
- For a Ready quiz whose only question was deleted, the menu shows "Can't be added to a session yet: Quiz needs at least one question" and no session buttons (`test_uc_a_29_needs_fixing_quiz_cannot_be_added`).
- For a quiz already queued in a session, that session's menu item reads "Already added · Queued"; other sessions' items don't say "Already added". Clicking it and dismissing the confirmation queues nothing; accepting it queues a second run.

### UC-A-23: Global quiz-runs report

- **Given** the admin owns sessions with QuizRuns
- **When** they open `/quizzes` and view the "Quiz runs" table
- **Then** they see every QuizRun across all their sessions (joined
  via owner), with quiz title, version number, session code, status,
  progress, respondent count, and created time
- **And** they can switch between **Flat**, **By quiz**, **By version**,
  and **By session** without refetching or changing the underlying run set
- **And** grouped views use collapsible group sections, while the chosen
  non-flat view is reflected in `?runs=quiz|version|session`

**Tests (API)**
- `GET /api/quiz_runs` → `200 [{id, status, session_code, session_title, quiz_id, quiz_title, version_no, current_question_idx, question_count, respondent_count, created_at, started_at, closed_at}, ...]`. Auth: admin cookie.
- Rows from another admin's sessions are excluded.
- Order is `created_at desc`.
- `GET /api/quiz_runs` with no auth → `401`.

**Tests (UI)**
- On `/quizzes`, `#qs-rows` shows one row per QuizRun across owned sessions, with quiz title, version, session code, status badge, progress, and respondents. The column headers are spelled out ("Version", "Responses"), and the view summary uses plain words (no "playthrough" or "immutable") (`test_uc_a_23_run_report_uses_plain_words`).
- `#run-view-switcher` exposes four `aria-pressed` buttons. Selecting By quiz groups on `quiz_id`; By version groups on `(quiz_id, version_no)`; By session groups on `session_code`; selecting Flat restores `#qs-rows`.
- The quiz-library breadcrumb links back to Admin, and its section links target the quiz library and quiz-run report cards.

### UC-A-24: View one quiz-run's results

- **Given** the admin clicks a row in the Quiz runs table
- **When** `GET /api/quiz_runs/{id}/results` is called
- **Then** the inline results pane shows per-question answer counts,
  correctness markers, and respondent count; uses the snapshotted
  `quiz_title` + `version_no` so historical reports survive later
  edits to the template

**Tests (API)**
- `GET /api/quiz_runs/{id}/results` → `200 {id, status, session_code, session_title, quiz_title, version_no, current_question_idx, questions: [{id, text, qtype, answers: [{id, text, image_url, is_correct, count}], respondents}]}`. Auth: admin cookie.
- After three participants answer (two the correct answer, one the other), each answer's `count` is 2 and 1, `is_correct` marks the correct one, and `respondents` is 3 (`test_uc_a_24_results_counts_after_submission`).
- Renaming the source Quiz after the run does NOT change `quiz_title` in this response (snapshotted).
- For a run on another admin's session → `404`.

**Tests (UI)**
- On `/quizzes`, clicking a row in `#qs-rows` opens `#results-card`; `#results-body` shows per-question answer counts with correctness markers.
- `#results-title` names the thing: "Quiz run: <quiz title> · <session title>". The header line shows "Version <n>". Answers are drawn by `answerOption()` (UC-X-14): the correct one shows "✓ Correct" as text, and every count reads "<n> (<p>%)" (`test_uc_a_24_results_use_the_shared_answer_rows`).
- `#results-card` is in the viewport after opening.
- Opening `/quizzes?run=<run_id>` opens that run's `#results-card` directly (the session page's "View results →" link, UC-M-06).
- `#results-close` closes the pane.

### UC-A-25: Change admin password

- **Given** the admin is logged in and clicks **Change password** in
  the header bar on `/`
- **Then** a card appears with **Current password**, **New password**,
  **Confirm new password** fields
- **When** the admin submits with the current password correct, the
  two new-password fields matching, and the new password ≥ 8 chars
- **Then** `POST /api/admin/change_password` updates `password_hash`
  (bcrypt-rehashed), re-issues the admin session cookie, and the UI
  toasts "Password updated"; the card closes
- **And** an incorrect `current_password` returns `401`
- **And** mismatched new-password fields are blocked client-side with
  an error toast (no API call)
- **And** a new password shorter than 8 characters returns `400`
- **And** a new password longer than 72 bytes (UTF-8) returns `400
  "password must be at most 72 bytes"`, because bcrypt ignores anything
  past 72 bytes; first-run setup (UC-A-01) and `prashna reset-password`
  (UC-X-15) apply the same limit
- **And** Escape closes the card without saving

**Tests (API)**
- `POST /api/admin/change_password` with valid `{current_password, new_password}` (≥ 8 chars) → `200 {ok: true}`; re-issues the `prashna_admin` cookie; bcrypt-verifies new password. Auth: admin cookie.
- With wrong `current_password` (but valid cookie) → `401 "Current password is incorrect"`.
- With `new_password` shorter than 8 chars → `400 "New password must be at least 8 characters"`.
- With `new_password` of 73 bytes → `400 "password must be at most 72 bytes"`; `POST /api/admin/setup` with a 73-byte password gets the same `400` and creates no admin (`test_uc_a_25_password_over_72_bytes_is_refused`).
- With no cookie at all → `401 "Not authenticated"` (from `auth.current_admin`, before the handler runs). Two distinct 401 paths.
- **Old cookies are invalidated**: after a successful change_password call, the prior `prashna_admin` cookie no longer authenticates. Verified by capturing the pre-change cookie, changing password, then issuing an admin-only call with the captured cookie → `401`, while the re-issued cookie works (`test_uc_a_25_old_cookie_rejected_after_password_change`). (Implementation: signed cookies carry a `session_version`, bumped on each password change; `current_admin` rejects mismatched versions.)

**Tests (UI)**
- On `/` (authed), clicking Change password opens `#change-pw-card`.
- Submitting `#cp-current`, `#cp-new`, `#cp-new2` (matching) via `#cp-submit` toasts "Password updated" and closes the card.
- Mismatched `#cp-new`/`#cp-new2` shows an error toast and makes no API call.
- Wrong current password shows toast "Current password is incorrect" and the card stays open.
- A new password shorter than 8 chars shows the error toast "Password must be at least 8 characters" without an API call; the page checks the length before sending.
- Pressing Escape inside `#change-pw-card` closes it without submitting.
- `#cp-close` closes the card without submitting.

### UC-A-30: Export data

The admin downloads their data to keep it, analyse it, or move it
elsewhere. Several tables don't fit one CSV file, so an export is either
one nested JSON document or one Excel workbook.

- **Given** the admin is signed in and owns the data
- **When** they choose **Export ▾ → JSON** or **Export ▾ → Excel** in one
  of the places below
- **Then** the browser downloads one file holding that scope's data

**Scopes.** Each scope is one endpoint and one place in the UI. A session
scope narrows with `part`.

| Scope | Contains | Endpoint | Where in the UI |
| --- | --- | --- | --- |
| All data | Every session the admin owns, each with all of its data (as "One session"), and every quiz in the admin's quiz library (as "One quiz") | `GET /api/export/all` | `/`, Your sessions card (`#all-export`, labelled "Export all data") |
| One session | The session's details, every participant, its Q&A questions, its quiz runs with each participant's answers, and its feedback | `GET /api/sessions/{code}/export` (`part=all`, the default) | Session page, Session lifecycle card (`#session-export`, labelled "Export session"), in every state, including after End |
| One session's attendee profiles | The participants who gave any profile field or a photograph (UC-M-13) | `…/export?part=profiles` | Session page, Attendee profiles card (`#profiles-export`) |
| One session's feedback | Each participant's current rating and comments (UC-P-13) | `…/export?part=feedback` | Session page, Feedback card (`#feedback-export`) |
| One session's Q&A | The session's questions, including removed ones, with votes, status and response | `…/export?part=qna` | Session page, Questions card (`#qna-export`) |
| One session's quiz runs | The session's quiz runs, per-question results, and each participant's answers | `…/export?part=quiz_runs` | Included in the whole-session export; API only on its own |
| One quiz run | The run, its frozen quiz version, per-question answer counts, and each participant's answers | `GET /api/quiz_runs/{id}/export` | `/quizzes`, run report card (`#results-export`) |
| One quiz template | The quiz, its questions and answers with correctness, and its versions with their run counts | `GET /api/quizzes/{id}/export` | `/quizzes`, the quiz row's ⋯ menu (Export JSON, Export Excel) |

**Formats.** `format=json` (the default) or `format=xlsx`.

- **JSON** is one document. Its `export` object says what was exported:
  `scope`, `part` (session scopes), the identifiers, `exported_at`,
  `prashna_version`, and `contains_personal_data`. The data follows as
  `sessions` (a list), `session`, `quiz_run`, or `quiz` (one object), with
  child lists nested inside (`participants`, `questions`, `quiz_runs`,
  `feedback`; a run's `questions` and `responses`; a quiz's `questions`
  and `versions`). The same key means different things by parent: a
  session's `questions` (and `question_count`) are its Q&A entries, while
  a quiz's or a run's `questions` are quiz questions.
- **Excel** is one workbook with one sheet per table and one header row
  per sheet in plain words ("Asked at", "Votes", "Responded"). The first
  sheet, **About**, lists what was exported (scope and identifiers), when
  (UTC), the Prashna version, and, when the file holds participants'
  names or contact details, a note that it contains personal data.
  Sheets for one session: About, Session, Participants, Questions, Quiz
  runs, Quiz answers (one row per participant and question, with the
  chosen answers and whether they were correct), Feedback. All data
  uses the same tables with a Sessions sheet and a Session code column
  on each, then the quiz library: Quizzes, Quiz questions, and Answer
  options (each with a Quiz ID column). "Answer options" are a quiz's
  possible answers; "Quiz answers" are what participants chose. A part export has About, Session, and that part's sheets
  (Participants; Feedback; Questions; or Quiz runs and Quiz answers). A
  quiz run has About, Quiz run, Results, Quiz answers. A quiz template
  has About, Quiz, Questions, Answers, Versions.
- In both formats, timestamps are ISO 8601 in UTC with a `Z` suffix.
  Exports keep the **Anonymity** rule: the Participants table (profiles,
  present only in the all-data, one-session and profiles exports) has no
  ID that appears anywhere else; a question carries only the name its
  asker chose to show ("Asked by"); feedback carries no name; quiz
  answers identify a respondent only by a number local to that run
  ("Respondent", 1, 2, … in order of first answer), so one person's
  answers within a run group together but cannot be joined to a profile,
  another run or a question. A quiz-run export therefore holds no
  personal data, and its About sheet has no personal-data note. Uploaded
  images appear
  as their `/uploads/…` URL path. Excel cells hold text as text: a
  participant's entry that starts with `=` is never a formula.

**Access.** Only the signed-in admin who owns the data can export it.
Delegate moderators (mod_key) cannot, because exports include
participants' contact details. Session scopes follow the owner-only
convention (`401` without a cookie, `403 "Not your session"` for another
admin's session); quiz and quiz-run scopes return `404` for another
admin's data, as their other reads do.

**Never exported.** Participants' voter tokens, the admin's password
hash or any other secret, and moderator keys.

**Downloads.** Each response is an attachment named
`prashna-<scope>-<identifier>-<YYYYMMDD>.<ext>` (UTC date): for example
`prashna-all-data-20261011.json`,
`prashna-session-ABC123-20261011.xlsx`,
`prashna-profiles-ABC123-20261011.xlsx`,
`prashna-quiz-run-17-20261011.json`, `prashna-quiz-5-20261011.xlsx`
(scopes `session`, `profiles`, `feedback`, `qna`, `quiz-runs`,
`quiz-run`, `quiz`). Content types are `application/json` and
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`;
`Cache-Control` is `no-store`. An unknown `format` returns
`400 "format must be json or xlsx"`; an unknown `part` returns
`400 "part must be one of all, profiles, feedback, qna, quiz_runs"`.

**Tests (API)**
- `GET /api/sessions/{code}/export?format=json` → `200`, `Content-Type: application/json`, `Content-Disposition: attachment; filename="prashna-session-<code>-<YYYYMMDD>.json"`, `Cache-Control: no-store`; the body has `export` (`scope: "session"`, `part: "all"`, `session_code`, `exported_at`, `prashna_version`, `contains_personal_data: true`) and `session` with `participants`, `questions`, `quiz_runs` (each with `questions` and `responses`), and `feedback`. Auth: admin cookie.
- The same with `format=xlsx` → a workbook that openpyxl opens, with sheets About, Session, Participants, Questions, Quiz runs, Quiz answers, Feedback in that order, the documented header rows, and the session's data (a question's votes, a participant's chosen answer and correctness, a rating).
- `part=profiles`, `part=feedback`, `part=qna`, `part=quiz_runs` each return only that part (JSON keys and Excel sheets), named `prashna-<part>-<code>-<YYYYMMDD>.<ext>` (`quiz-runs` for `quiz_runs`); `part=profiles` lists only participants with profile data.
- `GET /api/export/all` in both formats covers every owned session and every owned quiz, not another admin's; each session table carries a Session code column, and the quiz library adds Quizzes, Quiz questions and Answer options sheets (each with a Quiz ID column); the JSON has `sessions` and `quizzes`; the file is `prashna-all-data-<YYYYMMDD>.<ext>`.
- `GET /api/quiz_runs/{id}/export` in both formats holds the frozen quiz title and version, per-answer counts with correctness, and each participant's chosen answers; another admin's run → `404`.
- `GET /api/quizzes/{id}/export` in both formats holds the questions, the answers with correctness, and the versions with run counts; another admin's quiz → `404`; the About sheet carries no personal-data note.
- No export, in either format, contains a participant's voter token, the admin's password hash, or the session's mod_key (searched in the JSON text and in every Excel cell).
- Anonymity: in a one-session export where a participant with the profile name "Alice" asked one question without a name and one as "Bob", answered a quiz and left feedback, "Alice" appears only in the Participants table; the questions read `author_name` `null` and "Bob"; no question, feedback item or quiz answer carries a participant id; quiz answers carry `respondent` 1; Participants rows carry no `id`; a quiz-run export has `contains_personal_data: false` and no personal-data note.
- A participant's question starting with `=` is a text cell in the workbook, not a formula.
- With only the mod_key header (no admin cookie) → `401`; with no auth → `401`; another admin's session → `403 "Not your session"`.
- `format=csv` → `400 "format must be json or xlsx"`; `part=everything` → `400 "part must be one of all, profiles, feedback, qna, quiz_runs"`.

**Tests (UI)**
- On `/` (authed), `#all-export` reads "Export all data ▾" and offers JSON and Excel; choosing Excel downloads `prashna-all-data-<YYYYMMDD>.xlsx`. The quiz library card's link reads "Open quiz library →".
- On `/m/<code>` as the owner, `#session-export` (Session lifecycle card, not Session settings, reading "Export session ▾"), `#qna-export` (Questions), `#profiles-export` (Attendee profiles) and `#feedback-export` (Feedback) are visible; choosing JSON downloads `prashna-session-<code>-…json`, `prashna-profiles-<code>-…json` and `prashna-feedback-<code>-…json`, and choosing Excel in `#qna-export` downloads `prashna-qna-<code>-…xlsx`.
- On `/m/<code>` for an ended session, `#session-export` is still visible in the Session lifecycle card, and choosing Excel downloads `prashna-session-<code>-…xlsx`.
- On `/m/<code>#k=<mod_key>` as a delegate, none of the export menus are shown.
- On `/quizzes`, a quiz row's ⋯ menu Export Excel downloads `prashna-quiz-<id>-<YYYYMMDD>.xlsx`, and the open run report's `#results-export` JSON downloads `prashna-quiz-run-<id>-<YYYYMMDD>.json`.

### UC-A-31: Adjust limits

The admin changes how much one person, or one network, may do before
Prashna slows them down (UC-X-08), for example when a large room shares
one Wi-Fi connection.

- **Given** the admin is signed in on `/`
- **Then** a **Limits** card (`#limits-card`) lists, for asking questions,
  voting on questions, answering quiz questions, rating the session and
  saving the attendee profile, how many times one person may do it at once and then per minute; and,
  for joining, how many people may share one network and how many more
  may join per minute. Each field shows its default as a tooltip.
- **When** the admin changes a value and leaves the field
- **Then** it is saved, a "Saved" toast appears, and the next request
  uses it, without a restart; the value survives a restart, because it is
  stored in the database
- **And** **Reset to defaults** restores every value
- **And** a value that is not a whole number from 1 to 100000 is refused
  with the server's message, and the field shows the saved value again

**Values** (the API names, defaults in brackets): `network_size` (300),
`join_per_minute` (120), `ask_burst` (6), `ask_per_minute` (6),
`vote_burst` (30), `vote_per_minute` (120), `submit_burst` (20),
`submit_per_minute` (30), `feedback_burst` (10), `feedback_per_minute`
(30), `profile_burst` (10), `profile_per_minute` (10). Login and the performance beacon are not adjustable.

**API.** `GET /api/admin/limits` returns `{"values": {...}, "defaults":
{...}}`. `PUT /api/admin/limits` takes any subset of the values, saves
them, applies them at once, and returns the same shape. Only the signed-in
admin may call either (`401` otherwise). A value outside 1–100000 or not
an integer returns `400 "<name> must be a whole number from 1 to
100000"`; an unknown name returns `400 "unknown limit: <name>"`.

**Tests (API)**
- `GET /api/admin/limits` → `200` with `values` equal to `defaults`, which match the list above; without the admin cookie → `401`.
- `PUT {"ask_burst": 3, "network_size": 50}` → `200` with those values and the others unchanged; a following `GET` returns them; after the server reloads its limits from the database (as at start), they are still in effect.
- `PUT {"ask_burst": 0}`, `{"ask_burst": 2.5}`, `{"ask_burst": "4"}`, `{"ask_burst": 100001}` → `400` with the message above; `PUT {"speed": 1}` → `400 "unknown limit: speed"`; nothing is saved by a refused request.
- `PUT` without the admin cookie → `401`.

**Tests (UI)**
- On `/` (authed), `#limits-card` shows the joining row's "at once" field as 300 and the profile row's fields (`#limit-profile_burst`, `#limit-profile_per_minute`) as 10; changing the asking "at once" field to 3 and leaving it shows a "Saved" toast, and after a reload the field reads 3; **Reset to defaults** sets it back to 6.

---

## Moderator

### UC-M-01: Open the moderator view

- **Given** the visitor is the admin owner of the session
- **When** they open `/m/<code>` (no fragment needed)
- **Then** the page loads the full moderator surface, authenticating
  every mod call via the admin cookie. No key gate appears.
- **Given** the visitor is a delegate with a moderator URL
- **When** they open `/m/<code>#k=<mod_key>`
- **Then** the page extracts the key from the URL fragment, persists
  it to `localStorage`, and strips the fragment from the address bar
- **And** if neither admin cookie nor stored key is present, the page
  attempts the boot, observes `403`, and shows the inline key-gate
  card for the delegate to paste their key
- **And** if a wrong key is stored, the boot 403s and the gate
  re-prompts with a "Couldn't load session — re-enter the moderator
  key." toast
- **And** the key gate shows only what a visitor without access can
  use: the header reads "Session <code>" without the status, online
  count, and view links; the Sessions breadcrumb is hidden; and the help
  text asks for the moderator link in plain words, without naming the
  URL fragment
- **And** pasting a moderator link (`/m/<code>#k=<mod_key>`) into a tab
  that already shows `/m/<code>` loads it: the page reloads when the
  part after `#` gains a `k=` key. Its section links (`#quizzes-card`
  and the others) stay ordinary jumps

**Tests (API)**
- Any `mod-or-owner` route (e.g., `POST /api/sessions/{code}/start`) with valid `X-Mod-Key` header → `200`. Auth: mod-key.
- Same with admin owner cookie and no mod_key → `200`.
- With no auth and no mod_key → `403 "Not authorized — moderator key or admin login required"`.
- With wrong mod_key and no admin cookie → `403`.
- `GET /api/sessions/{code}/moderator-bootstrap` with mod-key or owner
  auth returns the session, the quiz summaries the caller may add
  (UC-M-03), and `is_owner` in one response; unauthenticated and
  wrong-key calls return `403`.
- `GET /m/<code>` for an unknown code → `303` redirect to `/?bad_code=<code>`.

**Tests (UI)**
- Opening `/m/<code>` as the admin owner (cookie present) does NOT render `#modkey-card`; the moderator surface loads.
- Opening `/m/<code>#k=<mod_key>` as a delegate stores the key in `localStorage` under the session code and strips `#k=` from the address bar.
- Opening `/m/<code>` with neither cookie nor stored key renders `#modkey-card`; submitting `#modkey-input` via `#modkey-submit` boots the surface.
- Opening `/m/<code>` with a wrong stored key renders `#modkey-card` with toast "Couldn't load session — re-enter the moderator key."
- With `#modkey-card` showing, `#title` reads "Session <code>", `header.top .meta` and the Sessions breadcrumb are hidden, and the card's text does not mention `#k=` (`test_uc_m_01_key_gate_shows_no_session_chrome`).
- With `#modkey-card` showing, going to `/m/<code>#k=<mod_key>` in the same tab boots the moderator surface (`test_uc_m_01_moderator_link_pasted_into_an_open_tab`).
- `#moderator-breadcrumbs` shows Sessions → session title. The Sessions link targets `/`; the session title is the current page. The adjacent section links jump to Lifecycle, Set up, Quiz, Questions, Profiles, and Feedback; jumping to Set up opens the disclosure.
- The header links to the session's other views: `#participant-link` (`/s/<code>`, same tab) and `#projector-link` (`/p/<code>`, a new tab, so the session page stays open while the projector goes on the room screen; the session list's Projector link does the same). A delegate moderator does not see the Sessions breadcrumb, which only an admin can use (`test_uc_m_views_links_for_a_delegate`).

### UC-M-02: Session lifecycle: Start → End

- **Given** the moderator is on `/m/<code>` and the session is
  `planning`
- **When** they click **Start session**
- **Then** `POST /api/sessions/{code}/start` sets status to `live` and
  records `started_at`
- **When** they click **End session** (the UI shows a native
  `confirm()` first — the backend has no confirmation gate; the
  request is fired straight if the moderator clicks OK)
- **Then** `POST /api/sessions/{code}/end` sets status to `ended` and
  records `ended_at`
- **And** starting a quiz run on a `planning` session auto-advances
  it to `live` as a side effect
- **And** the `/end` route accepts a request on any non-ended status
  — there's no requirement to have first transitioned to `live`

**Tests (API)**
- `POST /api/sessions/{code}/start` on a `planning` session → `200 {status: "live"}` and sets `started_at`. Auth: mod-key OR admin cookie.
- `POST /api/sessions/{code}/start` on a `live` session → `200 {status: "live"}` (idempotent, no changes).
- `POST /api/sessions/{code}/start` on an `ended` session → `400 "Session has ended"`.
- `POST /api/sessions/{code}/end` on a `live` session → `200 {status: "ended"}` and sets `ended_at`.
- `POST /api/sessions/{code}/end` on a `planning` session → `200 {status: "ended"}` (allowed without first going live).
- `POST /api/sessions/{code}/end` on an `ended` session → `200` (no-op).
- `POST /api/sessions/{code}/end` while any QuizRun in this Session is still `live` → `400 "A quiz run is currently live — close it before ending the session"`; the session stays `live` with no `ended_at` (`test_uc_m_02_end_with_live_run_400`). The moderator must explicitly close the run first.
- `POST /api/sessions/{code}/end` while any QuizRun is still `queued` → `400 "Remove queued quizzes before ending the session"`. This prevents an ended Session from retaining an unstartable staged run.
- Each successful state change broadcasts `{type: "session_state"}`.
- With no auth → `403`.

**Tests (UI)**
- On `/m/<code>`, when status is `planning`, `#lifecycle-actions` contains Start session; clicking it flips `#session-status` to `.badge-live`.
- `#lifecycle-hint` uses the same words as the status badge: "Not started yet. Start it when the audience is ready." while `planning` (`test_uc_m_02_hint_matches_the_badge`).
- When status is `live`, `#lifecycle-actions` contains End session; clicking triggers native `confirm()`, then on OK flips `#session-status` to `.badge-ended`.

### UC-M-03: Queue a quiz onto the session

- **Given** the moderator picks a quiz in the **+ Add quiz** composer
  (`#quiz-select` + `#add-quiz-btn`) in the Quiz card header and clicks
  Add
- **When** the Quiz has unsaved edits since the latest version
- **Then** `_ensure_current_version` deep-copies the quiz tree into a
  new immutable `QuizVersion(version_no = latest+1)`; the new QuizRun
  points to it
- **And** when the Quiz has not changed since the latest version, the
  new QuizRun reuses that version
- **And** the picker lists Ready quizzes to everyone; the admin owner
  also sees Draft quizzes, labelled as drafts. A Ready quiz with a
  `problem` (UC-A-10) is listed but disabled and labelled "needs fixing
  in the quiz library", so a delegate sees why it can't be added instead
  of getting an error they can't fix. Adding a draft sends
  `publish: true`: the server runs the publish validation (UC-A-21),
  marks the quiz `ready`, and queues it in one step. If validation
  fails, nothing is published or queued
- **And** queueing a Draft quiz without `publish: true` returns `400`
- **And** `publish: true` from a delegate (mod_key, no admin cookie) on
  a draft returns `403`; on a Ready quiz the flag is ignored
- **And** queueing on an ended session returns `400`

**Tests (API)**
- `POST /api/sessions/{code}/quiz_runs` with `{"quiz_id": <ready_id>}` → `200 {id, version_no, status: "queued"}`. Auth: mod-key OR admin cookie.
- Two consecutive queues on an unedited quiz → both runs point to the same `version_no`.
- After PATCHing the quiz (edit between queues), next queue creates a new `version_no = prev+1` and the new run points to it.
- `POST /api/sessions/{code}/quiz_runs` with a `draft` quiz_id → `400 "Quiz is still a draft — publish it first"`.
- With `{"quiz_id": <valid draft>, "publish": true}` and the admin owner cookie → `200`; the quiz is now `ready` and the run is queued.
- With `{"quiz_id": <invalid draft>, "publish": true}` → `400` with the publish validation message (e.g. `"Quiz needs at least one question"`); the quiz stays `draft` and no run exists.
- With `{"quiz_id": <draft>, "publish": true}` and only a valid `X-Mod-Key` → `403 "Only the admin can publish a draft quiz"`; the quiz stays `draft`.
- With `{"quiz_id": <ready_id>, "publish": true}` and only a valid `X-Mod-Key` → `200` (nothing to publish).
- `POST /api/sessions/{code}/quiz_runs` with an unknown quiz_id → `404 "Quiz not found"`.
- Quiz owned by another admin → `404 "Quiz not found"`.
- `POST /api/sessions/{code}/quiz_runs` on an `ended` session → `400 "Session has ended"`.
- With no auth → `403`.
- Success broadcasts `{type: "quiz_run_new"}`.
- `GET /api/sessions/{code}/available_quizzes` (and the bootstrap's `available_quizzes`) returns Ready quizzes for a delegate, and Ready plus Draft quizzes (with `status`) for the admin owner.
- Each entry also has `problem`, as in UC-A-10 (`null` unless a Ready quiz was edited into an invalid state) (`test_uc_m_03_available_quizzes_report_problem`).
- Each entry has `in_session`: `null` when the quiz has no run in this session, otherwise `{run_status, run_count}` (same rules as UC-A-10's `sessions`). After queueing, it reports `{run_status: "queued", run_count: 1}`; after Start, `run_status: "live"`.

The **+ Add quiz** composer is an operational control during a session,
so it lives in the Quiz card header (`#quizzes-card` card-tools) and
stays visible whether the session is `planning` or `live`. On an `ended`
session nothing can be queued, so the composer is hidden (UX.md §16).
The picker starts on a "Choose a quiz…" placeholder, so a stray tap on
**+ Add quiz** can't queue the wrong quiz. The staged runs render below
it in `#quiz-runs`.

**Tests (UI)**
- On `/m/<code>` as a delegate (mod_key only), `#quiz-select` lists only ready quizzes (drafts filtered).
- On `/m/<code>` as the admin owner, `#quiz-select` lists ready quizzes and draft quizzes, with drafts labelled "draft".
- Each option counts questions in correct English: "(1 question)", "(2 questions)" (`test_uc_m_03_picker_counts_questions_in_words`).
- On `/m/<code>` as a delegate, a Ready quiz whose only question was deleted is a disabled option labelled "needs fixing in the quiz library" (`test_uc_m_03_needs_fixing_quiz_is_disabled_in_picker`).
- Selecting a quiz and clicking `#add-quiz-btn` appends a queued row to `#quiz-runs` with `.badge-queued`.
- On a `live` session, `#add-quiz-btn` is visible without opening Set up.
- Selecting a valid draft and clicking `#add-quiz-btn` queues it and toasts that it was published.
- `#quiz-select` starts on the placeholder (value `""`); clicking `#add-quiz-btn` without choosing toasts "Pick a quiz first." and queues nothing.
- On an `ended` session, `#quiz-composer` is hidden.
- A quiz already in this session is labelled in `#quiz-select` ("already added · Queued"); adding it asks for confirmation, and dismissing queues nothing. The picker refreshes when runs are added or removed.

### UC-M-04: Start a queued quiz run

- **Given** a QuizRun is `queued`
- **When** the moderator clicks Start
- **Then** `POST /api/sessions/{code}/quiz_runs/{id}/start` flips its
  status to `live`, resets `current_question_idx = 0`, `reveal_current =
  False`
- **And** if another QuizRun is already `live` in the same Session,
  the start returns `409 Another quiz is already live — close it
  first` (enforced by the `uq_session_live_run` partial unique index)
- **And** a `planning` session becomes `live` (with `started_at` set)
  when one of its runs starts; that start also broadcasts `session_state`
  and logs the session start, so every open page shows the session Live

**Tests (API)**
- `POST /api/sessions/{code}/quiz_runs/{id}/start` on a `queued` run → `200 {ok: true}`; sets `status: "live"`, `current_question_idx: 0`, `reveal_current: false`, `started_at`. Auth: mod-key OR admin cookie.
- Starting on a `planning` Session auto-advances it to `live` and sets `started_at`.
- Starting a run while another run on the same Session is already `live` → `409 "Another quiz is already live — close it first."`.
- Starting a run that's not `queued` (e.g., `live`, `closed`) → `400 "Cannot start from status: <status>"`.
- Starting a queued run in an `ended` Session → `400 "Session has ended"`, including legacy queued rows created before this invariant was enforced.
- For a non-existent run id (or wrong session) → `404`.
- With no auth → `403`.
- Success broadcasts `{type: "quiz_run_update"}`.
- Starting a run in a `planning` session also broadcasts `{type: "session_state"}` and logs `session.lifecycle` with `action=start`; starting one in a `live` session broadcasts only `quiz_run_update` (`test_uc_m_04_start_in_planning_broadcasts_session_state`).

**Tests (UI)**
- With `/m/<code>` open on a `planning` session, starting a queued run from another tab flips `#session-status` to Live (`test_uc_m_04_run_start_shows_session_live_in_other_tabs`).
- In `#quiz-runs` on `/m/<code>`, clicking Start on a `.badge-queued` row flips the row to `.badge-live` and reveals the Next/Reveal control.
- With one run already live, clicking Start on a second queued row toasts the 409 error.
- `#quiz-runs` lists the live run first, then queued runs in play order (oldest first), then closed runs (newest first).
- A queued row shows the quiz title, version, and question count with its controls, but no answer options (`.option`), so the correct answer stays hidden until the run starts.

### UC-M-05: Walk through questions

The primary affordance for advancing is a **single Next button** that
recognizes which phase the current question is in.

- **Given** a live QuizRun in **answering** phase (`reveal_current=false`)
- **When** the moderator clicks **Reveal results →**
- **Then** `reveal_current` flips to true → the current question
  enters **results** phase (bars + correctness shown on projector /
  participant pages); voting is locked.
- **Given** the QuizRun is in results phase and the current question
  is not the last
- **When** the moderator clicks **Next question →**
- **Then** `current_question_idx` advances → the next question's
  answering phase begins (or its results phase, if it was revealed
  earlier in this run).
- **Given** the QuizRun is in results phase and the current question
  **is** the last
- **When** the moderator clicks **Finish quiz →**
- **Then** the run closes (see UC-M-06).
- **Prev** moves `current_question_idx` backwards (mod can revisit a
  question). **A revealed question stays revealed** for the rest of the
  run: returning to it by Prev, Next or a jump shows its results and
  correct answer, and voting on it stays closed, so nobody can change an
  answer after seeing the right one. Only ⋯ → **Reopen voting**
  (`reveal:false`) opens it again, until it is revealed again. The run
  stores which questions are revealed (`quiz_runs.revealed_idxs`, added by
  the migration bridge, UC-X-05); Start clears it.
- **Reveal closes voting.** Clicking **Reveal results →** sets
  `reveal_current=true`, which **locks participant submissions** (their
  Submit is replaced by "Voting closed — the answer has been revealed").
  The moderator row shows a **"voting closed"** marker, and the ⋯ menu
  offers **Reopen voting** (`reveal:false`) to reopen the current question.
- **Row controls.** Only the primary drive controls stay on the row: the
  morphing primary (Reveal results → / Next question → / Finish quiz →)
  and **← Prev**. The rare run-management actions live in a **⋯ overflow
  menu** (`details.menu`, see UX.md §4): **Finish quiz** (close while
  keeping results — shown only when the primary isn't already the finish
  step, so it never appears twice), a **Show / Hide vote counts** audience
  toggle, **Remove from session** for queued runs, and **Delete run
  (discard results)** for live runs. "Finish" and "Delete" are the two
  distinct outcomes for a live run — finishing keeps results; deleting
  discards them.
- **In-flight guard.** Every run-control button ignores repeat clicks while
  an action is pending and disables itself for the duration. This prevents
  a slow request (server briefly busy) from being clicked several times and
  then advancing through multiple questions at once.
- **Live counts** are toggled independently per QuizRun via
  `POST /api/sessions/{code}/quiz_runs/{id}/live_counts` with body
  `{show: bool}` (mod-or-owner auth). Default off. The moderator UI
  surfaces this as a **Show vote counts to audience** / **Hide vote counts
  from audience** verb button inside the run's ⋯ overflow menu. See
  UC-D-08 / UC-P-12 for the rendered behavior.
- **Backend routes called by this UC**: `/start` (queued → live),
  `/advance` (`{direction: "next" | "prev" | "to", index?: int}`),
  `/reveal` (`{reveal: bool}`), `/close`, `/live_counts`. All POST,
  all mod-or-owner auth.

**Tests (API)**
- `POST /api/sessions/{code}/quiz_runs/{id}/reveal` with `{"reveal": true}` → `200 {ok: true}`; `reveal_current` is true. Auth: mod-key OR admin cookie.
- `POST /api/sessions/{code}/quiz_runs/{id}/advance` with `{"direction": "next"}` → `200 {ok: true}`; `current_question_idx` increments by 1 (capped at `len-1`); `reveal_current` is false on a question not yet revealed.
- `{"direction": "prev"}` → decrements idx (floored at 0).
- `{"direction": "to", "index": 2}` → sets idx to 2 (clamped to `[0, len-1]`).
- Reveal question 1, Next, then Prev → `reveal_current` is true and a participant's submit for question 1 → `400 "Voting closed — results have been revealed"`; jumping back with `to` behaves the same.
- Reveal question 1, Reopen voting (`reveal:false`), Next, Prev → `reveal_current` is false and a submit for question 1 succeeds.
- `{"direction": "to", "index": "x"}` → `400 "index must be an integer"`; `{"direction": "to"}` → `400 "index is required"`; `{"direction": "sideways"}` → `400 "direction must be next, prev or to"`; none of these changes the run.
- **Source-state guards**: `/advance`, `/reveal` and `/close` require `run.status == "live"`; calling one on a `queued` or `closed` run → `400 "Cannot <advance|reveal|close> from status: <queued|closed>"` and the run is unchanged (`test_uc_m_05_run_controls_require_live`).
- `POST /api/sessions/{code}/quiz_runs/{id}/live_counts` with `{"show": true}` → `200 {show_live_counts: true}`; with `{"show": false}` → `{show_live_counts: false}`. **Allowed on `queued` and `live`** (so a mod can pre-configure before Start). On a `closed` run → `400 "Cannot toggle live counts on a closed run"`.
- Each route broadcasts `{type: "quiz_run_update"}`.
- With no auth → `403`.

**Tests (UI)**
- On `/m/<code>` with a live run in answering phase (`reveal_current=false`), the primary control reads "Reveal results →"; clicking it flips the row to results phase.
- In results phase on a non-last question, the control reads "Next question →"; clicking advances `current_question_idx` and resets to answering phase for the next question.
- In results phase on the last question, the control reads "Finish quiz →"; clicking closes the run keeping results (see UC-M-06).
- A Prev control moves backwards through questions.
- A "Show vote counts to audience" / "Hide vote counts from audience" verb button inside the run's ⋯ overflow menu (`details.menu`) toggles `show_live_counts`; default is off. Opening the menu (`details.menu > summary`) reveals it. The ⋯ menu is **not rendered for closed runs** (the backend would 400 anyway since closed runs are historical).

### UC-M-06: Close a quiz run

- **Given** a live QuizRun
- **When** the moderator clicks **Finish quiz →** (the primary, on the
  last question) or **Finish quiz** (in the ⋯ overflow menu, to end
  early) — both keep results
- **Then** status → `closed`, `reveal_current → True`, `closed_at` is
  set
- **And** the run's ⋯ overflow menu disappears — closed runs are
  historical and have no remaining actions
- **And** the moderator's quiz-runs list refreshes via WebSocket
- **And** participants who already submitted keep their selections;
  no new responses are accepted

**Tests (API)**
- `POST /api/sessions/{code}/quiz_runs/{id}/close` on a live run → `200 {ok: true}`; sets `status: "closed"`, `reveal_current: true`, `closed_at`. Auth: mod-key OR admin cookie.
- After close, `POST .../submit` for this run → `404 "Quiz not live"`.
- Broadcasts `{type: "quiz_run_update"}`.
- With no auth → `403`.

**Tests (UI)**
- In `#quiz-runs`, after closing (via the ⋯ menu's "Finish quiz", or the primary "Finish quiz →" on the last question) the row's badge flips to `.badge-closed` and the run's ⋯ menu (`details.menu`) disappears.
- The participant page (in another tab) refreshes via WS and hides `#quiz-card`, because participants see only a live run (UC-P-07).
- For the admin owner, a closed row shows a "View results →" link to `/quizzes?run=<run_id>`, which opens that run's `#results-card` (UC-A-24) with every question's tallies. A delegate (mod_key only) doesn't see the link, because the quiz library is admin-only.

### UC-M-07: Remove a quiz run (only when queued / live)

- **Given** a queued or live QuizRun
- **When** the moderator opens the run's ⋯ overflow menu, clicks
  **Remove from session** for a queued run or **Delete run (discard
  results)** for a live run, and confirms
- **Then** `DELETE /api/sessions/{code}/quiz_runs/{id}` deletes the
  run and its responses
- **And** a closed run returns `400 Closed quiz runs are historical
  and cannot be deleted`

**Tests (API)**
- `DELETE /api/sessions/{code}/quiz_runs/{id}` on a `queued` run → `200 {ok: true}`; cascade removes QuizSubmissions. Auth: mod-key OR admin cookie.
- The same delete remains available for a legacy queued run whose Session is already `ended`, so orphaned staging state can be repaired without starting it.
- On a `live` run → `200 {ok: true}` and similar cleanup.
- On a `closed` run → `400 "Closed quiz runs are historical and cannot be deleted"`.
- Broadcasts `{type: "quiz_run_deleted"}`.
- With no auth → `403`.

**Tests (UI)**
- In `#quiz-runs`, opening the ⋯ menu on a queued row and clicking "Remove from session" (after native confirm) removes the row. Its control has `aria-label="Remove this queued quiz from the session"`; live rows retain "Delete run (discard results)" with `aria-label="Delete this quiz run"`.
- On an ended Session, a legacy queued row does not offer Start or vote-count controls; it offers only **Remove from session**. The backend also rejects a direct Start request.
- No ⋯ menu (and thus no Delete control) is rendered on `.badge-closed` rows.

### UC-M-08: Respond to a query

- **Given** a question in the moderator's questions list
- **When** they type an answer (optional) and click Mark responded
- **Then** `POST .../queries/{qid}/respond` sets `responded_at` and
  `response_text` (which may be null for verbal-only answers)
- **And** the participant view moves the question to the answered
  section
- **And** the moderator can Reopen an answered question, clearing
  `responded_at`
- **And** while the moderator types in a response box, live updates that
  redraw the questions list keep that box focused with the caret where it
  was, so no keystroke is lost

**Tests (API)**
- `POST /api/sessions/{code}/queries/{qid}/respond` with `{"response_text": "see docs"}` → `200 {ok: true}`; sets `responded_at` and `response_text = "see docs"`. Auth: mod-key OR admin cookie.
- `POST .../respond` with `{}` → marks responded with `response_text: null` (verbal-only).
- `POST .../respond` with `{"responded": false}` → clears `responded_at` (Reopen). Note: the handler always writes `response_text` from the payload — so omitting `response_text` on Reopen also **wipes** any prior text (handler does `q.response_text = (payload.get("response_text") or "").strip() or None`). Tests should assert this side effect.
- `POST .../respond` for a non-existent or cross-session qid → `404`. A real query id used under another session's code is refused by `/respond`, `/remove`, `DELETE` and `/vote` alike, and the query is unchanged (`test_uc_m_08_query_from_other_session_404`).
- Broadcasts `{type: "query_responded"}`.
- With no auth → `403` (see Conventions).

**Tests (UI)**
- In moderator `#queries`, clicking Mark responded on a query moves it into the answered section.
- Mark responded is a secondary button, not `.primary`: with one per row, a primary on each would break UX.md §10's one primary per card (`test_uc_m_09_removed_question_offers_only_restore`).
- Reopen on an answered query moves it back to the unanswered section.
- With the caret in a query's response box, a vote from another participant redraws the list; the box keeps focus and the keystrokes typed before and after the vote all land in it (`test_uc_m_08_typing_survives_live_refresh`).

### UC-M-09: Remove / Restore a query

- **Given** any question (e.g., spam / off-topic / duplicate)
- **When** the moderator clicks Remove
- **Then** `POST .../questions/{qid}/remove` sets `removed_at`; the
  question becomes invisible to participants but stays visible to the
  moderator with a Restore action
- **And** votes on a removed question return `404`

**Tests (API)**
- `POST /api/sessions/{code}/queries/{qid}/remove` with `{}` → `200 {ok: true}` and sets `removed_at`. Auth: mod-key OR admin cookie.
- `POST .../remove` with `{"removed": false}` → clears `removed_at` (Restore).
- After removal, `GET /api/sessions/{code}/queries` as a participant excludes the removed query; as moderator, includes it with `removed: true`.
- `POST .../vote` on a removed query (as participant) → `404 "Question not found"`, which the participant page shows as received (`test_uc_m_09_vote_on_removed_question_names_it`).
- Broadcasts `{type: "query_removed"}`.
- With no auth → `403`.
- **Hard delete is owner-only**: `DELETE /api/sessions/{code}/queries/{qid}` requires admin cookie. A delegated `mod_key` → `401`. (Soft-remove above remains mod-or-owner.)

**Tests (UI)**
- In moderator `#queries`, clicking Remove on a query marks it visually removed (still visible to moderator) with a Restore action. A removed question offers only Restore: no Mark responded, Update response, or Reopen, which the hidden state makes useless (UX.md §16) (`test_uc_m_09_removed_question_offers_only_restore`).
- Participant tab refreshes via WS and the query disappears from their list.

### UC-M-10: Live participant count

- **Given** participants are interacting with the session
- **When** the moderator views their header bar (and on each
  WebSocket-driven refresh)
- **Then** the count of participants whose `last_seen_at` falls within
  the last 30 seconds is shown
- **And** a moderator tab is never a participant: reading the count
  creates no Participant, and the moderator page reads the questions and
  quiz runs as a display (`?display=true`), so moderators are not counted
  online or in exports

**Tests (API)**
- `GET /api/sessions/{code}/presence` → `200 {online: <int>}` counting Participants with `last_seen_at >= now-30s`. Auth: none. The call issues no cookie and creates no Participant: on a new session it returns `online: 0` (`test_uc_m_10_presence_creates_no_participant`).
- After one participant calls a participant route, `online` returns 1; the presence call itself adds nobody.
- After waiting > 30s without further requests, `online` decrements back to 0.

**Tests (UI)**
- On `/m/<code>`, `#live-count` shows "N online" and updates after WS-driven refreshes.
- Opening `/m/<code>` as the owner on a new session shows "0 online", and the session export's `participant_count` stays 0 (`test_uc_m_10_moderator_tab_is_not_a_participant`).

### UC-M-11: Invite participants

- **Given** any moderator (delegate or admin owner) is on the
  moderator page
- **Then** the invite card shows the QR and the participant URL,
  and the Copy URL button works
- **Given** the visitor is the admin owner (cookie present)
- **When** they paste a Base URL and blur the input
- **Then** the page rebuilds the participant URL as
  `<base>/s/<code>`, renders a QR, and updates the copy-URL text
- **And** clicking Use default clears the override and the page falls
  back to `location.origin`
- **Given** the visitor is a delegated moderator (mod_key only, no
  admin cookie)
- **Then** the Base URL editor is **not rendered** — only the read-only
  QR/URL/Copy controls. The underlying
  `POST /api/sessions/{code}/participant_base_url` is owner-only
  (see UC-A-06).

**Tests (API)**
- Editing surface is owner-only — see UC-A-06 for the auth tests.

The invite card (`#invite-card`) is a **creational** control and lives in
the collapsible **Set up** section (`#setup-section`, see UX.md §4), open
by default while the session is `planning`.

**Tests (UI)**
- On `/m/<code>` opened with the admin cookie (session `planning`, so Set up is open), `#base-url` (inside its `.field` container) is visible; typing and blurring updates `#invite-url` and re-renders `#invite-qr` encoding `<base>/s/<code>`.
- On `/m/<code>` opened with only a `mod_key` (no admin cookie), the `.field` wrapping `#base-url` is hidden; QR, `#invite-url`, and `#invite-copy` remain visible.
- Clicking `#base-url-clear` (owner view) clears the override; the QR/URL fall back to `location.origin`.
- Clicking `#invite-copy` copies `#invite-url` text to clipboard.

### UC-M-12: Open rating and view session feedback

- **Given** a moderator (delegate or admin owner) is on the moderator page
- **Then** the Lifecycle card (`#lifecycle-actions`) shows **Open rating**
  while rating is closed and **Close rating** while it is open, in every
  session status
- **When** they click it → `POST /api/sessions/{code}/feedback_enabled`
  with `{"enabled": true|false}` (mod-or-owner auth) sets the session's
  `feedback_enabled` flag, returns `{feedback_enabled}`, and broadcasts
  `{type: "feedback_state"}`, so participant pages show or hide the
  rating card (UC-P-13)
- **And** rating starts closed on a new session (`feedback_enabled:
  false`)

- **Given** a moderator (delegate or admin owner) is on the moderator page
- **Then** a **Feedback** panel (`#feedback-card`) shows the aggregate of
  participant feedback (see UC-P-13): the average rating and response
  count (`#feedback-summary`) plus each response — its stars and the
  "went well" / "could be better" comments (`#feedback-list`), with no
  name (see **Anonymity**)
- **And** the panel refreshes live via the `feedback` WS broadcast
- **Backend route**: `GET /api/sessions/{code}/feedback/summary`
  (mod-or-owner auth) → `{count, average, distribution: {1..5}, items:
  [{rating, went_well, to_improve, updated_at}, ...]}`.

**Tests (API)**
- A new session reports `feedback_enabled: false`.
- `POST /api/sessions/{code}/feedback_enabled` with `{"enabled": true}` and the mod-key → `200 {feedback_enabled: true}`; a participant `POST .../feedback` then succeeds; with `{"enabled": false}` → `200 {feedback_enabled: false}` and the next participant `POST .../feedback` → `403` (`test_uc_m_12_feedback_toggle_by_moderator`).
- The toggle broadcasts `{"type": "feedback_state"}` (`test_uc_m_12_feedback_toggle_broadcasts_feedback_state`).
- `GET /api/sessions/{code}/feedback/summary` with two participants'
  ratings (5 and 3) → `200 {count: 2, average: 4.0, distribution: {"5":1,
  "3":1, ...}, items: [...]}`. Auth: mod-key OR admin cookie.
- No item carries a name or participant id, even when the participant has a profile name.
- With no auth (no admin cookie, no mod-key) → `403`.
- Owner reaches it via cookie with no mod-key; empty session → `count: 0`,
  `average: null`.

**Tests (UI)**
- A participant page hides `#feedback-card` while rating is closed; after the moderator clicks **Open rating** in `#lifecycle-actions`, the button reads **Close rating** and the participant page shows `#feedback-card` (`test_uc_m_12_moderator_controls_rating_widget`).
- After a participant submits feedback, on `/m/<code>` the `#feedback-card`
  is visible, `#feedback-summary` shows the average, and `#feedback-list`
  contains the comment text.

### UC-M-13: View attendee profiles

- **Given** a moderator (delegate or admin owner) is on the moderator page
- **Then** an **Attendee profiles** card (`#profiles-card`) lists every
  participant who has submitted any profile field or a photograph
  (UC-P-03), most recently seen first; `#profiles-summary` shows the count
  ("1 profile", "N profiles") and `#profiles-list` shows each profile's
  photograph, name ("Anonymous attendee" when blank), email, contact
  number, organization, role, LinkedIn link, current work, and learning
  goal; participants with no profile data are left out
- **And** the LinkedIn value is a link only when it starts with `http://`
  or `https://`; any other stored value is shown as plain text
- **And** with no profiles the card reads "No attendee profiles yet."
- **And** the card refreshes on the `participant` WebSocket broadcast
- **Backend route**: `GET /api/sessions/{code}/participants`
  (mod-or-owner auth) → `{count, items: [{id, name, email,
  contact_number, organization, role, linkedin_url, photo_url,
  current_work, learning_goal}, ...]}`

**Tests (API)**
- With one participant who submitted every field and a photograph, and a second participant with no profile data, `GET /api/sessions/{code}/participants` with the mod-key → `200 {count: 1, items: [...]}` carrying every field and the photograph URL (`test_uc_m_13_participant_profiles_summary`).
- With no auth → `403` (`test_uc_m_13_participant_profiles_requires_moderator`).

**Tests (UI)**
- After a participant submits a full profile with a photograph, `/m/<code>` as the admin owner shows `#profiles-card`; `#profiles-summary` contains "1 profile" and `#profiles-list` contains each field and an `img.profile-photo-preview` with the photograph URL (`test_uc_m_13_profiles_panel_shows_attendee_details`).
- When the profiles response carries a LinkedIn value of `javascript:alert(1)` (an older row), `#profiles-list` shows it as text and contains no link with that `href` (`test_uc_m_13_non_web_linkedin_is_plain_text`).

---

## Participant

### UC-P-01: Join a session by code

- **Given** the participant types a code on `/` and presses Enter (or
  clicks Join)
- **When** the code exists
- **Then** they navigate to `/s/<CODE>` and see the session title,
  code, name input, ask-question card, questions list, and invite QR
- **And** an unknown code redirects to `/?bad_code=XXX` showing a red
  banner "Session 'XXX' does not exist."

**Tests (API)**
- `GET /api/sessions/{code}` for an existing code → `200 {code, title, status, created_at, participant_base_url}`. Auth: none (public read).
- `GET /api/sessions/{code}` for an unknown code → `404 "Session not found"`.
- `GET /api/sessions/{code}/participant-bootstrap` returns the session,
  participant profile, visible questions, quiz runs, and current feedback in
  one response. A fresh caller receives one `voter_token` cookie and creates
  only one Participant row.
- `GET /s/{code}` for a valid code → serves `participant.html`.
- `GET /s/{code}` for an unknown code → `303` redirect to `/?bad_code=<code>`.

**Tests (UI)**
- On `/`, typing a valid code into `#join-code` and clicking `#join-btn` (or pressing Enter) navigates to `/s/<CODE>`.
- `/s/<CODE>` shows `#title`, `#code`, `#my-name`, `#ask-card`, `#questions-card`, `#invite-card`.
- `#participant-breadcrumbs` shows Prashna → session title → Participant, with section links for the long participant page.
- `#view-links` links the session's other views for those who may open them, and is hidden for everyone else: the admin who owns the session (`viewer_is_owner: true` in `GET /api/sessions/{code}/participant-bootstrap`) sees Sessions (`/`), Moderate (`/m/<code>`) and Projector (`/p/<code>`); a delegate moderator (this browser holds the session's moderator key) sees Moderate and Projector; a participant sees none (`test_uc_p_view_links_follow_the_viewer`).
- Typing an unknown code redirects to `/?bad_code=XXX`; `#bad-code-msg` shows "Session 'XXX' does not exist." in red.

### UC-P-02: Anonymous identity per session

- **Given** the participant has never visited this session
- **When** any participant-facing route runs
- **Then** the server resolves their `voter_token` cookie (issued on
  first interaction if missing) to a `Participant` row, scoped to
  this session
- **And** `last_seen_at` is updated at most once per 5 seconds per
  request
- **And** concurrent first-touch requests sharing one fresh
  `voter_token` (e.g. the projector firing `/queries` and
  `/quiz_runs` in parallel) resolve to a **single** Participant row:
  the loser of the insert race catches `IntegrityError`, re-reads the
  winner's row, and never surfaces a `500`

**Tests (API)**
- `GET /api/sessions/{code}/me` with no cookie → `200 {id, name: null}` and `Set-Cookie: voter_token=<token>` (non-HttpOnly, SameSite=Lax). Auth: none (cookie issued on first call).
- A second call with the cookie reuses the same Participant row (same `id`).
- Two distinct cookies for the same session create two distinct Participants (unique on `(session_id, voter_token)`).
- Two consecutive participant calls within 5s update `last_seen_at` only once (throttled).
- A call > 5s later updates `last_seen_at` again.
- Two concurrent participant-resolving GETs sharing one fresh `voter_token` on a not-yet-joined session → both return `200` and exactly one Participant row exists for `(session, voter_token)` (insert race handled, no `500`).

**Tests (UI)**
- Loading `/s/<CODE>` in a fresh browser context sets a `voter_token` cookie (readable in JS — non-HttpOnly).
- Reloading the page keeps the same `voter_token`; subsequent calls flag the participant's own questions with `mine: true`.

### UC-P-03: Set display name and attendee profile

The participant page starts with a **Profile** card (`#profile-card`, a
`<details>`), collapsed by default. Its header reads "Add your profile" with
an **Add details** call to action, or "Your profile" with **Edit details**
once something is saved. Every field is optional:

| Field | API key | Max length |
| --- | --- | --- |
| Display name | `name` | 80 |
| Email | `email` | 254 |
| Contact number | `contact_number` | 40 |
| Organization | `organization` | 120 |
| Role/title | `role` | 120 |
| LinkedIn profile | `linkedin_url` | 500 |
| What are you working on now? | `current_work` | 500 |
| Learning goal | `learning_goal` | 500 |
| Photograph | `photo_url` (upload only) | — |

- **Given** the participant opens the Profile card and fills in any fields
- **When** they click **Submit profile** (`#profile-submit`)
- **Then** `PATCH /api/sessions/{code}/me` saves the text fields on their
  Participant row; when a photograph was chosen, the page then uploads it
  with `POST /api/sessions/{code}/me/photo`
- **And** a toast confirms ("Profile submitted", naming the display name
  when there is one), and the button changes to **Resubmit profile**
- **And** the profile is a contact card for the moderator only: it is
  never shown with, or exported alongside, the participant's questions,
  quiz answers or feedback (see **Anonymity** above)
- **And** text is trimmed and cut to the field's maximum length; a blank
  field is stored as `null`
- **And** the photograph upload follows the image constraints of UC-X-04,
  needs no admin login, and returns the stored `/uploads/...` URL as
  `photo_url`; **Clear** beside the photograph (`#my-photo-clear`) sends
  `{"photo_url": null}`, and any other `photo_url` value in the `PATCH`
  returns `400 "photo must be uploaded"`
- **And** replacing or clearing the photograph deletes the previous file
  from the uploads folder, so its old URL returns `404`
- **And** a LinkedIn profile must start with `http://` or `https://`;
  any other value returns `400 "LinkedIn profile must start with
  http:// or https://"` and nothing is saved
- **And** saving the profile and uploading a photograph are rate-limited
  per person (UC-X-08); an exhausted bucket returns `429 "You're saving
  your profile too fast — wait a moment and try again"`
- **And** the Profile card stays on the page after the session ends, and
  the profile can still be saved then
- **And** reloading the page prefills every saved field and the photograph
- **And** each successful `PATCH` or photo upload broadcasts
  `{type: "participant"}`
- **And** moderators see submitted profiles on the session page (UC-M-13);
  other participants and the projector never see them

**Tests (API)**
- `PATCH /api/sessions/{code}/me` with `{"name": "Alice"}` → `200` with `name: "Alice"`. Auth: none (cookie issued on first call).
- With `{"name": ""}` → `200` with `name: null` (blank = anonymous).
- With a name > 80 chars → name is truncated to 80 chars.
- Broadcasts `{type: "participant"}` on success.
- All eight text fields round-trip through `PATCH` and `GET .../me` with surrounding whitespace trimmed; blank values become `null` (`test_uc_p_03_profile_fields_round_trip`, `test_uc_p_03_profile_blank_fields_become_null`).
- `POST .../me/photo` with a PNG → `200` with `photo_url` under `/uploads/`; `GET .../me` returns it; `PATCH` with `{"photo_url": null}` clears it (`test_uc_p_03_profile_photo_upload_and_clear`).
- `POST .../me/photo` with an `.svg` file → `400 "Images must be PNG, JPEG, GIF or WebP"` (`test_uc_p_03_profile_photo_rejects_unsupported_type`).
- `PATCH` with `{"photo_url": "https://example.com/avatar.png"}` → `400 "photo must be uploaded"` (`test_uc_p_03_profile_photo_url_cannot_be_set_directly`).
- Uploading a second photograph deletes the first one's file (its URL → `404`); clearing deletes the second (`test_uc_p_03_replaced_or_cleared_photo_file_is_deleted`).
- `PATCH` with `linkedin_url` set to `javascript:alert(1)`, `data:text/html,x` or `www.linkedin.com/in/x` → `400 "LinkedIn profile must start with http:// or https://"`, and the stored value is unchanged; `HTTPS://www.linkedin.com/in/x` and `http://…` are accepted (`test_uc_p_03_linkedin_url_must_be_web_address`).
- On an `ended` session, `PATCH .../me` and `POST .../me/photo` still return `200` (`test_uc_p_03_profile_editable_after_session_ends`).

**Tests (UI)**
- On `/s/<CODE>`, opening `#profile-card`, typing into `#my-name`, and clicking `#profile-submit` shows a toast with the name; a question the participant then asks without ticking **Show my name** shows no name (`test_uc_p_03_set_display_name_persists`).
- The Profile card starts closed with the closed-state title and call to action; after filling every field, choosing a photograph (`#my-photo`, previewed in `#my-photo-preview`), and submitting, the toast reads "Profile submitted" and the button reads **Resubmit profile**; after a reload every field and the photograph are prefilled; `#my-photo-clear` hides the photograph (`test_uc_p_03_attendee_profile_persists`).

### UC-P-04: Ask

- **Given** the session is `planning` or `live`
- **When** the participant types a question and clicks Ask (or
  Cmd/Ctrl+Enter)
- **Then** `POST .../questions` creates a Question linked to their
  Participant; a toast confirms
- **And** the question is anonymous unless the participant ticks **Show
  my name** (`#ask-show-name`), which reveals a name field (`#ask-name`).
  With the box ticked and a name typed, the question stores that name
  (`author_name`, trimmed, at most 80 characters) and shows it on every
  surface; later changes to the name field or the profile never change
  it. The box clears after each question, so every question is a fresh
  choice; the typed name is remembered on this device for next time. The
  profile name is neither read nor changed
- **And** an `ended` session refuses with `400 Session has ended` and
  the Ask card is hidden from the UI
- **And** the placeholder mentions the Cmd/Ctrl+Enter shortcut only on
  devices with a precise pointer (a keyboard is likely); phones show
  "Type your question…"

**Tests (API)**
- `POST /api/sessions/{code}/queries` with `{"text": "Hi?"}` on a `planning` or `live` session → `200 {id, text, author_name: null, response_text: null, responded: false, removed: false, vote_count: 0, voted: false, mine: true, created_at}`. Auth: none (cookie issued on first call).
- With `{"text": ""}` → `400 "text required"`.
- With `{"text": "   "}` → `400 "text required"`.
- With `{"text": "a"*1001}` → `400 "text too long"`.
- With `{"author_name": "Bob"}` → the question's `author_name` is `"Bob"`; `GET .../me` still has `name: null` (the profile is untouched).
- A participant whose profile name is "Alice" asks without `author_name` → the question's `author_name` is `null`; after they ask once with `"Bob"` and then set their profile name to "Carol", that question still reads "Bob" and the first still reads `null`.
- On an `ended` session → `400 "Session has ended"`.
- Success broadcasts `{type: "query_new"}`.

**Tests (UI)**
- On `/s/<CODE>` (planning/live), typing into `#query-text` and clicking `#ask-btn` adds the query to `#queries` and toasts confirmation.
- Cmd/Ctrl+Enter in `#query-text` submits.
- Pressing Ctrl+Enter twice in quick succession posts one question: the shortcut clicks `#ask-btn`, so its double-submit guard applies (`test_uc_p_04_double_ctrl_enter_posts_once`).
- Ticking `#ask-show-name`, typing "Bob" into `#ask-name` and asking shows "— Bob" with the question; afterwards `#ask-show-name` is unticked and `#ask-name` hidden; a participant with a profile name who asks without ticking the box shows no name.
- On an `ended` session, `#ask-card` is hidden and `#ended-card` is visible.

### UC-P-05: Vote on a query

- **Given** a non-removed question on a non-ended session
- **When** the participant clicks the vote button
- **Then** `POST .../questions/{qid}/vote` toggles their vote; vote
  count refreshes; aria-pressed updates
- **And** the vote button is disabled while its request runs, so a double
  tap sends one vote instead of voting and un-voting
- **And** removed queries return `404`; ended sessions return `400`

**Tests (API)**
- `POST /api/sessions/{code}/queries/{qid}/vote` first call → `200 {voted: true, vote_count: 1}`. Auth: none (cookie issued on first call).
- Same participant calls again → `200 {voted: false, vote_count: 0}` (toggle off).
- Same participant calling twice in quick succession can never increment past 1 (unique on `(query_id, participant_id)`).
- Vote on a removed query → `404`.
- Vote on a non-existent qid or cross-session qid → `404`.
- Vote on an `ended` session → `400 "Session has ended"`.
- Broadcasts `{type: "query_vote"}`.

**Tests (UI)**
- On `/s/<CODE>`, clicking the vote button on a query increments the displayed vote count and sets `aria-pressed="true"`.
- Clicking again decrements and sets `aria-pressed="false"`.
- Two clicks in quick succession send one `POST .../vote`; the query ends voted with a count of 1 (`test_uc_p_05_double_tap_votes_once`).

### UC-P-06: See queries sorted

- **Given** any participant viewing the session
- **When** `GET .../queries` returns
- **Then** removed queries are filtered out from the **API response**;
  the **frontend** re-sorts the returned list with unresponded-first,
  then by descending vote count
- **And** their own queries are flagged `mine: true` and the queries
  they voted on are flagged `voted: true`

**Tests (API)**
- `GET /api/sessions/{code}/queries` as a participant → `200 [{id, text, author_name, response_text, responded, removed: false, vote_count, voted, mine, created_at}, ...]`. Auth: none (cookie issued on first call).
- Server order: `created_at DESC` (newest first). The unresponded-first / votes-desc sort is **UI-applied**, not server-applied — API tests should NOT assert it.
- Removed queries are excluded for participants but included for moderators (with `removed: true`).
- A query the caller asked has `mine: true`; a query the caller voted on has `voted: true`.

**Tests (UI)**
- On `/s/<CODE>`, `#queries` lists visible (non-removed) queries; unresponded appear above responded, ties broken by `vote_count` descending. This sort is performed by the participant page's JS, not the API.
- The participant's own queries show the words "Your question" (`.mine-marker`), on that participant's device only; other people's queries show none. Voted queries show the `.voted` vote-button state (`test_uc_p_06_own_questions_say_your_question`).

### UC-P-07: See live quiz

- **Given** a QuizRun is `live`
- **When** the participant page loads (or refreshes via WS)
- **Then** the Live quiz card surfaces the current question, its answers,
  and the participant's prior selections (if any)
- **And** when status flips to `closed`, the participant card
  **disappears** — the participant page only renders runs in `live`
  status. Final results live on the projector (UC-D-06) and the
  moderator's quiz-runs list. This keeps the participant surface
  focused on actionable state and avoids stale "this is over"
  scrollback during a multi-quiz session.

**Tests (API)**
- `GET /api/sessions/{code}/quiz_runs` as a participant → returns runs in any non-deleted status: `queued`, `live`, `closed`. Queued is included so the projector can render the "Next up" lobby (UC-D-07); the participant page itself ignores both queued and closed in its `loadQuiz()` selector. Auth: none (cookie issued on first call).
- **Queued-run redaction**: for non-moderator callers, a `queued` run is serialized with `current_question: null` — the question text and answers are NOT exposed before Start (prevents pre-launch peek at the first question) — and `GET /api/sessions/{code}/quiz_runs/{id}` for it → `404`. Moderators/owners see `current_question` even on queued runs (`test_uc_p_07_queued_run_hidden_from_participants`).
- A real run id used under another session's code → `404` for the single-run GET (participant or that session's moderator), `/submit` (`404 "Quiz not live"`) and the moderator routes (`test_uc_p_07_run_from_other_session_404`).
- The serialized run includes `current_question` (id, text, qtype, answers without `is_correct` unless revealed/closed) and `my_selections` once live.
- For a `closed` run, `is_correct` and `results` are still included in the API payload — the participant page's selector is what hides the run; the contract for projector/moderator is unchanged.

**Tests (UI)**
- On `/s/<CODE>` with a live run, `#quiz-card` is visible and `#quiz-body` renders the current question with its answers and the participant's prior selections.
- When status flips to `closed` via WS, `#quiz-card` is **hidden** on the participant page (the projector and moderator views still display the closed run with results).

### UC-P-08: Submit an answer to the current question

- **Given** the current question is live and the participant hasn't been
  served `reveal_current=true`
- **When** they click answers (single → exclusive; multi → toggle)
  and click Submit
- **Then** `POST .../quiz_runs/{id}/submit` replaces their prior
  submissions for that question with the new ones (last-write-wins);
  the replace is a **diff** (drop rows no longer selected, add the
  newly selected), so re-submitting the identical selection is an
  idempotent no-op rather than a UNIQUE-constraint `500`
- **And** answer ids must reference the current question's answers
  (matched `answer_id ∈ vq.answers`); a wrong `question_id`
  (not in the run's version) returns `404 "Question not in this
  quiz run"`; a `question_id` that's not the current one returns
  `400 "Not the current question"`
- **And** single-type cannot have > 1 `answer_id`; returns `400`
- **And** an ended session refuses with `400 "Session has ended"`

**Tests (API)**
- `POST /api/sessions/{code}/quiz_runs/{id}/submit` with `{"question_id": <current_vq_id>, "answer_ids": [<aid>]}` → `200 {ok: true}` and replaces any prior submissions for this voter+question. Auth: none (cookie issued on first call).
- Resubmitting with a different answer replaces; old QuizSubmission rows are gone, new ones inserted.
- Re-submitting the **identical** selection three times in a row → each returns `200` (idempotent; no `500`), and `my_selections` is unchanged.
- `answer_ids` referencing an answer not in the current question → `400 "Invalid answer"`.
- `answer_ids` not a list → `400 "answer_ids must be a list"`; non-int entries → `400 "answer_ids must be integers"`.
- `question_id` belonging to a different run's version → `404 "Question not in this quiz run"`.
- `question_id` valid but not the current one → `400 "Not the current question"`.
- `single`-type with `len(answer_ids) > 1` → `400 "Only one answer allowed"`.
- Duplicate `answer_ids` (e.g. `[5, 5, 7]`) are deduped server-side before insert — no `IntegrityError` surfaces, the resulting submission set is `{5, 7}`.
- **Submit-after-reveal is blocked**: once the moderator clicks Reveal (so `run.reveal_current=true`), `POST .../submit` → `400 "Voting closed — results have been revealed"`. Prior submissions are preserved; no mutation occurs, and `my_selections` still lists the earlier pick (`test_uc_p_08_submit_after_reveal_400_keeps_selection`). This prevents a participant who sees the correct answer from going back to change their pick.
- Run not `live` (queued/closed) → `404 "Quiz not live"`.
- Session `ended` → `400 "Session has ended"`.
- Broadcasts `{type: "quiz_submission"}` on success.

**Tests (UI)**
- On `/s/<CODE>` with a single-choice question live, clicking an answer makes selection exclusive; clicking **Submit answer** POSTs and the inline note changes to "Your answer is recorded." (no toast: the note sits beside the button). The Submit button is **always enabled** (a disabled button reads as broken) — submitting with no selection shows a "Pick an answer first" toast instead of a no-op; a "Pick an answer, then Submit." hint shows until one is chosen. (The button reads "Submit answer", then "Update answer" after a prior submission; tests locate it via `#quiz-body button.primary`, not its text.)
- With multi-choice, clicking answers toggles each independently.
- After moderator reveals, the answer inputs become disabled.
- A chosen answer is marked by more than a border tint: it shows a ✓ and the word "Selected" (after reveal, "Your answer"); unchosen answers show neither.
- After reveal, a chosen answer that is wrong shows ✗ (not ✓) and the words "Your answer · wrong", so the result doesn't depend on the red border alone; a chosen correct answer keeps ✓, "Your answer", and "✓ Correct" (`test_uc_p_09_wrong_pick_says_wrong_in_words`).

### UC-P-09: See results on Reveal (participant)

- **Given** the moderator has clicked **Reveal** on a still-live run
- **When** the participant view refreshes
- **Then** the option bars are scaled to vote share, correctness is
  shown, and the participant's selected option is marked correct or
  wrong as appropriate
- **And** voting is locked until the moderator advances to the next
  question (which resets reveal) or closes the run (which removes
  the card per UC-P-07)

**Tests (API)**
- After `/reveal` with `{"reveal": true}`, `GET .../quiz_runs/{id}` for a participant returns answers with `is_correct` and a `results: {question_id, respondents, totals: {<aid>: <count>}}` payload.
- After `/close`, the same payload is still served by the API; only the participant page hides the run (see UC-P-07).

**Tests (UI)**
- On `/s/<CODE>`, after reveal `#quiz-body` shows each answer with a bar scaled to vote share and a correctness marker.
- The participant's selected answer is marked correct or wrong in words as well as colour (UC-P-08's last bullet).
- After the moderator finishes the quiz, `#quiz-card` is hidden on the participant page (final results live on the projector — UC-D-06).

### UC-P-10: Share QR with neighbor

- **Given** the participant page is open
- **When** they look at the Invite others card
- **Then** a QR encodes the same participant URL the moderator
  configured (or `location.origin` fallback)

**Tests (UI)**
- On `/s/<CODE>`, `#invite-card` is visible and `#share-qr` renders a QR encoding `<base>/s/<CODE>` (base = `participant_base_url` or `location.origin`).
- Changing the participant_base_url server-side and triggering a WS refresh updates the QR.

### UC-P-11: Ended session is read-only

- **Given** session.status flips to `ended` via WS broadcast
- **When** the participant view refreshes (via the broadcast)
- **Then** the Ask card disappears, a "Session ended" card appears,
  and existing queries remain visible; quiz results are on the projector,
  because a session can end only after its runs are closed (UC-M-02) and
  participants see only a live run (UC-P-07)

**Tests (API)**
- After `POST .../end`, `POST .../queries` → `400 "Session has ended"`.
- After `POST .../end`, `POST .../queries/{qid}/vote` → `400 "Session has ended"`.
- After `POST .../end`, `POST .../quiz_runs/{id}/submit` → `400 "Session has ended"`.
- `GET .../queries` still returns the existing list.

**Tests (UI)**
- On `/s/<CODE>`, after the moderator ends the session, the participant view (via WS) hides `#ask-card` and shows `#ended-card` with the "Session ended" message.
- Existing queries in `#queries` remain visible, and `#quiz-card` stays hidden.
- On an ended session the vote counts are plain text, not buttons (`#queries .vote-btn` are not `<button>`s), because voting is closed (`test_uc_p_11_ended_session_votes_are_not_buttons`).
- On an ended session with no questions, `#queries` reads "No questions were asked." (not an invitation to ask).
- The participant section links show only sections that are visible: on an ended session with no quiz and rating closed, the Ask, Quiz, and Rating links are hidden; Profile and Questions remain.

### UC-P-12: Live answer counts during voting

Participant-side counterpart of UC-D-08. Live counts show that answers
are coming in. For a graded question they must not show which answer
leads, or people would follow the crowd; for a poll there is no right
answer, so the split is the point.

- **Given** a QuizRun is `live` with `show_live_counts = true`
- **When** the participant view renders the current question's
  answering phase
- **Then** for a **graded** question it shows only how many have
  answered (`#quiz-answered`, "<n> answered so far"), with no counts on
  the answers
- **And** for a **poll** question each answer shows a running vote-share
  bar with its **absolute count and percentage** (e.g. `5 (50%)`) and a
  total respondent count
- **And** no correctness markers appear before reveal; after reveal every
  question shows its counts (and, if graded, its correct answer)
- **And** voting remains open — clicking still toggles selection and
  Submit is enabled
- **And** when `show_live_counts = false` (default), the answering
  phase shows only the question and answers (no bars, no counts)

**Tests (API)**
- Graded question, live counts on, before reveal, `GET .../quiz_runs/{id}` as a participant: `results.totals` is `null`, `results.respondents` is the number who answered, `results.masked_counts` lists one count per answer, largest first, summing to the answers given; no answer has `is_correct`.
- The same as the owner: `results.totals` maps answer ids to counts, and `masked_counts` is also present (the projector draws it).
- Poll question, live counts on: a participant gets `results.totals` by answer id, and no `masked_counts`.
- Graded question after reveal: a participant gets `results.totals` by answer id.
- With `show_live_counts=false` (default), `results` is `null` in the answering phase.

**Tests (UI)**
- On `/s/<CODE>` with live counts on and a graded question, the answering phase shows `#quiz-answered` with "<n> answered so far" and no `.opt-pct`; voting remains enabled.
- With live counts on and a poll question, each answer shows a bar with `<count> (<pct>%)`.
- With live counts off (default), the answering phase shows only question + answer texts.

### UC-P-13: Rate the session (feedback)

A participant can rate the session and leave course feedback while the
moderator has rating open (**Open rating** on the session page, UC-M-12;
`feedback_enabled`; any session status, including `ended`). While rating is
closed the rating card is hidden, and `POST` or `DELETE
/api/sessions/{code}/feedback` returns `403 "feedback is not enabled"`. The
control is a **collapsible
card** (`#feedback-card`, a `<details>`) placed right after the Profile
card. It is **open** until the participant submits; after a submit, and
on later visits, it **collapses** to a one-line summary in its header
(`#fb-summary`, e.g. "Rated ★★★★☆") and reopens when tapped. It uses
progressive disclosure: a 1–5 **star** rating that, once a star is
picked, expands to reveal "What went well?" and "What could be better?"
text fields plus Submit. Hovering a star previews the fill up to that
star (hovering the 5th lights all five).

**Card order.** The participant page shows Profile, Rating (when open),
Ask, Questions, and Invite. While a quiz is live, the **Live quiz card
moves to the top**, above Profile and Rating, so a participant who joins
or reloads mid-quiz sees the question first; it returns to its place
when the run is no longer live.

- **Given** the participant is on `/s/<CODE>`
- **When** they pick a star
- **Then** the expanded section (`#fb-expand`) appears with the two optional
  comment fields and the explicit **Submit feedback** button (`#fb-submit`)
  is ready to use; choosing a star or editing a comment does not persist the
  draft by itself. Submitting without a rating shows a "Choose a rating first"
  cue instead of silently doing nothing
- **And** clicking **Submit feedback** sends the rating and comments together
  (`POST /api/sessions/{code}/feedback`), confirms "Submitted ✓", and changes
  the action to **Resubmit feedback**; the rating card is visually distinct
  from the Q&A/quiz cards
- **And** the participant can retract their feedback via a subtle
  **two-step inline confirm** (`#fb-clear` → "Clear feedback? Yes / No"):
  "Yes" (`#fb-clear-yes`) issues `DELETE /api/sessions/{code}/feedback`,
  "No" (`#fb-clear-no`) cancels. (Deterministic — no auto-revert timer.)
  History in `SessionFeedbackVersion` is retained; afterward `mine`
  returns null and the summary count drops
- **And** participants may **resubmit their feedback any number of times**:
  each submission is appended to an immutable history (`SessionFeedbackVersion`)
  and the **latest** version is mirrored into the current view
  (`SessionFeedback`, one per participant keyed by `voter_token`) used by
  `mine`/`summary`
- **And** reloading prefills their prior rating + comments (via
  `GET /api/sessions/{code}/feedback/mine`, which returns the latest) and
  shows **Resubmit feedback**
- **And** live updates never overwrite a draft: the page loads the saved
  feedback when it first loads and when rating opens (closed to open),
  and leaves the stars and comments alone while they have unsent changes.
  Renaming or ending the session, or a reconnect, keeps what the
  participant was typing
- **And** comments are optional — a bare rating is valid; `rating` must be
  an integer 1–5 or the POST returns `400`
- **And** each comment is trimmed and cut to 2000 characters; a blank
  comment is stored as `null`
- **And** feedback submissions are rate-limited per person (UC-X-08)
- **And** submitting broadcasts `{type: "feedback"}` (UC-X-01) so the
  host's view (UC-M-12) updates live

**Tests (API)**
- `POST /api/sessions/{code}/feedback` with `{"rating": 4, "went_well": "...", "to_improve": "..."}` → `200 {rating, went_well, to_improve, updated_at}`. Auth: none (cookie issued on first call).
- A bare `{"rating": 5}` → `200` with null comment fields.
- With rating closed (the default for a new session) → `403 "feedback is not enabled"` (`test_uc_p_13_feedback_disabled_by_default`).
- Allowed on an `ended` session once the moderator opens rating (`test_uc_p_13_allowed_when_ended`).
- Resubmitting is allowed any number of times: each call appends a `SessionFeedbackVersion` (history retained), while the current view stays one row per participant — `summary.count` stays 1 and the latest values win.
- `rating` of `0`, `6`, missing, a string, a float, or a bool → `400 "rating must be an integer from 1 to 5"`.
- `GET .../feedback/mine` → `null` before submitting, then the row.
- `DELETE /api/sessions/{code}/feedback` after a submit → `200 {ok: true}`; `mine` then returns null and `summary.count` drops by one. The `SessionFeedbackVersion` history is retained.

**Tests (UI)**
- With rating open and no prior feedback, `#feedback-card` immediately follows `#profile-card` and is an open `<details>`.
- After a submit, `#feedback-card` closes and `#fb-summary` reads "Rated" with the chosen number of filled stars; tapping the summary reopens it.
- While a quiz is live, `#quiz-card` is the first card in `main`; once the run closes, `#quiz-card` is hidden and `#profile-card` is first again.
- `#fb-submit` is present and enabled. With no rating it shows a "Choose a rating first" cue; selecting a star reveals `#fb-expand` without submitting, and clicking **Submit feedback** fires one `POST .../feedback` with the rating and both comments.
- After reload, `#feedback-card` is closed with `#fb-summary` showing the prior rating; opening it shows the prior rating (filled stars count) and comment values prefilled, and the button reads **Resubmit feedback**. Editing then resubmitting fires another `POST`.
- Clicking `#fb-clear` reveals an inline confirm (`#fb-clear-confirm`); `#fb-clear-no` cancels (rating unchanged), `#fb-clear-yes` clears the stars (filled count 0) and hides `#fb-expand`.
- With a star picked and text typed in `#fb-went-well` but not submitted, the moderator renaming the session and then ending it leaves the typed text and the filled stars in place (`test_uc_p_13_live_updates_keep_feedback_draft`).

---

## Projector

The projector view (`/p/<code>`) is a public, read-only **display
surface** — the big screen at the front of the room. No auth, no
controls, no chrome. Updates live in lockstep with the rest of the
session.

### UC-D-01: Projector display

- **Given** anyone (no auth) opens `/p/<code>` for a valid session
- **Then** they see: session title, the join code in large type, the
  participant URL host, a QR encoding the full participant URL, top
  queries sorted by vote (limited to ~8 unanswered), and the current
  live or closed quiz question
- **And** an invalid `code` redirects to `/?bad_code=…` (same 303
  pattern used by participant/moderator pages)
- **And** the projector shows no navigation links, for any viewer: it is
  on the room's screen, so links would be visible to the audience. The
  session page links to it instead

**Tests (API)**
- `GET /p/<code>` for an existing code → `200` and serves `projector.html`.
- `GET /p/<code>` for an unknown code → `303` redirect to `/?bad_code=<code>`.
- `GET /api/sessions/{code}` (used by projector boot) requires no auth.
- `GET /api/sessions/{code}/display-bootstrap` returns the session, public
  questions, and display-safe quiz runs in one response without creating a
  Participant row or issuing a `voter_token` cookie.

**Tests (UI)**
- On `/p/<CODE>`, `#title` shows session title, `#code` shows the join code in large type, `#origin` shows the participant URL host, `#join-qr` renders the full participant URL.
- `#queries` shows up to ~8 unanswered queries sorted by vote desc.
- Live or closed quiz question appears in `#quiz-section` (`#quiz-body`).
- The page has no `#ask-card`, no `#login-card`, no `#sessions-card` (no chrome).
- Everything the room reads is display type, at least 20 px at 1920×1080 (UX.md §2): the quiz's "question n/N" line, the respondent count, "Next up:", question authors, and the "votes" label; the lobby's quiz title is in the main text colour, not uppercase (`test_uc_d_01_room_text_is_display_size`).

### UC-D-02: QR lightbox

- **Given** **any** QR code rendered via the shared `renderQR` helper —
  the projector join QR (`#join-qr`), the participant invite QR
  (`#share-qr`), and the moderator invite QR (`#invite-qr`)
- **When** someone clicks it (or focuses it via Tab and presses Enter /
  Space — every rendered QR is `role="button"`, `tabindex="0"`, with
  `cursor: zoom-in`)
- **Then** a shared full-screen lightbox (`.qr-lightbox`, appended to
  `body` on first use) shows the QR at ≈ 90% of the smaller viewport
  dimension; Esc, click anywhere, or the `cursor: zoom-out` area
  dismisses it

**Tests (UI)**
- On `/p/<CODE>`, clicking `#join-qr` opens the `.qr-lightbox` overlay (display flips from `none`).
- Tab-focusing a rendered QR then pressing Enter or Space opens the lightbox.
- Pressing Escape closes the `.qr-lightbox` overlay; clicking anywhere inside it (the zoom-out area) also closes it.
- The same enlarge behavior works on `/s/<CODE>` (`#share-qr`) and `/m/<code>` (`#invite-qr`).

### UC-D-03: Live updates via WebSocket

- **Given** the projector is connected to `/ws/sessions/{CODE}`
- **When** any state-changing route on that session commits
- **Then** the projector re-fetches session / queries / quiz_runs and
  re-renders without needing a page reload (see UC-X-01 for the full
  broadcast contract)

**Tests (API)**
- Connecting to `/ws/sessions/{CODE}` with matching Origin/Host header → upgrade accepted; any state change on the session emits `{type: "..."}` frames to the client.

**Tests (UI)**
- On `/p/<CODE>`, after a participant in another tab adds a query, the projector's `#queries` updates within ~1s without manual reload.
- After moderator advances quiz, projector's `#quiz-body` re-renders the new current question.

### UC-D-04: Session lifecycle reactions

- **Given** the session is in `planning` → the projector renders the
  join code and QR but shows no queries yet (none possible) and no
  live quiz card
- **And** in `live` → queries appear as participants submit them;
  the quiz card appears when the moderator starts a run; current item
  and revealed results update live
- **And** in `ended` → queries and the last quiz result remain
  visible read-only; no new queries can arrive

**Tests (UI)**
- On `/p/<CODE>` for a `planning` session, `#join-qr` and `#code` render but `#queries` is empty and `#quiz-section` is hidden.
- After moderator starts the session and a participant asks, `#queries` populates.
- After moderator starts a quiz run, `#quiz-section` becomes visible.
- After moderator ends the session, no new queries appear; the last quiz state remains visible.

### UC-D-05: Reconnect on long sessions

- **Given** the projector has been left on for a long session and
  the WebSocket connection drops (network blip, server restart)
- **Then** `openLiveSocket` retries with exponential backoff (capped
  ~32s); when it reconnects, the next broadcast prompts a refetch
  and the projector recovers without operator intervention
- **And** while a quiz run is live, the projector also refetches its state
  every 5 s whatever the socket does, so question changes and live vote
  counts (UC-D-08) are never more than about 5 s stale even when no
  live update arrives

**Tests (UI)**
- On `/p/<CODE>`, simulating a WS server restart causes the client to retry with exponential backoff (delays approximately 1s, 2s, 4s, 8s, 16s, capped near 32s).
- After the WS becomes available again, the next broadcast triggers a refetch and `#queries` / `#quiz-body` reflect the latest state.
- With the WebSocket blocked entirely and live counts on, a participant's vote appears in the projector's `#quiz-body` within about 5 s (`test_uc_d_05_projector_polls_while_a_quiz_is_live`).

### UC-D-06: Quiz states on the projector

Display priority when multiple QuizRuns exist for the session: **live**
beats **queued (lobby)** beats **closed**. If none, the quiz card is
hidden entirely.

- **No QuizRun present** → the quiz card is hidden.
- **A QuizRun is `queued`** → the projector enters the **lobby**
  state (see UC-D-07).
- **A QuizRun is `live` in the answering phase** (reveal_current=false)
  → projector shows the current question and answer choices, no
  correctness markers. If `show_live_counts` is true, vote-share bars
  appear during voting; otherwise no counts.
- **A QuizRun is `live` in the results phase** (reveal_current=true)
  → projector adds vote-share bars and correctness markers to the
  same current question.
- **A QuizRun is `closed`** → the projector keeps the last question
  visible with final tallies and correctness — the permanent record.

**Tests (UI)**
- On `/p/<CODE>` with no runs, `#quiz-section` is hidden.
- With one `queued` run and no others, `#quiz-section` shows the lobby (UC-D-07).
- With one `live` run in answering phase, `#quiz-body` shows the current question + answers; no correctness markers, no counts (default).
- With `show_live_counts=true` in answering phase, vote-share bars appear but no correctness markers.
- After reveal (results phase), bars + correctness markers appear.
- With a single `closed` run and no live/queued, `#quiz-body` keeps the last question with final tallies and correctness.
- Priority: when both `live` and `closed` runs exist, the live one wins; when both `queued` and `closed` exist (no live), the queued one wins (lobby).
- The question text renders as written (no forced uppercase) in the main text colour, so long questions stay readable from the back of the room.

### UC-D-07: Quiz lobby state

- **Given** a QuizRun is `queued` and none is `live`
- **Then** the projector replaces the quiz card body with a lobby
  view: "Next up:" + quiz title in display type + a prompt to scan
  the participant URL QR ("Scan the code to join — the quiz starts
  soon."). The room screen doesn't mention the moderator's controls
- **And** when the moderator clicks Start, the projector flips to
  UC-D-06 answering phase via WebSocket broadcast

**Tests (UI)**
- On `/p/<CODE>` with a `queued` run and no `live` run, `#quiz-body` shows "Next up:", the quiz title in display type, and the prompt "Scan the code to join — the quiz starts soon.", with no mention of the moderator.
- After moderator starts the run, `#quiz-body` transitions (via WS) to the answering phase (UC-D-06).

### UC-D-08: Live answer counts variant

Configurable per QuizRun via `show_live_counts` (default off). The rule
is the same as UC-P-12: a graded question never shows which answer leads
before reveal; a poll shows its split live.

- **Given** the moderator toggles "live counts" on for a QuizRun
- **When** the run is in answering phase
- **Then** for a **graded** question the projector shows how the votes are
  spread without naming the answers: one bar per answer, labelled
  "Option A", "Option B", … from the largest count down, each with
  `<count> (<pct>%)`, plus the respondent count. The answer texts and
  images are not shown
- **And** for a **poll** question the projector shows each answer's text
  with its count and percentage, plus the respondent count
- **And** no correctness appears until reveal; after reveal (or close)
  the projector shows the real answers with counts and, if graded, the
  correct answer
- **And** voting remains open — participants can still pick / change
  their answer until the moderator advances or reveals
- **And** when counts are off (default), the answering phase shows
  only the question and answer texts; counts and correctness appear
  only after reveal

**Tests (API)**
- See UC-M-05 tests for `POST .../live_counts`, and UC-P-12 for what the API sends before reveal.

**Tests (UI)**
- Graded question, live counts on, 1, 2 and 3 votes on three answers: `/p/<CODE>` shows `.opt-text` "Option A", "Option B", "Option C" with `.opt-pct` "3 (50%)", "2 (33%)", "1 (17%)", none of the answer texts, and no correctness markers; after reveal it shows the answer texts and the correct answer.
- Poll question, live counts on: `/p/<CODE>` shows the answer texts with `<count> (<pct>%)`.
- Toggling live counts off on the moderator UI triggers a WS refresh; the projector reverts to bare question + answers.

---

## System

Cross-cutting backend invariants. These aren't user actions; they
are the rules every user-facing UC silently relies on.

### UC-X-01: Live updates via WebSocket

- **Given** any of the participant / moderator / projector views are
  connected to `/ws/sessions/{CODE}`
- **When** any state-changing route on that session commits
- **Then** the server broadcasts `{type: <kind>}` to the room (kinds:
  `session_state`, `participant`, `query_new`, `query_vote`,
  `query_responded`, `query_removed`, `query_deleted`,
  `quiz_run_new`, `quiz_run_update`, `quiz_run_deleted`,
  `quiz_submission`, `feedback`, `feedback_state`, `session_deleted`); each frontend treats the message as a
  refresh hint and re-fetches the data it cares about
- **And** `session_deleted` is final: the participant, moderator, and
  projector pages replace their content with the banner "This session was
  deleted." (`#session-deleted`), stop refreshing, and close their socket
  without reconnecting
- **And** the client auto-reconnects with exponential backoff if the
  socket drops; **on every reconnect after the first**, the client
  fires its refresh callback with a synthetic `{type: "reconnect"}`
  message so the page resyncs any state it may have missed while
  disconnected.
- **And** delivery is fanned out concurrently with a per-send timeout
  (2 s by default, `PRASHNA_WS_SEND_TIMEOUT_SECS`). A slow or stalled receiver does not block the API
  response; a socket whose send fails or times out is evicted from the room
  **and closed**, so its page reconnects and resyncs instead of silently
  receiving nothing more
- **And** every page sends a `ping` text frame every 25 s and the server
  answers `{type: "pong"}`; a page that receives no frame for 60 s closes
  its socket and reconnects, so a connection that died without closing
  (Wi-Fi drop, sleeping network card, an hour-long proxy idle timeout)
  recovers within a minute

**Tests (API)**
- Connect WS to `/ws/sessions/{CODE}` with matching `Origin`/`Host`; perform `PATCH /api/sessions/{code}` → WS receives `{"type": "session_state"}`.
- `POST .../queries` → frame `{"type": "query_new"}`.
- `POST .../queries/{qid}/vote` → frame `{"type": "query_vote"}`.
- `POST .../queries/{qid}/respond` → frame `{"type": "query_responded"}`.
- `POST .../queries/{qid}/remove` → frame `{"type": "query_removed"}`.
- `DELETE .../queries/{qid}` → frame `{"type": "query_deleted"}`.
- `POST .../quiz_runs` → frame `{"type": "quiz_run_new"}`.
- `POST .../quiz_runs/{id}/{start|advance|reveal|close|live_counts}` → frame `{"type": "quiz_run_update"}`.
- `DELETE .../quiz_runs/{id}` → frame `{"type": "quiz_run_deleted"}`.
- `POST .../quiz_runs/{id}/submit` → frame `{"type": "quiz_submission"}`.
- `PATCH .../me` → frame `{"type": "participant"}`.
- `POST .../feedback` → frame `{"type": "feedback"}`.
- `POST .../feedback_enabled` → frame `{"type": "feedback_state"}` (UC-M-12).
- `DELETE /api/sessions/{code}` → frame `{"type": "session_deleted"}` (`test_uc_x_01_session_deleted_broadcasts`).
- Sending the text frame `ping` → the server answers `{"type": "pong"}` (`test_uc_x_01_ping_gets_pong`).
- A broadcast whose send to one socket fails or times out evicts that socket and closes it, and still delivers to the others (`test_uc_x_01_failed_socket_is_closed`).

**Tests (UI)**
- With `/s/<CODE>`, `/m/<CODE>`, and `/p/<CODE>` open, deleting the session shows `#session-deleted` reading "This session was deleted." on each page and no page opens another socket (`test_uc_x_01_session_deleted_shows_final_state`).
- With the server's frames to the page swallowed after the socket opens, the page reconnects (a second socket opens) once its silence timeout passes; test builds shorten the 25 s / 60 s timings through `localStorage` `prashna:keepalive-ms` (`test_uc_x_01_silent_socket_reconnects`).
- A refetch that a live update triggers and that fails shows the server's message in an error toast instead of failing silently, on the participant page and the session page (UX.md §8); the page raises no unhandled error (`test_uc_x_01_failed_live_refetch_shows_an_error`).

### UC-X-02: WebSocket upgrade rejections

- **Given** a browser sends an `Origin` header that doesn't match
  `Host`
- **Then** the WS upgrade is closed with code **4403** (cross-origin)
- **Given** the URL's `{code}` does not match any Session
- **Then** the WS upgrade is closed with code **4404** (no session)
- **And** the server completes the handshake before closing, so a browser
  sees the code (a refused handshake reaches a browser only as `1006`).
  The socket joins no room and receives no message
- **And** a page whose socket closes with 4403 or 4404 stops
  reconnecting. A 4404 after the page has been connected means the
  session was deleted while the page was offline, so the page shows the
  same final state as `session_deleted` (UC-X-01)

**Tests (API)**
- Connect WS to `/ws/sessions/{CODE}` with `Origin: https://evil.example`, `Host: localhost:8000` → server closes with code `4403`.
- Connect WS to `/ws/sessions/NOSUCH` with matching Origin/Host → server closes with code `4404`.
- Connect WS with no Origin header (curl-style client) → upgrade succeeds (matching skipped when Origin absent).

**Tests (UI)**
- Against the running server, a WebSocket client connecting to `/ws/sessions/NOSUCH` receives close code 4404 rather than a refused handshake (`test_uc_x_02_unknown_session_closes_with_4404`).
- On `/s/<CODE>`, when the socket drops and the session is deleted before the page reconnects, the reconnect gets 4404; the page shows `#session-deleted` and opens no further socket (`test_uc_x_02_page_stops_reconnecting_after_4404`).

### UC-X-03: HTTP security headers

Two tiers, applied by one middleware:

- **Baseline (every non-`/uploads` response — pages + API):**
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Content-Security-Policy: frame-ancestors 'none'` — blocks
    clickjacking of the admin / moderator UI. No `script-src` directive
    is set.
  - `Referrer-Policy: no-referrer` — session codes and `?bad_code=`
    never leak to third parties via the `Referer` header.
- **Uploaded files (`/uploads/*`)** carry a stricter isolation set
  **instead** of the baseline:
  - `X-Content-Type-Options: nosniff`
  - `Content-Security-Policy: default-src 'none'; sandbox`
  - `Cross-Origin-Resource-Policy: same-origin`
  — defense in depth in case a file slips past the extension check.

**Tests (API)**
- After a `POST /api/uploads` returning `/uploads/<uuid>.png`, `GET /uploads/<uuid>.png` returns the bytes with the uploads-tier headers:
  - `X-Content-Type-Options: nosniff`
  - `Content-Security-Policy: default-src 'none'; sandbox`
  - `Cross-Origin-Resource-Policy: same-origin`
- `GET /` and `GET /static/app.css` (non-uploads paths) carry the baseline headers (`nosniff`, `X-Frame-Options: DENY`, `Content-Security-Policy: frame-ancestors 'none'`, `Referrer-Policy: no-referrer`) and do NOT carry the uploads-tier `default-src 'none'; sandbox` CSP.

### UC-X-04: Image upload constraints

- **Given** an admin uploads a quiz image (`POST /api/uploads`, UC-A-20)
  or a participant uploads a profile photograph
  (`POST /api/sessions/{code}/me/photo`, UC-P-03; no admin login needed)
- **Then** both routes accept only `.png`, `.jpg`, `.jpeg`, `.gif`,
  `.webp` (SVG is explicitly excluded); enforce 5 MB caps on both
  Content-Length and streaming; and store the file under a fresh UUID
  filename served from `/uploads/`
- **And** a large URL-encoded body sent to either route is refused at
  once, by the form parser's limits (1000 fields, 1 MB per field) or by
  the authorization check, so parsing it never blocks the server

**Tests (API)**
- See UC-A-20 and UC-P-03 tests; in addition:
- `POST /api/uploads` with `.svg` → `400 "Images must be PNG, JPEG, GIF or WebP"`.
- `POST /api/uploads` two times with the same source file → two distinct UUID filenames on disk.
- Stored filename matches `^[0-9a-f]{32}\.(png|jpg|jpeg|gif|webp)$`.
- Without signing in, a 5 MB URL-encoded body (`a&a&…` and `a;a;…`) to `POST /api/uploads` and to `POST .../me/photo` returns `400`, `401` or `422` in under 1 second, and no file is stored (`test_uc_x_04_urlencoded_flood_is_refused_quickly`).

### UC-X-05: Storage-level invariants

| Invariant                                                              | Enforced by                                |
| ---------------------------------------------------------------------- | ------------------------------------------ |
| At most one **live** `QuizRun` per Session                             | Partial unique index `uq_session_live_run` |
| At most one `QuizVersion` per `(quiz_id, version_no)`                  | UNIQUE constraint                          |
| At most one `QueryVote` per `(query, participant)`                     | UNIQUE constraint                          |
| At most one `QuizSubmission` per `(run, question, answer, participant)` | UNIQUE constraint                         |
| One `Participant` per `(session, voter_token)`                         | UNIQUE constraint                          |

- **Given** a live session with an open query and a live quiz question
- **When** 40 distinct participants vote on the query and submit an answer
  at the same moment, while their pages refetch the query and quiz lists
- **Then** every request succeeds (no 5xx, no timeout) and the burst
  completes within 15 s
- **And** a `GET /api/admin/status` issued during the burst answers within
  2 s, because waiting for a database connection never blocks the server's
  event loop
- **And** a JSON value of the wrong type for a stored field (a number
  where text is expected, a string where an `order_index` integer is
  expected) is refused with `400` before it reaches the database, so a
  bad value can't break later requests (see "Value types" in the
  conventions above)

**Tests (API)**
- `test_uc_x_05_concurrent_writes_do_not_stall_the_server`: against a real
  uvicorn server, 40 participants with their own cookies each fire a vote, a
  quiz submission, and two list refetches at once; all 160 responses are
  2xx within 15 s, a concurrent status request answers within 2 s, and the
  query's vote count is 40.
- `test_uc_x_05_text_fields_reject_other_json_types`: a number, list or
  object sent as a session or quiz title, a base URL, question or answer
  text, a moderator response, a feedback comment, a sign-in username or
  password, or any attendee profile field (including `linkedin_url`)
  returns `400 "<field> must be text"`, not `500`.
- `test_uc_x_05_order_index_must_be_an_integer_on_create`: `POST
  /api/quizzes/{id}/questions` or `POST /api/quiz_questions/{id}/answers`
  with `{"order_index": "abc"}` returns `400 "order_index must be an
  integer"`, and the next append still succeeds.

**Tests (DB)**
- `PRAGMA foreign_keys` on every connection returns `1` (enabled via SQLAlchemy `connect` event). Cascade deletes (`ondelete="CASCADE"`) are actually enforced at the DB layer, not only by the ORM.
- Insert two `QuizRun` rows with `status="live"` for the same Session → second insert raises `IntegrityError` (partial unique index `uq_session_live_run`).
- Insert two `QuizVersion` rows with the same `(quiz_id, version_no)` → raises `IntegrityError`.
- Insert two `QueryVote` rows for the same `(query_id, participant_id)` → raises `IntegrityError`.
- Insert two `QuizSubmission` rows for the same `(quiz_run_id, question_id, answer_id, participant_id)` → raises `IntegrityError`.
- Insert two `Participant` rows with the same `(session_id, voter_token)` → raises `IntegrityError`.
- Each of the UNIQUE checks above expects the error to name a UNIQUE constraint, so a NOT NULL or foreign-key error does not satisfy it.
- `init_db()` on a database holding the old shape of every bridged table, with one row in each, adds every bridged column, keeps the rows' data, gives them the column defaults (`session_version` 1, `feedback_enabled` 0, `graded` 1, `show_live_counts` 0, `revealed_idxs` empty, the profile columns null) and creates `uq_session_live_run`, which then allows a queued run beside a live one but refuses a second live run (`test_uc_x_05_additive_migrations_upgrade_known_old_schema`).
- Adding `queries.author_name` copies each old question's asker name into it, once (`test_uc_x_05_bridge_backfills_question_names`).

### UC-X-06: Versioning lazy capture

- **Given** Quiz Q has versions v1, v2 already
- **When** the moderator queues Q without editing since v2 → the new
  QuizRun reuses v2
- **And** when an edit happens between v2 and the next queue → a v3
  is captured at queue time and the new run points to v3
- **And** when two requests race and both try to create version N+1,
  the UNIQUE constraint causes one to lose; the loser catches
  `IntegrityError`, re-reads the latest, and returns it

**Tests (API)**
- With Quiz Q published (v1 exists), `POST /api/sessions/{code}/quiz_runs` with `{"quiz_id": Q.id}` → run points to v1.
- Two consecutive queues with no edit in between → both runs point to the same `version_no` (v1).
- After `PATCH /api/quiz_questions/{qid}` (which advances `last_edited_at`), next queue produces `version_no = 2`.
- Simulate concurrent queue attempts (two threads) → both succeed; one creates v2, the other catches `IntegrityError` and returns the already-created v2.

### UC-X-07: Signing key lifecycle

The admin session cookie is signed (HMAC) by `itsdangerous`. The key is
chosen once at process start.

- **Given** `PRASHNA_SECRET_KEY` is set in the environment
- **Then** the signer uses that value; rotating it is a deliberate
  "invalidate all sessions" action
- **Given** `PRASHNA_SECRET_KEY` is **unset**
- **Then** the server uses the key in `secret-key` beside the database,
  creating it on first start (random, starting with `prashna_sk_`, mode
  `0600`); cookies therefore survive restarts with no operator step. The
  prefix lets a scanner recognise a leaked key in any file; a key without
  it, from an older install, keeps working
- **And** a `secret-key` (or `setup-token`, UC-A-01) file that is empty or
  shorter than 32 characters, for example after a crash or a full disk, is
  treated as corrupt: the server replaces it with a new random value and
  logs a `WARNING`. The server never signs with an empty key. Each file is
  written whole to a temporary file (mode `0600`) and then moved into
  place, so a crash never leaves a half-written file
- **And** only if that file can't be read or written does the process
  fall back to a key for the process lifetime, logging a `WARNING`
  (`auth.SECRET_KEY_IS_EPHEMERAL` is `True`) because sessions then end on
  every restart
- **Operational note:** setting `PRASHNA_SECRET_KEY` remains supported
  (e.g. to share one key across hosts). `prashna backup` archives the
  database and uploads but not `secret-key` (UC-X-10), so a restore keeps
  the target's own key, and admins sign in again after a restore onto
  another host.

**Tests (API)**
- Start app with `PRASHNA_SECRET_KEY=abc...`, log in; restart with the same value → the old cookie still returns `authenticated: true`.
- Start app with one value of `PRASHNA_SECRET_KEY`, log in; restart with a different value → the old cookie fails to verify (rotation invalidates sessions).
- Start app with `PRASHNA_SECRET_KEY` unset, log in; restart, still unset → the old cookie still returns `authenticated: true`; `secret-key` exists beside the database with mode `0600`; no ephemeral-key warning is logged.
- `auth._resolve_secret("abc", path)` returns `("abc", False)`; `auth._resolve_secret(None, path)` creates the file and returns `(<key>, False)` with a key starting `prashna_sk_`, and a second call returns the same key; an existing file without the prefix is used unchanged; with an unwritable path it returns `(<random>, True)`.
- An existing `secret-key` that is empty, holds only whitespace, or is shorter than 32 characters is replaced: `auth._resolve_secret(None, path)` returns `(<new key>, False)` with a key starting `prashna_sk_`, the file holds that key with mode `0600`, and no temporary file is left beside it; an empty `setup-token` is replaced the same way by a token starting `prashna_st_` (`test_uc_x_07_corrupt_key_files_are_replaced`).

### UC-X-08: Rate limiting

A single-process, in-memory token-bucket limiter (`prashna/ratelimit.py`)
slows down anyone who sends too much too fast. Each bucket allows a burst
("at once") and then refills at a steady rate ("per minute").

A room often reaches the internet through one shared network address
(corporate Wi-Fi, mobile carrier NAT), so actions by people who already
have a participant cookie are limited **per person**, not per address.

- **Given** the limiter is enabled (default; disable with
  `PRASHNA_RATELIMIT=off`)
- **Then** these buckets apply. The values marked "admin" are defaults the
  admin can change while the server runs (UC-A-31). An exhausted bucket
  returns `429` with a human-readable `detail`, except the performance
  beacon, which drops the sample and still returns `204`:

  | Action | Keyed on | At once | Then | Admin | Notes |
  | --- | --- | --- | --- | --- | --- |
  | `POST .../queries` (ask) | person, and an address ceiling | 6 | 6 per minute | yes | `detail` says "too fast" |
  | `POST .../queries/{id}/vote` | person, and an address ceiling | 30 | 120 per minute | yes | |
  | `POST .../quiz_runs/{id}/submit` | person, and an address ceiling | 20 | 30 per minute | yes | |
  | `POST .../feedback` | person, and an address ceiling | 10 | 30 per minute | yes | Checked after the rating-open check (UC-P-13) |
  | `PATCH .../me` and `POST .../me/photo` (profile) | person, and an address ceiling | 10 | 10 per minute | yes | One bucket for both; submitting a profile with a photograph uses two (UC-P-03) |
  | new `Participant` row (joining) | address | 300 (people on one network) | 120 per minute | yes | Bounds row growth from a cookie-rotating script |
  | `POST /api/admin/login` | address | 8 | 1 per 30 s | no | Checked **before** `verify_password` (bcrypt is costly); a successful login clears the bucket |
  | `POST /api/diagnostics/performance` | address | 10 | 1 per 5 s | no | Excess samples are dropped silently (UC-X-11) |

- **Person** is the request's `voter_token` cookie; a request without one
  is keyed on its address (it creates a participant, which the joining
  bucket bounds).
- **Address ceiling.** For each per-person action, one network address may
  use "people on one network" (default 300) times one person's allowance,
  at once and per minute. A room never shares one person's budget, and a
  script that rotates cookies is still bounded.
- **Changes apply at once.** When the admin saves new values, every bucket
  is cleared, so the next request uses them; no restart is needed.
- **Client IP** is the socket peer by default. Behind a reverse proxy
  set `PRASHNA_TRUSTED_PROXY_HOPS=N` (N = number of trusted hops; `1`
  for ngrok or the bundled nginx) so the limiter keys on the entry the
  outermost trusted proxy recorded in `X-Forwarded-For` — a
  client-supplied prefix to its left is ignored (spoof-resistant).
- **Forwarding headers in the container.** The container image's Uvicorn
  takes `X-Forwarded-For` and `X-Forwarded-Proto` only from `127.0.0.1`
  (Uvicorn's default; its own `FORWARDED_ALLOW_IPS` variable changes it).
  A request that reaches the container from any other address keeps its
  socket peer as the client, so with hops 0 a client cannot choose its own
  address by sending `X-Forwarded-For`. With hops 1 or more, Prashna itself
  takes `X-Forwarded-Proto: https` from the proxy, so cookies are marked
  `Secure` behind nginx or a tunnel.
- **Scope:** this stops single-source floods and login brute-forcing.
  A distributed (many-address) flood is out of scope for an in-process
  limiter. WebSocket connects are not rate-limited.

**Tests (API)**
- Token bucket: allows `capacity` calls then denies; refills at the configured rate (deterministic injected clock); keys are independent; `enabled=False` always allows; `reset`/`clear` restore a fresh bucket.
- `enabled_from_env`: `None`/`"on"`/`"1"` → enabled; `"off"`/`"0"`/`"false"`/`"no"` (any case) → disabled.
- `_client_ip`: with hops=0 returns the socket peer; with hops=1 returns the rightmost `X-Forwarded-For` entry even when a spoofed value precedes it; with hops=2 the second-from-right; with hops>0 and no XFF falls back to the peer.
- Endpoint floods (limiter re-enabled for the test): login → `429` after the burst, and a correct login resets the throttle; one participant's `POST queries` / `vote` / `submit` each return `429` under a sustained flood.
- One participant's profile saves (`PATCH .../me`) and photograph uploads (`POST .../me/photo`) share one bucket and return `429` after 10 at once (`test_uc_x_08_profile_throttled`).
- With the app wrapped as the container's `CMD` configures Uvicorn, wrong logins from one non-loopback peer that send a different `X-Forwarded-For` each time get `429` after the login burst (`test_uc_x_08_container_ignores_spoofed_forwarded_for`).
- Through the same wrapping, a request from a non-loopback peer with `X-Forwarded-Proto: https` gets a `voter_token` cookie without `Secure` at hops 0 and with `Secure` at hops 1 (`test_uc_x_08_forwarded_proto_trusted_only_with_proxy_hops`).
- A room on one address: 40 participants with their own cookies each ask a question and submit a quiz answer, and every request succeeds; 40 fresh cookies from one address all join (`GET /me` → `200`).
- The address ceiling: with "people on one network" set to 1, a second participant on the same address gets `429` once the first has used the allowance; with it set to 5, the sixth fresh cookie from one address gets `429` on joining.
- Changes apply at once: after `PUT /api/admin/limits {"ask_burst": 2}`, a participant's third question returns `429` without a restart.
- With the limiter off (suite default) none of these `429`.

### UC-X-09: Local operation through an ngrok tunnel

- **Given** the operator has built the Vite frontend and started the
  single-process Uvicorn app on localhost
- **And** the operator completes first-run admin setup on localhost before
  making the port public
- **When** an ngrok HTTP endpoint forwards its public HTTPS origin to that
  local port
- **Then** the landing and participant pages, API calls, and same-origin
  WebSocket live updates work through the public endpoint without a remote
  deployment
- **And** the local process uses `PRASHNA_TRUSTED_PROXY_HOPS=1` so rate-limit
  buckets use the client address ngrok recorded rather than the tunnel peer
- **And** the frontend derives `wss://<public-host>/ws/sessions/{CODE}` from
  the public HTTPS page origin.
- **And** with the `prashna` command, `prashna --tunnel ngrok` or
  `--tunnel cloudflare` performs these steps itself (UC-X-15); the manual
  steps remain for the container and for a source checkout run with
  Uvicorn.

**Tests (API)**
- A WebSocket request with matching public `Origin:
  https://prashna-smoke.ngrok.app` and `Host:
  prashna-smoke.ngrok.app` is accepted and receives a session-state
  broadcast; a mismatched origin remains rejected by UC-X-02.
- The one-hop forwarded-client-IP behavior is covered by UC-X-08.

**Tests (Ops, opt-in)**
- With an authenticated ngrok CLI installed, run
  `PRASHNA_NGROK_SMOKE=1 uv run pytest tests/ops/test_ngrok_smoke.py`.
  The test builds the frontend, starts an isolated Uvicorn process, performs
  admin setup and creates a session through localhost, then starts a real
  ngrok endpoint and verifies the public health API, landing/participant
  pages, and a WSS session-state broadcast.

### UC-X-10: Portable container distribution and data recovery

- **Given** a user installs Prashna from a versioned distribution bundle
- **Then** its root `compose.yaml` runs the published GHCR image on localhost
  with separate named volumes for `/data` and `/app/uploads`
- **And** it needs no `.env` and no `PRASHNA_SECRET_KEY`: unset, the server
  creates `secret-key` in the data volume and reuses it (UC-X-07)
- **And** it exposes a health check and stays independent of the
  Hetzner-only `/opt/prashna` configuration
- **And** tagged bundles pin the image tag to the matching release rather than
  silently following `latest`
- **And** published images cover `linux/amd64` and `linux/arm64`
- **And** backup creates a consistent SQLite snapshot plus uploads without
  storing secrets; restore validates the archive and database, requires an
  explicit confirmation flag, and creates a pre-restore recovery archive
  before replacing current data.
- **And** restoring into a data folder that has no database yet (a new
  machine) skips the pre-restore archive, since there is nothing to keep,
  restores the archive, and says there was no previous data
- **And** a backup or restore that fails (no database to back up, no
  `--confirm`, a missing or unsafe archive) prints one plain line
  starting `Backup failed:` or `Restore failed:` on standard error and
  exits 1, with no traceback. This holds for `prashna backup …` and for
  the container form `python -m prashna.backup …`
- **And** every SQLite connection the backup tool opens is closed before
  its temporary folder is removed, so cleanup can't fail on Windows,
  where an open file can't be deleted

**Tests (Ops)**
- Root Compose config resolves with no env file and no `PRASHNA_SECRET_KEY`
  (`test_local_compose_runs_without_any_env_file`); with a test env it
  resolves the requested image tag and port, health endpoint, and named-volume
  mounts without `/opt/prashna` host paths.
- The Hetzner `deploy/docker-compose.yml` without `PRASHNA_SECRET_KEY` fails
  with an actionable message (`test_compose_config_reports_missing_secret_actionably`).
- Backup/restore round-trip restores the original SQLite contents and uploads;
  restore refuses without `--confirm` and rejects archive path traversal.

**Tests (API)**
- `prashna --data-dir <empty> backup restore <archive> --confirm` and
  `python -m prashna.backup restore <archive> --confirm` (with
  `PRASHNA_DB_PATH` / `PRASHNA_UPLOADS_DIR` pointing at an empty folder)
  each exit 0, restore the database and uploads, write no pre-restore
  archive, and print that there was no previous data
  (`test_uc_x_10_restore_into_an_empty_data_folder`).
- `backup create` with no database, and `backup restore` without
  `--confirm`, each exit 1 with a `Backup failed:` / `Restore failed:`
  line and no `Traceback`, in both forms
  (`test_uc_x_10_backup_errors_are_plain_messages`).
- Creating and restoring an archive closes every SQLite connection it
  opened (`test_uc_x_10_backup_closes_its_database_connections`).
- Release-bundle build for `1.2.3` emits `.tar.gz`, `.zip`, and `SHA256SUMS`;
  both Compose and env defaults inside the bundle pin `1.2.3`.
- The release workflow declares amd64+arm64 publication, pulls the just-pushed
  image digest for a Compose smoke, and attaches the versioned bundle to the
  matching GitHub Release.

### UC-X-11: Fast, observable page bootstrap

- **Given** a visitor opens a Prashna HTML surface through a reverse proxy or
  CDN
- **Then** successful HTML shells are browser-revalidated and may be retained
  at the shared edge for five minutes, while API responses, redirects, and
  errors remain non-cacheable
- **And** the landing join/login shell is useful before the authentication
  status request completes
- **And** participant, moderator, and projector initial state is delivered by
  one role-specific bootstrap request rather than multiple sequential request
  waves
- **And** each page records a `prashna-usable` Performance mark when its useful
  surface is ready
- **And** a live update that refetches part of the participant page while
  its bootstrap request is in flight wins: the older bootstrap response
  does not overwrite that part
- **And** a non-blocking, rate-limited performance beacon logs only bounded
  timing, role, negotiated protocol, navigation type, and Cloudflare colo
  fields; it never logs a session code, URL, cookie, token, or client IP.

**Tests (API)**
- Successful `/`, `/quizzes`, `/s/{code}`, `/m/{code}`, and `/p/{code}` page
  responses carry browser-revalidation plus five-minute CDN cache directives;
  an invalid session redirect is `no-store`, and `/api/*` remains `no-store`.
- `POST /api/diagnostics/performance` accepts a bounded valid payload with
  `204`, emits `performance.usable`, derives only the colo suffix from
  `CF-Ray`, and ignores invalid or rate-limited samples without exposing input
  secrets.
- Participant, moderator, and display bootstrap contracts are covered by
  UC-P-01, UC-M-01, and UC-D-01.

**Tests (UI / Ops)**
- The landing shell remains visible while `/api/admin/status` is artificially
  delayed.
- Participant, moderator, and projector boots use their single bootstrap
  endpoints and create `performance.getEntriesByName("prashna-usable")`.
- With the participant bootstrap response held back, a question asked
  meanwhile appears through the live update and is still listed after the
  held, older bootstrap response arrives
  (`test_uc_x_11_live_update_during_bootstrap_is_kept`).
- `performance/measure.py` records `usable_ms`, fails an otherwise successful
  navigation that never reaches the usable mark, and retains the existing
  network/application metrics.
- The Cloudflare cache rule is scoped only to `prashna.sankara.net` HTML page
  routes and respects the origin cache directives; `/api/`, `/ws/`, and
  `/uploads/` are never matched.

### UC-X-12: Phone-width layout

Most participants use phones, and admins and moderators sometimes do.
Every surface works at a 390 px wide viewport.

- **Given** a viewport 390 px or 360 px wide, with or without touch input
- **Then** every page follows the phone and touch rules in
  [UX.md §16a](UX.md#16a-phones-and-touch); the sweep below checks the
  measurable ones

**Tests (UI)** — one sweep (`tests/ui/test_layout.py`) seeds a live
session (questions, a live and a queued run), a not-started session, and
an ended session with a closed run, then visits every page: `/` signed
out and signed in, `/quizzes` (list, editor open, run results open),
`/m/<code>` (live, not started, ended), `/s/<code>` (live, ended), and
`/p/<code>`. At 1280×800, 390×844, and 360×740 it fails on:
- `document.documentElement.scrollWidth` greater than the viewport width;
- any page error or console error;
- a visible control without an accessible name (label, `aria-label`, `title`, or text);
- at 390 and 360 px: a visible text input, text area, or select under 16 px;
- at 1280 px: a visible button (other than answer options, rating stars, and vote buttons) whose height is not 40, 32, or 24 px (UC-X-13), or a `.profile-cta` that isn't 40 px;
- at 390 px on `/` signed in and on `/quizzes` (flat and grouped quiz runs): a `.table-scroll` box wider inside than its own width, or a session-list or quiz-run row whose actions or counts fall outside the viewport (`test_uc_x_12_admin_lists_stack_on_phones`, which also checks that counts read with their words, e.g. "2 questions");
- in a touch-emulating context at 390 px: a visible `button`, `details.menu > summary`, `.section-links a`, `.breadcrumbs a`, `header.top a`, table row action link (`.ctable td.actions a`), or menu link (`a.menu-link`) under 32 px tall. Links inside a sentence are exempt, as in WCAG 2.2.

### UC-X-13: One button size scale

- **Given** any page at desktop width
- **Then** buttons and custom call-to-action elements use the three-size
  scale in [UX.md §10](UX.md#10-buttons), and all of a card's own actions
  use one size

**Tests (UI)**
- At 1280×800 on `/s/<code>` with rating open, `.profile-cta`, `#fb-submit`, and `#ask-btn` have the same height (within 1 px), 40 px, and a 14 px font.
- At 1280×800 on `/` signed out, `#join-btn` and `#li-btn` have that same height and font size.

### UC-X-14: One answer-option component

The participant page, the session page, the projector, and the quiz-run
report (UC-A-24) draw answer options with one shared renderer (`answerOption()` in `common.ts`,
[UX.md §4](UX.md#answer-options)), so a fix or style change reaches all
three. Surfaces differ only in what
they pass: whether the viewer can pick, whether counts show, and whether
correctness is revealed.

- **Given** a revealed question on all three surfaces
- **Then** the correct answer shows "✓ Correct" as text (not only a green
  border), and counts read "<n> (<p>%)" with a proportional bar
- **And** only the participant page's options are buttons; a chosen
  answer there shows a ✓ and "Selected" / "Your answer", or after
  reveal, when wrong, a ✗ and "Your answer · wrong" (UC-P-08)

**Tests (UI)**
- After reveal, `/s/<code>` (participant), `/m/<code>` (session page), and `/p/<code>` (projector) each show exactly one `.option.correct` containing `.opt-correct` with text "✓ Correct", and every `.opt-pct` matches `^\d+ \(\d+%\)$`.

**Tests (static)**
- `frontend/src/participant.ts`, `moderator.ts`, `projector.ts`, and `quizzes.ts` don't build `.option` elements themselves; they call `answerOption()`.

### UC-X-15: Install and run with one command

A presenter with no Docker and no Python setup gets Prashna running with
one command, on macOS, Linux, or Windows.

- **Given** a machine with a shell and internet access
- **When** the presenter runs one of
  - `uvx prashna` (if `uv` is installed)
  - `curl -LsSf https://kvsankar.github.io/prashna/install.sh | sh` (macOS, Linux)
  - `powershell -ExecutionPolicy ByPass -c "irm https://kvsankar.github.io/prashna/install.ps1 | iex"` (Windows)
  - `pipx install prashna`, or `pip install prashna` inside a virtual
    environment (any machine with Python 3.11 or newer, no `uv` needed)
- **Then** the install scripts install `uv` if it is missing (Astral's
  installer), then run `uv tool install --upgrade prashna`, and print how
  to start it; if `uv` still cannot be found after that step, they stop with
  status 1 and a message pointing to `https://docs.astral.sh/uv/` instead of
  continuing
- **When** the presenter runs `prashna`
- **Then** it serves on `http://127.0.0.1:8000`, keeps its database,
  uploads, `secret-key` and `setup-token` in the per-user app-data folder
  (`~/.local/share/prashna`, `~/Library/Application Support/prashna`,
  `%LOCALAPPDATA%\prashna`) — also when run from a source checkout, so
  runtime data and secrets never land in a repository unless
  `--data-dir` or `PRASHNA_DB_PATH` puts them there —
  prints the address and the data folder, and opens the browser — on the
  one-time setup page (`/#setup=<token>`, UC-A-01) while no admin exists,
  otherwise on `/`
- **And** the terminal shows only those lines, the setup link at most once
  (as a full URL with `--no-browser`), and how to stop; the server's
  diagnostic records go to `prashna.log` in the data folder instead of the
  terminal. Warnings and errors still reach the terminal
- **And** the terminal says which data it uses. A database that did not
  exist yet is reported as `Created a new database: <path>`. An existing
  one is reported as `Using existing data: <path>` with a summary of what
  it holds (admins by name, number of sessions and quizzes, or "no admin
  yet"), so a presenter knows when an earlier or seeded data folder is in
  use
- **And** once an admin exists, the terminal says where to sign in:
  `Sign in at <address>/ as <name>.` when there is exactly one password
  admin, otherwise `Sign in at <address>/ with your admin account.`
- **And** `--port`, `--host`, `--data-dir` (or `PRASHNA_DATA_DIR`), and
  `--no-browser` change those defaults; a port already in use exits with
  status 1 and suggests `--port`
- **And** `prashna --tunnel cloudflare` or `prashna --tunnel ngrok` makes
  the server reachable from the internet with nothing else to set: it
  starts a Cloudflare quick tunnel (`cloudflared tunnel --url …`, no
  account) or an ngrok tunnel (`ngrok http …`, the user's signed-in ngrok)
  to the local port, reads the tunnel's public `https://` address, makes it
  the default address for participant links, QR codes, and the copied
  moderator URL in every session (UC-A-06), and prints `Participants join
  at: <address>`. Rate limits (UC-X-08) still apply per visitor, not to
  the tunnel as a whole: uvicorn takes the visitor's address from the
  tunnel's `X-Forwarded-For`, which it trusts from the local machine. The
  presenter keeps using the local address. Stopping Prashna stops the
  tunnel; if the tunnel stops on its own, the terminal says participants
  can no longer reach the server
- **And** if the tunnel program is not installed, or prints no address
  within 45 seconds, `prashna --tunnel …` exits with status 1, showing the
  install command or the tunnel's last output lines
- **And** a Cloudflare quick-tunnel hostname appears in DNS about 15 s after
  `cloudflared` prints it; a lookup before then gets a "no such name"
  answer that resolvers cache, so the address would fail for a while.
  Prashna therefore prints the address only once the name resolves in
  public DNS, checked over DNS over HTTPS (`cloudflare-dns.com`) so the
  local resolver is never asked early. It waits at most 60 s
  (`PRASHNA_TUNNEL_DNS_WAIT_SECS`), then prints the address with a note
  that it may need a little longer
- **And** behind a reverse proxy on the same machine (nginx proxying to
  `127.0.0.1`), the forwarded scheme is honoured: uvicorn trusts
  `X-Forwarded-*` from `127.0.0.1` by default, so sign-in cookies are
  marked `Secure` when visitors use HTTPS; no extra option is needed
- **And** `prashna backup create|restore …` runs the backup tool
  (UC-X-10) against the same data folder; `prashna --version` prints the
  version
- **And** each version tag publishes the two scripts and a one-page
  landing page to GitHub Pages (`https://kvsankar.github.io/prashna/`),
  built by `scripts/build_pages_site.py`, after the PyPI package of that
  version is published, so the hosted script never points at a package
  that does not exist yet
- **And** every Prashna server also serves the scripts at `/install.sh`
  and `/install.ps1` (`text/plain`), so a self-hosted server can offer them
- **And** the wheel published to PyPI as `prashna` contains the built
  frontend, so the installed command needs no Node or build step

**Reset a forgotten password.** `prashna reset-password` sets a new password
for the admin. It works only on the machine that holds the data folder
(`--data-dir`, before or after the subcommand, as for `prashna`). Two
independent facets decide what happens.

The state of the data folder decides whether a reset can happen:

| Data folder | Result |
| --- | --- |
| No database | Exits 1: `No Prashna database in <folder>.` |
| Database, no admin yet | Exits 1: start `prashna` and use the setup link |
| Database with the admin | Asks for the new password (next table) |

The new password, entered twice, decides whether it succeeds:

| Entries | Result |
| --- | --- |
| Match, at least 8 characters | Saved; prints `Password changed for <name>.`; exits 0 |
| Differ | Exits 1; nothing changes |
| Shorter than 8 characters | Exits 1; nothing changes |
| Longer than 72 bytes | Exits 1 with `The password must be at most 72 bytes. Nothing changed.`; no traceback |

Where the command runs does not change these results. In a terminal it
asks twice without echoing; otherwise it reads two lines from standard
input. While Prashna is running, the new password works at once. Devices
already signed in stay signed in. In the container image, which runs the
code without installing the command, it is
`docker compose exec prashna python -m prashna reset-password`.

**Tests (API)**
- `GET /install.sh` → `200 text/plain` containing `uv tool install --upgrade prashna` and Astral's installer URL; `GET /install.ps1` likewise for PowerShell.
- `install.sh` run where `uv` is absent and its download fails exits 1 with a message naming `https://docs.astral.sh/uv/`, and never runs `uv tool install`.
- On a fresh data folder the CLI's terminal output contains no `diagnostic_event` line and the setup link at most once (exactly once with `--no-browser`); `prashna.log` in the data folder holds the diagnostic records.
- Applying the additive migration bridge to an up-to-date database logs no `db.migration` record.
- `prashna.db.default_data_dir()` returns the per-platform folder, also inside a source checkout (`XDG_DATA_HOME` honoured on Linux, `LOCALAPPDATA` on Windows), and never a folder inside the repository.
- The CLI resolves the data folder from `--data-dir`, then `PRASHNA_DATA_DIR`, then the default, and sets `PRASHNA_DB_PATH` / `PRASHNA_UPLOADS_DIR` inside it.
- On a fresh data folder the CLI opens the browser at `http://127.0.0.1:<port>/#setup=<token>` with the token the server will accept; once an admin exists it opens `/`; `--no-browser` opens nothing.
- With the port already bound, `prashna --port <it>` exits 1 and prints a message naming `--port`.
- A request from `127.0.0.1` carrying `X-Forwarded-Proto: https` gets a `Secure` session cookie; the same request without the header doesn't.
- `prashna backup create <file>` writes an archive of that data folder.
- `prashna --version` prints the installed version.
- `prashna reset-password` with two matching lines on standard input exits 0 and prints `Password changed for me.`; afterwards the new password signs in and the old one gets `401`. Mismatched entries, a password under 8 characters, a database with no admin, and a folder without a database each exit 1 with their message and change nothing (`test_uc_x_15_reset_password`).
- `prashna reset-password` with an 80-byte password exits 1, prints `The password must be at most 72 bytes. Nothing changed.`, prints no traceback, and the old password still signs in (`test_uc_x_15_reset_password_over_72_bytes`).
- A first run prints `Created a new database: <data>/prashna.db`; a later run against the same folder prints `Using existing data: <data>/prashna.db` with `1 admin (me)` and the session and quiz counts, and `Sign in at http://127.0.0.1:<port>/ as me.` (`test_uc_x_15_reports_new_or_existing_data_and_where_to_sign_in`).
- With a stub `cloudflared` (and, separately, a stub `ngrok`) on `PATH` that prints a known address, `prashna --tunnel …` prints `Participants join at: <address>`, sessions report it as `default_base_url`, and stopping Prashna stops the stub (`test_uc_x_15_tunnel_wires_the_public_address`).
- Through that tunnel, a visitor who exhausts the login rate limit (`X-Forwarded-For: <visitor A>`) gets `429` while another visitor (`<visitor B>`) still gets `401` for a wrong password (`test_uc_x_15_tunnel_rate_limits_each_visitor`).
- Without the tunnel program on `PATH`, `prashna --tunnel cloudflare` exits 1 and names `cloudflared` and how to install it; a stub that exits without an address makes it exit 1 showing the stub's output (`test_uc_x_15_tunnel_reports_missing_or_failed_programs`).
- `prashna.tunnel.wait_until_resolvable` returns once a DNS-over-HTTPS answer lists an address, returns `False` after its timeout, and returns at once for a timeout of 0 (`test_uc_x_15_tunnel_waits_for_public_dns`).
- Opt-in: `PRASHNA_CLOUDFLARE_SMOKE=1 uv run pytest tests/ops/test_cloudflare_smoke.py` runs `prashna --tunnel cloudflare` with the real `cloudflared` and checks the health API, a participant page, and a WebSocket ping through the public address, querying it only after Prashna prints it.

**Tests (packaging, CI)**
- `uv build --wheel` produces a wheel that contains `prashna/static/index.html`, the install scripts, and a `prashna` console-script entry point, and no top-level `app` package; its metadata declares `License-Expression: MIT`, includes `LICENSE`, and links Homepage to `https://kvsankar.github.io/prashna/` and Source to the GitHub repository.
- `scripts/build_pages_site.py <dir>` writes `install.sh` and `install.ps1` byte-for-byte equal to `prashna/installers/`, and an `index.html` showing both one-liners with the `kvsankar.github.io/prashna` URLs and the pipx and virtual-environment commands; README.md shows the same commands.
- The CI workflow has a `pages` job that runs only on `v*` tags, needs the PyPI job, builds the site with that script, and deploys it with `actions/upload-pages-artifact` and `actions/deploy-pages` under the `github-pages` environment with `pages: write` and `id-token: write`.

---

## Quality targets

| Target | Value | How it is checked |
| --- | --- | --- |
| Room size | 100 participants in one live room on the single-process deployment | No automated load test (see `todo.md`) |
| Interaction latency | Participant, moderator, admin, and projector interactions complete within 1000 ms at the 95th percentile with 100 participants in the room | No automated test. `performance/measure.py` measures page loads against `performance/budgets.json` (`performance/README.md`) |
| Reconnect recovery | A page refetches its state within 5 s after its WebSocket reconnects | `test_uc_d_05_reconnect_refetches_after_close` (UC-D-05) |
| Persistence | The database and uploads survive a container restart | `tests/ops/test_compose_smoke.py` (opt-in locally, run in CI) |
| Test-suite time | `uv run pytest` completes within 180 s on a development workstation | Not enforced |

## End-to-end journeys

These journeys chain use cases in the order a real session uses them. No
single automated test runs a whole journey; each step is covered by its
use case's tests.

- **Live room.** First-run setup (UC-A-01) → create a session (UC-A-03) →
  start it (UC-M-02) → a delegate opens the moderator link (UC-M-01) →
  participants join, submit profiles, ask, and vote (UC-P-01 to UC-P-05) →
  the moderator responds (UC-M-08) → the moderator queues, starts, walks
  through, reveals, and closes a quiz (UC-M-03 to UC-M-06) while
  participants answer (UC-P-07 to UC-P-09) and the projector follows
  (UC-D-01, UC-D-06) → the moderator opens rating and participants rate
  the session (UC-M-12, UC-P-13) → the moderator ends the session
  (UC-M-02). Final check: the ended session's Q&A, quiz results, projector
  view, and feedback summary agree.
- **Quiz history.** Author a quiz with an image (UC-A-09 to UC-A-20) →
  publish it (UC-A-21) → run it in a session with submissions and reveals
  (UC-M-03 to UC-M-06, UC-P-08) → edit the template → the run's report
  (UC-A-24) still shows the launched content (UC-X-06).
- **Release.** Configure an instance (UC-X-07, UC-X-08) → run the checks →
  start against an old-shape database (additive migration bridge) → deploy
  the container (UC-X-10) → create the first admin and sign in (UC-A-01,
  UC-A-02) → live pages receive broadcasts and recover after a reconnect
  (UC-X-01, UC-D-05). `tests/ops/test_compose_smoke.py` covers setup,
  upload, restart, and persistence for this journey.

---

## Deferred (decision needed)

Items that came up during design but were deliberately not specced as
use cases because they need a product call before they have shape.

- **Reopen an ended session** — no backend support; UI has no
  affordance. Today `ended` is one-way. Likely a real product need
  once sessions are recurring.
- **Reopen a closed QuizRun** — no backend support. Today `closed`
  is one-way; mods who close by mistake must delete and re-launch
  (losing submissions).
- **Per-question timer / auto-advance** — no schema, no UI. Adds
  scoring-pressure semantics; common in Kahoot-style products.
- **Hard-delete query UI** — the `DELETE /api/sessions/{c}/queries/{qid}`
  route exists for admin escapes but has no standard UI affordance.
- **Logout from `/quizzes`, `/m`, `/p`** — currently only on the
  landing page.
- **Image upload content-sniff** — today only the extension is
  validated; SVG is excluded by extension allowlist. A malformed
  file with a legit extension is accepted. Cheap to add
  (Pillow `verify`).
- **`image_url` server-side validation** — admin can set any URL on
  an item or option via PATCH. Limiting to `/uploads/<uuid>.<ext>`
  would harden against external-URL injection.
- **Multi-moderator audit columns** — who responded/removed/started/
  closed. Useful once delegate moderators are real.
- **CHECK constraints** on status enums (`session.status`,
  `quiz.status`, `quizrun.status`, `quiz_question.qtype`).
- **Image-only answers** — render correctly today, but publish
  validation accepts them; results UI shows blank cells if no text.
Each becomes its own UC when the product decision lands; the route /
column / verb names can stay stable until then.
