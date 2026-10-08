"""UC-X-12, UC-X-13, UC-X-14: every page fits phones, one button scale, one answer-option renderer."""
from __future__ import annotations

import re
import secrets

from playwright.sync_api import expect

from ._helpers import (
    admin_login_via_ui,
    api_login,
    api_make_quiz,
    api_make_session,
    api_queue_quiz_run,
    api_start_session,
    ask_query_api,
)

VIEWPORTS = {
    "desk": {"width": 1280, "height": 800},
    "phone": {"width": 390, "height": 844},
    "small": {"width": 360, "height": 740},
}

# Per-page checks (UC-X-12, UC-X-13). Returns lists of offenders.
PAGE_CHECKS_JS = """(opts) => {
  // checkVisibility() also excludes the contents of a closed <details>,
  // which Chromium keeps laid out.
  const vis = e => { const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && e.checkVisibility({ visibilityProperty: true }); };
  const name = e => (e.getAttribute('aria-label') || e.getAttribute('title') || (e.textContent || '').trim()
    || e.id || e.tagName).replace(/\\s+/g, ' ').slice(0, 40);
  const controls = [...document.querySelectorAll('button, input:not([type=hidden]), select, textarea, summary')].filter(vis);
  const unnamed = controls.filter(e => !(e.getAttribute('aria-label') || e.getAttribute('aria-labelledby')
      || (e.labels && e.labels.length) || (e.textContent || '').trim() || e.getAttribute('title')))
    .map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : ''));
  const out = { overflow: document.documentElement.scrollWidth - innerWidth, unnamed };
  if (opts.phone) {
    out.smallInputs = controls.filter(e => ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.tagName)
        && !['checkbox', 'radio', 'file'].includes(e.type) && parseFloat(getComputedStyle(e).fontSize) < 16)
      .map(e => name(e) + ' ' + getComputedStyle(e).fontSize);
  }
  if (opts.desk) {
    const scale = [34, 26, 20];
    const offScale = h => !scale.some(s => Math.abs(h - s) <= 1);
    out.offScale = [...document.querySelectorAll('button')].filter(vis)
      .filter(e => !e.closest('.option, .stars, .vote-btn') && !e.classList.contains('option'))
      .filter(e => offScale(e.getBoundingClientRect().height))
      .map(e => name(e) + ' ' + Math.round(e.getBoundingClientRect().height));
    out.offScale.push(...[...document.querySelectorAll('.profile-cta')].filter(vis)
      .filter(e => Math.abs(e.getBoundingClientRect().height - 34) > 1).map(e => 'profile-cta'));
  }
  if (opts.touch) {
    out.shortTargets = [...document.querySelectorAll('button, details.menu > summary, .section-links a')].filter(vis)
      .filter(e => e.getBoundingClientRect().height < 32)
      .map(e => name(e) + ' ' + Math.round(e.getBoundingClientRect().height));
  }
  return out;
}"""


def _seed(base_url):
    """Live session (questions, live + queued runs), a not-started session,
    and an ended session with a closed run."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"Agentic coding fundamentals {secrets.token_hex(3)}", publish=True)
    other = api_make_quiz(c, f"Python warm-up {secrets.token_hex(3)}", publish=True)
    live = api_make_session(c, f"UI-X12 session with a long title {secrets.token_hex(3)}")
    api_start_session(c, live["code"])
    api_queue_quiz_run(c, live["code"], other["id"])
    run = api_queue_quiz_run(c, live["code"], quiz["id"])
    c.post(f"/api/sessions/{live['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    ask_query_api(base_url, live["code"], "A question long enough to need several lines on a narrow phone screen?")
    planning = api_make_session(c, f"UI-X12 planning {secrets.token_hex(3)}")
    ended = api_make_session(c, f"UI-X12 ended {secrets.token_hex(3)}")
    closed = api_queue_quiz_run(c, ended["code"], other["id"])
    c.post(f"/api/sessions/{ended['code']}/quiz_runs/{closed['id']}/start").raise_for_status()
    c.post(f"/api/sessions/{ended['code']}/quiz_runs/{closed['id']}/close").raise_for_status()
    c.post(f"/api/sessions/{ended['code']}/end").raise_for_status()
    return c, quiz, live, planning, ended


def _pages(quiz, live, planning, ended):
    """(label, url, needs_admin, prepare) for every surface and state."""
    def open_editor(page):
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).locator("td").first.click()
        page.wait_for_selector("#editor-body .editor-q")

    def open_results(page):
        page.locator("#qs-rows tr").first.click()
        page.wait_for_selector("#results-body .result-q")

    return [
        ("landing signed out", "/", False, lambda p: p.wait_for_selector("#login-card:visible")),
        ("landing signed in", "/", True, lambda p: p.wait_for_selector("#session-rows tr.rowable")),
        ("quiz library", "/quizzes", True, lambda p: p.wait_for_selector("#quiz-rows tr.rowable")),
        ("quiz editor", "/quizzes", True, open_editor),
        ("run results", "/quizzes", True, open_results),
        ("session live", f"/m/{live['code']}", True, lambda p: p.wait_for_selector("#queries .question")),
        ("session planning", f"/m/{planning['code']}", True, lambda p: p.wait_for_selector("#settings-card:visible")),
        ("session ended", f"/m/{ended['code']}", True, lambda p: p.wait_for_selector("#quiz-runs .badge-closed")),
        ("participant live", f"/s/{live['code']}", False, lambda p: p.wait_for_selector("#quiz-body .option")),
        ("participant ended", f"/s/{ended['code']}", False, lambda p: p.wait_for_selector("#ended-card:visible")),
        ("projector", f"/p/{live['code']}", False, lambda p: p.wait_for_selector("#quiz-body .option")),
    ]


def _sweep(browser, base_url, viewport, *, touch=False):
    c, quiz, live, planning, ended = _seed(base_url)
    failures = []
    try:
        for label, url, needs_admin, prepare in _pages(quiz, live, planning, ended):
            ctx = browser.new_context(viewport=VIEWPORTS[viewport], has_touch=touch, is_mobile=touch)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)[:120]))
            page.on("console", lambda m: errors.append(m.text[:120]) if m.type == "error" else None)
            try:
                if needs_admin:
                    admin_login_via_ui(page, base_url)
                page.goto(base_url + url)
                prepare(page)
                page.wait_for_timeout(200)
                result = page.evaluate(PAGE_CHECKS_JS, {
                    "phone": viewport != "desk", "desk": viewport == "desk", "touch": touch})
                # A mobile-emulating context widens innerWidth to fit content,
                # so measure overflow against the configured width there.
                if touch:
                    result["overflow"] = page.evaluate(
                        "document.documentElement.scrollWidth") - VIEWPORTS[viewport]["width"]
                problems = {k: v for k, v in result.items() if (v if k != "overflow" else v > 0)}
                if errors:
                    problems["errors"] = errors
                if problems:
                    failures.append(f"{label} @ {viewport}{' touch' if touch else ''}: {problems}")
            finally:
                ctx.close()
    finally:
        c.close()
    assert failures == [], "\n".join(failures)


def test_uc_x_12_sweep_desktop(base_url, admin_setup, browser):
    """UC-X-12/13: every page at 1280 px — no overflow, errors, unnamed controls, off-scale buttons."""
    _sweep(browser, base_url, "desk")


def test_uc_x_12_sweep_phone(base_url, admin_setup, browser):
    """UC-X-12: every page at 390 px — no overflow, errors, unnamed controls, sub-16 px inputs."""
    _sweep(browser, base_url, "phone")


def test_uc_x_12_sweep_small_phone(base_url, admin_setup, browser):
    """UC-X-12: every page at 360 px."""
    _sweep(browser, base_url, "small")


def test_uc_x_12_sweep_touch(base_url, admin_setup, browser):
    """UC-X-12: every page at 390 px on a touch device — tap targets at least 32 px."""
    _sweep(browser, base_url, "phone", touch=True)


# ---------- UC-X-13 ----------

SIZES_JS = """(sels) => sels.map(s => { const e = document.querySelector(s); const r = e.getBoundingClientRect();
  return { sel: s, h: r.height, fs: getComputedStyle(e).fontSize }; })"""


def _assert_same_scale(sizes):
    heights = [x["h"] for x in sizes]
    assert max(heights) - min(heights) <= 1, sizes
    assert max(heights) <= 36, sizes
    assert all(x["fs"] == "14px" for x in sizes), sizes


def test_uc_x_13_participant_actions_share_one_size(base_url, admin_setup, page):
    """UC-X-13: the participant page's card actions share the default button size."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-X13 {secrets.token_hex(3)}")
    c.post(f"/api/sessions/{s['code']}/feedback_enabled", json={"enabled": True}).raise_for_status()
    try:
        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#feedback-card:visible")
        _assert_same_scale(page.evaluate(SIZES_JS, [".profile-cta", "#fb-submit", "#ask-btn"]))
    finally:
        c.close()


def test_uc_x_13_landing_actions_share_one_size(base_url, admin_setup, page):
    """UC-X-13: Join and Log in use the default button size."""
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(base_url + "/")
    page.wait_for_selector("#login-card:visible")
    _assert_same_scale(page.evaluate(SIZES_JS, ["#join-btn", "#li-btn"]))


# ---------- UC-X-14 ----------



def test_uc_x_14_revealed_answers_match_on_every_surface(base_url, admin_setup, browser):
    """UC-X-14: after reveal, participant, session page, and projector agree."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-X14 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-X14s {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/reveal", json={"reveal": True}).raise_for_status()
    pages = []
    try:
        for url, login in ((f"/s/{s['code']}", False), (f"/m/{s['code']}", True), (f"/p/{s['code']}", False)):
            ctx = browser.new_context()
            page = ctx.new_page()
            pages.append(ctx)
            if login:
                admin_login_via_ui(page, base_url)
            page.goto(base_url + url)
            options = page.locator(".option")
            expect(options.first).to_be_visible(timeout=5000)
            correct = page.locator(".option.correct")
            expect(correct).to_have_count(1)
            expect(correct.locator(".opt-correct")).to_have_text("✓ Correct")
            for pct in page.locator(".opt-pct").all_inner_texts():
                assert re.fullmatch(r"\d+ \(\d+%\)", pct), (url, pct)
    finally:
        for ctx in pages:
            ctx.close()
        c.close()
