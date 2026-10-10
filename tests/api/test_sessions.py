"""UC-A-03 through UC-A-08: session CRUD and lifecycle."""
from __future__ import annotations

import json

# ---------- UC-A-03: Create a session ----------

def test_uc_a_03_create_session_ok(admin_client):
    """UC-A-03: create with non-empty title."""
    r = admin_client.post("/api/sessions", json={"title": "Test"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Test"
    assert body["status"] == "planning"
    assert body["feedback_enabled"] is False
    assert len(body["code"]) == 6
    assert len(body["mod_key"]) == 16


def test_uc_a_03_empty_title_400(admin_client):
    """UC-A-03: empty title → 400."""
    r = admin_client.post("/api/sessions", json={"title": ""})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session title is required"}


def test_uc_a_03_whitespace_title_400(admin_client):
    """UC-A-03: whitespace-only title → 400."""
    r = admin_client.post("/api/sessions", json={"title": "   "})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session title is required"}


def test_uc_a_03_too_long_title_400(admin_client):
    """UC-A-03: title > 200 chars → 400."""
    r = admin_client.post("/api/sessions", json={"title": "a" * 201})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session title is too long (max 200 chars)"}


def test_uc_a_03_no_admin_cookie_401(client):
    """UC-A-03: no admin cookie → 401."""
    r = client.post("/api/sessions", json={"title": "x"})
    assert r.status_code == 401


def test_uc_a_03_two_creates_distinct_codes(admin_client):
    """UC-A-03: two consecutive creates → distinct codes."""
    r1 = admin_client.post("/api/sessions", json={"title": "A"})
    r2 = admin_client.post("/api/sessions", json={"title": "B"})
    assert r1.json()["code"] != r2.json()["code"]


# ---------- UC-A-04: List sessions ----------

def test_uc_a_04_list_sessions(admin_client, make_session):
    """UC-A-04: list returns owned sessions with expected shape."""
    s = make_session("hello")
    r = admin_client.get("/api/sessions")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    for k in ("code", "title", "status", "mod_key", "participant_base_url",
              "feedback_enabled", "created_at", "started_at", "ended_at",
              "query_count", "quiz_run_count"):
        assert k in row
    assert row["code"] == s["code"]


def test_uc_a_04_aggregate_counts_are_correct(
    admin_client, make_quiz, make_session
):
    """Session counts come from SQL aggregates without lazy-loading every child."""
    s = make_session("with activity")
    q = make_quiz()
    admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": "one"})
    admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": "two"})
    admin_client.post(
        f"/api/sessions/{s['code']}/quiz_runs",
        json={"quiz_id": q["id"]},
    )

    rows = admin_client.get("/api/sessions").json()
    row = next(item for item in rows if item["code"] == s["code"])
    assert row["query_count"] == 2
    assert row["quiz_run_count"] == 1


def test_uc_a_04_only_my_sessions(client, admin_client, make_session):
    """UC-A-04: only sessions owned by me."""
    make_session("mine")
    # create a second admin via DB to simulate other owner
    from prashna import auth
    from prashna import models as m
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="other", password_hash=auth.hash_password("longenough"))
        db.add(other)
        db.commit()
        db.refresh(other)
        s2 = m.Session(code="ZZZZZZ", title="not mine", mod_key="x" * 16, owner_user_id=other.id)
        db.add(s2)
        db.commit()
    r = admin_client.get("/api/sessions")
    titles = [row["title"] for row in r.json()]
    assert "mine" in titles
    assert "not mine" not in titles


def test_uc_a_04_order_desc(admin_client, make_session):
    """UC-A-04: order is created_at desc."""
    s1 = make_session("first")
    s2 = make_session("second")
    rows = admin_client.get("/api/sessions").json()
    assert rows[0]["code"] == s2["code"]
    assert rows[1]["code"] == s1["code"]


def test_uc_a_04_no_auth_401(client):
    """UC-A-04: no auth → 401."""
    r = client.get("/api/sessions")
    assert r.status_code == 401


# ---------- UC-A-05: Edit session title ----------

def test_uc_a_05_patch_title_ok(admin_client, make_session):
    """UC-A-05: PATCH title → 200."""
    s = make_session("orig")
    r = admin_client.patch(f"/api/sessions/{s['code']}", json={"title": "New"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == s["code"]
    assert body["title"] == "New"
    assert body["status"] == "planning"


def test_uc_a_05_empty_title_400(admin_client, make_session):
    """UC-A-05: empty title → 400."""
    s = make_session()
    r = admin_client.patch(f"/api/sessions/{s['code']}", json={"title": ""})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session title is required"}


def test_uc_a_05_too_long_title_400(admin_client, make_session):
    """UC-A-05: title > 200 chars → 400."""
    s = make_session()
    r = admin_client.patch(f"/api/sessions/{s['code']}", json={"title": "a" * 201})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session title is too long (max 200 chars)"}


def test_uc_a_05_no_auth_401(client, admin_client, make_session):
    """UC-A-05: PATCH session is owner-only → 401 with no cookie.

    The session metadata routes (title, base URL) were tightened to
    require admin owner cookie; the delegated-moderator path was
    removed because a delegate shouldn't rename someone else's session.
    """
    s = make_session()
    admin_client.cookies.clear()
    r = client.patch(f"/api/sessions/{s['code']}", json={"title": "X"})
    assert r.status_code == 401
    assert r.json() == {"detail": "Not authenticated"}


def test_uc_a_05_broadcasts_session_state(admin_client, make_session):
    """UC-A-05: PATCH broadcasts {type: session_state}."""
    s = make_session()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.patch(f"/api/sessions/{s['code']}", json={"title": "New"})
        msg = json.loads(ws.receive_text())
        assert msg == {"type": "session_state"}


# ---------- UC-A-06: participant_base_url ----------

def test_uc_a_06_set_base_url_strips_slash(admin_client, make_session):
    """UC-A-06: trailing slash stripped."""
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/participant_base_url",
                          json={"url": "https://example.com/"})
    assert r.status_code == 200
    assert r.json() == {"participant_base_url": "https://example.com"}


def test_uc_a_06_default_base_url_follows_the_tunnel(admin_client, make_session, app_module, monkeypatch):
    """UC-A-06: sessions carry the running tunnel's address as default_base_url."""
    s = make_session()
    assert admin_client.get(f"/api/sessions/{s['code']}").json()["default_base_url"] is None
    monkeypatch.setattr(app_module, "PUBLIC_URL", "https://stub-tunnel.trycloudflare.com", raising=False)
    body = admin_client.get(f"/api/sessions/{s['code']}").json()
    assert body["default_base_url"] == "https://stub-tunnel.trycloudflare.com"
    assert body["participant_base_url"] is None


def test_uc_a_06_invalid_scheme_400(admin_client, make_session):
    """UC-A-06: non-http(s) URL → 400."""
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/participant_base_url",
                          json={"url": "ftp://x"})
    assert r.status_code == 400
    assert r.json() == {"detail": "URL must start with http:// or https://"}


def test_uc_a_06_url_too_long_400(admin_client, make_session):
    """UC-A-06: URL too long → 400."""
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/participant_base_url",
                          json={"url": "http://" + "a" * 600})
    assert r.status_code == 400
    assert r.json() == {"detail": "URL is too long"}


def test_uc_a_06_empty_clears(admin_client, make_session):
    """UC-A-06: empty url clears the field."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/participant_base_url",
                      json={"url": "https://example.com"})
    r = admin_client.post(f"/api/sessions/{s['code']}/participant_base_url",
                          json={"url": ""})
    assert r.status_code == 200
    assert r.json() == {"participant_base_url": None}


def test_uc_a_06_no_auth_401(client, make_session):
    """UC-A-06: participant_base_url is owner-only → 401 with no cookie."""
    s = make_session()
    client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/participant_base_url",
                    json={"url": "https://example.com"})
    assert r.status_code == 401


def test_uc_a_06_broadcasts_session_state(admin_client, make_session):
    """UC-A-06: broadcasts session_state."""
    s = make_session()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.post(f"/api/sessions/{s['code']}/participant_base_url",
                          json={"url": "https://example.com"})
        msg = json.loads(ws.receive_text())
        assert msg == {"type": "session_state"}


# ---------- UC-A-07: Delete a session ----------

def test_uc_a_07_delete_planning_empty(admin_client, make_session):
    """UC-A-07: planning + 0 data → DELETE ok."""
    s = make_session()
    r = admin_client.request("DELETE", f"/api/sessions/{s['code']}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_a_07_delete_live_400(admin_client, make_session):
    """UC-A-07: live session → 400 End the session before deleting."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/start")
    r = admin_client.request("DELETE", f"/api/sessions/{s['code']}")
    assert r.status_code == 400
    assert r.json() == {"detail": "End the session before deleting it"}


def test_uc_a_07_delete_with_data_no_confirm_400(admin_client, make_session):
    """UC-A-07: has queries, missing confirm_title → 400."""
    s = make_session()
    # add a query (no auth needed)
    admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": "hi?"})
    r = admin_client.request("DELETE", f"/api/sessions/{s['code']}", json={})
    assert r.status_code == 400
    assert r.json() == {"detail": "Type the session title exactly to confirm deletion"}


def test_uc_a_07_delete_wrong_confirm_400(admin_client, make_session):
    """UC-A-07: wrong confirm_title → 400."""
    s = make_session("MyTitle")
    admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": "hi?"})
    r = admin_client.request("DELETE", f"/api/sessions/{s['code']}",
                             json={"confirm_title": "Wrong"})
    assert r.status_code == 400
    assert r.json() == {"detail": "Type the session title exactly to confirm deletion"}


def test_uc_a_07_delete_correct_confirm_ok(admin_client, make_session):
    """UC-A-07: correct confirm_title → ok; cascades."""
    s = make_session("MyTitle")
    admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": "hi?"})
    r = admin_client.request("DELETE", f"/api/sessions/{s['code']}",
                             json={"confirm_title": "MyTitle"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # confirm gone
    assert admin_client.get(f"/api/sessions/{s['code']}").status_code == 404


def test_uc_a_07_delete_non_owner_403(admin_client, make_session):
    """UC-A-07: non-owner admin → 403 Not your session."""
    s = make_session()
    from prashna import auth
    from prashna import models as m
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="other2", password_hash=auth.hash_password("longenough"))
        db.add(other)
        db.commit()
        db.refresh(other)
        oid = other.id
    # log out then log in as other (but other has no login flow — use issue_session pattern)
    # easier: directly hit the route with admin_client but flip ownership in DB
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        sess.owner_user_id = oid
        db.commit()
    r = admin_client.request("DELETE", f"/api/sessions/{s['code']}")
    assert r.status_code == 403
    assert r.json() == {"detail": "Not your session"}


def test_uc_a_07_delete_no_auth_401(client, make_session):
    """UC-A-07: no auth → 401."""
    s = make_session()
    client.cookies.clear()
    r = client.request("DELETE", f"/api/sessions/{s['code']}")
    assert r.status_code == 401


# ---------- UC-A-08: Inline lifecycle (start/end with admin cookie) ----------

def test_uc_a_08_start_planning(admin_client, make_session):
    """UC-A-08: start a planning session → live."""
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/start")
    assert r.status_code == 200
    assert r.json() == {"status": "live"}


def test_uc_a_08_end_live(admin_client, make_session):
    """UC-A-08: end → ended."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/start")
    r = admin_client.post(f"/api/sessions/{s['code']}/end")
    assert r.status_code == 200
    assert r.json() == {"status": "ended"}


def test_uc_a_08_start_ended_400(admin_client, make_session):
    """UC-A-08: start on ended → 400 Session has ended."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/end")
    r = admin_client.post(f"/api/sessions/{s['code']}/start")
    assert r.status_code == 400
    assert r.json() == {"detail": "Session has ended"}
