"""UC-X-12: phone-width layout across surfaces."""
from __future__ import annotations

import secrets

from ._helpers import (
    admin_login_via_ui,
    api_login,
    api_make_quiz,
    api_make_session,
    api_queue_quiz_run,
    api_start_session,
    ask_query_api,
)

PHONE = {"width": 390, "height": 844}


def _live_fixture(base_url):
    """A live session with a long-titled live run, a queued run, and a question."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"Agentic coding fundamentals {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-X12 session with a long title {secrets.token_hex(3)}")
    api_start_session(c, s["code"])
    api_queue_quiz_run(c, s["code"], quiz["id"])
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    ask_query_api(base_url, s["code"], "A question long enough to need several lines on a narrow phone screen?")
    return c, quiz, s


def _open_editor(page, base_url, title):
    page.goto(base_url + "/quizzes")
    page.locator("#quiz-rows tr").filter(has_text=title).locator("td").first.click()
    page.wait_for_selector("#editor-body .editor-q")


def _scroll_width(page) -> int:
    return page.evaluate("document.documentElement.scrollWidth")


def test_uc_x_12_no_sideways_scroll_at_phone_width(base_url, admin_setup, page):
    """UC-X-12: at 390 px no page scrolls sideways."""
    c, quiz, s = _live_fixture(base_url)
    try:
        page.set_viewport_size(PHONE)
        admin_login_via_ui(page, base_url)
        page.wait_for_selector("#session-rows tr.rowable")
        assert _scroll_width(page) <= 390, "/"
        _open_editor(page, base_url, quiz["title"])
        assert _scroll_width(page) <= 390, "/quizzes"
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-runs .badge-live")
        page.wait_for_selector("#queries .question")
        assert _scroll_width(page) <= 390, "/m"
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-body .option")
        assert _scroll_width(page) <= 390, "/s"
        page.goto(f"{base_url}/p/{s['code']}")
        page.wait_for_selector("#quiz-body .option")
        assert _scroll_width(page) <= 390, "/p"
    finally:
        c.close()


SMALL_FONT_JS = """() => [...document.querySelectorAll('input[type=text], input:not([type]), textarea, select')]
  .filter(e => e.getBoundingClientRect().width > 0)
  .filter(e => parseFloat(getComputedStyle(e).fontSize) < 16)
  .map(e => (e.id || e.getAttribute('aria-label') || e.tagName) + ' ' + getComputedStyle(e).fontSize)"""


def test_uc_x_12_inputs_are_16px_on_phones(base_url, admin_setup, page):
    """UC-X-12: text inputs are at least 16 px at phone width (no iOS focus zoom)."""
    c, quiz, s = _live_fixture(base_url)
    try:
        page.set_viewport_size(PHONE)
        admin_login_via_ui(page, base_url)
        _open_editor(page, base_url, quiz["title"])
        assert page.evaluate(SMALL_FONT_JS) == [], "/quizzes"
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#queries .question")
        assert page.evaluate(SMALL_FONT_JS) == [], "/m"
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-body .option")
        assert page.evaluate(SMALL_FONT_JS) == [], "/s"
    finally:
        c.close()


SHORT_TARGETS_JS = """(sel) => [...document.querySelectorAll(sel)]
  .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
  .filter(e => e.getBoundingClientRect().height < 32)
  .map(e => ((e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 30)) + ' ' + Math.round(e.getBoundingClientRect().height))"""


def test_uc_x_12_touch_targets_at_least_32px(base_url, admin_setup, browser):
    """UC-X-12: on touch devices, buttons, menu toggles, and section links are >= 32 px tall."""
    c, quiz, s = _live_fixture(base_url)
    ctx = browser.new_context(viewport=PHONE, has_touch=True, is_mobile=True)
    try:
        page = ctx.new_page()
        assert page.evaluate("matchMedia('(pointer: coarse)').matches")
        admin_login_via_ui(page, base_url)
        _open_editor(page, base_url, quiz["title"])
        sel = "button, details.menu > summary, .section-links a"
        assert page.evaluate(SHORT_TARGETS_JS, sel) == [], "/quizzes"
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#queries .question")
        assert page.evaluate(SHORT_TARGETS_JS, sel) == [], "/m"
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-body .option")
        assert page.evaluate(SHORT_TARGETS_JS, ".section-links a") == [], "/s"
    finally:
        ctx.close()
        c.close()
