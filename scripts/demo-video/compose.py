#!/usr/bin/env python3
"""Compose prashna-demo.mp4 from recordings/, cards/ and timeline.json.

Every scene becomes one segment in segments/ (1920x1080, 30 fps, H.264) with
its captions burned in by ffmpeg drawtext; the segments are then concatenated.
Composite scenes place the projector recording and the phone recording side by
side, cut from the same wall-clock span so they stay in sync.

Run:  python3 compose.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

W = Path(__file__).resolve().parent
SEG = W / "segments"
FONT = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
FPS = 30
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]
OUT = W / "prashna-demo.mp4"

tl = json.loads((W / "timeline.json").read_text())
V, M = tl["videos"], tl["marks"]
caption_no = 0
scene_log: list[tuple[str, float, list[str]]] = []  # (name, duration, captions)


def off(video: str, wall: float) -> float:
    """Offset into `video` for wall-clock time `wall` (seconds since T0)."""
    o = wall - V[video]["start"]
    if o < 0:
        raise ValueError(f"{video} starts after wall {wall}")
    return o


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def caption_filter(text: str, a: float, b: float) -> str:
    """drawtext filter: white box, dark text, bottom centre, visible from a to b (segment seconds)."""
    global caption_no
    caption_no += 1
    assert len(text.split()) <= 12, text
    path = SEG / "captions" / f"{caption_no:02d}.txt"
    path.write_text(text)
    return (
        f"drawtext=fontfile={FONT}:textfile={path}:fontsize=44:fontcolor=0x1f2328"
        f":box=1:boxcolor=white@0.95:boxborderw=24:x=(w-text_w)/2:y=h-text_h-64"
        f":enable='between(t\\,{a:.2f}\\,{b:.2f})'"
    )


def card(name: str, png: str, dur: float) -> Path:
    out = SEG / f"{name}.mp4"
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(W / "cards" / png), "-t", f"{dur:.2f}",
         "-vf", "format=yuv420p", *ENC, str(out)])
    scene_log.append((name, dur, []))
    return out


def clip(name: str, video: str, t_in: float, t_out: float, captions: list[tuple[str, float, float]],
         speed: float = 1.0) -> Path:
    """Cut `video` between offsets t_in..t_out (video seconds); captions are in output seconds."""
    out = SEG / f"{name}.mp4"
    src = V[video]["path"]
    filters = [f"setpts=PTS/{speed}", f"fps={FPS}", "scale=1920:1080"]
    filters += [caption_filter(*c) for c in captions]
    run(["ffmpeg", "-y", "-ss", f"{t_in:.3f}", "-t", f"{t_out - t_in:.3f}", "-i", src,
         "-vf", ",".join(filters), *ENC, str(out)])
    scene_log.append((name, (t_out - t_in) / speed, [c[0] for c in captions]))
    return out


def composite(name: str, w_in: float, w_out: float, captions: list[tuple[str, float, float]]) -> Path:
    """Projector (left) and phone (right) from the same wall-clock span; captions in local seconds."""
    out = SEG / f"{name}.mp4"
    dur = w_out - w_in
    caps = ",".join(caption_filter(*c) for c in captions)
    graph = (
        f"color=c=0xf6f7f9:s=1920x1080:r={FPS}:d={dur:.3f}[bg];"
        f"[0:v]fps={FPS},scale=1376:774[p];"
        f"[1:v]fps={FPS},scale=416:900,pad=428:912:6:6:0x2b3036[m];"
        f"[bg][p]overlay=32:90:shortest=1[a];[a][m]overlay=1456:36[b];"
        f"[b]{caps}[v]"
    )
    run(["ffmpeg", "-y",
         "-ss", f"{off('projector', w_in):.3f}", "-t", f"{dur:.3f}", "-i", V["projector"]["path"],
         "-ss", f"{off('phone', w_in):.3f}", "-t", f"{dur:.3f}", "-i", V["phone"]["path"],
         "-filter_complex", graph, "-map", "[v]", "-t", f"{dur:.3f}", *ENC, str(out)])
    scene_log.append((name, dur, [c[0] for c in captions]))
    return out


def main() -> None:
    shutil.rmtree(SEG, ignore_errors=True)
    (SEG / "captions").mkdir(parents=True)
    A = "admin"
    a = lambda mark: off(A, M[mark])  # noqa: E731
    segs: list[Path] = []

    segs.append(card("01-title", "title.png", 4.0))
    segs.append(card("02-why", "why.png", 8.0))

    t_dur = duration(Path(V["terminal"]["path"]))
    segs.append(clip("03-install", "terminal", 1.4, min(13.8, t_dur - 0.2),
                     [("One command installs Prashna. Then start it.", 0, 99)], speed=1.1))

    segs.append(clip("04-setup", A, 0.0, a("setup_done") + 0.9,
                     [("First run: create the admin account.", 0, 99)]))
    segs.append(clip("05-session", A, a("session_create_start") - 0.3, a("session_created") + 1.6,
                     [("Create a session for the workshop.", 0, 99)]))
    speed = 1.6
    segs.append(clip("06-quiz-write", A, a("library_page") - 0.3, a("q1_done") + 0.3,
                     [("Write a short quiz in the library.", 0, 99)], speed=speed))
    segs.append(clip("07-quiz-publish", A, a("q1_done") + 0.3, a("quiz_added") + 1.4,
                     [("Publish it and add it to the session.", 0, 99)]))
    segs.append(clip("08-start", A, a("mod_page") - 0.3, a("session_started") + 1.0,
                     [("Start the session.", 0, 99)]))

    w0 = V["phone"]["start"] + 0.2
    segs.append(composite("09-join-ask", w0, M["votes_done"] + 1.5, [
        ("The projector shows the join code. Phones join with it.", 0, M["phone_ask_start"] - w0),
        ("A participant asks a question.", M["phone_ask_start"] - w0, M["phone_asked"] + 0.8 - w0),
        ("Others ask and upvote. The projector lists the top questions.", M["phone_asked"] + 0.8 - w0, 99),
    ]))
    segs.append(clip("10-respond", A, a("mod_queries") - 0.4, a("responded") + 1.3,
                     [("The moderator marks a question as responded.", 0, 99)]))
    segs.append(clip("11-quiz-start", A, a("mod_quiz_card") - 0.3, a("quiz_started") + 0.8,
                     [("The moderator starts the quiz.", 0, 99)]))
    w1 = M["quiz_started"] + 0.2
    segs.append(composite("12-answer", w1, M["phone_answered"] + 1.0,
                          [("Phones show the question. A participant answers.", 0, 99)]))
    # Slowed slightly so the menu click and its caption are readable.
    segs.append(clip("13-counts-click", A, a("phone_answered") + 0.4, a("counts_on") + 0.9,
                     [("The moderator turns on live vote counts.", 0, 99)], speed=0.8))
    w2 = M["counts_on"] + 0.9
    segs.append(composite("14-counts", w2, M["others_answered"] + 1.4,
                          [("The projector shows live counts. Answers stay masked.", 0, 99)]))
    w3 = M["revealed"] - 0.3
    segs.append(composite("15-reveal", w3, M["end"] - 0.2,
                          [("Reveal results: the correct answer is shown.", 0, 99)]))
    segs.append(card("16-end", "end.png", 5.0))

    lst = SEG / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in segs))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-movflags", "+faststart", "-an", str(OUT)])
    t = 0.0
    lines = []
    for name, dur, caps in scene_log:
        lines.append(f"{t:6.1f}s  {name:18s} {dur:5.1f}s  {' | '.join(caps)}")
        t += dur
    lines.append(f"total ≈ {t:.1f}s; actual {duration(OUT):.2f}s")
    (W / "scene-list.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
