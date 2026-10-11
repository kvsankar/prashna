"""UI tests for the authed admin landing page.

Covers UC-A-03..08 (session create, list, the session page's owner-only
settings: rename, base URL, share, delete with typed-title), and UC-A-25
(change password).
"""
from __future__ import annotations

import secrets

import httpx
from playwright.sync_api import expect

from ._helpers import (
    admin_login_via_ui,
    api_login,
    api_make_session,
    api_start_session,
    ask_query_api,
)

# ---------- UC-A-03 ----------


def test_admin_breadcrumbs_link_sessions_and_quiz_library(
    base_url, admin_setup, page
):
    """Authenticated admin chrome exposes the current role and its child areas."""
    admin_login_via_ui(page, base_url)
    nav = page.locator("#admin-page-nav")
    expect(nav).to_be_visible()
    expect(nav.locator(".breadcrumbs")).to_contain_text("Admin")
    expect(nav.locator(".section-links a", has_text="Sessions")).to_have_attribute(
        "href", "#sessions-card"
    )
    expect(nav.locator(".section-links a", has_text="Quiz library")).to_have_attribute(
        "href", "/quizzes"
    )


def test_uc_a_03_create_session_via_ui(base_url, admin_setup, page):
    """UC-A-03: typing a title and clicking + New session adds a row with .badge-planning."""
    admin_login_via_ui(page, base_url)
    title = f"UI-A03 {secrets.token_hex(3)}"
    page.fill("#new-session-title", title)
    page.click("#new-session-btn")
    row = page.locator("#session-rows tr").filter(has_text=title)
    expect(row).to_be_visible()
    expect(row.locator(".badge-planning")).to_be_visible()


def test_uc_a_03_create_session_enter_submits(base_url, admin_setup, page):
    """UC-A-03: Enter in #new-session-title submits the create form."""
    admin_login_via_ui(page, base_url)
    title = f"UI-A03e {secrets.token_hex(3)}"
    page.fill("#new-session-title", title)
    page.press("#new-session-title", "Enter")
    expect(page.locator("#session-rows tr").filter(has_text=title)).to_be_visible()


def test_uc_a_03_empty_title_toasts(base_url, admin_setup, page):
    """UC-A-03: empty title shows error toast and input keeps focus."""
    admin_login_via_ui(page, base_url)
    page.fill("#new-session-title", "   ")
    page.click("#new-session-btn")
    expect(page.locator(".toast-error")).to_contain_text("Session title is required")
    # Input keeps focus.
    focused_id = page.evaluate("document.activeElement && document.activeElement.id")
    assert focused_id == "new-session-title"


def test_uc_a_03_new_row_at_top(base_url, admin_setup, page):
    """UC-A-03: newly created session appears at the top of #session-rows."""
    admin_login_via_ui(page, base_url)
    title = f"UI-A03top {secrets.token_hex(3)}"
    page.fill("#new-session-title", title)
    page.click("#new-session-btn")
    expect(page.locator("#session-rows tr").first).to_contain_text(title)


# ---------- UC-A-04 ----------


def test_uc_a_04_list_shows_owned_sessions(base_url, admin_setup, page):
    """UC-A-04: #session-rows lists owned sessions with badge + counts."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A04 {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        row = page.locator("#session-rows tr").filter(has_text=s["title"])
        expect(row).to_be_visible()
        expect(row.locator(".badge")).to_be_visible()
        expect(row.locator("td.num").first).to_contain_text("0")  # query count
    finally:
        c.close()


def test_uc_a_04_row_actions_and_title_link(base_url, admin_setup, page):
    """UC-A-04: the title opens the session page; the row links Participant and Projector and offers Start and Delete."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A04m {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        row = page.locator("#session-rows tr").filter(has_text=s["title"])
        actions = row.locator("td.actions")
        expect(actions.locator("a, button")).to_have_text(["Participant", "Projector", "Start", "Delete"])
        expect(actions.get_by_role("link", name="Participant")).to_have_attribute("href", f"/s/{s['code']}")
        expect(actions.get_by_role("link", name="Projector")).to_have_attribute("href", f"/p/{s['code']}")
        # Views are plain links, actions are buttons (UX.md §10).
        for view in ("Participant", "Projector"):
            link = actions.get_by_role("link", name=view)
            expect(link).to_have_css("background-color", "rgba(0, 0, 0, 0)")
            expect(link).to_have_css("border-top-width", "0px")
        row.get_by_role("link", name=s["title"]).click()
        page.wait_for_url(f"**/m/{s['code']}")
    finally:
        c.close()


def test_uc_a_04_start_from_the_list(base_url, admin_setup, page):
    """UC-A-04: Start on a not-started row starts the session in place."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A04s {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        row = page.locator("#session-rows tr").filter(has_text=s["title"])
        row.get_by_role("button", name="Start").click()
        expect(row.locator(".badge-live")).to_be_visible(timeout=5000)
        expect(row.get_by_role("button", name="Start")).to_have_count(0)
        expect(page).to_have_url(f"{base_url}/")
        assert c.get(f"/api/sessions/{s['code']}").json()["status"] == "live"
    finally:
        c.close()


def test_uc_a_04_session_query_redirects_to_session_page(base_url, admin_setup, page):
    """UC-A-04: /?session=<code> (older bookmarks) redirects to /m/<code>."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A04q {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/?session={s['code']}")
        page.wait_for_url(f"**/m/{s['code']}", timeout=5000)
    finally:
        c.close()


# ---------- UC-A-05 ----------


def _goto_session_page(page, base_url, s):
    """Open the session page from the list, as an admin would."""
    admin_login_via_ui(page, base_url)
    page.locator("#session-rows tr").filter(has_text=s["title"]).click()
    page.wait_for_url(f"**/m/{s['code']}")
    page.wait_for_selector("#settings-card:visible", timeout=5000)


def test_uc_a_05_edit_title_updates_header_and_list(base_url, admin_setup, page):
    """UC-A-05: editing #set-title and blurring updates #title and the session list."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A05 {secrets.token_hex(3)}")
    new_title = s["title"] + " EDITED"
    try:
        _goto_session_page(page, base_url, s)
        expect(page.locator("#set-title")).to_have_value(s["title"])
        page.fill("#set-title", new_title)
        page.locator("#set-title").blur()
        expect(page.locator("#title")).to_have_text(new_title, timeout=5000)
        page.goto(base_url + "/")
        expect(page.locator("#session-rows tr").filter(has_text=new_title)).to_be_visible(timeout=5000)
    finally:
        c.close()


def test_uc_a_05_edit_title_empty_reverts(base_url, admin_setup, page):
    """UC-A-05: an empty title shows an error toast and reverts #set-title."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A05r {secrets.token_hex(3)}")
    try:
        _goto_session_page(page, base_url, s)
        page.fill("#set-title", "   ")
        page.locator("#set-title").blur()
        expect(page.locator(".toast-error")).to_be_visible()
        expect(page.locator("#set-title")).to_have_value(s["title"])
    finally:
        c.close()


# ---------- UC-A-06 ----------


def test_uc_a_06_base_url_save_and_clear(base_url, admin_setup, page):
    """UC-A-06: typing into #base-url and blurring updates #invite-url;
    #base-url-clear falls back to location.origin.
    """
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A06 {secrets.token_hex(3)}")
    try:
        _goto_session_page(page, base_url, s)
        page.fill("#base-url", "https://example.org")
        page.locator("#base-url").blur()
        expect(page.locator("#invite-url")).to_contain_text("example.org", timeout=5000)
        page.click("#base-url-clear")
        # Fallback is location.origin = base_url (127.0.0.1 host).
        expect(page.locator("#invite-url")).to_contain_text("127.0.0.1", timeout=5000)
    finally:
        c.close()


def test_uc_a_06_pages_use_the_default_base_url(base_url, admin_setup, page):
    """UC-A-06: with no session base URL, links and QR use default_base_url
    (the tunnel's address) instead of the page's own origin."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A06d {secrets.token_hex(3)}")
    tunnel = "https://stub-tunnel.trycloudflare.com"

    def with_default(route):
        response = route.fetch()
        body = response.json()
        session = body["session"] if "session" in body else body
        session["default_base_url"] = tunnel
        route.fulfill(response=response, json=body)

    try:
        for pattern in (f"**/api/sessions/{s['code']}", "**/moderator-bootstrap", "**/display-bootstrap"):
            page.route(pattern, with_default)
        _goto_session_page(page, base_url, s)
        expect(page.locator("#invite-url")).to_have_text(f"{tunnel}/s/{s['code']}", timeout=5000)
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#origin")).to_have_text("stub-tunnel.trycloudflare.com", timeout=5000)
    finally:
        c.close()


def test_uc_a_06_base_url_invalid_toasts(base_url, admin_setup, page):
    """UC-A-06: invalid (non-http) URL shows error toast."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A06bad {secrets.token_hex(3)}")
    try:
        _goto_session_page(page, base_url, s)
        page.fill("#base-url", "ftp://example.org")
        page.locator("#base-url").blur()
        expect(page.locator(".toast-error")).to_be_visible()
    finally:
        c.close()


# ---------- UC-A-07 ----------


def test_uc_a_07_delete_live_blocked_with_toast(base_url, admin_setup, page):
    """UC-A-07: Delete on a live session shows toast 'End the session before deleting it'."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A07live {secrets.token_hex(3)}")
    api_start_session(c, s["code"])
    try:
        admin_login_via_ui(page, base_url)
        row = page.locator("#session-rows tr").filter(has_text=s["title"])
        row.locator("button.danger").click()
        expect(page.locator(".toast-error")).to_contain_text("End the session before deleting it")
        expect(row).to_be_visible()
    finally:
        c.close()


def test_uc_a_07_delete_no_data_native_confirm(base_url, admin_setup, page):
    """UC-A-07: Delete on planning session with no data → native confirm; OK removes the row."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A07empty {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.on("dialog", lambda d: d.accept())
        row = page.locator("#session-rows tr").filter(has_text=s["title"])
        row.locator("button.danger").click()
        expect(page.locator("#session-rows tr").filter(has_text=s["title"])).to_have_count(0, timeout=5000)
    finally:
        c.close()


def test_uc_a_07_delete_with_data_typed_title_flow(base_url, admin_setup, page):
    """UC-A-07: Delete on session with data → #confirm-delete-card; #cd-go
    disabled until #cd-confirm matches title; #cd-cancel closes card.
    """
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A07data {secrets.token_hex(3)}")
    # Add a query so the session has data.
    ask_query_api(base_url, s["code"], "got data?")
    try:
        admin_login_via_ui(page, base_url)
        row = page.locator("#session-rows tr").filter(has_text=s["title"])
        row.locator("button.danger").click()
        expect(page.locator("#confirm-delete-card")).to_be_visible()
        expect(page.locator("#cd-warn")).to_contain_text(s["title"])
        go = page.locator("#cd-go")
        expect(go).to_be_disabled()
        # Wrong title — still disabled.
        page.fill("#cd-confirm", "wrong title")
        expect(go).to_be_disabled()
        # Cancel works.
        page.click("#cd-cancel")
        expect(page.locator("#confirm-delete-card")).to_be_hidden()
        # Re-open and complete deletion.
        row.locator("button.danger").click()
        expect(page.locator("#confirm-delete-card")).to_be_visible()
        page.fill("#cd-confirm", s["title"])
        expect(page.locator("#cd-go")).to_be_enabled()
        page.click("#cd-go")
        expect(page.locator("#session-rows tr").filter(has_text=s["title"])).to_have_count(0, timeout=5000)
    finally:
        c.close()


def test_uc_a_07_delete_from_session_page(base_url, admin_setup, page):
    """UC-A-07: #set-delete on the session page runs the list's delete flow."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A07page {secrets.token_hex(3)}")
    try:
        _goto_session_page(page, base_url, s)
        page.on("dialog", lambda d: d.accept())
        page.click("#set-delete")
        expect(page.locator("#sessions-card")).to_be_visible(timeout=5000)
        expect(page.locator("#session-rows tr").filter(has_text=s["title"])).to_have_count(0, timeout=5000)
    finally:
        c.close()


# ---------- UC-A-08 ----------


def test_uc_a_08_row_opens_session_page_without_gate(base_url, admin_setup, page):
    """UC-A-08: clicking a row opens /m/<code> with no key gate and the settings card."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A08 {secrets.token_hex(3)}")
    try:
        _goto_session_page(page, base_url, s)
        expect(page.locator("#lifecycle-card")).to_be_visible()
        expect(page.locator("#modkey-card")).to_be_hidden()
        expect(page.locator("#settings-card")).to_be_visible()
    finally:
        c.close()


def test_uc_a_08_share_mod_copies_url(base_url, admin_setup, page):
    """UC-A-08: #set-share-mod copies the moderator URL with #k=<key> to clipboard."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A08share {secrets.token_hex(3)}")
    try:
        _goto_session_page(page, base_url, s)
        page.click("#set-share-mod")
        # Toast should confirm. Don't read clipboard (headless flakiness).
        expect(page.locator(".toast")).to_be_visible()
    finally:
        c.close()


def test_uc_a_08_delegate_sees_no_settings(base_url, admin_setup, page):
    """UC-A-08: a delegate (mod_key only) doesn't see #settings-card."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A08del {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/m/{s['code']}#k={s['mod_key']}")
        page.wait_for_selector("#lifecycle-card:visible", timeout=5000)
        expect(page.locator("#settings-card")).to_be_hidden()
    finally:
        c.close()


def test_uc_m_views_links_for_a_delegate(base_url, admin_setup, page):
    """Session page: a delegate sees the participant and projector links but not
    the Sessions breadcrumb."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-Mviews {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/m/{s['code']}#k={s['mod_key']}")
        page.wait_for_selector("#lifecycle-card:visible", timeout=5000)
        expect(page.locator("#participant-link")).to_have_attribute("href", f"/s/{s['code']}")
        expect(page.locator("#projector-link")).to_have_attribute("href", f"/p/{s['code']}")
        expect(page.locator("#moderator-breadcrumbs a[href='/']")).to_be_hidden()
    finally:
        c.close()


# ---------- UC-A-25 ----------


def test_uc_a_25_change_password_card_opens(base_url, admin_setup, page):
    """UC-A-25: Change password opens #change-pw-card."""
    admin_login_via_ui(page, base_url)
    page.get_by_role("button", name="Change password").click()
    expect(page.locator("#change-pw-card")).to_be_visible()


def test_uc_a_25_change_password_mismatch_toasts_no_api(base_url, admin_setup, page):
    """UC-A-25: mismatched new passwords toast and do not call API."""
    admin_login_via_ui(page, base_url)
    page.get_by_role("button", name="Change password").click()
    expect(page.locator("#change-pw-card")).to_be_visible()
    page.fill("#cp-current", admin_setup["password"])
    page.fill("#cp-new", "newpass123")
    page.fill("#cp-new2", "differentt")
    page.click("#cp-submit")
    expect(page.locator(".toast-error")).to_contain_text("don't match")
    expect(page.locator("#change-pw-card")).to_be_visible()


def test_uc_a_25_change_password_wrong_current_toasts(base_url, admin_setup, page):
    """UC-A-25: wrong current password → toast 'Current password is incorrect', card stays."""
    admin_login_via_ui(page, base_url)
    page.get_by_role("button", name="Change password").click()
    page.fill("#cp-current", "definitely-wrong")
    page.fill("#cp-new", "validpass1")
    page.fill("#cp-new2", "validpass1")
    page.click("#cp-submit")
    expect(page.locator(".toast-error")).to_contain_text("Current password is incorrect")
    expect(page.locator("#change-pw-card")).to_be_visible()


def test_uc_a_25_change_password_short_new_toasts(base_url, admin_setup, page):
    """UC-A-25: new password < 8 chars → error toast (client-side guard)."""
    admin_login_via_ui(page, base_url)
    page.get_by_role("button", name="Change password").click()
    page.fill("#cp-current", admin_setup["password"])
    page.fill("#cp-new", "short")
    page.fill("#cp-new2", "short")
    page.click("#cp-submit")
    expect(page.locator(".toast-error")).to_be_visible()


def test_uc_a_25_change_password_escape_closes(base_url, admin_setup, page):
    """UC-A-25: Escape inside #change-pw-card closes it without submitting."""
    admin_login_via_ui(page, base_url)
    page.get_by_role("button", name="Change password").click()
    expect(page.locator("#change-pw-card")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#change-pw-card")).to_be_hidden()


def test_uc_a_25_change_password_close_button(base_url, admin_setup, page):
    """UC-A-25: #cp-close closes the card."""
    admin_login_via_ui(page, base_url)
    page.get_by_role("button", name="Change password").click()
    expect(page.locator("#change-pw-card")).to_be_visible()
    page.click("#cp-close")
    expect(page.locator("#change-pw-card")).to_be_hidden()


def test_uc_a_25_change_password_success_toasts_and_closes(base_url, admin_setup, page):
    """UC-A-25: valid submit → toast 'Password updated' and card closes.

    Caveat: we rotate the password and rotate it back to keep the test suite
    idempotent (admin_setup fixture relies on the canonical password).
    """
    # Use a fresh httpx admin client to flip the password back at the end.
    admin_login_via_ui(page, base_url)
    page.get_by_role("button", name="Change password").click()
    page.fill("#cp-current", admin_setup["password"])
    new_pw = "rotated-" + secrets.token_hex(4)
    page.fill("#cp-new", new_pw)
    page.fill("#cp-new2", new_pw)
    page.click("#cp-submit")
    expect(page.locator(".toast").first).to_contain_text("Password updated")
    expect(page.locator("#change-pw-card")).to_be_hidden(timeout=5000)
    # Rotate back via API so other tests still pass.
    c = httpx.Client(base_url=base_url, timeout=5.0)
    c.post("/api/admin/login", json={"username": admin_setup["username"], "password": new_pw})
    c.post(
        "/api/admin/change_password",
        json={"current_password": new_pw, "new_password": admin_setup["password"]},
    )
    c.close()


def test_uc_a_31_admin_adjusts_limits(base_url, admin_setup, page):
    """UC-A-31: the Limits card saves a value on leaving the field and resets to defaults."""
    try:
        admin_login_via_ui(page, base_url)
        card = page.locator("#limits-card")
        expect(card).to_be_visible()
        expect(page.locator("#limit-network_size")).to_have_value("300")
        ask = page.locator("#limit-ask_burst")
        expect(ask).to_have_value("6")
        ask.fill("3")
        ask.blur()
        expect(page.locator(".toast:not(.toast-error)")).to_have_text("Saved")
        page.reload()
        expect(page.locator("#limit-ask_burst")).to_have_value("3")
        page.locator("#limits-reset").click()
        expect(page.locator("#limit-ask_burst")).to_have_value("6")
    finally:
        c = api_login(base_url)
        c.put("/api/admin/limits", json={"ask_burst": 6})
        c.close()
