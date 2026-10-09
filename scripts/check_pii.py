"""Block personal data and private infrastructure details from commits.

Run by pre-commit on staged files and by CI on every tracked file:

    python scripts/check_pii.py FILE...

It flags real-looking email addresses, public IPv4 addresses, and
home-directory paths. The patterns are generic on purpose, so this file
itself reveals nothing private. Placeholders are allowed: example.*
domains, GitHub no-reply addresses, and loopback, private and
documentation IP ranges. A line containing `pii-allow` is skipped, for
the rare deliberate case.
"""
from __future__ import annotations

import ipaddress
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ALLOW_MARKER = "pii-allow"

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")
ALLOWED_EMAIL_DOMAINS = re.compile(
    r"(^|\.)(example\.(com|org|net)|example|test|invalid|localhost|"
    r"users\.noreply\.github\.com|noreply\.github\.com|github\.com)$",
    re.IGNORECASE,
)

IPV4 = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.])")
DOCUMENTATION_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]

HOME_PATH = re.compile(r"(/home/[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/|\b[A-Za-z]:\\Users\\)")

# Generated or third-party files whose contents we don't author.
SKIP_FILES = re.compile(r"(^|/)(package-lock\.json|uv\.lock|\.secrets\.baseline)$|^frontend/public/vendor/")


@dataclass(frozen=True)
class Finding:
    line: int
    kind: str
    text: str


def _public_ip(match: re.Match[str]) -> bool:
    octets = [int(g) for g in match.groups()]
    if any(o > 255 for o in octets):
        return False
    ip = ipaddress.ip_address(".".join(map(str, octets)))
    if ip.is_loopback or ip.is_private or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return False
    return not any(ip in net for net in DOCUMENTATION_NETS)


def scan_text(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARKER in line:
            continue
        for m in EMAIL.finditer(line):
            if not ALLOWED_EMAIL_DOMAINS.search(m.group(1)):
                findings.append(Finding(number, "email", m.group(0)))
        for m in IPV4.finditer(line):
            if _public_ip(m):
                findings.append(Finding(number, "ip", m.group(0)))
        for m in HOME_PATH.finditer(line):
            findings.append(Finding(number, "path", m.group(0)))
    return findings


def main(paths: list[str]) -> int:
    failed = False
    for name in paths:
        if SKIP_FILES.search(name):
            continue
        path = Path(name)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue  # binaries and deleted files
        for f in scan_text(text):
            failed = True
            print(f"{name}:{f.line}: {f.kind}: {f.text}")
    if failed:
        print(f"\nPersonal or private data found. Replace it with a placeholder, "
              f"or add '{ALLOW_MARKER}' to the line if it is deliberate.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
