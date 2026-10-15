"""Build the GitHub Pages site that hosts the Prashna install scripts.

    python scripts/build_pages_site.py OUT_DIR

Writes install.sh and install.ps1 (copied unchanged from
prashna/installers/) and an index.html landing page. The release workflow
runs it on version tags and deploys OUT_DIR to
https://kvsankar.github.io/prashna/. The public addresses that the page
shows are under https://sankara.net/prashna/, which serves this site
(UC-X-15).
"""

from __future__ import annotations

import argparse
import html
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLERS = ROOT / "prashna" / "installers"
INSTALL_URL = "https://sankara.net/prashna"
REPO_URL = "https://github.com/kvsankar/prashna"

ONE_LINERS = (
    ("macOS and Linux", f"curl -LsSf {INSTALL_URL}/install.sh | sh"),
    ("Windows (PowerShell)", f'powershell -ExecutionPolicy ByPass -c "irm {INSTALL_URL}/install.ps1 | iex"'),
)

# The same routes the README shows for machines that already have Python.
WITH_PYTHON = (
    ("With pipx", "pipx install prashna"),
    ("Or with pip inside a virtual environment",
     "python3 -m venv ~/.prashna\n~/.prashna/bin/pip install prashna"),
)

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prashna</title>
<meta name="description" content="Live Q&amp;A and quizzes for any session with an audience.">
<style>
  :root {{ --bg: #ffffff; --fg: #1f2328; --muted: #59636e; --code-bg: #f6f8fa; --link: #0969da; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --code-bg: #161b22; --link: #4493f8; }}
  }}
  body {{ margin: 0; background: var(--bg); color: var(--fg);
         font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
  main {{ max-width: 44rem; margin: 0 auto; padding: 2.5rem 16px; }}
  h1 {{ margin: 0 0 0.25rem; font-size: 2rem; }}
  h2 {{ margin-top: 2rem; font-size: 1.15rem; }}
  p.lead {{ margin-top: 0; color: var(--muted); }}
  pre {{ background: var(--code-bg); padding: 0.75rem 1rem; border-radius: 6px;
        white-space: pre-wrap; overflow-wrap: anywhere; font-size: 0.9rem; }}
  a {{ color: var(--link); }}
</style>
</head>
<body>
<main>
<h1>Prashna</h1>
<p class="lead">Live Q&amp;A and quizzes for any session with an audience.</p>

<h2>Install</h2>
<p>One command, on a machine with or without Python. It installs
<a href="https://docs.astral.sh/uv/">uv</a>, which fetches Python if needed.</p>
{installs}
<h2>Already have Python 3.11 or newer?</h2>
<p>Install without uv:</p>
{with_python}
<p>A plain <code>pip install</code> into the system Python is refused on Debian,
Ubuntu, and some other Linux distributions; the virtual environment avoids
that. On Windows, the pip is <code>~\\.prashna\\Scripts\\pip</code>.</p>
<h2>Start it</h2>
<pre><code>prashna</code></pre>
<p>With the virtual environment, run <code>~/.prashna/bin/prashna</code>. Your
browser opens on a one-time page where you choose the admin's username and
password. If you already have uv, <code>uvx prashna</code> installs and starts
it in one step.</p>

<h2>More</h2>
<p><a href="{repo}">Source code and documentation on GitHub</a></p>
</main>
</body>
</html>
"""


def _blocks(items: tuple[tuple[str, str], ...]) -> str:
    return "\n".join(
        f"<p>{html.escape(label)}:</p>\n<pre><code>{html.escape(command, quote=False)}</code></pre>"
        for label, command in items
    )


def render_index() -> str:
    return PAGE.format(installs=_blocks(ONE_LINERS), with_python=_blocks(WITH_PYTHON), repo=REPO_URL)


def build_site(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("install.sh", "install.ps1"):
        shutil.copyfile(INSTALLERS / name, out_dir / name)
    (out_dir / "index.html").write_text(render_index(), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir", type=Path)
    build_site(parser.parse_args(argv).out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
