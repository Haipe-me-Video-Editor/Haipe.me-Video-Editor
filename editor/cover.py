"""Covers and thumbnails: the still that decides whether anyone taps. Picks the strongest frame of the speaker (a big
readable expression, eyes open and on the lens, sharp), cuts them out, and builds a few designs on the rules that
make a cover stop the scroll: one focal face, a 2-4 word headline that is readable at grid size, high contrast,
a background colour set against the speaker's own colours, nothing in the parts a platform covers or crops.
Every design is exported at each platform's size and checked; a phone-size preview sheet shows them as viewers will.

    python -m editor cover <raw clip> <out_dir> --title "3 to 5 words" [--accent word ...] [--sub "small line"]
        [--style <brand>] [--layouts punch frame minimal object] [--sizes reel youtube square] [--at seconds]
        [--image product.png] [--video-title "the video's title"]

Give it the raw clip, not the finished edit: a frame of the edit can hold the speaker inside a card or window.

The science and the numbers behind each rule are in skills/edit-video/SKILL.md, "Covers and thumbnails".
"""
import colorsys
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import cutout, fonts

SIZES = {"reel": (1080, 1920), "youtube": (1920, 1080), "square": (1080, 1080)}
# Where the face and the words must sit (x0, y0, x1, y1, fractions). Reel: the one rect (x 120-780, y 285-1248 of
# 1080x1920) inside Instagram's 4:5 feed and 3:4 grid crops, TikTok's grid, and both apps' buttons and captions.
SAFE = {"reel": (0.111, 0.148, 0.722, 0.65), "youtube": (0.04, 0.04, 0.96, 0.96), "square": (0.06, 0.06, 0.94, 0.94)}
AVOID = {"youtube": [(0.80, 0.85, 1.0, 1.0), (0.85, 0.0, 1.0, 0.12)]}  # duration badge; hover icons top right
MAX_BYTES = 2_000_000  # YouTube's limit for a thumbnail set from a phone
GRID = {"reel": (0.0, 0.125, 1.0, 0.875)}       # the profile-grid crop (3:4 of a 9:16 cover)
MAX_WORDS = 5
MAX_WORDS_AR, MAX_CHARS_AR = 4, 22  # Arabic words carry attached particles: cap by characters too
MIN_TEXT_H = {"reel": 0.045, "youtube": 0.10, "square": 0.06}  # a line's cap height, of the frame height
MIN_FACE_H = {"reel": 0.16, "youtube": 0.30, "square": 0.22}   # chin to hairline, of the frame height
MIN_CONTRAST = 4.5                                               # WCAG AA between the text and what is behind it
LAYOUTS = ("punch", "frame", "minimal", "object")  # object needs --image


# ---- frames ----------------------------------------------------------------------------------------------------
def _landmarker():
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core.base_options import BaseOptions

    from .extras import model_path
    return vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path("face_landmarker"))), num_faces=1,
        output_face_blendshapes=True))


def expression_score(b: dict) -> float:
    """0-1: a clear, genuine expression with the eyes open and on the lens. Large studies of breakout thumbnails find
    a well-lit face with a real expression, not an exaggerated "shocked" one; a mouth caught mid-word reads as a bad
    still. So: a smile or engaged brows score, open eyes on the lens are required, mid-word mouths are marked down
    (a wide genuine laugh is not)."""
    smile = (b.get("mouthSmileLeft", 0) + b.get("mouthSmileRight", 0)) / 2
    brows = b.get("browInnerUp", 0)
    jaw = b.get("jawOpen", 0)
    blink = (b.get("eyeBlinkLeft", 0) + b.get("eyeBlinkRight", 0)) / 2
    away = max(b.get("eyeLookOutLeft", 0), b.get("eyeLookOutRight", 0), b.get("eyeLookUpLeft", 0),
               b.get("eyeLookDownLeft", 0), b.get("eyeLookInLeft", 0))
    score = 0.45 + 0.9 * smile + 0.35 * min(brows, 0.6)
    if 0.08 < jaw < 0.5 and smile < 0.3:  # caught mid-word
        score -= 1.2 * (jaw - 0.08)
    score -= 1.4 * max(0.0, blink - 0.2) + 0.8 * max(0.0, away - 0.3)
    return float(np.clip(score, 0, 1))


def sharpness(gray: np.ndarray) -> float:
    import cv2
    return float(cv2.Laplacian(gray, cv2.CV_32F).var())


def score_frames(video, n: int = 40) -> list:
    """[{t, score, expr, sharp, face_h}] for n frames spread over the video (skipping the first and last 5%)."""
    import cv2
    import mediapipe as mp
    info = _probe(video)
    dur, W, H = info["duration"], 360, round(360 * info["height"] / info["width"] / 2) * 2
    lm, rows = _landmarker(), []
    for k in range(n):
        t = dur * (0.05 + 0.9 * k / max(1, n - 1))
        rgb = _frame(video, t, W, H)
        if rgb is None:
            continue
        r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        if not r.face_landmarks:
            continue
        P = np.array([(p.x * W, p.y * H) for p in r.face_landmarks[0]], np.float32)
        b = {c.category_name: c.score for c in r.face_blendshapes[0]}
        x0, y0 = P.min(0)
        x1, y1 = P.max(0)
        g = cv2.cvtColor(rgb[int(max(0, y0)):int(y1), int(max(0, x0)):int(x1)], cv2.COLOR_RGB2GRAY)
        rows.append({"t": round(t, 2), "expr": expression_score(b), "sharp": sharpness(g) if g.size else 0.0,
                     "face_h": float((y1 - y0) / H)})
    if not rows:
        return []
    top = max(r["sharp"] for r in rows) or 1.0
    for r in rows:  # expression first; a soft or motion-blurred frame loses most of its score
        r["score"] = round(r["expr"] * (0.35 + 0.65 * min(1.0, r["sharp"] / (0.6 * top))), 4)
    return sorted(rows, key=lambda r: -r["score"])


def pick(rows: list, k: int = 3, gap: float = 2.0) -> list:
    """The k best frames at least `gap` seconds apart (different moments, so the designs differ)."""
    out = []
    for r in rows:
        if all(abs(r["t"] - o["t"]) >= gap for o in out):
            out.append(r)
        if len(out) == k:
            break
    return out


def _probe(video) -> dict:
    from . import ffmpeg
    return ffmpeg.probe(video)


def _frame(video, t: float, W: int, H: int):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf",
                          f"scale={W}:{H},format=rgb24", "-f", "rawvideo", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(H, W, 3).copy() if len(raw) == W * H * 3 else None


def person_at(video, t: float, height: int = 1920) -> tuple:
    """(rgb uint8, alpha float 0-1) of the speaker at time t, full height `height`: the engine's own cut-out (edge
    colour cleaned, interior solid), run over half a second so the video matte has settled."""
    info = _probe(video)
    W = round(height * info["width"] / info["height"] / 2) * 2
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "win.mp4"
        start = max(0.0, t - 0.5)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", "0.6", "-i", str(video), "-vf",
                        f"fps=30,scale={W}:{height}", "-an", "-c:v", "libx264", "-crf", "12", "-preset", "veryfast",
                        str(src)], check=True)
        out = Path(tmp) / "cut.mov"
        cutout.cut_out(src, out, 0, 0.6, (W, height))
        raw = subprocess.run(["ffmpeg", "-v", "error", "-sseof", "-0.04", "-i", str(out), "-frames:v", "1", "-f",
                              "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True, check=True).stdout
    rgba = np.frombuffer(raw, np.uint8).reshape(height, W, 4)
    return rgba[..., :3].copy(), rgba[..., 3].astype(np.float32) / 255


# ---- colour ----------------------------------------------------------------------------------------------------
def dominant_hue(rgb: np.ndarray, alpha: np.ndarray) -> float:
    """The speaker's main hue (0-1) from their saturated pixels (clothes, mostly), weighted by saturation."""
    px = rgb[alpha > 0.9].reshape(-1, 3).astype(np.float32) / 255
    if not len(px):
        return 0.0
    px = px[:: max(1, len(px) // 20000)]
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in px])
    w = hsv[:, 1] * (hsv[:, 2] > 0.15)
    if w.sum() < 1e-3:
        return 0.0
    ang = hsv[:, 0] * 2 * np.pi
    return float((np.arctan2((np.sin(ang) * w).sum(), (np.cos(ang) * w).sum()) / (2 * np.pi)) % 1.0)


def palette(rgb, alpha, accent: str | None = None, bg: str | None = None) -> dict:
    """Background set against the speaker: the complementary hue of their own colours, deep and saturated, so they
    separate from it; a bright accent for the key word; white text with a dark edge. A brand's colours override."""
    h = (dominant_hue(rgb, alpha) + 0.5) % 1.0
    deep = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, 0.75, 0.32))
    mid = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, 0.65, 0.62))
    return {"bg1": _hex(bg) if bg else deep, "bg2": mid if not bg else _shade(_hex(bg), 1.7),
            "accent": _hex(accent) if accent else (255, 214, 10), "ink": (255, 255, 255), "edge": (12, 12, 16)}


def _hex(c: str) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _shade(c: tuple, k: float) -> tuple:
    return tuple(int(min(255, v * k)) for v in c)


def luminance(c) -> float:
    def ch(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(float(v)) for v in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ---- text ------------------------------------------------------------------------------------------------------
def is_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in text)


def _font(text: str, size: int, family: str | None = None):
    fam = family or ("Tajawal Black" if is_arabic(text) else "Anton")
    return ImageFont.truetype(str(fonts.ensure_font(fam)), size, layout_engine=ImageFont.Layout.RAQM)


def lines_for(title: str, max_lines: int = 2) -> list:
    """Split a title into at most max_lines balanced lines (by character count)."""
    words = title.split()
    if len(words) <= 1 or max_lines == 1:
        return [title]
    best, best_d = [title], 10 ** 9
    for i in range(1, len(words)):
        parts = [" ".join(words[:i]), " ".join(words[i:])]
        if max_lines >= 3 and len(words) >= 3:
            for j in range(i + 1, len(words)):
                three = [" ".join(words[:i]), " ".join(words[i:j]), " ".join(words[j:])]
                d = max(map(len, three)) - min(map(len, three)) + 1
                if d < best_d and max(map(len, three)) < max(map(len, parts)):
                    best, best_d = three, d
        d = abs(len(parts[0]) - len(parts[1]))
        if d < best_d:
            best, best_d = parts, d
    return best


def auto_accent(title: str, accent: list) -> list:
    """The accent words: as given, else a leading number ("20 years", "$10k"): numbers are what eyes land on."""
    if accent:
        return accent
    first = title.split()[0] if title.split() else ""
    return [first] if any(ch.isdigit() for ch in first) else []


def draw_title(img: Image.Image, box: tuple, title: str, accent_words: list, pal: dict, max_lines: int = 2,
               family: str | None = None, align: str = "center") -> dict:
    """The headline as big as fits `box` (x0, y0, x1, y1 px), the accent words in the accent colour, white with a
    dark edge and a soft shadow. Arabic: shaped right to left, a thin edge and a heavier shadow instead of a thick
    outline (a thick one fills the dots). Returns the drawn text box, cap height and size in px."""
    x0, y0, x1, y1 = box
    rtl = is_arabic(title)
    lines = lines_for(title, max_lines)
    d = ImageDraw.Draw(img)
    dirn = "rtl" if rtl else None
    size = int((y1 - y0) / len(lines) / 1.05)
    while size > 10:
        f = _font(title, size, family)
        if max(d.textlength(ln, font=f, direction=dirn) for ln in lines) <= (x1 - x0) and \
                size * 1.05 * len(lines) <= (y1 - y0):
            break
        size -= 4
    f = _font(title, size, family)
    edge = max(2, size // 28) if rtl or family else max(3, size // 14)
    acc = {w.strip().lower() for w in accent_words}
    placed, y = [], y0
    for ln in lines:
        w = d.textlength(ln, font=f, direction=dirn)
        x = {"center": x0 + ((x1 - x0) - w) / 2, "left": x0, "right": x1 - w}[align]
        placed.append((x, y, ln, w))
        y += size * 1.05
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    off = edge * (2.5 if rtl else 1.5)
    for x, yy, ln, w in placed:
        sd.text((x + off * 0.6, yy + off), ln, font=f, fill=(0, 0, 0, 200), stroke_width=edge + 2,
                stroke_fill=(0, 0, 0, 200), direction=dirn)
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(2, edge * (1.6 if rtl else 1.2)))))
    d = ImageDraw.Draw(img)
    for x, yy, ln, w in placed:
        if rtl:  # one run per line keeps the shaping intact; the line takes the accent if it holds an accent word
            colour = pal["accent"] if any(a in ln for a in acc) else pal["ink"]
            d.text((x, yy), ln, font=f, fill=colour, stroke_width=edge, stroke_fill=pal["edge"], direction="rtl")
            continue
        cx = x
        for word in ln.split(" "):
            colour = pal["accent"] if word.strip(".,!?").lower() in acc else pal["ink"]
            d.text((cx, yy), word, font=f, fill=colour, stroke_width=edge, stroke_fill=pal["edge"])
            cx += d.textlength(word + " ", font=f)
    tb = (min(x for x, *_ in placed) - edge, y0, max(x + w for x, _, _, w in placed) + edge,
          y0 + size * 1.05 * len(lines))
    return {"box": tb, "cap": size * 0.72, "size": size}


# ---- layouts ---------------------------------------------------------------------------------------------------
def _gradient(W: int, H: int, c1, c2, glow_at=None) -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    k = (yy / H)[..., None]
    img = np.asarray(c2, np.float32) * (1 - k) + np.asarray(c1, np.float32) * k
    if glow_at is not None:
        gx, gy, r = glow_at
        d = np.sqrt((xx - gx) ** 2 + (yy - gy) ** 2) / r
        img = img + (np.exp(-d * d * 1.5)[..., None] * 70)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")


def _place_person(rgb, alpha, W, H, face_frac: float, cx: float, snap: bool = False) -> tuple:
    """The cut-out scaled so the person fills face_frac of the cover's height (head to the frame bottom), standing
    on the bottom edge centred at x = cx (px). With snap, a body the source video cut off at its left or right edge
    is moved flush to the cover's edge on the side it stands, so the cut is hidden instead of showing as a straight line.
    Returns the RGBA layer and the person's box (px)."""
    ys, xs = np.where(alpha > 0.5)
    top, bottom = ys.min(), ys.max()
    s = face_frac * H / max(1, (bottom - top))
    ph, pw = int(alpha.shape[0] * s), int(alpha.shape[1] * s)
    layer = Image.fromarray(np.dstack([rgb, (alpha * 255).astype(np.uint8)])).resize((pw, ph), Image.LANCZOS)
    x = int(cx - (xs.min() + xs.max()) / 2 * s)
    if snap:
        cut = cut_sides(alpha)
        if "right" in cut and cx > W / 2:
            x = W - int(xs.max() * s) - 1
        elif "left" in cut and cx < W / 2:
            x = -int(xs.min() * s)
    y = int(H - bottom * s)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(layer, (x, y), layer)  # paste clips at the canvas edge
    a = np.asarray(canvas)[..., 3]
    yy, xx = np.where(a > 128)
    return canvas, ((int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max())) if len(yy) else (0, 0, 0, 0))


def cut_sides(alpha: np.ndarray, frac: float = 0.25) -> set:
    """The sides ("left", "right") where the person is cut off by a straight vertical line (the source video's
    edge, or a window or box the speaker was framed in): solid matte along the person's outermost column for more
    than frac of the person's height. A natural silhouette touches its outermost column at only a few rows."""
    ys, xs = np.where(alpha > 0.5)
    if not len(xs):
        return set()
    h = ys.max() - ys.min() + 1
    return {side for side, x in (("left", xs.min()), ("right", xs.max()))
            if (alpha[:, max(0, x - 1):x + 2].max(1) > 0.5).sum() > frac * h}


def _sticker(layer: Image.Image, width: int, colour=(255, 255, 255)) -> Image.Image:
    """A solid border round the cut-out (the outline effect, for a still). Not along a side where the body is cut
    off by a straight line (see cut_sides): an outline there draws a box edge instead of a silhouette."""
    a = layer.getchannel("A")
    grown = np.asarray(a.filter(ImageFilter.MaxFilter(width * 2 + 1)).filter(ImageFilter.GaussianBlur(1))).copy()
    la = np.asarray(a)
    cut = cut_sides(la.astype(np.float32) / 255)
    xs = np.where(la.max(0) > 128)[0]
    if len(xs):
        if "left" in cut:
            grown[:, : xs.min() + 1] = la[:, : xs.min() + 1]
        if "right" in cut:
            grown[:, xs.max():] = la[:, xs.max():]
    ring = Image.new("RGBA", layer.size, colour + (0,))
    ring.putalpha(Image.fromarray(grown))
    ring.alpha_composite(layer)
    return ring


def _scrim(img: Image.Image, box: tuple, strength: float) -> None:
    """Darken softly behind the headline (a blurred shadow of its box), so white words hold 4.5:1 on a light
    background without a heavy outline. Arabic gets more: its letters cannot take a thick stroke."""
    W, H = img.size
    x0, y0, x1, y1 = box
    m = Image.new("L", (W, H), 0)
    pad = int(min(W, H) * 0.04)
    ImageDraw.Draw(m).rectangle((x0 - pad, y0 - pad, x1 + pad, y1 + pad), fill=int(255 * strength))
    m = m.filter(ImageFilter.GaussianBlur(min(W, H) * 0.06))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade.putalpha(m)
    img.alpha_composite(shade)


def _feather_cuts(layer: Image.Image, cut: set, frac: float = 0.18) -> Image.Image:
    """Fade the person out towards a side where the body is cut by a straight line and that is not on the cover's
    own edge, so the cut reads as a soft vignette instead of a box edge."""
    a = np.asarray(layer.getchannel("A")).astype(np.float32)
    xs = np.where(a.max(0) > 128)[0]
    if not cut or not len(xs):
        return layer
    W = a.shape[1]
    band = max(2, int((xs.max() - xs.min()) * frac))
    ramp = np.linspace(0, 1, band, dtype=np.float32)
    if "left" in cut and xs.min() > 2:
        a[:, xs.min():xs.min() + band] *= ramp[: min(band, W - xs.min())]
        a[:, : xs.min()] = 0
    if "right" in cut and xs.max() < W - 3:
        x1 = xs.max() + 1
        a[:, x1 - band:x1] *= ramp[::-1][-min(band, x1):]
        a[:, x1:] = 0
    out = layer.copy()
    out.putalpha(Image.fromarray(a.astype(np.uint8)))
    return out


def _object_card(path, w: int, tilt: float = -4, max_h: int | None = None) -> Image.Image:
    """The product / screenshot / result as a white-bordered card, slightly tilted, with a drop shadow, no wider
    than w and (with its border) no taller than max_h."""
    im = Image.open(path).convert("RGB")
    im.thumbnail((w, max(40, int(max_h * 0.9)) if max_h else w * 2))
    pad = max(6, w // 40)
    card = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (255, 255, 255, 255))
    card.paste(im, (pad, pad))
    card = card.rotate(tilt, expand=True, resample=Image.BICUBIC)
    sh = Image.new("RGBA", (card.width + 40, card.height + 40), (0, 0, 0, 0))
    sh.paste((0, 0, 0, 120), (20, 28, 20 + card.width, 28 + card.height), card.getchannel("A"))
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    sh.alpha_composite(card, (20, 20))
    return sh


def compose(layout: str, size_name: str, person: tuple, frame_rgb, title: str, accent: list, sub: str, pal: dict,
            image=None):
    """One cover. Returns (image RGB, info for the checks)."""
    W, H = SIZES[size_name]
    rgb, alpha = person
    sx0, sy0, sx1, sy1 = SAFE[size_name]
    wide = W > H
    rtl = is_arabic(title)
    # the face sits in the safe zone: for a reel, centred on the safe rect (clear of the right-hand buttons); on a
    # wide thumbnail, opposite the headline (headline where the eye enters: left for Latin, right for Arabic)
    face_frac = {"reel": 0.58, "youtube": 0.95, "square": 0.64}[size_name]
    cx = (sx0 + sx1) / 2 * W if not wide else W * (0.30 if rtl else 0.70)
    if layout == "object" and image and not wide:  # the speaker to one side of the safe rect, the object the other
        cx = W * (sx1 - (sx1 - sx0) * 0.32 if rtl else sx0 + (sx1 - sx0) * 0.32)
    if layout == "frame":  # the real room behind, darkened and soft, so the cover still says where this is
        bg = Image.fromarray(frame_rgb).convert("RGBA").resize(_cover_fit(frame_rgb, W, H), Image.LANCZOS)
        bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
        bg = Image.blend(bg.filter(ImageFilter.GaussianBlur(W / 60)), Image.new("RGBA", (W, H), (0, 0, 0, 255)), 0.45)
    elif layout == "minimal":  # tinted, never near-black: it must not melt into YouTube's dark theme
        bg = _gradient(W, H, _shade(pal["bg1"], 0.55), _shade(pal["bg1"], 0.9))
    else:
        bg = _gradient(W, H, pal["bg1"], pal["bg2"], (cx, H * 0.45, max(W, H) * 0.45))
    layer, pbox = _place_person(rgb, alpha, W, H, face_frac, cx, snap=wide)  # the speaker keeps their colour
    cut = cut_sides(np.asarray(layer.getchannel("A")).astype(np.float32) / 255)
    if layout == "minimal":
        layer = _feather_cuts(layer, cut)
        glow = layer.getchannel("A").filter(ImageFilter.GaussianBlur(W / 40))
        halo = Image.new("RGBA", (W, H), (255, 255, 255, 0))
        halo.putalpha(glow.point(lambda v: int(v * 0.45)))
        bg.alpha_composite(halo)
    else:
        layer = _feather_cuts(_sticker(layer, max(4, min(W, H) // 120)), cut)
    img = bg
    img.alpha_composite(layer)
    if wide:
        tx0, tx1 = (W * 0.50, W * sx1) if rtl else (W * sx0, W * 0.52)
        ty0 = 0.14 if rtl else 0.10  # an Arabic headline starts top right, under YouTube's hover icons: lower it
        tbox = (int(tx0), int(H * ty0), int(tx1), int(H * (0.50 if layout == "object" else 0.80)))
    else:
        tbox = (int(W * sx0), int(H * sy0), int(W * sx1), int(H * (sy0 + {"reel": 0.17, "square": 0.22}[size_name] - (0.02 if layout == "object" else 0))))
    serif = layout == "minimal" and not rtl
    head = title if (rtl or serif) else title.upper()
    words = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # drawn apart first, so the scrim can fit what was drawn
    t = draw_title(words, tbox, head, auto_accent(title, accent), pal, max_lines=3 if wide else 2,
                   family=("Instrument Serif Italic" if serif else None),
                   align=("right" if rtl else "left") if wide else "center")
    if layout != "minimal":
        x0, y0, x1, y1 = t["box"]
        _scrim(img, (x0, y0, x1, y1 + (t["size"] * 0.6 if sub else 0)), 0.55 if rtl else 0.35)
    img.alpha_composite(words)
    text_bottom = t["box"][3]
    if sub:
        d = ImageDraw.Draw(img)
        f = _font(sub, max(14, int(t["size"] * 0.30)), "Montserrat" if not is_arabic(sub) else None)
        sw = d.textlength(sub, font=f, direction="rtl" if is_arabic(sub) else None)
        sx = {"center": t["box"][0] + (t["box"][2] - t["box"][0] - sw) / 2, "left": t["box"][0],
              "right": t["box"][2] - sw}["center" if not wide else ("right" if rtl else "left")]
        sy = t["box"][3] + t["size"] * 0.22
        d.text((sx, sy), sub, font=f, fill=pal["accent"], stroke_width=3,
               stroke_fill=pal["edge"], direction="rtl" if is_arabic(sub) else None)
        text_bottom = int(sy + f.size * 1.2)
    if layout == "object" and image:
        with Image.open(image) as im:
            tall = im.height > im.width
        gap = (t["box"][0] - pbox[2]) if rtl else (pbox[0] - t["box"][2])  # between headline and speaker
        if wide and tall and gap > W * 0.12:  # a phone screenshot or a bottle: standing in that gap
            card = _object_card(image, int(min(W * 0.24, gap * 0.9)), tilt=4 if rtl else -4, max_h=int(H * 0.78))
            mid = (pbox[2] + t["box"][0]) / 2 if rtl else (t["box"][2] + pbox[0]) / 2
            ox = int(mid - card.width / 2)
            oy = int(H * 0.56 - card.height / 2)
        elif wide:  # under the headline, lined up with it
            room = int(H * 0.96) - text_bottom - int(H * 0.03)
            card = _object_card(image, int((tbox[2] - tbox[0]) * 0.85), tilt=4 if rtl else -4, max_h=room)
            ox = tbox[2] - card.width if rtl else tbox[0]
            oy = text_bottom + int(H * 0.02)
        else:  # beside the head, on the other side of the safe rect
            room = int(H * (sy1 + 0.08)) - text_bottom - int(H * 0.03)
            card = _object_card(image, int(W * 0.30), tilt=4 if rtl else -4, max_h=room)
            # a reel's safe rect is too narrow for a close face and a card: the card may use the upper margin,
            # which the app's buttons (lower right) and the grid crop (top and bottom) leave clear
            edge = (0.08, 0.92) if size_name == "reel" else (sx0, sx1)
            ox = int(W * edge[0]) if rtl else int(W * edge[1]) - card.width
            oy = text_bottom + int(H * 0.03)
        img.alpha_composite(card, (max(0, ox), max(0, oy)))
    return img.convert("RGB"), {"text_box": t["box"], "cap": t["cap"], "person_box": pbox, "size": size_name,
                                "title": title}


def _cover_fit(frame, W, H):
    h, w = frame.shape[:2]
    s = max(W / w, H / h)
    return int(w * s) + 1, int(h * s) + 1


# ---- checks ----------------------------------------------------------------------------------------------------
def check(img: Image.Image, info: dict, face_h: float | None = None, video_title: str = "") -> list:
    """Problems with a finished cover: too many words, text too small to read at grid size, weak contrast behind
    the text, a face too small, words where the platform covers or crops them, an edge that melts into the
    platform's own background, or a headline that just repeats the video title."""
    W, H = img.size
    name, title = info["size"], info["title"]
    probs = []
    words = title.split()
    if is_arabic(title):
        if len(words) > MAX_WORDS_AR or len(title.replace(" ", "")) > MAX_CHARS_AR:
            probs.append(f"Arabic headline too long: keep to {MAX_WORDS_AR} words and {MAX_CHARS_AR} letters")
    elif len(words) > MAX_WORDS:
        probs.append(f"{len(words)} words: keep the headline to {MAX_WORDS} or fewer")
    if info["cap"] / H < MIN_TEXT_H[name]:
        probs.append(f"text too small: cap height {info['cap'] / H:.1%} of the height, want {MIN_TEXT_H[name]:.1%}+")
    x0, y0, x1, y1 = (int(v) for v in info["text_box"])
    region = np.asarray(img)[max(0, y0):y1, max(0, x0):x1].reshape(-1, 3)
    if len(region):
        bright, dark = region[region.mean(1) > 200], region[region.mean(1) <= 200]
        if len(bright) and len(dark):  # the text is the bright part; what is behind it is the rest
            c = contrast(np.median(bright, 0), np.median(dark, 0))
            if c < MIN_CONTRAST:
                probs.append(f"contrast {c:.1f}:1 behind the headline, want {MIN_CONTRAST}:1+")
    sx0, sy0, sx1, sy1 = SAFE[name]
    tol = 0.01
    if x0 < (sx0 - tol) * W or y0 < (sy0 - tol) * H or x1 > (sx1 + tol) * W or y1 > (sy1 + tol) * H:
        probs.append("the headline runs outside the safe zone (cropped in a grid or covered by the app)")
    for ax0, ay0, ax1, ay1 in AVOID.get(name, []):
        if x1 > ax0 * W and x0 < ax1 * W and y1 > ay0 * H and y0 < ay1 * H:
            probs.append("the headline sits under a platform badge or icon")
    if face_h is not None and face_h < MIN_FACE_H[name]:
        probs.append(f"the face is {face_h:.0%} of the height, want {MIN_FACE_H[name]:.1%}+")
    rim = np.concatenate([np.asarray(img)[: H // 20].reshape(-1, 3), np.asarray(img)[-H // 20:].reshape(-1, 3)])
    m = rim.mean(0)
    if m.min() > 235 or (m.max() < 24 and abs(m[0] - m[2]) < 6):
        probs.append("the edge is near white or near black: it will melt into the app's light or dark theme")
    if video_title:
        a = {w.lower().strip(".,!?") for w in words}
        b = {w.lower().strip(".,!?") for w in video_title.split()}
        if a and len(a & b) / len(a) > 0.5:
            probs.append("the headline repeats the video title: say something the title does not")
    return probs


def save(img: Image.Image, path, max_bytes: int = MAX_BYTES) -> Path:
    """JPEG at the highest quality that stays under max_bytes (YouTube refuses bigger thumbnails from a phone)."""
    for q in (95, 92, 88, 84, 80, 75, 68, 60, 50, 40):
        img.save(path, quality=q, optimize=True)
        if Path(path).stat().st_size <= max_bytes:
            return Path(path)
    raise ValueError(f"{path}: over {max_bytes} bytes even at JPEG quality 40")


def preview_sheet(paths: list, out) -> Path:
    """The covers as people meet them: a reel cover at profile-grid size (with its 3:4 crop) and at full phone size,
    a YouTube thumbnail at sidebar (168 px) and feed sizes."""
    tiles = []
    for p in paths:
        im = Image.open(p)
        if im.width < im.height:
            grid = im.crop((0, int(im.height * 0.125), im.width, int(im.height * 0.875))).resize((130, 173))
            phone = im.resize((270, 480))
            tile = Image.new("RGB", (130 + 270 + 30, 500), (240, 240, 240))
            tile.paste(grid, (10, 10))
            tile.paste(phone, (150, 10))
        else:
            small, feed = im.resize((168, 94)), im.resize((360, 202))
            tile = Image.new("RGB", (168 + 360 + 30, 230), (240, 240, 240))
            tile.paste(small, (10, 10))
            tile.paste(feed, (188, 10))
        tiles.append(tile)
    Wt = max(t.width for t in tiles)
    sheet = Image.new("RGB", (Wt, sum(t.height for t in tiles) + 10 * len(tiles)), (255, 255, 255))
    y = 0
    for t in tiles:
        sheet.paste(t, (0, y))
        y += t.height + 10
    sheet.save(out, quality=90)
    return Path(out)


# ---- the command -----------------------------------------------------------------------------------------------
def make(video, out_dir, title: str, accent: list | None = None, sub: str = "", style: dict | None = None,
         layouts=LAYOUTS, sizes=("reel", "youtube"), at: float | None = None, image=None,
         video_title: str = "") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = score_frames(video) if at is None else [{"t": at, "score": 1.0, "face_h": None}]
    if not rows:
        raise RuntimeError("no face found in the video: give --at <seconds> for the frame to use")
    best = pick(rows, k=1)[0]
    person = person_at(video, best["t"])
    info = _probe(video)
    frame = _frame(video, best["t"], round(1920 * info["width"] / info["height"] / 2) * 2, 1920)
    st = style or {}
    pal = palette(person[0], person[1], st.get("accent"), st.get("cover_bg"))
    report = {"frame_t": best["t"], "expression": best.get("expr"), "covers": []}
    files = []
    for lay in layouts:
        if lay == "object" and not image:
            continue
        for sz in sizes:
            img, meta = compose(lay, sz, person, frame, title, accent or [], sub, pal, image)
            p = save(img, out / f"cover-{lay}-{sz}.jpg")
            report["covers"].append({"file": p.name, "layout": lay, "size": sz,
                                     "problems": check(img, meta, video_title=video_title)})
            files.append(p)
    preview_sheet(files, out / "preview.jpg")
    (out / "covers.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def cmd(a) -> None:
    from .style import load_style
    st = load_style(a.style) if a.style else None
    r = make(a.video, a.out_dir, a.title, a.accent, a.sub or "", st, tuple(a.layouts), tuple(a.sizes), a.at,
             a.image, a.video_title or "")
    print(f"frame at {r['frame_t']}s")
    for c in r["covers"]:
        print(f"{c['file']}: " + ("ok" if not c["problems"] else "; ".join(c["problems"])))
    print(Path(a.out_dir) / "preview.jpg")
