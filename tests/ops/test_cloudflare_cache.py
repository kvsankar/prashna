from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/configure-cloudflare-cache.sh"


def test_cloudflare_cache_helper_is_valid_and_defaults_to_dry_run():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    source = SCRIPT.read_text()

    assert 'mode="dry-run"' in source
    assert "--apply" in source
    assert 'ref: "prashna_html_shells"' in source
    assert 'http.host eq "prashna.sankara.net"' in source
    assert 'edge_ttl: {mode: "respect_origin"}' in source
    assert 'browser_ttl: {mode: "respect_origin"}' in source
    assert 'map(select(.ref != "prashna_html_shells"))' in source
    assert "--request PUT" in source
    assert "CLOUDFLARE_API_TOKEN" in source
    assert "SANKARA_NET_CLOUDFLARE_API_TOKEN" in source
    assert "CLOUDFLARE_ZONE_ID" in source


def test_cloudflare_cache_dry_run_preserves_unrelated_rules(tmp_path):
    response = tmp_path / "response.json"
    response.write_text(json.dumps({
        "result": {
            "rules": [{
                "ref": "unrelated_rule",
                "description": "keep me",
                "expression": "http.host eq \"example.com\"",
                "action": "set_cache_settings",
                "action_parameters": {"cache": False},
            }]
        }
    }))
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "output=\n"
        "while (($#)); do\n"
        "  if [[ $1 == --output ]]; then output=$2; shift 2; else shift; fi\n"
        "done\n"
        f"cp {response} \"$output\"\n"
        "printf 200\n"
    )
    fake_curl.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "CLOUDFLARE_API_TOKEN": "test-only-token",
        "CLOUDFLARE_ZONE_ID": "test-zone",
    }

    result = subprocess.run(
        [str(SCRIPT), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(result.stdout.split("\n", 1)[1])

    assert [rule["ref"] for rule in payload["rules"]] == [
        "unrelated_rule",
        "prashna_html_shells",
    ]
    prashna = payload["rules"][1]
    assert prashna["action_parameters"]["cache"] is True
    assert "prashna.sankara.net" in prashna["expression"]
