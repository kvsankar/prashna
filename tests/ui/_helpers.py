"""Helpers shared by UI tests.

Drives the API directly with `httpx` to set up state — Playwright is used
only for the interactive bit being tested.

The uvicorn process is session-scoped (shared DB), so:

  * tests should NOT assume row counts; instead create their own
    fresh sessions / quizzes whose codes/ids they keep.
  * Playwright contexts are per-test by default → cookie isolation.
"""
from __future__ import annotations

import secrets
from typing import Any

import httpx

from ..support import SETUP_TOKEN

ADMIN = {"username": "admin", "password": "testpass1"}


def api_login(base_url: str) -> httpx.Client:
    """Return an httpx.Client authenticated as the admin (cookie set).

    Idempotently ensures the admin exists first.
    """
    c = httpx.Client(base_url=base_url, timeout=10.0)
    # Either setup (first run) or login.
    r = c.post("/api/admin/setup", json={**ADMIN, "setup_token": SETUP_TOKEN})
    if r.status_code == 409:
        r = c.post("/api/admin/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return c


def api_make_session(client: httpx.Client, title: str | None = None) -> dict[str, Any]:
    """Create a fresh session as the logged-in admin. Returns the JSON dict."""
    title = title or f"UI Test {secrets.token_hex(4)}"
    r = client.post("/api/sessions", json={"title": title})
    assert r.status_code == 200, r.text
    return r.json()


def api_start_session(client: httpx.Client, code: str) -> None:
    r = client.post(f"/api/sessions/{code}/start")
    assert r.status_code == 200, r.text


def api_end_session(client: httpx.Client, code: str) -> None:
    r = client.post(f"/api/sessions/{code}/end")
    assert r.status_code == 200, r.text


def api_make_quiz(
    client: httpx.Client,
    title: str | None = None,
    *,
    publish: bool = False,
    questions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a quiz, optionally with questions and publishing.

    `questions` is a list of {text, qtype, graded, answers: [{text, is_correct}, ...]};
    `graded` defaults to True (False makes a poll question).
    Defaults to a minimal valid published-ready quiz when publish=True.
    """
    title = title or f"UI Quiz {secrets.token_hex(4)}"
    r = client.post("/api/quizzes", json={"title": title})
    assert r.status_code == 200, r.text
    quiz = r.json()
    if questions is None and publish:
        questions = [
            {
                "text": "2+2?",
                "qtype": "single",
                "answers": [
                    {"text": "3", "is_correct": False},
                    {"text": "4", "is_correct": True},
                ],
            }
        ]
    for q in questions or []:
        rr = client.post(
            f"/api/quizzes/{quiz['id']}/questions",
            json={"text": q["text"], "qtype": q.get("qtype", "single"), "graded": q.get("graded", True)},
        )
        assert rr.status_code == 200, rr.text
        qid = rr.json()["id"]
        for a in q.get("answers", []):
            ra = client.post(
                f"/api/quiz_questions/{qid}/answers",
                json={"text": a["text"]},
            )
            assert ra.status_code == 200, ra.text
            aid = ra.json()["id"]
            if a.get("is_correct"):
                client.patch(
                    f"/api/quiz_answers/{aid}",
                    json={"is_correct": True},
                ).raise_for_status()
    if publish:
        rp = client.post(f"/api/quizzes/{quiz['id']}/publish")
        assert rp.status_code == 200, rp.text
        quiz["status"] = "ready"
    return quiz


def api_queue_quiz_run(client: httpx.Client, code: str, quiz_id: int) -> dict[str, Any]:
    r = client.post(f"/api/sessions/{code}/quiz_runs", json={"quiz_id": quiz_id})
    assert r.status_code == 200, r.text
    return r.json()


def admin_login_via_ui(page, base_url: str) -> None:
    """Log into the admin in a Playwright page. Assumes admin already exists."""
    page.goto(base_url + "/")
    # Wait for either login or sessions card.
    page.wait_for_function(
        "!document.querySelector('#login-card').hidden || "
        "!document.querySelector('#sessions-card').hidden"
    )
    if page.locator("#sessions-card").is_visible():
        return  # somehow already authed
    page.fill("#li-user", ADMIN["username"])
    page.fill("#li-pass", ADMIN["password"])
    page.click("#li-btn")
    page.wait_for_selector("#sessions-card:visible")


def ask_query_api(client_or_url, code: str, text: str, *, voter_token: str | None = None) -> dict:
    """POST a query as a participant. `client_or_url` is httpx.Client OR a base_url string."""
    if isinstance(client_or_url, str):
        cookies = {"voter_token": voter_token} if voter_token else None
        r = httpx.post(
            f"{client_or_url}/api/sessions/{code}/queries",
            json={"text": text},
            cookies=cookies,
            timeout=5.0,
        )
    else:
        r = client_or_url.post(f"/api/sessions/{code}/queries", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()
