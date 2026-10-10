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
from typing import Iterator

import httpx
import pytest

from ..support import SETUP_TOKEN


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_uvicorn(db_path: Path, upload_dir: Path, extra_env: dict[str, str] | None = None) -> tuple[str, subprocess.Popen]:
    """Start uvicorn on a free port with an isolated DB."""
    port = _find_free_port()
    env = os.environ.copy()
    env.update(extra_env or {})
    env["PRASHNA_DB_PATH"] = str(db_path)
    env["PRASHNA_UPLOADS_DIR"] = str(upload_dir)
    env["PRASHNA_SECRET_KEY"] = "ui-test-" + secrets.token_hex(8)
    # UI tests don't exercise rate limiting; keep it off so rapid scripted
    # clicks never trip a 429.
    env["PRASHNA_RATELIMIT"] = "off"

    root = Path(__file__).resolve().parents[2]
    # The frontend is built once per session by tests/conftest.py.
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "prashna.main:app", "--port", str(port), "--log-level", "warning"],
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
    return base, proc


def _stop_uvicorn(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def uvicorn_url(tmp_path_factory) -> Iterator[str]:
    """Start uvicorn on a free port with an isolated DB. Tear down at end of session."""
    db_path = tmp_path_factory.mktemp("uidb") / "prashna-ui.db"
    upload_dir = tmp_path_factory.mktemp("uiuploads")
    base, proc = _start_uvicorn(db_path, upload_dir)
    yield base
    _stop_uvicorn(proc)


@pytest.fixture
def fresh_base_url(tmp_path) -> Iterator[str]:
    """Start a one-test uvicorn process with no bootstrapped admin."""
    base, proc = _start_uvicorn(tmp_path / "prashna-ui.db", tmp_path / "uploads")
    yield base
    _stop_uvicorn(proc)


@pytest.fixture
def base_url(uvicorn_url: str) -> str:
    return uvicorn_url


@pytest.fixture
def admin_setup(base_url: str):
    """Ensure an admin exists (idempotent across tests in one session)."""
    r = httpx.post(
        f"{base_url}/api/admin/setup",
        json={"username": "admin", "password": "testpass1", "setup_token": SETUP_TOKEN},
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


@pytest.fixture(scope="session")
def _playwright():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(_playwright):
    b = _playwright.chromium.launch()
    try:
        yield b
    finally:
        b.close()


@pytest.fixture
def context(browser):
    """Per-test browser context — clean cookie jar."""
    ctx = browser.new_context(ignore_https_errors=True)
    # Grant clipboard so the share-mod and copy buttons don't blow up.
    try:
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    except Exception:
        pass
    try:
        yield ctx
    finally:
        ctx.close()


@pytest.fixture
def page(context):
    p = context.new_page()
    yield p
    p.close()
