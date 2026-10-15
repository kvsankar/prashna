#!/usr/bin/env python3
"""Speak narration.txt with Kokoro-82M v1.0, locally, one WAV per scene.

Model: the ONNX export of Kokoro-82M v1.0 (Apache-2.0) published on Hugging
Face as onnx-community/Kokoro-82M-v1.0-ONNX, pinned to one revision. On first
run the model and voice files are downloaded into models/ and their SHA-256
hashes are checked against the values below; later runs need no network and
no API key. Phonemes come from espeak-ng through kokoro-onnx's tokenizer;
PRONUNCIATIONS overrides single words.

A line may be split into parts with " | ". Each part is spoken on its own and
the parts are joined with PART_GAP seconds of silence, so the start and end
of every part is known exactly (the cards animate to them, and compose.py
times the subtitle cues and captions with them).

Outputs:
  voice/<scene>.wav          24 kHz mono, 16-bit, one per narration line
  voice/durations.json       seconds per scene (read by shoot_cards.py and compose.py)
  voice/parts.json           per scene: [start, end, text] of each part, in seconds
  voice/provenance.json      model, revision, file hashes, voice, speed, packages
  voice-samples/<voice>.wav  with --samples: the same short passage in other voices

Run:  uv run --project tooling python voice.py [--samples]
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path

# ONNX Runtime sends usage telemetry unless told not to; this must be set
# before it is imported. With it, nothing leaves the machine after the
# first model download.
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

import httpx  # noqa: E402

# These come from tooling/pyproject.toml, not from Prashna's own environment,
# which the repository's type check uses.
# pyrefly: ignore[missing-import]
import numpy as np  # noqa: E402

# pyrefly: ignore[missing-import]
import onnxruntime as rt  # noqa: E402

# pyrefly: ignore[missing-import]
import soundfile as sf  # noqa: E402

# pyrefly: ignore[missing-import]
from kokoro_onnx.tokenizer import Tokenizer  # noqa: E402

# pyrefly: ignore[missing-import]
from kokoro_onnx.trim import trim as trim_audio  # noqa: E402

W = Path(__file__).resolve().parent
MODELS = W / "models"
OUT = W / "voice"
SAMPLES = W / "voice-samples"

REPO = "onnx-community/Kokoro-82M-v1.0-ONNX"
REVISION = "1939ad2a8e416c0acfeecc08a694d14ef25f2231"  # pragma: allowlist secret  (git commit id)
# path in the repository -> SHA-256 (from the repository's LFS pointers; file
# hashes, not secrets)
FILES = {
    "onnx/model.onnx": "8fbea51ea711f2af382e88c833d9e288c6dc82ce5e98421ea61c058ce21a34cb",  # pragma: allowlist secret
    "voices/af_heart.bin": "d583ccff3cdca2f7fae535cb998ac07e9fcb90f09737b9a41fa2734ec44a8f0b",  # pragma: allowlist secret
    "voices/af_bella.bin": "f69d836209b78eb8c66e75e3cda491e26ea838a3674257e9d4e5703cbaf55c8b",  # pragma: allowlist secret
    "voices/bf_emma.bin": "669fe0647f9dd04fcab92f1439a40eeb4c8b4ab1f82e4996fe3d918ce4a63b73",  # pragma: allowlist secret
}
VOICE = "af_heart"          # graded A by the model's author
SAMPLE_VOICES = ("af_bella", "bf_emma")
SPEED = 1.0
LANG = "en-us"
SAMPLE_RATE = 24000
PART_GAP = 0.25  # seconds of silence between the parts of one line
# word -> IPA used in place of espeak-ng's guess ("Prashna" rhymes with "brush-na")
PRONUNCIATIONS = {"Prashna": "pɹˈʌʃnə"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(rel: str) -> Path:
    """Download one repository file into models/ (once) and check its hash."""
    dest = MODELS / rel
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{rel}"
        print("downloading", url, flush=True)
        part = dest.with_suffix(dest.suffix + ".part")
        with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as r:
            r.raise_for_status()
            with part.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
        part.rename(dest)
    got = sha256(dest)
    if got != FILES[rel]:
        dest.unlink()
        raise SystemExit(f"{rel}: SHA-256 {got} does not match the pinned {FILES[rel]}; file removed")
    return dest


def read_narration() -> list[tuple[str, list[str]]]:
    """(scene, parts) for every line of narration.txt."""
    rows = []
    for line in (W / "narration.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        scene, text = line.split("\t", 1)
        rows.append((scene.strip(), [part.strip() for part in text.split("|")]))
    return rows


class Speaker:
    def __init__(self) -> None:
        rt.disable_telemetry_events()
        self.sess = rt.InferenceSession(str(fetch("onnx/model.onnx")), providers=["CPUExecutionProvider"])
        self.inputs = {i.name: i.type for i in self.sess.get_inputs()}
        self.tok = Tokenizer()
        # (word, espeak-ng's phonemes for it, replacement) to substitute in context
        self.overrides = [(w, self.tok.phonemize(w, LANG), ipa) for w, ipa in PRONUNCIATIONS.items()]

    def phonemes(self, text: str) -> str:
        ph = self.tok.phonemize(text, LANG)
        for word, default, ipa in self.overrides:
            if word in text:
                if default not in ph:
                    raise SystemExit(f"cannot place the pronunciation of {word!r} in {ph!r}")
                ph = ph.replace(default, ipa)
        return ph

    def say(self, text: str, voice: str) -> np.ndarray:
        style_table = np.fromfile(fetch(f"voices/{voice}.bin"), dtype=np.float32).reshape(-1, 1, 256)
        ph = self.phonemes(text)
        tokens = self.tok.tokenize(ph)
        if len(tokens) > 500:
            raise SystemExit(f"narration line too long for one pass ({len(tokens)} tokens): {text}")
        speed_type = np.int32 if "int" in self.inputs.get("speed", "") else np.float32
        feeds = {
            "input_ids": np.array([[0, *tokens, 0]], dtype=np.int64),
            "style": style_table[len(tokens)],
            "speed": np.array([SPEED], dtype=speed_type),
        }
        audio = self.sess.run(None, feeds)[0].reshape(-1)
        audio, _ = trim_audio(audio)
        return audio


def write(path: Path, audio: np.ndarray) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")
    return len(audio) / SAMPLE_RATE


def main() -> int:
    samples = "--samples" in sys.argv[1:]
    for rel in FILES:
        fetch(rel)
    sp = Speaker()
    rows = read_narration()
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.wav"):
        old.unlink()
    durations: dict[str, float] = {}
    timing: dict[str, list[list[object]]] = {}
    gap = np.zeros(round(PART_GAP * SAMPLE_RATE), dtype=np.float32)
    for scene, parts in rows:
        pieces: list[np.ndarray] = []
        timing[scene] = []
        t = 0.0
        for k, part in enumerate(parts):
            if k:
                pieces.append(gap)
                t += PART_GAP
            audio = sp.say(part, VOICE).astype(np.float32)
            pieces.append(audio)
            timing[scene].append([round(t, 3), round(t + len(audio) / SAMPLE_RATE, 3), part])
            t += len(audio) / SAMPLE_RATE
        durations[scene] = round(write(OUT / f"{scene}.wav", np.concatenate(pieces)), 3)
        print(f"{scene:12s} {durations[scene]:5.2f}s  {' | '.join(parts)}")
    total = sum(durations.values())
    words = sum(len(" ".join(p).split()) for _, p in rows)
    print(f"total speech {total:.1f}s, {words} words")
    (OUT / "durations.json").write_text(json.dumps(durations, indent=2) + "\n")
    (OUT / "parts.json").write_text(json.dumps(timing, indent=2, ensure_ascii=False) + "\n")
    packages = {p: importlib.metadata.version(p) for p in ("kokoro-onnx", "onnxruntime", "espeakng-loader", "phonemizer-fork")}
    provenance = {
        "model": "Kokoro-82M v1.0 (ONNX export)",
        "model_licence": "Apache-2.0",
        "source": f"https://huggingface.co/{REPO}",
        "revision": REVISION,
        "files": {rel: {"sha256": h, "url": f"https://huggingface.co/{REPO}/resolve/{REVISION}/{rel}"}
                  for rel, h in FILES.items()},
        "voice": VOICE,
        "speed": SPEED,
        "language": LANG,
        "sample_rate": SAMPLE_RATE,
        "pronunciations": PRONUNCIATIONS,
        "part_gap_seconds": PART_GAP,
        "packages": packages,
        "narration_sha256": sha256(W / "narration.txt"),
    }
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n")
    if samples:
        # A passage of about 10 s for comparing voices by ear: the why card.
        text = " ".join(dict(rows)["04-why"])
        for voice in (VOICE, *SAMPLE_VOICES):
            d = write(SAMPLES / f"{voice}.wav", sp.say(text, voice))
            print(f"sample {voice}: {d:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
