# Prashna demo video build

Builds the Prashna demo video (about 84 s, 1920x1080, 30 fps, H.264) from real
headless screen recordings of Prashna 0.6.0, with a spoken narration. Outputs:

- `prashna-demo.mp4`: video with narration (AAC-LC, 48 kHz, 192 kbit/s,
  -14 LUFS integrated, true peak at most -1 dBTP), `+faststart`. It has one
  video and one audio stream: no subtitle stream, and no captions in the
  picture. The problem, the reasons and the end card are on-screen graphics
  that show the narration's words.
- `prashna-demo-silent.mp4`: the same video without sound, with the narration
  burned in as captions on the app scenes.
- `prashna-demo.srt`: the narration as subtitles, one cue per part of each
  line, timed to the voice. Upload it beside `prashna-demo.mp4` where a
  platform offers an optional caption track.
- `contact-sheet.png` and `frames/`: one frame every 6 s, for review.
- `opening-preview.png` and `ending-preview.png`: one frame each of the
  opening montage and the end card.
- `voice-samples/`: the why passage in the chosen voice and two others.

## Storyboard

| Scene | What is on screen | Narration |
| --- | --- | --- |
| 01, 02 | The problem, as large text | "Half the room has a question. Nobody asks." "And you can't tell who's keeping up." |
| 03 | Montage: the projector and three phones join, a question climbs, quiz bars fill | What Prashna does |
| 04 | Why Prashna: four lines, each appearing as it is said | Runs on your laptop, one command, built-in tunnel, data on your machine |
| 05-11 | The live room: projector and Diego's phone side by side; short zoomed shots of the presenter's laptop | Join, ask, upvote, answer, quiz, answer text hidden until reveal, reveal |
| 12-14 | Setup: `prashna --tunnel cloudflare`, the invite card, creating the session and quiz | One flag gives a public address |
| 15 | End card: "Free. Runs on your laptop. No sign-ups for your audience.", both install lines, the cloudflared note, QR code to the landing page | The same words |

`compose.py` holds the storyboard (`SCENES`) and `narration.txt` the words.

## Steps

`./build.sh` runs all of them. Individually:

1. `./run_install.sh` runs the real installer
   (`curl -LsSf https://kvsankar.github.io/prashna/install.sh | sh`) in an
   empty HOME under `clean-home/` with `PATH=/usr/bin:/bin` and only the proxy
   variables passed through. The output goes to `install-output.raw.txt`; it
   is not shown in the video.
2. `cd tooling && uv sync` creates the environment used by the Python steps:
   Playwright 1.59, httpx, and kokoro-onnx with ONNX Runtime (versions pinned
   in `tooling/uv.lock`). `build.sh` sets `UV_CACHE_DIR` to `uv-cache/` unless
   it is already set.
3. `uv run --project tooling python voice.py --samples` speaks
   `narration.txt` with Kokoro-82M v1.0 (see Narration below) into
   `voice/<scene>.wav`, and writes `voice/durations.json`, `voice/parts.json`
   (the start and end of each part of each line) and `voice/provenance.json`.
4. `uv run --project tooling python record_app.py` starts the installed
   Prashna as `prashna --tunnel cloudflare` on 127.0.0.1:8000 with an empty
   `demo-data/` folder, a fixed `PRASHNA_SETUP_TOKEN` and rate limiting off.
   This needs internet access and `cloudflared` on the PATH. Prashna starts a
   real Cloudflare quick tunnel and prints its public address
   (`https://<random words>.trycloudflare.com`, new on every run); the join
   link and the projector's QR code use it. The script then records headless
   (see Recording below). Outputs: `recordings/*.webm`, `timeline.json`
   (wall-clock marks, each recording's start, the boxes of the controls that
   the laptop shots zoom to, and the public address), `shots/*.png`
   (checkpoints), `server-output.raw.txt`, and `terminal-text.txt` via
   `sanitize_terminal.py`.
5. `uv run --project tooling python shoot_cards.py` renders the designed
   scenes from `cards.html` (see Cards and frames below): it calls the page's
   `renderAt(t)` for every frame at 30 fps, screenshots it at 1920x1080 in
   headless Chromium, and encodes `cards/01-hook.mp4`, `02-hook.mp4`,
   `04-why.mp4`, `12-tunnel.mp4` and `15-end.mp4`. The words appear when the
   voice says them (from `voice/parts.json`). With `--preview` it writes only
   the last frame of each card to `cards/preview/`.
6. `uv run --project tooling python compose.py` renders the device frames,
   builds every app scene from the recordings, and encodes each scene twice
   from one decode: clean, and with its narration burned in as captions (one
   caption per part, ffmpeg `drawtext`, Inter). The clean scenes and the
   cards are joined and muxed with the narration track into
   `prashna-demo.mp4`; the captioned ones become `prashna-demo-silent.mp4`.
   It also writes `prashna-demo.srt`, `scene-list.txt` (start, length and
   voice timing of every scene), `audio/loudness.json`,
   `opening-preview.png` and `ending-preview.png`.
7. ffmpeg extracts one frame every 6 s of `prashna-demo.mp4` into `frames/`,
   tiles them into `contact-sheet.png`, and prints the final file's duration,
   streams, loudness and true peak (`ebur128`).
8. `./check_text.sh` checks every text that reaches the screen or the
   narration (see Sanitising below).

## Recording

- Pages, each recorded at its own viewport size:

  | Recording | Viewport | Page zoom | Lays out as |
  | --- | --- | --- | --- |
  | `admin` (the presenter's laptop) | 1920x1080 | 2 | 960x540 |
  | `projector` (`/p/<code>` from 127.0.0.1) | 1920x1080 | 4/3 | 1440x810 |
  | `phone` (Diego), `phone2`, `phone3` | 720x1560, mobile, touch | 2 | 360x780 |

  Playwright records a page at its viewport size in CSS pixels, so a device
  scale factor would not add detail. The pages are opened at full size and
  zoomed with CSS `zoom` on the body, as browser zoom does: the text is
  larger in the frame and stays sharp.
- The phones open the join link (`https://<tunnel>/s/<code>`) directly,
  through the tunnel. Before that they show a dark blank page; they never
  show the landing or sign-in page.
- Before each click or tap an injected overlay draws an amber ring around
  the control and a dot where it is pressed. The overlay belongs to the
  recording only; it is not part of Prashna.
- Twenty-four more participants are simulated with httpx clients, each with
  its own voter cookie: they ask five questions, upvote (first another
  question leads, then Diego's question overtakes it) and answer the quiz.
  Two of the visible phones also upvote and answer. The script waits until
  the projector and Diego's phone show the same counts before it marks the
  end of each step.
- Live vote counts are turned on through the API before the quiz starts, so
  the projector shows how the votes split without saying which answer
  leads (UC-D-08) and the phones show how many have answered.

## Cards and frames

`cards.html` draws every designed picture as a pure function of time, with no
CSS transitions or animations, so every run gives the same frames. Colours are
copied from `frontend/src/tokens.css`; fonts are the local Inter and DejaVu
Sans Mono; no file is fetched from the network.

- `hook`: the two problem lines, then the third.
- `why`: four lines with icons: "Runs on your own laptop", "One command · no
  server · no subscription", "A built-in tunnel puts it online for your
  audience", "Your data stays on your machine".
- `terminal`: `prashna --tunnel cloudflare` typed, then the real output of
  the recording run (`terminal-text.txt`); the flag and the public address
  are lit when the narration names them.
- `end`: the headline, "Install with one line · macOS · Linux · Windows",
  the macOS/Linux and Windows (PowerShell) install lines from the
  repository's README, a note that the public link also needs `cloudflared`
  (the installer does not fetch it), a QR code for `https://kvsankar.github.io/prashna/`
  (the landing page with the install steps), "Open source · MIT", and "The
  narration is a synthetic voice." The QR code is drawn by the generator
  Prashna already vendors, `frontend/public/vendor/qrcode.js` (MIT, Kazuhiko
  Arase), error correction level M. It stays up 1.5 s after the voice ends.
- `plate`: the navy background with device frames (a projector screen, a
  phone with an address bar showing the tunnel's host name, a laptop
  window), drawn once behind the recordings and once, with transparent
  screens, over them so the frames' rounded corners mask the recordings.

The app scenes use three layouts: `room` (projector and three phones, with
the wordmark and the line "Ask anonymously · upvote · quick quizzes · one
shared screen"), `duo` (projector and Diego's phone, labelled) and `laptop`
(a full-width crop of the laptop recording around the panel in use, shown in
a window frame at up to 1:1). The crops never include the admin home's
Limits card. Each shot's recording span plays faster or slower to fill its
share of the scene (never slower than 0.75x; beyond that the last frame is
held).

## Narration

- `narration.txt` holds one line per scene; " | " splits a line into parts.
  The cards show the same words; for the app scenes the parts are the
  captions of the silent version, so those captions are an exact
  transcript.
- The narration speaks to the presenter ("you") and avoids product jargon
  such as "moderator", "responded" and "publish". It makes only these
  claims about Prashna's setup: it runs on your own laptop with one command,
  no server and no subscription; a built-in tunnel puts it online for your
  audience; your data stays on your machine; it is free, and the audience
  needs no sign-up. It does not say that Prashna works without internet or
  that nothing leaves the laptop.
- `voice.py` runs Kokoro-82M v1.0 (Apache-2.0) locally on the CPU through
  ONNX Runtime, using the ONNX export at
  `https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX`, pinned to
  one revision. The first run downloads `onnx/model.onnx` (325 MB) and the
  voice files into `models/` and checks each file's SHA-256 against the
  values in the script. Later runs need no network and no API key, and ONNX
  Runtime's telemetry is turned off (`ORT_DISABLE_TELEMETRY=1`).
- Voice `af_heart`, speed 1.0, American English. Each part is spoken
  separately and the parts are joined with 0.25 s of silence. Phonemes come
  from espeak-ng (bundled by `espeakng-loader`); `PRONUNCIATIONS` in
  `voice.py` sets "Prashna" to `pɹˈʌʃnə`.
- `voice/provenance.json` records the model, revision, file URLs and hashes,
  voice, speed, pronunciations, the pause between parts, package versions
  and the hash of `narration.txt`.
- Every scene is at least 0.2 s + its voice line + 0.4 s long, and each line
  starts 0.2 s into its scene, so no line runs into the next scene and the
  pause between lines is about 0.6 s. Three pauses are longer on purpose:
  after each problem line and on the revealed answer. The track is limited
  to 12 dB above its loudness (at 192 kHz, to catch peaks between samples),
  then normalised with two-pass `loudnorm` (linear) to -14 LUFS and -1 dBTP.
  There is no music.
- The GPL-licensed phonemizer packages (`phonemizer-fork`,
  `espeakng-loader`) are dependencies of this build environment only; they
  are not part of Prashna or its image.

## Sanitising

`sanitize_terminal.py` builds the terminal text from the real server output.
The command line is shown as `prashna --tunnel cloudflare`, the command a
presenter types; the recording run also passes `--no-browser`, `--data-dir`
and `--port 8000`, which change only lines that are dropped. Only the lines
"Starting the cloudflared tunnel...", "Waiting for the public address...",
"Prashna is running at http://127.0.0.1:8000", "Participants join at:
https://…" and "Press Ctrl+C to stop." are kept, verbatim. The data folder,
database and setup-link lines are dropped.

`check_text.sh` fails if any text on screen or in the narration (the terminal
text, `cards.html`, `cards/texts.json`, `segments/plates/texts.json`, the
captions, `narration.txt`, the SRT and the scene list) contains a path, a
token, an email, a non-loopback IP address, or the local user name. Web
addresses may only be the two installer scripts, the landing page,
`http://127.0.0.1:8000` and the tunnel's `trycloudflare.com` address. The
tunnel address is public only while the recording runs; it stops working
when the run ends, so the QR codes in the app scenes lead nowhere later.

## Fictional content

Admin `trainer`; session "Product onboarding workshop"; quiz "Onboarding
check". Diego (the featured phone) ticks "Show my name" on his question; the
simulated participants ask anonymously. No real people, emails, addresses,
tokens or machine paths appear on screen or in the narration. The end card
says that the narration is a synthetic voice.
