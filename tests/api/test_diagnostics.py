"""Diagnostics contracts for incident-useful, secret-safe event logs."""
from __future__ import annotations

import asyncio
import logging

import pytest
from sqlalchemy import create_engine
from starlette.websockets import WebSocketDisconnect


def _events(caplog):
    return {
        record.__dict__.get("diag_event")
        for record in caplog.records
        if record.name == "prashna"
    }


def _log_text(caplog) -> str:
    return "\n".join(
        f"{record.getMessage()} {record.__dict__}"
        for record in caplog.records
    )


def _assert_not_logged(caplog, values):
    text = _log_text(caplog)
    for value in values:
        assert value not in text


def test_diagnostic_message_includes_safe_payload(caplog):
    """Production log format should carry safe fields, not just logger extras."""
    from app.diagnostics import log_diagnostic

    caplog.set_level(logging.INFO, logger="prashna")
    log_diagnostic(
        "http.request",
        outcome="success",
        method="POST",
        path="/api/sessions/:code/feedback_enabled",
        duration_ms=12.5,
        mod_key="secret-value",
    )

    text = _log_text(caplog)
    assert "diagnostic_event" in text
    assert '"event":"http.request"' in text
    assert '"duration_ms":12.5' in text
    assert "secret-value" not in text


def test_state_changing_requests_emit_timing_diagnostics(admin_client, make_session, caplog):
    """Mutating API calls should leave request-duration evidence."""
    caplog.set_level(logging.INFO, logger="prashna")
    s = make_session()

    r = admin_client.post(f"/api/sessions/{s['code']}/feedback_enabled",
                          json={"enabled": True})

    assert r.status_code == 200
    assert "http.request" in _events(caplog)
    http_records = [
        record for record in caplog.records
        if record.__dict__.get("diag_event") == "http.request"
    ]
    http_text = "\n".join(record.getMessage() for record in http_records)
    assert "/api/sessions/:code/feedback_enabled" in http_text
    assert s["code"] not in http_text


def test_auth_session_upload_and_ws_diagnostics(client, caplog):
    """Core operator incidents should emit safe structured diagnostics."""
    caplog.set_level(logging.INFO, logger="prashna")
    setup_password = "setup-secret-123"
    login_password = "login-secret-123"
    upload_body = b"<svg>uploaded-secret</svg>"

    r = client.post(
        "/api/admin/setup",
        json={"username": "alice", "password": setup_password},
    )
    assert r.status_code == 200
    client.cookies.clear()

    r = client.post(
        "/api/admin/login",
        json={"username": "alice", "password": "wrong-secret-123"},
    )
    assert r.status_code == 401
    r = client.post(
        "/api/admin/login",
        json={"username": "alice", "password": setup_password},
    )
    assert r.status_code == 200

    s = client.post("/api/sessions", json={"title": "Diag Session"}).json()
    client.post(f"/api/sessions/{s['code']}/start")
    client.post(f"/api/sessions/{s['code']}/end")
    client.post(
        "/api/uploads",
        files={"file": ("bad.svg", upload_body, "image/svg+xml")},
    )

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws/sessions/{s['code']}",
            headers={"origin": "https://evil.example"},
        ):
            pass

    r = client.post(
        "/api/admin/change_password",
        json={
            "current_password": setup_password,
            "new_password": login_password,
        },
    )
    assert r.status_code == 200
    client.post("/api/admin/logout")

    assert {
        "auth.setup",
        "auth.login",
        "auth.password_change",
        "auth.logout",
        "session.lifecycle",
        "upload.reject",
        "ws.reject",
    } <= _events(caplog)
    _assert_not_logged(
        caplog,
        [
            setup_password,
            login_password,
            "wrong-secret-123",
            s["mod_key"],
            "bad.svg",
            upload_body.decode(),
        ],
    )


def test_qna_quiz_feedback_diagnostics(
    client,
    admin_client,
    make_quiz,
    make_session,
    caplog,
):
    """Moderator and learning-flow actions should be diagnosable."""
    caplog.set_level(logging.INFO, logger="prashna")

    s = make_session()
    q = admin_client.post(
        f"/api/sessions/{s['code']}/queries",
        json={"text": "What should I review?"},
    ).json()
    admin_client.post(
        f"/api/sessions/{s['code']}/queries/{q['id']}/respond",
        json={"response_text": "Focus on examples."},
    )
    admin_client.post(
        f"/api/sessions/{s['code']}/queries/{q['id']}/remove",
        json={"removed": True},
    )

    admin_client.post(
        f"/api/sessions/{s['code']}/feedback_enabled",
        json={"enabled": True},
    )
    client.post(f"/api/sessions/{s['code']}/feedback", json={"rating": 5})
    admin_client.get(f"/api/sessions/{s['code']}/feedback/summary")

    quiz = make_quiz()
    run = admin_client.post(
        f"/api/sessions/{s['code']}/quiz_runs",
        json={"quiz_id": quiz["id"]},
    ).json()
    base = f"/api/sessions/{s['code']}/quiz_runs/{run['id']}"
    admin_client.post(f"{base}/start")
    admin_client.post(f"{base}/live_counts", json={"show": True})
    admin_client.post(f"{base}/reveal", json={"reveal": True})
    admin_client.post(f"{base}/close")

    assert {
        "query.moderation",
        "feedback.summary",
        "quiz_run.lifecycle",
    } <= _events(caplog)
    _assert_not_logged(caplog, [s["mod_key"], "What should I review?"])


def test_websocket_send_failure_logs_safely(caplog):
    """A failed broadcast send should log the failure without payload data."""
    from app.ws import hub

    class BrokenSocket:
        async def send_json(self, _message):
            raise RuntimeError("socket-secret")

    caplog.set_level(logging.INFO, logger="prashna")

    ok = asyncio.run(
        hub._safe_send(BrokenSocket(), {"type": "secret-message"})
    )

    assert ok is False
    assert "ws.broadcast_failure" in _events(caplog)
    _assert_not_logged(caplog, ["socket-secret", "secret-message"])


def test_websocket_send_timeout_logs_safely(monkeypatch, caplog):
    """A stalled socket send should timeout quickly and log safely."""
    from app import ws as ws_module
    from app.ws import hub

    class StalledSocket:
        async def send_json(self, _message):
            await asyncio.sleep(1)

    monkeypatch.setattr(ws_module, "SEND_TIMEOUT_SECS", 0.01)
    caplog.set_level(logging.INFO, logger="prashna")

    ok = asyncio.run(
        hub._safe_send(StalledSocket(), {"type": "secret-message"})
    )

    assert ok is False
    assert "ws.broadcast_failure" in _events(caplog)
    _assert_not_logged(caplog, ["secret-message"])


def test_diagnostic_helpers_filter_unsafe_field_names(caplog):
    """Local diagnostic helpers should share the secret-name filter."""
    from app.db import _log_diagnostic as log_db
    from app.ws import _log_diagnostic as log_ws

    caplog.set_level(logging.INFO, logger="prashna")

    log_db("db.test", secret_key="db-secret", outcome="success")
    log_ws("ws.test", session_token="ws-token", outcome="success")

    assert {"db.test", "ws.test"} <= _events(caplog)
    _assert_not_logged(caplog, ["db-secret", "ws-token"])


def test_sqlite_additive_migration_logs_execution(tmp_path, caplog):
    """Startup migrations should log each additive schema change."""
    from app.db import _apply_additive_migrations

    engine = create_engine(f"sqlite:///{tmp_path / 'diag.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")

    caplog.set_level(logging.INFO, logger="prashna")
    _apply_additive_migrations(bind=engine)

    assert "db.migration" in _events(caplog)
