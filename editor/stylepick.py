"""Style picker: read the footage and the talk, pick the editing style that fits, and plan variety, so no edit comes out
basic and the user never has to choose. Brand rules (a brand skill or pack) still decide everything branded; this
only picks the editing style and its rhythm.

    python -m editor style-pick <project>           # after analyze: writes style-plan.json, prints the plan
    python -m editor style-pick <project> --check   # before render: flags a plan that repeats or goes flat

Signals: the face boxes (faces.json: close-up or medium, headroom, how much the speaker moves), a few proxy frames
(a busy or clean, dark or light room), the transcript (words a second, and what it is about: tools, money, a story,
a product, steps), the silences, the length, and the creator profile's look when there is one.
"""
import json
import re
from pathlib import Path

import numpy as np

STYLES = {
    "rapid_visual": "Rapid visual explainer: split screen, a new visual on every phrase (capture with point, stock, "
                    "terminal / code_card / rank_list), short bold captions, a soft sound on every shot.",
    "minimal_story": "Minimal storytelling: slow camera moves (pull_back, vertigo) on the story beats, line_art "
                     "cards between, small serif captions, soft music, few sounds.",
    "kinetic_captions": "Kinetic transparent captions: word_stack on the words that carry each line, outline and "
                        "freeze_callout on punchlines, snap zooms on stressed words.",
    "data_explainer": "Clean data explainer: chart_grow, list_tracker, checklist, glass_type on the numbers, gentle "
                      "zooms, a sticker outline for the serious beat.",
    "energetic": "Energetic reel: beat_shake on the music, zoom_through between sections, motion_echo on big gestures, "
                 "digital_zoom snaps, a sticker outline on the punchline.",
}
# what each style draws on, by kind: camera moves, cut-out looks, type, cards, transitions
PALETTES = {
    "rapid_visual": {"cards": ["terminal", "code_card", "rank_list", "checklist"],
                     "type": ["word_stack", "glass_type"], "camera": ["digital_zoom", "zoom_through"],
                     "cutout": ["outline", "freeze_callout"], "transition": ["zoom_through"]},
    "minimal_story": {"cutout": ["outline"], "cards": ["line_art"],
                      "type": ["wall_text", "glass_type"], "camera": ["digital_zoom", "pull_back", "vertigo"],
                      "transition": ["zoom_through"]},
    "kinetic_captions": {"type": ["word_stack", "wall_text", "headline_wall"], "cutout": ["outline", "freeze_callout"],
                         "camera": ["digital_zoom", "vertigo"], "cards": ["checklist"],
                         "transition": ["zoom_through"]},
    "data_explainer": {"cards": ["chart_grow", "list_tracker", "checklist", "rank_list"],
                       "type": ["glass_type", "wall_text"], "camera": ["digital_zoom", "pull_back"],
                       "cutout": ["outline"], "transition": ["zoom_through"]},
    "energetic": {"camera": ["beat_shake", "digital_zoom", "vertigo", "zoom_through"],
                  "cutout": ["outline", "motion_echo", "freeze_callout"], "type": ["word_stack", "wall_text"],
                  "transition": ["zoom_through"], "cards": ["rank_list"]},
}
TOPICS = {
    "tools": r"github|repo|code|claude|chatgpt|codex|\bai\b|app|website|site|tool|prompt|software|install|"
             r"برنامج|تطبيق|موقع|كود|ريبو|ذكاء|اداة|أداة",
    "money": r"\$|%|price|profit|revenue|market|stock|invest|million|سعر|ريال|دينار|دولار|أرباح|ارباح|سوق|سهم|"
             r"استثمار|مليون|نسبة",
    "story": r"\bi was\b|when i|years ago|my first|i remember|سنة|سنين|قصة|كنت|صار|أول مرة|اول مرة|تذكر",
    "product": r"buy|product|order|launch|offer|new|منتج|اشتر|شراء|طلب|جديد|عرض",
    "steps": r"first|second|third|step|number one|اولا|أولا|ثانيا|ثالثا|خطوة|الأول|الثاني",
}
# effects that need room the footage may not have
NEEDS_HEADROOM = {"wall_text", "headline_wall", "orbit"}
NEEDS_MOVEMENT = {"motion_echo"}
REPEAT_GAP = 10.0  # the same effect again sooner than this reads as a repeat


def footage(proj: Path) -> dict:
    """Facts about the picture: shot (close / medium), headroom (0-1), movement (0-1), room (busy, dark)."""
    out = {"shot": "medium", "headroom": 0.2, "movement": 0.0, "busy": 0.0, "dark": False}
    try:
        f = json.loads((proj / "faces.json").read_text())
        boxes = np.array([s["box"] for s in f["samples"] if s.get("box")], np.float32)
    except (OSError, ValueError, KeyError):
        boxes = np.zeros((0, 4), np.float32)
    if len(boxes):
        h = np.median(boxes[:, 3] - boxes[:, 1])
        out["shot"] = "close" if h > 0.38 else "medium"
        out["headroom"] = float(np.median(boxes[:, 1]))
        cx = (boxes[:, 0] + boxes[:, 2]) / 2
        out["movement"] = float(min(1.0, (np.std(cx) + np.mean(np.abs(np.diff(cx))) * 4) * 6)) if len(cx) > 2 else 0.0
    room = _room(proj, boxes)
    out.update(room)
    return out


def _room(proj: Path, boxes) -> dict:
    """How busy and how dark the background is, from a few proxy frames (the face box masked out)."""
    try:
        meta = json.loads((proj / "project.json").read_text())
        proxy = proj / meta["proxy"]
        dur = float(meta["probe"]["duration"])
    except (OSError, ValueError, KeyError):
        return {}
    import subprocess

    import cv2
    vals, lum = [], []
    for k in range(1, 6):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{dur * k / 6:.2f}", "-i", str(proxy), "-frames:v", "1",
                            "-vf", "scale=180:320,format=gray", "-f", "rawvideo", "-"], capture_output=True)
        if len(r.stdout) != 180 * 320:
            continue
        g = np.frombuffer(r.stdout, np.uint8).reshape(320, 180)
        mask = np.ones_like(g, bool)
        if len(boxes):
            x0, y0, x1, y1 = np.median(boxes, axis=0)
            mask[int(y0 * 320):, int(x0 * 180):int(x1 * 180)] = False  # the speaker, down to the frame bottom
        edges = cv2.Canny(g, 60, 140) > 0
        vals.append(edges[mask].mean())
        lum.append(g[mask].mean() / 255)
    if not vals:
        return {}
    return {"busy": float(min(1.0, np.mean(vals) * 8)), "dark": bool(np.mean(lum) < 0.33)}


def talk(proj: Path) -> dict:
    """Facts about the speech: words a second, the share of pauses, length, language and the topic scores."""
    try:
        tr = json.loads((proj / "transcript.json").read_text(encoding="utf-8"))
        words = tr.get("words") or []
    except (OSError, ValueError):
        tr, words = {}, []
    text = " ".join(w["w"] for w in words).lower()
    dur = (words[-1]["end"] - words[0]["start"]) if len(words) > 1 else 0.0
    spoken = sum(max(0.0, w["end"] - w["start"]) for w in words if w.get("end") is not None and w.get("start") is not None)
    scores = {k: len(re.findall(p, text)) / max(1, len(words)) * 100 for k, p in TOPICS.items()}
    return {"wps": round(len(words) / dur, 2) if dur else 0.0, "duration": round(dur, 1),
            "edit_s": round(min(dur, spoken * 0.95), 1),  # about how long the tight cut runs (retakes go, breaths stay)
            "language": tr.get("language"), "topics": {k: round(v, 2) for k, v in scores.items()}}


def choose(pic: dict, speech: dict, look: str = "") -> tuple:
    """(style, reasons). The profile's look leans the choice; the talk decides it; the picture rules out what it
    cannot carry."""
    t, why = speech.get("topics", {}), []
    look = look.lower()
    score = {s: 0.0 for s in STYLES}
    score["rapid_visual"] += 3 * t.get("tools", 0) + 1.5 * t.get("steps", 0)
    score["data_explainer"] += 3 * t.get("money", 0) + t.get("steps", 0)
    score["minimal_story"] += 3 * t.get("story", 0) + (1.0 if speech.get("wps", 3) < 2.2 else 0)
    score["kinetic_captions"] += 1.5 + 2 * t.get("product", 0) + (0.8 if pic.get("shot") == "close" else 0)
    score["energetic"] += 2 * pic.get("movement", 0) + (1.0 if speech.get("wps", 0) > 3.2 else 0)
    if re.search(r"minimal|calm|cinematic|clean|هادئ|بسيط|سينمائي", look):
        score["minimal_story"] += 2
    if re.search(r"bold|energ|high|fun|playful|حماس|قوي|مرح", look):
        score["energetic"] += 2
        score["kinetic_captions"] += 1
    if re.search(r"corporate|trust|finance|رسمي|مالي", look):
        score["data_explainer"] += 2
    style = max(score, key=score.get)
    top = max(t, key=t.get) if t else None
    if top and t[top] > 0:
        why.append(f"the talk is mostly about {top}")
    why.append(f"{pic.get('shot', 'medium')} shot, {'a lot of' if pic.get('movement', 0) > 0.5 else 'little'} movement")
    if pic.get("busy", 0) > 0.5:
        why.append("a busy room: a sticker outline lifts the speaker off it")
    if look:
        why.append("the creator profile's look")
    return style, why


def plan(proj, look: str = "") -> dict:
    proj = Path(proj)
    pic, speech = footage(proj), talk(proj)
    style, why = choose(pic, speech, look)
    pal = {k: [e for e in v if not (e in NEEDS_HEADROOM and pic["headroom"] < 0.08)
               and not (e in NEEDS_MOVEMENT and pic["movement"] < 0.2)] for k, v in PALETTES[style].items()}
    dur = speech.get("edit_s") or speech["duration"] or 60.0
    n_fx = int(max(3, min(14, round(dur / 9))))
    return {"style": style, "describe": STYLES[style], "why": why, "footage": pic, "talk": speech,
            "palette": pal, "effects": n_fx,
            "rhythm": {"hook": "something moves or lands in the first second: a zoom, a word, a visual",
                       "change_every_s": [1.5, 3.0] if style != "minimal_story" else [3.0, 6.0],
                       "effect_every_s": round(dur / n_fx, 1), "rehook_at_s": round(dur * 0.5, 1),
                       "end": "abrupt on the last useful line, or loop the last frame into the first"},
            "variety": [f"never the same effect within {REPEAT_GAP:.0f} s, none more than twice in the video",
                        "alternate kinds (camera, cut-out, type, cards) so two neighbours never share a kind",
                        f"at least {min(n_fx, 5)} different effect types",
                        "one signature moment near the middle: the strongest effect of the palette"],
            "brand": "a brand skill or pack decides colours, fonts, sounds and anything it forbids; it wins"}


def check(edit: dict, style_plan: dict | None = None) -> list:
    """Problems with an edit.json against the variety rules: repeats, too few kinds, a flat stretch, no hook."""
    fx = sorted(edit.get("fx", []), key=lambda f: f.get("at", 0))
    gfx = sorted(edit.get("graphics", []) + edit.get("broll", []), key=lambda g: g.get("at", 0))
    total = sum(max(0.0, s.get("out", 0) - s.get("in", 0)) for s in edit.get("segments", [])) or None
    probs = []
    types = [f["type"] for f in fx]
    for x, y in zip(fx, fx[1:]):
        if x["type"] == y["type"] and y["at"] - x["at"] < REPEAT_GAP:
            probs.append(f"{x['type']} twice within {REPEAT_GAP:.0f} s ({x['at']:.1f}s and {y['at']:.1f}s)")
    for t in set(types):
        if types.count(t) > 2:
            probs.append(f"{t} used {types.count(t)} times (at most twice)")
    want = min((style_plan or {}).get("effects", 5), 5)
    if len(set(types)) < want:
        probs.append(f"only {len(set(types))} different effect types; aim for {want}")
    events = sorted([f["at"] for f in fx] + [g["at"] for g in gfx] + [t.get("at", 0) for t in edit.get("transitions", [])
                                                                       if isinstance(t, dict)])
    if not events or events[0] > 1.5:
        probs.append("nothing lands in the first 1.5 s: open on a zoom, a word or a visual")
    marks = [0.0] + events + ([total] if total else [])
    for a, b in zip(marks, marks[1:]):
        if b - a > 15:
            probs.append(f"{a:.1f}-{b:.1f}s: {b - a:.0f} s with nothing new on screen")
    return probs


def cmd(a) -> None:
    proj = Path(a.project)
    look = ""
    try:
        from . import profile
        look = profile.load() or ""
    except Exception:
        pass
    if a.check:
        sp = json.loads((proj / "style-plan.json").read_text()) if (proj / "style-plan.json").exists() else None
        probs = check(json.loads((proj / "edit.json").read_text(encoding="utf-8")), sp)
        print("\n".join(f"VARIETY: {p}" for p in probs) or "variety ok")
        raise SystemExit(1 if probs else 0)
    p = plan(proj, look)
    (proj / "style-plan.json").write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"style: {p['style']} ({'; '.join(p['why'])})\n{p['describe']}\n"
          f"about {p['effects']} effects, one every ~{p['rhythm']['effect_every_s']} s, from: "
          + ", ".join(f"{k}: {'/'.join(v)}" for k, v in p["palette"].items() if v))
