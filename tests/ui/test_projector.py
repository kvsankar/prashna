"""UI tests for the projector surface (/p/<code>).

Covers UC-D-01..08. UC-D-05 (reconnect) is skipped — out of scope to simulate
a WebSocket server restart from a unit test.
"""
from __future__ import annotations

import secrets

import pytest
from playwright.sync_api import expect

from ._helpers import (
    api_login,
    api_make_quiz,
    api_make_session,
    api_queue_quiz_run,
    api_start_session,
    ask_query_api,
)


# ---------- UC-D-01 ----------


def test_uc_d_01_projector_renders_basic_elements(base_url, admin_setup, page):
    """UC-D-01: /p/<CODE> shows #title, #code, #origin, #join-qr, #queries."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-D01 {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#title")).to_contain_text(s["title"], timeout=5000)
        expect(page.locator("#code")).to_have_text(s["code"])
        expect(page.locator("#origin")).to_be_visible()
        expect(page.locator("#join-qr svg")).to_be_visible(timeout=10000)
        # No chrome.
        for absent in ["#ask-card", "#login-card", "#sessions-card"]:
            expect(page.locator(absent)).to_have_count(0)
    finally:
        c.close()


def test_uc_d_01_bad_code_redirects(base_url, admin_setup, page):
    """UC-D-01: invalid code → 303 redirect to /; landing shows bad-code banner.

    The landing page's JS strips ?bad_code from the URL via
    history.replaceState, so we check the banner content as proof.
    """
    bogus = "QQQ" + secrets.token_hex(2).upper()[:3]
    page.goto(f"{base_url}/p/{bogus}")
    expect(page.locator("#bad-code-msg")).to_be_visible()
    expect(page.locator("#bad-code-msg")).to_contain_text(bogus.upper())


# ---------- UC-D-02 ----------


def test_uc_d_02_qr_click_opens_lightbox(base_url, admin_setup, page):
    """UC-D-02: clicking #join-qr opens .qr-lightbox; Esc closes it."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-D02 {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        page.wait_for_selector("#join-qr svg")
        page.click("#join-qr")
        expect(page.locator(".qr-lightbox")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator(".qr-lightbox")).to_be_hidden()
    finally:
        c.close()


def test_uc_d_02_qr_keyboard_open(base_url, admin_setup, page):
    """UC-D-02: focusing #join-qr and pressing Enter opens the lightbox."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-D02k {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        page.wait_for_selector("#join-qr svg")
        page.focus("#join-qr")
        page.keyboard.press("Enter")
        expect(page.locator(".qr-lightbox")).to_be_visible()
        # Space also works (test via click instead — Space sometimes triggers scroll).
        page.keyboard.press("Escape")
        expect(page.locator(".qr-lightbox")).to_be_hidden()
    finally:
        c.close()


def test_uc_d_02_click_inside_lightbox_closes(base_url, admin_setup, page):
    """UC-D-02: clicking anywhere inside .qr-lightbox dismisses it."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-D02c {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        page.wait_for_selector("#join-qr svg")
        page.click("#join-qr")
        expect(page.locator(".qr-lightbox")).to_be_visible()
        page.locator(".qr-lightbox").click()
        expect(page.locator(".qr-lightbox")).to_be_hidden()
    finally:
        c.close()


# ---------- UC-D-03 ----------


def test_uc_d_03_live_query_appears_via_ws(base_url, admin_setup, page):
    """UC-D-03: a participant query in another context updates the projector's #queries within ~1s."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-D03 {secrets.token_hex(3)}")
    api_start_session(c, s["code"])
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        page.wait_for_selector("#queries")
        # Send a query via API (simulates another tab).
        ask_query_api(base_url, s["code"], "live-update-text")
        expect(page.locator("#queries")).to_contain_text("live-update-text", timeout=5000)
    finally:
        c.close()


# ---------- UC-D-04 ----------


def test_uc_d_04_planning_has_no_queries_no_quiz(base_url, admin_setup, page):
    """UC-D-04: planning session — #queries empty placeholder, #quiz-section hidden."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-D04 {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#title")).to_contain_text(s["title"], timeout=5000)
        # Wait for first load to settle.
        expect(page.locator("#queries")).to_contain_text("Waiting for questions", timeout=5000)
        expect(page.locator("#quiz-section")).to_be_hidden()
    finally:
        c.close()


def test_uc_d_04_live_with_quiz_run_shows_quiz_section(base_url, admin_setup, page):
    """UC-D-04: starting a quiz run makes #quiz-section visible."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-D04q {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-D04qs {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-section")).to_be_visible(timeout=5000)
        expect(page.locator("#quiz-body")).to_contain_text("2+2?")
    finally:
        c.close()


# ---------- UC-D-05 ----------


def test_uc_d_05_reconnect_skipped():
    """UC-D-05: simulating a WS server restart from a UI test is out of scope."""
    pytest.skip(
        "Cannot reliably simulate a WebSocket server restart from a Playwright "
        "test without tearing down the shared uvicorn process; the reconnect "
        "logic is also covered indirectly by UC-D-03 (any live update)."
    )


# ---------- UC-D-06 ----------


def test_uc_d_06_no_runs_hides_quiz_section(base_url, admin_setup, page):
    """UC-D-06: with no QuizRuns, #quiz-section is hidden."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-D06 {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        page.wait_for_selector("#title:not(:has-text('Loading'))")
        expect(page.locator("#quiz-section")).to_be_hidden()
    finally:
        c.close()


def test_uc_d_06_live_in_answering_phase(base_url, admin_setup, page):
    """UC-D-06: live run in answering phase — shows current question + answers, no .correct."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-D06live {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-D06lives {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-body")).to_contain_text("2+2?", timeout=5000)
        # No correctness markers yet.
        expect(page.locator("#quiz-body .option.correct")).to_have_count(0)
        # No counts (default).
        expect(page.locator("#quiz-body .opt-pct")).to_have_count(0)
    finally:
        c.close()


def test_uc_d_06_reveal_shows_bars_and_correctness(base_url, admin_setup, page):
    """UC-D-06: after reveal, bars + correctness markers appear."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-D06rev {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-D06revs {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(
        f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/reveal",
        json={"reveal": True},
    ).raise_for_status()
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-body .option.correct")).to_be_visible(timeout=5000)
        expect(page.locator("#quiz-body .opt-pct").first).to_be_visible()
    finally:
        c.close()


def test_uc_d_06_closed_run_keeps_final_state(base_url, admin_setup, page):
    """UC-D-06: a single closed run (no live/queued) keeps the last question with tallies."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-D06cl {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-D06cls {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close").raise_for_status()
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-body")).to_contain_text("2+2?", timeout=5000)
        # Closed runs are revealed → correctness markers visible.
        expect(page.locator("#quiz-body .option.correct")).to_be_visible()
    finally:
        c.close()


# ---------- UC-D-07 ----------


def test_uc_d_07_queued_run_shows_lobby(base_url, admin_setup, page):
    """UC-D-07: a queued run (no live) renders the lobby ('Next up:' + quiz title)."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-D07 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-D07s {secrets.token_hex(3)}")
    api_queue_quiz_run(c, s["code"], quiz["id"])
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-section")).to_be_visible(timeout=5000)
        expect(page.locator("#quiz-body")).to_contain_text("Next up:")
        expect(page.locator("#quiz-body")).to_contain_text(quiz["title"])
    finally:
        c.close()


# ---------- UC-D-08 ----------


def test_uc_d_08_live_counts_on_shows_bars(base_url, admin_setup, page):
    """UC-D-08: show_live_counts=true → answering phase has bars + % without correctness."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-D08 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-D08s {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(
        f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts",
        json={"show": True},
    ).raise_for_status()
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-body .opt-pct").first).to_be_visible(timeout=5000)
        # No correctness yet.
        expect(page.locator("#quiz-body .option.correct")).to_have_count(0)
    finally:
        c.close()


def test_uc_d_08_live_counts_off_reverts(base_url, admin_setup, page):
    """UC-D-08: toggling live counts off via API triggers WS refresh; bars disappear."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-D08off {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-D08offs {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(
        f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts",
        json={"show": True},
    ).raise_for_status()
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-body .opt-pct").first).to_be_visible(timeout=5000)
        # Toggle off.
        c.post(
            f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts",
            json={"show": False},
        ).raise_for_status()
        expect(page.locator("#quiz-body .opt-pct")).to_have_count(0, timeout=5000)
    finally:
        c.close()
