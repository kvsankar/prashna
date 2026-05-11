# Prashna

A minimal live Q&A and quiz tool for any session with an audience — training, lectures, workshops, town halls, meetups. "Prashna" (प्रश्न) is Sanskrit for *question*.

Two features, kept small on purpose:

- **Anonymous Q&A** with upvoting, moderator answers, and a projector view
- **Moderator-conducted quizzes** with single- or multi-choice questions, optional images, anonymous voting, live results

## Quick start

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000>.

To change the admin key used for quiz authoring:

```bash
PRASHNA_ADMIN_KEY=your-secret uv run uvicorn app.main:app --reload --port 8000
```

(Default is `admin`.)

## Concepts

| Concept        | What it is                                                       |
| -------------- | ---------------------------------------------------------------- |
| `Session`      | A live training session. Has a short join code and a moderator key. |
| `Question`     | Anonymous question posted in a session. Has votes and an optional moderator answer. |
| `Quiz`         | A reusable quiz template, authored in the quiz library.          |
| `QuizQuestion` | One question in a `Quiz`. Single- or multi-choice. May have an image. |
| `QuizOption`   | One option of a `QuizQuestion`. May be marked correct. May have an image. |
| `QuizSession`  | A *running instance* of a `Quiz` inside a `Session`. Has status `draft` → `live` → `closed`. |
| `QuizResponse` | A voter's selection of one option for one question in a `QuizSession`. |

A `Quiz` is a template you author once. You launch it as a `QuizSession` inside any session, possibly multiple times across different audiences.

## URLs

| View        | Path                  | Notes                                              |
| ----------- | --------------------- | -------------------------------------------------- |
| Home        | `/`                   | Join a session by code or create one as moderator. |
| Participant | `/s/<code>`           | Ask questions, upvote, answer the live quiz.       |
| Moderator   | `/m/<code>#k=<key>`   | Moderator URL embeds the session secret in the fragment. |
| Projector   | `/p/<code>`           | Read-only big-screen view.                          |
| Quiz library| `/quizzes`            | Author/edit quiz templates. Needs admin key.        |

Creating a new session on the home page prints all three links plus the moderator key. **Keep the moderator URL private** — anyone with it has moderator rights for that session.

## Identity model

- **Participants are anonymous.** A `voter_token` cookie is set on first interaction and used to enforce "one upvote per question" and "one answer per quiz question". They can optionally add a display name when asking a question; clearing the name reverts to anonymous.
- **Moderators** authenticate per session via a 16-char `mod_key` returned at session creation. The moderator page reads it from the URL fragment on first visit and stores it in `localStorage`.
- **Quiz authoring** is gated by a single global `PRASHNA_ADMIN_KEY` env var. The browser prompts for it on first visit to `/quizzes`.

## Live updates

The frontend opens a WebSocket to `/ws/sessions/<code>`. Every state-changing action broadcasts a short `{ "type": "..." }` event into the room; clients use the event as a hint and refetch the resources they care about. No diff payloads, no client-side reducers — the goal is to stay easy to read.

## API surface

REST under `/api/`:

- `POST /api/sessions` — create a session, returns `{code, title, mod_key}`
- `GET /api/sessions/{code}` — public session info
- `GET|POST /api/sessions/{code}/questions` — list / create
- `POST /api/sessions/{code}/questions/{qid}/vote` — toggle upvote
- `POST /api/sessions/{code}/questions/{qid}/answer` — moderator answers (or reopens) a question
- `POST /api/sessions/{code}/questions/{qid}/hide` — moderator hides a question from participants
- `DELETE /api/sessions/{code}/questions/{qid}` — moderator deletes a question
- `GET|POST /api/quizzes`, `GET|PATCH|DELETE /api/quizzes/{id}` — quiz CRUD
- `POST /api/quizzes/{id}/questions`, `PATCH|DELETE /api/quiz_questions/{qq_id}` — quiz question CRUD
- `POST /api/quiz_questions/{qq_id}/options`, `PATCH|DELETE /api/quiz_options/{op_id}` — option CRUD
- `POST /api/uploads` — image upload (5 MB, common image types)
- `GET|POST /api/sessions/{code}/quiz_sessions` — list / launch a quiz template in a session
- `POST /api/sessions/{code}/quiz_sessions/{qs_id}/start|advance|reveal|close` — moderator controls
- `GET /api/sessions/{code}/quiz_sessions/{qs_id}` — current state (current question, my selections, results if revealed)
- `POST /api/sessions/{code}/quiz_sessions/{qs_id}/respond` — participant submits selection(s) for the current question

WebSocket: `GET /ws/sessions/{code}` — connect to receive `{ type }` events.

## Project layout

```
app/
  main.py        FastAPI app + all routes + WebSocket
  models.py      SQLAlchemy models
  db.py          engine, session factory, init_db
  ws.py          in-memory room/broadcast hub
static/
  index.html, participant.html, moderator.html, projector.html, quizzes.html
  common.js, app.css
uploads/         user-uploaded images (gitignored)
prashna.db         SQLite database (created on first run, gitignored)
```

## Status

This is a small reference codebase, not a product. Things deliberately omitted:

- No tests yet
- No migrations (the schema rebuilds on startup; delete `prashna.db` if a model changes incompatibly)
- No real auth — moderator keys are random tokens, quiz authoring uses a shared admin key
- No CSRF protection; intended for trusted environments only
- No build step on the frontend
