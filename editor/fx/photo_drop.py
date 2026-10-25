"""Photo drop: the shot becomes a printed photo. A white border grows round the frame while it shrinks and tilts onto
a clean background, overshooting like a print tossed onto a table, then settling with a soft shadow under it. The
footage keeps playing inside the print, and at the end the print swings back to fill the frame exactly, so the
cut out of the window is seamless.

One affine map per frame (uniform scale, rotation about the frame centre, a small drop from above) takes the bordered
print to the screen, so footage, border and shadow stay locked together.
"""
import math

import cv2
import numpy as np

from . import _behind as B
from .frame_break import backdrop

NAME = "photo_drop"
DOC = ("The shot becomes a tilted printed photo (white border, soft shadow) that drops onto a clean background and "
       "settles, footage still playing inside; swings back to full frame at the end. For a 'remember this' / story "
       "beat or a section change.")
BEST_FOR = ["playful", "product", "any"]
DUR = (1.2, 8)
PARAMS = {
    "size": 0.74,        # print width (border included) as a fraction of the frame width
    "tilt": -4.0,        # resting tilt, degrees (negative leans left)
    "border": 0.035,     # border width, fraction of the frame width
    "print": "border",   # border (even) | polaroid (deeper bottom margin)
    "bg": "light",       # light (paper grey) | clean (style colours) | blur (the footage, blurred and dimmed)
    "spring": "bouncy",  # how it lands: gentle | snappy | bouncy
    "exit": True,        # swing back to full frame at the end (False: hold the print, end on a cut)
}
ENTER, EXIT = 0.8, 0.45
PAPER = np.float32([0.985, 0.98, 0.965])  # a warm photo-paper white
DROP = 0.06                               # how far above its resting place it falls from, fraction of the height


def light_backdrop(W: int, H: int) -> np.ndarray:
    """Soft paper grey with a pool of light behind the print and a gentle vignette, float32 (H, W, 3)."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W * 0.5) / (W * 0.85)) ** 2 + ((yy - H * 0.42) / (H * 0.6)) ** 2)
    base = np.float32([0.905, 0.91, 0.92])
    out = base[None, None, :] + 0.06 * (np.clip(1 - r, 0, 1) ** 1.5)[..., None]
    return np.clip(out, 0, 1).astype(np.float32)


def borders(W: int, H: int, border: float, kind: str) -> tuple:
    """Border widths (left/right, top, bottom) in source pixels for a print around a W x H frame."""
    if kind not in ("border", "polaroid"):
        raise ValueError("photo_drop print is border or polaroid")
    b = border * W
    return b, b, (b * 3.2 if kind == "polaroid" else b)


def pose(t: float, dur: float, s1: float, tilt: float, preset: str, exit_: bool, H: int) -> tuple:
    """(scale, rotation deg, y offset px, border fade 0-1) at time t. Scale and border follow a smooth ease; the tilt
    and the drop follow the spring, so the print overshoots its angle and bounces as it lands."""
    u = B.progress(t, 0.0, ENTER)
    k = B.ease_out(u)
    sp = B.spring(preset)(u)
    back = B.ease_in(B.progress(t, dur - EXIT, EXIT)) if exit_ else 0.0
    keep = 1 - back
    s = 1 + (s1 - 1) * k * keep
    rot = tilt * sp * keep
    dy = -DROP * H * (1 - sp) * (u > 0) * keep * k
    return s, rot, dy, min(1.0, k * 1.6) * keep


def render(ctx):
    W, H = ctx.W, ctx.H
    size = float(ctx.param("size", PARAMS["size"]))
    if not 0.4 <= size <= 0.95:
        raise ValueError("photo_drop size must be in [0.4, 0.95]")
    tilt = float(ctx.param("tilt", PARAMS["tilt"]))
    bl, bt, bb = borders(W, H, float(ctx.param("border", PARAMS["border"])), ctx.param("print", PARAMS["print"]))
    preset = ctx.param("spring", PARAMS["spring"])
    exit_ = bool(ctx.param("exit", PARAMS["exit"]))
    kind = ctx.param("bg", PARAMS["bg"])
    if kind not in ("light", "clean", "blur"):
        raise ValueError("photo_drop bg is light, clean or blur")
    pw, ph = W + 2 * bl, H + bt + bb                 # the print, border included, in source pixels
    s1 = size * W / pw
    # keep the resting print (rotated bounding box) inside the safe zone's height
    a = math.radians(abs(tilt))
    s1 = min(s1, (B.SAFE[3] - B.SAFE[1]) * H / (pw * math.sin(a) + ph * math.cos(a)))
    cx = (B.SAFE[0] + B.SAFE[2]) / 2 * W              # resting centre: the middle of the safe zone
    cy = (B.SAFE[1] + B.SAFE[3]) / 2 * H
    ox, oy = round(bl) + 2, round(bt) + 2               # where the frame sits on the print canvas (2 px margin)
    cw, chh = W + ox + round(bl) + 2, H + oy + round(bb) + 2
    alpha_full = np.zeros((chh, cw), np.float32)
    alpha_full[2:-2, 2:-2] = 1.0
    alpha_frame = np.zeros((chh, cw), np.float32)
    alpha_frame[oy:oy + H, ox:ox + W] = 1.0
    canvas = np.empty((chh, cw, 3), np.float32)
    bg = None
    with ctx.writer() as write:
        for i, frame in enumerate(ctx.frames()):
            t = i / ctx.fps
            s, rot, dy, fade = pose(t, ctx.dur, s1, tilt, preset, exit_, H)
            if abs(s - 1) < 1e-4 and abs(rot) < 1e-3 and abs(dy) < 0.5:
                write(frame)
                continue
            if bg is None:
                bg = light_backdrop(W, H) if kind == "light" else backdrop(ctx, kind, frame)
            F = frame.astype(np.float32) / 255
            canvas[:] = PAPER
            canvas[oy:oy + H, ox:ox + W] = F
            # the frame's centre on the canvas goes to a point between the full-frame centre and the resting centre
            p = (s - 1) / (s1 - 1) if s1 != 1 else 1.0
            tx, ty = W / 2 + (cx - W / 2) * p, H / 2 + (cy - H / 2) * p + dy
            c0 = (ox + W / 2, oy + H / 2)
            M = cv2.getRotationMatrix2D(c0, -rot, s)
            M[0, 2] += tx - c0[0]
            M[1, 2] += ty - c0[1]
            img = cv2.warpAffine(canvas, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            # the border fades in: blend the paper mask between "frame only" and "whole print"
            am = alpha_frame + (alpha_full - alpha_frame) * fade
            A = cv2.warpAffine(am, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            # soft shadow under the print, a little below it
            small = cv2.resize(A, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
            sh = cv2.GaussianBlur(small, (0, 0), 6 + 6 * p)
            sh = cv2.warpAffine(sh, np.float32([[1, 0, 0], [0, 1, 3 + 4 * p]]), (W // 4, H // 4))
            out = bg * (1 - 0.42 * p * cv2.resize(sh, (W, H))[..., None])
            out = out * (1 - A[..., None]) + img * A[..., None]
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out
