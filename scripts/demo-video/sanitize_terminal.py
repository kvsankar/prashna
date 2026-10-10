#!/usr/bin/env python3
"""Build terminal-text.txt for the install scene from the real captured output.

Inputs (written by run_install.sh and record_app.py):
  install-output.raw.txt  - stdout+stderr of `curl ... | sh`
  server-output.raw.txt   - stdout+stderr of `prashna` at startup

Rules applied (and nothing else):
  * any absolute path inside the work folder becomes `~` / `~/.local/share/prashna`
  * the setup token becomes `prashna_st_…`
  * the long `+ package==version` list is shortened with one `…` line
  * the trailing `exit=0` marker line is dropped
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

W = Path(__file__).resolve().parent
PORT_RE = re.compile(r"127\.0\.0\.1:\d+")


def sanitize(line: str) -> str:
    line = line.rstrip("\n")
    line = line.replace(str(W / "demo-data"), "~/.local/share/prashna")
    line = line.replace(str(W / "clean-home"), "~")
    line = line.replace(str(W), "~")
    line = re.sub(r"#setup=\S+", "#setup=prashna_st_…", line)
    return line


def shorten_packages(lines: list[str], keep: int = 3) -> list[str]:
    out: list[str] = []
    run: list[str] = []
    for ln in lines + [""]:
        if ln.startswith(" + "):
            run.append(ln)
            continue
        if run:
            if len(run) > keep + 1:
                out.extend(run[:keep])
                out.append(" …")
            else:
                out.extend(run)
            run = []
        out.append(ln)
    return out[:-1]


def main() -> int:
    install = (W / "install-output.raw.txt").read_text().splitlines()
    server = (W / "server-output.raw.txt").read_text().splitlines()
    install = [sanitize(x) for x in install if not x.startswith("exit=")]
    install = shorten_packages(install)
    server = [sanitize(x) for x in server]
    # Drop the trailing blank line of each block.
    while install and not install[-1].strip():
        install.pop()
    while server and not server[-1].strip():
        server.pop()
    text = ["$ curl -LsSf https://kvsankar.github.io/prashna/install.sh | sh", *install, "", "$ prashna", *server]
    (W / "terminal-text.txt").write_text("\n".join(text) + "\n")
    joined = "\n".join(text)
    bad = [p for p in ("/tmp/", "/home/", "clean-home", "demo-setup-token") if p in joined]
    if bad:
        print("sanitizer left forbidden text:", bad, file=sys.stderr)
        return 1
    print(f"wrote terminal-text.txt ({len(text)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
