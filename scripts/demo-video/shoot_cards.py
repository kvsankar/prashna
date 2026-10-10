#!/usr/bin/env python3
"""Screenshot the three cards in cards.html at 1920x1080 into cards/*.png."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

W = Path(__file__).resolve().parent
OUT = W / "cards"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto((W / "cards.html").as_uri())
        for name in ("title", "why", "end"):
            page.evaluate("n => document.body.dataset.card = n", name)
            page.wait_for_timeout(200)
            page.screenshot(path=str(OUT / f"{name}.png"))
            print("wrote", OUT / f"{name}.png")
        browser.close()


if __name__ == "__main__":
    main()
