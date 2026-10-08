"""UC-A-09 through UC-A-22 and UC-A-27: quiz CRUD, items, answers, publish, uploads, duplicate."""
from __future__ import annotations

import re

# ---------- UC-A-09: Create quiz template ----------

def test_uc_a_09_create_quiz(admin_client):
    """UC-A-09: create returns draft quiz."""
    r = admin_client.post("/api/quizzes", json={"title": "Trivia"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Trivia"
    assert body["status"] == "draft"
    assert "id" in body


def test_uc_a_09_empty_title_default(admin_client):
    """UC-A-09: empty title → 'Untitled quiz' default."""
    r = admin_client.post("/api/quizzes", json={"title": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Untitled quiz"
    assert body["status"] == "draft"


def test_uc_a_09_no_auth_401(client):
    """UC-A-09: no auth → 401."""
    r = client.post("/api/quizzes", json={"title": "x"})
    assert r.status_code == 401


# ---------- UC-A-10: Browse library ----------

def test_uc_a_10_list_quizzes(admin_client, make_quiz):
    """UC-A-10: list returns owned quizzes with shape."""
    make_quiz("Q1")
    r = admin_client.get("/api/quizzes")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    for k in ("id", "title", "status", "question_count"):
        assert k in rows[0]


def test_uc_a_10_aggregate_question_count(admin_client, make_quiz):
    """Quiz summaries count questions without loading answer trees."""
    quiz = make_quiz("two questions")
    admin_client.post(
        f"/api/quizzes/{quiz['id']}/questions",
        json={"text": "Second?", "qtype": "single"},
    )
    rows = admin_client.get("/api/quizzes").json()
    row = next(item for item in rows if item["id"] == quiz["id"])
    assert row["question_count"] == 2


def test_uc_a_10_other_admins_quiz_excluded(admin_client, make_quiz):
    """UC-A-10: another admin's quiz not in response."""
    make_quiz("mine")
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="other_q", password_hash=auth.hash_password("longenough"))
        db.add(other)
        db.commit()
        db.refresh(other)
        q = m.Quiz(title="other-quiz", owner_user_id=other.id)
        db.add(q)
        db.commit()
    rows = admin_client.get("/api/quizzes").json()
    titles = [r["title"] for r in rows]
    assert "other-quiz" not in titles


def test_uc_a_10_ready_only_filter(admin_client, make_quiz):
    """UC-A-10: ready_only=true filters drafts."""
    make_quiz("ready1")  # auto-published
    admin_client.post("/api/quizzes", json={"title": "draftQ"})  # draft
    r = admin_client.get("/api/quizzes?ready_only=true")
    rows = r.json()
    assert all(row["status"] == "ready" for row in rows)
    assert any(row["title"] == "ready1" for row in rows)
    assert not any(row["title"] == "draftQ" for row in rows)


def test_uc_a_10_no_auth_401(client):
    """UC-A-10: no auth → 401."""
    r = client.get("/api/quizzes")
    assert r.status_code == 401


# ---------- UC-A-11: Open quiz for editing ----------

def test_uc_a_11_get_quiz_with_correct(admin_client, make_quiz):
    """UC-A-11: include_correct=true returns is_correct."""
    q = make_quiz()
    r = admin_client.get(f"/api/quizzes/{q['id']}?include_correct=true")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == q["id"]
    assert body["title"] == q["title"]
    # one question, two answers
    assert len(body["questions"]) == 1
    for a in body["questions"][0]["answers"]:
        assert "is_correct" in a


def test_uc_a_11_get_quiz_default_omits_correct(admin_client, make_quiz):
    """UC-A-11: default omits is_correct."""
    q = make_quiz()
    r = admin_client.get(f"/api/quizzes/{q['id']}")
    body = r.json()
    for a in body["questions"][0]["answers"]:
        assert "is_correct" not in a


def test_uc_a_11_non_owner_404(admin_client, make_quiz):
    """UC-A-11: non-owner → 404."""
    q = make_quiz()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="other_open", password_hash=auth.hash_password("longenough"))
        db.add(other)
        db.commit()
        db.refresh(other)
        qz = db.get(m.Quiz, q["id"])
        qz.owner_user_id = other.id
        db.commit()
    r = admin_client.get(f"/api/quizzes/{q['id']}")
    assert r.status_code == 404


def test_uc_a_11_nonexistent_404(admin_client):
    """UC-A-11: nonexistent id → 404."""
    r = admin_client.get("/api/quizzes/99999")
    assert r.status_code == 404


def test_uc_a_11_no_auth_404(client, admin_client, make_quiz):
    """UC-A-11: no auth → 404 (handler returns 404 for non-owner)."""
    q = make_quiz()
    admin_client.cookies.clear()
    r = client.get(f"/api/quizzes/{q['id']}")
    assert r.status_code == 404


# ---------- UC-A-12: Rename quiz ----------

def test_uc_a_12_rename(admin_client, make_quiz):
    """UC-A-12: PATCH new title → ok."""
    q = make_quiz("orig")
    r = admin_client.patch(f"/api/quizzes/{q['id']}", json={"title": "New"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # verify title persisted
    g = admin_client.get(f"/api/quizzes/{q['id']}").json()
    assert g["title"] == "New"


def test_uc_a_12_empty_title_no_op(admin_client, make_quiz):
    """UC-A-12: empty title → title unchanged."""
    q = make_quiz("orig")
    r = admin_client.patch(f"/api/quizzes/{q['id']}", json={"title": ""})
    assert r.status_code == 200
    g = admin_client.get(f"/api/quizzes/{q['id']}").json()
    assert g["title"] == "orig"


def test_uc_a_12_same_title_no_op(admin_client, make_quiz):
    """UC-A-12: same title → no change."""
    q = make_quiz("same")
    r = admin_client.patch(f"/api/quizzes/{q['id']}", json={"title": "same"})
    assert r.status_code == 200


def test_uc_a_12_ready_stays_ready(admin_client, make_quiz):
    """UC-A-12: PATCH on ready quiz doesn't auto-revert to draft."""
    q = make_quiz()  # status ready
    admin_client.patch(f"/api/quizzes/{q['id']}", json={"title": "Renamed"})
    g = admin_client.get(f"/api/quizzes/{q['id']}").json()
    assert g["status"] == "ready"


def test_uc_a_12_non_owner_404(admin_client, make_quiz):
    """UC-A-12: non-owner → 404."""
    q = make_quiz()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="other_ren", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get(m.Quiz, q["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.patch(f"/api/quizzes/{q['id']}", json={"title": "x"})
    assert r.status_code == 404


# ---------- UC-A-13: Delete quiz template ----------

def test_uc_a_13_delete_unused(admin_client, make_quiz):
    """UC-A-13: delete unused quiz → ok."""
    q = make_quiz()
    r = admin_client.request("DELETE", f"/api/quizzes/{q['id']}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_a_13_delete_used_400(admin_client, make_quiz, make_session):
    """UC-A-13: used quiz → 400."""
    q = make_quiz()
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs", json={"quiz_id": q["id"]})
    r = admin_client.request("DELETE", f"/api/quizzes/{q['id']}")
    assert r.status_code == 400
    assert r.json() == {"detail": "Quiz has been used in a session run and cannot be deleted"}


def test_uc_a_13_non_owner_404(admin_client, make_quiz):
    """UC-A-13: non-owner → 404."""
    q = make_quiz()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="other_del", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get(m.Quiz, q["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.request("DELETE", f"/api/quizzes/{q['id']}")
    assert r.status_code == 404


# ---------- UC-A-27: Duplicate quiz template ----------

def _rich_quiz(admin_client) -> int:
    """A quiz with a graded single question and an ungraded multi poll, with images."""
    qid = admin_client.post("/api/quizzes", json={"title": "Source"}).json()["id"]
    q1 = admin_client.post(f"/api/quizzes/{qid}/questions",
                           json={"text": "2+2?", "qtype": "single"}).json()["id"]
    admin_client.patch(f"/api/quiz_questions/{q1}", json={"image_url": "/uploads/q1.png"})
    admin_client.post(f"/api/quiz_questions/{q1}/answers", json={"text": "3", "is_correct": False})
    a = admin_client.post(f"/api/quiz_questions/{q1}/answers",
                          json={"text": "4", "is_correct": True}).json()["id"]
    admin_client.patch(f"/api/quiz_answers/{a}", json={"image_url": "/uploads/a4.png"})
    q2 = admin_client.post(f"/api/quizzes/{qid}/questions",
                           json={"text": "Languages?", "qtype": "multi", "graded": False}).json()["id"]
    admin_client.post(f"/api/quiz_questions/{q2}/answers", json={"text": "Python"})
    admin_client.post(f"/api/quiz_questions/{q2}/answers", json={"text": "Go"})
    return qid


def _tree(admin_client, quiz_id: int) -> list[dict]:
    """The quiz's questions and answers without ids, for content comparison."""
    quiz = admin_client.get(f"/api/quizzes/{quiz_id}?include_correct=true").json()
    return [
        {
            **{k: q[k] for k in ("text", "image_url", "qtype", "graded", "order_index")},
            "answers": [
                {k: a[k] for k in ("text", "image_url", "is_correct", "order_index")}
                for a in q["answers"]
            ],
        }
        for q in quiz["questions"]
    ]


def test_uc_a_27_duplicate_returns_draft_copy(admin_client):
    """UC-A-27: duplicate returns a new draft quiz titled '<title> (copy)'."""
    src = _rich_quiz(admin_client)
    r = admin_client.post(f"/api/quizzes/{src}/duplicate")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] != src
    assert body["title"] == "Source (copy)"
    assert body["status"] == "draft"


def test_uc_a_27_duplicate_copies_questions_and_answers(admin_client):
    """UC-A-27: the copy has the same question/answer content with new ids."""
    src = _rich_quiz(admin_client)
    new_id = admin_client.post(f"/api/quizzes/{src}/duplicate").json()["id"]
    assert _tree(admin_client, new_id) == _tree(admin_client, src)
    src_ids = {q["id"] for q in admin_client.get(f"/api/quizzes/{src}").json()["questions"]}
    new_ids = {q["id"] for q in admin_client.get(f"/api/quizzes/{new_id}").json()["questions"]}
    assert src_ids.isdisjoint(new_ids)


def test_uc_a_27_ready_source_stays_ready_copy_is_draft(admin_client, make_quiz):
    """UC-A-27: duplicating a ready quiz leaves it ready; the copy is draft."""
    q = make_quiz("Ready one")
    copy = admin_client.post(f"/api/quizzes/{q['id']}/duplicate").json()
    assert admin_client.get(f"/api/quizzes/{q['id']}").json()["status"] == "ready"
    assert admin_client.get(f"/api/quizzes/{copy['id']}").json()["status"] == "draft"


def test_uc_a_27_editing_copy_leaves_source_unchanged(admin_client):
    """UC-A-27: question and answer edits on the copy don't reach the source."""
    src = _rich_quiz(admin_client)
    before = _tree(admin_client, src)
    new_id = admin_client.post(f"/api/quizzes/{src}/duplicate").json()["id"]
    copy = admin_client.get(f"/api/quizzes/{new_id}?include_correct=true").json()
    q = copy["questions"][0]
    admin_client.patch(f"/api/quiz_questions/{q['id']}", json={"text": "Changed?"})
    admin_client.patch(f"/api/quiz_answers/{q['answers'][0]['id']}", json={"text": "changed"})
    admin_client.request("DELETE", f"/api/quiz_questions/{copy['questions'][1]['id']}")
    assert _tree(admin_client, src) == before


def test_uc_a_27_duplicate_used_quiz(admin_client, make_quiz, make_session):
    """UC-A-27: a quiz used in a run can be duplicated; the copy has no runs."""
    q = make_quiz()
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs", json={"quiz_id": q["id"]})
    r = admin_client.post(f"/api/quizzes/{q['id']}/duplicate")
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    runs = admin_client.get("/api/quiz_runs").json()
    assert all(run["quiz_id"] != new_id for run in runs)
    assert admin_client.request("DELETE", f"/api/quizzes/{new_id}").status_code == 200


def test_uc_a_27_long_title_truncated(admin_client):
    """UC-A-27: a 200-char title yields a copy title of at most 200 chars ending in ' (copy)'."""
    src = admin_client.post("/api/quizzes", json={"title": "a" * 200}).json()["id"]
    title = admin_client.post(f"/api/quizzes/{src}/duplicate").json()["title"]
    assert len(title) <= 200
    assert title.endswith(" (copy)")


def test_uc_a_27_non_owner_404(admin_client, make_quiz):
    """UC-A-27: non-owner → 404."""
    q = make_quiz()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="other_dup", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get(m.Quiz, q["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.post(f"/api/quizzes/{q['id']}/duplicate")
    assert r.status_code == 404


def test_uc_a_27_nonexistent_404(admin_client):
    """UC-A-27: non-existent id → 404."""
    r = admin_client.post("/api/quizzes/999999/duplicate")
    assert r.status_code == 404


def test_uc_a_27_no_auth_401(client):
    """UC-A-27: no auth → 401."""
    r = client.post("/api/quizzes/1/duplicate")
    assert r.status_code == 401


# ---------- UC-A-14: Add question ----------

def test_uc_a_14_add_question_default(admin_client):
    """UC-A-14: POST with {} appends question."""
    qz = admin_client.post("/api/quizzes", json={"title": "Q"}).json()
    r = admin_client.post(f"/api/quizzes/{qz['id']}/questions", json={})
    assert r.status_code == 200
    assert "id" in r.json()


def test_uc_a_14_add_question_multi(admin_client):
    """UC-A-14: qtype=multi → ok."""
    qz = admin_client.post("/api/quizzes", json={"title": "Q"}).json()
    r = admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                          json={"text": "X", "qtype": "multi"})
    assert r.status_code == 200


def test_uc_a_14_add_poll_question(admin_client):
    """UC-A-14: graded=false creates a poll question; default stays graded."""
    qz = admin_client.post("/api/quizzes", json={"title": "Q"}).json()
    admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                      json={"text": "Age?", "graded": False})
    admin_client.post(f"/api/quizzes/{qz['id']}/questions", json={"text": "2+2?"})
    qs = admin_client.get(f"/api/quizzes/{qz['id']}").json()["questions"]
    assert qs[0]["graded"] is False
    assert qs[1]["graded"] is True  # default


def test_uc_a_15_toggle_graded(admin_client):
    """UC-A-15: PATCH graded toggles poll/scored."""
    qz = admin_client.post("/api/quizzes", json={"title": "Q"}).json()
    q = admin_client.post(f"/api/quizzes/{qz['id']}/questions", json={"text": "Age?"}).json()
    admin_client.patch(f"/api/quiz_questions/{q['id']}", json={"graded": False})
    qs = admin_client.get(f"/api/quizzes/{qz['id']}").json()["questions"]
    assert qs[0]["graded"] is False


def test_uc_a_14_bad_qtype_400(admin_client):
    """UC-A-14: bogus qtype → 400."""
    qz = admin_client.post("/api/quizzes", json={"title": "Q"}).json()
    r = admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                          json={"qtype": "bogus"})
    assert r.status_code == 400
    assert r.json() == {"detail": "qtype must be single or multi"}


def test_uc_a_14_non_owner_404(admin_client):
    """UC-A-14: non-owner → 404."""
    qz = admin_client.post("/api/quizzes", json={"title": "Q"}).json()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="oth14", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get(m.Quiz, qz["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.post(f"/api/quizzes/{qz['id']}/questions", json={})
    assert r.status_code == 404


# ---------- UC-A-15: Edit question ----------

def test_uc_a_15_patch_text(admin_client, make_quiz):
    """UC-A-15: PATCH text → ok."""
    q = make_quiz()
    r = admin_client.patch(f"/api/quiz_questions/{q['question_id']}",
                           json={"text": "Why?"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_a_15_patch_qtype(admin_client, make_quiz):
    """UC-A-15: PATCH qtype → updates."""
    q = make_quiz()
    r = admin_client.patch(f"/api/quiz_questions/{q['question_id']}",
                           json={"qtype": "multi"})
    assert r.status_code == 200


def test_uc_a_15_bad_qtype_400(admin_client, make_quiz):
    """UC-A-15: bad qtype → 400."""
    q = make_quiz()
    r = admin_client.patch(f"/api/quiz_questions/{q['question_id']}",
                           json={"qtype": "bogus"})
    assert r.status_code == 400
    assert r.json() == {"detail": "qtype must be single or multi"}


def test_uc_a_15_bad_order_index_400(admin_client, make_quiz):
    """UC-A-15: non-int order_index → 400."""
    q = make_quiz()
    r = admin_client.patch(f"/api/quiz_questions/{q['question_id']}",
                           json={"order_index": "x"})
    assert r.status_code == 400
    assert r.json() == {"detail": "order_index must be an integer"}


def test_uc_a_15_image_url_set_clear(admin_client, make_quiz):
    """UC-A-15: image_url set then clear."""
    q = make_quiz()
    qid = q["question_id"]
    admin_client.patch(f"/api/quiz_questions/{qid}",
                       json={"image_url": "/uploads/x.png"})
    g = admin_client.get(f"/api/quizzes/{q['id']}").json()
    assert g["questions"][0]["image_url"] == "/uploads/x.png"
    admin_client.patch(f"/api/quiz_questions/{qid}", json={"image_url": None})
    g = admin_client.get(f"/api/quizzes/{q['id']}").json()
    assert g["questions"][0]["image_url"] is None


def test_uc_a_15_non_owner_404(admin_client, make_quiz):
    """UC-A-15: non-owner → 404."""
    q = make_quiz()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="oth15", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get(m.Quiz, q["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.patch(f"/api/quiz_questions/{q['question_id']}", json={"text": "x"})
    assert r.status_code == 404


# ---------- UC-A-16: Delete question ----------

def test_uc_a_16_delete_question(admin_client, make_quiz):
    """UC-A-16: DELETE question → ok."""
    q = make_quiz()
    r = admin_client.request("DELETE", f"/api/quiz_questions/{q['question_id']}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_a_16_non_owner_404(admin_client, make_quiz):
    """UC-A-16: non-owner → 404."""
    q = make_quiz()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="oth16", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get(m.Quiz, q["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.request("DELETE", f"/api/quiz_questions/{q['question_id']}")
    assert r.status_code == 404


# ---------- UC-A-17: Add answer ----------

def test_uc_a_17_add_answer(admin_client, make_quiz):
    """UC-A-17: add answer → ok."""
    q = make_quiz()
    r = admin_client.post(f"/api/quiz_questions/{q['question_id']}/answers", json={})
    assert r.status_code == 200
    assert "id" in r.json()


def test_uc_a_17_non_owner_404(admin_client, make_quiz):
    """UC-A-17: non-owner → 404."""
    q = make_quiz()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="oth17", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get(m.Quiz, q["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.post(f"/api/quiz_questions/{q['question_id']}/answers", json={})
    assert r.status_code == 404


# ---------- UC-A-18: Edit answer ----------

def _first_answer_id(admin_client, quiz_id):
    g = admin_client.get(f"/api/quizzes/{quiz_id}?include_correct=true").json()
    return g["questions"][0]["answers"][0]["id"]


def test_uc_a_18_patch_text(admin_client, make_quiz):
    """UC-A-18: PATCH text → ok."""
    q = make_quiz()
    aid = _first_answer_id(admin_client, q["id"])
    r = admin_client.patch(f"/api/quiz_answers/{aid}", json={"text": "Right"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_a_18_patch_is_correct(admin_client, make_quiz):
    """UC-A-18: PATCH is_correct → ok."""
    q = make_quiz()
    aid = _first_answer_id(admin_client, q["id"])
    r = admin_client.patch(f"/api/quiz_answers/{aid}", json={"is_correct": True})
    assert r.status_code == 200


def test_uc_a_18_bad_order_index_400(admin_client, make_quiz):
    """UC-A-18: non-int order_index → 400."""
    q = make_quiz()
    aid = _first_answer_id(admin_client, q["id"])
    r = admin_client.patch(f"/api/quiz_answers/{aid}", json={"order_index": "x"})
    assert r.status_code == 400
    assert r.json() == {"detail": "order_index must be an integer"}


def test_uc_a_18_image_url_set_clear(admin_client, make_quiz):
    """UC-A-18: image_url set then clear."""
    q = make_quiz()
    aid = _first_answer_id(admin_client, q["id"])
    admin_client.patch(f"/api/quiz_answers/{aid}", json={"image_url": "/uploads/x.png"})
    admin_client.patch(f"/api/quiz_answers/{aid}", json={"image_url": None})


def test_uc_a_18_non_owner_404(admin_client, make_quiz):
    """UC-A-18: non-owner → 404."""
    q = make_quiz()
    aid = _first_answer_id(admin_client, q["id"])
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="oth18", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get(m.Quiz, q["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.patch(f"/api/quiz_answers/{aid}", json={"text": "x"})
    assert r.status_code == 404


# ---------- UC-A-19: Delete answer ----------

def test_uc_a_19_delete_answer(admin_client, make_quiz):
    """UC-A-19: delete answer → ok."""
    q = make_quiz()
    aid = _first_answer_id(admin_client, q["id"])
    r = admin_client.request("DELETE", f"/api/quiz_answers/{aid}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_a_19_non_owner_404(admin_client, make_quiz):
    """UC-A-19: non-owner → 404."""
    q = make_quiz()
    aid = _first_answer_id(admin_client, q["id"])
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="oth19", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get(m.Quiz, q["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.request("DELETE", f"/api/quiz_answers/{aid}")
    assert r.status_code == 404


# ---------- UC-A-20: Upload image ----------

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)


def test_uc_a_20_upload_png(admin_client):
    """UC-A-20: .png ≤ 5MB → 200 {url}."""
    files = {"file": ("a.png", PNG_BYTES, "image/png")}
    r = admin_client.post("/api/uploads", files=files)
    assert r.status_code == 200
    url = r.json()["url"]
    assert re.match(r"^/uploads/[0-9a-f]{32}\.png$", url)


def test_uc_a_20_upload_jpeg(admin_client):
    """UC-A-20: .jpeg accepted."""
    files = {"file": ("a.jpeg", b"\xff\xd8\xff\xe0", "image/jpeg")}
    r = admin_client.post("/api/uploads", files=files)
    assert r.status_code == 200


def test_uc_a_20_upload_jpg_gif_webp(admin_client):
    """UC-A-20: jpg, gif, webp all accepted."""
    for ext in ("jpg", "gif", "webp"):
        files = {"file": (f"a.{ext}", b"abc", "application/octet-stream")}
        r = admin_client.post("/api/uploads", files=files)
        assert r.status_code == 200, ext


def test_uc_a_20_upload_svg_400(admin_client):
    """UC-A-20: svg → 400 unsupported image type."""
    files = {"file": ("a.svg", b"<svg/>", "image/svg+xml")}
    r = admin_client.post("/api/uploads", files=files)
    assert r.status_code == 400
    assert r.json() == {"detail": "unsupported image type"}


def test_uc_a_20_upload_exe_400(admin_client):
    """UC-A-20: .exe → 400."""
    files = {"file": ("a.exe", b"\x4d\x5a", "application/octet-stream")}
    r = admin_client.post("/api/uploads", files=files)
    assert r.status_code == 400
    assert r.json() == {"detail": "unsupported image type"}


def test_uc_a_20_upload_no_ext_400(admin_client):
    """UC-A-20: no extension → 400."""
    files = {"file": ("noext", b"abc", "application/octet-stream")}
    r = admin_client.post("/api/uploads", files=files)
    assert r.status_code == 400


def test_uc_a_20_upload_6mb_content_length_400(admin_client):
    """UC-A-20: 6MB Content-Length → 400 max 5MB."""
    big = b"\x00" * (6 * 1024 * 1024)
    files = {"file": ("a.png", big, "image/png")}
    r = admin_client.post("/api/uploads", files=files)
    assert r.status_code == 400
    assert r.json() == {"detail": "max 5MB"}


def test_uc_a_20_upload_no_auth_401(client):
    """UC-A-20: no auth → 401."""
    files = {"file": ("a.png", PNG_BYTES, "image/png")}
    r = client.post("/api/uploads", files=files)
    assert r.status_code == 401


# ---------- UC-A-21: Publish ----------

def test_uc_a_21_publish_valid(admin_client):
    """UC-A-21: valid draft → ready."""
    qz = admin_client.post("/api/quizzes", json={"title": "T"}).json()
    q = admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                          json={"text": "Q?", "qtype": "single"}).json()
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers",
                      json={"text": "a", "is_correct": False})
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers",
                      json={"text": "b", "is_correct": True})
    r = admin_client.post(f"/api/quizzes/{qz['id']}/publish")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_uc_a_21_publish_poll_question_no_correct(admin_client):
    """UC-A-21: a poll question (graded=false) publishes with no correct answer."""
    qz = admin_client.post("/api/quizzes", json={"title": "Survey"}).json()
    q = admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                          json={"text": "Experience level?", "qtype": "single",
                                "graded": False}).json()
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers", json={"text": "Beginner"})
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers", json={"text": "Expert"})
    r = admin_client.post(f"/api/quizzes/{qz['id']}/publish")
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ready"}


def test_uc_a_21_zero_questions_400(admin_client):
    """UC-A-21: 0 questions → 400."""
    qz = admin_client.post("/api/quizzes", json={"title": "T"}).json()
    r = admin_client.post(f"/api/quizzes/{qz['id']}/publish")
    assert r.status_code == 400
    assert r.json() == {"detail": "Quiz needs at least one question"}


def test_uc_a_21_question_empty_text_400(admin_client):
    """UC-A-21: empty question text → 400."""
    qz = admin_client.post("/api/quizzes", json={"title": "T"}).json()
    admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                      json={"text": "", "qtype": "single"})
    r = admin_client.post(f"/api/quizzes/{qz['id']}/publish")
    assert r.status_code == 400
    assert r.json() == {"detail": "Question 1 is missing text"}


def test_uc_a_21_question_one_answer_400(admin_client):
    """UC-A-21: question with 1 answer → 400."""
    qz = admin_client.post("/api/quizzes", json={"title": "T"}).json()
    q = admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                          json={"text": "Q?", "qtype": "single"}).json()
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers",
                      json={"text": "a", "is_correct": True})
    r = admin_client.post(f"/api/quizzes/{qz['id']}/publish")
    assert r.status_code == 400
    assert r.json() == {"detail": "Question 1 needs at least 2 answers"}


def test_uc_a_21_single_zero_correct_400(admin_client):
    """UC-A-21: single with 0 correct → 400."""
    qz = admin_client.post("/api/quizzes", json={"title": "T"}).json()
    q = admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                          json={"text": "Q?", "qtype": "single"}).json()
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers", json={"text": "a"})
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers", json={"text": "b"})
    r = admin_client.post(f"/api/quizzes/{qz['id']}/publish")
    assert r.status_code == 400
    assert r.json() == {"detail": "Question 1 (single choice) needs exactly one correct answer"}


def test_uc_a_21_single_two_correct_400(admin_client):
    """UC-A-21: single with 2 correct → 400."""
    qz = admin_client.post("/api/quizzes", json={"title": "T"}).json()
    q = admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                          json={"text": "Q?", "qtype": "single"}).json()
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers",
                      json={"text": "a", "is_correct": True})
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers",
                      json={"text": "b", "is_correct": True})
    r = admin_client.post(f"/api/quizzes/{qz['id']}/publish")
    assert r.status_code == 400


def test_uc_a_21_multi_zero_correct_400(admin_client):
    """UC-A-21: multi with 0 correct → 400."""
    qz = admin_client.post("/api/quizzes", json={"title": "T"}).json()
    q = admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                          json={"text": "Q?", "qtype": "multi"}).json()
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers", json={"text": "a"})
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers", json={"text": "b"})
    r = admin_client.post(f"/api/quizzes/{qz['id']}/publish")
    assert r.status_code == 400
    assert r.json() == {"detail": "Question 1 (multiple choice) needs at least one correct answer"}


def test_uc_a_21_empty_answer_400(admin_client):
    """UC-A-21: empty answer text + no image → 400."""
    qz = admin_client.post("/api/quizzes", json={"title": "T"}).json()
    q = admin_client.post(f"/api/quizzes/{qz['id']}/questions",
                          json={"text": "Q?", "qtype": "single"}).json()
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers",
                      json={"text": "", "is_correct": True})
    admin_client.post(f"/api/quiz_questions/{q['id']}/answers",
                      json={"text": "b"})
    r = admin_client.post(f"/api/quizzes/{qz['id']}/publish")
    assert r.status_code == 400
    assert r.json() == {"detail": "Question 1, answer 1 is empty"}


def test_uc_a_21_publish_non_owner_404(admin_client, make_quiz):
    """UC-A-21: non-owner → 404."""
    q = make_quiz()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="oth21", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get(m.Quiz, q["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.post(f"/api/quizzes/{q['id']}/publish")
    assert r.status_code == 404


# ---------- UC-A-22: Unpublish ----------

def test_uc_a_22_unpublish(admin_client, make_quiz):
    """UC-A-22: ready → draft."""
    q = make_quiz()
    r = admin_client.post(f"/api/quizzes/{q['id']}/unpublish")
    assert r.status_code == 200
    assert r.json() == {"status": "draft"}


def test_uc_a_22_versions_unchanged(admin_client, make_quiz, make_session):
    """UC-A-22: pre-existing QuizVersion rows unchanged."""
    q = make_quiz()
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs", json={"quiz_id": q["id"]})
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        before = db.query(m.QuizVersion).filter_by(quiz_id=q["id"]).count()
    admin_client.post(f"/api/quizzes/{q['id']}/unpublish")
    with SessionLocal() as db:
        after = db.query(m.QuizVersion).filter_by(quiz_id=q["id"]).count()
    assert before == after


def test_uc_a_22_non_owner_404(admin_client, make_quiz):
    """UC-A-22: non-owner → 404."""
    q = make_quiz()
    from app import auth
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        other = m.User(username="oth22", password_hash=auth.hash_password("longenough"))
        db.add(other); db.commit(); db.refresh(other)
        db.get(m.Quiz, q["id"]).owner_user_id = other.id
        db.commit()
    r = admin_client.post(f"/api/quizzes/{q['id']}/unpublish")
    assert r.status_code == 404
