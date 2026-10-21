"""Natural face retouch, driven by MediaPipe face landmarks (preset "natural" is the default).

Gentle by design (a natural, not airbrushed look). Only LAB lightness changes, in float, so skin colour
can't shift:
- Under-eyes: a band from each lower lid down, curved like the lid. Its broad darkness (puffiness shadow) is lifted
  toward the upper cheek just below; fine detail stays.
- Evening: mid-frequency blotchiness on the skin is reduced; pores, stubble and lines (high frequency) are kept.
- Small marks: skin spots clearly darker than their local median are blended toward it.
Skin is the face oval minus eyes, brows and lips; dark pixels (glasses rims, lashes, beard) and glare are protected.
"""
import subprocess
from pathlib import Path

import cv2
import numpy as np

from .extras import model_path

PRESETS = {"gentle": (0.5, 0.6, 0.2), "natural": (0.85, 0.9, 0.4)}  # (under_eye, marks, even)
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148,
             176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
LOWER_LID = {"r": [33, 7, 163, 144, 145, 153, 154, 155, 133], "l": [263, 249, 390, 373, 374, 380, 381, 382, 362]}
EYE = {"r": [33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7],
       "l": [263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249]}
BROW = {"r": [70, 63, 105, 66, 107, 55, 65, 52, 53, 46], "l": [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]}
LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
CHEEKS = (454, 234)  # face width
RATE = {False: ["-preset", "slow", "-crf", "15", "-profile:v", "high"],
        True: ["-preset", "medium", "-crf", "20", "-maxrate", "3400k", "-bufsize", "6800k"]}


def landmarker(video: bool = True):
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core.base_options import BaseOptions
    mode = vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE
    return vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path("face_landmarker"))), num_faces=1, running_mode=mode))


def landmarks(lm, rgb: np.ndarray, ts_ms: int | None = None):
    """(478, 2) landmark pixels of the largest face, or None."""
    import mediapipe as mp
    img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
    res = lm.detect(img) if ts_ms is None else lm.detect_for_video(img, ts_ms)
    if not res.face_landmarks:
        return None
    H, W = rgb.shape[:2]
    return np.array([(p.x * W, p.y * H) for p in res.face_landmarks[0]], np.float32)


class Smoother:
    """Steady landmarks when the head is still, no lag on fast moves; holds 2 frames through a missed detection."""

    def __init__(self):
        self.prev, self.misses = None, 0

    def update(self, P):
        if P is None:
            self.misses += 1
            return self.prev if self.misses < 3 else None
        if self.prev is not None:
            move = np.linalg.norm(P - self.prev, axis=1).mean() / np.linalg.norm(P[CHEEKS[0]] - P[CHEEKS[1]])
            a = float(np.clip(move * 40, 0.35, 1.0))
            P = a * P + (1 - a) * self.prev
        self.prev, self.misses = P, 0
        return P


def _poly(shape, pts, blur: float = 0) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(pts).astype(np.int32)], 255)
    if blur > 0:
        m = cv2.GaussianBlur(m, (0, 0), blur)
    return m.astype(np.float32) / 255


def retouch_frame(bgr: np.ndarray, P, under_eye: float = 0.85, marks: float = 0.9, even: float = 0.4) -> np.ndarray:
    """One BGR frame; P is (478, 2) landmark pixels or None (frame returned unchanged)."""
    if P is None:
        return bgr
    H, W = bgr.shape[:2]
    fw = float(np.linalg.norm(P[CHEEKS[0]] - P[CHEEKS[1]]))
    x0, y0 = np.maximum(P.min(0) - 0.1 * fw, 0).astype(int)
    x1, y1 = np.minimum(P.max(0) + 0.1 * fw, (W, H)).astype(int)
    if x1 - x0 < 40 or y1 - y0 < 40:
        return bgr
    Q = P - (x0, y0)
    lab = cv2.cvtColor(bgr[y0:y1, x0:x1].astype(np.float32) / 255, cv2.COLOR_BGR2LAB)  # float: exact round trip
    L = lab[..., 0] * 2.55
    shape = L.shape
    protect = np.clip((L - 70) / 25, 0, 1) * np.clip((235 - L) / 15, 0, 1)

    skin = _poly(shape, Q[FACE_OVAL])
    for k in ("r", "l"):
        skin *= (1 - _poly(shape, Q[EYE[k]])) * (1 - _poly(shape, Q[BROW[k]]))
    skin *= 1 - _poly(shape, Q[LIPS])
    skin = cv2.GaussianBlur(cv2.erode(skin, np.ones((3, 3), np.uint8)), (0, 0), fw * 0.01) * protect

    low = cv2.GaussianBlur(L, (0, 0), fw * 0.02)
    out = L.copy()
    down = np.array([0, 1], np.float32)
    for k in ("r", "l"):
        lid = Q[LOWER_LID[k]]
        ew = float(np.linalg.norm(lid[0] - lid[-1]))
        drop = (0.30 + 0.45 * np.sin(np.linspace(0, np.pi, len(lid))))[:, None] * ew * down
        m = _poly(shape, np.vstack([lid + 0.04 * ew * down, (lid + drop)[::-1]]), ew * 0.07)
        cy = int(np.clip(lid[:, 1].mean() + 0.9 * ew, 2, shape[0] - 3))
        xs = slice(int(max(0, lid[:, 0].min())), int(min(shape[1], lid[:, 0].max())) + 1)
        ref = float(np.median(low[cy - 2:cy + 3, xs]))
        out += m * protect * np.clip(ref - low, 0, 35) * under_eye

    if even:
        mid = cv2.GaussianBlur(out, (0, 0), fw * 0.006) - cv2.GaussianBlur(out, (0, 0), fw * 0.03)
        out -= skin * np.clip(mid, -12, 12) * even

    if marks:
        k = max(5, min(int(fw * 0.035) | 1, 255))
        med = cv2.medianBlur(np.clip(out, 0, 255).astype(np.uint8), k).astype(np.float32)
        spot = cv2.GaussianBlur(np.clip((med - out - 5) / 8, 0, 1) * skin, (0, 0), 1.2) * marks
        out += spot * (med - out)

    lab[..., 0] = np.clip(out, 0, 255) / 2.55
    res = bgr.copy()
    res[y0:y1, x0:x1] = np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2BGR) * 255 + 0.5, 0, 255).astype(np.uint8)
    return res


def retouch_video(src, out, preset: str = "natural", size: tuple = (1080, 1920), fps: float | None = None,
                  ass: str | None = None, fonts_dir: str | None = None, chat: bool = False) -> Path:
    """Retouched copy of src at `size` (audio copied), optionally with ASS captions burned in. ~0.2 s a frame.
    Default is a high-quality master (CRF 15, no cap); chat=True caps the rate to fit 30 MB a minute, which the
    looks visibly compressed, so only use it for the chat preview."""
    W, H = size
    if fps is None:  # keep the source frame rate (iPhone clips come at 24, 30 or 60)
        from . import ffmpeg
        raw = ffmpeg.probe(src)["fps"] or 30
        fps = min((23.976, 24, 25, 29.97, 30, 50, 59.94, 60), key=lambda r: abs(r - raw))
    vf = "format=yuv420p"
    if ass:
        vf = f"ass={ass}" + (f":fontsdir={fonts_dir}" if fonts_dir else "") + ":shaping=complex," + vf
    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", str(src), "-vf",
                            f"scale={W}:{H}:flags=lanczos:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},format=bgr24", "-f", "rawvideo", "-pix_fmt", "bgr24",
                            "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                            "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-i", str(src), "-map", "0:v", "-map", "1:a:0?",
                            "-vf", vf, "-c:v", "libx264", *RATE[chat], "-color_primaries", "bt709", "-color_trc", "bt709",
                            "-colorspace", "bt709", "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(out)],
                           stdin=subprocess.PIPE)
    lm, smooth, n, i = landmarker(True), Smoother(), W * H * 3, 0
    try:
        while True:
            buf = dec.stdout.read(n)
            if len(buf) < n:
                break
            frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            P = smooth.update(landmarks(lm, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), int(i * 1000 / fps)))
            enc.stdin.write(retouch_frame(frame, P, *PRESETS[preset]).tobytes())
            i += 1
    finally:
        enc.stdin.close()
        dec.stdout.close()
        enc.wait()
        dec.wait()
    if enc.returncode or dec.returncode:
        raise RuntimeError(f"retouch of {src} failed")
    return Path(out)
