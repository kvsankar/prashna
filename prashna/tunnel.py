"""Make a local Prashna reachable from the internet (UC-X-15).

`prashna --tunnel cloudflare` runs a Cloudflare quick tunnel (`cloudflared`,
no account); `prashna --tunnel ngrok` runs the user's signed-in `ngrok`.
Both forward a public https:// address to the local port; Prashna reads that
address from the program's output and stops the program when it stops.
"""
from __future__ import annotations

import collections
import json
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable

PROGRAMS = {"cloudflare": "cloudflared", "ngrok": "ngrok"}
INSTALL_HINTS = {
    "cloudflare": (
        "Install it, then run the same command again:\n"
        "  macOS:   brew install cloudflared\n"
        "  Windows: winget install --id Cloudflare.cloudflared\n"
        "  Linux:   https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    ),
    "ngrok": (
        "Install it from https://ngrok.com/download and sign in once with\n"
        "  ngrok config add-authtoken <your token>\n"
        "then run the same command again."
    ),
}
# cloudflared prints the quick-tunnel address alone on a line of a box in its
# log output: "INF |  https://<name>.trycloudflare.com  |". Only that line
# counts. Other lines can hold trycloudflare.com URLs too: when cloudflared
# cannot reach Cloudflare it logs `failed to request quick Tunnel: Post
# "https://api.trycloudflare.com/tunnel"`, and api.trycloudflare.com is
# Cloudflare's service address, never a tunnel (UC-X-15).
CLOUDFLARE_URL = re.compile(r"\|\s+(https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com)\s+\|")
# ngrok (`--log-format json`) reports the public address in this record.
NGROK_STARTED = "started tunnel"
WAIT_SECS = 45


DOH_URL = "https://cloudflare-dns.com/dns-query"


def _doh_query(host: str) -> dict:
    """Ask public DNS (over HTTPS) for `host`, bypassing the local resolver."""
    query = urllib.parse.urlencode({"name": host, "type": "A"})
    request = urllib.request.Request(f"{DOH_URL}?{query}", headers={"Accept": "application/dns-json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def wait_until_resolvable(url: str, timeout: float) -> bool:
    """Wait until public DNS has `url`'s hostname.

    A Cloudflare quick-tunnel name appears in DNS about 15 s after cloudflared
    prints it, and a "no such name" answer from an early lookup is cached by
    resolvers. Checking over DNS over HTTPS never asks the local resolver, so
    the presenter's own cache stays clean (UC-X-15).
    """
    if timeout <= 0:
        return True
    host = urllib.parse.urlsplit(url).hostname or ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            answer = _doh_query(host)
            if answer.get("Status") == 0 and answer.get("Answer"):
                return True
        except Exception:
            pass  # public DNS unreachable for a moment: keep trying until the deadline
        time.sleep(1)
    return False


class TunnelError(Exception):
    """The tunnel could not be started; the message says why."""


class Tunnel:
    """One running tunnel program and the public address it reported."""

    def __init__(self, kind: str, port: int, host: str = "127.0.0.1") -> None:
        name = PROGRAMS[kind]
        program = shutil.which(name)
        if not program:
            raise TunnelError(f"`{name}` is not installed. {INSTALL_HINTS[kind]}")
        target = f"http://{host}:{port}"
        if kind == "cloudflare":
            command = [program, "tunnel", "--no-autoupdate", "--url", target]
        else:
            command = [program, "http", target, "--log", "stdout", "--log-format", "json"]
        self.kind = kind
        self.url: str | None = None
        self.on_unexpected_exit: Callable[[], None] | None = None
        self._stopping = False
        self._found = threading.Event()
        self._lines: collections.deque[str] = collections.deque(maxlen=15)
        self._proc = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()

    def _parse(self, line: str) -> str | None:
        """The public address, when `line` is the tunnel's success report."""
        if self.kind == "cloudflare":
            match = CLOUDFLARE_URL.search(line)
            return match.group(1) if match else None
        try:
            record = json.loads(line)
        except ValueError:
            return None
        if not isinstance(record, dict) or record.get("msg") != NGROK_STARTED:
            return None
        url = record.get("url")
        return url if isinstance(url, str) and url.startswith("https://") else None

    def _read(self) -> None:
        # Keep draining the output so the program never blocks on a full pipe.
        assert self._proc.stdout is not None
        for raw in self._proc.stdout:
            line = raw.rstrip()
            self._lines.append(line)
            if self.url is None and (url := self._parse(line)):
                self.url = url
                self._found.set()
        self._proc.wait()
        self._found.set()
        if self.url and not self._stopping and self.on_unexpected_exit:
            self.on_unexpected_exit()

    def wait_for_url(self, timeout: float = WAIT_SECS) -> str:
        """Return the public address, or stop and raise if none appears."""
        self._found.wait(timeout)
        if self.url:
            return self.url
        self.stop()
        output = "\n".join(self._lines) or "(no output)"
        raise TunnelError(f"`{PROGRAMS[self.kind]}` did not report a public address. Its last output:\n{output}")

    def stop(self) -> None:
        self._stopping = True
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
