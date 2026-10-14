#!/usr/bin/env python3
"""Compose the demo video from recordings/, cards/, timeline.json and voice/.

Every scene becomes one segment in segments/ (1920x1080, 30 fps, H.264). An
app scene carries its narration line from narration.txt as a burned-in caption
(ffmpeg drawtext); the card scenes are spoken only. Composite scenes place the
projector recording and the phone recording side by side, cut from the same
wall-clock span so they stay in sync.

Each scene lasts at least LEAD + its voice line + TAIL seconds. Where the
picture is shorter, its last frame is held (tpad=stop_mode=clone). The voice
line starts LEAD seconds into its scene, so no line runs into the next scene.

Outputs:
  prashna-demo-silent.mp4  video only, captions burned in
  prashna-demo.mp4         the same video with the narration track: two-pass
                           loudnorm to -14 LUFS integrated, -1 dBTP, AAC-LC
                           48 kHz 192 kbit/s (the mono voice on both
                           channels), +faststart
  prashna-demo.srt         the narration lines with their spoken times
  scene-list.txt           start, length and voice timing of every scene
  audio/loudness.json      loudnorm measurements of both passes

Run:  python3 -I compose.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

W = Path(__file__).resolve().parent
SEG = W / "segments"
AUD = W / "audio"
FONT = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
FPS = 30
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]
SILENT = W / "prashna-demo-silent.mp4"
OUT = W / "prashna-demo.mp4"
SRT = W / "prashna-demo.srt"
LEAD = 0.2   # seconds of silence before each voice line
TAIL = 0.4   # seconds of silence kept after each voice line
VOICE_RATE = 24000
LOUDNORM = "I=-14:TP=-1:LRA=11"
PEAK_TO_LOUDNESS_DB = 12.0

tl = json.loads((W / "timeline.json").read_text())
V, M = tl["videos"], tl["marks"]
NARRATION: dict[str, str] = {}
for _line in (W / "narration.txt").read_text(encoding="utf-8").splitlines():
    if _line.strip() and not _line.startswith("#"):
        _scene, _text = _line.split("\t", 1)
        NARRATION[_scene.strip()] = _text.strip()
VOICE: dict[str, float] = json.loads((W / "voice" / "durations.json").read_text())
caption_no = 0
scenes: list[tuple[str, Path, bool]] = []  # (scene id, segment, has caption)


def off(video: str, wall: float) -> float:
    """Offset into `video` for wall-clock time `wall` (seconds since T0)."""
    o = wall - V[video]["start"]
    if o < 0:
        raise ValueError(f"{video} starts after wall {wall}")
    return o


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).stdout
    return float(out.strip())


def frames(path: Path) -> int:
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
               "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)]).stdout
    return int(out.strip())


def need(name: str) -> float:
    """Shortest length of scene `name` that fits its voice line."""
    return LEAD + VOICE[name] + TAIL


def hold(picture: float, name: str) -> str:
    """tpad filter that holds the last frame long enough for the voice line, or ''."""
    extra = need(name) - picture
    return f"tpad=stop_mode=clone:stop_duration={extra + 1 / FPS:.3f}" if extra > 0 else ""


def caption_filter(name: str) -> str:
    """drawtext filter: the scene's narration line, white box, dark text, bottom centre."""
    global caption_no
    caption_no += 1
    text = NARRATION[name]
    assert len(text.split()) <= 12, text
    path = SEG / "captions" / f"{caption_no:02d}.txt"
    path.write_text(text)
    return (
        f"drawtext=fontfile={FONT}:textfile={path}:fontsize=44:fontcolor=0x1f2328"
        f":box=1:boxcolor=white@0.95:boxborderw=24:x=(w-text_w)/2:y=h-text_h-64"
    )


def card(name: str, png: str, base: float) -> None:
    out = SEG / f"{name}.mp4"
    dur = max(base, need(name))
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(W / "cards" / png), "-t", f"{dur:.3f}",
         "-vf", "format=yuv420p", *ENC, str(out)])
    scenes.append((name, out, False))


def clip(name: str, video: str, t_in: float, t_out: float, speed: float = 1.0) -> None:
    """Cut `video` between offsets t_in..t_out (video seconds), played at `speed`."""
    out = SEG / f"{name}.mp4"
    picture = (t_out - t_in) / speed
    filters = [f"setpts=PTS/{speed}", f"fps={FPS}", "scale=1920:1080", hold(picture, name), caption_filter(name)]
    run(["ffmpeg", "-y", "-ss", f"{t_in:.3f}", "-t", f"{t_out - t_in:.3f}", "-i", V[video]["path"],
         "-vf", ",".join(f for f in filters if f), *ENC, str(out)])
    scenes.append((name, out, True))


def composite(name: str, w_in: float, w_out: float, speed: float = 1.0) -> None:
    """Projector (left) and phone (right) from the same wall-clock span, played at `speed`."""
    out = SEG / f"{name}.mp4"
    dur = w_out - w_in
    pad = hold(dur / speed, name)
    graph = (
        f"color=c=0xf6f7f9:s=1920x1080:r={FPS}:d={dur / speed:.3f}[bg];"
        f"[0:v]setpts=PTS/{speed},fps={FPS},scale=1376:774[p];"
        f"[1:v]setpts=PTS/{speed},fps={FPS},scale=416:900,pad=428:912:6:6:0x2b3036[m];"
        f"[bg][p]overlay=32:90:shortest=1[a];[a][m]overlay=1456:36[b];"
        f"[b]{pad + ',' if pad else ''}{caption_filter(name)}[v]"
    )
    run(["ffmpeg", "-y",
         "-ss", f"{off('projector', w_in):.3f}", "-t", f"{dur:.3f}", "-i", V["projector"]["path"],
         "-ss", f"{off('phone', w_in):.3f}", "-t", f"{dur:.3f}", "-i", V["phone"]["path"],
         "-filter_complex", graph, "-map", "[v]", *ENC, str(out)])
    scenes.append((name, out, True))


def build_scenes() -> None:
    A = "admin"
    a = lambda mark: off(A, M[mark])  # noqa: E731

    card("01-title", "title.png", 4.0)
    card("02-why", "why.png", 8.0)
    t_dur = duration(Path(V["terminal"]["path"]))
    clip("03-install", "terminal", 1.4, min(13.8, t_dur - 0.2), speed=2.0)
    clip("04-setup", A, 0.0, a("setup_done") + 0.9, speed=1.4)
    clip("05-session", A, a("session_create_start") - 0.3, a("session_created") + 1.6, speed=1.3)
    clip("06-quiz-write", A, a("library_page") - 0.3, a("q1_done") + 0.3, speed=2.4)
    clip("07-quiz-check", A, a("q1_done") + 0.3, a("problem_shown") + 0.2)
    clip("08-quiz-add", A, a("problem_shown") + 0.2, a("quiz_added") + 1.4)
    clip("09-start", A, a("to_sessions") - 0.2, a("session_started") + 1.2)
    w0 = V["phone"]["start"] + 0.2
    composite("10-join", w0, M["phone_ask_start"])
    composite("11-ask", M["phone_ask_start"], M["phone_asked"] + 0.8)
    composite("12-others", M["phone_asked"] + 0.8, M["votes_done"] + 1.5, speed=1.5)
    clip("13-respond", A, a("mod_queries") - 0.4, a("responded") + 1.3, speed=1.3)
    clip("14-quiz-start", A, a("mod_quiz_card") - 0.3, a("quiz_started") + 0.8)
    composite("15-answer", M["quiz_started"] + 0.2, M["phone_answered"] + 1.0)
    # Slowed slightly so the menu click is readable.
    clip("16-counts-on", A, a("phone_answered") + 0.4, a("counts_on") + 0.9, speed=0.8)
    composite("17-counts", M["counts_on"] + 0.9, M["others_half"] - 0.5)
    composite("18-answered", M["others_half"] - 0.5, M["others_answered"] + 0.8)
    composite("19-reveal", M["revealed"] - 0.3, M["end"] - 0.2)
    card("20-end", "end.png", 5.0)
    missing = set(NARRATION) ^ {s for s, _, _ in scenes}
    assert not missing, f"narration.txt and the scene list differ: {missing}"


def srt_time(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def wrap(text: str, width: int = 42) -> str:
    """One line, or two lines of about equal length split at a space."""
    if len(text) <= width:
        return text
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    cut = min(spaces, key=lambda i: max(i, len(text) - i - 1))
    return text[:cut] + "\n" + text[cut + 1:]


def chunks(text: str, limit: int = 84) -> list[str]:
    """Group a line's sentences into cues of at most `limit` characters (two lines)."""
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if out and len(out[-1]) + 1 + len(sentence) <= limit:
            out[-1] += " " + sentence
        else:
            out.append(sentence)
    return out


def loudnorm_json(stderr: str) -> dict[str, str]:
    return json.loads(re.findall(r"\{[^{}]*\}", stderr)[-1])


def build_audio(lengths: list[float]) -> dict[str, dict[str, str]]:
    """One narration track as long as the video: each line LEAD s into its scene."""
    shutil.rmtree(AUD, ignore_errors=True)
    AUD.mkdir()
    parts = []
    for (name, _, _), length in zip(scenes, lengths):
        part = AUD / f"{name}.wav"
        samples = round(length * VOICE_RATE)
        run(["ffmpeg", "-y", "-i", str(W / "voice" / f"{name}.wav"),
             "-af", f"adelay={round(LEAD * 1000)}:all=1,apad=whole_len={samples},atrim=end_sample={samples}",
             "-ar", str(VOICE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(part)])
        parts.append(part)
    lst = AUD / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    raw = AUD / "narration-raw.wav"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "pcm_s16le", str(raw)])
    # Speech from the model has rare sharp peaks, about 21 dB above its loudness.
    # -14 LUFS with -1 dBTP allows 13 dB, so a limiter (run at 192 kHz to catch
    # peaks between samples) first holds peaks 12 dB above the measured loudness;
    # loudnorm can then apply one fixed gain (linear mode) instead of riding it.
    plain = loudnorm_json(run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af",
                               f"loudnorm={LOUDNORM}:print_format=json", "-f", "null", "-"]).stderr)
    ceiling = min(1.0, 10 ** ((float(plain["input_i"]) + PEAK_TO_LOUDNESS_DB) / 20))
    limited = AUD / "narration-limited.wav"
    run(["ffmpeg", "-y", "-i", str(raw), "-af",
         f"aresample=192000,alimiter=limit={ceiling:.4f}:attack=1:release=50:level=false,aresample={VOICE_RATE}",
         "-c:a", "pcm_f32le", str(limited)])
    raw = limited
    # Two-pass loudnorm: measure, then apply the measured values.
    first = loudnorm_json(run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af",
                               f"loudnorm={LOUDNORM}:print_format=json", "-f", "null", "-"]).stderr)
    measured = (f"measured_I={first['input_i']}:measured_TP={first['input_tp']}:measured_LRA={first['input_lra']}"
                f":measured_thresh={first['input_thresh']}:offset={first['target_offset']}")
    norm = AUD / "narration.wav"
    second = loudnorm_json(run(["ffmpeg", "-y", "-hide_banner", "-i", str(raw), "-af",
                                f"loudnorm={LOUDNORM}:{measured}:linear=true:print_format=json",
                                "-ar", "48000", "-c:a", "pcm_s24le", str(norm)]).stderr)
    result = {"before_limiter": plain, "limiter": {"ceiling": f"{ceiling:.4f}"}, "pass1": first, "pass2": second}
    (AUD / "loudness.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    shutil.rmtree(SEG, ignore_errors=True)
    (SEG / "captions").mkdir(parents=True)
    build_scenes()

    lst = SEG / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for _, p, _ in scenes))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-movflags", "+faststart", "-an", str(SILENT)])
    lengths = [frames(p) / FPS for _, p, _ in scenes]

    loud = build_audio(lengths)
    run(["ffmpeg", "-y", "-i", str(SILENT), "-i", str(AUD / "narration.wav"), "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-profile:a", "aac_low", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         "-movflags", "+faststart", str(OUT)])

    t = 0.0
    lines: list[str] = []
    cues: list[tuple[float, float, str]] = []
    for i, ((name, _, has_caption), length) in enumerate(zip(scenes, lengths)):
        v_start, v_end = t + LEAD, t + LEAD + VOICE[name]
        assert v_end <= t + length - TAIL + 0.01, f"{name}: voice runs past its scene"
        nxt = t + length + LEAD if i + 1 < len(scenes) else None
        gap = f"{nxt - v_end:4.2f}s" if nxt is not None else "  end"
        lines.append(f"{t:6.2f}s  {name:15s} {length:5.2f}s  voice {v_start:6.2f}-{v_end:6.2f}s"
                     f"  gap to next voice {gap}  {'caption' if has_caption else 'card   '}  {NARRATION[name]}")
        # A long line becomes several cues, timed by their share of the characters.
        parts = chunks(NARRATION[name])
        total_chars = sum(len(c) for c in parts)
        c_start = v_start
        for k, part in enumerate(parts):
            c_end = c_start + VOICE[name] * len(part) / total_chars
            last = k == len(parts) - 1
            cues.append((c_start, min(c_end + 0.3, t + length) if last else c_end, part))
            c_start = c_end
        t += length
    lines.append(f"total {t:.2f}s; silent mp4 {duration(SILENT):.2f}s; narrated mp4 {duration(OUT):.2f}s")
    p2 = loud["pass2"]
    lines.append(f"loudnorm pass 2: input {p2['input_i']} LUFS / {p2['input_tp']} dBTP -> "
                 f"output {p2['output_i']} LUFS / {p2['output_tp']} dBTP, {p2['normalization_type']}")
    SRT.write_text("\n".join(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{wrap(text)}\n"
                              for n, (a, b, text) in enumerate(cues, start=1)), encoding="utf-8")
    (W / "scene-list.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("wrote", SILENT, OUT, SRT)


if __name__ == "__main__":
    main()
