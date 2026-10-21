"""Noir minimal: the storytelling look. The room disappears to black; the speaker, cut out, in contrasty black and
white with a soft white glow around them; one lowercase serif line above; optionally a small orb of light drifting
across the frame. Calm and editorial: for the story beats between the busy parts. Pairs with line_art cards."""
import math

import cv2
import numpy as np

from . import _glass as G
from . import _looks as L

NAME = "noir_minimal"
DOC = ("Storytelling look: room goes black, speaker in black and white with a soft white glow, one lowercase serif "
       "line above, optional drifting light orb. For calm story beats; pairs with line_art cards. 2-12 s.")
BEST_FOR = ["any", "corporate"]
DUR = (1.0, 30)
PARAMS = {
    "text": "",        # one short lowercase line in a serif (Arabic: Amiri); empty for none
    "text_at": 0.15,   # s into the window the line fades in
    "text_y": 0.11,    # top of the line, 0-1 of the height
    "glow": 0.7,       # 0-1: the white halo round the speaker
    "mono": True,      # black and white speaker (False keeps colour)
    "scale": 0.92,     # the speaker a little smaller, anchored at the bottom, for headroom
    "orb": False,      # a small glowing orb drifting across
    "bg": "#000000",
    "enter": 0.3,      # s: the room fades to black (0: cut straight in)
}


def frame(F: np.ndarray, a: np.ndarray, p: float, glow: float, mono: bool, scale: float, bg) -> np.ndarray:
    """One frame: the speaker scaled about the bottom centre onto `bg`, the room faded to it by p."""
    H, W = a.shape
    M = np.float32([[scale, 0, W / 2 * (1 - scale)], [0, scale, H * (1 - scale)]])
    P = cv2.warpAffine(F, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    A = cv2.warpAffine(a, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    if mono:
        y = np.clip((L.luma(P) - 0.5) * 1.25 + 0.5, 0, 1)
        P = np.repeat(y[..., None], 3, axis=2)
    back = np.broadcast_to(np.asarray(bg, np.float32), F.shape)
    small = cv2.resize(A, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    halo = cv2.resize(cv2.GaussianBlur(small, (0, 0), W / 220), (W, H))
    back = L.screen(back, (np.clip(halo * 1.6 - A, 0, 1) * 0.55 * glow)[..., None])
    look = back * (1 - A[..., None]) + P * A[..., None]
    return F + (look - F) * p if p < 1 else look


def orb(H: int, W: int, t: float, dur: float) -> np.ndarray:
    """A small soft white light on a slow drifting path (alpha 0-1)."""
    u = t / max(dur, 1e-6)
    cx = W * (0.5 + 0.28 * math.sin(u * math.pi * 1.3 + 0.4))
    cy = H * (0.36 + 0.08 * math.sin(u * math.pi * 2.1))
    m = np.zeros((H, W), np.float32)
    cv2.circle(m, (int(cx), int(cy)), max(2, W // 70), 1.0, -1, cv2.LINE_AA)
    return np.clip(m + cv2.GaussianBlur(m, (0, 0), W / 60) * 2.5, 0, 1)


def render(ctx):
    P = {k: ctx.param(k, v) for k, v in PARAMS.items()}
    bg = L.hex_rgb(P["bg"])
    pic = ctx.work / "noir.mp4"
    with ctx.writer(pic) as w:
        for i, (f, pr) in enumerate(zip(ctx.frames(), ctx.frames(ctx.person(), rgba=True))):
            t = i / ctx.fps
            p = L.envelope(t, 1e9, float(P["enter"]), 0)
            a = pr[..., 3].astype(np.float32) / 255
            # the cut-out's own colour at the edge (cleaned of the room), the camera's elsewhere
            F = np.where((a > 0.01)[..., None], pr[..., :3], f).astype(np.float32) / 255
            out = frame(F, a, p, float(P["glow"]), bool(P["mono"]), float(P["scale"]), bg)
            if P["orb"]:
                out = L.screen(out, orb(ctx.H, ctx.W, t, ctx.dur)[..., None] * p)
            w(L.to8(out))
    if not P["text"]:
        import shutil
        shutil.copy2(pic, ctx.out)
        return ctx.out
    return ctx.stack([pic, ctx.layer(_page(ctx, str(P["text"]), float(P["text_at"]), float(P["text_y"])), "noir")])


def _page(ctx, text, at, y):
    is_rtl = G.rtl([text])
    size = round(ctx.W * (0.058 if len(text) <= 24 else 0.046))
    words = "".join(f'<span class="w">{G.esc(w)}</span> ' for w in text.split())
    css = f"""
#line{{position:absolute;left:{ctx.W * 0.08:.0f}px;right:{ctx.W * 0.08:.0f}px;top:{y * ctx.H:.0f}px;
  font-family:"{'AmiriSerif' if is_rtl else 'InstrumentSerif'}",serif;font-size:{size}px;font-weight:400;color:#fff;
  direction:{'rtl' if is_rtl else 'ltr'};text-align:{'right' if is_rtl else 'left'};line-height:1.25}}
.w{{display:inline-block;opacity:0}}"""
    js = (f"tl.fromTo('#line .w',{{opacity:0,y:10,filter:'blur(8px)'}},"
          f"{{opacity:1,y:0,filter:'blur(0px)',duration:.6,stagger:.12,ease:'power2.out'}},{at:.3f});")
    return ctx.page(f'<div id="line">{words}</div>', css, js)
