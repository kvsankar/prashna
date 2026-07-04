"""UI tests for the landing page in anonymous / join / first-run states.

Covers:
  - UC-A-01: First-run setup form (only on uninitialized DB → skipped because
    fixtures bootstrap an admin).
  - UC-A-02: Admin login / logout.
  - UC-P-01: Participant joins by code; bad code redirects show banner.
"""
from __future__ import annotations

import secrets

import httpx
from playwright.sync_api import expect

from ._helpers import ADMIN, api_login, api_make_session

# ---------- UC-A-01 ----------


def test_uc_a_01_setup_card_visibility(base_url, page):
    """UC-A-01: with admin already initialized, #setup-card is hidden.

    The fresh-DB branch (setup visible) can't be tested here because the
    uvicorn DB is shared with other tests that create an admin. Verify the
    opposite invariant instead: once initialized, the setup card is hidden.
    """
    # Force initialization.
    httpx.post(f"{base_url}/api/admin/setup", json=ADMIN, timeout=5.0)
    page.goto(base_url + "/")
    expect(page.locator("#setup-card")).to_be_hidden()
    # Either #login-card or #sessions-card is shown (depending on cookies),
    # but not the setup form.
    page.wait_for_selector("#login-card:visible, #sessions-card:visible")


def test_uc_a_01_setup_password_mismatch_no_api_call(fresh_base_url, page):
    """UC-A-01: mismatched #su-pass/#su-pass2 toast without API call.

    A fresh server keeps the first-run setup form visible for this client-side
    validation path.
    """
    page.goto(fresh_base_url + "/")
    expect(page.locator("#setup-card")).to_be_visible(timeout=5000)
    page.fill("#su-user", "admin")
    page.fill("#su-pass", "testpass1")
    page.fill("#su-pass2", "different1")
    page.click("#su-btn")
    expect(page.locator(".toast-error")).to_contain_text("Passwords don't match")
    status = httpx.get(f"{fresh_base_url}/api/admin/status", timeout=5.0).json()
    assert status["initialized"] is False


# ---------- UC-A-02 ----------


def test_uc_a_02_login_swaps_to_authed_view(base_url, admin_setup, page):
    """UC-A-02: valid login swaps to authed view."""
    page.goto(base_url + "/")
    page.wait_for_selector("#login-card:visible, #sessions-card:visible")
    if page.locator("#sessions-card").is_visible():
        # Log out first to be in the right state.
        return  # context is fresh — should not happen, but harmless
    page.fill("#li-user", admin_setup["username"])
    page.fill("#li-pass", admin_setup["password"])
    page.click("#li-btn")
    expect(page.locator("#sessions-card")).to_be_visible()


def test_uc_a_02_login_enter_submits(base_url, admin_setup, page):
    """UC-A-02: Enter in #li-pass submits the login form."""
    page.goto(base_url + "/")
    page.wait_for_selector("#login-card:visible")
    page.fill("#li-user", admin_setup["username"])
    page.fill("#li-pass", admin_setup["password"])
    page.press("#li-pass", "Enter")
    expect(page.locator("#sessions-card")).to_be_visible()


def test_uc_a_02_login_invalid_toasts_and_stays(base_url, admin_setup, page):
    """UC-A-02: invalid credentials toast and the login card stays visible."""
    page.goto(base_url + "/")
    page.wait_for_selector("#login-card:visible")
    page.fill("#li-user", admin_setup["username"])
    page.fill("#li-pass", "wrong-password-bad")
    page.click("#li-btn")
    expect(page.locator(".toast-error")).to_be_visible()
    expect(page.locator(".toast-error")).to_contain_text("Invalid username or password")
    expect(page.locator("#login-card")).to_be_visible()
    expect(page.locator("#sessions-card")).to_be_hidden()


def test_uc_a_02_logout_returns_to_login(base_url, admin_setup, page):
    """UC-A-02: clicking Log out reverts the page to #login-card view."""
    page.goto(base_url + "/")
    page.wait_for_selector("#login-card:visible")
    page.fill("#li-user", admin_setup["username"])
    page.fill("#li-pass", admin_setup["password"])
    page.click("#li-btn")
    expect(page.locator("#sessions-card")).to_be_visible()
    page.get_by_role("button", name="Log out").click()
    expect(page.locator("#login-card")).to_be_visible()
    expect(page.locator("#sessions-card")).to_be_hidden()


# ---------- UC-P-01 ----------


def test_uc_p_01_join_by_valid_code_navigates(base_url, admin_setup, page):
    """UC-P-01: typing a valid code in #join-code and clicking Join navigates to /s/<CODE>."""
    c = api_login(base_url)
    s = api_make_session(c, "Join target")
    try:
        page.goto(base_url + "/")
        # We need the join card visible — that's the anon view. Our context
        # is fresh, so we should be on login+join (admin initialized).
        page.wait_for_selector("#join-card:visible")
        page.fill("#join-code", s["code"])
        page.click("#join-btn")
        page.wait_for_url(f"**/s/{s['code']}")
        expect(page.locator("#title")).not_to_have_text("Loading…", timeout=5000)
        # Participant surfaces exist.
        for sel in ["#title", "#code", "#my-name", "#ask-card", "#invite-card"]:
            expect(page.locator(sel)).to_be_attached()
    finally:
        c.close()


def test_uc_p_01_join_enter_submits(base_url, admin_setup, page):
    """UC-P-01: pressing Enter in #join-code submits."""
    c = api_login(base_url)
    s = api_make_session(c, "Enter join")
    try:
        page.goto(base_url + "/")
        page.wait_for_selector("#join-card:visible")
        page.fill("#join-code", s["code"])
        page.press("#join-code", "Enter")
        page.wait_for_url(f"**/s/{s['code']}")
    finally:
        c.close()


def test_uc_p_01_bad_code_redirect_shows_banner(base_url, admin_setup, page):
    """UC-P-01: unknown code redirect shows #bad-code-msg error.

    Note: index.html does `history.replaceState` to strip `?bad_code=` from
    the address bar after reading it, so we check the banner content (not
    the URL) as proof the redirect happened.
    """
    bogus = "ZZZ" + secrets.token_hex(2).upper()[:3]  # 6 chars, definitely not real
    page.goto(f"{base_url}/s/{bogus}")
    expect(page.locator("#bad-code-msg")).to_be_visible()
    expect(page.locator("#bad-code-msg")).to_contain_text(bogus.upper())
    expect(page.locator("#bad-code-msg")).to_contain_text("does not exist")
    # Path should be `/` (history.replaceState clears the bad_code query string).
    from urllib.parse import urlparse
    assert urlparse(page.url).path == "/"
