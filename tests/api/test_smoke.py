"""Sanity test that the API scaffolding works."""


def test_admin_status_starts_uninitialized(client):
    r = client.get("/api/admin/status")
    assert r.status_code == 200
    assert r.json() == {"initialized": False, "authenticated": False, "username": None}


def test_admin_setup_creates_first_admin(client):
    r = client.post("/api/admin/setup", json={"username": "u", "password": "password1"})
    assert r.status_code == 200
    assert r.json() == {"username": "u"}


def test_admin_client_fixture_is_logged_in(admin_client):
    r = admin_client.get("/api/admin/status")
    assert r.json() == {"initialized": True, "authenticated": True, "username": "admin"}


def test_make_session_factory(make_session):
    s = make_session("hello")
    assert s["title"] == "hello"
    assert s["status"] == "planning"
    assert len(s["code"]) == 6
    assert len(s["mod_key"]) == 16
