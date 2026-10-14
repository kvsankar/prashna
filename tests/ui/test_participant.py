"""UI tests for the participant surface (/s/<code>).

Covers UC-P-02..12.
"""
from __future__ import annotations

import re
import secrets

import httpx
from playwright.sync_api import expect

from ._helpers import (
    accept_confirm,
    admin_login_via_ui,
    api_end_session,
    api_login,
    api_make_quiz,
    api_make_session,
    api_queue_quiz_run,
    api_start_session,
    ask_query_api,
    confirm_dialog,
    dismiss_confirm,
    watch_native_dialogs,
)

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)


def assert_no_horizontal_overflow(page):
    overflow = page.evaluate(
        """() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        })"""
    )
    assert overflow["scrollWidth"] <= overflow["clientWidth"] + 1, overflow


def test_participant_breadcrumbs_show_context_and_section_links(
    base_url, admin_setup, page
):
    """Participant chrome identifies the role and supports long-page jumps."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P-nav {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        crumbs = page.locator("#participant-breadcrumbs li")
        expect(crumbs).to_have_text(["Prashna", s["title"], "Participant view"], timeout=5000)
        expect(crumbs.first.locator("a")).to_have_attribute("href", "/")
        expect(page).to_have_title(f"{s['title']} · Participant view — Prashna")
        page.locator(".section-links a", has_text="Questions").click()
        assert page.evaluate("location.hash") == "#questions-card"
    finally:
        c.close()

# ---------- UC-P-13: session feedback ----------


def test_uc_p_13_submit_and_resubmit_prefills_prior_values(
    base_url,
    admin_setup,
    page,
):
    """UC-P-13: feedback has an explicit Submit action; after submitting,
    reload prefills the prior values and changes the action to Resubmit."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P13 {secrets.token_hex(3)}")
    c.post(
        f"/api/sessions/{s['code']}/feedback_enabled",
        json={"enabled": True},
    ).raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#feedback-card:visible")
        submit = page.locator("#fb-submit")
        expect(submit).to_have_text("Submit feedback")
        expect(submit).to_be_enabled()
        submit.click()
        expect(page.locator(".toast")).to_contain_text("Choose a rating first")
        # The expanded course-feedback section is hidden until a star is picked.
        expect(page.locator("#fb-expand")).to_be_hidden()
        # Picking a rating reveals the optional comments and enables Submit.
        page.locator("#fb-stars button.star").nth(3).click()
        expect(page.locator("#fb-expand")).to_be_visible()
        expect(page.locator("#fb-status")).to_have_text("Ready to submit")
        page.fill("#fb-went-well", "Loved the demos")
        # Nothing is persisted until the explicit action is used.
        with page.expect_response(
            lambda r: r.url.endswith("/feedback") and r.request.method == "POST"
        ):
            submit.click()
        expect(page.locator("#fb-status")).to_contain_text("Submitted")
        expect(submit).to_have_text("Resubmit feedback")
        # A submitted rating collapses to a one-line summary.
        expect(page.locator("#feedback-card")).not_to_have_attribute("open", "")
        expect(page.locator("#feedback-card > summary h2")).to_have_text("Feedback")
        expect(page.locator("#fb-summary")).to_have_text("Rated ★★★★☆")
        # Reload → still collapsed; opening shows the prior feedback.
        page.reload()
        expect(page.locator("#fb-summary")).to_have_text("Rated ★★★★☆", timeout=5000)
        expect(page.locator("#feedback-card")).not_to_have_attribute("open", "")
        page.locator("#feedback-card > summary").click()
        page.wait_for_selector("#fb-expand:visible")
        expect(page.locator("#fb-went-well")).to_have_value("Loved the demos")
        expect(page.locator("#fb-stars button.star.filled")).to_have_count(4)
        expect(page.locator("#fb-submit")).to_have_text("Resubmit feedback")
        page.fill("#fb-to-improve", "More time for questions")
        expect(page.locator("#fb-status")).to_have_text("Unsaved changes")
        with page.expect_response(
            lambda r: r.url.endswith("/feedback") and r.request.method == "POST"
        ):
            page.click("#fb-submit")
        expect(page.locator(".toast")).to_contain_text("resubmitted")
    finally:
        c.close()


def _submit_five_stars(page, base_url, code):
    page.goto(f"{base_url}/s/{code}")
    page.wait_for_selector("#feedback-card:visible")
    page.locator("#fb-stars button.star").nth(4).click()  # 5 stars
    with page.expect_response(
        lambda r: r.url.endswith("/feedback") and r.request.method == "POST"
    ):
        page.click("#fb-submit")
    expect(page.locator("#fb-stars button.star.filled")).to_have_count(5)
    # The card collapsed after submitting; reopen it to clear.
    page.locator("#feedback-card > summary").click()


def test_uc_p_13_clear_asks_in_page(base_url, admin_setup, page):
    """UC-P-13: 'Clear feedback' asks in the in-page confirmation dialog —
    Cancel keeps the rating, 'Clear feedback' clears it and hides the
    comment fields. No native dialog and no inline Yes / No."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P13c {secrets.token_hex(3)}")
    c.post(
        f"/api/sessions/{s['code']}/feedback_enabled",
        json={"enabled": True},
    ).raise_for_status()
    try:
        native = watch_native_dialogs(page)
        _submit_five_stars(page, base_url, s["code"])
        expect(page.locator("#fb-clear")).to_have_text("Clear feedback")
        expect(page.locator("#fb-clear-confirm")).to_have_count(0)
        page.click("#fb-clear")
        dialog = confirm_dialog(page, "Clear your feedback?")
        expect(dialog.locator(".confirm-detail")).to_have_text("Your stars and comments are removed.")
        expect(dialog.locator(".confirm-ok")).to_have_text("Clear feedback")
        expect(dialog.locator(".confirm-ok")).to_have_class(re.compile(r"\bdanger\b"))
        expect(dialog.locator(".confirm-cancel")).to_be_focused()
        dismiss_confirm(page)
        expect(page.locator("#fb-stars button.star.filled")).to_have_count(5)
        expect(page.locator("#fb-clear")).to_be_focused()
        # Ask again and confirm → DELETE clears it.
        page.click("#fb-clear")
        with page.expect_response(
            lambda r: r.url.endswith("/feedback") and r.request.method == "DELETE"
        ):
            accept_confirm(page, "Clear your feedback?", "Clear feedback")
        expect(page.locator("#fb-stars button.star.filled")).to_have_count(0)
        expect(page.locator("#fb-expand")).to_be_hidden()
        expect(page.locator(".toast", has_text="Feedback cleared")).to_be_visible()
        assert native == []
    finally:
        c.close()


def test_uc_p_13_clear_dialog_fits_a_phone(base_url, admin_setup, page):
    """UC-P-13 / UC-X-12: at 390 px the Clear feedback dialog keeps the
    page gutter and the page doesn't scroll sideways."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P13cp {secrets.token_hex(3)}")
    c.post(f"/api/sessions/{s['code']}/feedback_enabled", json={"enabled": True}).raise_for_status()
    try:
        page.set_viewport_size({"width": 390, "height": 844})
        _submit_five_stars(page, base_url, s["code"])
        page.click("#fb-clear")
        dialog = confirm_dialog(page, "Clear your feedback?")
        box = dialog.bounding_box()
        assert box["x"] >= 15 and box["x"] + box["width"] <= 390 - 15, box
        for button in (dialog.locator(".confirm-cancel"), dialog.locator(".confirm-ok")):
            b = button.bounding_box()
            assert b["x"] >= box["x"] and b["x"] + b["width"] <= box["x"] + box["width"], (b, box)
        assert_no_horizontal_overflow(page)
    finally:
        c.close()


# ---------- UC-P-02 ----------


def test_uc_p_13_rating_card_follows_profile_and_opens(base_url, admin_setup, page):
    """UC-P-13: with no prior feedback the open Feedback card follows the
    profile card, and its title and section link say "Feedback"."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P13o {secrets.token_hex(3)}")
    c.post(f"/api/sessions/{s['code']}/feedback_enabled", json={"enabled": True}).raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#feedback-card:visible")
        assert page.evaluate(
            "document.querySelector('#profile-card').nextElementSibling.id") == "feedback-card"
        expect(page.locator("#feedback-card")).to_have_attribute("open", "")
        expect(page.locator("#fb-summary")).to_be_hidden()
        expect(page.locator("#feedback-card > summary h2")).to_have_text("Feedback")
        expect(page.locator(".section-links a[href='#feedback-card']")).to_have_text("Feedback")
    finally:
        c.close()


def test_uc_p_13_live_quiz_card_moves_to_top(base_url, admin_setup, page):
    """UC-P-13: a live quiz moves to the top; when it closes, Profile is first again."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P13q {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-P13qs {secrets.token_hex(3)}")
    c.post(f"/api/sessions/{s['code']}/feedback_enabled", json={"enabled": True}).raise_for_status()
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    first_card = "[...document.querySelector('main').children].find(e => !e.hidden).id"
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-card:visible")
        assert page.evaluate(first_card) == "quiz-card"
        c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close").raise_for_status()
        expect(page.locator("#quiz-card")).to_be_hidden(timeout=5000)
        assert page.evaluate(first_card) == "profile-card"
    finally:
        c.close()


def test_uc_p_02_voter_token_cookie_set_on_load(base_url, admin_setup, page):
    """UC-P-02: loading /s/<code> sets a voter_token cookie readable in JS."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P02 {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#title:not(:has-text('Loading'))")
        # Trigger an interaction to ensure the cookie is set.
        page.wait_for_timeout(200)
        cookies = page.context.cookies()
        names = {c["name"] for c in cookies}
        assert "voter_token" in names
    finally:
        c.close()


def test_mobile_participants_can_complete_core_flow(
    base_url, admin_setup, browser
):
    """Mobile participants can identify, ask, vote, answer, and rate."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P-mobile-q {secrets.token_hex(3)}",
                         publish=True)
    s = api_make_session(c, f"UI-P-mobile {secrets.token_hex(3)}")
    c.post(
        f"/api/sessions/{s['code']}/feedback_enabled",
        json={"enabled": True},
    ).raise_for_status()
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(
        f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start"
    ).raise_for_status()

    ctx1 = browser.new_context(viewport={"width": 360, "height": 820})
    ctx2 = browser.new_context(viewport={"width": 360, "height": 820})
    p1 = ctx1.new_page()
    p2 = ctx2.new_page()
    try:
        p1.goto(f"{base_url}/s/{s['code']}")
        p2.goto(f"{base_url}/s/{s['code']}")
        p1.wait_for_selector("#ask-card:visible")
        p2.wait_for_selector("#ask-card:visible")

        p1.locator("#profile-card > summary").click()
        p1.fill("#my-name", "Mobile Dana")
        p1.click("#profile-submit")
        expect(p1.locator(".toast")).to_contain_text("Mobile Dana")
        assert_no_horizontal_overflow(p1)

        p1.fill("#query-text", "mobile responsive question")
        p1.click("#ask-btn")
        expect(p2.locator("#queries")).to_contain_text(
            "mobile responsive question",
            timeout=5000,
        )
        row = p2.locator("#queries .question").filter(
            has_text="mobile responsive question"
        )
        vote = row.locator("button.vote-btn")
        expect(vote).to_have_attribute("aria-pressed", "false")
        vote.click()
        expect(vote).to_have_attribute("aria-pressed", "true")

        expect(p2.locator("#quiz-card")).to_be_visible(timeout=5000)
        option = p2.locator("#quiz-body button.option").first
        option.click()
        expect(option).to_have_attribute("aria-pressed", "true")
        p2.locator("#quiz-body button.primary").click()
        expect(p2.locator("#quiz-body")).to_contain_text(
            "recorded",
            timeout=5000,
        )

        p2.locator("#fb-stars button.star").nth(3).click()
        p2.locator("#fb-submit").click()
        expect(p2.locator("#fb-status")).to_contain_text("Submitted")
        assert_no_horizontal_overflow(p2)
    finally:
        p1.close()
        p2.close()
        ctx1.close()
        ctx2.close()
        c.close()


def test_mobile_participant_controls_are_keyboard_accessible(
    base_url,
    admin_setup,
    page,
):
    """Mobile controls expose keyboard paths and accessible state."""
    page.set_viewport_size({"width": 360, "height": 820})
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P-mobile-k {secrets.token_hex(3)}")
    c.post(
        f"/api/sessions/{s['code']}/feedback_enabled",
        json={"enabled": True},
    ).raise_for_status()
    api_start_session(c, s["code"])
    ask_query_api(base_url, s["code"], "keyboard-votable")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#ask-card:visible")
        page.focus("#query-text")
        page.fill("#query-text", "keyboard mobile question")
        page.locator("#query-text").press("Control+Enter")
        expect(page.locator("#queries")).to_contain_text(
            "keyboard mobile question",
            timeout=5000,
        )

        vote = page.locator("#queries .question").filter(
            has_text="keyboard-votable"
        ).locator("button.vote-btn")
        expect(vote).to_have_attribute("aria-label", re.compile("Upvote"))
        expect(vote).to_have_attribute("aria-pressed", "false")
        vote.focus()
        page.keyboard.press("Enter")
        expect(vote).to_have_attribute("aria-pressed", "true")

        expect(page.locator("#fb-stars")).to_have_attribute(
            "role",
            "radiogroup",
        )
        expect(page.locator("#fb-stars button.star").first).to_have_attribute(
            "aria-label",
            "1 star",
        )
        assert_no_horizontal_overflow(page)
    finally:
        c.close()


def test_uc_p_02_reload_keeps_token_and_mine_flag(base_url, admin_setup, page):
    """UC-P-02: reloading /s/<CODE> keeps the same voter_token; subsequent
    queries from this participant should be flagged mine: true.
    """
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P02m {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#ask-card:visible")
        # Ask a query.
        page.fill("#query-text", "mine-flag-test")
        page.click("#ask-btn")
        expect(page.locator("#queries")).to_contain_text("mine-flag-test", timeout=5000)
        token_before = next(
            (ck["value"] for ck in page.context.cookies() if ck["name"] == "voter_token"), None
        )
        page.reload()
        page.wait_for_selector("#ask-card:visible")
        token_after = next(
            (ck["value"] for ck in page.context.cookies() if ck["name"] == "voter_token"), None
        )
        assert token_after
        assert token_after == token_before
        # The voted/mine flag is verifiable via API.
        r = httpx.get(
            f"{base_url}/api/sessions/{s['code']}/queries",
            cookies={"voter_token": token_after},
            timeout=5.0,
        )
        queries = r.json()
        assert any(q["text"] == "mine-flag-test" and q["mine"] for q in queries)
    finally:
        c.close()


# ---------- UC-P-03 ----------


def test_uc_p_03_set_display_name_persists(base_url, admin_setup, page):
    """UC-P-03: submitting #my-name PATCHes and persists."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P03 {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#profile-card:visible")
        page.locator("#profile-card > summary").click()
        page.fill("#my-name", "Alice")
        page.click("#profile-submit")
        # Toast confirms.
        expect(page.locator(".toast")).to_contain_text("Alice", timeout=5000)
        # Questions stay anonymous: the profile name is never attached.
        page.fill("#query-text", "anonymous query")
        page.click("#ask-btn")
        expect(page.locator("#queries")).to_contain_text("anonymous query", timeout=5000)
        expect(page.locator("#queries")).not_to_contain_text("Alice")
    finally:
        c.close()


def test_uc_p_04_show_my_name_is_a_choice_per_question(base_url, admin_setup, page):
    """UC-P-04: ticking Show my name attaches the typed name to that question only."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P04n {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#ask-card:visible")
        expect(page.locator("#ask-name")).to_be_hidden()
        page.check("#ask-show-name")
        page.fill("#ask-name", "Bob")
        page.fill("#query-text", "named question")
        page.click("#ask-btn")
        expect(page.locator("#queries")).to_contain_text("— Bob", timeout=5000)
        expect(page.locator("#ask-show-name")).not_to_be_checked()
        expect(page.locator("#ask-name")).to_be_hidden()
        page.fill("#query-text", "second question")
        page.click("#ask-btn")
        row = page.locator("#queries .question", has_text="second question")
        expect(row).to_be_visible(timeout=5000)
        expect(row).not_to_contain_text("Bob")
    finally:
        c.close()


def test_uc_p_03_attendee_profile_persists(
    base_url,
    admin_setup,
    page,
    tmp_path,
):
    """UC-P-03: attendee profile fields save and prefill after reload."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P03prof {secrets.token_hex(3)}")
    photo = tmp_path / "dana.png"
    photo.write_bytes(PNG_BYTES)
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#profile-card:visible")
        expect(page.locator("#profile-card")).not_to_have_attribute("open", "")
        expect(page.locator(".profile-title-closed")).to_be_visible()
        expect(page.locator(".profile-cta-closed")).to_be_visible()
        page.locator("#profile-card > summary").click()
        expect(page.locator(".profile-title-open")).to_be_visible()
        expect(page.locator(".profile-cta-open")).to_be_visible()
        expect(page.locator("#profile-submit")).to_have_text("Submit profile")
        page.fill("#my-name", "Dana")
        page.fill("#my-email", "dana@example.com")
        page.fill("#my-contact-number", "+1 415 555 0101")
        page.fill("#my-organization", "ExampleCo")
        page.fill("#my-role", "Engineering Manager")
        page.fill("#my-linkedin-url", "https://www.linkedin.com/in/dana-example")
        page.set_input_files("#my-photo", str(photo))
        expect(page.locator("#my-photo-preview")).to_be_visible(timeout=5000)
        page.fill("#my-current-work", "Building a training platform")
        page.fill("#my-learning-goal", "Practice live facilitation")
        page.click("#profile-submit")
        saved_toast = page.locator(".toast").filter(has_text="Profile submitted")
        expect(saved_toast).to_be_visible(
            timeout=5000
        )
        expect(page.locator("#profile-submit")).to_have_text("Resubmit profile")

        page.reload()
        page.wait_for_selector("#profile-card:visible")
        expect(page.locator("#profile-card")).not_to_have_attribute("open", "")
        expect(page.locator(".profile-title-closed")).to_be_visible()
        expect(page.locator(".profile-cta-closed")).to_be_visible()
        page.locator("#profile-card > summary").click()
        expect(page.locator(".profile-title-open")).to_be_visible()
        expect(page.locator(".profile-cta-open")).to_be_visible()
        expect(page.locator("#profile-submit")).to_have_text("Resubmit profile")
        expect(page.locator("#my-name")).to_have_value("Dana")
        expect(page.locator("#my-email")).to_have_value("dana@example.com")
        expect(page.locator("#my-contact-number")).to_have_value("+1 415 555 0101")
        expect(page.locator("#my-organization")).to_have_value("ExampleCo")
        expect(page.locator("#my-role")).to_have_value("Engineering Manager")
        expect(page.locator("#my-linkedin-url")).to_have_value("https://www.linkedin.com/in/dana-example")
        expect(page.locator("#my-photo-preview")).to_be_visible()
        expect(page.locator("#my-photo-preview")).to_have_attribute(
            "src",
            re.compile(r"/uploads/"),
        )
        expect(page.locator("#my-current-work")).to_have_value("Building a training platform")
        expect(page.locator("#my-learning-goal")).to_have_value("Practice live facilitation")
        page.click("#my-photo-clear")
        expect(page.locator("#my-photo-preview")).to_be_hidden(timeout=5000)
    finally:
        c.close()


# ---------- UC-P-04 ----------


def test_uc_p_04_ask_query_appears_in_list(base_url, admin_setup, page):
    """UC-P-04: typing into #query-text and clicking Submit adds the query and toasts."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P04 {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#ask-card:visible")
        page.fill("#query-text", "asked-via-button")
        page.click("#ask-btn")
        expect(page.locator("#queries")).to_contain_text("asked-via-button", timeout=5000)
        expect(page.locator(".toast")).to_contain_text("submitted", timeout=5000)
    finally:
        c.close()


def test_uc_p_04_ctrl_enter_submits(base_url, admin_setup, page):
    """UC-P-04: Cmd/Ctrl+Enter in #query-text submits."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P04k {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#ask-card:visible")
        page.fill("#query-text", "ctrl-enter-submit")
        page.locator("#query-text").press("Control+Enter")
        expect(page.locator("#queries")).to_contain_text("ctrl-enter-submit", timeout=5000)
    finally:
        c.close()


def test_uc_p_04_ended_session_hides_ask_card(base_url, admin_setup, page):
    """UC-P-04: ended session → #ask-card hidden, #ended-card visible."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P04e {secrets.token_hex(3)}")
    api_end_session(c, s["code"])
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#ended-card:visible", timeout=5000)
        expect(page.locator("#ask-card")).to_be_hidden()
        expect(page.locator("#ended-card")).to_be_visible()
    finally:
        c.close()


# ---------- UC-P-05 ----------


def test_uc_p_05_vote_toggles_count_and_aria(base_url, admin_setup, page):
    """UC-P-05: clicking the vote button increments count and sets aria-pressed=true; again decrements."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P05 {secrets.token_hex(3)}")
    # Ask the query as a different participant so this voter can upvote.
    ask_query_api(base_url, s["code"], "votable-query")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#queries .question")
        q = page.locator("#queries .question").filter(has_text="votable-query")
        btn = q.locator("button.vote-btn")
        expect(btn).to_have_attribute("aria-pressed", "false")
        btn.click()
        expect(btn).to_have_attribute("aria-pressed", "true", timeout=5000)
        expect(btn.locator(".count")).to_have_text("1")
        btn.click()
        expect(btn).to_have_attribute("aria-pressed", "false", timeout=5000)
        expect(btn.locator(".count")).to_have_text("0")
    finally:
        c.close()


# ---------- UC-P-06 ----------


def test_uc_p_06_queries_sorted_unresponded_first_then_votes(base_url, admin_setup, page):
    """UC-P-06: unresponded queries appear above responded; within unresponded, vote_count desc."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P06 {secrets.token_hex(3)}")
    # Three queries:
    # q1 will be marked responded, q2 high votes, q3 low.
    q1 = ask_query_api(base_url, s["code"], "to-respond-q1")
    q2 = ask_query_api(base_url, s["code"], "high-votes-q2")
    ask_query_api(base_url, s["code"], "low-votes-q3")  # third query, left unvoted
    # Mark q1 responded.
    c.post(f"/api/sessions/{s['code']}/queries/{q1['id']}/respond", json={"response_text": "done"}).raise_for_status()
    # Give q2 an upvote (different voter cookie).
    httpx.post(
        f"{base_url}/api/sessions/{s['code']}/queries/{q2['id']}/vote",
        cookies={"voter_token": "voter-x-token"},
        timeout=5.0,
    )
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#queries .question")
        # Sorted: q2 (unresp, 1 vote) > q3 (unresp, 0 votes) > q1 (responded).
        rows = page.locator("#queries .question").all_text_contents()
        # Find positions.
        idx = lambda needle: next(i for i, t in enumerate(rows) if needle in t)
        assert idx("high-votes-q2") < idx("low-votes-q3") < idx("to-respond-q1")
    finally:
        c.close()


# ---------- UC-P-07 ----------


def test_uc_p_07_live_quiz_card_visible(base_url, admin_setup, page):
    """UC-P-07: with a live run, #quiz-card is visible and shows the current question."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P07 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-P07s {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        expect(page.locator("#quiz-card")).to_be_visible(timeout=5000)
        expect(page.locator("#quiz-body")).to_contain_text("2+2?")
    finally:
        c.close()


def test_uc_p_07_closed_run_hidden_on_participant(base_url, admin_setup, page):
    """UC-P-07: closed run → participant card disappears.

    Final results live on the projector / moderator views. The
    participant surface only renders live runs to keep focus on
    actionable state.
    """
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P07c {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-P07cs {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close").raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        expect(page.locator("#quiz-card")).to_be_hidden(timeout=5000)
    finally:
        c.close()


# ---------- UC-P-08 ----------


def test_uc_p_08_submit_single_choice(base_url, admin_setup, page):
    """UC-P-08: single-choice — clicking an answer selects exclusively; Submit posts and toasts."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P08 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-P08s {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-card:visible")
        # Click the first answer button (non-Submit).
        first_opt = page.locator("#quiz-body button.option").first
        first_opt.click()
        expect(first_opt).to_have_attribute("aria-pressed", "true")
        # Submit button now enabled.
        submit = page.locator("#quiz-body button.primary")
        expect(submit).to_be_enabled()
        submit.click()
        # After submit, the page refreshes; "Your answer is recorded." text appears.
        expect(page.locator("#quiz-body")).to_contain_text("recorded", timeout=5000)
    finally:
        c.close()


def test_uc_p_08_selected_answer_is_marked(base_url, admin_setup, page):
    """UC-P-08: the chosen answer shows a ✓ and "Selected"; others show neither."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P08m {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-P08ms {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-card:visible")
        options = page.locator("#quiz-body button.option")
        options.first.click()
        expect(options.first).to_contain_text("✓")
        expect(options.first).to_contain_text("Selected")
        expect(options.nth(1)).not_to_contain_text("Selected")
        expect(options.nth(1)).not_to_contain_text("✓")
    finally:
        c.close()


def test_uc_p_08_reveal_disables_inputs(base_url, admin_setup, page):
    """UC-P-08: after moderator reveals, the answer inputs become disabled."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P08r {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-P08rs {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-card:visible")
        # Reveal via API.
        c.post(
            f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/reveal",
            json={"reveal": True},
        ).raise_for_status()
        # Wait for WS refresh; option buttons now disabled.
        expect(page.locator("#quiz-body button.option").first).to_be_disabled(timeout=5000)
    finally:
        c.close()


# ---------- UC-P-09 ----------


def test_uc_p_09_results_show_correctness(base_url, admin_setup, page):
    """UC-P-09: after reveal, answers show correctness marker; participant's selection
    is marked correct or wrong.
    """
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P09 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-P09s {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-card:visible")
        # Pick the first option (incorrect: "3"), then reveal.
        page.locator("#quiz-body button.option").first.click()
        page.locator("#quiz-body button.primary").click()
        # Wait for "recorded".
        expect(page.locator("#quiz-body")).to_contain_text("recorded", timeout=5000)
        # Reveal.
        c.post(
            f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/reveal",
            json={"reveal": True},
        ).raise_for_status()
        # The correct option has class .correct (the "4" button).
        expect(page.locator("#quiz-body button.option.correct")).to_be_visible(timeout=5000)
        # The selected wrong option is marked .wrong.
        expect(page.locator("#quiz-body button.option.wrong")).to_be_visible()
    finally:
        c.close()


# ---------- UC-P-10 ----------


def test_uc_p_10_share_qr_renders(base_url, admin_setup, page):
    """UC-P-10: #invite-card visible and #share-qr renders an SVG QR."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P10 {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        expect(page.locator("#invite-card")).to_be_visible()
        expect(page.locator("#share-qr svg")).to_be_visible(timeout=10000)
    finally:
        c.close()


def test_uc_d_02_share_qr_expands(base_url, admin_setup, page):
    """UC-D-02: the participant invite QR is click-to-enlarge via the shared lightbox."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P10x {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#share-qr svg")
        page.click("#share-qr")
        expect(page.locator(".qr-lightbox")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator(".qr-lightbox")).to_be_hidden()
    finally:
        c.close()


# ---------- UC-P-11 ----------


def test_uc_p_11_ended_session_hides_ask_and_keeps_queries(base_url, admin_setup, page):
    """UC-P-11: after session ends (via WS), #ask-card hidden, #ended-card visible, queries still listed."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P11 {secrets.token_hex(3)}")
    ask_query_api(base_url, s["code"], "persist-after-end")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#ask-card:visible")
        # End it.
        api_end_session(c, s["code"])
        # WS refresh hides ask-card.
        expect(page.locator("#ended-card")).to_be_visible(timeout=5000)
        expect(page.locator("#ask-card")).to_be_hidden()
        expect(page.locator("#queries")).to_contain_text("persist-after-end")
    finally:
        c.close()


def test_uc_p_11_ended_empty_state_and_section_links(base_url, admin_setup, page):
    """UC-P-11: ended + no questions reads 'No questions were asked.'; links hide for hidden sections."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P11e {secrets.token_hex(3)}")
    api_start_session(c, s["code"])
    api_end_session(c, s["code"])
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        expect(page.locator("#ended-card")).to_be_visible(timeout=5000)
        expect(page.locator("#queries")).to_contain_text("No questions were asked.")
        links = page.locator(".section-links a")
        for hidden in ("Ask", "Quiz", "Feedback"):
            expect(links.filter(has_text=hidden)).to_be_hidden()
        for shown in ("Profile", "Questions"):
            expect(links.filter(has_text=shown)).to_be_visible()
    finally:
        c.close()


# ---------- UC-P-12 ----------


def test_uc_p_12_graded_live_counts_show_only_how_many_answered(base_url, admin_setup, page):
    """UC-P-12: graded, counts on: the phone shows how many answered, not the split."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P12 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-P12s {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    question = c.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()["current_question"]
    for i in range(2):
        httpx.post(f"{base_url}/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
                   cookies={"voter_token": f"p12-{i}-{secrets.token_hex(3)}"},
                   json={"question_id": question["id"], "answer_ids": [question["answers"][0]["id"]]},
                   timeout=10.0).raise_for_status()
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts", json={"show": True}).raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-card:visible")
        expect(page.locator("#quiz-answered")).to_have_text("2 answered so far", timeout=5000)
        expect(page.locator("#quiz-body .opt-pct")).to_have_count(0)
        expect(page.locator("#quiz-body button.option").first).to_be_enabled()
        expect(page.locator("#quiz-body button.option.correct")).to_have_count(0)
    finally:
        c.close()


def test_uc_p_12_poll_live_counts_show_bars(base_url, admin_setup, page):
    """UC-P-12: a poll question's live counts show a bar per answer on the phone."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P12p {secrets.token_hex(3)}", publish=True, questions=[{
        "text": "Which city?", "qtype": "single", "graded": False,
        "answers": [{"text": "Pune", "is_correct": False}, {"text": "Delhi", "is_correct": False}],
    }])
    s = api_make_session(c, f"UI-P12ps {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts", json={"show": True}).raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-card:visible")
        expect(page.locator("#quiz-body .opt-pct")).to_have_count(2, timeout=5000)
        expect(page.locator("#quiz-body button.option").first).to_be_enabled()
    finally:
        c.close()


def test_uc_p_12_live_counts_off_default_no_bars(base_url, admin_setup, page):
    """UC-P-12: with show_live_counts=false (default), no bars/counts in answering phase."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P12d {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-P12ds {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-card:visible")
        # No percentages shown.
        expect(page.locator("#quiz-body .opt-pct")).to_have_count(0)
    finally:
        c.close()


def test_uc_p_view_links_follow_the_viewer(base_url, admin_setup, page, browser):
    """UC-P: #view-links shows the other views to the owner and to a delegate, and
    nothing to a participant."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-Pviews {secrets.token_hex(3)}")
    code = s["code"]
    try:
        page.goto(f"{base_url}/s/{code}")
        page.wait_for_selector("#questions-card")
        expect(page.locator("#view-links")).to_be_hidden()

        admin_login_via_ui(page, base_url)
        page.goto(f"{base_url}/s/{code}")
        links = page.locator("#view-links a")
        expect(links).to_have_text(["Sessions", "Session page", "Projector"], timeout=5000)
        expect(links.nth(1)).to_have_attribute("href", f"/m/{code}")
        expect(links.nth(2)).to_have_attribute("href", f"/p/{code}")

        delegate = browser.new_context()
        dpage = delegate.new_page()
        dpage.add_init_script(f"localStorage.setItem('mod_key:{code}', '{s['mod_key']}')")
        dpage.goto(f"{base_url}/s/{code}")
        expect(dpage.locator("#view-links a")).to_have_text(["Session page", "Projector"], timeout=5000)
        delegate.close()
    finally:
        c.close()


# ---------- Double-submit guards and live-update races ----------

DOUBLE_CTRL_ENTER = """(sel) => {
  const field = document.querySelector(sel);
  for (let i = 0; i < 2; i++) {
    field.dispatchEvent(new KeyboardEvent("keydown",
      { key: "Enter", ctrlKey: true, bubbles: true, cancelable: true }));
  }
}"""


def test_uc_p_04_double_ctrl_enter_posts_once(base_url, admin_setup, page):
    """UC-P-04: two quick Ctrl+Enter presses post one question (the key
    clicks #ask-btn, whose guard ignores the second press)."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P04dd {secrets.token_hex(3)}")
    posts = []
    page.on("request", lambda r: posts.append(r.url)
            if r.method == "POST" and r.url.endswith("/queries") else None)
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#ask-card:visible")
        page.fill("#query-text", "asked-only-once")
        page.evaluate(DOUBLE_CTRL_ENTER, "#query-text")
        expect(page.locator("#queries")).to_contain_text("asked-only-once", timeout=5000)
        page.wait_for_timeout(500)  # room for a second POST to show up
        assert len(posts) == 1, posts
        texts = [q["text"] for q in c.get(f"/api/sessions/{s['code']}/queries").json()]
        assert texts == ["asked-only-once"]
    finally:
        c.close()


def test_uc_p_05_double_tap_votes_once(base_url, admin_setup, page):
    """UC-P-05: two quick taps on the vote button send one vote."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P05dd {secrets.token_hex(3)}")
    ask_query_api(base_url, s["code"], "double-tap-query")
    posts = []
    page.on("request", lambda r: posts.append(r.url)
            if r.method == "POST" and r.url.endswith("/vote") else None)
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#queries .question")
        page.evaluate("""() => {
          const b = document.querySelector("#queries .question button.vote-btn");
          b.click(); b.click();
        }""")
        btn = page.locator("#queries .question button.vote-btn")
        expect(btn).to_have_attribute("aria-pressed", "true", timeout=5000)
        page.wait_for_timeout(500)
        assert len(posts) == 1, posts
        rows = c.get(f"/api/sessions/{s['code']}/queries").json()
        assert [q["vote_count"] for q in rows] == [1]
    finally:
        c.close()


def test_uc_p_13_live_updates_keep_feedback_draft(base_url, admin_setup, page):
    """UC-P-13: renaming or ending the session, and closing and reopening
    rating, leave an unsent rating and comment in place."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P13d {secrets.token_hex(3)}")
    code = s["code"]
    api_start_session(c, code)
    c.post(f"/api/sessions/{code}/feedback_enabled", json={"enabled": True}).raise_for_status()
    try:
        page.goto(f"{base_url}/s/{code}")
        page.wait_for_selector("#feedback-card:visible")
        page.locator("#fb-stars button.star").nth(2).click()  # 3 stars
        page.fill("#fb-went-well", "half-typed thought")

        renamed = f"Renamed {secrets.token_hex(3)}"
        c.patch(f"/api/sessions/{code}", json={"title": renamed}).raise_for_status()
        expect(page.locator("#title")).to_have_text(renamed, timeout=5000)
        page.wait_for_timeout(500)  # room for a feedback reload to land
        expect(page.locator("#fb-went-well")).to_have_value("half-typed thought")
        expect(page.locator("#fb-stars button.star.filled")).to_have_count(3)

        api_end_session(c, code)
        expect(page.locator("#ended-card")).to_be_visible(timeout=5000)
        page.wait_for_timeout(500)
        expect(page.locator("#fb-went-well")).to_have_value("half-typed thought")
        expect(page.locator("#fb-stars button.star.filled")).to_have_count(3)

        c.post(f"/api/sessions/{code}/feedback_enabled", json={"enabled": False}).raise_for_status()
        expect(page.locator("#feedback-card")).to_be_hidden(timeout=5000)
        c.post(f"/api/sessions/{code}/feedback_enabled", json={"enabled": True}).raise_for_status()
        expect(page.locator("#feedback-card")).to_be_visible(timeout=5000)
        page.wait_for_timeout(500)
        expect(page.locator("#fb-went-well")).to_have_value("half-typed thought")
        expect(page.locator("#fb-stars button.star.filled")).to_have_count(3)
    finally:
        c.close()


def test_uc_x_11_live_update_during_bootstrap_is_kept(base_url, admin_setup, page):
    """UC-X-11: a question that arrives through a live update while the
    participant bootstrap is in flight is not wiped by the older bootstrap."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-X11 {secrets.token_hex(3)}")
    held = []

    def hold(route):
        # Fetch now, so the bootstrap body predates the question below.
        held.append((route, route.fetch()))

    try:
        page.route("**/participant-bootstrap", hold)
        page.add_init_script("localStorage.setItem('prashna:socket-close-hook', '1')")
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_function("window.__prashnaLiveSocketTest?.readyState() === 1", timeout=5000)
        for _ in range(50):
            if held:
                break
            page.wait_for_timeout(100)
        assert held, "the bootstrap request was never made"

        ask_query_api(base_url, s["code"], "asked-during-boot")
        expect(page.locator("#queries")).to_contain_text("asked-during-boot", timeout=5000)

        route, stale = held[0]
        route.fulfill(response=stale)
        page.wait_for_function("performance.getEntriesByName('prashna-usable').length > 0", timeout=5000)
        expect(page.locator("#queries")).to_contain_text("asked-during-boot")
    finally:
        c.close()


# ---------- review batch 5: words, not only colour ----------


def test_uc_p_09_wrong_pick_says_wrong_in_words(base_url, admin_setup, page):
    """UC-P-08/09: after reveal a wrong pick shows ✗ and "Your answer · wrong",
    never the ✓ of a chosen answer."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P09w {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-P09ws {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-card:visible")
        page.locator("#quiz-body button.option").first.click()  # "3": wrong
        page.locator("#quiz-body button.primary").click()
        expect(page.locator("#quiz-body")).to_contain_text("recorded", timeout=5000)
        c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/reveal",
               json={"reveal": True}).raise_for_status()
        wrong = page.locator("#quiz-body .option.wrong")
        expect(wrong).to_be_visible(timeout=5000)
        expect(wrong.locator(".opt-mark")).to_have_text("✗")
        expect(wrong.locator(".opt-chosen")).to_have_text("Your answer · wrong")
        expect(wrong).not_to_contain_text("✓")
        expect(page.locator("#quiz-body .option.correct .opt-correct")).to_have_text("✓ Correct")
    finally:
        c.close()


def test_uc_p_11_ended_session_votes_are_not_buttons(base_url, admin_setup, page):
    """UC-P-11: on an ended session the vote counts are plain text."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P11v {secrets.token_hex(3)}")
    ask_query_api(base_url, s["code"], "asked-before-the-end")
    api_end_session(c, s["code"])
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        expect(page.locator("#queries .question")).to_have_count(1, timeout=5000)
        expect(page.locator("#queries .vote-btn")).to_have_count(1)
        expect(page.locator("#queries button")).to_have_count(0)
    finally:
        c.close()


def test_uc_p_06_own_questions_say_your_question(base_url, admin_setup, page):
    """UC-P-06: the participant's own question says "Your question"; others' don't."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P06m {secrets.token_hex(3)}")
    ask_query_api(base_url, s["code"], "someone-else-asked-this")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.fill("#query-text", "i-asked-this-one")
        page.click("#ask-btn")
        mine = page.locator("#queries .question").filter(has_text="i-asked-this-one")
        expect(mine.locator(".mine-marker")).to_have_text("Your question", timeout=5000)
        other = page.locator("#queries .question").filter(has_text="someone-else-asked-this")
        expect(other.locator(".mine-marker")).to_have_count(0)
    finally:
        c.close()


def test_uc_x_01_failed_live_refetch_shows_an_error(base_url, admin_setup, page):
    """UC-X-01: a live-update refetch that fails shows the server's message;
    nothing goes unhandled."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-X01p {secrets.token_hex(3)}")
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        expect(page.locator("#queries")).to_contain_text("No questions yet", timeout=5000)
        page.route(f"**/api/sessions/{s['code']}/queries", lambda route: route.fulfill(
            status=503, content_type="application/json", body='{"detail": "Server is restarting"}')
            if route.request.method == "GET" else route.continue_())
        ask_query_api(base_url, s["code"], "triggers-a-refetch")
        expect(page.locator(".toast-error")).to_contain_text("Server is restarting", timeout=5000)
        assert errors == []
    finally:
        c.close()
