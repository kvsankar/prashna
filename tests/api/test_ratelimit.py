"""UC-X-08: rate limiting.

Two layers of coverage:
- pure unit tests of the token-bucket limiter (deterministic injected clock)
- endpoint integration tests that re-enable the global limiter (the suite
  runs with PRASHNA_RATELIMIT=off; see conftest) and prove each guarded
  route returns 429 under a flood.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

import uvicorn
from fastapi import Request
from fastapi.testclient import TestClient
from uvicorn.main import main as uvicorn_cli

from prashna.ratelimit import TokenBucketLimiter, enabled_from_env

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
    def __init__(self, xff=None, peer="192.0.2.9"):
        self.headers = {"x-forwarded-for": xff} if xff else {}
        self.client = type("C", (), {"host": peer})()


def _fake_req(xff=None, peer="192.0.2.9") -> Request:
    """A stand-in with only the attributes _client_ip reads."""
    return cast(Request, _FakeReq(xff=xff, peer=peer))


def test_client_ip_proxy_hops(app_module, monkeypatch):
    import prashna.main as main
    # hops=0 → socket peer, XFF ignored
    monkeypatch.setattr(main, "TRUSTED_PROXY_HOPS", 0)
    assert main._client_ip(_fake_req(xff="203.0.113.1, 198.51.100.2")) == "192.0.2.9"
    # hops=1 → entry the single trusted proxy recorded (rightmost)
    monkeypatch.setattr(main, "TRUSTED_PROXY_HOPS", 1)
    assert main._client_ip(_fake_req(xff="203.0.113.1, 198.51.100.2")) == "198.51.100.2"
    # spoofed prefix is ignored — proxy-recorded tail wins
    assert main._client_ip(_fake_req(xff="evil-spoof, 198.51.100.2")) == "198.51.100.2"
    # hops=2 → second from the right
    monkeypatch.setattr(main, "TRUSTED_PROXY_HOPS", 2)
    assert main._client_ip(_fake_req(xff="203.0.113.1, 198.51.100.2")) == "203.0.113.1"
    # hops>0 but no XFF → fall back to socket peer
    monkeypatch.setattr(main, "TRUSTED_PROXY_HOPS", 1)
    assert main._client_ip(_fake_req(xff=None)) == "192.0.2.9"


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
    """UC-X-08: one person's questions are flood-limited."""
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
    """UC-X-08: one person's vote toggles are flood-limited."""
    s = make_session()
    q = admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": "Q?"}).json()
    _enable(app_module, monkeypatch)
    saw_429 = any(
        client.post(f"/api/sessions/{s['code']}/queries/{q['id']}/vote").status_code == 429
        for _ in range(60)
    )
    assert saw_429


def test_uc_x_08_submit_throttled(make_quiz, make_session, admin_client, app_module, monkeypatch):
    """UC-X-08: one person's quiz-answer submissions are flood-limited."""
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


def _start_run(admin_client, make_quiz, make_session):
    q = make_quiz()
    s = make_session()
    run = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs", json={"quiz_id": q["id"]}).json()
    admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start")
    g = admin_client.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    return s, run, g["current_question"]["id"], g["current_question"]["answers"][0]["id"]


def test_uc_x_08_room_on_one_address_all_succeed(make_quiz, make_session, admin_client, app_module, monkeypatch):
    """UC-X-08: 40 people behind one address each join, ask and answer; none is refused."""
    s, run, qid, aid = _start_run(admin_client, make_quiz, make_session)
    _enable(app_module, monkeypatch)
    for i in range(40):
        admin_client.cookies.set("voter_token", f"room{i}")
        assert admin_client.get(f"/api/sessions/{s['code']}/me").status_code == 200
        assert admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": f"q{i}"}).status_code == 200
        r = admin_client.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                              json={"question_id": qid, "answer_ids": [aid]})
        assert r.status_code == 200, r.text


def test_uc_x_08_address_ceiling(make_session, admin_client, app_module, monkeypatch):
    """UC-X-08: one address gets "people on one network" times one person's allowance."""
    s = make_session()
    assert admin_client.put("/api/admin/limits", json={"network_size": 1}).status_code == 200
    _enable(app_module, monkeypatch)
    admin_client.cookies.set("voter_token", "first")
    for i in range(6):  # one person's burst, which is also the whole address's
        assert admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": f"a{i}"}).status_code == 200
    admin_client.cookies.set("voter_token", "second")
    r = admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": "b"})
    assert r.status_code == 429


def test_uc_x_08_join_ceiling_follows_network_size(make_session, admin_client, client, app_module, monkeypatch):
    """UC-X-08: joining from one address allows "people on one network" at once."""
    s = make_session()
    assert admin_client.put("/api/admin/limits", json={"network_size": 5}).status_code == 200
    _enable(app_module, monkeypatch)
    codes = []
    for i in range(6):
        client.cookies.set("voter_token", f"tok{i}")
        codes.append(client.get(f"/api/sessions/{s['code']}/me").status_code)
    assert codes == [200] * 5 + [429]


def test_uc_x_08_changes_apply_at_once(make_session, admin_client, app_module, monkeypatch):
    """UC-X-08: a saved limit applies to the next request, without a restart."""
    s = make_session()
    _enable(app_module, monkeypatch)
    assert admin_client.put("/api/admin/limits", json={"ask_burst": 2}).status_code == 200
    admin_client.cookies.set("voter_token", "asker")
    codes = [admin_client.post(f"/api/sessions/{s['code']}/queries", json={"text": f"q{i}"}).status_code
             for i in range(3)]
    assert codes == [200, 200, 429]


def test_uc_x_08_disabled_passes_through(make_session, client, app_module):
    """UC-X-08: with the limiter off (suite default), no 429 under a flood."""
    s = make_session()
    assert app_module.limiter.enabled is False
    codes = {
        client.post(f"/api/sessions/{s['code']}/queries", json={"text": f"q{i}"}).status_code
        for i in range(30)
    }
    assert codes == {200}


def test_uc_x_08_profile_throttled(make_session, client, admin_client, app_module, monkeypatch):
    """UC-X-08: one person's profile saves and photograph uploads share a bucket."""
    from .test_participants import PNG_BYTES
    s = make_session()
    admin_client.cookies.clear()
    assert client.get(f"/api/sessions/{s['code']}/me").status_code == 200  # joins: voter_token cookie
    _enable(app_module, monkeypatch)
    codes = []
    for i in range(5):
        codes.append(client.patch(f"/api/sessions/{s['code']}/me", json={"name": f"n{i}"}).status_code)
        codes.append(client.post(f"/api/sessions/{s['code']}/me/photo",
                                 files={"file": ("p.png", PNG_BYTES, "image/png")}).status_code)
    assert codes == [200] * 10
    r = client.patch(f"/api/sessions/{s['code']}/me", json={"name": "late"})
    assert r.status_code == 429
    assert "too fast" in r.json()["detail"].lower()
    r = client.post(f"/api/sessions/{s['code']}/me/photo", files={"file": ("p.png", PNG_BYTES, "image/png")})
    assert r.status_code == 429


# ---------- the container's Uvicorn and forwarding headers ----------

ROOT = Path(__file__).resolve().parents[2]


def _container_app(app_module, monkeypatch):
    """The app wrapped by Uvicorn exactly as the Dockerfile's CMD configures it."""
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    found = re.search(r"^CMD (\[.*\])$", (ROOT / "Dockerfile").read_text(), re.M)
    assert found is not None
    cmd = json.loads(found.group(1))
    assert cmd[:2] == ["uvicorn", "prashna.main:app"]
    params = uvicorn_cli.make_context("uvicorn", cmd[1:]).params
    config = uvicorn.Config(app_module.app, proxy_headers=params["proxy_headers"],
                            forwarded_allow_ips=params["forwarded_allow_ips"])
    config.load()
    return config.loaded_app


def test_uc_x_08_container_ignores_spoofed_forwarded_for(admin_client, app_module, monkeypatch):
    """UC-X-08: with hops 0, a client outside the container cannot pick its
    own address with X-Forwarded-For, so the login limit still applies."""
    monkeypatch.setattr(app_module, "TRUSTED_PROXY_HOPS", 0)
    _enable(app_module, monkeypatch)
    peer = TestClient(_container_app(app_module, monkeypatch), client=("172.18.0.1", 40000))
    codes = [
        peer.post("/api/admin/login", json={"username": "admin", "password": "wrong"},
                  headers={"x-forwarded-for": f"10.0.0.{i}, 203.0.113.9"}).status_code
        for i in range(12)
    ]
    assert codes[:8] == [401] * 8
    assert 429 in codes[8:]


def test_uc_x_08_forwarded_proto_trusted_only_with_proxy_hops(make_session, client, admin_client,
                                                              app_module, monkeypatch):
    """UC-X-08: X-Forwarded-Proto from a non-loopback peer marks cookies
    Secure only when the operator declared a trusted proxy (hops >= 1)."""
    s = make_session()
    peer_app = _container_app(app_module, monkeypatch)

    def voter_cookie_header() -> str:
        peer = TestClient(peer_app, client=("172.18.0.1", 40000))
        r = peer.get(f"/api/sessions/{s['code']}/me", headers={"x-forwarded-proto": "https"})
        assert r.status_code == 200
        return next(v for k, v in r.headers.multi_items() if k == "set-cookie" and v.startswith("voter_token="))

    monkeypatch.setattr(app_module, "TRUSTED_PROXY_HOPS", 0)
    assert "secure" not in voter_cookie_header().lower()
    monkeypatch.setattr(app_module, "TRUSTED_PROXY_HOPS", 1)
    assert "secure" in voter_cookie_header().lower()
