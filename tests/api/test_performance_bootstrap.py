from __future__ import annotations

import logging

from sqlalchemy import func, select

PAGE_BROWSER_CACHE = "public, max-age=0, must-revalidate"
PAGE_CDN_CACHE = "public, s-maxage=300, stale-while-revalidate=60"


def _participant_count() -> int:
    from prashna import models as m
    from prashna.db import SessionLocal

    with SessionLocal() as db:
        return db.scalar(select(func.count(m.Participant.id))) or 0


def test_participant_bootstrap_returns_one_snapshot_and_one_identity(
    admin_client,
    make_session,
):
    session = make_session()
    admin_client.cookies.clear()

    response = admin_client.get(
        f"/api/sessions/{session['code']}/participant-bootstrap"
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "session",
        "me",
        "queries",
        "quiz_runs",
        "feedback",
    }
    assert response.json()["session"]["code"] == session["code"]
    assert response.json()["me"]["name"] is None
    assert response.json()["queries"] == []
    assert response.json()["quiz_runs"] == []
    assert response.json()["feedback"] is None
    assert "voter_token=" in response.headers["set-cookie"]
    assert "httponly" not in response.headers["set-cookie"].lower()
    assert _participant_count() == 1

    again = admin_client.get(
        f"/api/sessions/{session['code']}/participant-bootstrap"
    )
    assert again.status_code == 200
    assert again.json()["me"]["id"] == response.json()["me"]["id"]
    assert _participant_count() == 1


def test_moderator_bootstrap_accepts_owner_or_delegate(
    admin_client,
    make_quiz,
    make_session,
    mod_headers,
):
    quiz = make_quiz("Bootstrap quiz")
    session = make_session()
    path = f"/api/sessions/{session['code']}/moderator-bootstrap"

    owner = admin_client.get(path)
    assert owner.status_code == 200
    assert owner.json()["is_owner"] is True
    assert owner.json()["session"]["code"] == session["code"]
    assert owner.json()["available_quizzes"] == [
        {
            "id": quiz["id"],
            "title": "Bootstrap quiz",
            "status": "ready",
            "question_count": 1,
            "in_session": None,
        }
    ]

    admin_client.cookies.clear()
    assert admin_client.get(path).status_code == 403
    assert admin_client.get(path, headers=mod_headers("wrong")).status_code == 403

    delegate = admin_client.get(path, headers=mod_headers(session["mod_key"]))
    assert delegate.status_code == 200
    assert delegate.json()["is_owner"] is False
    assert delegate.json()["available_quizzes"][0]["id"] == quiz["id"]


def test_display_bootstrap_is_public_and_does_not_create_a_participant(
    admin_client,
    make_session,
):
    session = make_session()
    admin_client.cookies.clear()
    assert _participant_count() == 0

    response = admin_client.get(
        f"/api/sessions/{session['code']}/display-bootstrap"
    )

    assert response.status_code == 200
    assert set(response.json()) == {"session", "queries", "quiz_runs"}
    assert response.json()["session"]["code"] == session["code"]
    assert response.json()["queries"] == []
    assert response.json()["quiz_runs"] == []
    assert "voter_token=" not in response.headers.get("set-cookie", "")
    assert _participant_count() == 0


def test_html_shells_are_edge_cacheable_but_redirects_and_apis_are_not(
    admin_client,
    make_session,
):
    session = make_session()
    for path in (
        "/",
        "/quizzes",
        f"/s/{session['code']}",
        f"/m/{session['code']}",
        f"/p/{session['code']}",
    ):
        response = admin_client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == PAGE_BROWSER_CACHE, path
        assert response.headers["cdn-cache-control"] == PAGE_CDN_CACHE, path

    redirect = admin_client.get("/s/NOPE99", follow_redirects=False)
    assert redirect.status_code == 303
    assert redirect.headers["cache-control"] == "no-store"
    assert "cdn-cache-control" not in redirect.headers

    api = admin_client.get("/api/admin/status")
    assert api.headers["cache-control"] == "no-store"
    assert "cdn-cache-control" not in api.headers


def test_performance_beacon_logs_only_bounded_safe_fields(
    client,
    caplog,
):
    caplog.set_level(logging.INFO, logger="prashna")
    secret = "must-not-appear"

    response = client.post(
        "/api/diagnostics/performance",
        headers={"CF-Ray": "0123456789abcdef-SIN"},
        json={
            "role": "landing",
            "usable_ms": 412.4,
            "dcl_ms": 210.1,
            "fcp_ms": 230.2,
            "app_server_ms": 4.2,
            "protocol": "h3",
            "navigation_type": "navigate",
            "token": secret,
        },
    )

    assert response.status_code == 204
    records = [
        record
        for record in caplog.records
        if record.__dict__.get("diag_event") == "performance.usable"
    ]
    assert len(records) == 1
    record = records[0]
    assert record.__dict__["diag_role"] == "landing"
    assert record.__dict__["diag_cf_colo"] == "SIN"
    assert record.__dict__["diag_usable_ms"] == 412.4
    assert secret not in record.getMessage()


def test_performance_beacon_ignores_invalid_samples(client, caplog):
    caplog.set_level(logging.INFO, logger="prashna")

    response = client.post(
        "/api/diagnostics/performance",
        json={"role": "session/SECRET", "usable_ms": 999999},
    )

    assert response.status_code == 204
    assert not any(
        record.__dict__.get("diag_event") == "performance.usable"
        for record in caplog.records
    )
