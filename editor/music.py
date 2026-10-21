"""Measure tracks once, then pick by mood and length from text-only metadata."""
import hashlib
import json
import re
from pathlib import Path

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def analyze_track(path) -> dict:
    import librosa
    import numpy as np
    y, sr = librosa.load(str(path), sr=22050, mono=True)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    rms = librosa.feature.rms(y=y)[0]
    return {"duration": round(len(y) / sr, 2), "tempo": round(float(np.atleast_1d(tempo)[0]), 1),
            "beats": [round(float(t), 3) for t in librosa.frames_to_time(beats, sr=sr)],
            "energy": round(float(rms.mean()), 4)}


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def build_index(music_dir, index_path) -> list:
    music_dir, index_path = Path(music_dir), Path(index_path)
    old = {}
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text())
            if isinstance(data, list):
                for e in data:
                    if isinstance(e, dict) and "sha1" in e:
                        old[e["sha1"]] = e
        except (json.JSONDecodeError, ValueError):
            pass
    entries = []
    for p in sorted(music_dir.rglob("*")):
        if p.suffix.lower() not in AUDIO_EXTS:
            continue
        digest = _sha1(p)
        if digest in old:
            entries.append({**old[digest], "file": str(p.relative_to(music_dir)),
                           "tags": re.findall(r"[a-z0-9]+", p.stem.lower())})
            continue
        entries.append({"file": str(p.relative_to(music_dir)), "sha1": digest,
                        "tags": re.findall(r"[a-z0-9]+", p.stem.lower()), **analyze_track(p)})
    index_path.write_text(json.dumps(entries, indent=2))
    return entries


def energy_level(energy: float) -> str:
    return "low" if energy < 0.05 else "medium" if energy < 0.12 else "high"


def choose(index: list, min_duration: float, energy: str | None = None) -> dict | None:
    if not index:
        return None

    def score(e):
        return (e["duration"] >= min_duration, energy is None or energy_level(e["energy"]) == energy, e["duration"])

    return max(index, key=score)
