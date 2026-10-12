"""UC-P-04, UC-P-05, UC-P-06, UC-M-08, UC-M-09: queries (Q&A board)."""
from __future__ import annotations

# ---------- UC-P-04: Ask ----------

def test_uc_p_04_ask_planning(client, admin_client, make_session):
    """UC-P-04: ask on planning → 200."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries", json={"text": "Hi?"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "Hi?"
    assert body["responded"] is False
    assert body["removed"] is False
    assert body["vote_count"] == 0
    assert body["mine"] is True


def test_uc_p_04_empty_text_400(client, admin_client, make_session):
    """UC-P-04: empty text → 400 text required."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries", json={"text": ""})
    assert r.status_code == 400
    assert r.json() == {"detail": "text required"}


def test_uc_p_04_whitespace_text_400(client, admin_client, make_session):
    """UC-P-04: whitespace text → 400."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries", json={"text": "   "})
    assert r.status_code == 400
    assert r.json() == {"detail": "text required"}


def test_uc_p_04_text_too_long_400(client, admin_client, make_session):
    """UC-P-04: text > 1000 → 400."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries",
                    json={"text": "a" * 1001})
    assert r.status_code == 400
    assert r.json() == {"detail": "text too long"}


def test_uc_p_04_author_name_stays_on_the_question(client, admin_client, make_session):
    """UC-P-04: a shown name belongs to that question only; the profile is never read or changed."""
    s = make_session()
    admin_client.cookies.clear()
    code = s["code"]
    client.patch(f"/api/sessions/{code}/me", json={"name": "Alice"})
    anon = client.post(f"/api/sessions/{code}/queries", json={"text": "First?"}).json()
    assert anon["author_name"] is None
    r = client.post(f"/api/sessions/{code}/queries", json={"text": "Hi?", "author_name": "  Bob  "})
    assert r.status_code == 200
    assert r.json()["author_name"] == "Bob"
    assert client.get(f"/api/sessions/{code}/me").json()["name"] == "Alice"
    client.patch(f"/api/sessions/{code}/me", json={"name": "Carol"})
    names = {q["text"]: q["author_name"] for q in client.get(f"/api/sessions/{code}/queries").json()}
    assert names == {"First?": None, "Hi?": "Bob"}


def test_uc_p_04_ended_session_400(client, admin_client, make_session):
    """UC-P-04: ask on ended → 400."""
    s = make_session()
    admin_client.post(f"/api/sessions/{s['code']}/end")
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries", json={"text": "Hi?"})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session has ended"}


# ---------- UC-P-05: Vote ----------

def test_uc_p_05_toggle_vote(client, admin_client, make_session):
    """UC-P-05: vote toggles on/off."""
    s = make_session()
    admin_client.cookies.clear()
    q = client.post(f"/api/sessions/{s['code']}/queries",
                    json={"text": "Hi?"}).json()
    r = client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote")
    assert r.status_code == 200
    assert r.json() == {"voted": True, "vote_count": 1}
    r = client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote")
    assert r.json() == {"voted": False, "vote_count": 0}


def test_uc_p_05_no_double_vote(client, admin_client, make_session):
    """UC-P-05: same participant voting twice in row toggles, never > 1."""
    s = make_session()
    admin_client.cookies.clear()
    q = client.post(f"/api/sessions/{s['code']}/queries",
                    json={"text": "Hi?"}).json()
    client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote")
    # vote again
    r = client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote")
    assert r.json()["vote_count"] in (0, 1)


def test_uc_p_05_vote_removed_404(client, admin_client, make_session):
    """UC-P-05: vote on removed query → 404."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Hi?"}).json()
    admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/remove", json={})
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote")
    assert r.status_code == 404


def test_uc_p_05_vote_unknown_404(client, admin_client, make_session):
    """UC-P-05: vote on nonexistent qid → 404."""
    s = make_session()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries/99999/vote")
    assert r.status_code == 404


def test_uc_p_05_vote_ended_400(client, admin_client, make_session):
    """UC-P-05: vote on ended session → 400."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Hi?"}).json()
    admin_client.post(f"/api/sessions/{s['code']}/end")
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote")
    assert r.status_code == 400
    assert r.json() == {"detail": "Session has ended"}


# ---------- UC-P-06: See queries sorted ----------

def test_uc_p_06_list_shape(client, admin_client, make_session):
    """UC-P-06: list returns queries with expected fields."""
    s = make_session()
    admin_client.cookies.clear()
    client.post(f"/api/sessions/{s['code']}/queries", json={"text": "Q1?"})
    r = client.get(f"/api/sessions/{s['code']}/queries")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    for k in ("id", "text", "author_name", "response_text", "responded",
              "removed", "vote_count", "voted", "mine", "created_at"):
        assert k in rows[0]


def test_uc_p_06_created_at_desc(client, admin_client, make_session):
    """UC-P-06: order is created_at desc."""
    s = make_session()
    admin_client.cookies.clear()
    a = client.post(f"/api/sessions/{s['code']}/queries", json={"text": "first"}).json()
    b = client.post(f"/api/sessions/{s['code']}/queries", json={"text": "second"}).json()
    rows = client.get(f"/api/sessions/{s['code']}/queries").json()
    assert rows[0]["id"] == b["id"]
    assert rows[1]["id"] == a["id"]


def test_uc_p_06_removed_hidden_for_participants(client, admin_client, make_session, mod_headers):
    """UC-P-06: removed queries excluded for participants, included for mod."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/remove", json={})
    # participant
    admin_client.cookies.clear()
    rows = client.get(f"/api/sessions/{s['code']}/queries").json()
    assert all(r["id"] != q["id"] for r in rows)
    # moderator
    rows = client.get(f"/api/sessions/{s['code']}/queries",
                      headers=mod_headers(s["mod_key"])).json()
    found = [r for r in rows if r["id"] == q["id"]]
    assert len(found) == 1
    assert found[0]["removed"] is True


def test_uc_p_06_mine_voted_flags(client, admin_client, make_session):
    """UC-P-06: 'mine' and 'voted' flags."""
    s = make_session()
    admin_client.cookies.clear()
    q = client.post(f"/api/sessions/{s['code']}/queries", json={"text": "Q?"}).json()
    client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote")
    rows = client.get(f"/api/sessions/{s['code']}/queries").json()
    row = next(r for r in rows if r["id"] == q["id"])
    assert row["mine"] is True
    assert row["voted"] is True


# ---------- UC-M-08: Respond to a query ----------

def test_uc_m_08_respond_with_text(admin_client, make_session):
    """UC-M-08: respond with text → ok."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    r = admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/respond",
                          json={"response_text": "see docs"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    rows = admin_client.get(f"/api/sessions/{s['code']}/queries").json()
    row = next(r for r in rows if r["id"] == q["id"])
    assert row["responded"] is True
    assert row["response_text"] == "see docs"


def test_uc_m_08_respond_no_text_verbal(admin_client, make_session):
    """UC-M-08: respond {} → verbal (response_text null)."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    r = admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/respond",
                          json={})
    assert r.status_code == 200
    rows = admin_client.get(f"/api/sessions/{s['code']}/queries").json()
    row = next(r for r in rows if r["id"] == q["id"])
    assert row["responded"] is True
    assert row["response_text"] is None


def test_uc_m_08_reopen_clears(admin_client, make_session):
    """UC-M-08: respond with responded=false clears responded_at AND wipes text."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/respond",
                      json={"response_text": "answer"})
    r = admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/respond",
                          json={"responded": False})
    assert r.status_code == 200
    rows = admin_client.get(f"/api/sessions/{s['code']}/queries").json()
    row = next(r for r in rows if r["id"] == q["id"])
    assert row["responded"] is False
    assert row["response_text"] is None  # wiped per handler logic


def test_uc_m_08_unknown_qid_404(admin_client, make_session):
    """UC-M-08: unknown qid → 404."""
    s = make_session()
    r = admin_client.post(f"/api/sessions/{s['code']}/queries/99999/respond", json={})
    assert r.status_code == 404


def test_uc_m_08_no_auth_403(client, admin_client, make_session):
    """UC-M-08: no auth → 403."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/respond", json={})
    assert r.status_code == 403


# ---------- UC-M-09: Remove / Restore query ----------

def test_uc_m_09_remove(admin_client, make_session):
    """UC-M-09: remove sets removed_at."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    r = admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/remove",
                          json={})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_m_09_restore(admin_client, make_session):
    """UC-M-09: removed=false restores."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/remove", json={})
    r = admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/remove",
                          json={"removed": False})
    assert r.status_code == 200
    rows = admin_client.get(f"/api/sessions/{s['code']}/queries").json()
    row = next(r for r in rows if r["id"] == q["id"])
    assert row["removed"] is False


def test_uc_m_09_vote_removed_404(client, admin_client, make_session):
    """UC-M-09: vote on removed → 404."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    admin_client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/remove", json={})
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote")
    assert r.status_code == 404


def test_uc_m_09_no_auth_403(client, admin_client, make_session):
    """UC-M-09: no auth → 403."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries",
                          json={"text": "Q?"}).json()
    admin_client.cookies.clear()
    r = client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/remove", json={})
    assert r.status_code == 403
