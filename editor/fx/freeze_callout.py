"""Freeze-frame callout: on the hit the picture freezes, the room drops to mono (or dims), the speaker lifts out of
the frame a few percent bigger with a white sticker border, and a label pops in; then everything snaps back live.
The voice keeps running underneath: the freeze is a beat for the eye, not a pause in the talk."""
import cv2
import numpy as np

from . import _camera as cam
from . import _glass as G
from . import _looks as L

NAME = "freeze_callout"
DOC = ("Freeze on a word: room goes mono, the speaker lifts out bigger with a sticker border, a label pops in, "
       "then back to live. For the key claim or a name; 1-2.5 s.")
BEST_FOR = ["playful", "product", "any"]
DUR = (0.6, 4)
PARAMS = {
    "label": "",        # the callout text (one short line; Arabic or English)
    "sub": "",          # optional smaller second line
    "hit": 0.0,         # s into the window where the picture freezes
    "hold": None,       # s frozen (default: to 0.15 s before the window ends)
    "bg": "mono",       # mono | dim | blur | tint
    "lift": 1.06,       # how much bigger the frozen speaker gets
    "border": True,     # white sticker border round the lifted speaker
    "y": None,          # label centre, 0-1 of the height (default: above the head if it fits, else under the chin)
}
LIFT_T = 0.22  # s for the lift spring to land


def lift_frame(F: np.ndarray, a: np.ndarray, c, s: float, p: float, bg: str, border_px: float) -> np.ndarray:
    """The frozen frame F (float 0-1) with its matte a: room treated by p, the speaker scaled by s about c."""
    H, W = a.shape
    back = F + (L.treat_bg(F, bg) - F) * p
    M = cam.zoom_matrix(c, s)
    PF = cv2.warpAffine(F, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    PA = cv2.warpAffine(a, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    out = back
    if border_px > 0:
        out = L.over(out, (1.0, 1.0, 1.0), L.ring(PA, border_px * p, soft=1.0) * (1 - PA))
    return L.over(out, PF, PA)


def render(ctx):
    label, sub = str(ctx.param("label", "") or ""), str(ctx.param("sub", "") or "")
    bg = ctx.param("bg", PARAMS["bg"])
    if bg not in L.BG_MODES or bg == "keep":
        raise ValueError(f"freeze_callout bg must be one of {L.BG_MODES[1:]}")
    hit = float(ctx.param("hit", PARAMS["hit"]))
    hold = ctx.param("hold")
    hold = float(hold) if hold is not None else max(0.3, ctx.dur - hit - 0.15)
    h0, h1 = int(round(hit * ctx.fps)), min(ctx.n, int(round((hit + hold) * ctx.fps)))
    if not 0 <= h0 < h1 <= ctx.n:
        raise ValueError("freeze_callout: hit and hold must fit inside the window")
    lift = float(ctx.param("lift", PARAMS["lift"]))
    border = 0.012 * ctx.W if ctx.param("border", PARAMS["border"]) else 0
    spring = cam.spring_ease("snappy")
    c = cam.resolve_target("face", ctx.landmarks(every=3), range(max(0, h0 - 3), h0 + 3), (ctx.W, ctx.H))
    frozen = None
    pic = ctx.work / "frozen.mp4"
    with ctx.writer(pic) as w:
        for i, (f, a) in enumerate(zip(ctx.frames(), ctx.mattes())):
            if i < h0 or i >= h1:
                w(f)
                continue
            if frozen is None:
                frozen = (f.astype(np.float32) / 255, a.copy())
            t = (i - h0) / ctx.fps
            k = spring(min(1.0, t / LIFT_T))
            w(L.to8(lift_frame(frozen[0], frozen[1], c, 1 + (lift - 1) * k, min(1.0, t / 0.12), bg, border)))
    if not label:
        import shutil
        shutil.copy2(pic, ctx.out)
        return ctx.out
    y = ctx.param("y")
    if y is None:
        pts = [p for p in ctx.landmarks(every=3)[max(0, h0 - 3):h0 + 4] if p is not None]
        y = label_y(np.median(np.stack(pts), axis=0) if pts else None, ctx.H)
    return ctx.stack([pic, ctx.layer(_page(ctx, label, sub, hit, hold, float(y)), "callout")])


def label_y(P, H: int, need: float = 0.12) -> float:
    """Where the label's centre goes (0-1 of the height), clear of the face: above the head when there is `need` of
    the height free over it, else just under the chin. P: a (478, 2) face, or None (a typical framing)."""
    if P is None:
        return 0.13
    top = (P[10, 1] - 0.45 * (P[152, 1] - P[10, 1])) / H  # landmark 10 is the hairline: the crown is higher
    chin = P[152, 1] / H
    return top / 2 if top >= need else min(0.8, chin + need * 0.6)


def _page(ctx, label, sub, hit, hold, y):
    b = G.brand(ctx.style)
    is_rtl = G.rtl([label, sub])
    font = "BrandAR" if is_rtl else "BrandLT"
    y = y * ctx.H
    size = round(ctx.W * (0.068 if len(label) <= 14 else 0.052))
    out_at = hit + hold - 0.12
    body = f"""<div id="pos"><div id="tag" dir="{'rtl' if is_rtl else 'ltr'}"><div class="l">{G.esc(label)}</div>""" + (
        f"""<div class="s">{G.esc(sub)}</div>""" if sub else "") + "</div></div>"
    css = f"""
#pos{{position:absolute;left:0;right:0;top:{y - size * 0.75:.0f}px;display:flex;justify-content:center}}
#tag{{max-width:{ctx.W * 0.84:.0f}px;
  font-family:"{font}",sans-serif;text-align:center;padding:{size * 0.32:.0f}px {size * 0.6:.0f}px;
  border-radius:{size * 0.5:.0f}px;background:{b['hi']};color:{G.on_colour(b['hi'])};
  box-shadow:0 {size * 0.18:.0f}px {size * 0.6:.0f}px rgba(0,0,0,.35)}}
.l{{font-size:{size}px;font-weight:800;line-height:1.1}}
.s{{font-size:{size * 0.5:.0f}px;font-weight:600;opacity:.85;margin-top:{size * 0.12:.0f}px}}"""
    js = (f"springIn(tl,'#tag',{{scale:.4,rotation:-6,opacity:0}},{{scale:1,rotation:0,opacity:1,duration:.5}},"
          f"'bouncy',{hit + 0.04:.3f});"
          f"tl.to('#tag',{{scale:.6,opacity:0,duration:.12,ease:'power2.in'}},{max(hit + 0.3, out_at):.3f});")
    return ctx.page(body, css, js)
