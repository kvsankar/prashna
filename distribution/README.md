# Prashna local distribution

This bundle runs the published Prashna container on a laptop or a small
self-hosted machine. It is separate from the Hetzner production configuration.

## Start

1. Install Docker Desktop or Docker Engine with the Compose plugin.
2. Start Prashna and wait for its health check:

   ```bash
   docker compose up -d --wait
   ```

3. On a fresh install, find the one-time setup link in the log:

   ```bash
   docker compose logs prashna | grep setup=
   ```

4. Open <http://127.0.0.1:8000/> plus the `/#setup=...` path from the log,
   and choose the admin's username and password. The link works once.

No `.env` is needed. The cookie-signing key is generated into the data volume
on first start. To change the port or bind address, pin a version, or set
optional values, copy `compose.env.example` to `.env`; the file describes each
setting.

The database and uploads live in the Compose named volumes `prashna-data`
(mounted at `/data`) and `prashna-uploads` (mounted at `/app/uploads`). They
survive container replacement.

## Start without Compose

The image also runs on its own:

```bash
docker run -d --name prashna -p 127.0.0.1:8000:8000 \
  -v prashna-data:/data -v prashna-uploads:/app/uploads \
  ghcr.io/kvsankar/prashna
docker logs prashna 2>&1 | grep setup=
```

## Upgrade

The release bundle pins `PRASHNA_IMAGE_TAG` to its version. Upgrade only after
reading the release notes, then change the tag in `.env` and run
`docker compose pull` and `docker compose up -d --wait`.

## Registry access

Anonymous pulls work only while the `prashna` container package is set to
**Public** in GitHub Packages. That setting belongs to the GitHub account, not
to the repository workflow. While the package is private, authorized users
first sign in with a GitHub token that has `read:packages`:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_LOGIN --password-stdin
```

Do not put the token in `.env`; that file is passed to Compose and is for
application configuration only.

## Share temporarily over the internet

Set `PRASHNA_TRUSTED_PROXY_HOPS=1` in `.env`, restart with
`docker compose up -d`, and run one of these on the same machine:

```bash
cloudflared tunnel --url http://127.0.0.1:8000    # Cloudflare quick tunnel, no account
ngrok http 8000                                   # ngrok, signed in
```

Copy the `https://` address it prints. On each session's page, paste it into
**Base URL** in the Invite card, so the participant link and the projector's
QR code use it. The address is public; stop the tunnel when the session is
over.

## Backup

The database and uploads live in Docker named volumes. This command creates a
consistent archive inside the container, including SQLite WAL state and all
uploads:

```bash
mkdir -p backups
name="prashna-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
docker compose exec -T prashna python -m prashna.backup create "/data/$name"
docker compose cp "prashna:/data/$name" "backups/$name"
docker compose exec -T prashna rm "/data/$name"
```

Keep backup archives outside the Docker volumes.

## Restore

Restore replaces the database and uploads. The command creates an additional
pre-restore archive beside the staged archive before changing anything.

```bash
archive=prashna-YYYYMMDDTHHMMSSZ.tar.gz
docker compose cp "backups/$archive" "prashna:/data/$archive"
docker compose stop prashna
docker compose run --rm --no-deps prashna \
  python -m prashna.backup restore "/data/$archive" --confirm
docker compose start prashna
docker compose exec -T prashna rm "/data/$archive"
```

After restoring, open <http://127.0.0.1:8000/>, sign in, and check that the
session list shows the expected sessions. Copy the reported
`prashna-pre-restore-*.tar.gz` out of the container before deleting it.

## Useful commands

```bash
docker compose ps
docker compose logs -f prashna
docker compose restart prashna
docker compose down                 # keeps named volumes
docker compose down --volumes       # DELETES database and uploads
```
