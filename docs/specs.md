# Prashna — specs

Use cases and acceptance tests for the four roles in the system. Each use
case has a stable ID (`UC-<ROLE>-NN`) so tests, PRs, and bug reports can
cite it. Acceptance tests are Given/When/Then.

**Roles**
- **Admin** — a logged-in `User` (today: single global admin per
  deployment). Owns sessions and quiz templates. **Capabilities are a
  strict superset of Moderator.** Authenticates via signed cookie;
  reaches all moderator routes on owned sessions without needing the
  mod_key.
- **Moderator** — anyone holding the `mod_key` for a session. Used for
  *delegation*: the owner can hand the moderator URL to a TA / co-host
  who has no admin account. Capabilities are the moderation subset of
  Admin (no quiz authoring, no session create/delete, no global
  reports).
- **Participant** — anonymous audience member. Identified by a
  `voter_token` cookie that resolves to a per-session `Participant`
  row.
- **System** — implicit actor for lifecycle gates, WebSocket
  broadcasts, validation, and constraints enforced at the storage
  layer.

**Authorization model.** Every moderator-gated route accepts *either*
the admin owner cookie *or* an `X-Mod-Key` header. Reads that branch
on "is this caller a moderator?" (e.g., showing removed queries, or
queued runs) use the same rule. This means the admin gets the moderator
UI seamlessly; the mod_key path stays available for delegates.

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

### UC-A-04: See my sessions

- **Given** the admin owns sessions
- **When** they `GET /api/sessions`
- **Then** they see only sessions where `owner_user_id = me.id`,
  ordered by `created_at desc`, with status, query count, quiz-run
  count, mod_key, and participant_base_url

### UC-A-05: Edit session title

- **Given** the admin opens a session's detail card
- **When** they change the Title input and blur
- **Then** `PATCH /api/sessions/{code}` updates the title; the row in
  the list reflects the change
- **And** an empty new title returns `400` and the input reverts to
  the old value

### UC-A-06: Set per-session participant base URL

- **Given** the detail card is open
- **When** the admin types a URL into the Base URL input and blurs
- **Then** `POST /api/sessions/{code}/participant_base_url` saves the
  value (with trailing slash stripped); the QR and copy-URL widgets
  refresh
- **And** a URL not starting with `http://` or `https://` returns
  `400`
- **And** an empty submission (or Use default click) sets the field to
  `null` and the frontend falls back to `location.origin`

### UC-A-07: Delete a session

- **Given** the admin clicks Delete on a session row
- **When** the session is `live` → the action is refused with
  "End the session before deleting it" (toast)
- **And** the session has 0 questions and 0 quiz runs → a native
  `confirm()` followed by `DELETE` deletes it
- **And** the session has data → a confirm card opens below the table
  warning what will be lost (counts), with a typed-title input that
  must match `session.title` exactly to enable the Delete button
- **Then** on success, the session is removed; cascade-deletes its
  questions, votes, participants, quiz_runs, and responses.
  QuizVersions are NOT touched (they belong to Quiz templates).

### UC-A-08: Inline session moderation from the landing page

Because Admin ⊇ Moderator, the admin doesn't need to switch contexts
to do basic moderation on their own sessions.

- **Given** the admin opens a session detail card on `/`
- **Then** they see the session's status badge, a Start or End button
  appropriate to status, an "Open moderator →" link to the full
  moderator surface, and a "Share moderator URL" copy button for
  delegation
- **And** clicking Start or End calls the lifecycle endpoint with
  cookie auth (no mod_key)
- **And** the per-row "Moderate" link navigates to `/m/<code>` and
  loads the full moderator surface without a key gate (admin owners
  authenticate via cookie)

---

**Quiz authoring** (UC-A-09 through UC-A-22). Each operation gets its
own use case so tests and PRs can cite one ID per behavior.

### UC-A-09: Create a quiz template

- **Given** the admin clicks **+ New** on `/quizzes` with a title
- **When** `POST /api/quizzes` is called
- **Then** a Quiz is created with `owner_user_id = me.id`, status =
  `draft`, `last_edited_at = now`; the new quiz opens in the editor

### UC-A-10: Browse the quiz library

- **Given** the admin is on `/quizzes`
- **When** `GET /api/quizzes` (optionally `?ready_only=true`) is called
- **Then** the response includes only quizzes owned by the admin,
  ordered by `created_at desc`, with `status` and `question_count`
- **And** moderator dropdowns use `ready_only=true`; the quiz library
  table uses the full list

### UC-A-11: Open a quiz for editing

- **Given** the admin clicks a row in the library
- **When** `GET /api/quizzes/{id}?include_correct=true` is called
- **Then** the editor pane shows the title, items, options, and
  per-option correctness
- **And** the route returns `404` for a non-owner (no read access
  across owners)

### UC-A-12: Rename a quiz

- **Given** the editor is open
- **When** the admin edits the title input and blurs
- **Then** `PATCH /api/quizzes/{id}` updates the title and advances
  `last_edited_at`
- **And** an empty title is silently ignored (existing title kept)
- **And** status does **not** auto-revert from `ready` → `draft`
  (versioning protects history)

### UC-A-13: Delete a quiz template

- **Given** the admin clicks Delete on a quiz row
- **When** no QuizVersion of this quiz has been used in any run
- **Then** `DELETE /api/quizzes/{id}` cascades to items, options, and
  versions
- **And** if any version has been used, returns `400 Quiz has been
  used in a session run and cannot be deleted` (preserves session
  data)

### UC-A-14: Add a quiz question

- **Given** the admin clicks **+ Add question** in the editor
- **When** `POST /api/quizzes/{id}/questions` is called
- **Then** a `Question` is added at the end (`order_index = max + 1`)
  with default `text = "New question"` and `qtype = "single"`; parent's
  `last_edited_at` advances
- **And** a `qtype` not in `("single", "multi")` returns `400`

### UC-A-15: Edit a quiz question

- **Given** the admin focuses a question's text, type, image, or order
- **When** `PATCH /api/quiz_questions/{id}` is called with any subset of
  `text` / `qtype` / `image_url` / `order_index`
- **Then** the fields update; parent quiz `last_edited_at` advances
- **And** invalid `qtype` returns `400`; non-int `order_index`
  returns `400`

### UC-A-16: Delete a quiz question

- **Given** the admin clicks Delete on a question (with `confirm()`)
- **When** `DELETE /api/quiz_questions/{id}` is called
- **Then** the question and its answers are removed via cascade; parent
  quiz `last_edited_at` advances

### UC-A-17: Add an answer to a question

- **Given** the admin clicks **+ Answer** under an item
- **When** `POST /api/quiz_questions/{id}/answers` is called
- **Then** a `Answer` is added at the end with default
  `text = "New answer"`, `is_correct = false`; parent quiz
  `last_edited_at` advances

### UC-A-18: Edit an answer

- **Given** the admin changes an answer's text, correctness, image,
  or order
- **When** `PATCH /api/quiz_answers/{id}` is called
- **Then** the fields update; parent quiz `last_edited_at` advances
- **And** non-int `order_index` returns `400`

### UC-A-19: Delete an answer

- **Given** the admin clicks ✕ on an answer
- **When** `DELETE /api/quiz_answers/{id}` is called
- **Then** the answer is removed; parent quiz `last_edited_at`
  advances

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

### UC-A-21: Publish a quiz

- **Given** a Draft quiz
- **When** the admin clicks Publish (`POST /api/quizzes/{id}/publish`)
- **Then** validation runs: ≥ 1 question; each question with non-empty text;
  each question with ≥ 2 answers; each `single` question with exactly one
  `is_correct` answer; each `multi` question with ≥ 1 correct answer;
  each answer with non-empty text OR `image_url`
- **And** on pass, status → `ready`
- **And** on fail, returns `400` with the specific failing rule
  message ("Question 2 (single choice) needs exactly one correct answer")

### UC-A-22: Unpublish a quiz

- **Given** a Ready quiz
- **When** `POST /api/quizzes/{id}/unpublish` is called
- **Then** status → `draft`
- **And** quiz versions already captured for prior runs are NOT
  affected (history preserved)

---

**Reports**

### UC-A-23: Global quiz-runs report

- **Given** the admin owns sessions with QuizRuns
- **When** they open `/quizzes` and view the "Quiz runs" table
- **Then** they see every QuizRun across all their sessions (joined
  via owner), with quiz title, version number, session code, status,
  progress, respondent count, and created time

### UC-A-24: View one quiz-run's results

- **Given** the admin clicks a row in the Quiz runs table
- **When** `GET /api/quiz_runs/{id}/results` is called
- **Then** the inline results pane shows per-question answer counts,
  correctness markers, and respondent count; uses the snapshotted
  `quiz_title` + `version_no` so historical reports survive later
  edits to the template

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

### UC-M-02: Session lifecycle: Start → End

- **Given** the moderator is on `/m/<code>` and the session is
  `planning`
- **When** they click Start session
- **Then** `POST /api/sessions/{code}/start` sets status to `live` and
  records `started_at`
- **When** they click End session and confirm
- **Then** `POST /api/sessions/{code}/end` sets status to `ended` and
  records `ended_at`
- **And** starting a quiz run on a `planning` session auto-advances
  it to `live` as a side effect

### UC-M-03: Queue a quiz onto the session

- **Given** the moderator picks a Ready quiz from the dropdown (drafts
  are filtered out) and clicks Add to session
- **When** the Quiz has unsaved edits since the latest version
- **Then** `_ensure_current_version` deep-copies the quiz tree into a
  new immutable `QuizVersion(version_no = latest+1)`; the new QuizRun
  points to it
- **And** when the Quiz has not changed since the latest version, the
  new QuizRun reuses that version
- **And** queueing a Draft quiz returns `400`
- **And** queueing on an ended session returns `400`

### UC-M-04: Start a queued quiz run

- **Given** a QuizRun is `queued`
- **When** the moderator clicks Start
- **Then** `POST /api/sessions/{code}/quiz_runs/{id}/start` flips its
  status to `live`, resets `current_question_idx = 0`, `reveal_current =
  False`
- **And** if another QuizRun is already `live` in the same Session,
  the start returns `409 Another quiz is already live — close it
  first` (enforced by the `uq_session_live_run` partial unique index)

### UC-M-05: Walk through items

- **Given** a live QuizRun
- **When** the moderator clicks Next / Prev
- **Then** `current_question_idx` advances within `[0, question_count-1]` and
  `reveal_current` resets to `False`
- **And** clicking Reveal results / Hide results toggles
  `reveal_current` for the current item

### UC-M-06: Close a quiz run

- **Given** a live QuizRun
- **When** the moderator clicks Close
- **Then** status → `closed`, `reveal_current → True`, `closed_at` is
  set
- **And** the row's Delete (`✕`) action disappears (closed runs are
  preserved)
- **And** the moderator's quiz-runs list refreshes via WebSocket
- **And** participants who already submitted keep their selections;
  no new responses are accepted

### UC-M-07: Remove a quiz run (only when queued / live)

- **Given** a queued or live QuizRun
- **When** the moderator clicks `✕` and confirms
- **Then** `DELETE /api/sessions/{code}/quiz_runs/{id}` deletes the
  run and its responses
- **And** a closed run returns `400 Closed quiz runs are historical
  and cannot be deleted`

### UC-M-08: Mark a question answered

- **Given** a question in the moderator's questions list
- **When** they type an answer (optional) and click Mark responded
- **Then** `POST .../queries/{qid}/respond` sets `responded_at` and
  `response_text` (which may be null for verbal-only answers)
- **And** the participant view moves the question to the answered
  section
- **And** the moderator can Reopen an answered question, clearing
  `responded_at`

### UC-M-09: Remove / Restore a query

- **Given** any question (e.g., spam / off-topic / duplicate)
- **When** the moderator clicks Remove
- **Then** `POST .../questions/{qid}/remove` sets `removed_at`; the
  question becomes invisible to participants but stays visible to the
  moderator with a Restore action
- **And** votes on a removed question return `404`

### UC-M-10: Live participant count

- **Given** participants are interacting with the session
- **When** the moderator views their header bar (and on each
  WebSocket-driven refresh)
- **Then** the count of participants whose `last_seen_at` falls within
  the last 30 seconds is shown

### UC-M-11: Invite participants

- **Given** the moderator is on the moderator page
- **When** they paste a Base URL and blur the input
- **Then** the page rebuilds the participant URL as
  `<base>/s/<code>`, renders a QR, and updates the copy-URL text
- **And** clicking Use default clears the override and the page falls
  back to `location.origin`

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

### UC-P-02: Anonymous identity per session

- **Given** the participant has never visited this session
- **When** any participant-facing route runs
- **Then** the server resolves their `voter_token` cookie (issued on
  first interaction if missing) to a `Participant` row, scoped to
  this session
- **And** `last_seen_at` is updated at most once per 5 seconds per
  request

### UC-P-03: Set display name

- **Given** the participant types in the name input in the header
- **When** they blur the input
- **Then** `PATCH /api/sessions/{code}/me` saves it on the
  Participant row; their name appears beside every question / vote /
  response of theirs going forward
- **And** name is optional; blank = anonymous

### UC-P-04: Ask

- **Given** the session is `planning` or `live`
- **When** the participant types a question and clicks Ask (or
  Cmd/Ctrl+Enter)
- **Then** `POST .../questions` creates a Question linked to their
  Participant; a toast confirms
- **And** an `ended` session refuses with `400 Session has ended` and
  the Ask card is hidden from the UI

### UC-P-05: Vote on a query

- **Given** a non-removed question on a non-ended session
- **When** the participant clicks the vote button
- **Then** `POST .../questions/{qid}/vote` toggles their vote; vote
  count refreshes; aria-pressed updates
- **And** removed queries return `404`; ended sessions return `400`

### UC-P-06: See questions sorted

- **Given** any participant viewing the session
- **When** `GET .../questions` returns
- **Then** removed queries are filtered out; remaining are sorted
  unanswered-first, then by descending vote count
- **And** their own questions are flagged `mine: true` and the
  questions they voted on are flagged `voted: true`

### UC-P-07: See live quiz

- **Given** a QuizRun is `live`
- **When** the participant page loads (or refreshes via WS)
- **Then** the Live quiz card surfaces the current item, its options,
  and the participant's prior selections (if any)
- **And** when status flips to `closed`, the card stays visible
  showing results

### UC-P-08: Respond to the current item

- **Given** the current item is live and the participant hasn't been
  served `reveal_current=true`
- **When** they click options (single → exclusive; multi → toggle)
  and click Submit
- **Then** `POST .../quiz_runs/{id}/respond` replaces their prior
  responses for that item with the new ones (last-write-wins)
- **And** options must belong to the current item; mismatch returns
  `400`
- **And** single-type cannot have > 1 option_id; returns `400`
- **And** an ended session refuses with `400`

### UC-P-09: See results when revealed or closed

- **Given** the moderator has clicked Reveal or Close
- **When** the participant view refreshes
- **Then** the option bars are scaled to vote share, correctness is
  shown, and the participant's selected option is marked correct or
  wrong as appropriate

### UC-P-10: Share QR with neighbor

- **Given** the participant page is open
- **When** they look at the Invite others card
- **Then** a QR encodes the same participant URL the moderator
  configured (or `location.origin` fallback)

### UC-P-11: Ended session is read-only

- **Given** session.status flips to `ended` via WS broadcast
- **When** the participant view refreshes (via the broadcast)
- **Then** the Ask-a-question card disappears, a "Session ended" card
  appears, and existing questions / quiz results remain visible

---

## Projector / System

### UC-X-01: Projector display

- **Given** anyone (no auth) opens `/p/<code>` for a valid session
- **Then** they see: session title, the join code in large type, the
  participant URL host, a QR encoding the full participant URL, top
  questions sorted by vote, and the current live or closed quiz item

### UC-X-02: QR lightbox

- **Given** the projector page
- **When** someone clicks (or Tab→Enter) the QR
- **Then** a full-screen lightbox shows the QR at ≈90% of the
  smaller viewport dimension; Esc, click, or the `cursor: zoom-out`
  area dismisses it

### UC-X-03: Live updates via WebSocket

- **Given** any of the participant / moderator / projector views are
  connected to `/ws/sessions/{CODE}`
- **When** any state-changing route on that session commits
- **Then** the server broadcasts `{type: <kind>}` to the room (kinds:
  `session_state`, `participant`, `query_new`, `query_vote`,
  `query_responded`, `query_removed`, `query_deleted`,
  `quiz_run_new`, `quiz_run_update`, `quiz_run_deleted`,
  `quiz_submission`); each frontend treats it as a refresh hint and
  re-fetches its data
- **And** the client auto-reconnects with exponential backoff if the
  socket drops

### UC-X-04: Cross-origin WS rejected

- **Given** a browser sends an `Origin` header that doesn't match
  `Host`
- **Then** the WS upgrade is closed with code 4403

### UC-X-05: Static asset security headers

- **Given** any file under `/uploads/`
- **Then** responses carry `X-Content-Type-Options: nosniff`,
  `Content-Security-Policy: default-src 'none'; sandbox`, and
  `Cross-Origin-Resource-Policy: same-origin`

### UC-X-06: Image upload constraints

- **Given** the admin uploads an image
- **Then** `POST /api/uploads` accepts only `.png`, `.jpg`, `.jpeg`,
  `.gif`, `.webp` (SVG is explicitly excluded); rejects files over
  5 MB on size or streaming; stores under a fresh UUID filename

### UC-X-07: Storage-level invariants

| Invariant                                | Enforced by                             |
| ---------------------------------------- | --------------------------------------- |
| At most one live QuizRun per Session     | Partial unique index `uq_session_live_run` |
| At most one QuizVersion per (quiz_id, version_no) | UNIQUE constraint              |
| At most one vote per (question, participant) | UNIQUE constraint                  |
| At most one response per (run, item, option, participant) | UNIQUE constraint    |
| One Participant per (session, voter_token) | UNIQUE constraint                     |

### UC-X-08: Versioning lazy capture

- **Given** Quiz Q has versions v1, v2 already
- **When** the moderator queues Q without editing since v2 → the new
  QuizRun reuses v2
- **And** when an edit happens between v2 and the next queue → a v3
  is captured at queue time and the new run points to v3
- **And** when two requests race and both try to create version N+1,
  the UNIQUE constraint causes one to lose; the loser catches
  `IntegrityError`, re-reads the latest, and returns it
