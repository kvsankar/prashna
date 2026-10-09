"""UC-A-23, UC-A-24, UC-M-03..UC-M-07, UC-X-06: quiz runs."""
from __future__ import annotations

import time

# ---------- UC-A-23: Global quiz runs report ----------

def test_uc_a_23_list_runs(admin_client, make_quiz, make_session):
    """UC-A-23: GET /api/quiz_runs returns shape."""
    q = make_quiz()
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs", json={"quiz_id": q["id"]})
    r = admin_client.get("/api/quiz_runs")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    for k in ("id", "status", "session_code", "session_title", "quiz_id", "quiz_title",
              "version_no", "current_question_idx", "question_count", "respondent_count",
              "created_at", "started_at", "closed_at"):
        assert k in rows[0]


def test_uc_a_23_aggregate_respondent_count(admin_client, make_quiz, make_session):
    """Run summaries count distinct respondents without loading submissions."""
    q = make_quiz()
    s = make_session()
    run = admin_client.post(
        f"/api/sessions/{s['code']}/quiz_runs",
        json={"quiz_id": q["id"]},
    ).json()
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        quiz_run = db.get_one(m.QuizRun, run["id"])
        question = quiz_run.quiz_version.questions[0]
        answer = question.answers[0]
        participants = [
            m.Participant(session_id=quiz_run.session_id, voter_token=f"perf-{idx}")
            for idx in range(2)
        ]
        db.add_all(participants)
        db.flush()
        db.add_all([
            m.QuizSubmission(
                quiz_run_id=quiz_run.id,
                question_id=question.id,
                answer_id=answer.id,
                participant_id=participant.id,
            )
            for participant in participants
        ])
        db.commit()

    row = admin_client.get("/api/quiz_runs").json()[0]
    assert row["question_count"] == 1
    assert row["respondent_count"] == 2


def test_projector_display_reads_do_not_create_participants(
    client, admin_client, make_quiz, make_session
):
    """Display-only projector requests must not create attendee identities."""
    q = make_quiz()
    s = make_session()
    admin_client.post(
        f"/api/sessions/{s['code']}/quiz_runs",
        json={"quiz_id": q["id"]},
    )
    client.cookies.clear()

    queries = client.get(f"/api/sessions/{s['code']}/queries?display=true")
    runs = client.get(f"/api/sessions/{s['code']}/quiz_runs?display=true")
    assert queries.status_code == 200
    assert runs.status_code == 200
    assert "voter_token" not in queries.cookies
    assert "voter_token" not in runs.cookies

    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        assert db.query(m.Participant).count() == 0


def test_uc_a_23_other_admin_runs_excluded(admin_client, make_quiz, make_session):
    """UC-A-23: rows from other admin's sessions are excluded."""
    q = make_quiz()
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs", json={"quiz_id": q["id"]})
    # Re-own the session to another user
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="oth23", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.query(m.Session).filter_by(code=s["code"]).one().owner_user_id = other.id
        db.commit()
    r = admin_client.get("/api/quiz_runs")
    assert r.json() == []


def test_uc_a_23_no_auth_401(client):
    """UC-A-23: no auth → 401."""
    r = client.get("/api/quiz_runs")
    assert r.status_code == 401


# ---------- UC-A-24: View results ----------

def test_uc_a_24_results_shape(admin_client, make_quiz, make_session):
    """UC-A-24: GET /api/quiz_runs/{id}/results returns expected shape."""
    q = make_quiz("MyQuiz")
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    r = admin_client.get(f"/api/quiz_runs/{run['id']}/results")
    assert r.status_code == 200
    body = r.json()
    for k in ("id", "status", "session_code", "session_title", "quiz_title",
              "version_no", "current_question_idx", "questions"):
        assert k in body
    assert body["quiz_title"] == "MyQuiz"


def test_uc_a_24_quiz_title_snapshotted(admin_client, make_quiz, make_session):
    """UC-A-24: renaming quiz doesn't change snapshot title."""
    q = make_quiz("OldName")
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    admin_client.patch(f"/api/quizzes/{q['id']}", json={"title": "NewName"})
    r = admin_client.get(f"/api/quiz_runs/{run['id']}/results")
    assert r.json()["quiz_title"] == "OldName"


def test_uc_a_24_other_admin_404(admin_client, make_quiz, make_session):
    """UC-A-24: run on other admin's session → 404."""
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="oth24", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.query(m.Session).filter_by(code=s["code"]).one().owner_user_id = other.id
        db.commit()
    r = admin_client.get(f"/api/quiz_runs/{run['id']}/results")
    assert r.status_code == 404


# ---------- UC-M-03: Queue quiz onto session ----------

def test_uc_m_03_queue_ready_quiz(admin_client, make_quiz, make_session):
    """UC-M-03: queueing a ready quiz → 200 with version_no."""
    q = make_quiz()
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                          json={"quiz_id": q["id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert "id" in body
    assert "version_no" in body


def test_uc_m_03_two_queues_reuse_version(admin_client, make_quiz, make_session):
    """UC-M-03: unedited quiz, two queues → same version_no."""
    q = make_quiz()
    s = make_session()
    r1 = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                           json={"quiz_id": q["id"]}).json()
    r2 = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                           json={"quiz_id": q["id"]}).json()
    assert r1["version_no"] == r2["version_no"]


def test_uc_m_03_edit_creates_new_version(admin_client, make_quiz, make_session):
    """UC-M-03: edit between queues → version_no advances."""
    q = make_quiz()
    s = make_session()
    r1 = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                           json={"quiz_id": q["id"]}).json()
    # edit a question
    time.sleep(0.01)
    admin_client.patch(f"/api/quiz_questions/{q['question_id']}",
                       json={"text": "Changed?"})
    r2 = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                           json={"quiz_id": q["id"]}).json()
    assert r2["version_no"] == r1["version_no"] + 1


def test_uc_m_03_draft_quiz_400(admin_client, make_session):
    """UC-M-03: draft quiz → 400."""
    qz = admin_client.post("/api/quizzes", json={"title": "Draft"}).json()
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                          json={"quiz_id": qz["id"]})
    assert r.status_code == 400
    assert r.json() == {"detail": "Quiz is still a draft — publish it first"}


def test_uc_m_03_unknown_quiz_404(admin_client, make_session):
    """UC-M-03: unknown quiz_id → 404."""
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                          json={"quiz_id": 99999})
    assert r.status_code == 404
    assert r.json() == {"detail": "quiz not found"}


def test_uc_m_03_quiz_other_owner_404(admin_client, make_quiz, make_session):
    """UC-M-03: quiz owned by other admin → 404."""
    q = make_quiz()
    s = make_session()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="othM03", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get_one(m.Quiz, q["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                          json={"quiz_id": q["id"]})
    assert r.status_code == 404
    assert r.json() == {"detail": "quiz not found"}


def test_uc_m_03_ended_session_400(admin_client, make_quiz, make_session):
    """UC-M-03: queue on ended session → 400."""
    q = make_quiz()
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/end")
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                          json={"quiz_id": q["id"]})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session has ended"}


def test_uc_m_03_no_auth_403(client, admin_client, make_quiz, make_session):
    """UC-M-03: no auth → 403."""
    q = make_quiz()
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs",
                    json={"quiz_id": q["id"]})
    assert r.status_code == 403


def _valid_draft(admin_client, title: str = "Draft") -> int:
    """A draft quiz that would pass publish validation."""
    qid = admin_client.post("/api/quizzes", json={"title": title}).json()["id"]
    question = admin_client.post(f"/api/quizzes/{qid}/questions",
                                 json={"text": "2+2?", "qtype": "single"}).json()["id"]
    admin_client.post(f"/api/quiz_questions/{question}/answers", json={"text": "3"})
    admin_client.post(f"/api/quiz_questions/{question}/answers",
                      json={"text": "4", "is_correct": True})
    return qid


def _run_count(admin_client, code: str) -> int:
    return len(admin_client.get(f"/api/sessions/{code}/quiz_runs").json())


def test_uc_m_03_publish_and_add_valid_draft(admin_client, make_session):
    """UC-M-03: publish=true on a valid draft publishes it and queues a run."""
    qid = _valid_draft(admin_client)
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                          json={"quiz_id": qid, "publish": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued"
    assert admin_client.get(f"/api/quizzes/{qid}").json()["status"] == "ready"
    assert _run_count(admin_client, s["code"]) == 1


def test_uc_m_03_publish_and_add_invalid_draft_400(admin_client, make_session):
    """UC-M-03: publish=true on an invalid draft → publish validation 400; nothing changes."""
    qid = admin_client.post("/api/quizzes", json={"title": "Empty"}).json()["id"]
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                          json={"quiz_id": qid, "publish": True})
    assert r.status_code == 400
    assert r.json() == {"detail": "Quiz needs at least one question"}
    assert admin_client.get(f"/api/quizzes/{qid}").json()["status"] == "draft"
    assert _run_count(admin_client, s["code"]) == 0


def test_uc_m_03_publish_and_add_delegate_403(admin_client, make_session, mod_headers):
    """UC-M-03: a delegate can't publish a draft via publish=true."""
    qid = _valid_draft(admin_client)
    s = make_session()
    admin_client.cookies.clear()
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                          json={"quiz_id": qid, "publish": True},
                          headers=mod_headers(s["mod_key"]))
    assert r.status_code == 403
    assert r.json() == {"detail": "Only the admin can publish a draft quiz"}
    runs = admin_client.get(f"/api/sessions/{s['code']}/quiz_runs",
                            headers=mod_headers(s["mod_key"])).json()
    assert runs == []


def test_uc_m_03_publish_flag_ignored_for_ready_quiz(admin_client, make_quiz, make_session, mod_headers):
    """UC-M-03: publish=true on a ready quiz is a no-op, so delegates may send it."""
    q = make_quiz()
    s = make_session()
    admin_client.cookies.clear()
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                          json={"quiz_id": q["id"], "publish": True},
                          headers=mod_headers(s["mod_key"]))
    assert r.status_code == 200, r.text


def test_uc_m_03_available_quizzes_drafts_for_owner_only(admin_client, make_quiz, make_session, mod_headers):
    """UC-M-03: the owner's picker includes drafts; a delegate's doesn't."""
    ready = make_quiz("Ready one")
    draft = admin_client.post("/api/quizzes", json={"title": "Draft one"}).json()
    s = make_session()
    path = f"/api/sessions/{s['code']}/available_quizzes"
    owner = {q["id"]: q["status"] for q in admin_client.get(path).json()}
    assert owner == {ready["id"]: "ready", draft["id"]: "draft"}
    boot = admin_client.get(f"/api/sessions/{s['code']}/moderator-bootstrap").json()
    assert {q["id"] for q in boot["available_quizzes"]} == {ready["id"], draft["id"]}
    admin_client.cookies.clear()
    delegate = admin_client.get(path, headers=mod_headers(s["mod_key"])).json()
    assert [q["id"] for q in delegate] == [ready["id"]]


def test_uc_m_03_available_quizzes_report_in_session(admin_client, make_quiz, make_session):
    """UC-M-03: in_session is null until queued, then reports the run state here."""
    q = make_quiz("membership")
    s = make_session()
    other = make_session("other")
    path = f"/api/sessions/{s['code']}/available_quizzes"

    def entry():
        return next(x for x in admin_client.get(path).json() if x["id"] == q["id"])

    assert entry()["in_session"] is None
    admin_client.post(f"/api/sessions/{other['code']}/quiz_runs", json={"quiz_id": q["id"]})
    assert entry()["in_session"] is None  # a run elsewhere doesn't count here
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs", json={"quiz_id": q["id"]}).json()
    assert entry()["in_session"] == {"run_status": "queued", "run_count": 1}
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    assert entry()["in_session"] == {"run_status": "live", "run_count": 1}
    boot = admin_client.get(f"/api/sessions/{s['code']}/moderator-bootstrap").json()
    assert next(x for x in boot["available_quizzes"] if x["id"] == q["id"])["in_session"]["run_status"] == "live"


# ---------- UC-M-04: Start a queued quiz run ----------

def _queue_run(admin_client, make_quiz, make_session):
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    return s, q, run


def test_uc_m_04_start_queued(admin_client, make_quiz, make_session):
    """UC-M-04: start queued → ok and session auto-advances."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # session is now live
    s2 = admin_client.get(f"/api/sessions/{s['code']}").json()
    assert s2["status"] == "live"


def test_uc_m_04_another_live_409(admin_client, make_quiz, make_session):
    """UC-M-04: starting while another live → 409."""
    q = make_quiz()
    s = make_session()
    r1 = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                           json={"quiz_id": q["id"]}).json()
    r2 = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                           json={"quiz_id": q["id"]}).json()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{r1['id']}/start")
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{r2['id']}/start")
    assert r.status_code == 409
    assert r.json() == {"detail": "Another quiz is already live — close it first."}


def test_uc_m_04_start_already_live_400(admin_client, make_quiz, make_session):
    """UC-M-04: start a non-queued run → 400."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    assert r.status_code == 400
    assert r.json() == {"detail": "Cannot start from status: live"}


def test_uc_m_04_start_queued_in_ended_session_400(admin_client, make_quiz, make_session):
    """UC-M-04: legacy queued runs cannot be started after session end."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        session = db.query(m.Session).filter_by(code=s["code"]).one()
        session.status = "ended"
        db.commit()

    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    assert r.status_code == 400
    assert r.json() == {"detail": "Session has ended"}


def test_uc_m_04_unknown_run_404(admin_client, make_session):
    """UC-M-04: unknown run id → 404."""
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/99999/start")
    assert r.status_code == 404


def test_uc_m_04_no_auth_403(client, admin_client, make_quiz, make_session):
    """UC-M-04: no auth → 403."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    assert r.status_code == 403


# ---------- UC-M-05: Walk through questions ----------

def test_uc_m_05_reveal(admin_client, make_quiz, make_session):
    """UC-M-05: reveal → 200, reveal_current true."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/reveal",
                          json={"reveal": True})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_m_05_advance_next_prev(admin_client, admin_creds):
    """UC-M-05: advance next / prev with a multi-Q quiz."""
    # build quiz with 2 questions
    qz = admin_client.post("/api/quizzes", json={"title": "Multi"}).json()
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
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/advance",
                          json={"direction": "next"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # verify idx advanced
    g = admin_client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    assert g["current_question_idx"] == 1
    # prev
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/advance",
                      json={"direction": "prev"})
    g = admin_client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    assert g["current_question_idx"] == 0


def test_uc_m_05_advance_to_index(admin_client):
    """UC-M-05: advance to index."""
    qz = admin_client.post("/api/quizzes", json={"title": "M"}).json()
    for i in range(3):
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
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/advance",
                      json={"direction": "to", "index": 2})
    g = admin_client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    assert g["current_question_idx"] == 2


def test_uc_m_05_advance_to_non_int_400(admin_client, make_quiz, make_session):
    """UC-M-05: 'to' with non-int → 400."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/advance",
                          json={"direction": "to", "index": "x"})
    assert r.status_code == 400
    assert r.json() == {"detail": "index must be an integer"}


def test_uc_m_05_live_counts_toggle(admin_client, make_quiz, make_session):
    """UC-M-05: live_counts on/off."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts",
                          json={"show": True})
    assert r.status_code == 200
    assert r.json() == {"show_live_counts": True}
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts",
                          json={"show": False})
    assert r.json() == {"show_live_counts": False}


def test_uc_m_05_no_auth_403(client, admin_client, make_quiz, make_session):
    """UC-M-05: no auth → 403 on reveal."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/reveal",
                    json={"reveal": True})
    assert r.status_code == 403


# ---------- UC-M-06: Close ----------

def test_uc_m_06_close_run(admin_client, make_quiz, make_session):
    """UC-M-06: close live run → ok."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    g = admin_client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    assert g["status"] == "closed"
    assert g["reveal_current"] is True


def test_uc_m_06_submit_after_close_404(admin_client, make_quiz, make_session):
    """UC-M-06: after close, submit → 404 Quiz not live."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    # grab current question + answer
    g = admin_client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    qid = g["current_question"]["id"]
    aid = g["current_question"]["answers"][0]["id"]
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close")
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                          json={"question_id": qid, "answer_ids": [aid]})
    assert r.status_code == 404
    assert r.json() == {"detail": "Quiz not live"}


def test_uc_m_06_no_auth_403(client, admin_client, make_quiz, make_session):
    """UC-M-06: no auth → 403."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close")
    assert r.status_code == 403


# ---------- UC-M-07: Remove a quiz run ----------

def test_uc_m_07_delete_queued(admin_client, make_quiz, make_session):
    """UC-M-07: delete a queued run → ok."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    r = admin_client.request("DELETE", f"/api/sessions/{s['code']}/quiz_runs/{run['id']}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_m_07_delete_legacy_queued_from_ended_session(
    admin_client, make_quiz, make_session
):
    """UC-M-07: an orphaned queued run remains removable after session end."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        session = db.query(m.Session).filter_by(code=s["code"]).one()
        session.status = "ended"
        db.commit()

    r = admin_client.request("DELETE", f"/api/sessions/{s['code']}/quiz_runs/{run['id']}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_m_07_delete_live(admin_client, make_quiz, make_session):
    """UC-M-07: delete a live run → ok."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    r = admin_client.request("DELETE", f"/api/sessions/{s['code']}/quiz_runs/{run['id']}")
    assert r.status_code == 200


def test_uc_m_07_delete_closed_400(admin_client, make_quiz, make_session):
    """UC-M-07: delete closed → 400."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close")
    r = admin_client.request("DELETE", f"/api/sessions/{s['code']}/quiz_runs/{run['id']}")
    assert r.status_code == 400
    assert r.json() == {"detail": "Closed quiz runs are historical and cannot be deleted"}


def test_uc_m_07_no_auth_403(client, admin_client, make_quiz, make_session):
    """UC-M-07: no auth → 403."""
    s, q, run = _queue_run(admin_client, make_quiz, make_session)
    admin_client.cookies.clear()
    r = client.request("DELETE", f"/api/sessions/{s['code']}/quiz_runs/{run['id']}")
    assert r.status_code == 403


# ---------- UC-X-06: Versioning lazy capture ----------

def test_uc_x_06_first_queue_v1(admin_client, make_quiz, make_session):
    """UC-X-06: first queue → v1."""
    q = make_quiz()
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                          json={"quiz_id": q["id"]}).json()
    assert r["version_no"] == 1


def test_uc_x_06_two_queues_unedited_same_version(admin_client, make_quiz, make_session):
    """UC-X-06: two unedited queues reuse v1."""
    q = make_quiz()
    s = make_session()
    r1 = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                           json={"quiz_id": q["id"]}).json()
    r2 = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                           json={"quiz_id": q["id"]}).json()
    assert r1["version_no"] == r2["version_no"] == 1


def test_uc_x_06_edit_creates_v2(admin_client, make_quiz, make_session):
    """UC-X-06: edit after queue → v2."""
    q = make_quiz()
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                      json={"quiz_id": q["id"]})
    time.sleep(0.01)
    admin_client.patch(f"/api/quiz_questions/{q['question_id']}",
                       json={"text": "Edited"})
    r2 = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                           json={"quiz_id": q["id"]}).json()
    assert r2["version_no"] == 2


def test_uc_x_06_integrity_race_returns_winning_version(
    app_module,
    make_quiz,
    monkeypatch,
):
    """UC-X-06: duplicate-version integrity race returns the winning version."""
    q = make_quiz()
    with app_module.SessionLocal() as db:
        quiz = db.get(app_module.m.Quiz, q["id"])
        assert quiz is not None
        winner = app_module.m.QuizVersion(
            quiz_id=quiz.id,
            version_no=1,
            quiz_title=quiz.title,
        )
        calls = {"latest": 0}

        def fake_latest(_db, _quiz):
            calls["latest"] += 1
            return None if calls["latest"] == 1 else winner

        def fake_flush():
            raise app_module.IntegrityError("insert quiz version", {}, Exception())

        monkeypatch.setattr(app_module, "_latest_version", fake_latest)
        monkeypatch.setattr(db, "flush", fake_flush)

        assert app_module._ensure_current_version(db, quiz) is winner
        assert calls["latest"] == 2
