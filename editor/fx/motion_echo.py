"""Motion echo: ghosted copies of the speaker trail behind them as they move (a hand flung out, a lean in), each
older copy fainter, optionally tinted. Built from the cut-out of earlier frames of the same window, so it only
shows where there is real movement and costs nothing on a still speaker."""
import numpy as np

from . import _looks as L

NAME = "motion_echo"
DOC = ("Ghost trails of the speaker on fast moves (gestures, a lean, a turn), fading with age, optional tint. "
       "Needs real movement in the window; 0.8-4 s.")
BEST_FOR = ["playful", "any"]
DUR = (0.5, 8)
PARAMS = {
    "count": 4,        # how many echoes
    "step": 2,         # frames between echoes
    "decay": 0.55,     # each older echo's opacity relative to the one before
    "opacity": 0.6,    # the newest echo's opacity
    "color": None,     # tint the echoes (e.g. the accent); None keeps their own colour
    "enter": 0.15,
    "exit": 0.2,
}


def composite(F: np.ndarray, a: np.ndarray, echoes: list, p: float, tint=None) -> np.ndarray:
    """F, a: this frame and its matte; echoes: [(rgb, alpha, weight)] oldest first. Echoes sit behind the
    speaker as they are now (never over them)."""
    out = F.copy()
    front = a[..., None]
    for rgb, ea, wgt in echoes:
        col = rgb if tint is None else rgb * 0.35 + np.asarray(tint, np.float32) * 0.65
        k = (ea * wgt * p)[..., None] * (1 - front)
        out = out * (1 - k) + col * k
    return out


def render(ctx):
    count, step = int(ctx.param("count", PARAMS["count"])), max(1, int(ctx.param("step", PARAMS["step"])))
    decay, opacity = float(ctx.param("decay", PARAMS["decay"])), float(ctx.param("opacity", PARAMS["opacity"]))
    tint = L.hex_rgb(ctx.param("color")) if ctx.param("color") else None
    enter, exit = float(ctx.param("enter", PARAMS["enter"])), float(ctx.param("exit", PARAMS["exit"]))
    if not 1 <= count <= 8:
        raise ValueError("motion_echo count must be 1-8")
    hist = []  # (rgb float, alpha) of the last count*step frames, newest last
    with ctx.writer() as w:
        for i, (f, pr) in enumerate(zip(ctx.frames(), ctx.frames(ctx.person(), rgba=True))):
            F, a = f.astype(np.float32) / 255, pr[..., 3].astype(np.float32) / 255
            rgb = pr[..., :3].astype(np.float32) / 255  # the cut-out's own (edge-cleaned) colour
            echoes = []
            for k in range(count, 0, -1):
                j = len(hist) - k * step
                if j >= 0:
                    echoes.append((hist[j][0], hist[j][1], opacity * decay ** (k - 1)))
            p = L.envelope(i / ctx.fps, (ctx.n - 1) / ctx.fps, enter, exit)
            w(L.to8(composite(F, a, echoes, p, tint)))
            hist.append((rgb, a))
            del hist[:-count * step]
    return ctx.out
