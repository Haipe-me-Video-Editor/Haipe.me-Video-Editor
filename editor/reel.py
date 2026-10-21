"""The talking-head reel recipe: a clip delivered as recorded, made to look and sound its best.

No cuts. English subtitles translated by meaning from the Arabic, the `natural` retouch, the studio voice, a
1080x1920 HQ master for Gofile and a capped preview for chat. Two commands:

1. `reel-prep <clip> <work>`: Whisper large-v3 word timings (and a second engine's text as a check when this
   copy has one), written to
   `<work>/words.md`, while the studio voice restore runs in the background into `<work>/voice_final.wav`.
2. Claude writes `<work>/subs.json`: `[[start, end, "line one\\Nline two"], ...]` in source seconds, one idea per
   cue, at most 2 lines of `max_line_chars()` characters, timed to the words.
3. `reel-deliver <clip> <work> <out_dir> [--style NAME]`: captions → retouch + burn → mux the voice → HQ master and preview.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from . import captions, transcribe
from .config import PACKAGE_DIR
from .style import load_style

SIZE = (1080, 1920)


def _style(style) -> dict:
    return style if isinstance(style, dict) else load_style(style or "default")


def max_line_chars(style=None) -> int:
    return captions.max_chars_for(_style(style), SIZE)


def prep(src, work) -> Path:
    """Transcripts for the translation; starts the studio voice in a background process (log: voice.log)."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    voice_log = open(work / "voice.log", "w")
    subprocess.Popen([sys.executable, "-c", "import sys; from editor import voice; "
                      "voice.studio_restore(sys.argv[1], sys.argv[2], sys.argv[3]); print('VOICE_DONE')",
                      str(src), str(work / "voice_final.wav"), str(work / "voice")],
                     cwd=str(PACKAGE_DIR.parent), stdout=voice_log, stderr=subprocess.STDOUT)
    wav = work / "audio16k.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(wav)], check=True)
    from faster_whisper import WhisperModel
    segs, _ = WhisperModel("large-v3", device="cpu", compute_type="int8").transcribe(
        str(wav), language="ar", vad_filter=True, condition_on_previous_text=False, word_timestamps=True, beam_size=5)
    lines = ["# Whisper large-v3 (word@start-end, source seconds)", ""]
    for s in segs:
        lines.append(" ".join(f"{w.word.strip()}@{w.start:.2f}-{w.end:.2f}" for w in s.words))
    lines += transcribe.arabic_check_lines(wav, work)
    lines += ["", f"Max characters per subtitle line: {max_line_chars()}"]
    md = work / "words.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md


def check_subs(subs: list, limit: int | None = None, style=None) -> list:
    """Problems with subs.json: overlaps, too-short cues, lines too long or more than two lines."""
    limit = limit or max_line_chars(style)
    errs = []
    for i, (s, e, text) in enumerate(subs):
        if e - s < 0.5:
            errs.append(f"cue {i} at {s:.2f}s is shorter than 0.5 s")
        if i and s < subs[i - 1][1] - 0.01:
            errs.append(f"cue {i} at {s:.2f}s overlaps the previous one")
        parts = text.split("\\N")
        if len(parts) > 2:
            errs.append(f"cue {i} at {s:.2f}s has more than 2 lines")
        errs += [f"cue {i} line {part!r} is {len(part)} chars (max {limit})" for part in parts if len(part) > limit]
    return errs


def to_ass(subs: list, gap_fill: float = 0.35, style=None) -> str:
    """ASS in the given style (a name, a path or a dict; default the built-in default). Gaps shorter than gap_fill are closed so captions don't flicker."""
    subs = [list(x) for x in subs]
    for i in range(len(subs) - 1):
        if subs[i + 1][0] - subs[i][1] < gap_fill:
            subs[i][1] = subs[i + 1][0]
    lines = [{"start": s, "end": e, "hook": False, "words": [{"w": "ع"}], "tr": t.replace("\\N", "¦")}
             for s, e, t in subs]
    return captions.to_ass(lines, _style(style), SIZE, mode="en").replace("¦", "\\N")


def deliver(src, work, out_dir, style=None) -> dict:
    from . import voice
    from .fonts import ensure_font
    from .retouch import retouch_video
    work, out_dir = Path(work), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    style = _style(style)
    subs = json.loads((work / "subs.json").read_text(encoding="utf-8"))
    errs = check_subs(subs, style=style)
    if errs:
        raise SystemExit("subs.json:\n  " + "\n  ".join(errs))
    ass = work / "en.ass"
    ass.write_text(to_ass(subs, style=style), encoding="utf-8")
    retouched = retouch_video(src, work / "retouched.mp4", "natural", ass=str(ass),
                              fonts_dir=str(ensure_font(style["font"]).parent))
    wav, log = work / "voice_final.wav", work / "voice.log"
    while log.exists() and not any(k in log.read_text() for k in ("VOICE_DONE", "Error", "Traceback")):
        time.sleep(5)  # prep's background restore is still running
    if not (log.exists() and "VOICE_DONE" in log.read_text()):
        voice.studio_restore(src, wav, work / "voice")
    stem = Path(src).stem
    master = voice.mux(retouched, wav, out_dir / f"{stem}-HQ.mp4")
    preview = out_dir / f"{stem}-preview.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(master), "-c:v", "libx264", "-preset", "medium",
                    "-crf", "21", "-maxrate", "3000k", "-bufsize", "6000k", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(preview)], check=True)
    return {"master": master, "preview": preview}
