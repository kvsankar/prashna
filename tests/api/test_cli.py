"""UC-X-15: the `prashna` command and the hosted install scripts.

The CLI tests run the real command in a subprocess on a free port. The
browser is captured through the standard BROWSER variable, which Python's
webbrowser module honours, so the test sees exactly the URL a user's
browser would be sent to.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _cli_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("PRASHNA_DB_PATH", "PRASHNA_UPLOADS_DIR", "PRASHNA_SETUP_TOKEN",
                        "PRASHNA_DATA_DIR", "PRASHNA_SECRET_KEY")}
    env.update(extra)
    return env


def _start_cli(args: list[str], env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen([sys.executable, "-m", "prashna.cli", *args], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _wait_up(port: int) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/admin/status", timeout=1).status_code == 200:
                return
        except httpx.TransportError:
            time.sleep(0.1)
    raise AssertionError("prashna did not start")


def _stop(proc: subprocess.Popen[str]) -> str:
    proc.terminate()
    out, _ = proc.communicate(timeout=10)
    return out


def _recorder(tmp_path: Path) -> tuple[str, Path]:
    """A BROWSER command that appends each opened URL to a file."""
    log = tmp_path / "opened.txt"
    script = tmp_path / "record_browser.py"
    script.write_text(f"import sys\nopen({str(log)!r}, 'a').write(sys.argv[1] + '\\n')\n")
    return f"{sys.executable} {script} %s", log


def _wait_for_file(path: Path) -> str:
    deadline = time.time() + 10
    while time.time() < deadline:
        if path.exists() and path.read_text().strip():
            return path.read_text().strip()
        time.sleep(0.1)
    raise AssertionError("browser was not opened")


def test_uc_x_15_first_run_opens_setup_page_with_a_working_token(tmp_path):
    """UC-X-15: on a fresh data folder the browser opens /#setup=<token>, and that token creates the admin."""
    port, data = _free_port(), tmp_path / "data"
    browser, opened = _recorder(tmp_path)
    proc = _start_cli(["--data-dir", str(data), "--port", str(port)], _cli_env(BROWSER=browser))
    try:
        _wait_up(port)
        url = _wait_for_file(opened)
        assert url.startswith(f"http://127.0.0.1:{port}/#setup=")
        token = url.split("#setup=", 1)[1]
        r = httpx.post(f"http://127.0.0.1:{port}/api/admin/setup",
                       json={"username": "me", "password": "longenough", "setup_token": token})
        assert r.status_code == 200, r.text
        assert (data / "prashna.db").is_file()
        assert (data / "secret-key").is_file()
    finally:
        out = _stop(proc)
    assert f"http://127.0.0.1:{port}" in out
    assert str(data) in out


def test_uc_x_15_later_runs_open_home_and_no_browser_opens_nothing(tmp_path):
    """UC-X-15: with an admin the browser opens /; --no-browser opens nothing."""
    port, data = _free_port(), tmp_path / "data"
    browser, opened = _recorder(tmp_path)
    proc = _start_cli(["--data-dir", str(data), "--port", str(port), "--no-browser"], _cli_env(BROWSER=browser))
    try:
        _wait_up(port)
        token = (data / "setup-token").read_text().strip()
        httpx.post(f"http://127.0.0.1:{port}/api/admin/setup",
                   json={"username": "me", "password": "longenough", "setup_token": token}).raise_for_status()
        time.sleep(1)
        assert not opened.exists()
    finally:
        _stop(proc)

    proc = _start_cli(["--port", str(port)], _cli_env(BROWSER=browser, PRASHNA_DATA_DIR=str(data)))
    try:
        _wait_up(port)
        assert _wait_for_file(opened) == f"http://127.0.0.1:{port}/"
    finally:
        _stop(proc)


def test_uc_x_15_port_in_use_exits_with_a_hint(tmp_path):
    """UC-X-15: a busy port exits 1 and names --port."""
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        result = subprocess.run(
            [sys.executable, "-m", "prashna.cli", "--data-dir", str(tmp_path / "d"), "--port", str(port), "--no-browser"],
            cwd=ROOT, env=_cli_env(), capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert "--port" in result.stdout + result.stderr


def test_uc_x_15_honours_https_from_a_local_reverse_proxy(tmp_path):
    """UC-X-15: behind nginx on the same machine, cookies are Secure for HTTPS visitors."""
    port = _free_port()
    proc = _start_cli(["--data-dir", str(tmp_path / "d"), "--port", str(port), "--no-browser"],
                      _cli_env(PRASHNA_SETUP_TOKEN="t"))
    try:
        _wait_up(port)
        base = f"http://127.0.0.1:{port}"
        proxied = httpx.post(f"{base}/api/admin/setup", headers={"X-Forwarded-Proto": "https"},
                             json={"username": "me", "password": "longenough", "setup_token": "t"})
        assert proxied.status_code == 200, proxied.text
        assert "secure" in proxied.headers["set-cookie"].lower()
        direct = httpx.post(f"{base}/api/admin/login", json={"username": "me", "password": "longenough"})
        assert direct.status_code == 200
        assert "secure" not in direct.headers["set-cookie"].lower()
    finally:
        _stop(proc)


def test_uc_x_15_backup_and_version(tmp_path):
    """UC-X-15: `prashna backup create` archives the data folder; --version prints it."""
    data = tmp_path / "data"
    port = _free_port()
    proc = _start_cli(["--data-dir", str(data), "--port", str(port), "--no-browser"], _cli_env())
    try:
        _wait_up(port)
    finally:
        _stop(proc)
    archive = tmp_path / "backup.tar.gz"
    result = subprocess.run(
        [sys.executable, "-m", "prashna.cli", "--data-dir", str(data), "backup", "create", str(archive)],
        cwd=ROOT, env=_cli_env(), capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    with tarfile.open(archive) as tar:
        assert any(name.endswith("prashna.db") for name in tar.getnames())
    version = subprocess.run([sys.executable, "-m", "prashna.cli", "--version"], cwd=ROOT,
                             env=_cli_env(), capture_output=True, text=True, timeout=30)
    assert version.returncode == 0
    assert version.stdout.startswith("prashna ")


def test_uc_x_15_data_dir_defaults(monkeypatch, tmp_path):
    """UC-X-15: the per-user folder, also from a source checkout; never inside the repository."""
    from prashna import db
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(db.sys, "platform", "linux")
    default = db.default_data_dir()
    assert default == Path.home() / ".local" / "share" / "prashna"
    assert default != ROOT and ROOT not in default.parents
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert db.default_data_dir() == tmp_path / "xdg" / "prashna"
    monkeypatch.setattr(db.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert db.default_data_dir() == tmp_path / "local" / "prashna"
    monkeypatch.setattr(db.sys, "platform", "darwin")
    assert db.default_data_dir() == Path.home() / "Library" / "Application Support" / "prashna"


def test_uc_x_15_install_scripts_are_served(client):
    """UC-X-15: /install.sh and /install.ps1 are served as text."""
    sh = client.get("/install.sh")
    assert sh.status_code == 200
    assert sh.headers["content-type"].startswith("text/plain")
    assert "uv tool install --upgrade prashna" in sh.text
    assert "https://astral.sh/uv/install.sh" in sh.text
    ps1 = client.get("/install.ps1")
    assert ps1.status_code == 200
    assert ps1.headers["content-type"].startswith("text/plain")
    assert "uv tool install --upgrade prashna" in ps1.text
    assert "https://astral.sh/uv/install.ps1" in ps1.text
