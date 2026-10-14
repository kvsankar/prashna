"""UC-M-01, UC-M-02: moderator auth gates + session lifecycle."""
from __future__ import annotations

from fastapi.testclient import TestClient

from ..support import ws_receive

# ---------- UC-M-01: Auth gates on mod-or-owner routes ----------

def test_uc_m_01_mod_key_header_ok(client, admin_client, make_session, mod_headers):
    """UC-M-01: valid X-Mod-Key on a mod-or-owner route → 200.

    Tested via POST /start (mod-or-owner). PATCH session is now
    owner-only and would 401 here.
    """
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/start",
                    headers=mod_headers(s["mod_key"]))
    assert r.status_code == 200


def test_uc_m_01_admin_owner_cookie_ok(admin_client, make_session):
    """UC-M-01: admin cookie, no mod_key → 200."""
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/start")
    assert r.status_code == 200


def test_uc_m_01_no_auth_403(client, admin_client, make_session):
    """UC-M-01: no auth + no mod_key on a mod-or-owner route → 403."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/start")
    assert r.status_code == 403
    assert r.json() == {"detail": "Not authorized — moderator key or admin login required"}


def test_uc_m_01_wrong_mod_key_403(client, admin_client, make_session, mod_headers):
    """UC-M-01: wrong mod_key + no admin cookie → 403."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/start",
                    headers=mod_headers("badbadbadbadbadx"))
    assert r.status_code == 403


def test_uc_m_01_patch_session_is_owner_only(client, admin_client, make_session, mod_headers):
    """Mod-key cannot rename a session — owner-only after the audit fix."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.patch(f"/api/sessions/{s['code']}",
                     json={"title": "delegate-tried"},
                     headers=mod_headers(s["mod_key"]))
    # No admin cookie → 401 from auth.current_admin.
    assert r.status_code == 401


def test_uc_a_08_owner_changes_the_moderator_key(client, admin_client, make_session, mod_headers, caplog):
    """UC-A-08: the owner changes the moderator key; the old key stops
    working at once, the new one works, open pages get a hint, and the key
    is never logged."""
    import logging

    caplog.set_level(logging.INFO, logger="prashna")
    s = make_session()
    old_key = s["mod_key"]
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        r = admin_client.post(f"/api/sessions/{s['code']}/mod_key")
        assert r.status_code == 200, r.text
        assert ws_receive(ws) == {"type": "moderator_key"}
    new_key = r.json()["mod_key"]
    assert new_key and new_key != old_key
    assert len(new_key) == len(old_key)
    listed = {row["code"]: row["mod_key"] for row in admin_client.get("/api/sessions").json()}
    assert listed[s["code"]] == new_key

    admin_client.cookies.clear()
    refused = client.get(f"/api/sessions/{s['code']}/moderator-bootstrap", headers=mod_headers(old_key))
    assert refused.status_code == 403
    assert refused.json() == {"detail": "Not authorized — moderator key or admin login required"}
    assert client.post(f"/api/sessions/{s['code']}/start", headers=mod_headers(old_key)).status_code == 403
    assert client.get(f"/api/sessions/{s['code']}/moderator-bootstrap",
                      headers=mod_headers(new_key)).status_code == 200

    log_text = "\n".join(f"{rec.getMessage()} {rec.__dict__}" for rec in caplog.records)
    assert old_key not in log_text
    assert new_key not in log_text


def test_uc_a_08_change_moderator_key_is_owner_only(client, admin_client, make_session, mod_headers):
    """UC-A-08: changing the moderator key needs the owner's admin cookie:
    a delegate's key alone gets 401, another admin gets 403 "Not your
    session", and the key stays the same."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/mod_key")
    assert r.status_code == 401
    assert r.json() == {"detail": "Not authenticated"}
    r = client.post(f"/api/sessions/{s['code']}/mod_key", headers=mod_headers(s["mod_key"]))
    assert r.status_code == 401
    assert r.json() == {"detail": "Not authenticated"}

    from prashna import auth
    from prashna import models as m
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="other", password_hash=auth.hash_password("longenough"))
        db.add(other)
        db.commit()
        db.refresh(other)
        db.query(m.Session).filter_by(code=s["code"]).one().owner_user_id = other.id
        db.commit()
    client.post("/api/admin/login", json={"username": "admin", "password": "testpass1"}).raise_for_status()  # pragma: allowlist secret
    r = client.post(f"/api/sessions/{s['code']}/mod_key")
    assert r.status_code == 403
    assert r.json() == {"detail": "Not your session"}
    client.cookies.clear()
    assert client.get(f"/api/sessions/{s['code']}/moderator-bootstrap",
                      headers=mod_headers(s["mod_key"])).status_code == 200


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
    g = admin_client.get(f"/api/sessions/{s['code']}").json()
    assert g["status"] == "ended"
    assert g["ended_at"] is not None


def test_uc_m_02_end_with_live_run_400(admin_client, make_quiz, make_session):
    """UC-M-02: ending is refused while a quiz run is live; the session stays live."""
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    r = admin_client.post(f"/api/sessions/{s['code']}/end")
    assert r.status_code == 400
    assert r.json() == {"detail": "A quiz run is currently live — close it before ending the session"}
    g = admin_client.get(f"/api/sessions/{s['code']}").json()
    assert g["status"] == "live"
    assert g["ended_at"] is None


def test_uc_m_02_end_planning_allowed(admin_client, make_session):
    """UC-M-02: end on planning → 200 ended (no requirement to go live first)."""
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/end")
    assert r.status_code == 200
    assert r.json() == {"status": "ended"}


def test_uc_m_02_end_with_queued_quiz_400(admin_client, make_quiz, make_session):
    """UC-M-02: queued runs must be removed before the session can end."""
    q = make_quiz()
    s = make_session()
    admin_client.post(
        f"/api/sessions/{s['code']}/quiz_runs",
        json={"quiz_id": q["id"]},
    )
    r = admin_client.post(f"/api/sessions/{s['code']}/end")
    assert r.status_code == 400
    assert r.json() == {"detail": "Remove queued quizzes before ending the session"}
    assert admin_client.get(f"/api/sessions/{s['code']}").json()["status"] == "planning"


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
        msg = ws_receive(ws)
        assert msg == {"type": "session_state"}


def test_uc_m_02_end_broadcasts(admin_client, make_session):
    """UC-M-02: end broadcasts session_state."""
    s = make_session()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.post(f"/api/sessions/{s['code']}/end")
        msg = ws_receive(ws)
        assert msg == {"type": "session_state"}


def test_uc_m_02_no_auth_403(client, admin_client, make_session):
    """UC-M-02: no auth on start → 403."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/start")
    assert r.status_code == 403
