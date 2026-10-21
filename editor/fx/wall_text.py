"""Couch wall: a big word painted on the wall behind the speaker; their head, shoulders and hands pass in front.

Placement is solved from the person matte over the window (see _behind.solve): the word goes where the wall is
actually visible and stays readable: above the head on a wide shot, big beside the head (turned to read up the
side) on a close-up, or across the shoulders when that is where the wall shows. It is sized to the largest that
keeps every letter at least ~80% visible, lit by the wall it sits on, and the person is composited back on top.
"""
import math

import cv2
import numpy as np

from . import _behind as B

NAME = "wall_text"
DOC = ("Big word(s) painted on the wall behind the speaker (head and hands in front), placed and sized "
       "automatically where the wall is visible. For the one word that sums up a section.")
BEST_FOR = ["product", "finance", "any"]
DUR = (1.5, 8)
PARAMS = {
    "text": "",          # 1-3 words; \\N forces a line break (else one line or a balanced two-line split is chosen)
    "hi": [],            # words drawn in the accent colour
    "font": "Anton",     # any fx font family (Anton, BebasNeue, Montserrat, Sora, Orbitron, Lalezar, BrandLT, BrandAR)
    "place": "auto",     # auto | above (horizontal only) | side (turned, up the side) | behind (fixed, may be covered)
    "y": None,           # force the top of the block, 0-1 of the height (implies place=behind)
    "size": None,        # largest font size as a fraction of the width (default 0.30); with y: the exact size
    "color": None,       # default the style ink
    "opacity": 0.92,
}

ENTER, STAGGER, EXIT = 0.55, 0.09, 0.3


def _font(ctx, text):
    fam = ctx.param("font", PARAMS["font"])
    if B.is_arabic(text) and fam in ("Anton", "BebasNeue", "Montserrat", "Sora", "Orbitron", "BrandLT"):
        fam = "Lalezar"
    return B.font_file(ctx, fam)


def layout(ctx, text: str, occ: np.ndarray, head: dict) -> dict:
    """Where and how big: {block, em, rotate, x, y}."""
    font = _font(ctx, text)
    W, H = ctx.W, ctx.H
    size = ctx.param("size")
    place = ctx.param("place", "auto")
    if ctx.param("y") is not None:
        place = "behind"
    blocks = [B.Block(ls, font) for ls in B.split_lines(text)]
    if place != "behind":
        blocked = B.blocked_grid(occ, W, H, margin_cells=0)
        hi = (size or 0.30) * W
        anchor = (head["cx"], head["top"] + (head["eye_y"] - head["top"]) * 0.5)
        best = B.solve(blocked, blocks, anchor, (0.05 * W, hi), allow_rotate=place in ("auto", "side") and not B.is_arabic(text),
                       rotate_penalty=0.72 if place == "auto" else 10.0, max_letter=0.3, max_total=0.12)
        if best:
            return best
    # behind: a fixed size just above the face, centred in the safe zone; the head may cover part of it
    blk = blocks[0] if ctx.param("y") is not None else blocks[-1]
    em = (size or 0.26) * W
    s = em / blk.em
    w, h = blk.size[0] * s, blk.size[1] * s
    max_w = (B.SAFE[2] - B.SAFE[0]) * W
    if w > max_w:
        s *= max_w / w
        w, h, em = w * max_w / w, h * max_w / w, em * max_w / w
    y = ctx.param("y")
    top = y * H if y is not None else max(B.SAFE[1] * H, head["top"] - h * 0.55)
    x = (B.SAFE[0] + B.SAFE[2]) / 2 * W - w / 2
    return {"block": blk, "em": em, "scale": s, "rotate": 0, "x": int(x), "y": int(top)}


def _wall_light(frame: np.ndarray, box) -> np.ndarray:
    """Low-frequency light on the wall around the text, normalised to 1 at its median: paint picks it up."""
    x0, y0, x1, y1 = box
    lum = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(np.float32)
    lum = cv2.GaussianBlur(lum, (0, 0), 45)[y0:y1, x0:x1]
    med = max(float(np.median(lum)), 8.0)
    return np.clip(lum / med, 0.78, 1.12)


def render(ctx):
    text = (ctx.param("text") or "").strip()
    if not text:
        raise ValueError("wall_text needs text")
    B.prime(ctx)
    occ = B.occupancy(ctx)
    face = ctx.face()
    B.publish(ctx)
    head = B.head_box(occ, face, ctx.W, ctx.H)
    occ = B.occupancy_for_text(ctx, head)
    L = layout(ctx, text, occ, head)
    blk, s, rot = L["block"], L["scale"], L["rotate"]
    sprites = blk.word_sprites(s, rot)
    em = L["em"]
    hi = {w.lower().strip(".,!?") for w in ctx.param("hi", [])}
    ink = B.hex_rgb(ctx.param("color") or ctx.style.get("ink", "#ffffff"))
    acc = B.hex_rgb(ctx.style.get("accent", "#ff7a1a"))
    op = float(ctx.param("opacity", PARAMS["opacity"]))
    # "down" of the text in screen space (the direction a word rises from)
    down = {0: (0.0, 1.0), 1: (1.0, 0.0), -1: (-1.0, 0.0)}[rot]
    W, H = ctx.W, ctx.H
    bx, by = L["x"], L["y"]
    pad = int(em * 0.6)
    bw = math.ceil(blk.size[0] * s) if not rot else math.ceil(blk.size[1] * s)
    bh = math.ceil(blk.size[1] * s) if not rot else math.ceil(blk.size[0] * s)
    box = (max(bx - pad, 0), max(by - pad, 0), min(bx + bw + pad, W), min(by + bh + pad, H))
    x0, y0, x1, y1 = box
    sig = max(em * 0.035, 2)
    sh_off = (em * 0.02, em * 0.035)
    enter = B.spring("snappy")
    light = None
    with ctx.writer() as write:
        for i, (frame, m) in enumerate(zip(ctx.frames(), B.person_alpha(ctx))):
            t = i / ctx.fps
            if light is None:
                light = _wall_light(frame, box)[..., None]
            A = np.zeros((y1 - y0, x1 - x0), np.float32)
            C = np.zeros((y1 - y0, x1 - x0, 3), np.float32)
            tout = B.ease_in(B.progress(t, ctx.dur - EXIT, EXIT))
            for k, sp in enumerate(sprites):
                tk = t - 0.05 - STAGGER * k
                if tk <= 0:
                    continue
                p = enter(min(tk / ENTER, 1.0))
                fade = B.ease_out(tk / (ENTER * 0.6)) * (1 - tout)
                if fade <= 0.002:
                    continue
                off = (1 - p) * em * 0.5 - tout * em * 0.15
                a, ox, oy = B.warp_sprite(sp["alpha"], down[0] * off, down[1] * off)
                col = acc if sp["word"].lower().strip(".,!?") in hi else ink
                X, Y = bx + sp["x"] + ox - x0, by + sp["y"] + oy - y0
                a = a * fade
                layer = np.zeros_like(A)
                B.paste(layer, a, X, Y)
                C += col * layer[..., None]
                A += layer
            out = frame.astype(np.float32) / 255
            if A.max() > 0.002:
                reg = out[y0:y1, x0:x1]
                shadow = cv2.GaussianBlur(A, (0, 0), sig)
                M = np.float32([[1, 0, sh_off[0]], [0, 1, sh_off[1]]])
                shadow = cv2.warpAffine(shadow, M, (A.shape[1], A.shape[0]))
                reg *= 1 - 0.38 * shadow[..., None] * op
                C /= np.maximum(A, 1e-4)[..., None]
                A = np.minimum(A, 1)
                paint = np.clip(C * (1 + 0.45 * (light - 1)), 0, 1)
                a3 = (A * op)[..., None]
                reg[:] = reg * (1 - a3) + paint * a3
                mm = m[y0:y1, x0:x1, None]
                orig = frame[y0:y1, x0:x1].astype(np.float32) / 255
                reg[:] = reg * (1 - mm) + orig * mm
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out
