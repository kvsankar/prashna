# Run Prashna in Docker

This guide is for people who want to run Prashna in a Docker container
instead of installing the `prashna` command. The container runs on a
laptop, or on a server of your own with HTTPS on your domain. To install
the command, see the
[README](https://github.com/kvsankar/prashna#install). The
[user guide](https://github.com/kvsankar/prashna/blob/main/docs/user-guide.md)
explains how to use Prashna once it runs.

## Get the release bundle

Each Prashna release has a bundle, `prashna-<version>.zip` (and the same
files as `prashna-<version>.tar.gz`), on the
[GitHub Releases page](https://github.com/kvsankar/prashna/releases). For
release 0.6.1, the file is `prashna-0.6.1.zip`. `SHA256SUMS` beside it
holds the checksums of both files.

The bundle holds five files:

- `compose.yaml` runs Prashna. It uses the image of that release, for
  example `ghcr.io/kvsankar/prashna:0.6.1`.
- `compose.https.yaml` and `Caddyfile` add HTTPS on your own domain (see
  [Run on your own server with HTTPS](#run-on-your-own-server-with-https)).
- `compose.env.example` describes the optional settings.
- `README.md` is this guide.

On a laptop:

1. Download `prashna-<version>.zip` and unzip it.
2. Open a terminal in the unzipped folder `prashna-<version>`.

On a server, use the commands in
[Run on your own server with HTTPS](#run-on-your-own-server-with-https).
If you are reading this guide inside the bundle, you have done these
steps.

The `compose.yaml` in the root of the source repository is not pinned to
a release. It uses the image tag `latest`, which follows the `main`
branch and is not a release. Use the bundle, or a release tag such as
`0.6.1`, to run a released version.

## Start

1. Install Docker Desktop, or Docker Engine with the Compose plugin. On
   Linux, run each `docker` command in this guide with `sudo`, unless
   your user is in the `docker` group.
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

By default, Prashna accepts connections from this machine only
(`127.0.0.1`). Warning: `PRASHNA_BIND_ADDR=0.0.0.0` publishes plain HTTP
to everyone who can reach the machine. Passwords then cross the network
unencrypted. Docker's published ports bypass UFW rules, so a UFW rule
does not protect the port. Use `0.0.0.0` only on a trusted local network.
On an internet server, use HTTPS as described below.

The database and the uploads live in two Compose named volumes:
`prashna-data` (mounted at `/data`) and `prashna-uploads` (mounted at
`/app/uploads`). They stay when you replace the container.

## Run on your own server with HTTPS

This section is for a server with a public address and a domain name,
for example a small cloud server. Prashna runs behind Caddy, a web server
that gets and renews a free Let's Encrypt certificate for your domain.
Prashna itself publishes no port. The commands are for Ubuntu or Debian.
Replace `quiz.example.org` with your domain.

Before you start:

- Point your domain at the server. Create a DNS A record with the
  server's IPv4 address. If the server has IPv6, also create an AAAA
  record with its IPv6 address. If the DNS is at Cloudflare, set the
  records to "DNS only".
- Open ports 80 and 443 (TCP) in any cloud firewall in front of the
  server. Many cloud providers allow only SSH by default. Caddy needs
  port 80 to get the certificate.
- Check that no other program on the server uses ports 80 and 443. If a
  web server already runs there, see
  [Already run a reverse proxy?](#already-run-a-reverse-proxy).
- Install Docker with Compose 2.24 or later.

To install Docker with the Compose plugin, use Docker's install script:

```sh
curl -fsSL https://get.docker.com | sudo sh
```

If Docker is already installed, check the Compose version:

```sh
docker compose version
```

If that command fails on Ubuntu, Docker came from Ubuntu's `docker.io`
package, which has no Compose plugin. Install it:

```sh
sudo apt install docker-compose-v2
```

Every bundle uses the Compose project name `prashna`. If this server
already runs another Compose project named `prashna`, set another name
before the first start (step 6 below). To list the projects:

```sh
sudo docker compose ls
```

### Install and start

1. Download the bundle:

   ```sh
   curl -fsSLO https://github.com/kvsankar/prashna/releases/download/v0.6.1/prashna-0.6.1.tar.gz
   ```

2. Download the checksums:

   ```sh
   curl -fsSLO https://github.com/kvsankar/prashna/releases/download/v0.6.1/SHA256SUMS
   ```

3. Check the download. It prints `prashna-0.6.1.tar.gz: OK`:

   ```sh
   sha256sum -c --ignore-missing SHA256SUMS
   ```

4. Unpack the bundle. Many servers have no `unzip`, so use the
   `.tar.gz`:

   ```sh
   tar xzf prashna-0.6.1.tar.gz
   ```

5. Go to the bundle folder:

   ```sh
   cd prashna-0.6.1
   ```

6. Turn on HTTPS for your domain. This writes a `.env` with two settings:
   `COMPOSE_FILE` adds `compose.https.yaml` to every `docker compose`
   command, and `PRASHNA_DOMAIN` names your domain.

   ```sh
   printf 'COMPOSE_FILE=compose.yaml:compose.https.yaml\nPRASHNA_DOMAIN=%s\n' quiz.example.org > .env
   ```

   On a server that already runs another Compose project named
   `prashna`, also add a line such as `COMPOSE_PROJECT_NAME=prashna-quiz`
   to `.env`.

7. Start Prashna and Caddy. The first start downloads both images.

   ```sh
   sudo docker compose up -d --wait
   ```

8. Wait until Caddy has the certificate, usually a few seconds after the
   start. This command prints a line when it has. If it prints nothing,
   wait a few seconds and run it again.

   ```sh
   sudo docker compose logs caddy | grep "certificate obtained"
   ```

9. Find the one-time setup link:

   ```sh
   sudo docker compose logs prashna | grep setup=
   ```

   The line ends in `/#setup=…`.

10. In a browser, open `https://quiz.example.org` followed by the
    `/#setup=…` part of that line, and choose the admin's username and
    password. The link works once.

If `PRASHNA_DOMAIN` is missing from `.env`, Compose stops with the
message "Set PRASHNA_DOMAIN in .env to your domain name".

Because `.env` turns on the add-on, the other commands in this guide
(backup, restore, password reset, logs) work unchanged. Where they say
<http://127.0.0.1:8000/>, open your domain instead.

The `Caddyfile` sends an HSTS header: browsers then use only HTTPS for
your domain for one year. If the domain may serve plain HTTP later,
delete the `header` line from the `Caddyfile` before the first start.

### If the site does not load

Look for errors in Caddy's log:

```sh
sudo docker compose logs caddy | grep '"level":"error"'
```

Some normal Caddy lines contain the word "error" in a field. Only lines
with `"level":"error"` are errors. The usual causes are a DNS record that
does not point at the server yet, and a firewall that blocks port 80 or
443.

## Already run a reverse proxy?

If the server already runs a web server such as nginx or Caddy on ports
80 and 443, do not use `compose.https.yaml`. Keep `compose.yaml` alone
(no `COMPOSE_FILE` in `.env`), so Prashna listens on `127.0.0.1:8000`, and
let your web server forward to it:

- In `.env`, set `PRASHNA_TRUSTED_PROXY_HOPS=1`: one proxy hop. Prashna
  then reads each visitor's address from the proxy's `X-Forwarded-For`
  header, and the scheme from `X-Forwarded-Proto`. Without it, rate limits
  treat all visitors as one.
- Forward WebSockets. Live updates use WebSocket connections on `/ws/`,
  which stay open for the whole session.
- Allow request bodies of 6 MB. Uploads can be up to 5 MB.

An nginx site for `quiz.example.org`. Add HTTPS to it as for your other
sites, for example with `certbot --nginx`.

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    listen [::]:80;
    server_name quiz.example.org;

    # Uploads can be up to 5 MB.
    client_max_body_size 6m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket upgrade for /ws/...
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        $connection_upgrade;

        # Long timeouts so open WebSocket connections are not closed.
        proxy_read_timeout 1h;
        proxy_send_timeout 1h;
    }
}
```

In Caddy, the site needs one line, `reverse_proxy 127.0.0.1:8000`. Caddy
forwards WebSockets and sets the headers itself.

If the DNS is at Cloudflare, set the record to "DNS only". With
Cloudflare's proxy turned on, every visitor seems to come from a
Cloudflare address, unless your web server is set up to trust
Cloudflare's addresses.

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

## Update

1. Read the release notes.
2. Download and unpack the new bundle beside the old one, as in
   [Get the release bundle](#get-the-release-bundle) or
   [Install and start](#install-and-start).
3. Copy `.env`, if you have one, from the old folder into the new one.
   It brings the domain and the HTTPS add-on with it.
4. In the new folder, start the new release:

   ```sh
   docker compose up -d --wait
   ```

   Compose downloads the new image and replaces the container.

If your `.env` sets `PRASHNA_IMAGE_TAG`, it keeps that release. Delete
the line, or change it to the new version. To also get the newest Caddy 2
release, run `docker compose pull` before step 4.

Your data stays. Every bundle uses the Compose project name `prashna`,
or the name in `COMPOSE_PROJECT_NAME`. So the new folder takes over the
same containers and volumes, including the certificate. Keep one folder
in control of the live project: from now on, run the commands in the new
folder only. Do not run `docker compose down` in the old folder, because it
stops the live site. To go back to the old release, run
`docker compose up -d --wait` in the old folder.

### Run an unreleased build

Release tags are the supported choice. Builds from `main` are not tested
between releases, so use one only to try a fix before it is released.

Every push to the `main` branch publishes an image with three tags:
`latest`, `main` and `sha-<short commit>`, for example `sha-5d2d6d0`. The
`sha-` tag names one exact commit. To run it, set the tag in `.env`, for
example `PRASHNA_IMAGE_TAG=sha-5d2d6d0`. Then download the image:

```sh
docker compose pull -q
```

And replace the container:

```sh
docker compose up -d --wait
```

To roll back, set the previous tag in `.env`, and run the same two
commands. To go back to the bundle's release, delete the line instead.

If that commit also changed the bundle files (`compose.yaml`,
`compose.https.yaml`, `Caddyfile` or `compose.env.example`), build a
bundle from it. In a clone of the repository at that commit, run
`python3 scripts/build_release_bundle.py` with the current release
number, for example `0.6.1`. It writes the bundle into `dist/`. Unpack
it and copy your `.env` into it, as for an update.

## Share over the internet

For a quick session from a laptop, use a tunnel. For a permanent
address, see
[Run on your own server with HTTPS](#run-on-your-own-server-with-https).

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

Run these commands in the bundle folder. First create the folder
`backups` for the backup files:

```sh
mkdir -p backups
```

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

Keep backup files outside the Docker volumes. Also copy them off the
machine: a backup on the same disk is lost with the disk.

### Back up every night (optional)

On a server, root's crontab can make a backup every night. Create the
folder for the backup files:

```sh
sudo mkdir -p /var/backups/prashna
```

Open root's crontab:

```sh
sudo crontab -e
```

Add this line. Replace `/srv/prashna-0.6.1` with your bundle
folder, and change it after each update.

```text
30 3 * * * cd /srv/prashna-0.6.1 && docker compose exec -T prashna python -m prashna.backup create /data/nightly.tar.gz && docker compose cp prashna:/data/nightly.tar.gz /var/backups/prashna/prashna-$(date +\%Y\%m\%d).tar.gz && docker compose exec -T prashna rm /data/nightly.tar.gz
```

It makes a backup at 03:30, server time. Each file holds the whole
database and all uploads, so delete old files from time to time. Copy
the files off the machine, for example with `rsync` or your provider's
backup service.

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

After the restore, open <http://127.0.0.1:8000/> (or your domain), sign
in, and check that the session list shows the sessions you expect.

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
