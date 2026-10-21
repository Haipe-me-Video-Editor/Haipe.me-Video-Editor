"""Glass type: huge 3D frosted-glass letters mounted on the wall behind the speaker, head in front.

Built in numpy on the real frame, so the glass shows the room through it: every letter is a bevelled slab whose
face refracts a frosted copy of the wall behind it (offset along the bevel normals), with a specular bevel lit
from the top left, a bright inner rim, side walls extruded toward the frame centre (the depth you see on a sign
seen from the speaker's camera), a soft shadow cast on the wall and a light sheen that sweeps across once the
word has assembled. The letters fly in from scattered positions and spring into place; the person is composited
back on top. Placement comes from the shared solver (_behind.solve): above the head when the wall shows there,
otherwise big beside the head, turned to read up the side.
"""
import math
import random

import cv2
import numpy as np

from . import _behind as B

NAME = "glass_type"
DOC = ("Huge 3D frosted-glass letters on the wall behind the speaker (head in front), refracting the room, "
       "assembling with a spring. For one bold word: a launch, a product name, a theme.")
BEST_FOR = ["product", "finance", "corporate", "any"]
DUR = (2.0, 8)
PARAMS = {
    "text": "",          # 1-2 words (\\N for a line break)
    "hi": [],            # words in tinted glass (the style accent)
    "font": "auto",      # auto (the style font, or Anton when the word must stand on its side), or any fx family
    "place": "auto",     # auto | above | side
    "size": None,        # largest font size as a fraction of the width (default 0.32)
    "tint": None,        # glass tint colour (default the style ink; hi words take the accent)
    "depth": 0.11,       # extrusion depth, fraction of the font size
    "tilt": 0.10,        # perspective: how much the far end shrinks (0 = flat on to the camera)
    "frost": 1.0,        # 0 clear glass .. 1.5 heavy frost
}

ENTER, STAGGER, EXIT = 0.75, 0.065, 0.35
LIGHT = np.array([-0.45, -0.75, 0.55], np.float32) / np.linalg.norm([-0.45, -0.75, 0.55])


def letter_maps(alpha: np.ndarray, em: float) -> np.ndarray:
    """(h, w, 4) float32 maps of one glyph: alpha, bevel normal x, normal y, bevel height (0 edge .. 1 face)."""
    m = (alpha > 0.5).astype(np.uint8)
    bevel = max(em * 0.05, 2.0)
    dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    h = np.clip(dist / bevel, 0, 1)
    h = h * h * (3 - 2 * h)
    h = cv2.GaussianBlur(h, (0, 0), max(bevel * 0.22, 0.8))
    gy, gx = np.gradient(h)
    nx, ny = -gx * bevel * 0.9, -gy * bevel * 0.9
    return np.dstack([alpha, nx * alpha, ny * alpha, h]).astype(np.float32)


def scatter(n: int, em: float, seed: str):
    """Deterministic start offsets for the assembly: (dx, dy, rotation, scale) per letter."""
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        ang = rnd.uniform(-math.pi, math.pi)
        r = em * rnd.uniform(0.45, 0.9)
        out.append((math.cos(ang) * r, math.sin(ang) * r - em * 0.35, rnd.uniform(-22, 22), rnd.uniform(1.25, 1.5)))
    return out


def homography(w: int, h: int, far: str, tilt: float) -> np.ndarray:
    """Keystone the canvas so the `far` edge (left/right/top/bottom) shrinks by `tilt` about its midpoint."""
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = src.copy()
    if tilt > 0:
        if far in ("left", "right"):
            i, j = (0, 3) if far == "left" else (1, 2)
            dst[i, 1] += h * tilt / 2
            dst[j, 1] -= h * tilt / 2
            dst[[i, j], 0] += (w * tilt * 0.35) * (1 if far == "left" else -1)
        else:
            i, j = (0, 1) if far == "top" else (3, 2)
            dst[i, 0] += w * tilt / 2
            dst[j, 0] -= w * tilt / 2
            dst[[i, j], 1] += (h * tilt * 0.35) * (1 if far == "top" else -1)
    return cv2.getPerspectiveTransform(src, dst)


def render(ctx):
    text = (ctx.param("text") or "").strip()
    if not text:
        raise ValueError("glass_type needs text")
    B.prime(ctx)
    occ = B.occupancy(ctx)
    face = ctx.face()
    B.publish(ctx)
    head = B.head_box(occ, face, ctx.W, ctx.H)
    occ = B.occupancy_for_text(ctx, head, 85)  # slabs may tuck behind the head as it sways: go bigger
    W, H = ctx.W, ctx.H
    fam = ctx.param("font", PARAMS["font"])
    if B.is_arabic(text):
        fams = [fam if fam in ("BrandAR", "Lalezar", "Tajawal", "PlexArabic") else "Lalezar"]
    else:
        fams = ["BrandLT", "Anton"] if fam == "auto" else [fam]
    place = ctx.param("place", "auto")
    size = ctx.param("size") or 0.32
    depth = float(ctx.param("depth", PARAMS["depth"]))
    blocks, weights = [], []
    for fi, f in enumerate(fams):
        for li, ls in enumerate(B.split_lines(text)):
            blocks.append(B.Block(ls, B.font_file(ctx, f), leading=0.98, tracking=0.02 if f != "Anton" else 0.03))
            weights.append((1.0 if fi == 0 else 0.9) * (1.0 if li == 0 else 0.95))
    blocked = B.blocked_grid(occ, W, H, margin_cells=1, safe=(B.SAFE[0], B.SAFE[1], B.SAFE[2] - depth * 0.15,
                                                               B.SAFE[3]))
    anchor = (head["cx"], head["top"] + (head["eye_y"] - head["top"]) * 0.5)
    L = B.solve(blocked, blocks, anchor, (0.06 * W, size * W), allow_rotate=place != "above" and not B.is_arabic(text),
                rotate_penalty=0.75 if place == "auto" else 10.0, weights=weights, max_letter=0.32, max_total=0.13)
    if L is None:  # nothing readable fits: centre it just above the face and let the head cover what it covers
        blk = blocks[-1]
        s = min(size * W, (B.SAFE[2] - B.SAFE[0]) * W / blk.size[0] * blk.em) / blk.em
        L = {"block": blk, "em": blk.em * s, "scale": s, "rotate": 0,
             "x": int((B.SAFE[0] + B.SAFE[2]) / 2 * W - blk.size[0] * s / 2),
             "y": int(max(B.SAFE[1] * H, head["top"] - blk.size[1] * s * 0.6))}
    blk, s, rot, em = L["block"], L["scale"], L["rotate"], L["em"]
    sprites = blk.word_sprites(s, rot)
    # split words into letters (connected components, kept in reading order) so each one assembles on its own
    letters = []
    for sp in sprites:
        a = sp["alpha"]
        n, lab = cv2.connectedComponents(cv2.dilate((a > 0.3).astype(np.uint8),
                                                    np.ones((max(3, int(em * 0.06)) | 1,) * 2, np.uint8)))
        parts = []
        for k in range(1, n):
            ys, xs = np.where(lab == k)
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            piece = a[y0:y1, x0:x1] * (lab[y0:y1, x0:x1] == k)
            parts.append((x0 if rot == 0 else (-y0 if rot == 1 else y0), piece, sp["x"] + x0, sp["y"] + y0))
        parts.sort(key=lambda p: p[0])
        for _, piece, x, y in parts:
            letters.append({"word": sp["word"], "alpha": piece, "x": x, "y": y})
    pad = int(em * 0.25)
    for lt in letters:
        lt["maps"] = letter_maps(np.pad(lt["alpha"], pad), em)
        lt["x"] -= pad
        lt["y"] -= pad
    starts = scatter(len(letters), em, text)
    hi = {w.lower().strip(".,!?") for w in ctx.param("hi", [])}
    tint_main = (B.hex_rgb(ctx.param("tint")) if ctx.param("tint") else  # ink, a breath of the brand accent
                 B.hex_rgb(ctx.style.get("ink", "#ffffff")) * 0.8 + B.hex_rgb(ctx.style.get("accent", "#ffffff")) * 0.2)
    tint_hi = B.hex_rgb(ctx.style.get("accent", "#ff7a1a"))
    frost = float(ctx.param("frost", PARAMS["frost"]))

    # canvas: the block plus room for the flight in, the extrusion and the shadow
    bw = blk.size[0] * s if not rot else blk.size[1] * s
    bh = blk.size[1] * s if not rot else blk.size[0] * s
    margin = int(em * 1.0)
    cx0, cy0 = max(int(L["x"]) - margin, 0), max(int(L["y"]) - margin, 0)
    cx1, cy1 = min(int(L["x"] + bw) + margin, W), min(int(L["y"] + bh) + margin, H)
    cw, ch = cx1 - cx0, cy1 - cy0
    bcx, bcy = L["x"] + bw / 2, L["y"] + bh / 2
    vp = np.array([W * 0.5, H * 0.42])
    dvec = vp - np.array([bcx, bcy])
    dvec = dvec / (np.linalg.norm(dvec) + 1e-6) * em * depth
    if rot == 0:
        far = "left" if bcx < W * 0.5 else "right"
    else:
        far = "top"
    Hm = homography(cw, ch, far, float(ctx.param("tilt", PARAMS["tilt"])))
    # light sheen direction
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    u = ((xx - (L["x"] - cx0)) * 0.8 + (yy - (L["y"] - cy0)) * 0.6) / max(bw * 0.8 + bh * 0.6, 1)
    vert = (yy - (L["y"] - cy0)) / max(bh, 1)
    sheen_t0 = 0.1 + STAGGER * len(letters) + ENTER * 0.7
    enter = B.spring("bouncy")
    K = max(6, int(np.linalg.norm(dvec) / 2))

    with ctx.writer() as write:
        for i, (frame, m) in enumerate(zip(ctx.frames(), B.person_alpha(ctx))):
            t = i / ctx.fps
            tout = B.ease_in(B.progress(t, ctx.dur - EXIT, EXIT))
            maps = np.zeros((ch, cw, 4), np.float32)
            tint = np.zeros((ch, cw, 3), np.float32)
            for k, lt in enumerate(letters):
                tk = t - 0.08 - STAGGER * k
                if tk <= 0:
                    continue
                p = enter(min(tk / ENTER, 1.0))
                fade = B.ease_out(tk / (ENTER * 0.45)) * (1 - tout)
                if fade <= 0.003:
                    continue
                sx, sy, sr, ss = starts[k]
                q = 1 - p
                a, ox, oy = B.warp_sprite(lt["maps"], sx * q, sy * q, 1 + (ss - 1) * q - 0.04 * tout, sr * q)
                a = a.copy()
                a[..., 0] *= fade
                X, Y = int(L["x"] + lt["x"] + ox - cx0), int(L["y"] + lt["y"] + oy - cy0)
                h_, w_ = a.shape[:2]
                xa, ya, xb, yb = max(X, 0), max(Y, 0), min(X + w_, cw), min(Y + h_, ch)
                if xb <= xa or yb <= ya:
                    continue
                src = a[ya - Y:yb - Y, xa - X:xb - X]
                dst = maps[ya:yb, xa:xb]
                al = src[..., :1]
                dst[..., 1:] = dst[..., 1:] * (1 - al) + src[..., 1:] * (al > 0)
                dst[..., 0:1] = dst[..., 0:1] + al * (1 - dst[..., 0:1])
                col = tint_hi if lt["word"].lower().strip(".,!?") in hi else tint_main
                tint[ya:yb, xa:xb] = tint[ya:yb, xa:xb] * (1 - al) + col * al
            out = frame.astype(np.float32) / 255
            A = maps[..., 0]
            if A.max() > 0.003:
                reg = out[cy0:cy1, cx0:cx1]
                bg = reg.copy()
                layer, alpha, shadow = shade(bg, maps, tint, dvec, K, em, frost, u, vert, t, sheen_t0)
                # perspective, then shadow on the wall, the glass, and the person back on top
                layer = cv2.warpPerspective(layer, Hm, (cw, ch), flags=cv2.INTER_LINEAR)
                alpha = cv2.warpPerspective(alpha, Hm, (cw, ch), flags=cv2.INTER_LINEAR)
                shadow = cv2.warpPerspective(shadow, Hm, (cw, ch), flags=cv2.INTER_LINEAR)
                reg *= 1 - shadow[..., None]
                reg[:] = reg * (1 - alpha[..., None]) + layer * alpha[..., None]
                mm = m[cy0:cy1, cx0:cx1, None]
                reg[:] = reg * (1 - mm) + bg * mm
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out


def shade(bg, maps, tint, dvec, K, em, frost, u, vert, t, sheen_t0):
    """The glass layer (colour, alpha) and its wall shadow for one frame, from the composited letter maps."""
    ch, cw = bg.shape[:2]
    A, NX, NY, Hh = maps[..., 0], maps[..., 1], maps[..., 2], maps[..., 3]
    # extrusion: copies of the face pushed toward the vanishing point; T = how deep (0 front .. 1 back)
    S = np.zeros_like(A)
    T = np.zeros_like(A)
    for k in range(K, 0, -1):
        f = k / K
        M = np.float32([[1, 0, dvec[0] * f], [0, 1, dvec[1] * f]])
        sk = cv2.warpAffine(A, M, (cw, ch), flags=cv2.INTER_LINEAR)
        T = T * (1 - sk) + f * sk
        S = np.maximum(S, sk)
    # frosted wall seen through the glass
    sig = max(em * 0.035 * frost, 0.5)
    Fb = cv2.GaussianBlur(bg, (0, 0), sig) if frost > 0 else bg
    xx, yy = np.meshgrid(np.arange(cw, dtype=np.float32), np.arange(ch, dtype=np.float32))
    R = em * 0.22
    mx = xx - NX * R + em * 0.04
    my = yy - NY * R + em * 0.03
    refr = cv2.remap(Fb, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    # lighting on the bevel
    nz = np.ones_like(NX)
    nrm = np.sqrt(NX * NX + NY * NY + nz)
    ndl = (NX * LIGHT[0] + NY * LIGHT[1] + nz * LIGHT[2]) / nrm
    flat = LIGHT[2]
    spec = np.clip((ndl - flat) / (1 - flat), 0, 1) ** 1.6
    dark = np.clip((flat - ndl) / flat, 0, 1)
    face = refr * 0.68 + tint * 0.26 + 0.05
    face *= (1.06 - 0.12 * vert)[..., None]
    face = face * (1 - 0.45 * dark[..., None]) + 0.95 * spec[..., None]
    # inner rim: a hairline of light just inside the silhouette, brighter where it faces the light
    er = cv2.erode(A, np.ones((3, 3), np.uint8), iterations=max(1, int(em * 0.008)))
    rim = np.clip(A - er, 0, 1)
    facing = np.clip((NX * LIGHT[0] + NY * LIGHT[1]) * 1.5, 0, 1)
    face += ((0.18 + 0.55 * facing) * rim)[..., None]
    # sheen sweeping across once assembled
    c = -0.3 + 1.6 * B.ease_out((t - sheen_t0) / 0.9) if t > sheen_t0 else -1
    sheen = np.exp(-((u - c) / 0.07) ** 2) * 0.28 + np.exp(-((u - c + 0.12) / 0.025) ** 2) * 0.18
    face += sheen[..., None] * Hh[..., None]
    # side walls: darker, denser glass, getting darker with depth
    side_refr = cv2.GaussianBlur(refr, (0, 0), 2) if frost > 0 else refr
    side = side_refr * 0.5 + tint * 0.10
    side *= (0.78 - 0.38 * T)[..., None]
    side_edge = np.clip(S - cv2.erode(S, np.ones((3, 3), np.uint8)), 0, 1)
    side += 0.12 * side_edge[..., None]
    alpha_side = S * 0.94
    layer = side * (1 - A[..., None]) * alpha_side[..., None] + face * A[..., None]
    alpha = A + alpha_side * (1 - A)
    layer = np.clip(layer / np.maximum(alpha, 1e-4)[..., None], 0, 1)
    # shadow cast down-right on the wall, soft
    U = np.maximum(A, S)
    M = np.float32([[1, 0, em * 0.06], [0, 1, em * 0.10]])
    sh = cv2.warpAffine(U, M, (cw, ch))
    sh = cv2.GaussianBlur(sh, (0, 0), max(em * 0.07, 1)) * 0.42
    sh += cv2.GaussianBlur(U, (0, 0), max(em * 0.015, 1)) * 0.12  # contact darkening right at the letters
    return layer, alpha, np.clip(sh, 0, 0.6) * (1 - alpha)
