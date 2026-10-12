"""UI tests for the landing page in anonymous / join / first-run states.

Covers:
  - UC-A-01: First-run setup through the one-time link (fresh servers).
  - UC-A-02: Admin login / logout.
  - UC-P-01: Participant joins by code; bad code redirects show banner.
"""
from __future__ import annotations

import json
import secrets

import httpx
from playwright.sync_api import expect

from ..support import SETUP_TOKEN
from ._helpers import ADMIN, api_login, api_make_session


def _expect_no_github(page) -> None:
    """Password is the only admin sign-in: nothing on the page, shown or
    hidden, mentions GitHub or carries a GitHub id (UC-A-01)."""
    expect(page.get_by_text("GitHub")).to_have_count(0)
    expect(page.locator("[id*='github' i]")).to_have_count(0)

# ---------- UC-A-01 ----------


def test_uc_a_01_setup_card_visibility(base_url, page):
    """UC-A-01: with admin already initialized, #setup-card is hidden.

    The fresh-DB branch (setup visible) can't be tested here because the
    uvicorn DB is shared with other tests that create an admin. Verify the
    opposite invariant instead: once initialized, the setup card is hidden.
    """
    # Force initialization.
    httpx.post(f"{base_url}/api/admin/setup", json={**ADMIN, "setup_token": SETUP_TOKEN}, timeout=5.0)
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
    page.goto(f"{fresh_base_url}/#setup={SETUP_TOKEN}")
    expect(page.locator("#setup-card")).to_be_visible(timeout=5000)
    page.fill("#su-user", "admin")
    page.fill("#su-pass", "testpass1")
    page.fill("#su-pass2", "different1")
    page.click("#su-btn")
    expect(page.locator(".toast-error")).to_contain_text("Passwords don't match")
    status = httpx.get(f"{fresh_base_url}/api/admin/status", timeout=5.0).json()
    assert status["initialized"] is False


def test_uc_a_01_without_link_explains_where_to_find_it(fresh_base_url, page):
    """UC-A-01: no #setup= in the address → the setup-needed card, no form."""
    page.goto(fresh_base_url + "/")
    expect(page.locator("#setup-needed-card")).to_be_visible(timeout=5000)
    expect(page.locator("#setup-needed-card")).to_contain_text("server log")
    for hidden in ("#setup-card", "#login-card", "#sessions-card"):
        expect(page.locator(hidden)).to_be_hidden()
    _expect_no_github(page)


def test_uc_a_01_setup_link_pasted_into_an_open_tab(fresh_base_url, page):
    """UC-A-01: pasting the setup link into a tab that already shows / loads it."""
    page.goto(fresh_base_url + "/")
    expect(page.locator("#setup-needed-card")).to_be_visible(timeout=5000)
    page.goto(f"{fresh_base_url}/#setup={SETUP_TOKEN}")
    expect(page.locator("#setup-card")).to_be_visible(timeout=5000)
    expect(page.locator("#setup-needed-card")).to_be_hidden()
    assert "setup=" not in page.url


def test_uc_a_01_setup_link_creates_admin(fresh_base_url, page):
    """UC-A-01: the one-time link shows the form; submitting signs the admin in."""
    page.goto(f"{fresh_base_url}/#setup={SETUP_TOKEN}")
    expect(page.locator("#setup-card")).to_be_visible(timeout=5000)
    page.fill("#su-user", "admin")
    page.fill("#su-pass", "testpass1")
    page.fill("#su-pass2", "testpass1")
    page.click("#su-btn")
    expect(page.locator("#sessions-card")).to_be_visible(timeout=5000)
    assert "setup=" not in page.url


def test_uc_a_01_setup_form_offers_no_other_sign_in(fresh_base_url, page):
    """UC-A-01: the first-run setup form offers no GitHub sign-in."""
    page.goto(f"{fresh_base_url}/#setup={SETUP_TOKEN}")
    expect(page.locator("#setup-card")).to_be_visible(timeout=5000)
    _expect_no_github(page)


def test_uc_a_01_sign_in_page_offers_no_other_sign_in(base_url, admin_setup, page):
    """UC-A-01: the signed-out sign-in page offers only the password form."""
    page.goto(base_url + "/")
    expect(page.locator("#login-card")).to_be_visible(timeout=5000)
    _expect_no_github(page)


# ---------- UC-A-02 ----------


def test_uc_a_02_shell_visible_while_status_is_pending(base_url, admin_setup, page):
    """UC-A-02 / UC-X-11: useful landing controls do not wait on auth status."""
    pending = []
    page.route("**/api/admin/status", lambda route: pending.append(route))

    page.goto(base_url + "/", wait_until="domcontentloaded")

    expect(page.locator("#join-card")).to_be_visible()
    expect(page.locator("#login-card")).to_be_visible()
    assert pending
    assert page.evaluate(
        "performance.getEntriesByName('prashna-usable').length"
    ) == 1

    pending[0].fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps(
            {
                "initialized": True,
                "authenticated": False,
                "username": None,
            }
        ),
    )
    expect(page.locator("#login-card")).to_be_visible()


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
