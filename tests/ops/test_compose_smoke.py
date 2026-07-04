"""Docker Compose deployment smoke coverage."""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "docker-compose.yml"
SETUP = ROOT / "deploy" / "setup.sh"
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)
SMOKE_SECRET = "dummy_secret_not_real"


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _run(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def _compose_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base or os.environ)
    for key in tuple(env):
        if key.startswith("PRASHNA_"):
            env.pop(key)
    return env


def _write_env(path: Path, *, port: int, data_dir: Path, uploads_dir: Path):
    path.write_text(
        "\n".join(
            [
                f"PRASHNA_SECRET_KEY={SMOKE_SECRET}",
                "PRASHNA_TRUSTED_PROXY_HOPS=1",
                "PRASHNA_RATELIMIT=off",
                f"PRASHNA_PORT={port}",
                f"PRASHNA_DATA_DIR={data_dir}",
                f"PRASHNA_UPLOADS_HOST_DIR={uploads_dir}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _compose_cmd(project: str, env_file: Path, override: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(COMPOSE),
        "-f",
        str(override),
        "--project-name",
        project,
    ]


def _wait_for_status(base_url: str, *, timeout: int = 90) -> dict:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/api/admin/status", timeout=2.0)
            if r.status_code == 200:
                return r.json()
            last_error = f"status {r.status_code}: {r.text[:200]}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)
    raise AssertionError(
        f"compose health endpoint did not become ready: {last_error}"
    )


def test_compose_config_reports_missing_secret_actionably():
    result = _run(
        ["docker", "compose", "-f", str(COMPOSE), "config"],
        env=_compose_env(),
        timeout=30,
    )
    assert result.returncode != 0
    assert "Set PRASHNA_SECRET_KEY in .env" in result.stdout


def test_compose_config_declares_health_and_persistent_paths(tmp_path):
    env_file = tmp_path / ".env"
    data_dir = tmp_path / "data"
    uploads_dir = tmp_path / "uploads"
    data_dir.mkdir()
    uploads_dir.mkdir()
    _write_env(
        env_file,
        port=8766,
        data_dir=data_dir,
        uploads_dir=uploads_dir,
    )

    result = _run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(COMPOSE),
            "config",
        ],
        env=_compose_env(),
        timeout=30,
    )

    assert result.returncode == 0
    assert "http://127.0.0.1:8000/api/admin/status" in result.stdout
    assert str(data_dir) in result.stdout
    assert str(uploads_dir) in result.stdout
    assert "/data/prashna.db" in result.stdout
    assert "/app/uploads" in result.stdout
    assert SMOKE_SECRET in result.stdout


def test_setup_script_provisions_container_writable_persistent_paths():
    script = SETUP.read_text(encoding="utf-8")

    assert "APP_UID=1001" in script
    assert "APP_GID=1001" in script
    assert 'sudo install -d -o "$APP_UID" -g "$APP_GID"' in script
    assert 'sudo chown -R "$APP_UID:$APP_GID"' in script
    assert '"$APP_DIR/data" "$APP_DIR/uploads"' in script
    assert 'sudo install -d -o "$USER" -g "$USER" "$APP_DIR"' in script
    assert '"$APP_DIR" "$APP_DIR/data" "$APP_DIR/uploads"' not in script


if os.environ.get("PRASHNA_COMPOSE_SMOKE") == "1":

    def test_compose_deploy_smoke_preserves_state_and_logs_safely(tmp_path):
        project = f"prashna-smoke-{secrets.token_hex(4)}"
        image = f"{project}:latest"
        port = _free_port()
        env_file = tmp_path / ".env"
        override = tmp_path / "compose.override.yml"
        data_dir = tmp_path / "data"
        uploads_dir = tmp_path / "uploads"
        data_dir.mkdir()
        uploads_dir.mkdir()
        data_dir.chmod(0o777)
        uploads_dir.chmod(0o777)
        _write_env(
            env_file,
            port=port,
            data_dir=data_dir,
            uploads_dir=uploads_dir,
        )
        override.write_text(
            "\n".join(
                [
                    "services:",
                    "  prashna:",
                    f"    image: {image}",
                    "    build:",
                    f"      context: {ROOT}",
                    f"    container_name: {project}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        cmd = _compose_cmd(project, env_file, override)
        base_url = f"http://127.0.0.1:{port}"

        try:
            up = _run(
                cmd + ["up", "--build", "-d"],
                env=_compose_env(),
                timeout=300,
            )
            assert up.returncode == 0, up.stdout
            assert _wait_for_status(base_url)["initialized"] is False

            with httpx.Client(base_url=base_url, timeout=10.0) as client:
                setup = client.post(
                    "/api/admin/setup",
                    json={"username": "admin", "password": "testpass1"},
                )
                assert setup.status_code == 200, setup.text
                cookie = client.cookies.get("prashna_admin")
                assert cookie
                upload = client.post(
                    "/api/uploads",
                    files={"file": ("a.png", PNG_BYTES, "image/png")},
                )
                assert upload.status_code == 200, upload.text
                uploaded = uploads_dir / Path(upload.json()["url"]).name
                assert uploaded.is_file()

            restarted = _run(cmd + ["restart", "prashna"], env=_compose_env())
            assert restarted.returncode == 0, restarted.stdout
            assert _wait_for_status(base_url)["initialized"] is True
            with httpx.Client(
                base_url=base_url,
                cookies={"prashna_admin": cookie},
                timeout=10.0,
            ) as client:
                status = client.get("/api/admin/status")
                assert status.json()["authenticated"] is True
            assert (data_dir / "prashna.db").is_file()
            assert uploaded.is_file()

            logs = _run(
                cmd + ["logs", "--no-color", "prashna"],
                env=_compose_env(),
            )
            assert logs.returncode == 0, logs.stdout
            assert "diagnostic_event" in logs.stdout
            assert SMOKE_SECRET not in logs.stdout
        finally:
            _run(
                cmd + ["down", "--volumes", "--remove-orphans"],
                env=_compose_env(),
                timeout=120,
            )
