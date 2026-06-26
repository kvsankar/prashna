"""Repository documentation contracts for current architecture."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_authoritative_docs_reference_vite_frontend_paths():
    """README/spec/UX docs should point reviewers at the current Vite source tree."""
    readme = read("README.md")
    ux = read("docs/UX.md")
    specs = read("docs/specs.md")

    assert "frontend/          Vite + TypeScript frontend" in readme
    assert "static/             Vanilla JS / HTML / CSS" not in readme
    assert "frontend/src/app.css" in ux
    assert "static/app.css" not in ux
    assert "frontend/*.html" in specs
    assert "static/*.html" not in specs


def test_authoritative_docs_describe_additive_sqlite_migrations():
    """Operator docs should match the current additive migration bridge."""
    readme = read("README.md")
    claude = read("CLAUDE.md")

    assert "additive SQLite migration bridge" in readme
    assert "additive SQLite migration bridge" in claude
    assert "no migrations yet" not in readme
    assert "### Database migrations\nNone." not in claude
