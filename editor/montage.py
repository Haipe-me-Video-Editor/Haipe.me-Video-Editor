"""Event coverage: many clips in, one beat-cut montage out.

`score_clip` rates every half second of a clip (sharpness, motion, brightness, loudness) so the best
moments can be found without watching everything; `best_moments` picks non-overlapping windows from
those scores; `beat_cut` lays the chosen moments on the music's beat grid. The draft is a starting
point: Claude reviews the sheets and refines edit.json (order, speed ramps, effects) by the preset.
"""
import json
from pathlib import Path

import numpy as np

from . import analyze, ffmpeg

STEP = 0.5  # seconds between scored samples
SCORE_W = 160  # width the frames are scored at


def _frames(path, fps: float, width: int) -> np.ndarray:
    info = ffmpeg.probe(path)
    w, h = info["width"], info["height"]
    out_w, out_h = width, max(2, int(round(h * width / w / 2)) * 2)
    raw = ffmpeg.run_bytes(["-i", path, "-vf", f"fps={fps},scale={out_w}:{out_h},format=gray",
                            "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    return np.frombuffer(raw, np.uint8).reshape(-1, out_h, out_w).astype(np.float32)


def score_clip(path, has_audio: bool = True) -> list:
    """Per STEP: sharpness (Laplacian variance), motion (mean frame difference), brightness and loudness."""
    frames = _frames(path, 1 / STEP, SCORE_W)
    loud = analyze.rms_db(path, hop=STEP) if has_audio else None
    rows, prev = [], None
    for i, f in enumerate(frames):
        lap = f[:-2, 1:-1] + f[2:, 1:-1] + f[1:-1, :-2] + f[1:-1, 2:] - 4 * f[1:-1, 1:-1]
        rows.append({"t": round(i * STEP, 2), "sharp": round(float(lap.var()), 1),
                     "motion": round(float(np.abs(f - prev).mean()), 2) if prev is not None else 0.0,
                     "bright": round(float(f.mean()), 1),
                     "loud": round(float(loud[i]), 1) if loud is not None and i < len(loud) else None})
        prev = f
    return rows


def _norm(values: list) -> np.ndarray:
    v = np.array(values, np.float32)
    lo, hi = np.percentile(v, 5), np.percentile(v, 95)
    return np.clip((v - lo) / (hi - lo + 1e-6), 0, 1)


def moment_scores(rows: list) -> np.ndarray:
    """0-1 per sample: sharp and well-exposed first, some motion and crowd noise as a bonus."""
    if not rows:
        return np.zeros(0)
    sharp = _norm([r["sharp"] for r in rows])
    motion = np.array([r["motion"] for r in rows], np.float32)
    lively = np.clip(motion / 12.0, 0, 1) * (motion < 40)  # very high motion is usually a whip or shake
    bright = np.array([r["bright"] for r in rows], np.float32)
    exposed = 1 - np.clip(np.abs(bright - 120) / 120, 0, 1)
    loud = np.array([r["loud"] if r["loud"] is not None else -60 for r in rows], np.float32)
    noisy = np.clip((loud + 40) / 30, 0, 1)
    return 0.45 * sharp + 0.2 * lively + 0.2 * exposed + 0.15 * noisy


def best_moments(clips: dict, length: float = 2.0, top: int = 40) -> list:
    """Best non-overlapping windows across all clips: [{src, in, out, score}] best first."""
    found = []
    for src, data in clips.items():
        rows = data["scores"]
        s = moment_scores(rows)
        k = max(1, int(round(length / STEP)))
        if len(s) < k:
            continue
        win = np.convolve(s, np.ones(k) / k, mode="valid")
        taken = np.zeros(len(win), bool)
        for i in np.argsort(-win):
            if taken[i]:
                continue
            found.append({"src": src, "in": rows[i]["t"], "out": round(rows[i]["t"] + length, 2),
                          "score": round(float(win[i]), 3)})
            taken[max(0, i - k + 1):i + k] = True
    found.sort(key=lambda m: -m["score"])
    return found[:top]


def beat_cut(moments: list, beats: list, total: float, beats_per_shot: int = 2, offset: float = 0.0) -> list:
    """Segments whose cuts land on the beats: each shot lasts beats_per_shot beats (stretched to fill)."""
    grid = [b - offset for b in beats if b - offset >= 0]
    if len(grid) < 2:
        raise ValueError("the music needs at least two beats to cut on")
    if grid[0] > 0.05:
        grid = [0.0] + grid
    cuts = grid[::beats_per_shot]
    if cuts[-1] < total:
        cuts.append(total)
    segs, pool = [], list(moments)
    for a, b in zip(cuts, cuts[1:]):
        if a >= total or not pool:
            break
        b = min(b, total)
        m = pool.pop(0)
        need = round(b - a, 3)
        start = m["in"]
        segs.append({"src": m["src"], "in": round(start, 3), "out": round(start + need, 3), "mute": True})
    return segs


def write_clips(project: Path, clips: dict) -> None:
    (project / "clips.json").write_text(json.dumps(clips, indent=1))


def clip_summary(clips: dict) -> str:
    """A short text table for planning: each clip with its best moments."""
    out = []
    for src, data in clips.items():
        s = moment_scores(data["scores"])
        best = [data["scores"][i]["t"] for i in np.argsort(-s)[:5]] if len(s) else []
        out.append(f"{src}: {data['duration']:.1f}s, audio={'yes' if data['has_audio'] else 'no'}, "
                   f"best at {', '.join(f'{t:.1f}s' for t in sorted(best))}")
    return "\n".join(out)


def snap(t: float, beats: list) -> float:
    """The beat nearest to t (for placing effects and text on the beat)."""
    return min(beats, key=lambda b: abs(b - t)) if beats else t

