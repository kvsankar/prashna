"""UI-suite live-server boundary tests."""
from __future__ import annotations

import secrets

from websockets.sync.client import connect

from ._helpers import api_login, api_make_session


def test_websocket_accepts_no_origin(base_url, admin_setup):
    """UC-X-02: websocket connection without Origin is accepted."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-X02 {secrets.token_hex(3)}")
    ws_url = base_url.replace("http://", "ws://", 1) + f"/ws/sessions/{s['code']}"
    try:
        with connect(ws_url, origin=None) as ws:
            ws.send("ping")
    finally:
        c.close()
