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
import subprocess
from pathlib import Path

import pytest

# Always isolate tests from any real DB on disk. Individual test files / fixtures
# override this with a per-test temp path, but this is the safety net.
os.environ.setdefault("PRASHNA_DB_PATH", "/tmp/prashna-test-default.db")
os.environ.setdefault("PRASHNA_SECRET_KEY", "dummy_secret_do_not_use_in_prod")

# Keep upload writes inside the tests folder when API tests need a real file path.
TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
os.environ.setdefault("PRASHNA_UPLOADS_DIR", str(TESTS_DIR / "_tmp_uploads"))
(TESTS_DIR / "_tmp_uploads").mkdir(parents=True, exist_ok=True)


def _selected_only_ops_tests(args: list[str]) -> bool:
    selected = []
    ops_dir = (TESTS_DIR / "ops").resolve()
    for arg in args:
        if arg.startswith("-"):
            continue
        path_arg = arg.split("::", 1)[0]
        if not path_arg:
            continue
        selected.append((ROOT / path_arg).resolve())
    return bool(selected) and all(
        path == ops_dir or ops_dir in path.parents
        for path in selected
    )


@pytest.fixture(scope="session", autouse=True)
def _build_frontend(request: pytest.FixtureRequest) -> None:
    """Build the Vite frontend once before any test. The page routes (and a
    few API tests that fetch them) serve frontend/dist, so it must exist.
    Requires Node + `npm install` (devDependencies) on the machine."""
    if _selected_only_ops_tests(request.config.args):
        return
    subprocess.run(["npm", "run", "build", "--", "--mode", "test"],
                   cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
