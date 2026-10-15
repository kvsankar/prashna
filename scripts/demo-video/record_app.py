#!/usr/bin/env python3
"""Record the Prashna demo scenes against a fresh Prashna 0.6.0.

Starts the `prashna` installed by run_install.sh (clean HOME) on
127.0.0.1:8000 with an empty data folder. It starts no tunnel. Instead it
gives Prashna, as its public address, the address that an earlier
`prashna --tunnel cloudflare` run printed (the "Participants join at:" line
of terminal-text.txt, a https://<random words>.trycloudflare.com name that no
longer works). Prashna then shows that address as it does with a tunnel: in
the session's join link, the invite card and the projector's QR code. All
pages open Prashna at 127.0.0.1. Then it drives the real pages headless with
Playwright:

  admin      1920x1080, page zoom 2    the presenter's laptop (lays out as 960x540)
  projector  1920x1080, page zoom 4/3  /p/<code> on the projector (as 1440x810)
  phone      720x1560, page zoom 2     Diego, the featured participant (as 360x780)
  phone2, phone3                       two more phones, for the opening

Each page is recorded with the Chrome DevTools screencast: Chromium sends a
lossless PNG frame each time the page changes, with the time it was drawn.
The frames go to recordings/frames/<name>/; after the run each recording is
turned into a constant 30 fps lossless video (recordings/<name>.mkv, H.264
RGB with -qp 0), each frame held until the next one was drawn. A frame is
the page's viewport in CSS pixels, so the pages are opened at the full
recording size and zoomed (CSS zoom on the body, as browser zoom does). The
text is larger in the frame and stays sharp. The phones' media queries see a
720 px wide screen, which selects the same phone layout as 360 px. Before
each click or tap an injected demo overlay draws a ring around the control (and a dot where it is
pressed), so viewers can see what is used. The overlay belongs to the
recording only; it is not part of Prashna.

Twenty-four more participants are simulated with httpx clients (own voter
cookie each) so the counts move. Every key moment is written to timeline.json
as a wall-clock mark, with each recording's start time, the on-screen box of
the controls that compose.py zooms to, and the public address.

Run:  uv run --project tooling python record_app.py [--encode-only]
      (--encode-only makes the videos again from the last run's frames)
"""
from __future__ import annotations

import base64
import bisect
import json
import random
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from contextlib import ExitStack
from pathlib import Path

import httpx
from playwright.sync_api import (
    BrowserContext,
    FloatRect,
    Locator,
    Page,
    ViewportSize,
    sync_playwright,
)
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as ws_connect

W = Path(__file__).resolve().parent
CLEAN = W / "clean-home"
OUT = W / "recordings"
FPS = 30
# The tool environment that run_install.sh's `uv tool install` created.
PRASHNA_PYTHON = CLEAN / ".local/share/uv/tools/prashna/bin/python"
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
RESPONSE = "Yes. I'll email them to everyone tonight."
# Asked anonymously by simulated participants, in this order.
OTHER_QUESTIONS = [
    "Is there a recording of this session?",
    "Which tool do we use for time sheets?",
    "How do I get access to the staging server?",
    "Is the handbook available offline?",
    "Where do I find the holiday calendar?",
]
SIMULATED = 24
TYPE_DELAY = 55  # ms per character for visible typing
ADMIN_VIEW: ViewportSize = {"width": 1920, "height": 1080}
ADMIN_ZOOM = 2
PROJ_VIEW: ViewportSize = {"width": 1920, "height": 1080}
PROJ_ZOOM = 4 / 3
PHONE_VIEW: ViewportSize = {"width": 720, "height": 1560}
PHONE_ZOOM = 2

T0 = time.monotonic()
# The wall clock at T0: screencast frames carry wall-clock timestamps.
EPOCH0 = time.time()
marks: dict[str, float] = {}
boxes: dict[str, list[float]] = {}
videos: dict[str, dict[str, object]] = {}

# The demo overlay: a ring around the control about to be used, and a dot
# where it is pressed. Injected into the recorded pages only. It sits outside
# the zoomed body, so its coordinates are screen pixels.
OVERLAY = """
window.__demo = {
  ring(x, y, w, h) {
    let r = document.getElementById('__demo_ring');
    if (!r) { r = document.createElement('div'); r.id = '__demo_ring'; document.documentElement.appendChild(r); }
    Object.assign(r.style, { position: 'fixed', left: (x - 6) + 'px', top: (y - 6) + 'px',
      width: (w + 12) + 'px', height: (h + 12) + 'px', boxSizing: 'border-box',
      border: '3px solid #fbbf24', borderRadius: '10px',
      boxShadow: '0 0 0 4px rgba(251,191,36,0.30), 0 0 22px rgba(251,191,36,0.55)',
      zIndex: 2147483647, pointerEvents: 'none' });
  },
  dot(x, y) {
    let d = document.getElementById('__demo_dot');
    if (!d) { d = document.createElement('div'); d.id = '__demo_dot'; document.documentElement.appendChild(d); }
    Object.assign(d.style, { position: 'fixed', left: (x - 14) + 'px', top: (y - 14) + 'px', width: '28px',
      height: '28px', borderRadius: '50%', background: 'rgba(251,191,36,0.75)',
      boxShadow: '0 0 0 6px rgba(251,191,36,0.25)', zIndex: 2147483647, pointerEvents: 'none' });
  },
  clear() {
    for (const id of ['__demo_ring', '__demo_dot']) { const e = document.getElementById(id); if (e) e.remove(); }
  },
};
"""


def now() -> float:
    return round(time.monotonic() - T0, 3)


def mark(name: str) -> None:
    marks[name] = now()
    print(f"  [{marks[name]:7.2f}] {name}", flush=True)


def pause(sec: float) -> None:
    time.sleep(sec)


class Recorder:
    """Lossless frames of one page from the DevTools screencast, with their times.

    A thread of its own holds a DevTools connection to the page (Chromium is
    started with a debugging port) and acknowledges each frame as soon as it
    arrives, so the screencast keeps its pace while the main thread drives
    the pages or sleeps. Each frame's file name, its draw time and its
    arrival time (seconds since T0) go to frames/<name>/times.tsv.
    """

    def __init__(self, name: str, ctx: BrowserContext, page: Page, port: int) -> None:
        self.name = name
        self.dir = OUT / "frames" / name
        self.dir.mkdir(parents=True)
        view = page.viewport_size
        assert view is not None
        self.size = (view["width"], view["height"])
        target = ctx.new_cdp_session(page).send("Target.getTargetInfo")["targetInfo"]["targetId"]
        self.stack = ExitStack()  # websockets wants its connection used as a context manager
        self.ws = self.stack.enter_context(ws_connect(f"ws://127.0.0.1:{port}/devtools/page/{target}",
                                                      max_size=None, proxy=None, compression=None))
        self.ws.send(json.dumps({"id": 1, "method": "Page.startScreencast", "params": {
            "format": "png", "everyNthFrame": 1, "maxWidth": self.size[0], "maxHeight": self.size[1]}}))
        self.times = open(self.dir / "times.tsv", "w")
        self.count = 0
        self.thread = threading.Thread(target=self._run, name=f"screencast-{name}", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        next_id = 2
        try:
            for message in self.ws:
                msg = json.loads(message)
                if msg.get("method") != "Page.screencastFrame":
                    continue
                arrived = now()
                params = msg["params"]
                self.ws.send(json.dumps({"id": next_id, "method": "Page.screencastFrameAck",
                                         "params": {"sessionId": params["sessionId"]}}))
                next_id += 1
                stamp = params["metadata"].get("timestamp")
                drawn = round(stamp - EPOCH0, 4) if stamp else arrived
                name = f"{self.count:06d}.png"
                (self.dir / name).write_bytes(base64.b64decode(params["data"]))
                self.times.write(f"{name}\t{drawn}\t{arrived}\n")
                self.count += 1
        except ConnectionClosed:
            pass

    def stop(self) -> float:
        """Stop the screencast; return the time the recording ends."""
        end = now()
        try:
            self.ws.send(json.dumps({"id": 0, "method": "Page.stopScreencast"}))
        finally:
            self.stack.close()
            self.thread.join(timeout=10)
            self.times.close()
        return end


def encode(name: str, end: float, size: list[int]) -> dict[str, object]:
    """A constant 30 fps lossless video of one recording: each frame held until the next one's time."""
    folder = OUT / "frames" / name
    rows = [line.split("\t") for line in (folder / "times.tsv").read_text().splitlines()]
    files = [r[0] for r in rows]
    # Draw times, made non-decreasing in arrival order (a frame never shows before the one before it).
    times: list[float] = []
    fixed = 0
    for _, drawn, _ in rows:
        t = float(drawn)
        if times and t < times[-1]:
            t, fixed = times[-1], fixed + 1
        times.append(t)
    start = times[0]
    count = int((end - start) * FPS)
    picks = [bisect.bisect_right(times, start + k / FPS) - 1 for k in range(count)]
    entries: list[tuple[str, int]] = []  # (file, frames held)
    for i in picks:
        if entries and entries[-1][0] == files[i]:
            entries[-1] = (files[i], entries[-1][1] + 1)
        else:
            entries.append((files[i], 1))
    lst = folder / "list.txt"
    lst.write_text("ffconcat version 1.0\n" + "".join(
        f"file '{f}'\nduration {n / FPS:.6f}\n" for f, n in entries) + f"file '{entries[-1][0]}'\n")
    out = OUT / f"{name}.mkv"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", f"fps={FPS},format=bgr24", "-frames:v", str(count),
                    "-c:v", "libx264rgb", "-qp", "0", "-preset", "veryfast", "-g", str(FPS), str(out)],
                   check=True)
    gaps = [b - a for a, b in zip(times, times[1:])]
    busy = sum(1 for g in gaps if g < 1.5 / FPS)
    print(f"  {name}: {len(times)} frames over {end - start:.1f} s, {len(entries)} distinct frames in the"
          f" 30 fps video; {busy} frame gaps under 50 ms; {fixed} draw times reordered", flush=True)
    return {"start": start, "end": end, "path": str(out), "size": size, "frames": len(times),
            "distinct_frames": len(entries)}


def zoom_script(zoom: float) -> str:
    """Init script: zoom the page body before it is first drawn."""
    return (f"(() => {{ const add = () => {{ const s = document.createElement('style');"
            f" s.textContent = 'body {{ zoom: {zoom:.6f}; }}';"
            f" (document.head || document.documentElement).appendChild(s); }};"
            f" if (document.documentElement) add(); else document.addEventListener('readystatechange', add, {{ once: true }}); }})();")


def box(name: str, page: Page, *locs: Locator) -> None:
    """Remember the union of the locators' boxes, in video pixels, for compose.py's zoom."""
    rects = [b for b in (loc.bounding_box() for loc in locs) if b]
    x0 = min(r["x"] for r in rects)
    y0 = min(r["y"] for r in rects)
    x1 = max(r["x"] + r["width"] for r in rects)
    y1 = max(r["y"] + r["height"] for r in rects)
    vw, vh = page.viewport_size["width"], page.viewport_size["height"]  # type: ignore[index]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(vw, x1), min(vh, y1)
    boxes[name] = [round(v, 1) for v in (x0, y0, x1 - x0, y1 - y0)]


def ring(page: Page, loc: Locator) -> FloatRect:
    loc.scroll_into_view_if_needed()
    b = loc.bounding_box()
    assert b is not None
    page.evaluate("b => window.__demo.ring(b.x, b.y, b.width, b.height)", b)
    return b


def press(page: Page, loc: Locator, hold: float = 0.6, tap: bool = False) -> None:
    """Ring the control, wait, show the press dot, then click (or tap) it."""
    b = ring(page, loc)
    pause(hold)
    page.evaluate("b => window.__demo.dot(b.x + b.width / 2, b.y + b.height / 2)", b)
    pause(0.15)
    if tap:
        loc.tap()
    else:
        loc.click()
    # Clear at once: the page may put another control where this one was.
    page.evaluate("() => window.__demo.clear()")
    pause(0.3)


def type_into(page: Page, loc: Locator, text: str, delay: int = TYPE_DELAY, replace: bool = False) -> None:
    """Ring the field while typing into it, as a viewer's eye would follow it."""
    ring(page, loc)
    loc.click()
    if replace:
        loc.press("Control+A")
    loc.press_sequentially(text, delay=delay)
    pause(0.2)
    page.evaluate("() => window.__demo.clear()")


def wait_port_free(seconds: float = 120) -> None:
    """Connections of an earlier run linger in TIME-WAIT for up to a minute."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", PORT))
                return
            except OSError:
                time.sleep(2)
    raise SystemExit(f"port {PORT} stays in use")


def captured_address() -> str:
    """The public address printed by the earlier tunnel run (terminal-text.txt)."""
    found = re.search(r"^Participants join at: (https://[a-z0-9-]+\.trycloudflare\.com)$",
                      (W / "terminal-text.txt").read_text(), re.M)
    if not found:
        raise SystemExit("terminal-text.txt has no 'Participants join at:' trycloudflare.com address")
    return found.group(1)


# Runs the installed Prashna's command line as `prashna` does, and sets the
# public address that a tunnel would have set, just before the server starts.
LAUNCH = """
import os, sys, uvicorn
_run = uvicorn.run
def run(*args, **kwargs):
    from prashna import main as server
    server.PUBLIC_URL = os.environ["DEMO_PUBLIC_URL"]
    print("Participants join at: " + server.PUBLIC_URL, flush=True)
    return _run(*args, **kwargs)
uvicorn.run = run
from prashna.cli import main
sys.exit(main())
"""


def start_server() -> tuple[subprocess.Popen, str]:
    public = captured_address()
    wait_port_free()
    data = W / "demo-data"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir()
    (CLEAN / "tmp").mkdir(exist_ok=True)
    env = {
        "HOME": str(CLEAN),
        # cloudflared is found on the normal system PATH.
        "PATH": f"{CLEAN}/.local/bin:/usr/local/bin:/usr/bin:/bin",
        "TMPDIR": str(CLEAN / "tmp"),
        "PRASHNA_SETUP_TOKEN": SETUP_TOKEN,
        "PRASHNA_RATELIMIT": "off",
        "DEMO_PUBLIC_URL": public,
    }
    # Not server-output.raw.txt: that is the earlier tunnel run's output.
    log_path = W / "server-output.recording.raw.txt"
    log = open(log_path, "w")
    proc = subprocess.Popen(
        [str(PRASHNA_PYTHON), "-c", LAUNCH, "--no-browser", "--data-dir", str(data), "--port", str(PORT)],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 120
    while time.time() < deadline:
        text = log_path.read_text()
        if "Press Ctrl+C" in text:
            break
        if proc.poll() is not None:
            raise SystemExit("prashna exited:\n" + text)
        time.sleep(0.5)
    else:
        proc.terminate()
        raise SystemExit("prashna did not start")
    for _ in range(100):
        try:
            if httpx.get(f"{BASE}/api/admin/status", timeout=1.0, trust_env=False).status_code == 200:
                return proc, public
        except Exception:
            pass
        time.sleep(0.2)
    proc.terminate()
    raise SystemExit("prashna did not answer on 127.0.0.1")


def client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=10.0, trust_env=False)


def wait_text(page: Page, selector: str, text: str, timeout: float = 15000) -> None:
    page.wait_for_function(
        "([s, t]) => [...document.querySelectorAll(s)].some(e => e.textContent.includes(t))",
        arg=[selector, text], timeout=timeout)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> int:
    if "--encode-only" in sys.argv[1:]:
        encode_all()  # again, from the frames of the last run
        return 0
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    shots = W / "shots"
    shutil.rmtree(shots, ignore_errors=True)
    shots.mkdir()
    server, public = start_server()
    print("server up; public address shown", public)
    recorders: dict[str, Recorder] = {}
    rng = random.Random(7)
    code = ""
    try:
        with sync_playwright() as p:
            devtools = free_port()
            browser = p.chromium.launch(headless=True, args=["--no-proxy-server",
                                                             f"--remote-debugging-port={devtools}"])

            def desktop(view: ViewportSize, zoom: float):  # noqa: ANN202
                ctx = browser.new_context(viewport=view)
                ctx.add_init_script(zoom_script(zoom))
                return ctx

            def phone_ctx():  # noqa: ANN202
                ctx = browser.new_context(viewport=PHONE_VIEW, is_mobile=True, has_touch=True)
                ctx.add_init_script(zoom_script(PHONE_ZOOM))
                ctx.add_init_script(OVERLAY)
                return ctx

            # ---------------- the presenter's laptop ----------------
            actx = desktop(ADMIN_VIEW, ADMIN_ZOOM)
            actx.add_init_script(OVERLAY)
            a = actx.new_page()
            recorders["admin"] = Recorder("admin", actx, a, devtools)
            # First-run account (not shown in the video).
            a.goto(f"{BASE}/#setup={SETUP_TOKEN}")
            a.wait_for_selector("#setup-card:visible")
            a.fill("#su-user", ADMIN["username"])
            a.fill("#su-pass", ADMIN["password"])
            a.fill("#su-pass2", ADMIN["password"])
            a.click("#su-btn")
            a.wait_for_selector("#sessions-card:visible")
            pause(1.0)
            # Create a session.
            mark("sess_start")
            box("sess", a, a.locator("#sessions-card"))
            type_into(a, a.locator("#new-session-title"), SESSION_TITLE)
            press(a, a.locator("#new-session-btn"))
            a.wait_for_selector(f"#session-rows tr:has-text('{SESSION_TITLE}')")
            pause(1.2)
            box("sess", a, a.locator("#sessions-card"))
            mark("sess_done")
            a.screenshot(path=str(shots / "a-session.png"))
            admin_api = client()
            admin_api.post("/api/admin/login", json=ADMIN).raise_for_status()
            code = next(s["code"] for s in admin_api.get("/api/sessions").json() if s["title"] == SESSION_TITLE)
            print("session code", code)

            # Write the quiz: question 1 in the editor.
            a.goto(f"{BASE}/quizzes")
            a.wait_for_selector("#quiz-rows")
            a.fill("#new-quiz-title", QUIZ_TITLE)
            a.click("#create-quiz")
            a.wait_for_selector("#editor-card:visible")
            a.click("#editor-insert-end")
            a.wait_for_selector("#editor-questions .editor-q")
            qbox = a.locator("#editor-questions .editor-q").first
            # Exactly three empty answers and an empty question text before filming.
            while qbox.locator(".editor-opt").count() < 3:
                n = qbox.locator(".editor-opt").count()
                qbox.locator("button.add-answer").click()
                a.wait_for_function("n => document.querySelectorAll('#editor-questions .editor-q .editor-opt').length > n", arg=n)
            assert qbox.locator(".editor-opt").count() == 3, "the editor shows more than three answers"
            for i in range(3):
                qbox.locator(".editor-opt").nth(i).locator("input[type='text']").fill("")
            qbox.scroll_into_view_if_needed()
            a.evaluate("() => window.scrollBy(0, -120)")
            pause(0.8)
            mark("quiz_start")
            q_text, answers, correct_idx = QUESTIONS[0]
            type_into(a, qbox.locator("textarea").first, q_text, delay=45, replace=True)
            for i, text in enumerate(answers):
                type_into(a, qbox.locator(".editor-opt").nth(i).locator("input[type='text']"), text, delay=40)
            press(a, qbox.locator(".editor-opt").nth(correct_idx).locator("input[type='checkbox']"))
            pause(1.0)
            box("quiz", a, qbox)
            mark("quiz_done")
            a.screenshot(path=str(shots / "b-quiz.png"))
            # Questions 2 and 3 through the API (same admin), each with its correct answer.
            quiz = next(q for q in admin_api.get("/api/quizzes").json() if q["title"] == QUIZ_TITLE)
            for q_text, answers, correct_idx in QUESTIONS[1:]:
                qq = admin_api.post(f"/api/quizzes/{quiz['id']}/questions", json={"text": q_text, "qtype": "single"}).json()
                for i, text in enumerate(answers):
                    ans = admin_api.post(f"/api/quiz_questions/{qq['id']}/answers", json={"text": text}).json()
                    if i == correct_idx:
                        admin_api.patch(f"/api/quiz_answers/{ans['id']}", json={"is_correct": True}).raise_for_status()

            # Session page: start the session, then open the invite card.
            a.goto(f"{BASE}/m/{code}")
            a.wait_for_selector("#lifecycle-card:visible")
            pause(1.0)
            mark("start_start")
            box("start", a, a.locator("#lifecycle-card"))
            press(a, a.locator("#lifecycle-actions button", has_text="Start session"))
            a.wait_for_selector("#session-status.badge-live")
            pause(1.2)
            box("start", a, a.locator("#lifecycle-card"))
            mark("start_done")
            a.screenshot(path=str(shots / "c-started.png"))
            setup = a.locator("#setup-section > summary")
            was_open = a.evaluate("() => document.querySelector('#setup-section').open")
            if not was_open:
                setup.click()
            invite = a.locator("#invite-card")
            invite.wait_for(state="visible")
            invite.scroll_into_view_if_needed()
            wait_text(a, "body", public.removeprefix("https://"))
            pause(0.6)
            mark("invite_start")
            box("invite", a, invite)
            pause(2.5)
            mark("invite_done")
            a.screenshot(path=str(shots / "d-invite.png"))
            # Collapse it again so the page looks as it did.
            if not was_open:
                setup.click()
            pause(0.3)

            # ---------------- projector and phones ----------------
            pctx = desktop(PROJ_VIEW, PROJ_ZOOM)
            pr = pctx.new_page()
            recorders["projector"] = Recorder("projector", pctx, pr, devtools)
            pr.goto(f"{BASE}/p/{code}")
            pr.wait_for_selector("#join-qr canvas, #join-qr img, #join-qr svg, #join-qr table", timeout=10000)
            wait_text(pr, "#origin", "trycloudflare.com")
            mark("projector_shown")
            pr.screenshot(path=str(shots / "e-projector.png"))
            # The phones open Prashna at 127.0.0.1; the join link, the QR codes
            # and the phone frame's address bar show the public address.
            join_url = f"{BASE}/s/{code}"
            phones: list[tuple[str, Page, object]] = []
            for name in ("phone", "phone2", "phone3"):
                ctx = phone_ctx()
                page = ctx.new_page()
                recorders[name] = Recorder(name, ctx, page, devtools)
                # A dark page until the phone opens the join link (no white flash).
                page.set_content("<html style='background:#0f172a'><body></body></html>")
                phones.append((name, page, ctx))
            ph, ph2, ph3 = (pg for _, pg, _ in phones)
            pause(1.5)
            mark("join_start")
            for _, page, _ in phones:
                page.goto(join_url)
                pause(0.7)
            for _, page, _ in phones:
                page.wait_for_selector("#ask-card")
                page.wait_for_function("document.querySelector('#title').textContent !== 'Loading…'")
            # The simulated participants open the page too.
            others = [client() for _ in range(SIMULATED)]
            for c in others:
                c.get(f"/api/sessions/{code}/participant-bootstrap")
            pause(1.5)
            mark("join_done")
            ph.screenshot(path=str(shots / "e-phone.png"))

            # ---------------- questions ----------------
            mark("ask_start")
            type_into(ph, ph.locator("#query-text"), PHONE_QUESTION)
            press(ph, ph.locator("#ask-show-name"), hold=0.5, tap=True)
            ph.wait_for_selector("#ask-name:visible")
            type_into(ph, ph.locator("#ask-name"), PHONE_NAME)
            press(ph, ph.locator("#ask-btn"), hold=0.5, tap=True)
            wait_text(ph, "#queries .question", PHONE_QUESTION[:20])
            wait_text(pr, "#queries .question", PHONE_QUESTION[:20])
            pause(0.8)
            qids: list[int] = []
            for i, text in enumerate(OTHER_QUESTIONS):
                r = others[i].post(f"/api/sessions/{code}/queries", json={"text": text})
                r.raise_for_status()
                qids.append(r.json()["id"])
                pause(0.6)
            for page in (pr, ph):
                wait_text(page, "#queries .question", OTHER_QUESTIONS[-1][:20])
            for page in (ph, ph2, ph3):
                page.locator("#queries").scroll_into_view_if_needed()
            pause(1.0)
            mark("ask_done")
            pr.screenshot(path=str(shots / "f-projector-asked.png"))
            ph.screenshot(path=str(shots / "f-phone-asked.png"))

            # ---------------- upvotes ----------------
            queries = admin_api.get(f"/api/sessions/{code}/queries").json()
            diego = next(q["id"] for q in queries if q["text"] == PHONE_QUESTION)
            rec, sheets, staging = qids[0], qids[1], qids[2]
            # First the recording question leads, then Diego's question climbs past it.
            votes = [(c, rec) for c in others[:6]] + [(c, sheets) for c in others[6:9]]
            rng.shuffle(votes)
            later = [(c, diego) for c in others[4:22]] + [(c, rec) for c in others[12:14]] + [(c, staging) for c in others[20:22]]
            rng.shuffle(later)
            mark("vote_start")
            for c, qid in votes:
                c.post(f"/api/sessions/{code}/queries/{qid}/vote").raise_for_status()
                pause(0.25)
            pause(1.0)
            for k, (c, qid) in enumerate(later):
                c.post(f"/api/sessions/{code}/queries/{qid}/vote").raise_for_status()
                pause(0.28)
                if k == 6:
                    # Two of the visible phones upvote Diego's question.
                    for page in (ph2, ph3):
                        btn = page.locator("#queries .question", has_text=PHONE_QUESTION[:20]).locator("button.vote-btn")
                        press(page, btn, hold=0.35, tap=True)
            expected = len([v for v in later if v[1] == diego]) + 2
            for page in (pr, ph):
                page.wait_for_function(
                    "([t, n]) => { const q = [...document.querySelectorAll('#queries .question')][0];"
                    " return q && q.textContent.includes(t) && q.textContent.includes(String(n)); }",
                    arg=[PHONE_QUESTION[:20], expected], timeout=15000)
            pause(1.5)
            mark("vote_done")
            print("top question votes", expected)
            pr.screenshot(path=str(shots / "g-projector-votes.png"))
            ph.screenshot(path=str(shots / "g-phone-votes.png"))

            # ---------------- the presenter answers the top question ----------------
            top = a.locator("#queries .question", has_text=PHONE_QUESTION)
            top.scroll_into_view_if_needed()
            a.evaluate("() => window.scrollBy(0, -80)")
            pause(0.6)
            mark("answer_start")
            box("answer", a, top)
            type_into(a, top.locator("textarea.response-input"), RESPONSE, delay=40)
            press(a, top.locator("button", has_text="Mark responded"))
            a.wait_for_selector("#queries .question.answered")
            wait_text(ph, "#queries .question.answered", RESPONSE[:15])
            pr.wait_for_function(
                "t => ![...document.querySelectorAll('#queries .question')].some(e => e.textContent.includes(t))",
                arg=PHONE_QUESTION[:20], timeout=15000)
            mark("answer_clicked")
            pause(0.4)
            ans_loc = ph.locator("#queries .question.answered")
            ans_loc.scroll_into_view_if_needed()
            ph.evaluate("() => window.scrollBy(0, 240)")
            pause(2.2)
            mark("answer_done")
            a.screenshot(path=str(shots / "h-answer.png"))
            ph.screenshot(path=str(shots / "h-phone-answer.png"))
            pr.screenshot(path=str(shots / "h-projector-answer.png"))

            # ---------------- quiz ----------------
            card = a.locator("#quizzes-card")
            card.scroll_into_view_if_needed()
            pause(0.5)
            mark("quiz_add_start")
            box("quizcard", a, card)
            sel = a.locator("#quiz-select")
            ring(a, sel)
            pause(0.4)
            value = a.evaluate(
                "t => [...document.querySelectorAll('#quiz-select option')].find(o => o.textContent.startsWith(t)).value",
                QUIZ_TITLE)
            sel.select_option(value=value)
            pause(0.4)
            press(a, a.locator("#add-quiz-btn"))
            a.wait_for_selector("#quiz-runs button:has-text('Start')")
            pause(0.8)
            mark("quiz_add_done")
            runs = admin_api.get(f"/api/sessions/{code}/quiz_runs").json()
            run_id = next(r["id"] for r in runs if r["status"] == "queued")
            # Live counts on before the start (allowed while queued); not shown.
            admin_api.post(f"/api/sessions/{code}/quiz_runs/{run_id}/live_counts", json={"show": True}).raise_for_status()
            pause(1.0)
            box("quizcard", a, card)
            mark("quiz_go")
            press(a, a.locator("#quiz-runs button", has_text="Start").first)
            a.wait_for_selector("#quiz-runs button:has-text('Reveal results')")
            mark("quiz_started")
            run = admin_api.get(f"/api/sessions/{code}/quiz_runs/{run_id}").json()
            qid1 = run["current_question"]["id"]
            ans = run["current_question"]["answers"]
            for page in (ph, ph2, ph3):
                page.wait_for_selector("#quiz-card:visible .option", timeout=15000)
                page.locator("#quiz-card").scroll_into_view_if_needed()
            pr.wait_for_selector("#quiz-body .option")
            pause(1.4)
            box("quizcard", a, card)
            mark("quiz_shown")
            pr.screenshot(path=str(shots / "i-projector-quiz.png"))
            ph.screenshot(path=str(shots / "i-phone-quiz.png"))

            # Answers: Diego (correct), the other two phones, then the simulated room.
            mark("votes_start")
            press(ph, ph.locator("#quiz-card .option").nth(1), hold=0.4, tap=True)
            press(ph, ph.locator("#quiz-card button", has_text="Submit answer"), hold=0.4, tap=True)
            ph.wait_for_selector("#quiz-card :text('Your answer is recorded')")
            for page, pick in ((ph2, 1), (ph3, 0)):
                page.locator("#quiz-card .option").nth(pick).tap()
                page.locator("#quiz-card button", has_text="Submit answer").tap()
            picks = [1] * 13 + [0] * 7 + [2] * 4
            rng.shuffle(picks)
            for c, pick in zip(others, picks):
                c.post(f"/api/sessions/{code}/quiz_runs/{run_id}/submit",
                       json={"question_id": qid1, "answer_ids": [ans[pick]["id"]]}).raise_for_status()
                pause(0.22)
            total = SIMULATED + 3
            wait_text(pr, "#quiz-body", f"{total} respondent", timeout=20000)
            wait_text(ph, "#quiz-card", f"{total} answered", timeout=20000)
            pause(1.6)
            mark("votes_done")
            pr.screenshot(path=str(shots / "j-projector-counts.png"))
            ph.screenshot(path=str(shots / "j-phone-counts.png"))

            # Reveal.
            box("reveal", a, a.locator("#quiz-runs .quiz-run, #quiz-runs > *").first)
            mark("reveal_start")
            press(a, a.locator("#quiz-runs button", has_text="Reveal results"))
            a.wait_for_selector("#quiz-runs :text('voting closed')")
            wait_text(pr, "#quiz-body", QUESTIONS[0][1][1])
            pr.wait_for_selector("#quiz-body .opt-correct, #quiz-body :text('Correct')")
            ph.wait_for_selector("#quiz-card :text('Correct')")
            mark("revealed")
            pause(3.5)
            mark("end")
            pr.screenshot(path=str(shots / "k-projector-reveal.png"))
            ph.screenshot(path=str(shots / "k-phone-reveal.png"))
            a.screenshot(path=str(shots / "k-admin-reveal.png"))
            pause(0.3)
            ends = {name: rec.stop() for name, rec in recorders.items()}
            for page, ctx in ((a, actx), (pr, pctx), *((pg, c) for _, pg, c in phones)):
                page.close()
                ctx.close()  # type: ignore[attr-defined]
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    for name, rec in recorders.items():
        videos[name] = {"end": ends[name], "size": list(rec.size)}
    write_timeline(code, public)
    encode_all()
    return 0


def write_timeline(code: str, public: str) -> None:
    (W / "timeline.json").write_text(json.dumps(
        {"videos": videos, "marks": marks, "boxes": boxes, "code": code, "public_url": public}, indent=2))


def encode_all() -> None:
    """Turn the frames into recordings/<name>.mkv and add each one's start and path to timeline.json."""
    tl = json.loads((W / "timeline.json").read_text())
    for name, v in tl["videos"].items():
        tl["videos"][name] = encode(name, v["end"], v["size"])
    (W / "timeline.json").write_text(json.dumps(tl, indent=2))
    print("wrote timeline.json")


if __name__ == "__main__":
    sys.exit(main())
