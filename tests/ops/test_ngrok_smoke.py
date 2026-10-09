"""Opt-in end-to-end smoke test for the local Uvicorn + ngrok workflow."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from websockets.sync.client import connect
from websockets.typing import Origin

ROOT = Path(__file__).resolve().parents[2]
RUN_LIVE_SMOKE = os.environ.get("PRASHNA_NGROK_SMOKE") == "1"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _stop(proc: subprocess.Popen[str]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def _wait_for_http(url: str, *, timeout: float = 20) -> httpx.Response:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=2)
            if response.status_code == 200:
                return response
            last_error = f"HTTP {response.status_code}: {response.text[:160]}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise AssertionError(f"endpoint did not become ready: {url}: {last_error}")


def _wait_for_tunnel(name: str, *, timeout: float = 30) -> str:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            response = httpx.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
            response.raise_for_status()
            for tunnel in response.json().get("tunnels", []):
                if tunnel.get("name") == name and tunnel.get("public_url", "").startswith(
                    "https://"
                ):
                    return tunnel["public_url"].rstrip("/")
            last_error = f"tunnel {name!r} not present in agent API"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise AssertionError(f"ngrok endpoint did not become ready: {last_error}")


@pytest.mark.skipif(
    not RUN_LIVE_SMOKE,
    reason="set PRASHNA_NGROK_SMOKE=1 to open a real temporary ngrok endpoint",
)
def test_local_bootstrap_then_ngrok_http_and_websocket(tmp_path):
    """UC-X-09: localhost bootstrap, public pages/API, and WSS broadcast."""
    ngrok = shutil.which("ngrok")
    assert ngrok, "ngrok CLI is required for PRASHNA_NGROK_SMOKE=1"

    # The public port serves Vite's production-style output, not the HMR
    # server. This is the step an operator must perform on a clean checkout.
    subprocess.run(
        ["npm", "run", "build", "--", "--mode", "test"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=60,
    )

    app_port = _free_port()
    env = os.environ.copy()
    env.update(
        {
            "PRASHNA_DB_PATH": str(tmp_path / "prashna.db"),
            "PRASHNA_UPLOADS_DIR": str(tmp_path / "uploads"),
            "PRASHNA_SECRET_KEY": "ngrok-smoke-" + secrets.token_hex(16),
            "PRASHNA_SETUP_TOKEN": "ngrok-smoke-setup",
            "PRASHNA_TRUSTED_PROXY_HOPS": "1",
            "PRASHNA_RATELIMIT": "off",
        }
    )
    local_url = f"http://127.0.0.1:{app_port}"
    app_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(app_port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
        text=True,
    )
    ngrok_proc: subprocess.Popen[str] | None = None
    try:
        assert _wait_for_http(f"{local_url}/api/admin/status").json()["initialized"] is False

        # Setup needs the one-time token (UC-A-01), so the order of setup
        # and opening the tunnel no longer matters; keep it local anyway.
        with httpx.Client(base_url=local_url, timeout=10) as local:
            setup = local.post(
                "/api/admin/setup",
                json={"username": "admin", "password": "testpass1", "setup_token": "ngrok-smoke-setup"},
            )
            assert setup.status_code == 200, setup.text
            created = local.post("/api/sessions", json={"title": "ngrok smoke"})
            assert created.status_code == 200, created.text
            session = created.json()

            tunnel_name = "prashna-smoke-" + secrets.token_hex(4)
            ngrok_proc = subprocess.Popen(
                [
                    ngrok,
                    "http",
                    str(app_port),
                    "--name",
                    tunnel_name,
                    "--log",
                    "stdout",
                    "--log-format",
                    "json",
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            public_url = _wait_for_tunnel(tunnel_name)

            status = _wait_for_http(f"{public_url}/api/admin/status", timeout=30)
            assert status.json()["initialized"] is True
            landing = httpx.get(f"{public_url}/", timeout=10)
            assert landing.status_code == 200
            assert "Prashna" in landing.text
            participant = httpx.get(f"{public_url}/s/{session['code']}", timeout=10)
            assert participant.status_code == 200
            assert "participant" in participant.text.lower()

            ws_url = public_url.replace("https://", "wss://", 1)
            ws_url += f"/ws/sessions/{session['code']}"
            with connect(ws_url, origin=Origin(public_url), open_timeout=15) as websocket:
                changed = local.patch(
                    f"/api/sessions/{session['code']}",
                    json={"title": "ngrok smoke updated"},
                )
                assert changed.status_code == 200, changed.text
                assert json.loads(websocket.recv(timeout=10)) == {"type": "session_state"}
    finally:
        if ngrok_proc is not None:
            _stop(ngrok_proc)
        _stop(app_proc)
