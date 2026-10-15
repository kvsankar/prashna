"""UC-X-15: the PyPI wheel ships the frontend, the installers and the CLI.

Builds the wheel with `uv build`; needs network access for the build
backend. It packages the frontend the test session already built and builds
one only when none exists: a production rebuild here would replace the
test-mode build that the UI tests rely on later in the same session.
"""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_wheel_contains_frontend_installers_and_entry_point(tmp_path):
    if not (ROOT / "prashna" / "static" / "index.html").is_file():
        subprocess.run(["npm", "run", "build", "--", "--mode", "test"], cwd=ROOT, check=True,
                       capture_output=True)
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path)], cwd=ROOT, check=True,
                   capture_output=True)
    wheel = next(tmp_path.glob("prashna-*.whl"))
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        entry_points = next(n for n in names if n.endswith(".dist-info/entry_points.txt"))
        assert "prashna = prashna.cli:main" in zf.read(entry_points).decode()
        metadata = zf.read(next(n for n in names if n.endswith(".dist-info/METADATA"))).decode()
        assert "License-Expression: MIT" in metadata
        assert "Project-URL: Homepage, https://sankara.net/prashna/" in metadata
        assert "Project-URL: Source, https://github.com/kvsankar/prashna" in metadata
        assert any(n.endswith(".dist-info/licenses/LICENSE") for n in names)
    assert "prashna/static/index.html" in names
    assert "prashna/installers/install.sh" in names
    assert "prashna/installers/install.ps1" in names
    assert not any(n.startswith("app/") for n in names)
