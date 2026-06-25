"""UC-X-08: rate limiting.

Two layers of coverage:
- pure unit tests of the token-bucket limiter (deterministic injected clock)
- endpoint integration tests that re-enable the global limiter (the suite
  runs with PRASHNA_RATELIMIT=off; see conftest) and prove each guarded
  route returns 429 under a flood.
"""
from __future__ import annotations

from app.ratelimit import TokenBucketLimiter, enabled_from_env

# ---------- unit: token bucket ----------

def test_bucket_allows_burst_then_denies():
    clock = {"t": 0.0}
    lim = TokenBucketLimiter(enabled=True, time_func=lambda: clock["t"])
    for _ in range(5):
        assert lim.allow("k", 5, 1.0) is True
    assert lim.allow("k", 5, 1.0) is False  # burst exhausted
    clock["t"] = 2.0                          # +2s → +2 tokens at 1/s
    assert lim.allow("k", 5, 1.0) is True
    assert lim.allow("k", 5, 1.0) is True
    assert lim.allow("k", 5, 1.0) is False


def test_bucket_refill_caps_at_capacity():
    clock = {"t": 0.0}
    lim = TokenBucketLimiter(enabled=True, time_func=lambda: clock["t"])
    assert lim.allow("k", 3, 1.0) is True     # consume 1 (2 left)
    clock["t"] = 10_000.0                      # huge idle → cap at capacity
    for _ in range(3):
        assert lim.allow("k", 3, 1.0) is True
    assert lim.allow("k", 3, 1.0) is False    # not more than capacity


def test_bucket_keys_independent():
    lim = TokenBucketLimiter(enabled=True, time_func=lambda: 0.0)
    assert lim.allow("a", 1, 1.0) is True
    assert lim.allow("a", 1, 1.0) is False
    assert lim.allow("b", 1, 1.0) is True     # different key unaffected


def test_bucket_disabled_always_allows():
    lim = TokenBucketLimiter(enabled=False)
    for _ in range(100):
        assert lim.allow("k", 1, 0.0) is True


def test_reset_and_clear():
    lim = TokenBucketLimiter(enabled=True, time_func=lambda: 0.0)
    assert lim.allow("k", 1, 0.0) is True
    assert lim.allow("k", 1, 0.0) is False
    lim.reset("k")
    assert lim.allow("k", 1, 0.0) is True     # reset → fresh bucket
    lim.allow("k", 1, 0.0)
    lim.clear()
    assert lim.allow("k", 1, 0.0) is True     # clear → fresh bucket


def test_enabled_from_env():
    assert enabled_from_env(None) is True
    assert enabled_from_env("on") is True
    assert enabled_from_env("1") is True
    for off in ("off", "0", "false", "no", "OFF", "False", " no "):
        assert enabled_from_env(off) is False


# ---------- unit: client IP resolution under trusted-proxy hops ----------

class _FakeReq:
    def __init__(self, xff=None, peer="9.9.9.9"):
        self.headers = {"x-forwarded-for": xff} if xff else {}
        self.client = type("C", (), {"host": peer})()


def test_client_ip_proxy_hops(app_module, monkeypatch):
    import app.main as main
    # hops=0 → socket peer, XFF ignored
    monkeypatch.setattr(main, "TRUSTED_PROXY_HOPS", 0)
    assert main._client_ip(_FakeReq(xff="1.1.1.1, 2.2.2.2")) == "9.9.9.9"
    # hops=1 → entry the single trusted proxy recorded (rightmost)
    monkeypatch.setattr(main, "TRUSTED_PROXY_HOPS", 1)
    assert main._client_ip(_FakeReq(xff="1.1.1.1, 2.2.2.2")) == "2.2.2.2"
    # spoofed prefix is ignored — proxy-recorded tail wins
    assert main._client_ip(_FakeReq(xff="evil-spoof, 2.2.2.2")) == "2.2.2.2"
    # hops=2 → second from the right
    monkeypatch.setattr(main, "TRUSTED_PROXY_HOPS", 2)
    assert main._client_ip(_FakeReq(xff="1.1.1.1, 2.2.2.2")) == "1.1.1.1"
    # hops>0 but no XFF → fall back to socket peer
    monkeypatch.setattr(main, "TRUSTED_PROXY_HOPS", 1)
    assert main._client_ip(_FakeReq(xff=None)) == "9.9.9.9"


# ---------- endpoint integration ----------

def _enable(app_module, monkeypatch):
    monkeypatch.setattr(app_module.limiter, "enabled", True)
    app_module.limiter.clear()


def test_uc_x_08_login_throttled_then_clears_on_success(admin_client, app_module, monkeypatch):
    """UC-X-08: login floods 429; a correct login resets the IP throttle."""
    _enable(app_module, monkeypatch)
    # A handful of wrong attempts stay 401 (under the burst).
    for _ in range(3):
        r = admin_client.post("/api/admin/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401
    # Correct login succeeds and clears the bucket.
    r = admin_client.post("/api/admin/login", json={"username": "admin", "password": "testpass1"})
    assert r.status_code == 200
    # Fresh bucket: an immediate wrong attempt is 401, not 429.
    r = admin_client.post("/api/admin/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    # Sustained flood eventually trips 429.
    saw_429 = any(
        admin_client.post("/api/admin/login",
                          json={"username": "admin", "password": "wrong"}).status_code == 429
        for _ in range(20)
    )
    assert saw_429


def test_uc_x_08_ask_throttled(make_session, client, app_module, monkeypatch):
    """UC-X-08: query submissions are flood-limited per IP."""
    s = make_session()
    _enable(app_module, monkeypatch)
    saw_429 = False
    for i in range(20):
        r = client.post(f"/api/sessions/{s['code']}/queries", json={"text": f"q{i}"})
        if r.status_code == 429:
            saw_429 = True
            break
        assert r.status_code == 200
    assert saw_429
    assert "too fast" in r.json()["detail"].lower()


def test_uc_x_08_vote_throttled(make_session, admin_client, client, app_module, monkeypatch):
    """UC-X-08: vote toggles are flood-limited per IP."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": "Q?"}).json()
    _enable(app_module, monkeypatch)
    saw_429 = any(
        client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote").status_code == 429
        for _ in range(60)
    )
    assert saw_429


def test_uc_x_08_submit_throttled(make_quiz, make_session, admin_client, app_module, monkeypatch):
    """UC-X-08: quiz-answer submissions are flood-limited per IP."""
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs",
                            json={"quiz_id": q["id"]}).json()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    g = admin_client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    qid = g["current_question"]["id"]
    aid = g["current_question"]["answers"][0]["id"]
    _enable(app_module, monkeypatch)
    saw_429 = any(
        admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                          json={"question_id": qid, "answer_ids": [aid]}).status_code == 429
        for _ in range(40)
    )
    assert saw_429


def test_uc_x_08_new_participant_throttled(make_session, client, app_module, monkeypatch):
    """UC-X-08 (S4): fresh Participant creation is bounded per IP."""
    s = make_session()
    _enable(app_module, monkeypatch)
    saw_429 = False
    for i in range(40):
        client.cookies.set("voter_token", f"tok{i}")
        r = client.get(f"/api/sessions/{s['code']}/me")
        if r.status_code == 429:
            saw_429 = True
            break
        assert r.status_code == 200
    assert saw_429


def test_uc_x_08_disabled_passes_through(make_session, client, app_module):
    """UC-X-08: with the limiter off (suite default), no 429 under a flood."""
    s = make_session()
    assert app_module.limiter.enabled is False
    codes = {
        client.post(f"/api/sessions/{s['code']}/queries", json={"text": f"q{i}"}).status_code
        for i in range(30)
    }
    assert codes == {200}
