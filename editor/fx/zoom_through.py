"""Zoom-through cut: the camera rushes into a point on the speaker (between the eyes, an eye, the mouth) with real
radial motion blur, punches through on a bright frame, and lands in the next shot, which settles from an overscale.

The window must span the cut: the effect gets one clip holding both shots. The cut is found by frame difference
(or given as `cut`, seconds into the window). Without a cut it still works: a punch into the point and back out.
"""
import numpy as np

from . import _camera as cam

NAME = "zoom_through"
DOC = ("Transition across a cut: rush into the speaker's face with motion blur, punch through, land in the next shot "
       "settling from an overscale. Centre the window on the cut (e.g. at = cut - 0.6, dur 1.4).")
BEST_FOR = ["product", "finance", "corporate", "any"]
DUR = (0.8, 4)
PARAMS = {
    "cut": None,         # seconds into the window where shot B starts; default: found by frame difference
    "target": "face",    # where to rush in on shot A: face | eye | mouth | center | [x, y] in 0-1
    "target_b": "face",  # the point shot B settles about
    "rush": 0.45,        # length of the rush in, s
    "settle": 0.5,       # length of shot B's settle, s
    "depth": 7.0,        # zoom reached on shot A's last frame
    "overscale": 1.45,   # zoom shot B starts from
    "flash": 0.18,       # 0-1 brightness of the punch-through frames
}
SHUTTER = 0.6  # of a frame
RUSH_POW = 2.4


def find_cut(small: np.ndarray, min_ratio: float = 4.0, min_diff: float = 12.0):
    """Index of the first frame of the second shot in small grey frames (N, h, w), or None when there is no cut.
    A cut is the one frame step whose difference towers over the window's typical (motion) difference."""
    if len(small) < 3:
        return None
    f = small.astype(np.float32)
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    # colour/exposure jumps count too: difference of the frame means, scaled
    d = d + 0.5 * np.abs(np.diff(f.mean(axis=(1, 2))))
    i = int(np.argmax(d))
    rest = np.delete(d, i)
    base = float(np.median(rest)) if len(rest) else 0.0
    if d[i] < min_diff or d[i] < min_ratio * max(base, 1.0):
        return None
    return i + 1


def rush_scale(t: float, tc: float, rush: float, depth: float) -> float:
    """Shot A's zoom: 1 until the rush starts, accelerating to `depth` at the cut."""
    u = (t - (tc - rush)) / rush
    if u <= 0:
        return 1.0
    return float(depth ** (min(u, 1.0) ** RUSH_POW))


def settle_scale(t: float, tc: float, settle: float, over: float) -> float:
    """Shot B's zoom: `over` at the cut, decelerating to 1 (cubic out; before the cut it keeps rising, so the first
    frame of B carries the blur of the punch)."""
    v = (t - tc) / settle
    if v >= 1:
        return 1.0
    return float(1 + (over - 1) * (1 - v) ** 3) if v >= 0 else float(over * (1 + 12 * -v))


def flash_at(t: float, tc: float, fps: float, amount: float) -> float:
    """Exposure lift around the cut: peaks on the last A frame and first B frame, gone 3 frames out."""
    d = abs(t - (tc - 0.5 / fps)) * fps  # in frames from the cut
    return amount * max(0.0, 1 - max(0.0, d - 0.5) / 2.5)


def render(ctx):
    import cv2
    fps, n, size = ctx.fps, ctx.n, (ctx.W, ctx.H)
    rush = float(ctx.param("rush", PARAMS["rush"]))
    settle = float(ctx.param("settle", PARAMS["settle"]))
    depth = float(ctx.param("depth", PARAMS["depth"]))
    over = float(ctx.param("overscale", PARAMS["overscale"]))
    flash = float(ctx.param("flash", PARAMS["flash"]))
    if depth < 1.5 or over < 1:
        raise ValueError("zoom_through needs depth >= 1.5 and overscale >= 1")
    cut = ctx.param("cut")
    if cut is None:
        small = np.stack([cv2.resize(cv2.cvtColor(np.ascontiguousarray(f), cv2.COLOR_RGB2GRAY), (36, 64),
                                     interpolation=cv2.INTER_AREA) for f in ctx.frames()])
        ci = find_cut(small)
        ci = ci if ci is not None else n // 2
    else:
        ci = round(float(cut) * fps)
    ci = min(max(int(ci), 2), n - 1)
    tc = ci / fps
    rush = min(rush, tc)
    settle = min(settle, ctx.dur - tc)
    lm = ctx.landmarks(every=2)
    a_idx = range(max(0, ci - int(rush * fps) - 4), max(1, ci - 2))
    b_idx = range(min(n - 1, ci + 4), min(n, ci + 4 + int(0.6 * fps)))
    ta = cam.resolve_target(ctx.param("target", PARAMS["target"]), lm, a_idx, size)
    tb = cam.resolve_target(ctx.param("target_b", PARAMS["target_b"]), lm, b_idx, size)
    mid = (ctx.W / 2, ctx.H / 2)
    with ctx.writer() as w:
        for i, f in enumerate(ctx.frames()):
            t = i / fps
            # the shutter opens wider on the punch-through frames, so they smear into one another
            t0 = t - SHUTTER * (1.8 if ci - 2 <= i <= ci else 1.0) / fps
            if i < ci:
                s1, s0 = rush_scale(t, tc, rush, depth), rush_scale(t0, tc, rush, depth)
                if s1 <= 1.0001:
                    out = f
                else:
                    k = np.log(s1) / np.log(depth)  # the camera swings the target to the centre as it closes in
                    dst = (ta[0] + (mid[0] - ta[0]) * k, ta[1] + (mid[1] - ta[1]) * k)
                    dst = cam.cover_dst(ta, s0, dst, size)
                    out = cam.zoom_frame(f, ta, cam.blur_samples(s0, s1, cam.corner_dist(dst, size), cap=28), dst)
            else:
                s1, s0 = settle_scale(t, tc, settle, over), settle_scale(t0, tc, settle, over)
                if s1 <= 1.0001 and s0 <= 1.0001:
                    out = f
                else:
                    dst = cam.cover_dst(tb, min(s0, s1), tb, size)
                    out = cam.zoom_frame(f, tb, cam.blur_samples(s0, s1, cam.corner_dist(dst, size), cap=28), dst)
            lift = flash_at(t, tc, fps, flash)
            if lift > 0.005:
                out = cv2.convertScaleAbs(out, alpha=1 + 2.2 * lift, beta=60 * lift)  # exposure, not a white fade
            w(out)
    return ctx.out
