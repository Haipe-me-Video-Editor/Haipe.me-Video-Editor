"""Digital zoom: an animated punch-in on the speaker's face mid-shot, either a spring snap (with real motion blur
and an optional shake on the hit) or a slow push, then an eased release back to the full frame.

Different from edit.json's `segments[].zoom` (a static crop for a whole segment) and `push` (a slow ease from the
segment's start) and the cut-only `zoom` transition: this one lands on a word, anywhere inside a shot.
"""
import math

from . import _camera as cam

NAME = "digital_zoom"
DOC = ("Animated punch-in on the face mid-shot: spring snap with motion blur (and an optional shake on the hit) or "
       "a slow push, then eases back. Put `at` on the word to hit.")
BEST_FOR = ["product", "finance", "corporate", "any"]
DUR = (0.6, 10)
PARAMS = {
    "amount": 1.3,       # zoom at the hit (1.1 subtle .. 1.8 dramatic)
    "mode": "snap",      # snap (spring, ~0.4 s) | push (eased over the whole window)
    "target": "face",    # face | eye | mouth | center | [x, y] in 0-1: the point the zoom closes on
    "hit": 0.0,          # seconds into the window when the zoom starts
    "shake": 0.0,        # 0-1: a damped shake on the hit (snap only); 0.4 is a firm thump
    "release": True,     # ease back to the full frame in the last `out` seconds (False: hold, end on a cut)
    "out": 0.35,         # release length, s
    "centre": 0.5,       # 0-1: how far the zoom pulls the target towards the frame's centre line
    "spring": "snappy",  # snap spring: gentle | snappy | bouncy
}
SNAP = 0.42     # spring length, s
SHUTTER = 0.5   # fraction of a frame the virtual shutter is open (180 degrees)
SHAKE_PX = 22   # shake amplitude at shake=1, output pixels


def zoom_curve(t: float, dur: float, amount: float, mode: str = "snap", hit: float = 0.0, release: bool = True,
               out: float = 0.35, preset: str = "snappy") -> float:
    """Zoom factor at time t (s) in the window: 1 before the hit, up to `amount`, back to 1 at the end if release."""
    if mode not in ("snap", "push"):
        raise ValueError("digital_zoom mode is snap or push")
    out = min(out, max(0.0, dur - hit) * 0.45) if release else 0.0
    end = dur - out
    if t < hit:
        k = 0.0
    elif mode == "snap":
        k = cam.spring_ease(preset)(min(1.0, (t - hit) / SNAP))
    else:
        k = cam.ease("inout", (t - hit) / max(1e-6, end - hit))
    if release and t > end:
        k *= 1 - cam.ease("inout", (t - end) / max(1e-6, out))
    return max(1.0, 1 + (amount - 1) * k)


def render(ctx):
    amount = float(ctx.param("amount", PARAMS["amount"]))
    if not 1.0 < amount <= 3.0:
        raise ValueError("digital_zoom amount must be in (1, 3]")
    mode = ctx.param("mode", PARAMS["mode"])
    hit = float(ctx.param("hit", PARAMS["hit"]))
    release = bool(ctx.param("release", PARAMS["release"]))
    out = float(ctx.param("out", PARAMS["out"]))
    preset = ctx.param("spring", PARAMS["spring"])
    shake_amt = float(ctx.param("shake", PARAMS["shake"])) if mode == "snap" else 0.0
    centre = float(ctx.param("centre", PARAMS["centre"]))
    target = ctx.param("target", PARAMS["target"])
    size, fps = (ctx.W, ctx.H), ctx.fps
    lm = ctx.landmarks(every=2) if target != "center" and not isinstance(target, (list, tuple)) else []
    h0 = int(hit * fps)
    c = cam.resolve_target(target, lm, range(max(0, h0 - 6), min(ctx.n, h0 + int(0.8 * fps))), size)
    rmax = cam.corner_dist(c, size)
    last = (ctx.n - 1) / fps  # the release lands exactly on the window's last frame
    curve = [zoom_curve(i / fps, last, amount, mode, hit, release, out, preset) for i in range(ctx.n + 1)]
    prev_t = [i / fps - SHUTTER / fps for i in range(ctx.n)]
    # the shake starts when the spring first reaches the target (the "hit")
    t_hit = hit + next((i / fps - hit for i in range(h0, ctx.n) if curve[i] >= amount - 1e-3), 0.12)
    with ctx.writer() as w:
        for i, f in enumerate(ctx.frames()):
            t = i / fps
            s = curve[i]
            s_prev = zoom_curve(prev_t[i], last, amount, mode, hit, release, out, preset)
            k = (s - 1) / (amount - 1)
            dst = (c[0] + (ctx.W / 2 - c[0]) * centre * k, c[1])
            dx, dy, rot = cam.shake(t - t_hit, SHAKE_PX * shake_amt * k)
            if rot:
                s_rot = 1 + ctx.H / ctx.W * abs(math.radians(rot))
                s, s_prev = s * s_rot, s_prev * s_rot
            dst = cam.cover_dst(c, min(s, s_prev), (dst[0] + dx, dst[1] + dy), size)
            if abs(s - 1) < 1e-4 and abs(s_prev - 1) < 1e-4 and not rot:
                w(f)
                continue
            w(cam.zoom_frame(f, c, cam.blur_samples(s_prev, s, rmax), dst, rot))
    return ctx.out
