"""Scored self-review: Claude looks at every graphic's frames, scores it out of 10, and re-renders anything under 8.

`critique <project>` writes one strip per graphic, desk, B-roll and look (`<project>/review/item-NN.jpg`: entrance,
landing, middle and exit frames with timecodes) and `<project>/review/scores.json` with a null score for each.
Claude views each strip once, fills `score` (1-10) and `notes` against RUBRIC, fixes edit.json for anything under
PASS, re-renders and runs `critique` again (scores of unchanged items are kept). At most MAX_ROUNDS rounds; then
`critique <project> --check` must pass or the leftovers go to the user as open items.
"""
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PASS = 8
MAX_ROUNDS = 2
RUBRIC = [
    "Readable at phone size in under a second; strong hierarchy (one thing is clearly the headline).",
    "Not AI slop: no centred all-caps text on a generic gradient, no glow on everything, no stock-template look; "
    "uses the brand's fonts, colours and the studied reference style.",
    "Placed with intent: off the face, inside the safe zone, aligned to the layout grid, not fighting the captions.",
    "Motion feels physical: it lands (spring settle) on the spoken word, one element at a time, holds, exits cleanly.",
    "Every word and number is true to the transcript or the brief; nothing invented, no typos, correct Arabic shaping.",
    "No dead or broken frames: no blank card, no half-loaded font, no flash, no frozen hold, no leak at the cut.",
]
KINDS = ("graphics", "desks", "broll", "looks")


def items(plan: dict) -> list:
    out = []
    for kind in KINDS:
        for i, g in enumerate(plan.get(kind, [])):
            if "at" in g and "dur" in g:
                label = g.get("type") or g.get("card", {}).get("type") or g.get("query") or kind
                out.append({"key": f"{kind}[{i}]", "kind": kind, "label": str(label), "at": float(g["at"]),
                            "dur": float(g["dur"]), "spec": json.dumps(g, sort_keys=True, ensure_ascii=False)})
    return sorted(out, key=lambda x: x["at"])


def sample_times(at: float, dur: float) -> list:
    """Entrance (two frames), landing, middle, late hold and the exit."""
    ts = [at + 0.12, at + min(0.45, dur * 0.2), at + min(0.9, dur * 0.35), at + dur * 0.55, at + dur - 0.6,
          at + dur - 0.12]
    return [round(max(at, min(t, at + dur - 0.05)), 3) for t in ts]


def strip(video, times: list, out, title: str, width: int = 270) -> Path:
    frames = []
    for t in times:
        p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                            "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        from io import BytesIO
        frames.append(Image.open(BytesIO(p.stdout)).convert("RGB") if p.stdout else Image.new("RGB", (width, 480)))
    h = max(f.height for f in frames)
    sheet = Image.new("RGB", (width * len(frames), h + 34), (16, 16, 18))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for k, (f, t) in enumerate(zip(frames, times)):
        sheet.paste(f, (k * width, 34))
        d.text((k * width + 6, 18), f"{t:.2f}s", fill=(255, 210, 0), font=font)
    d.text((6, 3), title, fill=(255, 255, 255), font=font)
    sheet.save(out, quality=88)
    return Path(out)


def build(project, video=None) -> Path:
    project = Path(project)
    plan = json.loads((project / "edit.json").read_text(encoding="utf-8"))
    video = Path(video) if video else project / "out" / "final.mp4"
    rev = project / "review"
    rev.mkdir(exist_ok=True)
    path = rev / "scores.json"
    old = {s["key"]: s for s in json.loads(path.read_text())["items"]} if path.exists() else {}
    rounds = (json.loads(path.read_text()).get("round", 0) + 1) if path.exists() else 1
    rows = []
    for n, it in enumerate(items(plan)):
        sheet = strip(video, sample_times(it["at"], it["dur"]), rev / f"item-{n:02d}.jpg",
                      f"{it['key']} {it['label']} @ {it['at']:.2f}s for {it['dur']:.1f}s")
        prev = old.get(it["key"])
        keep = prev and prev.get("spec") == it["spec"] and prev.get("score") is not None
        rows.append({**it, "sheet": str(sheet.relative_to(project)), "score": prev["score"] if keep else None,
                     "notes": prev.get("notes", "") if keep else "", "tries": (prev or {}).get("tries", 0) + (0 if keep else 1)})
    path.write_text(json.dumps({"round": rounds, "pass": PASS, "rubric": RUBRIC, "items": rows}, indent=1,
                               ensure_ascii=False), encoding="utf-8")
    return path


def check(project) -> list:
    """Problems left: unscored items, items under PASS."""
    data = json.loads((Path(project) / "review" / "scores.json").read_text())
    probs = []
    for it in data["items"]:
        if it["score"] is None:
            probs.append(f"{it['key']} ({it['label']} @ {it['at']:.1f}s) not scored")
        elif it["score"] < PASS:
            probs.append(f"{it['key']} ({it['label']} @ {it['at']:.1f}s) scored {it['score']}: {it['notes']}")
    return probs
