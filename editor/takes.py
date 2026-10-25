"""Find the right take of every line in a long raw recording: many retakes, an off-camera director, one camera file.

Learned from a client shoot (29 min of raw, a 2 min finished edit) by aligning the edit back onto the raw:
- The presenter says each line until it is right; the editor keeps the LAST complete take of each line and drops every
  earlier attempt, false start and fragment. A sentence is sometimes joined from the best halves of two takes.
- The off-camera director (prompts, "okay", "again", notes) is off the presenter's lav: about 7-12 dB quieter. None of
  it is ever kept.
- Joins are tight: about 0.05 s before the first word and 0.10 s after the last; no pause over ~0.25 s survives inside
  a kept take.

Pure functions over word timings plus two media helpers (chunked transcription and the selects file). The picks are a
proposal: read `takes.md` and fix a pick with `--keep` / `--drop` before cutting.
"""
import difflib
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from .config import ffmpeg_bin

OFF_DB = 7.0          # a word this much under the presenter's level is the off-camera voice
UNIT_GAP = 0.45       # a pause this long ends a unit (a phrase the presenter says in one go)
WINDOW = 240.0        # a later take supersedes an earlier one only within this many seconds
COVER = 0.6           # share of a unit's letters a later unit must repeat, in order, to supersede it
MIN_WORDS = 3         # a take has at least this many real words
LEAD, TAIL = 0.05, 0.10
MAX_PAUSE = 0.25      # longer pauses inside kept speech are cut
HANDLE = 0.4          # extra picture around each span in the selects file
CHATTER = {"اه", "اها", "اهه", "اههم", "هم", "ايه", "اي", "ايوه", "ايوا", "اوكي", "اوك", "ماشي", "صح", "طيب", "يلا", "تمام",
           "لا", "خلاص", "اهلا", "حسنا", "شكرا", "ماذا", "ممتاز", "متاز", "برافو", "تاني", "كمان", "عادي", "ca", "va",
           "حلو", "جميل", "مم", "ام", "يعني", "okay", "ok", "يس", "نعم", "طب", "بس", "كده", "كدا", "هيك"}
FILLERS = {"اه", "ام", "مم", "اا", "uh", "um", "eh"}
TALK = {"اوكي", "اوك", "ok", "okay", "ماشي", "يلا", "ممتاز", "متاز", "شكرا", "تمام", "حلو", "برافو", "تاني", "اشتركوا"}  # never inside a take: a word to the crew

_DIAC = re.compile("[ً-ٰٟـ]")  # harakat, superscript alef, tatweel
_PUNCT = re.compile(r"[^\w]+")
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي",
                       **{chr(0x660 + i): str(i) for i in range(10)}})


def norm(word: str) -> str:
    """A word folded for matching takes: no diacritics or tatweel, one alef, ta marbuta as ha, Western digits."""
    return _PUNCT.sub("", _DIAC.sub("", word).translate(_FOLD).lower())


def word_levels(words: list, db: np.ndarray, hop: float = 0.01) -> list:
    """90th-percentile level (dB) of each word from a 10 ms envelope."""
    out = []
    for w in words:
        seg = db[int(w["start"] / hop):max(int(w["start"] / hop) + 1, int(w["end"] / hop))]
        out.append(float(np.percentile(seg, 90)) if len(seg) else -99.0)
    return out


def split_level(levels: list, min_gap: float = OFF_DB) -> float | None:
    """The level between two voices (Otsu on the word levels): the presenter on a lav, the director off it. None when
    the two clusters are under min_gap dB apart (one voice only)."""
    x = np.sort(np.asarray(levels, float))
    x = x[x > -60]
    if len(x) < 10:
        return None
    best, cut = -1.0, None
    for k in range(2, len(x) - 1):
        lo, hi = x[:k], x[k:]
        score = len(lo) * len(hi) * (hi.mean() - lo.mean()) ** 2
        if score > best:
            best, cut = score, (x[k - 1] + x[k]) / 2
    lo, hi = x[x < cut], x[x >= cut]
    return float(cut) if hi.mean() - lo.mean() >= min_gap else None


def mark_speaker(words: list, levels: list, gap: float = 0.35) -> float:
    """Tag each word `off` when it is the off-camera voice, judged per phrase (words closer than gap) so one soft word
    does not flip the voice. Returns the split level (or the presenter's median when there is one voice)."""
    for w, lv in zip(words, levels):
        w["lv"] = round(lv, 1)
    cut = split_level(levels)
    phrases = []
    for w in words:
        if phrases and w["start"] - phrases[-1][-1]["end"] < gap:
            phrases[-1].append(w)
        else:
            phrases.append([w])
    for ph in phrases:
        off = cut is not None and float(np.median([w["lv"] for w in ph])) < cut
        for w in ph:
            w["off"] = off
    return cut if cut is not None else float(np.median(levels)) if levels else 0.0


def drop_loops(words: list, max_repeat: int = 3) -> list:
    """Remove ASR loops (the same word over and over, a known Whisper failure on long files)."""
    out, run = [], 0
    for w in words:
        if out and norm(w["w"]) == norm(out[-1]["w"]):
            run += 1
            if run >= max_repeat:
                continue
        else:
            run = 0
        out.append(w)
    return out


def units(words: list, gap: float = UNIT_GAP) -> list:
    """Words into units: a new unit at every pause of `gap` or more, wherever the voice changes, and where the presenter
    starts the same line again without a pause ("let me show you. let me show you how...")."""
    out = []
    for w in words:
        if out and (w["start"] - out[-1][-1]["end"] >= gap or w.get("off") != out[-1][-1].get("off")):
            out.append([])
        if not out:
            out.append([])
        out[-1].append(w)
    return [t for u in out for part in split_restarts(u) if (t := trim_talk(part))]


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def split_restarts(unit: list) -> list:
    """A unit cut where its opening two words come back (a restart inside one breath)."""
    toks = [norm(w["w"]) for w in unit]
    if len(toks) >= 4:
        head = " ".join(toks[:2])
        for k in range(2, len(toks) - 1):
            if _similar(head, " ".join(toks[k:k + 2])) >= 0.8:
                return [unit[:k]] + split_restarts(unit[k:])
    return [unit]


def _tokens(unit: list) -> list:
    return [t for t in (norm(w["w"]) for w in unit) if t and t not in FILLERS]


def covered(a: list, b: list) -> float:
    """Share of a's letters that b repeats in order (runs of 4+ letters): robust to the transcript spelling the same
    word two ways in two takes."""
    sa, sb = " ".join(a), " ".join(b)
    if not sa or not sb:
        return 0.0
    blocks = difflib.SequenceMatcher(None, sa, sb, autojunk=False).get_matching_blocks()
    return sum(m.size for m in blocks if m.size >= 4) / len(sa)


def is_chatter(unit: list) -> bool:
    """Under MIN_WORDS real words, only acknowledgements, or a word to the crew inside it ("... okay so ..."): never a
    take."""
    toks = _tokens(unit)
    return len(toks) < MIN_WORDS or all(t in CHATTER for t in toks) or any(t in TALK for t in toks)


def trim_talk(unit: list) -> list:
    """A take with the crew's reply run onto it ("... في قرارك. حلو، ممتاز"): the words to the crew come off its
    edges."""
    a, b = 0, len(unit)
    while a < b and norm(unit[a]["w"]) in TALK | FILLERS:
        a += 1
    while b > a and norm(unit[b - 1]["w"]) in TALK | FILLERS:
        b -= 1
    return unit[a:b]


def pick(us: list, window: float = WINDOW, cover: float = COVER) -> list:
    """One verdict per unit: {"keep": bool, "why": str, "by": index of the take that replaces it}.

    - off-camera voice and chatter ("okay", "again", one-word replies) go;
    - a unit whose words a later presenter unit repeats (COVER of its letters, within WINDOW) is an earlier attempt:
      the later take replaces it;
    - a fragment that only repeats part of the take just kept before it (a stumble after a good take) goes too.
    """
    toks = [_tokens(u) for u in us]
    out = []
    for i, u in enumerate(us):
        if u[0].get("off") or all(w.get("off") for w in u):
            out.append({"keep": False, "why": "off-camera voice"})
            continue
        if is_chatter(u):
            out.append({"keep": False, "why": "chatter"})
            continue
        by = None
        for j in range(i + 1, len(us)):
            if us[j][0]["start"] - u[-1]["end"] > window:
                break
            if us[j][0].get("off") or is_chatter(us[j]):
                continue
            if covered(toks[i], toks[j]) >= cover:
                by = j
                break
        if by is not None:
            out.append({"keep": False, "why": "earlier take", "by": by})
            continue
        out.append({"keep": True, "why": ""})
    # a short repeat of the kept take right before it is a stumble, not new content
    kept = [i for i, v in enumerate(out) if v["keep"]]
    for p, i in zip(kept, kept[1:]):
        if us[i][0]["start"] - us[p][-1]["end"] > window or len(toks[i]) >= len(toks[p]):
            continue
        if covered(toks[i], toks[p]) >= 0.8:
            out[i] = {"keep": False, "why": "repeat of the take before", "by": p}
    return out


def clean_unit(unit: list) -> list:
    """Kept words of a kept unit: fillers out, a stutter ("the the") keeps its last word."""
    out = []
    for w in unit:
        t = norm(w["w"])
        if t in FILLERS:
            continue
        if out and t and t == norm(out[-1]["w"]):
            out[-1] = w
            continue
        out.append(w)
    return out


def spans(us: list, verdicts: list, lead: float = LEAD, tail: float = TAIL, max_pause: float = MAX_PAUSE,
          end: float | None = None) -> list:
    """[[in, out], ...] source seconds of everything kept, cut at every pause over max_pause."""
    words = [w for u, v in zip(us, verdicts) if v["keep"] for w in clean_unit(u)]
    out = []
    for w in words:
        if out and w["start"] - out[-1][-1]["end"] <= max_pause:
            out[-1].append(w)
        else:
            out.append([w])
    res = []
    for run in out:
        a, b = max(0.0, run[0]["start"] - lead), run[-1]["end"] + tail
        if end is not None:
            b = min(b, end)
        if res and a < res[-1][1]:
            a = res[-1][1]
        if b - a > 0.08:
            res.append([round(a, 3), round(b, 3)])
    return res


def apply_overrides(verdicts: list, keep=(), drop=()) -> list:
    """Hand fixes by unit number (as takes.md prints them)."""
    for i in keep:
        verdicts[i] = {"keep": True, "why": "kept by hand"}
    for i in drop:
        verdicts[i] = {"keep": False, "why": "dropped by hand"}
    return verdicts


def report(us: list, verdicts: list, lens: list | None = None) -> str:
    """takes.md: every unit with its time, voice, verdict and words; kept units in bold. A kept unit said off the
    lens (reading) is marked COVER: it goes under B-roll or a full-screen graphic."""
    rows = ["# Takes", "", "`#` unit, time in the raw, then the verdict. Kept units are bold. Fix a pick with "
            "`takes --keep n,n --drop n,n` and run it again. COVER: he reads off the lens there; put B-roll over it.",
            ""]
    for i, (u, v) in enumerate(zip(us, verdicts)):
        text = " ".join(w["w"].strip() for w in u)
        who = "director" if u[0].get("off") else "COVER" if lens and lens[i] is not None and lens[i] < 0.5 else ""
        why = v["why"] + (f" (#{v['by']})" if v.get("by") is not None else "")
        line = f"{i:4d}  {u[0]['start']:7.2f}-{u[-1]['end']:7.2f}  {who:8s} "
        rows.append(f"- **{line} {text}**" if v["keep"] else f"- {line} ~~{text}~~  _{why}_")
    return "\n".join(rows) + "\n"


# --- media -----------------------------------------------------------------------------------------------------------

def _pcm(src, af: str = "anull") -> np.ndarray:
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(src), "-map", "0:a:0", "-ac", "1", "-ar", "16000",
                          "-af", af, "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def envelope(x: np.ndarray, hop: int = 160) -> np.ndarray:
    n = len(x) // hop
    return 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)


def speech_chunks(db: np.ndarray, max_len: float = 25.0, min_gap: float = 0.5) -> list:
    """[[a, b], ...] seconds: speech regions split at pauses, each at most max_len (split at its longest pause)."""
    on = db > np.percentile(db, 90) - 30
    t = np.arange(len(on)) / 100
    regions, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            regions.append([t[i], t[j - 1] + 0.01])
            i = j
        else:
            i += 1
    merged = []
    for a, b in regions:
        if merged and a - merged[-1][1] < min_gap and b - merged[-1][0] <= max_len:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [[max(0.0, round(a - 0.15, 2)), round(b + 0.15, 2)] for a, b in merged if b - a >= 0.2]


def transcribe_chunks(audio: np.ndarray, chunks: list, language: str = "ar", model=None, log=None) -> list:
    """Whisper on each speech chunk on its own: no ASR loops and no dropped stretches, which a single pass over a
    half-hour file produces. Words as [{w, start, end}] in file seconds."""
    if model is None:
        from faster_whisper import WhisperModel

        from .transcribe import WHISPER_MODEL
        model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    words = []
    for a, b in chunks:
        segs, _ = model.transcribe(audio[int(a * 16000):int(b * 16000)], language=language, vad_filter=False,
                                   condition_on_previous_text=False, word_timestamps=True, beam_size=5)
        got = [{"w": w.word.strip(), "start": round(a + w.start, 3), "end": round(a + w.end, 3)}
               for s in segs for w in (s.words or []) if w.word.strip()]
        words += got
        if log:
            log(f"[{a:7.2f}-{b:7.2f}] " + " ".join(w["w"] for w in got))
    return words


def detect_rotation(src, samples: int = 5) -> int:
    """Clockwise degrees (0, 90, 270) that stand the speaker upright: a camera mounted on its side records sideways
    without saying so in the file. Counts frontal faces found in a few frames at each turn."""
    import cv2

    from . import ffmpeg
    info = ffmpeg.probe(src)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    score = {0: 0, 90: 0, 270: 0}
    for k in range(samples):
        t = info["duration"] * (k + 0.5) / samples
        b = subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
                            "-vf", "scale=640:-2", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           capture_output=True).stdout
        h = len(b) // 640
        if h == 0:
            continue
        img = np.frombuffer(b[:640 * h], np.uint8).reshape(h, 640)
        for deg, rot in ((0, None), (90, cv2.ROTATE_90_CLOCKWISE), (270, cv2.ROTATE_90_COUNTERCLOCKWISE)):
            im = img if rot is None else cv2.rotate(img, rot)
            score[deg] += len(cascade.detectMultiScale(im, 1.1, 6, minSize=(40, 40)))
    return max(score, key=lambda d: (score[d], d == 0))


ROTATE = {0: "", 90: "transpose=1,", 270: "transpose=2,", 180: "hflip,vflip,"}


def gaze_track(src, rotate: int = 0, size: tuple = (270, 480)) -> list:
    """[{t, yaw, pitch}] head angles at every keyframe (camera files carry one every ~0.5 s, and decoding only those
    is fast even in 4K); rows without a face carry only t. Takes are said into the lens; talk with the people behind
    the camera turns the head away."""
    import mediapipe as mp
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core.base_options import BaseOptions

    from .extras import model_path
    W, H = size
    lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path("face_landmarker"))),
        output_facial_transformation_matrixes=True))
    times = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                            "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(src)],
                           capture_output=True, text=True).stdout.split()
    p = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-skip_frame", "nokey", "-i", str(src), "-vsync", "0",
                          "-vf", f"{ROTATE[rotate]}scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    rows = []
    for t in times:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                               data=np.ascontiguousarray(np.frombuffer(b, np.uint8).reshape(H, W, 3))))
        row = {"t": round(float(t.strip(",")), 2)}
        if r.face_landmarks:
            m = np.array(r.facial_transformation_matrixes[0])[:3, :3]
            row.update(pitch=round(float(np.degrees(np.arctan2(-m[2, 1], m[2, 2]))), 1),
                       yaw=round(float(np.degrees(np.arcsin(np.clip(m[2, 0], -1, 1)))), 1))
        rows.append(row)
    p.wait()
    return rows


def lens_share(rows: list, a: float, b: float, ref: tuple, tol: float = 12.0) -> float | None:
    """Share of [a, b] the presenter faces the lens (head within tol degrees of the reference pose)."""
    sel = [r for r in rows if a - 0.25 <= r["t"] <= b + 0.25]
    if not sel:
        return None
    ok = [r for r in sel if "yaw" in r and abs(r["yaw"] - ref[0]) <= tol and abs(r["pitch"] - ref[1]) <= tol]
    return len(ok) / len(sel)


def lens_pose(rows: list) -> tuple:
    """The pose held most often: the presenter delivering to the camera (the busiest 4-degree cell)."""
    yp = np.array([(r["yaw"], r["pitch"]) for r in rows if "yaw" in r])
    if not len(yp):
        return (0.0, 0.0)
    cells = np.round(yp / 4).astype(int)
    vals, counts = np.unique(cells, axis=0, return_counts=True)
    best = vals[counts.argmax()] * 4
    near = yp[(np.abs(yp - best) <= 6).all(1)]
    return tuple(float(v) for v in np.median(near, axis=0))


def selects_plan(spans_: list, handle: float = HANDLE, end: float | None = None) -> list:
    """Pieces of the raw for the selects file: each kept span with `handle` either side, overlaps merged.
    [{"in", "out", "at"}]: raw in/out and where the piece starts in the selects file."""
    pieces = []
    for a, b in spans_:
        a2, b2 = max(0.0, a - handle), b + handle
        if end is not None:
            b2 = min(b2, end)
        if pieces and a2 <= pieces[-1]["out"]:
            pieces[-1]["out"] = round(b2, 3)
        else:
            pieces.append({"in": round(a2, 3), "out": round(b2, 3)})
    t = 0.0
    for p in pieces:
        p["at"] = round(t, 3)
        t += p["out"] - p["in"]
    return pieces


def to_selects(pieces: list, t: float) -> float:
    """A raw time inside a piece -> its time in the selects file."""
    for p in pieces:
        if p["in"] - 1e-6 <= t <= p["out"] + 1e-6:
            return round(p["at"] + t - p["in"], 3)
    raise ValueError(f"{t:.3f}s is not inside any selected piece")


def write_selects(src, pieces: list, dst, rotate: int = 0, size: tuple = (1440, 2560), crf: int = 14) -> Path:
    """One upright file of the selected pieces (picture and sound), cut frame-exact from the camera original."""
    dst = Path(dst)
    args, parts = [], []
    for k, p in enumerate(pieces):
        args += ["-ss", f"{p['in']:.3f}", "-t", f"{p['out'] - p['in']:.3f}", "-i", str(src)]
        parts.append(f"[{k}:v]{ROTATE[rotate]}scale={size[0]}:{size[1]}:flags=lanczos,setsar=1,fps=30000/1001,"
                     f"trim=duration={p['out'] - p['in']:.3f},setpts=PTS-STARTPTS[v{k}];"
                     f"[{k}:a:0]atrim=duration={p['out'] - p['in']:.3f},asetpts=PTS-STARTPTS[a{k}]")
    graph = ";".join(parts) + ";" + "".join(f"[v{k}][a{k}]" for k in range(len(pieces))) \
        + f"concat=n={len(pieces)}:v=1:a=1[v][a]"
    subprocess.run([ffmpeg_bin(), "-v", "error", "-y", *args, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
                    "-c:a", "pcm_s16le", "-ar", "48000", str(dst)], check=True)
    return dst


def build(src, workdir, language: str = "ar", keep=(), drop=(), words=None, gaze: bool = True, log=print) -> dict:
    """The whole step: chunked transcript (cached in takes-words.json), voices, units, picks, and where he reads off
    the lens (gaze.json, cached); writes takes.json and takes.md in workdir. Returns the takes.json record."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    audio = _pcm(src)
    db = envelope(_pcm(src, "highpass=f=120,lowpass=f=4000"))
    cache = workdir / "takes-words.json"
    if words is None:
        if cache.exists():
            words = json.loads(cache.read_text(encoding="utf-8"))
        else:
            words = transcribe_chunks(audio, speech_chunks(db), language, log=log)
            cache.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    words = drop_loops([dict(w) for w in words])
    ref = mark_speaker(words, word_levels(words, db))
    us = units(words)
    verdicts = apply_overrides(pick(us), keep, drop)
    end = len(audio) / 16000
    sp = spans(us, verdicts, end=end)
    lens = [None] * len(us)
    if gaze:
        gpath = workdir / "gaze.json"
        if not gpath.exists():
            gpath.write_text(json.dumps(gaze_track(src, detect_rotation(src))))
        rows = json.loads(gpath.read_text())
        pose = lens_pose(rows)
        lens = [lens_share(rows, u[0]["start"], u[-1]["end"], pose) for u in us]
    cover = [[u[0]["start"], u[-1]["end"]] for u, v, ls in zip(us, verdicts, lens)
             if v["keep"] and ls is not None and ls < 0.5]
    rec = {"src": str(src), "presenter_db": round(ref, 1), "duration": round(end, 3),
           "units": [{"i": i, "start": u[0]["start"], "end": u[-1]["end"], "off": bool(u[0].get("off")),
                      "lens": None if ls is None else round(ls, 2), "text": " ".join(w["w"] for w in u), **v}
                     for i, (u, v, ls) in enumerate(zip(us, verdicts, lens))],
           "spans": sp, "cover": cover, "kept_s": round(sum(b - a for a, b in sp), 2)}
    (workdir / "takes.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    (workdir / "takes.md").write_text(report(us, verdicts, lens), encoding="utf-8")
    return rec
