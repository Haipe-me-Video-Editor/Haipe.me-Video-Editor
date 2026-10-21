"""Shared helpers for the "spatial UI around the person" effects (ui_world, orbit, headline_wall).

Not an effect (the leading underscore keeps it out of the registry). It adds what those three need on top of
core.Ctx: a matte cache shared across re-renders of the same window, an occlusion matte with the holes filled
(so cards behind the speaker never show through the shirt), a map of where the speaker is over the window, brand
tokens per style, stills grabbed from footage, and a numpy compositor that puts layers behind and in front of
the speaker with a frosted-glass blur under the panels.
"""
import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# 9:16 safe zone (fractions of the frame): platform UI covers the top 13%, bottom 20% and right 12%.
SAFE = {"x0": 0.04, "x1": 0.88, "y0": 0.135, "y1": 0.80}
GRID = 8  # coverage map is 1/GRID of the frame
_AR = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def is_arabic(s) -> bool:
    return bool(_AR.search(str(s or "")))


def esc(s) -> str:
    import html
    return html.escape(str(s or ""), quote=True)


# ---- the speaker ---------------------------------------------------------------------------------------------
def person(ctx) -> Path:
    """ctx.person(), but the matte is cached by the window's pixels in a folder shared by every window of the
    run, so changing an effect's text or code does not pay for MODNet again (~0.5 s a frame)."""
    own = ctx.work / "cut-person.mov"
    if own.exists():
        return own
    from .. import cutout
    h = hashlib.sha1(f"{cutout.MATTE_VERSION}:{cutout.engine()}:{ctx.W}x{ctx.H}@{ctx.fps}:{ctx.n}".encode())
    with open(ctx.src, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    shared = ctx.work.parent / "_person" / f"{h.hexdigest()[:20]}.mov"
    if shared.exists():
        _link(shared, own)
        return own
    out = ctx.person()
    shared.parent.mkdir(parents=True, exist_ok=True)
    _link(out, shared.with_suffix(".part.mov"))
    shared.with_suffix(".part.mov").replace(shared)
    return out


def _link(src: Path, dst: Path) -> None:
    """Hard link (a matte is ~250 MB of ProRes), or copy across file systems."""
    import os
    try:
        if dst.exists():
            dst.unlink()
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def fill_matte(a: np.ndarray) -> np.ndarray:
    """Occlusion matte: the soft MODNet alpha with every hole inside the silhouette filled (holes that touch the
    bottom edge count as inside: the body continues below the frame). Soft edges are kept."""
    import cv2
    from scipy import ndimage
    h, w = a.shape
    small = cv2.resize(a, (w // 2, h // 2), interpolation=cv2.INTER_AREA) > 0.5
    # a solid row under the frame closes the silhouette; one empty column either side keeps the sides open
    pad = np.pad(small, ((0, 1), (1, 1)), constant_values=False)
    pad[-1, 1:-1] = True
    filled = ndimage.binary_fill_holes(pad)[:-1, 1:-1]
    big = cv2.resize(filled.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
    big = cv2.GaussianBlur(big, (0, 0), 2.0)
    return np.maximum(a, big)


def occluders(ctx):
    """Per-frame occlusion mattes (float32 H x W, 0..1)."""
    for f in ctx.frames(person(ctx), rgba=True):
        yield fill_matte(f[..., 3].astype(np.float32) / 255)


@dataclass
class Scene:
    W: int
    H: int
    cover: np.ndarray            # (H/GRID, W/GRID) fraction of the window's frames where the speaker is there
    face: tuple | None           # (x0, y0, x1, y1) head box in px over the whole window, padded; None: no face
    chin: float                  # lowest chin y in px (or an estimate)
    cx: float                    # face centre x
    fw: float                    # face width px
    safe: dict = field(default_factory=lambda: dict(SAFE))
    face_mask: np.ndarray | None = None  # (H/GRID, W/GRID) 1 where the face (hull of every frame's landmarks) is

    def face_hit(self, x0, y0, x1, y1) -> float:
        """Fraction of the rect on the face itself (landmark hull, padded), not the looser head box."""
        if self.face_mask is None:
            return self.face_overlap(x0, y0, x1, y1)
        g = self.face_mask
        a, b = int(max(0, y0) // GRID), int(np.ceil(min(self.H, y1) / GRID))
        c, d = int(max(0, x0) // GRID), int(np.ceil(min(self.W, x1) / GRID))
        if b <= a or d <= c:
            return 0.0
        return float(g[a:b, c:d].mean())

    def rect_cover(self, x0, y0, x1, y1) -> float:
        """Mean speaker coverage over a pixel rect (0: always clear wall, 1: always the speaker)."""
        g = self.cover
        a, b = int(max(0, y0) / GRID), int(np.ceil(min(self.H, y1) / GRID))
        c, d = int(max(0, x0) / GRID), int(np.ceil(min(self.W, x1) / GRID))
        if b <= a or d <= c:
            return 1.0
        return float(g[a:b, c:d].mean())

    def face_overlap(self, x0, y0, x1, y1) -> float:
        """Fraction of the rect that lies on the (padded) head box."""
        if self.face is None:
            return 0.0
        fx0, fy0, fx1, fy1 = self.face
        iw = max(0.0, min(x1, fx1) - max(x0, fx0))
        ih = max(0.0, min(y1, fy1) - max(y0, fy0))
        area = max(1.0, (x1 - x0) * (y1 - y0))
        return iw * ih / area

    def px(self, key) -> float:
        return self.safe[key] * (self.W if key[0] == "x" else self.H)


def clear_run(sc: Scene, r, right: bool, thresh: float = 0.22) -> float:
    """Width in px of clear wall inside rect r, from its outer side (right edge if `right`) to where the speaker
    starts: where text on a card behind the speaker can go."""
    import math
    x0, y0, x1, y1 = r
    a, b = int(max(0, y0) // GRID), int(math.ceil(min(sc.H, y1) / GRID))
    c, d = int(max(0, x0) // GRID), int(math.ceil(min(sc.W, x1) / GRID))
    if b <= a or d <= c:
        return 0.0
    cols = sc.cover[a:b, c:d].mean(axis=0)
    n = 0
    for v in (cols[::-1] if right else cols):
        if v > thresh:
            break
        n += 1
    return min(x1 - x0, n * GRID)


def scene_from(W, H, cover, pts) -> Scene:
    """Scene from a coverage map and a list of (478, 2) landmark arrays (None entries allowed). Pure, testable."""
    pts = [np.asarray(p, np.float64) for p in pts if p is not None]
    if pts:
        P = np.stack(pts)
        fw = float(np.median(np.linalg.norm(P[:, 454] - P[:, 234], axis=1)))
        x0, x1 = float(P[:, :, 0].min()), float(P[:, :, 0].max())
        top = float(P[:, 10, 1].min()) - 0.42 * fw   # landmark 10 is the hairline; the skull goes higher
        chin = float(P[:, 152, 1].max())
        face = (x0 - 0.10 * fw, top, x1 + 0.10 * fw, chin + 0.07 * fw)
        cx = float(np.median(P[:, :, 0].mean(axis=1)))
        import cv2
        mask = np.zeros(cover.shape, np.uint8)
        allp = P[::max(1, len(P) // 12)].reshape(-1, 2) / GRID
        hull = cv2.convexHull(allp.astype(np.float32)).astype(np.int32)
        cv2.fillConvexPoly(mask, hull, 1)
        r = max(1, int(round(0.07 * fw / GRID)))
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
        face_mask = mask.astype(np.float32)
    else:
        face_mask = None
        rows = np.where(cover.max(axis=1) > 0.5)[0]
        top = (rows[0] * GRID) if len(rows) else H * 0.15
        fw, cx = W * 0.36, W * 0.5
        cols = np.where(cover[min(len(cover) - 1, int((top + fw * 0.6) / GRID))] > 0.5)[0]
        if len(cols):
            cx = (cols[0] + cols[-1]) / 2 * GRID
        chin = top + fw * 1.35
        face = (cx - fw * 0.65, top, cx + fw * 0.65, chin + 0.07 * fw)
    return Scene(W, H, cover, face, chin, cx, fw, face_mask=face_mask)


def scene(ctx) -> Scene:
    """Where the speaker is over this window (coverage map + head box), cached in the window's work folder."""
    cache = ctx.work / "spatial-scene.npz"
    if cache.exists():
        d = np.load(cache, allow_pickle=True)
        cover = d["cover"]
    else:
        import cv2
        acc, k = None, 0
        for m in occluders(ctx):
            s = cv2.resize(m, (ctx.W // GRID, ctx.H // GRID), interpolation=cv2.INTER_AREA)
            s = (s > 0.5).astype(np.float32)
            acc = s if acc is None else acc + s
            k += 1
        cover = acc / max(1, k)
        np.savez(cache, cover=cover)
    return scene_from(ctx.W, ctx.H, cover, ctx.landmarks(every=3))


# ---- brand ---------------------------------------------------------------------------------------------------
def _rgb(hexs: str) -> tuple:
    h = hexs.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba(hexs: str, a: float) -> str:
    r, g, b = _rgb(hexs)
    return f"rgba({r},{g},{b},{a:.3f})"


def mix(a: str, b: str, t: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ra, rb))


def luminance(hexs: str) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _rgb(hexs))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def theme(style: dict, mode: str = "dark") -> dict:
    """UI tokens for a style: surfaces, hairlines, ink, muted ink, accent and the ink that sits on the accent."""
    accent = style.get("accent", "#ff7a1a")
    bg = style.get("bg", "#101114")
    ink = style.get("ink", "#ffffff")
    on_accent = "#101114" if luminance(accent) > 0.35 else "#ffffff"
    if mode == "light":
        return {"surface": "rgba(250,250,248,.94)", "surface2": "rgba(238,238,234,.96)", "line": "rgba(10,12,16,.10)",
                "ink": "#121417", "muted": "rgba(18,20,23,.55)", "accent": accent, "on_accent": on_accent,
                "shadow": "0 18px 50px rgba(0,0,0,.30), 0 2px 8px rgba(0,0,0,.18)", "paper": "#fbfaf6",
                "chip": "rgba(10,12,16,.06)", "mode": "light"}
    return {"surface": rgba(bg, 0.66), "surface2": rgba(mix(bg, "#ffffff", 0.07), 0.78),
            "line": "rgba(255,255,255,.13)", "ink": ink, "muted": rgba(ink, 0.58) if ink.startswith("#") else ink,
            "accent": accent, "on_accent": on_accent, "paper": "#f6f4ee",
            "shadow": "0 24px 60px rgba(0,0,0,.45), 0 2px 10px rgba(0,0,0,.30)",
            "chip": "rgba(255,255,255,.07)", "mode": "dark"}


# ---- stills --------------------------------------------------------------------------------------------------
def stills(ctx, n: int, src=None, size=(240, 426), face=None) -> list:
    """n JPEG stills (of `size`) from `src` (default the window): evenly spread over the clip, each with its own
    crop (wide, tight on the face, offset) so a row of them reads as different clips. Paths in ctx.work."""
    import cv2
    import subprocess
    path = Path(src) if src else ctx.src
    try:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                    "default=nw=1:nk=1", str(path)], capture_output=True, text=True).stdout)
    except ValueError:
        dur = ctx.dur
    out = []
    W, H = ctx.W, ctx.H
    zooms = [1.0, 1.55, 1.2, 1.85, 1.1, 1.4, 1.7, 1.25]
    fcx, fcy = (face if face else (W / 2, H * 0.35))
    for i in range(n):
        t = dur * (i + 0.5) / n
        p = ctx.work / f"still-{hashlib.sha1(str(path).encode()).hexdigest()[:6]}-{i}-{n}.jpg"
        if not p.exists():
            raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                                  "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                                  "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
            if len(raw) < W * H * 3:
                raise RuntimeError(f"could not grab a still from {path} at {t:.2f}s")
            img = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
            z = zooms[i % len(zooms)]
            cw = W / z
            ch = cw * size[1] / size[0]  # the crop has the thumbnail's shape (portrait or landscape)
            if ch > H:
                cw, ch = cw * H / ch, H
            ox = (i % 3 - 1) * 0.06 * W if z > 1.05 else 0
            x0 = int(np.clip(fcx - cw / 2 + ox, 0, W - cw))
            y0 = int(np.clip(fcy - ch * 0.4, 0, H - ch))
            crop = img[y0:y0 + int(ch), x0:x0 + int(cw)]
            cv2.imwrite(str(p), cv2.resize(crop, size, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 90])
        out.append(p)
    return out


def image_like(s) -> bool:
    return isinstance(s, str) and s.lower().rsplit(".", 1)[-1] in {"png", "jpg", "jpeg", "webp"}


# ---- compositing ---------------------------------------------------------------------------------------------
def envelope(t: float, dur: float, a: float = 0.4, b: float = 0.4) -> float:
    """0 -> 1 over the first `a` s, 1 -> 0 over the last `b` s (smoothstep)."""
    def ss(x):
        x = min(1.0, max(0.0, x))
        return x * x * (3 - 2 * x)
    return min(ss(t / a) if a > 0 else 1.0, ss((dur - t) / b) if b > 0 else 1.0)


def _soft(img: np.ndarray, k: int = 4, sigma: float = 5.0) -> np.ndarray:
    import cv2
    h, w = img.shape[:2]
    s = cv2.resize(img, (w // k, h // k), interpolation=cv2.INTER_AREA)
    s = cv2.GaussianBlur(s, (0, 0), sigma)
    return cv2.resize(s, (w, h), interpolation=cv2.INTER_LINEAR)


def composite(ctx, back=(), front=(), dim: float = 0.0, desat: float = 0.0, bg_blur: float = 0.0,
              frost: float = 0.85, ramp=(0.35, 0.4), back_tint=None):
    """Write ctx.out: the window with `back` layers (RGBA clips) between the room and the speaker and `front`
    layers over everything. The room (not the speaker) is dimmed, desaturated and softened by up to dim / desat /
    bg_blur, eased in and out over `ramp`. Under each layer's opaque parts the picture is frosted (blurred) by
    `frost`, so panels read as glass rather than stickers. `back_tint` (per-channel gains) lights the back layers
    like the room."""
    tint = None if back_tint is None else np.asarray(back_tint, np.float32).reshape(1, 1, 3)
    backs = [ctx.frames(p, rgba=True) for p in back]
    fronts = [ctx.frames(p, rgba=True) for p in front]
    with ctx.writer() as w:
        for i, (f, m) in enumerate(zip(ctx.frames(), occluders(ctx))):
            t = i / ctx.fps
            env = envelope(t, ctx.dur, *ramp)
            img = f.astype(np.float32) / 255
            m3 = m[..., None]
            if env > 0 and (dim or desat or bg_blur):
                room = img
                if bg_blur:
                    room = room + (_soft(room, 4, 3.0) - room) * (bg_blur * env)
                if desat:
                    g = room.mean(axis=2, keepdims=True)
                    room = room + (g - room) * (desat * env)
                room = room * (1 - dim * env)
                img = img * m3 + room * (1 - m3)
            for L in backs:
                lay = next(L).astype(np.float32) / 255
                a = lay[..., 3:4] * (1 - m3)
                if frost and a.max() > 0:
                    fa = np.clip((lay[..., 3:4] - 0.35) / 0.4, 0, 1) * (1 - m3) * frost
                    img = img + (_soft(img, 4, 4.0) - img) * fa
                rgb = lay[..., :3] if tint is None else lay[..., :3] * tint
                img = img * (1 - a) + rgb * a
            for L in fronts:
                lay = next(L).astype(np.float32) / 255
                a = lay[..., 3:4]
                if frost and a.max() > 0:
                    fa = np.clip((a - 0.35) / 0.4, 0, 1) * frost
                    img = img + (_soft(img, 4, 5.0) - img) * fa
                img = img * (1 - a) + lay[..., :3] * a
            w(np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8))
    return ctx.out
