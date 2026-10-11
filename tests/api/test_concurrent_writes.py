"""UC-X-05: a burst of concurrent participant writes against a real uvicorn
server completes promptly, without 5xx, and without freezing the event loop.

The in-process TestClient cannot reproduce this: the stall needs a real
event loop serving many async routes at once, each holding a database
connection until its request ends."""
from __future__ import annotations

import asyncio
import time

import httpx

from .test_secret_lifecycle import _setup_admin, _start_app, _stop_app

PARTICIPANTS = 40
BURST_DEADLINE_S = 15.0
STATUS_DEADLINE_S = 2.0


def _prepare_live_session(base_url: str) -> dict:
    """Admin creates a live session with one query and one live quiz run."""
    cookie = _setup_admin(base_url)
    with httpx.Client(base_url=base_url, cookies={"prashna_admin": cookie}, timeout=5.0) as c:
        quiz_id = c.post("/api/quizzes", json={"title": "Burst"}).json()["id"]
        question = c.post(f"/api/quizzes/{quiz_id}/questions",
                          json={"text": "2+2?", "qtype": "single"}).json()
        for text, correct in (("3", False), ("4", True)):
            r = c.post(f"/api/quiz_questions/{question['id']}/answers",
                       json={"text": text, "is_correct": correct})
            assert r.status_code == 200, r.text
        assert c.post(f"/api/quizzes/{quiz_id}/publish").status_code == 200
        code = c.post("/api/sessions", json={"title": "Burst"}).json()["code"]
        assert c.post(f"/api/sessions/{code}/start").status_code == 200
        query_id = c.post(f"/api/sessions/{code}/queries", json={"text": "Hi?"}).json()["id"]
        run_id = c.post(f"/api/sessions/{code}/quiz_runs", json={"quiz_id": quiz_id}).json()["id"]
        assert c.post(f"/api/sessions/{code}/quiz_runs/{run_id}/start").status_code == 200
        current = c.get(f"/api/sessions/{code}/quiz_runs/{run_id}").json()["current_question"]
    return {
        "code": code,
        "query_id": query_id,
        "run_id": run_id,
        "question_id": current["id"],
        "answer_id": current["answers"][1]["id"],
    }


async def _burst(base_url: str, live: dict) -> tuple[list, float]:
    """Fire the burst; return each write's response (or exception) and how
    long a status request issued during the burst took."""
    code = live["code"]
    clients = [httpx.AsyncClient(base_url=base_url, timeout=10.0) for _ in range(PARTICIPANTS)]
    tasks: list[asyncio.Future] = []
    try:
        # Each client becomes a distinct participant (its own voter_token).
        joins = await asyncio.gather(
            *(c.get(f"/api/sessions/{code}/participant-bootstrap") for c in clients))
        assert all(r.status_code == 200 for r in joins), [r.status_code for r in joins]

        for c in clients:
            tasks.append(asyncio.ensure_future(
                c.post(f"/api/sessions/{code}/queries/{live['query_id']}/vote")))
            tasks.append(asyncio.ensure_future(c.post(
                f"/api/sessions/{code}/quiz_runs/{live['run_id']}/submit",
                json={"question_id": live["question_id"], "answer_ids": [live["answer_id"]]},
            )))
            # The refetches a broadcast triggers on every participant page.
            tasks.append(asyncio.ensure_future(c.get(f"/api/sessions/{code}/queries")))
            tasks.append(asyncio.ensure_future(c.get(f"/api/sessions/{code}/quiz_runs")))

        await asyncio.sleep(0.05)
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as probe:
            started = time.perf_counter()
            try:
                status = await probe.get("/api/admin/status")
                assert status.status_code == 200, status.text
                status_elapsed = time.perf_counter() - started
            except httpx.TimeoutException:
                status_elapsed = float("inf")

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results, status_elapsed
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*(c.aclose() for c in clients), return_exceptions=True)


def _describe(result) -> str | None:
    """None for a 2xx response; otherwise a short description of the failure."""
    if isinstance(result, httpx.Response):
        if result.is_success:
            return None
        return f"{result.request.method} {result.request.url.path} -> {result.status_code}"
    return f"{type(result).__name__}: {result}"


async def test_uc_x_05_concurrent_writes_do_not_stall_the_server(tmp_path):
    """UC-X-05: 40 simultaneous votes and 40 simultaneous quiz submissions from
    distinct participants, with refetches, all succeed within 15 s, and a
    status request issued during the burst answers within 2 s."""
    proc, base_url = _start_app(tmp_path / "prashna.db", tmp_path / "uploads", "burst-secret")
    stalled = False
    results: list = []
    status_elapsed = burst_elapsed = float("inf")
    rows: list | Exception = []
    try:
        live = _prepare_live_session(base_url)
        started = time.perf_counter()
        try:
            results, status_elapsed = await asyncio.wait_for(
                _burst(base_url, live), timeout=BURST_DEADLINE_S)
        except TimeoutError:
            stalled = True
        else:
            burst_elapsed = time.perf_counter() - started
            try:
                rows = httpx.get(f"{base_url}/api/sessions/{live['code']}/queries",
                                 timeout=5.0).json()
            except httpx.HTTPError as exc:
                rows = exc
    finally:
        output = _stop_app(proc)

    assert not stalled, f"burst did not finish within {BURST_DEADLINE_S}s\n{output[-2000:]}"
    failures = [d for d in map(_describe, results) if d]
    assert not failures, f"{len(failures)} failed: {failures[:5]}\n{output[-2000:]}"
    assert status_elapsed < STATUS_DEADLINE_S, f"status took {status_elapsed:.2f}s"
    assert burst_elapsed < BURST_DEADLINE_S
    assert not isinstance(rows, Exception), f"vote count unreadable after the burst: {rows!r}"
    assert rows[0]["vote_count"] == PARTICIPANTS
