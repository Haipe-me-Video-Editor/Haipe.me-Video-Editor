"""Headline wall: notes, sticky notes and news-style cards pin themselves to the wall behind the speaker.

Each item pops onto the wall in turn (a spring with a little rotation, then its pin or tape lands), sits on the wall
plane (behind the speaker: their head and shoulders hide what is behind them; lit and softened like the room) and
everything clears at the end. Placement reads the speaker matte: notes go where the wall shows, may tuck behind
the head, and their text is set only in the part you can see. Content is whatever the spec says; a `source` line
is printed only when given (no invented outlets).
"""
import math
from pathlib import Path

from . import _spatial as sp

NAME = "headline_wall"
DOC = ("Notes, sticky notes and news-style cards pop onto the wall behind the speaker one by one (head in front). "
       "For listing 3-5 short points, announcements or quotes. items: strings or {text, kind, source}.")
BEST_FOR = ["product", "finance", "corporate", "any"]
DUR = (2.0, 8)
PARAMS = {
    # items: "text" or {"text": ..., "kind": "headline|note|sticky|dark|search", "source": "..."}; 2-6 of them,
    # 2-7 words each. kind defaults cycle headline, sticky, dark, note, search. source: printed small, only if given.
    "items": [],
    "source": None,        # one source line for every news-style card (e.g. "example.com"); default none
    "stagger": None,       # seconds between pops; default spreads them over the first ~55% of the window
    "light": 0.3,         # how much the notes take on the room's light (0 = pasted-on white)
    "blur": 0.7,           # wall softness in px (the wall is out of focus behind the speaker)
    "dim": 0.0,            # darken the room behind the notes
}

KINDS = ("headline", "sticky", "dark", "note", "search")
SIZES = {  # width as a fraction of W, height as a fraction of W
    "headline": (0.40, 0.25), "note": (0.36, 0.22), "sticky": (0.31, 0.31), "dark": (0.34, 0.20),
    "search": (0.42, 0.095),
}
SERIF = [Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"),
         Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
         Path("/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"),
         Path("/Library/Fonts/Georgia Bold.ttf")]


def normalise(items, source=None) -> list:
    """Items as dicts with text, kind and source."""
    out = []
    for i, it in enumerate(items or []):
        d = {"text": it} if isinstance(it, str) else dict(it or {})
        d["text"] = str(d.get("text", "")).strip()
        if not d["text"]:
            continue
        if d.get("kind") not in KINDS:
            d["kind"] = KINDS[i % len(KINDS)]
            if d["kind"] == "search" and len(d["text"]) > 24:  # a search bar holds one short line
                d["kind"] = "note"
        if d.get("source") is None and source and d["kind"] in ("headline", "note"):
            d["source"] = source
        out.append(d)
    return out


def layout(sc: sp.Scene, items: list, k: float = 1.0) -> list:
    """Greedy placement on the clear wall: each note where most of it (and all of its text) shows, high up,
    spread out, overlapping earlier notes only a little. Returns per item {rect, rot, side, text_w} or None when
    the wall is full. Pure; tests drive it with fake scenes."""
    W, H = sc.W, sc.H
    sx0, sx1, sy0, sy1 = sc.px("x0"), sc.px("x1"), sc.px("y0"), sc.px("y1")
    floor = min(sy1, max(sc.chin + 0.06 * H, sy0 + 0.30 * H))
    placed, out = [], []
    # scarce wall (close-ups): smaller notes so more of them fit
    G = sp.GRID
    a, b = int(sy0 // G), int(floor // G)
    c, d = int(sx0 // G), int(sx1 // G)
    free = float((1 - sc.cover[a:b, c:d]).clip(0, 1).sum()) * G * G
    need = sum(SIZES[it["kind"]][0] * SIZES[it["kind"]][1] for it in items) * W * W
    s0 = max(0.6, min(1.0, math.sqrt(0.75 * free / max(1.0, need))))
    for i, it in enumerate(items):
        wf, hf = SIZES[it["kind"]]
        shrinks = (s0, s0 * 0.86, s0 * 0.74)
        if it["kind"] == "search":  # a pill as long as its one line at ~26 px, never squeezed
            wf = min(0.62, (len(it["text"]) * 0.72 * 26 + 120) / 1080)
            shrinks = (1.0,)
        best = None
        for shrink in shrinks:
            w, h = wf * W * shrink, hf * W * shrink
            min_text = (0.8 if it["kind"] == "search" else 0.5) * w
            ys = [sy0 + 6 * k + j * 0.018 * H for j in range(60)]
            xs = [sx0 + (sx1 - sx0 - w) * j / 16 for j in range(17)]
            for y in ys:
                if y + h > floor:
                    break
                for x in xs:
                    r = (x, y, x + w, y + h)
                    right = (x + w / 2) > sc.cx
                    tw = sp.clear_run(sc, r, right)
                    if tw < min_text:
                        continue
                    ov = max([_overlap(r, p) for p in placed] + [0.0])
                    if ov > 0.28:
                        continue
                    spread = min([_dist(r, p) for p in placed] + [W]) / W
                    score = (tw / w) + 0.35 * (1 - sc.rect_cover(*r)) - 0.35 * (y - sy0) / H \
                        - 1.2 * ov + 0.25 * min(spread, 0.35) + 0.15 * shrink
                    if best is None or score > best[0]:
                        best = (score, r, right, tw)
            if best:
                break
        if best is None:
            out.append(None)
            continue
        _, r, right, tw = best
        rot = (-4.5, 3.5, -2.5, 5.0, -3.5, 2.0)[i % 6] * (1 if right else -1) * 0.8
        out.append({"rect": r, "rot": rot, "side": "right" if right else "left", "text_w": tw})
        placed.append(r)
    return out


def _overlap(a, b) -> float:
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return iw * ih / max(1.0, min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])))


def _dist(a, b) -> float:
    return math.hypot((a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2)


def fit_font(text: str, width: float, height: float, sizes, char_w: float = 0.56, lh: float = 1.12,
             max_lines: int = 4) -> tuple:
    """Largest size from `sizes` whose greedy word wrap fits width x height. Returns (size, lines)."""
    words = text.split()
    for s in sizes:
        lines, cur = 1, 0.0
        for w in words:
            ww = len(w) * char_w * s
            if ww > width:
                lines = 99
                break
            add = ww if cur == 0 else cur + char_w * s + ww
            if add > width:
                lines, cur = lines + 1, ww
            else:
                cur = add
        if lines <= max_lines and lines * s * lh <= height:
            return s, lines
    return sizes[-1], max_lines


def sticky_color(style: dict) -> str:
    """A paper colour from the brand accent: pale, never neon."""
    acc = style.get("accent", "#ff7a1a")
    return sp.mix(acc, "#fbf8ef", 0.72)


def render(ctx):
    items = normalise(ctx.param("items") or [], ctx.param("source"))
    if not items:
        raise ValueError("headline_wall needs items (2-6 short strings or {text, kind, source})")
    sc = sp.scene(ctx)
    k = ctx.W / 1080
    lay = layout(sc, items, k)
    skipped = [it["text"] for it, L in zip(items, lay) if not L]
    if skipped:
        import sys
        print(f"[fx] headline_wall: no clear wall left for {skipped}", file=sys.stderr)
    D = ctx.dur
    n_ok = sum(1 for x in lay if x)
    stagger = ctx.param("stagger") or min(0.55, max(0.18, (D * 0.55 - 0.2) / max(1, n_ok)))
    th = sp.theme(ctx.style, "dark")
    serif = next((p for p in SERIF if p.exists()), None)
    assets = {"newsserif" + serif.suffix.lower(): serif} if serif else {}
    blur = float(ctx.param("blur", PARAMS["blur"]))
    notes, js = [], []
    j = 0
    for i, (it, L) in enumerate(zip(items, lay)):
        if not L:
            continue
        x0, y0, x1, y1 = L["rect"]
        w, h = x1 - x0, y1 - y0
        kind, side = it["kind"], L["side"]
        pad = 0.07 * w
        tw = max(40.0, L["text_w"] - pad * 1.6)
        ar = sp.is_arabic(it["text"])
        src = it.get("source")
        meta_h = 26 * k if src and kind in ("headline", "note") else 0
        avail_h = h - 2 * pad - meta_h - (8 * k if kind == "headline" else 0)
        cw = 0.5 if ar else 0.66  # average advance per character, in em
        if kind == "search":
            tw = max(40.0, tw - 44 * k)  # the magnifier and its gap share the pill
            fs, _ = fit_font(it["text"], tw, h * 0.6, [s * k for s in (34, 31, 28, 25, 22, 19)],
                             cw + 0.08, 1.1, 1)
        elif kind in ("headline", "note"):
            fs, _ = fit_font(it["text"], tw, avail_h, [s * k for s in (54, 48, 43, 38, 34, 30, 27, 24)],
                             0.5, 1.06, 4)
        else:
            fs, _ = fit_font(it["text"], tw, avail_h, [s * k for s in (48, 43, 39, 35, 31, 28, 25, 22)],
                             cw, 1.14 if not ar else 1.3, 4)
        align = "right" if side == "right" or ar else "left"
        txt_style = (f"width:{tw:.0f}px;font-size:{fs:.1f}px;{'margin-left:auto;' if side == 'right' else ''}"
                     f"text-align:{align}")
        meta = f'<div class="src">{sp.esc(src)}</div>' if meta_h else ""
        rule = '<div class="rule"></div>' if kind == "headline" else ""
        glyph = ('<svg class="mag" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" '
                 'stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/></svg>'
                 if kind == "search" else "")
        hold = ('<i class="tape"></i>' if kind in ("headline", "note") else '<i class="pin"></i>'
                if kind in ("sticky", "dark") else "")
        dot = ""
        notes.append(
            f'<div class="nw" id="n{j}" style="left:{x0:.0f}px;top:{y0:.0f}px;width:{w:.0f}px;height:{h:.0f}px">'
            f'<div class="pp {kind}{" ar" if ar else ""} {side}" style="padding:{pad:.0f}px">'
            f'{meta}{rule}{dot}{glyph}<div class="tx" style="{txt_style}">{sp.esc(it["text"])}</div></div>{hold}</div>')
        t0 = 0.12 + j * stagger
        js.append(f"springIn(tl, '#n{j}', {{y: -26*K, scale: 1.18, rotation: {L['rot'] + (7 if j % 2 else -7):.1f}, "
                  f"opacity: 0}}, {{y: 0, scale: 1, rotation: {L['rot']:.1f}, opacity: 1, duration: .55}}, 'bouncy', "
                  f"{t0:.3f});")
        js.append(f"if (document.querySelector('#n{j} .pin, #n{j} .tape')) springIn(tl, '#n{j} .pin, #n{j} .tape', "
                  f"{{scale: 1.8, opacity: 0}}, {{scale: 1, opacity: 1, duration: .35}}, 'snappy', {t0 + 0.2:.3f});")
        j += 1
    out = "{duration: .32, ease: 'power2.in', immediateRender: false}"
    js.append(f"tl.fromTo('.nw', {{opacity: 1}}, Object.assign({{opacity: 0}}, {out}), {D - 0.34:.3f});")
    css = _css(th, k, ctx.style, serif, blur)
    page = ctx.page("".join(notes), css, f"const K = {k:.4f};\n  " + "\n  ".join(js))
    layer = ctx.layer(page, "hwall", assets)
    tint = _room_tint(ctx, float(ctx.param("light", PARAMS["light"])))
    return sp.composite(ctx, [layer], [], dim=float(ctx.param("dim", PARAMS["dim"])), frost=0.0,
                        ramp=(0.3, 0.35), back_tint=tint)


def _room_tint(ctx, amount: float):
    """Per-channel gain that lights the notes like the room (its average colour, mostly as brightness, a little as
    hue), mixed in by `amount`. None when there is no clear wall to sample."""
    import subprocess

    import cv2
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(ctx.src), "-frames:v", "1", "-vf",
                          f"scale={ctx.W}:{ctx.H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    if len(raw) < ctx.W * ctx.H * 3:
        return None
    f = np.frombuffer(raw, np.uint8).reshape(ctx.H, ctx.W, 3).astype(np.float32) / 255
    sc = sp.scene(ctx)
    clear = cv2.resize((sc.cover < 0.1).astype(np.uint8), (ctx.W, ctx.H), interpolation=cv2.INTER_NEAREST) > 0
    if clear.sum() < 1000:
        return None
    return tint_from(f[clear].mean(axis=0), amount)


def tint_from(room, amount: float):
    """Gains from a room's mean RGB (0-1): 70% brightness, 30% hue, mixed in by `amount`."""
    import numpy as np
    room = np.asarray(room, np.float32)
    lum = float(room.mean())
    hue = room / max(1e-3, float(room.max()))
    colour = 0.7 + 0.3 * hue
    level = min(1.0, 0.66 + 1.3 * lum)
    return (1 - amount) + amount * colour * level


def _css(th, k, style, serif, blur):
    def px(v):
        return f"{v * k:.1f}px"
    accent = th["accent"]
    face = f'@font-face{{font-family:"NewsSerif";src:url("newsserif{serif.suffix.lower()}")}}' if serif else ""
    return f"""{face}
.nw{{position:absolute;will-change:transform,opacity;filter:blur({blur * k:.2f}px)}}
.pp{{position:absolute;inset:0;box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;
  overflow:hidden;box-shadow:0 {px(2)} {px(3)} rgba(0,0,0,.25),0 {px(10)} {px(22)} rgba(0,0,0,.30)}}
.pp .tx{{line-height:1.08;letter-spacing:-.01em}}
.headline,.note{{background:#f4f1e8;color:#16171a;border-radius:{px(3)}}}
.headline .tx{{font-family:"NewsSerif","BrandLT",serif;line-height:1.04;letter-spacing:-.015em}}
.headline .rule{{height:{px(3)};background:#16171a;margin-bottom:{px(10)};flex:none}}
.note .tx{{font-family:"NewsSerif","BrandLT",serif}}
.src{{font:500 {px(16)}/1 "PlexMono";letter-spacing:.08em;text-transform:uppercase;color:rgba(22,23,26,.55);
  margin-bottom:{px(10)};flex:none}}
.right .src{{text-align:right}}
.sticky{{background:{sticky_color(style)};color:#14161a;border-radius:{px(2)};
  background-image:linear-gradient(180deg,rgba(0,0,0,.05),rgba(0,0,0,0) 30%,rgba(0,0,0,.04))}}
.sticky .tx{{font-family:"BrandLT";line-height:1.14;letter-spacing:-.02em}}
.dark{{background:#0d0e10;color:#ffffff;border-radius:{px(12)};box-shadow:0 0 0 1px rgba(255,255,255,.08),
  0 {px(10)} {px(24)} rgba(0,0,0,.4)}}
.dark .tx{{font-family:"BrandLT";line-height:1.14;letter-spacing:-.02em}}
.dark .dot{{position:absolute;top:{px(16)};left:{px(16)};width:{px(10)};height:{px(10)};border-radius:50%;background:{accent}}}
.dark.right .dot{{left:auto;right:{px(16)}}}
.search{{background:#fff;color:#16171a;border-radius:999px;flex-direction:row;align-items:center;gap:{px(14)}}}
.search.right{{flex-direction:row-reverse}}
.search .tx{{font-family:"BrandLT";white-space:nowrap;overflow:hidden;line-height:1}}
.search .mag{{flex:none;width:{px(30)};height:{px(30)};color:#5b5f66}}
.pp.ar .tx{{font-family:"BrandAR";direction:rtl;letter-spacing:0;line-height:1.3}}
.tape{{position:absolute;left:50%;top:{px(-14)};width:{px(110)};height:{px(30)};margin-left:{px(-55)};
  background:rgba(236,232,220,.78);box-shadow:0 1px 2px rgba(0,0,0,.18);transform:rotate(-3deg)}}
.pin{{position:absolute;left:50%;top:{px(8)};width:{px(22)};height:{px(22)};margin-left:{px(-11)};border-radius:50%;
  background:radial-gradient(circle at 35% 30%,{sp.mix(accent, '#ffffff', 0.45)},{accent} 45%,{sp.mix(accent, '#000000', 0.45)});
  box-shadow:{px(2)} {px(4)} {px(5)} rgba(0,0,0,.4)}}
"""
