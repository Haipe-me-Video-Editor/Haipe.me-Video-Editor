"""Delivery gate for any finished file (a reel, a clip, a full edit): the checks a viewer or a platform would catch,
run before anything is uploaded. `qc <video> [--source <clip>]` prints a pass/fail line per check.

- format: the expected size, a constant frame rate, H.264 + yuv420p, AAC audio, fast start (plays while it loads)
- duration: picture and sound end together (no drift), and match the source when nothing was cut
- loudness: -14 LUFS integrated (±1), true peak at or under -1 dBTP (no clipping on phones)
- picture: no black frames, no frozen stretches, a video bitrate high enough for a master (not "compressed")
"""
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import analyze, ffmpeg
from .review import FREEZE_MIN, FREEZE_NOISE

MASTER_KBPS = 8000  # below this a 1080x1920 master looks compressed on a phone


def _streams(path) -> dict:
    p = subprocess.run([ffmpeg.ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format",
                        "-show_streams", str(path)], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def _moov_first(path) -> bool:
    """True when the moov atom comes before mdat (the file can start playing before it has fully downloaded)."""
    with open(path, "rb") as f:
        pos = 0
        while True:
            f.seek(pos)
            head = f.read(8)
            if len(head) < 8:
                return False
            size, kind = int.from_bytes(head[:4], "big"), head[4:8]
            if kind == b"moov":
                return True
            if kind == b"mdat":
                return False
            if size == 1:
                size = int.from_bytes(f.read(8), "big")
            if size < 8:
                return False
            pos += size


def qc(video, source=None, size=(1080, 1920), min_kbps: int | None = MASTER_KBPS, cut: bool = False) -> dict:
    """{"passed", "checks": [{"name", "ok", "detail"}]}. `cut`: the edit removed time, so don't compare durations
    with the source. `min_kbps` None skips the bitrate check (previews)."""
    video = Path(video)
    data = _streams(video)
    v = next((s for s in data["streams"] if s.get("codec_type") == "video"), {})
    a = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    info = ffmpeg.probe(video)
    checks = []

    def check(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("size", (info["width"], info["height"]) == tuple(size), f"{info['width']}x{info['height']}, want "
          f"{size[0]}x{size[1]}")
    rf, af = v.get("r_frame_rate", "0/1"), v.get("avg_frame_rate", "0/1")
    to_f = lambda r: float(r.split("/")[0]) / float(r.split("/")[1] or 1)  # noqa: E731
    check("constant_fps", abs(to_f(rf) - to_f(af)) < 0.05, f"{to_f(af):.3f} fps (nominal {to_f(rf):.3f})")
    check("codec", v.get("codec_name") == "h264" and v.get("pix_fmt") == "yuv420p",
          f"{v.get('codec_name')} {v.get('pix_fmt')}, want h264 yuv420p")
    check("audio", a is not None and a.get("codec_name") == "aac",
          "none" if a is None else f"{a.get('codec_name')} {a.get('sample_rate')} Hz")
    check("fast_start", _moov_first(video), "moov before mdat" if _moov_first(video) else "run with -movflags +faststart")
    vd = float(v.get("duration") or info["duration"])
    if a is not None:
        ad = float(a.get("duration") or info["duration"])
        check("av_in_sync", abs(vd - ad) <= 0.1, f"picture {vd:.2f}s, sound {ad:.2f}s")
    if source and not cut:
        sd = ffmpeg.probe(source)["duration"]
        check("duration_matches_source", abs(info["duration"] - sd) <= 0.15, f"{info['duration']:.2f}s, source {sd:.2f}s")
    with ThreadPoolExecutor(3) as pool:  # three independent decodes: run them side by side
        loud_f = pool.submit(analyze.loudness, video) if a is not None else None
        blacks_f = pool.submit(analyze.black_frames, video)
        freezes_f = pool.submit(analyze.frozen_ranges, video, FREEZE_NOISE, FREEZE_MIN, info["duration"])
    if a is not None:
        loud = loud_f.result()
        check("loudness", abs(loud["input_i"] + 14) <= 1.0, f"{loud['input_i']:.1f} LUFS, target -14")
        check("true_peak", loud["input_tp"] <= -0.9, f"{loud['input_tp']:.1f} dBTP, max -1")
    blacks = blacks_f.result()
    check("no_black_frames", not blacks, "none" if not blacks else "black at " + ", ".join(f"{b:.1f}s" for b in blacks[:5]))
    freezes = freezes_f.result()
    check("no_frozen_frames", not freezes,
          "none" if not freezes else "frozen " + ", ".join(f"{x:.1f}-{y:.1f}s" for x, y in freezes[:5]))
    if min_kbps:
        kbps = int(v.get("bit_rate") or 0) / 1000 or (video.stat().st_size * 8 / 1000 / max(info["duration"], 0.1))
        check("bitrate", kbps >= min_kbps, f"{kbps:.0f} kb/s video, master floor {min_kbps}")
    return {"passed": all(c["ok"] for c in checks), "checks": checks}


def report(result: dict) -> str:
    return "\n".join(f"{'ok  ' if c['ok'] else 'FAIL'} {c['name']}: {c['detail']}" for c in result["checks"])


def gate(video, **kw) -> dict:
    """qc, printed; raises SystemExit with the failures so a broken file is never uploaded."""
    r = qc(video, **kw)
    print(f"qc {Path(video).name}\n{report(r)}")
    if not r["passed"]:
        raise SystemExit(f"qc failed for {video}: fix it before delivery (or pass --no-qc to deliver anyway)")
    return r
