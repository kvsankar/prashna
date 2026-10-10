"""Distribution contracts for local Compose, backups, and release bundles."""

from __future__ import annotations

import html
import io
import os
import sqlite3
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from prashna.backup import create_archive, restore_archive
from scripts.build_release_bundle import build_bundle

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "docker.yml"
NODE24_ACTION_REFS = (
    "actions/checkout@v7",
    "actions/setup-node@v7",
    "astral-sh/setup-uv@v10.0.1",
    "docker/setup-qemu-action@v4",
    "docker/setup-buildx-action@v4",
    "docker/login-action@v4",
    "docker/metadata-action@v6",
    "docker/build-push-action@v7",
)


def _run(args: list[str], *, env: dict[str, str] | None = None):
    return subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=30,
    )


def _clean_prashna_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("PRASHNA_"):
            env.pop(key)
    return env


def _sample_db(path: Path, marker: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL);
            CREATE TABLE sessions (id INTEGER PRIMARY KEY, title TEXT NOT NULL);
            """
        )
        connection.execute("INSERT INTO users (username) VALUES (?)", (marker,))
        connection.execute("INSERT INTO sessions (title) VALUES (?)", (marker,))


def test_local_compose_runs_without_any_env_file():
    """The laptop model needs no .env: the signing key is generated and kept
    in the data volume (UC-X-07) and setup uses the logged link (UC-A-01)."""
    result = _run(
        [
            "docker",
            "compose",
            "--env-file",
            os.devnull,
            "-f",
            str(COMPOSE),
            "config",
        ],
        env=_clean_prashna_env(),
    )
    assert result.returncode == 0, result.stdout
    assert "ghcr.io/kvsankar/prashna:latest" in result.stdout
    assert "target: /data" in result.stdout


def test_local_compose_uses_named_volumes_healthcheck_and_pinned_tag(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "PRASHNA_SECRET_KEY=test-only-secret",
                "PRASHNA_IMAGE_TAG=9.8.7",
                "PRASHNA_PORT=8123",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = _run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(COMPOSE),
            "config",
        ],
        env=_clean_prashna_env(),
    )
    assert result.returncode == 0, result.stdout
    assert "ghcr.io/kvsankar/prashna:9.8.7" in result.stdout
    assert "host_ip: 127.0.0.1" in result.stdout
    assert 'published: "8123"' in result.stdout
    assert "http://127.0.0.1:8000/api/admin/status" in result.stdout
    assert "source: prashna-data" in result.stdout
    assert "target: /data" in result.stdout
    assert "source: prashna-uploads" in result.stdout
    assert "target: /app/uploads" in result.stdout
    assert "/opt/prashna" not in result.stdout


def test_backup_round_trip_includes_consistent_db_and_uploads(tmp_path, monkeypatch):
    db_path = tmp_path / "data" / "prashna.db"
    db_path.parent.mkdir()
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    _sample_db(db_path, "before")
    (uploads / "photo.png").write_bytes(b"before-image")
    monkeypatch.setenv("PRASHNA_DB_PATH", str(db_path))
    monkeypatch.setenv("PRASHNA_UPLOADS_DIR", str(uploads))

    archive = create_archive(tmp_path / "backups" / "snapshot.tar.gz")
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE users SET username = 'after'")
    (uploads / "photo.png").write_bytes(b"after-image")
    (uploads / "extra.png").write_bytes(b"extra")

    pre_restore = restore_archive(archive, confirmed=True)

    assert pre_restore.is_file()
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT username FROM users").fetchone()[0] == "before"
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert (uploads / "photo.png").read_bytes() == b"before-image"
    assert not (uploads / "extra.png").exists()


def test_restore_refuses_without_confirmation(tmp_path):
    with pytest.raises(RuntimeError, match="requires --confirm"):
        restore_archive(tmp_path / "anything.tar.gz")


def test_restore_rejects_archive_path_traversal(tmp_path, monkeypatch):
    db_path = tmp_path / "prashna.db"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    _sample_db(db_path, "safe")
    monkeypatch.setenv("PRASHNA_DB_PATH", str(db_path))
    monkeypatch.setenv("PRASHNA_UPLOADS_DIR", str(uploads))
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        info = tarfile.TarInfo("../escape")
        payload = b"bad"
        info.size = len(payload)
        output.addfile(info, io.BytesIO(payload))
    with pytest.raises(RuntimeError, match="unsafe backup member"):
        restore_archive(archive, confirmed=True)


def test_release_bundle_pins_version_and_has_matching_checksums(tmp_path):
    tar_path, zip_path, checksums = build_bundle("1.2.3", tmp_path)

    assert tar_path.is_file() and zip_path.is_file() and checksums.is_file()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        compose = archive.read("prashna-1.2.3/compose.yaml").decode()
        env_example = archive.read("prashna-1.2.3/compose.env.example").decode()
    assert names == {
        "prashna-1.2.3/README.md",
        "prashna-1.2.3/compose.env.example",
        "prashna-1.2.3/compose.yaml",
    }
    assert "${PRASHNA_IMAGE_TAG:-1.2.3}" in compose
    assert "PRASHNA_IMAGE_TAG=1.2.3" in env_example
    checksum_text = checksums.read_text(encoding="utf-8")
    assert tar_path.name in checksum_text
    assert zip_path.name in checksum_text


def test_release_bundle_rejects_non_semver(tmp_path):
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        build_bundle("latest", tmp_path)


@pytest.mark.parametrize("action_ref", NODE24_ACTION_REFS)
def test_workflow_uses_node24_action_releases(action_ref):
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert f"uses: {action_ref}" in workflow


def test_release_workflow_contract():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "docker/setup-qemu-action@v4" in workflow
    assert "platforms: linux/amd64,linux/arm64" in workflow
    assert "PRASHNA_COMPOSE_SMOKE_IMAGE" in workflow
    assert "needs: build-and-push" in workflow
    assert "scripts/build_release_bundle.py" in workflow
    assert "gh release upload" in workflow


def test_pypi_publish_contract():
    """UC-X-15: tags publish the wheel to PyPI with trusted publishing, after
    building the frontend into the package and checking the version."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = workflow[workflow.index("  pypi-publish:"):]
    assert "if: startsWith(github.ref, 'refs/tags/v')" in job
    assert "id-token: write" in job
    assert "environment: pypi" in job
    assert job.index("npm run build") < job.index("uv build") < job.index("uv publish")
    assert "--trusted-publishing always" in job
    assert 'test "${GITHUB_REF_NAME#v}" = "$version"' in job


PAGES_URL = "https://kvsankar.github.io/prashna"
ONE_LINERS = (
    f"curl -LsSf {PAGES_URL}/install.sh | sh",
    f'powershell -ExecutionPolicy ByPass -c "irm {PAGES_URL}/install.ps1 | iex"',
    # Without uv, for anyone with Python 3.11 or newer.
    "pipx install prashna",
    "python3 -m venv ~/.prashna",
    "~/.prashna/bin/pip install prashna",
)


def test_pages_site_serves_the_packaged_installers(tmp_path):
    """UC-X-15: the GitHub Pages site carries the same install scripts as the
    package, and a landing page with the one-liners the README shows."""
    site = tmp_path / "site"
    subprocess.run([sys.executable, "scripts/build_pages_site.py", str(site)], cwd=ROOT, check=True)
    for name in ("install.sh", "install.ps1"):
        assert (site / name).read_bytes() == (ROOT / "prashna" / "installers" / name).read_bytes()
    index = (site / "index.html").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for line in ONE_LINERS:
        assert html.escape(line, quote=False) in index
        assert line in readme
    assert "prashna.sankara.net/install" not in readme


def test_pages_publish_contract():
    """UC-X-15: tags publish the install scripts to GitHub Pages only after the
    PyPI package of that version is published."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = workflow[workflow.index("\n  pages:"):]
    assert "if: startsWith(github.ref, 'refs/tags/v')" in job
    assert "needs: [pypi-publish]" in job
    assert "pages: write" in job and "id-token: write" in job
    assert "name: github-pages" in job
    assert job.index("scripts/build_pages_site.py") < job.index("actions/upload-pages-artifact@v5") \
        < job.index("actions/deploy-pages@v5")
