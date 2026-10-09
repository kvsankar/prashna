"""Repository documentation contracts for current architecture."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE_ID = re.compile(r"\b(?:AT|JT|TEST)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")


def read(path: str) -> str:
    return (ROOT / path).read_text()


def trace_ids(text: str) -> set[str]:
    return set(TRACE_ID.findall(text))


def test_authoritative_docs_reference_vite_frontend_paths():
    """README/spec/UX docs should point to the current Vite source tree."""
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


def test_spec_describes_setup_token_bootstrap():
    """First-admin setup through a one-time link is the current baseline
    (UC-A-01); the SRS no longer defers public-safe bootstrap."""
    spec = read("spec.md")

    assert "Public-first bootstrap is not current baseline scope" not in spec
    assert "Future delta: public or hosted bootstrap" not in spec
    assert re.search(r"NFR-BOOTSTRAP-PUBLIC: Deployments, including ones already\s+public", spec)
    assert "one-time setup link" in spec


def test_traceability_file_classifies_accepted_obligations():
    """Traceability should classify accepted acceptance and test obligations."""
    spec_ids = {
        item
        for item in trace_ids(read("spec.md"))
        if item.startswith(("AT-", "JT-"))
    }
    design_test_ids = {
        item
        for item in trace_ids(read("design.md"))
        if item.startswith("TEST-")
    }
    traceability = read(".sdlc/test-traceability.yaml")
    classified_ids = trace_ids(traceability)

    missing = sorted((spec_ids | design_test_ids) - classified_ids)
    assert missing == []
    assert "existing_evidence:" in traceability
    assert "planned_remediation:" in traceability
    assert "residual_risks:" in traceability
