"""Checklist pop: short items pop up beside the speaker as white pills, one under another, and each one ticks (a
green circle with a white check springs in, the text darkens) as the next arrives. Light and quick, beside the
chin, for "trim, captions, effects, post" lists said out loud.

Different from `checklist` (a dark frosted card with a counter and a progress bar): here the items float on their
own over the shot. Every pill is drawn once in both states (2x supersampled), so a frame only places sprites.
"""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .. import fonts
from . import _behind as B
from . import _camera as cam
from .news_bars import paste

NAME = "checklist_pop"
DOC = ("White pills pop up one by one beside the speaker's chin, each ticking green as the next lands: a light, "
       "spoken list ('trim, captions, effects, post'). `items`: 1-6 short words from the script.")
BEST_FOR = ["product", "playful", "any"]
DUR = (1.5, 10)
PARAMS = {
    "items": [],        # 1-6 short items (required)
    "times": None,      # seconds into the window when each item appears (default: spread evenly)
    "tick": 0.35,       # how long after it appears an item ticks, s
    "side": "auto",     # auto | left | right: which side of the face the pills grow towards
    "green": "#16a05d",  # tick colour
    "size": 0.05,       # pill height as a fraction of the frame height
}
POP = 0.32
EXIT = 0.3
INK, GREY = (17, 24, 39), (120, 128, 140)


def times_for(n: int, given, dur: float, tick: float) -> list:
    """Appear times: as given, or spread so the last item has time to tick and be read before the exit."""
    if given:
        if len(given) != n:
            raise ValueError(f"checklist_pop times needs {n} entries, one per item")
        return [float(t) for t in given]
    last = max(0.15, dur - EXIT - tick - 0.45)
    return [0.15 + (last - 0.15) * k / max(n - 1, 1) for k in range(n)]


def pill(text: str, h: int, done: bool, green) -> np.ndarray:
    """One pill as RGBA float32: white body, light rim, soft shadow; a green check circle when done, a grey ring
    when not."""
    S = 2
    hh = h * S
    font = ImageFont.truetype(str(fonts.ensure_font("Montserrat")), int(hh * 0.5))
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    tw = probe.textlength(text, font=font)
    pad = int(hh * 0.35)
    w = int(hh * 0.28 + hh * 0.62 + hh * 0.26 + tw + hh * 0.42)
    im = Image.new("RGBA", (w + 2 * pad, hh + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = pad, pad, pad + w, pad + hh
    d.rounded_rectangle([x0, y0, x1, y1], radius=hh / 2, fill=(255, 255, 255, 250), outline=(214, 219, 226, 255),
                        width=max(2, int(hh * 0.05)))
    cr = hh * 0.31
    cx, cy = x0 + hh * 0.28 + cr, y0 + hh / 2
    if done:
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=tuple(green) + (255,))
        lw = max(3, int(hh * 0.075))
        d.line([(cx - cr * 0.45, cy + cr * 0.02), (cx - cr * 0.1, cy + cr * 0.36), (cx + cr * 0.48, cy - cr * 0.34)],
               fill=(255, 255, 255, 255), width=lw, joint="curve")
    else:
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], outline=(200, 205, 212, 255), width=max(2, int(hh * 0.05)))
    d.text((cx + cr + hh * 0.26, cy), text, font=font, fill=(INK if done else GREY) + (255,), anchor="lm")
    a = im.getchannel("A")
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    shadow.putalpha(a.filter(ImageFilter.GaussianBlur(hh * 0.12)).point(lambda v: int(v * 0.28)))
    shadow = shadow.transform(im.size, Image.AFFINE, (1, 0, 0, 0, 1, -hh * 0.06), Image.BICUBIC)
    im = Image.alpha_composite(shadow, im)
    im = im.resize((im.size[0] // S, im.size[1] // S), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255


def layout(widths: list, h: float, face: dict, side: str, W: int, H: int) -> tuple:
    """(left x of the pills, centre y of each, side): a column starting just under the mouth, growing towards the
    side with more room, nudged up if it would run past the safe zone's bottom."""
    if side not in ("auto", "left", "right"):
        raise ValueError("checklist_pop side is auto, left or right")
    if side == "auto":
        side = "right" if face["cx"] <= W / 2 else "left"
    step = h * 1.25
    top = face["cy"] + face["fw"] * 0.62 + h * 0.6  # below the chin
    bottom = B.SAFE[3] * H - h * 0.6
    top = min(top, bottom - step * (len(widths) - 1))
    top = max(top, B.SAFE[1] * H + h)
    wmax = max(widths)
    if side == "right":
        x = face["cx"] - face["fw"] * 0.25
        x = min(x, B.SAFE[2] * W - wmax)
    else:
        x = face["cx"] + face["fw"] * 0.25 - wmax
        x = max(x, B.SAFE[0] * W)
    x = float(np.clip(x, B.SAFE[0] * W, max(B.SAFE[0] * W, B.SAFE[2] * W - wmax)))
    return x, [top + k * step for k in range(len(widths))], side


def render(ctx):
    W, H = ctx.W, ctx.H
    items = [str(t).strip() for t in (ctx.param("items", PARAMS["items"]) or [])]
    if not 1 <= len(items) <= 6 or not all(items):
        raise ValueError("checklist_pop needs 1-6 non-empty items")
    tick = float(ctx.param("tick", PARAMS["tick"]))
    times = times_for(len(items), ctx.param("times", PARAMS["times"]), ctx.dur, tick)
    green = cam.hex_rgb(ctx.param("green", PARAMS["green"])).astype(int)
    h = int(float(ctx.param("size", PARAMS["size"])) * H)
    sprites = [(pill(t, h, False, green), pill(t, h, True, green)) for t in items]
    widths = [s[1].shape[1] for s in sprites]
    x, ys, _ = layout(widths, h, ctx.face(), ctx.param("side", PARAMS["side"]), W, H)
    pop = B.spring("bouncy")
    with ctx.writer() as write:
        for i, frame in enumerate(ctx.frames()):
            t = i / ctx.fps
            out = frame.astype(np.float32) / 255
            for k, (todo, done) in enumerate(sprites):
                u = B.progress(t, times[k], POP)
                if u <= 0:
                    continue
                v = B.progress(t, ctx.dur - EXIT + k * 0.04, EXIT - 0.04 * len(sprites))
                s = max(pop(u), 0.0) * (1 - 0.3 * B.ease_in(v))
                a = min(1.0, u * 3) * (1 - B.ease_in(v))
                g = B.progress(t, times[k] + tick, 0.14)  # the tick: crossfade to the done pill with a small pulse
                spr = todo if g <= 0 else done if g >= 1 else todo * (1 - g) + done * g
                s *= 1 + 0.07 * np.sin(np.pi * g)
                if s < 0.05 or a <= 0:
                    continue
                sh, sw = spr.shape[:2]
                if abs(s - 1) > 1e-3:
                    spr = cv2.resize(spr, (max(1, round(sw * s)), max(1, round(sh * s))), interpolation=cv2.INTER_LINEAR)
                paste(out, spr, x + spr.shape[1] / 2, ys[k], a)  # grows out from its left end, where the check sits
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out
