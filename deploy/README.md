# Deploy

> **Maintainer's runbook.** This folder is the maintainer's runbook for
> `https://prashna.sankara.net` and will be removed. To run Prashna on a
> server of your own, use the container guide:
> [Run on your own server with HTTPS](../distribution/README.md#run-on-your-own-server-with-https),
> or [Already run a reverse proxy?](../distribution/README.md#already-run-a-reverse-proxy)
> if the server already has a web server.
>
> Warning: `/opt/prashna` and the container guide's bundle both use the
> Compose project name `prashna`. On a server that has both, give the
> bundle another name with `COMPOSE_PROJECT_NAME` in its `.env`, or its
> commands replace this deployment's container.

This directory holds everything the **Hetzner** box needs to run Prashna at
`https://prashna.sankara.net`.

Laptop and other self-hosted container installs use the root `compose.yaml`
instead; see [`distribution/README.md`](../distribution/README.md).

## One-time setup

1. **DNS** — create a proxied Cloudflare `A` record whose origin value is:

   ```
   prashna.sankara.net → <server-ip>
   ```

   With the orange cloud enabled, public DNS correctly returns Cloudflare
   anycast addresses rather than the server's IP. Verify the record and proxy
   state in Cloudflare before continuing.

2. **GitHub Actions** — the `CI & publish image` workflow (its `Build &
   publish Docker image` job) pushes to `ghcr.io/kvsankar/prashna`. No extra
   secrets needed; it uses the built-in
   `GITHUB_TOKEN` with `packages:write` permission. Trigger it once by pushing
   to `main` or running it manually so the image exists.

3. **On the server**, install nginx and Certbot if they are not already
   present. `setup.sh` installs Docker when necessary, but it expects the nginx
   and Certbot commands to exist before configuring TLS.

4. **If the GHCR package is private**, sign in to `ghcr.io` on the server
   first with `docker login ghcr.io` and a GitHub token that has
   `read:packages`.

5. **Run the bootstrap**:

   ```bash
   git clone git@github.com:kvsankar/prashna.git ~/repos/prashna
   cd ~/repos/prashna
   CERTBOT_EMAIL=you@example.com ./deploy/setup.sh
   ```

   This installs Docker when it is missing, lays down `/opt/prashna/` with a
   generated `PRASHNA_SECRET_KEY` in `.env`, pulls the image, installs the
   nginx site, prepares nginx for Cloudflare proxying
   (`prepare-cloudflare-proxy.sh`), requests a TLS certificate with Certbot,
   enables HTTP/2 (`enable-http2.sh`), and starts the container.

6. **Create the first admin.** Find the one-time setup link in the log and
   open it on `https://prashna.sankara.net`:

   ```bash
   cd /opt/prashna && docker compose logs prashna | grep setup=
   ```

## Updating

```bash
cd /opt/prashna
old=$(docker inspect --format '{{.Image}}' $(docker compose ps -q))
docker tag "$old" ghcr.io/kvsankar/prashna:rollback-$(date +%Y%m%d%H%M)
docker compose pull && docker compose up -d --wait
```

The tag keeps the image that was running, so a bad release can be undone
with `docker tag ghcr.io/kvsankar/prashna:rollback-<stamp>
ghcr.io/kvsankar/prashna:latest && docker compose up -d`. A restart drops
every live connection for a few seconds; update between quizzes.

## Cloudflare visitor IP and HTTP/2

`setup.sh` runs two idempotent nginx helpers. Each one backs up the site file,
validates the result with `nginx -t`, and restores the backup if validation
fails.

- `prepare-cloudflare-proxy.sh` downloads Cloudflare's published IP ranges and
  writes them to `/etc/nginx/snippets/prashna-cloudflare-realip.conf` as
  `set_real_ip_from` lines with `real_ip_header CF-Connecting-IP`. It includes
  that file in the site. nginx then sees the visitor's address rather than a
  Cloudflare edge address, and passes it on in `X-Forwarded-For`, which the
  application reads with `PRASHNA_TRUSTED_PROXY_HOPS=1`. Re-run the script to
  refresh the ranges.
- `enable-http2.sh` adds `http2` to the Certbot-managed TLS listeners without
  touching the certificates.

Both read `PRASHNA_DOMAIN` and `PRASHNA_NGINX_SITE_PATH` to target another
site.

## Cloudflare HTML-shell caching

The application marks only its static HTML page shells as edge-cacheable. API
responses, bad-session redirects, and personalized data remain `no-store`.
Cloudflare still needs a Cache Rule to make non-static HTML eligible. Preview
the idempotent ruleset update, then apply it with a token that can edit zone
rulesets:

```bash
export CLOUDFLARE_API_TOKEN=...       # Zone Rulesets:Edit and Zone:Read
export CLOUDFLARE_ZONE_ID=...         # optional; discovered by zone name
deploy/configure-cloudflare-cache.sh --dry-run
deploy/configure-cloudflare-cache.sh --apply
```

The helper preserves unrelated cache rules and replaces only the stable
`prashna_html_shells` rule. It covers `/`, `/quizzes`, and the `/s/`, `/m/`,
and `/p/` page prefixes, and respects the application's browser and edge TTLs.
Verify a repeated page response with `CF-Cache-Status`; purge the affected URLs
after a deploy if the five-minute edge TTL is too long for an urgent shell fix.

## Smoke test

Run the production-like Docker Compose smoke from a development checkout with:

```bash
PRASHNA_COMPOSE_SMOKE=1 uv run pytest tests/ops/test_compose_smoke.py -q
```

The smoke builds the local image, starts Compose with temporary data and upload
directories, waits for `/api/admin/status`, creates the first admin user,
uploads an image, restarts the service, and verifies the SQLite file, upload,
health endpoint, cookie signing, and safe diagnostics survive the restart.

After an image is published, CI runs the same state/restart checks against its
exact digest through the root distribution Compose model and also verifies the
in-image backup command.

The test removes its Compose project at the end. If it is interrupted, clean up
with `docker compose --project-name <printed-project> down --volumes
--remove-orphans`.

## Files

- `docker-compose.yml`: the service definition, copied to `/opt/prashna/`.
  It requires `PRASHNA_SECRET_KEY` in `.env`. The file installed on the host
  differs from it (see "Reconcile the production compose file" in
  [`docs/todo.md`](../docs/todo.md)).
- `env.example`: reference for `/opt/prashna/.env`. `setup.sh` writes that
  file with a generated key when it is missing.
- `nginx-prashna.conf`: the nginx server block, symlinked into
  `sites-enabled/`.
- `setup.sh`: the idempotent bootstrap script.
- `prepare-cloudflare-proxy.sh`: Cloudflare visitor-IP configuration for nginx.
- `enable-http2.sh`: HTTP/2 on the TLS listeners.
- `configure-cloudflare-cache.sh`: dry-run and apply reconciler for the
  Cloudflare Cache Rule for HTML shells.

## Persistent data

- SQLite DB → `/opt/prashna/data/prashna.db`
- User uploads → `/opt/prashna/uploads/`

Back these two up. Everything else is rebuilt from the image.

The container writes as UID/GID `1001:1001`, so those two host directories must
be writable by that identity. If startup logs show SQLite or upload permission
errors, fix ownership with:

```bash
sudo chown -R 1001:1001 /opt/prashna/data /opt/prashna/uploads
```

For local smoke tests only, the compose file accepts `PRASHNA_PORT`,
`PRASHNA_DATA_DIR`, and `PRASHNA_UPLOADS_HOST_DIR` overrides. Here
`PRASHNA_DATA_DIR` is the host folder mounted at `/data`; it is a Compose
variable, unrelated to the `prashna` command's `PRASHNA_DATA_DIR`. Production
keeps the `/opt/prashna` defaults.

## File permissions

`/opt/prashna/data` holds the SQLite database (the admin's password hash and
participants' profiles) and its copies. It is owned by the container's user
(uid 1001) with mode `700`, so no other account on the host can read it;
`setup.sh` sets this. `/opt/prashna/.env` is mode `600`.

## Logs and retention

The app writes operator diagnostics to the container log stream. The compose
file sends that stream to the host's systemd journal (`logging: journald`), so
the logs survive a deploy, which replaces the container. Inspect them with:

```bash
cd /opt/prashna && docker compose logs -f prashna          # current container
journalctl CONTAINER_NAME=prashna --since yesterday         # across deploys
```

The journal's size and age limits bound the logs: on the Hetzner host,
`homelab`'s `journald.yml` playbook sets 1 GB and 8 weeks. Keep at least 7
days of application logs; Prashna emits safe diagnostic context but does not
own log rotation.
