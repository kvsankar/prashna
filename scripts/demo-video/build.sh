#!/bin/sh
# Rebuild prashna-demo.mp4 (narrated, no captions), prashna-demo-silent.mp4
# (captions burned in) and prashna-demo.srt from scratch.
# See README.md for what each step does. Steps 1-3 need network access the
# first time (installer, PyPI, Hugging Face). Step 4 needs internet and
# cloudflared every time: it records through a real Cloudflare quick tunnel.
set -eu
W="$(cd "$(dirname "$0")" && pwd)"
cd "$W"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$W/uv-cache}"

# 1. Real installer run in a clean HOME -> install-output.raw.txt, clean-home/.local/bin/prashna
[ -x clean-home/.local/bin/prashna ] || ./run_install.sh

# 2. Tooling environment (Playwright 1.59, httpx, kokoro-onnx) for the scripts below
[ -d tooling/.venv ] || (cd tooling && uv sync -q)

# 3. Narration: Kokoro-82M speaks narration.txt -> voice/*.wav, durations.json,
#    provenance.json; voice-samples/ holds the same passage in two other voices.
#    Downloads and hash-checks the model into models/ on first run.
uv run --project tooling python voice.py --samples

# 4. Start `prashna --tunnel cloudflare` (0.6.0, clean HOME), drive the real
#    pages headless (phones through the public trycloudflare.com address),
#    record laptop/projector/phone videos -> recordings/, timeline.json
#    (also writes server-output.raw.txt and terminal-text.txt via sanitize_terminal.py)
uv run --project tooling python record_app.py

# 5. The designed cards from cards.html, one frame at a time, timed to the
#    narration -> cards/01-hook.mp4, 02-hook.mp4, 04-why.mp4, 12-tunnel.mp4, 15-end.mp4
uv run --project tooling python shoot_cards.py

# 6. Place the recordings in device frames, zoom the laptop shots, fit scenes
#    to the voice, caption, mix and normalise the narration
#    -> prashna-demo.mp4 (no captions), prashna-demo-silent.mp4 (captions),
#    prashna-demo.srt, scene-list.txt, opening-preview.png, ending-preview.png
uv run --project tooling python compose.py

# 7. Review material: one frame every 6 s -> frames/, and contact-sheet.png;
#    loudness and true peak of the final file
rm -rf frames && mkdir frames
ffmpeg -v error -i prashna-demo.mp4 -vf fps=1/6 frames/frame-%03d.png
ffmpeg -y -v error -i prashna-demo.mp4 \
  -vf "fps=1/6,scale=480:-1,tile=4x4:padding=6:margin=6:color=white" \
  -frames:v 1 -update 1 contact-sheet.png
ffprobe -v error -show_entries format=duration,size -of default=nw=1 prashna-demo.mp4
ffprobe -v error -show_entries stream=index,codec_type,codec_name -of csv=p=0 prashna-demo.mp4
ffmpeg -hide_banner -nostats -i prashna-demo.mp4 -map 0:a -af ebur128=peak=true -f null - 2>&1 \
  | sed -n '/Summary:/,$p'

# 8. Text-level check that nothing machine-specific reached the screen or the narration
./check_text.sh
