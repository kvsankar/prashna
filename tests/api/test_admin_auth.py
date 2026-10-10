"""UC-A-01, UC-A-02, UC-A-25: admin setup, login/logout, change password."""
from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import httpx
from sqlalchemy import create_engine

from ..support import SETUP_TOKEN
from .test_secret_lifecycle import _start_app, _stop_app

STATUS_KEYS = {"initialized", "authenticated", "username"}

# ---------- UC-A-01: First-run admin setup ----------

def test_uc_a_01_status_fresh_db(client):
    """UC-A-01: GET /api/admin/status on a fresh DB."""
    r = client.get("/api/admin/status")
    assert r.status_code == 200
    assert r.json() == {"initialized": False, "authenticated": False, "username": None}


def test_uc_a_01_setup_creates_admin_and_cookie(client):
    """UC-A-01: setup creates user and sets admin_session cookie."""
    r = client.post("/api/admin/setup", json={"username": "alice", "password": "longenough", "setup_token": SETUP_TOKEN})
    assert r.status_code == 200
    assert r.json() == {"username": "alice"}
    # cookie name per prashna/auth.py is "prashna_admin"
    assert "prashna_admin" in client.cookies


def test_uc_a_01_status_after_setup(client):
    """UC-A-01: status after setup reports authed."""
    client.post("/api/admin/setup", json={"username": "alice", "password": "longenough", "setup_token": SETUP_TOKEN})
    r = client.get("/api/admin/status")
    assert r.status_code == 200
    assert r.json() == {"initialized": True, "authenticated": True, "username": "alice"}


def test_uc_a_01_status_reports_only_password_sign_in(client):
    """UC-A-01: the status payload has exactly initialized/authenticated/username."""
    assert set(client.get("/api/admin/status").json()) == STATUS_KEYS
    client.post("/api/admin/setup", json={"username": "alice", "password": "longenough", "setup_token": SETUP_TOKEN})
    assert set(client.get("/api/admin/status").json()) == STATUS_KEYS


def test_uc_a_01_no_github_sign_in_routes(client, monkeypatch):
    """UC-A-01: password is the only sign-in; GitHub routes 404 even with the variables set."""
    monkeypatch.setenv("PRASHNA_GITHUB_CLIENT_ID", "cid")
    monkeypatch.setenv("PRASHNA_GITHUB_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("PRASHNA_GITHUB_ADMINS", "someone")
    assert client.get("/api/auth/github/login", follow_redirects=False).status_code == 404
    r = client.get("/api/auth/github/callback?code=x&state=y", follow_redirects=False)
    assert r.status_code == 404
    assert "prashna_admin" not in client.cookies
    assert set(client.get("/api/admin/status").json()) == STATUS_KEYS


def _old_shape_db(path: Path, users: Sequence[tuple] = ()) -> None:
    """A database whose users table still has the nullable github_id column
    and its unique index, as databases created by earlier releases do."""
    from prashna import models  # noqa: F401
    from prashna.db import Base
    engine = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    with sqlite3.connect(path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "github_id" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN github_id INTEGER")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_github_id ON users (github_id)")
        conn.executemany(
            "INSERT INTO users (id, username, password_hash, github_id, session_version, created_at)"
            " VALUES (?, ?, ?, ?, 1, '2026-01-01 00:00:00')",
            users,
        )


def _github_column_state(path: Path) -> tuple[bool, bool, list[tuple]]:
    with sqlite3.connect(path) as conn:
        has_col = "github_id" in {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        has_idx = "ix_users_github_id" in {row[1] for row in conn.execute("PRAGMA index_list(users)")}
        rows = conn.execute("SELECT username, github_id FROM users ORDER BY id").fetchall()
    return has_col, has_idx, rows


def test_uc_a_01_old_database_with_github_id_sets_up_password_admin(tmp_path):
    """UC-A-01: a database that still has users.github_id starts, runs first-run
    setup, and lets the password admin log in; the column stays."""
    db_path = tmp_path / "old.db"
    _old_shape_db(db_path)
    proc, base = _start_app(db_path, tmp_path / "uploads", "old-shape-secret")
    try:
        with httpx.Client(base_url=base, timeout=5.0) as c:
            assert c.get("/api/admin/status").json() == {
                "initialized": False, "authenticated": False, "username": None}
            r = c.post("/api/admin/setup", json={
                "username": "admin", "password": "testpass1", "setup_token": SETUP_TOKEN})
            assert r.status_code == 200, r.text
            c.post("/api/admin/logout")
            c.cookies.clear()
            r = c.post("/api/admin/login", json={"username": "admin", "password": "testpass1"})
            assert r.status_code == 200, r.text
            assert c.get("/api/admin/status").json() == {
                "initialized": True, "authenticated": True, "username": "admin"}
    finally:
        _stop_app(proc)
    assert _github_column_state(db_path) == (True, True, [("admin", None)])


def test_uc_a_02_old_database_keeps_github_rows_but_only_passwords_sign_in(tmp_path):
    """UC-A-02: on a database with a GitHub-linked row, the password admin logs
    in, the passwordless row cannot, and its github_id is left unchanged."""
    from prashna import auth
    db_path = tmp_path / "old.db"
    _old_shape_db(db_path, [
        (1, "admin", auth.hash_password("testpass1"), None),
        (2, "someone", "", 4242),
    ])
    proc, base = _start_app(db_path, tmp_path / "uploads", "old-shape-secret")
    try:
        with httpx.Client(base_url=base, timeout=5.0) as c:
            r = c.post("/api/admin/login", json={"username": "someone", "password": ""})
            assert r.status_code == 401
            assert "prashna_admin" not in c.cookies
            r = c.post("/api/admin/login", json={"username": "admin", "password": "testpass1"})
            assert r.status_code == 200, r.text
            assert c.get("/api/admin/status").json() == {
                "initialized": True, "authenticated": True, "username": "admin"}
            r = c.post("/api/admin/setup", json={
                "username": "other", "password": "testpass1", "setup_token": SETUP_TOKEN})
            assert r.status_code == 409
    finally:
        _stop_app(proc)
    assert _github_column_state(db_path) == (True, True, [("admin", None), ("someone", 4242)])


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
    from prashna import models as m
    from prashna.db import SessionLocal
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
