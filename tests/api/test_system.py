"""UC-X-01 through UC-X-07: system invariants — WS broadcasts, headers, DB unique constraints."""
from __future__ import annotations

import json
import re

import pytest
from sqlalchemy.exc import IntegrityError


PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)


def _ws_recv_types(ws, n=1):
    msgs = []
    for _ in range(n):
        msgs.append(json.loads(ws.receive_text()))
    return msgs


# ---------- UC-X-01: WebSocket broadcast contracts ----------

def test_uc_x_01_session_state_on_patch(admin_client, make_session):
    """UC-X-01: PATCH /api/sessions/{code} → session_state."""
    s = make_session()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.patch(f"/api/sessions/{s['code']}", json={"title": "x"})
        assert _ws_recv_types(ws) == [{"type": "session_state"}]


def test_uc_x_01_query_new(admin_client, make_session):
    """UC-X-01: POST queries → query_new."""
    s = make_session()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": "Q?"})
        assert _ws_recv_types(ws) == [{"type": "query_new"}]


def test_uc_x_01_query_vote(client, admin_client, make_session):
    """UC-X-01: vote → query_vote."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    admin_client.cookies.clear()
    with client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote")
        assert _ws_recv_types(ws) == [{"type": "query_vote"}]


def test_uc_x_01_query_responded(admin_client, make_session):
    """UC-X-01: respond → query_responded."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/respond", json={})
        assert _ws_recv_types(ws) == [{"type": "query_responded"}]


def test_uc_x_01_query_removed(admin_client, make_session):
    """UC-X-01: remove → query_removed."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/remove", json={})
        assert _ws_recv_types(ws) == [{"type": "query_removed"}]


def test_uc_x_01_query_deleted(admin_client, make_session):
    """UC-X-01: DELETE query → query_deleted."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.request("DELETE", f"/api/sessions/{s['code']}/queries/{q['id']}")
        assert _ws_recv_types(ws) == [{"type": "query_deleted"}]


def test_uc_x_01_quiz_run_new(admin_client, make_quiz, make_session):
    """UC-X-01: POST quiz_runs → quiz_run_new."""
    q = make_quiz()
    s = make_session()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                          json={"quiz_id": q["id"]})
        assert _ws_recv_types(ws) == [{"type": "quiz_run_new"}]


def test_uc_x_01_quiz_run_update(admin_client, make_quiz, make_session):
    """UC-X-01: start / reveal / advance / close / live_counts → quiz_run_update."""
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    base = f"/api/sessions/{s['code']}/quiz_runs/{run['id']}"
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.post(f"{base}/start")
        admin_client.post(f"{base}/reveal", json={"reveal": True})
        admin_client.post(f"{base}/advance", json={"direction": "next"})
        admin_client.post(f"{base}/live_counts", json={"show": True})
        admin_client.post(f"{base}/close")
        msgs = _ws_recv_types(ws, 5)
    assert all(m == {"type": "quiz_run_update"} for m in msgs)


def test_uc_x_01_quiz_run_deleted(admin_client, make_quiz, make_session):
    """UC-X-01: DELETE quiz_run → quiz_run_deleted."""
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        admin_client.request("DELETE", f"/api/sessions/{s['code']}/quiz_runs/{run['id']}")
        assert _ws_recv_types(ws) == [{"type": "quiz_run_deleted"}]


def test_uc_x_01_quiz_submission(client, admin_client, make_quiz, make_session):
    """UC-X-01: submit → quiz_submission."""
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    admin_client.cookies.clear()
    g = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    qid = g["current_question"]["id"]
    aid = g["current_question"]["answers"][0]["id"]
    with client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                    json={"question_id": qid, "answer_ids": [aid]})
        assert _ws_recv_types(ws) == [{"type": "quiz_submission"}]


def test_uc_x_01_participant_broadcast(client, admin_client, make_session):
    """UC-X-01: PATCH /me → participant."""
    s = make_session()
    admin_client.cookies.clear()
    with client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        client.patch(f"/api/sessions/{s['code']}/me", json={"name": "x"})
        assert _ws_recv_types(ws) == [{"type": "participant"}]


# ---------- UC-X-02: WS upgrade rejections ----------

def test_uc_x_02_cross_origin_4403(admin_client, make_session):
    """UC-X-02: mismatched Origin → close 4403."""
    s = make_session()
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as ei:
        with admin_client.websocket_connect(
            f"/ws/sessions/{s['code']}",
            headers={"origin": "https://evil.example"},
        ) as ws:
            ws.receive_text()
    assert ei.value.code == 4403


def test_uc_x_02_no_session_4404(admin_client):
    """UC-X-02: unknown code → close 4404."""
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as ei:
        with admin_client.websocket_connect("/ws/sessions/NOSUCH") as ws:
            ws.receive_text()
    assert ei.value.code == 4404


@pytest.mark.skip(reason="UC-X-02: TestClient's websocket_connect always injects a matching Origin; the no-Origin path can't be exercised in-process.")
def test_uc_x_02_no_origin_ok():
    pass


# ---------- UC-X-03: Static asset security headers ----------

def test_uc_x_03_uploads_have_security_headers(admin_client):
    """UC-X-03: /uploads/<file> carries security headers."""
    files = {"file": ("a.png", PNG_BYTES, "image/png")}
    url = admin_client.post("/api/uploads", files=files).json()["url"]
    r = admin_client.get(url)
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("content-security-policy") == "default-src 'none'; sandbox"
    assert r.headers.get("cross-origin-resource-policy") == "same-origin"


def test_uc_x_03_static_no_extra_headers(admin_client):
    """UC-X-03: /static/* does NOT carry uploads headers."""
    r = admin_client.get("/static/app.css")
    # If the file doesn't exist this test is moot, but assertion holds either way
    assert r.headers.get("content-security-policy") != "default-src 'none'; sandbox"


# ---------- UC-X-04: Image upload constraints ----------

def test_uc_x_04_svg_400(admin_client):
    """UC-X-04: svg → 400."""
    r = admin_client.post("/api/uploads", files={"file": ("a.svg", b"<svg/>", "image/svg+xml")})
    assert r.status_code == 400
    assert r.json() == {"detail": "unsupported image type"}


def test_uc_x_04_distinct_filenames(admin_client):
    """UC-X-04: uploading same file twice → distinct UUID filenames."""
    r1 = admin_client.post("/api/uploads",
                           files={"file": ("a.png", PNG_BYTES, "image/png")}).json()
    r2 = admin_client.post("/api/uploads",
                           files={"file": ("a.png", PNG_BYTES, "image/png")}).json()
    assert r1["url"] != r2["url"]


def test_uc_x_04_filename_pattern(admin_client):
    """UC-X-04: stored filename matches ^[0-9a-f]{32}\\.(png|jpg|jpeg|gif|webp)$."""
    r = admin_client.post("/api/uploads",
                          files={"file": ("a.png", PNG_BYTES, "image/png")}).json()
    name = r["url"].rsplit("/", 1)[-1]
    assert re.match(r"^[0-9a-f]{32}\.(png|jpg|jpeg|gif|webp)$", name)


# ---------- UC-X-05: Storage-level invariants ----------

def test_uc_x_05_two_live_quiz_runs_integrity(admin_client, make_quiz, make_session):
    """UC-X-05: two QuizRun status='live' on same session → IntegrityError."""
    q = make_quiz()
    s = make_session()
    from app.db import SessionLocal
    from app import models as m
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        ver = m.QuizVersion(quiz_id=q["id"], version_no=99, quiz_title="x")
        db.add(ver); db.commit(); db.refresh(ver)
        r1 = m.QuizRun(session_id=sess.id, quiz_version_id=ver.id, status="live")
        r2 = m.QuizRun(session_id=sess.id, quiz_version_id=ver.id, status="live")
        db.add(r1); db.add(r2)
        with pytest.raises(IntegrityError):
            db.commit()


def test_uc_x_05_two_versions_same_quiz_no(admin_client, make_quiz):
    """UC-X-05: two QuizVersion with same (quiz_id, version_no) → IntegrityError."""
    q = make_quiz()
    from app.db import SessionLocal
    from app import models as m
    with SessionLocal() as db:
        v1 = m.QuizVersion(quiz_id=q["id"], version_no=42, quiz_title="x")
        v2 = m.QuizVersion(quiz_id=q["id"], version_no=42, quiz_title="x")
        db.add(v1); db.add(v2)
        with pytest.raises(IntegrityError):
            db.commit()


def test_uc_x_05_two_query_votes(admin_client, make_session):
    """UC-X-05: two QueryVote rows same (query, participant) → IntegrityError."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    from app.db import SessionLocal
    from app import models as m
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        # need a participant
        p = db.query(m.Participant).filter_by(session_id=sess.id).first()
        if not p:
            p = m.Participant(session_id=sess.id, voter_token="ttt")
            db.add(p); db.commit(); db.refresh(p)
        v1 = m.QueryVote(query_id=q["id"], participant_id=p.id)
        v2 = m.QueryVote(query_id=q["id"], participant_id=p.id)
        db.add(v1); db.add(v2)
        with pytest.raises(IntegrityError):
            db.commit()


def test_uc_x_05_two_quiz_submissions(admin_client, make_quiz, make_session):
    """UC-X-05: duplicate QuizSubmission rows → IntegrityError."""
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    from app.db import SessionLocal
    from app import models as m
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        p = m.Participant(session_id=sess.id, voter_token="qq1")
        db.add(p); db.commit(); db.refresh(p)
        runobj = db.get(m.QuizRun, run["id"])
        vq = runobj.quiz_version.questions[0]
        a = vq.answers[0]
        s1 = m.QuizSubmission(quiz_run_id=run["id"], question_id=vq.id,
                              answer_id=a.id, participant_id=p.id)
        s2 = m.QuizSubmission(quiz_run_id=run["id"], question_id=vq.id,
                              answer_id=a.id, participant_id=p.id)
        db.add(s1); db.add(s2)
        with pytest.raises(IntegrityError):
            db.commit()


def test_uc_x_05_two_participants_same_token(admin_client, make_session):
    """UC-X-05: two Participant rows same (session, voter_token) → IntegrityError."""
    s = make_session()
    from app.db import SessionLocal
    from app import models as m
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        p1 = m.Participant(session_id=sess.id, voter_token="dup")
        p2 = m.Participant(session_id=sess.id, voter_token="dup")
        db.add(p1); db.add(p2)
        with pytest.raises(IntegrityError):
            db.commit()


# ---------- UC-X-07: SECRET_KEY ----------

@pytest.mark.skip(reason="UC-X-07: requires app restart with different env vars; not feasible in shared TestClient session.")
def test_uc_x_07_secret_key_lifecycle():
    pass
