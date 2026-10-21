"""Clip Factory: several short vertical clips from one long talking-head video, in the reel look (editor/reel.py).

1. `clips-prep <video> <work>`: transcript with sentence timings (`<work>/transcript.md`) for picking moments.
2. Claude writes `<work>/clips.json`: `[{"name", "start", "end", "title"?}, ...]` (source seconds; 20-60 s each,
   self-contained, strongest line first) and `<work>/subs.json` (English cues in source seconds, only for those
   ranges, same rules as the reel recipe).
3. `clips-render <video> <work> <out> [--style NAME]`: per clip: cut, reframe to 9:16 on the face (landscape sources), retouch +
   subtitles (+ optional title for the first 3 s), studio voice on the clip's own audio, HQ master + preview.
Studio voice runs per clip (about 9 s per second of audio), so total time scales with the clips, not the source.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

from . import captions, ffmpeg, reel, transcribe

TITLE_SECS = 3.0
MIN_LEN, MAX_LEN = 8.0, 90.0


def prep(src, work, language: str = "ar") -> Path:
    """Whisper segments and words (turbo for sources over 5 min), and a second engine's Arabic text when there is one."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    wav = work / "audio16k.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(wav)], check=True)
    dur = ffmpeg.probe(src)["duration"] or 0
    from faster_whisper import WhisperModel
    model = WhisperModel("large-v3" if dur <= 300 else "large-v3-turbo", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(wav), language=language, vad_filter=True, condition_on_previous_text=False,
                               word_timestamps=True, beam_size=5)
    lines = [f"# Transcript ({dur:.0f} s). Sentences: [start-end] text. Words below for exact timing.", ""]
    words = []
    for s in segs:
        lines.append(f"[{s.start:7.2f}-{s.end:7.2f}] {s.text.strip()}")
        words.append(" ".join(f"{w.word.strip()}@{w.start:.2f}" for w in s.words))
    lines += ["", "# Words (word@start)", ""] + words
    if language == "ar":
        lines += transcribe.arabic_check_lines(wav, work)
    lines += ["", f"Max characters per subtitle line: {reel.max_line_chars()}"]
    md = work / "transcript.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md


def check_clips(clips: list, duration: float) -> list:
    errs, names = [], set()
    for c in clips:
        n, s, e = c.get("name", ""), c.get("start", -1), c.get("end", -1)
        if not n or not n.replace("-", "").replace("_", "").isalnum() or n in names:
            errs.append(f"clip name {n!r} must be unique, letters/digits/-/_")
        names.add(n)
        if not 0 <= s < e <= duration + 0.05:
            errs.append(f"clip {n}: {s}-{e} is outside 0-{duration:.2f}")
        elif not MIN_LEN <= e - s <= MAX_LEN:
            errs.append(f"clip {n}: {e - s:.1f} s long (keep {MIN_LEN:.0f}-{MAX_LEN:.0f} s)")
        parts = c.get("title", "").split("\\N") if c.get("title") else []
        limit = title_chars()
        if len(parts) > 2 or any(len(p) > limit for p in parts):
            errs.append(f"clip {n}: title must be at most 2 lines of {limit} chars (break with \\N)")
    return errs


def clip_subs(subs: list, start: float, end: float) -> list:
    """Cues overlapping [start, end], shifted to clip time and clamped to it."""
    out = []
    for s, e, t in subs:
        if e > start + 0.05 and s < end - 0.05:
            out.append([round(max(s, start) - start, 3), round(min(e, end) - start, 3), t])
    return [c for c in out if c[1] - c[0] >= 0.3]


def title_chars(style=None) -> int:
    return captions.max_chars_for(reel._style(style), reel.SIZE, hook=True)


def title_events(title: str, until: float = TITLE_SECS) -> list:
    """A big title at the top of the safe zone for the first seconds (ASS events in the Hook style)."""
    if not title:
        return []
    text = captions._esc(title.replace("\\N", "¦")).replace("¦", "\\N")
    return [f"Dialogue: 1,{captions._t(0)},{captions._t(until)},HookL,,0,0,0,,"
            f"{{\\an8\\pos(540,300)\\fad(150,250)}}{text}"]


def face_center_x(src, start: float, end: float, samples: int = 12) -> float | None:
    """Median face centre (0-1 of width) over the clip, for a static 9:16 crop of a landscape shot."""
    import cv2

    from .retouch import landmarker, landmarks
    lm, xs = landmarker(False), []
    for t in np.linspace(start + 0.2, max(start + 0.3, end - 0.2), samples):
        p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                            "-vf", "scale=640:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        img = cv2.imdecode(np.frombuffer(p.stdout, np.uint8), cv2.IMREAD_COLOR) if p.stdout else None
        if img is None:
            continue
        P = landmarks(lm, cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if P is not None:
            xs.append(float(P[:, 0].mean()) / img.shape[1])
    return float(np.median(xs)) if xs else None


def cut(src, start: float, end: float, out) -> Path:
    """Exact cut, reframed to 9:16 (face-centred crop for wider sources), 1080x1920, near-lossless intermediate."""
    info = ffmpeg.probe(src)
    w, h = info["width"], info["height"]
    vf = "scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1920"
    if w and h and w / h > 9 / 16 + 0.01:
        cx = face_center_x(src, start, end) or 0.5
        vf = (f"crop=trunc(ih*9/16/2)*2:ih:x='min(max(iw*{cx:.4f}-ow/2,0),iw-ow)':y=0,"
              "scale=1080:1920:flags=lanczos")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{end - start:.3f}",
                    "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "12", "-pix_fmt", "yuv420p",
                    "-c:a", "pcm_s16le", "-ar", "48000", str(out)], check=True)
    return Path(out)


def render(src, work, out_dir, voice: str = "studio", retouch: bool = True, only: list | None = None,
           style=None) -> list:
    from . import voice as voice_mod
    from .fonts import ensure_font
    from .retouch import retouch_video
    work, out_dir = Path(work), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    style = reel._style(style)
    clips = json.loads((work / "clips.json").read_text(encoding="utf-8"))
    subs = json.loads((work / "subs.json").read_text(encoding="utf-8")) if (work / "subs.json").exists() else []
    errs = check_clips(clips, ffmpeg.probe(src)["duration"] or 0) + reel.check_subs(subs, style=style)
    if errs:
        raise SystemExit("clips:\n  " + "\n  ".join(errs))
    fonts = str(ensure_font(style["font"]).parent)
    done = []
    for c in clips:
        if only and c["name"] not in only:
            continue
        cw = work / "clips" / c["name"]
        cw.mkdir(parents=True, exist_ok=True)
        raw = cut(src, c["start"], c["end"], cw / "cut.mov")
        ass = reel.to_ass(clip_subs(subs, c["start"], c["end"]), style=style)
        if c.get("title"):
            ass = ass.rstrip("\n") + "\n" + "\n".join(title_events(c["title"])) + "\n"
        (cw / "subs.ass").write_text(ass, encoding="utf-8")
        if retouch:
            picture = retouch_video(raw, cw / "picture.mp4", "natural", ass=str(cw / "subs.ass"), fonts_dir=fonts)
        else:
            picture = cw / "picture.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-vf",
                            f"ass={cw / 'subs.ass'}:fontsdir={fonts}:shaping=complex,format=yuv420p", "-c:v",
                            "libx264", "-preset", "slow", "-crf", "15", "-c:a", "copy", str(picture)], check=True)
        if voice == "studio":
            wav = voice_mod.studio_restore(raw, cw / "voice.wav", cw / "voice")
        else:
            wav = cw / "voice.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-vn", "-af", "loudnorm=I=-14:TP=-1.5",
                            "-ar", "48000", str(wav)], check=True)
        master = voice_mod.mux(picture, wav, out_dir / f"{c['name']}-HQ.mp4")
        preview = out_dir / f"{c['name']}-preview.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(master), "-c:v", "libx264", "-preset", "medium",
                        "-crf", "21", "-maxrate", "3000k", "-bufsize", "6000k", "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", str(preview)], check=True)
        done.append({"name": c["name"], "master": master, "preview": preview})
    return done
