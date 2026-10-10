# Prashna demo video build

Builds `prashna-demo.mp4` (1920x1080, 30 fps, H.264, silent, captions on
screen) from real headless screen recordings of Prashna 0.4.0.

## Steps

`./build.sh` runs all of them. Individually:

1. `./run_install.sh` runs the real installer
   (`curl -LsSf https://kvsankar.github.io/prashna/install.sh | sh`) in an
   empty HOME under `clean-home/` with `PATH=/usr/bin:/bin` and only the proxy
   variables passed through; the verbatim output goes to
   `install-output.raw.txt`. `TMPDIR` is pointed inside the clean HOME because
   `/tmp` is read-only in the sandbox where this was built.
2. `cd tooling && uv sync` creates the Playwright 1.59 + httpx environment used
   by the recording scripts (`UV_CACHE_DIR` is set to `uv-cache/` by
   `build.sh`).
3. `uv run --project tooling python record_app.py` starts the installed
   `prashna` on 127.0.0.1:8000 with an empty `demo-data/` folder, a fixed
   `PRASHNA_SETUP_TOKEN` and rate limiting off, then records headless:
   `admin` (1920x1080: setup, session, quiz library, moderator actions),
   `projector` (1920x1080), `phone` (390x844, mobile, touch) and `terminal`
   (the install scene, `terminal.html` typing `terminal-text.txt`). Four
   other participants are simulated with httpx clients, each with its own
   voter cookie. Outputs: `recordings/*.webm`, `timeline.json` (wall-clock
   marks and each recording's start), `shots/*.png` (checkpoints),
   `server-output.raw.txt`, and `terminal-text.txt` via
   `sanitize_terminal.py`.
4. `uv run --project tooling python shoot_cards.py` screenshots the title,
   why and end cards from `cards.html` into `cards/`.
5. `python3 -I compose.py` cuts each scene from the recordings using the
   timeline marks, burns the captions in with ffmpeg `drawtext` (Inter), puts
   projector and phone side by side for the live scenes, and concatenates the
   segments into `prashna-demo.mp4`. It also writes `scene-list.txt`.
6. ffmpeg extracts one frame every 6 s into `frames/` and tiles them into
   `contact-sheet.png`.
7. `./check_text.sh` greps every text that reaches the screen for paths,
   tokens, emails, non-loopback IPs and the local user name.

## Sanitising rules (`sanitize_terminal.py`)

Only these edits are made to the captured terminal output: absolute paths in
the work folder become `~` or `~/.local/share/prashna`, the setup token
becomes `prashna_st_…`, the `+ package==version` list is shortened with one
`…` line, and the trailing `exit=0` marker is dropped.

## Fictional content

Admin `trainer`; session "Product onboarding workshop"; quiz "Onboarding
check"; participants Diego (the phone), Asha, Ben, Chen, Mira. No real
people, emails, addresses, tokens or machine paths appear.
