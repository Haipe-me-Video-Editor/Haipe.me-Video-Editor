"""Viewfinder: the shot is suddenly seen through a camera's screen. Corner brackets, a blinking REC dot and a running
timecode across the top, a zoom readout (a pill over a sliding tick ruler), the camera settings along the bottom,
and a focus box that locks onto the face. The camera then punches in step by step (1.8x, 3x, ...) with a spring
and motion blur, the readout counting along and the focus box re-locking on every step, and comes back to 1x.

The HUD never zooms: it is drawn on top of the zoomed picture, and the focus box follows the face through the
same zoom, so it stays on the face at every step.
"""
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .. import fonts
from . import _behind as B
from . import _camera as cam

NAME = "viewfinder"
DOC = ("The shot becomes a camera viewfinder (REC, timecode, corner brackets, settings, a focus box locked on the "
       "face) and punches in step by step with a live zoom readout (1x > 1.8x > 3x > 1x). For 'let me zoom in on "
       "that', emphasis on a detail, or a behind-the-scenes feel.")
BEST_FOR = ["product", "playful", "any"]
DUR = (1.5, 10)
PARAMS = {
    "zooms": [1.0, 1.8, 3.0, 1.0],  # zoom levels in order; the first holds from the start of the window
    "steps": [],                    # seconds into the window of each step after the first (default: evenly)
    "target": "face",               # face | eye | mouth | center | [x, y] in 0-1: what the zoom closes on
    "left_text": "4K · 30 FPS",     # bottom-left settings line
    "right_text": "ISO 400 · 1/50",  # bottom-right settings line
    "timecode": 12.0,               # timecode at the start of the window, seconds
    "accent": "#ffd60a",            # focus-lock colour (camera yellow)
}
STEP = 0.38       # spring length of one zoom step, s
LOCK = 0.45       # how long the focus box shows the lock colour after a step, s
FADE = 0.18       # HUD fade in / out, s
INK = (255, 255, 255)


def step_times(zooms: list, at: list, dur: float) -> list:
    """Start time of each step after the first. Given `steps`, they are used as is; otherwise they spread evenly,
    leaving the last one time to finish its spring before the window ends."""
    n = len(zooms) - 1
    if n < 1:
        raise ValueError("viewfinder needs at least two zoom levels")
    if at:
        if len(at) != n:
            raise ValueError(f"viewfinder steps needs {n} times, one per step after the first")
        return [float(a) for a in at]
    span = max(dur - STEP - 0.25, 0.3)
    return [0.25 + span * (k + 1) / (n + 0.5) for k in range(n)]


def zoom_at(t: float, zooms: list, times: list, preset: str = "snappy") -> float:
    """Zoom level at t: the spring from one level to the next starting at each step time."""
    z = zooms[0]
    for k, t0 in enumerate(times):
        if t < t0:
            break
        u = min(1.0, (t - t0) / STEP)
        z = zooms[k] + (zooms[k + 1] - zooms[k]) * cam.spring_ease(preset)(u)
    return max(z, 0.5)


@lru_cache(maxsize=8)
def _font(size: int):
    return ImageFont.truetype(str(fonts.ensure_font("IBM Plex Mono")), size)


def timecode(sec: float, fps: float) -> str:
    f = round(sec * fps)
    fr, s = f % round(fps), f // round(fps)
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{fr:02d}"


def brackets(d: ImageDraw.ImageDraw, x0, y0, x1, y1, arm, width, fill):
    for (x, y, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        d.line([(x, y + sy * arm), (x, y), (x + sx * arm, y)], fill=fill, width=width, joint="curve")


def static_hud(W: int, H: int, left: str, right: str) -> Image.Image:
    """Everything that never moves: frame brackets, bottom settings lines, a faint centre cross."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = B.SAFE[0] * W, B.SAFE[1] * H, B.SAFE[2] * W, B.SAFE[3] * H
    brackets(d, x0, y0, x1, y1, W * 0.07, 5, INK + (235,))
    f = _font(int(W * 0.032))
    yb = y1 - W * 0.045
    d.text((x0 + W * 0.03, yb), left, font=f, fill=INK + (235,), anchor="lm")
    d.text((x1 - W * 0.03, yb), right, font=f, fill=INK + (235,), anchor="rm")
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    d.line([(cx - 16, cy), (cx + 16, cy)], fill=INK + (120,), width=2)
    d.line([(cx, cy - 16), (cx, cy + 16)], fill=INK + (120,), width=2)
    return im


def draw_dynamic(im: Image.Image, t: float, z: float, tc: str, box, lock: float, accent, W: int, H: int):
    d = ImageDraw.Draw(im)
    x0, y0, x1 = B.SAFE[0] * W, B.SAFE[1] * H, B.SAFE[2] * W
    f = _font(int(W * 0.034))
    ty = y0 + W * 0.05
    # REC: a red dot blinking once a second
    if (t % 1.0) < 0.6:
        r = W * 0.012
        d.ellipse([x0 + W * 0.035 - r, ty - r, x0 + W * 0.035 + r, ty + r], fill=(255, 59, 48, 255))
    d.text((x0 + W * 0.06, ty), "REC", font=f, fill=INK + (240,), anchor="lm")
    d.text((x1 - W * 0.03, ty), tc, font=f, fill=INK + (240,), anchor="rm")
    # zoom pill over a tick ruler that slides with the zoom
    cx = (x0 + x1) / 2
    label = f"{z:.1f}×"
    fz = _font(int(W * 0.038))
    tw = d.textlength(label, font=fz)
    py = ty + W * 0.075
    d.rounded_rectangle([cx - tw / 2 - 26, py - 36, cx + tw / 2 + 26, py + 36], radius=36, fill=(0, 0, 0, 110))
    d.text((cx, py), label, font=fz, fill=INK + (255,), anchor="mm")
    ry, gap = py + 66, W * 0.016
    for k in range(5, 51):
        v = k / 10
        x = cx + (v - z) * 10 * gap
        a = max(0.0, 1 - abs(x - cx) / (W * 0.2))
        if a <= 0:
            continue
        hgt = 20 if k % 10 == 0 else (13 if k % 5 == 0 else 8)
        d.line([(x, ry - hgt / 2), (x, ry + hgt / 2)], fill=INK + (int(220 * a),), width=3 if k % 10 == 0 else 2)
    d.polygon([(cx - 8, ry + 18), (cx + 8, ry + 18), (cx, ry + 8)], fill=accent + (255,))
    # focus box on the face: yellow and slightly larger just after a step, settling to white
    if box is not None:
        bx, by, side = box
        grow = 1 + 0.25 * lock
        h = side * grow / 2
        col = tuple(int(accent[i] * lock + INK[i] * (1 - lock)) for i in range(3)) + (255,)
        brackets(d, bx - h, by - h, bx + h, by + h, side * 0.2, 5, col)


def render(ctx):
    W, H = ctx.W, ctx.H
    zooms = [float(z) for z in ctx.param("zooms", PARAMS["zooms"])]
    if any(not 1.0 <= z <= 4.0 for z in zooms):
        raise ValueError("viewfinder zooms must be in [1, 4]")
    times = step_times(zooms, list(ctx.param("steps", PARAMS["steps"]) or []), ctx.dur)
    target = ctx.param("target", PARAMS["target"])
    accent = tuple(int(v) for v in cam.hex_rgb(ctx.param("accent", PARAMS["accent"])))
    tc0 = float(ctx.param("timecode", PARAMS["timecode"]))
    lm = ctx.landmarks(every=1)
    hud = static_hud(W, H, ctx.param("left_text", PARAMS["left_text"]), ctx.param("right_text", PARAMS["right_text"]))
    fw = ctx.face()["fw"]
    prev = None
    with ctx.writer() as write:
        for i, frame in enumerate(ctx.frames()):
            t = i / ctx.fps
            c = cam.resolve_target(target, lm, range(max(0, i - 3), min(ctx.n, i + 4)), (W, H))
            z = zoom_at(t, zooms, times)
            zp = zoom_at(t - 0.5 / ctx.fps, zooms, times) if prev is not None else z
            prev = z
            k = min(1.0, max(0.0, z - 1))
            dst = cam.cover_dst(c, max(z, 1.0), (c[0] + (W / 2 - c[0]) * 0.5 * k, c[1]), (W, H))
            img = frame if abs(z - 1) < 1e-4 and abs(zp - 1) < 1e-4 else cam.zoom_frame(
                frame, c, cam.blur_samples(max(zp, 1.0), max(z, 1.0), cam.corner_dist(c, (W, H))), dst)
            # the focus box follows the face through the zoom
            P = lm[i] if i < len(lm) else None
            box = None
            if P is not None:
                fc = P[[168, 13]].mean(0)
                sx, sy = dst[0] + (fc[0] - c[0]) * z, dst[1] + (fc[1] - c[1]) * z
                box = (sx, sy, min(fw * 1.25 * z, W * 0.8))
            since = min((t - t0 for t0 in times if t >= t0), default=None)
            lock = 0.0 if since is None or since > LOCK else 1 - since / LOCK
            if t < 0.2:
                lock = max(lock, 1 - t / 0.2)
            layer = hud.copy()
            draw_dynamic(layer, t, z, timecode(tc0 + t, ctx.fps), box, lock, accent, W, H)
            A = np.asarray(layer, np.float32) / 255
            env = B.ease_out(B.progress(t, 0, FADE)) * (1 - B.ease_in(B.progress(t, ctx.dur - FADE, FADE)))
            a = A[..., 3:4] * env
            F = img.astype(np.float32) / 255
            out = F * (1 - a) + A[..., :3] * a
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out
