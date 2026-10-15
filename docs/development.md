# Developing Prashna

This guide is for contributors working from a source checkout. How Prashna is
built and why is in [`architecture.md`](architecture.md). The behaviour
contract is [`specs.md`](specs.md), and the UI rules are in [`UX.md`](UX.md).

## Prerequisites

- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).
- Node.js 22 and npm, to build the Vite frontend.
- Chromium for Playwright, for the UI tests (installed below).
- Optional: Docker with the Compose plugin, for the container smoke tests.
- Optional: `cloudflared` (no account needed) or the ngrok CLI, signed in,
  for sharing a local server.

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
  While no admin exists, it opens the one-time setup page and also prints
  that link, for when no browser opens. `--help` lists the options.
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

A source checkout keeps its data where an installed copy does: the database
(`prashna.db`), the uploads folder, `secret-key`, and `setup-token` live in
the per-user app-data folder (see `PRASHNA_DATA_DIR` below), not in the
repository. Use `uv run prashna --data-dir <folder>` for a separate
database, and keep that folder outside any repository. The commit checks
reject a generated secret or a SQLite database wherever it is staged (see
[Checks](#checks)).

To load settings from a file, copy `.env.example` to `.env` and pass
`--env-file .env` to uvicorn.

### Share a local server over the internet

`uv run prashna --tunnel cloudflare` (or `--tunnel ngrok`) works from a
source checkout exactly as for an installed copy; see
[Share over the internet](../README.md#share-over-the-internet).

To run Uvicorn directly instead (UC-X-09), build the frontend, start it on
localhost, and run the tunnel yourself:

```bash
uv sync
npm ci
npm run build
export PRASHNA_TRUSTED_PROXY_HOPS=1
uv run uvicorn prashna.main:app --host 127.0.0.1 --port 8000
cloudflared tunnel --url http://127.0.0.1:8000    # or: ngrok http 8000
```

Then set each session's Base URL (UC-A-06) to the tunnel's address, so its
participant link and QR code use it. One endpoint carries both HTTP and
secure WebSocket traffic, so live updates need no second tunnel. Run one
Uvicorn worker only: the WebSocket hub is in memory. The address is public;
stop the tunnel when the session ends.

## Environment variables

These are all the variables the application reads. Each one is optional.

| Variable | Default | Effect |
| --- | --- | --- |
| `PRASHNA_DATA_DIR` | The per-user app-data folder, for a source checkout and an installed package alike (`~/.local/share/prashna`, or `$XDG_DATA_HOME/prashna`; `~/Library/Application Support/prashna`; `%LOCALAPPDATA%\prashna`). | Read only by the `prashna` command. It is the folder for the database, uploads and `prashna.log`. `--data-dir` takes precedence. Without `--data-dir`, `PRASHNA_DB_PATH` and `PRASHNA_UPLOADS_DIR`, when set, choose the database and uploads instead of this folder (UC-X-15). |
| `PRASHNA_DB_PATH` | `prashna.db` in the default data folder above. The container image sets `/data/prashna.db`. | SQLite database file. `secret-key` and `setup-token` live in the same folder. The `prashna` command, including `prashna backup` and `prashna reset-password`, ignores it when `--data-dir` is given. `python -m prashna.backup` assumes `/data/prashna.db` when this is unset. |
| `PRASHNA_UPLOADS_DIR` | `uploads/` in the default data folder. The container image sets `/app/uploads`. | Folder for uploaded images. The `prashna` command ignores it when `--data-dir` is given. `python -m prashna.backup` assumes `/app/uploads` when this is unset. |
| `PRASHNA_SECRET_KEY` | Unset: the key in `secret-key` beside the database, created with mode `0600` on first start; generated keys start with `prashna_sk_`. | Cookie-signing key. Changing it signs every admin out (UC-X-07). |
| `PRASHNA_SETUP_TOKEN` | Unset: a random token starting with `prashna_st_`, kept in `setup-token` beside the database until an admin exists. | Fixed first-admin setup token (UC-A-01). |
| `PRASHNA_TRUSTED_PROXY_HOPS` | `0` (use the socket peer). | Number of trusted reverse-proxy hops for client-IP resolution. Set `1` behind ngrok or the bundled nginx (UC-X-08). |
| `PRASHNA_RATELIMIT` | On. | `off`, `0`, `false`, or `no` (any case) disables rate limiting (UC-X-08). |
| `PRASHNA_TUNNEL_DNS_WAIT_SECS` | `60` seconds. | How long `prashna --tunnel cloudflare` waits for the new address to appear in public DNS before printing it anyway (UC-X-15). `0` skips the wait; the stub-tunnel tests use that. |
| `PRASHNA_WS_SEND_TIMEOUT_SECS` | `2.0` seconds. | Per-send timeout for WebSocket hints; a socket that times out is removed from its room. |

The Compose files read further variables for image tags, ports, and host
paths. Those are described in [`distribution/README.md`](../distribution/README.md)
and [`deploy/README.md`](../deploy/README.md).

The opt-in operations tests read `PRASHNA_CLOUDFLARE_SMOKE`,
`PRASHNA_NGROK_SMOKE`, `PRASHNA_COMPOSE_SMOKE`, and
`PRASHNA_COMPOSE_SMOKE_IMAGE` (see [Tests](#tests)).

## Tests

```bash
uv run playwright install chromium   # once, for the UI tests
uv run pytest                        # full suite
uv run pytest tests/api/             # API tests only
uv run pytest tests/ui/              # UI tests only
```

Test layers:

- `tests/api/`: in-process tests with FastAPI's `TestClient` and httpx
  against one SQLite database per run, with every table emptied before each
  test. A WebSocket receive in these tests fails after 5 s
  (`tests/support.py::ws_receive`), so a missing broadcast fails the test
  instead of hanging the run. They also cover the CLI, the rate
  limiter, the repository hooks, the frontend source contracts, and these
  documentation contracts.
- `tests/ui/`: Playwright tests against a real uvicorn process with an
  isolated database.
- Export tests read the generated Excel workbooks with `openpyxl`, a
  dev-only dependency; the application writes them with `XlsxWriter`.
- `tests/ops/`: packaging, distribution, nginx, Cloudflare, and performance
  tooling. Some of them need Docker or network access. Three are opt-in:
  - `PRASHNA_COMPOSE_SMOKE=1 uv run pytest tests/ops/test_compose_smoke.py`
    builds the image and checks a Compose deployment across a restart
    (`PRASHNA_COMPOSE_SMOKE_IMAGE` tests a published image instead).
  - `PRASHNA_NGROK_SMOKE=1 uv run pytest tests/ops/test_ngrok_smoke.py`
    runs the ngrok flow above through a real temporary endpoint.
  - `PRASHNA_CLOUDFLARE_SMOKE=1 uv run pytest tests/ops/test_cloudflare_smoke.py`
    runs `prashna --tunnel cloudflare` through a real quick tunnel; it needs
    `cloudflared`.

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

`scripts/check_pii.py` rejects real email addresses, public IP addresses,
home-directory paths, and generated Prashna secrets (values starting with
`prashna_sk_` or `prashna_st_`) in text files. It also rejects any SQLite
database, recognised by its file header, whatever the file is called and
wherever it is staged. Mark a deliberate text line with `pii-allow`.

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
  ratelimit.py       token-bucket rate limiter
  ws.py              in-memory WebSocket hub
  diagnostics.py     structured, secret-safe diagnostic logging
  export.py          data export as JSON or an Excel workbook (XlsxWriter)
  backup.py          backup and restore (python -m prashna.backup)
  cli.py             the `prashna` command
  tunnel.py          --tunnel: run cloudflared or ngrok and read its address
  installers/        install.sh and install.ps1, served at /install.sh and /install.ps1
  static/            Vite build output (generated, ignored by Git)
frontend/            Vite + TypeScript frontend, one HTML entry per role
  src/               common.ts, types.ts, one entry per page, app.css, tokens.css
  public/vendor/     vendored QR code generator
tests/
  api/               API, CLI, hook, and contract tests
  ui/                Playwright tests
  ops/               packaging, distribution, deployment, and performance tests
scripts/             build_release_bundle.py, build_pages_site.py, check_pii.py,
                     check_commit_msg.py
performance/         measure.py, budgets.json, and the measurement runbook
deploy/              Hetzner Compose file, nginx, setup and Cloudflare scripts
distribution/        README shipped inside the Compose release bundle
docs/                specs, UX rules, architecture, this guide, the backlog
compose.yaml         laptop and small-host Compose model
compose.env.example  optional settings for compose.yaml
compose.https.yaml   HTTPS add-on for compose.yaml: Caddy on ports 80 and 443
Caddyfile            Caddy site for compose.https.yaml
Dockerfile           production image
```

## Cut a release

1. Set the new version in `pyproject.toml`, and in the example image tag,
   bundle name and download URLs in `distribution/README.md` (tests check
   that they match). Commit both.
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
  if the tag does not match the version in `pyproject.toml`;
- after the PyPI job, builds the install-script site with
  `scripts/build_pages_site.py` and deploys it to GitHub Pages at
  `https://kvsankar.github.io/prashna/`. Users install from
  `https://sankara.net/prashna/install.sh` and `install.ps1`, the addresses
  the README shows; sankara.net redirects them to the GitHub Pages site, so
  each Pages deploy updates them. The GitHub Pages addresses also work.

Two one-time settings make the publishing jobs work: a trusted publisher on
PyPI for project `prashna` (workflow `docker.yml`, environment `pypi`), and
**Settings → Pages → Source: GitHub Actions** in the repository.

Anonymous image pulls need the `prashna` container package to be
**Public** in GitHub Packages. That setting belongs to the GitHub account,
not to the workflow. While the package is private, users must first sign in
to `ghcr.io` with a GitHub token that has `read:packages`.

## Documentation policy

- Tracked documentation describes the current product and its operation. It
  is not a history or changelog.
- Each topic has one owner, and other documents link to it instead of
  repeating it:

  | Topic | Owner |
  | --- | --- |
  | What Prashna is, install, quick tutorial | [`README.md`](../README.md) |
  | End-user how-to: features, tunnels, data, backup, update, uninstall, troubleshooting | [`user-guide.md`](user-guide.md) |
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
