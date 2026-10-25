"""Portal: a small round window pops up in a corner showing a close-up of the speaker's face (a white ring, a soft
shadow), floats there for a beat, then swells and races across the frame until it swallows it, landing on the
close-up full screen. Optionally it eases back out to the wide shot at the end.

The window shows the whole head small at first, and its picture zooms in as it grows, ending on exactly the image
the window lands on (the frame zoomed about the face, the face at the circle's centre), so when the circle covers
the frame the cut is invisible.
"""

import cv2
import numpy as np

from . import _behind as B
from . import _camera as cam

NAME = "portal"
DOC = ("A round window with a close-up of the face pops up in a corner, then grows until it fills the frame and "
       "the shot lands on the close-up (optionally easing back to wide). A punch-in with a reveal; for an aside, "
       "a reaction, or 'now look at this'.")
BEST_FOR = ["playful", "product", "any"]
DUR = (1.2, 8)
PARAMS = {
    "corner": "tl",      # tl | tr | bl | br: where the window pops up (inside the safe zone)
    "size": 0.26,        # window diameter as a fraction of the frame width
    "amount": 1.8,       # close-up zoom (1.3 .. 3)
    "target": "face",    # face | eye | mouth | center | [x, y] in 0-1: what the close-up centres on
    "grow_at": 0.7,      # seconds into the window when it starts to grow
    "grow": 0.45,        # how long the grow takes, s
    "release": True,     # ease back out to the wide shot in the last `out` seconds
    "out": 0.4,
    "ring": "#ffffff",   # ring colour
}
POP = 0.45


def corner_centre(corner: str, R: float, W: int, H: int) -> tuple:
    if corner not in ("tl", "tr", "bl", "br"):
        raise ValueError("portal corner is tl, tr, bl or br")
    pad = R * 0.25
    x = B.SAFE[0] * W + R + pad if corner[1] == "l" else B.SAFE[2] * W - R - pad
    y = B.SAFE[1] * H + R + pad if corner[0] == "t" else B.SAFE[3] * H - R - pad
    return x, y


def disc(W: int, H: int, c, R: float) -> np.ndarray:
    """Anti-aliased disc coverage, float32 (H, W); only the bounding box is computed."""
    out = np.zeros((H, W), np.float32)
    x0, y0 = max(int(c[0] - R - 2), 0), max(int(c[1] - R - 2), 0)
    x1, y1 = min(int(c[0] + R + 3), W), min(int(c[1] + R + 3), H)
    if x1 <= x0 or y1 <= y0:
        return out
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32) + 0.5
    out[y0:y1, x0:x1] = np.clip(R - np.hypot(xx - c[0], yy - c[1]) + 0.5, 0, 1)
    return out


def render(ctx):
    W, H = ctx.W, ctx.H
    amount = float(ctx.param("amount", PARAMS["amount"]))
    if not 1.2 <= amount <= 3:
        raise ValueError("portal amount must be in [1.2, 3]")
    R0 = float(ctx.param("size", PARAMS["size"])) * W / 2
    grow_at = float(ctx.param("grow_at", PARAMS["grow_at"]))
    grow = float(ctx.param("grow", PARAMS["grow"]))
    release = bool(ctx.param("release", PARAMS["release"]))
    out_len = min(float(ctx.param("out", PARAMS["out"])), max(0.0, ctx.dur - grow_at - grow) * 0.6) if release else 0.0
    ring = cam.hex_rgb(ctx.param("ring", PARAMS["ring"])) / 255
    target = ctx.param("target", PARAMS["target"])
    lm = ctx.landmarks(every=2) if not isinstance(target, (list, tuple)) and target != "center" else []
    c0 = corner_centre(ctx.param("corner", PARAMS["corner"]), R0, W, H)
    # in the small window the whole head shows (face ~60% of the diameter); the zoom then grows to `amount`
    s_small = min(amount, 1.2 * R0 / max(ctx.face()["fw"], 1.0))
    prev_s = None
    pop = B.spring("bouncy")
    with ctx.writer() as write:
        for i, frame in enumerate(ctx.frames()):
            t = i / ctx.fps
            face = cam.resolve_target(target, lm, range(max(0, i - 4), min(ctx.n, i + 5)), (W, H))
            # where the face sits in the full-frame close-up (pulled towards the centre line, frame covered)
            land = cam.cover_dst(face, amount, (face[0] + (W / 2 - face[0]) * 0.5, face[1]), (W, H))
            g = B.ease_in(B.progress(t, grow_at, grow)) ** 1.4
            back = B.ease_in(B.progress(t, ctx.dur - out_len, out_len)) if out_len > 0 else 0.0
            if g >= 1:  # full screen: the close-up, then the release back to wide
                s = amount + (1 - amount) * back
                if s <= 1 + 1e-4:
                    write(frame)
                    continue
                k = (s - 1) / (amount - 1)
                dst = cam.cover_dst(face, s, (face[0] + (land[0] - face[0]) * k, face[1] + (land[1] - face[1]) * k),
                                    (W, H))
                write(cam.zoom_frame(frame, face, [s], dst))
                continue
            sc = max(pop(B.progress(t, 0.0, POP)), 0.0)
            if sc < 0.01:
                write(frame)
                continue
            c = (c0[0] + (land[0] - c0[0]) * g, c0[1] + (land[1] - c0[1]) * g)
            R = R0 * sc + (cam.corner_dist(c, (W, H)) + 4 - R0) * g
            s_in = s_small + (amount - s_small) * g
            scales = cam.blur_samples(prev_s, s_in, R) if prev_s and g > 0 else [s_in]
            prev_s = s_in
            close = cam.zoom_frame(frame, face, scales, c).astype(np.float32) / 255
            F = frame.astype(np.float32) / 255
            D = disc(W, H, c, R)
            ringw = max(2.0, R0 * 0.045) * (1 - g)
            Dr = disc(W, H, c, R + ringw)
            # shadow under the window
            small = cv2.resize(Dr, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
            sh = cv2.GaussianBlur(small, (0, 0), 5)
            sh = cv2.warpAffine(sh, np.float32([[1, 0, 0], [0, 1, 3]]), (W // 4, H // 4))
            out = F * (1 - 0.35 * (1 - g) * cv2.resize(sh, (W, H))[..., None])
            out = out * (1 - Dr[..., None]) + ring * Dr[..., None]
            out = out * (1 - D[..., None]) + close * D[..., None]
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out
