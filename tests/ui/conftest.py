"""UI test fixtures. Spawns a uvicorn subprocess against an isolated DB.

The subprocess is per-session (one for the whole pytest run); individual tests
reset state via API calls or by relying on Playwright's per-test browser context.
"""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def uvicorn_url(tmp_path_factory) -> str:
    """Start uvicorn on a free port with an isolated DB. Tear down at end of session."""
    port = _find_free_port()
    db_path = tmp_path_factory.mktemp("uidb") / "prashna-ui.db"
    upload_dir = tmp_path_factory.mktemp("uiuploads")
    env = os.environ.copy()
    env["PRASHNA_DB_PATH"] = str(db_path)
    env["PRASHNA_UPLOADS_DIR"] = str(upload_dir)
    env["PRASHNA_SECRET_KEY"] = "ui-test-" + secrets.token_hex(8)

    root = Path(__file__).resolve().parents[2]
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=root,
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    # Wait until the server is ready.
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base}/api/admin/status", timeout=1.0)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    else:
        proc.terminate()
        raise RuntimeError("uvicorn did not start in time")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def base_url(uvicorn_url: str) -> str:
    return uvicorn_url


@pytest.fixture
def admin_setup(base_url: str):
    """Ensure an admin exists (idempotent across tests in one session)."""
    r = httpx.post(
        f"{base_url}/api/admin/setup",
        json={"username": "admin", "password": "testpass1"},
        timeout=5.0,
    )
    # 200 on first run, 409 thereafter — both fine for tests that just need an admin to exist.
    assert r.status_code in (200, 409), r.text
    return {"username": "admin", "password": "testpass1"}


@pytest.fixture
def browser_context_args():
    """Per-test browser context: ignore HTTPS errors (we're on http).

    Each test gets its own context (Playwright default), so cookies don't leak.
    """
    return {"ignore_https_errors": True}
