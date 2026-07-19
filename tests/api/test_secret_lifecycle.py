"""Subprocess restart coverage for admin session signing keys."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
ADMIN = {"username": "admin", "password": "testpass1"}


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _start_app(db_path: Path, upload_dir: Path, secret: str | None):
    port = _free_port()
    env = os.environ.copy()
    env["PRASHNA_DB_PATH"] = str(db_path)
    env["PRASHNA_UPLOADS_DIR"] = str(upload_dir)
    env["PRASHNA_RATELIMIT"] = "off"
    if secret is None:
        env.pop("PRASHNA_SECRET_KEY", None)
    else:
        env["PRASHNA_SECRET_KEY"] = secret
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
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


def _setup_admin(base_url: str) -> str:
    with httpx.Client(base_url=base_url, timeout=5.0) as client:
        r = client.post("/api/admin/setup", json=ADMIN)
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


def test_unset_secret_warns_and_invalidates_cookie_on_restart(tmp_path):
    """Unset secret logs a warning and makes cookies process-local."""
    db_path = tmp_path / "prashna.db"
    upload_dir = tmp_path / "uploads"

    proc, base_url = _start_app(db_path, upload_dir, None)
    try:
        cookie = _setup_admin(base_url)
    finally:
        first_output = _stop_app(proc)
    assert "PRASHNA_SECRET_KEY is not set" in first_output

    proc, base_url = _start_app(db_path, upload_dir, None)
    try:
        status = _status_with_cookie(base_url, cookie)
        assert status["initialized"] is True
        assert status["authenticated"] is False
        assert status["username"] is None
    finally:
        second_output = _stop_app(proc)
    assert "PRASHNA_SECRET_KEY is not set" in second_output
