"""UC-M-01, UC-M-02: moderator auth gates + session lifecycle."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient


# ---------- UC-M-01: Auth gates on mod-or-owner routes ----------

def test_uc_m_01_mod_key_header_ok(client, admin_client, make_session, mod_headers):
    """UC-M-01: valid X-Mod-Key → 200."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.patch(f"/api/sessions/{s['code']}",
                     json={"title": "x"},
                     headers=mod_headers(s["mod_key"]))
    assert r.status_code == 200


def test_uc_m_01_admin_owner_cookie_ok(admin_client, make_session):
    """UC-M-01: admin cookie, no mod_key → 200."""
    s = make_session()
    r = admin_client.patch(f"/api/sessions/{s['code']}", json={"title": "x"})
    assert r.status_code == 200


def test_uc_m_01_no_auth_403(client, admin_client, make_session):
    """UC-M-01: no auth + no mod_key → 403."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.patch(f"/api/sessions/{s['code']}", json={"title": "x"})
    assert r.status_code == 403
    assert r.json() == {"detail": "Not authorized — moderator key or admin login required"}


def test_uc_m_01_wrong_mod_key_403(client, admin_client, make_session, mod_headers):
    """UC-M-01: wrong mod_key + no admin cookie → 403."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.patch(f"/api/sessions/{s['code']}",
                     json={"title": "x"},
                     headers=mod_headers("badbadbadbadbadx"))
    assert r.status_code == 403


def test_uc_m_01_unknown_code_redirects(make_session, app_module):
    """UC-M-01: GET /m/<unknown> → 303 to /?bad_code=..."""
    with TestClient(app_module.app, follow_redirects=False) as c:
        r = c.get("/m/NOPE99")
    assert r.status_code == 303
    assert r.headers["location"] == "/?bad_code=NOPE99"


# ---------- UC-M-02: Session lifecycle ----------

def test_uc_m_02_start_planning(admin_client, make_session):
    """UC-M-02: start planning → live with started_at."""
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/start")
    assert r.status_code == 200
    assert r.json() == {"status": "live"}
    # started_at set
    info = admin_client.get("/api/sessions").json()
    row = [x for x in info if x["code"] == s["code"]][0]
    assert row["started_at"] is not None


def test_uc_m_02_start_live_idempotent(admin_client, make_session):
    """UC-M-02: start on live → 200 live (no changes)."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/start")
    r = admin_client.post(f"/api/sessions/{s['code']}/start")
    assert r.status_code == 200
    assert r.json() == {"status": "live"}


def test_uc_m_02_start_ended_400(admin_client, make_session):
    """UC-M-02: start on ended → 400."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/end")
    r = admin_client.post(f"/api/sessions/{s['code']}/start")
    assert r.status_code == 400
    assert r.json() == {"detail": "Session has ended"}


def test_uc_m_02_end_live(admin_client, make_session):
    """UC-M-02: end live → ended with ended_at."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/start")
    r = admin_client.post(f"/api/sessions/{s['code']}/end")
    assert r.status_code == 200
    assert r.json() == {"status": "ended"}


def test_uc_m_02_end_planning_allowed(admin_client, make_session):
    """UC-M-02: end on planning → 200 ended (no requirement to go live first)."""
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/end")
    assert r.status_code == 200
    assert r.json() == {"status": "ended"}


def test_uc_m_02_end_ended_noop(admin_client, make_session):
    """UC-M-02: end on ended → 200 ended (no-op)."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/end")
    r = admin_client.post(f"/api/sessions/{s['code']}/end")
    assert r.status_code == 200
    assert r.json() == {"status": "ended"}


def test_uc_m_02_start_broadcasts(admin_client, make_session):
    """UC-M-02: start broadcasts session_state."""
    s = make_session()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.post(f"/api/sessions/{s['code']}/start")
        msg = json.loads(ws.receive_text())
        assert msg == {"type": "session_state"}


def test_uc_m_02_end_broadcasts(admin_client, make_session):
    """UC-M-02: end broadcasts session_state."""
    s = make_session()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.post(f"/api/sessions/{s['code']}/end")
        msg = json.loads(ws.receive_text())
        assert msg == {"type": "session_state"}


def test_uc_m_02_no_auth_403(client, admin_client, make_session):
    """UC-M-02: no auth on start → 403."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/start")
    assert r.status_code == 403
