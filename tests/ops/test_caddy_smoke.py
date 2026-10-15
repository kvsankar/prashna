"""Opt-in smoke test for the bundle's HTTPS add-on with Caddy (UC-X-10).

Builds the release bundle, runs it with `compose.https.yaml` and
`PRASHNA_DOMAIN=localhost` (Caddy then uses its own certificate authority),
and checks the redirect, the Secure cookie and a live question over wss.
It pulls `caddy:2` and the release image, so it needs Docker and the network:

    PRASHNA_CADDY_SMOKE=1 uv run pytest tests/ops/test_caddy_smoke.py

`PRASHNA_CADDY_SMOKE_IMAGE_TAG` runs another Prashna image tag than the
bundle's release.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import tarfile
import time
from pathlib import Path

import httpx
import pytest

from scripts.build_release_bundle import build_bundle

ROOT = Path(__file__).resolve().parents[2]
RUN_SMOKE = os.environ.get("PRASHNA_CADDY_SMOKE") == "1"
IMAGE_TAG = os.environ.get("PRASHNA_CADDY_SMOKE_IMAGE_TAG")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _version() -> str:
    import tomllib
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def _env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items()
            if not key.startswith(("PRASHNA_", "COMPOSE_"))}


def _compose(bundle: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", "compose", *args], cwd=bundle, env=_env(), text=True,
                          capture_output=True, check=False, timeout=timeout)


def _wait_for(check, timeout: float = 60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(1)
    raise AssertionError("timed out")


@pytest.mark.skipif(not RUN_SMOKE, reason="set PRASHNA_CADDY_SMOKE=1 to run Docker and pull images")
def test_uc_x_10_https_add_on_end_to_end(tmp_path):
    from playwright.sync_api import expect, sync_playwright

    version = _version()
    tar_path = build_bundle(version, tmp_path / "dist")[0]
    with tarfile.open(tar_path) as archive:
        archive.extractall(tmp_path, filter="data")
    bundle = tmp_path / f"prashna-{version}"
    http_port, https_port = _free_port(), _free_port()
    project = f"prashnacaddysmoke{secrets.token_hex(3)}"
    settings = [
        "COMPOSE_FILE=compose.yaml:compose.https.yaml",
        f"COMPOSE_PROJECT_NAME={project}",
        f"PRASHNA_HTTP_PORT={http_port}",
        f"PRASHNA_HTTPS_PORT={https_port}",
    ]
    if IMAGE_TAG:
        settings.append(f"PRASHNA_IMAGE_TAG={IMAGE_TAG}")
    env_file = bundle / ".env"
    env_file.write_text("\n".join(settings) + "\n", encoding="utf-8")

    missing = _compose(bundle, "config")
    assert missing.returncode != 0
    assert "Set PRASHNA_DOMAIN in .env to your domain name" in missing.stderr

    env_file.write_text("\n".join([*settings, "PRASHNA_DOMAIN=localhost"]) + "\n", encoding="utf-8")
    base = f"https://localhost:{https_port}"
    try:
        up = _compose(bundle, "up", "-d", "--wait", timeout=600)
        assert up.returncode == 0, up.stdout + up.stderr

        # Only Caddy publishes ports.
        listing = _compose(bundle, "ps", "--format", "json")
        services = [json.loads(line) for line in listing.stdout.splitlines() if line.strip()]
        published = {service["Service"]: {p["PublishedPort"] for p in service.get("Publishers") or []
                                          if p.get("PublishedPort")}
                     for service in services}
        assert published["prashna"] == set()
        assert published["caddy"] == {http_port, https_port}

        # HTTP redirects to HTTPS.
        redirect = httpx.get(f"http://localhost:{http_port}/", follow_redirects=False, timeout=10)
        assert redirect.status_code in (301, 308)
        assert redirect.headers["location"].startswith("https://localhost")

        with httpx.Client(base_url=base, verify=False, timeout=10) as client:
            def ready():
                try:
                    return client.get("/api/admin/status").status_code == 200
                except httpx.HTTPError:
                    return False
            _wait_for(ready)
            assert client.get("/").headers.get("strict-transport-security") == "max-age=31536000"

            def setup_token():
                logs = _compose(bundle, "logs", "--no-color", "prashna").stdout
                match = re.search(r"/#setup=([A-Za-z0-9_-]+)", logs)
                return match.group(1) if match else None
            token = _wait_for(setup_token)
            setup = client.post("/api/admin/setup",
                                json={"username": "owner", "password": "smoke-pass-1", "setup_token": token})  # pragma: allowlist secret
            assert setup.status_code == 200, setup.text
            set_cookie = setup.headers["set-cookie"]
            assert "prashna_admin=" in set_cookie and "Secure" in set_cookie
            cookie = client.cookies["prashna_admin"]
            created = client.post("/api/sessions", json={"title": "Caddy smoke"})
            assert created.status_code == 200, created.text
            code = created.json()["code"]
            assert client.post(f"/api/sessions/{code}/start").status_code == 200

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            sockets: list[str] = []
            errors: list[str] = []
            try:
                moderator_context = browser.new_context(ignore_https_errors=True)
                moderator_context.add_cookies([{"name": "prashna_admin", "value": cookie,
                                                "url": f"{base}/", "secure": True, "httpOnly": True}])
                moderator = moderator_context.new_page()
                participant = browser.new_context(ignore_https_errors=True).new_page()
                for page in (moderator, participant):
                    page.on("websocket", lambda ws: sockets.append(ws.url))
                    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
                moderator.goto(f"{base}/m/{code}")
                moderator.wait_for_selector("#queries-card:visible")
                participant.goto(f"{base}/s/{code}")
                participant.wait_for_selector("#ask-card:visible")
                participant.fill("#query-text", "Does the question arrive over wss?")
                participant.click("#ask-btn")
                expect(moderator.locator("#queries")).to_contain_text("Does the question arrive over wss?",
                                                                      timeout=10000)
            finally:
                browser.close()
            assert sockets and all(url.startswith(f"wss://localhost:{https_port}/ws/sessions/")
                                   for url in sockets), sockets
            assert errors == []
    finally:
        _compose(bundle, "down", "--volumes", "--remove-orphans", timeout=180)
