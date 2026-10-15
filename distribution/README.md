# Run Prashna in Docker

This guide is for people who want to run Prashna in a Docker container
instead of installing the `prashna` command. The container runs on a
laptop or on a small machine that you host yourself. To install the command, see the
[README](https://github.com/kvsankar/prashna#install). The
[user guide](https://github.com/kvsankar/prashna/blob/main/docs/user-guide.md)
explains how to use Prashna once it runs.

## Get the release bundle

Each Prashna release has a bundle, `prashna-<version>.zip` (and the same
files as `prashna-<version>.tar.gz`), on the
[GitHub Releases page](https://github.com/kvsankar/prashna/releases). For
release 0.6.1, the file is `prashna-0.6.1.zip`. `SHA256SUMS` beside it
holds the checksums of both files.

The bundle holds three files: `compose.yaml`, `compose.env.example` and
this guide. Its `compose.yaml` uses the image of that release, for
example `ghcr.io/kvsankar/prashna:0.6.1`.

1. Download `prashna-<version>.zip` and unzip it.
2. Open a terminal in the unzipped folder `prashna-<version>`.

If you are reading this guide inside the bundle, you have done these
steps.

The `compose.yaml` in the root of the source repository is not pinned to
a release. It uses the image tag `latest`, which follows the `main`
branch and is not a release. Use the bundle, or a release tag such as
`0.6.1`, to run a released version.

## Start

1. Install Docker Desktop, or Docker Engine with the Compose plugin.
2. In the bundle folder, start Prashna and wait for its health check:

   ```sh
   docker compose up -d --wait
   ```

3. On a fresh install, find the one-time setup link in the log:

   ```sh
   docker compose logs prashna
   ```

   The link ends in `/#setup=…`.

4. Open <http://127.0.0.1:8000/> followed by the `/#setup=…` part from the
   log, and choose the admin's username and password. The link works
   once.

No `.env` file is needed. Prashna creates its cookie-signing key in the
data volume on the first start. To change the port or the address it
listens on, choose another release, or set other options, copy
`compose.env.example` to `.env`. That file describes each setting.

The database and the uploads live in two Compose named volumes:
`prashna-data` (mounted at `/data`) and `prashna-uploads` (mounted at
`/app/uploads`). They stay when you replace the container.

## Start without Compose

The image also runs on its own. Replace `0.6.1` with the release you
want:

```sh
docker run -d --name prashna -p 127.0.0.1:8000:8000 -v prashna-data:/data -v prashna-uploads:/app/uploads ghcr.io/kvsankar/prashna:0.6.1
```

Then find the setup link in its log:

```sh
docker logs prashna
```

## Upgrade

Read the release notes first. Then download the new release bundle and
copy your `.env`, if you have one, into its folder. If your `.env` sets
`PRASHNA_IMAGE_TAG`, change it to the new version. In the new bundle
folder, pull the new image:

```sh
docker compose pull
```

Then replace the container:

```sh
docker compose up -d --wait
```

The named volumes, and so your data, stay. Both bundles use the Compose
project name `prashna`, so they use the same volumes.

## Share over the internet

1. In `.env`, set `PRASHNA_TRUSTED_PROXY_HOPS=1`, then restart:

   ```sh
   docker compose up -d
   ```

2. On the same machine, start a tunnel. For a Cloudflare quick tunnel
   (no account needed):

   ```sh
   cloudflared tunnel --url http://127.0.0.1:8000
   ```

   Or, for ngrok (signed in):

   ```sh
   ngrok http 8000
   ```

3. Copy the `https://` address that the tunnel prints. On each session's
   page, open **Set up** and paste the address into **Base URL** in the
   **Invite participants** card. The participant link and the projector's
   QR code then use it.

The address is public. Stop the tunnel when the session is over.

## Back up

This command creates a backup file inside the container. The file holds
the database and all uploads. Replace the date in the file name with
today's date.

```sh
docker compose exec -T prashna python -m prashna.backup create /data/prashna-20261015.tar.gz
```

Copy the file out of the container into the folder `backups`:

```sh
docker compose cp prashna:/data/prashna-20261015.tar.gz backups/prashna-20261015.tar.gz
```

Then delete it inside the container:

```sh
docker compose exec -T prashna rm /data/prashna-20261015.tar.gz
```

Keep backup files outside the Docker volumes.

## Restore

Restore replaces the database and the uploads. Before it changes
anything, it saves the current data in an extra file,
`prashna-pre-restore-<time>.tar.gz`, beside the restored file. Replace
`prashna-20261015.tar.gz` with your backup file.

1. Copy the backup file into the container:

   ```sh
   docker compose cp backups/prashna-20261015.tar.gz prashna:/data/prashna-20261015.tar.gz
   ```

2. Stop Prashna:

   ```sh
   docker compose stop prashna
   ```

3. Restore:

   ```sh
   docker compose run --rm --no-deps prashna python -m prashna.backup restore /data/prashna-20261015.tar.gz --confirm
   ```

   It prints the name of the pre-restore file.

4. Start Prashna:

   ```sh
   docker compose start prashna
   ```

5. Copy the pre-restore file out of the container, with the name that
   step 3 printed:

   ```sh
   docker compose cp prashna:/data/prashna-pre-restore-<time>.tar.gz backups/
   ```

6. Delete both files inside the container:

   ```sh
   docker compose exec -T prashna rm /data/prashna-20261015.tar.gz /data/prashna-pre-restore-<time>.tar.gz
   ```

After the restore, open <http://127.0.0.1:8000/>, sign in, and check
that the session list shows the sessions you expect.

## Reset the admin password

If you forgot the admin password, set a new one:

```sh
docker compose exec prashna python -m prashna reset-password
```

It asks for the new password twice and needs at least 8 characters.

## Useful commands

Show the container's state:

```sh
docker compose ps
```

Follow the log:

```sh
docker compose logs -f prashna
```

Restart Prashna:

```sh
docker compose restart prashna
```

Stop and remove the container. The named volumes, and so your data,
stay:

```sh
docker compose down
```

Stop and remove the container and **delete the database and uploads**:

```sh
docker compose down --volumes
```
