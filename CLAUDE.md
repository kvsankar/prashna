# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**Prashna** — a minimal live Q&A + quiz tool for training sessions, lectures, workshops, or any group gathering that needs audience interaction. Built to be readable as a small reference codebase, not a production product. Keep code clear and small; resist adding frameworks, abstractions, or features beyond what's actually needed.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2 (sync), SQLite. Single-process. WebSockets for live broadcast.
- **Frontend:** Vanilla JS ES modules, no build step. Plain HTML + CSS. One page per role.
- **Tooling:** `uv` for dependency management. No test suite yet.

## Layout

```
app/
  main.py        # all FastAPI routes + WebSocket endpoint
  models.py      # SQLAlchemy models
  db.py          # engine, SessionLocal, get_db, init_db
  ws.py          # in-memory pub/sub hub keyed by session code
static/
  index.html     # landing — join or create a session
  participant.html
  moderator.html
  projector.html
  quizzes.html   # quiz template authoring
  common.js      # shared helpers (api, el, ws, key storage)
  app.css        # shared styles
uploads/         # user-uploaded images (gitignored)
prashna.db         # SQLite database (gitignored, created on first run)
```

## Run

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Admin key for quiz authoring defaults to `admin`; override with `PRASHNA_ADMIN_KEY=...` in the environment.

## Conventions

- **Auth model**
  - Participants: anonymous, identified by `voter_token` cookie set on first interaction.
  - Moderator: per-session secret `mod_key` passed via `X-Mod-Key` header. Embedded in the moderator URL hash as `#k=<key>` and persisted to `localStorage` keyed by session code.
  - Quiz authoring: a global `PRASHNA_ADMIN_KEY` env var, passed as `X-Admin-Key`. Persisted to `localStorage` under `admin_key`.
- **Data model semantics**
  - `Quiz` is a reusable *template*. `QuizSession` is a *running instance* of a quiz bound to a `Session`. Don't conflate them.
  - `QuizQuestion.qtype` is `"single"` or `"multi"`. For `multi`, a voter creates one `QuizResponse` row per selected option.
  - Re-submitting a quiz answer deletes the voter's previous `QuizResponse` rows for that question and inserts new ones — last write wins.
  - Question votes use `UniqueConstraint(question_id, voter_token)` so each voter contributes at most one upvote.
- **Live updates** — any state-changing route ends by broadcasting `{type: "..."}` to the `session:<CODE>` room. Clients use the type as a hint to refetch rather than as a diff payload. Keep payloads small and event-typed; do not stream model state through the socket.
- **Routes file** — `app/main.py` is intentionally one file. If it grows, split by resource (sessions, questions, quizzes, quiz_sessions, uploads) rather than by HTTP method.
- **No build step on the frontend** — don't introduce React/Vite/TypeScript without checking first. The goal is to keep the frontend readable end-to-end in the browser.
- **Database migrations** — none. `init_db()` calls `create_all` on startup. If a model changes in a breaking way, delete `prashna.db` and recreate.

## Things to be careful about

- The moderator URL contains a secret in the fragment (`#k=...`). Don't log full URLs server-side and don't print mod_key to stdout outside the creation response.
- `init_db` runs in `@app.on_event("startup")` — that hook is deprecated in newer FastAPI. If touching startup, consider the lifespan API but verify the rest still works.
- Image uploads write to `uploads/` and are served via `StaticFiles`. The 5 MB cap and extension allowlist are the only validation — keep them.
- `voter_token` is set as a non-HttpOnly cookie on purpose so the frontend can read it for "mine" checks. Don't change to HttpOnly without rethinking the UI.

## When the user asks for changes

- Prefer editing existing files. Don't add new modules unless the change clearly doesn't fit.
- Don't introduce a frontend build pipeline, ORM migrations, auth library, or testing framework without explicit ask.
- This codebase is used live in sessions with real audiences. Sweeping refactors mid-event are a problem; prefer additive, reversible changes.
