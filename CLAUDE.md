# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**Prashna** — live Q&A + quiz tool for training sessions, lectures, and
workshops. Heading toward open-source release **and** a hosted SaaS;
not just a reference codebase. Keep code clear and small; resist
adding frameworks, abstractions, or features beyond what's actually
needed. Bias toward additive, reversible changes — the app is used
live with real audiences.

Authoritative docs in `docs/`:

- **`docs/specs.md`** — Use-case spec for all five surfaces (Admin /
  Moderator / Participant / Projector / System). Each UC has
  Given/When/Then ACs **and** `Tests (API)` / `Tests (UI)` bullets
  that map 1:1 to pytest + Playwright tests. Update when behavior
  changes. Read the **Conventions used by the Tests blocks** section
  for cross-cutting auth/error-message conventions.
- **`docs/UX.md`** — Frontend design system. Compact-table, drill-down,
  card-head, CRUD verbs, status badges, etc. Read before touching
  any HTML/CSS.

## Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2 (sync), SQLite.
  Single-process. WebSockets for live broadcast.
- **Frontend:** Vanilla JS ES modules, no build step. Plain HTML +
  CSS. One page per role.
- **Auth:** bcrypt password hashing + `itsdangerous`-signed session
  cookie for admin; `mod_key` URL fragment for delegate moderators;
  `voter_token` cookie for anonymous participants.
- **Tests:** pytest + httpx (API) + Playwright Python (UI).
  ~350 tests against `docs/specs.md`. Run with `uv run pytest`.
- **Tooling:** `uv` for dependency management.

## Layout

```
app/
  main.py        # all FastAPI routes + WebSocket endpoint
  models.py      # SQLAlchemy models
  auth.py        # password hashing + signed cookie helpers
  db.py          # engine, SessionLocal, get_db, init_db
  ws.py          # in-memory pub/sub hub keyed by session code
static/
  index.html     # landing — admin setup / login / session list
  participant.html
  moderator.html
  projector.html
  quizzes.html   # quiz template authoring
  common.js      # shared helpers (api, el, toast, ws, modKey)
  app.css        # shared styles
  vendor/qrcode.js  # vendored QR generator (MIT, Kazuhiko Arase)
docs/
  specs.md       # use cases + AT bullets — authoritative
  UX.md          # frontend design system — authoritative
tests/
  conftest.py    # shared env setup
  api/           # pytest + httpx tests
  ui/            # Playwright tests
deploy/
  docker-compose.yml, nginx-prashna.conf, setup.sh, ...
uploads/         # user-uploaded images (gitignored)
prashna.db       # SQLite database (gitignored, created on first run)
```

## Run

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Environment:

- `PRASHNA_SECRET_KEY` — signs admin session cookies. **Production
  must set this** to a long random string; without it, cookies die
  on every process restart (UC-X-07).
- `PRASHNA_DB_PATH` — override DB location (default
  `<repo>/prashna.db`). Used by Docker + tests.
- `PRASHNA_UPLOADS_DIR` — override uploads dir (default
  `<repo>/uploads`).
- `PRASHNA_TRUSTED_PROXY_HOPS` — number of trusted reverse-proxy hops
  for client-IP resolution (rate limiting). Default `0` (socket peer).
  Set `1` behind ngrok or the bundled nginx so per-IP limits key on the
  real client, not a spoofable `X-Forwarded-For` prefix (UC-X-08).
- `PRASHNA_RATELIMIT` — set to `off` (also `0`/`false`/`no`) to disable
  rate limiting entirely. On by default (UC-X-08).
- `PRASHNA_GITHUB_CLIENT_ID` / `PRASHNA_GITHUB_CLIENT_SECRET` /
  `PRASHNA_GITHUB_ADMINS` — enable GitHub OAuth admin login when all
  three are set; `_ADMINS` is a comma-separated GitHub-login allowlist.
  OAuth App callback: `https://<host>/api/auth/github/callback`
  (UC-A-26).

Tests:

```bash
uv run pytest               # full suite (~2 min, 350 tests)
uv run pytest tests/api/    # API only (fast, ~1 min)
uv run pytest tests/ui/     # UI only (Playwright, ~1 min)
```

## Roles & entities

Five surfaces (`UC-A-*` Admin, `UC-M-*` Moderator, `UC-P-*`
Participant, `UC-D-*` Projector/Display, `UC-X-*` System). Admin
capabilities are a strict **superset** of Moderator — admin owners
reach moderator routes via their cookie without needing the
`mod_key`. `mod_key` is the **delegation** mechanism (give the URL
to a TA / co-host without an admin account).

Entity names (after the renames):

- `User` — the admin (single global today; SSO-based multi-admin
  later).
- `Session` — the live event. Lifecycle: `planning → live → ended`.
- `Participant` — per-session row keyed by `voter_token` cookie.
- `Query` — a participant-asked Q&A entry. Moderator marks it
  *responded* (with optional text) or *removed* (soft-hide).
  Each `Query` has `QueryVote`s (one per participant).
- `Quiz` — reusable template owned by a `User`. Lifecycle:
  `draft → ready`. Has many `Question`s, each with many `Answer`s.
- `QuizVersion` — immutable snapshot of a `Quiz` captured lazily on
  Launch when the editable tree has changed since the last
  version. `QuizVersionQuestion` / `QuizVersionAnswer` are the
  frozen copies that historical `QuizRun`s reference.
- `QuizRun` — one playthrough of a `QuizVersion` inside a `Session`.
  Lifecycle: `queued → live → closed`. Owns `QuizSubmission`s
  (the participants' selected answers).

Don't conflate `Question` (quiz template) with `Query` (Q&A board).
Don't conflate `QuizRun` (playthrough) with `Session` (the gathering).

## Conventions

### Auth model
- **Admin** — bcrypt password, signed cookie. First-run setup
  creates the only admin row; `POST /api/admin/setup` returns 409
  thereafter (UC-A-01).
- **Admin via GitHub OAuth** — optional, allowlisted sign-in for
  hosted deploys (UC-A-26, `app/oauth.py`). Enabled when
  `PRASHNA_GITHUB_CLIENT_ID` / `_CLIENT_SECRET` / `_ADMINS` are set.
  Runs **alongside** password login (fallback). The callback
  find-or-creates a `User` keyed by `User.github_id`; such users have
  `password_hash=""` and can't password-login. Issues the same signed
  cookie. Don't make GitHub the *only* admin path without an ask.
- **Moderator** — `mod_key` (16-char hex) per Session. Passed via
  `X-Mod-Key` header. Moderator routes accept **either** admin
  cookie (owner) **or** `mod_key` via `require_mod_or_owner`.
  Frontend extracts `mod_key` from `#k=…` URL fragment and persists
  it to `localStorage` under the session code.
- **Participant** — anonymous `voter_token` cookie (non-HttpOnly on
  purpose; frontend reads it for "mine" checks). Resolves to a
  per-session `Participant` row.

### CRUD shape
Reflected in `docs/UX.md`. Inline `+ New` composer in card-tools;
persist on blur (no Save button for single fields); explicit named
verb buttons for status transitions (`Publish`, `Start`, `Close`,
`Mark responded`, `Remove`). Error wording on backend is the
authoritative string — frontend just surfaces.

### Live updates
Every state-changing route ends with
`broadcast_session(s, "<kind>")`. Clients use the type as a hint
to refetch — never stream model state through the socket. Kinds
listed in UC-X-01.

### Versioning protects history
A `QuizRun` always references a `QuizVersion` (frozen). Editing a
`Quiz` template after a run was launched does **not** affect that
run's historical view. New versions are captured lazily on Launch
when `quiz.last_edited_at > latest_version.created_at`. Status
stays `ready` across edits (does not auto-revert).

### Database migrations
None. `init_db()` calls `create_all` at startup (via the FastAPI
lifespan context manager). If a model changes in a breaking way,
delete `prashna.db` and recreate. Pre-launch — no data to preserve
yet.

### Routes file
`app/main.py` is intentionally one file. If it grows past ~1500
lines and needs splitting, split by resource (sessions, queries,
quizzes, quiz_runs, uploads, admin) rather than by HTTP method.

### Frontend
- No build step. Don't introduce React/Vite/TypeScript without
  asking.
- Selectors should be stable IDs (`#new-session-title`, `#sd-base-url`)
  or documented classes (`.badge-live`, `.option`, `.question`).
- Toast for transient errors, banner for sticky ones, redirect for
  auth expiry. Never `alert()`/`prompt()` in new code.

## Things to be careful about

- The moderator URL contains a secret in the fragment (`#k=...`).
  Don't log full URLs server-side and don't print `mod_key` to
  stdout outside the creation response. The landing page's
  "Share moderator URL" button is the only path that exposes it
  (clipboard copy on demand, not baked into the DOM).
- Image uploads write to `uploads/` and are served via
  `StaticFiles` with strict CSP / nosniff / CORP headers
  (UC-X-03). The 5 MB cap and extension allowlist are the only
  validation — keep them. SVG is explicitly excluded.
- `voter_token` is a non-HttpOnly cookie on purpose so the frontend
  can do "mine" checks. Don't change to HttpOnly without rethinking
  the UI.
- The partial unique index `uq_session_live_run` enforces
  "at most one live QuizRun per Session" at the DB layer. Backend
  catches `IntegrityError` → 409. Don't remove this; race-fixing
  via app-level checks alone won't survive SQLite single-writer
  ordering.

## Tests are the contract

`docs/specs.md` + `tests/` are the source of truth. When you
change behavior:

1. Update `docs/specs.md` first (the UC's prose **and** the
   `Tests (API)` / `Tests (UI)` bullets).
2. Update or add tests in `tests/api/` and/or `tests/ui/`.
3. Implement the change.
4. Run `uv run pytest` and make sure it's still green.

When a test fails, the first question is "is the test wrong, or is
the code wrong?" Use the spec as the tiebreaker. If spec and code
disagree, decide which to change consciously.

## When the user asks for changes

- Prefer editing existing files. Don't add new modules unless the
  change clearly doesn't fit.
- Don't introduce a frontend build pipeline or ORM migrations
  without explicit ask.
- The codebase is used live in sessions with real audiences.
  Sweeping refactors mid-event are a problem; prefer additive,
  reversible changes.

## Items deferred (need product decisions)

See the **Deferred (decision needed)** appendix at the bottom of
`docs/specs.md`. Don't implement these without checking with the
user — they're flagged because they need a product call before
they have shape.
