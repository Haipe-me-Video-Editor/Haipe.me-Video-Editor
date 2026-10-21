"""Shared helpers for the data/list effects (chart_grow, checklist, list_tracker): brand palettes, where the head
is and where free space is, Arabic detection, and real frosted glass (the footage blurred behind a card).

Frosted glass: a HyperFrames page cannot see the video under it, so `backdrop-filter` would blur nothing. Instead
the card is drawn with a known fill alpha (GLASS_A) and `glass_stack` blurs the source frame wherever the layer's
alpha says there is card (alpha / GLASS_A, clipped), then lays the layer on top. Keep anything that should not
frost (shadows, glows) out of the layer, or very faint.
"""
import re

import numpy as np

GLASS_A = 0.5  # the fill alpha every glass card uses; glass_stack reads card coverage from it

SAFE_TOP, SAFE_BOTTOM, SAFE_RIGHT, SAFE_LEFT = 0.13, 0.20, 0.12, 0.05  # 9:16 platform UI margins

_AR = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def is_arabic(text: str) -> bool:
    return bool(_AR.search(text or ""))


def rtl(texts) -> bool:
    """True when most of the given texts are Arabic: the whole card then reads right to left."""
    texts = [t for t in texts if t]
    return bool(texts) and sum(map(is_arabic, texts)) * 2 > len(texts)


def brand(style: dict) -> dict:
    """Colours for data graphics in this style. up/down are the rise/fall colours, hi the highlight (pill, tick,
    current item), tint the glass tint, on_hi the text colour on a highlight fill. The style's `data_look` picks the
    colouring: market (rises in up, falls in down, the line in up), accent (everything in the accent), card (the
    accent on the style's card colour), or generic (default)."""
    accent = style.get("accent", "#ff7a1a")
    out = {"ink": style.get("ink", "#ffffff"), "hi": accent, "up": style.get("up", accent),
           "down": style.get("down", "#ff5a6e"), "tint": style.get("bg", "#101114"), "line": accent,
           "kind": "generic"}
    look = style.get("data_look", "generic")
    if look == "market":
        out.update(kind="market", hi=accent, line=style.get("up", "#2ecc71"))
    elif look == "card":
        out.update(kind="card", line=accent, up=accent, tint=style.get("card_bg", style.get("bg", "#101114")))
    elif look == "accent":
        out.update(kind="accent", up=accent, line=accent)
    out["on_hi"] = on_colour(out["hi"])
    return out


def rgb(hexcol: str):
    h = hexcol.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba(hexcol: str, a: float) -> str:
    r, g, b = rgb(hexcol)
    return f"rgba({r},{g},{b},{a:.3f})"


def on_colour(hexcol: str) -> str:
    """Dark or light text, whichever reads on this fill."""
    r, g, b = (c / 255 for c in rgb(hexcol))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#0b0d10" if lum > 0.45 else "#ffffff"


# ---- where the head is ---------------------------------------------------------------------------------------
def head(ctx) -> dict:
    """Median head box over the window, in pixels: x0..x1 (cheek to cheek plus ears), skull (top of the head,
    estimated above the landmark hairline), brow, eye_y, chin. Falls back to a typical close-up when no face."""
    pts = [p for p in ctx.landmarks(every=3) if p is not None]
    if not pts:
        W, H = ctx.W, ctx.H
        return head_from(W * 0.5, W * 0.5, H * 0.3, H * 0.17, H * 0.23, H * 0.57, W * 0.5)
    P = np.median(np.stack(pts), axis=0)
    fw = float(np.linalg.norm(P[454] - P[234]))
    return head_from(float(P[:, 0].min()), float(P[:, 0].max()), float(P[[33, 263], 1].mean()), float(P[10, 1]),
                     float(P[[105, 334], 1].mean()), float(P[152, 1]), fw)


def head_from(xmin, xmax, eye_y, top, brow, chin, fw) -> dict:
    pad = 0.12 * fw
    return {"x0": xmin - pad, "x1": xmax + pad, "skull": top - 0.32 * fw, "top": top, "brow": brow,
            "eye_y": eye_y, "chin": chin, "fw": fw, "cx": (xmin + xmax) / 2}


def free_regions(W, H, hd, margin=None) -> dict:
    """Free rectangles (x0, y0, x1, y1) inside the safe zone that keep clear of the head: above it, below the chin
    (the chest: free of the face, not of the body), left and right of it."""
    m = margin if margin is not None else 0.025 * H
    sx0, sx1, sy0, sy1 = SAFE_LEFT * W, (1 - SAFE_RIGHT) * W, SAFE_TOP * H, (1 - SAFE_BOTTOM) * H
    return {
        "above": (sx0, sy0, sx1, min(sy1, hd["skull"] - m)),
        "below": (sx0, max(sy0, hd["chin"] + m), sx1, sy1),
        "left": (sx0, sy0, min(sx1, hd["x0"] - m * 0.6), min(sy1, hd["chin"])),
        "right": (max(sx0, hd["x1"] + m * 0.6), sy0, sx1, min(sy1, hd["chin"])),
    }


def place(W, H, hd, w0, h0, prefer=("above", "left", "right", "below"), min_scale=0.55, max_scale=1.0) -> dict:
    """Best spot for a card of natural size w0 x h0: the free region that lets it be biggest (ties go to `prefer`
    order). Returns {region, scale, x, y, w, h} with the card centred in its region along x for above/below,
    hugging the head for left/right, and vertically near the head."""
    regs = free_regions(W, H, hd)
    best = None
    for rank, name in enumerate(prefer):
        x0, y0, x1, y1 = regs[name]
        rw, rh = x1 - x0, y1 - y0
        if rw <= 0 or rh <= 0:
            s = 0.0
        else:
            s = min(max_scale, rw / w0, rh / h0)
        key = (round(min(s, 1.0), 2), -rank)
        if best is None or key > best[0]:
            best = (key, name, s)
    _, name, s = best
    s = max(s, min_scale)
    x0, y0, x1, y1 = regs[name]
    w, h = w0 * s, h0 * s
    if name == "above":
        x, y = (x0 + x1) / 2 - w / 2, max(y0, y1 - h)           # sits just above the head
    elif name == "below":
        x, y = (x0 + x1) / 2 - w / 2, y0                         # just under the chin
    elif name == "left":
        x, y = x1 - w, max(y0, min(hd["eye_y"] - h / 2, y1 - h))
    else:
        x, y = x0, max(y0, min(hd["eye_y"] - h / 2, y1 - h))
    x = min(max(x, SAFE_LEFT * W), (1 - SAFE_RIGHT) * W - w)
    y = min(max(y, SAFE_TOP * H), (1 - SAFE_BOTTOM) * H - h)
    return {"region": name, "scale": s, "x": x, "y": y, "w": w, "h": h}


# ---- frosted glass ------------------------------------------------------------------------------------------
def frost(frame: np.ndarray, blur: float = 26.0, dim: float = 0.0) -> np.ndarray:
    """The frame blurred like frosted glass (computed small and scaled up: cheap and smooth)."""
    import cv2
    H, W = frame.shape[:2]
    k = 4
    small = cv2.resize(frame, (W // k, H // k), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), max(1.0, blur / k))
    out = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    if dim:
        out *= 1 - dim
    return out


def glass_composite(src: np.ndarray, layer: np.ndarray, blur: float = 26.0, glass_a: float = GLASS_A,
                    under: np.ndarray | None = None) -> np.ndarray:
    """One frame: src with the glass under the layer's card frosted, the layer over it, then `under`'s
    foreground (an RGBA frame, e.g. the speaker's hands) back on top when given."""
    a = layer[..., 3].astype(np.float32) / 255
    ys, xs = np.nonzero(a > 0.004)
    out = src.astype(np.float32)
    if len(ys):
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        pad = int(blur * 2)
        Y0, Y1, X0, X1 = max(0, y0 - pad), min(src.shape[0], y1 + pad), max(0, x0 - pad), min(src.shape[1], x1 + pad)
        region = src[Y0:Y1, X0:X1]
        fr = frost(region, blur)[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0]
        aa = a[y0:y1, x0:x1, None]
        m = np.clip(aa / glass_a, 0, 1)
        o = out[y0:y1, x0:x1]
        o = o * (1 - m) + fr * m
        o = o * (1 - aa) + layer[y0:y1, x0:x1, :3].astype(np.float32) * aa
        out[y0:y1, x0:x1] = o
    if under is not None:
        ua = under[..., 3:4].astype(np.float32) / 255
        out = out * (1 - ua) + under[..., :3].astype(np.float32) * ua
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def glass_stack(ctx, layer, blur: float = 26.0, front=None):
    """Write ctx.out: the window with the layer's glass cards frosted and the layer on top; `front` is an optional
    RGBA clip (the speaker's hands) drawn over everything."""
    srcs, lays = ctx.frames(), ctx.frames(layer, rgba=True)
    fronts = ctx.frames(front, rgba=True) if front else None
    with ctx.writer() as w:
        for f, lay in zip(srcs, lays):
            w(glass_composite(f, lay, blur, under=next(fronts) if fronts else None))
    return ctx.out


def esc(text) -> str:
    import html
    return html.escape(str(text), quote=True)
