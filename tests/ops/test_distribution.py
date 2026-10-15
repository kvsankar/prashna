"""Distribution contracts for local Compose, backups, and release bundles."""

from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
import yaml

from prashna.backup import create_archive, restore_archive
from scripts.build_release_bundle import build_bundle

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"
HTTPS_COMPOSE = ROOT / "compose.https.yaml"
CADDYFILE = ROOT / "Caddyfile"
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

    assert pre_restore is not None and pre_restore.is_file()
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


BUNDLE_FILES = {"README.md", "compose.yaml", "compose.env.example", "compose.https.yaml", "Caddyfile"}


def test_release_bundle_pins_version_and_has_matching_checksums(tmp_path):
    """UC-X-10: both archives hold exactly the five bundle files; the bundle's
    compose.yaml defaults to its release, and its env example shows the
    release only on a commented line."""
    tar_path, zip_path, checksums = build_bundle("1.2.3", tmp_path)

    assert tar_path.is_file() and zip_path.is_file() and checksums.is_file()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        compose = archive.read("prashna-1.2.3/compose.yaml").decode()
        env_example = archive.read("prashna-1.2.3/compose.env.example").decode()
    with tarfile.open(tar_path) as archive:
        tar_names = {member.name for member in archive.getmembers() if member.isfile()}
    expected = {f"prashna-1.2.3/{name}" for name in BUNDLE_FILES}
    assert names == expected
    assert tar_names == expected
    assert "${PRASHNA_IMAGE_TAG:-1.2.3}" in compose
    assert re.search(r"^# PRASHNA_IMAGE_TAG=1\.2\.3$", env_example, re.MULTILINE)
    assert not re.search(r"^PRASHNA_IMAGE_TAG=", env_example, re.MULTILINE)
    listed = {
        name: digest
        for digest, name in (line.split("  ", 1) for line in checksums.read_text(encoding="utf-8").splitlines())
    }
    assert listed == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (tar_path, zip_path)
    }


def _unpacked_bundle(tmp_path: Path, version: str = "1.2.3") -> Path:
    """Build the release bundle and unpack its .tar.gz, as a server owner does."""
    tar_path = build_bundle(version, tmp_path / "dist")[0]
    with tarfile.open(tar_path) as archive:
        archive.extractall(tmp_path, filter="data")
    return tmp_path / f"prashna-{version}"


def _compose_env() -> dict[str, str]:
    """The environment without PRASHNA_* or COMPOSE_* settings, so only the
    bundle folder's .env decides the configuration."""
    env = _clean_prashna_env()
    for key in tuple(env):
        if key.startswith("COMPOSE_"):
            env.pop(key)
    return env


def _bundle_config(bundle: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=bundle, env=_compose_env(), text=True, capture_output=True, check=False, timeout=30,
    )


class _ComposeLoader(yaml.SafeLoader):
    """Reads Compose's `!reset` tag as ("!reset", value)."""


def _reset(loader: yaml.SafeLoader, node: yaml.Node):
    if isinstance(node, yaml.SequenceNode):
        return ("!reset", loader.construct_sequence(node))
    if isinstance(node, yaml.MappingNode):
        return ("!reset", loader.construct_mapping(node))
    assert isinstance(node, yaml.ScalarNode)
    return ("!reset", loader.construct_scalar(node))


_ComposeLoader.add_constructor("!reset", _reset)

DOMAIN_MESSAGE = "Set PRASHNA_DOMAIN in .env to your domain name"
HTTPS_ENV = "COMPOSE_FILE=compose.yaml:compose.https.yaml\n"


def test_uc_x_10_https_override_content():
    """UC-X-10: the HTTPS add-on hides Prashna's port, trusts one proxy hop,
    runs Caddy on 80, 443 and 443/udp with named volumes, needs a domain,
    and turns on IPv6 on the Compose network."""
    override = yaml.load(HTTPS_COMPOSE.read_text(encoding="utf-8"), Loader=_ComposeLoader)
    prashna = override["services"]["prashna"]
    caddy = override["services"]["caddy"]

    assert prashna["ports"] == ("!reset", [])
    assert prashna["environment"] == {"PRASHNA_TRUSTED_PROXY_HOPS": "1"}
    assert caddy["image"] == "caddy:2"
    assert caddy["restart"] == "unless-stopped"
    assert caddy["depends_on"] == {"prashna": {"condition": "service_healthy"}}
    assert caddy["ports"] == [
        "${PRASHNA_HTTP_PORT:-80}:80",
        "${PRASHNA_HTTPS_PORT:-443}:443",
        "${PRASHNA_HTTPS_PORT:-443}:443/udp",
    ]
    assert caddy["environment"] == {"PRASHNA_DOMAIN": "${PRASHNA_DOMAIN:?" + DOMAIN_MESSAGE + "}"}
    assert caddy["volumes"] == [
        "./Caddyfile:/etc/caddy/Caddyfile:ro",
        "caddy-data:/data",
        "caddy-config:/config",
    ]
    assert override["networks"] == {"default": {"enable_ipv6": True}}
    assert set(override["volumes"]) == {"caddy-data", "caddy-config"}


def test_uc_x_10_https_override_resolves_and_requires_a_domain(tmp_path):
    """UC-X-10: in an unpacked bundle, a .env with COMPOSE_FILE and a domain
    makes plain `docker compose` use the add-on; without the domain Compose
    stops with the add-on's message."""
    bundle = _unpacked_bundle(tmp_path)
    (bundle / ".env").write_text(HTTPS_ENV + "PRASHNA_DOMAIN=quiz.example.org\n", encoding="utf-8")

    result = _bundle_config(bundle)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    prashna = config["services"]["prashna"]
    caddy = config["services"]["caddy"]
    assert config["name"] == "prashna"
    assert not prashna.get("ports")
    assert prashna["image"] == "ghcr.io/kvsankar/prashna:1.2.3"
    assert prashna["environment"]["PRASHNA_TRUSTED_PROXY_HOPS"] == "1"
    published = {(port["published"], port["target"], port["protocol"]) for port in caddy["ports"]}
    assert published == {("80", 80, "tcp"), ("443", 443, "tcp"), ("443", 443, "udp")}
    assert caddy["environment"]["PRASHNA_DOMAIN"] == "quiz.example.org"
    assert config["networks"]["default"]["enable_ipv6"] is True
    mounts = {(volume["type"], volume["source"], volume["target"]) for volume in caddy["volumes"]}
    assert ("volume", "caddy-data", "/data") in mounts
    assert ("volume", "caddy-config", "/config") in mounts
    assert ("bind", str(bundle / "Caddyfile"), "/etc/caddy/Caddyfile") in mounts

    (bundle / ".env").write_text(HTTPS_ENV, encoding="utf-8")
    missing = _bundle_config(bundle)
    assert missing.returncode != 0
    assert DOMAIN_MESSAGE in missing.stderr


def test_uc_x_10_caddyfile_proxies_to_prashna_with_hsts():
    """UC-X-10: the Caddyfile serves PRASHNA_DOMAIN, forwards to Prashna and
    sends HSTS."""
    lines = [line.strip() for line in CADDYFILE.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.strip().startswith("#")]

    assert lines == [
        "{$PRASHNA_DOMAIN} {",
        'header Strict-Transport-Security "max-age=31536000"',
        "reverse_proxy prashna:8000",
        "}",
    ]


def test_uc_x_10_env_example_sets_nothing(tmp_path):
    """UC-X-10: a .env copied from compose.env.example, in the repository or
    in a bundle, changes no default and pins no release; it offers the HTTPS
    lines commented out and warns about 0.0.0.0."""
    bundle = _unpacked_bundle(tmp_path)
    for path in (ROOT / "compose.env.example", bundle / "compose.env.example"):
        text = path.read_text(encoding="utf-8")
        settings = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        assert settings == [], path
        assert re.search(r"^# COMPOSE_FILE=compose\.yaml:compose\.https\.yaml$", text, re.MULTILINE)
        assert re.search(r"^# PRASHNA_DOMAIN=", text, re.MULTILINE)
        assert re.search(r"^# PRASHNA_IMAGE_TAG=", text, re.MULTILINE)
        flat = " ".join(text.split())
        assert "PRASHNA_BIND_ADDR=0.0.0.0" in flat
        assert "plain HTTP" in flat
    shutil.copy(bundle / "compose.env.example", bundle / ".env")
    result = _bundle_config(bundle)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    assert config["services"]["prashna"]["image"] == "ghcr.io/kvsankar/prashna:1.2.3"
    assert "caddy" not in config["services"]


def test_uc_x_10_project_name_can_be_changed(tmp_path):
    """UC-X-10: COMPOSE_PROJECT_NAME in .env replaces the project name
    `prashna`, for a server that already runs a project of that name."""
    bundle = _unpacked_bundle(tmp_path)
    (bundle / ".env").write_text("COMPOSE_PROJECT_NAME=prashna-quiz\n", encoding="utf-8")  # pragma: allowlist secret

    result = _bundle_config(bundle)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["name"] == "prashna-quiz"


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


def _job(workflow: str, name: str) -> str:
    """The text of one job in the workflow, up to the next job's header."""
    start = workflow.index(f"\n  {name}:\n")
    following = re.search(r"\n  [a-z][a-z0-9_-]*:\n", workflow[start + 1:])
    return workflow[start:start + 1 + following.start()] if following else workflow[start:]


def test_pypi_publish_contract():
    """UC-X-15: tags publish the wheel to PyPI with trusted publishing, after
    building the frontend into the package and checking the version."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = _job(workflow, "pypi-publish")
    assert "if: startsWith(github.ref, 'refs/tags/v')" in job
    assert "id-token: write" in job
    assert "environment: pypi" in job
    assert job.index("npm run build") < job.index("uv build") < job.index("uv publish")
    assert "--trusted-publishing always" in job
    assert 'test "${GITHUB_REF_NAME#v}" = "$version"' in job


# The public landing page; sankara.net serves it from the GitHub Pages site.
INSTALL_URL = "https://sankara.net/prashna"
SH_ONE_LINER = f"curl -LsSf {INSTALL_URL}/install.sh | sh"
PS1_ONE_LINER = f'powershell -ExecutionPolicy ByPass -c "irm {INSTALL_URL}/install.ps1 | iex"'
ONE_LINERS = (
    SH_ONE_LINER,
    PS1_ONE_LINER,
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
    assert "kvsankar.github.io/prashna/install" not in readme
    assert f"<{INSTALL_URL}/>" in readme or f"]({INSTALL_URL}/)" in readme


def test_uc_x_15_landing_page_offers_uv_tool_install_before_pipx(tmp_path):
    """UC-X-15: the landing page offers `uv tool install prashna` after the
    one-liners and before pipx, and `uvx prashna` to try Prashna, described
    as not installing it, and `uvx prashna@latest` for the newest version."""
    site = tmp_path / "site"
    subprocess.run([sys.executable, "scripts/build_pages_site.py", str(site)], cwd=ROOT, check=True)
    index = (site / "index.html").read_text(encoding="utf-8")
    one_liner = index.index(html.escape(SH_ONE_LINER, quote=False))
    uv_tool = index.index("<pre><code>uv tool install prashna</code></pre>")
    uvx = index.index("<pre><code>uvx prashna</code></pre>")
    uvx_latest = index.index("<pre><code>uvx prashna@latest</code></pre>")
    pipx = index.index("<pre><code>pipx install prashna</code></pre>")

    assert one_liner < uv_tool < uvx < uvx_latest < pipx
    uvx_intro = " ".join(index[index.rindex("<p>", 0, uvx):uvx].split())
    assert "without installing" in uvx_intro
    latest_intro = " ".join(index[index.rindex("<p>", 0, uvx_latest):uvx_latest].split())
    assert "newest version" in latest_intro
    assert index.count("uvx prashna") == 2
    assert "installs and starts" not in index


def test_installer_usage_comments_show_the_public_address():
    """UC-X-15: each install script's header comment shows its own one-liner
    with the sankara.net address, as the README does."""
    sh = (ROOT / "prashna" / "installers" / "install.sh").read_text(encoding="utf-8")
    ps1 = (ROOT / "prashna" / "installers" / "install.ps1").read_text(encoding="utf-8")
    assert f"#   {SH_ONE_LINER}\n" in sh
    assert f"#   {PS1_ONE_LINER}\n" in ps1
    assert "kvsankar.github.io" not in sh
    assert "kvsankar.github.io" not in ps1


def test_uc_x_15_windows_installer_checks_exit_codes():
    """UC-X-15: install.ps1 stops when the uv installer or `uv tool install`
    fails. `$ErrorActionPreference = "Stop"` ignores a program's exit status,
    so each of these calls must be followed by a `$LASTEXITCODE` check that
    throws before the success message. PowerShell is not run here."""
    path = ROOT / "prashna" / "installers" / "install.ps1"
    ps1 = path.read_text(encoding="utf-8")
    code = [line.strip() for line in ps1.splitlines()
            if line.strip() and not line.strip().startswith("#")]
    success = next(i for i, line in enumerate(code) if "Prashna is installed" in line)
    for native in ('powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
                   "uv tool install --upgrade prashna"):
        at = code.index(native)
        assert code[at + 1] == "if ($LASTEXITCODE -ne 0) {", native
        assert code[at + 2].startswith('throw "'), native
        assert at + 2 < success
    pwsh = shutil.which("pwsh")
    if pwsh:  # a syntax check only; the installer itself is never run
        parse = subprocess.run(
            [pwsh, "-NoProfile", "-Command",
             "$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
             f"'{path}', [ref]$null, [ref]$e); $e.Count"],
            capture_output=True, text=True, timeout=60)
        assert parse.stdout.strip() == "0", parse.stdout + parse.stderr


def test_pages_publish_contract():
    """UC-X-15: tags publish the install scripts to GitHub Pages only after the
    PyPI package of that version is published."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = _job(workflow, "pages")
    assert "if: startsWith(github.ref, 'refs/tags/v')" in job
    assert "needs: [pypi-publish]" in job
    assert "pages: write" in job and "id-token: write" in job
    assert "name: github-pages" in job
    assert job.index("scripts/build_pages_site.py") < job.index("actions/upload-pages-artifact@v5") \
        < job.index("actions/deploy-pages@v5")


def test_production_compose_logs_to_the_journal():
    """Production container logs go to the host journal, so a deploy (which
    replaces the container) does not delete them (deploy/README.md)."""
    import yaml
    service = yaml.safe_load((ROOT / "deploy" / "docker-compose.yml").read_text())["services"]["prashna"]
    assert service["logging"] == {"driver": "journald", "options": {"tag": "prashna"}}


def test_setup_keeps_the_data_folder_private():
    """The data folder holds the database (admin password hash, participant
    profiles) and the signing key; only the container's user may read it."""
    setup = (ROOT / "deploy" / "setup.sh").read_text()
    assert 'sudo chmod 700 "$APP_DIR/data"' in setup
    assert setup.index('sudo chown -R "$APP_UID:$APP_GID"') < setup.index('sudo chmod 700 "$APP_DIR/data"')


TAGLINE = "Live questions and quizzes for trainers, teachers and speakers"
GUIDE_URL = "https://github.com/kvsankar/prashna/blob/main/docs/user-guide.md"


def _project_version() -> str:
    import tomllib
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def test_uc_x_15_pages_site_opens_with_context_and_links_the_landing_page(tmp_path):
    """UC-X-15: the GitHub Pages page opens with the README's context, links
    the sankara.net landing page and the user guide, and puts one command in
    each block; it and the package share one tagline."""
    import tomllib
    site = tmp_path / "site"
    subprocess.run([sys.executable, "scripts/build_pages_site.py", str(site)], cwd=ROOT, check=True)
    index = (site / "index.html").read_text(encoding="utf-8")

    assert "trainers, teachers and speakers" in index
    assert f'href="{INSTALL_URL}/"' in index
    assert f'href="{GUIDE_URL}"' in index
    assert f'<meta name="description" content="{TAGLINE}.">' in index
    blocks = re.findall(r"<pre><code>(.*?)</code></pre>", index, re.DOTALL)
    assert blocks
    for block in blocks:
        assert len([line for line in block.splitlines() if line.strip()]) == 1, block
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["description"] == TAGLINE


def test_uc_x_15_container_guide_names_a_release_and_its_bundle():
    """UC-X-15: the container guide names a release image and the bundle it
    comes in, says what `latest` is, and gives the password reset."""
    guide = (ROOT / "distribution" / "README.md").read_text(encoding="utf-8")
    flat = " ".join(guide.split())

    assert f"ghcr.io/kvsankar/prashna:{_project_version()}" in guide
    assert re.search(r"`latest`[^.]*\bfollows the `main` branch", flat)
    assert "prashna-<version>.zip" in guide
    assert "docker compose exec prashna python -m prashna reset-password" in guide
    assert "**Invite participants**" in guide
    for internal in ("Invite card", "Hetzner", "Registry access"):
        assert internal not in guide
    # Fenced blocks, also those indented inside a numbered list.
    blocks = re.findall(r"^ *```[^\n]*\n(.*?)^ *```$", guide, re.MULTILINE | re.DOTALL)
    assert len(blocks) == guide.count("```") // 2
    for block in blocks:
        assert len([line for line in block.splitlines() if line.strip()]) == 1, block
