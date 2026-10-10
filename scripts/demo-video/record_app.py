#!/usr/bin/env python3
"""Record the Prashna demo scenes against a fresh Prashna 0.4.0.

Starts the `prashna` installed by run_install.sh (clean HOME) on 127.0.0.1:8000
with an empty data folder, then drives the real pages headless with Playwright:

  admin.webm      1920x1080  setup, session, quiz library, moderator actions
  projector.webm  1920x1080  /p/<code>
  phone.webm      390x844    participant on a phone (is_mobile, has_touch)
  terminal.webm   1920x1080  the install scene (terminal.html typing the real output)

Other participants are simulated with httpx clients (own voter cookie each).
Every key moment is written to timeline.json as a wall-clock mark together with
each recording's start time, so compose.sh can cut the recordings in sync.

Run:  uv run --project tooling python record_app.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

W = Path(__file__).resolve().parent
CLEAN = W / "clean-home"
OUT = W / "recordings"
PORT = 8000
BASE = f"http://127.0.0.1:{PORT}"
SETUP_TOKEN = "demo-setup-token-3f9c1b"  # never shown on screen; fictional
ADMIN = {"username": "trainer", "password": "onboarding-2026"}  # pragma: allowlist secret  (throwaway demo database)
SESSION_TITLE = "Product onboarding workshop"
QUIZ_TITLE = "Onboarding check"
QUESTIONS = [
    ("Where is the team handbook kept?", ["In the shared drive", "On the intranet wiki", "In the welcome email"], 1),
    ("Who approves a laptop request?", ["The team lead", "IT support", "Finance"], 0),
    ("When is the first check-in with your manager?", ["End of week one", "End of month one", "After probation"], 0),
]
PHONE_NAME = "Diego"
PHONE_QUESTION = "Can we get the slides after the session?"
OTHERS = [
    ("Asha", "Is there a recording of this session?"),
    ("Ben", "Which tool do we use for time sheets?"),
    ("Chen", "How do I get access to the staging server?"),
    ("Mira", "Is the handbook available offline?"),
]
TYPE_DELAY = 55  # ms per character for visible typing

T0 = time.monotonic()
marks: dict[str, float] = {}
videos: dict[str, dict[str, object]] = {}


def now() -> float:
    return round(time.monotonic() - T0, 3)


def mark(name: str) -> None:
    marks[name] = now()
    print(f"  [{marks[name]:7.2f}] {name}", flush=True)


def start_server() -> subprocess.Popen:
    data = W / "demo-data"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir()
    env = {
        "HOME": str(CLEAN),
        "PATH": f"{CLEAN}/.local/bin:/usr/bin:/bin",
        "TMPDIR": str(CLEAN / "tmp"),
        "PRASHNA_SETUP_TOKEN": SETUP_TOKEN,
        "PRASHNA_RATELIMIT": "off",
    }
    log = open(W / "server-output.raw.txt", "w")
    proc = subprocess.Popen(
        [str(CLEAN / ".local/bin/prashna"), "--no-browser", "--data-dir", str(data), "--port", str(PORT)],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/api/admin/status", timeout=1.0, trust_env=False).status_code == 200:
                return proc
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    raise SystemExit("prashna did not start")


def client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=10.0, trust_env=False)


def type_into(page: Page, selector: str, text: str, *, clear: bool = False) -> None:
    loc = page.locator(selector)
    loc.click()
    if clear:
        loc.fill("")
    loc.press_sequentially(text, delay=TYPE_DELAY)


def pause(sec: float) -> None:
    time.sleep(sec)


def main() -> int:
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    shots = W / "shots"
    shutil.rmtree(shots, ignore_errors=True)
    shots.mkdir()
    server = start_server()
    print("server up")
    # The server has written server-output.raw.txt; build the terminal text now.
    subprocess.run([sys.executable, "-I", str(W / "sanitize_terminal.py")], check=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-proxy-server"])
            desktop = dict(viewport={"width": 1920, "height": 1080}, record_video_dir=str(OUT),
                           record_video_size={"width": 1920, "height": 1080})
            # ---------------- terminal scene ----------------
            term_lines = (W / "terminal-text.txt").read_text().splitlines()
            ctx = browser.new_context(**desktop)
            tp = ctx.new_page()
            terminal_video: dict[str, object] = {"start": now()}
            videos["terminal"] = terminal_video
            tp.goto((W / "terminal.html").as_uri())
            tp.evaluate("lines => window.runScript(lines)", term_lines)
            pause(2.5)
            tp.screenshot(path=str(shots / "terminal.png"))
            tp.close()
            ctx.close()
            assert tp.video is not None  # recording is on for every context
            videos["terminal"]["path"] = str(tp.video.path())

            # ---------------- admin context ----------------
            actx = browser.new_context(**desktop)
            a = actx.new_page()
            videos["admin"] = {"start": now()}
            # a. first-run setup
            a.goto(f"{BASE}/#setup={SETUP_TOKEN}")
            a.wait_for_selector("#setup-card:visible")
            mark("setup_page")
            pause(1.0)
            type_into(a, "#su-user", ADMIN["username"])
            pause(0.4)
            type_into(a, "#su-pass", ADMIN["password"])
            pause(0.3)
            type_into(a, "#su-pass2", ADMIN["password"])
            pause(0.5)
            a.click("#su-btn")
            a.wait_for_selector("#sessions-card:visible")
            mark("setup_done")
            a.screenshot(path=str(shots / "a-setup-done.png"))
            pause(1.2)
            # b. create a session
            mark("session_create_start")
            type_into(a, "#new-session-title", SESSION_TITLE)
            pause(0.5)
            a.click("#new-session-btn")
            a.wait_for_selector(f"#session-rows tr:has-text('{SESSION_TITLE}')")
            mark("session_created")
            pause(1.5)
            a.screenshot(path=str(shots / "b-session.png"))
            admin_api = client()
            r = admin_api.post("/api/admin/login", json=ADMIN)
            r.raise_for_status()
            sessions = admin_api.get("/api/sessions").json()
            code = next(s["code"] for s in sessions if s["title"] == SESSION_TITLE)
            print("session code", code)

            # c. quiz library
            a.goto(f"{BASE}/quizzes")
            a.wait_for_selector("#quiz-rows")
            mark("library_page")
            pause(0.8)
            type_into(a, "#new-quiz-title", QUIZ_TITLE)
            pause(0.4)
            a.click("#create-quiz")
            a.wait_for_selector("#editor-card:visible")
            pause(0.8)
            a.locator("#editor-body button", has_text="+ Add question").click()
            a.wait_for_selector("#editor-body .editor-q")
            pause(0.5)
            q_text, answers, correct_idx = QUESTIONS[0]
            qbox = a.locator("#editor-body .editor-q").first
            ta = qbox.locator("textarea").first
            ta.click()
            ta.fill("")
            ta.press_sequentially(q_text, delay=TYPE_DELAY)
            ta.press("Tab")
            pause(0.5)
            while qbox.locator(".editor-opt").count() < len(answers):
                qbox.locator("button", has_text="+ Answer").click()
                pause(0.4)
            for i, text in enumerate(answers):
                inp = qbox.locator(".editor-opt").nth(i).locator("input[type='text']")
                inp.click()
                inp.fill("")
                inp.press_sequentially(text, delay=TYPE_DELAY)
                inp.press("Tab")
                pause(0.25)
            qbox.locator(".editor-opt").nth(correct_idx).locator("input[type='checkbox']").check()
            pause(0.6)
            mark("q1_done")
            a.screenshot(path=str(shots / "c-q1.png"))
            # Questions 2 and 3 through the API (same admin), then reopen the editor.
            quiz = next(q for q in admin_api.get("/api/quizzes").json() if q["title"] == QUIZ_TITLE)
            for q_text, answers, correct_idx in QUESTIONS[1:]:
                qq = admin_api.post(f"/api/quizzes/{quiz['id']}/questions", json={"text": q_text, "qtype": "single"}).json()
                for i, text in enumerate(answers):
                    ans = admin_api.post(f"/api/quiz_questions/{qq['id']}/answers", json={"text": text}).json()
                    if i == correct_idx:
                        admin_api.patch(f"/api/quiz_answers/{ans['id']}", json={"is_correct": True}).raise_for_status()
            a.reload()
            a.wait_for_selector("#quiz-rows tr:has-text('Onboarding check')")
            a.locator("#quiz-rows tr", has_text=QUIZ_TITLE).locator("td").first.click()
            a.wait_for_selector("#editor-body .editor-q >> nth=2")
            mark("q3_shown")
            pause(1.5)
            a.screenshot(path=str(shots / "c-q3.png"))
            row = a.locator("#quiz-rows tr", has_text=QUIZ_TITLE)
            row.scroll_into_view_if_needed()
            row.locator("button", has_text="Publish").click()
            a.wait_for_selector("#quiz-rows tr:has-text('Onboarding check') >> text=/Ready|ready/")
            mark("quiz_published")
            pause(1.0)
            row = a.locator("#quiz-rows tr", has_text=QUIZ_TITLE)
            row.locator("summary", has_text="Add to session").click()
            row.locator(".session-picker button", has_text=SESSION_TITLE).wait_for()
            pause(0.8)
            row.locator(".session-picker button", has_text=SESSION_TITLE).click()
            a.wait_for_selector(".toast, [class*=toast]", timeout=5000)
            mark("quiz_added")
            pause(1.5)
            a.screenshot(path=str(shots / "c-added.png"))

            # d. session page: start the session
            a.goto(f"{BASE}/m/{code}")
            a.wait_for_selector("#lifecycle-card:visible")
            mark("mod_page")
            pause(1.0)
            a.locator("#lifecycle-actions button", has_text="Start session").click()
            a.wait_for_selector("#session-status:has-text('ive')")
            mark("session_started")
            pause(1.0)
            a.screenshot(path=str(shots / "d-started.png"))

            # projector + phone contexts
            pctx = browser.new_context(**desktop)
            pr = pctx.new_page()
            videos["projector"] = {"start": now()}
            pr.goto(f"{BASE}/p/{code}")
            pr.wait_for_selector("#join-qr canvas, #join-qr img, #join-qr svg, #join-qr table", timeout=5000)
            mark("projector_shown")
            pause(0.5)
            pr.screenshot(path=str(shots / "d-projector.png"))

            phctx = browser.new_context(
                viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                record_video_dir=str(OUT), record_video_size={"width": 390, "height": 844},
            )
            ph = phctx.new_page()
            videos["phone"] = {"start": now()}
            ph.goto(f"{BASE}/")
            ph.wait_for_selector("#join-code")
            mark("phone_landing")
            pause(1.0)
            type_into(ph, "#join-code", code)
            pause(0.5)
            ph.tap("#join-btn")
            ph.wait_for_selector("#ask-card")
            ph.wait_for_function("document.querySelector('#title').textContent !== 'Loading…'")
            mark("phone_joined")
            pause(0.5)
            ph.screenshot(path=str(shots / "d-phone.png"))
            # Optional display name so the question carries a first name. Set
            # through the API with the phone's own voter cookie, so the profile
            # form (whose placeholders include an example email) stays closed.
            voter = next(c["value"] for c in phctx.cookies() if c["name"] == "voter_token")
            client().patch(f"/api/sessions/{code}/me", json={"name": PHONE_NAME},
                           cookies={"voter_token": voter}).raise_for_status()
            pause(0.3)

            # e. Q&A
            ph.locator("#ask-card").scroll_into_view_if_needed()
            mark("phone_ask_start")
            type_into(ph, "#query-text", PHONE_QUESTION)
            pause(0.4)
            ph.tap("#ask-btn")
            ph.wait_for_selector(f"#queries .question:has-text('{PHONE_QUESTION[:20]}')")
            mark("phone_asked")
            pause(1.0)
            others: list[tuple[str, httpx.Client]] = []
            qids: list[int] = []
            for name, text in OTHERS:
                c = client()
                c.patch(f"/api/sessions/{code}/me", json={"name": name})
                r = c.post(f"/api/sessions/{code}/queries", json={"text": text})
                r.raise_for_status()
                qids.append(r.json()["id"])
                others.append((name, c))
                pause(0.7)
            mark("others_asked")
            queries = admin_api.get(f"/api/sessions/{code}/queries").json()
            phone_qid = next(q["id"] for q in queries if q["text"] == PHONE_QUESTION)
            # Everyone upvotes the phone's question; some upvote the first other question.
            for i, (_, c) in enumerate(others):
                c.post(f"/api/sessions/{code}/queries/{phone_qid}/vote")
                pause(0.6)
                if i < 2:
                    c.post(f"/api/sessions/{code}/queries/{qids[0]}/vote")
                    pause(0.4)
            mark("votes_done")
            pause(1.5)
            pr.screenshot(path=str(shots / "e-projector.png"))
            ph.screenshot(path=str(shots / "e-phone.png"))
            # Moderator marks the top question as responded.
            a.locator("#queries-card").scroll_into_view_if_needed()
            top = a.locator("#queries .question", has_text=PHONE_QUESTION)
            top.wait_for()
            mark("mod_queries")
            pause(0.8)
            resp = top.locator("textarea.response-input")
            resp.click()
            resp.press_sequentially("Yes, the slides go out by email tomorrow.", delay=40)
            pause(0.4)
            top.locator("button", has_text="Mark responded").click()
            a.wait_for_selector("#queries .question.answered")
            mark("responded")
            pause(1.5)
            a.screenshot(path=str(shots / "e-responded.png"))
            ph.screenshot(path=str(shots / "e-phone-responded.png"))
            pr.screenshot(path=str(shots / "e-projector-responded.png"))

            # f. quiz run
            a.locator("#quizzes-card").scroll_into_view_if_needed()
            mark("mod_quiz_card")
            pause(0.8)
            a.locator("#quiz-runs button", has_text="Start").first.click()
            a.wait_for_selector("#quiz-runs button:has-text('Reveal results')")
            mark("quiz_started")
            runs = admin_api.get(f"/api/sessions/{code}/quiz_runs").json()
            run = next(r for r in runs if r["status"] == "live")
            run_id = run["id"]
            qid1 = run["current_question"]["id"]
            ans = run["current_question"]["answers"]
            ph.wait_for_selector("#quiz-card:visible .option")
            pause(1.2)
            ph.locator("#quiz-card").scroll_into_view_if_needed()
            pr.screenshot(path=str(shots / "f-projector-q.png"))
            ph.screenshot(path=str(shots / "f-phone-q.png"))
            # Phone answers (second option).
            ph.locator("#quiz-card .option").nth(1).tap()
            pause(0.8)
            ph.locator("#quiz-card button", has_text="Submit answer").tap()
            ph.wait_for_selector("#quiz-card :text('Your answer is recorded')")
            mark("phone_answered")
            pause(0.6)
            # Moderator turns on live counts (answers masked on the projector).
            a.locator("#quiz-runs details.menu summary").first.click()
            pause(0.5)
            a.locator("#quiz-runs button", has_text="Show vote counts to audience").click()
            a.wait_for_selector("#quiz-runs button:has-text('Hide vote counts')", state="attached")
            a.keyboard.press("Escape")
            mark("counts_on")
            # Others answer, spread out so the projector bars move.
            picks = [1, 1, 0, 2]
            for (_, c), pick in zip(others, picks):
                c.post(f"/api/sessions/{code}/quiz_runs/{run_id}/submit",
                       json={"question_id": qid1, "answer_ids": [ans[pick]["id"]]}).raise_for_status()
                pause(0.9)
            mark("others_answered")
            pause(1.5)
            pr.screenshot(path=str(shots / "f-projector-counts.png"))
            a.screenshot(path=str(shots / "f-mod-counts.png"))
            # Reveal.
            a.locator("#quiz-runs button", has_text="Reveal results").click()
            a.wait_for_selector("#quiz-runs :text('voting closed')")
            mark("revealed")
            pause(3.0)
            pr.screenshot(path=str(shots / "f-projector-reveal.png"))
            ph.screenshot(path=str(shots / "f-phone-reveal.png"))
            a.screenshot(path=str(shots / "f-mod-reveal.png"))
            mark("end")
            pause(0.5)
            for name, page, ctx in (("admin", a, actx), ("projector", pr, pctx), ("phone", ph, phctx)):
                page.close()
                ctx.close()
                assert page.video is not None  # recording is on for every context
                videos[name]["path"] = str(page.video.path())
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
    (W / "timeline.json").write_text(json.dumps({"videos": videos, "marks": marks, "code": code}, indent=2))
    print("wrote timeline.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
