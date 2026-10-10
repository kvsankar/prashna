"""Subprocess restart coverage for the signing key (UC-X-07) and the
one-time setup token (UC-A-01)."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from ..support import SETUP_TOKEN

ROOT = Path(__file__).resolve().parents[2]
ADMIN = {"username": "admin", "password": "testpass1"}


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _start_app(db_path: Path, upload_dir: Path, secret: str | None, *, setup_token: str | None = SETUP_TOKEN):
    port = _free_port()
    env = os.environ.copy()
    env["PRASHNA_DB_PATH"] = str(db_path)
    env["PRASHNA_UPLOADS_DIR"] = str(upload_dir)
    env["PRASHNA_RATELIMIT"] = "off"
    if secret is None:
        env.pop("PRASHNA_SECRET_KEY", None)
    else:
        env["PRASHNA_SECRET_KEY"] = secret
    if setup_token is None:
        env.pop("PRASHNA_SETUP_TOKEN", None)
    else:
        env["PRASHNA_SETUP_TOKEN"] = setup_token
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "prashna.main:app",
            "--port",
            str(port),
            "--log-level",
            "info",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/api/admin/status", timeout=1.0)
            if r.status_code == 200:
                return proc, base_url
        except Exception:
            time.sleep(0.1)
    output = _stop_app(proc)
    raise RuntimeError(f"uvicorn did not start in time:\n{output}")


def _stop_app(proc: subprocess.Popen[str]) -> str:
    proc.terminate()
    try:
        output, _ = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        output, _ = proc.communicate(timeout=5)
    return output or ""


def _setup_admin(base_url: str, token: str = SETUP_TOKEN) -> str:
    with httpx.Client(base_url=base_url, timeout=5.0) as client:
        r = client.post("/api/admin/setup", json={**ADMIN, "setup_token": token})
        assert r.status_code == 200, r.text
        cookie = client.cookies.get("prashna_admin")
        assert cookie
        return cookie


def _status_with_cookie(base_url: str, cookie: str) -> dict:
    with httpx.Client(
        base_url=base_url,
        cookies={"prashna_admin": cookie},
        timeout=5.0,
    ) as client:
        r = client.get("/api/admin/status")
        assert r.status_code == 200, r.text
        return r.json()


def test_fixed_secret_survives_restart_and_rotated_secret_expires(tmp_path):
    """Fixed secret preserves cookies; rotated secret expires them safely."""
    db_path = tmp_path / "prashna.db"
    upload_dir = tmp_path / "uploads"

    proc, base_url = _start_app(db_path, upload_dir, "fixed-one")
    try:
        cookie = _setup_admin(base_url)
    finally:
        _stop_app(proc)

    proc, base_url = _start_app(db_path, upload_dir, "fixed-one")
    try:
        status = _status_with_cookie(base_url, cookie)
        assert status["authenticated"] is True
        assert status["username"] == "admin"
    finally:
        _stop_app(proc)

    proc, base_url = _start_app(db_path, upload_dir, "fixed-two")
    try:
        status = _status_with_cookie(base_url, cookie)
        assert status["initialized"] is True
        assert status["authenticated"] is False
        assert status["username"] is None
    finally:
        _stop_app(proc)


def test_unset_secret_persists_key_beside_database(tmp_path):
    """UC-X-07: with no PRASHNA_SECRET_KEY the key is kept in secret-key, so
    cookies survive a restart and no ephemeral-key warning is logged."""
    db_path = tmp_path / "prashna.db"
    upload_dir = tmp_path / "uploads"

    proc, base_url = _start_app(db_path, upload_dir, None)
    try:
        cookie = _setup_admin(base_url)
    finally:
        first_output = _stop_app(proc)
    key_file = tmp_path / "secret-key"
    assert key_file.exists()
    assert (key_file.stat().st_mode & 0o777) == 0o600
    assert "PRASHNA_SECRET_KEY is not set" not in first_output

    proc, base_url = _start_app(db_path, upload_dir, None)
    try:
        status = _status_with_cookie(base_url, cookie)
        assert status["authenticated"] is True
        assert status["username"] == "admin"
    finally:
        second_output = _stop_app(proc)
    assert "PRASHNA_SECRET_KEY is not set" not in second_output


def test_generated_setup_token_is_logged_reused_and_retired(tmp_path):
    """UC-A-01: without PRASHNA_SETUP_TOKEN a token is written beside the
    database (0600), logged as /#setup=<token>, reused after a restart, and
    deleted once the admin exists."""
    db_path = tmp_path / "prashna.db"
    upload_dir = tmp_path / "uploads"
    token_file = tmp_path / "setup-token"

    proc, base_url = _start_app(db_path, upload_dir, "fixed", setup_token=None)
    _stop_app_output = ""
    try:
        assert token_file.exists()
        assert (token_file.stat().st_mode & 0o777) == 0o600
        token = token_file.read_text().strip()
        assert token.startswith("prashna_st_") and len(token) > 30
    finally:
        _stop_app_output = _stop_app(proc)
    assert f"/#setup={token}" in _stop_app_output

    proc, base_url = _start_app(db_path, upload_dir, "fixed", setup_token=None)
    try:
        assert token_file.read_text().strip() == token
        with httpx.Client(base_url=base_url, timeout=5.0) as client:
            wrong = client.post("/api/admin/setup", json={**ADMIN, "setup_token": "nope"})
            assert wrong.status_code == 403
        _setup_admin(base_url, token)
        assert not token_file.exists()
    finally:
        _stop_app(proc)
