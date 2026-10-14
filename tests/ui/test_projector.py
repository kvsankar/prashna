"""UI tests for the projector surface (/p/<code>)."""
from __future__ import annotations

import json
import secrets

import httpx
from playwright.sync_api import expect

from ._helpers import (
    api_login,
    api_make_quiz,
    api_make_session,
    api_queue_quiz_run,
    api_start_session,
    ask_query_api,
)


def assert_no_horizontal_overflow(page):
    overflow = page.evaluate(
        """() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        })"""
    )
    assert overflow["scrollWidth"] <= overflow["clientWidth"] + 1, overflow

# ---------- UC-D-01 ----------


def test_uc_d_01_projector_renders_basic_elements(base_url, admin_setup, page):
    """UC-D-01: /p/<CODE> shows #title, #code, #origin, #join-qr, #queries."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-D01 {secrets.token_hex(3)}")
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#title")).to_contain_text(s["title"], timeout=5000)
        expect(page).to_have_title(f"{s['title']} · Projector — Prashna")
        expect(page.locator("#code")).to_have_text(s["code"])
        expect(page.locator("#origin")).to_be_visible()
        expect(page.locator("#join-qr svg")).to_be_visible(timeout=10000)
        # No chrome.
        for absent in ["#ask-card", "#login-card", "#sessions-card"]:
            expect(page.locator(absent)).to_have_count(0)
    finally:
        c.close()


def test_uc_d_01_first_load_fetches_display_state_once(base_url, admin_setup, page):
    """The initial socket connection must not duplicate projector API reads."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-D01-load {secrets.token_hex(3)}")
    seen: list[str] = []
    page.on("request", lambda request: seen.append(request.url))
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#title")).to_contain_text(s["title"], timeout=5000)
        page.wait_for_timeout(750)

        prefix = f"/api/sessions/{s['code']}"
        assert sum(url.endswith(f"{prefix}/display-bootstrap") for url in seen) == 1
        assert sum(url.endswith(prefix) for url in seen) == 0
        assert sum(url.endswith(f"{prefix}/queries?display=true") for url in seen) == 0
        assert sum(url.endswith(f"{prefix}/quiz_runs?display=true") for url in seen) == 0
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


def test_mobile_projector_keeps_live_state_visible(base_url, admin_setup, page):
    """Mobile-width projector keeps join, query, and quiz state usable."""
    page.set_viewport_size({"width": 360, "height": 820})
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-D-mobile-q {secrets.token_hex(3)}",
                         publish=True)
    s = api_make_session(c, f"UI-D-mobile {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(
        f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start"
    ).raise_for_status()
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#code")).to_have_text(s["code"])
        expect(page.locator("#join-qr svg")).to_be_visible(timeout=10000)
        expect(page.locator("#quiz-section")).to_be_visible(timeout=5000)
        assert_no_horizontal_overflow(page)

        ask_query_api(base_url, s["code"], "projector mobile question")
        expect(page.locator("#queries")).to_contain_text(
            "projector mobile question",
            timeout=5000,
        )
        assert_no_horizontal_overflow(page)
    finally:
        c.close()


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


def test_uc_d_02_qr_rerenders_when_join_url_changes_with_same_base(base_url, admin_setup, page):
    """UC-D-02: projector QR cache is keyed by the full participant URL, not only origin."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-D02url {secrets.token_hex(3)}")
    try:
        calls = {"session": 0}

        def route_bootstrap(route):
            calls["session"] += 1
            code = s["code"] if calls["session"] == 1 else "NEWS01"
            title = s["title"] if calls["session"] == 1 else "Changed title"
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "session": {
                        "code": code,
                        "title": title,
                        "status": "planning",
                        "participant_base_url": base_url,
                        "feedback_enabled": False,
                    },
                    "queries": [],
                    "quiz_runs": [],
                }),
            )

        page.route(
            f"**/api/sessions/{s['code']}/display-bootstrap",
            route_bootstrap,
        )
        page.goto(f"{base_url}/p/{s['code']}")
        page.wait_for_selector("#join-qr svg")
        first_qr = page.locator("#join-qr").inner_html()

        ask_query_api(base_url, s["code"], "trigger qr reload")

        expect(page.locator("#title")).to_have_text("Changed title", timeout=5000)
        page.wait_for_function(
            "initial => document.querySelector('#join-qr').innerHTML !== initial",
            arg=first_qr,
            timeout=5000,
        )
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


def test_uc_d_05_reconnect_refetches_after_close(base_url, admin_setup, page):
    """UC-D-05: reconnect refetch catches a broadcast missed while closed."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-D05 {secrets.token_hex(3)}")
    api_start_session(c, s["code"])
    text = f"reconnect-catchup-{secrets.token_hex(3)}"
    try:
        page.add_init_script(
            "localStorage.setItem('prashna:socket-close-hook', '1')"
        )
        page.goto(f"{base_url}/p/{s['code']}")
        page.wait_for_selector("#queries")
        page.wait_for_function(
            "window.__prashnaLiveSocketTest?.activeCount() === 1",
            timeout=5000,
        )

        page.evaluate("window.__prashnaLiveSocketTest.closeActive()")
        page.wait_for_function(
            "window.__prashnaLiveSocketTest.activeCount() === 0",
            timeout=5000,
        )
        ask_query_api(base_url, s["code"], text)

        expect(page.locator("#queries")).to_contain_text(text, timeout=5000)
    finally:
        c.close()


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


def test_uc_d_06_question_text_not_uppercased(base_url, admin_setup, page):
    """UC-D-06: the projector shows the question as written (no forced uppercase)."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-D06case {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-D06cases {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-body")).to_contain_text("2+2?", timeout=5000)
        question = page.locator("#quiz-body .proj-question")
        expect(question).to_have_text("2+2?")
        assert question.evaluate("e => getComputedStyle(e).textTransform") == "none"
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
        # The room screen invites people in; it doesn't describe operator controls.
        expect(page.locator("#quiz-body")).to_contain_text("Scan the code to join — the quiz starts soon.")
        expect(page.locator("#quiz-body")).not_to_contain_text("moderator")
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


def test_uc_d_08_graded_live_counts_hide_answers_until_reveal(base_url, admin_setup, page):
    """UC-D-08: a graded question's live counts are unlabelled, largest first, until reveal."""
    c = api_login(base_url)
    quiz = api_make_quiz(
        c,
        f"UI-D08mask {secrets.token_hex(3)}",
        publish=True,
        questions=[
            {
                "text": "Pick the deployment marker",
                "qtype": "single",
                "answers": [
                    {"text": "Alpha", "is_correct": False},
                    {"text": "Bravo", "is_correct": True},
                    {"text": "Charlie", "is_correct": False},
                ],
            }
        ],
    )
    s = api_make_session(c, f"UI-D08masks {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    state = c.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()
    question = state["current_question"]
    answers = question["answers"]
    for token, answer in (
        ("mask-a", answers[0]),
        ("mask-b", answers[1]),
        ("mask-c", answers[1]),
        ("mask-d", answers[2]),
        ("mask-e", answers[2]),
        ("mask-f", answers[2]),
    ):
        httpx.post(
            f"{base_url}/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
            cookies={"voter_token": f"{token}-{secrets.token_hex(3)}"},
            json={"question_id": question["id"], "answer_ids": [answer["id"]]},
            timeout=10.0,
        ).raise_for_status()
    c.post(
        f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts",
        json={"show": True},
    ).raise_for_status()
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-body .opt-pct")).to_have_count(3, timeout=5000)
        for label in ("Alpha", "Bravo", "Charlie"):
            expect(page.locator("#quiz-body")).not_to_contain_text(label)
        expect(page.locator("#quiz-body .opt-text")).to_have_text(["Option A", "Option B", "Option C"])
        expect(page.locator("#quiz-body .opt-pct")).to_have_text(["3 (50%)", "2 (33%)", "1 (17%)"])
        expect(page.locator("#quiz-body .option.correct")).to_have_count(0)

        c.post(
            f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/reveal",
            json={"reveal": True},
        ).raise_for_status()
        expect(page.locator("#quiz-body .opt-text")).to_have_text(["Alpha", "Bravo", "Charlie"])
        expect(page.locator("#quiz-body .option.correct")).to_be_visible()
    finally:
        c.close()


def test_uc_d_08_poll_live_counts_show_answers(base_url, admin_setup, page):
    """UC-D-08: a poll question's live counts show the real answers."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-D08poll {secrets.token_hex(3)}", publish=True, questions=[{
        "text": "Which city?", "qtype": "single", "graded": False,
        "answers": [{"text": "Pune", "is_correct": False}, {"text": "Delhi", "is_correct": False}],
    }])
    s = api_make_session(c, f"UI-D08polls {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    question = c.get(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}").json()["current_question"]
    httpx.post(f"{base_url}/api/sessions/{s['code']}/quiz_runs/{run['id']}/submit",
               cookies={"voter_token": f"poll-{secrets.token_hex(3)}"},
               json={"question_id": question["id"], "answer_ids": [question["answers"][0]["id"]]},
               timeout=10.0).raise_for_status()
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts", json={"show": True}).raise_for_status()
    try:
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-body .opt-text")).to_have_text(["Pune", "Delhi"], timeout=5000)
        expect(page.locator("#quiz-body .opt-pct")).to_have_text(["1 (100%)", "0 (0%)"])
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


# ---------- live updates that cannot freeze (UC-X-01, UC-D-05) ----------

def _vote_as_new_participant(base_url, code, run_id):
    with httpx.Client(base_url=base_url, timeout=5) as p:
        q = p.get(f"/api/sessions/{code}/quiz_runs/{run_id}").json()["current_question"]
        r = p.post(f"/api/sessions/{code}/quiz_runs/{run_id}/submit",
                   json={"question_id": q["id"], "answer_ids": [q["answers"][0]["id"]]})
        assert r.status_code == 200, r.text


def _live_quiz_with_counts(base_url):
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-live {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-lives {secrets.token_hex(3)}")
    api_start_session(c, s["code"])
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/live_counts", json={"show": True}).raise_for_status()
    return c, s, run


def test_uc_x_01_silent_socket_reconnects(base_url, admin_setup, page):
    """UC-X-01: a socket that stays open but delivers nothing is replaced once
    the page's keepalive hears no reply (timings shortened for the test build)."""
    c, s, _run = _live_quiz_with_counts(base_url)
    opened = []

    def swallow_server_frames(ws):
        opened.append(ws.url)
        server = ws.connect_to_server()
        server.on_message(lambda _message: None)  # the server's frames never reach the page

    try:
        page.add_init_script("localStorage.setItem('prashna:keepalive-ms', '300')")
        page.route_web_socket("**/ws/sessions/**", swallow_server_frames)
        page.goto(f"{base_url}/p/{s['code']}")
        page.wait_for_selector("#quiz-body .option")
        for _ in range(50):
            if len(opened) >= 2:
                break
            page.wait_for_timeout(100)
        assert len(opened) >= 2, "the page kept a silent socket instead of reconnecting"
    finally:
        c.close()


def test_uc_x_01_slowed_background_timers_keep_the_socket(base_url, admin_setup, page):
    """UC-X-01: a background tab whose timers the browser runs only once a
    minute keeps its socket; it reconnects only when a ping goes unanswered."""
    c = api_login(base_url)
    s = api_make_session(c, f"UI-X01slow {secrets.token_hex(3)}")
    opened = []
    page.on("websocket", lambda ws: opened.append(ws.url))
    try:
        page.clock.install()
        page.goto(f"{base_url}/s/{s['code']}")
        page.wait_for_selector("#ask-card:visible")
        page.wait_for_timeout(500)
        for _ in range(3):
            # One jump fires the 25 s ping timer once, as in a throttled tab.
            page.clock.fast_forward("01:01")
            page.wait_for_timeout(500)  # the ping's reply arrives
        assert len(opened) == 1, opened
    finally:
        c.close()


def test_uc_d_05_projector_polls_while_a_quiz_is_live(base_url, admin_setup, page):
    """UC-D-05: with no live updates at all, the projector still shows new votes within ~5 s."""
    c, s, run = _live_quiz_with_counts(base_url)
    try:
        page.route_web_socket("**/ws/sessions/**", lambda _ws: None)  # socket opens, nothing ever arrives
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-body")).to_contain_text("0 respondent", timeout=5000)
        _vote_as_new_participant(base_url, s["code"], run["id"])
        expect(page.locator("#quiz-body")).to_contain_text("1 respondent", timeout=8000)
    finally:
        c.close()


def test_uc_d_01_room_text_is_display_size(base_url, admin_setup, page):
    """UC-D-01: text the room reads is at least 20 px at 1920x1080, and the
    lobby title is in the main text colour, not uppercase."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-D01size {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-D01sizes {secrets.token_hex(3)}")
    api_start_session(c, s["code"])
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/reveal", json={"reveal": True}).raise_for_status()
    httpx.post(f"{base_url}/api/sessions/{s['code']}/queries",
               json={"text": "Who wrote this?", "author_name": "Asha"}, timeout=5.0).raise_for_status()
    lobby_session = api_make_session(c, f"UI-D01lobby {secrets.token_hex(3)}")
    api_queue_quiz_run(c, lobby_session["code"], quiz["id"])
    size = "e => parseFloat(getComputedStyle(e).fontSize)"
    try:
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.goto(f"{base_url}/p/{s['code']}")
        expect(page.locator("#quiz-body .option.correct")).to_be_visible(timeout=5000)
        expect(page.locator("#queries")).to_contain_text("Asha", timeout=5000)
        small = {
            "question line": page.locator("#quiz-body > .muted").first,
            "respondents": page.locator("#quiz-body > .muted").last,
            "author": page.locator("#queries .question .body .small").first,
            "votes label": page.locator("#queries .vote-btn .label").first,
        }
        sizes = {name: loc.evaluate(size) for name, loc in small.items()}
        assert all(v >= 20 for v in sizes.values()), sizes

        page.goto(f"{base_url}/p/{lobby_session['code']}")
        expect(page.locator("#quiz-body")).to_contain_text("Next up:", timeout=5000)
        assert page.locator("#quiz-body > .muted").first.evaluate(size) >= 20
        title = page.locator("#quiz-body .proj-lobby-title")
        assert title.evaluate("e => getComputedStyle(e).textTransform") == "none"
        assert title.evaluate("e => getComputedStyle(e).color") == page.locator("#title").evaluate(
            "e => getComputedStyle(e).color")
    finally:
        c.close()
