"""Static frontend contracts that are hard to exercise in browser tests."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_live_clients_drop_stale_refresh_responses():
    """Live clients should gate async paints so older responses cannot win."""
    for rel in (
        "frontend/src/moderator.ts",
        "frontend/src/participant.ts",
        "frontend/src/projector.ts",
    ):
        src = (ROOT / rel).read_text()
        assert "latest" in src.lower(), rel
        assert "seq" in src.lower(), rel
        assert "!== " in src or "!== latest" in src, rel


def test_live_socket_reconnect_test_hook_is_gated():
    """Reconnect UI tests need a gated hook to close the active socket."""
    src = (ROOT / "frontend/src/common.ts").read_text()

    assert 'import.meta.env.MODE === "test"' in src
    assert "prashna:socket-close-hook" in src
    assert "localStorage.getItem" in src
    assert "__prashnaLiveSocketTest" in src
    assert "closeActive" in src
    assert "activeCount" in src


def test_role_pages_use_single_bootstrap_requests_and_usable_marks():
    sources = {
        "participant": "participant-bootstrap",
        "moderator": "moderator-bootstrap",
        "projector": "display-bootstrap",
    }
    for role, endpoint in sources.items():
        src = (ROOT / f"frontend/src/{role}.ts").read_text()
        assert endpoint in src, role
        assert f'markUsable("{role}")' in src, role

    common = (ROOT / "frontend/src/common.ts").read_text()
    assert 'performance.mark("prashna-usable")' in common
    assert 'navigator.sendBeacon("/api/diagnostics/performance"' in common


def test_landing_shell_is_visible_before_auth_reconciliation():
    html = (ROOT / "frontend/index.html").read_text()
    assert 'id="join-card" style="display:none;"' not in html
    assert 'id="login-card" style="display:none;"' not in html

    src = (ROOT / "frontend/src/index.ts").read_text()
    assert 'markUsable("landing")' in src
