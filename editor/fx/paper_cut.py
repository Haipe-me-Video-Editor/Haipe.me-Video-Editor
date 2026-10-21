"""Paper cut: the speaker becomes a cut-out sticker (thick torn white border, soft drop shadow) on a stop-motion
paper collage: textured paper, torn coloured paper, graph-paper scrap, crayon hatching, tape, marker marks, and a
ransom-note word or number from the spec (each character its own scrap of paper) circled in marker. Every collage
element is re-placed every 2-3 frames like hand-shot stop motion. All generated in code."""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .. import fonts
from . import _cutkit as K

NAME = "paper_cut"
DOC = ("Speaker as a torn-paper sticker on a stop-motion paper collage with a ransom-note word/number ('5', "
       "'3-4', 'NEW') and a typed caption strip. For a playful stat or a list item.")
BEST_FOR = ["playful", "product", "any"]
DUR = (1.5, 6)
PARAMS = {
    "text": "",            # ransom-note word or number, up to ~8 characters ("5", "3-4", "100%", "NEW")
    "caption": "",         # small typed strip under it ("BETA TESTERS"); "" for none
    "side": "left",        # where the sticker sits: left / right / center (the collage fills the other side)
    "scale": None,         # sticker size (fraction of the frame); default puts the head top ~42% down
    "paper": "#eee8db",    # base paper colour
    "border": 0.024,       # sticker border, fraction of the width
    "stepped_person": False,  # also step the speaker on twos/threes (full stop motion; lip sync gets choppy)
    "seed": 0,             # a different collage arrangement
    # brand controls (defaults keep the look above)
    "palette": None,       # override any of accent, piece, crayon, mark, dark, ink, tape, grid (hex)
    "fonts": None,         # families for the ransom tiles (default a mix of display faces)
    "caption_font": None,  # family for the caption strip (default IBM Plex Mono)
    "marks": None,         # collage marks to draw, any of hatch, mark_hatch, loops, crosses, asterisk (default all)
    "stickers": [],        # images taped onto the collage: [{file, x, y, w, rot?}] (fractions of the frame, degrees)
}
MARKS = ("hatch", "mark_hatch", "loops", "crosses", "asterisk")

INK = (23, 23, 26)
PAPER_WHITE = (250, 249, 244)


def render(ctx):
    p = {k: ctx.param(k, v) for k, v in PARAMS.items()}
    W, H, n = ctx.W, ctx.H, ctx.n
    seed = int(p["seed"] or 0)
    pal = palette(ctx.style, p["palette"])
    cm = K.clean_mattes(ctx)
    occ = K.occupancy(K.small_mattes(ctx, every=2, scale=4), 50)
    box = K.bbox(occ) or (0.15, 0.1, 0.85, 1.0)
    s = p["scale"] or float(np.clip((1 - 0.42) / max(0.05, 1 - box[1]), 0.5, 0.9))
    side = p["side"] if p["side"] in ("left", "right", "center") else "left"
    M_t = K.place(W, H, box, s, side, bleed=14)

    paper = paper_base(W, H, p["paper"], seed)
    sprites = collage(W, H, pal, seed, side, p["text"], p["caption"], marks=p["marks"], fonts_=p["fonts"],
                      caption_font=p["caption_font"],
                      stickers=[{**st, "path": ctx.asset(st["file"])} for st in (p["stickers"] or [])])
    border_w = p["border"] * W
    edge_noise = (K.noise(H, W, 70, seed + 11) * 0.35 + K.noise(H, W, 10, seed + 12) * 0.18) * border_w

    steps = K.steps_of(n)
    last = steps[-1]
    cache = {"step": None, "bg": None}
    src_hold = None
    with ctx.writer() as write:
        for i, (frame, fa) in enumerate(zip(ctx.frames(), ctx.mattes())):
            st = steps[i]
            e = last - st  # steps before the end
            if st == 0 or (e == 0 and last >= 6):
                write(frame)  # in and out on the real picture: the cut lands on a real frame
                continue
            if p["stepped_person"]:
                if i == 0 or steps[i - 1] != st:
                    src_hold = (frame, K.fine_alpha(cm[i], fa))
                frame_use, a_full = src_hold
            else:
                frame_use, a_full = frame, K.fine_alpha(cm[i], fa)
            # sticker size: in from full frame over 3 steps with a small overshoot, out the same way
            k = {1: 0.0, 2: 0.62, 3: 1.06}.get(st, 1.0)
            if last >= 6 and e == 1:
                k = min(k, 0.5)
            M = K.lerp_m(K.IDENTITY, M_t, k)
            rng = np.random.default_rng(st * 977 + seed)
            M = M.copy()
            M[:, 2] += rng.uniform(-2.2, 2.2, 2)
            # the collage for this step (re-placed every step: stop motion)
            if cache["step"] != st:
                visible = [sp for sp in sprites if sp["at"] <= st and not (last >= 6 and e <= sp.get("gone", 0))]
                cache["bg"] = compose(paper, visible, st, seed, W, H)
                cache["step"] = st
            out = sticker(cache["bg"], frame_use, K.tighten(a_full), M, border_w, edge_noise,
                          W, H)
            write(out)
    return ctx.out


# ---- palette --------------------------------------------------------------------------------------------------

def palette(style: dict, override: dict | None = None) -> dict:
    acc = K.rgb(style.get("accent", "#ff7a1a"))
    bg = K.rgb(style.get("bg", "#0b0b0d"))
    mark = K.rgb(style.get("live") or style.get("down") or "#e5484d")
    if np.abs(mark - acc).sum() < 90:  # the marks need to differ from the accent
        mark = K.rgb("#e5484d")
    pal = {
        "accent": acc,
        "piece": K.mix(acc, "#ffffff", 0.12),
        "crayon": K.mix(acc, bg, 0.42),
        "mark": mark,
        "dark": K.mix(bg, "#000000", 0.2) if K.luma(bg) > 40 else bg,
        "ink": np.array(INK, np.float32),
        "tape": np.array((240, 232, 210), np.float32),
        "grid": np.array((150, 178, 214), np.float32),
    }
    for k, v in (override or {}).items():
        if k in pal:
            pal[k] = K.rgb(v)
    return pal


# ---- paper and collage pieces -------------------------------------------------------------------------------

def paper_base(W, H, colour, seed) -> np.ndarray:
    base = K.rgb(colour)
    g = K.grain(H, W, seed + 1, 0.022)
    mott = 1 + 0.035 * K.noise(H, W, 220, seed + 2, octaves=2)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vig = 1 - 0.07 * (((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2) * 2.2
    img = base[None, None, :] * (g * mott * vig)[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


def torn_poly(pts, seed, rough: float, step: float = 7.0) -> np.ndarray:
    """A polygon whose edges look torn: densified and pushed in/out by fractal noise along the edge."""
    rng = np.random.default_rng(seed)
    P = np.asarray(pts, np.float32)
    out = []
    for a, b in zip(P, np.vstack([P[1:], P[:1]])):
        L = float(np.linalg.norm(b - a))
        m = max(2, int(L / step))
        t = np.linspace(0, 1, m, endpoint=False)[:, None]
        seg = a + (b - a) * t
        nrm = np.array([-(b - a)[1], (b - a)[0]], np.float32) / max(L, 1e-6)
        x = np.arange(m, dtype=np.float32)
        d = np.zeros(m, np.float32)
        for k, amp in ((0.05, 1.0), (0.17, 0.5), (0.55, 0.3)):
            d += amp * np.sin(x * k * (1 + rng.uniform(-0.3, 0.3)) + rng.uniform(0, 6.28))
        d += rng.normal(0, 0.35, m)
        out.append(seg + nrm * (d * rough)[:, None])
    return np.vstack(out)


def _fill(mask, poly):
    cv2.fillPoly(mask, [np.round(poly * 16).astype(np.int32)], 255, cv2.LINE_AA, shift=4)
    return mask


def _canvas(W, H):
    return np.zeros((H, W, 3), np.float32), np.zeros((H, W), np.float32)


def _sprite(rgbf, a, at, gone=0, ident=0, pad=10):
    ys, xs = np.where(a > 0.004)
    if len(xs) == 0:
        return None
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(a.shape[1], xs.max() + pad + 1), min(a.shape[0], ys.max() + pad + 1)
    rgba = np.dstack([np.clip(rgbf[y0:y1, x0:x1], 0, 255), np.clip(a[y0:y1, x0:x1] * 255, 0, 255)]).astype(np.uint8)
    return {"rgba": rgba, "x": int(x0), "y": int(y0), "at": at, "gone": gone, "id": ident}


def torn_piece(W, H, rect, colour, seed, rim=True, texture=None):
    """A torn scrap of coloured paper with the white fibrous core showing along the tear."""
    x0, y0, x1, y1 = rect
    rng = np.random.default_rng(seed)
    pts = [(x0 + rng.uniform(-.03, .03) * W, y0), (x1, y0 + rng.uniform(-.02, .02) * H),
           (x1 + rng.uniform(-.02, .02) * W, y1), (x0, y1 + rng.uniform(-.02, .02) * H)]
    rgbf, a = _canvas(W, H)
    if rim:
        m = _fill(np.zeros((H, W), np.uint8), torn_poly(pts, seed, 7.5)).astype(np.float32) / 255
        rgbf = K.over(rgbf, PAPER_WHITE, m)
        a = np.maximum(a, m)
    inner = np.asarray(pts, np.float32)
    c = inner.mean(0)
    inner = c + (inner - c) * 0.985
    m2 = _fill(np.zeros((H, W), np.uint8), torn_poly(inner, seed + 1, 6.0)).astype(np.float32) / 255
    col = np.asarray(colour, np.float32)[None, None, :] * K.grain(H, W, seed + 3, 0.03)[..., None]
    if texture is not None:
        col = col * texture[..., None]
    rgbf = K.over(rgbf, col, m2)
    return rgbf, np.maximum(a, m2)


def graph_scrap(W, H, rect, seed, line=(150, 178, 214)):
    rgbf, a = torn_piece(W, H, rect, (248, 248, 244), seed, rim=False)
    yy, xx = np.mgrid[0:H, 0:W]
    cell = int(W * 0.026)
    grid = ((xx % cell) < 2) | ((yy % cell) < 2)
    blue = np.asarray(line, np.float32)
    rgbf = np.where((grid & (a > 0.5))[..., None], rgbf * 0.55 + blue * 0.45, rgbf)
    return rgbf, a


def crayon(W, H, strokes, colour, width, seed, alpha=0.92):
    m = K.draw(np.zeros((H, W), np.uint8), strokes, width).astype(np.float32) / 255
    g = K.noise(H, W, 2.2, seed + 5)
    wax = np.clip(0.75 + 0.9 * g, 0, 1)  # waxy gaps where the paper tooth shows through
    a = m * wax * alpha
    rgbf = np.zeros((H, W, 3), np.float32) + np.asarray(colour, np.float32)
    return rgbf, a


def marker(W, H, strokes, colour, width):
    m = K.draw(np.zeros((H, W), np.uint8), strokes, width).astype(np.float32) / 255
    return np.zeros((H, W, 3), np.float32) + np.asarray(colour, np.float32), m * 0.95


def tape(W, H, centre, length, angle, seed, colour=(240, 232, 210)):
    """A strip of semi-clear masking tape with zig-zag torn ends."""
    rng = np.random.default_rng(seed)
    w = length * 0.3
    pts = []
    for sgn in (-1, 1):
        x = sgn * length / 2
        ys = np.linspace(-w / 2, w / 2, 7) if sgn > 0 else np.linspace(w / 2, -w / 2, 7)
        for k, y in enumerate(ys):
            pts.append((x + sgn * (k % 2) * w * 0.12 * rng.uniform(0.5, 1.2), y))
    P = np.asarray(pts, np.float32)
    c, s = math.cos(angle), math.sin(angle)
    P = P @ np.array([[c, s], [-s, c]], np.float32) + np.asarray(centre, np.float32)
    m = _fill(np.zeros((H, W), np.uint8), P).astype(np.float32) / 255
    col = np.asarray(colour, np.float32)[None, None, :] * K.grain(H, W, seed, 0.04)[..., None]
    return col + np.zeros((H, W, 3), np.float32), m * 0.62


def ransom(W, H, text, x, y, max_w, th, pal, seed, fams=None):
    """Each character on its own scrap of paper, mixed fonts and colours, slightly rotated. Returns sprites
    (one per tile, so they can arrive one per step) and the block's box."""
    fams = list(fams or ["Anton", "Montserrat", "Bebas Neue", "IBM Plex Mono", "Sora", "Orbitron"])
    acc = pal["accent"]
    acc_ink = np.array(INK, np.float32) if K.luma(acc) > 120 else np.array(PAPER_WHITE, np.float32)
    combos = [(pal["dark"], PAPER_WHITE), (PAPER_WHITE, INK), (acc, acc_ink), (pal["mark"], PAPER_WHITE),
              (INK, acc), ((246, 240, 226), pal["mark"])]
    chars = [text] if K.has_arabic(text) else [c for c in text.strip()]
    if K.has_arabic(text):
        fams = ["Lalezar"]
    rng = np.random.default_rng(seed + 40)
    tiles = []
    for j, ch in enumerate(chars):
        if ch == " ":
            tiles.append(None)
            continue
        fam = fams[(j + seed) % len(fams)]
        font = ImageFont.truetype(str(fonts.ensure_font(fam)), int(th * (0.78 if fam not in ("Anton", "Bebas Neue")
                                                                            else 0.92)))
        bg, fg = combos[(j + seed) % len(combos)]
        bb = font.getbbox(ch)
        gw, gh = bb[2] - bb[0], bb[3] - bb[1]
        tw = int(max(gw + th * 0.32, th * 0.62))
        img = Image.new("RGBA", (tw + 40, int(th) + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        jit = [(rng.uniform(-1, 1) * th * 0.04) for _ in range(8)]
        poly = [(20 + jit[0], 20 + jit[1]), (20 + tw + jit[2], 20 + jit[3]), (20 + tw + jit[4], 20 + th + jit[5]),
                (20 + jit[6], 20 + th + jit[7])]
        d.polygon(poly, fill=tuple(int(v) for v in np.asarray(bg)) + (255,))
        d.text((20 + (tw - gw) / 2 - bb[0], 20 + (th - gh) / 2 - bb[1]), ch, font=font,
               fill=tuple(int(v) for v in np.asarray(fg)) + (255,), direction="rtl" if K.has_arabic(ch) else None)
        img = img.rotate(rng.uniform(-7, 7), resample=Image.BICUBIC, expand=True)
        tiles.append(np.asarray(img))
    gap = th * 0.06
    widths = [t.shape[1] - 30 if t is not None else th * 0.35 for t in tiles]
    total = sum(widths) + gap * (len(widths) - 1)
    k = min(1.0, max_w / max(total, 1))
    sprites, cx = [], x
    top = y
    for j, t in enumerate(tiles):
        if t is None:
            cx += widths[j] * k + gap * k
            continue
        if k < 1:
            t = cv2.resize(t, (int(t.shape[1] * k), int(t.shape[0] * k)), interpolation=cv2.INTER_AREA)
        dy = rng.uniform(-0.06, 0.06) * th * k
        rgba = _drop_shadow(t)
        sprites.append({"rgba": rgba, "x": int(cx - 15 * k), "y": int(top - 15 * k + dy), "id": 100 + j})
        cx += widths[j] * k + gap * k
    return sprites, (x, top, cx, top + th * k)


def _drop_shadow(rgba, off=(5, 7), blur=5, op=0.35):
    """Paper lifted off the page: a soft shadow under an RGBA sprite (returned with a margin)."""
    h, w = rgba.shape[:2]
    pad = 16
    out = np.zeros((h + pad * 2, w + pad * 2, 4), np.float32)
    a = rgba[..., 3].astype(np.float32) / 255
    sh = np.zeros(out.shape[:2], np.float32)
    sh[pad + off[1]:pad + off[1] + h, pad + off[0]:pad + off[0] + w] = a
    sh = cv2.GaussianBlur(sh, (0, 0), blur) * op
    out[..., 3] = sh
    a_full = np.zeros(out.shape[:2], np.float32)
    a_full[pad:pad + h, pad:pad + w] = a
    col = np.zeros((h + pad * 2, w + pad * 2, 3), np.float32)
    col[pad:pad + h, pad:pad + w] = rgba[..., :3]
    oa = a_full + sh * (1 - a_full)
    rgb = col * (a_full / np.maximum(oa, 1e-6))[..., None]
    return np.dstack([rgb, oa * 255]).clip(0, 255).astype(np.uint8)


def caption_strip(W, H, text, x, y, pal, seed, max_w, family=None):
    """A label-maker strip: dark tape, small spaced capitals in mono."""
    size = int(H * 0.025)
    font = ImageFont.truetype(str(fonts.ensure_font(family or "IBM Plex Mono")), size)
    txt = text.upper() if not K.has_arabic(text) else text
    if K.has_arabic(text):
        font = ImageFont.truetype(str(fonts.ensure_font("IBM Plex Sans Arabic")), size)
    spaced = txt if K.has_arabic(text) else " ".join(txt.split()).replace(" ", "  ")
    bb = font.getbbox(spaced)
    while bb[2] - bb[0] > max_w - size * 1.6 and size > 12:
        size -= 2
        font = ImageFont.truetype(font.path, size)
        bb = font.getbbox(spaced)
    tw, th = int(bb[2] - bb[0] + size * 1.5), int(size * 1.9)
    img = Image.new("RGBA", (tw + 30, th + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([15, 15, 15 + tw, 15 + th], fill=tuple(int(v) for v in pal["dark"]) + (255,))
    d.text((15 + size * 0.75 - bb[0], 15 + (th - (bb[3] - bb[1])) / 2 - bb[1]), spaced, font=font,
           fill=PAPER_WHITE + (255,), direction="rtl" if K.has_arabic(text) else None)
    img = img.rotate(np.random.default_rng(seed + 9).uniform(-2.5, -1), resample=Image.BICUBIC, expand=True)
    rgba = _drop_shadow(np.asarray(img), off=(3, 5), blur=4, op=0.3)
    return {"rgba": rgba, "x": int(x - 30), "y": int(y - 30), "id": 300}, (x, y, x + tw, y + th)


def collage(W, H, pal, seed, side, text, caption, marks=None, fonts_=None, caption_font=None, stickers=()) -> list:
    """Every collage element as a sprite with the step it arrives on (and how many steps before the end it
    leaves). Laid out for a sticker on the left; mirrored for one on the right."""
    rng = np.random.default_rng(seed + 100)
    els = []
    marks = set(MARKS if marks is None else marks)

    def add(rgbf_a, at, gone, ident):
        sp = _sprite(*rgbf_a, at=at, gone=gone, ident=ident)
        if sp:
            els.append(sp)

    j = lambda v: v * (1 + rng.uniform(-0.05, 0.05))
    # graph-paper scrap low right, the coloured torn piece over it, crayon block top
    add(graph_scrap(W, H, (j(0.5) * W, j(0.66) * H, 1.06 * W, 1.03 * H), seed + 1, pal["grid"]), 1, 2, 1)
    add(torn_piece(W, H, (j(0.47) * W, j(0.43) * H, 1.05 * W, j(0.67) * H), pal["piece"], seed + 2), 2, 2, 2)
    zz = K.zigzag(0.56 * W, 0.16 * H, 12, seed=seed + 3, slant=0.18)
    zz = [s + np.array([0.3 * W, 0.135 * H], np.float32) for s in zz]
    add(crayon(W, H, K.wobble(zz, 6, seed + 3), pal["crayon"], W * 0.024, seed + 3, 0.7), 2, 2, 3)
    # ink hatching on the coloured piece, a red hatch, loops, crosses
    hz = [s + np.array([0.58 * W, 0.47 * H], np.float32) for s in K.zigzag(0.27 * W, 0.12 * H, 11, seed + 4, 0.1)]
    if "hatch" in marks:
        add(crayon(W, H, K.wobble(hz, 3, seed + 4), pal["ink"], W * 0.008, seed + 4, 0.9), 3, 2, 4)
    rz = [s + np.array([0.7 * W, 0.71 * H], np.float32) for s in K.zigzag(0.12 * W, 0.06 * H, 8, seed + 5, 0.1)]
    if "mark_hatch" in marks:
        add(crayon(W, H, K.wobble(rz, 3, seed + 5), pal["mark"], W * 0.009, seed + 5, 0.95), 3, 2, 5)
    lp = [s + np.array([0.64 * W, 0.83 * H], np.float32) for s in K.loops(0.2 * W, 0.024 * H, 5)]
    if "loops" in marks:
        add(marker(W, H, K.wobble(lp, 2, seed + 6), pal["ink"], W * 0.005), 4, 2, 6)
    for k, (cx, cy) in enumerate(((0.79 * W, 0.62 * H), (0.84 * W, 0.6 * H))):
        if "crosses" in marks:
            add(marker(W, H, K.transform(K.cross(W * 0.014), 1, rng.uniform(-.3, .3), at=(cx, cy)), pal["ink"],
                       W * 0.0055), 4, 2, 7 + k)
    if "asterisk" in marks:
        add(marker(W, H, K.transform(K.asterisk(W * 0.016), 1, 0.2, at=(0.86 * W, 0.4 * H)), pal["ink"],
                   W * 0.005), 4, 2, 9)
    add(tape(W, H, (0.52 * W, 0.45 * H), W * 0.17, math.radians(-38), seed + 7, pal["tape"]), 3, 2, 10)
    add(tape(W, H, (0.95 * W, 0.68 * H), W * 0.15, math.radians(30), seed + 8, pal["tape"]), 3, 2, 11)
    for k, st in enumerate(stickers):  # image stickers (a character, a product shot) taped onto the collage
        sp, (cx, cy, top) = image_sticker(W, H, st, seed + 20 + k)
        sp.update(at=4, gone=2, id=40 + k)
        els.append(sp)
        add(tape(W, H, (cx, top), W * 0.12, math.radians(st.get("rot", 0) - 8), seed + 30 + k, pal["tape"]),
            4, 2, 50 + k)

    # the ransom word and the caption strip, top left
    tx, ty = 0.07 * W, 0.15 * H
    block = None
    if text and text.strip():
        nch = len(text.strip())
        th = (0.105 if nch <= 4 else 0.09 if nch <= 6 else 0.075) * H
        tiles, block = ransom(W, H, text, tx, ty, 0.72 * W, th, pal, seed, fonts_)
        for k_, sp in enumerate(tiles):
            sp.update(at=5 + k_, gone=3)
            els.append(sp)
        first = 5 + len(tiles)
        bx0, by0, bx1, by1 = block
        loop = K.ellipse_loop((bx1 - bx0) * 0.6, (by1 - by0) * 0.78, turns=1.08, seed=seed)
        loop = [s + np.array([(bx0 + bx1) / 2, (by0 + by1) / 2], np.float32) for s in loop]
        for q in range(4):  # the marker loop draws on over 4 steps
            add(marker(W, H, K.wobble(K.reveal(loop, (q + 1) / 4), 2, seed), pal["mark"], W * 0.006), first + q,
                3, 200 + q)
            els[-1]["only"] = q < 3  # each partial loop shows for one step only
        ty = by1 + 0.022 * H
    else:
        first = 5
    if caption and caption.strip():
        sp, _ = caption_strip(W, H, caption, tx + 0.01 * W, ty, pal, seed, 0.74 * W, caption_font)
        sp.update(at=first + (4 if block else 0), gone=3)
        els.append(sp)
        els.append(_sprite(*tape(W, H, (tx + 0.005 * W, ty + 0.018 * H), W * 0.09, math.radians(-70), seed + 9,
                                 pal["tape"]),
                           at=sp["at"], gone=3, ident=301))
    if side == "right":
        for sp in els:
            sp["x"] = W - sp["x"] - sp["rgba"].shape[1] if sp["id"] < 100 else sp["x"]
    # each partial marker loop shows only on its own step
    out = []
    for sp in els:
        if sp.get("only"):
            sp["until"] = sp["at"]
        out.append(sp)
    return out


def image_sticker(W, H, st, seed):
    """An RGBA image (a character pose, a product cut-out) as a die-cut paper sticker: a white border that follows its
    outline, a lifted shadow, a slight turn. Returns the sprite and where its tape goes (centre x, y and top)."""
    img = Image.open(st["path"]).convert("RGBA")
    w = int(st.get("w", 0.3) * W)
    img = img.resize((w, max(1, int(img.height * w / img.width))), Image.LANCZOS)
    a = np.asarray(img)[..., 3].astype(np.float32) / 255
    pad = int(W * 0.03)
    a = np.pad(a, pad)
    rgb = np.pad(np.asarray(img)[..., :3].astype(np.float32), ((pad, pad), (pad, pad), (0, 0)))
    inside = (a > 0.5).astype(np.uint8)
    dist = cv2.distanceTransform(1 - inside, cv2.DIST_L2, 5)
    border = np.clip(W * 0.012 - dist, 0, 1)
    border = np.maximum(border, a)
    out = np.zeros(rgb.shape, np.float32) + np.asarray(PAPER_WHITE, np.float32)
    out = K.over(out, rgb, a)
    rgba = np.dstack([out, border * 255]).clip(0, 255).astype(np.uint8)
    rot = st.get("rot", 0) + np.random.default_rng(seed).uniform(-1.5, 1.5)
    pil = Image.fromarray(rgba).rotate(rot, resample=Image.BICUBIC, expand=True)
    rgba = _drop_shadow(np.asarray(pil), off=(6, 9), blur=7, op=0.32)
    h, ww = rgba.shape[:2]
    cx, cy = st.get("x", 0.75) * W, st.get("y", 0.3) * H
    x0, y0 = int(cx - ww / 2), int(cy - h / 2)
    return {"rgba": rgba, "x": x0, "y": y0}, (cx, cy, y0 + pad * 1.6)


def compose(paper, sprites, step, seed, W, H) -> np.ndarray:
    """The collage for one stop-motion step: every element nudged a little (re-placed by hand)."""
    img = paper.copy()
    for sp in sprites:
        if "until" in sp and step > sp["until"]:
            continue
        rng = np.random.default_rng(step * 131 + sp["id"] * 7 + seed)
        rgba = sp["rgba"]
        h, w = rgba.shape[:2]
        ang = rng.uniform(-0.8, 0.8)
        dx, dy = rng.uniform(-2.5, 2.5, 2)
        Mr = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        rgba = cv2.warpAffine(rgba, Mr, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
        x, y = int(round(sp["x"] + dx)), int(round(sp["y"] + dy))
        xa, ya, xb, yb = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
        if xb <= xa or yb <= ya:
            continue
        sub = rgba[ya - y:yb - y, xa - x:xb - x]
        img[ya:yb, xa:xb] = K.over8(img[ya:yb, xa:xb], np.ascontiguousarray(sub[..., :3]),
                                    sub[..., 3].astype(np.float32) / 255)
    return img


def sticker(bg, frame, A, M, border_w, edge_noise, W, H) -> np.ndarray:
    """The speaker as a cut-out sticker (torn white border, lifted shadow) over the collage."""
    rgb = K.decontaminate(frame, A).astype(np.uint8)
    pr = K.warp(rgb, M, W, H)
    a = K.warp(A, M, W, H)
    inside = (a > 0.5).astype(np.uint8)
    dist = cv2.distanceTransform(1 - inside, cv2.DIST_L2, 5)
    border = np.clip(border_w + edge_noise - dist, 0, 1.0)
    border = np.maximum(border, a)
    # the shadow: a soft lift plus a tight contact edge
    soft = K.shift(K.blur(border, W * 0.014, down=4), W * 0.008, W * 0.013)
    tight = K.shift(K.blur(border, 2.5, down=1), 2, 3)
    out = K.over8(bg, (40, 30, 22), np.clip(soft * 0.34 + tight * 0.18, 0, 0.5))
    out = K.over8(out, PAPER_WHITE, border)
    # a hint of paper grey just inside the border edge, so the white reads as thick card
    out = K.over8(out, pr, a)
    return out
