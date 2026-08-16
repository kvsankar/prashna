"""UC-X-01 through UC-X-07: system invariants — WS broadcasts, headers, DB unique constraints."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)
BASELINE_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "content-security-policy": "frame-ancestors 'none'",
    "referrer-policy": "no-referrer",
}
UPLOAD_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "content-security-policy": "default-src 'none'; sandbox",
    "cross-origin-resource-policy": "same-origin",
}


def assert_security_headers(response, expected, label):
    for name, value in expected.items():
        assert response.headers.get(name) == value, label


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


def test_uc_x_01_session_deleted_broadcasts(admin_client, make_session, app_module, monkeypatch):
    """UC-X-01: DELETE session → session_deleted."""
    s = make_session()
    sent = []

    async def fake_broadcast(room, message):
        sent.append((room, message))

    monkeypatch.setattr(app_module.hub, "broadcast", fake_broadcast)
    r = admin_client.request("DELETE", f"/api/sessions/{s['code']}")
    assert r.status_code == 200
    assert sent == [(f"session:{s['code']}", {"type": "session_deleted"})]


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


def test_uc_x_09_matching_ngrok_origin_accepts_live_updates(admin_client, make_session):
    """UC-X-09: a matching public HTTPS Origin/Host works behind ngrok."""
    s = make_session()
    public_host = "prashna-smoke.ngrok.app"
    with admin_client.websocket_connect(
        f"/ws/sessions/{s['code']}",
        headers={
            "host": public_host,
            "origin": f"https://{public_host}",
        },
    ) as ws:
        r = admin_client.patch(
            f"/api/sessions/{s['code']}",
            json={"title": "Tunnel update"},
        )
        assert r.status_code == 200
        assert _ws_recv_types(ws) == [{"type": "session_state"}]


def test_uc_x_02_no_session_4404(admin_client):
    """UC-X-02: unknown code → close 4404."""
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as ei:
        with admin_client.websocket_connect("/ws/sessions/NOSUCH") as ws:
            ws.receive_text()
    assert ei.value.code == 4404


# ---------- UC-X-03: Static asset security headers ----------

def test_uc_x_03_uploads_have_security_headers(admin_client):
    """UC-X-03: /uploads/<file> carries security headers."""
    files = {"file": ("a.png", PNG_BYTES, "image/png")}
    url = admin_client.post("/api/uploads", files=files).json()["url"]
    r = admin_client.get(url)
    assert r.status_code == 200
    assert_security_headers(r, UPLOAD_SECURITY_HEADERS, url)


def test_uc_x_03_static_no_extra_headers(admin_client):
    """UC-X-03: /static/* does NOT carry the uploads-tier strict CSP."""
    r = admin_client.get("/static/app.css")
    # If the file doesn't exist this test is moot, but assertion holds either way
    assert r.headers.get("content-security-policy") != "default-src 'none'; sandbox"


def test_uc_x_03_baseline_headers_on_pages(client):
    """UC-X-03: non-uploads responses carry the clickjacking/sniffing baseline."""
    for path in ("/", "/static/app.css"):
        r = client.get(path)
        assert_security_headers(r, BASELINE_SECURITY_HEADERS, path)


def test_uc_x_03_baseline_headers_on_page_and_static_samples(
    admin_client,
    make_session,
):
    """UC-X-03: page/static samples carry baseline security headers."""
    s = make_session()
    paths = (
        "/",
        "/quizzes",
        f"/s/{s['code']}",
        f"/p/{s['code']}",
        "/static/vendor/qrcode.js",
    )
    for path in paths:
        r = admin_client.get(path)
        assert r.status_code in (200, 404), path
        assert_security_headers(r, BASELINE_SECURITY_HEADERS, path)


def test_uc_x_03_baseline_headers_on_api_success_and_errors(
    admin_client,
):
    """UC-X-03: API payload and error samples carry baseline headers."""
    samples = [
        admin_client.get("/api/admin/status"),
        admin_client.get("/api/sessions"),
        admin_client.get("/api/sessions/NOPE99"),
        admin_client.post(
            "/api/uploads",
            files={"file": ("bad.svg", b"<svg/>", "image/svg+xml")},
        ),
    ]
    for response in samples:
        assert_security_headers(
            response,
            BASELINE_SECURITY_HEADERS,
            str(response.request.url),
        )


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
    from app import models as m
    from app.db import SessionLocal
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
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        v1 = m.QuizVersion(quiz_id=q["id"], version_no=42, quiz_title="x")
        v2 = m.QuizVersion(quiz_id=q["id"], version_no=42, quiz_title="x")
        db.add(v1); db.add(v2)
        with pytest.raises(IntegrityError):
            db.commit()


def test_uc_x_05_additive_migrations_upgrade_known_old_schema(tmp_path):
    """UC-X-05: init migration bridge upgrades persisted DBs from known old shapes."""
    from app import db as app_db

    old = tmp_path / "old-shape.db"
    engine = create_engine(f"sqlite:///{old}", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE users (
                id INTEGER NOT NULL PRIMARY KEY,
                username VARCHAR(80) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at DATETIME NOT NULL
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE sessions (
                id INTEGER NOT NULL PRIMARY KEY,
                code VARCHAR(12) NOT NULL,
                title VARCHAR(200) NOT NULL,
                mod_key VARCHAR(32) NOT NULL,
                owner_user_id INTEGER NOT NULL,
                status VARCHAR(10) NOT NULL,
                started_at DATETIME,
                ended_at DATETIME,
                created_at DATETIME NOT NULL
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE quiz_questions (
                id INTEGER NOT NULL PRIMARY KEY,
                quiz_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                image_url VARCHAR(500),
                qtype VARCHAR(10) NOT NULL,
                order_index INTEGER NOT NULL
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE quiz_version_questions (
                id INTEGER NOT NULL PRIMARY KEY,
                version_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                image_url VARCHAR(500),
                qtype VARCHAR(10) NOT NULL,
                order_index INTEGER NOT NULL
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE quiz_runs (
                id INTEGER NOT NULL PRIMARY KEY,
                session_id INTEGER NOT NULL,
                quiz_version_id INTEGER NOT NULL,
                status VARCHAR(10) NOT NULL,
                current_question_idx INTEGER NOT NULL,
                reveal_current BOOLEAN NOT NULL,
                started_at DATETIME,
                closed_at DATETIME,
                created_at DATETIME NOT NULL
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE participants (
                id INTEGER NOT NULL PRIMARY KEY,
                session_id INTEGER NOT NULL,
                voter_token VARCHAR(64) NOT NULL,
                name VARCHAR(80),
                first_seen_at DATETIME NOT NULL,
                last_seen_at DATETIME NOT NULL
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE quiz_submissions (
                id INTEGER NOT NULL PRIMARY KEY,
                quiz_run_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                answer_id INTEGER NOT NULL,
                participant_id INTEGER NOT NULL,
                created_at DATETIME NOT NULL
            )
        """)

    app_db._apply_additive_migrations(bind=engine)
    with engine.begin() as conn:
        columns = {
            table: {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for table in (
                "users",
                "sessions",
                "participants",
                "quiz_questions",
                "quiz_version_questions",
                "quiz_runs",
            )
        }
        assert "session_version" in columns["users"]
        assert "github_id" in columns["users"]
        assert "participant_base_url" in columns["sessions"]
        assert "feedback_enabled" in columns["sessions"]
        assert "photo_url" in columns["participants"]
        assert "graded" in columns["quiz_questions"]
        assert "graded" in columns["quiz_version_questions"]
        assert "show_live_counts" in columns["quiz_runs"]

        indexes = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA index_list(quiz_runs)").fetchall()
        }
        assert "uq_session_live_run" in indexes
        qsub_indexes = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA index_list(quiz_submissions)").fetchall()
        }
        assert "ix_qsub_run_question" in qsub_indexes


def test_uc_x_05_two_query_votes(admin_client, make_session):
    """UC-X-05: two QueryVote rows same (query, participant) → IntegrityError."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    from app import models as m
    from app.db import SessionLocal
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
    from app import models as m
    from app.db import SessionLocal
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
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        p1 = m.Participant(session_id=sess.id, voter_token="dup")
        p2 = m.Participant(session_id=sess.id, voter_token="dup")
        db.add(p1); db.add(p2)
        with pytest.raises(IntegrityError):
            db.commit()


# ---------- UC-X-07: SECRET_KEY ----------

def test_uc_x_07_secret_key_lifecycle_subprocess_contract_present():
    """UC-X-07: restart coverage lives in a subprocess integration file."""
    text = (Path(__file__).with_name("test_secret_lifecycle.py")).read_text()
    assert "test_fixed_secret_survives_restart" in text
    assert "test_unset_secret_warns" in text


def test_uc_x_07_resolve_secret_pure():
    """UC-X-07: _resolve_secret reports ephemeral only when env is unset."""
    from app import auth
    key, ephemeral = auth._resolve_secret(None)
    assert ephemeral is True and isinstance(key, str) and key
    key2, ephemeral2 = auth._resolve_secret("abc")
    assert (key2, ephemeral2) == ("abc", False)
    # The test session sets PRASHNA_SECRET_KEY, so the live flag is False.
    assert auth.SECRET_KEY_IS_EPHEMERAL is False
