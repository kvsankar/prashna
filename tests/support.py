"""Values shared by the API, UI, and ops test trees."""
from __future__ import annotations

# Tests run the server with PRASHNA_SETUP_TOKEN set to this value (see
# tests/conftest.py), so first-admin setup is deterministic (UC-A-01).
SETUP_TOKEN = "test-setup-token"


def ws_receive(ws, timeout: float = 5.0):
    """Receive one JSON text frame from a TestClient WebSocket, or fail after
    `timeout` seconds. `receive_text()` waits forever, so a missing broadcast
    would hang the suite (and the pre-push hook and CI) instead of failing.
    A close frame raises `WebSocketDisconnect`, as `receive_text()` does."""
    import json

    import anyio

    async def _receive():
        with anyio.fail_after(timeout):
            return await ws._send_rx.receive()

    message = ws.portal.call(_receive)
    ws._raise_on_close(message)
    return json.loads(message["text"])
