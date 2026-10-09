"""UC-P-13 / UC-M-12: session feedback (participant star rating + comments,
host-visible aggregate)."""
from __future__ import annotations

import json


def _ws_recv_types(ws, n=1):
    return [json.loads(ws.receive_text()) for _ in range(n)]


def _enable_feedback(admin_client, code: str) -> None:
    r = admin_client.post(
        f"/api/sessions/{code}/feedback_enabled",
        json={"enabled": True},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"feedback_enabled": True}


# ---------- UC-P-13: submit feedback ----------

def test_uc_p_13_feedback_disabled_by_default(
    client,
    admin_client,
    make_session,
):
    """A participant cannot submit feedback until a moderator opens rating."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 4})
    assert r.status_code == 403
    assert r.json() == {"detail": "feedback is not enabled"}


def test_uc_m_12_feedback_toggle_by_moderator(
    client,
    admin_client,
    make_session,
    mod_headers,
):
    """A moderator can open and close participant ratings."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(
        f"/api/sessions/{s['code']}/feedback_enabled",
        headers=mod_headers(s["mod_key"]),
        json={"enabled": True},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"feedback_enabled": True}

    r = client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 4})
    assert r.status_code == 200, r.text

    r = client.post(
        f"/api/sessions/{s['code']}/feedback_enabled",
        headers=mod_headers(s["mod_key"]),
        json={"enabled": False},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"feedback_enabled": False}
    assert client.post(
        f"/api/sessions/{s['code']}/feedback",
        json={"rating": 5},
    ).status_code == 403


def test_uc_m_12_feedback_toggle_broadcasts_feedback_state(
    admin_client,
    make_session,
):
    """Opening rating notifies connected participants through feedback_state."""
    s = make_session()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        _enable_feedback(admin_client, s["code"])
        assert _ws_recv_types(ws) == [{"type": "feedback_state"}]


def test_uc_p_13_submit_feedback(client, admin_client, make_session):
    """A participant submits a rating + comments → 200 echoing the row."""
    s = make_session()
    _enable_feedback(admin_client, s["code"])
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/feedback",
                    json={"rating": 4, "went_well": "Clear pace", "to_improve": "More demos"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rating"] == 4
    assert body["went_well"] == "Clear pace"
    assert body["to_improve"] == "More demos"
    assert body["updated_at"]


def test_uc_p_13_rating_only(client, admin_client, make_session):
    """Comments are optional — a bare rating is accepted."""
    s = make_session()
    _enable_feedback(admin_client, s["code"])
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["rating"] == 5
    assert body["went_well"] is None
    assert body["to_improve"] is None


def test_uc_p_13_allowed_when_ended(client, admin_client, make_session):
    """Feedback can be opened after a session has ended."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/start")
    admin_client.post(f"/api/sessions/{s['code']}/end")
    _enable_feedback(admin_client, s["code"])
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 3})
    assert r.status_code == 200


def test_uc_p_13_upsert_one_per_participant(client, admin_client, make_session):
    """Resubmitting updates the same row rather than creating a second."""
    s = make_session()
    _enable_feedback(admin_client, s["code"])
    admin_client.cookies.clear()
    client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 2, "went_well": "ok"})
    r = client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 5, "went_well": "great"})
    assert r.status_code == 200
    assert r.json()["rating"] == 5
    # Summary (as owner) shows exactly one response.
    admin_client.post("/api/admin/login", json={"username": "admin", "password": "testpass1"})
    sumr = admin_client.get(f"/api/sessions/{s['code']}/feedback/summary").json()
    assert sumr["count"] == 1
    assert sumr["average"] == 5
    assert sumr["items"][0]["went_well"] == "great"


def test_uc_p_13_every_submission_is_versioned(client, admin_client, make_session):
    """Resubmitting appends a history row each time, while the current view
    stays one row per participant."""
    from sqlalchemy import func
    from sqlalchemy import select as _select

    from prashna import db as _db
    from prashna import models as _m

    s = make_session()
    _enable_feedback(admin_client, s["code"])
    admin_client.cookies.clear()
    for rating in (3, 4, 5):
        client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": rating})
    with _db.SessionLocal() as dbs:
        versions = dbs.scalar(_select(func.count()).select_from(_m.SessionFeedbackVersion))
        current = dbs.scalar(_select(func.count()).select_from(_m.SessionFeedback))
    assert versions == 3   # full history retained
    assert current == 1    # one current row per participant


def test_uc_p_13_rating_out_of_range_400(client, admin_client, make_session):
    s = make_session()
    _enable_feedback(admin_client, s["code"])
    admin_client.cookies.clear()
    for bad in (0, 6, -1):
        r = client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": bad})
        assert r.status_code == 400, bad
        assert r.json()["detail"] == "rating must be an integer from 1 to 5"


def test_uc_p_13_rating_missing_or_non_int_400(client, admin_client, make_session):
    s = make_session()
    _enable_feedback(admin_client, s["code"])
    admin_client.cookies.clear()
    for bad in ({}, {"rating": "4"}, {"rating": 4.5}, {"rating": True}):
        r = client.post(f"/api/sessions/{s['code']}/feedback", json=bad)
        assert r.status_code == 400, bad


def test_uc_p_13_delete_retracts_feedback(client, admin_client, make_session, mod_headers):
    """DELETE retracts the caller's current feedback; mine→null, summary
    count drops, but version history is retained."""
    from sqlalchemy import func
    from sqlalchemy import select as _select

    from prashna import db as _db
    from prashna import models as _m

    s = make_session()
    _enable_feedback(admin_client, s["code"])
    admin_client.cookies.clear()
    client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 4, "went_well": "x"})
    assert client.get(f"/api/sessions/{s['code']}/feedback/mine").json()["rating"] == 4
    r = client.delete(f"/api/sessions/{s['code']}/feedback")
    assert r.status_code == 200
    assert client.get(f"/api/sessions/{s['code']}/feedback/mine").json() is None
    summary = client.get(f"/api/sessions/{s['code']}/feedback/summary",
                         headers=mod_headers(s["mod_key"])).json()
    assert summary["count"] == 0
    with _db.SessionLocal() as dbs:
        versions = dbs.scalar(_select(func.count()).select_from(_m.SessionFeedbackVersion))
    assert versions == 1  # history kept


def test_uc_p_13_mine_null_then_value(client, admin_client, make_session):
    """GET .../feedback/mine is null before submitting, then echoes the row."""
    s = make_session()
    _enable_feedback(admin_client, s["code"])
    admin_client.cookies.clear()
    assert client.get(f"/api/sessions/{s['code']}/feedback/mine").json() is None
    client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 4})
    mine = client.get(f"/api/sessions/{s['code']}/feedback/mine").json()
    assert mine["rating"] == 4


# ---------- UC-M-12: host-visible summary ----------

def test_uc_m_12_summary_aggregates(client, admin_client, make_session, mod_headers):
    """Summary returns count, average, distribution, and per-response items."""
    s = make_session()
    _enable_feedback(admin_client, s["code"])
    # Two distinct participants (separate cookie jars via clear between).
    admin_client.cookies.clear()
    client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 5, "went_well": "A"})
    client.cookies.clear()
    client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 3, "to_improve": "B"})
    r = client.get(f"/api/sessions/{s['code']}/feedback/summary",
                   headers=mod_headers(s["mod_key"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    assert body["average"] == 4.0
    assert body["distribution"]["5"] == 1
    assert body["distribution"]["3"] == 1
    assert len(body["items"]) == 2


def test_uc_m_12_summary_requires_mod_or_owner(client, admin_client, make_session):
    """No admin cookie and no mod key → 403."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.get(f"/api/sessions/{s['code']}/feedback/summary")
    assert r.status_code == 403


def test_uc_m_12_summary_owner_cookie(admin_client, make_session):
    """Admin owner reaches the summary via cookie (no mod key needed)."""
    s = make_session()
    r = admin_client.get(f"/api/sessions/{s['code']}/feedback/summary")
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_uc_m_12_summary_includes_author_name(client, admin_client, make_session, mod_headers):
    """A named participant's feedback carries author_name in the summary."""
    s = make_session()
    _enable_feedback(admin_client, s["code"])
    admin_client.cookies.clear()
    client.patch(f"/api/sessions/{s['code']}/me", json={"name": "Dana"})
    client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 4, "went_well": "ok"})
    body = client.get(f"/api/sessions/{s['code']}/feedback/summary",
                      headers=mod_headers(s["mod_key"])).json()
    assert body["items"][0]["author_name"] == "Dana"


# ---------- UC-X-01: broadcast ----------

def test_uc_x_01_feedback_broadcast(client, admin_client, make_session):
    """Submitting feedback broadcasts {type: 'feedback'}."""
    s = make_session()
    _enable_feedback(admin_client, s["code"])
    admin_client.cookies.clear()
    with client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 5})
        assert _ws_recv_types(ws) == [{"type": "feedback"}]
