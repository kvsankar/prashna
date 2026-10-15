"""UC-X-15: the `prashna` command and the hosted install scripts.

The CLI tests run the real command in a subprocess on a free port. The
browser is captured through the standard BROWSER variable, which Python's
webbrowser module honours, so the test sees exactly the URL a user's
browser would be sent to.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import httpx
import pytest

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
    # The terminal stays readable: no diagnostics, and the setup link once.
    assert "diagnostic_event" not in out
    assert out.count("#setup=") == 1
    assert "diagnostic_event" in (data / "prashna.log").read_text()


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
        out = _stop(proc)
    assert out.count("#setup=") == 1
    assert "diagnostic_event" not in out

    proc = _start_cli(["--port", str(port)], _cli_env(BROWSER=browser, PRASHNA_DATA_DIR=str(data)))
    try:
        _wait_up(port)
        assert _wait_for_file(opened) == f"http://127.0.0.1:{port}/"
    finally:
        _stop(proc)


def _start_patched_cli(patch: str, args: list[str], env: dict[str, str]) -> subprocess.Popen[str]:
    """Run `prashna` after the Python statements in `patch`, which stand in
    for a part of the machine (the browser, or a Ctrl+C) in the test."""
    code = f"import sys\n{patch}\nfrom prashna import cli\nsys.exit(cli.main(sys.argv[1:]))\n"
    return subprocess.Popen([sys.executable, "-c", code, *args], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


@pytest.mark.parametrize("browser", ["opens", "fails", "disabled"])
def test_uc_x_15_terminal_always_shows_the_setup_link(tmp_path, browser):
    """UC-X-15: while no admin exists the terminal shows the one-time setup
    link exactly once, whether the browser opens, fails to open (as over
    SSH), or is turned off; once an admin exists it shows no setup link."""
    port, data = _free_port(), tmp_path / "data"
    args = ["--data-dir", str(data), "--port", str(port)]
    recorder, opened = _recorder(tmp_path)
    if browser == "opens":
        proc = _start_cli(args, _cli_env(BROWSER=recorder))
    elif browser == "fails":
        # No BROWSER setting, and webbrowser finds no browser to open: it
        # notes the URL it was asked to open, then reports failure.
        patch = ("import webbrowser\n"
                 f"webbrowser.open = lambda url, *a, **k: (open({str(opened)!r}, 'a').write(url + '\\n'), False)[1]")
        env = _cli_env()
        env.pop("BROWSER", None)
        proc = _start_patched_cli(patch, args, env)
    else:
        proc = _start_cli([*args, "--no-browser"], _cli_env())
    try:
        _wait_up(port)
        token = (data / "setup-token").read_text().strip()
        if browser != "disabled":
            assert _wait_for_file(opened) == f"http://127.0.0.1:{port}/#setup={token}"
        httpx.post(f"http://127.0.0.1:{port}/api/admin/setup",
                   json={"username": "me", "password": "longenough", "setup_token": token}).raise_for_status()
    finally:
        out = _stop(proc)
    assert out.count("#setup=") == 1, out
    assert f"http://127.0.0.1:{port}/#setup={token}" in out

    proc = _start_cli([*args, "--no-browser"], _cli_env())
    try:
        _wait_up(port)
    finally:
        later = _stop(proc)
    assert "#setup=" not in later


def test_uc_x_15_ctrl_c_while_starting_exits_quietly(tmp_path):
    """UC-X-15: a Ctrl+C that arrives before the server serves ends the
    command quietly, with no traceback."""
    patch = "import uvicorn\ndef interrupted(*a, **k):\n    raise KeyboardInterrupt\nuvicorn.run = interrupted"
    proc = _start_patched_cli(patch, ["--data-dir", str(tmp_path / "d"), "--port", str(_free_port()),
                                      "--no-browser"], _cli_env())
    out, _ = proc.communicate(timeout=60)
    assert "Press Ctrl+C to stop." in out
    assert "Traceback" not in out
    assert "KeyboardInterrupt" not in out
    assert proc.returncode == 130, out


@pytest.mark.parametrize("command", [[], ["create"], ["restore"]])
def test_uc_x_15_backup_help(tmp_path, command):
    """UC-X-15: `prashna backup [create|restore] --help` prints help written
    for users and exits 0, without touching the data folder."""
    data = tmp_path / "data"
    result = subprocess.run(
        [sys.executable, "-m", "prashna.cli", "--data-dir", str(data), "backup", *command, "--help"],
        cwd=ROOT, env=_cli_env(), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    help_text = result.stdout
    usage = " ".join(help_text.split("\n\n", 1)[0].split())
    assert usage.startswith(f"usage: prashna backup {' '.join(command)}".rstrip()), usage
    assert "container" not in help_text.lower()
    assert "sqlite" not in help_text.lower()
    assert "uploaded images" in help_text
    if command:
        # argparse lists a described argument as "  archive   <its help>".
        assert re.search(r"^\s+archive\s+\S", help_text, re.MULTILINE), help_text
    if command == ["restore"]:
        assert re.search(r"^\s+--confirm\s+\S", help_text, re.MULTILINE), help_text
    if not command:
        assert "create" in help_text and "restore" in help_text
    assert not data.exists()


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


def _seed_db(folder: Path, marker: str) -> None:
    """A minimal Prashna-shaped database whose one admin is named `marker`,
    plus one upload, so an archive shows which folder it came from."""
    import sqlite3
    from contextlib import closing

    folder.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(folder / "prashna.db")) as con:
        con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
        con.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY)")
        con.execute("INSERT INTO users (username) VALUES (?)", (marker,))
        con.commit()
    (folder / "uploads").mkdir(exist_ok=True)
    (folder / "uploads" / f"{marker}.png").write_bytes(marker.encode())


def _archived_admin(archive: Path, tmp_path: Path) -> tuple[str, list[str]]:
    """The admin name in an archive's database, and its upload names."""
    import sqlite3
    from contextlib import closing

    out = tmp_path / "unpacked"
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        tar.extract("prashna.db", out, filter="data")
    with closing(sqlite3.connect(out / "prashna.db")) as con:
        (name,) = con.execute("SELECT username FROM users").fetchone()
    return name, sorted(n for n in names if n.startswith("uploads/"))


def test_uc_x_15_explicit_data_dir_wins_over_environment_paths(tmp_path):
    """UC-X-15: an explicit --data-dir wins over PRASHNA_DB_PATH and
    PRASHNA_UPLOADS_DIR for the server, backup, and reset-password."""
    folder_a, folder_b = tmp_path / "a", tmp_path / "b"
    env_a = _cli_env(PRASHNA_DB_PATH=str(folder_a / "prashna.db"),
                     PRASHNA_UPLOADS_DIR=str(folder_a / "uploads"))

    # The server: the database, signing key and setup token go to B.
    port = _free_port()
    proc = _start_cli(["--data-dir", str(folder_b), "--port", str(port), "--no-browser"], env_a)
    try:
        _wait_up(port)
    finally:
        out = _stop(proc)
    assert f"Created a new database: {folder_b / 'prashna.db'}" in out
    assert (folder_b / "prashna.db").is_file()
    assert (folder_b / "secret-key").is_file()
    assert (folder_b / "setup-token").is_file()
    assert not folder_a.exists()

    # Backup: B's database and uploads, not A's.
    _seed_db(folder_a, "alice")
    (folder_b / "prashna.db").unlink()
    _seed_db(folder_b, "bob")
    archive = tmp_path / "b.tar.gz"
    result = subprocess.run(
        [sys.executable, "-m", "prashna.cli", "--data-dir", str(folder_b), "backup", "create", str(archive)],
        cwd=ROOT, env=env_a, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _archived_admin(archive, tmp_path) == ("bob", ["uploads/bob.png"])

    # reset-password: B's database. A has a valid-looking admin row too, but
    # no password, so the command would stop with "No admin yet" there.
    (folder_b / "prashna.db").unlink()
    port = _free_port()
    proc = _start_cli(["--data-dir", str(folder_b), "--port", str(port), "--no-browser"],
                      _cli_env(PRASHNA_SETUP_TOKEN="t"))
    try:
        _wait_up(port)
        httpx.post(f"http://127.0.0.1:{port}/api/admin/setup",
                   json={"username": "me", "password": "oldpassword", "setup_token": "t"}).raise_for_status()  # pragma: allowlist secret
    finally:
        _stop(proc)
    reset = subprocess.run(
        [sys.executable, "-m", "prashna.cli", "reset-password", "--data-dir", str(folder_b)],
        cwd=ROOT, env=env_a, input="newpassword\nnewpassword\n", capture_output=True, text=True, timeout=60)
    assert reset.returncode == 0, reset.stdout + reset.stderr
    assert "Password changed for me." in reset.stdout


def test_uc_x_15_environment_paths_apply_without_data_dir(tmp_path):
    """UC-X-15: without --data-dir, PRASHNA_DB_PATH and PRASHNA_UPLOADS_DIR
    still choose the database and uploads."""
    folder_a, data = tmp_path / "a", tmp_path / "data"
    env = _cli_env(PRASHNA_DATA_DIR=str(data),
                   PRASHNA_DB_PATH=str(folder_a / "prashna.db"),
                   PRASHNA_UPLOADS_DIR=str(folder_a / "uploads"))
    port = _free_port()
    proc = _start_cli(["--port", str(port), "--no-browser"], env)
    try:
        _wait_up(port)
    finally:
        out = _stop(proc)
    assert f"Created a new database: {folder_a / 'prashna.db'}" in out
    assert (folder_a / "secret-key").is_file()
    assert not (data / "prashna.db").exists()

    (folder_a / "prashna.db").unlink()
    _seed_db(folder_a, "alice")
    archive = tmp_path / "a.tar.gz"
    result = subprocess.run([sys.executable, "-m", "prashna.cli", "backup", "create", str(archive)],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _archived_admin(archive, tmp_path) == ("alice", ["uploads/alice.png"])


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


def test_uc_x_15_installer_stops_when_uv_cannot_be_installed(tmp_path):
    """UC-X-15: with no uv and a failing download, install.sh exits 1 with a clear message."""
    import shutil
    if shutil.which("uv", path="/usr/bin:/bin"):
        pytest.skip("uv is installed system-wide, so the installer would not need to fetch it")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    (stubs / "curl").write_text("#!/bin/sh\necho 'curl: (6) Could not resolve host' >&2\nexit 6\n")
    (stubs / "curl").chmod(0o755)
    result = subprocess.run(
        ["sh", str(ROOT / "prashna" / "installers" / "install.sh")],
        env={"HOME": str(tmp_path), "PATH": f"{stubs}:/usr/bin:/bin"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert "https://docs.astral.sh/uv/" in result.stderr
    assert "uv: not found" not in result.stderr


def test_uc_x_15_installer_stops_when_uv_tool_install_fails(tmp_path):
    """UC-X-15: when `uv tool install` fails, install.sh exits non-zero and
    does not say Prashna is installed."""
    stubs = tmp_path / "bin"
    stubs.mkdir()
    (stubs / "uv").write_text('#!/bin/sh\nif [ "$1 $2" = "tool install" ]; then\n'
                              '    echo "error: failed to fetch prashna" >&2\n    exit 1\nfi\nexit 0\n')
    (stubs / "uv").chmod(0o755)
    result = subprocess.run(
        ["sh", str(ROOT / "prashna" / "installers" / "install.sh")],
        env={"HOME": str(tmp_path), "PATH": f"{stubs}:/usr/bin:/bin"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "failed to fetch prashna" in result.stderr
    assert "Prashna is installed" not in result.stdout


# ---------- --tunnel (UC-X-15) ----------

STUB_URLS = {"cloudflare": "https://stub-tunnel.trycloudflare.com", "ngrok": "https://stub-tunnel.ngrok-free.app"}

_STUB = '''#!{python}
import json, os, sys, time
d = os.environ["STUB_DIR"]
open(os.path.join(d, "{name}.pid"), "w").write(str(os.getpid()))
open(os.path.join(d, "{name}.args"), "w").write(json.dumps(sys.argv[1:]))
{body}
while True:
    time.sleep(0.2)
'''
_BODIES = {
    # cloudflared logs its quick-tunnel address in a box on stderr.
    "cloudflared": 'print("INF +----------------------------------------+", file=sys.stderr, flush=True)\n'
                   'print("INF |  https://stub-tunnel.trycloudflare.com  |", file=sys.stderr, flush=True)',
    # ngrok with --log stdout --log-format json writes one JSON object per line.
    "ngrok": 'print(json.dumps({"lvl": "info", "msg": "started tunnel", "url": "https://stub-tunnel.ngrok-free.app"}), flush=True)',
}


def _stub_dir(tmp_path: Path, body_overrides: dict[str, str] | None = None) -> Path:
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    for name, body in {**_BODIES, **(body_overrides or {})}.items():
        script = stubs / name
        script.write_text(_STUB.format(python=sys.executable, name=name, body=body))
        script.chmod(0o755)
    return stubs


def _setup_admin_and_session(base: str) -> tuple[httpx.Client, dict]:
    c = httpx.Client(base_url=base, timeout=10)
    c.post("/api/admin/setup", json={"username": "me", "password": "longenough", "setup_token": "t"}).raise_for_status()
    session = c.post("/api/sessions", json={"title": "Tunnel"}).json()
    return c, session


@pytest.mark.parametrize("kind", ["cloudflare", "ngrok"])
def test_uc_x_15_tunnel_wires_the_public_address(tmp_path, kind):
    """UC-X-15: --tunnel starts the tunnel, prints its address, makes it every
    session's default address, and stops the tunnel with Prashna."""
    stubs = _stub_dir(tmp_path)
    port = _free_port()
    env = _cli_env(PATH=f"{stubs}{os.pathsep}{os.environ['PATH']}", STUB_DIR=str(stubs), PRASHNA_SETUP_TOKEN="t",
                   PRASHNA_TUNNEL_DNS_WAIT_SECS="0")
    proc = _start_cli(["--data-dir", str(tmp_path / "d"), "--port", str(port), "--no-browser", "--tunnel", kind], env)
    program = "cloudflared" if kind == "cloudflare" else "ngrok"
    try:
        _wait_up(port)
        c, session = _setup_admin_and_session(f"http://127.0.0.1:{port}")
        assert c.get(f"/api/sessions/{session['code']}").json()["default_base_url"] == STUB_URLS[kind]
        c.close()
        args = (stubs / f"{program}.args").read_text()
        assert str(port) in args
    finally:
        out = _stop(proc)
    assert f"Participants join at: {STUB_URLS[kind]}" in out
    pid = int((stubs / f"{program}.pid").read_text())
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, 9)
        raise AssertionError("the tunnel kept running after Prashna stopped")


def test_uc_x_15_tunnel_rate_limits_each_visitor(tmp_path):
    """UC-X-15: behind the tunnel, rate limits apply per visitor, not per tunnel."""
    stubs = _stub_dir(tmp_path)
    port = _free_port()
    env = _cli_env(PATH=f"{stubs}{os.pathsep}{os.environ['PATH']}", STUB_DIR=str(stubs), PRASHNA_SETUP_TOKEN="t",
                   PRASHNA_TUNNEL_DNS_WAIT_SECS="0")
    env["PRASHNA_RATELIMIT"] = "on"  # the test configuration turns limiting off
    proc = _start_cli(["--data-dir", str(tmp_path / "d"), "--port", str(port), "--no-browser", "--tunnel", "cloudflare"], env)
    try:
        _wait_up(port)
        c, _session = _setup_admin_and_session(f"http://127.0.0.1:{port}")
        c.close()
        wrong = {"username": "me", "password": "wrong-password"}  # pragma: allowlist secret
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as visitor:
            codes = [visitor.post("/api/admin/login", json=wrong,
                                  headers={"X-Forwarded-For": "203.0.113.5"}).status_code for _ in range(9)]
            assert codes[-1] == 429, codes
            other = visitor.post("/api/admin/login", json=wrong, headers={"X-Forwarded-For": "203.0.113.6"})
            assert other.status_code == 401, other.text
    finally:
        _stop(proc)


def test_uc_x_15_tunnel_reports_missing_or_failed_programs(tmp_path):
    """UC-X-15: a missing tunnel program, or one that exits without an address,
    stops Prashna with status 1 and says why."""
    import shutil
    if shutil.which("cloudflared", path="/usr/bin:/bin"):
        pytest.skip("cloudflared is installed system-wide")
    missing = subprocess.run(
        [sys.executable, "-m", "prashna.cli", "--data-dir", str(tmp_path / "d1"), "--port", str(_free_port()),
         "--no-browser", "--tunnel", "cloudflare"],
        cwd=ROOT, env=_cli_env(PATH="/usr/bin:/bin"), capture_output=True, text=True, timeout=30)
    assert missing.returncode == 1
    assert "cloudflared" in missing.stderr and "install" in missing.stderr.lower()

    stubs = _stub_dir(tmp_path, {"cloudflared": 'print("ERR failed to reach the edge: test failure", file=sys.stderr, flush=True)\nsys.exit(1)'})
    failed = subprocess.run(
        [sys.executable, "-m", "prashna.cli", "--data-dir", str(tmp_path / "d2"), "--port", str(_free_port()),
         "--no-browser", "--tunnel", "cloudflare"],
        cwd=ROOT, env=_cli_env(PATH=f"{stubs}{os.pathsep}/usr/bin:/bin", STUB_DIR=str(stubs)),
        capture_output=True, text=True, timeout=60)
    assert failed.returncode == 1
    assert "test failure" in failed.stderr


# cloudflared's own lines: what it prints when the quick tunnel is created,
# and what it prints when it cannot reach Cloudflare (network blocked).
CLOUDFLARED_SUCCESS = [
    "2026-10-15T10:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...",
    "2026-10-15T10:00:03Z INF +--------------------------------------------------------------------------------------------+",
    "2026-10-15T10:00:03Z INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |",
    "2026-10-15T10:00:03Z INF |  https://wired-example-words-here.trycloudflare.com                                        |",
    "2026-10-15T10:00:03Z INF +--------------------------------------------------------------------------------------------+",
]
CLOUDFLARED_FAILURE = [
    "2026-10-15T10:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...",
    '2026-10-15T10:00:01Z ERR failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": '
    "dial tcp: lookup api.trycloudflare.com: no such host",
]


def test_uc_x_15_tunnel_failure_never_reports_the_api_address(tmp_path):
    """UC-X-15: when cloudflared cannot create the quick tunnel, Prashna exits 1
    and shows its output; the API address in the error is never the address."""
    lines = "\n".join(f"print({line!r}, file=sys.stderr, flush=True)" for line in CLOUDFLARED_FAILURE)
    stubs = _stub_dir(tmp_path, {"cloudflared": f"{lines}\nsys.exit(1)"})
    proc = subprocess.Popen(
        [sys.executable, "-m", "prashna.cli", "--data-dir", str(tmp_path / "d"), "--port", str(_free_port()),
         "--no-browser", "--tunnel", "cloudflare"],
        cwd=ROOT, env=_cli_env(PATH=f"{stubs}{os.pathsep}/usr/bin:/bin", STUB_DIR=str(stubs),
                               PRASHNA_TUNNEL_DNS_WAIT_SECS="0"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        raise AssertionError(f"prashna kept running after the tunnel failed:\n{out}{err}") from None
    assert proc.returncode == 1, out + err
    assert "failed to request quick Tunnel" in err
    assert "Participants join at" not in out + err


class _FakeTunnelProcess:
    """Stands in for the tunnel program: prints `lines`, then exits."""

    def __init__(self, lines: list[str]) -> None:
        import io
        self.stdout = io.StringIO("".join(line + "\n" for line in lines))
        self.returncode: int | None = None

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            self.returncode = 1
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    kill = terminate


@pytest.mark.parametrize(("kind", "lines", "expected"), [
    ("cloudflare", CLOUDFLARED_SUCCESS, "https://wired-example-words-here.trycloudflare.com"),
    ("cloudflare", CLOUDFLARED_FAILURE, None),
    ("ngrok", ['{"lvl": "info", "msg": "update available", "url": "https://ngrok.com/download"}',
               '{"addr": "http://127.0.0.1:8000", "lvl": "info", "msg": "started tunnel", "name": "command_line", '
               '"obj": "tunnels", "url": "https://abc-123.ngrok-free.app"}'],
     "https://abc-123.ngrok-free.app"),
    ("ngrok", ['{"lvl": "info", "msg": "update available", "url": "https://ngrok.com/download"}'], None),
], ids=["cloudflare-success-box", "cloudflare-api-error", "ngrok-started-tunnel", "ngrok-other-record"])
def test_uc_x_15_tunnel_reads_only_the_success_report(monkeypatch, kind, lines, expected):
    """UC-X-15: the public address comes only from the tunnel's success report;
    a URL in any other line (such as cloudflared's API error) is never used."""
    from prashna import tunnel

    started: list[list[str]] = []
    monkeypatch.setattr(tunnel.shutil, "which", lambda name: f"/opt/fake/{name}")
    monkeypatch.setattr(tunnel.subprocess, "Popen",
                        lambda command, **_: (started.append(command), _FakeTunnelProcess(lines))[1])
    t = tunnel.Tunnel(kind, 8000)
    assert started and started[0][0].startswith("/opt/fake/")
    if expected:
        assert t.wait_for_url(timeout=5) == expected
    else:
        with pytest.raises(tunnel.TunnelError) as error:
            t.wait_for_url(timeout=5)
        assert t.url is None
        assert lines[-1] in str(error.value)


def test_uc_x_15_tunnel_waits_for_public_dns(monkeypatch):
    """UC-X-15: the quick-tunnel address is reported only once public DNS has it."""
    from prashna import tunnel

    answers = iter([{"Status": 3}, {"Status": 3}, {"Status": 0, "Answer": [{"data": "198.51.100.7"}]}])
    asked = []
    monkeypatch.setattr(tunnel, "_doh_query", lambda host: (asked.append(host), next(answers))[1])
    monkeypatch.setattr(tunnel.time, "sleep", lambda _s: None)
    assert tunnel.wait_until_resolvable("https://new-name.trycloudflare.com", timeout=30) is True
    assert asked == ["new-name.trycloudflare.com"] * 3

    monkeypatch.setattr(tunnel, "_doh_query", lambda host: {"Status": 3})
    clock = iter(range(0, 1000, 5))
    monkeypatch.setattr(tunnel.time, "monotonic", lambda: next(clock))
    assert tunnel.wait_until_resolvable("https://never.trycloudflare.com", timeout=30) is False

    monkeypatch.setattr(tunnel, "_doh_query", lambda host: (_ for _ in ()).throw(AssertionError("asked")))
    assert tunnel.wait_until_resolvable("https://x.trycloudflare.com", timeout=0) is True


def test_uc_x_15_reports_new_or_existing_data_and_where_to_sign_in(tmp_path):
    """UC-X-15: the terminal says whether the database is new or existing, what
    it holds, and where to sign in once an admin exists."""
    port, data = _free_port(), tmp_path / "data"
    env = _cli_env(PRASHNA_SETUP_TOKEN="t")
    proc = _start_cli(["--data-dir", str(data), "--port", str(port), "--no-browser"], env)
    try:
        _wait_up(port)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as c:
            c.post("/api/admin/setup", json={"username": "me", "password": "longenough", "setup_token": "t"}).raise_for_status()
            c.post("/api/sessions", json={"title": "One"}).raise_for_status()
    finally:
        first = _stop(proc)
    assert f"Created a new database: {data / 'prashna.db'}" in first
    assert "Sign in at" not in first

    proc = _start_cli(["--data-dir", str(data), "--port", str(port), "--no-browser"], env)
    try:
        _wait_up(port)
    finally:
        second = _stop(proc)
    assert f"Using existing data: {data / 'prashna.db'}" in second
    assert "1 admin (me), 1 session, 0 quizzes" in second
    assert f"Sign in at http://127.0.0.1:{port}/ as me." in second
    assert "Created a new database" not in second


def _reset(data: Path, stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "prashna.cli", "reset-password", "--data-dir", str(data)],
                          cwd=ROOT, env=_cli_env(), input=stdin, capture_output=True, text=True, timeout=60)


def test_uc_x_15_reset_password(tmp_path):
    """UC-X-15: `prashna reset-password` sets a new admin password from the
    machine that holds the data folder, and refuses the error cases."""
    missing = _reset(tmp_path / "nowhere", "newpassword\nnewpassword\n")
    assert missing.returncode == 1 and "No Prashna database in" in missing.stdout + missing.stderr

    port, data = _free_port(), tmp_path / "data"
    proc = _start_cli(["--data-dir", str(data), "--port", str(port), "--no-browser"], _cli_env(PRASHNA_SETUP_TOKEN="t"))
    try:
        _wait_up(port)  # a database now exists, with no admin
    finally:
        _stop(proc)
    no_admin = _reset(data, "newpassword\nnewpassword\n")
    assert no_admin.returncode == 1 and "No admin yet" in no_admin.stdout + no_admin.stderr

    proc = _start_cli(["--data-dir", str(data), "--port", str(port), "--no-browser"], _cli_env(PRASHNA_SETUP_TOKEN="t"))
    try:
        _wait_up(port)
        httpx.post(f"http://127.0.0.1:{port}/api/admin/setup",
                   json={"username": "me", "password": "oldpassword", "setup_token": "t"}).raise_for_status()  # pragma: allowlist secret
        mismatch = _reset(data, "newpassword\notherpassword\n")
        assert mismatch.returncode == 1 and "did not match" in mismatch.stdout + mismatch.stderr
        short = _reset(data, "short\nshort\n")
        assert short.returncode == 1 and "at least 8 characters" in short.stdout + short.stderr
        ok = _reset(data, "newpassword\nnewpassword\n")  # pragma: allowlist secret
        assert ok.returncode == 0, ok.stdout + ok.stderr
        assert "Password changed for me." in ok.stdout
        base = f"http://127.0.0.1:{port}"
        assert httpx.post(f"{base}/api/admin/login", json={"username": "me", "password": "newpassword"}).status_code == 200  # pragma: allowlist secret
        assert httpx.post(f"{base}/api/admin/login", json={"username": "me", "password": "oldpassword"}).status_code == 401  # pragma: allowlist secret
    finally:
        _stop(proc)


def test_uc_x_15_reset_password_over_72_bytes(tmp_path):
    """UC-X-15: a password over 72 bytes exits 1 with a plain message and
    no traceback; the old password still works."""
    port, data = _free_port(), tmp_path / "data"
    proc = _start_cli(["--data-dir", str(data), "--port", str(port), "--no-browser"], _cli_env(PRASHNA_SETUP_TOKEN="t"))
    try:
        _wait_up(port)
        httpx.post(f"http://127.0.0.1:{port}/api/admin/setup",
                   json={"username": "me", "password": "oldpassword", "setup_token": "t"}).raise_for_status()  # pragma: allowlist secret
        too_long = "x" * 80
        result = _reset(data, f"{too_long}\n{too_long}\n")
        output = result.stdout + result.stderr
        assert result.returncode == 1, output
        assert "The password must be at most 72 bytes. Nothing changed." in output
        assert "Traceback" not in output
        base = f"http://127.0.0.1:{port}"
        assert httpx.post(f"{base}/api/admin/login", json={"username": "me", "password": "oldpassword"}).status_code == 200  # pragma: allowlist secret
    finally:
        _stop(proc)


def _make_archive(tmp_path: Path) -> Path:
    """A real archive of a data folder holding a Prashna database and one upload."""
    data = tmp_path / "source"
    port = _free_port()
    proc = _start_cli(["--data-dir", str(data), "--port", str(port), "--no-browser"], _cli_env())
    try:
        _wait_up(port)
    finally:
        _stop(proc)
    (data / "uploads").mkdir(exist_ok=True)
    (data / "uploads" / "photo.png").write_bytes(b"image")
    archive = tmp_path / "backups" / "backup.tar.gz"
    result = subprocess.run(
        [sys.executable, "-m", "prashna.cli", "--data-dir", str(data), "backup", "create", str(archive)],
        cwd=ROOT, env=_cli_env(), capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return archive


def _backup_forms(target: Path) -> dict[str, tuple[list[str], dict[str, str]]]:
    """The two entry points: `prashna backup …` and the container's
    `python -m prashna.backup …`, both aimed at the folder `target`."""
    return {
        "cli": ([sys.executable, "-m", "prashna.cli", "--data-dir", str(target), "backup"], _cli_env()),
        "module": ([sys.executable, "-m", "prashna.backup"],
                   _cli_env(PRASHNA_DB_PATH=str(target / "prashna.db"),
                            PRASHNA_UPLOADS_DIR=str(target / "uploads"))),
    }


@pytest.mark.parametrize("form", ["cli", "module"])
def test_uc_x_10_restore_into_an_empty_data_folder(tmp_path, form):
    """UC-X-10: restoring on a new machine (no database yet) restores the
    archive and writes no pre-restore archive."""
    archive = _make_archive(tmp_path)
    target = tmp_path / "empty"
    command, env = _backup_forms(target)[form]
    result = subprocess.run([*command, "restore", str(archive), "--confirm"],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Traceback" not in output
    assert "no previous data" in output
    assert (target / "prashna.db").is_file()
    assert (target / "uploads" / "photo.png").read_bytes() == b"image"
    assert sorted(p.name for p in archive.parent.iterdir()) == ["backup.tar.gz"]


@pytest.mark.parametrize("form", ["cli", "module"])
def test_uc_x_10_backup_errors_are_plain_messages(tmp_path, form):
    """UC-X-10: a failed backup or restore prints one plain line, exits 1,
    and shows no traceback."""
    target = tmp_path / "empty"
    command, env = _backup_forms(target)[form]
    create = subprocess.run([*command, "create", str(tmp_path / "out.tar.gz")],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert create.returncode == 1
    assert "Backup failed: database not found" in create.stderr
    assert "Traceback" not in create.stdout + create.stderr
    restore = subprocess.run([*command, "restore", str(tmp_path / "missing.tar.gz")],
                             cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert restore.returncode == 1
    assert "Restore failed: restore requires --confirm" in restore.stderr
    assert "Traceback" not in restore.stdout + restore.stderr


def test_uc_x_10_backup_closes_its_database_connections(tmp_path, monkeypatch):
    """UC-X-10: every SQLite connection the backup tool opens is closed
    (on Windows an open snapshot can't be deleted with its temporary folder)."""
    import sqlite3

    from prashna import backup

    data = tmp_path / "data"
    data.mkdir()
    with sqlite3.connect(data / "prashna.db") as seed:
        seed.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        seed.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY)")
    seed.close()
    monkeypatch.setenv("PRASHNA_DB_PATH", str(data / "prashna.db"))
    monkeypatch.setenv("PRASHNA_UPLOADS_DIR", str(data / "uploads"))

    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def spy(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(backup.sqlite3, "connect", spy)
    archive = backup.create_archive(tmp_path / "b.tar.gz")
    backup.restore_archive(archive, confirmed=True)
    assert len(opened) >= 3  # source, snapshot, and the restore check
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
