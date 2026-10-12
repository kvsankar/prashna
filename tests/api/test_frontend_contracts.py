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
    for rel in ("participant.ts", "moderator.ts", "projector.ts", "quizzes.ts"):
        src = (ROOT / "frontend/src" / rel).read_text()
        assert not re.search(r'class:\s*"option\b', src), rel
        assert '"opt-text"' not in src, rel
        assert "answerOption(" in src, rel
    assert "export function answerOption(" in (ROOT / "frontend/src/common.ts").read_text()


def test_keyboard_shortcuts_submit_through_the_guarded_button():
    """UX.md §12: Enter / Ctrl+Enter submit by clicking the form's button,
    so the button's guardClick double-submit guard also covers the key."""
    shortcuts = {
        "frontend/src/participant.ts": {"#query-text": "#ask-btn"},
        "frontend/src/index.ts": {
            "#su-pass2": "#su-btn",
            "#li-pass": "#li-btn",
            "#new-session-title": "#new-session-btn",
            "#cp-new2": "#cp-submit",
        },
        "frontend/src/quizzes.ts": {"#new-quiz-title": "#create-quiz"},
    }
    for rel, keys in shortcuts.items():
        src = (ROOT / rel).read_text()
        for field, button in keys.items():
            match = re.search(
                # The listener's line plus any indented lines of its body.
                rf'\$\("{re.escape(field)}"\)\.addEventListener\("keydown",([^\n]*(?:\n  [^\n]*)*)',
                src,
            )
            assert match, (rel, field)
            handler = match.group(1)
            assert f'"{button}").click()' in handler, (rel, field, handler)


def _tokens() -> dict[str, str]:
    css = (ROOT / "frontend/src/tokens.css").read_text()
    root = css.split(":root", 1)[1].split("}", 1)[0]
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", root))


def _rgb(value: str) -> tuple[float, float, float, float]:
    value = value.strip()
    if value.startswith("#"):
        h = value[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
    parts = [float(x) for x in re.findall(r"[\d.]+", value)]
    return (parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else 1.0)


def _over(fg: tuple[float, float, float, float], bg: tuple[float, float, float, float]):
    a = fg[3]
    return tuple(fg[i] * a + bg[i] * (1 - a) for i in range(3)) + (1.0,)


def _contrast(a, b) -> float:
    def lum(c):
        ch = [x / 255 for x in c[:3]]
        ch = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_text_colours_meet_wcag_contrast():
    """UX.md §1 Text contrast: text tokens reach WCAG AA (4.5:1) on the
    surfaces they sit on, computed from tokens.css."""
    t = {k: _rgb(v) for k, v in _tokens().items() if v.strip().startswith(("#", "rgb"))}
    panel, panel2 = t["--panel"], t["--panel-2"]
    pairs = {
        "white on primary button": (t["--on-accent"], t["--accent"]),
        "danger text on a card": (t["--bad"], panel),
        "danger text on a row": (t["--bad"], panel2),
        "error banner text": (t["--bad"], _over(t["--bad-bg"], panel)),
        "muted text on a row": (t["--muted"], panel2),
        "body text on a row": (t["--text"], panel2),
        "info banner text": (t["--text"], _over(t["--accent-bg"], panel)),
    }
    low = {name: round(_contrast(fg, bg), 2) for name, (fg, bg) in pairs.items() if _contrast(fg, bg) < 4.5}
    assert low == {}


def test_state_cues_do_not_use_the_accent_as_text():
    """UX.md §1: --accent is a fill, too dark for text on the dark surfaces;
    the session page's "voting closed" cue uses the text colour."""
    ts = (ROOT / "frontend/src/moderator.ts").read_text()
    assert "accent-text" not in ts
    css = (ROOT / "frontend/src/app.css").read_text()
    assert ".accent-text" not in css
    # The info banner's text is --text, the colour the contrast check covers.
    assert re.search(r"\.info-banner \{[^}]*[^-]color: var\(--text\)", css)
