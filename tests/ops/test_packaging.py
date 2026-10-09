"""UC-X-15: the PyPI wheel ships the frontend, the installers and the CLI.

Builds the wheel with `uv build`; needs the frontend built first (the test
session builds it) and network access for the build backend.
"""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_wheel_contains_frontend_installers_and_entry_point(tmp_path):
    subprocess.run(["npm", "run", "build"], cwd=ROOT, check=True, capture_output=True)
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path)], cwd=ROOT, check=True,
                   capture_output=True)
    wheel = next(tmp_path.glob("prashna-*.whl"))
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        entry_points = next(n for n in names if n.endswith(".dist-info/entry_points.txt"))
        assert "prashna = prashna.cli:main" in zf.read(entry_points).decode()
    assert "prashna/static/index.html" in names
    assert "prashna/installers/install.sh" in names
    assert "prashna/installers/install.ps1" in names
    assert not any(n.startswith("app/") for n in names)
