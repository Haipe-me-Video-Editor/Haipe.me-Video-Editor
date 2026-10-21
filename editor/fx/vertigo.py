"""Vertigo (dolly zoom): the speaker holds still in size while the room behind them zooms, the Hitchcock move.

How: the person matte splits the frame. The background is rebuilt without the person: a clean plate (the median of
every background pixel the window ever shows) fills where they stand, its hidden core inpainted and softened, and
its colour follows the live frame (so changing room light still matches). That background is zoomed about the face
with a defocus that grows with the move, and the person goes back on top through a background-swap composite
(out = frame + (1 - alpha) * (new bg - old bg)), so the old room never ghosts around their edge.
"""
import numpy as np

from . import _camera as cam

NAME = "vertigo"
DOC = ("Dolly zoom: the speaker stays the same size while the room behind them zooms in (or out). A slow, uneasy "
       "beat for a reveal or a big realisation. Static camera shots only.")
BEST_FOR = ["product", "finance", "corporate", "any"]
DUR = (1.2, 6)
PARAMS = {
    "amount": 0.3,       # background zoom at the peak (0.3 = 30% bigger); 0.1 subtle .. 0.6 extreme
    "direction": "in",   # in: the room looms closer | out: the room snaps close then stretches away
    "ease": "inout",     # linear | in | out | inout | expo
    "blur": 5.0,         # background defocus at the peak, output px (0 = none)
    "back": True,        # ease the room back to normal in the last 0.45 s (False: hold, end the window on a cut)
    "centre": None,      # [x, y] 0-1 vanishing point; default the face
}
LOW = 3            # plate resolution divisor
HOLE_PX = 30       # how far beyond the matte the old background is treated as unknown (output px)
BACK = 0.45        # release length, s
OUT_IN = 0.3       # direction=out: share of the window spent snapping the room close


def bg_scale(t: float, dur: float, amount: float, direction: str = "in", ease: str = "inout",
             back: bool = True) -> float:
    """Background zoom factor (>= 1: the plate never has to invent pixels past the frame edge) at time t."""
    if direction not in ("in", "out"):
        raise ValueError("vertigo direction is in or out")
    u = min(max(t / dur, 0.0), 1.0)
    if direction == "out":  # snap close (smooth), then a long stretch back to 1
        k = cam.ease("inout", u / OUT_IN) if u < OUT_IN else 1 - cam.ease(ease, (u - OUT_IN) / (1 - OUT_IN))
        return 1 + amount * k
    rel = min(BACK, dur * 0.3) if back else 0.0
    end = dur - rel
    k = cam.ease(ease, t / end) if t < end or rel <= 0 else 1 - cam.ease("inout", (t - end) / rel)
    return 1 + amount * k


def masked_median(stack: np.ndarray, valid: np.ndarray) -> tuple:
    """Per-pixel median of stack (N, h, w, 3) over frames where valid (N, h, w); returns (plate, seen mask)."""
    _, h, w, _ = stack.shape
    out = np.zeros((h, w, 3), np.float32)
    seen = valid.any(0)
    for r in range(0, h, 48):  # row chunks keep the float copy small
        s = stack[:, r:r + 48].astype(np.float32)
        s[~valid[:, r:r + 48]] = np.nan
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                out[r:r + 48] = np.nan_to_num(np.nanmedian(s, axis=0))
    return out, seen


def fill_holes(plate: np.ndarray, seen: np.ndarray) -> np.ndarray:
    """Inpaint never-seen pixels, then soften the inpainted core so it reads as out-of-focus room, not smears."""
    import cv2
    if seen.all():
        return plate
    if not seen.any():
        return plate
    p8 = np.clip(plate, 0, 255).astype(np.uint8)
    hole = (~seen).astype(np.uint8) * 255
    filled = cv2.inpaint(p8, hole, 9, cv2.INPAINT_TELEA).astype(np.float32)
    # push-pull: a heavy blur of the seen pixels, normalised, gives a smooth colour field to blend the core into
    wgt = cv2.GaussianBlur(seen.astype(np.float32), (0, 0), 14)
    smooth = cv2.GaussianBlur(plate * seen[..., None], (0, 0), 14) / np.maximum(wgt[..., None], 1e-3)
    depth = cv2.distanceTransform(hole, cv2.DIST_L2, 5)
    k = np.clip(depth / 25.0, 0, 1)[..., None]  # deep inside the hole: mostly the smooth field
    core = filled * (1 - 0.7 * k) + smooth * 0.7 * k
    core = cv2.GaussianBlur(core, (0, 0), 3.5)
    return np.where(seen[..., None], plate, core)


def render(ctx):
    import cv2
    amount = float(ctx.param("amount", PARAMS["amount"]))
    if not 0.02 <= amount <= 1.0:
        raise ValueError("vertigo amount must be 0.02-1.0")
    direction = ctx.param("direction", PARAMS["direction"])
    ease = ctx.param("ease", PARAMS["ease"])
    blur = float(ctx.param("blur", PARAMS["blur"]))
    back = bool(ctx.param("back", PARAMS["back"]))
    W, H, n, fps = ctx.W, ctx.H, ctx.n, ctx.fps
    w, h = W // LOW, H // LOW
    centre = ctx.param("centre")
    if centre:
        c = (float(centre[0]) * W, float(centre[1]) * H)
    else:
        f = ctx.face()
        c = (f["cx"], f["eye_y"])
    last = (n - 1) / fps  # the move lands exactly on the last frame
    curve = [bg_scale(i / fps, last, amount, direction, ease, back) for i in range(n)]
    scales = [(bg_scale((i - 0.5) / fps, last, amount, direction, ease, back), curve[i]) for i in range(n)]
    rmax = cam.corner_dist(c, (W, H))

    # pass 1: low-res frames and "unknown" masks -> clean plate
    grow = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * (HOLE_PX // LOW) + 1,) * 2)
    smalls = np.zeros((n, h, w, 3), np.uint8)
    holes = np.zeros((n, h, w), bool)
    for i, (f, a) in enumerate(zip(ctx.frames(), ctx.mattes())):
        smalls[i] = cv2.resize(f, (w, h), interpolation=cv2.INTER_AREA)
        holes[i] = cv2.dilate((cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA) > 0.04).astype(np.uint8), grow) > 0
    plate, seen = masked_median(smalls, ~holes)
    plate = fill_holes(plate, seen)
    # per-frame colour gain: the live room light against the plate, over pixels both can see, smoothed in time
    gains = np.ones((n, 3), np.float32)
    for i in range(n):
        vis = ~holes[i] & seen
        if vis.sum() > 200:
            gains[i] = (smalls[i][vis].astype(np.float32).mean(0) + 1) / (plate[vis].mean(0) + 1)
    k = np.exp(-0.5 * (np.arange(-6, 7) / 3.0) ** 2)
    gains = np.stack([np.convolve(np.pad(gains[:, j], 6, mode="edge"), k / k.sum(), "valid") for j in range(3)], 1)
    del smalls

    # pass 2: per frame, old bg = frame outside the hole + plate inside; new bg = old bg zoomed and defocused
    with ctx.writer() as wr:
        for i, (f, a) in enumerate(zip(ctx.frames(), ctx.mattes())):
            s0, s1 = scales[i]
            if abs(s1 - 1) < 1e-4 and abs(s0 - 1) < 1e-4:
                wr(f)
                continue
            hole = cv2.GaussianBlur(holes[i].astype(np.float32), (0, 0), 2)
            hole = cv2.resize(hole, (W, H), interpolation=cv2.INTER_LINEAR)
            pl = cv2.resize(np.clip(plate * gains[i] + 0.5, 0, 255).astype(np.uint8), (W, H),
                            interpolation=cv2.INTER_CUBIC)
            f = np.ascontiguousarray(f)
            old = cv2.blendLinear(f, pl, 1 - hole, hole)
            sig = blur * (s1 - 1) / amount
            src = cv2.GaussianBlur(old, (0, 0), sig / s1) if sig > 0.3 else old
            new = cam.zoom_frame(src, c, cam.blur_samples(s0, s1, rmax, cap=8))
            # background swap: what the old room contributed to every pixel is replaced by the new room
            swap = np.clip(f.astype(np.int16) - old + new, 0, 255).astype(np.uint8)
            wr(cv2.blendLinear(f, swap, a, 1 - a))
    return ctx.out
