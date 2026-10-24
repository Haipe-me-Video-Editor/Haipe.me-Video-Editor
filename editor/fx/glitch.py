"""Glitch: a burst of digital damage peaking on the hit: RGB split, horizontal slices torn sideways, a few blocky
macro-pixels and scanlines. With `mosh`, a datamosh: for a few frames after the hit the old picture is smeared along
the new picture's motion (optical flow) before the new one resolves, the look of a broken video stream. Put the
window across a cut for a transition, or on a word."""
import cv2
import numpy as np

NAME = "glitch"
DOC = ("Digital glitch burst (RGB split, torn slices, blocks, scanlines) peaking on `hit`; mosh adds a datamosh "
       "smear. Across a cut as a transition or on a word; 0.4-1.2 s.")
BEST_FOR = ["playful", "product"]
DUR = (0.3, 3)
PARAMS = {
    "hit": None,       # s into the window of the peak (default the middle)
    "amount": 0.7,     # 0-1
    "spread": 0.25,    # s either side of the hit the damage lasts
    "mosh": False,     # datamosh smear after the hit
    "mosh_len": 0.3,   # s of smear
    "seed": 11,
}


def strength(t: float, hit: float, spread: float) -> float:
    u = abs(t - hit) / max(spread, 1e-6)
    return float(max(0.0, 1 - u) ** 1.5)


def damage(f: np.ndarray, k: float, rng) -> np.ndarray:
    """One glitched frame (uint8 RGB) at strength k 0-1."""
    if k <= 0.02:
        return f
    H, W = f.shape[:2]
    g = f.copy()
    o = int(round(W * 0.025 * k))
    if o:
        g[:, o:, 0] = f[:, :-o, 0]
        g[:, :-o, 2] = f[:, o:, 2]
    for _ in range(int(3 + 9 * k)):  # torn slices
        y0 = int(rng.uniform(0, H))
        h = int(rng.uniform(H * 0.004, max(H * 0.004 + 1, H * 0.05 * k + 2)))
        dx = int(rng.normal(0, W * 0.08 * k))
        g[y0:y0 + h] = np.roll(g[y0:y0 + h], dx, axis=1)
    for _ in range(int(4 * k)):  # macro-blocks
        bw, bh = int(rng.uniform(W * 0.05, W * 0.2)), int(rng.uniform(H * 0.01, H * 0.05))
        x, y = int(rng.uniform(0, W - bw)), int(rng.uniform(0, H - bh))
        blk = g[y:y + bh, x:x + bw]
        small = cv2.resize(blk, (max(1, bw // 16), max(1, bh // 16)), interpolation=cv2.INTER_AREA)
        g[y:y + bh, x:x + bw] = cv2.resize(small, (bw, bh), interpolation=cv2.INTER_NEAREST)
    g[::3] = (g[::3].astype(np.float32) * (1 - 0.25 * k)).astype(np.uint8)  # scanlines
    return g


def flow(a: np.ndarray, b: np.ndarray, scale: int = 4) -> np.ndarray:
    """Dense flow from frame a to b (full-size pixels), computed at 1/scale."""
    H, W = a.shape[:2]
    ga = cv2.cvtColor(cv2.resize(a, (W // scale, H // scale)), cv2.COLOR_RGB2GRAY)
    gb = cv2.cvtColor(cv2.resize(b, (W // scale, H // scale)), cv2.COLOR_RGB2GRAY)
    fl = cv2.calcOpticalFlowFarneback(gb, ga, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    return cv2.resize(fl, (W, H)) * scale


def mosh(prev_out: np.ndarray, prev_src: np.ndarray, cur: np.ndarray, keep: float) -> np.ndarray:
    """The previous output pushed along the motion into this frame, `keep` of it kept over the new frame."""
    H, W = cur.shape[:2]
    fl = flow(prev_src, cur)
    gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    smear = cv2.remap(prev_out, gx + fl[..., 0], gy + fl[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return (smear.astype(np.float32) * keep + cur.astype(np.float32) * (1 - keep)).astype(np.uint8)


def render(ctx):
    hit = ctx.param("hit")
    hit = float(hit) if hit is not None else ctx.dur / 2
    amount, spread = float(ctx.param("amount", PARAMS["amount"])), float(ctx.param("spread", PARAMS["spread"]))
    use_mosh, mlen = bool(ctx.param("mosh", PARAMS["mosh"])), float(ctx.param("mosh_len", PARAMS["mosh_len"]))
    rng = np.random.default_rng(int(ctx.param("seed", PARAMS["seed"])))
    prev_out = prev_src = None
    with ctx.writer() as w:
        for i, f in enumerate(ctx.frames()):
            t = i / ctx.fps
            base = f
            if use_mosh and prev_out is not None and hit <= t < hit + mlen:
                base = mosh(prev_out, prev_src, f, 0.85 * (1 - (t - hit) / mlen))
            out = damage(base, amount * strength(t, hit, spread), rng)
            w(out)
            prev_out, prev_src = base, f
    return ctx.out
