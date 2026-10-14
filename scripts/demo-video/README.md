# Prashna demo video build

Builds the Prashna demo video (about 92 s, 1920x1080, 30 fps, H.264) from real
headless screen recordings of Prashna 0.6.0, with a spoken narration and the
same words burned in as captions. Outputs:

- `prashna-demo.mp4`: video with narration (AAC-LC, 48 kHz, 192 kbit/s,
  -14 LUFS integrated, true peak at most -1 dBTP), `+faststart`.
- `prashna-demo-silent.mp4`: the same video without sound.
- `prashna-demo.srt`: the narration as subtitles, timed to the voice.
- `contact-sheet.png` and `frames/`: one frame every 6 s, for review.
- `voice-samples/`: the why-card passage in the chosen voice and two others.

## Steps

`./build.sh` runs all of them. Individually:

1. `./run_install.sh` runs the real installer
   (`curl -LsSf https://kvsankar.github.io/prashna/install.sh | sh`) in an
   empty HOME under `clean-home/` with `PATH=/usr/bin:/bin` and only the proxy
   variables passed through; the verbatim output goes to
   `install-output.raw.txt`. `TMPDIR` is pointed inside the clean HOME, so the
   step also works where `/tmp` is read-only.
2. `cd tooling && uv sync` creates the environment used by the Python steps:
   Playwright 1.59, httpx, and kokoro-onnx with ONNX Runtime (versions pinned
   in `tooling/uv.lock`). `build.sh` sets `UV_CACHE_DIR` to `uv-cache/` unless
   it is already set.
3. `uv run --project tooling python voice.py --samples` speaks each line of
   `narration.txt` with Kokoro-82M v1.0 (see Narration below) into
   `voice/<scene>.wav`, and writes `voice/durations.json` and
   `voice/provenance.json`. With `--samples` it also writes
   `voice-samples/<voice>.wav`.
4. `uv run --project tooling python record_app.py` starts the installed
   `prashna` on 127.0.0.1:8000 with an empty `demo-data/` folder, a fixed
   `PRASHNA_SETUP_TOKEN` and rate limiting off, then records headless:
   `admin` (1920x1080: setup, session, quiz library with a publish problem
   and its fix, session page, moderator actions), `projector` (1920x1080),
   `phone` (390x844, mobile, touch) and `terminal` (the install scene,
   `terminal.html` typing `terminal-text.txt`). Four other participants are
   simulated with httpx clients, each with its own voter cookie. Outputs:
   `recordings/*.webm`, `timeline.json` (wall-clock marks and each
   recording's start), `shots/*.png` (checkpoints), `server-output.raw.txt`,
   and `terminal-text.txt` via `sanitize_terminal.py`.
5. `uv run --project tooling python shoot_cards.py` screenshots the title,
   why and end cards from `cards.html` into `cards/`.
6. `python3 -I compose.py` cuts each scene from the recordings using the
   timeline marks, burns each app scene's narration line in as its caption
   with ffmpeg `drawtext` (Inter), puts projector and phone side by side for
   the live scenes, and concatenates the segments into
   `prashna-demo-silent.mp4`. It then builds the narration track and muxes
   it into `prashna-demo.mp4`, and writes `prashna-demo.srt`,
   `scene-list.txt` (start, length and voice timing of every scene) and
   `audio/loudness.json`.
7. ffmpeg extracts one frame every 6 s into `frames/`, tiles them into
   `contact-sheet.png`, and prints the final file's loudness and true peak
   (`ebur128`).
8. `./check_text.sh` greps every text that reaches the screen or the
   narration (terminal text, cards, captions, `narration.txt`, the SRT and
   the scene list) for paths, tokens, emails, non-loopback IPs and the local
   user name.

## Narration

- `narration.txt` holds one line per scene. For every app scene the line is
  also the burned-in caption, so the captions are an exact transcript. The
  title, why and end cards are spoken only.
- `voice.py` runs Kokoro-82M v1.0 (Apache-2.0) locally on the CPU through
  ONNX Runtime, using the ONNX export at
  `https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX`, pinned to
  one revision. The first run downloads `onnx/model.onnx` (325 MB) and the
  voice files into `models/` and checks each file's SHA-256 against the
  values in the script. Later runs need no network and no API key, and ONNX
  Runtime's telemetry is turned off (`ORT_DISABLE_TELEMETRY=1`).
- Voice `af_heart`, speed 1.0, American English. Phonemes come from
  espeak-ng (bundled by `espeakng-loader`); `PRONUNCIATIONS` in `voice.py`
  sets "Prashna" to `pɹˈʌʃnə`.
- `voice/provenance.json` records the model, revision, file URLs and hashes,
  voice, speed, pronunciations, package versions and the hash of
  `narration.txt`.
- `compose.py` makes every scene at least 0.2 s + its voice line + 0.4 s
  long, holding the last frame (`tpad=stop_mode=clone`) where the picture is
  shorter, and starts each line 0.2 s into its scene, so no line runs into
  the next scene. The track is limited to 12 dB above its loudness (at
  192 kHz, to catch peaks between samples), then normalised with two-pass
  `loudnorm` (linear) to -14 LUFS and -1 dBTP. There is no music.
- The GPL-licensed phonemizer packages (`phonemizer-fork`,
  `espeakng-loader`) are dependencies of this build environment only; they
  are not part of Prashna or its image.

## Sanitising rules (`sanitize_terminal.py`)

Only these edits are made to the captured terminal output: absolute paths in
the work folder become `~` or `~/.local/share/prashna`, the setup token
becomes `prashna_st_…`, the `+ package==version` list is shortened to its
first three lines and the `+ prashna==<version>` line with `…` lines for the
rest, and the trailing `exit=0` marker is dropped.

## Fictional content

Admin `trainer`; session "Product onboarding workshop"; quiz "Onboarding
check". Diego (the phone) ticks "Show my name" on his question; four other
participants ask anonymously. No real people, emails, addresses, tokens or
machine paths appear on screen or in the narration. The end card says that
the narration is a synthetic voice.
