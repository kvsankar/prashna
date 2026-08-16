# Deploy

This directory holds everything the **Hetzner** box needs to run Prashna at
`https://prashna.sankara.net`.

It is not the end-user distribution bundle. Laptop and generic self-hosted
installs use the root `compose.yaml`; tagged GitHub Releases contain a
version-pinned copy with their own README and named-volume storage.

## One-time setup

1. **DNS** — add an `A` record:

   ```
   prashna.sankara.net → 204.168.217.73
   ```

   Wait for it to resolve before continuing (`dig +short prashna.sankara.net`).

2. **GitHub Actions** — the `Build & publish Docker image` workflow pushes to
   `ghcr.io/kvsankar/prashna`. No extra secrets needed; it uses the built-in
   `GITHUB_TOKEN` with `packages:write` permission. Trigger it once by pushing
   to `main` or running it manually so the image exists.

3. **On the server**, log in to GHCR so the private image can be pulled:

   ```bash
   # Create a PAT with `read:packages` scope:
   # https://github.com/settings/tokens
   echo <PAT> | docker login ghcr.io -u kvsankar --password-stdin
   ```

4. **Run the bootstrap**:

   ```bash
   git clone https://github.com/kvsankar/prashna.git ~/repos/prashna
   cd ~/repos/prashna
   ./deploy/setup.sh
   ```

   This installs Docker, lays down `/opt/prashna/`, fetches the image, drops
   the nginx site, requests a TLS cert via certbot, and starts the container.

## Updating

Either:

```bash
cd /opt/prashna && docker compose pull && docker compose up -d
```

Or wire up the optional `deploy.yml` workflow (not included by default) that
SSHes in and runs that on every push to `main`.

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
