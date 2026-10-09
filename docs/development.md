# Developing Prashna

This guide is for contributors working from a source checkout. How Prashna is
built and why is in [`architecture.md`](architecture.md). The behaviour
contract is [`specs.md`](specs.md), and the UI rules are in [`UX.md`](UX.md).

## Prerequisites

- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).
- Node.js 22 and npm, to build the Vite frontend.
- Chromium for Playwright, for the UI tests (installed below).
- Optional: Docker with the Compose plugin, for the container smoke tests.
- Optional: the ngrok CLI, signed in, for sharing a local server.

## Set up

```bash
uv sync          # Python dependencies, including the dev group
npm ci           # frontend build tools
npm run build    # builds the frontend into prashna/static
```

## Run

```bash
uv run prashna                                           # the CLI, as users run it
uv run uvicorn prashna.main:app --reload --port 8000     # backend with auto-reload
npm run dev                                              # Vite dev server with hot reload
```

- `uv run prashna` serves on `http://127.0.0.1:8000` and opens the browser.
  While no admin exists, it opens the one-time setup page. `--help` lists the
  options.
- `uvicorn` serves the API, the WebSocket endpoint, and the last frontend
  build. While no admin exists, it logs the setup link as a `WARNING`:

  ```text
  No admin yet. Create one by opening this one-time link on this server's address: /#setup=...
  ```

  Open the server's address plus that path, for example
  `http://localhost:8000/#setup=...`. The link works once.
- `npm run dev` starts the Vite dev server with hot module reload. It proxies
  `/api`, `/ws`, and `/uploads` to the backend on port 8000. Use the URL it
  prints during frontend work.

In a source checkout, the database (`prashna.db`), the uploads folder
(`uploads/`), `secret-key`, and `setup-token` are created in the repository
root. Git ignores `prashna.db` and the contents of `uploads/`. `secret-key`
and `setup-token` are not in `.gitignore`; do not commit them.

To load settings from a file, copy `.env.example` to `.env` and pass
`--env-file .env` to uvicorn.

### Share a local server through ngrok

A local server can serve a live audience through an ngrok tunnel without a
remote deployment:

```bash
uv sync
npm ci
npm run build
export PRASHNA_TRUSTED_PROXY_HOPS=1
uv run uvicorn prashna.main:app --host 127.0.0.1 --port 8000
```

Complete first-run setup on localhost before sharing the address. Then, in
another terminal:

```bash
ngrok http 8000
```

Share the HTTPS URL that ngrok prints. One endpoint carries both HTTP and
secure WebSocket traffic, so live updates need no second tunnel. Run one
uvicorn worker only: the WebSocket hub is in memory. The ngrok URL is public;
stop ngrok when the session ends. The behaviour is specified in UC-X-09.

## Environment variables

These are all the variables the application reads. Each one is optional.

| Variable | Default | Effect |
| --- | --- | --- |
| `PRASHNA_DATA_DIR` | Source checkout: the repository root. Installed package: the per-user app-data folder (`~/.local/share/prashna`, or `$XDG_DATA_HOME/prashna`; `~/Library/Application Support/prashna`; `%LOCALAPPDATA%\prashna`). | Read only by the `prashna` command. It is the folder for the database and uploads. `--data-dir` takes precedence. The command sets `PRASHNA_DB_PATH` and `PRASHNA_UPLOADS_DIR` inside this folder unless they are already set. |
| `PRASHNA_DB_PATH` | `prashna.db` in the default data folder above. The container image sets `/data/prashna.db`. | SQLite database file. `secret-key` and `setup-token` live in the same folder. `python -m prashna.backup` assumes `/data/prashna.db` when this is unset. |
| `PRASHNA_UPLOADS_DIR` | `uploads/` in the default data folder. The container image sets `/app/uploads`. | Folder for uploaded images. `python -m prashna.backup` assumes `/app/uploads` when this is unset. |
| `PRASHNA_SECRET_KEY` | Unset: the key in `secret-key` beside the database, created with mode `0600` on first start. | Cookie-signing key. Changing it signs every admin out (UC-X-07). |
| `PRASHNA_SETUP_TOKEN` | Unset: a random token kept in `setup-token` beside the database until an admin exists. | Fixed first-admin setup token (UC-A-01). |
| `PRASHNA_TRUSTED_PROXY_HOPS` | `0` (use the socket peer). | Number of trusted reverse-proxy hops for client-IP resolution. Set `1` behind ngrok or the bundled nginx (UC-X-08). |
| `PRASHNA_RATELIMIT` | On. | `off`, `0`, `false`, or `no` (any case) disables rate limiting (UC-X-08). |
| `PRASHNA_GITHUB_CLIENT_ID` | Unset. | GitHub OAuth app client id. GitHub sign-in is enabled only when all three GitHub variables are set (UC-A-26). |
| `PRASHNA_GITHUB_CLIENT_SECRET` | Unset. | GitHub OAuth app client secret. |
| `PRASHNA_GITHUB_ADMINS` | Unset. | Comma-separated allowlist of GitHub logins, matched case-insensitively. The OAuth app's callback URL is `https://<host>/api/auth/github/callback`. |
| `PRASHNA_WS_SEND_TIMEOUT_SECS` | `2.0` seconds. | Per-send timeout for WebSocket hints; a socket that times out is removed from its room. |

The Compose files read further variables for image tags, ports, and host
paths. Those are described in [`distribution/README.md`](../distribution/README.md)
and [`deploy/README.md`](../deploy/README.md).

The opt-in operations tests read `PRASHNA_NGROK_SMOKE`,
`PRASHNA_COMPOSE_SMOKE`, and `PRASHNA_COMPOSE_SMOKE_IMAGE` (see
[Tests](#tests)).

## Tests

```bash
uv run playwright install chromium   # once, for the UI tests
uv run pytest                        # full suite
uv run pytest tests/api/             # API tests only
uv run pytest tests/ui/              # UI tests only
```

Test layers:

- `tests/api/`: in-process tests with FastAPI's `TestClient` and httpx
  against a fresh SQLite database per test. They also cover the CLI, the rate
  limiter, the repository hooks, the frontend source contracts, and these
  documentation contracts.
- `tests/ui/`: Playwright tests against a real uvicorn process with an
  isolated database.
- `tests/ops/`: packaging, distribution, nginx, Cloudflare, and performance
  tooling. Some of them need Docker or network access. Two are opt-in:
  - `PRASHNA_COMPOSE_SMOKE=1 uv run pytest tests/ops/test_compose_smoke.py`
    builds the image and checks a Compose deployment across a restart
    (`PRASHNA_COMPOSE_SMOKE_IMAGE` tests a published image instead).
  - `PRASHNA_NGROK_SMOKE=1 uv run pytest tests/ops/test_ngrok_smoke.py`
    runs the ngrok flow above through a real temporary endpoint.

The suite builds the frontend once per run with
`npm run build -- --mode test`. The test-mode build includes a socket test
hook. Run `npm run build` again before a production-like run or a package
build.

Test names cite the use case they verify: `test_uc_<role>_<nn>_<what>`, for
example `test_uc_p_13_submit_feedback` for UC-P-13. Each use case in
[`specs.md`](specs.md) lists its tests under **Tests (API)** and
**Tests (UI)**.

## Checks

```bash
uv run pre-commit install           # once; installs the pre-commit, commit-msg, and pre-push hooks
uv run pre-commit run --all-files   # what CI runs
npm run typecheck                   # TypeScript
npm run lint                        # TypeScript, ESLint, and Stylelint
uv run pyrefly check                # Python types
```

| Stage | What runs |
| --- | --- |
| pre-commit | YAML and TOML checks, merge-conflict markers, files over 600 KB, final newline, trailing whitespace, private keys, `detect-secrets` against `.secrets.baseline`, `scripts/check_pii.py`, Ruff, Pyrefly, `tsc`, ESLint, and Stylelint |
| commit-msg | `scripts/check_commit_msg.py`: Conventional Commits with a body |
| pre-push | The API tests |

`scripts/check_pii.py` rejects real email addresses, public IP addresses, and
home-directory paths. Mark a deliberate line with `pii-allow`.

CI (`.github/workflows/docker.yml`) runs on pushes to `main`, on version
tags, and on pull requests to `main`:

1. Pre-commit on every file, the Playwright browser install, and the full
   pytest suite with coverage. CI fails below 94% coverage.
2. `npm run lint`.
3. The Docker Compose smoke test.
4. On pushes and tags (not pull requests): the multi-architecture image build
   and push to GHCR, then a smoke test of the exact pushed digest.

## Project layout

```text
prashna/             Python package
  main.py            routes, middleware, and the WebSocket endpoint
  models.py          SQLAlchemy models
  db.py              engine, SQLite pragmas, default data folder, migration bridge
  auth.py            password hashing, signed cookies, signing key, setup token
  oauth.py           GitHub OAuth sign-in
  ratelimit.py       token-bucket rate limiter
  ws.py              in-memory WebSocket hub
  diagnostics.py     structured, secret-safe diagnostic logging
  backup.py          backup and restore (python -m prashna.backup)
  cli.py             the `prashna` command
  installers/        install.sh and install.ps1, served at /install.sh and /install.ps1
  static/            Vite build output (generated, ignored by Git)
frontend/            Vite + TypeScript frontend, one HTML entry per role
  src/               common.ts, types.ts, one entry per page, app.css
  public/vendor/     vendored QR code generator
tests/
  api/               API, CLI, hook, and contract tests
  ui/                Playwright tests
  ops/               packaging, distribution, deployment, and performance tests
scripts/             build_release_bundle.py, check_pii.py, check_commit_msg.py
performance/         measure.py, budgets.json, and the measurement runbook
deploy/              Hetzner Compose file, nginx, setup and Cloudflare scripts
distribution/        README shipped inside the Compose release bundle
docs/                specs, UX rules, architecture, this guide, the backlog
compose.yaml         laptop and small-host Compose model
compose.env.example  optional settings for compose.yaml
Dockerfile           production image
uploads/             uploaded images in a source checkout (ignored by Git)
```

## Cut a release

1. Set the new version in `pyproject.toml` and commit it.
2. Tag the commit `vX.Y.Z` with the same version and push the tag.

The tag starts the CI workflow, which:

- runs the checks and tests;
- builds and pushes `ghcr.io/kvsankar/prashna` for `linux/amd64` and
  `linux/arm64`, tagged `X.Y.Z`, `X.Y`, and `sha-<commit>`, and smoke-tests
  the pushed digest (the `latest` tag follows pushes to `main`);
- builds the version-pinned Compose bundle (`.tar.gz`, `.zip`, and
  `SHA256SUMS`) with `scripts/build_release_bundle.py` and attaches it to the
  GitHub Release, creating the release if needed;
- builds the frontend, the wheel, and the sdist, and publishes them to PyPI
  through trusted publishing in the GitHub environment `pypi`. This job fails
  if the tag does not match the version in `pyproject.toml`.

Anonymous image pulls need the GHCR package to be public; see
[`distribution/README.md`](../distribution/README.md).

## Documentation policy

- Tracked documentation describes the current product and its operation. It
  is not a history or changelog.
- Each topic has one owner, and other documents link to it instead of
  repeating it:

  | Topic | Owner |
  | --- | --- |
  | What Prashna is, install, first run | [`README.md`](../README.md) |
  | Behaviour and its tests | [`specs.md`](specs.md) |
  | UI rules | [`UX.md`](UX.md) |
  | Architecture, data model, decisions, risks | [`architecture.md`](architecture.md) |
  | Contributor setup, environment, tests, checks, releases | this guide |
  | Rules for coding agents | [`CLAUDE.md`](../CLAUDE.md) |
  | Engineering follow-ups | [`todo.md`](todo.md) |
  | Production host operations | [`deploy/README.md`](../deploy/README.md) |
  | Container bundle operations | [`distribution/README.md`](../distribution/README.md) |
  | Performance measurement | [`performance/README.md`](../performance/README.md) |

- Reviews, assessments, completed plans, proposals, generated reports, and
  dated investigations are one-off records. Keep them in the local checkout,
  list their paths in `.git/info/exclude`, and do not commit them.
- Product ideas that still need a decision stay in the deferred appendix of
  [`specs.md`](specs.md#deferred-decision-needed); engineering follow-ups go
  in [`todo.md`](todo.md).

Prashna uses Sarathi in "govern only new changes" mode
(`.sdlc/process-decisions.yaml`). `specs.md` and `architecture.md` are the
baseline. A change document governs a change while it is in progress. Once the
change ships, its behaviour moves into `specs.md`, and its change document
becomes a local one-off record.
