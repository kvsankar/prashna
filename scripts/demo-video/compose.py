#!/usr/bin/env python3
"""Compose the demo video from recordings/, cards/, timeline.json and voice/.

The storyboard is SCENES below. Every scene becomes a segment in segments/
(1920x1080, 30 fps, H.264), in two versions: a clean one, and one with the
scene's narration burned in as captions (ffmpeg drawtext), cue by cue. The
designed cards (context, hook, why, tunnel, end) come from shoot_cards.py and already
show the narration's words, so they carry no captions.

App scenes are one or more shots. Each shot places recordings in device
frames on the navy background:
  room    the projector and three phones (the opening)
  duo     the projector and Diego's phone, cut from the same wall-clock span
          so they stay in sync
  laptop  a zoomed crop of the presenter's laptop in a window frame; the crop
          shows only the panel in use (and never the Limits card)
The frames are stills drawn by cards.html (scene "plate"): one behind the
recordings and one, with transparent screens, over them. Each shot's
recording span is played faster or slower to fill its share of the scene;
where it would play slower than MIN_SPEED its last frame is held.

Each scene lasts at least LEAD + its voice line + TAIL seconds (MIN_LENGTH
lengthens a few on purpose). The voice line starts LEAD seconds into its
scene, so no line runs into the next scene.

Outputs:
  prashna-demo.mp4         the clean segments with the narration track: no
                           captions in the picture and no subtitle stream;
                           two-pass loudnorm to -14 LUFS integrated, -1 dBTP,
                           AAC-LC 48 kHz 192 kbit/s (the mono voice on both
                           channels), +faststart
  prashna-demo-silent.mp4  the captioned segments, video only
  prashna-demo.srt         the narration as subtitle cues (one per part of
                           each line, timed to the voice), a separate file
  scene-list.txt           start, length and voice timing of every scene
  audio/loudness.json      loudnorm measurements of both passes
  opening-preview.png, ending-preview.png
                           one frame each of the opening (the context card)
                           and the end card

Run:  uv run --project tooling python compose.py
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import sync_playwright

W = Path(__file__).resolve().parent
SEG = W / "segments"
AUD = W / "audio"
PLATES = SEG / "plates"
FONT = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
FPS = 30
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]
SILENT = W / "prashna-demo-silent.mp4"
CLEAN = SEG / "clean.mp4"  # the narrated video's picture, before the audio is added
OUT = W / "prashna-demo.mp4"
SRT = W / "prashna-demo.srt"
LEAD = 0.2   # seconds of silence before each voice line
TAIL = 0.4   # seconds of silence kept after each voice line
MIN_SPEED = 0.75
MIN_LENGTH = {"11-reveal": 5.0}  # hold on the revealed answer
VOICE_RATE = 24000
LOUDNORM = "I=-14:TP=-1:LRA=11"
PEAK_TO_LOUDNESS_DB = 12.0

tl = json.loads((W / "timeline.json").read_text())
V, M, BOX = tl["videos"], tl["marks"], tl["boxes"]
HOST = tl["public_url"].removeprefix("https://")
VOICE: dict[str, float] = json.loads((W / "voice" / "durations.json").read_text())
PARTS: dict[str, list] = json.loads((W / "voice" / "parts.json").read_text())

# ------------------------------------------------------------ layouts
# Screen rectangles (x, y, w, h) in the 1920x1080 frame.
PROJ_DUO = (60, 150, 1344, 756)
PHONE_DUO = (1480, 166, 380, 823)
PROJ_ROOM = (60, 262, 1120, 630)
PHONES_ROOM = [(1256, 374, 188, 407), (1466, 334, 188, 407), (1676, 374, 188, 407)]
WINDOW_MAX = (1680, 800)        # the laptop window's largest screen area
WINDOW_CENTRE = (960, 566)


def duo_plate(label: str) -> dict:
    x, y, w, h = PROJ_DUO
    px, py, pw, ph = PHONE_DUO
    return {"devices": [{"kind": "screen", "x": x, "y": y, "w": w, "h": h},
                        {"kind": "phone", "x": px, "y": py, "w": pw, "h": ph, "url": HOST}],
            "labels": [{"x": x - 2, "y": 74, "html": label},
                       {"x": px + pw / 2, "y": 50, "html": "Diego's phone", "center": True}]}


def room_plate() -> dict:
    x, y, w, h = PROJ_ROOM
    return {"devices": [{"kind": "screen", "x": x, "y": y, "w": w, "h": h}]
            + [{"kind": "phone", "x": a, "y": b, "w": c, "h": d} for a, b, c, d in PHONES_ROOM],
            "brand": {"x": 60, "y": 56, "size": 76},
            "labels": [{"x": 62, "y": 160, "size": 40,
                        "html": '<span class="sub">Ask anonymously · upvote · quick quizzes · one shared screen</span>'}]}


def window_rect(crop: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Where a crop of the laptop recording goes: as large as fits, never above 1:1."""
    _, _, cw, ch = crop
    scale = min(WINDOW_MAX[0] / cw, WINDOW_MAX[1] / ch, 1.0)
    w, h = round(cw * scale / 2) * 2, round(ch * scale / 2) * 2
    return WINDOW_CENTRE[0] - w // 2, WINDOW_CENTRE[1] - h // 2 + 23, w, h


def window_plate(crop: tuple[int, int, int, int]) -> dict:
    x, y, w, h = window_rect(crop)
    return {"devices": [{"kind": "window", "x": x, "y": y, "w": w, "h": h, "title": "Your laptop"}]}


# ------------------------------------------------------------ storyboard
@dataclass
class Shot:
    layout: str                     # room | duo | laptop
    w_in: float                     # wall-clock span (seconds since record_app.py's T0)
    w_out: float
    weight: float = 1.0
    label: str = "Projector"        # duo: the label over the projector
    crop: tuple[int, int, int, int] | None = None  # laptop: x, y, w, h in recording pixels


@dataclass
class Scene:
    name: str
    shots: list[Shot] = field(default_factory=list)  # empty: a card from shoot_cards.py
    caption_x: int = 960


def full_width(y0: float, y1: float) -> tuple[int, int, int, int]:
    y0, y1 = max(0, round(y0)), min(1080, round(y1))
    return (0, y0, 1920, y1 - y0)


def around(box: str, above: float, below: float) -> tuple[int, int, int, int]:
    """Full-width crop from `above` px over a recorded control box to `below` px under it."""
    _, y, _, h = BOX[box]
    return full_width(y - above, y + h + below)


PROJ_LABEL = 'Projector <span class="sub">· join address and QR code</span>'
SCENES = [
    Scene("00-context"),
    Scene("01-hook"),
    Scene("02-hook"),
    Scene("03-intro", [
        Shot("room", M["join_start"] - 0.2, M["join_done"], 2.2),
        Shot("room", M["vote_start"], M["vote_done"] - 0.8, 2.6),
        Shot("room", M["votes_start"] + 1.0, M["votes_done"] - 0.4, 2.4),
    ]),
    Scene("04-why"),
    Scene("05-join", [Shot("duo", M["join_start"] - 0.2, M["join_done"], label=PROJ_LABEL)], caption_x=732),
    Scene("06-ask", [Shot("duo", M["ask_start"], M["ask_done"])], caption_x=732),
    Scene("07-upvote", [Shot("duo", M["vote_start"], M["vote_done"])], caption_x=732),
    Scene("08-answer", [
        Shot("laptop", M["answer_start"] - 0.2, M["answer_clicked"] + 0.3, 0.55, crop=around("answer", 110, 60)),
        Shot("duo", M["answer_clicked"], M["answer_done"], 0.45),
    ]),
    Scene("09-quiz", [
        Shot("laptop", M["quiz_go"] - 0.5, M["quiz_started"] + 0.5, 0.45, crop=full_width(110, 620)),
        Shot("duo", M["quiz_started"], M["votes_start"] + 0.3, 0.55),
    ]),
    Scene("10-votes", [Shot("duo", M["votes_start"], M["votes_done"],
                            label='Projector <span class="sub">· answer text hidden until you reveal it</span>')],
          caption_x=732),
    Scene("11-reveal", [
        Shot("laptop", M["reveal_start"] - 0.5, M["revealed"] + 0.2, 0.35, crop=around("reveal", 10, 30)),
        Shot("duo", M["revealed"] - 0.2, M["end"], 0.65),
    ]),
    Scene("12-tunnel"),
    Scene("13-invite", [Shot("laptop", M["invite_start"], M["invite_done"], crop=full_width(380, 1080))]),
    Scene("14-setup", [
        Shot("laptop", M["sess_start"], M["sess_done"], 1.0, crop=full_width(0, 680)),
        Shot("laptop", M["quiz_start"], M["quiz_done"], 1.2, crop=around("quiz", 12, 0)),
        Shot("laptop", M["start_start"], M["start_done"], 0.8, crop=full_width(0, 640)),
    ]),
    Scene("15-end"),
]
CARDS = {s.name for s in SCENES if not s.shots}


# ------------------------------------------------------------ helpers
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
    return max(MIN_LENGTH.get(name, 0.0), LEAD + VOICE[name] + TAIL)


def off(video: str, wall: float) -> float:
    o = wall - V[video]["start"]
    if o < 0:
        raise ValueError(f"{video} starts after wall {wall}")
    return o


def wrap(text: str, width: int = 42) -> str:
    """One line, or two lines of about equal length split at a space."""
    if len(text) <= width:
        return text
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    cut = min(spaces, key=lambda i: max(i, len(text) - i - 1))
    return text[:cut] + "\n" + text[cut + 1:]


def cues(name: str, start: float, length: float) -> list[tuple[float, float, str]]:
    """The scene's narration parts as cues: (start, end, text), absolute seconds."""
    out = []
    parts = PARTS[name]
    for k, (a, b, text) in enumerate(parts):
        end = start + LEAD + (parts[k + 1][0] if k + 1 < len(parts) else min(b + 0.3, length - LEAD))
        out.append((start + LEAD + a, end, text))
    return out


# ------------------------------------------------------------ plates
_plate_jobs: dict[str, dict] = {}


def plate(spec: dict) -> tuple[Path, Path]:
    """Background and foreground stills for a layout; rendered in one batch later."""
    key = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
    _plate_jobs[key] = spec
    return PLATES / f"{key}-bg.png", PLATES / f"{key}-fg.png"


def render_plates() -> None:
    PLATES.mkdir(parents=True, exist_ok=True)
    # Every text the frames show (labels, the phone's address bar), for check_text.sh.
    (PLATES / "texts.json").write_text(json.dumps(_plate_jobs, indent=2, ensure_ascii=False) + "\n")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        for key, spec in _plate_jobs.items():
            for layer in ("bg", "fg"):
                page.goto((W / "cards.html").as_uri())
                page.evaluate("c => window.setup(c)", {"scene": "plate", "layer": layer, **spec})
                page.screenshot(path=str(PLATES / f"{key}-{layer}.png"), omit_background=layer == "fg")
        browser.close()


# ------------------------------------------------------------ scenes
def shot_graph(shot: Shot, length: float, idx: int, inputs: list[str]) -> str:
    """Filter graph for one shot, ending in the label [s<idx>]; appends its inputs."""
    span = shot.w_out - shot.w_in
    speed = max(span / length, MIN_SPEED)
    if speed > 4.5:
        print(f"  note: shot {idx} plays at {speed:.1f}x")
    hold = max(0.0, length - span / speed) + 1 / FPS
    if shot.layout == "room":
        bg, fg = plate(room_plate())
        sources = [("projector", PROJ_ROOM, None)] + [(n, r, None) for n, r in zip(("phone", "phone2", "phone3"), PHONES_ROOM)]
    elif shot.layout == "duo":
        bg, fg = plate(duo_plate(shot.label))
        sources = [("projector", PROJ_DUO, None), ("phone", PHONE_DUO, None)]
    else:
        assert shot.crop is not None
        bg, fg = plate(window_plate(shot.crop))
        sources = [("admin", window_rect(shot.crop), shot.crop)]
    n0 = sum(1 for x in inputs if x == "-i")
    inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{length:.3f}", "-i", str(bg)]
    inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{length:.3f}", "-i", str(fg)]
    g = [f"[{n0}:v]format=yuv420p,setsar=1[b{idx}]", f"[{n0 + 1}:v]format=rgba[f{idx}]"]
    cur = f"b{idx}"
    for k, (video, (x, y, w, h), crop) in enumerate(sources):
        inputs += ["-ss", f"{off(video, shot.w_in):.3f}", "-t", f"{span:.3f}", "-i", V[video]["path"]]
        n = n0 + 2 + k
        crop_f = f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}," if crop else ""
        g.append(f"[{n}:v]{crop_f}setpts=(PTS-STARTPTS)/{speed:.5f},fps={FPS},scale={w}:{h}:flags=lanczos,setsar=1,"
                 f"tpad=stop_mode=clone:stop_duration={hold:.3f},trim=duration={length:.3f}[r{idx}_{k}]")
        g.append(f"[{cur}][r{idx}_{k}]overlay={x}:{y}:eof_action=repeat[o{idx}_{k}]")
        cur = f"o{idx}_{k}"
    g.append(f"[{cur}][f{idx}]overlay=0:0,trim=duration={length:.3f},setpts=PTS-STARTPTS[s{idx}]")
    return ";".join(g)


def caption_filters(scene: Scene, length: float) -> str:
    """drawtext filters: each narration part shown while it is spoken, white box, dark text."""
    out = []
    for k, (a, b, text) in enumerate(cues(scene.name, 0.0, length)):
        lines = wrap(text).split("\n")
        for j, line in enumerate(reversed(lines)):
            path = SEG / "captions" / f"{scene.name}-{k}-{j}.txt"
            path.write_text(line)
            y = 1080 - 56 - 60 * (j + 1)
            out.append(f"drawtext=fontfile={FONT}:textfile={path}:fontsize=42:fontcolor=0x1f2328"
                       f":box=1:boxcolor=white@0.95:boxborderw=14:x={scene.caption_x}-text_w/2:y={y}"
                       f":enable='between(t,{a:.3f},{b:.3f})'")
    return ",".join(out)


def build_scene(scene: Scene) -> tuple[Path, Path]:
    clean, captioned = SEG / f"{scene.name}.mp4", SEG / "captioned" / f"{scene.name}.mp4"
    if not scene.shots:
        src = W / "cards" / f"{scene.name}.mp4"
        if frames(src) < round(need(scene.name) * FPS):
            raise SystemExit(f"{src.name} is shorter than its narration needs; run shoot_cards.py again")
        return src, src
    total_frames = round(need(scene.name) * FPS + 0.499)
    weights = [s.weight for s in scene.shots]
    alloc, used = [], 0
    for k, wgt in enumerate(weights):
        n = total_frames - used if k == len(weights) - 1 else round(total_frames * wgt / sum(weights))
        alloc.append(n)
        used += n
    inputs: list[str] = []
    graphs = [shot_graph(s, n / FPS, k, inputs) for k, (s, n) in enumerate(zip(scene.shots, alloc))]
    labels = "".join(f"[s{k}]" for k in range(len(scene.shots)))
    graph = ";".join(graphs) + f";{labels}concat=n={len(scene.shots)}:v=1:a=0,split[clean][c];" \
        f"[c]{caption_filters(scene, total_frames / FPS)}[captioned]"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", graph,
         "-map", "[clean]", "-frames:v", str(total_frames), *ENC, str(clean),
         "-map", "[captioned]", "-frames:v", str(total_frames), *ENC, str(captioned)])
    return clean, captioned


# ------------------------------------------------------------ audio and output
def srt_time(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def loudnorm_json(stderr: str) -> dict[str, str]:
    return json.loads(re.findall(r"\{[^{}]*\}", stderr)[-1])


def build_audio(names: list[str], lengths: list[float]) -> dict[str, dict[str, str]]:
    """One narration track as long as the video: each line LEAD s into its scene."""
    shutil.rmtree(AUD, ignore_errors=True)
    AUD.mkdir()
    parts = []
    for name, length in zip(names, lengths):
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
    first = loudnorm_json(run(["ffmpeg", "-hide_banner", "-i", str(limited), "-af",
                               f"loudnorm={LOUDNORM}:print_format=json", "-f", "null", "-"]).stderr)
    measured = (f"measured_I={first['input_i']}:measured_TP={first['input_tp']}:measured_LRA={first['input_lra']}"
                f":measured_thresh={first['input_thresh']}:offset={first['target_offset']}")
    norm = AUD / "narration.wav"
    second = loudnorm_json(run(["ffmpeg", "-y", "-hide_banner", "-i", str(limited), "-af",
                                f"loudnorm={LOUDNORM}:{measured}:linear=true:print_format=json",
                                "-ar", "48000", "-c:a", "pcm_s24le", str(norm)]).stderr)
    result = {"before_limiter": plain, "limiter": {"ceiling": f"{ceiling:.4f}"}, "pass1": first, "pass2": second}
    (AUD / "loudness.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def concat(segments: list[Path], out: Path) -> None:
    lst = SEG / f"{out.stem}.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in segments))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-movflags", "+faststart", "-an", "-sn", "-dn", "-map_metadata", "-1", str(out)])


def still(t: float, out: Path) -> None:
    run(["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(OUT), "-frames:v", "1", "-update", "1", str(out)])


def main() -> None:
    names = [s.name for s in SCENES]
    assert set(names) == set(VOICE), f"narration.txt and the storyboard differ: {set(names) ^ set(VOICE)}"
    shutil.rmtree(SEG, ignore_errors=True)
    (SEG / "captions").mkdir(parents=True)
    (SEG / "captioned").mkdir()
    # Plates first (they are stills), then every scene.
    for scene in SCENES:
        for shot in scene.shots:
            if shot.layout == "room":
                plate(room_plate())
            elif shot.layout == "duo":
                plate(duo_plate(shot.label))
            else:
                assert shot.crop is not None
                plate(window_plate(shot.crop))
    render_plates()
    built = []
    for scene in SCENES:
        print("scene", scene.name, flush=True)
        built.append(build_scene(scene))
    lengths = [frames(clean) / FPS for clean, _ in built]
    for scene, (clean, captioned), length in zip(SCENES, built, lengths):
        assert frames(captioned) == round(length * FPS), f"{scene.name}: the two versions differ in length"
    concat([c for c, _ in built], CLEAN)
    concat([c for _, c in built], SILENT)

    loud = build_audio(names, lengths)
    run(["ffmpeg", "-y", "-i", str(CLEAN), "-i", str(AUD / "narration.wav"), "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-profile:a", "aac_low", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         "-map_metadata", "-1", "-movflags", "+faststart", str(OUT)])

    t = 0.0
    lines: list[str] = []
    all_cues: list[tuple[float, float, str]] = []
    starts: dict[str, tuple[float, float]] = {}
    for i, (scene, length) in enumerate(zip(SCENES, lengths)):
        name = scene.name
        starts[name] = (t, length)
        v_start, v_end = t + LEAD, t + LEAD + VOICE[name]
        assert v_end <= t + length - TAIL + 0.01, f"{name}: voice runs past its scene"
        nxt = t + length + LEAD if i + 1 < len(SCENES) else None
        gap = f"{nxt - v_end:4.2f}s" if nxt is not None else "  end"
        text = " ".join(p[2] for p in PARTS[name])
        lines.append(f"{t:6.2f}s  {name:10s} {length:5.2f}s  voice {v_start:6.2f}-{v_end:6.2f}s"
                     f"  gap to next voice {gap}  {'card   ' if name in CARDS else 'caption'}  {text}")
        all_cues += cues(name, t, length)
        t += length
    lines.append(f"total {t:.2f}s; silent mp4 {duration(SILENT):.2f}s; narrated mp4 {duration(OUT):.2f}s")
    p2 = loud["pass2"]
    lines.append(f"loudnorm pass 2: input {p2['input_i']} LUFS / {p2['input_tp']} dBTP -> "
                 f"output {p2['output_i']} LUFS / {p2['output_tp']} dBTP, {p2['normalization_type']}")
    SRT.write_text("\n".join(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{wrap(text)}\n"
                             for n, (a, b, text) in enumerate(all_cues, start=1)), encoding="utf-8")
    (W / "scene-list.txt").write_text("\n".join(lines) + "\n")
    start, length = starts["00-context"]
    still(start + LEAD + VOICE["00-context"], W / "opening-preview.png")
    start, length = starts["15-end"]
    still(start + length - 0.5, W / "ending-preview.png")
    print("\n".join(lines))
    print("wrote", OUT, SILENT, SRT)


if __name__ == "__main__":
    main()
