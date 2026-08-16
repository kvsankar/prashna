from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "prepare-cloudflare-proxy.sh"


def _env(tmp_path: Path, site: Path, ipv4: Path, ipv6: Path) -> dict[str, str]:
    return {
        **os.environ,
        "PRASHNA_NGINX_SITE_PATH": str(site),
        "PRASHNA_CLOUDFLARE_INCLUDE_PATH": str(tmp_path / "cloudflare-realip.conf"),
        "PRASHNA_CLOUDFLARE_IPV4_URL": ipv4.as_uri(),
        "PRASHNA_CLOUDFLARE_IPV6_URL": ipv6.as_uri(),
        "PRASHNA_NGINX_TEST_MODE": "1",
    }


def test_prepare_cloudflare_proxy_is_validated_and_idempotent(tmp_path: Path):
    site = tmp_path / "prashna.conf"
    site.write_text("server { listen 443 ssl http2; }\n")
    ipv4 = tmp_path / "ips-v4"
    ipv4.write_text("192.0.2.0/24\n")
    ipv6 = tmp_path / "ips-v6"
    ipv6.write_text("2001:db8::/32\n")
    env = _env(tmp_path, site, ipv4, ipv6)

    subprocess.run(["bash", str(SCRIPT)], check=True, env=env)
    subprocess.run(["bash", str(SCRIPT)], check=True, env=env)

    include = tmp_path / "cloudflare-realip.conf"
    configured = include.read_text()
    assert "set_real_ip_from 192.0.2.0/24;" in configured
    assert "set_real_ip_from 2001:db8::/32;" in configured
    assert "real_ip_header CF-Connecting-IP;" in configured
    include_line = f"include {include};"
    assert site.read_text().count(include_line) == 1
    assert len(list(tmp_path.glob("prashna.conf.bak.*"))) >= 1


def test_prepare_cloudflare_proxy_rejects_invalid_ranges_without_changes(
    tmp_path: Path,
):
    site = tmp_path / "prashna.conf"
    original = "server { listen 80; }\n"
    site.write_text(original)
    ipv4 = tmp_path / "ips-v4"
    ipv4.write_text("not-a-network\n")
    ipv6 = tmp_path / "ips-v6"
    ipv6.write_text("2001:db8::/32\n")

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=_env(tmp_path, site, ipv4, ipv6),
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert site.read_text() == original
    assert not (tmp_path / "cloudflare-realip.conf").exists()
    assert not list(tmp_path.glob("prashna.conf.bak.*"))


def test_prepare_cloudflare_proxy_rejects_an_empty_address_family(tmp_path: Path):
    site = tmp_path / "prashna.conf"
    original = "server { listen 80; }\n"
    site.write_text(original)
    ipv4 = tmp_path / "ips-v4"
    ipv4.write_text("192.0.2.0/24\n")
    ipv6 = tmp_path / "ips-v6"
    ipv6.write_text("")

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=_env(tmp_path, site, ipv4, ipv6),
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "IPv6 range response was empty" in result.stderr
    assert site.read_text() == original
    assert not (tmp_path / "cloudflare-realip.conf").exists()
