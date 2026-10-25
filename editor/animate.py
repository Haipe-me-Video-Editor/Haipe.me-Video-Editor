"""Animation studio: a short animated film where every frame is drawn in code on a canvas, the sound is
synthesised, and nothing comes from a video or image model. The agent researches the topic, writes a style bible
and a shot list, draws each shot in `comp/shots.js`, checks snapshots against the bible, then renders.

    python -m editor animate-new <dir> --topic "how a hummingbird hovers" --seconds 15 --format 9:16 --refs a.jpg
    python -m editor animate-snap <dir>      # contact sheet of every shot, to check against the style bible
    python -m editor animate-sound <dir>     # sound.json -> sound.wav (listen before the render)
    python -m editor animate-render <dir>    # final MP4 with sound, checked by qc

A film folder holds brief.json (topic, length, format), style.md (the style bible), shots.json (the shot list,
which owns all timing), sound.json (the sound cues, see editor/synth.py), refs/ (the references) and comp/ (the
HyperFrames composition: index.html, shots.js and the studio.js runtime).
"""
import hashlib
import json
import re
import shutil
import string
from pathlib import Path

from . import ffmpeg, fonts, synth
from .config import GSAP_JS

KIT = Path(__file__).with_name("animate_kit")
FORMATS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
DEFAULT_FONTS = ["Instrument Serif Italic", "IBM Plex Mono"]
REF_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
ROOT_DURATION = re.compile(r'(<div[^>]*data-composition-id="main"[^>]*data-duration=")[^"]*(")')

STYLE_MD = """# Style bible: {topic}

Write this before drawing anything, from the references in refs/ (look at each one). Every shot is checked
against it, so make each line something a frame can pass or fail.

## Palette
Name each colour and give its hex. Say which colour is the background, which is the subject, which is the accent.

## Shape and line
Flat or shaded, outline or none, how thick, how round the corners, how much detail on the subject.

## Texture and light
Paper, gouache, grain, glow. Where the light comes from and how hard the shadows are.

## Motion
How things move: slow drifts, springy pops, held frames. What the camera does (most shots: it holds).

## Words on screen
Font, size, where words sit, how they arrive. Keep them few.

## Never
Things that would break the look.

## Facts to get right
What the research found that the picture must show correctly, with where each fact came from.
"""


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _even_shots(seconds: float, n: int) -> list:
    base = round(seconds / n, 2)
    shots, start = [], 0.0
    for i in range(n):
        dur = round(seconds - start, 2) if i == n - 1 else base
        shots.append({"id": f"s{i + 1}", "start": round(start, 2), "dur": dur, "what": "", "camera": "holds",
                      "words": ""})
        start += dur
    return shots


def _font_faces(names: list) -> str:
    return "\n".join(f'      @font-face {{ font-family: "{n}"; src: url("fonts/{Path(f).name}"); }}'
                     for n, f in names)


def new(film, topic: str, seconds: float = 15, fmt: str = "9:16", shots: int = 5, refs=(), font_names=None,
        fps: int = 30) -> Path:
    """Scaffold a film folder. Refuses a folder that already has a brief, so work is never overwritten."""
    film = Path(film)
    if (film / "brief.json").exists():
        raise SystemExit(f"{film} already holds a film (brief.json); pick a new folder")
    if fmt not in FORMATS:
        raise SystemExit(f"format {fmt!r}: choose one of {', '.join(FORMATS)}")
    if not 3 <= seconds <= 180:
        raise SystemExit("seconds: 3 to 180")
    if not 1 <= shots <= 40:
        raise SystemExit("shots: 1 to 40")
    w, h = FORMATS[fmt]
    comp, ref_dir = film / "comp", film / "refs"
    (comp / "fonts").mkdir(parents=True, exist_ok=True)
    ref_dir.mkdir(exist_ok=True)
    kept = []
    for r in refs:
        r = Path(r)
        if not r.is_file() or r.suffix.lower() not in REF_EXT:
            raise SystemExit(f"reference {r}: give image files ({', '.join(sorted(REF_EXT))})")
        shutil.copy2(r, ref_dir / r.name)
        kept.append(f"refs/{r.name}")
    names = font_names or DEFAULT_FONTS
    faces = [(n, fonts.ensure_font(n)) for n in names]
    for _, f in faces:
        shutil.copy2(f, comp / "fonts" / f.name)
    shutil.copy2(GSAP_JS, comp / GSAP_JS.name)
    shutil.copy2(KIT / "studio.js", comp / "studio.js")
    shot_list = _even_shots(seconds, shots)
    page = string.Template((KIT / "index.html").read_text(encoding="utf-8")).substitute(
        W=w, H=h, D=f"{seconds:g}", TITLE=topic.replace("<", "").replace(">", ""), FONTFACES=_font_faces(faces))
    (comp / "index.html").write_text(page, encoding="utf-8")
    draw = "\n".join(f"  // {s['id']}(ctx, s) {{ ... }}," for s in shot_list)
    (comp / "shots.js").write_text((KIT / "shots.js").read_text(encoding="utf-8").replace("$DRAW", draw),
                                   encoding="utf-8")
    _write_json(film / "brief.json", {"topic": topic, "seconds": seconds, "format": fmt, "width": w, "height": h,
                                      "fps": fps, "blend": 0.35, "fonts": names, "refs": kept})
    _write_json(film / "shots.json", shot_list)
    _write_json(film / "sound.json", {"seed": 7, "reverb": 0.2, "cues": []})
    (film / "style.md").write_text(STYLE_MD.format(topic=topic), encoding="utf-8")
    sync(film)
    return film


def load(film) -> tuple:
    film = Path(film)
    try:
        brief = json.loads((film / "brief.json").read_text(encoding="utf-8"))
        shots = json.loads((film / "shots.json").read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise SystemExit(f"{film} is not a film folder ({Path(e.filename).name} missing): run animate-new first")
    return brief, check_shots(shots)


def check_shots(shots: list) -> list:
    """Shots must tile the film: start at 0, each one where the last ended, no gaps (a gap renders as nothing)."""
    if not shots:
        raise SystemExit("shots.json has no shots")
    ids, end = set(), 0.0
    for i, s in enumerate(sorted(shots, key=lambda s: s["start"])):
        sid = s.get("id")
        if not sid or not re.fullmatch(r"[A-Za-z][\w-]*", sid) or sid in ids:
            raise SystemExit(f"shot {i + 1}: needs a unique id made of letters, digits, - or _ (got {sid!r})")
        ids.add(sid)
        if s["dur"] <= 0:
            raise SystemExit(f"shot {sid}: dur must be above 0")
        if abs(s["start"] - end) > 0.011:
            raise SystemExit(f"shot {sid} starts at {s['start']}s but the shot before it ends at {end:g}s: "
                             "shots must follow each other with no gap or overlap")
        end = s["start"] + s["dur"]
    return sorted(shots, key=lambda s: s["start"])


def duration(shots: list) -> float:
    return round(shots[-1]["start"] + shots[-1]["dur"], 3)


def sync(film) -> dict:
    """Write shots.json's timing into the composition (timing.js and the root data-duration)."""
    film = Path(film)
    brief, shots = load(film)
    total = duration(shots)
    data = {"width": brief["width"], "height": brief["height"], "fps": brief["fps"], "duration": total,
            "blend": brief.get("blend", 0.35), "shots": [{k: s[k] for k in ("id", "start", "dur", "what") if k in s}
                                                          for s in shots]}
    comp = film / "comp"
    (comp / "timing.js").write_text("window.FILM = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    page = (comp / "index.html").read_text(encoding="utf-8")
    page, n = ROOT_DURATION.subn(lambda m: f"{m.group(1)}{total:g}{m.group(2)}", page, count=1)
    if not n:
        raise SystemExit("comp/index.html lost its root (data-composition-id=\"main\" with data-duration)")
    (comp / "index.html").write_text(page, encoding="utf-8")
    return data


def snap_times(shots: list) -> list:
    """Three moments per shot (early, middle, late), away from the cross-fades."""
    times = []
    for s in shots:
        for k in (0.2, 0.5, 0.85):
            times.append((round(s["start"] + s["dur"] * k, 2), s["id"]))
    return times


def snap(film, at=None) -> list:
    """Lint, then capture frames into snaps/ with contact sheets. Returns the sheets."""
    from .graphics.render import _hf, check_local
    film = Path(film).resolve()
    _, shots = load(film)
    sync(film)
    comp = film / "comp"
    check_local(comp)
    _hf(["lint", "."], comp)
    times = [(t, _shot_at(shots, t)) for t in at] if at else snap_times(shots)
    out = film / "snaps"
    shutil.rmtree(out, ignore_errors=True)
    _hf(["snapshot", ".", "--at", ",".join(f"{t:g}" for t, _ in times), "-o", str(out)], comp)
    # from the files written: hyperframes may add frames of its own (it adds the last frame of the film)
    shot_frames = []
    for f in sorted(out.glob("frame-*-at-*s.png")):
        t = float(re.search(r"-at-([\d.]+)s\.png$", f.name).group(1))
        shot_frames.append({"frame": len(shot_frames) + 1, "file": f.name, "at": t, "shot": _shot_at(shots, t)})
    _write_json(out / "frames.json", shot_frames)
    sheets = sorted(out.glob("contact-sheet*.jpg"))  # one sheet, or several numbered ones for many frames
    if not sheets:
        raise RuntimeError(f"hyperframes snapshot wrote no contact sheet in {out}")
    return sheets


def _shot_at(shots: list, t: float) -> str:
    return next((s["id"] for s in shots if t < s["start"] + s["dur"]), shots[-1]["id"])


def sound(film) -> Path:
    film = Path(film)
    _, shots = load(film)
    spec = json.loads((film / "sound.json").read_text(encoding="utf-8"))
    for c in spec.get("cues", []):
        if c.get("type") == "file" and "path" in c:
            c["path"] = str((film / c["path"]).resolve()) if not Path(c["path"]).is_absolute() else c["path"]
    if not spec.get("cues"):
        raise SystemExit("sound.json has no cues: write the score and effects first (see editor/synth.py)")
    return synth.write(spec, duration(shots), film / "sound.wav", {s["id"]: s["start"] for s in shots})


def check_drawn(film) -> None:
    """Every shot has a draw function, and no reference image was copied into the film."""
    js = (Path(film) / "comp" / "shots.js").read_text(encoding="utf-8")
    _, shots = load(film)
    missing = [s["id"] for s in shots if not re.search(rf"^\s*{re.escape(s['id'])}\s*[:(]", js, re.M)]
    if missing:
        raise SystemExit(f"shots.js draws no {', '.join(missing)}: every shot in shots.json needs a draw function")
    digest = lambda f: hashlib.sha1(f.read_bytes()).hexdigest()  # noqa: E731
    refs = {digest(r): r.name for r in (Path(film) / "refs").glob("*") if r.is_file()}
    comp = Path(film) / "comp"
    for f in comp.rglob("*"):
        if f.is_file() and f.suffix.lower() in REF_EXT and digest(f) in refs:
            raise SystemExit(f"comp/{f.relative_to(comp)} is the reference {refs[digest(f)]}: references are for "
                             "reading the style only, and the film draws everything itself")


def render(film, out=None, quality: str = "delivery", silent: bool = False, run_qc: bool = True) -> Path:
    from .graphics.render import _hf, check_local
    film = Path(film).resolve()
    brief, shots = load(film)
    check_drawn(film)
    sync(film)
    comp = film / "comp"
    check_local(comp)
    _hf(["lint", "."], comp)
    work = film / "work"
    work.mkdir(exist_ok=True)
    picture = work / "picture.mp4"
    _hf(["render", ".", "--format", "mp4", "--fps", str(brief["fps"]), "--quality", quality,
         "--video-bitrate", "14M", "-o", str(picture)], comp)
    out = Path(out) if out else film / "out" / "film.mp4"
    return mux(picture, None if silent else sound(film), out, duration(shots), work, (brief["width"], brief["height"]),
               run_qc)


def mux(picture, wav, out, total: float, work, size: tuple, run_qc: bool = True) -> Path:
    """The picture with its sound at -14 LUFS (or silence when wav is None), checked by qc."""
    from . import qc
    from .render import normalize
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if wav is None:
        audio = ["-f", "lavfi", "-t", f"{total}", "-i", "anullsrc=r=48000:cl=stereo"]
    else:
        norm = normalize(wav, Path(work) / "sound-14lufs.wav")
        # AAC adds up to ~1 dB to the peaks it is given (short pops and plucks most): a ceiling at -2.5 dBFS keeps
        # the encoded file under qc's -1 dBTP without touching the loudness
        safe = Path(work) / "sound-safe.wav"
        ffmpeg.run(["-i", str(norm), "-af", "alimiter=limit=0.75:level=false:attack=1:release=40", str(safe)])
        audio = ["-i", str(safe)]
    ffmpeg.run(["-i", str(picture), *audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                "-b:a", "192k", "-ar", "48000", "-t", f"{total}", "-movflags", "+faststart", str(out)])
    if run_qc:
        r = qc.qc(out, size=size)
        if wav is None:
            r["checks"] = [c for c in r["checks"] if c["name"] not in ("loudness", "true_peak")]
            r["passed"] = all(c["ok"] for c in r["checks"])
        print(f"qc {out.name}\n{qc.report(r)}")
        if not r["passed"]:
            raise SystemExit(f"qc failed for {out}: fix it before delivery")
    return out


def cmd_new(a) -> None:
    film = new(a.film, a.topic, a.seconds, a.format, a.shots, a.refs or (), a.fonts, a.fps)
    print(f"{film}\nnext: write style.md, fill shots.json, draw comp/shots.js, write sound.json")


def cmd_snap(a) -> None:
    for sheet in snap(a.film, [float(x) for x in a.at.split(",")] if a.at else None):
        print(sheet)


def cmd_sound(a) -> None:
    print(sound(a.film))


def cmd_render(a) -> None:
    print(render(a.film, a.out, a.quality, a.silent, not a.no_qc))


def register(add) -> None:
    p = add("animate-new", cmd_new, "film")
    p.add_argument("--topic", required=True, help="what the film is about, in a sentence")
    p.add_argument("--seconds", type=float, default=15)
    p.add_argument("--format", default="9:16", choices=list(FORMATS))
    p.add_argument("--shots", type=int, default=5, help="how many shots to start the list with")
    p.add_argument("--refs", nargs="*", help="style reference images (a pin, a film frame, an illustration)")
    p.add_argument("--fonts", nargs="*", choices=sorted(fonts.SOURCES), help=f"default: {', '.join(DEFAULT_FONTS)}")
    p.add_argument("--fps", type=int, default=30, choices=[24, 25, 30, 60])
    p = add("animate-snap", cmd_snap, "film")
    p.add_argument("--at", help="comma-separated seconds instead of three frames per shot")
    add("animate-sound", cmd_sound, "film")
    p = add("animate-render", cmd_render, "film")
    p.add_argument("--out", help="default: <film>/out/film.mp4")
    p.add_argument("--quality", default="delivery", choices=["draft", "looks", "delivery"])
    p.add_argument("--silent", action="store_true", help="no sound track (a draft only: a post needs sound)")
    p.add_argument("--no-qc", action="store_true")
