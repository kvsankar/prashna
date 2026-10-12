"""UC-X-01 through UC-X-07: system invariants — WS broadcasts, headers, DB unique constraints."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

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


def test_uc_x_01_ping_gets_pong(admin_client, make_session):
    """UC-X-01: a page's keepalive ping is answered, so it can tell the socket is alive."""
    s = make_session()
    with admin_client.websocket_connect(f"/ws/sessions/{s['code']}") as ws:
        ws.send_text("ping")
        # A broadcast follows, so the test never waits forever for a missing pong.
        admin_client.patch(f"/api/sessions/{s['code']}", json={"title": "x"})
        assert ws.receive_json() == {"type": "pong"}
        assert ws.receive_json() == {"type": "session_state"}


def test_uc_x_01_failed_socket_is_closed():
    """UC-X-01: a socket whose send fails is evicted *and closed* (so its page
    reconnects), and the broadcast still reaches the other sockets."""
    import asyncio
    from typing import cast

    from fastapi import WebSocket

    from prashna.ws import Hub

    class Healthy:
        def __init__(self):
            self.sent = []
            self.closed = False

        async def accept(self):
            pass

        async def send_json(self, message):
            self.sent.append(message)

        async def close(self, code=1000):
            self.closed = True

    class Broken(Healthy):
        async def send_json(self, message):
            raise RuntimeError("stalled")

    async def scenario():
        hub = Hub()
        good, bad = Healthy(), Broken()
        await hub.join("room", cast(WebSocket, good))
        await hub.join("room", cast(WebSocket, bad))
        await hub.broadcast("room", {"type": "quiz_submission"})
        await asyncio.sleep(0.05)  # the eviction close runs in the background
        return hub, good, bad

    hub, good, bad = asyncio.run(scenario())
    assert good.sent == [{"type": "quiz_submission"}] and not good.closed
    assert bad.closed
    assert hub.client_count("room") == 1


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
    # A live session: a start in a planning session also sends session_state
    # (UC-M-04, covered by test_uc_m_04_start_in_planning_broadcasts_session_state).
    admin_client.post(f"/api/sessions/{s['code']}/start").raise_for_status()
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


def test_uc_x_04_urlencoded_flood_is_refused_quickly(client, admin_client, make_session, app_module):
    """UC-X-04: a large URL-encoded body to either upload route, without
    signing in, is refused at once and stores nothing (it used to take
    seconds to parse before the authorization check)."""
    import time
    s = make_session()
    admin_client.cookies.clear()
    before = set(app_module.UPLOADS.iterdir())
    for sep in (b"&", b";"):
        body = (b"a" + sep) * (5 * 1024 * 1024 // 2)
        for path in ("/api/uploads", f"/api/sessions/{s['code']}/me/photo"):
            started = time.monotonic()
            r = client.post(path, content=body,
                            headers={"content-type": "application/x-www-form-urlencoded"})
            elapsed = time.monotonic() - started
            assert r.status_code in (400, 401, 422), (path, sep, r.status_code)
            assert elapsed < 1.0, (path, sep, elapsed)
    assert set(app_module.UPLOADS.iterdir()) == before


# ---------- UC-X-05: Storage-level invariants ----------

def test_uc_x_05_two_live_quiz_runs_integrity(admin_client, make_quiz, make_session):
    """UC-X-05: two QuizRun status='live' on same session → IntegrityError."""
    q = make_quiz()
    s = make_session()
    from prashna import models as m
    from prashna.db import SessionLocal
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
    from prashna import models as m
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        v1 = m.QuizVersion(quiz_id=q["id"], version_no=42, quiz_title="x")
        v2 = m.QuizVersion(quiz_id=q["id"], version_no=42, quiz_title="x")
        db.add(v1); db.add(v2)
        with pytest.raises(IntegrityError):
            db.commit()


def test_uc_x_05_additive_migrations_upgrade_known_old_schema(tmp_path):
    """UC-X-05: init migration bridge upgrades persisted DBs from known old shapes."""
    from prashna import db as app_db

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
        assert "participant_base_url" in columns["sessions"]
        assert "feedback_enabled" in columns["sessions"]
        assert "photo_url" in columns["participants"]
        assert "graded" in columns["quiz_questions"]
        assert "graded" in columns["quiz_version_questions"]
        assert "show_live_counts" in columns["quiz_runs"]
        assert "revealed_idxs" in columns["quiz_runs"]

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


def test_uc_x_05_bridge_backfills_question_names(tmp_path):
    """UC-X-05 / UC-P-04: adding queries.author_name copies the name each old question showed."""
    from prashna import db as app_db

    old = tmp_path / "old-queries.db"
    engine = create_engine(f"sqlite:///{old}", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE participants (
                id INTEGER NOT NULL PRIMARY KEY, session_id INTEGER NOT NULL,
                voter_token VARCHAR(64) NOT NULL, name VARCHAR(80),
                first_seen_at DATETIME NOT NULL, last_seen_at DATETIME NOT NULL)
        """)
        conn.exec_driver_sql("""
            CREATE TABLE queries (
                id INTEGER NOT NULL PRIMARY KEY, session_id INTEGER NOT NULL,
                participant_id INTEGER NOT NULL, text TEXT NOT NULL, response_text TEXT,
                responded_at DATETIME, removed_at DATETIME, created_at DATETIME NOT NULL)
        """)
        conn.exec_driver_sql("INSERT INTO participants VALUES (1, 1, 'a', 'Asha', '2026-01-01', '2026-01-01')")
        conn.exec_driver_sql("INSERT INTO participants VALUES (2, 1, 'b', NULL, '2026-01-01', '2026-01-01')")
        conn.exec_driver_sql("INSERT INTO queries VALUES (1, 1, 1, 'Named?', NULL, NULL, NULL, '2026-01-01')")
        conn.exec_driver_sql("INSERT INTO queries VALUES (2, 1, 2, 'Anon?', NULL, NULL, NULL, '2026-01-01')")

    app_db._apply_additive_migrations(bind=engine)
    app_db._apply_additive_migrations(bind=engine)  # idempotent: a second run changes nothing
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("SELECT id, author_name FROM queries ORDER BY id").fetchall()
    assert rows == [(1, "Asha"), (2, None)]


def test_uc_x_05_two_query_votes(admin_client, make_session):
    """UC-X-05: two QueryVote rows same (query, participant) → IntegrityError."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    from prashna import models as m
    from prashna.db import SessionLocal
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
    from prashna import models as m
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        sess = db.query(m.Session).filter_by(code=s["code"]).one()
        p = m.Participant(session_id=sess.id, voter_token="qq1")
        db.add(p); db.commit(); db.refresh(p)
        runobj = db.get_one(m.QuizRun, run["id"])
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
    from prashna import models as m
    from prashna.db import SessionLocal
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
    assert "test_unset_secret_persists_key_beside_database" in text


def test_uc_x_07_resolve_secret(tmp_path):
    """UC-X-07: env wins; otherwise a persisted key file; ephemeral only if unwritable."""
    from prashna import auth
    key_file = tmp_path / "secret-key"
    assert auth._resolve_secret("abc", key_file) == ("abc", False)
    assert not key_file.exists()
    key, ephemeral = auth._resolve_secret(None, key_file)
    assert ephemeral is False and key.startswith("prashna_sk_") and len(key) > 40
    assert key_file.read_text().strip() == key
    assert (key_file.stat().st_mode & 0o777) == 0o600
    assert auth._resolve_secret(None, key_file) == (key, False)
    older = tmp_path / "older-secret-key"
    older.write_text("unprefixed-key-from-an-older-install")
    assert auth._resolve_secret(None, older) == ("unprefixed-key-from-an-older-install", False)
    blocked = tmp_path / "missing-dir" / "sub"
    blocked.parent.mkdir()
    blocked.parent.chmod(0o500)
    try:
        key3, ephemeral3 = auth._resolve_secret(None, blocked / "secret-key")
        assert ephemeral3 is True and key3
    finally:
        blocked.parent.chmod(0o700)
    # The test session sets PRASHNA_SECRET_KEY, so the live flag is False.
    assert auth.SECRET_KEY_IS_EPHEMERAL is False


@pytest.mark.parametrize("corrupt", ["", "\n", "   \n", "short-key"])
def test_uc_x_07_corrupt_key_files_are_replaced(tmp_path, monkeypatch, corrupt):
    """UC-X-07: an empty or too-short secret-key or setup-token is replaced
    with a new random value, written whole with mode 0600."""
    from prashna import auth
    key_file = tmp_path / "secret-key"
    key_file.write_text(corrupt)
    key, ephemeral = auth._resolve_secret(None, key_file)
    assert ephemeral is False
    assert key.startswith("prashna_sk_") and len(key) >= 32
    assert key_file.read_text().strip() == key
    assert (key_file.stat().st_mode & 0o777) == 0o600
    assert auth._resolve_secret(None, key_file) == (key, False)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["secret-key"]

    token_file = tmp_path / "setup-token"
    token_file.write_text(corrupt)
    monkeypatch.setattr(auth, "SETUP_TOKEN_FILE", token_file)
    monkeypatch.setattr(auth, "admin_exists", lambda _db: False)
    monkeypatch.delenv("PRASHNA_SETUP_TOKEN", raising=False)
    token = auth.setup_token(cast(DbSession, None))  # admin_exists is stubbed
    assert token and token.startswith("prashna_st_")
    assert token_file.read_text().strip() == token
    assert (token_file.stat().st_mode & 0o777) == 0o600


# ---------- UC-X-05: wrong JSON types never reach storage ----------

PROFILE_TEXT_FIELDS = ("name", "email", "contact_number", "organization", "role",
                       "linkedin_url", "current_work", "learning_goal", "photo_url")


def _text_field_cases(admin_client, make_session) -> list[tuple[str, str, dict, str]]:
    s = make_session("types")
    code = s["code"]
    admin_client.post(f"/api/sessions/{code}/feedback_enabled", json={"enabled": True})
    qid = admin_client.post(f"/api/sessions/{code}/queries", json={"text": "hi"}).json()["id"]
    quiz = admin_client.post("/api/quizzes", json={"title": "types"}).json()["id"]
    question = admin_client.post(f"/api/quizzes/{quiz}/questions", json={"text": "q"}).json()["id"]
    answer = admin_client.post(f"/api/quiz_questions/{question}/answers", json={"text": "a"}).json()["id"]
    cases = [
        ("POST", "/api/sessions", {}, "title"),
        ("PATCH", f"/api/sessions/{code}", {}, "title"),
        ("POST", f"/api/sessions/{code}/participant_base_url", {}, "url"),
        ("POST", f"/api/sessions/{code}/queries", {}, "text"),
        ("POST", f"/api/sessions/{code}/queries", {"text": "hi"}, "author_name"),
        ("POST", f"/api/sessions/{code}/queries/{qid}/respond", {}, "response_text"),
        ("POST", f"/api/sessions/{code}/feedback", {"rating": 3}, "went_well"),
        ("POST", f"/api/sessions/{code}/feedback", {"rating": 3}, "to_improve"),
        ("POST", "/api/quizzes", {}, "title"),
        ("PATCH", f"/api/quizzes/{quiz}", {}, "title"),
        ("POST", f"/api/quizzes/{quiz}/questions", {}, "text"),
        ("PATCH", f"/api/quiz_questions/{question}", {}, "text"),
        ("POST", f"/api/quiz_questions/{question}/answers", {}, "text"),
        ("PATCH", f"/api/quiz_answers/{answer}", {}, "text"),
        ("POST", "/api/admin/login", {"password": "testpass1"}, "username"),  # pragma: allowlist secret
        ("POST", "/api/admin/login", {"username": "admin"}, "password"),
        ("POST", "/api/admin/change_password", {"new_password": "longenough"}, "current_password"),  # pragma: allowlist secret
        ("POST", "/api/admin/change_password", {"current_password": "testpass1"}, "new_password"),  # pragma: allowlist secret
    ]
    cases += [("PATCH", f"/api/sessions/{code}/me", {}, field) for field in PROFILE_TEXT_FIELDS]
    return cases


@pytest.mark.parametrize("bad", [5, ["x"], {"a": 1}, True])
def test_uc_x_05_text_fields_reject_other_json_types(admin_client, make_session, bad):
    """UC-X-05 / conventions: a non-string text field → 400, never 500."""
    for method, url, base, field in _text_field_cases(admin_client, make_session):
        r = admin_client.request(method, url, json={**base, field: bad})
        assert r.status_code == 400, (method, url, field, r.status_code, r.text)
        assert r.json() == {"detail": f"{field} must be text"}, (method, url, field)
    # Nothing was stored: the admin still signs in with the old password.
    assert admin_client.post("/api/admin/login", json={"username": "admin", "password": "testpass1"}).status_code == 200  # pragma: allowlist secret


@pytest.mark.parametrize("field", ["username", "password"])
def test_uc_x_05_setup_rejects_non_string_credentials(client, field):
    """UC-X-05 / UC-A-01: first-run setup refuses a non-string username or password."""
    from ..support import SETUP_TOKEN
    body = {"username": "alice", "password": "longenough", "setup_token": SETUP_TOKEN, field: 12345678}  # pragma: allowlist secret
    r = client.post("/api/admin/setup", json=body)
    assert r.status_code == 400
    assert r.json() == {"detail": f"{field} must be text"}
    assert client.get("/api/admin/status").json()["initialized"] is False


def test_uc_x_05_order_index_must_be_an_integer_on_create(admin_client):
    """UC-X-05 / UC-A-14 / UC-A-17: order_index on create is an integer."""
    quiz = admin_client.post("/api/quizzes", json={"title": "order"}).json()["id"]
    r = admin_client.post(f"/api/quizzes/{quiz}/questions", json={"text": "a", "order_index": "abc"})
    assert r.status_code == 400
    assert r.json() == {"detail": "order_index must be an integer"}
    question = admin_client.post(f"/api/quizzes/{quiz}/questions", json={"text": "b"})
    assert question.status_code == 200, question.text
    question_id = question.json()["id"]
    r = admin_client.post(f"/api/quiz_questions/{question_id}/answers", json={"text": "a", "order_index": "abc"})
    assert r.status_code == 400
    assert r.json() == {"detail": "order_index must be an integer"}
    assert admin_client.post(f"/api/quiz_questions/{question_id}/answers", json={"text": "b"}).status_code == 200
    body = admin_client.get(f"/api/quizzes/{quiz}").json()
    assert [q["text"] for q in body["questions"]] == ["b"]
    assert [a["text"] for a in body["questions"][0]["answers"]] == ["b"]
    # An integer order_index is still accepted.
    assert admin_client.post(f"/api/quizzes/{quiz}/questions", json={"text": "c", "order_index": 5}).status_code == 200
