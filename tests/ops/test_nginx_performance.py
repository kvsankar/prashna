from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_enable_http2_is_idempotent_and_preserves_a_backup(tmp_path):
    site = tmp_path / "prashna.conf"
    site.write_text(
        """server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name prashna.sankara.net;
}
"""
    )
    env = {
        **os.environ,
        "PRASHNA_NGINX_SITE_PATH": str(site),
        "PRASHNA_NGINX_TEST_MODE": "1",
    }
    script = ROOT / "deploy" / "enable-http2.sh"

    subprocess.run(["bash", str(script)], check=True, env=env)
    configured = site.read_text()
    assert "listen 443 ssl http2;" in configured
    assert "listen [::]:443 ssl http2;" in configured
    assert len(list(tmp_path.glob("prashna.conf.bak.*"))) == 1

    subprocess.run(["bash", str(script)], check=True, env=env)
    assert len(list(tmp_path.glob("prashna.conf.bak.*"))) == 1


def test_enable_http2_rejects_a_site_without_tls(tmp_path):
    site = tmp_path / "prashna.conf"
    site.write_text("server { listen 80; }\n")
    result = subprocess.run(
        ["bash", str(ROOT / "deploy" / "enable-http2.sh")],
        env={
            **os.environ,
            "PRASHNA_NGINX_SITE_PATH": str(site),
            "PRASHNA_NGINX_TEST_MODE": "1",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "no Certbot-managed TLS listener" in result.stderr
