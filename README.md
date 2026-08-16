# Prashna

A live Q&A and quiz tool for any session with an audience — training,
lectures, workshops, town halls, meetups. *Prashna* (प्रश्न) is
Sanskrit for *question*.

Two core features:

- **Anonymous Q&A** — participants post queries, upvote each other,
  moderator responds (text or verbal). Removed queries are
  soft-deleted (kept for audit, hidden from participants).
- **Moderator-conducted quizzes** — single- or multi-choice
  questions, optional images, anonymous voting, per-question
  reveal, lobby state on the projector, optional live counts
  during voting. Quizzes are versioned: editing a template never
  alters a past run's report.

Plus a **projector view** for the big screen at the front of the
room: join code, scannable QR for the participant URL (admin can
override the base URL per session), top queries, and the current
quiz in lockstep with the moderator.

## Quick start

```bash
uv sync
npm ci
npm run build
uv run uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/>. The first visitor creates the admin
account (username + password). After that, sign in to create
sessions and author quizzes.

### Run locally and share through ngrok

The original no-server-deployment workflow is still supported. Build the
frontend first, start Prashna on localhost, complete admin setup locally, and
only then expose port 8000:

```bash
uv sync
npm ci
npm run build
export PRASHNA_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export PRASHNA_TRUSTED_PROXY_HOPS=1
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://localhost:8000/> and complete first-run setup. In another
terminal, start the tunnel:

```bash
ngrok http 8000
```

Share the HTTPS URL ngrok prints. The same endpoint carries normal HTTP and
secure WebSocket traffic, so participant, moderator, and projector live
updates do not need a second tunnel. Keep the Uvicorn process to one worker:
Prashna's WebSocket hub is in-memory and intentionally single-process.

An opt-in end-to-end smoke test exercises this exact flow with an isolated
database and a real temporary ngrok endpoint (the ngrok CLI must already be
installed and authenticated):

```bash
PRASHNA_NGROK_SMOKE=1 uv run pytest tests/ops/test_ngrok_smoke.py
```

For production, set a stable signing key:

```bash
PRASHNA_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))') \
  uv run uvicorn app.main:app --port 8000
```

Without it, the process generates a random key on each start —
admins must re-login after every restart.

## Roles

| Role        | URL                  | Auth                                  |
| ----------- | -------------------- | ------------------------------------- |
| Admin       | `/`                  | Cookie (bcrypt password, signed)      |
| Moderator   | `/m/<code>`          | Admin cookie OR `mod_key` URL frag    |
| Participant | `/s/<code>`          | Anonymous (`voter_token` cookie)      |
| Projector   | `/p/<code>`          | Public, read-only                     |
| Quiz library| `/quizzes`           | Admin cookie                          |

**Admin ⊇ Moderator**: the admin who owns a session reaches the
moderator UI directly with their cookie. The `mod_key` (delivered
via `/m/<code>#k=<key>` URL) is the *delegation* mechanism —
hand it to a TA / co-host who has no admin account.

Interactive role pages include breadcrumbs and section jump links. The
moderator session breadcrumb returns an authenticated owner directly to
that session's admin detail. The quiz library's run report can be viewed
flat or grouped by quiz, immutable quiz version, or session. The projector
deliberately remains chrome-free for presentation use.

## Entities

| Entity              | What it is                                                     |
| ------------------- | -------------------------------------------------------------- |
| `User`              | The admin. Single global today; SSO-based multi-admin planned. |
| `Session`           | A live event. Lifecycle: `planning → live → ended`.            |
| `Participant`       | Per-session anonymous identity, keyed by `voter_token` cookie. |
| `Query`             | A participant-asked Q&A entry. Has votes and an optional response. |
| `Quiz`              | Reusable quiz template owned by a User. Lifecycle: `draft → ready`. |
| `Question` / `Answer` | One quiz question and one answer choice in the template.     |
| `QuizVersion`       | Immutable snapshot of a Quiz captured on Launch. Historical reports point to versions, never to the editable template. |
| `QuizRun`           | One playthrough of a `QuizVersion` inside a Session. Lifecycle: `queued → live → closed`. At most one `live` per Session, enforced by a partial unique index. |
| `QuizSubmission`    | A participant's selected `Answer`(s) for a `Question` in a `QuizRun`. |

For the full data model, lifecycles, and authoritative behavior
spec, see [`docs/specs.md`](docs/specs.md). For the frontend design
system, see [`docs/UX.md`](docs/UX.md).

## Live updates

Every page opens a WebSocket to `/ws/sessions/<code>`. State-changing
actions broadcast a short `{"type": "..."}` hint; clients refetch
on receipt. Kinds: `session_state`, `participant`, `query_*`,
`quiz_run_*`, `quiz_submission`. Auto-reconnect with exponential
backoff if the socket drops.

## Tests

~350 acceptance tests against `docs/specs.md`:

```bash
uv run pytest               # full suite (~2 min)
uv run pytest tests/api/    # API only (pytest + httpx + TestClient)
uv run pytest tests/ui/     # UI only (Playwright Python)
```

UI tests need Chromium installed once:

```bash
uv run playwright install chromium
```

Every UC in the spec has `Tests (API)` and/or `Tests (UI)` bullets
that map 1:1 to a pytest function.

## Environment

- `PRASHNA_SECRET_KEY` — signs admin session cookies. **Set in
  production.** Without it, sessions die on every restart.
- `PRASHNA_DB_PATH` — override DB location (default
  `<repo>/prashna.db`). Used by Docker and tests.
- `PRASHNA_UPLOADS_DIR` — override uploads dir.

## Diagnostics

Prashna emits structured operator diagnostics through the Python `prashna`
logger. Records use `diag_event` plus safe context such as outcome, route
area, row ids, session code, and upload size or extension. They deliberately
omit passwords, cookies, OAuth tokens, moderator keys, participant contact
fields, uploaded bytes, filenames, and user-entered Q&A text.

Production operators should retain application or container logs for at least
7 days. Retention is owned by the host log driver, journald policy, or external
log shipper; Prashna does not store diagnostic logs in the SQLite database.

## Project layout

```
app/                FastAPI app — routes, models, auth, db, websocket hub
frontend/          Vite + TypeScript frontend, one page per role
  src/              shared TS helpers, page entries, and app.css tokens
  public/vendor/    vendored QR lib
docs/
  specs.md          Use-case spec + acceptance tests — authoritative
  UX.md             Frontend design system — authoritative
tests/
  api/              pytest + httpx + FastAPI TestClient
  ui/               Playwright Python
deploy/             Dockerfile, docker-compose.yml, nginx, setup.sh
uploads/            user-uploaded images (gitignored)
compose.yaml        laptop/self-host distribution using the published image
compose.env.example configuration template for the local Compose bundle
```

## Distribution

The canonical runnable artifact is the multi-architecture image at
`ghcr.io/kvsankar/prashna`. The root [`compose.yaml`](compose.yaml) is the
laptop/small-host distribution; the separate `deploy/` configuration remains
specific to the Hetzner production service.

For a local container installation:

```bash
cp compose.env.example .env
# Replace PRASHNA_SECRET_KEY in .env with a generated secret.
docker compose pull
docker compose up -d --wait
```

Open <http://127.0.0.1:8000/> and create the first admin. Database and uploads
live in named volumes and survive container replacement. Do not run
`docker compose down --volumes` unless you intend to delete them.

Version tags publish `linux/amd64` and `linux/arm64` images, smoke-test the
exact pushed digest, and attach version-pinned `.zip` and `.tar.gz` Compose
bundles plus `SHA256SUMS` to the matching GitHub Release. See
[`distribution/README.md`](distribution/README.md) for ngrok, backup, restore,
upgrade, registry access, and operational commands. Broad anonymous
distribution also requires the GHCR package visibility to be set to Public in
GitHub Packages; that account-level setting is intentionally not controlled by
the repository workflow.

## Deploy

There's a Dockerfile and a `deploy/` kit for a Hetzner VPS behind
nginx + Caddy/Let's Encrypt. Images publish to
`ghcr.io/kvsankar/prashna` via the `.github/workflows/docker.yml`
workflow on each push to `main` and version tags. See
[`deploy/README.md`](deploy/README.md).

## Status

Pre-launch. `init_db()` creates fresh schemas and runs a lightweight
additive SQLite migration bridge for known post-deploy columns/indexes.
Breaking schema changes still require an explicit release note or a real
migration before user data matters. Heading to open-source release plus a
hosted SaaS variant. See the
**Deferred (decision needed)** appendix at the bottom of
`docs/specs.md` for items that need product calls before they ship:
SSO, multi-admin, reopen lifecycles, per-question timer,
content-sniffing on uploads, etc.
