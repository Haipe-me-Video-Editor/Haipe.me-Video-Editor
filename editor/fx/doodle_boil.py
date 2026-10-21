"""Doodle boil: a hand-drawn white outline traced around the speaker (from the matte, offset outward) that "boils"
like hand animation (re-drawn every few frames), plus marker doodles (a hand-lettered word, an underline, an arrow
pointing at them, stars) that draw themselves on in the free space around the person. The background dims and
desaturates a little so the lines read."""
import math

import cv2
import numpy as np

from .. import fonts
from . import _cutkit as K

NAME = "doodle_boil"
DOC = ("Hand-drawn white outline boiling around the speaker + marker doodles (word, underline, arrow, stars) that "
       "draw on in the free space. For a playful beat or a callout: 'I need 5 beta testers'.")
BEST_FOR = ["playful", "product", "any"]
DUR = (1.5, 8)
PARAMS = {
    "text": "",             # the hand-lettered word(s), 1-3 short words; \\N for a second line. Arabic uses Lalezar
    "doodles": ["word", "underline", "arrow", "stars", "scribble"],  # any of word underline arrow circle stars
                            # sparkles heart scribble (a hatched box in the accent colour)
    "color": "#ffffff",     # outline and word colour
    "accent": None,         # doodle accent (underline, stars); default the style accent
    "offset": 0.018,        # outline gap from the body, fraction of the width
    "width": 0.0072,        # line width, fraction of the width
    "boil": 3,              # frames per re-draw of the jitter (2-3 = hand animation on twos/threes)
    "dim": 0.32,            # how much darker the background gets (0-1)
    "desat": 0.5,           # how much greyer the background gets (0-1)
    "size": None,           # word cap height, fraction of the height (default fits the free space)
    "font": None,           # a font family for the word instead of the hand-drawn marker alphabet
    "stickers": [],         # images that pop into free space with the same boiling outline:
                            # [{file, w?: 0.3, at?: 0.6, x?, y?}] (w a fraction of the width; x, y its centre)
}

SAFE = (0.05, 0.14, 0.86, 0.78)  # x0, y0, x1, y1 of where doodles may go (platform UI clear)


def render(ctx):
    p = {k: ctx.param(k, v) for k, v in PARAMS.items()}
    W, H, fps = ctx.W, ctx.H, ctx.fps
    lw = max(3.0, p["width"] * W)
    off = p["offset"] * W
    boil = max(1, int(p["boil"]))
    white = K.rgb(p["color"])
    acc = K.rgb(p["accent"] or ctx.style.get("accent", "#ff7a1a"))
    if K.luma(acc) < 110:  # a deep brand colour would vanish on a dimmed background
        acc = K.mix(acc, "#ffffff", 0.35)

    small = K.small_mattes(ctx, every=2, scale=4)
    occ = K.occupancy(small, 60)
    face = K.face_box(ctx)
    plan = layout(p, occ, face, W, H, seed=len(p["text"] or "") + 3)
    interior = body_interior(occ, off * occ.shape[1] / W)
    stickers = [place_sticker(st, ctx.asset(st["file"]), occ, face, plan, W, H) for st in (p["stickers"] or [])]

    # ---- timing ----
    T_IN, T_OUT = 0.5, 0.3
    with ctx.writer() as write:
        cm = K.clean_mattes(ctx)
        for i, (frame, fa) in enumerate(zip(ctx.frames(), ctx.mattes())):
            t = i / fps
            step = i // boil
            # stepped like hand animation: the drawing advances once per boil step
            ts = (step * boil) / fps
            rem = ctx.dur - ts
            k_in = K.ease_out(t / 0.35, 2)
            k_out = K.ease_in(max(0.0, (T_OUT - (ctx.dur - t))) / T_OUT, 2)
            grade = k_in * (1 - k_out)
            A = K.fine_alpha(cm[i], fa)
            img = frame
            if grade > 0:
                g = cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
                d = p["desat"] * grade
                bg = cv2.addWeighted(frame, 1 - d, g, d, 0)
                bg = cv2.convertScaleAbs(bg, alpha=1 - p["dim"] * grade)
                img = K.over8(bg, frame, A)
            sweep = K.ease_out(ts / T_IN, 2)
            mw = np.zeros((H, W), np.uint8)   # white lines
            ma = np.zeros((H, W), np.uint8)   # accent lines
            sk = np.zeros((H, W), np.uint8)   # the second, thinner "sketch" pass of the outline
            if sweep > 0:
                runs = outline_runs(A, off, W, H, plan["centre"], sweep, interior)
                K.draw(mw, K.wobble(runs, lw * 0.5, seed=step * 7 + 1, freq=0.03), lw)
                K.draw(sk, K.wobble(runs, lw * 0.9, seed=step * 7 + 2, freq=0.022), lw * 0.45)
            fade = 1.0 if rem > T_OUT else max(0.0, rem / T_OUT)
            draw_doodles(plan, ts, mw, ma, lw, step)
            if plan.get("word_mask") is not None:
                paste_word_mask(mw, plan, ts, step)
            if fade < 1:  # exit: everything lets go together, in boil steps
                mw, ma, sk = [(m.astype(np.float32) * fade).astype(np.uint8) for m in (mw, ma, sk)]
            out = paint(img, mw, ma, sk, white, acc)
            for st in stickers:  # on top of the person's lines, with the same boiling outline of its own
                out, a_st = paint_sticker(out, st, t, ts, step, fps)
                if a_st is not None:
                    ms = np.zeros((H, W), np.uint8)
                    K.draw(ms, K.wobble(outline_runs(a_st, off * 0.8, W, H, (W / 2, 0), 1.0), lw * 0.5,
                                        seed=step * 7 + 5, freq=0.03), lw)
                    if fade < 1:
                        ms = (ms.astype(np.float32) * fade).astype(np.uint8)
                    out = paint(out, ms, np.zeros_like(ms), np.zeros_like(ms), white, acc)
            write(out)
    return ctx.out


def paint(img, mw, ma, sk, white, acc):
    """Lines over the picture (uint8) with a soft dark under-shadow so white reads even on a bright wall."""
    if mw.max() == 0 and ma.max() == 0 and sk.max() == 0:
        return img
    m = cv2.max(cv2.max(mw, ma), (sk.astype(np.float32) * 0.6).astype(np.uint8)).astype(np.float32) / 255
    sh = K.shift(K.blur(m, 5, down=2), 1.5, 3)
    img = K.over8(img, (0, 0, 0), np.clip(sh * 0.6, 0, 0.38))
    img = K.over8(img, white, sk.astype(np.float32) * (0.55 / 255))
    img = K.over8(img, white, mw.astype(np.float32) * (1 / 255))
    return K.over8(img, acc, ma.astype(np.float32) * (1 / 255))


# ---- the outline ----------------------------------------------------------------------------------------------

def outline_runs(A: np.ndarray, off: float, W: int, H: int, centre, sweep: float, interior=None) -> list:
    """Open polylines of the matte's outline grown by `off` px, without the parts along the frame edge, revealed
    by an angular sweep from the top of the head down both sides (sweep 0-1)."""
    d = 2
    a = cv2.resize(A, (W // d, H // d), interpolation=cv2.INTER_AREA)
    a = cv2.GaussianBlur(a, (0, 0), 2.0)
    b = (a > 0.5).astype(np.uint8)
    r = max(1, int(round(off / d)))
    b = cv2.dilate(b, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    b = (cv2.GaussianBlur(b.astype(np.float32), (0, 0), max(2.0, r * 0.6)) > 0.5).astype(np.uint8)
    cs, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    area = (W // d) * (H // d)
    runs = []
    for c in cs:
        if cv2.contourArea(c) < 0.004 * area:
            continue
        P = c[:, 0, :].astype(np.float32) * d + d / 2
        P = _smooth_closed(P, 7)
        edge = 6
        keep = (P[:, 0] > edge) & (P[:, 0] < W - edge) & (P[:, 1] > edge) & (P[:, 1] < H - edge)
        if interior is not None:  # a gap the matte opened inside the body for a moment (between arm and chest)
            ih, iw = interior.shape
            xi = np.clip((P[:, 0] * iw / W).astype(int), 0, iw - 1)
            yi = np.clip((P[:, 1] * ih / H).astype(int), 0, ih - 1)
            keep &= ~interior[yi, xi]
        if sweep < 1:
            ang = np.abs(np.arctan2(P[:, 0] - centre[0], -(P[:, 1] - centre[1])))  # 0 at the top, pi below
            keep &= ang <= sweep * math.pi
        runs += [_resample(r_, 9) for r_ in _split(P, keep) if len(r_) > 4 and K.length(r_) > 0.06 * W]
    return runs


def body_interior(occ: np.ndarray, off_small: float) -> np.ndarray:
    """Where the person always is, shrunk well inside their edge: outline points there are matte gaps."""
    core = (occ > 0.5).astype(np.uint8)
    r = int(math.ceil(off_small + 5))
    core = cv2.erode(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    return core.astype(bool)


def _smooth_closed(P, k):
    if len(P) < k * 2:
        return P
    pad = np.vstack([P[-k:], P, P[:k]])
    ker = np.ones(k, np.float32) / k
    return np.stack([np.convolve(pad[:, j], ker, "same")[k:-k] for j in (0, 1)], 1)


def _split(P, keep):
    """Contiguous runs of kept points of a closed contour (a run that wraps around is joined)."""
    if keep.all():
        return [np.vstack([P, P[:1]])]
    runs, cur = [], []
    for pt, k in zip(P, keep):
        if k:
            cur.append(pt)
        elif cur:
            runs.append(np.asarray(cur))
            cur = []
    if cur:
        if runs and keep[0]:
            runs[0] = np.vstack([np.asarray(cur), runs[0]])
        else:
            runs.append(np.asarray(cur))
    return runs


def _resample(P, spacing):
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    if cum[-1] < spacing:
        return P
    s = np.arange(0, cum[-1], spacing)
    return np.stack([np.interp(s, cum, P[:, 0]), np.interp(s, cum, P[:, 1])], 1).astype(np.float32)


# ---- doodles --------------------------------------------------------------------------------------------------

def layout(p, occ, face, W, H, seed=3) -> dict:
    """Where each doodle goes and when it draws on. Works on the 1/4-size occupancy map; returns full-size strokes."""
    q = W / occ.shape[1]
    safe = (SAFE[0] * W / q, SAFE[1] * H / q, SAFE[2] * W / q, SAFE[3] * H / q)
    forbid = []
    if face:
        fx0, fy0, fx1, fy1 = face
        mx, my = (fx1 - fx0) * 0.12, (fy1 - fy0) * 0.1
        forbid.append(((fx0 - mx) / q, (fy0 - my) / q, (fx1 + mx) / q, (fy1 + my) / q))
        centre = ((fx0 + fx1) / 2, (fy0 + fy1) / 2)
        head = ((fx0 + fx1) / 2, fy0)
    else:
        bb = K.bbox(occ) or (0.3, 0.2, 0.7, 1)
        centre = ((bb[0] + bb[2]) / 2 * W, (bb[1] + bb[3]) / 2 * H)
        head = (centre[0], bb[1] * H)
    want = list(p["doodles"] or [])
    text = (p["text"] or "").strip()
    items = []  # (kind, strokes, colour 'w'/'a', t0, dur)
    plan = {"centre": centre, "items": items, "word_mask": None}
    t = 0.32
    word_box = None
    if text and "word" in want:
        word_box, t = _place_word(p, text, occ, safe, forbid, head, q, W, H, plan, t, seed)
        plan["word_box"] = word_box
        forbid.append(tuple(v / q for v in word_box))
        if "underline" in want:
            x0, y0, x1, y1 = word_box
            ul = K.underline((x1 - x0) * 1.04, seed=seed)
            ul = [s + np.array([x0 - (x1 - x0) * 0.02, y1 + (y1 - y0) * 0.12], np.float32) for s in ul]
            items.append(("underline", ul, "a", t - 0.05, 0.3))
            t += 0.2
        if "arrow" in want and face and plan.get("word_cost", 1) < 0.3:  # an arrow from a word on the chest
            # would point at the chin: only when the word sits in free space beside / above the person
            a, b = _arrow_ends(word_box, face, W, H)
            if a is not None:
                items.append(("arrow", K.arrow(a, b, bend=0.22 if a[0] < b[0] else -0.22, head=0.2), "w", t, 0.3))
                t += 0.22
        if "circle" in want:
            x0, y0, x1, y1 = word_box
            loop = K.ellipse_loop((x1 - x0) * 0.62, (y1 - y0) * 0.9, seed=seed)
            items.append(("circle", [s + np.array([(x0 + x1) / 2, (y0 + y1) / 2], np.float32) for s in loop], "a",
                          t, 0.35))
            t += 0.25
    if "scribble" in want:
        bw, bh = 0.12 * W, 0.085 * W
        spot, cost = K.find_spot(occ, bw / q, bh / q, safe, forbid, near=(head[0] / q - 0.25 * W / q, head[1] / q),
                                 step=4, weight_near=0.5)
        if spot is not None and cost < 0.5:
            x0, y0 = spot[0] * q, spot[1] * q
            forbid.append((spot[0], spot[1], spot[0] + bw / q, spot[1] + bh / q))
            zz = [z + np.array([x0 + bw * 0.1, y0 + bh * 0.12], np.float32)
                  for z in K.zigzag(bw * 0.8, bh * 0.76, 7, seed=seed, slant=0.3)]
            rng = np.random.default_rng(seed)
            corners = np.array([(x0, y0), (x0 + bw, y0), (x0 + bw, y0 + bh), (x0, y0 + bh), (x0, y0 - bh * 0.15)],
                               np.float32) + rng.uniform(-4, 4, (5, 2)).astype(np.float32)
            items.append(("scribble", zz, "a", t + 0.05, 0.45))
            items.append(("frame", [K._densify(corners, 12)], "w", t + 0.25, 0.3))
    marks = [k for k in want if k in ("stars", "sparkles", "heart")]
    shapes = []
    for k in marks:
        if k == "stars":
            shapes += [("star", 0.044), ("sparkle", 0.034)]
        elif k == "sparkles":
            shapes += [("sparkle", 0.04), ("sparkle", 0.028)]
        else:
            shapes += [("heart", 0.04)]
    for j, (kind, r) in enumerate(shapes[:4]):
        R = r * W
        box = 2.4 * R / q
        spot, cost = K.find_spot(occ, box, box, safe, forbid, near=(head[0] / q + (-1) ** j * 0.18 * W / q,
                                                                    head[1] / q), step=4, weight_near=0.6)
        if spot is None or cost > 0.6:
            continue
        cx, cy = (spot[0] + box / 2) * q, (spot[1] + box / 2) * q
        forbid.append((spot[0], spot[1], spot[0] + box, spot[1] + box))
        shape = {"star": K.star, "sparkle": K.sparkle, "heart": K.heart}[kind]
        strokes = shape(R) if kind != "star" else K.star(R, seed=seed + j)
        rot = math.radians(-12 + 24 * ((seed + j) % 3) / 2)
        items.append((kind, K.transform(strokes, 1, rot, at=(cx, cy)), "a" if j % 2 == 0 else "w",
                      max(0.2, t - 0.1) + 0.12 * j, 0.25))
    return plan


def _place_word(p, text, occ, safe, forbid, head, q, W, H, plan, t, seed):
    arabic = K.has_arabic(text)
    nchar = max(len(line) for line in text.replace("\\N", "\n").split("\n"))
    sizes = [p["size"]] if p["size"] else [0.05, 0.043, 0.036, 0.03]
    best = None
    for frac in sizes:
        h = frac * H
        if arabic or p.get("font"):
            mask, (bw, bh) = K.text_mask_font(text, fonts.ensure_font(p.get("font") or "Lalezar"), h)
            strokes = None
        else:
            strokes, (bw, bh) = K.text_strokes(text, h, seed=seed)
            mask = None
        if bw > (SAFE[2] - SAFE[0]) * W:
            continue
        pad = 0.25 * h
        spot, cost = K.find_spot(occ, (bw + 2 * pad) / q, (bh + 2.2 * pad) / q, safe, forbid,
                                 near=(head[0] / q, head[1] / q), step=4, weight_near=0.25)
        if spot is None:
            continue
        cost += 0.05 * (sizes.index(frac) if frac in sizes else 0)  # prefer bigger when nearly as free
        if best is None or cost < best[0]:
            best = (cost, frac, h, strokes, mask, bw, bh, spot, pad)
        if cost < 0.2:
            break
    if best is None:  # nothing fits: centre it low, small
        h = 0.03 * H
        strokes, (bw, bh) = K.text_strokes(text, h, seed=seed) if not arabic else (None, (0, 0))
        mask = None
        if arabic:
            mask, (bw, bh) = K.text_mask_font(text, fonts.ensure_font("Lalezar"), h)
        best = (0, 0.03, h, strokes, mask, bw, bh, ((W - bw) / 2 / q, 0.7 * H / q), 0)
    _, _, h, strokes, mask, bw, bh, spot, pad = best
    x0, y0 = spot[0] * q + pad, spot[1] * q + pad
    dur = min(1.0, 0.09 * max(3, nchar))
    if strokes is not None:
        plan["items"].append(("word", [s + np.array([x0, y0], np.float32) for s in strokes], "w", t, dur))
    else:
        plan["word_mask"] = (mask, int(x0), int(y0), t, dur)
    plan["word_h"] = h
    plan["word_cost"] = best[0]
    return (x0, y0, x0 + bw, y0 + bh), t + dur


def _arrow_ends(box, face, W, H):
    """From the word's edge facing the head to a point just beside the face (never on it)."""
    x0, y0, x1, y1 = box
    fx0, fy0, fx1, fy1 = face
    fcx, fcy = (fx0 + fx1) / 2, (fy0 + fy1) / 2
    wcx, wcy = (x0 + x1) / 2, (y0 + y1) / 2
    gap = 0.035 * W
    if wcy > fy1:  # word below the face: point up at the chin side
        a = (wcx + (fcx - wcx) * 0.3, y0 - gap * 0.5)
        b = (fcx + (fx1 - fcx) * 0.9 * (1 if wcx > fcx else -1), fy1 + gap * 0.3)
    elif wcx < fcx:
        a = (x1 + gap * 0.3, wcy)
        b = (fx0 - gap, fcy)
    else:
        a = (x0 - gap * 0.3, wcy)
        b = (fx1 + gap, fcy)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 0.06 * W:
        return None, None
    if L > 0.3 * W:  # a long arrow reads as a diagram, not a doodle: shorten from the head end
        f = 0.3 * W / L
        b = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
    b = (min(max(b[0], 0.04 * W), 0.86 * W), min(max(b[1], 0.14 * H), 0.8 * H))
    return a, b


def draw_doodles(plan, ts, mw, ma, lw, step):
    for kind, strokes, col, t0, dur in plan["items"]:
        pr = min(1.0, (ts - t0) / dur)
        if pr <= 0:
            continue
        s = K.reveal(strokes, K.ease_out(pr, 2))
        w = lw * (1.2 if kind == "word" else 1.0)
        amp = lw * (0.35 if kind == "word" else 0.5)
        K.draw(mw if col == "w" else ma, K.wobble(s, amp, seed=step * 13 + sum(map(ord, kind)) % 97, freq=0.05), w)


def paste_word_mask(mw, plan, ts, step):
    mask, x0, y0, t0, dur = plan["word_mask"]
    pr = min(1.0, (ts - t0) / dur)
    if pr <= 0:
        return
    m = mask.copy()
    cut = int(m.shape[1] * (1 - K.ease_out(pr, 2)))
    m[:, :cut] = 0
    rng = np.random.default_rng(step)
    M = cv2.getRotationMatrix2D((m.shape[1] / 2, m.shape[0] / 2), rng.uniform(-1.2, 1.2), 1)
    M[:, 2] += rng.uniform(-1.5, 1.5, 2)
    m = cv2.warpAffine(m, M, (m.shape[1], m.shape[0]))
    H, W = mw.shape
    h, w = m.shape
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if xb <= xa or yb <= ya:
        return
    sub = (m[ya - y0:yb - y0, xa - x0:xb - x0] * 255).astype(np.uint8)
    mw[ya:yb, xa:xb] = np.maximum(mw[ya:yb, xa:xb], sub)


# ---- stickers -------------------------------------------------------------------------------------------------

def place_sticker(st: dict, path, occ, face, plan, W, H) -> dict:
    """Load and size a sticker image and choose where it goes: the given centre, or the freest spot away from the
    face and the word, nearest the upper corners."""
    from PIL import Image
    img = Image.open(path).convert("RGBA")
    w = int(st.get("w", 0.3) * W)
    img = img.resize((w, max(1, int(img.height * w / img.width))), Image.LANCZOS)
    rgba = np.asarray(img)
    h = rgba.shape[0]
    if st.get("x") is not None and st.get("y") is not None:
        cx, cy = st["x"] * W, st["y"] * H
    else:
        q = W / occ.shape[1]
        safe = (SAFE[0] * W / q, SAFE[1] * H / q, SAFE[2] * W / q, SAFE[3] * H / q)
        forbid = []
        if face:  # the whole head (crown to chin, ear to ear and a margin) stays clear; shoulders and chest may not
            fx0, fy0, fx1, fy1 = face
            bb = K.bbox(occ)
            top = bb[1] * H if bb else fy0 - 0.4 * (fy1 - fy0)
            mx = 0.22 * (fx1 - fx0)
            forbid.append(((fx0 - mx) / q, (min(top, fy0) - 0.03 * H) / q, (fx1 + mx) / q, (fy1 + 0.04 * H) / q))
        if plan.get("word_box"):
            forbid.append(tuple(v / q for v in plan["word_box"]))
        spot, _ = K.find_spot(occ, w / q, h / q, safe, forbid, near=(0.82 * W / q, 0.3 * H / q), step=4,
                              weight_near=0.3)
        if spot is None and st.get("w", 0.3) * 0.85 >= 0.2:  # a little smaller, never below a readable size
            return place_sticker({**st, "w": st.get("w", 0.3) * 0.85, "w0": st.get("w0", st.get("w", 0.3))}, path,
                                 occ, face, plan, W, H)
        if spot is None:  # a close-up with no room: it peeks in from the right edge at head height, full size
            if st.get("w0"):
                return place_sticker({**st, "w": st["w0"], "w0": None, "x": 1 - st["w0"] * 0.36,
                                      "y": ((face[1] + face[3]) / 2 / H) if face else 0.32}, path, occ, face, plan, W, H)
            cx, cy = W - w * 0.36, (face[1] + face[3]) / 2 if face else 0.32 * H
        else:
            cx, cy = spot[0] * q + w / 2, spot[1] * q + h / 2
    return {"rgba": rgba, "cx": cx, "cy": cy, "at": float(st.get("at", 0.6)), "pop": K.spring("bouncy")}


def paint_sticker(img, st, t, ts, step, fps):
    """The sticker on this frame: springs in from nothing, then holds with a hand-animation jitter that changes
    once per boil step. Returns the picture and the sticker's full-frame alpha (None before it appears)."""
    if t < st["at"]:
        return img, None
    k = st["pop"](min(1.0, (t - st["at"]) / 0.45))
    if k <= 0.01:
        return img, None
    H, W = img.shape[:2]
    rng = np.random.default_rng(step * 31 + 7)
    rgba = st["rgba"]
    h, w = rgba.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-1.5, 1.5), k)
    M[:, 2] += [st["cx"] - w / 2 + rng.uniform(-1.5, 1.5), st["cy"] - h / 2 + rng.uniform(-1.5, 1.5)]
    layer = cv2.warpAffine(rgba, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    a = layer[..., 3].astype(np.float32) / 255
    return K.over8(img, np.ascontiguousarray(layer[..., :3]), a), a
