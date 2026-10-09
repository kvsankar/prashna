"""UC-A-26: GitHub OAuth admin login (allowlist).

The GitHub HTTP round-trip is mocked (oauth.exchange_code / fetch_user are
monkeypatched) so no network is touched; the rest of the flow — state
signing, allowlist, find-or-create, cookie issuance — runs for real.
"""
from __future__ import annotations

# NB: do NOT import prashna.* at module top — that runs at collection time, before
# the session `_env` fixture overrides PRASHNA_DB_PATH, pinning the engine to
# the root conftest's default path. Import app modules inside the functions.


def _enable_github(monkeypatch, admins="kvsankar"):
    monkeypatch.setenv("PRASHNA_GITHUB_CLIENT_ID", "cid")
    monkeypatch.setenv("PRASHNA_GITHUB_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("PRASHNA_GITHUB_ADMINS", admins)


def _mock_github(monkeypatch, app_module, gid, login, token="tok"):
    monkeypatch.setattr(app_module.oauth, "exchange_code", lambda code: token)
    monkeypatch.setattr(app_module.oauth, "fetch_user", lambda t: {"id": gid, "login": login})


# ---------- unit ----------

def test_uc_a_26_enabled_and_allowlist(monkeypatch, app_module):
    from prashna import oauth
    assert oauth.enabled() is False
    _enable_github(monkeypatch, "kvsankar, Alice")
    assert oauth.enabled() is True
    assert oauth.is_allowed("kvsankar") is True
    assert oauth.is_allowed("ALICE") is True       # case-insensitive
    assert oauth.is_allowed("bob") is False
    assert oauth.is_allowed("") is False


def test_uc_a_26_state_roundtrip(monkeypatch, app_module):
    from prashna import oauth
    _enable_github(monkeypatch)
    state = oauth.sign_state()
    assert oauth.check_state(state) is True
    assert oauth.check_state("garbage") is False
    assert oauth.check_state(None) is False


# ---------- routes ----------

def test_uc_a_26_disabled_404_and_status(client, app_module):
    assert client.get("/api/auth/github/login", follow_redirects=False).status_code == 404
    assert client.get("/api/auth/github/callback?code=x&state=y",
                      follow_redirects=False).status_code == 404
    assert client.get("/api/admin/status").json()["github_enabled"] is False


def test_uc_a_26_status_true_and_login_redirect(client, monkeypatch, app_module):
    _enable_github(monkeypatch)
    assert client.get("/api/admin/status").json()["github_enabled"] is True
    r = client.get("/api/auth/github/login", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://github.com/login/oauth/authorize")
    assert "state=" in loc
    assert "client_id=cid" in loc


def test_uc_a_26_callback_bad_state_redirects(client, monkeypatch, app_module):
    _enable_github(monkeypatch)
    r = client.get("/api/auth/github/callback?code=abc&state=forged", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/?auth_error=")
    assert "prashna_admin" not in r.headers.get("set-cookie", "")


def test_uc_a_26_callback_allowed_logs_in(client, monkeypatch, app_module):
    _enable_github(monkeypatch)
    _mock_github(monkeypatch, app_module, 4242, "kvsankar")
    state = app_module.oauth.sign_state()
    r = client.get(f"/api/auth/github/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/"
    assert "prashna_admin" in r.headers.get("set-cookie", "")
    st = client.get("/api/admin/status").json()
    assert st["authenticated"] is True
    assert st["username"] == "kvsankar"
    from sqlalchemy import select

    from prashna import models as m
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        u = db.scalar(select(m.User).where(m.User.github_id == 4242))
        assert u is not None
        assert u.username == "kvsankar"
        assert u.password_hash == ""


def test_uc_a_26_callback_not_allowed(client, monkeypatch, app_module):
    _enable_github(monkeypatch)
    _mock_github(monkeypatch, app_module, 999, "stranger")
    state = app_module.oauth.sign_state()
    r = client.get(f"/api/auth/github/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 303
    assert "auth_error" in r.headers["location"]
    assert "prashna_admin" not in r.headers.get("set-cookie", "")
    from prashna import models as m
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        assert db.query(m.User).count() == 0


def test_uc_a_26_find_or_create_idempotent(client, monkeypatch, app_module):
    _enable_github(monkeypatch)
    _mock_github(monkeypatch, app_module, 4242, "kvsankar")
    r1 = client.get(f"/api/auth/github/callback?code=a&state={app_module.oauth.sign_state()}",
                    follow_redirects=False)
    assert r1.status_code == 303
    client.cookies.clear()
    r2 = client.get(f"/api/auth/github/callback?code=b&state={app_module.oauth.sign_state()}",
                    follow_redirects=False)
    assert r2.status_code == 303
    from prashna import models as m
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        assert db.query(m.User).filter(m.User.github_id == 4242).count() == 1


def test_uc_a_26_github_admin_cannot_password_login(client, monkeypatch, app_module):
    _enable_github(monkeypatch)
    _mock_github(monkeypatch, app_module, 4242, "kvsankar")
    client.get(f"/api/auth/github/callback?code=a&state={app_module.oauth.sign_state()}",
               follow_redirects=False)
    client.cookies.clear()
    # password_hash="" never verifies — GitHub admins can't use password login.
    r = client.post("/api/admin/login", json={"username": "kvsankar", "password": "anything"})
    assert r.status_code == 401


def test_uc_a_26_password_admin_coexists(admin_client, monkeypatch, app_module):
    """The local password admin still logs in when GitHub is enabled."""
    _enable_github(monkeypatch)
    admin_client.cookies.clear()
    r = admin_client.post("/api/admin/login", json={"username": "admin", "password": "testpass1"})
    assert r.status_code == 200


# ---------- UC-A-26: the GitHub HTTP calls themselves ----------
# The flow tests above stub exchange_code/fetch_user; these check what those
# two functions send and how they handle GitHub's replies, with urlopen
# replaced so no network is used.

class _Reply:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


def _capture_urlopen(monkeypatch, oauth, body: bytes | Exception):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"], seen["data"], seen["timeout"] = req.full_url, req.data, timeout
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        if isinstance(body, Exception):
            raise body
        return _Reply(body)

    monkeypatch.setattr(oauth.urllib.request, "urlopen", fake_urlopen)
    return seen


def test_uc_a_26_exchange_code_posts_credentials_and_returns_token(app_module, monkeypatch):
    """UC-A-26: the code exchange sends client id, secret and code; returns the token."""
    _enable_github(monkeypatch)
    oauth = app_module.oauth
    seen = _capture_urlopen(monkeypatch, oauth, b'{"access_token": "gho_test", "scope": "read:user"}')
    assert oauth.exchange_code("the-code") == "gho_test"
    assert seen["url"] == oauth.TOKEN_URL
    assert seen["data"] == b"client_id=cid&client_secret=csecret&code=the-code"
    assert seen["headers"]["accept"] == "application/json"
    assert seen["timeout"] == oauth._HTTP_TIMEOUT


def test_uc_a_26_exchange_code_without_token_or_on_error_returns_none(app_module, monkeypatch):
    """UC-A-26: an error reply or a network failure yields None (callback rejects it)."""
    _enable_github(monkeypatch)
    oauth = app_module.oauth
    _capture_urlopen(monkeypatch, oauth, b'{"error": "bad_verification_code"}')
    assert oauth.exchange_code("stale") is None
    _capture_urlopen(monkeypatch, oauth, OSError("network down"))
    assert oauth.exchange_code("x") is None
    _capture_urlopen(monkeypatch, oauth, b"<html>not json</html>")
    assert oauth.exchange_code("x") is None


def test_uc_a_26_fetch_user_sends_bearer_token_and_returns_profile(app_module, monkeypatch):
    """UC-A-26: the profile request carries the bearer token; failures yield None."""
    oauth = app_module.oauth
    seen = _capture_urlopen(monkeypatch, oauth, b'{"id": 42, "login": "someone"}')
    assert oauth.fetch_user("gho_test") == {"id": 42, "login": "someone"}
    assert seen["url"] == oauth.USER_URL
    assert seen["headers"]["authorization"] == "Bearer gho_test"
    _capture_urlopen(monkeypatch, oauth, OSError("network down"))
    assert oauth.fetch_user("gho_test") is None
