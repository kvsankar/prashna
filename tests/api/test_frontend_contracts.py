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
        tag = re.search(rf'<section[^>]*id="{card}"[^>]*>', html).group(0)
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


def _css_outside_root(css: str) -> str:
    return re.sub(r":root\s*\{[^}]*\}", "", css)


def test_font_sizes_use_type_tokens():
    """Every font size outside :root uses a --text-* token (UX.md §1)."""
    sources = [("app.css", (ROOT / "frontend/src/app.css").read_text())]
    for p in HTML_PAGES:
        sources += [(p.name, block) for block in re.findall(r"<style>(.*?)</style>", p.read_text(), re.S)]
    offenders = [
        f"{name}: {decl}"
        for name, css in sources
        for decl in re.findall(r"font-size:\s*[^;}]+", _css_outside_root(css))
        if not re.fullmatch(r"font-size:\s*var\(--text-[\w-]+\)", decl.strip())
    ]
    assert offenders == []


def test_button_sizes_come_from_control_tokens():
    """The button scale (UC-X-13) is defined once, from the control-height tokens."""
    css = (ROOT / "frontend/src/app.css").read_text()
    for token in ("--control-h)", "--control-h-sm)", "--control-h-xs)"):
        assert token in css, token
