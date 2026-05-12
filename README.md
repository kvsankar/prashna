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
uv run uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/>. The first visitor creates the admin
account (username + password). After that, sign in to create
sessions and author quizzes.

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

## Project layout

```
app/                FastAPI app — routes, models, auth, db, websocket hub
static/             Vanilla JS / HTML / CSS, one page per role; vendored QR lib
docs/
  specs.md          Use-case spec + acceptance tests — authoritative
  UX.md             Frontend design system — authoritative
tests/
  api/              pytest + httpx + FastAPI TestClient
  ui/               Playwright Python
deploy/             Dockerfile, docker-compose.yml, nginx, setup.sh
uploads/            user-uploaded images (gitignored)
```

## Deploy

There's a Dockerfile and a `deploy/` kit for a Hetzner VPS behind
nginx + Caddy/Let's Encrypt. Images publish to
`ghcr.io/kvsankar/prashna` via the `.github/workflows/docker.yml`
workflow on each push to `main` and version tags. See
[`deploy/README.md`](deploy/README.md).

## Status

Pre-launch. The schema rebuilds on every change (no migrations
yet — delete `prashna.db` if a model changes incompatibly). Heading
to open-source release plus a hosted SaaS variant. See the
**Deferred (decision needed)** appendix at the bottom of
`docs/specs.md` for items that need product calls before they ship:
SSO, multi-admin, reopen lifecycles, per-question timer, rate
limiting, content-sniffing on uploads, etc.
