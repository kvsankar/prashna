"""Check a commit message against the repository's convention.

Run by pre-commit at the commit-msg stage:

    python scripts/check_commit_msg.py .git/COMMIT_EDITMSG

Rules (Conventional Commits 1.0 plus a required body):
- subject `<type>(<optional scope>)<optional !>: <summary>`, with a known
  type, a summary that starts lower-case and has no trailing period;
- a blank line, then a body explaining what changed, why, and how it
  was verified;
- no agent attribution lines (co-author trailers for AI tools,
  "Generated with ..." lines).
Merge commits and `fixup!`/`squash!` commits are accepted as they are.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = ("feat", "fix", "docs", "refactor", "test", "perf", "build", "ci", "chore", "style", "revert")
SUBJECT = re.compile(rf"^({'|'.join(TYPES)})(\([a-z0-9][a-z0-9-]*\))?!?: (?P<summary>.+)$")
ATTRIBUTION = re.compile(
    r"^(co-authored-by:.*(claude|anthropic|copilot|openai|codex|gemini)|generated with\b)",
    re.IGNORECASE,
)


def problems(message: str) -> list[str]:
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ["empty commit message"]
    subject = lines[0]
    if subject.startswith(("Merge ", "fixup! ", "squash! ", "amend! ")):
        return []
    found: list[str] = []
    m = SUBJECT.match(subject)
    if not m:
        found.append(f"subject must be '<type>(<scope>): <summary>' with type in {', '.join(TYPES)}")
    else:
        summary = m.group("summary")
        if summary[:1] != summary[:1].lower():
            found.append("summary must start lower-case")
        if summary.endswith("."):
            found.append("summary must not end with a period")
    if len(lines) < 3 or lines[1].strip() or not any(line.strip() for line in lines[2:]):
        found.append("add a blank line and a body: what changed, why, and how it was verified")
    if any(ATTRIBUTION.match(line.strip()) for line in lines[1:]):
        found.append("remove agent attribution lines")
    return found


def main(argv: list[str]) -> int:
    message = Path(argv[0]).read_text(encoding="utf-8")
    found = problems(message)
    for p in found:
        print(f"commit message: {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
