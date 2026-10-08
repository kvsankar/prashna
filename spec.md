<!-- sarathi:artifact-format version="2" -->

# Prashna Retrospective Software Requirements Specification

## Product Overview

Prashna lets an organizer run a live room where participants can join without
accounts, ask and support questions, answer moderator-led quiz questions, give
feedback, and follow the projected room state. The baseline is deliberately
small: one private operator bootstrap, one admin-owned session model, delegated
moderator access, anonymous participant identity scoped to a session, and a
single-process deployment model.

Success means the existing brownfield product remains understandable and
testable from observable behavior. Admin, moderator, participant, projector,
quiz, feedback, live-refresh, deployment, and documentation contracts must be
explicit enough for future changes to preserve the accepted baseline. Public
bootstrap hardening, distributed scale, richer migration tooling, and larger UX
redesigns remain future deltas unless separately approved.

## Mission Statement

Prashna shall help organizers run live audience sessions where participants can
ask questions anonymously, answer moderator-led quizzes, give feedback, and
follow a shared room display without account setup. This retrospective baseline
SRS reconstructs current intended behavior for the existing brownfield product
from governing documentation, tests, code behavior, review reports, deployment
notes, and open-decision records. It is a product/system parent specification,
not a direct implementation plan.

Work Scope: product/system

Ready To Implement: No

Review Level: Standard

Extra Checks: Security, Privacy and compliance, Reliability and operations,
Build and release, Documentation, UI and accessibility

## Source Reconciliation

This is a Brownfield Baseline Adoption SRS. Current behavior is reconstructed
from source sets rather than invented as a new product.

- `docs/specs.md`
  - Classification: current governing source
  -  Use In This SRS: Detailed behavior, roles, lifecycles, auth boundaries,
    acceptance intent, deferred product decisions.
- `docs/UX.md`
  - Classification: current governing source
  -  Use In This SRS: Current UI density, card, table, feedback, menu, status,
    accessibility, copy, and control conventions.
- `README.md` and `CLAUDE.md`
  - Classification: adopted source
  -  Use In This SRS: Product mission, run commands, stack, role model,
    deployment posture, repo conventions.
- `tests/api` and `tests/ui`
  - Classification: adopted source
  - Use In This SRS: Executable evidence for current API and browser behavior.
- `app/`, `frontend/`, deploy files, CI config
  - Classification: adapted source
  -  Use In This SRS: Observed behavior and externally visible constraints,
    filtered to requirements rather than design.
- `docs/todo.md`
  - Classification: current engineering follow-up ledger
  -  Use In This SRS: Active cleanups and prerequisites for broader hosted
    operation. Product ideas awaiting decisions remain in `docs/specs.md`.
- One-off reviews, assessments, plans, proposals, and dated investigations
  - Classification: immutable historical evidence, intentionally local-only
  -  Use In This SRS: They informed the original baseline reconstruction but
    are not governing sources and are not revised as the product changes.

Current baseline and future deltas are separated below. Open-decision items are
listed as non-goals or open questions unless current docs already define
accepted behavior.

## User Needs

-  UN-PARTICIPANT-ASK: Participants need anonymous question asking during a live
  session.
-  UN-PARTICIPANT-SUPPORT: Participants need a way to support questions raised
  by others.
-  UN-PARTICIPANT-IDENTITY: Participants need optional display identity scoped
  to one session.
-  UN-PARTICIPANT-QUIZ: Participants need clear quiz participation during the
  active question.
-  UN-PARTICIPANT-FEEDBACK: Participants need a low-friction way to rate the
  session.
- UN-MODERATOR-RUN: Moderators need a cockpit for live session control.
- UN-MODERATOR-QA: Moderators need audience question triage during the event.
- UN-MODERATOR-QUIZ: Moderators need controlled quiz playback for the room.
-  UN-ADMIN-BOOTSTRAP: Operators need first-run admin access for a new
  deployment.
- UN-ADMIN-SESSIONS: Admins need session setup plus owner-only management.
- UN-ADMIN-QUIZZES: Admins need reusable quiz authoring.
- UN-ADMIN-REPORTS: Admins need stable historical reports.
- UN-DISPLAY-JOIN: Room audiences need clear join information on the projector.
- UN-DISPLAY-STATE: Room audiences need visible live session state.
-  UN-OPS-RUN: Operators need repeatable local run plus production deployment
  steps.
- UN-OPS-SAFETY: Operators need safe deployment configuration.
-  UN-DEVELOPER-CONTRACT: Developers need behavior docs that stay aligned with
  tests.

## Non-Goals

-  Multi-tenant SaaS administration is not current baseline scope for
  UN-ADMIN-BOOTSTRAP or UN-ADMIN-SESSIONS.
-  Public-first bootstrap is not current baseline scope; the accepted private
  operator bootstrap workflow constrains UN-OPS-SAFETY until a child spec
  chooses a token, CLI, or equivalent public-safe flow.
-  Reopening ended sessions or closed quiz runs is not current baseline scope
  for UN-MODERATOR-RUN or UN-MODERATOR-QUIZ.
-  Per-question timers and auto-advance are not current baseline scope for
  UN-MODERATOR-QUIZ.
-  Image content sniffing and server-side `image_url` origin validation are not
  current baseline scope for UN-ADMIN-QUIZZES.
-  Multiple FastAPI workers, replicated WebSocket hubs, Redis pub-sub, and
  distributed rate limiting are not current baseline scope for UN-OPS-RUN.
-  A frontend framework migration is not current baseline scope for
  UN-DEVELOPER-CONTRACT.
-  Alembic migrations are not current baseline scope, but additive SQLite
  migration coverage remains required under NFR-SCHEMA-MIGRATION.
-  The UX simplification proposal is not current baseline scope until approved
  through child specs.
-  Live production deployment, push, or redeploy is not in scope without
  explicit user instruction.

## Features

-  FEAT-AUTH-ADMIN: First-run setup, password admin login, password rotation,
  logout, and optional allowlisted GitHub admin login satisfy UN-ADMIN-BOOTSTRAP
  and UN-OPS-SAFETY.
-  FEAT-SESSION-MANAGE: Admin session creation, listing, metadata editing,
  lifecycle control, deletion, and participant URL configuration satisfy
  UN-ADMIN-SESSIONS.
-  FEAT-MOD-DELEGATE: Moderator-key delegation gives non-admin hosts live-room
  powers without owner-only controls, satisfying UN-MODERATOR-RUN.
-  FEAT-QA-LIVE: Anonymous question creation, voting, sorting, response, soft
  removal, and restore behavior satisfy UN-PARTICIPANT-ASK,
  UN-PARTICIPANT-SUPPORT, and UN-MODERATOR-QA.
-  FEAT-QUIZ-AUTHOR: Quiz template authoring, validation, publishing, image
  attachment, and version capture satisfy UN-ADMIN-QUIZZES.
-  FEAT-QUIZ-RUN: Queue, start, advance, reveal, live-count, close, delete,
  submit, and results behavior satisfy UN-MODERATOR-QUIZ and
  UN-PARTICIPANT-QUIZ.
-  FEAT-FEEDBACK-RATE: Participant feedback capture and moderator summary views
  satisfy UN-PARTICIPANT-FEEDBACK and UN-ADMIN-REPORTS.
-  FEAT-DISPLAY-ROOM: Public projector join, Q&A, participant-count, quiz,
  reveal, and ended-state views satisfy UN-DISPLAY-JOIN and UN-DISPLAY-STATE.
-  FEAT-LIVE-REFRESH: WebSocket hints plus HTTP refetch keep role pages
  synchronized, satisfying UN-DISPLAY-STATE and UN-MODERATOR-RUN.
-  FEAT-OPS-BASELINE: Local commands, Docker deployment, persistent data paths,
  security headers, upload isolation, rate limits, additive migration checks,
  and docs contracts satisfy UN-OPS-RUN, UN-OPS-SAFETY, and
  UN-DEVELOPER-CONTRACT.

## Use Cases

- UC-AUTH-BOOTSTRAP
  - Primary actor: Operator.
  -  Supporting actors/systems: Browser client, admin API, signed-cookie
    service, password verifier, optional GitHub OAuth provider.
  - Goal: Establish trusted admin access for a fresh deployment.
  - Scope: Product/system baseline.
  - Trigger: The operator opens the root page before any admin exists.
  -  Preconditions: The app is running, the database is reachable, and no admin
    user exists.
  -  Minimal guarantees: A failed setup attempt does not create partial admin
    access. Existing sessions and quiz data remain unchanged.
  -  Success guarantees: Exactly one admin identity can authenticate after
    setup, and later setup attempts are rejected.
  - Main success scenario:
    1. Operator opens the landing page.
    2. System detects that no admin exists.
    3. System shows first-run setup instead of login.
    4. Operator submits a non-empty username plus an acceptable password.
    5. System creates the admin identity.
    6. System issues an admin session cookie.
    7. System shows the authenticated admin view.
  -  Alternate flows: GitHub OAuth login is offered when configured. Existing
    admin deployments show login instead of setup. A successful password change
    rotates admin session validity.
  -  Error/exception flows: Short passwords are rejected. Empty usernames are
    rejected. Concurrent setup attempts leave exactly one admin. Public
    deployment before private bootstrap is a future hardening delta, not
    current baseline behavior.
  -  Postconditions: Admin-only features are available to the authenticated
    operator.
  - Frequency/importance: Critical first-run and recovery path.
  -  Trace links: UN-ADMIN-BOOTSTRAP, UN-OPS-SAFETY, FEAT-AUTH-ADMIN,
    FR-AUTH-BOOTSTRAP, FR-AUTH-LOGIN, FR-AUTH-GITHUB, FR-AUTH-PASSWORD,
    NFR-SEC-PASSWORDS, NFR-BOOTSTRAP-PUBLIC, AT-AUTH-BOOTSTRAP, AT-AUTH-LOGIN,
    AT-AUTH-GITHUB, AT-AUTH-PASSWORD, JT-ROOM-LIVE, JT-OPS-RELEASE.

- UC-SESSION-ADMIN
  - Primary actor: Admin.
  -  Supporting actors/systems: Browser client, session API, QR generator,
    signed-cookie service.
  - Goal: Prepare and manage an event session owned by the admin.
  - Scope: Product/system baseline.
  - Trigger: Admin opens the authenticated landing page.
  - Preconditions: Admin is authenticated.
  -  Minimal guarantees: Invalid edits do not corrupt an existing session.
    Delegated moderators cannot perform owner-only edits.
  -  Success guarantees: The session has a stable code, owner, lifecycle state,
    moderator key, participant URL behavior, and delete rules.
  - Main success scenario:
    1. Admin enters a session title.
    2. System creates a planning session with a unique code.
    3. System lists owned sessions with status and counts.
    4. Admin opens session details.
    5. Admin updates title or participant base URL when needed.
    6. Admin starts the session when ready.
    7. System allows live participation surfaces to reflect the live state.
    8. Admin ends the session after live work is complete.
  -  Alternate flows: Admin clears a custom participant base URL. Admin copies
    participant, moderator, or projector links. Admin deletes a non-live empty
    session through a simple confirmation. Admin deletes a non-live data-bearing
    session through a typed-title confirmation.
  -  Error/exception flows: Empty or oversized titles are rejected. Invalid base
    URLs are rejected. Live sessions cannot be deleted. A non-owner admin cannot
    manage another owner session. A delegated moderator sees read-only invite
    controls.
  -  Postconditions: Session state, ownership, invite data, and lifecycle are
    visible to the correct surfaces.
  - Frequency/importance: Core admin path for every event.
  -  Trace links: UN-ADMIN-SESSIONS, FEAT-SESSION-MANAGE, FEAT-MOD-DELEGATE,
    FR-SESSION-CREATE, FR-SESSION-METADATA, FR-SESSION-LIFECYCLE,
    FR-SESSION-DELETE, FR-MOD-ACCESS, AT-SESSION-CREATE, AT-SESSION-METADATA,
    AT-SESSION-LIFECYCLE, AT-SESSION-DELETE, AT-MOD-ACCESS, JT-ROOM-LIVE.

- UC-QUIZ-AUTHOR
  - Primary actor: Admin.
  -  Supporting actors/systems: Quiz library page, quiz API, upload API, static
    upload file service.
  - Goal: Create reusable quiz templates that can later be run in sessions.
  - Scope: Product/system baseline.
  - Trigger: Admin opens the quiz library.
  - Preconditions: Admin is authenticated.
  -  Minimal guarantees: Invalid templates do not become ready for use.
    Historical reports are not changed by later template edits.
  -  Success guarantees: Published quiz templates have valid questions, valid
    answer options, and a reusable ready state.
  - Main success scenario:
    1. Admin creates a quiz template.
    2. System shows the template in the quiz library.
    3. Admin opens the editor.
    4. Admin adds questions.
    5. Admin adds answer options.
    6. Admin marks correct answers for graded questions.
    7. Admin attaches allowed image files when useful.
    8. Admin publishes the template.
    9. System makes the ready quiz available for session runs.
  -  Alternate flows: Admin edits an existing ready quiz. Admin unpublishes a
    quiz. Admin duplicates a template into a new draft and edits the copy.
    Admin deletes an unused or allowed template. Admin creates a
    poll-style question without a correct answer when the baseline supports that
    mode.
  -  Error/exception flows: Invalid publish attempts show actionable validation.
    Unsupported image extensions are rejected. Oversized uploads are rejected.
    Uploaded files are served with isolation headers. Image content sniffing
    remains deferred.
  -  Postconditions: Ready quiz templates can be queued into a session without
    changing past quiz reports.
  - Frequency/importance: Important before each quiz-enabled event.
  -  Trace links: UN-ADMIN-QUIZZES, UN-ADMIN-REPORTS, FEAT-QUIZ-AUTHOR,
    FR-QUIZ-TEMPLATE, FR-QUIZ-PUBLISH, FR-QUIZ-UPLOAD, FR-QUIZ-VERSION,
    NFR-SEC-UPLOADS, AT-QUIZ-TEMPLATE, AT-QUIZ-PUBLISH, AT-QUIZ-UPLOAD,
    AT-QUIZ-VERSION, JT-QUIZ-HISTORY.

- UC-MOD-RUNROOM
  - Primary actor: Moderator.
  -  Supporting actors/systems: Admin owner, moderator page, session API,
    quiz-run API, Q&A API, feedback API, WebSocket hub.
  - Goal: Run the live room without full admin ownership.
  - Scope: Product/system baseline.
  -  Trigger: Moderator opens a session moderator URL with a valid delegation
    key or owner cookie.
  -  Preconditions: Session exists. Caller has the moderator key or owner admin
    cookie.
  -  Minimal guarantees: Unauthorized callers cannot mutate live state. Failed
    actions do not skip lifecycle rules.
  -  Success guarantees: The moderator can coordinate Q&A, quiz progress,
    feedback visibility, and session state for the room.
  - Main success scenario:
    1. Moderator opens the moderator page.
    2. System validates moderator authority.
    3. Moderator starts the session when the room is ready.
    4. Moderator reviews participant questions.
    5. Moderator responds to or removes questions.
    6. Moderator queues a ready quiz.
    7. Moderator starts the queued quiz run.
    8. Moderator advances through quiz questions.
    9. Moderator reveals results for each question.
    10. Moderator closes the quiz run.
    11. Moderator reviews session feedback summary.
    12. Moderator ends the session after live activity is complete.
  -  Alternate flows: Owning admin uses the same surface through an admin
    cookie. Moderator toggles live answer counts before or during a run.
    Moderator restores a removed question. Moderator deletes a queued or live
    run when permitted.
  -  Error/exception flows: Missing or invalid moderator authority is rejected.
    Owner-only controls remain unavailable to delegated moderators. Ending a
    session with a live quiz run is rejected. Closed run controls do not mutate
    history.
  -  Postconditions: Participant and projector views converge on the
    moderator-controlled state.
  - Frequency/importance: Critical live-event path.
  -  Trace links: UN-MODERATOR-RUN, UN-MODERATOR-QA, UN-MODERATOR-QUIZ,
    FEAT-MOD-DELEGATE, FEAT-QA-LIVE, FEAT-QUIZ-RUN, FEAT-FEEDBACK-RATE,
    FR-MOD-ACCESS, FR-QA-RESPOND, FR-QA-REMOVE, FR-RUN-QUEUE, FR-RUN-PROGRESS,
    FR-FEEDBACK-SUMMARY, AT-MOD-ACCESS, AT-QA-RESPOND, AT-QA-REMOVE,
    AT-RUN-QUEUE, AT-RUN-PROGRESS, AT-FEEDBACK-SUMMARY, JT-ROOM-LIVE.

- UC-PARTICIPANT-QA
  - Primary actor: Participant.
  -  Supporting actors/systems: Participant page, session API, participant
    cookie, Q&A API, WebSocket hub.
  - Goal: Ask and support audience questions anonymously.
  - Scope: Product/system baseline.
  - Trigger: Participant opens a session link.
  -  Preconditions: Session code exists. Browser can store the participant token
    cookie.
  -  Minimal guarantees: Invalid question or vote attempts do not create
    duplicate or corrupt rows.
  -  Success guarantees: Participant can identify themselves within the session,
    submit and resubmit optional profile details including a photograph, ask
    bounded questions, vote once per question, and see participant-visible
    questions sorted by current rules.
  - Main success scenario:
    1. Participant opens a session URL.
    2. System creates or resolves a per-session participant identity.
    3. Participant optionally enters display details and a photograph.
    4. Participant submits the profile.
    5. Participant writes a question.
    6. System stores the question under the session.
    7. System broadcasts a Q&A refresh hint.
    8. Participant views visible questions.
    9. Participant votes for another question.
    10. System updates the visible vote count.
  -  Alternate flows: Participant revisits with the same cookie. Participant
    resubmits, updates, or clears display details or photograph. Participant
    removes a prior vote. Moderator responses appear with the question.
  -  Error/exception flows: Ended sessions are read-only. Empty or oversized
    question text is rejected. Removed questions disappear from participant
    lists. Duplicate vote conflicts resolve to a controlled state.
  -  Postconditions: Participant contribution is visible where policy allows and
    remains anonymous outside session-scoped display details.
  - Frequency/importance: Core audience path.
  -  Trace links: UN-PARTICIPANT-ASK, UN-PARTICIPANT-SUPPORT,
    UN-PARTICIPANT-IDENTITY, FEAT-QA-LIVE, FR-QA-IDENTITY, FR-QA-ASK,
    FR-QA-VOTE, FR-QA-SORT, NFR-PRIVACY-ANON, AT-QA-IDENTITY, AT-QA-ASK,
    AT-QA-VOTE, AT-QA-SORT, JT-ROOM-LIVE.

- UC-PARTICIPANT-QUIZ
  - Primary actor: Participant.
  -  Supporting actors/systems: Moderator, participant page, quiz-run API,
    WebSocket hub.
  - Goal: Answer the current quiz question and understand reveal state.
  - Scope: Product/system baseline.
  - Trigger: Moderator starts or advances a live quiz run.
  - Preconditions: Participant is in a live session with a live quiz run.
  -  Minimal guarantees: A failed submission does not change prior valid
    submissions. Revealed questions do not accept answer changes.
  -  Success guarantees: Participant can submit allowed answers for the current
    question and see results when the moderator reveals them.
  - Main success scenario:
    1. Moderator starts a quiz run.
    2. Participant page refetches live quiz state.
    3. System displays the current question.
    4. Participant selects allowed answer options.
    5. Participant submits the answer.
    6. System stores the participant submission.
    7. Moderator reveals the question result.
    8. System shows aggregate results and correctness state when available.
  -  Alternate flows: Multi-choice submissions may include more than one answer.
    A participant may update an unrevealed answer. Live counts can show
    aggregate counts before reveal when the moderator enables them.
  -  Error/exception flows: Submission without required choices is rejected.
    Submission after reveal is rejected. Submission to a non-live run is
    rejected. Unknown answer IDs are rejected.
  -  Postconditions: The current run has at most one effective participant
    submission per question.
  - Frequency/importance: Core quiz path.
  -  Trace links: UN-PARTICIPANT-QUIZ, FEAT-QUIZ-RUN, FR-RUN-SUBMIT,
    FR-RUN-RESULTS, NFR-RELY-HISTORY, AT-RUN-SUBMIT, AT-RUN-RESULTS,
    JT-ROOM-LIVE, JT-QUIZ-HISTORY.

- UC-PARTICIPANT-FEEDBACK
  - Primary actor: Participant.
  -  Supporting actors/systems: Participant page, feedback API, moderator
    summary view.
  - Goal: Give session feedback without an account.
  - Scope: Product/system baseline.
  - Trigger: Moderator opens the feedback/rating control for the session.
  -  Preconditions: Participant identity is resolved for the session. Moderator
    has enabled participant feedback.
  - Minimal guarantees: Failed feedback writes do not remove prior feedback.
  -  Success guarantees: Participant can submit, update, clear, and confirm
    their own feedback state.
  - Main success scenario:
    1. Moderator enables rating for the session.
    2. Participant page shows the feedback control.
    3. Participant selects a rating.
    4. Participant enters optional feedback text.
    5. System stores the participant feedback for the session.
    6. Participant sees the saved state.
    7. Moderator opens the feedback summary.
    8. System shows aggregate feedback.
  -  Alternate flows: Participant updates a prior rating. Participant clears
    feedback through confirmation. Moderator closes and reopens feedback.
    Moderator views summary after participants submit responses.
  -  Error/exception flows: Feedback submitted before moderator enablement is
    rejected. Invalid rating is rejected. Oversized text is rejected.
    Participant can only mutate their own feedback.
  -  Postconditions: Feedback summary reflects participant-submitted ratings and
    comments allowed by the current baseline.
  - Frequency/importance: Common after training sessions.
  -  Trace links: UN-PARTICIPANT-FEEDBACK, UN-ADMIN-REPORTS, FEAT-FEEDBACK-RATE,
    FR-FEEDBACK-SUBMIT, FR-FEEDBACK-SUMMARY, AT-FEEDBACK-SUBMIT,
    AT-FEEDBACK-SUMMARY, JT-ROOM-LIVE.

- UC-DISPLAY-PROJECTOR
  - Primary actor: Room audience.
  -  Supporting actors/systems: Projector operator, projector page, QR
    generator, session API, quiz-run API, WebSocket hub.
  -  Goal: Follow join instructions, Q&A state, and quiz state from a public
    room display.
  - Scope: Product/system baseline.
  - Trigger: Projector page opens for a session code.
  - Preconditions: Session exists.
  - Minimal guarantees: Projector viewers cannot mutate session data.
  -  Success guarantees: The display shows join information and current session
    state without admin or participant auth.
  - Main success scenario:
    1. Projector operator opens the projector URL.
    2. System shows session title, code, participant URL, and QR code.
    3. System shows top visible questions.
    4. System shows participant count.
    5. Moderator starts a quiz run.
    6. Projector refetches quiz state.
    7. System shows the current quiz question.
    8. Moderator reveals results.
    9. System shows aggregate result state.
    10. Moderator ends the session.
    11. System shows ended-state messaging.
  -  Alternate flows: No quiz is active, so the projector shows lobby or
    non-quiz state. A queued run can show lobby-safe metadata. Live counts
    appear when the moderator enables them.
  -  Error/exception flows: Unknown session codes show safe not-found behavior.
    WebSocket reconnect triggers state refetch. Stale projector recovery after
    missed events remains an important verification path.
  -  Postconditions: Public display reflects the latest visible state allowed by
    the current baseline.
  - Frequency/importance: Core in-room experience.
  -  Trace links: UN-DISPLAY-JOIN, UN-DISPLAY-STATE, FEAT-DISPLAY-ROOM,
    FEAT-LIVE-REFRESH, FR-DISPLAY-JOIN, FR-DISPLAY-QUIZ, FR-LIVE-BROADCAST,
    FR-LIVE-RECONNECT, AT-DISPLAY-JOIN, AT-DISPLAY-QUIZ, AT-LIVE-BROADCAST,
    AT-LIVE-RECONNECT, JT-ROOM-LIVE.

- UC-LIVE-SYNC
  - Primary actor: Browser client.
  - Supporting actors/systems: WebSocket hub, role pages, HTTP APIs.
  -  Goal: Keep admin, moderator, participant, and projector pages synchronized
    after state changes.
  - Scope: Product/system baseline.
  - Trigger: Any state-changing route commits a session-visible change.
  - Preconditions: A role page has opened a WebSocket connection for a session.
  -  Minimal guarantees: Missed or failed socket delivery does not corrupt
    server state.
  -  Success guarantees: Connected clients receive lightweight hints and refetch
    authoritative HTTP state.
  - Main success scenario:
    1. A state-changing action succeeds.
    2. System broadcasts a lightweight event hint to the session room.
    3. Browser client receives the hint.
    4. Browser client refetches affected state through HTTP.
    5. Browser client renders the latest state.
    6. A dropped client reconnects.
    7. Browser client refetches after reconnect.
  -  Alternate flows: Different event kinds may trigger different refetch
    scopes. Slow sockets are evicted. Clients can recover on the next successful
    refetch.
  -  Error/exception flows: WebSocket upgrade for unknown sessions is rejected.
    Network loss enters reconnect backoff. Multiple worker support remains
    outside current baseline.
  -  Postconditions: Browser state converges on server state for the current
    single-process deployment.
  - Frequency/importance: High during live sessions.
  -  Trace links: UN-DISPLAY-STATE, UN-MODERATOR-RUN, FEAT-LIVE-REFRESH,
    FR-LIVE-BROADCAST, FR-LIVE-RECONNECT, NFR-RELY-LIVEUPDATES,
    AT-LIVE-BROADCAST, AT-LIVE-RECONNECT, JT-ROOM-LIVE.

- UC-OPS-DEPLOY
  - Primary actor: Operator.
  -  Supporting actors/systems: Developer workstation, GitHub Actions, GHCR,
    Docker, nginx, SQLite file, uploads directory.
  - Goal: Run, verify, deploy, and preserve a Prashna instance.
  - Scope: Product/system baseline.
  -  Trigger: Operator prepares local development, production-like run, or
    server deployment.
  - Preconditions: Repository checkout exists.
  -  Minimal guarantees: Failed startup or deployment does not erase persistent
    data.
  -  Success guarantees: The operator can run the app locally, build the
    frontend, run verification, configure secrets, deploy the container, and
    identify persistent data paths.
  - Main success scenario:
    1. Operator installs backend dependencies.
    2. Operator installs frontend dependencies.
    3. Operator starts the backend locally.
    4. Operator builds or serves the frontend through the documented path.
    5. Operator runs documented checks.
    6. Operator configures a stable secret key.
    7. Operator configures database and upload paths.
    8. Operator deploys the Docker image behind nginx when using the server kit.
    9. Operator verifies persistent data and upload paths.
    10. Operator backs up both persistent paths.
  -  Alternate flows: Rate limiting can be disabled for controlled tests.
    Trusted proxy hop count can be configured behind nginx. GitHub OAuth can be
    configured for allowlisted admin login.
  -  Error/exception flows: Missing production secret invalidates cookies after
    restart. Private image pulls need GHCR credentials. Existing old-shape
    SQLite databases need additive migration coverage. Push and redeploy remain
    gated on explicit user instruction.
  -  Postconditions: The instance is runnable within the current single-process
    SQLite deployment constraints.
  - Frequency/importance: Critical for release and maintenance.
  -  Trace links: UN-OPS-RUN, UN-OPS-SAFETY, UN-DEVELOPER-CONTRACT,
    FEAT-OPS-BASELINE, FR-OPS-CONFIG, FR-OPS-DEPLOY, FR-OPS-MIGRATE,
    NFR-DATA-PERSISTENCE, NFR-SCHEMA-MIGRATION, NFR-BUILD-CHECKS,
    NFR-DOCS-TRACE, AT-OPS-CONFIG, AT-OPS-DEPLOY, AT-OPS-MIGRATE,
    AT-BUILD-CHECKS, AT-DOCS-TRACE, JT-OPS-RELEASE.

## Functional Requirements

- FR-AUTH-BOOTSTRAP: Prashna shall allow exactly one first-run admin bootstrap.
  - Trace: UC-AUTH-BOOTSTRAP, FEAT-AUTH-ADMIN, AT-AUTH-BOOTSTRAP.
- FR-AUTH-LOGIN: Prashna shall authenticate admins through password credentials.
  - Trace: UC-AUTH-BOOTSTRAP, FEAT-AUTH-ADMIN, AT-AUTH-LOGIN.
-  FR-AUTH-GITHUB: Prashna shall offer allowlisted GitHub admin login when
  configured.
  - Trace: UC-AUTH-BOOTSTRAP, FEAT-AUTH-ADMIN, AT-AUTH-GITHUB.
-  FR-AUTH-PASSWORD: Prashna shall invalidate stale admin sessions after
  password rotation.
  - Trace: UC-AUTH-BOOTSTRAP, FEAT-AUTH-ADMIN, AT-AUTH-PASSWORD.
-  FR-SESSION-CREATE: Prashna shall create owned planning sessions from valid
  admin input.
  - Trace: UC-SESSION-ADMIN, FEAT-SESSION-MANAGE, AT-SESSION-CREATE.
- FR-SESSION-METADATA: Prashna shall keep session metadata owner-controlled.
  - Trace: UC-SESSION-ADMIN, FEAT-SESSION-MANAGE, AT-SESSION-METADATA.
-  FR-SESSION-LIFECYCLE: Prashna shall enforce planning to live to ended session
  transitions.
  - Trace: UC-SESSION-ADMIN, FEAT-SESSION-MANAGE, AT-SESSION-LIFECYCLE.
-  FR-SESSION-DELETE: Prashna shall delete eligible owner sessions only after
  required confirmation.
  - Trace: UC-SESSION-ADMIN, FEAT-SESSION-MANAGE, AT-SESSION-DELETE.
-  FR-MOD-ACCESS: Prashna shall authorize moderator actions through recognized
  live-room credentials.
  - Trace: UC-SESSION-ADMIN, UC-MOD-RUNROOM, FEAT-MOD-DELEGATE, AT-MOD-ACCESS.
-  FR-QA-IDENTITY: Prashna shall resolve a per-session anonymous participant
  identity and update optional profile details and photograph when submitted.
  - Trace: UC-PARTICIPANT-QA, FEAT-QA-LIVE, AT-QA-IDENTITY.
- FR-QA-ASK: Prashna shall store valid participant questions for a live session.
  - Trace: UC-PARTICIPANT-QA, FEAT-QA-LIVE, AT-QA-ASK.
-  FR-QA-VOTE: Prashna shall record one effective participant vote per visible
  question.
  - Trace: UC-PARTICIPANT-QA, FEAT-QA-LIVE, AT-QA-VOTE.
-  FR-QA-SORT: Prashna shall present participant-visible questions by current
  ranking rules.
  - Trace: UC-PARTICIPANT-QA, FEAT-QA-LIVE, AT-QA-SORT.
-  FR-QA-RESPOND: Prashna shall let moderators mark questions responded with
  optional text.
  - Trace: UC-MOD-RUNROOM, FEAT-QA-LIVE, AT-QA-RESPOND.
-  FR-QA-REMOVE: Prashna shall let moderators soft-hide questions from
  participant views.
  - Trace: UC-MOD-RUNROOM, FEAT-QA-LIVE, AT-QA-REMOVE.
- FR-QUIZ-TEMPLATE: Prashna shall let admins maintain reusable quiz templates.
  - Trace: UC-QUIZ-AUTHOR, FEAT-QUIZ-AUTHOR, AT-QUIZ-TEMPLATE.
- FR-QUIZ-PUBLISH: Prashna shall publish only valid quiz templates.
  - Trace: UC-QUIZ-AUTHOR, FEAT-QUIZ-AUTHOR, AT-QUIZ-PUBLISH.
-  FR-QUIZ-UPLOAD: Prashna shall attach accepted uploaded image files to quiz
  content.
  - Trace: UC-QUIZ-AUTHOR, FEAT-QUIZ-AUTHOR, AT-QUIZ-UPLOAD.
-  FR-QUIZ-VERSION: Prashna shall preserve launched quiz versions for historical
  reports.
  - Trace: UC-QUIZ-AUTHOR, FEAT-QUIZ-AUTHOR, AT-QUIZ-VERSION.
-  FR-RUN-QUEUE: Prashna shall queue ready quizzes into sessions for moderator
  control.
  - Trace: UC-MOD-RUNROOM, FEAT-QUIZ-RUN, AT-RUN-QUEUE.
-  FR-RUN-PROGRESS: Prashna shall enforce quiz-run progress through allowed
  moderator transitions.
  - Trace: UC-MOD-RUNROOM, FEAT-QUIZ-RUN, AT-RUN-PROGRESS.
-  FR-RUN-SUBMIT: Prashna shall accept participant submissions only for the
  current answerable question.
  - Trace: UC-PARTICIPANT-QUIZ, FEAT-QUIZ-RUN, AT-RUN-SUBMIT.
-  FR-RUN-RESULTS: Prashna shall show quiz results according to current
  visibility state.
  -  Trace: UC-PARTICIPANT-QUIZ, UC-DISPLAY-PROJECTOR, FEAT-QUIZ-RUN,
    AT-RUN-RESULTS.
-  FR-FEEDBACK-SUBMIT: Prashna shall store participant feedback for the current
  session only after moderator enablement.
  - Trace: UC-PARTICIPANT-FEEDBACK, FEAT-FEEDBACK-RATE, AT-FEEDBACK-SUBMIT.
-  FR-FEEDBACK-SUMMARY: Prashna shall summarize session feedback for moderator
  review.
  -  Trace: UC-PARTICIPANT-FEEDBACK, UC-MOD-RUNROOM, FEAT-FEEDBACK-RATE,
    AT-FEEDBACK-SUMMARY.
- FR-DISPLAY-JOIN: Prashna shall show public join information on the projector.
  - Trace: UC-DISPLAY-PROJECTOR, FEAT-DISPLAY-ROOM, AT-DISPLAY-JOIN.
- FR-DISPLAY-QUIZ: Prashna shall show public quiz state on the projector.
  - Trace: UC-DISPLAY-PROJECTOR, FEAT-DISPLAY-ROOM, AT-DISPLAY-QUIZ.
-  FR-LIVE-BROADCAST: Prashna shall broadcast lightweight live-update hints
  after state changes.
  - Trace: UC-LIVE-SYNC, FEAT-LIVE-REFRESH, AT-LIVE-BROADCAST.
-  FR-LIVE-RECONNECT: Prashna shall refetch browser state after live-update
  reconnect.
  - Trace: UC-LIVE-SYNC, FEAT-LIVE-REFRESH, AT-LIVE-RECONNECT.
-  FR-OPS-CONFIG: Prashna shall expose required runtime configuration through
  documented environment variables.
  - Trace: UC-OPS-DEPLOY, FEAT-OPS-BASELINE, AT-OPS-CONFIG.
- FR-OPS-DEPLOY: Prashna shall provide a documented Docker deployment path.
  - Trace: UC-OPS-DEPLOY, FEAT-OPS-BASELINE, AT-OPS-DEPLOY.
-  FR-OPS-MIGRATE: Prashna shall apply known additive SQLite migration bridges
  at startup.
  - Trace: UC-OPS-DEPLOY, FEAT-OPS-BASELINE, AT-OPS-MIGRATE.

## Non-Functional Requirements

-  NFR-PERF-INTERACTION: Browser-visible participant, moderator, admin, and
  projector interactions shall complete within 1000 ms at p95 for 100 users on
  the current single-process deployment target.
  -  Verification method: representative seeded-room benchmark before public
    release.
-  NFR-CAPACITY-ROOM: The current baseline shall support 100 users in one live
  room on the single-process deployment target.
  - Verification method: load test or rehearsal using seeded participants.
-  NFR-SEC-PASSWORDS: Passwords shall require at least 8 characters and expose
  password hashes to 0 users.
  - Verification method: API tests plus code review.
-  NFR-SEC-HEADERS: Non-upload pages and API payloads shall include the 4
  baseline security headers across at least 4 req samples per class.
  - Verification method: HTTP header tests.
-  NFR-SEC-UPLOADS: Authenticated image uploads shall accept no more than 5 MB
  per file.
  - Verification method: upload API tests.
-  NFR-PRIVACY-ANON: Participant identity shall require account creation from 0
  users.
  - Verification method: API and browser tests.
-  NFR-RELY-LIVEUPDATES: Reconnected live clients shall refetch affected state
  within 5 s of connection restoration.
  - Verification method: WebSocket reconnect integration or browser test.
-  NFR-RELY-HISTORY: Historical quiz reports shall preserve launched content
  across checks representing 2 users after later template edits.
  - Verification method: versioned quiz-run report tests.
-  NFR-ACCESS-KEYBOARD: Core controls shall be keyboard operable across
  role-surface checks representing at least 5 users.
  - Verification method: browser accessibility review and targeted UI tests.
-  NFR-UX-RESPONSIVE: Participant pages shall remain usable across viewport
  checks representing at least 2 users at 360 pixel width.
  - Verification method: mobile viewport browser test and UX review.
-  NFR-ERROR-FEEDBACK: User-visible validation, authorization, lifecycle,
  upload, connectivity, and unexpected failures shall surface safe feedback
  within 1000 ms of detection.
  - Verification method: API and browser error-path tests.
-  NFR-DIAG-SUPPORT: Operator diagnostics shall retain incident-useful auth,
  lifecycle, upload, and live-update context for at least 7 days without raw
  secrets.
  - Verification method: log review and incident drill.
-  NFR-RATE-LIMIT: Protected write paths shall have at least 1 req token-bucket
  capacity per protected key when rate limiting is enabled.
  - Verification method: deterministic limiter tests and endpoint flood tests.
-  NFR-DATA-PERSISTENCE: Production deployments shall preserve the SQLite
  database and uploads within 1 min after container restart.
  - Verification method: deployment smoke check.
-  NFR-SCHEMA-MIGRATION: Known additive SQLite schema changes shall start within
  1 min against an old-shape database fixture.
  - Verification method: old-shape database regression test.
-  NFR-BOOTSTRAP-PUBLIC: Future public deployments shall expose first-admin
  setup to 0 users outside the intended operator path.
  - Current baseline verification: private operator setup review confirms
    public-first bootstrap hardening is deferred.
  - Future verification method: child-spec deployment review and bootstrap
    smoke check.
-  NFR-BUILD-CHECKS: The full local verification suite shall complete within 180
  s on the development workstation.
  - Verification method: documented local command run.
-  NFR-DOCS-TRACE: Behavior-changing work shall update governing behavior docs
  no later than 24 hours after merge.
  - Verification method: docs contract review.

## External Interfaces & Contracts

-  IFACE-HTTP: Browser pages consume JSON HTTP endpoints under `/api`. The
  contract includes success payloads, human-readable error bodies, signed admin
  cookies, moderator-key headers, participant token cookies, validation
  failures, authorization failures, lifecycle failures, upload failures, and
  not-found cases. Real-boundary verification is available through the FastAPI
  app and browser tests.
-  IFACE-WEBSOCKET: Role pages connect to `/ws/sessions/{code}` and
  receive lightweight event hints. Hints are not authoritative model state;
  clients refetch HTTP state after hints and reconnect. Real-boundary
  verification is available through in-process WebSocket tests.
-  IFACE-GITHUB: Optional GitHub login uses GitHub authorization, token,
  and user endpoints when configured. Local tests may mock provider responses;
  live behavior changes require official GitHub documentation review.
-  IFACE-SQLITE: Durable data lives in SQLite through SQLAlchemy models
  plus additive startup migrations. Current baseline does not require Alembic,
  but old-shape fixture coverage is required for known additive changes.
-  IFACE-UPLOADS: Quiz images are stored under the configured uploads
  directory and served from `/uploads/{uuid}.{ext}` with isolation headers.
  Current baseline verifies extension, size, naming, auth, and serving behavior;
  content sniffing is deferred.
-  IFACE-STATIC: Role pages are Vite TypeScript multi-page frontend
  entries. Production serves built assets from `frontend/dist`.
-  IFACE-DOCKER: Server deployment uses a Docker image published to GHCR
  and run behind nginx on the current Hetzner deployment path. Pull credentials
  and persistent paths are operational concerns.

## Acceptance Tests

-  AT-AUTH-BOOTSTRAP: Given a fresh database with no admin, when the operator
  submits valid first-run credentials, then the system creates one admin, issues
  an admin cookie, rejects a second setup attempt, and satisfies
  UC-AUTH-BOOTSTRAP plus FR-AUTH-BOOTSTRAP.
-  AT-AUTH-LOGIN: Given an initialized deployment, when an admin submits valid
  password credentials, then the system authenticates the admin and satisfies
  UC-AUTH-BOOTSTRAP plus FR-AUTH-LOGIN plus NFR-SEC-PASSWORDS.
-  AT-AUTH-GITHUB: Given GitHub OAuth configuration, when an allowlisted GitHub
  user completes callback, then the system creates or resolves the admin
  identity and satisfies UC-AUTH-BOOTSTRAP plus FR-AUTH-GITHUB.
-  AT-AUTH-PASSWORD: Given an authenticated admin, when the password is changed,
  then old admin cookies lose access and satisfy UC-AUTH-BOOTSTRAP plus
  FR-AUTH-PASSWORD.
-  AT-SESSION-CREATE: Given an authenticated admin, when they submit a valid
  title, then a planning session appears in their list and satisfies
  UC-SESSION-ADMIN plus FR-SESSION-CREATE.
-  AT-SESSION-METADATA: Given an owned session, when the admin edits title or
  participant base URL, then valid changes persist and delegated moderators
  cannot perform the edit, satisfying UC-SESSION-ADMIN plus FR-SESSION-METADATA.
-  AT-SESSION-LIFECYCLE: Given a planning session, when the owner starts and
  later ends it, then role pages observe lifecycle state changes and satisfy
  UC-SESSION-ADMIN plus FR-SESSION-LIFECYCLE.
-  AT-SESSION-DELETE: Given a non-live owned session, when the admin completes
  the required confirmation, then eligible session data is removed and satisfies
  UC-SESSION-ADMIN plus FR-SESSION-DELETE.
-  AT-MOD-ACCESS: Given a session moderator URL, when the caller has the
  moderator key or owner cookie, then moderator actions are authorized and
  owner-only actions remain blocked, satisfying UC-MOD-RUNROOM plus
  FR-MOD-ACCESS.
-  AT-QA-IDENTITY: Given a participant opens a session link, when no participant
  token exists or profile details are submitted, then a per-session anonymous
  identity is created or updated with optional text and photograph details,
  satisfying UC-PARTICIPANT-QA plus FR-QA-IDENTITY plus NFR-PRIVACY-ANON.
-  AT-QA-ASK: Given a live session, when a participant submits valid question
  text, then the question becomes visible to participants and satisfies
  UC-PARTICIPANT-QA plus FR-QA-ASK.
-  AT-QA-VOTE: Given a visible question, when a participant toggles support,
  then one effective vote is reflected and satisfies UC-PARTICIPANT-QA plus
  FR-QA-VOTE.
-  AT-QA-SORT: Given multiple visible questions, when their votes or timestamps
  differ, then participant lists follow the current ranking rule and satisfy
  UC-PARTICIPANT-QA plus FR-QA-SORT.
-  AT-QA-RESPOND: Given a participant question, when a moderator marks it
  responded, then the participant-visible response state changes and satisfies
  UC-MOD-RUNROOM plus FR-QA-RESPOND.
-  AT-QA-REMOVE: Given a participant question, when a moderator removes it, then
  participant views hide it while moderator views retain context, satisfying
  UC-MOD-RUNROOM plus FR-QA-REMOVE.
-  AT-QUIZ-TEMPLATE: Given an authenticated admin, when they create and edit a
  quiz template, then the library reflects the template and satisfies
  UC-QUIZ-AUTHOR plus FR-QUIZ-TEMPLATE.
-  AT-QUIZ-PUBLISH: Given a quiz template, when the admin publishes it, then
  invalid structures are rejected and valid structures become ready, satisfying
  UC-QUIZ-AUTHOR plus FR-QUIZ-PUBLISH.
-  AT-QUIZ-UPLOAD: Given an authenticated admin, when an allowed image below the
  size limit is uploaded, then a distinct upload URL is returned and satisfies
  UC-QUIZ-AUTHOR plus FR-QUIZ-UPLOAD plus NFR-SEC-UPLOADS.
-  AT-QUIZ-VERSION: Given a ready quiz that has been launched, when the template
  is later edited, then the historical report keeps launched content and
  satisfies UC-QUIZ-AUTHOR plus FR-QUIZ-VERSION plus NFR-RELY-HISTORY.
-  AT-RUN-QUEUE: Given a ready quiz and live-capable session, when the moderator
  queues the quiz, then a queued run exists and satisfies UC-MOD-RUNROOM plus
  FR-RUN-QUEUE.
-  AT-RUN-PROGRESS: Given a queued quiz run, when the moderator starts,
  advances, reveals, and closes through allowed actions, then invalid source
  states are rejected and UC-MOD-RUNROOM plus FR-RUN-PROGRESS are satisfied.
-  AT-RUN-SUBMIT: Given a live unrevealed quiz question, when a participant
  submits allowed answers, then the submission is stored and satisfies
  UC-PARTICIPANT-QUIZ plus FR-RUN-SUBMIT.
-  AT-RUN-RESULTS: Given a submitted quiz question, when the moderator reveals
  results, then participant or projector results follow reveal and count rules,
  satisfying UC-PARTICIPANT-QUIZ plus FR-RUN-RESULTS.
-  AT-FEEDBACK-SUBMIT: Given moderator-enabled feedback and a participant
  identity, when the participant submits or clears feedback, then their own
  feedback state changes; before moderator enablement, submission is rejected,
  satisfying UC-PARTICIPANT-FEEDBACK plus FR-FEEDBACK-SUBMIT.
-  AT-FEEDBACK-SUMMARY: Given submitted feedback, when a moderator opens the
  summary, then aggregate session feedback appears and satisfies
  UC-PARTICIPANT-FEEDBACK plus FR-FEEDBACK-SUMMARY.
-  AT-DISPLAY-JOIN: Given a valid projector URL, when the page loads, then
  title, code, participant URL, and QR join information appear, satisfying
  UC-DISPLAY-PROJECTOR plus FR-DISPLAY-JOIN.
-  AT-DISPLAY-QUIZ: Given a live quiz run, when quiz state changes, then
  projector quiz content reflects current public state and satisfies
  UC-DISPLAY-PROJECTOR plus FR-DISPLAY-QUIZ.
-  AT-LIVE-BROADCAST: Given a session-visible state change, when the change
  commits, then connected role pages receive a hint and refetch state,
  satisfying UC-LIVE-SYNC plus FR-LIVE-BROADCAST.
-  AT-LIVE-RECONNECT: Given a role page loses its socket, when the socket
  reconnects, then the page refetches within 5 s and satisfies UC-LIVE-SYNC plus
  FR-LIVE-RECONNECT plus NFR-RELY-LIVEUPDATES.
-  AT-OPS-CONFIG: Given a private operator deployment, when required variables
  are set, then secret key, data path, upload path, proxy trust, rate-limit,
  OAuth behavior, and private bootstrap expectations match configuration,
  satisfying UC-OPS-DEPLOY plus FR-OPS-CONFIG.
-  AT-OPS-DEPLOY: Given the documented deploy kit, when the operator follows the
  Docker path, then the service starts behind nginx and satisfies UC-OPS-DEPLOY
  plus FR-OPS-DEPLOY plus NFR-DATA-PERSISTENCE.
-  AT-OPS-MIGRATE: Given an old-shape SQLite fixture for a known additive
  change, when the app starts, then the bridge completes within 1 min and
  satisfies UC-OPS-DEPLOY plus FR-OPS-MIGRATE plus NFR-SCHEMA-MIGRATION.
-  AT-BUILD-CHECKS: Given a development checkout, when local verification
  commands run, then they complete within 180 s and satisfy UC-OPS-DEPLOY plus
  NFR-BUILD-CHECKS.
-  AT-DOCS-TRACE: Given a behavior-changing change, when it is prepared for
  merge, then governing behavior docs are updated within 1 days and satisfy
  UC-OPS-DEPLOY plus NFR-DOCS-TRACE.
-  AT-NFR-RATE: Given rate limiting is enabled, when protected paths are flooded
  from one key, then throttling occurs after configured capacity and satisfies
  UC-OPS-DEPLOY plus NFR-RATE-LIMIT.
-  AT-NFR-ACCESS: Given core role surfaces, when keyboard-only checks run, then
  primary controls are operable and satisfy UC-DISPLAY-PROJECTOR plus
  NFR-ACCESS-KEYBOARD.
-  AT-NFR-ERRORS: Given validation, authorization, lifecycle, upload,
  connectivity, or unexpected failure cases, when they occur, then safe user
  feedback appears within 1000 ms and satisfies UC-MOD-RUNROOM plus
  NFR-ERROR-FEEDBACK.

## Journey Tests

-  JT-ROOM-LIVE: Sequence: AT-AUTH-BOOTSTRAP, AT-SESSION-CREATE,
  AT-SESSION-LIFECYCLE, AT-MOD-ACCESS, AT-QA-IDENTITY, AT-QA-ASK, AT-QA-VOTE,
  AT-QA-RESPOND, AT-RUN-QUEUE, AT-RUN-PROGRESS, AT-RUN-SUBMIT, AT-RUN-RESULTS,
  AT-DISPLAY-JOIN, AT-DISPLAY-QUIZ, AT-FEEDBACK-SUBMIT, and AT-FEEDBACK-SUMMARY.
  Actors/systems: admin, moderator, participant, projector, APIs, WebSocket hub.
  State carried: session code, moderator key, participant token, quiz run,
  feedback record. Final oracle: check that ended session state, Q&A state, quiz
  result state, projector state, and feedback summary remain coherent.
-  JT-QUIZ-HISTORY: Sequence: AT-QUIZ-TEMPLATE, AT-QUIZ-PUBLISH, AT-QUIZ-UPLOAD,
  AT-RUN-QUEUE, AT-RUN-PROGRESS, AT-RUN-SUBMIT, AT-RUN-RESULTS, and
  AT-QUIZ-VERSION. Actors/systems: admin, moderator, participants, quiz library,
  report view. State carried: quiz template, quiz version, quiz run,
  submissions. Final oracle: verify historical report content remains stable
  after template edits.
-  JT-OPS-RELEASE: Sequence: AT-OPS-CONFIG, AT-BUILD-CHECKS, AT-OPS-MIGRATE,
  AT-OPS-DEPLOY, AT-AUTH-BOOTSTRAP, AT-AUTH-LOGIN, AT-LIVE-BROADCAST, and
  AT-LIVE-RECONNECT. Actors/systems: developer, operator, Docker host, browser
  clients. State carried: environment variables, database path, uploads path,
  admin cookie, session code. Final oracle: verify a production-like instance
  starts, preserves persistent data, authenticates, and recovers browser state
  within the current single-process constraints.

## Assumptions & Open Questions

### Source Reconciliation Notes

-  Current governing source: `docs/specs.md` and `docs/UX.md` remain governing
  behavior sources until superseded by approved Sarathi child artifacts.
-  Adopted source: `README.md`, `CLAUDE.md`, tests, deploy docs, and current
  code are accepted as baseline evidence.
-  Adapted source: Route and schema details from code are represented here as
  external behavior or constraints, not as internal design.
-  Historical one-off evidence informed the baseline but is intentionally
  local-only and does not govern current behavior.
-  Engineering follow-up ledger: `docs/todo.md` contains active implementation
  and operational follow-ups; product decisions stay in the deferred appendix
  of `docs/specs.md`.

### Assumptions

-  Project Entry Mode: Brownfield Baseline Adoption, decided by the user on
  2026-07-03.
-  This product/system SRS is Decomposable; child feature/component or
  slice/change specs are needed before new code work.
-  UI Mock Preference: Deferred. The app has current implemented pages and
  `docs/UX.md`; future UI-facing child specs must choose Required, Optional, Not
  needed, or Deferred.
-  GitHub OAuth can be mocked locally for baseline tests; behavior changes
  should check official GitHub documentation.
-  Current scale target is a single-process deployment using SQLite and an
  in-memory WebSocket hub.

### Open Questions

-  Future delta: public or hosted bootstrap must choose a setup token, CLI
  bootstrap, private bootstrap mode, or another operator-only flow before it
  becomes current baseline scope.
-  Should upload content sniffing become current baseline before less-trusted
  operators can upload images?
-  Should server-side `image_url` validation restrict quiz image references to
  uploaded file URLs?
- Should ended sessions or closed quiz runs gain reopen flows?
- Should per-question timers or auto-advance become quiz-run features?
-  Should CHECK constraints, Alembic, or a richer migration workflow become
  release gates?
-  Should multi-moderator audit columns become part of delegate moderator
  support?
- When should the temporary legacy admin cookie parsing shim be removed?

## Traceability

- Need: UN-PARTICIPANT-ASK
  - Scope Boundary: Anonymous session-scoped participation
  - Features: FEAT-QA-LIVE
  - Use Cases: UC-PARTICIPANT-QA
  - Requirements: FR-QA-IDENTITY, FR-QA-ASK
  - Acceptance: AT-QA-IDENTITY, AT-QA-ASK
  - Journey: JT-ROOM-LIVE
  - Priority/Risk: High core audience value
- Need: UN-PARTICIPANT-SUPPORT
  - Scope Boundary: One effective vote per participant
  - Features: FEAT-QA-LIVE
  - Use Cases: UC-PARTICIPANT-QA
  - Requirements: FR-QA-VOTE, FR-QA-SORT
  - Acceptance: AT-QA-VOTE, AT-QA-SORT
  - Journey: JT-ROOM-LIVE
  - Priority/Risk: High live prioritization value
- Need: UN-PARTICIPANT-IDENTITY
  - Scope Boundary: Optional per-session display identity
  - Features: FEAT-QA-LIVE
  - Use Cases: UC-PARTICIPANT-QA
  - Requirements: FR-QA-IDENTITY
  - Acceptance: AT-QA-IDENTITY
  - Journey: JT-ROOM-LIVE
  - Priority/Risk: Medium UX value
- Need: UN-PARTICIPANT-QUIZ
  - Scope Boundary: Current live question only
  - Features: FEAT-QUIZ-RUN
  - Use Cases: UC-PARTICIPANT-QUIZ
  - Requirements: FR-RUN-SUBMIT, FR-RUN-RESULTS
  - Acceptance: AT-RUN-SUBMIT, AT-RUN-RESULTS
  - Journey: JT-ROOM-LIVE, JT-QUIZ-HISTORY
  - Priority/Risk: High correctness risk
- Need: UN-PARTICIPANT-FEEDBACK
  - Scope Boundary: Session feedback per participant
  - Features: FEAT-FEEDBACK-RATE
  - Use Cases: UC-PARTICIPANT-FEEDBACK
  - Requirements: FR-FEEDBACK-SUBMIT
  - Acceptance: AT-FEEDBACK-SUBMIT
  - Journey: JT-ROOM-LIVE
  - Priority/Risk: Medium learning value
- Need: UN-MODERATOR-RUN
  - Scope Boundary: Delegated live control only
  - Features: FEAT-MOD-DELEGATE, FEAT-LIVE-REFRESH
  - Use Cases: UC-MOD-RUNROOM, UC-LIVE-SYNC
  - Requirements: FR-MOD-ACCESS, FR-LIVE-BROADCAST, FR-LIVE-RECONNECT
  - Acceptance: AT-MOD-ACCESS, AT-LIVE-BROADCAST, AT-LIVE-RECONNECT
  - Journey: JT-ROOM-LIVE
  - Priority/Risk: High authorization risk
- Need: UN-MODERATOR-QA
  - Scope Boundary: Soft moderation preserves audit context
  - Features: FEAT-QA-LIVE
  - Use Cases: UC-MOD-RUNROOM
  - Requirements: FR-QA-RESPOND, FR-QA-REMOVE
  - Acceptance: AT-QA-RESPOND, AT-QA-REMOVE
  - Journey: JT-ROOM-LIVE
  - Priority/Risk: Medium live-event risk
- Need: UN-MODERATOR-QUIZ
  - Scope Boundary: Controlled quiz run lifecycle
  - Features: FEAT-QUIZ-RUN
  - Use Cases: UC-MOD-RUNROOM
  - Requirements: FR-RUN-QUEUE, FR-RUN-PROGRESS
  - Acceptance: AT-RUN-QUEUE, AT-RUN-PROGRESS
  - Journey: JT-ROOM-LIVE, JT-QUIZ-HISTORY
  - Priority/Risk: High historical correctness risk
- Need: UN-ADMIN-BOOTSTRAP
  - Scope Boundary: Private operator bootstrap baseline
  - Features: FEAT-AUTH-ADMIN
  - Use Cases: UC-AUTH-BOOTSTRAP
  -  Requirements: FR-AUTH-BOOTSTRAP, FR-AUTH-LOGIN, FR-AUTH-GITHUB,
    FR-AUTH-PASSWORD
  -  Acceptance: AT-AUTH-BOOTSTRAP, AT-AUTH-LOGIN, AT-AUTH-GITHUB,
    AT-AUTH-PASSWORD
  - Journey: JT-OPS-RELEASE
  - Priority/Risk: High deployment risk
- Need: UN-ADMIN-SESSIONS
  - Scope Boundary: Owner-only session management
  - Features: FEAT-SESSION-MANAGE
  - Use Cases: UC-SESSION-ADMIN
  -  Requirements: FR-SESSION-CREATE, FR-SESSION-METADATA, FR-SESSION-LIFECYCLE,
    FR-SESSION-DELETE
  -  Acceptance: AT-SESSION-CREATE, AT-SESSION-METADATA, AT-SESSION-LIFECYCLE,
    AT-SESSION-DELETE
  - Journey: JT-ROOM-LIVE
  - Priority/Risk: High owner-boundary risk
- Need: UN-ADMIN-QUIZZES
  - Scope Boundary: Reusable templates
  - Features: FEAT-QUIZ-AUTHOR
  - Use Cases: UC-QUIZ-AUTHOR
  - Requirements: FR-QUIZ-TEMPLATE, FR-QUIZ-PUBLISH, FR-QUIZ-UPLOAD
  - Acceptance: AT-QUIZ-TEMPLATE, AT-QUIZ-PUBLISH, AT-QUIZ-UPLOAD
  - Journey: JT-QUIZ-HISTORY
  - Priority/Risk: Medium authoring risk
- Need: UN-ADMIN-REPORTS
  - Scope Boundary: Stable history
  - Features: FEAT-QUIZ-AUTHOR, FEAT-FEEDBACK-RATE
  - Use Cases: UC-QUIZ-AUTHOR, UC-PARTICIPANT-FEEDBACK
  - Requirements: FR-QUIZ-VERSION, FR-FEEDBACK-SUMMARY
  - Acceptance: AT-QUIZ-VERSION, AT-FEEDBACK-SUMMARY
  - Journey: JT-QUIZ-HISTORY
  - Priority/Risk: High trust risk
- Need: UN-DISPLAY-JOIN
  - Scope Boundary: Public room join info
  - Features: FEAT-DISPLAY-ROOM
  - Use Cases: UC-DISPLAY-PROJECTOR
  - Requirements: FR-DISPLAY-JOIN
  - Acceptance: AT-DISPLAY-JOIN
  - Journey: JT-ROOM-LIVE
  - Priority/Risk: High in-room usability
- Need: UN-DISPLAY-STATE
  - Scope Boundary: Public live state
  - Features: FEAT-DISPLAY-ROOM, FEAT-LIVE-REFRESH
  - Use Cases: UC-DISPLAY-PROJECTOR, UC-LIVE-SYNC
  - Requirements: FR-DISPLAY-QUIZ, FR-LIVE-BROADCAST, FR-LIVE-RECONNECT
  - Acceptance: AT-DISPLAY-QUIZ, AT-LIVE-BROADCAST, AT-LIVE-RECONNECT
  - Journey: JT-ROOM-LIVE
  - Priority/Risk: High stale-state risk
- Need: UN-OPS-RUN
  - Scope Boundary: Repeatable run and deploy
  - Features: FEAT-OPS-BASELINE
  - Use Cases: UC-OPS-DEPLOY
  - Requirements: FR-OPS-CONFIG, FR-OPS-DEPLOY
  - Acceptance: AT-OPS-CONFIG, AT-OPS-DEPLOY
  - Journey: JT-OPS-RELEASE
  - Priority/Risk: High release risk
- Need: UN-OPS-SAFETY
  - Scope Boundary: Secrets, data, uploads, bootstrap, migration
  - Features: FEAT-OPS-BASELINE
  - Use Cases: UC-OPS-DEPLOY
  - Requirements: FR-OPS-MIGRATE, FR-AUTH-BOOTSTRAP
  - Acceptance: AT-OPS-MIGRATE, AT-NFR-RATE, AT-NFR-ERRORS
  - Journey: JT-OPS-RELEASE
  - Priority/Risk: High production risk
- Need: UN-DEVELOPER-CONTRACT
  - Scope Boundary: Docs stay aligned with tests
  - Features: FEAT-OPS-BASELINE
  - Use Cases: UC-OPS-DEPLOY
  - Requirements: FR-OPS-CONFIG
  - Acceptance: AT-DOCS-TRACE, AT-BUILD-CHECKS
  - Journey: JT-OPS-RELEASE
  - Priority/Risk: Medium maintainability risk
