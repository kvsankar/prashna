"""UC-P-01, UC-P-02, UC-P-03, UC-P-11, UC-M-10: session lookup, participants, presence."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)

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
    assert body["feedback_enabled"] is False


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


def test_uc_p_02_concurrent_first_touch_single_row(make_session, app_module):
    """UC-P-02: concurrent first-touch sharing one fresh token → one row, no 500.

    Mirrors the projector firing /queries and /quiz_runs in parallel before a
    Participant row exists for the cookie. The insert race must resolve to a
    single row with both requests returning 200.
    """
    import secrets as _secrets
    import threading

    s = make_session()
    token = "shared-" + _secrets.token_hex(8)
    results = []
    barrier = threading.Barrier(2)

    def hit(path):
        with TestClient(app_module.app) as c:
            c.cookies.set("voter_token", token)
            barrier.wait()
            r = c.get(f"/api/sessions/{s['code']}/{path}")
            results.append(r.status_code)

    threads = [
        threading.Thread(target=hit, args=("queries",)),
        threading.Thread(target=hit, args=("quiz_runs",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [200, 200], results
    from prashna import models as m
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        rows = db.query(m.Participant).filter_by(
            session_id=sess.id, voter_token=token).all()
        assert len(rows) == 1


def test_uc_p_02_last_seen_throttle(client, admin_client, make_session):
    """UC-P-02: two calls within 5s → last_seen_at advances only once."""
    s = make_session()
    admin_client.cookies.clear()
    client.get(f"/api/sessions/{s['code']}/me")  # creates row
    from prashna import models as m
    from prashna.db import SessionLocal
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
    from datetime import datetime, timedelta

    from prashna import models as m
    from prashna.db import SessionLocal
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


def test_uc_p_03_profile_fields_round_trip(client, admin_client, make_session):
    """UC-P-03: PATCH /me stores optional attendee profile fields."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.patch(f"/api/sessions/{s['code']}/me", json={
        "name": "  Dana  ",
        "email": "  dana@example.com  ",
        "contact_number": "  +1 415 555 0101  ",
        "organization": "  ExampleCo  ",
        "role": "  Engineering Manager  ",
        "linkedin_url": "  https://www.linkedin.com/in/dana-example  ",
        "current_work": "  Building a training platform  ",
        "learning_goal": "  Learn facilitation patterns  ",
    })
    assert r.status_code == 200, r.text
    assert r.json() == {
        "id": r.json()["id"],
        "name": "Dana",
        "email": "dana@example.com",
        "contact_number": "+1 415 555 0101",
        "organization": "ExampleCo",
        "role": "Engineering Manager",
        "linkedin_url": "https://www.linkedin.com/in/dana-example",
        "photo_url": None,
        "current_work": "Building a training platform",
        "learning_goal": "Learn facilitation patterns",
    }
    g = client.get(f"/api/sessions/{s['code']}/me").json()
    assert g["email"] == "dana@example.com"
    assert g["contact_number"] == "+1 415 555 0101"
    assert g["organization"] == "ExampleCo"
    assert g["role"] == "Engineering Manager"
    assert g["linkedin_url"] == "https://www.linkedin.com/in/dana-example"
    assert g["photo_url"] is None
    assert g["current_work"] == "Building a training platform"
    assert g["learning_goal"] == "Learn facilitation patterns"


def test_uc_p_03_profile_photo_upload_and_clear(
    client,
    admin_client,
    make_session,
):
    """UC-P-03: participant can add and clear an optional profile photograph."""
    s = make_session()
    admin_client.cookies.clear()

    r = client.post(
        f"/api/sessions/{s['code']}/me/photo",
        files={"file": ("dana.png", PNG_BYTES, "image/png")},
    )
    assert r.status_code == 200, r.text
    uploaded = r.json()["photo_url"]
    assert uploaded.startswith("/uploads/")

    g = client.get(f"/api/sessions/{s['code']}/me").json()
    assert g["photo_url"] == uploaded

    r = client.patch(f"/api/sessions/{s['code']}/me", json={"photo_url": None})
    assert r.status_code == 200, r.text
    assert r.json()["photo_url"] is None


def test_uc_p_03_profile_photo_rejects_unsupported_type(
    client,
    admin_client,
    make_session,
):
    """UC-P-03: participant profile photo uploads use image constraints."""
    s = make_session()
    admin_client.cookies.clear()

    r = client.post(
        f"/api/sessions/{s['code']}/me/photo",
        files={"file": ("bad.svg", b"<svg/>", "image/svg+xml")},
    )
    assert r.status_code == 400
    assert r.json() == {"detail": "unsupported image type"}


def test_uc_p_03_profile_photo_url_cannot_be_set_directly(
    client,
    admin_client,
    make_session,
):
    """UC-P-03: profile PATCH cannot point a photo at an arbitrary URL."""
    s = make_session()
    admin_client.cookies.clear()

    r = client.patch(
        f"/api/sessions/{s['code']}/me",
        json={"photo_url": "https://example.com/avatar.png"},
    )
    assert r.status_code == 400
    assert r.json() == {"detail": "photo must be uploaded"}


def test_uc_p_03_replaced_or_cleared_photo_file_is_deleted(client, admin_client, make_session):
    """UC-P-03: a replaced or cleared photograph's file is deleted."""
    s = make_session()
    admin_client.cookies.clear()
    first = client.post(f"/api/sessions/{s['code']}/me/photo",
                        files={"file": ("a.png", PNG_BYTES, "image/png")}).json()["photo_url"]
    assert client.get(first).status_code == 200
    second = client.post(f"/api/sessions/{s['code']}/me/photo",
                         files={"file": ("b.png", PNG_BYTES, "image/png")}).json()["photo_url"]
    assert second != first
    assert client.get(first).status_code == 404
    assert client.get(second).status_code == 200
    r = client.patch(f"/api/sessions/{s['code']}/me", json={"photo_url": None})
    assert r.status_code == 200
    assert client.get(second).status_code == 404


@pytest.mark.parametrize("bad", ["javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,x",
                                 "www.linkedin.com/in/x"])
def test_uc_p_03_linkedin_url_must_be_web_address(client, admin_client, make_session, bad):
    """UC-P-03: only http:// and https:// LinkedIn addresses are stored."""
    s = make_session()
    admin_client.cookies.clear()
    ok = client.patch(f"/api/sessions/{s['code']}/me", json={"linkedin_url": "https://www.linkedin.com/in/x"})
    assert ok.status_code == 200
    r = client.patch(f"/api/sessions/{s['code']}/me", json={"linkedin_url": bad, "name": "Eve"})
    assert r.status_code == 400
    assert r.json() == {"detail": "LinkedIn profile must start with http:// or https://"}
    me = client.get(f"/api/sessions/{s['code']}/me").json()
    assert me["linkedin_url"] == "https://www.linkedin.com/in/x"
    assert me["name"] is None
    for good in ("HTTPS://www.linkedin.com/in/x", "http://www.linkedin.com/in/x"):
        r = client.patch(f"/api/sessions/{s['code']}/me", json={"linkedin_url": good})
        assert r.status_code == 200
        assert r.json()["linkedin_url"] == good


def test_uc_p_03_profile_editable_after_session_ends(client, admin_client, make_session):
    """UC-P-03: the profile can still be saved after the session ends."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/end")
    admin_client.cookies.clear()
    assert client.patch(f"/api/sessions/{s['code']}/me", json={"name": "Dana"}).status_code == 200
    r = client.post(f"/api/sessions/{s['code']}/me/photo", files={"file": ("a.png", PNG_BYTES, "image/png")})
    assert r.status_code == 200


def test_uc_p_03_profile_blank_fields_become_null(client, admin_client, make_session):
    """UC-P-03: blank optional profile fields are stored as null."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.patch(f"/api/sessions/{s['code']}/me", json={
        "name": "Dana",
        "email": "dana@example.com",
        "contact_number": "+1 415 555 0101",
        "organization": "ExampleCo",
        "role": "Manager",
        "linkedin_url": "https://www.linkedin.com/in/dana-example",
        "current_work": "Building a training platform",
        "learning_goal": "Learn",
    })
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/sessions/{s['code']}/me", json={
        "name": "",
        "email": " ",
        "contact_number": "",
        "organization": "",
        "role": " ",
        "linkedin_url": "",
        "current_work": " ",
        "learning_goal": "",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("name", "email", "contact_number", "organization", "role", "linkedin_url", "current_work", "learning_goal"):
        assert body[key] is None


def test_uc_m_13_participant_profiles_summary(client, admin_client, make_session, mod_headers):
    """UC-M-13: moderators can list only attendees with provided profile data."""
    s = make_session()
    admin_client.cookies.clear()
    client.patch(f"/api/sessions/{s['code']}/me", json={
        "name": "Dana",
        "email": "dana@example.com",
        "contact_number": "+1 415 555 0101",
        "organization": "ExampleCo",
        "role": "Manager",
        "linkedin_url": "https://www.linkedin.com/in/dana-example",
        "photo_url": None,
        "current_work": "Building a training platform",
        "learning_goal": "Practice live facilitation",
    })
    photo = client.post(
        f"/api/sessions/{s['code']}/me/photo",
        files={"file": ("dana.png", PNG_BYTES, "image/png")},
    ).json()["photo_url"]
    client.cookies.clear()
    client.get(f"/api/sessions/{s['code']}/me")

    r = client.get(f"/api/sessions/{s['code']}/participants", headers=mod_headers(s["mod_key"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["name"] == "Dana"
    assert body["items"][0]["email"] == "dana@example.com"
    assert body["items"][0]["contact_number"] == "+1 415 555 0101"
    assert body["items"][0]["organization"] == "ExampleCo"
    assert body["items"][0]["role"] == "Manager"
    assert body["items"][0]["linkedin_url"] == "https://www.linkedin.com/in/dana-example"
    assert body["items"][0]["photo_url"] == photo
    assert body["items"][0]["current_work"] == "Building a training platform"
    assert body["items"][0]["learning_goal"] == "Practice live facilitation"


def test_uc_m_13_participant_profiles_requires_moderator(client, admin_client, make_session):
    """UC-M-13: anonymous callers cannot list attendee profiles."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.get(f"/api/sessions/{s['code']}/participants")
    assert r.status_code == 403


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
    """UC-P-11: submit on ended → 400 Session has ended.

    Per the audit fix, /end refuses while a quiz is live — so this test
    closes the run first, then ends the session.
    """
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    g = admin_client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    qid = g["current_question"]["id"]
    aid = g["current_question"]["answers"][0]["id"]
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close")
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

def test_uc_m_10_presence_creates_no_participant(client, admin_client, make_session):
    """UC-M-10: reading presence is read-only: no cookie, no Participant,
    so a moderator tab polling it is never counted online."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.get(f"/api/sessions/{s['code']}/presence")
    assert r.status_code == 200
    assert r.json() == {"online": 0}
    assert "voter_token" not in r.headers.get("set-cookie", "")
    from prashna import models as m
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        assert db.query(m.Participant).filter_by(session_id=sess.id).count() == 0


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
    from prashna import models as m
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        for p in db.query(m.Participant).filter_by(session_id=sess.id).all():
            p.last_seen_at = datetime.utcnow() - timedelta(seconds=60)
        db.commit()
    with TestClient(app_module.app) as c2:
        r = c2.get(f"/api/sessions/{s['code']}/presence")
    # The backdated participant is excluded, and the presence call itself
    # creates no participant.
    assert r.json()["online"] == 0


def test_uc_p_bootstrap_reports_the_owner(admin_client, make_session):
    """UC-P: participant-bootstrap says whether the viewer is the admin who owns the session."""
    s = make_session()
    owner_view = admin_client.get(f"/api/sessions/{s['code']}/participant-bootstrap").json()
    assert owner_view["viewer_is_owner"] is True
    admin_client.cookies.delete("prashna_admin")
    participant_view = admin_client.get(f"/api/sessions/{s['code']}/participant-bootstrap").json()
    assert participant_view["viewer_is_owner"] is False
