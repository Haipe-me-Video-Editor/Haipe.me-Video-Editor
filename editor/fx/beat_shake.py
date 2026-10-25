"""Beat shake: a short, punchy camera shake (with a small punch-in and a flick of RGB split) on each hit: the music's
drops, or the words to stress. Static phone footage gets rhythm. The frame is overscanned so no edge ever shows."""
import math

import cv2
import numpy as np

from . import _camera as cam

NAME = "beat_shake"
DOC = ("Punchy camera shake + tiny punch-in + RGB flick on each hit (music drops or stressed words). `hits` are "
       "seconds into the window; keep it to the moments that matter, never on a timer.")
BEST_FOR = ["playful", "product", "any"]
DUR = (0.3, 20)
PARAMS = {
    "hits": [0.0],     # seconds into the window
    "amount": 0.5,     # 0-1: shake strength (1 is violent)
    "punch": 0.04,     # extra zoom on each hit
    "split": False,    # RGB split for the first frames of each hit (recolours the footage: off by house rule)
}
SHAKE_DUR = 0.3
OVERSCAN = 1.03


def motion(t: float, hits: list, amount: float, punch: float, W: int) -> tuple:
    """(dx, dy, rot, scale, split) at time t: every hit's damped shake added up, the punch decaying after each."""
    dx = dy = rot = 0.0
    s = OVERSCAN
    split = 0.0
    for k, h in enumerate(hits):
        u = t - h
        if 0 <= u <= SHAKE_DUR:
            a, b, r = cam.shake(u, amount * W * 0.028, SHAKE_DUR, seed=3 + k)
            dx, dy, rot = dx + a, dy + b, rot + r
            env = (1 - u / SHAKE_DUR) ** 2
            s += punch * env
            split = max(split, env if u < 0.1 else 0.0)
    return dx, dy, rot, s, split


def render(ctx):
    hits = sorted(float(h) for h in (ctx.param("hits") or PARAMS["hits"]))
    amount, punch = float(ctx.param("amount", PARAMS["amount"])), float(ctx.param("punch", PARAMS["punch"]))
    split_on = bool(ctx.param("split", PARAMS["split"]))
    W, H = ctx.W, ctx.H
    c = (W / 2, H / 2)
    with ctx.writer() as w:
        for i, f in enumerate(ctx.frames()):
            dx, dy, rot, s, split = motion(i / ctx.fps, hits, amount, punch, W)
            s *= 1 + H / W * abs(math.radians(rot))  # rotation needs a little more overscan
            dst = cam.cover_dst(c, s, (c[0] + dx, c[1] + dy), (W, H))
            M = cam.zoom_matrix(c, s, dst, rot).astype(np.float32)
            g = cv2.warpAffine(f, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            o = int(round(W * 0.008 * split)) if split_on else 0
            if o:
                g = g.copy()
                g[:, o:, 0] = g[:, :-o, 0].copy()
                g[:, :-o, 2] = g[:, o:, 2].copy()
            w(g)
    return ctx.out
