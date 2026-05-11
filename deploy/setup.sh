#!/usr/bin/env bash
# One-time bootstrap for the Hetzner box.
#
# Run as the `sankar` user. Will prompt for sudo password.
#
# Pre-reqs:
#   - DNS A record: prashna.sankara.net → 204.168.217.73 must resolve.
#   - This repo cloned somewhere readable (e.g., ~/repos/prashna).
#
# What it does:
#   1. Installs Docker CE + compose plugin (if missing) and adds you to the
#      docker group.
#   2. Creates /opt/prashna with compose + .env (you fill in the secret).
#   3. Pulls the latest image from ghcr.io (you must `docker login ghcr.io`
#      first if the repo is private).
#   4. Drops the nginx site, runs certbot for prashna.sankara.net.
#   5. Starts the container.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR=/opt/prashna
DOMAIN=prashna.sankara.net

log() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

# 1. Install Docker if missing.
if ! command -v docker >/dev/null; then
  log "Installing Docker CE"
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
  echo "NOTE: log out and back in (or run 'newgrp docker') so docker group membership takes effect."
else
  log "Docker already installed: $(docker --version)"
fi

# 2. App directory layout.
log "Creating $APP_DIR"
sudo install -d -o "$USER" -g "$USER" "$APP_DIR" "$APP_DIR/data" "$APP_DIR/uploads"
sudo cp "$REPO_DIR/deploy/docker-compose.yml" "$APP_DIR/docker-compose.yml"
sudo chown "$USER:$USER" "$APP_DIR/docker-compose.yml"

if [[ ! -f "$APP_DIR/.env" ]]; then
  log "Generating $APP_DIR/.env with a fresh PRASHNA_SECRET_KEY"
  SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  cat > /tmp/prashna.env <<EOF
PRASHNA_SECRET_KEY=$SECRET
EOF
  sudo mv /tmp/prashna.env "$APP_DIR/.env"
  sudo chown "$USER:$USER" "$APP_DIR/.env"
  sudo chmod 600 "$APP_DIR/.env"
else
  log "Keeping existing $APP_DIR/.env"
fi

# 3. Pull image (assumes you've already `docker login ghcr.io` if private).
log "Pulling image"
( cd "$APP_DIR" && docker compose pull )

# 4. nginx site + TLS.
log "Installing nginx site for $DOMAIN"
sudo cp "$REPO_DIR/deploy/nginx-prashna.conf" "/etc/nginx/sites-available/$DOMAIN"
sudo ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
sudo nginx -t
sudo systemctl reload nginx

if [[ ! -d "/etc/letsencrypt/live/$DOMAIN" ]]; then
  log "Requesting TLS cert via certbot"
  sudo certbot --nginx -d "$DOMAIN" --redirect --non-interactive --agree-tos -m "kvsankar@gmail.com"
else
  log "TLS cert already exists for $DOMAIN — skipping certbot"
fi

# 5. Start the container.
log "Starting container"
( cd "$APP_DIR" && docker compose up -d )

log "Done. Visit: https://$DOMAIN"
