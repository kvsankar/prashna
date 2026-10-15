"""Repository documentation contracts.

Each topic has one owning document. These checks pin facts to their owner
and fail when a fact is copied into a second place or a link breaks.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REMOVED_DOCS = (
    "spec.md",
    "design.md",
    ".sdlc/approvals.yaml",
    ".sdlc/test-traceability.yaml",
    ".sdlc/wip.md",
)
# Markdown links and images: [text](target) and ![alt](target).
MD_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)")
# Raw HTML attributes that also become links on PyPI.
HTML_LINK = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""")
# An environment-variable name used as a whole string literal in Python.
ENV_LITERAL = re.compile(r"""["'](PRASHNA_[A-Z0-9_]+)["']""")
POLICY_MARKER = ".git/info/exclude"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def live_text_files() -> list[Path]:
    """Tracked and new, non-ignored text files that exist on disk."""
    listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    suffixes = {".md", ".py", ".yml", ".yaml", ".toml", ".ts", ".html", ".sh"}
    return [
        ROOT / name
        for name in listing
        if Path(name).suffix in suffixes and (ROOT / name).is_file()
    ]


def test_authoritative_docs_reference_vite_frontend_paths():
    """The layout, UX, and spec docs point to the current Vite source tree."""
    development = read("docs/development.md")
    ux = read("docs/UX.md")
    specs = read("docs/specs.md")

    assert re.search(r"^frontend/\s+Vite \+ TypeScript frontend", development, re.M)
    assert "static/             Vanilla JS / HTML / CSS" not in development
    assert "frontend/src/app.css" in ux
    assert "static/app.css" not in ux
    assert "frontend/*.html" in specs
    assert "static/*.html" not in specs


def test_architecture_describes_additive_sqlite_migrations():
    """The migration mechanism is described once, in the architecture doc."""
    architecture = read("docs/architecture.md")
    readme = read("README.md")
    claude = read("CLAUDE.md")

    assert "additive SQLite migration bridge" in architecture
    assert "no migrations yet" not in readme
    assert "### Database migrations\nNone." not in claude


def test_spec_describes_setup_token_bootstrap():
    """First-admin setup through a one-time link is current behavior (UC-A-01),
    and it stays safe when the address is already public."""
    specs = read("docs/specs.md")
    uc_a_01 = specs.split("### UC-A-01", 1)[1].split("\n### ", 1)[0]

    assert "Public-first bootstrap is not current baseline scope" not in specs
    assert "Future delta: public or hosted bootstrap" not in specs
    assert re.search(r"already\s+public", uc_a_01)
    assert "one-time setup link" in uc_a_01


def test_readme_uses_only_absolute_links():
    """README.md is the PyPI long description; relative links break there."""
    readme = read("README.md")
    targets = MD_LINK.findall(readme) + HTML_LINK.findall(readme)

    assert targets, "README.md should link to the documentation"
    relative = [t for t in targets if not re.match(r"https?://", t)]
    assert relative == []


# A fenced code block in Markdown: its language tag and its body.
FENCED_BLOCK = re.compile(r"^```([^\n]*)\n(.*?)^```$", re.MULTILINE | re.DOTALL)


def test_readme_opens_with_context_before_install():
    """UC-X-15: the README (the GitHub and PyPI front page) says who Prashna
    is for and why, before it says how to install it."""
    readme = read("README.md")
    headings = re.findall(r"^## (.+)$", readme, re.MULTILINE)

    assert headings[:3] == ["What Prashna does", "Why Prashna", "Install"]
    opening = readme.split("\n## ", 1)[0]
    assert "trainers, teachers and speakers" in opening


def test_readme_puts_each_command_in_its_own_tagged_block():
    """UC-X-15: each README command sits alone in a fenced block tagged sh or
    powershell, with no prompt sign, so it copies cleanly."""
    readme = read("README.md")
    blocks = FENCED_BLOCK.findall(readme)

    assert blocks, "README.md should show its commands in fenced blocks"
    for language, body in blocks:
        lines = [line for line in body.splitlines() if line.strip()]
        assert language in ("sh", "powershell"), body
        assert len(lines) == 1, body
        assert not lines[0].lstrip().startswith("$"), body
    assert readme.count("```") == 2 * len(blocks)


def test_removed_process_docs_stay_removed():
    """The Sarathi baseline files are replaced by docs/specs.md and
    docs/architecture.md."""
    present = [path for path in REMOVED_DOCS if (ROOT / path).exists()]
    assert present == []


def test_no_live_file_references_removed_docs():
    """No live file links to a removed document."""
    this_file = Path(__file__).resolve()
    patterns = [
        re.compile(r"(?<![A-Za-z])spec\.md"),
        re.compile(r"(?<![A-Za-z])design\.md"),
        re.compile(r"approvals\.yaml|test-traceability\.yaml|wip\.md"),
    ]
    hits = []
    for path in live_text_files():
        if path.resolve() == this_file:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            if pattern.search(text):
                hits.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    assert hits == []


def test_documentation_policy_has_one_owner():
    """The documentation policy is stated in docs/development.md only."""
    development = read("docs/development.md")

    assert POLICY_MARKER in development
    assert "one owner" in development
    assert POLICY_MARKER not in read("README.md")
    assert POLICY_MARKER not in read("CLAUDE.md")


def test_every_environment_variable_is_documented():
    """Every PRASHNA_* variable the app reads is in the development guide."""
    names = set()
    for source in (ROOT / "prashna").rglob("*.py"):
        names.update(ENV_LITERAL.findall(source.read_text(encoding="utf-8")))
    development = read("docs/development.md")

    # The scan must find every known setting, so a broken pattern cannot make
    # the documentation check below pass vacuously.
    known = {
        "PRASHNA_DATA_DIR", "PRASHNA_DB_PATH", "PRASHNA_UPLOADS_DIR",
        "PRASHNA_SECRET_KEY", "PRASHNA_SETUP_TOKEN", "PRASHNA_TRUSTED_PROXY_HOPS",
        "PRASHNA_RATELIMIT", "PRASHNA_TUNNEL_DNS_WAIT_SECS", "PRASHNA_WS_SEND_TIMEOUT_SECS",
    }
    assert known <= names, sorted(known - names)
    missing = sorted(name for name in names if f"`{name}`" not in development)
    assert missing == []
