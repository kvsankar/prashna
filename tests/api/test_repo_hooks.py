"""Repository hooks: the PII guard and the commit-message check.

Both run from pre-commit (scripts/check_pii.py on staged files,
scripts/check_commit_msg.py at the commit-msg stage) and in CI.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.check_commit_msg import problems as commit_problems
from scripts.check_pii import scan_text

ROOT = Path(__file__).resolve().parents[2]


# ---------- PII guard ----------

def kinds(text: str) -> list[str]:
    return [f.kind for f in scan_text(text)]


def test_flags_real_email_addresses():
    assert kinds("contact: someone.real@gmail.com") == ["email"]  # pii-allow: deliberate sample
    assert kinds("ops@company.io and dev@company.io") == ["email", "email"]  # pii-allow: deliberate sample


def test_allows_placeholder_and_noreply_emails():
    assert kinds("you@example.com alice@example.org bot@test.example") == []
    assert kinds("123+someone@users.noreply.github.com noreply@github.com") == []


def test_flags_public_ip_addresses():
    assert kinds("origin: 8.8.4.4") == ["ip"]  # pii-allow: deliberate sample


def test_allows_loopback_private_and_documentation_ips():
    text = "127.0.0.1 0.0.0.0 10.1.2.3 172.16.0.9 192.168.1.20 192.0.2.7 198.51.100.4 203.0.113.9"
    assert kinds(text) == []


def test_ignores_version_like_numbers():
    assert kinds("version 1.2.3, sha 1.22.333.4444") == []


def test_flags_home_directory_paths():
    assert kinds("see /home/someone/code") == ["path"]  # pii-allow: deliberate sample
    assert kinds("open /Users/someone/notes") == ["path"]  # pii-allow: deliberate sample
    assert kinds(r"C:\Users\someone\file") == ["path"]  # pii-allow: deliberate sample


def test_allow_marker_skips_a_line():
    assert kinds("certbot -m someone.real@gmail.com  # pii-allow") == []


def test_cli_exits_nonzero_with_findings(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("mail me at someone.real@gmail.com\n")  # pii-allow: deliberate sample
    good = tmp_path / "good.md"
    good.write_text("mail me at you@example.com\n")
    run = lambda *files: subprocess.run(  # noqa: E731
        [sys.executable, "scripts/check_pii.py", *map(str, files)],
        cwd=ROOT, capture_output=True, text=True)
    assert run(good).returncode == 0
    result = run(good, bad)
    assert result.returncode == 1
    assert "bad.md:1" in result.stdout and "email" in result.stdout


def test_tracked_files_are_clean():
    """The whole repository passes the guard (it also runs in CI)."""
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    result = subprocess.run([sys.executable, "scripts/check_pii.py", *files], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


# ---------- commit-message check ----------

GOOD = "fix(sync): keep the queue when a push fails\n\nThe queue was dropped on error. Verified with the sync tests.\n"


def test_accepts_conventional_commit_with_body():
    assert commit_problems(GOOD) == []
    assert commit_problems("feat!: drop the old API\n\nBreaking change for clients.\n") == []


def test_rejects_bad_subjects():
    assert commit_problems("Update stuff\n\nbody\n")  # no type
    assert commit_problems("feat: Add a thing\n\nbody\n")  # upper-case summary
    assert commit_problems("feat: add a thing.\n\nbody\n")  # trailing period
    assert commit_problems("feature: add a thing\n\nbody\n")  # unknown type


def test_requires_a_body_after_a_blank_line():
    assert commit_problems("fix: keep the queue\n")
    assert commit_problems("fix: keep the queue\nno blank line\n")


def test_rejects_agent_attribution_lines():
    msg = GOOD + "\nCo-Authored-By: Claude <noreply@anthropic.com>\n"  # pii-allow: deliberate sample
    assert any("attribution" in p for p in commit_problems(msg))
    assert commit_problems(GOOD + "\nGenerated with some tool\n")


def test_ignores_comments_and_allows_merges_and_fixups():
    assert commit_problems(GOOD + "# Please enter the commit message\n") == []
    assert commit_problems("Merge branch 'main' into feature\n") == []
    assert commit_problems("fixup! fix(sync): keep the queue when a push fails\n") == []


# ---------- runtime secrets and databases ----------

def test_flags_generated_prashna_secrets():
    assert kinds("key prashna_sk_" + "A1b2C3d4E5f6G7h8I9j0-_kLmN") == ["secret"]  # pii-allow: deliberate sample  # pragma: allowlist secret
    assert kinds("prashna_st_" + "Zz9Yy8Xx7Ww6Vv5Uu4") == ["secret"]  # pii-allow: deliberate sample


def test_allows_documented_secret_prefixes():
    assert kinds("generated keys start with `prashna_sk_` or `prashna_st_<random>`") == []


def test_cli_rejects_a_sqlite_database_under_any_name(tmp_path):
    import sqlite3
    db_file = tmp_path / "nested" / "notes.bin"
    db_file.parent.mkdir()
    sqlite3.connect(db_file).execute("create table t (x)").connection.commit()
    image = tmp_path / "photo.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(256)))
    result = subprocess.run([sys.executable, "scripts/check_pii.py", str(db_file), str(image)],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 1
    assert "notes.bin" in result.stdout and "sqlite" in result.stdout
    assert "photo.png" not in result.stdout


def test_pii_hook_receives_binary_files():
    """The hook must not filter to text files, or a staged database never reaches the check."""
    config = (ROOT / ".pre-commit-config.yaml").read_text()
    block = config.split("id: check-pii", 1)[1].split("- id:", 1)[0]
    assert "types: [text]" not in block
