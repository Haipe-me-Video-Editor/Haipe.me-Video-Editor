"""Shared helpers for the "type behind / around the person" effects (wall_text, glass_type, cover_story,
frame_break): spring timing in Python, a cache of the person matte shared across re-renders of the same window,
where the wall is actually visible (an occupancy grid of the person over the window), font files for PIL, and a
layout solver that puts a block of text where it stays readable behind the speaker.

A private module (leading underscore): the registry skips it.
"""
import hashlib
import math
import os
import subprocess
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..graphics.spring import PRESETS
from ..graphics.spring import spring as _spring

CELL = 8                      # occupancy grid cell, px
SAFE = (0.04, 0.13, 0.88, 0.80)  # left, top, right, bottom of the 9:16 safe zone (fractions)


# ---- time ------------------------------------------------------------------------------------------------------
@lru_cache(None)
def spring(preset: str = "snappy"):
    """The house spring ease (same curve as the JS springIn) for numpy-rendered effects: t in 0..1 -> 0..~1.1."""
    return _spring(*PRESETS[preset])


def ease_in(t: float) -> float:
    """power2.in: the exit curve."""
    t = min(max(t, 0.0), 1.0)
    return t * t


def ease_out(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def progress(t: float, start: float, dur: float) -> float:
    return min(max((t - start) / dur, 0.0), 1.0) if dur > 0 else float(t >= start)


# ---- shared caches ---------------------------------------------------------------------------------------------
def _window_key(ctx) -> str:
    h = hashlib.sha1()
    with open(ctx.src, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    from .. import cutout
    h.update(f"{cutout.MATTE_VERSION}:{cutout.engine()}:{ctx.W}x{ctx.H}@{ctx.fps}".encode())
    return h.hexdigest()[:16]


def prime(ctx) -> None:
    """Re-use the person matte and landmarks of an identical window rendered before (any effect, any code
    version): the framework caches them per spec+code key, which re-runs MODNet on every code edit."""
    shared = ctx.work.parent / "_shared" / _window_key(ctx)
    shared.mkdir(parents=True, exist_ok=True)
    for name in ("cut-person.mov", "landmarks-3.npz"):
        mine, theirs = ctx.work / name, shared / name
        if not mine.exists() and theirs.exists():
            try:
                os.link(theirs, mine)
            except OSError:
                pass
    ctx._shared = shared


def publish(ctx) -> None:
    """After ctx.person()/ctx.face() ran: offer their caches to later renders of the same window."""
    shared = getattr(ctx, "_shared", None)
    if shared is None:
        return
    for name in ("cut-person.mov", "landmarks-3.npz"):
        mine, theirs = ctx.work / name, shared / name
        if mine.exists() and not theirs.exists():
            try:
                os.link(mine, theirs)
            except OSError:
                pass


def person_alpha(ctx):
    """Per-frame person alpha, float32 (H, W)."""
    path = ctx.person()
    publish(ctx)
    yield from ctx.mattes()
    _ = path


def occupancy(ctx, pct: float = 80) -> np.ndarray:
    """Where the person is over the window: the pct-th percentile of the matte per CELL x CELL cell, (H/CELL, W/CELL)
    in 0..1. A percentile, not the max, so a hand sweeping once across the wall does not ban the wall."""
    cache = ctx.work / f"occ-{pct}.npy"
    if cache.exists():
        return np.load(cache)
    path = ctx.person()
    publish(ctx)
    gw, gh = ctx.W // CELL, ctx.H // CELL
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-vf",
                          f"fps={ctx.fps},scale={gw}:{gh}:flags=area,format=rgba", "-frames:v", str(ctx.n),
                          "-f", "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, gh, gw, 4)[..., 3].astype(np.float32) / 255
    occ = np.percentile(a, pct, axis=0).astype(np.float32)
    np.save(cache, occ)
    return occ


def occupancy_for_text(ctx, head: dict, head_pct: float = 92) -> np.ndarray:
    """Occupancy for placing text: the head nearly as far as it ever sways (head_pct percentile above the chin),
    the body and hands as they usually are (80th below it), so a word does not slide under the head mid-window."""
    lo, hi = occupancy(ctx, 80), occupancy(ctx, head_pct)
    r = int(np.clip(head["chin"] / CELL, 0, lo.shape[0]))
    out = lo.copy()
    out[:r] = np.maximum(lo[:r], hi[:r])
    return out


def head_box(occ: np.ndarray, face: dict, W: int, H: int) -> dict:
    """The head from the occupancy grid and the face landmarks: the top of the skull (landmark 10 is the hairline,
    not the crown), left/right at eye level, in pixels."""
    gh, gw = occ.shape
    c0 = int(np.clip((face["cx"] - face["fw"] * 0.35) / CELL, 0, gw - 1))
    c1 = int(np.clip((face["cx"] + face["fw"] * 0.35) / CELL, c0 + 1, gw))
    cols = occ[:, c0:c1] > 0.5
    rows = np.where(cols.mean(axis=1) > 0.3)[0]
    top = float(rows[0] * CELL) if len(rows) else face["top"] - face["fw"] * 0.35
    top = min(top, face["top"])
    r = int(np.clip(face["eye_y"] / CELL, 0, gh - 1))
    line = np.where(occ[r] > 0.5)[0]
    left = float(line[0] * CELL) if len(line) else face["cx"] - face["fw"] * 0.6
    right = float((line[-1] + 1) * CELL) if len(line) else face["cx"] + face["fw"] * 0.6
    return {"top": top, "left": left, "right": right, "cx": face["cx"], "eye_y": face["eye_y"], "fw": face["fw"],
            "chin": face["cy"] + (face["cy"] - face["top"])}


# ---- fonts -----------------------------------------------------------------------------------------------------
SERIF_CANDIDATES = [  # a Didone first if the machine has one, else the best high-contrast serif we can find
    "Bodoni Moda", "Playfair Display", "DM Serif Display", "Didot", "Bodoni 72", "Abril Fatface",
    "FreeSerif:style=Bold", "Liberation Serif:style=Bold", "DejaVu Serif:style=Bold"]


@lru_cache(None)
def serif_font() -> Path | None:
    """A display serif from the system (no downloads). None when there is none."""
    for cand in SERIF_CANDIDATES:
        fam = cand.split(":")[0]
        try:
            out = subprocess.run(["fc-match", "-f", "%{family}|%{file}", cand], capture_output=True, text=True,
                                 timeout=10, check=False).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        family, _, file = out.partition("|")
        if fam.lower() in family.lower() and file.lower().endswith((".ttf", ".otf")) and Path(file).exists():
            return Path(file)
    return None


def font_file(ctx, family: str) -> Path:
    """A TTF for a CSS family name used by the fx pack (Sora, Anton, ..., BrandLT, BrandAR, Serif)."""
    from .. import fonts
    from .core import FONT_FAMILIES
    if family == "Serif":
        p = serif_font()
        return p if p else fonts.ensure_font("Anton")
    if family == "BrandLT":
        family = ctx.style.get("font", "Sora")
    elif family == "BrandAR":
        family = ctx.style.get("arabic_font", "IBM Plex Sans Arabic")
    return fonts.ensure_font(FONT_FAMILIES.get(family, family))


def is_arabic(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" or "ݐ" <= ch <= "ݿ" or "ﭐ" <= ch <= "ﻼ" for ch in text)


# ---- text blocks -----------------------------------------------------------------------------------------------
class Block:
    """A block of text laid out by PIL at a reference em size: per-word boxes (for animation) and the ink mask
    (for the occupancy fit). Lines are centred; Arabic lines run right to left."""

    def __init__(self, lines: list, font: Path, em: float = 200, leading: float = 0.95, tracking: float = 0.0,
                 upper: bool = True):
        self.lines = [[w.upper() if upper and not is_arabic(w) else w for w in ln] for ln in lines]
        self.font_path, self.em, self.leading, self.tracking = Path(font), em, leading, tracking
        f = ImageFont.truetype(str(font), int(em))
        self.font = f
        # vertical metrics from the ink of capitals (and Arabic letters) so lines sit tight
        sample = "HXE" if not any(is_arabic(w) for ln in lines for w in ln) else "البيت"
        b = f.getbbox(sample, anchor="ls")
        self.cap = -b[1]
        self.desc = max(b[3], 0)
        space = f.getlength(" ")
        words, widths = [], []
        for li, ln in enumerate(self.lines):
            rtl = any(is_arabic(w) for w in ln)
            ws = [self._wlen(w) for w in ln]
            widths.append(sum(ws) + space * 0.9 * (len(ln) - 1))
            words.append((ln, ws, rtl))
        self.width = max(widths) if widths else 0
        lh = self.cap * (1 + 0.28) * leading if not any(r for _, _, r in words) else em * 1.1 * leading
        self.line_h = lh
        pad = int(em * 0.12)
        self.pad = pad
        self.height = lh * (len(self.lines) - 1) + self.cap + self.desc
        self.boxes = []  # (word, x, baseline_y, width, line index)
        for li, ((ln, ws, rtl), lw) in enumerate(zip(words, widths)):
            x = pad + (self.width - lw) / 2
            base = pad + self.cap + li * lh
            order = list(zip(ln, ws))
            if rtl:
                order = order[::-1]
            for w, wl in order:
                self.boxes.append((w, x, base, wl, li))
                x += wl + space * 0.9
        self.size = (math.ceil(self.width + 2 * pad), math.ceil(self.height + 2 * pad))

    def _wlen(self, w: str) -> float:
        if self.tracking and not is_arabic(w):
            return sum(self.font.getlength(c) for c in w) + self.tracking * self.em * (len(w) - 1)
        return self.font.getlength(w)

    def draw_word(self, draw: ImageDraw.ImageDraw, w: str, x: float, base: float, fill=255, font=None,
                  scale: float = 1.0):
        font = font or self.font
        if self.tracking and not is_arabic(w):
            for c in w:
                draw.text((x * scale, base * scale), c, font=font, fill=fill, anchor="ls")
                x += self.font.getlength(c) + self.tracking * self.em
        else:
            draw.text((x * scale, base * scale), w, font=font, fill=fill, anchor="ls")

    def mask(self) -> np.ndarray:
        im = Image.new("L", self.size, 0)
        d = ImageDraw.Draw(im)
        for w, x, base, _, _ in self.boxes:
            self.draw_word(d, w, x, base)
        return np.asarray(im, np.float32) / 255

    def word_sprites(self, scale: float, rotate: int = 0):
        """Each word rendered at em*scale as (alpha float32, (x, y) top-left in the block at that scale,
        rotated by `rotate` quarter turns counter-clockwise together with the block)."""
        f = ImageFont.truetype(str(self.font_path), max(4, round(self.em * scale)))
        bw, bh = math.ceil(self.size[0] * scale), math.ceil(self.size[1] * scale)
        out = []
        for w, x, base, wl, li in self.boxes:
            im = Image.new("L", (bw, bh), 0)
            self.draw_word(ImageDraw.Draw(im), w, x, base, font=f, scale=scale)
            a = np.asarray(im, np.float32) / 255
            if rotate:
                a = np.rot90(a, rotate)
            ys, xs = np.where(a > 0.004)
            if not len(ys):
                continue
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            out.append({"word": w, "alpha": np.ascontiguousarray(a[y0:y1, x0:x1]), "x": int(x0), "y": int(y0),
                        "line": li})
        return out


def split_lines(text: str, max_lines: int = 2) -> list:
    """Line arrangements to try: the text's own lines when it has \\N, else one line and a balanced split."""
    if "\\N" in text or "\n" in text:
        return [[ln.split() for ln in text.replace("\n", "\\N").split("\\N") if ln.strip()]]
    words = text.split()
    opts = [[words]]
    if len(words) >= 2 and max_lines >= 2:
        best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
        opts.append([words[:best], words[best:]])
    return opts


# ---- layout solver ---------------------------------------------------------------------------------------------
def blocked_grid(occ: np.ndarray, W: int, H: int, margin_cells: int = 2, safe=SAFE) -> np.ndarray:
    """1 where text may not go: the person (dilated a little) and everything outside the safe zone."""
    b = (occ > 0.4).astype(np.uint8)
    if margin_cells:
        k = np.ones((2 * margin_cells + 1, 2 * margin_cells + 1), np.uint8)
        b = cv2.dilate(b, k)
    gh, gw = b.shape
    x0, y0, x1, y1 = int(safe[0] * gw), int(safe[1] * gh), math.ceil(safe[2] * gw), math.ceil(safe[3] * gh)
    out = np.ones_like(b, np.float32)
    out[y0:y1, x0:x1] = b[y0:y1, x0:x1]
    return out


def _components(mask: np.ndarray):
    """Letters (or Arabic letter groups) of a block mask as (label image, count)."""
    m = (mask > 0.3).astype(np.uint8)
    m = cv2.dilate(m, np.ones((3, max(3, int(mask.shape[0] * 0.02)) | 1), np.uint8))
    n, lab = cv2.connectedComponents(m)
    return lab, n


def fit(blocked: np.ndarray, mask: np.ndarray, scale: float, anchor: tuple, max_letter: float = 0.18,
        max_total: float = 0.07, side: str | None = None):
    """Best top-left (in grid cells) for `mask` (a block mask at the reference size) shrunk by `scale` and then to
    the grid, or None. A position passes when no letter is more than max_letter hidden and the word as a whole no
    more than max_total; among those, the closest to `anchor` (grid cells) wins."""
    gh, gw = blocked.shape
    h, w = mask.shape
    th, tw = max(1, round(h * scale / CELL)), max(1, round(w * scale / CELL))
    if th > gh or tw > gw:
        return None
    small = cv2.resize(mask, (tw, th), interpolation=cv2.INTER_AREA)
    lab, n = _components(mask)
    if n - 1 < 3:  # a joined-up (Arabic) word is one component: hiding a third of it hides whole letters
        max_letter = min(max_letter, 0.1)
    lab_s = cv2.resize(lab.astype(np.float32), (tw, th), interpolation=cv2.INTER_NEAREST).astype(np.int32)
    total_area = small.sum()
    if total_area <= 0:
        return None
    ny, nx = gh - th + 1, gw - tw + 1
    total = np.zeros((ny, nx), np.float32)
    worst = np.zeros((ny, nx), np.float32)
    for k in range(1, n):
        t = small * (lab_s == k)
        a = t.sum()
        if a < 0.5:
            continue
        r = cv2.matchTemplate(blocked, t.astype(np.float32), cv2.TM_CCORR)
        total += r
        worst = np.maximum(worst, r / a)
    total /= total_area
    ok = (worst <= max_letter) & (total <= max_total)
    yy, xx = np.mgrid[0:ny, 0:nx]
    cy, cx = yy + th / 2, xx + tw / 2
    if side == "left":
        ok &= cx < anchor[0]
    elif side == "right":
        ok &= cx > anchor[0]
    if not ok.any():
        return None
    dist = np.hypot(cx - anchor[0], (cy - anchor[1]) * 1.15) + total * 40
    dist[~ok] = np.inf
    i = np.unravel_index(np.argmin(dist), dist.shape)
    return int(i[1]), int(i[0]), float(total[i]), float(worst[i])


def solve(blocked: np.ndarray, blocks: list, anchor_px: tuple, em_range: tuple, allow_rotate: bool = True,
          rotate_penalty: float = 0.72, weights: list | None = None, **tol):
    """Largest readable placement of any of `blocks` (Block objects: alternative line arrangements or fonts) in the
    free grid: horizontal, or turned a quarter to read up the left side / down the right side of the head. Scored
    by cap height (x rotate_penalty when turned, x weights[i]). Returns a dict with block, em (px), scale, rotate
    (quarter turns ccw: 0, 1 or -1), x, y (top-left px of the block image at that em), w, h, or None when nothing
    fits at the smallest size."""
    anchor = (anchor_px[0] / CELL, anchor_px[1] / CELL)
    best = None
    for bi, blk in enumerate(blocks):
        base = blk.mask()
        for rot, side in ([(0, None), (1, "left"), (-1, "right")] if allow_rotate else [(0, None)]):
            m = np.rot90(base, rot) if rot else base
            lo, hi = em_range[0] / blk.em, em_range[1] / blk.em
            if fit(blocked, m, lo, anchor, side=side, **tol) is None:
                continue
            for _ in range(9):  # binary search on the scale; fitting gets harder as the block grows
                mid = (lo + hi) / 2
                if fit(blocked, m, mid, anchor, side=side, **tol) is None:
                    hi = mid
                else:
                    lo = mid
            pos = fit(blocked, m, lo, anchor, side=side, **tol)
            score = blk.cap * lo * (rotate_penalty if rot else 1.0) * (weights[bi] if weights else 1 - 0.04 * bi)
            if best is None or score > best["score"]:
                best = {"block": blk, "em": blk.em * lo, "scale": lo, "rotate": rot, "x": pos[0] * CELL,
                        "y": pos[1] * CELL, "hidden": pos[2], "score": score, "w": m.shape[1] * lo,
                        "h": m.shape[0] * lo, "index": bi}
    return best


# ---- compositing -----------------------------------------------------------------------------------------------
def paste(dst: np.ndarray, src: np.ndarray, x: int, y: int, op=np.maximum):
    """dst[y:, x:] = op(dst, src) for 2-D (or 3-D) arrays, clipped to dst."""
    H, W = dst.shape[:2]
    h, w = src.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    dst[y0:y1, x0:x1] = op(dst[y0:y1, x0:x1], src[y0 - y:y1 - y, x0 - x:x1 - x])


def warp_sprite(a: np.ndarray, dx: float, dy: float, scale: float = 1.0, rot_deg: float = 0.0,
                pivot: tuple | None = None, pad: int = 0):
    """A sprite moved by (dx, dy), scaled and rotated about its centre (or pivot): (array, x offset, y offset) of the
    bounding canvas relative to the sprite's original top-left."""
    h, w = a.shape[:2]
    if abs(scale - 1) < 1e-4 and abs(rot_deg) < 1e-3:
        ix, iy = math.floor(dx), math.floor(dy)
        fx, fy = dx - ix, dy - iy
        if fx < 1e-3 and fy < 1e-3:
            return a, ix, iy
        M = np.float32([[1, 0, fx], [0, 1, fy]])
        out = cv2.warpAffine(a, M, (w + 1, h + 1), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        return out, ix, iy
    px, py = pivot if pivot else (w / 2, h / 2)
    M = cv2.getRotationMatrix2D((px, py), -rot_deg, scale)
    corners = np.array([[0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]], np.float32) @ M.T
    x0, y0 = np.floor(corners.min(0)).astype(int) - 1 - pad
    x1, y1 = np.ceil(corners.max(0)).astype(int) + 1 + pad
    M[0, 2] -= x0
    M[1, 2] -= y0
    ix, iy = math.floor(dx), math.floor(dy)
    M[0, 2] += dx - ix
    M[1, 2] += dy - iy
    out = cv2.warpAffine(a, M, (int(x1 - x0), int(y1 - y0)), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    return out, int(x0) + ix, int(y0) + iy


def hex_rgb(c: str) -> np.ndarray:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255


class NotBackground:
    """MediaPipe selfie_multiclass: per-pixel probability that a pixel is NOT background (person, hair, clothes,
    accessories), smoothed over time. MODNet keeps a chair back as part of the person; on a clean backdrop that
    chair has to go, and this class map knows a chair from a shoulder."""

    def __init__(self):
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        from ..extras import ensure_model
        self.mp = mp
        self.seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(ensure_model("selfie_multiclass"))),
            output_confidence_masks=True, output_category_mask=False))
        self.prev = None

    def __call__(self, rgb: np.ndarray) -> np.ndarray:
        H, W = rgb.shape[:2]
        res = self.seg.segment(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
        bg = np.squeeze(res.confidence_masks[0].numpy_view()).astype(np.float32)
        keep = np.clip((0.75 - bg) / 0.5, 0, 1)
        self.prev = keep if self.prev is None or self.prev.shape != keep.shape else self.prev * 0.5 + keep * 0.5
        out = cv2.resize(self.prev, (W, H), interpolation=cv2.INTER_LINEAR)
        out = cv2.dilate(out, np.ones((9, 9), np.uint8))
        return cv2.GaussianBlur(out, (0, 0), 4)
