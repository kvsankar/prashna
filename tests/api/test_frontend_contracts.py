"""Static frontend contracts that are hard to exercise in browser tests."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_live_clients_drop_stale_refresh_responses():
    """Live clients should gate async paints so older responses cannot win."""
    for rel in (
        "frontend/src/moderator.ts",
        "frontend/src/participant.ts",
        "frontend/src/projector.ts",
    ):
        src = (ROOT / rel).read_text()
        assert "latest" in src.lower(), rel
        assert "seq" in src.lower(), rel
        assert "!== " in src or "!== latest" in src, rel


def test_live_socket_reconnect_test_hook_is_gated():
    """Reconnect UI tests need a gated hook to close the active socket."""
    src = (ROOT / "frontend/src/common.ts").read_text()

    assert 'import.meta.env.MODE === "test"' in src
    assert "prashna:socket-close-hook" in src
    assert "localStorage.getItem" in src
    assert "__prashnaLiveSocketTest" in src
    assert "closeActive" in src
    assert "activeCount" in src


def test_role_pages_use_single_bootstrap_requests_and_usable_marks():
    sources = {
        "participant": "participant-bootstrap",
        "moderator": "moderator-bootstrap",
        "projector": "display-bootstrap",
    }
    for role, endpoint in sources.items():
        src = (ROOT / f"frontend/src/{role}.ts").read_text()
        assert endpoint in src, role
        assert f'markUsable("{role}")' in src, role

    common = (ROOT / "frontend/src/common.ts").read_text()
    assert 'performance.mark("prashna-usable")' in common
    assert 'navigator.sendBeacon("/api/diagnostics/performance"' in common


def test_landing_shell_is_visible_before_auth_reconciliation():
    html = (ROOT / "frontend/index.html").read_text()
    assert 'id="join-card" style="display:none;"' not in html
    assert 'id="login-card" style="display:none;"' not in html
    for card in ("join-card", "login-card"):
        match = re.search(rf'<section[^>]*id="{card}"[^>]*>', html)
        assert match, card
        tag = match.group(0)
        assert not re.search(r"\shidden(\s|>|=)", tag), tag

    src = (ROOT / "frontend/src/index.ts").read_text()
    assert 'markUsable("landing")' in src


# ---------- UC-X-13 / UX.md §1: one source for sizes and spacing ----------


HTML_PAGES = sorted((ROOT / "frontend").glob("*.html"))
TS_SOURCES = sorted((ROOT / "frontend/src").glob("*.ts"))


def test_markup_has_no_inline_styles():
    """Pages style elements only through classes; hiding uses `hidden`."""
    offenders = [
        f"{p.name}:{n}"
        for p in HTML_PAGES
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if re.search(r'\sstyle="', line)
    ]
    assert offenders == []


def test_scripts_set_no_inline_styles():
    """Scripts don't pass `style` attributes or assign `.style.*`; the only
    allowed write is a CSS custom property (data such as a result share)."""
    offenders = []
    for p in TS_SOURCES:
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if re.search(r"[{,]\s*style:", line):
                offenders.append(f"{p.name}:{n} style attr")
            for m in re.finditer(r"\.style\.(\w+)", line):
                if m.group(1) != "setProperty":
                    offenders.append(f"{p.name}:{n} .style.{m.group(1)}")
            if '.style.setProperty("' in line and '.style.setProperty("--' not in line:
                offenders.append(f"{p.name}:{n} non-custom property")
    assert offenders == []


def test_pages_have_no_style_blocks():
    """All styles live in .css files, where stylelint enforces the design
    tokens (UX.md §1); a <style> block in a page would escape that check."""
    offenders = [p.name for p in HTML_PAGES if re.search(r"<style[\s>]", p.read_text())]
    assert offenders == []


def test_button_sizes_come_from_control_tokens():
    """The button scale (UC-X-13) is defined once, from the control-height tokens."""
    css = (ROOT / "frontend/src/app.css").read_text()
    for token in ("--control-h)", "--control-h-sm)", "--control-h-xs)"):
        assert token in css, token


def test_flex_containers_declare_wrapping():
    """Every flex container states flex-wrap (or is a column), so rows wrap
    unless a rule decides otherwise (UX.md §4). Overflow on phones came from
    rows that never made that decision."""
    css = (ROOT / "frontend/src/app.css").read_text()
    offenders = [
        sel.strip().splitlines()[-1]
        for sel, decls in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        if re.search(r"display:\s*(inline-)?flex\b", decls)
        and "flex-wrap" not in decls
        and not re.search(r"flex-direction:\s*column", decls)
    ]
    assert offenders == []


def test_answer_options_come_from_one_renderer():
    """UC-X-14: surfaces call answerOption() instead of building .option markup."""
    for rel in ("participant.ts", "moderator.ts", "projector.ts"):
        src = (ROOT / "frontend/src" / rel).read_text()
        assert not re.search(r'class:\s*"option\b', src), rel
        assert '"opt-text"' not in src, rel
    assert "export function answerOption(" in (ROOT / "frontend/src/common.ts").read_text()
