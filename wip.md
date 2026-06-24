# WIP — follow-ups

Deferred cleanups from the 2026-06-23 Hetzner deploy. Neither blocks the
live site (https://prashna.sankara.net is up and working).

## 1. `deploy/setup.sh` — chown volume dirs to the container uid (uid 1001)

**Problem.** The container runs as user `prashna` = **uid 1001** (see
`Dockerfile`). `setup.sh` creates `/opt/prashna/{data,uploads}` owned by
`$USER` (uid 1000), so the container can't write them and SQLite fails at
startup with `sqlite3.OperationalError: unable to open database file`.
On the live box this was worked around manually with
`sudo chown -R 1001:1001 /opt/prashna/data /opt/prashna/uploads`.

**Fix.** In `deploy/setup.sh`, after the `install -d … /opt/prashna/data
/opt/prashna/uploads` step, chown those two dirs to `1001:1001` (or create
them with `-o 1001 -g 1001`). Keep it idempotent.

**Effort.** One-line repo change + commit. **No redeploy needed** — the
running box is already correct. Matters only for a fresh re-bootstrap.

## 2. Show "Sign in with GitHub" on the setup screen too

**Problem.** On a fresh deploy (`/api/admin/status` → `initialized:false`),
the landing page shows the password **"Set up admin account"** card; the
GitHub button only renders on the *login* screen (which needs an admin to
already exist). So a GitHub-first operator can't bootstrap from the
homepage — they must hit `https://…/api/auth/github/login` directly. The
backend already find-or-creates the admin on that route; it's purely a
frontend gap.

**Fix.** In `static/index.html` `refresh()`, surface the "Sign in with
GitHub" affordance whenever `github_enabled && !authenticated` — i.e. in
**both** the setup and login states (today the `#github-login-wrap` lives
inside `#login-card`, so it's hidden on the setup screen). Simplest: make
it a standalone element toggled independently of `show()`. Update the
UC-A-26 UI test bullet in `docs/specs.md` accordingly.

**Effort.** Frontend edit + spec/test tweak, then a rebuild + redeploy:
commit → push (CI builds `:latest`) → on the box
`cd /opt/prashna && sudo docker compose pull && sudo docker compose up -d`.

---
Related: `docs/specs.md` UC-A-26, `docs/todo.md`, and the deploy notes in
memory (`project_prashna_deployed.md`).
