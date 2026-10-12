"""UC-A-31: the admin adjusts the rate limits while the server runs."""
from __future__ import annotations

import pytest

DEFAULTS = {
    "network_size": 300, "join_per_minute": 120,
    "ask_burst": 6, "ask_per_minute": 6,
    "vote_burst": 30, "vote_per_minute": 120,
    "submit_burst": 20, "submit_per_minute": 30,
    "feedback_burst": 10, "feedback_per_minute": 30,
    "profile_burst": 10, "profile_per_minute": 10,
}


def test_uc_a_31_get_returns_defaults(admin_client):
    """UC-A-31: a fresh server reports the documented defaults."""
    r = admin_client.get("/api/admin/limits")
    assert r.status_code == 200
    assert r.json() == {"values": DEFAULTS, "defaults": DEFAULTS}


def test_uc_a_31_needs_the_admin(client):
    """UC-A-31: only the signed-in admin may read or change the limits."""
    assert client.get("/api/admin/limits").status_code == 401
    assert client.put("/api/admin/limits", json={"ask_burst": 3}).status_code == 401


def test_uc_a_31_put_saves_and_survives_a_reload(admin_client, app_module):
    """UC-A-31: saved values are returned, kept, and reloaded from the database at start."""
    r = admin_client.put("/api/admin/limits", json={"ask_burst": 3, "network_size": 50})
    assert r.status_code == 200
    expected = {**DEFAULTS, "ask_burst": 3, "network_size": 50}
    assert r.json()["values"] == expected
    assert admin_client.get("/api/admin/limits").json()["values"] == expected
    # Simulate a restart: forget the in-memory values, then load as at start.
    app_module.limits.update(DEFAULTS)
    from prashna.db import SessionLocal
    with SessionLocal() as db:
        app_module.load_limits(db)
    assert app_module.limits == expected


@pytest.mark.parametrize("bad", [0, 2.5, "4", 100001, None, True])
def test_uc_a_31_refuses_bad_values(admin_client, bad):
    """UC-A-31: values must be whole numbers from 1 to 100000; nothing is saved otherwise."""
    r = admin_client.put("/api/admin/limits", json={"vote_burst": 40, "ask_burst": bad})
    assert r.status_code == 400
    assert r.json()["detail"] == "ask_burst must be a whole number from 1 to 100000"
    assert admin_client.get("/api/admin/limits").json()["values"] == DEFAULTS


def test_uc_a_31_refuses_unknown_names(admin_client):
    """UC-A-31: an unknown limit name is refused."""
    r = admin_client.put("/api/admin/limits", json={"speed": 1})
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown limit: speed"
