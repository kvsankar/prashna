#!/usr/bin/env python3
"""Build terminal-text.txt for the tunnel scene from the real server output.

Input (written by record_app.py): server-output.raw.txt, the stdout and
stderr of `prashna --no-browser --data-dir <folder> --port 8000 --tunnel
cloudflare`.

Rules applied (and nothing else):
  * the command line is shown as `prashna --tunnel cloudflare`, the command a
    presenter types; the other options only change lines that are dropped
  * only the lines that start with KEEP are kept, in their order and
    verbatim; the data folder, database and one-time setup link lines are
    dropped (they hold machine paths and the setup token)
  * the blank line before "Prashna is running at" is kept
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

W = Path(__file__).resolve().parent
KEEP = (
    "Starting the cloudflared tunnel",
    "Waiting for the public address",
    "Prashna is running at http://127.0.0.1:",
    "Participants join at: https://",
    "Press Ctrl+C to stop.",
)
COMMAND = "$ prashna --tunnel cloudflare"


def main() -> int:
    raw = (W / "server-output.raw.txt").read_text().splitlines()
    kept = [ln.rstrip() for ln in raw if ln.startswith(KEEP)]
    missing = [k for k in KEEP if not any(ln.startswith(k) for ln in kept)]
    if missing:
        print("server output lacks:", missing, file=sys.stderr)
        return 1
    text = [COMMAND]
    for ln in kept:
        if ln.startswith("Prashna is running at"):
            text.append("")
        text.append(ln)
    joined = "\n".join(text)
    bad = [p for p in ("/tmp/", "/home/", "clean-home", "demo-setup-token", "#setup=") if p in joined]
    if bad or not re.search(r"https://[a-z0-9-]+\.trycloudflare\.com$", joined, re.M):
        print("terminal text failed its check:", bad or "no tunnel address", file=sys.stderr)
        return 1
    (W / "terminal-text.txt").write_text(joined + "\n")
    print(f"wrote terminal-text.txt ({len(text)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
