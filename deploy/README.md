# Deploy

This directory holds everything the **Hetzner** box needs to run Prashna at
`https://prashna.sankara.net`.

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
   # Create a PAT with `read:packages` scope at https://github.com/settings/tokens
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

## Files

- `docker-compose.yml` — service definition; bind-mounted to `/opt/prashna/`.
- `env.example` — copy to `/opt/prashna/.env` with a real `PRASHNA_SECRET_KEY`.
- `nginx-prashna.conf` — nginx server block; symlinked into `sites-enabled/`.
- `setup.sh` — idempotent bootstrap script.

## Persistent data

- SQLite DB → `/opt/prashna/data/prashna.db`
- User uploads → `/opt/prashna/uploads/`

Back these two up. Everything else is rebuilt from the image.
