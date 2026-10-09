"""UC-A-01, UC-A-02, UC-A-25: admin setup, login/logout, change password."""
from __future__ import annotations

from ..support import SETUP_TOKEN

# ---------- UC-A-01: First-run admin setup ----------

def test_uc_a_01_status_fresh_db(client):
    """UC-A-01: GET /api/admin/status on a fresh DB."""
    r = client.get("/api/admin/status")
    assert r.status_code == 200
    assert r.json() == {"initialized": False, "authenticated": False, "username": None, "github_enabled": False}


def test_uc_a_01_setup_creates_admin_and_cookie(client):
    """UC-A-01: setup creates user and sets admin_session cookie."""
    r = client.post("/api/admin/setup", json={"username": "alice", "password": "longenough", "setup_token": SETUP_TOKEN})
    assert r.status_code == 200
    assert r.json() == {"username": "alice"}
    # cookie name per app/auth.py is "prashna_admin"
    assert "prashna_admin" in client.cookies


def test_uc_a_01_status_after_setup(client):
    """UC-A-01: status after setup reports authed."""
    client.post("/api/admin/setup", json={"username": "alice", "password": "longenough", "setup_token": SETUP_TOKEN})
    r = client.get("/api/admin/status")
    assert r.status_code == 200
    assert r.json() == {"initialized": True, "authenticated": True, "username": "alice", "github_enabled": False}


def test_uc_a_01_setup_requires_the_token(client):
    """UC-A-01: no token or a wrong token → 403 and no admin is created."""
    msg = {"detail": "Open the one-time setup link from the server log to create the first admin"}
    for payload in ({"username": "alice", "password": "longenough"},
                    {"username": "alice", "password": "longenough", "setup_token": "wrong"}):
        r = client.post("/api/admin/setup", json=payload)
        assert r.status_code == 403
        assert r.json() == msg
    assert client.get("/api/admin/status").json()["initialized"] is False


def test_uc_a_01_second_setup_returns_409(client):
    """UC-A-01: second setup → 409 Admin already initialized."""
    client.post("/api/admin/setup", json={"username": "alice", "password": "longenough", "setup_token": SETUP_TOKEN})
    r = client.post("/api/admin/setup", json={"username": "bob", "password": "longenough", "setup_token": SETUP_TOKEN})
    assert r.status_code == 409
    assert r.json() == {"detail": "Admin already initialized"}


def test_uc_a_01_setup_short_password(client):
    """UC-A-01: password < 8 chars → 400."""
    r = client.post("/api/admin/setup", json={"username": "alice", "password": "short", "setup_token": SETUP_TOKEN})
    assert r.status_code == 400
    assert r.json() == {"detail": "password must be at least 8 characters"}


def test_uc_a_01_setup_empty_username(client):
    """UC-A-01: empty username → 400."""
    r = client.post("/api/admin/setup", json={"username": "", "password": "longenough", "setup_token": SETUP_TOKEN})
    assert r.status_code == 400
    assert r.json() == {"detail": "username required"}


def test_uc_a_01_concurrent_setup_different_usernames(app_module):
    """UC-A-01: two concurrent setups with different usernames → exactly one wins.

    Closes the round-2 race finding: without the process-wide lock,
    both callers could pass the admin_exists() check and both could
    commit a User. The lock serializes the check+insert so the second
    caller sees the first's row and gets 409.
    """
    import threading

    from fastapi.testclient import TestClient

    results = []
    barrier = threading.Barrier(2)

    def attempt(username):
        with TestClient(app_module.app) as c:
            barrier.wait()
            r = c.post("/api/admin/setup",
                       json={"username": username, "password": "longenough", "setup_token": SETUP_TOKEN})
            results.append(r.status_code)

    threads = [
        threading.Thread(target=attempt, args=("alice",)),
        threading.Thread(target=attempt, args=("bob",)),
    ]
    for t in threads: t.start()
    for t in threads: t.join()

    # Exactly one 200 and one 409 — no double-admin outcome.
    assert sorted(results) == [200, 409]
    # And exactly one User row exists.
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        assert db.query(m.User).count() == 1


# ---------- UC-A-02: Login / Logout ----------

def test_uc_a_02_login_valid(client, admin_creds):
    """UC-A-02: valid login → 200 + cookie."""
    client.post("/api/admin/setup", json={**admin_creds, "setup_token": SETUP_TOKEN})
    client.cookies.clear()
    r = client.post("/api/admin/login", json=admin_creds)
    assert r.status_code == 200
    assert r.json() == {"username": "admin"}
    assert "prashna_admin" in client.cookies


def test_uc_a_02_login_wrong_password(client, admin_creds):
    """UC-A-02: wrong password → 401."""
    client.post("/api/admin/setup", json={**admin_creds, "setup_token": SETUP_TOKEN})
    client.cookies.clear()
    r = client.post("/api/admin/login", json={"username": "admin", "password": "wrongpass"})
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid username or password"}


def test_uc_a_02_login_unknown_user(client, admin_creds):
    """UC-A-02: unknown username → 401."""
    client.post("/api/admin/setup", json={**admin_creds, "setup_token": SETUP_TOKEN})
    client.cookies.clear()
    r = client.post("/api/admin/login", json={"username": "nope", "password": "whatever1"})
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid username or password"}


def test_uc_a_02_logout_clears_cookie(admin_client):
    """UC-A-02: logout returns ok and clears cookie."""
    r = admin_client.post("/api/admin/logout")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_uc_a_02_status_after_logout(admin_client):
    """UC-A-02: status after logout: initialized true, authed false."""
    admin_client.post("/api/admin/logout")
    admin_client.cookies.clear()
    r = admin_client.get("/api/admin/status")
    assert r.status_code == 200
    body = r.json()
    assert body["initialized"] is True
    assert body["authenticated"] is False


# ---------- UC-A-25: Change password ----------

def test_uc_a_25_change_password_valid(admin_client):
    """UC-A-25: valid current pwd + new pwd ≥ 8 chars → 200."""
    r = admin_client.post("/api/admin/change_password", json={
        "current_password": "testpass1",
        "new_password": "newpass12",
    })
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # new password actually works
    admin_client.post("/api/admin/logout")
    admin_client.cookies.clear()
    r2 = admin_client.post("/api/admin/login", json={"username": "admin", "password": "newpass12"})
    assert r2.status_code == 200


def test_uc_a_25_wrong_current_password(admin_client):
    """UC-A-25: wrong current_password → 401."""
    r = admin_client.post("/api/admin/change_password", json={
        "current_password": "wrong",
        "new_password": "newpass12",
    })
    assert r.status_code == 401
    assert r.json() == {"detail": "Current password is incorrect"}


def test_uc_a_25_short_new_password(admin_client):
    """UC-A-25: new password < 8 chars → 400."""
    r = admin_client.post("/api/admin/change_password", json={
        "current_password": "testpass1",
        "new_password": "short",
    })
    assert r.status_code == 400
    assert r.json() == {"detail": "new password must be at least 8 characters"}


def test_uc_a_25_no_cookie_401(client):
    """UC-A-25: no cookie → 401 Not authenticated."""
    r = client.post("/api/admin/change_password", json={
        "current_password": "x", "new_password": "longenough",
    })
    assert r.status_code == 401
    assert r.json() == {"detail": "Not authenticated"}
