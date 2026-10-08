"""UI tests for the participant surface (/s/<code>).

Covers UC-P-02..12.
"""
from __future__ import annotations

import re
import secrets

import httpx
from playwright.sync_api import expect

from ._helpers import (
    api_end_session,
    api_login,
    api_make_quiz,
    api_make_session,
    api_queue_quiz_run,
    api_start_session,
    ask_query_api,
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
        crumbs = page.locator("#participant-breadcrumbs")
        expect(crumbs).to_contain_text(s["title"], timeout=5000)
        expect(crumbs).to_contain_text("Participant")
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
        # Reload → prior feedback prefilled.
        page.reload()
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


def test_uc_p_13_two_step_clear(base_url, admin_setup, page):
    """UC-P-13: 'Clear rating' is a two-step undo via an inline confirm —
    'No' cancels, 'Yes' clears the rating and hides the comment fields."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P13c {secrets.token_hex(3)}")
    c.post(
        f"/api/sessions/{s['code']}/feedback_enabled",
        json={"enabled": True},
    ).raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#feedback-card:visible")
        page.locator("#fb-stars button.star").nth(4).click()  # 5 stars
        with page.expect_response(
            lambda r: r.url.endswith("/feedback") and r.request.method == "POST"
        ):
            page.click("#fb-submit")
        expect(page.locator("#fb-stars button.star.filled")).to_have_count(5)
        # First tap reveals the confirm; "No" cancels (no delete).
        page.click("#fb-clear")
        expect(page.locator("#fb-clear-confirm")).to_be_visible()
        page.click("#fb-clear-no")
        expect(page.locator("#fb-clear-confirm")).to_be_hidden()
        expect(page.locator("#fb-stars button.star.filled")).to_have_count(5)
        # Re-open and confirm with "Yes" → DELETE clears it.
        page.click("#fb-clear")
        with page.expect_response(
            lambda r: r.url.endswith("/feedback") and r.request.method == "DELETE"
        ):
            page.click("#fb-clear-yes")
        expect(page.locator("#fb-stars button.star.filled")).to_have_count(0)
        expect(page.locator("#fb-expand")).to_be_hidden()
    finally:
        c.close()


# ---------- UC-P-02 ----------


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
        assert token_before == token_after
        # The voted/mine flag is verifiable via API.
        if token_after:
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
        # Asking a query attributes to Alice.
        page.fill("#query-text", "named query")
        page.click("#ask-btn")
        expect(page.locator("#queries")).to_contain_text("Alice", timeout=5000)
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
        for hidden in ("Ask", "Quiz", "Rating"):
            expect(links.filter(has_text=hidden)).to_be_hidden()
        for shown in ("Profile", "Questions"):
            expect(links.filter(has_text=shown)).to_be_visible()
    finally:
        c.close()


# ---------- UC-P-12 ----------


def test_uc_p_12_live_counts_on_shows_bars(base_url, admin_setup, page):
    """UC-P-12: with show_live_counts=true, answering phase shows vote-share bars + %."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-P12 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-P12s {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(
        f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts",
        json={"show": True},
    ).raise_for_status()
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#quiz-card:visible")
        # Bars appear under each option.
        expect(page.locator("#quiz-body .opt-pct").first).to_be_visible(timeout=5000)
        # Options still enabled.
        expect(page.locator("#quiz-body button.option").first).to_be_enabled()
        # No .correct class yet (not revealed).
        expect(page.locator("#quiz-body button.option.correct")).to_have_count(0)
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
