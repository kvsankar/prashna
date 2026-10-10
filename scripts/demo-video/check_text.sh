#!/bin/sh
# Fails if any text that ends up on screen (terminal text, cards, captions,
# scene list) contains a path, a token, an email, a public IP, or the local
# user name. 127.0.0.1 is allowed (it is what the app prints).
set -u
W="$(cd "$(dirname "$0")" && pwd)"
files="$W/terminal-text.txt $W/cards.html $W/scene-list.txt $W/segments/captions/*.txt"
pattern='/home/|/tmp/|/Users/|clean-home|demo-setup-token|setup=[A-Za-z0-9-]{8,}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
# The local account's name must not appear on screen either.
pattern="$pattern|$(id -un)"
# shellcheck disable=SC2086
if grep -nE "$pattern" $files | grep -vE 'kvsankar\.github\.io|github\.com/kvsankar'; then
  echo "check_text: forbidden text found (see above)"; exit 1
fi
# any IPv4 that is not loopback
# shellcheck disable=SC2086
if grep -nE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' $files | grep -v '127\.0\.0\.1'; then
  echo "check_text: non-loopback IP found"; exit 1
fi
echo "check_text: ok"
