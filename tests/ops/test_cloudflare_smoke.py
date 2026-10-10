"""Opt-in end-to-end smoke test for `prashna --tunnel cloudflare` (UC-X-15).

Runs the real `cloudflared` (no account needed), so it reaches the internet:

    PRASHNA_CLOUDFLARE_SMOKE=1 uv run pytest tests/ops/test_cloudflare_smoke.py
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
from websockets.sync.client import connect
from websockets.typing import Origin

ROOT = Path(__file__).resolve().parents[2]
RUN_LIVE_SMOKE = os.environ.get("PRASHNA_CLOUDFLARE_SMOKE") == "1"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(not RUN_LIVE_SMOKE, reason="set PRASHNA_CLOUDFLARE_SMOKE=1 to reach the internet")
def test_prashna_tunnel_cloudflare_end_to_end(tmp_path):
    if not shutil.which("cloudflared"):
        pytest.skip("cloudflared is not installed")
    port = _free_port()
    env = {k: v for k, v in os.environ.items()
           if k not in ("PRASHNA_DB_PATH", "PRASHNA_UPLOADS_DIR", "PRASHNA_SECRET_KEY", "PRASHNA_RATELIMIT")}
    env["PRASHNA_SETUP_TOKEN"] = "smoke-setup-token"
    proc = subprocess.Popen(
        [sys.executable, "-m", "prashna.cli", "--data-dir", str(tmp_path / "data"), "--port", str(port),
         "--no-browser", "--tunnel", "cloudflare"],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines: list[str] = []
    threading.Thread(target=lambda: lines.extend(proc.stdout or []), daemon=True).start()
    try:
        public = ""
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not public:
            for line in list(lines):
                match = re.search(r"Participants join at: (https://\S+)", line)
                if match:
                    public = match.group(1)
            time.sleep(0.2)
        assert public, "no public address printed:\n" + "".join(lines)

        # A new quick-tunnel hostname can take a few seconds to resolve.
        status = None
        last_error = ""
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                status = httpx.get(f"{public}/api/admin/status", timeout=5)
                if status.status_code == 200:
                    break
                last_error = f"HTTP {status.status_code}"
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(1)
        assert status is not None and status.status_code == 200, f"public health API unreachable: {last_error}"

        with httpx.Client(base_url=public, timeout=10) as admin:
            admin.post("/api/admin/setup", json={"username": "smoke", "password": "smoke-password",  # pragma: allowlist secret
                                                 "setup_token": "smoke-setup-token"}).raise_for_status()
            session = admin.post("/api/sessions", json={"title": "Cloudflare smoke"}).json()
            assert session["default_base_url"] == public
            page = admin.get(f"/s/{session['code']}")
            assert page.status_code == 200 and "text/html" in page.headers["content-type"]

        ws_url = public.replace("https://", "wss://") + f"/ws/sessions/{session['code']}"
        with connect(ws_url, origin=Origin(public), open_timeout=15) as ws:
            ws.send("ping")
            assert '"pong"' in str(ws.recv(timeout=10))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
