"""Splice rendered effect windows back into a picture, frame-exactly, with a cache per window."""
import shutil
import sys
import time
from pathlib import Path

from .. import ffmpeg, quality
from . import registry
from .core import Ctx, spec_key

COMMON = ("type", "at", "dur", "note", "captions")  # captions: keep | hide (default: the effect's CAPTIONS)


def hides_captions(spec: dict) -> bool:
    """Whether burned captions should be left out during this window (effects that fill the caption band)."""
    mode = spec.get("captions") or getattr(registry().get(spec.get("type")), "CAPTIONS", "keep")
    return mode == "hide"


def check(fx: list, total: float | None = None) -> list:
    """Problems with an fx list: unknown types or fields, bad windows, overlaps."""
    reg, errs = registry(), []
    prev_end, prev = -1.0, None
    for i, f in enumerate(sorted(fx, key=lambda x: x.get("at", 0))):
        t = f.get("type")
        if t not in reg:
            errs.append(f"fx[{i}]: unknown type {t!r}; one of {sorted(reg)}")
            continue
        extra = set(f) - set(COMMON) - set(getattr(reg[t], "PARAMS", {}))
        if extra:
            errs.append(f"fx[{i}] {t}: unknown field(s) {sorted(extra)}; allowed {sorted(reg[t].PARAMS)}")
        if f.get("captions") not in (None, "keep", "hide"):
            errs.append(f"fx[{i}] {t}: captions must be keep or hide")
        at, dur = f.get("at"), f.get("dur")
        if not isinstance(at, (int, float)) or not isinstance(dur, (int, float)) or at < 0 or dur < 0.5:
            errs.append(f"fx[{i}] {t}: needs at >= 0 and dur >= 0.5")
            continue
        lo, hi = getattr(reg[t], "DUR", (0.5, 30))
        if not lo <= dur <= hi:
            errs.append(f"fx[{i}] {t}: dur {dur} outside {lo}-{hi} s")
        if total is not None and at + dur > total + 0.05:
            errs.append(f"fx[{i}] {t}: ends at {at + dur:.2f}s, after the video ({total:.2f}s)")
        if at < prev_end - 1e-3:
            errs.append(f"fx[{i}] {t}: overlaps {prev} (effects can't stack; split the window)")
        prev_end, prev = at + dur, t
    return errs


def render_window(video, spec: dict, work, style: dict, size, fps, project=None) -> Path:
    """The effect for one window, cached under work/ by spec, effect code and the source video."""
    mod = registry()[spec["type"]]
    work = Path(work)
    st = Path(video).stat()
    key = spec_key({**spec, "_src": [str(video), st.st_size, int(st.st_mtime)], "_style": style.get("name")}, mod)
    out = work / f"{spec['type']}-{key}.mp4"
    if out.exists():
        return out
    wdir = work / f"{spec['type']}-{key}"
    wdir.mkdir(parents=True, exist_ok=True)
    seg = wdir / "window.mp4"
    lead = min(1.0, spec["at"])
    n = int(round(spec["dur"] * fps))
    ffmpeg.run(["-ss", f"{spec['at'] - lead:.3f}", "-i", video, "-vf",
                f"fps={fps},trim=start={lead:.4f},setpts=PTS-STARTPTS,scale={size[0]}:{size[1]}",
                "-frames:v", n, "-an", "-c:v", "libx264", *quality.inter("veryfast", 10), "-pix_fmt", "yuv420p",
                seg])
    ctx = Ctx(seg, wdir / "out.mp4", spec, style, wdir, size, fps, project)
    t0 = time.time()
    mod.render(ctx)
    print(f"[fx] {spec['type']} at {spec['at']:.2f}s ({spec['dur']:.1f}s): {time.time() - t0:.0f}s",
          file=sys.stderr, flush=True)
    info = ffmpeg.probe(ctx.out)
    if abs(info["duration"] - spec["dur"]) > 1.5 / fps:
        raise RuntimeError(f"{spec['type']}: rendered {info['duration']:.3f}s for a {spec['dur']}s window")
    shutil.move(ctx.out, out)
    return out


def apply_fx(video, fx: list, work, style: dict, size=(1080, 1920), fps: float = 30, project=None, out=None) -> Path:
    """`video` with every fx window replaced by its effect. Audio, if any, is copied untouched."""
    video, work = Path(video), Path(work)
    work.mkdir(parents=True, exist_ok=True)
    info = ffmpeg.probe(video)
    errs = check(fx, info["duration"])
    if errs:
        raise ValueError("fx:\n  " + "\n  ".join(errs))
    fx = sorted(fx, key=lambda f: f["at"])
    windows = [render_window(video, f, work, style, size, fps, project) for f in fx]
    out = Path(out or work / "picture-fx.mp4")
    args, chain, cur = ["-i", video], [f"[0:v]fps={fps},setpts=PTS-STARTPTS,scale={size[0]}:{size[1]}[b]"], "b"
    for i, (f, w) in enumerate(zip(fx, windows), 1):
        args += ["-itsoffset", f"{f['at']:.4f}", "-i", w]
        end = f["at"] + f["dur"]
        chain.append(f"[{i}:v]fps={fps}[w{i}]")
        chain.append(f"[{cur}][w{i}]overlay=enable='between(t,{f['at']:.4f},{end - 0.5 / fps:.4f})'"
                     f":eof_action=pass[o{i}]")
        cur = f"o{i}"
    chain.append(f"[{cur}]format=yuv420p[v]")
    audio = ["-map", "0:a?", "-c:a", "copy"]
    ffmpeg.run([*args, "-filter_complex", ";".join(chain), "-map", "[v]", *audio, "-c:v", "libx264", *quality.inter(),
                "-r", fps, "-t", f"{info['duration']:.4f}", "-movflags", "+faststart", out])
    return out
