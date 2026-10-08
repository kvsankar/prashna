# Prashna — specs

Use cases and acceptance tests for the five surfaces of the system.
Each use case has a stable ID (`UC-<ROLE>-NN`) so tests, PRs, and bug
reports can cite it. Acceptance tests are Given/When/Then.

**Roles** (and their UC prefixes)
- **Admin** (`UC-A-*`) — a logged-in `User` (today: single global
  admin per deployment). Owns sessions and quiz templates.
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
- **Projector / Display** (`UC-D-*`) — the big-screen view at the
  front of the room (`/p/<code>`). Public, read-only, no chrome,
  updates live via WebSocket.
- **System** (`UC-X-*`) — cross-cutting backend invariants, broadcast
  contracts, security headers, and storage-level constraints. Not a
  user action; the substrate every other UC silently depends on.

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

---

## Admin

### UC-A-01: First-run admin setup

A fresh deployment has no admin. The landing page surfaces a one-time
setup form for the first visitor to claim admin.

- **Given** no user rows exist
- **When** the visitor submits a username and a password of ≥ 8 chars
  via `POST /api/admin/setup`
- **Then** the user is created, an `admin_session` cookie is issued,
  and `/api/admin/status` reports `{initialized: true, authenticated:
  true}`
- **And** any subsequent `POST /api/admin/setup` returns `409 Admin
  already initialized`
- **And** passwords shorter than 8 chars return `400` with a length
  message

**Tests (API)**
- `GET /api/admin/status` on a fresh DB → `200 {initialized: false, authenticated: false, username: null, github_enabled: false}` (`github_enabled` reflects whether GitHub OAuth is configured — see UC-A-26). Auth: none.
- `POST /api/admin/setup` with `{"username": "alice", "password": "longenough"}` → `200 {username: "alice"}` and sets `admin_session` cookie. Auth: none.
- `GET /api/admin/status` immediately after setup (with cookie) → `200 {initialized: true, authenticated: true, username: "alice"}`.
- `POST /api/admin/setup` a second time → `409 "Admin already initialized"`.
- Race: two concurrent setup calls with **different usernames** — exactly one returns `200`, the other returns `409`. Serialized by a process-wide `threading.Lock` around the check+insert (Prashna is single-process per CLAUDE.md, so this is a real invariant). Test: `test_uc_a_01_concurrent_setup_different_usernames`.
- Same-username conflict path is also caught via `try/except IntegrityError` and surfaces as `409`.
- `POST /api/admin/setup` with `{"username": "alice", "password": "short"}` → `400 "password must be at least 8 characters"`.
- `POST /api/admin/setup` with `{"username": "", "password": "longenough"}` → `400 "username required"`.

**Tests (UI)**
- On `/` with no admin, `#setup-card` is visible; `#login-card` and `#sessions-card` are hidden.
- Filling `#su-user`, `#su-pass`, `#su-pass2` (matching) and clicking `#su-btn` swaps the page to the authed view (`#sessions-card` visible).
- Mismatched `#su-pass`/`#su-pass2` shows an error toast without an API call.
- A password shorter than 8 chars surfaces a `400` toast and leaves `#setup-card` visible.

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
- `POST /api/admin/login` with valid `{username, password}` → `200 {username}` and sets `admin_session` cookie. Auth: none.
- `POST /api/admin/login` with wrong password → `401 "Invalid username or password"`.
- `POST /api/admin/login` with unknown username → `401 "Invalid username or password"`.
- `POST /api/admin/logout` → `200 {ok: true}` and clears the `admin_session` cookie.
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
- **And** the new row appears in the list with a `Planning` badge

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
- Empty title shows an error toast "Session title is required" and the input keeps focus.
- The new row appears at the top of `#session-rows`.

### UC-A-04: See my sessions

- **Given** the admin owns sessions
- **When** they `GET /api/sessions`
- **Then** they see only sessions where `owner_user_id = me.id`,
  ordered by `created_at desc`, with status, query count, quiz-run
  count, mod_key, and participant_base_url

**Tests (API)**
- `GET /api/sessions` → `200 [{code, title, status, mod_key, participant_base_url, created_at, started_at, ended_at, query_count, quiz_run_count}, ...]`. Auth: admin cookie.
- Rows include only sessions where `owner_user_id = me.id` (a second admin's session is not returned).
- Order is `created_at desc` — the most recently created session appears first.
- `GET /api/sessions` with no admin cookie → `401`.

**Tests (UI)**
- On `/` (authed), `#session-rows` lists each owned session with title, status badge, query count, and quiz-run count.
- Most-recently-created session appears at the top.
- Authenticated admin chrome shows `#admin-page-nav` with an Admin breadcrumb and links to Sessions and Quiz library.
- Clicking a row in `#session-rows` opens the session page `/m/<code>` (UC-A-08). Each row's title is a link to the same URL; the Actions column keeps Participant, Projector, and Delete.
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
  `null` and the frontend falls back to `location.origin`

**Tests (API)**
- `POST /api/sessions/{code}/participant_base_url` with `{"url": "https://example.com/"}` → `200 {participant_base_url: "https://example.com"}` (trailing slash stripped). Auth: **admin cookie only** (owner-only).
- `POST /api/sessions/{code}/participant_base_url` with `{"url": "ftp://x"}` → `400 "URL must start with http:// or https://"`.
- `POST /api/sessions/{code}/participant_base_url` with `{"url": "http://" + "a"*600}` → `400 "URL is too long"`.
- `POST /api/sessions/{code}/participant_base_url` with `{"url": ""}` → `200 {participant_base_url: null}`.
- `POST /api/sessions/{code}/participant_base_url` with no auth → `401`.
- With a valid `mod_key` but no admin cookie → `401`.
- After success, broadcasts `{type: "session_state"}`.

**Tests (UI)**
- On `/m/<code>` as the admin owner, typing into `#base-url` and blurring updates `#invite-url` text and re-renders `#invite-qr`.
- Clicking `#base-url-clear` clears `#base-url`, and the page falls back to `location.origin` for the QR/URL widgets.
- Entering an invalid URL (no `http(s)://`) shows an error toast.

### UC-A-07: Delete a session

- **Given** the admin clicks Delete on a session row, or **Delete
  session…** in the session page's Session settings card (which opens
  `/?delete=<code>` and runs the same flow on the list)
- **When** the session is `live` → the action is refused with
  "End the session before deleting it" (toast)
- **And** the session has 0 queries and 0 quiz runs → a native
  `confirm()` followed by `DELETE` deletes it
- **And** the session has data → a confirm card opens below the table
  warning what will be lost (counts), with a typed-title input that
  must match `session.title` exactly to enable the Delete button
- **Then** on success, the session is removed; cascade-deletes its
  queries, votes, participants, quiz_runs, and submissions.
  QuizVersions are NOT touched (they belong to Quiz templates).

**Tests (API)**
- `DELETE /api/sessions/{code}` on a `planning` session with 0 queries/quiz_runs (no body) → `200 {ok: true}`. Auth: admin cookie.
- `DELETE /api/sessions/{code}` on a `live` session → `400 "End the session before deleting it"`.
- `DELETE /api/sessions/{code}` on a session with queries/quiz_runs but missing `confirm_title` → `400 "Type the session title exactly to confirm deletion"`.
- `DELETE /api/sessions/{code}` with `{"confirm_title": "Wrong"}` → `400 "Type the session title exactly to confirm deletion"`.
- `DELETE /api/sessions/{code}` with `{"confirm_title": <exact title>}` → `200 {ok: true}`; cascade removes Queries, QueryVotes, Participants, QuizRuns, QuizSubmissions; QuizVersions for the underlying Quiz remain.
- `DELETE /api/sessions/{code}` by a non-owner admin → `403 "Not your session"`.
- `DELETE /api/sessions/{code}` with no auth → `401`.

**Tests (UI)**
- On `/`, clicking Delete on a `live` row shows toast "End the session before deleting it" and no row is removed.
- Clicking Delete on a `planning` row with no data fires a native `confirm()`; accepting removes the row from `#session-rows`.
- Clicking Delete on a row with data opens `#confirm-delete-card` below the table with the warning text in `#cd-warn`.
- `#cd-go` is disabled until `#cd-confirm` exactly matches `session.title`.
- Typing the exact title enables `#cd-go`; clicking it removes the row.
- `#cd-cancel` closes the confirm card without deleting.
- On `/m/<code>` as the admin owner, clicking `#set-delete` on an empty `planning` session opens `/?delete=<code>`, fires the native `confirm()`, and, once accepted, the row is gone from `#session-rows`.

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
- **And** the owner sees the Base URL field in the Invite card (UC-A-06)
- **And** a delegate (mod_key, no admin cookie) sees neither the
  Session settings card nor the Base URL field
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
- Opening `/m/<code>#k=<mod_key>` as a delegate (no admin cookie) hides `#settings-card`.
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

### UC-A-10: Browse the quiz library

- **Given** the admin is on `/quizzes`
- **When** `GET /api/quizzes` (optionally `?ready_only=true`) is called
- **Then** the response includes only quizzes owned by the admin,
  ordered by `created_at desc`, with `status` and `question_count`
- **And** moderator dropdowns use `ready_only=true`; the quiz library
  table uses the full list

**Tests (API)**
- `GET /api/quizzes` → `200 [{id, title, status, question_count, sessions}, ...]` ordered `created_at desc`. Auth: admin cookie.
- `sessions` lists each session that holds a run of the quiz: `{code, title, session_status, run_status, run_count}`, where `run_status` is the most relevant state of its runs there (`live` over `queued` over `closed`). A quiz never run has `sessions: []`. The same server function produces `in_session` for UC-M-03, so the library and the session page always agree.
- A quiz owned by another admin is not in the response.
- `GET /api/quizzes?ready_only=true` returns only quizzes with `status: "ready"`.
- `GET /api/quizzes` with no auth → `401`.

**Tests (UI)**
- On `/quizzes` (authed), `#quiz-rows` contains a row per owned quiz with title, status badge, and question count.
- Order: most recently created first.

### UC-A-11: Open a quiz for editing

- **Given** the admin clicks a row in the library
- **When** `GET /api/quizzes/{id}?include_correct=true` is called
- **Then** the editor pane shows the title, questions, answers, and
  per-answer correctness
- **And** the route returns `404` for a non-owner (no read access
  across owners)

**Tests (API)**
- `GET /api/quizzes/{id}?include_correct=true` → `200 {id, title, status, questions: [{id, text, image_url, qtype, order_index, answers: [{id, text, image_url, order_index, is_correct}]}]}`. Auth: admin cookie.
- `include_correct=false` (default) omits `is_correct` from answer objects.
- `GET /api/quizzes/{id}` for a quiz owned by another admin → `404`.
- `GET /api/quizzes/{id}` for a non-existent id → `404`.
- `GET /api/quizzes/{id}` with no auth → `404`.

The editor card sits directly below the quiz list and scrolls into view
when it opens, so on a phone the editor appears where the admin is
looking. Every editor control has an accessible name ("Question 1 text",
"Question 1 type", "Answer 1 text", "Answer 1 is correct"), and images
are added with an **Add image** button rather than a bare file input.

**Tests (UI)**
- On `/quizzes`, clicking a row in `#quiz-rows` opens `#editor-card`, populates `#editor-title`, and `#editor-body` lists each question with its answers and a correctness marker per answer.
- `#editor-card` immediately follows `#quiz-library-card` in the page and is in the viewport after opening, at desktop and phone widths.
- The first question's text box is reachable by role as "Question 1 text", its first answer as "Answer 1 text", and that answer's checkbox as "Answer 1 is correct".

### UC-A-12: Rename a quiz

- **Given** the editor is open
- **When** the admin edits the title input and blurs
- **Then** `PATCH /api/quizzes/{id}` updates the title and advances
  `last_edited_at`
- **And** an empty title is silently ignored (existing title kept)
- **And** status does **not** auto-revert from `ready` → `draft`
  (versioning protects history)

**Tests (API)**
- `PATCH /api/quizzes/{id}` with `{"title": "New"}` (different from current) → `200 {ok: true, status}`; updates `title` and advances `last_edited_at`. Auth: admin cookie.
- `PATCH /api/quizzes/{id}` with `{"title": ""}` → `200`; title stays unchanged AND `last_edited_at` does NOT advance (the no-op branch skips `_mark_quiz_edited`).
- `PATCH /api/quizzes/{id}` with `{"title": "<same as current>"}` → `200`; same no-op behavior (no change, no edit bump).
- After PATCH on a `ready` quiz, `GET /api/quizzes/{id}` still returns `status: "ready"`.
- `PATCH /api/quizzes/{id}` for a non-owner quiz → `404`.

**Tests (UI)**
- In `#editor-card`, editing the title input and blurring updates the row's title in `#quiz-rows`.

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

- **Given** the admin clicks **+ Add question** in the editor
- **When** `POST /api/quizzes/{id}/questions` is called
- **Then** a `Question` is added at the end (`order_index = max + 1`);
  parent's `last_edited_at` advances
- **And** a `qtype` not in `("single", "multi")` returns `400`
- **And** `graded` (default `true`) marks whether the question has a
  correct answer; `graded: false` is a **poll/survey** question (options
  but no correct answer — e.g. age / experience range)

**Tests (API)**
- `POST /api/quizzes/{id}/questions` with `{}` → `200 {id}`; new Question appended with `order_index = max+1`, `text = ""` (empty), `qtype = "single"`, `graded = true`, parent `last_edited_at` advances. Auth: admin cookie. Note: the **backend** defaults `text` to empty string; the UI passes `{"text": "New question"}` so users see a sensible placeholder, but that string is a frontend choice.
- `POST /api/quizzes/{id}/questions` with `{"text": "X", "qtype": "multi"}` → `200`; created with `text: "X"`, `qtype: "multi"`.
- `POST /api/quizzes/{id}/questions` with `{"graded": false}` → `200`; created as a poll question (`graded: false`), surfaced by `GET /api/quizzes/{id}`.
- `POST /api/quizzes/{id}/questions` with `{"qtype": "bogus"}` → `400 "qtype must be single or multi"`.
- For a non-owner quiz → `404`.

**Tests (UI)**
- In `#editor-body`, clicking `+ Add question` appends a new question row. The frontend submits `{"text": "New question", "qtype": "single"}`, so the new row's text input shows "New question" as the editable starting value.
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

**Tests (API)**
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
- `.svg` → `400 "unsupported image type"`.
- `.exe` or no extension → `400 "unsupported image type"`.
- 6 MB file (Content-Length header set) → `400 "max 5MB"`.
- 6 MB streamed payload (no Content-Length) → `400 "max 5MB"`.
- `POST /api/uploads` with no auth → `401`.
- In the editor, each question and answer offers an **Add image** button (**Change image** once set) that opens the hidden file input.

**Tests (UI)**
- In `#editor-body`, picking an image file via the question's file input uploads, then PATCHes the question with the new `image_url`, then re-renders the thumbnail.
- Same flow under each answer row updates its thumbnail.

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
- **And** on fail, returns `400` with the specific failing rule
  message ("Question 2 (single choice) needs exactly one correct answer")

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

**Tests (UI)**
- In `#editor-card`, clicking Publish on a valid draft quiz flips its status badge in `#quiz-rows` to `.badge-ready`.
- Clicking Publish on an invalid quiz surfaces an error toast with the exact failing-rule message and status stays `draft`.

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
- In `#editor-card`, clicking Unpublish flips status badge in `#quiz-rows` from `.badge-ready` to `.badge-draft`.

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
- **And** a session that already holds a run of this quiz (from the
  quiz's `sessions`, UC-A-10) says so on its menu item ("Already added ·
  Queued", "· Live", or "· Closed", the shared status labels). Clicking it asks for confirmation
  before adding another run (repeating a quiz is allowed but usually a
  mistake); declining adds nothing

**Tests (UI)**
- On `/quizzes`, opening a ready quiz row's Add to session menu lists a `planning` session and a `live` session (live first) but not an `ended` one; clicking the planning session toasts its title, and `GET /api/sessions/{code}/quiz_runs` returns one queued run.
- Doing the same for a valid draft quiz flips the row's badge to Ready and queues a run.
- Doing the same for an invalid draft (no questions) shows an error toast; the badge stays Draft and no run is queued.
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
- On `/quizzes`, `#qs-rows` shows one row per QuizRun across owned sessions, with quiz title, version, session code, status badge, progress, and respondents.
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
- Renaming the source Quiz after the run does NOT change `quiz_title` in this response (snapshotted).
- For a run on another admin's session → `404`.

**Tests (UI)**
- On `/quizzes`, clicking a row in `#qs-rows` opens `#results-card`; `#results-body` shows per-question answer counts with correctness markers.
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
- **And** Escape closes the card without saving

**Tests (API)**
- `POST /api/admin/change_password` with valid `{current_password, new_password}` (≥ 8 chars) → `200 {ok: true}`; re-issues `admin_session` cookie; bcrypt-verifies new password. Auth: admin cookie.
- With wrong `current_password` (but valid cookie) → `401 "Current password is incorrect"`.
- With `new_password` shorter than 8 chars → `400 "new password must be at least 8 characters"`.
- With no cookie at all → `401 "Not authenticated"` (from `auth.current_admin`, before the handler runs). Two distinct 401 paths.
- **Old cookies are invalidated**: after a successful change_password call, the prior `admin_session` cookie no longer authenticates. Verified by capturing the pre-change cookie, changing password, then issuing an admin-only call with the captured cookie → `401`. (Implementation: signed cookies carry a `session_version`, bumped on each password change; `current_admin` rejects mismatched versions.)

**Tests (UI)**
- On `/` (authed), clicking Change password opens `#change-pw-card`.
- Submitting `#cp-current`, `#cp-new`, `#cp-new2` (matching) via `#cp-submit` toasts "Password updated" and closes the card.
- Mismatched `#cp-new`/`#cp-new2` shows an error toast and makes no API call.
- Wrong current password shows toast "Current password is incorrect" and the card stays open.
- A new password shorter than 8 chars shows a `400` toast.
- Pressing Escape inside `#change-pw-card` closes it without submitting.
- `#cp-close` closes the card without submitting.

### UC-A-26: GitHub OAuth admin login (allowlist)

An optional sign-in path for hosted deploys (e.g. the Hetzner box).
It runs **alongside** username/password login — password stays as a
fallback. It's enabled only when all of `PRASHNA_GITHUB_CLIENT_ID`,
`PRASHNA_GITHUB_CLIENT_SECRET`, and `PRASHNA_GITHUB_ADMINS`
(comma-separated GitHub logins) are set; otherwise the routes 404 and
the UI shows no button.

- **Given** GitHub login is configured
- **Then** `GET /api/admin/status` reports `github_enabled: true`, and
  the landing page shows a **Sign in with GitHub** button
- **When** the admin clicks it → `GET /api/auth/github/login` redirects
  to GitHub's authorize URL with a signed, short-lived `state` (CSRF)
- **And** GitHub redirects back to `GET /api/auth/github/callback`;
  the server verifies `state`, exchanges the `code`, fetches the
  GitHub `{id, login}`, and:
  - if `login` is in the allowlist (case-insensitive) → **find-or-create**
    the admin `User` keyed by the immutable GitHub `id` (so the first
    allowlisted sign-in bootstraps the admin — no password setup needed
    on the server), issues the normal signed `prashna_admin` session
    cookie, and `303`-redirects to `/`
  - otherwise → `303`-redirects to `/?auth_error=…` with a banner; no
    cookie is issued
- **And** a missing/invalid/expired `state` or a failed token exchange
  → `303` to `/?auth_error=…`, no cookie
- **And** GitHub-created admins have no password (`password_hash=""`),
  so they cannot use the password login; the local password admin (if
  any) is unaffected

**Tests (API)**
- `oauth.enabled()` is `True` only when all three env vars are set; `oauth.is_allowed()` matches the allowlist case-insensitively.
- With GitHub unconfigured: `GET /api/auth/github/login` and `/callback` → `404`; `GET /api/admin/status` → `github_enabled: false`.
- With GitHub configured: `GET /api/admin/status` → `github_enabled: true`; `GET /api/auth/github/login` → `302` to `github.com/login/oauth/authorize` carrying a `state`.
- Callback with a forged/garbage `state` → `303` to `/?auth_error=…`, no `prashna_admin` cookie.
- Callback with valid `state` and an **allowlisted** login (token/user fetch mocked) → `303` to `/`, sets `prashna_admin`; a follow-up `GET /api/admin/status` is `authenticated: true` with `username` = the GitHub login; a `User` row exists with that `github_id`.
- Callback with a **non-allowlisted** login → `303` to `/?auth_error=…`, no cookie, no new `User`.
- Two callbacks for the same GitHub `id` reuse the same `User` (no duplicate row).

**Tests (UI)**
- On `/` with GitHub configured and not authenticated, `#github-login-btn` is visible and links to `/api/auth/github/login`; with GitHub unconfigured it stays hidden.
- Loading `/?auth_error=Nope` surfaces the message as an error toast and strips the query param.

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
  re-prompts with a "Couldn't load — re-enter the moderator key"
  toast

**Tests (API)**
- Any `mod-or-owner` route (e.g., `PATCH /api/sessions/{code}` with `{"title":"x"}`) with valid `X-Mod-Key` header → `200`. Auth: mod-key.
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
- Opening `/m/<code>` with a wrong stored key renders `#modkey-card` with toast "Couldn't load — re-enter the moderator key".
- `#moderator-breadcrumbs` shows Sessions → session title. The Sessions link targets `/`; the session title is the current page. The adjacent section links jump to Lifecycle, Set up, Quiz, Questions, Profiles, and Feedback; jumping to Set up opens the disclosure.

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
- `POST /api/sessions/{code}/end` while any QuizRun in this Session is still `live` → `400 "A quiz run is currently live — close it before ending the session"`. The moderator must explicitly close the run first.
- `POST /api/sessions/{code}/end` while any QuizRun is still `queued` → `400 "Remove queued quizzes before ending the session"`. This prevents an ended Session from retaining an unstartable staged run.
- Each successful state change broadcasts `{type: "session_state"}`.
- With no auth → `403`.

**Tests (UI)**
- On `/m/<code>`, when status is `planning`, `#lifecycle-actions` contains Start session; clicking it flips `#session-status` to `.badge-live`.
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
  also sees Draft quizzes, labelled as drafts. Adding a draft sends
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
- `POST /api/sessions/{code}/quiz_runs` with an unknown quiz_id → `404 "quiz not found"`.
- Quiz owned by another admin → `404 "quiz not found"`.
- `POST /api/sessions/{code}/quiz_runs` on an `ended` session → `400 "Session has ended"`.
- With no auth → `403`.
- Success broadcasts `{type: "quiz_run_new"}`.
- `GET /api/sessions/{code}/available_quizzes` (and the bootstrap's `available_quizzes`) returns Ready quizzes for a delegate, and Ready plus Draft quizzes (with `status`) for the admin owner.
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
  when one of its runs starts

**Tests (API)**
- `POST /api/sessions/{code}/quiz_runs/{id}/start` on a `queued` run → `200 {ok: true}`; sets `status: "live"`, `current_question_idx: 0`, `reveal_current: false`, `started_at`. Auth: mod-key OR admin cookie.
- Starting on a `planning` Session auto-advances it to `live` and sets `started_at`.
- Starting a run while another run on the same Session is already `live` → `409 "Another quiz is already live — close it first."`.
- Starting a run that's not `queued` (e.g., `live`, `closed`) → `400 "Cannot start from status: <status>"`.
- Starting a queued run in an `ended` Session → `400 "Session has ended"`, including legacy queued rows created before this invariant was enforced.
- For a non-existent run id (or wrong session) → `404`.
- With no auth → `403`.
- Success broadcasts `{type: "quiz_run_update"}`.

**Tests (UI)**
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
- **Then** `current_question_idx` advances; `reveal_current` resets
  to false → the next question's answering phase begins.
- **Given** the QuizRun is in results phase and the current question
  **is** the last
- **When** the moderator clicks **Finish quiz →**
- **Then** the run closes (see UC-M-06).
- **Prev** moves `current_question_idx` backwards (mod can revisit a
  question). Any advance call (next / prev / to) resets
  `reveal_current = False` server-side.
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
- `POST /api/sessions/{code}/quiz_runs/{id}/advance` with `{"direction": "next"}` → `200 {ok: true}`; `current_question_idx` increments by 1 (capped at `len-1`); `reveal_current` resets to false.
- `{"direction": "prev"}` → decrements idx (floored at 0); resets `reveal_current`.
- `{"direction": "to", "index": 2}` → sets idx to 2 (clamped to `[0, len-1]`).
- `{"direction": "to", "index": "x"}` → `400 "index must be an integer"`.
- **Source-state guards**: `/advance` and `/reveal` require `run.status == "live"`; calling on a `queued` or `closed` run → `400 "Run is not live"`. `/close` requires `live` too — calling on `queued` → `400`; on `closed` → `400 "Run is already closed"`.
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
- The participant page (in another tab) refreshes via WS and continues to show the last question with results.
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

**Tests (API)**
- `POST /api/sessions/{code}/queries/{qid}/respond` with `{"response_text": "see docs"}` → `200 {ok: true}`; sets `responded_at` and `response_text = "see docs"`. Auth: mod-key OR admin cookie.
- `POST .../respond` with `{}` → marks responded with `response_text: null` (verbal-only).
- `POST .../respond` with `{"responded": false}` → clears `responded_at` (Reopen). Note: the handler always writes `response_text` from the payload — so omitting `response_text` on Reopen also **wipes** any prior text (handler does `q.response_text = (payload.get("response_text") or "").strip() or None`). Tests should assert this side effect.
- `POST .../respond` for a non-existent or cross-session qid → `404`.
- Broadcasts `{type: "query_responded"}`.
- With no auth → `403` (see Conventions).

**Tests (UI)**
- In moderator `#queries`, clicking Mark responded on a query moves it into the answered section.
- Reopen on an answered query moves it back to the unanswered section.

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
- `POST .../vote` on a removed query (as participant) → `404`.
- Broadcasts `{type: "query_removed"}`.
- With no auth → `403`.
- **Hard delete is owner-only**: `DELETE /api/sessions/{code}/queries/{qid}` requires admin cookie. A delegated `mod_key` → `401`. (Soft-remove above remains mod-or-owner.)

**Tests (UI)**
- In moderator `#queries`, clicking Remove on a query marks it visually removed (still visible to moderator) with a Restore action.
- Participant tab refreshes via WS and the query disappears from their list.

### UC-M-10: Live participant count

- **Given** participants are interacting with the session
- **When** the moderator views their header bar (and on each
  WebSocket-driven refresh)
- **Then** the count of participants whose `last_seen_at` falls within
  the last 30 seconds is shown

**Tests (API)**
- `GET /api/sessions/{code}/presence` → `200 {online: <int>}` counting Participants with `last_seen_at >= now-30s`. Auth: none (cookie issued on first call).
- After one participant calls a participant route, `online` returns ≥ 1.
- After waiting > 30s without further requests, `online` decrements back to 0.

**Tests (UI)**
- On `/m/<code>`, `#live-count` shows "N online" and updates after WS-driven refreshes.

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

### UC-M-12: View session feedback

- **Given** a moderator (delegate or admin owner) is on the moderator page
- **Then** a **Feedback** panel (`#feedback-card`) shows the aggregate of
  participant feedback (see UC-P-13): the average rating and response
  count (`#feedback-summary`) plus each response — its stars, optional
  author name, and the "went well" / "could be better" comments
  (`#feedback-list`)
- **And** the panel refreshes live via the `feedback` WS broadcast
- **And** the same aggregate is shown in the admin session-detail card
  (`#sd-feedback`) when the owner drills into a session on `/`
- **Backend route**: `GET /api/sessions/{code}/feedback/summary`
  (mod-or-owner auth) → `{count, average, distribution: {1..5}, items:
  [{rating, went_well, to_improve, author_name, updated_at}, ...]}`.

**Tests (API)**
- `GET /api/sessions/{code}/feedback/summary` with two participants'
  ratings (5 and 3) → `200 {count: 2, average: 4.0, distribution: {"5":1,
  "3":1, ...}, items: [...]}`. Auth: mod-key OR admin cookie.
- A named participant's item carries `author_name`.
- With no auth (no admin cookie, no mod-key) → `403`.
- Owner reaches it via cookie with no mod-key; empty session → `count: 0`,
  `average: null`.

**Tests (UI)**
- After a participant submits feedback, on `/m/<code>` the `#feedback-card`
  is visible, `#feedback-summary` shows the average, and `#feedback-list`
  contains the comment text.

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
- `/s/<CODE>` shows `#title`, `#code`, `#my-name`, `#ask-card`, `#queries-card`, `#invite-card`.
- `#participant-breadcrumbs` shows Prashna → session title → Participant, with section links for the long participant page.
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

### UC-P-03: Set display name

- **Given** the participant types in the name input in the header
- **When** they blur the input
- **Then** `PATCH /api/sessions/{code}/me` saves it on the
  Participant row; their name appears beside every question / vote /
  response of theirs going forward
- **And** name is optional; blank = anonymous

**Tests (API)**
- `PATCH /api/sessions/{code}/me` with `{"name": "Alice"}` → `200 {id, name: "Alice"}`. Auth: none (cookie issued on first call).
- With `{"name": ""}` → `200 {id, name: null}` (blank = anonymous).
- With a name > 80 chars → name is truncated to 80 chars.
- Broadcasts `{type: "participant"}` on success.

**Tests (UI)**
- On `/s/<CODE>`, typing into `#my-name` and blurring PATCHes and persists the name.
- After saving a name, a query the participant asks shows that name beside it; with blank name, queries show as anonymous.

### UC-P-04: Ask

- **Given** the session is `planning` or `live`
- **When** the participant types a question and clicks Ask (or
  Cmd/Ctrl+Enter)
- **Then** `POST .../questions` creates a Question linked to their
  Participant; a toast confirms
- **And** an `ended` session refuses with `400 Session has ended` and
  the Ask card is hidden from the UI
- **And** the placeholder mentions the Cmd/Ctrl+Enter shortcut only on
  devices with a precise pointer (a keyboard is likely); phones show
  "Type your question…"

**Tests (API)**
- `POST /api/sessions/{code}/queries` with `{"text": "Hi?"}` on a `planning` or `live` session → `200 {id, text, author_name, response_text: null, responded: false, removed: false, vote_count: 0, voted: false, mine: true, created_at}`. Auth: none (cookie issued on first call).
- With `{"text": ""}` → `400 "text required"`.
- With `{"text": "   "}` → `400 "text required"`.
- With `{"text": "a"*1001}` → `400 "text too long"`.
- With `{"author_name": "Bob"}` → also updates participant name.
- On an `ended` session → `400 "Session has ended"`.
- Success broadcasts `{type: "query_new"}`.

**Tests (UI)**
- On `/s/<CODE>` (planning/live), typing into `#query-text` and clicking `#ask-btn` adds the query to `#queries` and toasts confirmation.
- Cmd/Ctrl+Enter in `#query-text` submits.
- On an `ended` session, `#ask-card` is hidden and `#ended-card` is visible.

### UC-P-05: Vote on a query

- **Given** a non-removed question on a non-ended session
- **When** the participant clicks the vote button
- **Then** `POST .../questions/{qid}/vote` toggles their vote; vote
  count refreshes; aria-pressed updates
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
- The participant's own queries are styled with a "you" marker; voted queries show the `.voted` vote-button state.

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
- **Queued-run redaction**: for non-moderator callers, a `queued` run is serialized with `current_question: null` — the question text and answers are NOT exposed before Start (prevents pre-launch peek at the first question). Moderators/owners see `current_question` even on queued runs.
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
- **Submit-after-reveal is blocked**: once the moderator clicks Reveal (so `run.reveal_current=true`), `POST .../submit` → `400 "Voting closed — results have been revealed"`. Prior submissions are preserved; no mutation occurs. This prevents a participant who sees the correct answer from going back to change their pick.
- Run not `live` (queued/closed) → `404 "Quiz not live"`.
- Session `ended` → `400 "Session has ended"`.
- Broadcasts `{type: "quiz_submission"}` on success.

**Tests (UI)**
- On `/s/<CODE>` with a single-choice question live, clicking an answer makes selection exclusive; clicking **Submit answer** POSTs and toasts. The Submit button is **always enabled** (a disabled button reads as broken) — submitting with no selection shows a "Pick an answer first" toast instead of a no-op; a "Pick an answer, then Submit." hint shows until one is chosen. (The button reads "Submit answer", then "Update answer" after a prior submission; tests locate it via `#quiz-body button.primary`, not its text.)
- With multi-choice, clicking answers toggles each independently.
- After moderator reveals, the answer inputs become disabled.
- A chosen answer is marked by more than a border tint: it shows a ✓ and the word "Selected" (after reveal, "Your answer"); unchosen answers show neither.

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
- The participant's selected answer is visually marked correct or wrong.
- After the moderator clicks Close, `#quiz-card` is hidden on the participant page (final results live on the projector — UC-D-06).

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
  and existing queries / quiz results remain visible

**Tests (API)**
- After `POST .../end`, `POST .../queries` → `400 "Session has ended"`.
- After `POST .../end`, `POST .../queries/{qid}/vote` → `400 "Session has ended"`.
- After `POST .../end`, `POST .../quiz_runs/{id}/submit` → `400 "Session has ended"`.
- `GET .../queries` still returns the existing list.

**Tests (UI)**
- On `/s/<CODE>`, after the moderator ends the session, the participant view (via WS) hides `#ask-card` and shows `#ended-card` with the "Session ended" message.
- Existing queries in `#queries` and the last quiz state in `#quiz-card` remain visible.
- On an ended session with no questions, `#queries` reads "No questions were asked." (not an invitation to ask).
- The participant section links show only sections that are visible: on an ended session with no quiz and rating closed, the Ask, Quiz, and Rating links are hidden; Profile and Questions remain.

### UC-P-12: Live answer counts during voting

Participant-side counterpart of UC-D-08.

- **Given** a QuizRun is `live` with `show_live_counts = true`
- **When** the participant view renders the current question's
  answering phase
- **Then** each answer shows a running vote-share bar with its **absolute
  count and percentage** (e.g. `5 (50%)`), and a **total respondent
  count** below, **without** correctness markers
- **And** voting remains open — clicking still toggles selection and
  Submit is enabled
- **And** when `show_live_counts = false` (default), the answering
  phase shows only the question and answers (no bars, no counts)

**Tests (API)**
- With `show_live_counts=true` and run live in answering phase, `GET .../quiz_runs/{id}` returns `results: {totals, respondents}` but answers do NOT include `is_correct`.
- With `show_live_counts=false` (default), `results` is `null` in the answering phase.

**Tests (UI)**
- On `/s/<CODE>` with live counts on, the answering phase shows running vote-share bars with each answer's count and percentage (`<count> (<pct>%)`) and a total respondent count; no correctness markers.
- Voting remains enabled — clicking still toggles selection and Submit is enabled.
- With live counts off (default), the answering phase shows only question + answer texts.

### UC-P-13: Rate the session (feedback)

A participant can rate the session and leave course feedback. The control
is **always available** (any session status) as the **first element on the
page** in a **collapsible card** (`#feedback-card`, a `<details>` that is
**open by default**) and uses progressive disclosure: a 1–5 **star** rating
that, once a star is picked, expands to reveal "What went well?" and "What
could be better?" text fields plus Submit. Hovering a star previews the
fill up to that star (hovering the 5th lights all five).

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
- **And** comments are optional — a bare rating is valid; `rating` must be
  an integer 1–5 or the POST returns `400`
- **And** submitting broadcasts `{type: "feedback"}` (UC-X-01) so the
  host's view (UC-M-12) updates live

**Tests (API)**
- `POST /api/sessions/{code}/feedback` with `{"rating": 4, "went_well": "...", "to_improve": "..."}` → `200 {rating, went_well, to_improve, updated_at}`. Auth: none (cookie issued on first call).
- A bare `{"rating": 5}` → `200` with null comment fields.
- Allowed on an `ended` session (the card is always available).
- Resubmitting is allowed any number of times: each call appends a `SessionFeedbackVersion` (history retained), while the current view stays one row per participant — `summary.count` stays 1 and the latest values win.
- `rating` of `0`, `6`, missing, a string, a float, or a bool → `400 "rating must be an integer from 1 to 5"`.
- `GET .../feedback/mine` → `null` before submitting, then the row.
- `DELETE /api/sessions/{code}/feedback` after a submit → `200 {ok: true}`; `mine` then returns null and `summary.count` drops by one. The `SessionFeedbackVersion` history is retained.

**Tests (UI)**
- `#feedback-card` is the first card on `/s/<CODE>` and is a collapsible `<details>` that is open by default.
- `#fb-submit` is present and enabled. With no rating it shows a "Choose a rating first" cue; selecting a star reveals `#fb-expand` without submitting, and clicking **Submit feedback** fires one `POST .../feedback` with the rating and both comments.
- After reload, the prior rating (filled stars count) and comment values are prefilled, and the button reads **Resubmit feedback**. Editing then resubmitting fires another `POST`.
- Clicking `#fb-clear` reveals an inline confirm (`#fb-clear-confirm`); `#fb-clear-no` cancels (rating unchanged), `#fb-clear-yes` clears the stars (filled count 0) and hides `#fb-expand`.

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

### UC-D-02: QR lightbox

- **Given** **any** QR code rendered via the shared `renderQR` helper —
  the projector join QR (`#join-qr`), the participant invite QR
  (`#share-qr`), the moderator invite QR (`#invite-qr`), and the landing
  session-detail QR (`#sd-qr`)
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
- The same enlarge behavior works on `/s/<CODE>` (`#share-qr`), `/m/<code>` (`#invite-qr`), and `/` session detail (`#sd-qr`).

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

**Tests (UI)**
- On `/p/<CODE>`, simulating a WS server restart causes the client to retry with exponential backoff (delays approximately 1s, 2s, 4s, 8s, 16s, capped near 32s).
- After the WS becomes available again, the next broadcast triggers a refetch and `#queries` / `#quiz-body` reflect the latest state.

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
  the participant URL QR
- **And** when the moderator clicks Start, the projector flips to
  UC-D-06 answering phase via WebSocket broadcast

**Tests (UI)**
- On `/p/<CODE>` with a `queued` run and no `live` run, `#quiz-body` shows "Next up:", the quiz title in display type, and a prompt to scan the participant URL QR.
- After moderator starts the run, `#quiz-body` transitions (via WS) to the answering phase (UC-D-06).

### UC-D-08: Live answer counts variant

Configurable per QuizRun via `show_live_counts` (default off).

- **Given** the moderator toggles "live counts" on for a QuizRun
- **When** the run is in answering phase
- **Then** the projector and participant pages display running vote
  totals — a bar with each answer's **absolute count and percentage**
  (`<count> (<pct>%)`) plus a **total respondent count** — **without**
  revealing correctness
- **And** voting remains open — participants can still pick / change
  their answer until the moderator advances or reveals
- **And** when counts are off (default), the answering phase shows
  only the question and answer texts; counts and correctness appear
  only after reveal

**Tests (API)**
- See UC-M-05 tests for `POST .../live_counts`.

**Tests (UI)**
- On `/p/<CODE>` with `show_live_counts=true`, the answering phase in `#quiz-body` shows running totals — bar + `<count> (<pct>%)` per answer and a total respondent count — without correctness markers.
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
  `quiz_submission`, `feedback`); each frontend treats the message as a
  refresh hint and re-fetches the data it cares about
- **And** the client auto-reconnects with exponential backoff if the
  socket drops; **on every reconnect after the first**, the client
  fires its refresh callback with a synthetic `{type: "reconnect"}`
  message so the page resyncs any state it may have missed while
  disconnected.
- **And** delivery is fanned out concurrently with a per-send timeout
  (~2 s). A slow or stalled receiver does not block the API
  response; failed sockets are evicted from the room.

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

### UC-X-02: WebSocket upgrade rejections

- **Given** a browser sends an `Origin` header that doesn't match
  `Host`
- **Then** the WS upgrade is closed with code **4403** (cross-origin)
- **Given** the URL's `{code}` does not match any Session
- **Then** the WS upgrade is closed with code **4404** (no session)

**Tests (API)**
- Connect WS to `/ws/sessions/{CODE}` with `Origin: https://evil.example`, `Host: localhost:8000` → server closes with code `4403`.
- Connect WS to `/ws/sessions/NOSUCH` with matching Origin/Host → server closes with code `4404`.
- Connect WS with no Origin header (curl-style client) → upgrade succeeds (matching skipped when Origin absent).

### UC-X-03: HTTP security headers

Two tiers, applied by one middleware:

- **Baseline (every non-`/uploads` response — pages + API):**
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Content-Security-Policy: frame-ancestors 'none'` — blocks
    clickjacking of the admin / moderator UI. A stricter `script-src`
    CSP is intentionally **not** set: the no-build pages rely on
    inline `<script type="module">` blocks, and `frame-ancestors` is
    the high-value directive that doesn't break them.
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

- **Given** the admin uploads an image
- **Then** `POST /api/uploads` accepts only `.png`, `.jpg`, `.jpeg`,
  `.gif`, `.webp` (SVG is explicitly excluded); enforces 5 MB caps
  on both Content-Length and streaming; stores under a fresh UUID
  filename

**Tests (API)**
- See UC-A-20 tests; in addition:
- `POST /api/uploads` with `.svg` → `400 "unsupported image type"`.
- `POST /api/uploads` two times with the same source file → two distinct UUID filenames on disk.
- Stored filename matches `^[0-9a-f]{32}\.(png|jpg|jpeg|gif|webp)$`.

### UC-X-05: Storage-level invariants

| Invariant                                                              | Enforced by                                |
| ---------------------------------------------------------------------- | ------------------------------------------ |
| At most one **live** `QuizRun` per Session                             | Partial unique index `uq_session_live_run` |
| At most one `QuizVersion` per `(quiz_id, version_no)`                  | UNIQUE constraint                          |
| At most one `QueryVote` per `(query, participant)`                     | UNIQUE constraint                          |
| At most one `QuizSubmission` per `(run, question, answer, participant)` | UNIQUE constraint                         |
| One `Participant` per `(session, voter_token)`                         | UNIQUE constraint                          |

**Tests (DB)**
- `PRAGMA foreign_keys` on every connection returns `1` (enabled via SQLAlchemy `connect` event). Cascade deletes (`ondelete="CASCADE"`) are actually enforced at the DB layer, not only by the ORM.
- Insert two `QuizRun` rows with `status="live"` for the same Session → second insert raises `IntegrityError` (partial unique index `uq_session_live_run`).
- Insert two `QuizVersion` rows with the same `(quiz_id, version_no)` → raises `IntegrityError`.
- Insert two `QueryVote` rows for the same `(query_id, participant_id)` → raises `IntegrityError`.
- Insert two `QuizSubmission` rows for the same `(quiz_run_id, question_id, answer_id, participant_id)` → raises `IntegrityError`.
- Insert two `Participant` rows with the same `(session_id, voter_token)` → raises `IntegrityError`.

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

### UC-X-07: PRASHNA_SECRET_KEY lifecycle

The admin session cookie is signed (HMAC) by `itsdangerous`. The
signing key is read from `PRASHNA_SECRET_KEY` at process start.

- **Given** `PRASHNA_SECRET_KEY` is set in the environment
- **Then** the signer uses that value; cookies survive process
  restarts and admins stay logged in
- **Given** `PRASHNA_SECRET_KEY` is **unset**
- **Then** the process generates a random key once and uses it for
  the process lifetime; all admin sessions are invalidated on every
  restart (admins must re-login)
- **And** the process logs a `WARNING` at startup
  (`auth.SECRET_KEY_IS_EPHEMERAL` is `True`) so an operator running
  without the env var isn't surprised by sessions dropping on restart
- **Operational rule:** production deployments **must** set
  `PRASHNA_SECRET_KEY` to a long random string and keep it stable.
  Rotating it is a deliberate "invalidate all sessions" action.

**Tests (API)**
- Start app with `PRASHNA_SECRET_KEY=abc...` env var, log in (admin cookie issued); restart app with same env var → `GET /api/admin/status` with the old cookie still returns `authenticated: true`.
- Start app with `PRASHNA_SECRET_KEY` unset, log in; restart app without setting the env var → old cookie now fails to verify and `GET /api/admin/status` returns `authenticated: false`.
- Start app with one value of `PRASHNA_SECRET_KEY`, log in; restart with a different value → old cookie fails to verify (rotation invalidates sessions).
- `auth._resolve_secret(None)` returns `(<random>, True)` (ephemeral) and `auth._resolve_secret("abc")` returns `("abc", False)`; with the env var set (as in the test session) `auth.SECRET_KEY_IS_EPHEMERAL` is `False`.

### UC-X-08: Rate limiting

A single-process, in-memory token-bucket limiter (`app/ratelimit.py`)
throttles abuse-prone routes. Each bucket is keyed by client IP; the
capacity is the allowed burst and refill is the sustained rate.

- **Given** the limiter is enabled (default; disable with
  `PRASHNA_RATELIMIT=off`)
- **Then** the following per-IP buckets apply, returning `429` with a
  human-readable `detail` when exhausted:

  | Route | Burst | Sustained | Notes |
  | --- | --- | --- | --- |
  | `POST /api/admin/login` | 8 | 1 / 30s | Checked **before** `verify_password` (bcrypt is costly); a successful login clears the bucket so a legitimate admin is never locked out |
  | new `Participant` row (in participant resolution) | 15 | 1 / 20s | Bounds row growth / presence inflation from a token-rotating flooder |
  | `POST .../queries` | 6 | 1 / 10s | |
  | `POST .../queries/{id}/vote` | 30 | 2 / s | |
  | `POST .../quiz_runs/{id}/submit` | 20 | 1 / 2s | |

- **Client IP** is the socket peer by default. Behind a reverse proxy
  set `PRASHNA_TRUSTED_PROXY_HOPS=N` (N = number of trusted hops; `1`
  for ngrok or the bundled nginx) so the limiter keys on the entry the
  outermost trusted proxy recorded in `X-Forwarded-For` — a
  client-supplied prefix to its left is ignored (spoof-resistant).
- **Scope:** this stops single-source floods and login brute-forcing.
  A distributed (many-IP) flood is out of scope for an in-process
  limiter. WebSocket connects are not rate-limited.

**Tests (API)**
- Token bucket: allows `capacity` calls then denies; refills at the configured rate (deterministic injected clock); keys are independent; `enabled=False` always allows; `reset`/`clear` restore a fresh bucket.
- `enabled_from_env`: `None`/`"on"`/`"1"` → enabled; `"off"`/`"0"`/`"false"`/`"no"` (any case) → disabled.
- `_client_ip`: with hops=0 returns the socket peer; with hops=1 returns the rightmost `X-Forwarded-For` entry even when a spoofed value precedes it; with hops=2 the second-from-right; with hops>0 and no XFF falls back to the peer.
- Endpoint floods (limiter re-enabled for the test): login → `429` after the burst, and a correct login resets the throttle; `POST queries` / `vote` / `submit` each return `429` under a sustained flood; rapid fresh `voter_token`s eventually `429` on participant creation. With the limiter off (suite default) none of these `429`.

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
- **And** it requires a stable `PRASHNA_SECRET_KEY`, exposes a health check,
  and remains independent of the Hetzner-only `/opt/prashna` configuration
- **And** tagged bundles pin the image tag to the matching release rather than
  silently following `latest`
- **And** published images cover `linux/amd64` and `linux/arm64`
- **And** backup creates a consistent SQLite snapshot plus uploads without
  storing secrets; restore validates the archive and database, requires an
  explicit confirmation flag, and creates a pre-restore recovery archive
  before replacing current data.

**Tests (Ops)**
- Root Compose config without `PRASHNA_SECRET_KEY` fails with an actionable
  message; with a test env it resolves the requested image tag and port, health
  endpoint, and named-volume mounts without `/opt/prashna` host paths.
- Backup/restore round-trip restores the original SQLite contents and uploads;
  restore refuses without `--confirm` and rejects archive path traversal.
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
- `performance/measure.py` records `usable_ms`, fails an otherwise successful
  navigation that never reaches the usable mark, and retains the existing
  network/application metrics.
- The Cloudflare cache rule is scoped only to `prashna.sankara.net` HTML page
  routes and respects the origin cache directives; `/api/`, `/ws/`, and
  `/uploads/` are never matched.

### UC-X-12: Phone-width layout

Most participants use phones, and admins and moderators sometimes do.
Every surface works at a 390 px wide viewport.

- **Given** a viewport 390 px wide
- **Then** no page scrolls sideways; wide tables scroll inside their own
  `.table-scroll` box, and row headers (quiz-run controls, editor rows)
  wrap instead of widening the page
- **And** text inputs, text areas, and selects use at least a 16 px font
  on narrow screens, so iOS Safari does not zoom in when one is focused
- **And** on touch devices (`pointer: coarse`) buttons, menu toggles, and
  section links are at least 32 px tall
- **And** a detail card opened from a list (quiz editor, run results)
  scrolls into view

**Tests (UI)**
- At 390×844, `/`, `/quizzes` (with the editor open), `/m/<code>` (live, with a live run and questions), `/s/<code>` (live quiz), and `/p/<code>` each have `document.documentElement.scrollWidth <= 390`.
- At 390×844, every visible `input[type=text]`, `textarea`, and `select` on `/quizzes` (editor open), `/m/<code>`, and `/s/<code>` has a computed font size of at least 16 px.
- In a touch-emulating context at 390×844, every visible `button` and `details.menu > summary` on `/quizzes` and `/m/<code>`, and every `.section-links a`, is at least 32 px tall.

### UC-X-13: One button size scale

Buttons come in three sizes (UX.md §10), and all of a card's own actions
use the same one, so a page never mixes large and small versions of the
same kind of action.

- **Given** any page at desktop width
- **Then** default buttons use 14 px text and are about 34 px tall
- **And** custom call-to-action elements (the participant profile's
  "Add details") match the default button size and weight
- **And** `.small` (card headers, dense lists) and `.xsmall` (table rows)
  are the only smaller sizes

**Tests (UI)**
- At 1280×800 on `/s/<code>` with rating open, `.profile-cta`, `#fb-submit`, and `#ask-btn` have the same height (within 1 px), at most 36 px, and a 14 px font.
- At 1280×800 on `/` signed out, `#join-btn` and `#li-btn` have that same height and font size.

### UC-X-14: One answer-option component

The participant page, the session page, and the projector draw answer
options with one shared renderer (`answerOption()` in `common.ts`), so
a fix or style change reaches all three. Surfaces differ only in what
they pass: whether the viewer can pick, whether counts show, and whether
correctness is revealed.

- **Given** a revealed question on all three surfaces
- **Then** the correct answer shows "✓ Correct" as text (not only a green
  border), and counts read "<n> (<p>%)" with a proportional bar
- **And** only the participant page's options are buttons; a chosen
  answer there shows a ✓ and "Selected" / "Your answer" (UC-P-08)

**Tests (UI)**
- After reveal, `/s/<code>` (participant), `/m/<code>` (session page), and `/p/<code>` (projector) each show exactly one `.option.correct` containing `.opt-correct` with text "✓ Correct", and every `.opt-pct` matches `^\d+ \(\d+%\)$`.

**Tests (static)**
- `frontend/src/participant.ts`, `moderator.ts`, and `projector.ts` don't build `.option` elements themselves; they call `answerOption()`.

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
