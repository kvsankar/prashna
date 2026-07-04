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
