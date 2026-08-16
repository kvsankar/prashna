#!/usr/bin/env bash
# Enable HTTP/2 on Certbot-managed TLS listeners without touching certificates.

set -euo pipefail

DOMAIN="${PRASHNA_DOMAIN:-prashna.sankara.net}"
SITE_PATH="${PRASHNA_NGINX_SITE_PATH:-/etc/nginx/sites-available/$DOMAIN}"
TEST_MODE="${PRASHNA_NGINX_TEST_MODE:-0}"

run_root() {
  if [[ "$TEST_MODE" == "1" ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

if [[ ! -f "$SITE_PATH" ]]; then
  echo "nginx site not found: $SITE_PATH" >&2
  exit 1
fi

if ! grep -Eq '^[[:space:]]*listen[[:space:]]+(443|\[::\]:443)[[:space:]]+ssl;' "$SITE_PATH" \
    && grep -Eq '^[[:space:]]*listen[[:space:]]+(443|\[::\]:443)[[:space:]]+ssl[[:space:]]+http2;' "$SITE_PATH"; then
  echo "HTTP/2 is already enabled in $SITE_PATH"
  exit 0
fi

if ! grep -Eq '^[[:space:]]*listen[[:space:]]+(443|\[::\]:443)[[:space:]]+ssl;' "$SITE_PATH"; then
  echo "no Certbot-managed TLS listener found in $SITE_PATH" >&2
  exit 1
fi

backup="${SITE_PATH}.bak.$(date -u +%Y%m%dT%H%M%SZ)"
run_root cp "$SITE_PATH" "$backup"
run_root sed -E -i \
  's/^([[:space:]]*listen[[:space:]]+(443|\[::\]:443)[[:space:]]+ssl);/\1 http2;/' \
  "$SITE_PATH"

if [[ "$TEST_MODE" == "1" ]]; then
  echo "Enabled HTTP/2 in $SITE_PATH (test mode; backup: $backup)"
  exit 0
fi

if sudo nginx -t; then
  sudo systemctl reload nginx
  echo "Enabled HTTP/2 in $SITE_PATH (backup: $backup)"
else
  sudo cp "$backup" "$SITE_PATH"
  sudo nginx -t
  echo "nginx validation failed; restored $backup" >&2
  exit 1
fi
