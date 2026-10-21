"""Shared drawing kit for the cut-out styles (paper_cut, doodle_boil, green_screen): springs, procedural noise,
hand-drawn strokes (a single-stroke marker alphabet that can be drawn on and "boiled"), person placement from the
matte, and alpha compositing. Pure numpy / OpenCV / PIL, no network, deterministic for a given seed.

Private to the fx pack (the registry skips modules whose name starts with "_")."""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---- colour ---------------------------------------------------------------------------------------------------


def rgb(hex_or_list, default=(255, 255, 255)) -> np.ndarray:
    """#rrggbb (or [r, g, b]) to a float32 RGB triple 0-255."""
    if hex_or_list is None:
        return np.array(default, np.float32)
    if isinstance(hex_or_list, (list, tuple, np.ndarray)):
        return np.array(hex_or_list[:3], np.float32)
    h = str(hex_or_list).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def mix(a, b, t: float) -> np.ndarray:
    return rgb(a) * (1 - t) + rgb(b) * t


def luma(c) -> float:
    c = rgb(c)
    return float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])


def hexc(c) -> str:
    c = np.clip(rgb(c), 0, 255).astype(int)
    return "#%02x%02x%02x" % tuple(c)


# ---- time -----------------------------------------------------------------------------------------------------

SPRINGS = {"gentle": (170, 20, 1), "snappy": (400, 26, 1), "bouncy": (400, 22.5, 1)}  # = graphics/spring.py


def spring(preset: str = "snappy"):
    """The house damped-spring ease (same closed form as graphics/spring.py): f(0) = 0, f(1) = 1, overshoot between."""
    k, d, m = SPRINGS[preset]
    w0, z = math.sqrt(k / m), d / (2 * math.sqrt(k * m))
    a = z * w0
    wd = w0 * math.sqrt(max(1e-9, 1 - z * z))

    def x(s):
        return 1 - math.exp(-a * s) * (math.cos(wd * s) + (a / wd) * math.sin(wd * s))
    scan, steps, T = 12 / a, 4000, 12 / a
    for i in range(steps, -1, -1):
        if abs(1 - x(i / steps * scan)) > 0.001:
            T = (i + 1) / steps * scan
            break
    xT = x(T)
    return lambda t: 0.0 if t <= 0 else 1.0 if t >= 1 else x(t * T) + t * (1 - xT)


def ease_in(t: float, p: float = 2) -> float:
    t = min(1.0, max(0.0, t))
    return t ** p


def ease_out(t: float, p: float = 3) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** p


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float32) - e0) / max(1e-6, e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def steps_of(n: int, pattern=(2, 3, 2, 2, 3)) -> list:
    """Stop-motion step index per frame: holds of 2-3 frames in an irregular, repeating pattern."""
    out, s, i, k = [], 0, 0, 0
    while len(out) < n:
        out += [s] * pattern[k % len(pattern)]
        s, k = s + 1, k + 1
        i += 1
    return out[:n]


# ---- noise ----------------------------------------------------------------------------------------------------

def noise(h: int, w: int, cell: float, seed: int, octaves: int = 1) -> np.ndarray:
    """Smooth value noise in -1..1, shape (h, w); `cell` is the feature size in pixels."""
    rng = np.random.default_rng(seed)
    out, amp, tot = np.zeros((h, w), np.float32), 1.0, 0.0
    for _ in range(octaves):
        gh, gw = int(h / cell) + 3, int(w / cell) + 3
        g = rng.uniform(-1, 1, (gh, gw)).astype(np.float32)
        big = cv2.resize(g, (int(gw * cell), int(gh * cell)), interpolation=cv2.INTER_CUBIC)
        out += amp * big[:h, :w]
        tot += amp
        amp, cell = amp * 0.5, max(1.0, cell / 2)
    return np.clip(out / tot, -1, 1)


def grain(h: int, w: int, seed: int, strength: float = 1.0) -> np.ndarray:
    """Fine paper fibre: per-pixel noise with a little horizontal streak, around 1.0."""
    rng = np.random.default_rng(seed)
    g = rng.normal(0, 1, (h, w)).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), sigmaX=1.6, sigmaY=0.6)
    return 1 + strength * g / (g.std() + 1e-6)


# ---- strokes --------------------------------------------------------------------------------------------------

def catmull(pts, n: int = 8, closed: bool = False) -> np.ndarray:
    """Catmull-Rom spline through pts, n samples per segment."""
    P = np.asarray(pts, np.float32)
    if len(P) < 3:
        return P
    if closed:
        P = np.vstack([P[-1:], P, P[:2]])
    else:
        P = np.vstack([P[:1], P, P[-1:]])
    t = np.linspace(0, 1, n, endpoint=False, dtype=np.float32)[:, None]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2:-1])
    return np.vstack(out)


def length(stroke) -> float:
    s = np.asarray(stroke, np.float32)
    return float(np.linalg.norm(np.diff(s, axis=0), axis=1).sum()) if len(s) > 1 else 0.0


def reveal(strokes: list, p: float) -> list:
    """The first fraction p (0-1) of a stroke list by drawn length: the "draw on" animation."""
    if p >= 1:
        return strokes
    if p <= 0:
        return []
    total = sum(length(s) for s in strokes)
    left, out = p * total, []
    for s in strokes:
        s = np.asarray(s, np.float32)
        L = length(s)
        if L <= left:
            out.append(s)
            left -= L
            continue
        seg = np.linalg.norm(np.diff(s, axis=0), axis=1)
        cum = np.concatenate([[0], np.cumsum(seg)])
        k = int(np.searchsorted(cum, left))
        if k >= 1:
            f = (left - cum[k - 1]) / max(seg[k - 1], 1e-6)
            out.append(np.vstack([s[:k], s[k - 1] + f * (s[k] - s[k - 1])]))
        break
    return out


def draw(mask: np.ndarray, strokes: list, width: float, value: int = 255) -> np.ndarray:
    """Anti-aliased round-capped polylines into a uint8 mask (in place)."""
    w = max(1, int(round(width)))
    for s in strokes:
        s = np.asarray(s, np.float32)
        if len(s) == 0:
            continue
        if len(s) == 1 or length(s) < 0.5:
            c = tuple(int(v) for v in np.round(s[0] * 16))
            cv2.circle(mask, c, max(1, w // 2) * 16, value, -1, cv2.LINE_AA, shift=4)
            continue
        cv2.polylines(mask, [np.round(s * 16).astype(np.int32)], False, value, w, cv2.LINE_AA, shift=4)
    return mask


def wobble(strokes: list, amp: float, seed: int, freq: float = 0.02) -> list:
    """Hand jitter: each point moves along a smooth random field (so a held stroke stays a stroke, not noise)."""
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 2 * np.pi, 6)
    fr = freq * rng.uniform(0.7, 1.4, 6)
    out = []
    for s in strokes:
        s = np.asarray(s, np.float32)
        x, y = s[:, 0], s[:, 1]
        dx = np.sin(x * fr[0] + y * fr[1] + ph[0]) + 0.5 * np.sin(x * fr[2] * 2.3 - y * fr[3] * 1.7 + ph[1])
        dy = np.sin(y * fr[4] - x * fr[5] + ph[2]) + 0.5 * np.sin(y * fr[1] * 2.1 + x * fr[0] * 1.3 + ph[3])
        out.append(s + amp / 1.5 * np.stack([dx, dy], 1))
    return out


def transform(strokes: list, scale: float = 1, rot: float = 0, at=(0, 0), origin=(0, 0)) -> list:
    c, s = math.cos(rot), math.sin(rot)
    R = np.array([[c, -s], [s, c]], np.float32) * scale
    o, a = np.asarray(origin, np.float32), np.asarray(at, np.float32)
    return [(np.asarray(k, np.float32) - o) @ R.T + a for k in strokes]


def bounds(strokes: list):
    allp = np.vstack([np.asarray(s, np.float32) for s in strokes if len(s)])
    return allp.min(0), allp.max(0)


# ---- a single-stroke marker alphabet --------------------------------------------------------------------------
# Each glyph is (advance width, strokes); a stroke is "L" (straight polyline) or "C" (Catmull-Rom curve) through
# points in a box 1 high (y down, 0 = cap line, 1 = baseline). Drawn in order, so "draw on" writes like a hand.

_O = ("C", [(.4, 0), (.1, .12), (0, .5), (.1, .88), (.4, 1), (.7, .88), (.8, .5), (.7, .12), (.4, 0), (.3, .03)])
_P = ("C", [(0, .02), (.44, .02), (.6, .25), (.44, .48), (0, .5)])
GLYPHS = {
    "A": (.78, [("L", [(0, 1), (.38, 0), (.76, 1)]), ("L", [(.14, .64), (.62, .64)])]),
    "B": (.68, [("L", [(0, 1), (0, 0)]), ("C", [(0, 0), (.42, .02), (.56, .24), (.4, .46), (0, .48)]),
                ("C", [(0, .48), (.48, .5), (.64, .74), (.46, .98), (0, 1)])]),
    "C": (.72, [("C", [(.68, .16), (.46, 0), (.18, .04), (.02, .3), (.02, .7), (.2, .97), (.46, 1), (.7, .84)])]),
    "D": (.74, [("L", [(0, 0), (0, 1)]), ("C", [(0, 0), (.42, .04), (.68, .3), (.68, .7), (.42, .96), (0, 1)])]),
    "E": (.64, [("L", [(.6, 0), (0, 0), (0, 1), (.62, 1)]), ("L", [(0, .5), (.48, .5)])]),
    "F": (.6, [("L", [(.6, 0), (0, 0), (0, 1)]), ("L", [(0, .5), (.46, .5)])]),
    "G": (.76, [("C", [(.68, .16), (.46, 0), (.18, .04), (.02, .3), (.02, .7), (.2, .97), (.46, 1), (.68, .86),
                       (.7, .58)]), ("L", [(.7, .58), (.4, .58)])]),
    "H": (.72, [("L", [(0, 0), (0, 1)]), ("L", [(.66, 0), (.66, 1)]), ("L", [(0, .5), (.66, .5)])]),
    "I": (.24, [("L", [(.1, 0), (.1, 1)])]),
    "J": (.58, [("C", [(.52, 0), (.52, .72), (.42, .96), (.2, 1), (0, .84)])]),
    "K": (.68, [("L", [(0, 0), (0, 1)]), ("L", [(.62, 0), (0, .6)]), ("L", [(.18, .44), (.66, 1)])]),
    "L": (.6, [("L", [(0, 0), (0, 1), (.58, 1)])]),
    "M": (.9, [("L", [(0, 1), (.04, 0), (.42, .66), (.8, 0), (.84, 1)])]),
    "N": (.74, [("L", [(0, 1), (0, 0), (.66, 1), (.66, 0)])]),
    "O": (.86, [_O]),
    "P": (.64, [("L", [(0, 1), (0, 0)]), _P]),
    "Q": (.86, [_O, ("L", [(.48, .72), (.84, 1.06)])]),
    "R": (.68, [("L", [(0, 1), (0, 0)]), _P, ("L", [(.26, .5), (.64, 1)])]),
    "S": (.66, [("C", [(.6, .14), (.4, 0), (.12, .04), (.04, .24), (.2, .42), (.46, .54), (.62, .74), (.52, .96),
                       (.26, 1), (0, .86)])]),
    "T": (.7, [("L", [(0, 0), (.7, 0)]), ("L", [(.35, 0), (.35, 1)])]),
    "U": (.72, [("C", [(0, 0), (0, .7), (.12, .96), (.33, 1), (.55, .94), (.66, .7), (.66, 0)])]),
    "V": (.74, [("L", [(0, 0), (.36, 1), (.72, 0)])]),
    "W": (.98, [("L", [(0, 0), (.22, 1), (.48, .34), (.72, 1), (.94, 0)])]),
    "X": (.68, [("L", [(0, 0), (.64, 1)]), ("L", [(.64, 0), (0, 1)])]),
    "Y": (.7, [("L", [(0, 0), (.34, .5), (.68, 0)]), ("L", [(.34, .5), (.34, 1)])]),
    "Z": (.68, [("L", [(0, 0), (.64, 0), (0, 1), (.66, 1)])]),
    "0": (.66, [("C", [(.32, 0), (.06, .14), (0, .5), (.08, .88), (.32, 1), (.56, .88), (.62, .5), (.56, .12),
                       (.32, 0), (.24, .04)])]),
    "1": (.42, [("L", [(.04, .2), (.28, 0), (.28, 1)])]),
    "2": (.64, [("C", [(.04, .2), (.2, .02), (.44, .02), (.58, .2), (.52, .44), (.02, 1)]),
                ("L", [(.02, 1), (.62, 1)])]),
    "3": (.62, [("C", [(.04, .12), (.3, 0), (.54, .1), (.52, .36), (.22, .48)]),
                ("C", [(.22, .48), (.56, .6), (.6, .84), (.36, 1), (.02, .9)])]),
    "4": (.68, [("L", [(.5, 1), (.5, 0), (0, .68), (.66, .68)])]),
    "5": (.64, [("L", [(.58, 0), (.08, 0), (.04, .44)]),
                ("C", [(.04, .44), (.36, .36), (.6, .54), (.6, .82), (.36, 1), (0, .9)])]),
    "6": (.64, [("C", [(.54, .04), (.24, .1), (.04, .46), (.06, .84), (.3, 1), (.54, .9), (.58, .64), (.34, .5),
                       (.06, .62)])]),
    "7": (.64, [("L", [(0, 0), (.62, 0), (.2, 1)])]),
    "8": (.64, [("C", [(.32, .48), (.08, .36), (.1, .1), (.32, 0), (.54, .1), (.56, .34), (.32, .48), (.04, .64),
                       (.06, .92), (.32, 1), (.6, .92), (.6, .64), (.32, .48)])]),
    "9": (.64, [("C", [(.56, .36), (.32, .5), (.06, .38), (.06, .12), (.3, 0), (.56, .1), (.58, .4), (.5, .8),
                       (.3, 1), (.06, .94)])]),
    "%": (.7, [("C", [(.14, 0), (0, .12), (.14, .26), (.28, .12), (.14, 0)]), ("L", [(.62, 0), (.04, 1)]),
               ("C", [(.52, .74), (.38, .86), (.52, 1), (.66, .86), (.52, .74)])]),
    "!": (.26, [("L", [(.1, 0), (.1, .7)]), ("L", [(.1, .95), (.1, .97)])]),
    "?": (.6, [("C", [(.02, .18), (.2, 0), (.46, .04), (.52, .26), (.28, .46), (.26, .7)]),
               ("L", [(.26, .95), (.26, .97)])]),
    "+": (.66, [("L", [(.32, .2), (.32, .8)]), ("L", [(.02, .5), (.62, .5)])]),
    "-": (.52, [("L", [(.06, .52), (.44, .5)])]),
    ".": (.22, [("L", [(.06, .95), (.07, .97)])]),
    ",": (.24, [("L", [(.1, .9), (.03, 1.1)])]),
    "'": (.2, [("L", [(.08, 0), (.06, .24)])]),
    ":": (.22, [("L", [(.06, .3), (.07, .32)]), ("L", [(.06, .95), (.07, .97)])]),
    "/": (.56, [("L", [(.52, 0), (0, 1)])]),
    "$": (.64, [("C", [(.58, .2), (.4, .08), (.14, .1), (.06, .28), (.2, .44), (.44, .54), (.6, .7), (.5, .9),
                       (.24, .94), (.02, .82)]), ("L", [(.32, -.08), (.32, 1.08)])]),
    "&": (.72, [("C", [(.7, 1), (.12, .44), (.12, .14), (.3, 0), (.46, .12), (.4, .34), (.04, .6), (.06, .9),
                       (.3, 1), (.5, .9), (.66, .62)])]),
    "#": (.7, [("L", [(.24, 0), (.16, 1)]), ("L", [(.52, 0), (.44, 1)]), ("L", [(0, .32), (.68, .32)]),
               ("L", [(0, .68), (.66, .68)])]),
    " ": (.42, []),
}


def has_arabic(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" or "ݐ" <= ch <= "ݿ" or "ﭐ" <= ch <= "﻿" for ch in text)


def glyph_strokes(ch: str, h: float):
    """(advance, strokes) for one character at cap height h, or None when the alphabet lacks it."""
    g = GLYPHS.get(ch.upper())
    if g is None:
        return None
    adv, parts = g
    out = []
    for kind, pts in parts:
        P = np.asarray(pts, np.float32) * h
        out.append(catmull(P, 10) if kind == "C" else _densify(P, h * 0.08))
    return adv * h, out


def _densify(P, step: float):
    """Insert points along straight segments so wobble() can bend them a little like a real hand."""
    out = [P[0]]
    for a, b in zip(P[:-1], P[1:]):
        n = max(1, int(np.linalg.norm(b - a) / max(step, 1)))
        for k in range(1, n + 1):
            out.append(a + (b - a) * k / n)
    return np.asarray(out, np.float32)


def text_strokes(text: str, h: float, seed: int = 7, tracking: float = 0.16, line_gap: float = 0.42):
    """Hand-lettered strokes for text (\\N or \\n breaks lines) at cap height h, origin top-left; each letter gets a
    fixed small tilt / size / baseline wobble so it reads as written, not typeset. Returns (strokes, (w, h))."""
    rng = np.random.default_rng(seed)
    lines = text.replace("\\N", "\n").split("\n")
    out, widths, y = [], [], 0.0
    rows = []
    for line in lines:
        x, row = 0.0, []
        for ch in line:
            g = glyph_strokes(ch, h)
            if g is None:
                continue
            adv, strokes = g
            if strokes:
                sc = 1 + rng.uniform(-0.06, 0.06)
                rot = math.radians(rng.uniform(-4, 4))
                dy = rng.uniform(-0.04, 0.04) * h
                row += transform(strokes, sc, rot, at=(x + adv / 2, y + h / 2 + dy), origin=(adv / 2, h / 2))
            x += adv + tracking * h
        widths.append(max(0.0, x - tracking * h))
        rows.append(row)
        y += h * (1 + line_gap)
    W = max(widths) if widths else 0
    for row, w in zip(rows, widths):  # centre each line in the block
        out += [s + np.array([(W - w) / 2, 0], np.float32) for s in row]
    return out, (W, y - h * line_gap)


def text_mask_font(text: str, font_path, h: float, rtl_wipe: float = 1.0):
    """Fallback for scripts the stroke alphabet lacks (Arabic): the text in a font, as a float mask, with a
    right-to-left wipe (rtl_wipe 0-1) standing in for the draw-on. Returns (mask, (w, h))."""
    size = int(h * 1.35)
    font = ImageFont.truetype(str(font_path), size)
    lines = text.replace("\\N", "\n").split("\n")
    dirs = ["rtl" if has_arabic(s) else None for s in lines]
    boxes = [font.getbbox(s, direction=d_) for s, d_ in zip(lines, dirs)]
    W = max(b[2] - b[0] for b in boxes) + 16
    lh = max(b[3] - b[1] for b in boxes) + int(size * 0.2)
    img = Image.new("L", (W, lh * len(lines) + 16), 0)
    d = ImageDraw.Draw(img)
    for i, (s, b, d_) in enumerate(zip(lines, boxes, dirs)):
        d.text(((W - (b[2] - b[0])) / 2 - b[0], i * lh - b[1] + 8), s, font=font, fill=255, direction=d_)
    m = np.asarray(img, np.float32) / 255
    if rtl_wipe < 1:
        cut = int(m.shape[1] * (1 - rtl_wipe))
        m[:, :cut] = 0
    return m, (m.shape[1], m.shape[0])


# ---- doodle shapes (unit-size, centred at 0) ------------------------------------------------------------------

def star(r: float, points: int = 5, seed: int = 0) -> list:
    """A hand-drawn star outline in one stroke that overshoots its start, like a marker."""
    rng = np.random.default_rng(seed)
    pts = []
    for i in range(points * 2 + 2):
        a = -math.pi / 2 + i * math.pi / points
        rr = (r if i % 2 == 0 else r * 0.45) * (1 + rng.uniform(-0.06, 0.06))
        pts.append((rr * math.cos(a), rr * math.sin(a)))
    return [_densify(np.asarray(pts, np.float32), r * 0.15)]


def sparkle(r: float) -> list:
    """Four-point twinkle: sharp tips joined by concave curves (quadratic Beziers pulled to the centre)."""
    tips = [np.array([r * math.cos(a), r * math.sin(a)], np.float32)
            for a in (-math.pi / 2, 0, math.pi / 2, math.pi, 3 * math.pi / 2)]
    t = np.linspace(0, 1, 10, dtype=np.float32)[:, None]
    ctrl = np.zeros(2, np.float32)
    segs = [(1 - t) ** 2 * a + 2 * (1 - t) * t * (ctrl + (a + b) * 0.12) + t ** 2 * b for a, b in zip(tips, tips[1:])]
    return [np.vstack(segs)]


def heart(r: float) -> list:
    t = np.linspace(0, 2 * np.pi * 1.04, 60)
    x = 16 * np.sin(t) ** 3
    y = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
    return [np.stack([x, y], 1).astype(np.float32) * (r / 17)]


def ellipse_loop(rx: float, ry: float, turns: float = 1.12, seed: int = 0) -> list:
    """A loose hand-drawn ellipse that doesn't quite close (circling something with a marker)."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 2 * np.pi * turns, 90) + rng.uniform(0, 2 * np.pi)
    grow = 1 + 0.06 * np.linspace(0, 1, len(t))
    tilt = math.radians(rng.uniform(-5, 5))
    x, y = rx * np.cos(t) * grow, ry * np.sin(t) * grow
    c, s = math.cos(tilt), math.sin(tilt)
    return [np.stack([x * c - y * s, x * s + y * c], 1).astype(np.float32)]


def underline(w: float, seed: int = 0, double: bool = True) -> list:
    rng = np.random.default_rng(seed)
    x = np.linspace(0, w, 24)
    y = np.sin(x / w * np.pi) * w * 0.02 + rng.uniform(-1, 1) * w * 0.01
    out = [np.stack([x, y], 1).astype(np.float32)]
    if double:
        x2 = np.linspace(w * 0.08, w * 0.9, 20)
        y2 = w * 0.06 + np.sin(x2 / w * np.pi) * w * 0.015
        out.append(np.stack([x2[::-1], y2[::-1]], 1).astype(np.float32))
    return out


def arrow(a, b, bend: float = 0.25, head: float = 0.18) -> list:
    """A curved arrow from a to b with a two-stroke head."""
    a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
    d = b - a
    n = np.array([-d[1], d[0]], np.float32)
    mid = (a + b) / 2 + n * bend
    shaft = catmull([a, a + (mid - a) * 0.5 + n * bend * 0.2, mid, b], 10)
    L = float(np.linalg.norm(d))
    end_dir = shaft[-1] - shaft[-4]
    end_dir /= np.linalg.norm(end_dir) + 1e-6
    hl = L * head
    out = [shaft]
    for sgn in (1, -1):
        ang = math.radians(28) * sgn
        c, s = math.cos(ang), math.sin(ang)
        v = -end_dir
        r = np.array([v[0] * c - v[1] * s, v[0] * s + v[1] * c], np.float32)
        out.append(np.stack([b, b + r * hl]))
    return out


def zigzag(w: float, h: float, rows: int, seed: int = 0, slant: float = 0.25) -> list:
    """Crayon hatching that fills a w x h box with one back-and-forth stroke."""
    rng = np.random.default_rng(seed)
    pts, n = [], rows * 2
    for i in range(n + 1):
        x = w * i / n + rng.uniform(-0.25, 0.25) * w / n
        y = (0 if i % 2 == 0 else h) + rng.uniform(-0.08, 0.08) * h
        pts.append((x + slant * (y - h / 2), y))
    return [np.asarray(pts, np.float32)]


def loops(w: float, h: float, n: int = 4) -> list:
    """A row of little cursive loops: ' oooo '."""
    t = np.linspace(0, 2 * np.pi * n, 40 * n)
    r = h / 2
    x = t / (2 * np.pi * n) * w + r * 0.9 * np.sin(t)
    y = -r * np.cos(t)
    return [np.stack([x, y], 1).astype(np.float32)]


def cross(r: float) -> list:
    return [np.array([(-r, -r), (r, r)], np.float32), np.array([(r, -r), (-r, r)], np.float32)]


def asterisk(r: float) -> list:
    out = []
    for k in range(3):
        a = math.pi / 2 + k * math.pi / 3
        v = np.array([math.cos(a), math.sin(a)], np.float32) * r
        out.append(np.stack([-v, v]))
    return out


# ---- the person -----------------------------------------------------------------------------------------------

def small_mattes(ctx, every: int = 2, scale: int = 4) -> list:
    """Every `every`-th clean matte of the window at 1/scale size (float32 0-1), for layout decisions."""
    cm = clean_mattes(ctx)
    return [cv2.resize(np.asarray(cm[i]), (ctx.W // scale, ctx.H // scale), interpolation=cv2.INTER_AREA)
            .astype(np.float32) / 255 for i in range(0, len(cm), every)]


def occupancy(mattes: list, q: float = 50) -> np.ndarray:
    """Where the person usually is: the q-th percentile of the matte over time (0-1)."""
    return np.percentile(np.stack(mattes), q, axis=0).astype(np.float32)


def bbox(mask: np.ndarray, thr: float = 0.5):
    """(x0, y0, x1, y1) as fractions of the mask, or None."""
    ys, xs = np.where(mask > thr)
    if len(xs) < 20:
        return None
    h, w = mask.shape
    return (float(np.percentile(xs, 0.5) / w), float(np.percentile(ys, 0.5) / h),
            float((np.percentile(xs, 99.5) + 1) / w), float((np.percentile(ys, 99.5) + 1) / h))


def face_box(ctx):
    """Face box over the window (x0, y0, x1, y1 px) from landmarks: the 5th-95th percentile of every frame's box,
    so the eyes and mouth stay clear all the time. None when no face was found."""
    pts = [p for p in ctx.landmarks(every=3) if p is not None]
    if not pts:
        return None
    boxes = np.array([[p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()] for p in pts], np.float32)
    lo, hi = np.percentile(boxes, 5, axis=0), np.percentile(boxes, 95, axis=0)
    return float(lo[0]), float(lo[1]), float(hi[2]), float(hi[3])


def place(W: int, H: int, box, scale: float, side: str = "center", bleed: float = 10):
    """Affine matrix (2x3) that scales the frame by `scale` about the bottom and puts the person on `side`.
    A person cut by the frame's left/right/bottom edge stays cut by it (the cut edge never shows mid-frame),
    with `bleed` px of overscan so stop-motion jitter can't open a gap."""
    x0, y0, x1, y1 = box
    target = {"left": 0.36, "center": 0.5, "right": 0.64}.get(side, 0.5) * W
    cx = (x0 + x1) / 2 * W
    tx = target - scale * cx
    if x0 < 0.02 and x1 > 0.98:  # cut on both sides: keep the side the effect asked for
        if side == "left":
            tx = -bleed
        elif side == "right":
            tx = W + bleed - scale * W
    else:
        if x0 < 0.02:
            tx = min(tx, -bleed)
        if x1 > 0.98:
            tx = max(tx, W + bleed - scale * W)
    ty = H - scale * H + (bleed if y1 > 0.98 else 0)
    return np.array([[scale, 0, tx], [0, scale, ty]], np.float32)


def lerp_m(M0, M1, t: float):
    return M0 * (1 - t) + M1 * t


IDENTITY = np.array([[1, 0, 0], [0, 1, 0]], np.float32)


def warp(img: np.ndarray, M, W: int, H: int, interp=cv2.INTER_LINEAR) -> np.ndarray:
    if np.allclose(M, IDENTITY):
        return img
    return cv2.warpAffine(img, np.asarray(M, np.float32), (W, H), flags=interp, borderMode=cv2.BORDER_CONSTANT,
                          borderValue=0)


def edge_fade(a: np.ndarray, sides: dict, width: float) -> np.ndarray:
    """Fade the alpha towards the given frame sides ({"left": True, ...}) over `width` px (soft cut edges)."""
    h, w = a.shape
    out = a
    if sides.get("left"):
        out = out * smoothstep(0, width, np.arange(w, dtype=np.float32))[None, :]
    if sides.get("right"):
        out = out * smoothstep(0, width, np.arange(w, dtype=np.float32)[::-1])[None, :]
    if sides.get("bottom"):
        out = out * smoothstep(0, width, np.arange(h, dtype=np.float32)[::-1])[:, None]
    return out


def decontaminate(rgb: np.ndarray, a: np.ndarray, sigma: float = 6) -> np.ndarray:
    """Replace the old background bleeding into the matte's soft edge with the speaker's own colour (0-255 in and
    out, float32): cutout.foreground's blur-fusion estimate. `sigma` is kept for callers; the radii are set there."""
    from .. import cutout
    return cutout.foreground(rgb.astype(np.float32) / 255, a) * 255


def over(dst: np.ndarray, src_rgb, a: np.ndarray) -> np.ndarray:
    """dst (float32 HxWx3) with src (colour triple or HxWx3) composited at alpha a (HxW)."""
    a = a[..., None] if a.ndim == 2 else a
    return dst * (1 - a) + np.asarray(src_rgb, np.float32) * a


def blur(a: np.ndarray, sigma: float, down: int = 4) -> np.ndarray:
    """Gaussian blur done at 1/down size (fast for big sigmas), back at full size."""
    if sigma <= 0:
        return a
    h, w = a.shape[:2]
    if down > 1 and sigma > down * 1.5:
        s = cv2.resize(a, (max(1, w // down), max(1, h // down)), interpolation=cv2.INTER_AREA)
        s = cv2.GaussianBlur(s, (0, 0), sigma / down)
        return cv2.resize(s, (w, h), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(a, (0, 0), sigma)


def shift(a: np.ndarray, dx: float, dy: float) -> np.ndarray:
    M = np.array([[1, 0, dx], [0, 1, dy]], np.float32)
    return cv2.warpAffine(a, M, (a.shape[1], a.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def find_spot(occ: np.ndarray, bw: float, bh: float, safe, forbid: list, near=None, step: int = 6,
              weight_person: float = 1.0, weight_near: float = 0.15):
    """Best top-left (x, y) for a bw x bh box on the occupancy map `occ` (all in occ's pixels): inside `safe`
    (x0, y0, x1, y1), never touching `forbid` boxes, as little over the person as possible, near `near`."""
    h, w = occ.shape
    ii = cv2.integral(occ.astype(np.float64))
    sx0, sy0, sx1, sy1 = safe
    best, best_cost = None, 1e18
    bw, bh = int(math.ceil(bw)), int(math.ceil(bh))
    for y in range(int(sy0), int(sy1 - bh) + 1, step):
        for x in range(int(sx0), int(sx1 - bw) + 1, step):
            if any(x < f[2] and x + bw > f[0] and y < f[3] and y + bh > f[1] for f in forbid):
                continue
            s = ii[y + bh, x + bw] - ii[y, x + bw] - ii[y + bh, x] + ii[y, x]
            cost = weight_person * s / (bw * bh)
            if near is not None:
                cost += weight_near * math.hypot(x + bw / 2 - near[0], y + bh / 2 - near[1]) / max(h, w)
            if cost < best_cost:
                best, best_cost = (x, y), cost
    return best, best_cost


# ---- fast uint8 compositing (cv2.blendLinear is ~15x faster than float numpy on a 1080x1920 frame) -------------

_SOLID = {}


def solid(shape, colour) -> np.ndarray:
    key = (tuple(shape), tuple(int(v) for v in np.clip(rgb(colour), 0, 255)))
    if key not in _SOLID:
        if len(_SOLID) > 16:
            _SOLID.clear()
        im = np.empty(shape, np.uint8)
        im[:] = key[1]
        _SOLID[key] = im
    return _SOLID[key]


def over8(dst: np.ndarray, src, a: np.ndarray) -> np.ndarray:
    """uint8 dst with src (a colour, or a uint8 image) laid over it at float alpha a (HxW, 0-1)."""
    if not isinstance(src, np.ndarray) or src.ndim == 1:
        src = solid(dst.shape, src)
    a = np.clip(a, 0, 1).astype(np.float32, copy=False)
    return cv2.blendLinear(src, dst, a, 1 - a)


# ---- a cleaner person matte -----------------------------------------------------------------------------------
# MODNet (ctx.person) gives a sharp edge but, on real footage, can keep a chair's back beside the
# shoulders and opens holes in a dark top. MediaPipe's selfie_multiclass knows "person" semantically (hair,
# skin, clothes) but its edge is soft. Together: MODNet's edge, gated by the semantic person (chair out), with the
# semantic body's core filled in (no holes). Cached per window at half size.

def _segmenter():
    import mediapipe as mp
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core.base_options import BaseOptions

    from ..extras import model_path
    seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
        base_options=BaseOptions(model_asset_path=str(model_path("selfie_multiclass"))),
        output_confidence_masks=True, output_category_mask=False))
    return mp, seg


def combine_mattes(modnet: np.ndarray, sem: np.ndarray, W: int, fill_from: int = 0) -> np.ndarray:
    """modnet, sem: float 0-1 mattes at the same (working) size; W the working width. The semantic core fills
    MODNet's holes only below row `fill_from` (the clothes; above the head the semantic mask can smear upward).
    Returns the clean matte."""
    k_in = max(3, int(0.03 * W)) | 1
    inner = cv2.erode((sem > 0.6).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_in, k_in)))
    inner[:max(0, fill_from)] = 0
    inner = cv2.GaussianBlur(inner.astype(np.float32), (0, 0), max(1.0, W / 400))
    k_g = max(3, int(0.008 * W)) | 1
    gate = cv2.dilate((sem > 0.45).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_g, k_g)))
    gate = cv2.GaussianBlur(gate.astype(np.float32), (0, 0), max(1.5, W / 220))
    return np.clip(np.maximum(modnet, inner) * gate, 0, 1)


def clean_mattes(ctx, ema: float = 0.25, q: float = 50) -> np.ndarray:
    """(n, H/2, W/2) uint8: the cleaned person matte of every frame of the window (cached in ctx.work).

    The semantic gate is split by class so it is stable over time: skin, hair and accessories (hands, head,
    glasses) follow the current frame; clothes use their median over the window. Furniture the segmenter calls
    "clothes" in some frames (a chair's back beside the shoulders) is then either always in or always
    out, never flickering."""
    from .. import cutout
    w2, h2 = ctx.W // 2, ctx.H // 2
    path = ctx.work / f"clean-matte-{cutout.MATTE_VERSION}-{cutout.engine()}-{w2}x{h2}.npy"
    if path.exists():
        arr = np.load(path, mmap_mode="r")
        if arr.shape[0] == ctx.n:
            return arr
    if cutout.engine() == "rvm":
        # RVM's matte is already background-gated and hole-filled (cutout.cut_out). A class gate on top of it cut
        # thin ~0.5 seams where hands meet the shirt and clipped the glasses arm, so it is used as is: only seams
        # narrower than ~1% of the width are closed and specks dropped.
        k = max(3, int(0.01 * w2)) | 1
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        out = np.zeros((ctx.n, h2, w2), np.uint8)
        for i, p in enumerate(ctx.frames(ctx.person(), rgba=True)):
            a = cv2.resize(p[..., 3], (w2, h2), interpolation=cv2.INTER_AREA)
            a = np.maximum(a, cv2.morphologyEx(a, cv2.MORPH_CLOSE, ker)).astype(np.float32) / 255
            out[i] = (drop_islands(fill_holes(a), 0.003) * 255).astype(np.uint8)
        tmp = path.with_suffix(".part.npy")
        np.save(tmp, out)
        tmp.replace(path)
        return out
    fb = face_box(ctx)
    fill_from = int((fb[1] + 0.6 * (fb[3] - fb[1])) / 2) if fb else 0
    mp, seg = _segmenter()
    n = ctx.n
    live = np.zeros((n, h2, w2), np.uint8)       # skin + hair + accessories, this frame
    cloth = np.zeros((n, h2 // 2, w2 // 2), np.uint8)  # clothes, quarter size (for the median)
    mod = np.zeros((n, h2, w2), np.uint8)        # MODNet
    prev = None
    for i, (f, p) in enumerate(zip(ctx.frames(), ctx.frames(ctx.person(), rgba=True))):
        small = cv2.resize(f, (w2, h2), interpolation=cv2.INTER_AREA)
        res = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(small)))
        cm = [np.squeeze(m.numpy_view()).astype(np.float32) for m in res.confidence_masks]
        cm = [c if c.shape == (h2, w2) else cv2.resize(c, (w2, h2)) for c in cm]
        lv = np.clip(cm[1] + cm[2] + cm[3] + cm[5], 0, 1)
        lv = lv if prev is None else (1 - ema) * lv + ema * prev
        prev = lv
        live[i] = (lv * 255).astype(np.uint8)
        cloth[i] = (cv2.resize(cm[4], (w2 // 2, h2 // 2), interpolation=cv2.INTER_AREA) * 255).astype(np.uint8)
        mod[i] = cv2.resize(p[..., 3], (w2, h2), interpolation=cv2.INTER_AREA)
    seg.close()
    cl = np.percentile(cloth, q, axis=0).astype(np.float32) / 255
    cl = cv2.resize(cl, (w2, h2), interpolation=cv2.INTER_LINEAR)
    out = np.zeros((n, h2, w2), np.uint8)
    for i in range(n):
        sem = np.maximum(live[i].astype(np.float32) / 255, cl)
        m = combine_mattes(mod[i].astype(np.float32) / 255, sem, w2, fill_from)
        out[i] = (drop_islands(fill_holes(m), 0.003) * 255).astype(np.uint8)
    tmp = path.with_suffix(".part.npy")
    np.save(tmp, out)
    tmp.replace(path)
    return out


def fill_holes(a: np.ndarray) -> np.ndarray:
    """Close holes inside the person (MODNet loses patches of a dark top, often only while a hand is in front of
    it): background not reachable from the top / left / right frame edges is a hole. The bottom edge counts as
    the person, since a talking head is cut by it."""
    b = (a > 0.5).astype(np.uint8)
    h, w = b.shape
    pad = np.zeros((h + 3, w + 2), np.uint8)
    pad[1:h + 1, 1:w + 1] = b
    pad[h + 1:, :] = 1  # the frame bottom belongs to the body
    reach = pad.copy()
    mask = np.zeros((h + 5, w + 4), np.uint8)
    cv2.floodFill(reach, mask, (0, 0), 2)
    holes = (reach[1:h + 1, 1:w + 1] == 0).astype(np.float32)
    if not holes.any():
        return a
    return np.maximum(a, cv2.GaussianBlur(holes, (0, 0), 1.5))


def drop_islands(a: np.ndarray, min_frac: float) -> np.ndarray:
    """The matte without specks: connected parts smaller than min_frac of the frame are removed (they would each
    get a sticker border or an outline of their own)."""
    b = (a > 0.5).astype(np.uint8)
    k, lab, stats, _ = cv2.connectedComponentsWithStats(b, connectivity=8)
    if k <= 2:
        return a
    small = stats[:, cv2.CC_STAT_AREA] < min_frac * a.size
    small[0] = False
    if not small.any():
        return a
    kill = cv2.dilate(small[lab].astype(np.uint8), np.ones((5, 5), np.uint8))
    return a * (1 - kill)


def tighten(a: np.ndarray, lo: float = 0.2, hi: float = 0.8) -> np.ndarray:
    """Crisper matte edge after the half-size upscale (a levels stretch, not a blur)."""
    return np.clip((a - lo) / (hi - lo), 0, 1)


def full_alpha(small: np.ndarray, W: int, H: int) -> np.ndarray:
    """A half-size uint8 matte back at full size, float 0-1."""
    return cv2.resize(np.asarray(small), (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255


def fine_alpha(small: np.ndarray, full: np.ndarray) -> np.ndarray:
    """The clean matte's shape with the cut-out's own full-size edge. `small` (a clean_mattes frame) decides what is
    the person: its closed seams and filled holes are kept, its dropped specks stay dropped. `full` (the person
    clip's alpha, float 0-1) gives the edge: fine and flyaway hair and thin glasses frames, which a half-size matte
    blurs away and tighten() then cuts off."""
    H, W = full.shape
    up = full_alpha(small, W, H)
    k = max(3, int(0.05 * W)) | 1  # the edge may reach 2.5% of the width past the clean shape
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    near = cv2.GaussianBlur(cv2.dilate((up > 0.3).astype(np.uint8), ker).astype(np.float32), (0, 0), k / 4)
    k2 = max(3, int(0.012 * W)) | 1
    return np.maximum(full * near, cv2.erode(up, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k2, k2))))
