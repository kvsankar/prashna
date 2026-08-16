#!/usr/bin/env bash
# Prepare nginx to preserve the visitor IP when Cloudflare proxying is enabled.

set -euo pipefail

DOMAIN="${PRASHNA_DOMAIN:-prashna.sankara.net}"
SITE_PATH="${PRASHNA_NGINX_SITE_PATH:-/etc/nginx/sites-available/$DOMAIN}"
INCLUDE_PATH="${PRASHNA_CLOUDFLARE_INCLUDE_PATH:-/etc/nginx/snippets/prashna-cloudflare-realip.conf}"
IPV4_URL="${PRASHNA_CLOUDFLARE_IPV4_URL:-https://www.cloudflare.com/ips-v4}"
IPV6_URL="${PRASHNA_CLOUDFLARE_IPV6_URL:-https://www.cloudflare.com/ips-v6}"
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

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

curl -fsSL "$IPV4_URL" -o "$work_dir/ips-v4"
curl -fsSL "$IPV6_URL" -o "$work_dir/ips-v6"

python3 - "$work_dir/ips-v4" "$work_dir/ips-v6" > "$work_dir/cloudflare-realip.conf" <<'PY'
import ipaddress
import pathlib
import sys

ranges = []
for expected_version, source in zip((4, 6), sys.argv[1:]):
    source_ranges = []
    for raw_line in pathlib.Path(source).read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        network = ipaddress.ip_network(line, strict=True)
        if network.version != expected_version:
            raise SystemExit(f"unexpected IPv{network.version} range in {source}: {line}")
        source_ranges.append(str(network))
    if not source_ranges:
        raise SystemExit(f"Cloudflare IPv{expected_version} range response was empty")
    ranges.extend(source_ranges)

print("# Generated from Cloudflare's published IP ranges.")
print("# Re-run deploy/prepare-cloudflare-proxy.sh to refresh this file.")
for network in ranges:
    print(f"set_real_ip_from {network};")
print("real_ip_header CF-Connecting-IP;")
print("real_ip_recursive on;")
PY

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
site_backup="${SITE_PATH}.bak.${timestamp}"
include_backup=""
include_existed=0

run_root cp "$SITE_PATH" "$site_backup"
if [[ -f "$INCLUDE_PATH" ]]; then
  include_existed=1
  include_backup="${INCLUDE_PATH}.bak.${timestamp}"
  run_root cp "$INCLUDE_PATH" "$include_backup"
fi

run_root install -d -m 0755 "$(dirname "$INCLUDE_PATH")"
run_root install -m 0644 "$work_dir/cloudflare-realip.conf" "$INCLUDE_PATH"

include_line="include $INCLUDE_PATH;"
if ! grep -Fqx "$include_line" "$SITE_PATH"; then
  {
    printf '%s\n\n' "$include_line"
    cat "$SITE_PATH"
  } > "$work_dir/site.conf"
  run_root install -m 0644 "$work_dir/site.conf" "$SITE_PATH"
fi

if [[ "$TEST_MODE" == "1" ]]; then
  echo "Prepared Cloudflare visitor-IP handling in $SITE_PATH (test mode; backup: $site_backup)"
  exit 0
fi

if sudo nginx -t && sudo systemctl reload nginx; then
  echo "Prepared Cloudflare visitor-IP handling in $SITE_PATH (backup: $site_backup)"
else
  sudo cp "$site_backup" "$SITE_PATH"
  if [[ "$include_existed" == "1" ]]; then
    sudo cp "$include_backup" "$INCLUDE_PATH"
  else
    sudo rm -f "$INCLUDE_PATH"
  fi
  sudo nginx -t
  echo "nginx validation failed; restored previous configuration" >&2
  exit 1
fi
