#!/usr/bin/env python3
"""Render the designed scenes from cards.html into video clips.

cards.html draws every frame as a pure function of time (window.renderAt(t)),
so this script steps through the frames at 30 fps, screenshots each one at
1920x1080 in headless Chromium, and encodes the frames with ffmpeg. The
result is the same on every run.

The words on these cards are the narration's words, and they appear when
the voice says them: the times come from voice/parts.json (written by
voice.py). Each clip is at least LEAD + its voice + TAIL long (the rule
compose.py checks); the two hook scenes and the end card are held longer
on purpose (MIN_LENGTH, END_HOLD).

Outputs:
  cards/01-hook.mp4, cards/02-hook.mp4  the problem (one animation, two scenes)
  cards/04-why.mp4                      why Prashna
  cards/12-tunnel.mp4                   `prashna --tunnel cloudflare` (terminal-text.txt)
  cards/15-end.mp4                      the end card
  cards/<name>/*.png                    the frames
  cards/texts.json                      every text the cards show (read by check_text.sh)

Run:  uv run --project tooling python shoot_cards.py [--preview]
      (--preview writes only the last frame of each card to cards/preview/)
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

W = Path(__file__).resolve().parent
OUT = W / "cards"
FPS = 30
LEAD = 0.2      # same as compose.py
TAIL = 0.4      # same as compose.py
MIN_LENGTH = {"01-hook": 4.0, "02-hook": 3.0}  # deliberate pauses after the problem lines
END_HOLD = 1.5  # the end card stays up this long after the voice ends
LANDING = "https://kvsankar.github.io/prashna/"
INSTALL = [
    ("#", "macOS and Linux"),
    ("$", "curl -LsSf https://kvsankar.github.io/prashna/install.sh | sh"),
    ("#", "Windows (PowerShell)"),
    (">", 'powershell -ExecutionPolicy ByPass -c "irm https://kvsankar.github.io/prashna/install.ps1 | iex"'),
]
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]


def frames(seconds: float) -> int:
    return math.ceil(seconds * FPS - 1e-6)


def at_word(part: list, word: str) -> float:
    """Approximate time a word is spoken inside a part, by its share of the characters."""
    start, end, text = part
    return start + (end - start) * text.index(word) / len(text)


def shoot(browser, name: str, config: dict, count: int) -> Path:  # noqa: ANN001
    folder = OUT / name
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    page.goto((W / "cards.html").as_uri())
    page.evaluate("c => window.setup(c)", config)
    for i in range(count):
        page.evaluate("t => window.renderAt(t)", i / FPS)
        page.screenshot(path=str(folder / f"{i:05d}.png"))
    page.close()
    print(f"{name}: {count} frames")
    return folder


def encode(folder: Path, first: int, count: int, out: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-start_number", str(first),
                    "-i", str(folder / "%05d.png"), "-frames:v", str(count), *ENC, str(out)], check=True)
    print("wrote", out)


def main() -> None:
    voice: dict[str, float] = json.loads((W / "voice" / "durations.json").read_text())
    parts: dict[str, list] = json.loads((W / "voice" / "parts.json").read_text())

    def length(scene: str) -> float:
        return max(MIN_LENGTH.get(scene, 0.0), LEAD + voice[scene] + TAIL)

    OUT.mkdir(exist_ok=True)
    n1, n2 = frames(length("01-hook")), frames(length("02-hook"))
    t1 = n1 / FPS
    p1, p2 = parts["01-hook"], parts["02-hook"]
    hook = {"scene": "hook", "at": [max(0.05, LEAD + p1[0][0] - 0.1), LEAD + p1[1][0] - 0.1, t1 + LEAD + p2[0][0] - 0.1]}

    pw = parts["04-why"]
    assert len(pw) == 4, "04-why needs four parts, one per row on the card"
    why = {"scene": "why", "at": [LEAD + p[0] - 0.1 for p in pw], "rows": [
        ["laptop", "Runs on your own laptop"],
        ["command", 'One command<span class="dot">&middot;</span>no server<span class="dot">&middot;</span>no subscription'],
        ["globe", "A built-in tunnel puts it online for your audience"],
        ["shield", "Your data stays on your machine"],
    ]}

    lines = (W / "terminal-text.txt").read_text().splitlines()
    assert len(lines) == 7 and lines[0] == "$ prashna --tunnel cloudflare", lines
    pt = parts["12-tunnel"]
    second = LEAD + pt[1][0]
    terminal = {"scene": "terminal", "lines": lines, "typeFor": 0.9,
                "at": [0.25, 1.35, 1.65, second - 0.05, second, second + 0.35, second + 0.6],
                "flagAt": LEAD + at_word(pt[1], "flag") - 0.1,
                "urlAt": LEAD + at_word(pt[1], "public") - 0.1}

    pe = parts["15-end"]
    head = ["Free.", "Runs on your laptop.", "No sign-ups for your audience."]
    end = {"scene": "end", "head": head, "install": INSTALL, "qr": LANDING, "qrLabel": "kvsankar.github.io/prashna",
           # The installer does not fetch cloudflared; --tunnel cloudflare needs it.
           "tunnelNote": "For the public link, also install cloudflared, Cloudflare's free tunnel program (no account needed).",
           "at": [LEAD + pe[0][0] - 0.1, LEAD + at_word(pe[0], "Runs") - 0.1,
                  LEAD + at_word(pe[0], "No sign") - 0.1, LEAD + pe[1][0] - 0.1]}
    n_end = frames(LEAD + voice["15-end"] + END_HOLD)

    # Every text these cards put on screen, for check_text.sh.
    (OUT / "texts.json").write_text(json.dumps({"hook": hook, "why": why, "terminal": terminal, "end": end},
                                               indent=2, ensure_ascii=False) + "\n")
    if "--preview" in sys.argv[1:]:
        prev = OUT / "preview"
        prev.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for name, cfg, t in (("hook-1", hook, t1 - 0.1), ("hook-2", hook, t1 + n2 / FPS - 0.1),
                                 ("why", why, length("04-why") - 0.1), ("terminal", terminal, length("12-tunnel") - 0.1),
                                 ("end", end, n_end / FPS - 0.1)):
                page = browser.new_page(viewport={"width": 1920, "height": 1080})
                page.goto((W / "cards.html").as_uri())
                page.evaluate("c => window.setup(c)", cfg)
                page.evaluate("t => window.renderAt(t)", t)
                page.screenshot(path=str(prev / f"{name}.png"))
                page.close()
            browser.close()
        print("wrote", prev)
        return
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        folder = shoot(browser, "hook", hook, n1 + n2)
        encode(folder, 0, n1, OUT / "01-hook.mp4")
        encode(folder, n1, n2, OUT / "02-hook.mp4")
        encode(shoot(browser, "why", why, frames(length("04-why"))), 0, frames(length("04-why")), OUT / "04-why.mp4")
        n_t = frames(length("12-tunnel"))
        encode(shoot(browser, "terminal", terminal, n_t), 0, n_t, OUT / "12-tunnel.mp4")
        encode(shoot(browser, "end", end, n_end), 0, n_end, OUT / "15-end.mp4")
        browser.close()


if __name__ == "__main__":
    main()
