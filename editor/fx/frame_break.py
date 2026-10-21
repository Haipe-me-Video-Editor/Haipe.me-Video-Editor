"""Frame break: the footage shrinks into a framed card (a phone screen, rounded, with a hairline border and an
optional generic reel UI) on a clean background, and the speaker breaks out over the top edge of the card: the
crown of the head and any hand raised above the shoulders stay full size outside the frame, with a soft shadow
on the card behind them.

Geometry from the matte and the face: the card's top edge crosses the forehead, the card is a 1:2 phone centred on
the face, and the composition (crown to card bottom) fills the safe zone. One affine map (uniform scale + offset)
takes the source to the screen, so the card, the footage inside it and the cut-out stay locked together while it
springs in from full frame and unwinds at the end.
"""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

from . import _behind as B

NAME = "frame_break"
DOC = ("The footage becomes a framed phone card on a clean background and the speaker's head (and raised hands) "
       "break out over the frame edge. For a 'look at this' / reveal / product moment.")
BEST_FOR = ["product", "finance", "corporate", "any"]
DUR = (1.5, 8)
PARAMS = {
    "bg": "clean",       # clean (style colours, soft light) | blur (the footage, blurred and dimmed)
    "ui": True,          # generic reel UI on the card (side icons, progress bar)
    "handle": "",        # optional @handle on the card's UI (e.g. "yourbrand"); empty: none
    "width": 0.6,        # card width as a fraction of the frame width
    "pop": 0.75,         # where the card's top edge crosses: 0 = at the crown, 1 = at the eyes
    "radius": 0.075,     # corner radius, fraction of the card width
}

ENTER, EXIT = 0.85, 0.45


def geometry(W: int, H: int, head: dict, shoulder_y: float, width: float = 0.6, pop: float = 0.75) -> dict:
    """Card rect in source px (x0, y0, w, h), the uniform scale s and offset (ox, oy) to the screen, and the
    source row below which only hands break out. The head is shown ~0.4 of the frame wide; the card is `width`
    of the frame wide and as tall as the safe zone allows under the popped-out crown."""
    crown, eye = head["top"], head["eye_y"]
    head_w = head["fw"] * 1.15  # landmarks, not the matte: a chair back widens the matte at eye level
    cut = crown + pop * max(eye - crown, H * 0.05)
    top_safe, bot = B.SAFE[1] * H + H * 0.008, B.SAFE[3] * H
    avail = bot - top_safe
    s0 = float(np.clip(0.40 * W / head_w, 0.55, 1.0))
    ch = min((avail - (cut - crown) * s0) / s0, H - cut)
    s = min(avail / ((cut - crown) + ch), 1.0)  # fill the safe height (larger when the source runs out below)
    cw = min(max(width * W / s, head_w * 1.25), W, 0.8 * W / s)
    cx = float(np.clip(head["cx"], cw / 2, W - cw / 2))
    x0 = cx - cw / 2
    screen_cx = (B.SAFE[0] + B.SAFE[2]) / 2 * W
    ox = screen_cx - s * cx
    used = ((cut - crown) + ch) * s
    oy = top_safe + (avail - used) / 2 + (cut - crown) * s - s * cut
    return {"x0": x0, "y0": cut, "w": cw, "h": ch, "s": s, "ox": ox, "oy": oy,
            "break_y": min(shoulder_y, cut + ch * 0.6)}


def shoulder_row(occ: np.ndarray, head: dict) -> float:
    """First row below the chin where the person spans most of the frame: where the shoulders widen."""
    gh, _gw = occ.shape
    start = int(min(max(head["eye_y"] / B.CELL, 0), gh - 1))
    for r in range(start, gh):
        if (occ[r] > 0.5).mean() > 0.78:
            return r * B.CELL
    return head["chin"] + head["fw"] * 0.3


def rounded_mask(W: int, H: int, x0: float, y0: float, x1: float, y1: float, r: float, ss: int = 2) -> np.ndarray:
    """Anti-aliased rounded-rect coverage, float32 (H, W)."""
    out = np.zeros((H, W), np.float32)
    X0, Y0 = max(math.floor(x0) - 2, 0), max(math.floor(y0) - 2, 0)
    X1, Y1 = min(math.ceil(x1) + 2, W), min(math.ceil(y1) + 2, H)
    if X1 <= X0 or Y1 <= Y0:
        return out
    yy, xx = np.mgrid[Y0:Y1, X0:X1].astype(np.float32) + 0.5
    r = max(min(r, (x1 - x0) / 2, (y1 - y0) / 2), 0.0)
    dx = np.maximum(np.maximum(x0 + r - xx, xx - (x1 - r)), 0)
    dy = np.maximum(np.maximum(y0 + r - yy, yy - (y1 - r)), 0)
    inside_rect = (xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1)
    d = np.sqrt(dx * dx + dy * dy) - r  # <0 inside the rounded corners
    cov = np.clip(0.5 - d, 0, 1)
    edge = np.clip(np.minimum.reduce([xx - x0, x1 - xx, yy - y0, y1 - yy]) + 0.5, 0, 1)
    out[Y0:Y1, X0:X1] = np.where(inside_rect | (d < 0.5), np.minimum(cov, edge), 0)
    return out


def ui_overlay(w: int, h: int, handle: str, ink=(255, 255, 255)) -> np.ndarray:
    """Generic reel chrome for a card w x h: heart / comment / send icons up the right, optional @handle and a
    progress bar at the bottom. RGBA float32 (premultiplied-free), drawn 3x and downsampled for clean edges."""
    S = 3
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    u = w * S / 100.0
    lw = max(int(u * 0.9), 2)
    col = ink + (235,)
    x = w * S - u * 10
    y = h * S - u * 52
    hr = u * 2.6
    # heart (filled)
    d.ellipse([x - hr * 2, y - hr, x, y + hr], fill=col)
    d.ellipse([x, y - hr, x + hr * 2, y + hr], fill=col)
    d.polygon([(x - hr * 1.93, y + hr * 0.35), (x + hr * 1.93, y + hr * 0.35), (x, y + hr * 2.55)], fill=col)
    # comment (filled bubble with a tail)
    y += u * 12
    d.ellipse([x - u * 4.4, y - u * 3.6, x + u * 4.4, y + u * 3.6], fill=col)
    d.polygon([(x - u * 3.2, y + u * 1.6), (x - u * 4.8, y + u * 5.0), (x - u * 0.6, y + u * 3.2)], fill=col)
    # share (paper plane)
    y += u * 12
    d.polygon([(x - u * 4.6, y - u * 0.4), (x + u * 4.6, y - u * 4.4), (x + u * 0.6, y + u * 4.6),
               (x - u * 0.9, y + u * 0.9)], fill=col)
    d.line([(x - u * 0.9, y + u * 0.9), (x + u * 4.6, y - u * 4.4)], fill=(0, 0, 0, 90), width=max(lw // 2, 1))
    # handle + progress
    by = h * S - u * 7
    if handle:
        from PIL import ImageFont

        from .. import fonts
        f = ImageFont.truetype(str(fonts.ensure_font("Montserrat")), int(u * 4.2))
        ax, ay = u * 7, by - u * 11
        d.ellipse([ax, ay - u * 3.4, ax + u * 6.8, ay + u * 3.4], fill=(255, 255, 255, 60), outline=col, width=lw)
        tx = ax + u * 9.5
        d.text((tx, ay), "@" + handle.lstrip("@"), font=f, fill=col, anchor="lm")
        fw_ = d.textlength("@" + handle.lstrip("@"), font=f)
        px = tx + fw_ + u * 3
        d.rounded_rectangle([px, ay - u * 3.0, px + u * 15, ay + u * 3.0], radius=u * 1.4, outline=col, width=lw)
        f2 = ImageFont.truetype(str(fonts.ensure_font("Montserrat")), int(u * 3.2))
        d.text((px + u * 7.5, ay), "Follow", font=f2, fill=col, anchor="mm")
    d.rounded_rectangle([u * 7, by, w * S - u * 7, by + u * 0.9], radius=u * 0.45, fill=ink + (70,))
    d.rounded_rectangle([u * 7, by, u * 7 + (w * S - u * 14) * 0.38, by + u * 0.9], radius=u * 0.45, fill=col)
    from PIL import ImageFilter
    a = im.getchannel("A")
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    shadow.putalpha(a.filter(ImageFilter.GaussianBlur(u * 0.8)).point(lambda v: int(v * 0.45)))
    im = Image.alpha_composite(shadow, im)
    im = im.resize((w, h), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255


def backdrop(ctx, kind: str, frame0: np.ndarray) -> np.ndarray:
    """The clean background: the style's bg lit by a soft pool of its bg2 and a faint accent glow behind the
    card; kind="blur" lays the footage underneath, blurred and dimmed, tinted toward the same colours."""
    W, H = ctx.W, ctx.H
    base = B.hex_rgb(ctx.style.get("bg", "#0b0c0e"))
    lift = B.hex_rgb(ctx.style["bg2"]) if ctx.style.get("bg2") else np.clip(base + 0.10, 0, 1)
    acc = B.hex_rgb(ctx.style.get("accent", "#ff7a1a"))
    bg = np.empty((H, W, 3), np.float32)
    bg[:] = base
    if kind == "blur":
        small = cv2.resize(frame0, (W // 8, H // 8), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
        small = cv2.GaussianBlur(small, (0, 0), 6)
        bg = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR) * 0.40 + base * 0.45
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W * 0.46) / (W * 0.9)) ** 2 + ((yy - H * 0.42) / (H * 0.55)) ** 2)
    bg += (lift - base) * (np.clip(1 - r, 0, 1) ** 1.5)[..., None] * (0.6 if kind == "blur" else 1.0)
    r2 = np.sqrt(((xx - W * 0.46) / (W * 0.5)) ** 2 + ((yy - H * 0.30) / (H * 0.22)) ** 2)
    bg += acc * (np.clip(1 - r2, 0, 1) ** 2 * 0.11)[..., None]
    v = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.75)) ** 2)
    bg *= (1 - 0.35 * np.clip(v - 0.35, 0, 1))[..., None]
    return np.clip(bg, 0, 1).astype(np.float32)


def render(ctx):
    W, H = ctx.W, ctx.H
    B.prime(ctx)
    occ = B.occupancy(ctx)
    face = ctx.face()
    B.publish(ctx)
    head = B.head_box(occ, face, W, H)
    G = geometry(W, H, head, shoulder_row(occ, head), float(ctx.param("width", PARAMS["width"])),
                 float(ctx.param("pop", PARAMS["pop"])))
    s1, ox1, oy1 = G["s"], G["ox"], G["oy"]
    cw_scr, ch_scr = G["w"] * s1, G["h"] * s1
    rad = float(ctx.param("radius", PARAMS["radius"])) * cw_scr
    ui = ui_overlay(round(cw_scr), round(ch_scr), ctx.param("handle", "")) if ctx.param("ui", True) else None
    # source-space breakout: everything above the card's top edge (the crown, raised hands) and, down to the
    # shoulders, bare skin (hands, arms); never clothes or the chair, never the source frame's own side edges
    yy = np.arange(H, dtype=np.float32)[:, None]
    xx = np.arange(W, dtype=np.float32)[None, :]
    sides = np.clip(np.minimum(xx, W - 1 - xx) / (W * 0.03) - 0.4, 0, 1)
    above_cut = (np.clip((G["y0"] + H * 0.012 - yy) / (H * 0.01) + 0.5, 0, 1) * sides).astype(np.float32)
    above_break = (np.clip((G["break_y"] - yy) / (H * 0.02) + 0.5, 0, 1) * sides).astype(np.float32)
    from ..cutout import _Skin
    skin = _Skin()
    sk_prev = None
    first = None
    bg = None
    enter = B.spring("gentle")
    d = ctx.dur
    with ctx.writer() as write:
        for i, (frame, m) in enumerate(zip(ctx.frames(), B.person_alpha(ctx))):
            t = i / ctx.fps
            if bg is None:
                first = frame
                bg = backdrop(ctx, ctx.param("bg", "clean"), first)
            p = enter(B.progress(t, 0.0, ENTER)) * (1 - B.ease_in(B.progress(t, d - EXIT, EXIT)))
            F = frame.astype(np.float32) / 255
            if p < 0.002:
                write(frame)
                continue
            s = 1 + (s1 - 1) * p
            ox, oy = ox1 * p, oy1 * p
            # source crop rect, interpolated from the full frame to the card
            rx0, ry0 = G["x0"] * p, G["y0"] * p
            rx1 = W + (G["x0"] + G["w"] - W) * p
            ry1 = H + (G["y0"] + G["h"] - H) * p
            A = np.float32([[s, 0, ox], [0, s, oy]])
            TF = cv2.warpAffine(F, A, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            TM = cv2.warpAffine(m, A, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            sk = skin(frame)
            sk_prev = sk if sk_prev is None else sk_prev * 0.45 + sk * 0.55  # steady edges on moving hands
            bm_src = np.maximum(above_cut, above_break * sk_prev)
            BM = cv2.warpAffine(bm_src, A, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            cx0, cy0, cx1, cy1 = s * rx0 + ox, s * ry0 + oy, s * rx1 + ox, s * ry1 + oy
            card = rounded_mask(W, H, cx0, cy0, cx1, cy1, rad * p)
            out = bg.copy()
            # card shadow on the backdrop
            small = cv2.resize(card, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
            sh = cv2.GaussianBlur(small, (0, 0), 10)
            sh = cv2.warpAffine(sh, np.float32([[1, 0, 0], [0, 1, 8]]), (W // 4, H // 4))
            out *= (1 - 0.55 * p * cv2.resize(sh, (W, H))[..., None])
            # the card: footage inside, a hairline border
            out = out * (1 - card[..., None]) + TF * card[..., None]
            inner = rounded_mask(W, H, cx0 + 2, cy0 + 2, cx1 - 2, cy1 - 2, max(rad * p - 2, 0))
            ring = np.clip(card - inner, 0, 1) * p
            out = out * (1 - 0.55 * ring[..., None]) + 0.55 * ring[..., None] * np.float32([1, 1, 1])
            if ui is not None:
                uh, uw = ui.shape[:2]
                X, Y = round(cx0), round(cy0)
                ua = ui[..., 3:4] * B.ease_out(B.progress(p, 0.75, 0.25))
                if ua.max() > 0 and abs((cx1 - cx0) - uw) < 3:
                    reg = out[max(Y, 0):Y + uh, max(X, 0):X + uw]
                    sub = ui[max(-Y, 0):max(-Y, 0) + reg.shape[0], max(-X, 0):max(-X, 0) + reg.shape[1]]
                    a = ua[max(-Y, 0):max(-Y, 0) + reg.shape[0], max(-X, 0):max(-X, 0) + reg.shape[1]]
                    reg[:] = reg * (1 - a) + sub[..., :3] * a
            # the speaker breaking out: shadow on the card, then the cut-out on top
            P = TM * BM
            if P.max() > 0.01:
                small = cv2.resize(P * (1 - card), (W // 4, H // 4), interpolation=cv2.INTER_AREA)
                psh = cv2.GaussianBlur(small, (0, 0), 5)
                psh = cv2.warpAffine(psh, np.float32([[1, 0, 3], [0, 1, 6]]), (W // 4, H // 4))
                # only on what is not the speaker (a shadow across their own forehead reads as a seam)
                out *= (1 - 0.35 * p * cv2.resize(psh, (W, H)) * (1 - TM))[..., None]
                out = out * (1 - P[..., None]) + TF * P[..., None]
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out
