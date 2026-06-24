"""UI tests for the participant surface (/s/<code>).

Covers UC-P-02..12.
"""
from __future__ import annotations

import secrets

import httpx
import pytest
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
    """UC-P-03: typing into #my-name and blurring PATCHes and persists."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-P03 {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#my-name")
        page.fill("#my-name", "Alice")
        page.locator("#my-name").blur()
        # Toast confirms.
        expect(page.locator(".toast")).to_contain_text("Alice", timeout=5000)
        # Asking a query attributes to Alice.
        page.fill("#query-text", "named query")
        page.click("#ask-btn")
        expect(page.locator("#queries")).to_contain_text("Alice", timeout=5000)
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
    q3 = ask_query_api(base_url, s["code"], "low-votes-q3")
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
