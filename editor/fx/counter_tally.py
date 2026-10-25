"""Counter tally: the picture cuts to a clean page where a big number counts up (0, 1, 2 ... 18) over "/ 18 effects",
a caption and a progress bar, above a white card listing every item in one or two numbered columns; each item ticks
(mint box, green check, the name turns dark) the moment the count reaches it. The voice carries on underneath, and
the page fades back to the shot at the end.

The page is drawn twice at 2x (every item pending, every item done) and downsampled once; a frame only takes each
item's row from one or the other, draws the number and fills the bar, so a long count stays cheap.
"""
import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .. import fonts
from . import _behind as B
from . import _camera as cam

NAME = "counter_tally"
DOC = ("Full-frame clean page: a big number counts up to the total ('/ 18 effects', a caption, a progress bar) over "
       "a card listing the items in numbered columns, each ticking as the count reaches it. For 'here are all N', "
       "recaps and roundups. Numbers and items only from the script.")
BEST_FOR = ["product", "corporate", "finance", "any"]
DUR = (2.0, 10)
PARAMS = {
    "items": [],         # 0-20 short items (the list on the card); empty: the counter alone
    "total": None,       # the number counted to (default: the number of items)
    "label": "",         # word after the total ("effects" -> "/ 18 effects")
    "caption": "",       # one short line under the number
    "count": None,       # [start, end] seconds into the window of the count (default: after the fade, to near the end)
    "bg": "light",       # light | dark
    "accent": "",        # bar colour (default: the style's accent)
    "exit": True,        # fade back to the shot at the end
}
FADE = 0.3
SS = 2  # supersampling of the static page

LIGHT = {"bg": (241, 243, 246), "bg2": (250, 251, 252), "num": (17, 24, 39), "sub": (88, 98, 114), "card": (255, 255, 255),
         "rim": (226, 230, 236), "track": (221, 227, 236), "done": (17, 24, 39), "todo": (160, 168, 182),
         "box": (214, 219, 227), "mint": (200, 242, 220), "check": (19, 138, 79), "idx": (150, 158, 170)}
DARK = {"bg": (14, 16, 20), "bg2": (30, 34, 42), "num": (245, 246, 248), "sub": (160, 168, 182), "card": (26, 29, 36),
        "rim": (44, 48, 58), "track": (52, 57, 68), "done": (245, 246, 248), "todo": (100, 108, 122),
        "box": (70, 76, 90), "mint": (24, 70, 48), "check": (90, 220, 150), "idx": (110, 118, 132)}


@lru_cache(maxsize=32)
def _font(family: str, size: int):
    return ImageFont.truetype(str(fonts.ensure_font(family)), size)


def count_at(t: float, a: float, b: float, start: int, total: int) -> int:
    """The number shown at t: start before a, total from b on, a steady count between (whole numbers), so every
    step gets the same beat."""
    if t <= a:
        return start
    if t >= b:
        return total
    u = (t - a) / max(b - a, 1e-6)
    return start + math.floor((total - start) * u + 1e-9)


def geometry(W: int, H: int, n_items: int, has_caption: bool) -> dict:
    """Pixel layout of the page: number baseline, caption, bar, card rect, columns and row height."""
    u = W / 1080
    x0, x1 = B.SAFE[0] * W + 24 * u, B.SAFE[2] * W - 8 * u
    top = B.SAFE[1] * H + 40 * u
    base = top + 220 * u
    cap = base + 78 * u
    bar = (cap + 52 * u) if has_caption else (base + 60 * u)
    g = {"u": u, "x0": x0, "x1": x1, "num_base": base, "cap_base": cap, "bar_y": bar, "bar_h": 12 * u}
    if n_items:
        cols = 2 if n_items > 6 else 1
        rows = math.ceil(n_items / cols)
        ctop = bar + 70 * u
        pad = 26 * u
        avail = B.SAFE[3] * H - 20 * u - ctop - 2 * pad
        rh = min(74 * u, avail / rows)
        if rh < 40 * u:
            raise ValueError("counter_tally: too many items for the card")
        g.update(cols=cols, rows=rows, card=(x0 - 10 * u, ctop, x1, ctop + 2 * pad + rows * rh), pad=pad, rh=rh)
    return g


def item_rect(g: dict, k: int) -> tuple:
    """Row k's rect (x0, y0, x1, y1) on the card: column-major, like a printed list."""
    cx0, cy0, cx1, _ = g["card"]
    col, row = divmod(k, g["rows"])
    cw = (cx1 - cx0 - 2 * g["pad"]) / g["cols"]
    x = cx0 + g["pad"] + col * cw
    y = cy0 + g["pad"] + row * g["rh"]
    return x, y, x + cw, y + g["rh"]


def draw_page(W: int, H: int, g: dict, items: list, caption: str, done: bool, pal: dict) -> np.ndarray:
    """The static page (background, label, caption, bar track, card, every row pending or every row done), drawn at
    SS x and returned at 1x as float32 RGB."""
    S = SS
    im = Image.new("RGB", (W * S, H * S), pal["bg"])
    d = ImageDraw.Draw(im)
    # a soft pool of light behind the number
    glow = Image.new("L", (W // 4, H // 4), 0)
    ImageDraw.Draw(glow).ellipse([-W // 8, -H // 16, W // 3, H // 6], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(W // 14)).resize((W * S, H * S), Image.BILINEAR)
    im = Image.composite(Image.new("RGB", im.size, pal["bg2"]), im, glow)
    d = ImageDraw.Draw(im)
    u = g["u"] * S
    if caption:
        d.text((g["x0"] * S, g["cap_base"] * S), caption, font=_font("Montserrat", int(40 * u)), fill=pal["sub"],
               anchor="ls")
    by, bh = g["bar_y"] * S, g["bar_h"] * S
    d.rounded_rectangle([g["x0"] * S, by, g["x1"] * S, by + bh], radius=bh / 2, fill=pal["track"])
    if items:
        cx0, cy0, cx1, cy1 = (v * S for v in g["card"])
        shadow = Image.new("L", (W // 4, H // 4), 0)
        ImageDraw.Draw(shadow).rounded_rectangle([cx0 / S / 4, cy0 / S / 4 + 4, cx1 / S / 4, cy1 / S / 4 + 6],
                                                 radius=8, fill=110)
        shadow = shadow.filter(ImageFilter.GaussianBlur(10)).resize((W * S, H * S), Image.BILINEAR)
        im = Image.composite(Image.new("RGB", im.size, tuple(int(c * 0.86) for c in pal["bg"])), im, shadow)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=26 * u, fill=pal["card"], outline=pal["rim"], width=int(3 * u))
        if g["cols"] == 2:
            mid = (cx0 + cx1) / 2
            d.line([(mid, cy0 + 24 * u), (mid, cy1 - 24 * u)], fill=pal["rim"], width=int(2 * u))
        f_idx = _font("IBM Plex Mono", int(22 * u))
        for k, name in enumerate(items):
            x0, y0, x1, y1 = (v * S for v in item_rect(g, k))
            cy = (y0 + y1) / 2
            bs = 36 * u
            bx = x0 + 6 * u
            if done:
                d.rounded_rectangle([bx, cy - bs / 2, bx + bs, cy + bs / 2], radius=9 * u, fill=pal["mint"])
                lw = max(2, int(4.5 * u))
                d.line([(bx + bs * 0.24, cy + bs * 0.02), (bx + bs * 0.43, cy + bs * 0.2), (bx + bs * 0.76, cy - bs * 0.2)],
                       fill=pal["check"], width=lw, joint="curve")
            else:
                d.rounded_rectangle([bx, cy - bs / 2, bx + bs, cy + bs / 2], radius=9 * u, outline=pal["box"],
                                    width=max(2, int(3 * u)))
            tx = bx + bs + 18 * u
            d.text((tx, cy), f"{k + 1:02d}", font=f_idx, fill=pal["idx"], anchor="lm")
            nx = tx + 44 * u
            size = int(32 * u)
            f_name = _font("Montserrat", size)
            while d.textlength(name, font=f_name) > x1 - nx - 10 * u and size > 18 * u:
                size -= 2
                f_name = _font("Montserrat", size)
            d.text((nx, cy), name, font=f_name, fill=pal["done"] if done else pal["todo"], anchor="lm")
    return np.asarray(im.resize((W, H), Image.LANCZOS), np.float32) / 255


@lru_cache(maxsize=256)
def number_sprite(text: str, size: int, rgb: tuple) -> np.ndarray:
    """The big number (and nothing else) as an RGBA float32 sprite, left/baseline origin at (0, ascent)."""
    f = _font("Sora", size)
    l, t, r, b = f.getbbox(text, anchor="ls")
    im = Image.new("RGBA", (r - l + 8, b - t + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - l, 4 - t), text, font=f, fill=rgb + (255,), anchor="ls")
    return np.asarray(im, np.float32) / 255, 4 - l, 4 - t


def render(ctx):
    W, H = ctx.W, ctx.H
    items = [str(t).strip() for t in (ctx.param("items", PARAMS["items"]) or [])]
    if len(items) > 20 or not all(items):
        raise ValueError("counter_tally takes 0-20 non-empty items")
    total = ctx.param("total", PARAMS["total"])
    total = int(total) if total is not None else len(items)
    if total < 1:
        raise ValueError("counter_tally needs a total (or items to count)")
    label, caption = str(ctx.param("label", "")), str(ctx.param("caption", ""))
    pal = DARK if ctx.param("bg", PARAMS["bg"]) == "dark" else LIGHT
    accent = tuple(int(v) for v in cam.hex_rgb(ctx.param("accent") or ctx.style.get("accent", "#2f6bed")))
    exit_ = bool(ctx.param("exit", PARAMS["exit"]))
    span = ctx.param("count", PARAMS["count"]) or [FADE + 0.15, max(FADE + 0.4, ctx.dur - (FADE + 0.5 if exit_ else 0.4))]
    a, b = float(span[0]), float(span[1])
    g = geometry(W, H, len(items), bool(caption))
    todo = draw_page(W, H, g, items, caption, False, pal)
    done = draw_page(W, H, g, items, caption, True, pal) if items else todo
    rects = [tuple(round(v) for v in item_rect(g, k)) for k in range(len(items))]
    u = g["u"]
    bar_x0, bar_x1, bar_y, bar_h = g["x0"], g["x1"], g["bar_y"], g["bar_h"]
    ticked_at = {}
    with ctx.writer() as write:
        for i, frame in enumerate(ctx.frames()):
            t = i / ctx.fps
            env = B.ease_out(B.progress(t, 0, FADE))
            if exit_:
                env *= 1 - B.ease_in(B.progress(t, ctx.dur - FADE, FADE))
            if env <= 0.001:
                write(frame)
                continue
            n = count_at(t, a, b, 0, total)
            page = todo.copy()
            # rows tick as the count passes them (an item k is done once the count reaches k + 1 of the list's share)
            for k, (x0, y0, x1, y1) in enumerate(rects):
                need = math.ceil((k + 1) * total / len(items))
                if n >= need:
                    ticked_at.setdefault(k, t)
                    w = min(1.0, (t - ticked_at[k]) / 0.14)
                    page[y0:y1, x0:x1] = todo[y0:y1, x0:x1] * (1 - w) + done[y0:y1, x0:x1] * w
            # the number, then "/ total label" on its baseline
            spr, ox, oy = number_sprite(str(n), int(230 * u), pal["num"])
            X, Y = int(g["x0"] - ox), int(g["num_base"] - oy)
            h_, w_ = spr.shape[:2]
            reg = page[max(Y, 0):Y + h_, X:X + w_]
            s = spr[max(-Y, 0):max(-Y, 0) + reg.shape[0], :reg.shape[1]]
            reg[:] = reg * (1 - s[..., 3:4]) + s[..., :3] * s[..., 3:4]
            tail = f"/ {total}" + (f" {label}" if label else "")
            tspr, tox, toy = number_sprite(tail, int(58 * u), pal["sub"])
            X2, Y2 = int(X + w_ + 14 * u - tox), int(g["num_base"] - toy)
            th, tw = tspr.shape[:2]
            reg = page[Y2:Y2 + th, X2:X2 + tw]
            s = tspr[:reg.shape[0], :reg.shape[1]]
            reg[:] = reg * (1 - s[..., 3:4]) + s[..., :3] * s[..., 3:4]
            # the bar fills with the count
            fill = (bar_x1 - bar_x0) * n / total
            if fill > 1:
                y0, y1 = round(bar_y), round(bar_y + bar_h)
                x1 = round(bar_x0 + max(fill, bar_h))
                seg = page[y0:y1, int(bar_x0):x1]
                yy = np.arange(y1 - y0)[:, None] + 0.5 - bar_h / 2
                xx = np.arange(x1 - int(bar_x0))[None, :] + 0.5
                r = bar_h / 2
                dx = np.maximum(np.maximum(r - xx, xx - (x1 - int(bar_x0) - r)), 0)
                cov = np.clip(r - np.sqrt(dx ** 2 + yy ** 2) + 0.5, 0, 1)[..., None]
                seg[:] = seg * (1 - cov) + np.float32(accent) / 255 * cov
            F = frame.astype(np.float32) / 255
            out = F * (1 - env) + page * env
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out
