"""edit.json: the single source of truth for an edit."""
import hashlib
import json
import math
from pathlib import Path

from .config import FORMATS
from .score import CALM_SFX, PLAYFUL_SFX

GRAPHIC_TYPES = ("hook", "lower_third", "list", "stat", "quote", "ticker", "headline", "kinetic",
                 "credit", "chapter", "outro", "custom", "stack", "card", "badge", "bars", "leak", "endcard",
                 "tiles", "poll", "balance", "wave", "mark", "sticker", "title", "flag")
CAPTION_MODES = ("source", "ar", "en", "bilingual")
SFX_KINDS = ("whoosh", "pop", "thump", "hit", "tick", "riser", "ding", "shutter", "glitch", "coin",
             *PLAYFUL_SFX, *CALM_SFX)
LOOK_TYPES = ("bars", "vignette", "blur")
SFX_VOLUME = 0.35  # gain on every sound effect; lower it when the effects sit too loud over the music
KINETIC_FX = ("words", "pop", "shine", "neon", "bloom")
DESK_TYPES = ("profile", "steps", "themes", "chart", "image", "balance")
DESK_MOODS = ("brand", "bull", "bear")
PERSON_FX = ("glow", "spotlight")
TRANSITIONS = ("flash", "whip", "zoom", "dip", "glitch", "settle", "leak", "sweep")
BROLL_MAX = 10  # seconds; most presets hold B-roll 4-9 s
BROLL_FRAMES = ("full", "top")  # top: the shot fills the upper half, the speaker stays in the lower half
GRAPHIC_FIELDS = {"hook": ("text",), "lower_third": ("name",), "stat": ("value", "label"), "quote": ("text",),
                  "ticker": ("name", "ticker"), "headline": ("text",), "kinetic": ("text",), "credit": ("text",),
                  "chapter": ("text",)}


def new_plan(segments: list, fmt: str = "9:16", style: str = "default") -> dict:
    return {
        "version": 1, "format": fmt, "style": style, "segments": segments,
        "broll": [], "graphics": [],
        "captions": {"enabled": True, "mode": "source", "words_per_line": [2, 4]},
        "music": {"src": None, "credit": None},
        "sfx": [], "looks": [], "retouch": 0.3, "hook": {"cold_open": None}, "notes": [],
    }


def seg_len(s: dict) -> float:
    """Timeline length of a segment: its source span played at its speed."""
    return (s["out"] - s["in"]) / s.get("speed", 1.0)


def timeline_duration(plan: dict) -> float:
    return round(sum(seg_len(s) for s in plan["segments"]), 3)


def segments_hash(plan: dict) -> str:
    """Hash of the cut. Private keys the render adds (`_grade`) are left out, so a graded render keeps
    work/captions.json and its hand edits instead of rebuilding it."""
    segs = [{k: v for k, v in s.items() if not k.startswith("_")} if isinstance(s, dict) else s
            for s in plan["segments"]]
    return hashlib.sha1(json.dumps(segs, sort_keys=True).encode()).hexdigest()


def _num(x) -> bool:
    """True for a finite int/float (bool, NaN and inf do not count)."""
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return False
    try:
        return math.isfinite(x)
    except OverflowError:
        return False


def _list(plan: dict, key: str):
    """(items, error): a missing key is []; a non-list value is an error."""
    if key not in plan:
        return [], None
    value = plan[key]
    if not isinstance(value, list):
        return [], f"{key} must be a list"
    return value, None


def _entries(plan: dict, key: str, errs: list):
    """Yield (i, entry) for dict entries of plan[key]; report anything else."""
    items, err = _list(plan, key)
    if err:
        errs.append(err)
    for i, item in enumerate(items):
        if isinstance(item, dict):
            yield i, item
        else:
            errs.append(f"{key}[{i}]: must be an object")


def _text(x) -> bool:
    return isinstance(x, str) and x != ""


def validate(plan) -> list:
    """Return a list of error strings for any JSON-shaped input; never raises."""
    if not isinstance(plan, dict):
        return ["plan must be an object"]
    errs = []
    fmt = plan.get("format")
    if not isinstance(fmt, str) or fmt not in FORMATS:
        errs.append(f"format must be one of {sorted(FORMATS)}")
    if "fx" in plan:
        if not isinstance(plan["fx"], list):
            errs.append("fx must be a list")
        else:
            from .fx.apply import check as check_fx
            errs += check_fx(plan["fx"])

    segments = plan.get("segments")
    if not isinstance(segments, list):
        errs.append("segments must be a list")
        segments = []
    elif not segments:
        errs.append("segments is empty")

    total, cuts = 0.0, []
    for i, s in enumerate(segments):
        if not isinstance(s, dict):
            errs.append(f"segments[{i}]: must be an object")
            continue
        if not _text(s.get("src")):
            errs.append(f"segments[{i}]: src must be a non-empty string")
        if not (_num(s.get("in")) and _num(s.get("out"))):
            errs.append(f"segments[{i}]: in/out must be numbers")
        elif s["out"] <= s["in"]:
            errs.append(f"segments[{i}]: out must be after in")
        else:
            speed = s.get("speed", 1.0)
            span = (float(s["out"]) - float(s["in"])) / (speed if _num(speed) and speed > 0 else 1.0)
            if not math.isfinite(span):
                errs.append(f"segments[{i}]: in/out span is too large")
            else:
                total += span
                cuts.append(round(total, 3))
        if "push" in s and not (_num(s["push"]) and 1.0 <= s["push"] <= 2.5):
            errs.append(f"segments[{i}]: push must be between 1.0 and 2.5")
        if "push_dur" in s and not (_num(s["push_dur"]) and s["push_dur"] > 0):
            errs.append(f"segments[{i}]: push_dur must be a positive number of seconds")
        if "zoom" in s and not (_num(s["zoom"]) and 1.0 <= s["zoom"] <= 2.5):
            errs.append(f"segments[{i}]: zoom must be between 1.0 and 2.5")
        if "focus" in s and not (isinstance(s["focus"], list) and len(s["focus"]) == 2
                                 and all(_num(v) and 0 <= v <= 1 for v in s["focus"])):
            errs.append(f"segments[{i}]: focus must be [x, y], fractions of the frame")
        if "speed" in s and not (_num(s["speed"]) and 0.25 <= s["speed"] <= 4.0):
            errs.append(f"segments[{i}]: speed must be between 0.25 and 4")
        if "mute" in s and not isinstance(s["mute"], bool):
            errs.append(f"segments[{i}]: mute must be true or false")
    if not math.isfinite(total):
        errs.append("segments: timeline duration is too large")
        total = 0.0
    total = round(total, 3)

    for key in ("broll", "graphics", "looks", "desks", "person", "overlays"):
        for i, item in _entries(plan, key, errs):
            at, dur = item.get("at"), item.get("dur")
            if not (_num(at) and _num(dur)):
                errs.append(f"{key}[{i}]: at/dur must be numbers")
            else:
                item_end = float(at) + float(dur)
                if not math.isfinite(item_end):
                    errs.append(f"{key}[{i}]: at/dur span is too large")
                elif dur <= 0 or at < 0 or item_end > total + 0.01:
                    errs.append(f"{key}[{i}]: must fit inside the {total:.2f}s timeline")
            if key == "broll":
                if not item.get("query"):
                    errs.append(f"broll[{i}]: query is required")
                if item.get("src_in") is not None and not (_num(item["src_in"]) and item["src_in"] >= 0):
                    errs.append(f"broll[{i}]: src_in must be a number >= 0")
                if item.get("frame", "full") not in BROLL_FRAMES:
                    errs.append(f"broll[{i}]: frame must be one of {BROLL_FRAMES}")
                if item.get("split_y") is not None and not (_num(item["split_y"]) and 0 <= item["split_y"] <= 0.5):
                    errs.append(f"broll[{i}]: split_y must be between 0 and 0.5")
                split = item.get("frame") == "top"  # the speaker stays on screen in the lower half
                if _num(at) and at < 1.5 and not item.get("open") and not split:  # open: unusable speaker at the start
                    errs.append(f"broll[{i}]: at must be >= 1.5 (face on screen first), or set open: true")
                if _num(dur) and not 0.5 <= dur <= BROLL_MAX:
                    errs.append(f"broll[{i}]: dur must be between 0.5 and {BROLL_MAX} seconds")
            if key == "looks":
                if item.get("type") not in LOOK_TYPES:
                    errs.append(f"looks[{i}]: type must be one of {LOOK_TYPES}")
                if _num(dur) and dur < 1.0:
                    errs.append(f"looks[{i}]: dur must be at least 1 second")
            if key == "person":
                if item.get("type") not in PERSON_FX:
                    errs.append(f"person[{i}]: type must be one of {PERSON_FX}")
                for j, b in _entries(plan, "broll", []):
                    if _num(b.get("at")) and _num(b.get("dur")) and _num(at) and _num(dur) and \
                            b["at"] < at + dur and at < b["at"] + b["dur"]:
                        errs.append(f"person[{i}]: overlaps broll[{j}]; person effects need the speaker on screen")
            if key == "desks":
                errs += [f"desks[{i}]: {e}" for e in _desk_errors(item)]
                for other in ("graphics", "broll"):
                    for j, g in _entries(plan, other, []):
                        if g.get("type") == "leak":  # transition flashes ride over the desk's edges
                            continue
                        if _num(g.get("at")) and _num(g.get("dur")) and _num(at) and _num(dur) and \
                                g["at"] < at + dur and at < g["at"] + g["dur"]:
                            errs.append(f"desks[{i}]: overlaps {other}[{j}]; the desk panel replaces it")
            if key == "graphics":
                kind = item.get("type")
                if kind not in GRAPHIC_TYPES:
                    errs.append(f"graphics[{i}]: type must be one of {GRAPHIC_TYPES}")
                if kind in ("stack", "card") and not (isinstance(item.get("lines"), list) and item["lines"]
                                                      and all(isinstance(x, dict) and _text(x.get("text")) for x in item["lines"])):
                    errs.append(f"graphics[{i}]: {kind} needs 'lines', a list of {{text, ...}}")
                if kind == "bars" and not (isinstance(item.get("values"), list) and len(item["values"]) == 2
                                           and all(isinstance(v, dict) and _num(v.get("value")) for v in item["values"])):
                    errs.append(f"graphics[{i}]: bars needs 'values', two {{value, label}} entries")
                if kind == "title" and not _text(item.get("text")):
                    errs.append(f"graphics[{i}]: title needs 'text'")
                if kind == "custom" and not _text(item.get("dir")):
                    errs.append(f"graphics[{i}]: custom graphics need a 'dir'")
                if kind == "list" and not (isinstance(item.get("items"), list) and item["items"]
                                           and all(_text(x) for x in item["items"])):
                    errs.append(f"graphics[{i}]: list needs 'items', a non-empty list of non-empty strings")
                if kind == "stat" and item.get("dir") is not None and item["dir"] not in ("up", "down"):
                    errs.append(f"graphics[{i}]: stat 'dir' must be 'up' or 'down'")
                if kind == "kinetic" and item.get("fx", "words") not in KINETIC_FX:
                    errs.append(f"graphics[{i}]: kinetic 'fx' must be one of {KINETIC_FX}")
                if item.get("place") in ("behind", "hands"):  # cut-out layers come from the talking head
                    for j, b in _entries(plan, "broll", []):
                        if _num(b.get("at")) and _num(b.get("dur")) and _num(at) and _num(dur) and \
                                b["at"] < at + dur and at < b["at"] + b["dur"]:
                            errs.append(f"graphics[{i}]: place '{item['place']}' overlaps broll[{j}]; the speaker's "
                                        "cut-out would float over the B-roll")
                if kind == "kinetic" and item.get("place") not in (None, "slot", "behind", "center", "hands"):
                    errs.append(f"graphics[{i}]: kinetic 'place' must be 'slot', 'behind', 'hands' or 'center'")
                if kind == "kinetic" and item.get("hi") is not None and not (
                        isinstance(item["hi"], list) and all(_text(x) for x in item["hi"])):
                    errs.append(f"graphics[{i}]: kinetic 'hi' must be a list of non-empty strings")
                if kind not in ("endcard", "leak") and _num(at) and _num(dur) and abs(at) < 1e6 and abs(dur) < 1e6:
                    for c in cuts[:-1]:  # within 3 frames of a cut is never intended: a ghost or a flash on the other shot
                        if 0.005 < at + dur - c <= 0.1:
                            errs.append(f"graphics[{i}]: ends {at + dur - c:.3f}s after the cut at {c:.3f}s; end it on "
                                        "the cut (it would ghost onto the next shot)")
                        if 0.005 < c - at <= 0.1:
                            errs.append(f"graphics[{i}]: starts {c - at:.3f}s before the cut at {c:.3f}s; start it on "
                                        "the cut (it would flash on the previous shot)")
                if kind == "endcard" and _num(at) and _num(dur) and abs(at) < 1e6 and abs(dur) < 1e6 and total \
                        and at + dur < total - 0.02:
                    errs.append(f"graphics[{i}]: the end card ends at {at + dur:.3f}s but the video runs to "
                                f"{total:.3f}s; its last frames would show the footage under it")
                for field in GRAPHIC_FIELDS.get(kind, ()):
                    if not _text(item.get(field)):
                        errs.append(f"graphics[{i}]: {kind} needs a non-empty string '{field}'")

    if "retouch" in plan and not (_num(plan["retouch"]) and 0 <= plan["retouch"] <= 0.6):
        errs.append("retouch must be between 0 and 0.6 (0.3-0.4 is natural)")

    lufs = plan.get("music", {}).get("lufs") if isinstance(plan.get("music"), dict) else None
    if lufs is not None and not (_num(lufs) and -45 <= lufs <= -18):
        errs.append("music.lufs must be between -45 and -18 (default -33; lower is quieter)")
    g = plan.get("grade")
    if g is not None:  # house rule (2026-10-25): footage keeps its camera colour on every edit
        errs.append("grade is refused: the footage's colour never changes, under any condition (house rule); "
                    "remove grade from edit.json")
    if g is not None and not (isinstance(g, dict) and g.get("look", "clean") in ("clean", "punchy", "cinematic")):
        errs.append("grade must be {\"look\": \"clean\"|\"punchy\"|\"cinematic\"}")
    elif g is not None and "curves" in g and not (
            isinstance(g["curves"], dict) and g["curves"] and set(g["curves"]) <= {"r", "g", "b", "all"}
            and all(isinstance(v, list) and len(v) >= 2 and all(isinstance(q, list) and len(q) == 2 and
                                                                 all(_num(c) and 0 <= c <= 255 for c in q) for q in v)
                    for v in g["curves"].values())):
        errs.append("grade.curves must be {r|g|b|all: [[in, out], ...]} with values 0-255")
    for i, o in _entries(plan, "overlays", errs):
        errs += [f"overlays[{i}]: {e}" for e in _overlay_errors(o)]
    music = plan.get("music") if isinstance(plan.get("music"), dict) else {}
    if "end" in music and not (_num(music["end"]) and music["end"] > 0):
        errs.append("music.end must be a positive time (timeline seconds where the bed stops)")
    if "start" in music and not (_num(music["start"]) and music["start"] >= 0):
        errs.append("music.start must be 0 or more (seconds into the track)")
    duck = music.get("duck", {})
    if not isinstance(duck, dict) or set(duck) - {"threshold", "ratio", "release"} or not all(
            _num(duck[k]) for k in duck) or not (0.001 <= duck.get("threshold", 0.02) <= 1
                                                 and 1 <= duck.get("ratio", 8) <= 20 and 20 <= duck.get("release", 350) <= 2000):
        errs.append("music.duck must be {threshold 0.001-1, ratio 1-20, release 20-2000 ms}; ratio 2-3 is a light dip")
    if "sfx_volume" in plan and not (_num(plan["sfx_volume"]) and 0 <= plan["sfx_volume"] <= 1):
        errs.append(f"sfx_volume must be between 0 and 1 (default {SFX_VOLUME})")

    captions = plan.get("captions", {})
    if not isinstance(captions, dict):
        errs.append("captions must be an object")
    else:
        if captions.get("mode", "source") not in CAPTION_MODES:
            errs.append(f"captions.mode must be one of {CAPTION_MODES}")
        srcs = {s["src"] for s in segments if isinstance(s, dict) and _text(s.get("src"))}
        if captions.get("enabled") and len(srcs) > 1:
            errs.append("captions support one source clip per project for now")

    for i, x in _entries(plan, "transitions", errs):
        if x.get("type") not in TRANSITIONS:
            errs.append(f"transitions[{i}]: type must be one of {TRANSITIONS}")
        lo_ok = (lambda a: 0 <= a) if x.get("type") == "settle" else (lambda a: 0 < a)
        if not (_num(x.get("at")) and lo_ok(x["at"]) and x["at"] < total):
            errs.append(f"transitions[{i}]: at must be a time inside the timeline (a cut)")

    for i, x in _entries(plan, "sfx", errs):
        if not _num(x.get("at")):
            errs.append(f"sfx[{i}]: at must be a number")
        elif not 0 <= x["at"] <= total + 0.01:
            errs.append(f"sfx[{i}]: at must be inside the timeline")
        if x.get("kind") not in SFX_KINDS:
            errs.append(f"sfx[{i}]: kind must be one of {SFX_KINDS}")
        if x.get("file") is not None and not _text(x.get("file")):
            errs.append(f"sfx[{i}]: file must be a path to a sound file")
        if x.get("align") not in (None, "peak", "start"):
            errs.append(f"sfx[{i}]: align must be 'peak' or 'start'")
        if x.get("gain") is not None and not (_num(x["gain"]) and 0 <= x["gain"] <= 2):
            errs.append(f"sfx[{i}]: gain must be between 0 and 2")
    return errs


def _texts_ok(x, lo: int, hi: int) -> bool:
    return isinstance(x, list) and lo <= len(x) <= hi and all(_text(v) for v in x)


def _desk_errors(item: dict) -> list:
    errs = []
    if _num(item.get("at")) and item["at"] < 1.5:
        errs.append("at must be >= 1.5 (face on screen first)")
    if _num(item.get("dur")) and item["dur"] < 2:
        errs.append("dur must be at least 2 seconds")
    if item.get("mood", "brand") not in DESK_MOODS:
        errs.append(f"mood must be one of {DESK_MOODS}")
    card = item.get("card")
    if not isinstance(card, dict) or card.get("type") not in DESK_TYPES:
        return errs + [f"card must be an object with type one of {DESK_TYPES}"]
    t = card["type"]
    need = {"profile": ("ticker",), "steps": ("title",), "themes": ("title",), "chart": ("name", "value"),
            "image": ("src",)}.get(t, ())
    errs += [f"{t} card needs a non-empty string '{f}'" for f in need if not _text(card.get(f))]
    if t == "profile":
        stats = card.get("stats", [])
        if not (isinstance(stats, list) and len(stats) <= 3 and all(
                isinstance(x, dict) and _text(x.get("value")) and _text(x.get("label")) for x in stats)):
            errs.append("profile 'stats' must be up to 3 objects with 'value' and 'label'")
        if card.get("tags") is not None and not _texts_ok(card["tags"], 1, 4):
            errs.append("profile 'tags' must be 1-4 non-empty strings")
        if card.get("color") not in (None, "up", "down"):
            errs.append("profile 'color' must be 'up' or 'down'")
    if t == "steps" and not _texts_ok(card.get("items"), 2, 4):
        errs.append("steps 'items' must be 2-4 non-empty strings")
    if t == "themes" and not (isinstance(card.get("items"), list) and 2 <= len(card["items"]) <= 4 and all(
            isinstance(x, dict) and _text(x.get("title")) for x in card["items"])):
        errs.append("themes 'items' must be 2-4 objects with a 'title'")
    if t == "chart":
        pts = card.get("points")
        if not (isinstance(pts, list) and len(pts) >= 2 and all(_num(x) for x in pts)):
            errs.append("chart 'points' must be at least 2 numbers (real data from the user, never invented)")
        if card.get("dir") not in (None, "up", "down"):
            errs.append("chart 'dir' must be 'up' or 'down'")
    return errs


def _overlay_errors(o: dict) -> list:
    errs = []
    if not _text(o.get("file")):
        errs.append("file must be a path to a clip or image")
    if o.get("key") not in (None, "alpha", "green"):
        errs.append("key must be 'alpha' or 'green'")
    if o.get("color") is not None and not (isinstance(o["color"], str) and len(o["color"].lstrip("#")) == 6):
        errs.append("color must be a hex colour like '#00ff00'")
    for f in ("x", "y"):
        if f in o and not (_num(o[f]) and -0.5 <= o[f] <= 1.5):
            errs.append(f"{f} must be a fraction of the frame (-0.5 to 1.5)")
    if "w" in o and not (_num(o["w"]) and 0.05 <= o["w"] <= 3):
        errs.append("w must be between 0.05 and 3 (fraction of the frame width)")
    if "src_in" in o and not (_num(o["src_in"]) and o["src_in"] >= 0):
        errs.append("src_in must be 0 or more")
    if o.get("layer") not in (None, "over", "under"):
        errs.append("layer must be 'over' or 'under' (the graphics)")
    if "flip" in o and not isinstance(o["flip"], bool):
        errs.append("flip must be true or false")
    return errs


def _check(plan) -> None:
    errs = validate(plan)
    if errs:
        raise ValueError("edit.json is invalid:\n- " + "\n- ".join(errs))


def load(path) -> dict:
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    _check(plan)
    return plan


def save(path, plan: dict) -> None:
    _check(plan)
    Path(path).write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
