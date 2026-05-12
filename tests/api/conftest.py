"""API-level test fixtures.

We import the app once per pytest session against a fixed temp DB path,
then truncate every table between tests for isolation. Truncation is
cheaper than reloading the module and avoids subtle import-order issues
with SQLAlchemy / FastAPI lifespans.
"""
from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------- session-scoped: spin up the app once ----------

@pytest.fixture(scope="session", autouse=True)
def _env(tmp_path_factory):
    """Set env before app import. Runs once for the whole pytest session."""
    db_path = tmp_path_factory.mktemp("apidb") / "prashna-api.db"
    os.environ["PRASHNA_DB_PATH"] = str(db_path)
    os.environ["PRASHNA_UPLOADS_DIR"] = str(tmp_path_factory.mktemp("apiuploads"))
    os.environ["PRASHNA_SECRET_KEY"] = "api-" + secrets.token_hex(8)
    yield


@pytest.fixture(scope="session")
def app_module(_env):
    from app import main
    return main


@pytest.fixture(scope="session")
def _live_client(app_module):
    """One TestClient for the whole session. Lifespan runs init_db once."""
    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture
def client(_live_client, app_module) -> TestClient:
    """Per-test client: same underlying app, but all tables truncated before each test."""
    from app import db as _db
    from app import models as _m
    # Truncate every ORM table. Order: children before parents matters under FKs;
    # SQLAlchemy's `metadata.sorted_tables` returns them in dependency order, so
    # iterating in reverse deletes children first.
    with _db.engine.begin() as conn:
        for table in reversed(_db.Base.metadata.sorted_tables):
            conn.execute(table.delete())
    # Clear any cookies (admin / voter) from prior test.
    _live_client.cookies.clear()
    return _live_client


@pytest.fixture
def admin_client(client: TestClient) -> TestClient:
    """Client with an admin set up + logged in (cookie attached)."""
    r = client.post("/api/admin/setup", json={"username": "admin", "password": "testpass1"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def admin_creds() -> dict:
    return {"username": "admin", "password": "testpass1"}


@pytest.fixture
def make_session(admin_client: TestClient):
    """Factory: create a session and return its dict (code, mod_key, title, status)."""
    def _make(title: str = "Test Session") -> dict:
        r = admin_client.post("/api/sessions", json={"title": title})
        assert r.status_code == 200, r.text
        return r.json()
    return _make


@pytest.fixture
def make_quiz(admin_client: TestClient):
    """Factory: create a Ready quiz with one single-choice question and two answers (one correct)."""
    def _make(title: str = "Test Quiz") -> dict:
        r = admin_client.post("/api/quizzes", json={"title": title})
        assert r.status_code == 200
        qid = r.json()["id"]
        r = admin_client.post(f"/api/quizzes/{qid}/questions", json={"text": "2+2?", "qtype": "single"})
        assert r.status_code == 200
        question_id = r.json()["id"]
        admin_client.post(f"/api/quiz_questions/{question_id}/answers", json={"text": "3", "is_correct": False})
        admin_client.post(f"/api/quiz_questions/{question_id}/answers", json={"text": "4", "is_correct": True})
        r = admin_client.post(f"/api/quizzes/{qid}/publish")
        assert r.status_code == 200, r.text
        return {"id": qid, "title": title, "question_id": question_id}
    return _make


def mod_headers(mod_key: str) -> dict:
    return {"X-Mod-Key": mod_key}
