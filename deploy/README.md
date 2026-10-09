# Deploy

This directory holds everything the **Hetzner** box needs to run Prashna at
`https://prashna.sankara.net`.

It is not the end-user distribution bundle. Laptop and generic self-hosted
installs use the root `compose.yaml`; tagged GitHub Releases contain a
version-pinned copy with their own README and named-volume storage.

## One-time setup

1. **DNS** — create a proxied Cloudflare `A` record whose origin value is:

   ```
   prashna.sankara.net → <server-ip>
   ```

   With the orange cloud enabled, public DNS correctly returns Cloudflare
   anycast addresses rather than the server's IP. Verify the record and proxy
   state in Cloudflare before continuing.

2. **GitHub Actions** — the `Build & publish Docker image` workflow pushes to
   `ghcr.io/kvsankar/prashna`. No extra secrets needed; it uses the built-in
   `GITHUB_TOKEN` with `packages:write` permission. Trigger it once by pushing
   to `main` or running it manually so the image exists.

3. **On the server**, install nginx and Certbot if they are not already
   present. `setup.sh` installs Docker when necessary, but it expects the nginx
   and Certbot commands to exist before configuring TLS.

4. **If the GHCR package is private**, log in on the server with a token that
   has `read:packages`. A public package can be pulled anonymously:

   ```bash
   export GHCR_TOKEN=...  # GitHub token with read:packages
   echo "$GHCR_TOKEN" | docker login ghcr.io -u kvsankar --password-stdin
   ```

5. **Run the bootstrap**:

   ```bash
   git clone git@github.com:kvsankar/prashna.git ~/repos/prashna
   cd ~/repos/prashna
   CERTBOT_EMAIL=you@example.com ./deploy/setup.sh
   ```

   This installs Docker, lays down `/opt/prashna/`, fetches the image, drops
   the nginx site, requests a TLS cert via certbot, and starts the container.

## Updating

Either:

```bash
cd /opt/prashna && docker compose pull && docker compose up -d --wait
```

Or wire up the optional `deploy.yml` workflow (not included by default) that
SSHes in and runs that on every push to `main`.

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

- `docker-compose.yml` — service definition; bind-mounted to `/opt/prashna/`.
- `env.example` — copy to `/opt/prashna/.env` with a real `PRASHNA_SECRET_KEY`.
- `nginx-prashna.conf` — nginx server block; symlinked into `sites-enabled/`.
- `setup.sh` — idempotent bootstrap script.
- `configure-cloudflare-cache.sh` — dry-run/apply Cache Rule reconciler for
  static HTML shells.

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
`PRASHNA_DATA_DIR`, and `PRASHNA_UPLOADS_HOST_DIR` overrides. Production should
keep the `/opt/prashna` defaults from `env.example`.

## Logs and retention

The app writes operator diagnostics to the container log stream. Inspect them
with:

```bash
cd /opt/prashna && docker compose logs -f prashna
```

Keep at least 7 days of application logs on the host or in your external log
shipper. Configure that retention in Docker, journald, or the server's logging
stack; Prashna emits safe diagnostic context but does not own log rotation.
