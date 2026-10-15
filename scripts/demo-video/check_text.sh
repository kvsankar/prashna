#!/bin/sh
# Fails if any text that ends up on screen or in the narration contains a
# path, a token, an email, a public IP, or the local user name. Checked: the
# terminal text, cards.html and the texts of every card (cards/texts.json)
# and device frame (segments/plates/texts.json), captions, narration,
# subtitles and the scene list. 127.0.0.1 is allowed (it is what the app
# prints). Web addresses may only be the installer scripts, the landing
# page and the tunnel's public address (a trycloudflare.com name, new on
# every run).
set -u
W="$(cd "$(dirname "$0")" && pwd)"
texts="$W/cards/texts.json $W/segments/plates/texts.json"
files="$W/terminal-text.txt $W/cards.html $texts $W/scene-list.txt $W/segments/captions/*.txt $W/narration.txt $W/prashna-demo.srt"
for f in $texts; do [ -s "$f" ] || { echo "check_text: $f is missing; run shoot_cards.py and compose.py"; exit 1; }; done
pattern='/home/|/tmp/|/Users/|clean-home|demo-setup-token|setup=[A-Za-z0-9-]{8,}|prashna_st_|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
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
# web addresses on the cards, frames, terminal and in the narration (the SVG namespace is not shown)
# shellcheck disable=SC2086
if grep -noE 'https?://[^ "<>`)|]+' "$W/cards.html" "$W/narration.txt" "$W/terminal-text.txt" $texts \
  | grep -vE ':(https://kvsankar\.github\.io/prashna/(install\.sh|install\.ps1)?|http://127\.0\.0\.1:8000|https://[a-z0-9-]+\.trycloudflare\.com|http://www\.w3\.org/2000/svg)$'; then
  echo "check_text: unexpected address found"; exit 1
fi
echo "check_text: ok"
