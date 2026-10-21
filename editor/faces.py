"""Where the speaker's head is, so graphics can stay off it.

`detect` samples the source at a low rate and finds the largest frontal face per frame with
OpenCV's bundled Haar cascade. Boxes are fractions of the source frame and are grown from the
face to the whole head (hair, beard, glasses). `head_band` maps them onto the rendered frame
for a timeline span, following each segment's zoom and centre crop.
"""
import subprocess

import numpy as np

from . import ffmpeg
from .config import ffmpeg_bin
from .editjson import seg_len

SAMPLE_FPS = 2
SAMPLE_W = 360
# A Haar box covers forehead to chin; grow it to the whole head (hair, beard).
GROW_UP, GROW_DOWN, GROW_SIDE = 0.25, 0.15, 0.10


def _frames(src, w: int, h: int):
    """Grey frames at SAMPLE_FPS, SAMPLE_W wide; yields (t, frame)."""
    p = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(src), "-vf",
                        f"fps={SAMPLE_FPS},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, check=True)
    n = len(p.stdout) // (w * h)
    for i in range(n):
        yield i / SAMPLE_FPS, np.frombuffer(p.stdout, np.uint8, w * h, i * w * h).reshape(h, w)


def detect(src) -> dict:
    """{"source": [w, h], "samples": [{"t": s, "box": [x0, y0, x1, y1] | None}]}."""
    import cv2
    info = ffmpeg.probe(src)
    sw, sh = info["width"], info["height"]
    w = SAMPLE_W
    h = round(sh * w / sw / 2) * 2
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    samples = []
    for t, frame in _frames(src, w, h):
        found = cascade.detectMultiScale(frame, scaleFactor=1.1, minNeighbors=5, minSize=(w // 8, w // 8))
        if len(found) == 0:
            samples.append({"t": t, "box": None})
            continue
        x, y, fw, fh = max(found, key=lambda b: b[2] * b[3])
        box = [(x - GROW_SIDE * fw) / w, (y - GROW_UP * fh) / h,
               (x + fw + GROW_SIDE * fw) / w, (y + fh + GROW_DOWN * fh) / h]
        samples.append({"t": t, "box": [round(min(max(v, 0.0), 1.0), 4) for v in box]})
    return {"source": [sw, sh], "samples": samples}


def _to_frame(box: list, source: list, size: tuple, zoom: float) -> list:
    """Source-fraction box -> rendered-frame fractions (cover scale by zoom, centre crop)."""
    sw, sh = source
    W, H = size
    s = max(W * zoom / sw, H * zoom / sh)
    ox, oy = (sw * s - W) / 2, (sh * s - H) / 2
    x0, y0, x1, y1 = box
    return [(x0 * sw * s - ox) / W, (y0 * sh * s - oy) / H, (x1 * sw * s - ox) / W, (y1 * sh * s - oy) / H]


def head_band(faces: dict, segments: list, at: float, dur: float, size: tuple):
    """(top, bottom) of the head as fractions of the frame height over timeline [at, at+dur],
    or None when no face was seen in that span."""
    tops, bottoms, t0 = [], [], 0.0
    for s in segments:
        length, k = seg_len(s), s.get("speed", 1.0)
        lo, hi = max(at, t0), min(at + dur, t0 + length)
        if lo < hi:
            a, b = s["in"] + (lo - t0) * k, s["in"] + (hi - t0) * k
            for x in faces["samples"]:
                if x["box"] and a - 0.5 / SAMPLE_FPS <= x["t"] <= b + 0.5 / SAMPLE_FPS:
                    _, y0, _, y1 = _to_frame(x["box"], faces["source"], size, s.get("zoom", 1.0))
                    tops.append(y0)
                    bottoms.append(y1)
        t0 += length
    if not tops:
        return None
    # 10th/90th percentile: follows the head as it moves but ignores a stray false detection.
    return max(0.0, float(np.percentile(tops, 10))), min(1.0, float(np.percentile(bottoms, 90)))
