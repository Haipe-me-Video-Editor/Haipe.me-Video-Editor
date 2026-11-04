"""Real app screens on a talking head: while the speaker talks about a screen, it appears as a rounded card above the
captions, over a blurred and dimmed copy of the speaker, with an optional glowing ring on the part they name. Made
for the no-cut subtitle copy (`reel-deliver --screens`); the screens come from `capture` (a demo build or a public
page, never a customer's data).

`screens.json`, paths relative to its own folder, times in source seconds, boxes in CSS pixels of the capture:
    {"label": "Sample data shown.", "dpr": 3, "cards": [
      {"at": 4.3, "end": 6.3, "image": "profile.png", "crop": [0, 134, 390, 610],
       "ring": [31, 527, 359, 589], "ring_at": 4.9}, ...]}
A card that starts exactly where the last one ends crossfades into it. `label` is a small pill above the card.
"""
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = (1080, 1920)
TOP = 285          # below the platform's top bar and the label pill
GAP = 46           # between the card and the first caption line
RADIUS = 38


def ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def card_area(style: dict, size: tuple = SIZE) -> tuple:
    """(top, bottom) in pixels: the band between the top safe zone and two lines of captions sitting at the
    style's caption_margin_v."""
    W, H = size
    cap_bottom = H * (1 - style.get("caption_margin_v", 0.1))
    cap_top = cap_bottom - 1.75 * style.get("caption_size", 0.07) * W
    return TOP, int(cap_top - GAP)


def load(path) -> dict:
    """screens.json with image paths resolved and the cards checked: in order, not overlapping, crops inside."""
    path = Path(path)
    spec = json.loads(path.read_text(encoding="utf-8"))
    dpr = spec.get("dpr", 3)
    errs, last_end = [], 0.0
    for i, c in enumerate(spec["cards"]):
        c["image"] = str((path.parent / c["image"]).resolve())
        w, h = Image.open(c["image"]).size
        x0, y0, x1, y1 = c["crop"]
        if not (0 <= x0 < x1 <= w / dpr + 0.5 and 0 <= y0 < y1 <= h / dpr + 0.5):
            errs.append(f"card {i}: crop {c['crop']} is outside the {w / dpr:.0f}x{h / dpr:.0f} capture")
        if c["end"] <= c["at"]:
            errs.append(f"card {i}: ends before it starts")
        if c["at"] < last_end - 0.01:
            errs.append(f"card {i} at {c['at']}s overlaps the card before it")
        last_end = c["end"]
    if errs:
        raise ValueError("screens.json:\n  " + "\n  ".join(errs))
    return spec


def _card(c: dict, dpr: float, area: tuple, accent: tuple) -> tuple:
    """The card (RGBA float) and its ring layer (or None), scaled to fit the card area."""
    im = Image.open(c["image"]).convert("RGB")
    x0, y0, x1, y1 = [v * dpr for v in c["crop"]]
    im = im.crop((x0, y0, x1, y1))
    h = area[1] - area[0]
    w = round(im.width * h / im.height)
    if w > 900:
        w, h = 900, round(im.height * 900 / im.width)
    s = w / im.width
    im = im.resize((w, h), Image.LANCZOS)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), RADIUS, fill=255)
    base = Image.new("RGBA", (w, h))
    base.paste(im, (0, 0), mask)
    ImageDraw.Draw(base).rounded_rectangle((0, 0, w - 1, h - 1), RADIUS, outline=(255, 255, 255, 60), width=2)
    ring = None
    if c.get("ring"):
        rx0, ry0, rx1, ry1 = [(v * dpr - o) * s for v, o in zip(c["ring"], (x0, y0, x0, y0))]
        box = (rx0 - 6, ry0 - 6, rx1 + 6, ry1 + 6)
        glow = Image.new("RGBA", (w, h))
        ImageDraw.Draw(glow).rounded_rectangle(box, 18, outline=accent + (110,), width=8)
        ring = glow.filter(ImageFilter.GaussianBlur(9))
        ImageDraw.Draw(ring).rounded_rectangle(box, 18, outline=accent + (255,), width=4)
        ring = np.array(ring).astype(np.float32) / 255
    return np.array(base).astype(np.float32) / 255, ring


def _pill(text: str, font_path: str) -> np.ndarray:
    font = ImageFont.truetype(font_path, 34)
    tw = font.getbbox(text)[2]
    pill = Image.new("RGBA", (tw + 56, 64))
    d = ImageDraw.Draw(pill)
    d.rounded_rectangle((0, 0, pill.width - 1, 63), 32, fill=(255, 255, 255, 26), outline=(255, 255, 255, 50), width=2)
    d.text((28, 31), text, font=font, fill=(244, 244, 240, 235), anchor="lm")
    return np.array(pill).astype(np.float32) / 255


def _paste(dst: np.ndarray, rgba: np.ndarray, cx: float, cy: float, alpha: float, scale: float = 1.0) -> None:
    if alpha <= 0:
        return
    if scale != 1.0:
        h, w = rgba.shape[:2]
        rgba = cv2.resize(rgba, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    h, w = rgba.shape[:2]
    x, y = round(cx - w / 2), round(cy - h / 2)
    a = rgba[..., 3:4] * alpha
    region = dst[y:y + h, x:x + w]
    region[:] = region * (1 - a) + rgba[..., [2, 1, 0]] * a  # RGBA onto BGR


class Compositor:
    """Draws the cards of one screens.json onto 1080x1920 BGR frames."""

    def __init__(self, spec: dict, style: dict, font_path: str):
        self.cards = spec["cards"]
        self.area = card_area(style)
        accent = style.get("accent", "#ffffff").lstrip("#")
        rgb = tuple(int(accent[i:i + 2], 16) for i in (0, 2, 4))
        self.layers = [_card(c, spec.get("dpr", 3), self.area, rgb) for c in self.cards]
        self.pill = _pill(spec["label"], font_path) if spec.get("label") else None

    def _joined(self, t: float, at_start: bool) -> bool:
        return any(abs((c["end"] if at_start else c["at"]) - t) < 0.01 for c in self.cards)

    def background(self, t: float) -> float:
        """How far the speaker is blurred and dimmed at time t (0-1)."""
        k = 0.0
        for c in self.cards:
            out = 1 - ease((t - c["end"]) / 0.35) if t > c["end"] else 1.0
            k = max(k, min(ease((t - c["at"] + 0.05) / 0.4), out))
        return k

    def frame(self, f: np.ndarray, t: float) -> np.ndarray:
        k = self.background(t)
        if k <= 0:
            return f
        H, W = f.shape[:2]
        img = f.astype(np.float32) / 255
        blur = cv2.GaussianBlur(cv2.resize(f, (W // 4, H // 4), interpolation=cv2.INTER_AREA), (0, 0), 6)
        blur = cv2.resize(blur, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255
        blur = blur * 0.38 + np.float32([10, 8, 7]) / 255 * 0.31
        img = img * (1 - k) + blur * k
        cy = sum(self.area) / 2
        for c, (crd, ring) in zip(self.cards, self.layers):
            if t < c["at"] - 0.01 or t > c["end"] + 0.35:
                continue
            joined_in = self._joined(c["at"], True)
            v = min(ease((t - c["at"]) / (0.3 if joined_in else 0.4)),
                    1 - ease((t - c["end"]) / 0.3) if t > c["end"] else 1.0)
            if v <= 0:
                continue
            rise = 0 if joined_in else (1 - v) * 40
            scale = (0.965 + 0.035 * v) * (1 + 0.012 * min((t - c["at"]) / 5, 1))  # settle, then a slow push
            _paste(img, crd, W / 2, cy + rise, v, scale)
            ra = c.get("ring_at", c["at"])
            if ring is not None and t >= ra:
                _paste(img, ring, W / 2, cy + rise, v * ease((t - ra) / 0.35), scale)
        if self.pill is not None:
            _paste(img, self.pill, W / 2, self.area[0] - 52, k)
        return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def render(src, screens, out, style: dict) -> Path:
    """src: a 1080x1920 clip (the retouched copy, no captions yet). Writes `out` near-lossless, audio copied."""
    from . import ffmpeg
    from .fonts import ensure_font
    spec = load(screens)
    comp = Compositor(spec, style, str(ensure_font("Sora Light")))
    W, H = SIZE
    fps = ffmpeg.probe(src)["fps"] or 30
    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "bgr24",
                            "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                            "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-i", str(src), "-map", "0:v",
                            "-map", "1:a:0?", "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p",
                            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-c:a", "copy",
                            "-shortest", str(out)], stdin=subprocess.PIPE)
    n, i = W * H * 3, 0
    try:
        while True:
            buf = dec.stdout.read(n)
            if len(buf) < n:
                break
            enc.stdin.write(comp.frame(np.frombuffer(buf, np.uint8).reshape(H, W, 3), i / fps).tobytes())
            i += 1
    finally:
        enc.stdin.close()
        enc.wait()
        dec.wait()
    return Path(out)
