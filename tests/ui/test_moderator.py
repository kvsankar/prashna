"""UI tests for the moderator surface (/m/<code>).

Covers UC-M-01..11.
"""
from __future__ import annotations

import secrets
import time

import httpx
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

# ---------- UC-M-01 ----------


def test_uc_m_01_admin_owner_no_key_gate(base_url, admin_setup, page):
    """UC-M-01: opening /m/<code> as admin owner (cookie) does NOT render #modkey-card."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M01 {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)  # sets admin cookie
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#lifecycle-card:visible", timeout=5000)
        expect(page.locator("#modkey-card")).to_be_hidden()
    finally:
        c.close()


def test_uc_m_01_delegate_with_hash_stores_key(base_url, admin_setup, page):
    """UC-M-01: opening /m/<code>#k=<key> persists key to localStorage and strips fragment."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M01d {secrets.token_hex(3)}")
    try:
        # No admin cookie on this page context.
        page.goto(f"{base_url}/m/{s['code']}#k={s['mod_key']}")
        page.wait_for_selector("#lifecycle-card:visible", timeout=5000)
        # Fragment stripped.
        url = page.evaluate("location.href")
        assert "#k=" not in url
        # Key in localStorage.
        stored = page.evaluate(f"localStorage.getItem('mod_key:{s['code']}')")
        assert stored == s["mod_key"]
    finally:
        c.close()


def test_uc_m_01_no_auth_renders_key_gate(base_url, admin_setup, page):
    """UC-M-01: opening /m/<code> without cookie or stored key renders #modkey-card."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M01g {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/m/{s['code']}")
        expect(page.locator("#modkey-card")).to_be_visible(timeout=5000)
        # Submitting the right key proceeds.
        page.fill("#modkey-input", s["mod_key"])
        page.click("#modkey-submit")
        page.wait_for_selector("#lifecycle-card:visible", timeout=5000)
    finally:
        c.close()


def test_uc_m_01_wrong_stored_key_toasts(base_url, admin_setup, page):
    """UC-M-01: wrong stored key → boot 403, gate re-prompts with error toast."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M01w {secrets.token_hex(3)}")
    try:
        # Pre-populate localStorage with a bad key for the session code.
        page.goto(f"{base_url}/m/{s['code']}#k=wrongkeyxxxxxxxx")
        # Boot 403 → key gate shown + toast.
        expect(page.locator("#modkey-card")).to_be_visible(timeout=5000)
        expect(page.locator(".toast-error")).to_be_visible()
    finally:
        c.close()


# ---------- UC-M-02 ----------


def test_uc_m_02_start_button_flips_status(base_url, admin_setup, page):
    """UC-M-02: planning → Start session → #session-status flips to .badge-live."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M02 {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#lifecycle-card:visible")
        page.locator("#lifecycle-actions button", has_text="Start session").click()
        expect(page.locator("#session-status")).to_have_class("badge badge-live", timeout=5000)
    finally:
        c.close()


def test_uc_m_02_end_button_flips_status(base_url, admin_setup, page):
    """UC-M-02: live → End session (confirm) → #session-status flips to .badge-ended."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M02e {secrets.token_hex(3)}")
    api_start_session(c, s["code"])
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#lifecycle-card:visible")
        page.on("dialog", lambda d: d.accept())
        page.locator("#lifecycle-actions button", has_text="End session").click()
        expect(page.locator("#session-status")).to_have_class("badge badge-ended", timeout=5000)
    finally:
        c.close()


# ---------- UC-M-03 ----------


def test_uc_m_03_quiz_select_lists_ready_only(base_url, admin_setup, page):
    """UC-M-03: #quiz-select lists only ready quizzes (drafts filtered)."""
    c = api_login(base_url)
    ready = api_make_quiz(c, f"UI-M03ready {secrets.token_hex(3)}", publish=True)
    draft = api_make_quiz(c, f"UI-M03draft {secrets.token_hex(3)}")
    s = api_make_session(c, f"UI-M03s {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-select")
        opts = page.locator("#quiz-select option").all_text_contents()
        assert any(ready["title"] in o for o in opts)
        assert not any(draft["title"] in o for o in opts)
    finally:
        c.close()


def test_uc_m_03_add_quiz_queues_run(base_url, admin_setup, page):
    """UC-M-03: selecting + Add to session appends a queued row to #quiz-runs."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-M03q {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-M03qs {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-select")
        page.locator("#quiz-select").select_option(value=str(quiz["id"]))
        page.click("#add-quiz-btn")
        expect(page.locator("#quiz-runs .badge-queued")).to_be_visible(timeout=5000)
        expect(page.locator("#quiz-runs")).to_contain_text(quiz["title"])
    finally:
        c.close()


# ---------- UC-M-04 ----------


def test_uc_m_04_start_queued_run_flips_to_live(base_url, admin_setup, page):
    """UC-M-04: clicking Start on a queued row flips the row to .badge-live and reveals Reveal/Next."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-M04 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-M04s {secrets.token_hex(3)}")
    api_queue_quiz_run(c, s["code"], quiz["id"])
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-runs .badge-queued")
        page.locator("#quiz-runs button", has_text="Start").first.click()
        expect(page.locator("#quiz-runs .badge-live")).to_be_visible(timeout=5000)
        expect(page.locator("#quiz-runs button", has_text="Reveal")).to_be_visible()
    finally:
        c.close()


def test_uc_m_04_second_live_run_toasts_409(base_url, admin_setup, page):
    """UC-M-04: starting a second queued run while one is live toasts 409."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-M04m {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-M04ms {secrets.token_hex(3)}")
    run1 = api_queue_quiz_run(c, s["code"], quiz["id"])
    api_queue_quiz_run(c, s["code"], quiz["id"])  # second queued run (for the 409)
    # Start run1 via API so we're cleanly in the "one live" state.
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run1['id']}/start").raise_for_status()
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-runs .badge-queued")
        # Click Start on the queued row (run2).
        queued_row = page.locator("#quiz-runs > section").filter(has=page.locator(".badge-queued"))
        queued_row.locator("button", has_text="Start").click()
        expect(page.locator(".toast-error")).to_contain_text("Another quiz is already live", timeout=5000)
    finally:
        c.close()


# ---------- UC-M-05 ----------


def test_uc_m_05_reveal_next_close_walk(base_url, admin_setup, page):
    """UC-M-05: walk through the single-button Reveal/Next/Close progression and Prev."""
    c = api_login(base_url)
    # Quiz with 2 questions so we can test next and close paths.
    quiz = api_make_quiz(
        c,
        f"UI-M05 {secrets.token_hex(3)}",
        publish=True,
        questions=[
            {"text": "q1", "qtype": "single", "answers": [{"text": "a", "is_correct": True}, {"text": "b"}]},
            {"text": "q2", "qtype": "single", "answers": [{"text": "c", "is_correct": True}, {"text": "d"}]},
        ],
    )
    s = api_make_session(c, f"UI-M05s {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-runs .badge-live")
        # Phase 1: answering → Reveal.
        reveal = page.locator("#quiz-runs button", has_text="Reveal results")
        expect(reveal).to_be_visible()
        reveal.click()
        # Phase 2: results, not last question → Next question.
        next_btn = page.locator("#quiz-runs button", has_text="Next question")
        expect(next_btn).to_be_visible(timeout=5000)
        next_btn.click()
        # Back to answering; Reveal again.
        page.locator("#quiz-runs button", has_text="Reveal results").click()
        # Last question → Finish quiz.
        finish_btn = page.locator("#quiz-runs button", has_text="Finish quiz")
        expect(finish_btn).to_be_visible(timeout=5000)
        # Don't click Finish here — UC-M-06 tests closing. Verify Prev exists.
        expect(page.locator("#quiz-runs button", has_text="Prev")).to_be_visible()
    finally:
        c.close()


def test_uc_m_05_live_counts_toggle(base_url, admin_setup, page):
    """UC-M-05: live counts checkbox toggles show_live_counts (default off)."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-M05lc {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-M05lcs {secrets.token_hex(3)}")
    api_queue_quiz_run(c, s["code"], quiz["id"])
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-runs .badge-queued")
        # The audience vote-count toggle is a verb button in the ⋯ menu.
        row = page.locator("#quiz-runs > section").filter(has=page.locator(".badge-queued"))
        row.locator("details.menu > summary").click()
        row.locator("button", has_text="Show vote counts to audience").click()
        # Verify via API.
        deadline = time.monotonic() + 5
        while True:
            runs = c.get(f"/api/sessions/{s['code']}/quiz_runs").json()
            if runs[0]["show_live_counts"] is True:
                break
            if time.monotonic() >= deadline:
                assert runs[0]["show_live_counts"] is True
            time.sleep(0.1)
    finally:
        c.close()


def test_uc_m_05_run_menu_closes_on_outside_click(base_url, admin_setup, page):
    """UC-M-05: the ⋯ run-action menu closes when clicking outside it."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-M05menu {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-M05menus {secrets.token_hex(3)}")
    api_queue_quiz_run(c, s["code"], quiz["id"])
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-runs .badge-queued")
        menu = page.locator("#quiz-runs details.menu").first
        panel = menu.locator(".menu-panel")
        menu.locator("summary").click()
        expect(panel).to_be_visible()
        # Clicking outside the menu (e.g. the page heading) closes it.
        page.locator("h1#title").click()
        expect(panel).to_be_hidden(timeout=5000)
    finally:
        c.close()


def test_uc_m_05_reveal_closes_voting_and_reopen(base_url, admin_setup, page):
    """UC-M-05: 'Reveal results →' closes voting (shows a 'voting closed'
    marker); the ⋯ menu's 'Reopen voting' reopens it."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-M05r {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-M05rs {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-runs .badge-live")
        page.locator("#quiz-runs button", has_text="Reveal results").click()
        expect(page.locator("#quiz-runs")).to_contain_text("voting closed", timeout=5000)
        # Reopen via the ⋯ overflow menu.
        page.locator("#quiz-runs details.menu > summary").click()
        page.locator("#quiz-runs button", has_text="Reopen voting").click()
        expect(page.locator("#quiz-runs")).not_to_contain_text("voting closed", timeout=5000)
        expect(page.locator("#quiz-runs button", has_text="Reveal results")).to_be_visible()
    finally:
        c.close()


# ---------- UC-M-06 ----------


def test_uc_m_06_close_run_flips_badge_and_hides_menu(base_url, admin_setup, page):
    """UC-M-06: closing a live run (via ⋯ → Finish quiz) flips badge to
    .badge-closed and removes the run's ⋯ overflow menu."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-M06 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-M06s {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-runs .badge-live")
        live_row = page.locator("#quiz-runs > section").filter(has=page.locator(".badge-live"))
        live_row.locator("details.menu > summary").click()
        live_row.locator("button", has_text="Finish quiz").click()
        expect(page.locator("#quiz-runs .badge-closed")).to_be_visible(timeout=5000)
        # No ⋯ menu (and no Remove control) rendered for closed rows.
        closed_row = page.locator("#quiz-runs > section").filter(has=page.locator(".badge-closed"))
        expect(closed_row.locator("details.menu")).to_have_count(0)
        expect(closed_row.locator("button[aria-label*='Remove']")).to_have_count(0)
    finally:
        c.close()


# ---------- UC-M-07 ----------


def test_uc_m_07_delete_queued_run_removes_row(base_url, admin_setup, page):
    """UC-M-07: ✕ on a queued/live row (confirm) removes the row."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-M07 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-M07s {secrets.token_hex(3)}")
    api_queue_quiz_run(c, s["code"], quiz["id"])
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-runs .badge-queued")
        page.on("dialog", lambda d: d.accept())
        # Delete now lives in the run's ⋯ overflow menu.
        queued_row = page.locator("#quiz-runs > section").filter(has=page.locator(".badge-queued"))
        queued_row.locator("details.menu > summary").click()
        queued_row.locator("button", has_text="Delete run").click()
        expect(page.locator("#quiz-runs .badge-queued")).to_have_count(0, timeout=5000)
    finally:
        c.close()


def test_uc_m_07_no_menu_on_closed_rows(base_url, admin_setup, page):
    """UC-M-07: no ⋯ overflow menu (and thus no Delete) on .badge-closed rows."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-M07c {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-M07cs {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close").raise_for_status()
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#quiz-runs .badge-closed")
        closed_row = page.locator("#quiz-runs > section").filter(has=page.locator(".badge-closed"))
        expect(closed_row.locator("details.menu")).to_have_count(0)
    finally:
        c.close()


# ---------- UC-M-08 ----------


def test_uc_m_08_respond_moves_query_to_answered(base_url, admin_setup, page):
    """UC-M-08: Mark responded moves the query into the answered (.answered) section;
    Reopen moves it back.
    """
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M08 {secrets.token_hex(3)}")
    ask_query_api(base_url, s["code"], "moderator-test-query")
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#queries .question")
        q = page.locator("#queries .question").filter(has_text="moderator-test-query")
        expect(q).not_to_have_class("question answered")
        q.locator("button", has_text="Mark responded").click()
        # Re-rendered as .answered.
        answered = page.locator("#queries .question.answered").filter(has_text="moderator-test-query")
        expect(answered).to_be_visible(timeout=5000)
        # Reopen.
        answered.locator("button", has_text="Reopen").click()
        page.wait_for_function(
            "document.querySelectorAll('#queries .question.answered').length === 0",
            timeout=5000,
        )
    finally:
        c.close()


# ---------- UC-M-09 ----------


def test_uc_m_09_remove_query_marks_hidden_with_restore(base_url, admin_setup, page):
    """UC-M-09: clicking Remove visually marks the query removed (.hidden-q) with Restore."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M09 {secrets.token_hex(3)}")
    ask_query_api(base_url, s["code"], "spam-text-to-remove")
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#queries .question")
        q = page.locator("#queries .question").filter(has_text="spam-text-to-remove")
        q.locator("button", has_text="Remove").click()
        # Now .hidden-q with a Restore button.
        hidden = page.locator("#queries .question.hidden-q").filter(has_text="spam-text-to-remove")
        expect(hidden).to_be_visible(timeout=5000)
        expect(hidden.locator("button", has_text="Restore")).to_be_visible()
    finally:
        c.close()


# ---------- UC-M-12: feedback panel ----------


def test_uc_m_12_feedback_panel_shows_summary(base_url, admin_setup, page):
    """UC-M-12: the moderator Feedback panel shows the average + comments."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M12 {secrets.token_hex(3)}")
    # A participant submits feedback (own client → own voter_token).
    with httpx.Client(base_url=base_url) as pc:
        pc.post(f"/api/sessions/{s['code']}/feedback",
                json={"rating": 5, "went_well": "Great pace"}).raise_for_status()
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#feedback-card:visible")
        expect(page.locator("#feedback-summary")).to_contain_text("5", timeout=5000)
        expect(page.locator("#feedback-list")).to_contain_text("Great pace")
    finally:
        c.close()


# ---------- UC-M-13: attendee profiles ----------


def test_uc_m_13_profiles_panel_shows_attendee_details(base_url, admin_setup, page):
    """UC-M-13: moderator Attendee profiles panel shows submitted profile details."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M13 {secrets.token_hex(3)}")
    with httpx.Client(base_url=base_url) as pc:
        pc.patch(f"/api/sessions/{s['code']}/me", json={
            "name": "Dana",
            "email": "dana@example.com",
            "contact_number": "+1 415 555 0101",
            "organization": "ExampleCo",
            "role": "Engineering Manager",
            "linkedin_url": "https://www.linkedin.com/in/dana-example",
            "current_work": "Building a training platform",
            "learning_goal": "Practice live facilitation",
        }).raise_for_status()
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#profiles-card:visible")
        expect(page.locator("#profiles-summary")).to_contain_text("1 profile", timeout=5000)
        expect(page.locator("#profiles-list")).to_contain_text("Dana")
        expect(page.locator("#profiles-list")).to_contain_text("dana@example.com")
        expect(page.locator("#profiles-list")).to_contain_text("+1 415 555 0101")
        expect(page.locator("#profiles-list")).to_contain_text("ExampleCo")
        expect(page.locator("#profiles-list")).to_contain_text("Engineering Manager")
        expect(page.locator("#profiles-list")).to_contain_text("linkedin.com/in/dana-example")
        expect(page.locator("#profiles-list")).to_contain_text("Building a training platform")
        expect(page.locator("#profiles-list")).to_contain_text("Practice live facilitation")
    finally:
        c.close()


# ---------- UC-M-10 ----------


def test_uc_m_10_live_count_renders(base_url, admin_setup, page):
    """UC-M-10: #live-count shows 'N online' text."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M10 {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        expect(page.locator("#live-count")).to_contain_text("online", timeout=5000)
    finally:
        c.close()


# ---------- UC-M-11 ----------


def test_uc_m_11_base_url_updates_invite_url(base_url, admin_setup, page):
    """UC-M-11: typing into #base-url and blurring updates #invite-url + re-renders QR."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M11 {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#invite-card:visible")
        page.fill("#base-url", "https://override.example")
        page.locator("#base-url").blur()
        expect(page.locator("#invite-url")).to_contain_text("override.example", timeout=5000)
        expect(page.locator("#invite-url")).to_contain_text(f"/s/{s['code']}")
        # Clear.
        page.click("#base-url-clear")
        expect(page.locator("#invite-url")).to_contain_text("127.0.0.1", timeout=5000)
    finally:
        c.close()


def test_uc_m_11_invite_copy_button_present(base_url, admin_setup, page):
    """UC-M-11: clicking #invite-copy copies the URL (toast confirms)."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M11c {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        page.wait_for_selector("#invite-copy")
        page.click("#invite-copy")
        # Either success toast OR error toast (clipboard may need HTTPS).
        expect(page.locator(".toast")).to_be_visible(timeout=5000)
    finally:
        c.close()


def test_uc_m_11_invite_qr_renders(base_url, admin_setup, page):
    """UC-M-11: #invite-qr renders an SVG QR. (Cannot test 'scannable' headlessly.)"""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-M11q {secrets.token_hex(3)}")
    try:
        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/m/{s['code']}")
        expect(page.locator("#invite-qr svg")).to_be_visible(timeout=10000)
    finally:
        c.close()
