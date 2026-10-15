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
        # A prompt is "$ " or "PS> "; `$HOME` in a PowerShell command is not one.
        assert not re.match(r"(\$|PS>)\s", lines[0].lstrip()), body
    assert readme.count("```") == 2 * len(blocks)


def test_uc_x_15_readme_offers_uv_tool_install_before_pipx():
    """UC-X-15: for people who already have uv, the README offers
    `uv tool install prashna` after the one-liners and before pipx, and
    `uvx prashna` to try Prashna, described as not installing it, and
    `uvx prashna@latest` for the newest version."""
    readme = read("README.md")
    one_liner = readme.index("```sh\ncurl -LsSf https://sankara.net/prashna/install.sh | sh\n```")
    uv_tool = readme.index("```sh\nuv tool install prashna\n```")
    uvx = readme.index("```sh\nuvx prashna\n```")
    uvx_latest = readme.index("```sh\nuvx prashna@latest\n```")
    pipx = readme.index("```sh\npipx install prashna\n```")

    assert one_liner < uv_tool < uvx < uvx_latest < pipx
    latest_intro = " ".join(readme[readme.rindex("```", 0, uvx_latest - 1) + 3:uvx_latest].split())
    assert "newest version" in latest_intro
    uvx_intro = " ".join(readme[readme.rindex("```", 0, uvx - 1) + 3:uvx].split())
    assert "without installing" in uvx_intro
    assert not re.search(r"\binstalls\b", uvx_intro), uvx_intro
    for paragraph in readme.split("\n\n"):
        paragraph = " ".join(paragraph.split())
        if "uvx" in paragraph and "without installing" not in paragraph:
            assert not re.search(r"\binstalls?\b", paragraph), paragraph


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


# User documentation (UC-X-15, "User documentation").
GUIDE_URL = "https://github.com/kvsankar/prashna/blob/main/docs/user-guide.md"
README_HEADINGS = [
    "What Prashna does", "Why Prashna", "Install", "Quick tutorial", "User guide", "Licence",
]
GUIDE_HEADINGS = [
    "Roles", "Run a session", "Questions and answers", "Quizzes and polls", "Feedback",
    "The projector page", "Share moderation", "Put Prashna online", "Where your data is",
    "Export", "Back up and restore", "Update Prashna", "Uninstall Prashna",
    "Reset the admin password", "Troubleshooting", "Run Prashna in Docker",
]
# A bold span in Markdown: **label**.
BOLD = re.compile(r"\*\*([^*]+)\*\*")


def section(text: str, heading: str) -> str:
    """The body of one `## heading` section, up to the next `## ` heading."""
    return text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def frontend_text() -> str:
    files = [*(ROOT / "frontend").glob("*.html"), *(ROOT / "frontend" / "src").glob("*.ts")]
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def missing_ui_labels(text: str) -> list[str]:
    """Bold spans that name no label in the frontend source. The docs set UI
    labels in bold, so each one must be text that the UI shows."""
    ui = frontend_text()
    labels = {label.strip().rstrip("→▾ ").strip() for label in BOLD.findall(text)}
    return sorted(label for label in labels if label not in ui)


def test_uc_x_15_readme_is_install_tutorial_and_guide_link():
    """UC-X-15: the README installs Prashna, gives a quick tutorial, and
    points to the user guide; the rest of the how-to lives in the guide."""
    readme = read("README.md")

    assert re.findall(r"^## (.+)$", readme, re.MULTILINE) == README_HEADINGS
    assert re.search(r"\bpolls?\b", section(readme, "What Prashna does"))
    why = " ".join(section(readme, "Why Prashna").split())
    assert "One command installs it" in why
    assert "MIT License" in why
    guide = section(readme, "User guide")
    assert GUIDE_URL in guide
    assert "https://sankara.net/prashna/" in guide
    assert "https://github.com/kvsankar/prashna/blob/main/docs/development.md" in section(readme, "Licence")


def test_uc_x_15_readme_windows_venv_commands():
    """UC-X-15: the Windows virtual-environment route works in PowerShell:
    `py`, and `$HOME` (PowerShell 5.1 does not expand `~` for programs)."""
    readme = read("README.md")
    for command in (
        r"py -m venv $HOME\.prashna",
        r"$HOME\.prashna\Scripts\pip install prashna",
        r"$HOME\.prashna\Scripts\prashna",
        r"$HOME\.prashna\Scripts\pip install --upgrade prashna",
    ):
        assert f"```powershell\n{command}\n```" in readme, command
    assert "~\\.prashna" not in readme


def test_uc_x_15_readme_quick_tutorial_steps():
    """UC-X-15: the quick tutorial walks from the first start to an online
    audience, in order, with the labels the UI shows."""
    tutorial = section(read("README.md"), "Quick tutorial")
    steps = [
        "setup link", "**+ New session**", "**Projector**", "QR code", "**Ask**",
        "**Reveal results", "prashna --tunnel cloudflare", "prashna --host 0.0.0.0",
    ]
    positions = [tutorial.find(step) for step in steps]

    assert -1 not in positions, dict(zip(steps, positions))
    assert positions == sorted(positions), dict(zip(steps, positions))
    assert "**Base URL**" in tutorial[positions[-1]:]
    assert "prashna --tunnel ngrok" in tutorial
    assert missing_ui_labels(tutorial) == []


def test_uc_x_15_user_guide_covers_the_end_user_topics():
    """UC-X-15: docs/user-guide.md is the main user guide: it covers every
    end-user topic, with the exact commands and the labels the UI shows."""
    guide = read("docs/user-guide.md")

    assert re.findall(r"^## (.+)$", guide, re.MULTILINE) == GUIDE_HEADINGS
    for text in (
        "~/.local/share/prashna",
        "~/Library/Application Support/prashna",
        r"%LOCALAPPDATA%\prashna",
        "--data-dir",
        "prashna backup create",
        "prashna backup restore",
        "--confirm",
        "uv tool upgrade prashna",
        "pipx upgrade prashna",
        "uv tool uninstall prashna",
        "pipx uninstall prashna",
        "prashna reset-password",
        "docker compose exec prashna python -m prashna reset-password",
        "prashna --tunnel cloudflare",
        "prashna --tunnel ngrok",
        "prashna --host 0.0.0.0",
        "](../distribution/README.md)",
    ):
        assert text in guide, text
    assert missing_ui_labels(guide) == []


def test_uc_x_15_user_guide_is_listed_where_topics_live():
    """The user guide owns end-user how-to; CLAUDE.md and the documentation
    policy say so."""
    assert "docs/user-guide.md" in read("CLAUDE.md")
    policy = read("docs/development.md").split("## Documentation policy", 1)[1]
    assert "[`user-guide.md`](user-guide.md)" in policy


def test_uc_x_15_user_guide_points_server_owners_to_https():
    """UC-X-15: the user guide's Docker section sends owners of a server
    with a domain to the container guide's HTTPS section."""
    docker = section(read("docs/user-guide.md") + "\n## ", "Run Prashna in Docker")

    assert "](../distribution/README.md#run-on-your-own-server-with-https)" in docker
    assert "## Run on your own server with HTTPS\n" in read("distribution/README.md")
