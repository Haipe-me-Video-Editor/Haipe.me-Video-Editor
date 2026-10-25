"""Lens: a ball of liquid glass drifts across the frame and settles on the speaker's face, magnifying what is under it
the way a real glass sphere does: strong in the middle, bending hard at the rim, with a split of colour at the edge,
a thin bright rim, a soft highlight and a faint shadow round it. The edge wobbles a little as it moves, like a drop.

Built with one remap per colour channel (red and blue bend slightly differently from green), so it is real
refraction of the live frame, not an overlay.
"""

import cv2
import numpy as np

from . import _behind as B
from . import _camera as cam

NAME = "lens"
DOC = ("A ball of liquid glass glides in and settles on the face, magnifying and bending the picture under it (colour "
       "fringes, bright rim, highlight), then drifts off. For a 'look closer' / focus / 'see what I mean' line.")
BEST_FOR = ["product", "playful", "any"]
DUR = (1.0, 8)
PARAMS = {
    "size": 0.42,        # lens diameter as a fraction of the frame width
    "mag": 1.45,         # magnification at the centre (1.15 subtle .. 2 strong)
    "path": "sweep",     # sweep (glides in from the side, settles on the face, drifts off) | face (grows on the face)
    "target": "face",    # face | eye | mouth | center | [x, y] in 0-1: where it settles
    "from": "left",      # sweep: left | right, the side it comes in from
    "wobble": 0.035,     # liquid edge wobble while moving, fraction of the radius
    "fringe": 0.0,       # colour split at the rim (0: none; house rule: footage colour never changes)
}
ENTER, EXIT = 0.7, 0.5


def refract(F: np.ndarray, c, R: float, mag: float, fringe: float, wob=None) -> tuple:
    """The frame seen through a glass ball at c with radius R: (image, coverage) float32. `wob(theta)` gives a radius
    multiplier per angle for the liquid edge. Profile: sample offset = d / m(r), with m falling from `mag` at the
    centre to 1 at the rim along a sphere curve, so the rim compresses the picture like the edge of a lens."""
    H, W = F.shape[:2]
    x0, y0 = max(int(c[0] - R * 1.2), 0), max(int(c[1] - R * 1.2), 0)
    x1, y1 = min(int(c[0] + R * 1.2) + 1, W), min(int(c[1] + R * 1.2) + 1, H)
    out, cov = F.copy(), np.zeros((H, W), np.float32)
    if x1 <= x0 or y1 <= y0:
        return out, cov
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx, dy = xx - c[0], yy - c[1]
    d = np.sqrt(dx * dx + dy * dy)
    Rl = R * (wob(np.arctan2(dy, dx)) if wob else 1.0)
    r = np.clip(d / Rl, 0, 1)
    sphere = np.sqrt(np.clip(1 - r * r, 0, 1))          # 1 at the centre, 0 at the rim
    region = out[y0:y1, x0:x1]
    for ch, k in ((0, 1 + fringe), (1, 1.0), (2, 1 - fringe)):
        m = 1 + (mag * k - 1) * sphere ** 0.6
        # rim compression: near the edge the sample reaches outward past the rim
        reach = 1 + 0.9 * (1 - sphere) ** 3
        sx, sy = c[0] + dx / m * reach, c[1] + dy / m * reach
        region[..., ch] = cv2.remap(F[..., ch], sx, sy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    inside = np.clip((Rl - d) + 0.5, 0, 1)
    cov[y0:y1, x0:x1] = inside
    # glass: a slight cool tint and lift, a bright rim, an inner shade at the edge, a soft highlight up-left
    rim = np.clip(1 - np.abs(d - Rl * 0.985) / (R * 0.022), 0, 1)
    edge = (1 - sphere) ** 3
    hx, hy = c[0] - R * 0.38, c[1] - R * 0.42
    hl = np.exp(-(((xx - hx) / (R * 0.22)) ** 2 + ((yy - hy) / (R * 0.12)) ** 2))
    glass = region * (1 - 0.18 * edge[..., None]) + 0.03
    glass = glass + (1 - glass) * (0.6 * rim + 0.4 * hl)[..., None]
    region[:] = glass
    return out, cov


def path_at(t: float, dur: float, start, settle, end, kind: str, preset: str = "gentle") -> tuple:
    """(centre, scale 0..1, speed 0..1) of the lens at t: glide in and settle with a spring, hold, drift off."""
    u = B.progress(t, 0.0, ENTER)
    v = B.progress(t, dur - EXIT, EXIT)
    sp = B.spring(preset)(u)
    if kind == "face":
        scale = B.spring("bouncy")(u) * (1 - B.ease_in(v))
        return settle, max(scale, 0.0), abs(1 - sp) + v
    if v > 0:
        e = B.ease_in(v)
        c = (settle[0] + (end[0] - settle[0]) * e, settle[1] + (end[1] - settle[1]) * e)
        return c, 1.0, v
    c = (start[0] + (settle[0] - start[0]) * sp, start[1] + (settle[1] - start[1]) * sp)
    return c, 1.0, abs(1 - sp)


def render(ctx):
    W, H = ctx.W, ctx.H
    size = float(ctx.param("size", PARAMS["size"]))
    mag = float(ctx.param("mag", PARAMS["mag"]))
    if not 0.15 <= size <= 0.8 or not 1.05 <= mag <= 3:
        raise ValueError("lens size must be in [0.15, 0.8] and mag in [1.05, 3]")
    kind = ctx.param("path", PARAMS["path"])
    if kind not in ("sweep", "face"):
        raise ValueError("lens path is sweep or face")
    side = -1 if ctx.param("from", PARAMS["from"]) == "left" else 1
    wobble = float(ctx.param("wobble", PARAMS["wobble"]))
    fringe = float(ctx.param("fringe", PARAMS["fringe"]))
    target = ctx.param("target", PARAMS["target"])
    lm = ctx.landmarks(every=2) if not isinstance(target, (list, tuple)) and target != "center" else []
    R0 = size * W / 2
    with ctx.writer() as write:
        for i, frame in enumerate(ctx.frames()):
            t = i / ctx.fps
            # follow the face, lightly smoothed over a few frames
            settle = cam.resolve_target(target, lm, range(max(0, i - 4), min(ctx.n, i + 5)), (W, H))
            start = (W / 2 + side * (W / 2 + R0 * 1.3), settle[1] + H * 0.06)
            end = (W / 2 - side * (W / 2 + R0 * 1.3), settle[1] - H * 0.04)
            c, sc, speed = path_at(t, ctx.dur, start, settle, end, kind)
            R = R0 * sc
            if R < 2:
                write(frame)
                continue
            amp = wobble * min(1.0, speed * 1.5)
            wob = (lambda th, a=amp, t=t: 1 + a * np.sin(3 * th + 7 * t) + 0.6 * a * np.sin(5 * th - 5 * t)) if amp > 1e-3 else None
            F = frame.astype(np.float32) / 255
            img, cov = refract(F, c, R, 1 + (mag - 1) * min(1.0, sc), fringe, wob)
            # contact shadow just outside the rim
            yy, xx = np.ogrid[0:H, 0:W]
            d = np.sqrt((xx - c[0]) ** 2 + (yy - c[1] - R * 0.05) ** 2, dtype=np.float32)
            sh = np.clip(1 - (d - R) / (R * 0.18), 0, 1) * (d > R * 0.9)
            base = F * (1 - 0.22 * sh[..., None])
            out = base * (1 - cov[..., None]) + img * cov[..., None]
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out
