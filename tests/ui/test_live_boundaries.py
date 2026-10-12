"""UI-suite live-server boundary tests."""
from __future__ import annotations

import secrets

import pytest
from playwright.sync_api import expect
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from ._helpers import admin_login_via_ui, api_login, api_make_session


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


def test_uc_x_02_unknown_session_closes_with_4404(base_url, admin_setup):
    """UC-X-02: against the real server, an unknown code reaches the client as
    close code 4404, not as a refused handshake (which a browser sees as 1006)."""
    ws_url = base_url.replace("http://", "ws://", 1) + "/ws/sessions/NOSUCH"
    with pytest.raises(ConnectionClosed) as closed:
        with connect(ws_url, origin=None) as ws:
            ws.recv(timeout=5)
    assert closed.value.rcvd is not None
    assert closed.value.rcvd.code == 4404


def _count_sockets(page) -> list[str]:
    opened: list[str] = []
    page.on("websocket", lambda ws: opened.append(ws.url))
    return opened


def test_uc_x_01_session_deleted_shows_final_state(base_url, admin_setup, context):
    """UC-X-01: deleting the session puts the participant, moderator and
    projector pages in a final "deleted" state, and none reconnects."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-X01del {secrets.token_hex(3)}")
    code = s["code"]
    pages = {role: context.new_page() for role in ("s", "m", "p")}
    sockets = {role: _count_sockets(pg) for role, pg in pages.items()}
    try:
        admin_login_via_ui(pages["m"], base_url)
        for role, pg in pages.items():
            pg.goto(f"{base_url}/{role}/{code}")
            pg.wait_for_function(
                "performance.getEntriesByName('prashna-usable').length > 0", timeout=5000)
        for role in pages:
            assert len(sockets[role]) == 1, (role, sockets[role])

        c.request("DELETE", f"/api/sessions/{code}", json={}).raise_for_status()

        for pg in pages.values():
            banner = pg.locator("#session-deleted")
            expect(banner).to_be_visible(timeout=5000)
            expect(banner).to_have_text("This session was deleted.")
        pages["s"].wait_for_timeout(2500)  # longer than the first reconnect delay
        for role in pages:
            assert len(sockets[role]) == 1, (role, sockets[role])
    finally:
        c.close()


def test_uc_x_02_page_stops_reconnecting_after_4404(base_url, admin_setup, page):
    """UC-X-02: a session deleted while the page was offline closes the
    reconnect with 4404; the page shows the final state and stops."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-X02del {secrets.token_hex(3)}")
    sockets = _count_sockets(page)
    try:
        page.add_init_script("localStorage.setItem('prashna:socket-close-hook', '1')")
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_function("window.__prashnaLiveSocketTest?.activeCount() === 1", timeout=5000)
        page.evaluate("window.__prashnaLiveSocketTest.closeActive()")
        page.wait_for_function("window.__prashnaLiveSocketTest.activeCount() === 0", timeout=5000)
        c.request("DELETE", f"/api/sessions/{s['code']}", json={}).raise_for_status()

        expect(page.locator("#session-deleted")).to_be_visible(timeout=5000)
        page.wait_for_timeout(2500)
        assert len(sockets) == 2, sockets
    finally:
        c.close()
