"""Shared test config.

Two test trees:

- `tests/api/` — fast, in-process tests using FastAPI's TestClient against
  a fresh sqlite DB per test.
- `tests/ui/` — Playwright tests against a real uvicorn subprocess.

Both trees inherit env settings from this file so they don't accidentally
clobber a real prashna.db.
"""
from __future__ import annotations

import os
from pathlib import Path

# Always isolate tests from any real DB on disk. Individual test files / fixtures
# override this with a per-test temp path, but this is the safety net.
os.environ.setdefault("PRASHNA_DB_PATH", "/tmp/prashna-test-default.db")
os.environ.setdefault("PRASHNA_SECRET_KEY", "test-secret-do-not-use-in-prod")

# Keep upload writes inside the tests folder when API tests need a real file path.
TESTS_DIR = Path(__file__).resolve().parent
os.environ.setdefault("PRASHNA_UPLOADS_DIR", str(TESTS_DIR / "_tmp_uploads"))
(TESTS_DIR / "_tmp_uploads").mkdir(parents=True, exist_ok=True)
