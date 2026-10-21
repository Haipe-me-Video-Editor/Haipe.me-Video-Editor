"""Automatic checks on a finished render, plus images Claude looks at before delivering."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from . import analyze, captions, ffmpeg
from .config import FORMATS, PACKAGE_DIR
from .editjson import seg_len, timeline_duration
from .sheets import contact_sheet

HOP = 0.01
# Frozen picture: a talking head almost never holds still, so a freeze this long is a stuck overlay, a frozen
# B-roll tail or a graphic held over a static frame.
FREEZE_NOISE = 0.001  # freezedetect noise tolerance (-60 dB)
FREEZE_MIN = 1.5      # seconds; a freeze at least this long fails review
# Per-graphic motion, measured on the final render: grey, ~270p, 6 fps.
MOTION_FPS = 6
MOTION_HEIGHT = 270
STILL_DIFF = 0.3        # mean |frame difference| in 8-bit grey levels below which a step counts as no motion
STATIC_HOLD_MAX = 2.5   # seconds a graphic's window may sit completely still
ENTRANCE_WINDOW = 0.8   # seconds; the entrance must move somewhere in here


def cut_times(plan: dict) -> list:
    out, t = [], 0.0
    for s in plan["segments"][:-1]:
        t += seg_len(s)
        out.append(round(t, 3))
    return out


def find_pops(db, hop: float, times: list, jump_db: float = 9.0) -> list:
    pops = []
    for t in times:
        i = int(t / hop)
        near = db[max(0, i - 5):i + 6]
        around = db[max(0, i - 30):i + 31]
        if len(near) and len(around) and float(np.max(near)) - float(np.median(around)) > jump_db:
            pops.append(t)
    return pops


def _grey_width(path, height: int) -> int:
    p = ffmpeg.probe(path)
    return max(2, round(p["width"] * height / p["height"] / 2) * 2)


def _grey_frames(path, at: float, dur: float, fps: int = MOTION_FPS, height: int = MOTION_HEIGHT, w: int | None = None):
    """Grey frames of [at, at + dur] sampled at `fps`, downscaled to `height` rows: array (n, h, w) uint8."""
    w = w or _grey_width(path, height)
    raw = ffmpeg.run_bytes(["-ss", f"{max(0.0, at):.3f}", "-t", f"{dur:.3f}", "-i", path, "-an",
                            "-vf", f"fps={fps},scale={w}:{height}:flags=area,format=gray",
                            "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    n = len(raw) // (w * height)
    return np.frombuffer(raw[:n * w * height], np.uint8).reshape(n, height, w)


def motion_profile(frames) -> list:
    """Mean absolute difference between consecutive frames, one value per step."""
    if len(frames) < 2:
        return []
    f = frames.astype(np.int16)
    return [round(float(x), 3) for x in np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))]


def judge_motion(diffs: list, fps: float = MOTION_FPS, still: float = STILL_DIFF,
                 hold_max: float = STATIC_HOLD_MAX, entrance: float = ENTRANCE_WINDOW) -> dict:
    """Longest completely still run (seconds, offset from the window start) and whether the entrance moved."""
    best, run, best_end = 0, 0, 0
    for k, x in enumerate(diffs):
        run = run + 1 if x < still else 0
        if run > best:
            best, best_end = run, k + 1
    head = diffs[:max(1, round(entrance * fps))]
    entrance_peak = max(head) if head else 0.0
    static = best / fps
    return {"longest_static": round(static, 2),
            "static_at": [round((best_end - best) / fps, 2), round(best_end / fps, 2)] if best else None,
            "entrance_peak": round(entrance_peak, 3),
            "dead_hold": static > hold_max, "no_entrance": bool(diffs) and entrance_peak < still}


def graphic_motion(final, plan: dict, fps: int = MOTION_FPS, height: int = MOTION_HEIGHT) -> list:
    """For each plan["graphics"] entry, how its window moves in the final render (whole frame, grey, ~270p):
    flags a dead hold (completely still for more than STATIC_HOLD_MAX s) and an entrance that did not animate
    (no motion in its first ENTRANCE_WINDOW s). Timeline seconds; static_at is relative to the graphic's `at`."""
    out, w = [], None
    for i, g in enumerate(plan.get("graphics") or []):
        at, dur = float(g["at"]), float(g["dur"])
        w = w or _grey_width(final, height)
        diffs = motion_profile(_grey_frames(final, at, dur, fps, height, w))
        out.append({"index": i, "type": g.get("type"), "at": at, "dur": dur, **judge_motion(diffs, fps)})
    return out


def review(project, plan: dict, style: dict) -> dict:
    project = Path(project).resolve()
    size = FORMATS[plan["format"]]
    final, nomusic = project / "out" / "final.mp4", project / "out" / "final-nomusic.mp4"
    info = ffmpeg.probe(final)
    planned = timeline_duration(plan)
    checks = []

    def check(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("duration", abs(info["duration"] - planned) <= 0.25, f"{info['duration']:.2f}s, planned {planned:.2f}s")
    blacks = analyze.black_frames(final)
    check("no_black_frames", not blacks, "none" if not blacks else "black at " + ", ".join(f"{b:.1f}s" for b in blacks[:5]))
    freezes = analyze.frozen_ranges(final, FREEZE_NOISE, FREEZE_MIN, info["duration"])
    check("no_frozen_frames", not freezes,
          "none" if not freezes else "frozen " + ", ".join(f"{a:.1f}–{b:.1f}s" for a, b in freezes[:5]))
    motion = graphic_motion(final, plan) if plan.get("graphics") else []
    bad = [m for m in motion if m["dead_hold"] or m["no_entrance"]]
    if motion:
        check("graphics_motion", not bad, "ok" if not bad else "; ".join(
            f"graphics[{m['index']}] {m['type']} at {m['at']:.1f}s: "
            + ", ".join((["still for %.1fs from %.1fs" % (m["longest_static"], m["at"] + m["static_at"][0])]
                         if m["dead_hold"] else []) + (["entrance did not move"] if m["no_entrance"] else []))
            for m in bad[:5]))
    # A music-only edit (every segment muted, e.g. event coverage) has no voice: judge dead air on the final mix,
    # and skip the pop check, which looks for clicks in the voice at cuts.
    music_only = all(x.get("mute") for x in plan["segments"])
    times = cut_times(plan)
    gaps = [g for g in analyze.silences(final if music_only else nomusic, noise_db=-45, min_dur=1.0,
                                        duration=info["duration"])
            if g[0] > 0.3 and g[1] < info["duration"] - 0.3]
    check("no_dead_air", not gaps, "none" if not gaps else "silent " + ", ".join(f"{a:.1f}–{b:.1f}s" for a, b in gaps[:5]))
    if not music_only:
        pops = find_pops(analyze.rms_db(nomusic, HOP), HOP, times)
        check("no_pops", not pops, "none" if not pops else "spike at " + ", ".join(f"{p:.2f}s" for p in pops[:5]))
    lufs = analyze.loudness(final)["input_i"]
    check("loudness", abs(lufs + 14) <= 1.0, f"{lufs:.1f} LUFS, target -14")
    cap, tr = project / "work" / "captions.json", project / "transcript.json"
    if plan.get("captions", {}).get("enabled") and cap.exists():
        doc = json.loads(cap.read_text(encoding="utf-8"))
        words = json.loads(tr.read_text(encoding="utf-8")).get("words") if tr.exists() else None
        if doc.get("key") != captions.cache_key(plan, words, style):
            check("captions_safe_area", False, "captions.json is stale; run captions")
        else:
            issues = captions.check_layout(doc["lines"], style, size, plan["captions"].get("mode", "source"))
            check("captions_safe_area", not issues, "ok" if not issues else "; ".join(issues[:5]))
    verify = project / "verify"
    verify.mkdir(exist_ok=True)
    picks = times if len(times) <= 8 else [times[round(i * (len(times) - 1) / 7)] for i in range(8)]
    views = []
    for k, t in enumerate(picks):
        png = verify / f"cut-{k:02d}.png"
        subprocess.run([sys.executable, "-I", str(PACKAGE_DIR / "vendor" / "timeline_view.py"), str(final),
                        str(max(0.0, t - 1.5)), str(min(info["duration"] - 0.05, t + 1.5)), "-o", str(png)],
                       check=True, capture_output=True)
        views.append(str(png.relative_to(project)))
    contact_sheet(final, project / "sheets" / "final.jpg")
    result = {"passed": all(c["ok"] for c in checks), "checks": checks, "sheet": "sheets/final.jpg", "cut_views": views,
              "freezes": freezes, "graphics_motion": motion}
    (project / "review.json").write_text(json.dumps(result, indent=2))
    return result
