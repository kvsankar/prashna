# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**Prashna** — live Q&A + quiz tool for training sessions, lectures, and
workshops. It has a live single-operator production deployment and a packaged
container release; broader open-source distribution and hosted SaaS remain
future directions. Keep code clear and small; resist
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
- **`performance/README.md`** — Current measurement, diagnosis, and release
  verification runbook.
- **`deploy/README.md`** and **`distribution/README.md`** — Production and
  portable-container operations respectively.
- **`docs/todo.md`** — Current engineering follow-ups only. Product decisions
  that do not yet have accepted behavior stay in the deferred appendix of
  `docs/specs.md`.

`spec.md` and `design.md` are the system-level Sarathi requirements and design
views. They summarize the system; they do not replace the detailed behavior
contract in `docs/specs.md`, the UX rules in `docs/UX.md`, or their tests.

### Documentation lifecycle

- Version only live documentation that is expected to stay correct as the
  product changes.
- Treat reviews, assessments, completed plans, proposals, generated reports,
  and dated investigations as immutable one-off records.
- Preserve one-off records locally and add their exact paths to
  `.git/info/exclude`; do not commit later revisions of them.
- Consolidate live guidance into the smallest authoritative document for its
  audience and replace repeated instructions with links.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2 (sync), SQLite. The
  production image currently runs Python 3.12. Single-process. WebSockets for
  live broadcast.
- **Frontend:** TypeScript ES modules, built with **Vite** (multi-page,
  one entry per role). Plain HTML + CSS, no framework. FastAPI serves the
  Vite build output (`prashna/static`) under `/static`. Dev uses the Vite
  dev server (`npm run dev`) with HMR, proxying `/api`, `/ws`, `/uploads`
  to the backend.
- **Auth:** bcrypt password hashing + `itsdangerous`-signed session
  cookie for admin; `mod_key` URL fragment for delegate moderators;
  `voter_token` cookie for anonymous participants.
- **Tests:** pytest + httpx (API) + Playwright Python (UI).
  500+ tests against `docs/specs.md`. Run with `uv run pytest`.
- **Tooling:** `uv` for dependency management.

## Layout

```
prashna/         # the Python package (installed as `prashna`)
  main.py        # all FastAPI routes + WebSocket endpoint
  models.py      # SQLAlchemy models
  auth.py        # password hashing + signed cookie helpers
  db.py          # engine, SessionLocal, get_db, init_db
  ws.py          # in-memory pub/sub hub keyed by session code
frontend/        # Vite + TypeScript frontend (source)
  index.html     # landing — admin setup / login / session list (Vite entry)
  participant.html
  moderator.html
  projector.html
  quizzes.html   # quiz template authoring
  src/
    common.ts    # shared helpers (api, el, toast, ws, $, guardClick…)
    types.ts     # API payload interfaces
    {index,participant,moderator,projector,quizzes}.ts  # per-page entries
    app.css      # shared styles (imported by common.ts)
  public/vendor/qrcode.js  # vendored QR generator (MIT, Kazuhiko Arase)
vite.config.ts, tsconfig.json, package.json   # frontend build config
docs/
  specs.md       # use cases + AT bullets — authoritative
  UX.md          # frontend design system — authoritative
  todo.md        # current engineering follow-ups
performance/
  README.md      # live performance runbook
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
uv sync                 # backend deps
npm install             # frontend dev/build deps
uv run uvicorn prashna.main:app --reload --port 8000   # backend (API + WS)
uv run prashna                                     # same, the way users run it (UC-X-15)
npm run dev             # Vite dev server (HMR) — proxies /api,/ws,/uploads → :8000
```

Open the Vite dev server URL for development (HMR). For a production-like
run, `npm run build` then hit uvicorn directly (it serves `prashna/static`
at `/static`). The Docker image builds the frontend in a Node stage. The
UI tests build the frontend automatically (see `tests/ui/conftest.py`).
Frontend checks: `npm run typecheck`, `npm run lint`.

Environment:

- `PRASHNA_SECRET_KEY` — optional cookie-signing key. Unset, the
  server creates `secret-key` (0600) beside the database and reuses it,
  so sessions survive restarts (UC-X-07).
- `PRASHNA_SETUP_TOKEN` — optional fixed first-admin setup token. Unset,
  the server generates one in `setup-token` beside the database and logs
  the link `/#setup=<token>` at start until an admin exists (UC-A-01).
  Tests set it (see `tests/support.py`).
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
uv run pytest               # full suite (~2 min, 500+ tests)
uv run pytest tests/api/    # API only (fast, ~1 min)
uv run pytest tests/ui/     # UI only (Playwright, ~1 min)
```

Checks (pre-commit, also run by CI on every file):

```bash
uv run pre-commit install           # once: pre-commit, commit-msg, pre-push
uv run pre-commit run --all-files   # what CI runs
uv run pyrefly check                # Python types (app, scripts, tests)
```

The pre-commit stage runs file hygiene, `detect-secrets` (against
`.secrets.baseline`), `scripts/check_pii.py` (no real emails, public IPs,
or home paths; mark a deliberate line `pii-allow`), ruff, Pyrefly, tsc,
eslint, and stylelint. The commit-msg stage enforces Conventional
Commits with a body (`scripts/check_commit_msg.py`); pre-push runs the
API tests. CI fails below 94% coverage.

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
- **Admin** — bcrypt password, signed cookie. First-run setup needs
  the one-time setup token from the server log (or
  `PRASHNA_SETUP_TOKEN`); it creates the only admin row, retires the
  token, and `POST /api/admin/setup` returns 409 thereafter (UC-A-01).
- **Admin via GitHub OAuth** — optional, allowlisted sign-in for
  hosted deploys (UC-A-26, `prashna/oauth.py`). Enabled when
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
`init_db()` calls `create_all` at startup (via the FastAPI lifespan
context manager), then runs the additive SQLite migration bridge in
`prashna/db.py` for known post-deploy columns and indexes. When adding a
column or storage invariant to an existing table, update that bridge and
add an old-shape SQLite regression test. Truly breaking schema changes
still need an explicit release/reset plan or Alembic before real user
data matters.

### Routes file
`prashna/main.py` is intentionally one file. If it grows past ~1500
lines and needs splitting, split by resource (sessions, queries,
quizzes, quiz_runs, uploads, admin) rather than by HTTP method.

### Frontend
- TypeScript + Vite (multi-page), no UI framework. Keep it that way —
  don't introduce React/Vue/Svelte without asking. Authoring is in
  `frontend/src/*.ts`; the browser loads the Vite build.
- `strict` TypeScript. Type DOM lookups with the generic `$<T>` helper
  (e.g. `$<HTMLInputElement>("#x").value`); add API shapes to
  `frontend/src/types.ts`. `npm run typecheck` + `npm run lint` must pass
  (also enforced by pre-commit + CI).
- Mutating buttons go through `guardClick` (see UX.md §10).
- Selectors should be stable IDs (`#new-session-title`, `#base-url`)
  or documented classes (`.badge-live`, `.option`, `.question`).
- Toast for transient errors, banner for sticky ones, redirect for
  auth expiry. Never `alert()`/`prompt()` in new code.

## Things to be careful about

- The moderator URL contains a secret in the fragment (`#k=...`).
  Don't log full URLs server-side and don't print `mod_key` to
  stdout outside the creation response. The "Share moderator URL"
  button in the session page's Session settings card (owner-only) is the
  only path that exposes it
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
- The frontend build is Vite + TypeScript (already in place). Don't add
  ORM migrations, a UI framework, or CSS preprocessors without explicit ask.
- The codebase is used live in sessions with real audiences.
  Sweeping refactors mid-event are a problem; prefer additive,
  reversible changes.
- Use the live documentation and current repository state for product and
  operational decisions; historical one-off records are context, not authority.

## Items deferred (need product decisions)

See the **Deferred (decision needed)** appendix at the bottom of
`docs/specs.md`. Don't implement these without checking with the
user — they're flagged because they need a product call before
they have shape.
