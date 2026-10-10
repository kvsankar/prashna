#!/bin/sh
# Runs the real Prashna installer in a clean, empty HOME under the work folder
# and captures its stdout/stderr verbatim to install-output.raw.txt.
# Only PATH=/usr/bin:/bin and the proxy variables are passed through.
set -eu
W="$(cd "$(dirname "$0")" && pwd)"
CLEAN="$W/clean-home"
rm -rf "$CLEAN"; mkdir -p "$CLEAN/tmp"
PROXY_ENV=""
for v in http_proxy https_proxy no_proxy HTTP_PROXY HTTPS_PROXY NO_PROXY all_proxy ALL_PROXY; do
  val="$(printenv "$v" || true)"
  [ -n "$val" ] && PROXY_ENV="$PROXY_ENV $v=$val"
done
# shellcheck disable=SC2086
env -i HOME="$CLEAN" XDG_CONFIG_HOME="$CLEAN/.config" XDG_DATA_HOME="$CLEAN/.local/share" \
  XDG_CACHE_HOME="$CLEAN/.cache" TMPDIR="$CLEAN/tmp" XDG_BIN_HOME="$CLEAN/.local/bin" PATH=/usr/bin:/bin TERM=dumb \
  $PROXY_ENV sh -c 'curl -LsSf https://kvsankar.github.io/prashna/install.sh | sh' \
  > "$W/install-output.raw.txt" 2>&1
echo "exit=$?" >> "$W/install-output.raw.txt"
