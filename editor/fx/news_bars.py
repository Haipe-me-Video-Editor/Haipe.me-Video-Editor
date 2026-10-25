"""News bars: a storm of breaking-news strips. Each strip is a coloured tag (BREAKING, JUST IN, LIVE, ...) on a white
bar with a heavy slanted headline; they slam in one after another from alternating sides, each at its own small
tilt, stacking above and below the speaker's face (never across it while there is room), then all fly out.

Every strip is drawn once as a sprite (2x supersampled, sheared to italic, tilted, with a drop shadow); a frame only
places sprites, so a long storm stays cheap.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .. import fonts
from . import _behind as B
from . import _camera as cam

NAME = "news_bars"
DOC = ("Breaking-news strips (a coloured tag like BREAKING / JUST IN on a white bar with a heavy slanted headline) "
       "slam in one by one from alternating sides around the face, then fly out. `items`: headlines, or "
       "{tag, text}. For hype, announcements, 'everyone is talking about this'.")
BEST_FOR = ["playful", "finance", "product", "any"]
DUR = (1.2, 8)
PARAMS = {
    "items": [],          # ["headline", ...] or [{"tag": "LIVE", "text": "headline"}, ...]; 1 .. 8 items
    "tags": ["BREAKING", "JUST IN", "LIVE", "NEW", "UPDATE"],  # cycled for items without their own tag
    "accent": "",         # tag colour (default: the style's accent)
    "stagger": 0.32,      # seconds between strips
    "tilt": 3.0,          # largest tilt of a strip, degrees
    "size": 0.056,        # bar height as a fraction of the frame height
}
EXIT = 0.35
SLAM = 0.4           # spring length of one strip's entry, s
SHEAR = 0.2          # italic lean


def normalise(items: list, tags: list) -> list:
    if not items:
        raise ValueError("news_bars needs items (headlines)")
    if len(items) > 8:
        raise ValueError("news_bars takes at most 8 items")
    out = []
    for k, it in enumerate(items):
        if isinstance(it, str):
            it = {"text": it}
        text = str(it.get("text", "")).strip()
        if not text:
            raise ValueError("news_bars item without text")
        out.append({"tag": str(it.get("tag") or tags[k % len(tags)]).upper(), "text": text.upper()})
    return out


def sprite(tag: str, text: str, h: int, accent, rot: float, max_w: int) -> np.ndarray:
    """One strip as RGBA float32: tag box + white bar + headline (wrapped to two lines when it is long), sheared to
    italic, rotated, with a soft shadow."""
    S = 2
    hh = h * S
    font = str(fonts.ensure_font("Montserrat"))
    f_tag = ImageFont.truetype(font, int(hh * 0.36))
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    tag_w = probe.textlength(tag, font=f_tag) + hh * 0.5
    # one line if it fits at a readable size, else two balanced lines in a taller bar (the italic lean widens the
    # strip by SHEAR x its height, so that comes off the room too)
    for lines, top, floor in (([text], 0.6, 0.45), ([" ".join(w) for w in B.split_lines(text)[-1]], 0.42, 0.3)):
        room = max_w * S - tag_w - hh * 0.9 - SHEAR * hh * (1 if len(lines) == 1 else 1.6)
        size = int(hh * top)
        f_text = ImageFont.truetype(font, size)
        while max(probe.textlength(ln, font=f_text) for ln in lines) > room and size >= hh * floor:
            size -= 2
            f_text = ImageFont.truetype(font, size)
        if size >= hh * floor:
            break
    else:
        raise ValueError(f"news_bars headline too long for one strip: {text!r}")
    bh = hh if len(lines) == 1 else int(hh * 1.6)
    text_w = max(probe.textlength(ln, font=f_text) for ln in lines)
    bar_w = int(tag_w + text_w + hh * 0.85)
    pad = int(hh * 0.6)
    im = Image.new("RGBA", (bar_w + 2 * pad, bh + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0 = pad, pad
    d.rectangle([x0, y0, x0 + bar_w, y0 + bh], fill=(255, 255, 255, 255))
    th = hh * 0.78
    ty = y0 + (bh - th) / 2
    d.rectangle([x0 + hh * 0.12, ty, x0 + hh * 0.12 + tag_w, ty + th], fill=tuple(accent) + (255,))
    d.text((x0 + hh * 0.12 + tag_w / 2, y0 + bh / 2), tag, font=f_tag, fill=(255, 255, 255, 255), anchor="mm")
    lh = size * 1.12
    for k, ln in enumerate(lines):
        ly = y0 + bh / 2 + (k - (len(lines) - 1) / 2) * lh
        d.text((x0 + hh * 0.12 + tag_w + hh * 0.3, ly), ln, font=f_text, fill=(12, 12, 14, 255), anchor="lm")
    # italic lean, then the tilt
    im = im.transform(im.size, Image.AFFINE, (1, SHEAR, -SHEAR * im.size[1] / 2, 0, 1, 0), Image.BICUBIC)
    im = im.rotate(rot, Image.BICUBIC, expand=True)
    a = im.getchannel("A")
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    shadow.putalpha(a.filter(ImageFilter.GaussianBlur(hh * 0.12)).point(lambda v: int(v * 0.4)))
    shadow = shadow.transform(im.size, Image.AFFINE, (1, 0, 0, 0, 1, -hh * 0.08), Image.BICUBIC)
    im = Image.alpha_composite(shadow, im)
    im = im.resize((im.size[0] // S, im.size[1] // S), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255


def slots(heights: list, face: dict, W: int, H: int) -> list:
    """Centre y of each strip, given each strip's drawn height: stack them above the head (upwards) and below the
    chin (downwards), alternating, with a gap of a quarter strip; packed tighter when that makes them all fit, and
    only then over the face (on the mouth line, never the eyes)."""
    top, bot = B.SAFE[1] * H, B.SAFE[3] * H
    head_top = face["top"] - face["fw"] * 0.35
    chin = face["cy"] + face["fw"] * 0.75
    base = min(heights)
    for gap in (base * 0.25, base * 0.04):
        up, down, ys = head_top - base * 0.2, chin + base * 0.2, []
        for k, hk in enumerate(heights):
            fits_up, fits_down = up - hk >= top, down + hk <= bot
            if fits_up and (k % 2 == 0 or not fits_down):
                ys.append(up - hk / 2)
                up -= hk + gap
            elif fits_down:
                ys.append(down + hk / 2)
                down += hk + gap
            else:
                ys.append(None)
        if None not in ys:
            break
    mouth = face["cy"] + face["fw"] * 0.45
    return [float(mouth if y is None else y) for y in ys]


def paste(out: np.ndarray, spr: np.ndarray, x: float, y: float, alpha: float) -> None:
    """Alpha-blend sprite (RGBA float) centred at (x, y) into out (float RGB), clipped to the frame."""
    H, W = out.shape[:2]
    h, w = spr.shape[:2]
    X, Y = round(x - w / 2), round(y - h / 2)
    x0, y0, x1, y1 = max(X, 0), max(Y, 0), min(X + w, W), min(Y + h, H)
    if x1 <= x0 or y1 <= y0 or alpha <= 0:
        return
    s = spr[y0 - Y:y1 - Y, x0 - X:x1 - X]
    a = s[..., 3:4] * alpha
    reg = out[y0:y1, x0:x1]
    reg[:] = reg * (1 - a) + s[..., :3] * a


def render(ctx):
    W, H = ctx.W, ctx.H
    items = normalise(list(ctx.param("items", PARAMS["items"]) or []), list(ctx.param("tags", PARAMS["tags"])))
    accent = cam.hex_rgb(ctx.param("accent") or ctx.style.get("accent", "#2f6bff")).astype(int)
    stagger = float(ctx.param("stagger", PARAMS["stagger"]))
    tilt = float(ctx.param("tilt", PARAMS["tilt"]))
    h = float(ctx.param("size", PARAMS["size"])) * H
    face = ctx.face()
    rng = np.random.default_rng(11)
    safe_w = (B.SAFE[2] - B.SAFE[0]) * W
    sprites = []
    for k, it in enumerate(items):
        rot = tilt * (rng.uniform(0.3, 1.0) * (-1 if k % 2 == 0 else 1))
        spr = sprite(it["tag"], it["text"], int(h), accent, rot, int(safe_w * 0.98))
        rows = np.nonzero((spr[..., 3] > 0.5).any(axis=1))[0]
        sprites.append((spr, float(rows[-1] - rows[0] + 1)))
    ys = slots([hk for _, hk in sprites], face, W, H)
    bars = []
    for k, (spr, _) in enumerate(sprites):
        side = -1 if k % 2 == 0 else 1
        cx = (B.SAFE[0] + B.SAFE[2]) / 2 * W + rng.uniform(-0.04, 0.04) * W
        cx = float(np.clip(cx, B.SAFE[0] * W + spr.shape[1] / 2 - h, B.SAFE[2] * W - spr.shape[1] / 2 + h))
        bars.append({"spr": spr, "x": cx, "y": ys[k], "side": side, "t0": 0.1 + k * stagger})
    slam = B.spring("snappy")
    with ctx.writer() as write:
        for i, frame in enumerate(ctx.frames()):
            t = i / ctx.fps
            out = frame.astype(np.float32) / 255
            for k, b in enumerate(bars):
                u = B.progress(t, b["t0"], SLAM)
                if u <= 0:
                    continue
                w = b["spr"].shape[1]
                off = (1 - slam(u)) * (W / 2 + w) * b["side"]
                v = B.progress(t, ctx.dur - EXIT + k * 0.03, EXIT - len(bars) * 0.03)
                off += B.ease_in(v) * (W / 2 + w) * -b["side"]
                paste(out, b["spr"], b["x"] + off, b["y"], min(1.0, u * 4))
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out
