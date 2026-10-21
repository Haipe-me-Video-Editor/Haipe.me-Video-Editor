"""Colour pop: the room behind the speaker drops to black and white (or darkens, blurs, or turns one colour) while
the speaker stays in full colour. An instant mood shift with one focal point, eased on and off."""
import numpy as np

from . import _looks as L

NAME = "color_pop"
DOC = ("The room goes black and white (or dim, blurred, or one tint) while the speaker stays in colour. "
       "For a serious beat, a reveal or a section change; 1-6 s.")
BEST_FOR = ["any", "corporate", "finance"]
DUR = (0.5, 15)
PARAMS = {
    "mode": "mono",   # mono | dim | blur | tint
    "color": None,    # tint colour (default the style accent)
    "amount": 1.0,    # 0-1: how far the room goes
    "enter": 0.25,    # s
    "exit": 0.25,     # s (0: hold to the cut)
}


def frame(F: np.ndarray, a: np.ndarray, p: float, mode: str, tint=None) -> np.ndarray:
    if p <= 1e-3:
        return F
    back = F + (L.treat_bg(F, mode, tint) - F) * p
    return back * (1 - a[..., None]) + F * a[..., None]


def render(ctx):
    mode = ctx.param("mode", PARAMS["mode"])
    if mode not in L.BG_MODES or mode == "keep":
        raise ValueError(f"color_pop mode must be one of {L.BG_MODES[1:]}")
    tint = L.hex_rgb(ctx.param("color") or ctx.style.get("accent"))
    amount = float(ctx.param("amount", PARAMS["amount"]))
    enter, exit = float(ctx.param("enter", PARAMS["enter"])), float(ctx.param("exit", PARAMS["exit"]))
    with ctx.writer() as w:
        for i, (f, a) in enumerate(zip(ctx.frames(), ctx.mattes())):
            p = amount * L.envelope(i / ctx.fps, (ctx.n - 1) / ctx.fps, enter, exit)
            w(L.to8(frame(f.astype(np.float32) / 255, a, p, mode, tint)))
    return ctx.out
