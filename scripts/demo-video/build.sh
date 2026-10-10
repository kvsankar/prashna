#!/bin/sh
# Rebuild prashna-demo.mp4 from scratch. See README.md for what each step does.
# Steps 1 and 2 need network access (installer, PyPI); steps 3-6 do not.
set -eu
W="$(cd "$(dirname "$0")" && pwd)"
cd "$W"
export UV_CACHE_DIR="$W/uv-cache"

# 1. Real installer run in a clean HOME -> install-output.raw.txt, clean-home/.local/bin/prashna
[ -x clean-home/.local/bin/prashna ] || ./run_install.sh

# 2. Tooling environment (Playwright 1.59 + httpx) for the recording scripts
[ -d tooling/.venv ] || (cd tooling && uv sync -q)

# 3. Start Prashna 0.4.0 from the clean HOME, drive the real pages headless,
#    record admin/projector/phone/terminal videos -> recordings/, timeline.json
#    (also writes server-output.raw.txt and terminal-text.txt via sanitize_terminal.py)
uv run --project tooling python record_app.py

# 4. Title / why / end cards -> cards/*.png
uv run --project tooling python shoot_cards.py

# 5. Cut, caption and concatenate -> prashna-demo.mp4, scene-list.txt
python3 -I compose.py

# 6. Review material: one frame every 6 s -> frames/, and contact-sheet.png
rm -rf frames && mkdir frames
ffmpeg -v error -i prashna-demo.mp4 -vf fps=1/6 frames/frame-%03d.png
ffmpeg -y -v error -i prashna-demo.mp4 \
  -vf "fps=1/6,scale=480:-1,tile=4x4:padding=6:margin=6:color=white" \
  -frames:v 1 -update 1 contact-sheet.png
ffprobe -v error -show_entries format=duration,size -of default=nw=1 prashna-demo.mp4

# 7. Text-level check that nothing machine-specific reached the video inputs
./check_text.sh
