# Prashna local distribution

This bundle runs the published Prashna container on a laptop or a small
self-hosted machine. It is separate from the Hetzner production configuration.

## Start

1. Install Docker Desktop or Docker Engine with the Compose plugin.
2. Copy `compose.env.example` to `.env`.
3. Replace `PRASHNA_SECRET_KEY` in `.env` with output from one of:

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   openssl rand -base64 48
   ```

4. Start Prashna and wait for its health check:

   ```bash
   docker compose pull
   docker compose up -d --wait
   ```

5. Open <http://127.0.0.1:8000/> and create the first admin locally.

The release bundle pins `PRASHNA_IMAGE_TAG` to its version. Upgrade only after
reading the release notes, then change the tag in `.env` and run the two Docker
commands again.

For public distribution, the `prashna` container package must be set to
**Public** in GitHub Packages. While it is private, authorized users must first
authenticate with a GitHub token carrying `read:packages`:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_LOGIN --password-stdin
```

Do not put the token in `.env`; that file is passed to Compose and is for
application configuration only.

## Share temporarily with ngrok

Complete first-admin setup locally. Then set
`PRASHNA_TRUSTED_PROXY_HOPS=1` in `.env`, restart with
`docker compose up -d`, and run:

```bash
ngrok http 8000
```

The ngrok URL is public. Stop ngrok when the session is over.

## Backup

The database and uploads live in Docker named volumes. This command creates a
consistent archive inside the container, including SQLite WAL state and all
uploads:

```bash
mkdir -p backups
name="prashna-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
docker compose exec -T prashna python -m app.backup create "/data/$name"
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
  python -m app.backup restore "/data/$archive" --confirm
docker compose start prashna
docker compose exec -T prashna rm "/data/$archive"
```

After restoring, open <http://127.0.0.1:8000/api/admin/status> and confirm the
expected session data. Copy the reported `prashna-pre-restore-*.tar.gz` out of
the container before deleting it.

## Useful commands

```bash
docker compose ps
docker compose logs -f prashna
docker compose restart prashna
docker compose down                 # keeps named volumes
docker compose down --volumes       # DELETES database and uploads
```
