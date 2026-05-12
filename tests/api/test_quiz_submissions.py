"""UC-P-07, UC-P-08, UC-P-09, UC-P-12: participant quiz submissions and visibility."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _live_run(admin_client, make_quiz, make_session):
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    return s, q, run


# ---------- UC-P-07: See live quiz ----------

def test_uc_p_07_list_runs_includes_queued(client, admin_client, make_quiz, make_session):
    """UC-P-07: queued runs are returned to non-mods (powers UC-D-07 lobby
    on the projector). Participant UI ignores queued in its own render
    — only the projector treats it as a lobby state."""
    q = make_quiz()
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                      json={"quiz_id": q["id"]})  # queued
    admin_client.cookies.clear()
    rows = client.get(f"/api/sessions/{s['code']}/quiz_runs").json()
    assert len(rows) == 1
    assert rows[0]["status"] == "queued"


def test_uc_p_07_live_run_visible(client, admin_client, make_quiz, make_session):
    """UC-P-07: live run is returned for participants with current_question."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.cookies.clear()
    rows = client.get(f"/api/sessions/{s['code']}/quiz_runs").json()
    assert len(rows) == 1
    r0 = rows[0]
    assert r0["current_question"] is not None
    # is_correct omitted while not revealed
    for a in r0["current_question"]["answers"]:
        assert "is_correct" not in a


def test_uc_p_07_closed_run_has_correctness(client, admin_client, make_quiz, make_session):
    """UC-P-07: closed run reveals is_correct."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close")
    admin_client.cookies.clear()
    rows = client.get(f"/api/sessions/{s['code']}/quiz_runs").json()
    r0 = rows[0]
    for a in r0["current_question"]["answers"]:
        assert "is_correct" in a
    assert r0["results"] is not None


# ---------- UC-P-08: Submit answer ----------

def test_uc_p_08_submit_ok(client, admin_client, make_quiz, make_session):
    """UC-P-08: submit answer → ok and replaces prior."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.cookies.clear()
    g = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    qid = g["current_question"]["id"]
    aid = g["current_question"]["answers"][0]["id"]
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                    json={"question_id": qid, "answer_ids": [aid]})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_p_08_resubmit_replaces(client, admin_client, make_quiz, make_session):
    """UC-P-08: resubmit replaces prior."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.cookies.clear()
    g = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    qid = g["current_question"]["id"]
    a1, a2 = [a["id"] for a in g["current_question"]["answers"]]
    client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                json={"question_id": qid, "answer_ids": [a1]})
    client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                json={"question_id": qid, "answer_ids": [a2]})
    g2 = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    assert g2["my_selections"] == [a2]


def test_uc_p_08_invalid_answer_400(client, admin_client, make_quiz, make_session):
    """UC-P-08: answer not in current question → 400 Invalid answer."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.cookies.clear()
    g = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    qid = g["current_question"]["id"]
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                    json={"question_id": qid, "answer_ids": [99999]})
    assert r.status_code == 400
    assert r.json() == {"detail": "Invalid answer"}


def test_uc_p_08_answer_ids_not_list_400(client, admin_client, make_quiz, make_session):
    """UC-P-08: answer_ids not list → 400."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.cookies.clear()
    g = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    qid = g["current_question"]["id"]
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                    json={"question_id": qid, "answer_ids": "notalist"})
    assert r.status_code == 400
    assert r.json() == {"detail": "answer_ids must be a list"}


def test_uc_p_08_answer_ids_non_int_400(client, admin_client, make_quiz, make_session):
    """UC-P-08: non-int entries → 400."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.cookies.clear()
    g = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    qid = g["current_question"]["id"]
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                    json={"question_id": qid, "answer_ids": ["abc"]})
    assert r.status_code == 400
    assert r.json() == {"detail": "answer_ids must be integers"}


def test_uc_p_08_wrong_question_id_404(client, admin_client, make_quiz, make_session):
    """UC-P-08: question_id not in this run's version → 404."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                    json={"question_id": 99999, "answer_ids": []})
    assert r.status_code == 404
    assert r.json() == {"detail": "Question not in this quiz run"}


def test_uc_p_08_not_current_question_400(admin_client):
    """UC-P-08: question_id valid but not current → 400."""
    # build 2-question quiz
    qz = admin_client.post("/api/quizzes", json={"title": "T"}).json()
    for i in range(2):
        q = admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                              json={"text": f"Q{i}?", "qtype": "single"}).json()
        admin_client.post(f"/api/quiz_questions/{q['id']}/answers",
                          json={"text": "a", "is_correct": True})
        admin_client.post(f"/api/quiz_questions/{q['id']}/answers", json={"text": "b"})
    admin_client.post(f"/api/quizzes/{qz['id']}/publish")
    s = admin_client.post("/api/sessions", json={"title": "S"}).json()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": qz["id"]}).json()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    # advance to question 2, then try to submit question 1
    g = admin_client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    first_qid = g["current_question"]["id"]
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/advance",
                      json={"direction": "next"})
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                          json={"question_id": first_qid, "answer_ids": []})
    assert r.status_code == 400
    assert r.json() == {"detail": "Not the current question"}


def test_uc_p_08_single_two_answers_400(client, admin_client, make_quiz, make_session):
    """UC-P-08: single-type with > 1 answer → 400 Only one answer allowed."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.cookies.clear()
    g = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    qid = g["current_question"]["id"]
    aids = [a["id"] for a in g["current_question"]["answers"]]
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                    json={"question_id": qid, "answer_ids": aids})
    assert r.status_code == 400
    assert r.json() == {"detail": "Only one answer allowed"}


def test_uc_p_08_not_live_404(client, admin_client, make_quiz, make_session):
    """UC-P-08: run queued → 404 Quiz not live."""
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                    json={"question_id": 0, "answer_ids": []})
    assert r.status_code == 404
    assert r.json() == {"detail": "Quiz not live"}


def test_uc_p_08_ended_session_400(client, admin_client, make_quiz, make_session):
    """UC-P-08: ended session → 400 Session has ended."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/end")
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                    json={"question_id": 0, "answer_ids": []})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session has ended"}


# ---------- UC-P-09: Results on reveal/close ----------

def test_uc_p_09_reveal_shows_correct_and_results(client, admin_client, make_quiz, make_session):
    """UC-P-09: after reveal, is_correct + results visible to participant."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/reveal",
                      json={"reveal": True})
    admin_client.cookies.clear()
    g = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    for a in g["current_question"]["answers"]:
        assert "is_correct" in a
    assert g["results"] is not None
    for k in ("question_id", "respondents", "totals"):
        assert k in g["results"]


def test_uc_p_09_closed_run_results(client, admin_client, make_quiz, make_session):
    """UC-P-09: after close, results visible."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close")
    admin_client.cookies.clear()
    g = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    assert g["status"] == "closed"
    assert g["reveal_current"] is True
    assert g["results"] is not None


# ---------- UC-P-12: Live counts ----------

def test_uc_p_12_live_counts_on(client, admin_client, make_quiz, make_session):
    """UC-P-12: show_live_counts=true → results returned, is_correct omitted."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts",
                      json={"show": True})
    admin_client.cookies.clear()
    g = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    assert g["results"] is not None
    for a in g["current_question"]["answers"]:
        assert "is_correct" not in a


def test_uc_p_12_live_counts_off_default(client, admin_client, make_quiz, make_session):
    """UC-P-12: default off → results is null in answering phase."""
    s, q, run = _live_run(admin_client, make_quiz, make_session)
    admin_client.cookies.clear()
    g = client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    assert g["results"] is None
