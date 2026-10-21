"""Outline: a stroke traced around the speaker, as a white sticker border or a glowing neon line, popping on for a
punchline; the room can drop to black and white or darken behind it so the speaker lifts off the frame."""
import cv2
import numpy as np

from . import _looks as L

NAME = "outline"
DOC = ("Sticker border or neon glow traced around the speaker (the cut-out), popping on for a punchline; the room "
       "can go mono or dim behind it. Short windows (0.8-3 s) on the line that matters.")
BEST_FOR = ["playful", "product", "any"]
DUR = (0.5, 10)
PARAMS = {
    "style": "sticker",  # sticker (solid border) | neon (thin line with a glow)
    "color": None,       # default: white for sticker, the style accent for neon
    "width": 0.014,      # stroke width as a fraction of the frame width
    "glow": 0.8,         # neon glow strength 0-1
    "bg": "keep",        # keep | mono | dim | blur | tint: the room behind the speaker
    "enter": 0.18,       # s: the stroke grows on
    "exit": 0.18,        # s: and shrinks away (0: hold to the cut)
}
STYLES = ("sticker", "neon")


def frame(F: np.ndarray, a: np.ndarray, p: float, style: str, colour, width_px: float, glow: float,
          bg: str) -> np.ndarray:
    """One frame: F (float 0-1 RGB), a the person matte, p the envelope 0-1."""
    if p <= 1e-3:
        return F
    back = F if bg == "keep" else F + (L.treat_bg(F, bg) - F) * p
    out = back * (1 - a[..., None]) + F * a[..., None]
    outside = 1 - a
    if style == "sticker":
        r = L.ring(a, width_px * p, soft=1.0)
        return L.over(out, colour, r * outside)
    r = L.ring(a, max(1.0, width_px * 0.35) * p, soft=0.8)
    halo = cv2.GaussianBlur(r, (0, 0), max(2.0, width_px * 1.2)) * 2.2 * glow * p
    lit = L.screen(out, np.asarray(colour, np.float32) * np.clip(halo, 0, 1)[..., None] * outside[..., None])
    return L.over(lit, np.minimum(1, np.asarray(colour, np.float32) * 0.6 + 0.4), r * outside)


def render(ctx):
    style = ctx.param("style", PARAMS["style"])
    if style not in STYLES:
        raise ValueError(f"outline style must be one of {STYLES}")
    bg = ctx.param("bg", PARAMS["bg"])
    if bg not in L.BG_MODES:
        raise ValueError(f"outline bg must be one of {L.BG_MODES}")
    colour = L.hex_rgb(ctx.param("color") or ("#ffffff" if style == "sticker" else ctx.style.get("accent")))
    width = float(ctx.param("width", PARAMS["width"])) * ctx.W
    glow = float(ctx.param("glow", PARAMS["glow"]))
    enter, exit = float(ctx.param("enter", PARAMS["enter"])), float(ctx.param("exit", PARAMS["exit"]))
    with ctx.writer() as w:
        for i, (f, a) in enumerate(zip(ctx.frames(), ctx.mattes())):
            p = L.envelope(i / ctx.fps, (ctx.n - 1) / ctx.fps, enter, exit)
            w(L.to8(frame(f.astype(np.float32) / 255, a, p, style, colour, width, glow, bg)))
    return ctx.out
