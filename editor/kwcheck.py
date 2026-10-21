"""Keyword check before a full render: each text graphic composited over the real frame under it (talking head
through its framing, or the B-roll clip), with the real hand or person cut-out on top for place "hands"/"behind",
at three moments of its hold (just landed, settled, about to leave): hands and held objects move during a hold.

Writes qc/kw/NN.png per graphic (three panels) and qc/kw/sheetN.jpg (six graphics per sheet)."""
import subprocess
from pathlib import Path

from . import cutout, editjson, layout
from .config import FORMATS
from .graphics.render import render_graphic
from .render import build_base, load_faces

CHECKED = ("stack", "badge", "card", "poll", "tiles")


def moments(g: dict) -> list:
    ts = ([line.get("t", 0.0) for line in g.get("lines", [])] + [it.get("t", 0.0) for it in g.get("items", [])]
          + [g.get(k) or 0.0 for k in ("text_t", "title_t", "t_a", "t_b")])
    last = max(ts)
    d = g["dur"]
    return sorted({round(max(0.0, min(d - 0.35, last + 0.2)), 2), round(max(0.0, min(d - 0.1, last + 0.55)), 2),
                   round(max(0.0, d - 0.35), 2)})


def check(project, style: dict, only=None, width: int = 300) -> list:
    project = Path(project).resolve()
    plan = editjson.load(project / "edit.json")
    size = FORMATS[plan["format"]]
    work, out = project / "work", project / "qc" / "kw"
    work.mkdir(exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    base = build_base(project, plan, size)
    faces = load_faces(project, plan["segments"][0]["src"])
    vf = f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase,crop={size[0]}:{size[1]}"

    def under(t):
        for b in plan["broll"]:
            if b.get("resolved") and b["at"] <= t < b["at"] + b["dur"]:
                p = Path(b["resolved"])
                return str(p if p.is_absolute() else project / p), b.get("src_in", 0.0) + t - b["at"], True
        return str(base), t, False

    pngs = []
    for i, g in enumerate(plan["graphics"]):
        if g["type"] not in CHECKED or (only and i not in only):
            continue
        slot = layout.place(g, plan, faces, style, size)
        slot.pop("note", None)
        mov = render_graphic({**g, "slot": slot}, style, size, work / f"gfx-{i}.mov", project)
        panels = []
        for k, rel in enumerate(moments(g)):
            src, st, is_broll = under(g["at"] + rel)
            p = out / f"{i:02d}_{k}.png"
            fg = []
            chain = f"[0]{vf},setpts=PTS-STARTPTS[a];[1]setpts=PTS-STARTPTS[g];[a][g]overlay=eof_action=repeat"
            if g.get("place") in ("hands", "behind") and not is_broll:
                f = out / f"fg_{i}_{k}.mov"
                cutout.cut_out(base, f, g["at"] + rel, 0.1, size, part="hands" if g["place"] == "hands" else "person")
                fg = ["-i", str(f)]
                chain += "[o];[2]setpts=PTS-STARTPTS[f];[o][f]overlay=eof_action=repeat"
            chain += (f",drawtext=text='{i} {g['at'] + rel:.2f}':x=20:y=20:fontsize=48:fontcolor=yellow,"
                      f"scale={width}:-2")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{st:.3f}", "-i", src, "-ss", f"{rel:.3f}",
                            "-c:v", "prores", "-i", str(mov), *fg, "-filter_complex", chain, "-frames:v", "1", str(p)],
                           check=True)
            panels.append(str(p))
        p = out / f"{i:02d}.png"
        subprocess.run(["montage", *panels, "-tile", f"{len(panels)}x", "-geometry", "+2+2", str(p)], check=True)
        pngs.append(str(p))
    sheets = []
    for n in range(0, len(pngs), 6):
        s = out / f"sheet{n // 6}.jpg"
        subprocess.run(["montage", *pngs[n:n + 6], "-tile", "2x", "-geometry", "+6+6", str(s)], check=True)
        sheets.append(str(s))
    return sheets
