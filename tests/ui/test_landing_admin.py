"""UI tests for the authed admin landing page.

Covers UC-A-03..08 (session create, list, detail card, rename, base URL,
delete with typed-title), and UC-A-25 (change password).
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


# ---------- UC-A-05 ----------


def test_uc_a_05_edit_title_updates_row(base_url, admin_setup, page):
    """UC-A-05: editing #sd-session-title and blurring updates row title."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A05 {secrets.token_hex(3)}")
    new_title = s["title"] + " EDITED"
    try:
        admin_login_via_ui(page, base_url)
        row = page.locator("#session-rows tr").filter(has_text=s["title"])
        row.click()
        expect(page.locator("#session-detail-card")).to_be_visible()
        expect(page.locator("#sd-session-title")).to_have_value(s["title"])
        page.fill("#sd-session-title", new_title)
        page.locator("#sd-session-title").blur()
        # The row updates after refresh.
        expect(page.locator("#session-rows tr").filter(has_text=new_title)).to_be_visible(timeout=5000)
    finally:
        c.close()


def test_uc_a_05_edit_title_empty_reverts(base_url, admin_setup, page):
    """UC-A-05: blank title — frontend skips PATCH (no API call); the no-op
    path leaves the original title in place. Empty submission does not toast
    an error in this implementation; verify the title doesn't change.
    """
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A05r {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        row = page.locator("#session-rows tr").filter(has_text=s["title"])
        row.click()
        expect(page.locator("#sd-session-title")).to_have_value(s["title"])
        page.fill("#sd-session-title", "   ")
        page.locator("#sd-session-title").blur()
        # No update should be visible — original title still in rows.
        expect(page.locator("#session-rows tr").filter(has_text=s["title"])).to_be_visible()
    finally:
        c.close()


# ---------- UC-A-06 ----------


def test_uc_a_06_base_url_save_and_clear(base_url, admin_setup, page):
    """UC-A-06: typing into #sd-base-url and blurring updates #sd-url;
    #sd-clear falls back to location.origin.
    """
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A06 {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.locator("#session-rows tr").filter(has_text=s["title"]).click()
        expect(page.locator("#session-detail-card")).to_be_visible()
        page.fill("#sd-base-url", "https://example.org")
        page.locator("#sd-base-url").blur()
        expect(page.locator("#sd-url")).to_contain_text("example.org", timeout=5000)
        page.click("#sd-clear")
        # Fallback is location.origin = base_url (127.0.0.1 host).
        expect(page.locator("#sd-url")).to_contain_text("127.0.0.1", timeout=5000)
    finally:
        c.close()


def test_uc_a_06_base_url_invalid_toasts(base_url, admin_setup, page):
    """UC-A-06: invalid (non-http) URL shows error toast."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A06bad {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.locator("#session-rows tr").filter(has_text=s["title"]).click()
        page.fill("#sd-base-url", "ftp://example.org")
        page.locator("#sd-base-url").blur()
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


# ---------- UC-A-08 ----------


def test_uc_a_08_start_button_flips_status(base_url, admin_setup, page):
    """UC-A-08: planning session detail shows Start; clicking flips badge to live."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A08 {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.locator("#session-rows tr").filter(has_text=s["title"]).click()
        expect(page.locator("#sd-status")).to_have_class("badge badge-planning")
        page.locator("#sd-lifecycle-actions button", has_text="Start session").click()
        expect(page.locator("#sd-status")).to_have_class("badge badge-live", timeout=5000)
    finally:
        c.close()


def test_uc_a_08_end_button_flips_status(base_url, admin_setup, page):
    """UC-A-08: live session detail shows End; clicking (confirm) flips badge to ended."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A08end {secrets.token_hex(3)}")
    api_start_session(c, s["code"])
    try:
        admin_login_via_ui(page, base_url)
        page.locator("#session-rows tr").filter(has_text=s["title"]).click()
        page.on("dialog", lambda d: d.accept())
        page.locator("#sd-lifecycle-actions button", has_text="End session").click()
        expect(page.locator("#sd-status")).to_have_class("badge badge-ended", timeout=5000)
    finally:
        c.close()


def test_uc_a_08_open_mod_link_no_gate(base_url, admin_setup, page):
    """UC-A-08: #sd-open-mod link → /m/<code> and loads moderator surface with no key gate."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A08mod {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.locator("#session-rows tr").filter(has_text=s["title"]).click()
        link = page.locator("#sd-open-mod")
        href = link.get_attribute("href")
        assert href == f"/m/{s['code']}"
        page.goto(base_url + href)
        # Admin cookie auths — no key gate.
        page.wait_for_selector("#lifecycle-card:visible", timeout=5000)
        expect(page.locator("#modkey-card")).to_be_hidden()
    finally:
        c.close()


def test_uc_a_08_share_mod_copies_url(base_url, admin_setup, page):
    """UC-A-08: #sd-share-mod copies the moderator URL with #k=<key> to clipboard."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-A08share {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.locator("#session-rows tr").filter(has_text=s["title"]).click()
        page.click("#sd-share-mod")
        # Toast should confirm. Don't read clipboard (headless flakiness).
        expect(page.locator(".toast")).to_be_visible()
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
