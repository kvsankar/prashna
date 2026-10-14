#!/usr/bin/env python3
"""Render the animated opening and end card from cards.html into video clips.

cards.html draws every frame as a pure function of time (window.renderAt(t)),
so this script steps through the frames at 30 fps, screenshots each one at
1920x1080 in headless Chromium, and encodes the frames with ffmpeg. The
result is the same on every run.

Each clip is as long as its narration line needs (LEAD + voice + TAIL, the
rule compose.py checks), so this step runs after voice.py. The opening is one
continuous animation cut into the two scenes 01-title and 02-why; the end
card is held for at least END_MIN seconds.

Outputs:
  cards/01-title.mp4, cards/02-why.mp4, cards/20-end.mp4
  cards/opening/*.png, cards/end/*.png   the frames

Run:  uv run --project tooling python shoot_cards.py
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

W = Path(__file__).resolve().parent
OUT = W / "cards"
FPS = 30
LEAD = 0.2      # same as compose.py
TAIL = 0.4      # same as compose.py
END_MIN = 8.0   # the end card stays up at least this long, for the QR code
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]


def frames_for(voice: dict[str, float], scene: str, minimum: float = 0.0) -> int:
    return math.ceil(max(minimum, LEAD + voice[scene] + TAIL) * FPS - 1e-6)


def shoot(browser, scene: str, count: int, query: str = "") -> Path:  # noqa: ANN001
    folder = OUT / scene
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    page.goto(f"{(W / 'cards.html').as_uri()}?scene={scene}{query}")
    page.evaluate("() => window.ready")
    for i in range(count):
        page.evaluate("t => window.renderAt(t)", i / FPS)
        page.screenshot(path=str(folder / f"{i:05d}.png"))
    page.close()
    print(f"{scene}: {count} frames")
    return folder


def encode(folder: Path, first: int, count: int, out: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-start_number", str(first),
                    "-i", str(folder / "%05d.png"), "-frames:v", str(count), *ENC, str(out)], check=True)
    print("wrote", out)


def main() -> None:
    voice: dict[str, float] = json.loads((W / "voice" / "durations.json").read_text())
    n_title = frames_for(voice, "01-title")
    n_why = frames_for(voice, "02-why")
    n_end = frames_for(voice, "20-end", END_MIN)
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        opening = shoot(browser, "opening", n_title + n_why, f"&t1={n_title / FPS:.6f}")
        end = shoot(browser, "end", n_end)
        browser.close()
    encode(opening, 0, n_title, OUT / "01-title.mp4")
    encode(opening, n_title, n_why, OUT / "02-why.mp4")
    encode(end, 0, n_end, OUT / "20-end.mp4")


if __name__ == "__main__":
    main()
