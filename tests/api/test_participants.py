"""UC-P-01, UC-P-02, UC-P-03, UC-P-11, UC-M-10: session lookup, participants, presence."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient


# ---------- UC-P-01: Join by code ----------

def test_uc_p_01_get_session_ok(client, make_session):
    """UC-P-01: GET /api/sessions/{code} for existing → 200 with public fields."""
    s = make_session("Hi")
    r = client.get(f"/api/sessions/{s['code']}")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == s["code"]
    assert body["title"] == "Hi"
    assert body["status"] == "planning"
    assert "created_at" in body
    assert "participant_base_url" in body


def test_uc_p_01_get_unknown_404(client):
    """UC-P-01: unknown code → 404."""
    r = client.get("/api/sessions/NOPE99")
    assert r.status_code == 404
    assert r.json() == {"detail": "Session not found"}


def test_uc_p_01_participant_page_ok(client, make_session, app_module):
    """UC-P-01: /s/{code} serves participant.html for valid code."""
    s = make_session()
    with TestClient(app_module.app, follow_redirects=False) as c:
        r = c.get(f"/s/{s['code']}")
    assert r.status_code == 200


def test_uc_p_01_participant_page_bad_code_redirect(app_module):
    """UC-P-01: unknown code → 303 redirect."""
    with TestClient(app_module.app, follow_redirects=False) as c:
        r = c.get("/s/NOPE99")
    assert r.status_code == 303
    assert r.headers["location"] == "/?bad_code=NOPE99"


# ---------- UC-P-02: Anonymous identity per session ----------

def test_uc_p_02_me_issues_cookie(client, admin_client, make_session):
    """UC-P-02: GET /me with no cookie issues voter_token."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.get(f"/api/sessions/{s['code']}/me")
    assert r.status_code == 200
    body = r.json()
    assert "id" in body
    assert body["name"] is None
    assert "voter_token" in client.cookies


def test_uc_p_02_second_call_reuses(client, admin_client, make_session):
    """UC-P-02: second call reuses the same Participant row."""
    s = make_session()
    admin_client.cookies.clear()
    r1 = client.get(f"/api/sessions/{s['code']}/me")
    r2 = client.get(f"/api/sessions/{s['code']}/me")
    assert r1.json()["id"] == r2.json()["id"]


def test_uc_p_02_distinct_cookies_distinct_participants(admin_client, make_session, app_module):
    """UC-P-02: two distinct voter_token cookies → two distinct Participants."""
    s = make_session()
    with TestClient(app_module.app) as c1, TestClient(app_module.app) as c2:
        r1 = c1.get(f"/api/sessions/{s['code']}/me").json()
        r2 = c2.get(f"/api/sessions/{s['code']}/me").json()
    assert r1["id"] != r2["id"]


def test_uc_p_02_last_seen_throttle(client, admin_client, make_session):
    """UC-P-02: two calls within 5s → last_seen_at advances only once."""
    s = make_session()
    admin_client.cookies.clear()
    client.get(f"/api/sessions/{s['code']}/me")  # creates row
    from app.db import SessionLocal
    from app import models as m
    with SessionLocal() as db:
        p = db.query(m.Participant).filter_by(session_id=db.query(m.Session)
                                              .filter_by(code=s["code"]).one().id).one()
        before = p.last_seen_at
    client.get(f"/api/sessions/{s['code']}/me")
    with SessionLocal() as db:
        p = db.query(m.Participant).filter_by(session_id=db.query(m.Session)
                                              .filter_by(code=s["code"]).one().id).one()
        after = p.last_seen_at
    assert before == after  # throttled, unchanged


def test_uc_p_02_last_seen_advances_after_window(client, admin_client, make_session, monkeypatch):
    """UC-P-02: a call > 5s later updates last_seen_at."""
    s = make_session()
    admin_client.cookies.clear()
    client.get(f"/api/sessions/{s['code']}/me")
    from app.db import SessionLocal
    from app import models as m
    from datetime import datetime, timedelta
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        p = db.query(m.Participant).filter_by(session_id=sess.id).one()
        p.last_seen_at = datetime.utcnow() - timedelta(seconds=10)
        db.commit()
        before = p.last_seen_at
    client.get(f"/api/sessions/{s['code']}/me")
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        p = db.query(m.Participant).filter_by(session_id=sess.id).one()
        after = p.last_seen_at
    assert after > before


# ---------- UC-P-03: Set display name ----------

def test_uc_p_03_set_name(client, admin_client, make_session):
    """UC-P-03: PATCH /me sets name."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.patch(f"/api/sessions/{s['code']}/me", json={"name": "Alice"})
    assert r.status_code == 200
    assert r.json()["name"] == "Alice"


def test_uc_p_03_blank_name_null(client, admin_client, make_session):
    """UC-P-03: blank name → null (anonymous)."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.patch(f"/api/sessions/{s['code']}/me", json={"name": ""})
    assert r.status_code == 200
    assert r.json()["name"] is None


def test_uc_p_03_name_truncated_80(client, admin_client, make_session):
    """UC-P-03: name > 80 chars → truncated to 80."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.patch(f"/api/sessions/{s['code']}/me",
                     json={"name": "x" * 200})
    assert r.status_code == 200
    assert len(r.json()["name"]) == 80


def test_uc_p_03_broadcasts(client, admin_client, make_session):
    """UC-P-03: PATCH /me broadcasts {type: participant}."""
    import json
    s = make_session()
    admin_client.cookies.clear()
    with client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        client.patch(f"/api/sessions/{s['code']}/me", json={"name": "Alice"})
        msg = json.loads(ws.receive_text())
        assert msg == {"type": "participant"}


# ---------- UC-P-11: Ended session is read-only ----------

def test_uc_p_11_ask_after_end_400(client, admin_client, make_session):
    """UC-P-11: ask on ended → 400."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/end")
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries", json={"text": "Q?"})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session has ended"}


def test_uc_p_11_vote_after_end_400(client, admin_client, make_session):
    """UC-P-11: vote on ended → 400."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    admin_client.post(f"/api/sessions/{s['code']}/end")
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote")
    assert r.status_code == 400
    assert r.json() == {"detail": "Session has ended"}


def test_uc_p_11_submit_after_end_400(admin_client, make_quiz, make_session):
    """UC-P-11: submit on ended → 400."""
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    g = admin_client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    qid = g["current_question"]["id"]
    aid = g["current_question"]["answers"][0]["id"]
    admin_client.post(f"/api/sessions/{s['code']}/end")
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                          json={"question_id": qid, "answer_ids": [aid]})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session has ended"}


def test_uc_p_11_get_queries_still_works(client, admin_client, make_session):
    """UC-P-11: GET queries still returns existing list after end."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": "Q?"})
    admin_client.post(f"/api/sessions/{s['code']}/end")
    admin_client.cookies.clear()
    r = client.get(f"/api/sessions/{s['code']}/queries")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ---------- UC-M-10: Live participant count ----------

def test_uc_m_10_presence_empty(client, admin_client, make_session):
    """UC-M-10: presence with no other activity returns ≥ 0; the call itself counts."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.get(f"/api/sessions/{s['code']}/presence")
    assert r.status_code == 200
    body = r.json()
    assert "online" in body
    # the call itself creates / refreshes a participant within window
    assert body["online"] >= 1


def test_uc_m_10_presence_after_participant_activity(client, admin_client, make_session, app_module):
    """UC-M-10: after a participant call, online ≥ 1."""
    s = make_session()
    with TestClient(app_module.app) as c:
        c.get(f"/api/sessions/{s['code']}/me")
    # different client polls
    with TestClient(app_module.app) as c2:
        r = c2.get(f"/api/sessions/{s['code']}/presence")
    assert r.json()["online"] >= 1


def test_uc_m_10_presence_expires_after_30s(client, admin_client, make_session, app_module):
    """UC-M-10: after >30s of inactivity, online decrements."""
    from datetime import datetime, timedelta
    s = make_session()
    with TestClient(app_module.app) as c:
        c.get(f"/api/sessions/{s['code']}/me")
    # backdate last_seen for that participant
    from app.db import SessionLocal
    from app import models as m
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        for p in db.query(m.Participant).filter_by(session_id=sess.id).all():
            p.last_seen_at = datetime.utcnow() - timedelta(seconds=60)
        db.commit()
    # use a fresh client so this presence call doesn't create another within-window participant
    with TestClient(app_module.app) as c2:
        # the call itself will create a participant for c2, so account for that
        r = c2.get(f"/api/sessions/{s['code']}/presence")
    # the new participant from c2 is fresh; backdated one is excluded.
    assert r.json()["online"] == 1
