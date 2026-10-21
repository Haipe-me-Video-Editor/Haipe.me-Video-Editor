"""Word stack: big kinetic words that land on the beat of the voice, stacked in the upper frame BEHIND the speaker's
head, each in its own look: see-through outlined letters, a large italic serif with a soft gradient, plain italic
serif, or heavy bold sans. The "transparent captions that move with your words" style. The small burned-in
captions keep running below; this carries the two or three words that matter."""
import numpy as np

from . import _glass as G

NAME = "word_stack"
DOC = ("Big words behind the head, landing on their spoken times, each in a look: outline (see-through), gradient "
       "(italic serif, pastel gradient), serif (italic), bold. words: [{t, text, look, new?}]; 1-6 s.")
BEST_FOR = ["playful", "product", "any"]
DUR = (0.6, 10)
PARAMS = {
    "words": [],        # [{"t": s into the window, "text": "caption", "look": "gradient", "new": false}]; new starts
                        # a fresh stack (the earlier words leave)
    "y": None,          # top of the stack, 0-1 of the height (default: over the top of the head when there is
                        # headroom, the head covering the last line a little; on the chest on a close-up)
    "size": 1.0,        # scale on the automatic sizes
    "gradient": ["#ff9d5c", "#ff7eb6", "#b28dff", "#6ccbff"],
    "behind": True,     # the speaker in front of the words when they sit above the head (on the chest they go on top)
    "exit": 0.2,        # s: the last stack leaves before the window ends
}
LOOKS = ("outline", "gradient", "serif", "bold")


def font_for(look: str, arabic: bool) -> str:
    if arabic:
        return "AmiriSerif" if look in ("serif", "gradient") else "Lalezar"
    return "InstrumentItalic" if look in ("serif", "gradient") else "Montserrat"


def size_for(text: str, look: str, W: int, scale: float = 1.0) -> float:
    """Font size (px) so the word fills most of the width without spilling: per-look average glyph widths."""
    em = {"outline": 0.66, "bold": 0.66, "serif": 0.42, "gradient": 0.42}[look]
    return min(W * 0.25, W * 0.84 / max(1, len(text)) / em) * scale


def stack_y(P, H: int) -> float:
    """Top of the stack (0-1 of the height): high in the frame when the crown leaves room (the head then covers the
    bottom of the last line, the look of the style), else just under the chin, on the chest."""
    if P is None:
        return 0.12
    crown = (P[10, 1] - 0.45 * (P[152, 1] - P[10, 1])) / H
    return 0.10 if crown >= HEADROOM else min(0.62, P[152, 1] / H + 0.03)


HEADROOM = 0.24  # crown this far down (0-1) leaves room for the stack above the head


def groups(words: list) -> list:
    """The words split into stacks: a word with new=true (or past 3 lines) starts a fresh one."""
    out = []
    for w in sorted(words, key=lambda w: float(w["t"])):
        if not out or w.get("new") or len(out[-1]) >= 3:
            out.append([])
        out[-1].append(w)
    return out


def render(ctx):
    words = ctx.param("words") or []
    if not words:
        raise ValueError("word_stack needs words: [{t, text, look}]")
    for w in words:
        if w.get("look", "bold") not in LOOKS:
            raise ValueError(f"word_stack look must be one of {LOOKS}")
        if not 0 <= float(w["t"]) < ctx.dur:
            raise ValueError(f"word_stack: {w['text']!r} at {w['t']} s is outside the window")
    y = ctx.param("y")
    if y is None:
        pts = [p for p in ctx.landmarks(every=3) if p is not None]
        y = stack_y(np.median(np.stack(pts), axis=0) if pts else None, ctx.H)
    layer = ctx.layer(_page(ctx, words, float(y)), "word-stack")
    # behind the speaker only when the words sit above them: on the chest (a close-up) the body would hide them
    if ctx.param("behind", PARAMS["behind"]) and float(y) < 0.2:
        return ctx.stack([ctx.src, layer, ctx.person()])
    return ctx.stack([ctx.src, layer])


def _page(ctx, words, y):
    W, H = ctx.W, ctx.H
    grad = ", ".join(ctx.param("gradient") or PARAMS["gradient"])
    scale = float(ctx.param("size", PARAMS["size"]))
    gs = groups(words)
    html, js = [], []
    for gi, g in enumerate(gs):
        rows = []
        for wi, w in enumerate(g):
            text, look = str(w["text"]), w.get("look", "bold")
            ar = G.is_arabic(text)
            sz = size_for(text, look, W, scale)
            rows.append(f'<div class="w {look}" id="w{gi}_{wi}" style="font-family:\'{font_for(look, ar)}\';'
                        f'font-size:{sz:.0f}px" dir="{"rtl" if ar else "ltr"}">{G.esc(text)}</div>')
            js.append(f"springIn(tl,'#w{gi}_{wi}',{{y:{sz * 0.35:.0f},scale:.86,opacity:0,filter:'blur(14px)'}},"
                      f"{{y:0,scale:1,opacity:1,filter:'blur(0px)',duration:.45}},'snappy',{float(w['t']):.3f});")
        html.append(f'<div class="g" id="g{gi}">{"".join(rows)}</div>')
        end = float(gs[gi + 1][0]["t"]) - 0.06 if gi + 1 < len(gs) else ctx.dur - float(ctx.param("exit", 0.2))
        js.append(f"tl.to('#g{gi}',{{opacity:0,y:-20,filter:'blur(10px)',duration:.18,ease:'power2.in'}},"
                  f"{max(0.0, end - 0.18):.3f});")
    y = y * H
    css = f"""
.g{{position:absolute;left:0;right:0;top:{y:.0f}px;display:flex;flex-direction:column;align-items:center}}
.w{{line-height:.98;white-space:nowrap;opacity:0;margin-bottom:{W * 0.005:.0f}px}}
.outline{{color:rgba(255,255,255,.14);-webkit-text-stroke:{W / 300:.1f}px rgba(255,255,255,.9);font-weight:800;
  text-shadow:0 0 {W / 90:.0f}px rgba(0,0,0,.18)}}
.bold{{color:#fbfaf6;font-weight:800;text-shadow:0 {W / 180:.0f}px {W / 40:.0f}px rgba(0,0,0,.35)}}
.serif{{color:#fff;font-weight:400;text-shadow:0 {W / 270:.0f}px {W / 60:.0f}px rgba(0,0,0,.3)}}
.gradient{{font-weight:400;background:linear-gradient(90deg,{grad});-webkit-background-clip:text;
  background-clip:text;color:transparent;filter:drop-shadow(0 {W / 270:.0f}px {W / 90:.0f}px rgba(0,0,0,.25))}}"""
    return ctx.page("".join(html), css, "\n  ".join(js))
