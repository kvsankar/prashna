"""UI tests for UC-A-30: Export ▾ menus start a JSON or Excel download."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

import httpx
from playwright.sync_api import expect

from ._helpers import (
    admin_login_via_ui,
    api_login,
    api_make_quiz,
    api_make_session,
    api_queue_quiz_run,
)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _download(page, menu, label: str) -> str:
    """Open an Export ▾ menu, pick a format, and return the suggested filename."""
    menu.locator("summary").click()
    with page.expect_download() as info:
        menu.get_by_role("link", name=label, exact=True).click()
    return info.value.suggested_filename


def test_uc_a_30_sessions_list_exports_all_sessions(base_url, admin_setup, page):
    """UC-A-30: the session list's Export ▾ downloads every session as Excel."""
    c = api_login(base_url)
    api_make_session(c, f"UI-A30 {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        menu = page.locator("#all-export")
        expect(menu).to_be_visible()
        expect(menu.locator("summary")).to_have_text("Export all data ▾")
        expect(page.get_by_role("link", name="Open quiz library →")).to_have_attribute("href", "/quizzes")
        assert _download(page, menu, "Excel") == f"prashna-all-data-{_today()}.xlsx"
    finally:
        c.close()


def test_uc_a_30_session_page_exports_for_the_owner(base_url, admin_setup, page):
    """UC-A-30: the owner exports the session, its Q&A, its profiles, and its feedback."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A30s {secrets.token_hex(3)}")
    code = s["code"]
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{code}")
        page.wait_for_selector("#settings-card:visible")
        expect(page.locator("#lifecycle-card #session-export")).to_be_visible()
        expect(page.locator("#session-export summary")).to_have_text("Export session ▾")
        expect(page.locator("#settings-card #session-export")).to_have_count(0)
        expect(page.locator("#queries-card #qna-export")).to_be_visible()
        assert _download(page, page.locator("#session-export"), "JSON") == f"prashna-session-{code}-{_today()}.json"
        assert _download(page, page.locator("#qna-export"), "Excel") == f"prashna-qna-{code}-{_today()}.xlsx"
        assert _download(page, page.locator("#profiles-export"), "JSON") == f"prashna-profiles-{code}-{_today()}.json"
        assert _download(page, page.locator("#feedback-export"), "JSON") == f"prashna-feedback-{code}-{_today()}.json"
    finally:
        c.close()


def test_uc_a_30_session_export_stays_visible_after_end(base_url, admin_setup, page):
    """UC-A-30: the whole-session export sits in the Lifecycle card, so it shows after End."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A30e {secrets.token_hex(3)}")
    code = s["code"]
    c.post(f"/api/sessions/{code}/start").raise_for_status()
    c.post(f"/api/sessions/{code}/end").raise_for_status()
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{code}")
        expect(page.locator("#session-status")).to_have_text("Ended")
        expect(page.locator("#lifecycle-card #session-export")).to_be_visible()
        assert _download(page, page.locator("#session-export"), "Excel") == f"prashna-session-{code}-{_today()}.xlsx"
    finally:
        c.close()


def test_uc_a_30_delegate_sees_no_export(base_url, admin_setup, page):
    """UC-A-30: a delegate moderator is never offered an export."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A30d {secrets.token_hex(3)}")
    c.close()
    page.goto(f"{base_url}/m/{s['code']}#k={s['mod_key']}")
    page.wait_for_selector("#profiles-card:visible")
    for sel in ("#session-export", "#qna-export", "#profiles-export", "#feedback-export"):
        expect(page.locator(sel)).to_be_hidden()


def test_uc_a_30_quiz_library_exports_quiz_and_run(base_url, admin_setup, page):
    """UC-A-30: a quiz row's ⋯ menu and the run report each offer an export."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-A30q {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-A30r {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    try:
        admin_login_via_ui(page, base_url)
        page.goto(base_url + "/quizzes")
        row = page.locator("#quiz-rows tr", has_text=quiz["title"])
        assert _download(page, row.locator("details.row-more"), "Export Excel") == (
            f"prashna-quiz-{quiz['id']}-{_today()}.xlsx")

        page.goto(f"{base_url}/quizzes?run={run['id']}")
        expect(page.locator("#results-card")).to_be_visible(timeout=5000)
        assert _download(page, page.locator("#results-export"), "JSON") == (
            f"prashna-quiz-run-{run['id']}-{_today()}.json")
    finally:
        c.close()


def test_uc_a_30_export_link_needs_the_admin_cookie(base_url, admin_setup):
    """UC-A-30: the download URL behind the menu refuses a cookieless request."""
    r = httpx.get(f"{base_url}/api/export/all?format=json", timeout=5.0)
    assert r.status_code == 401
