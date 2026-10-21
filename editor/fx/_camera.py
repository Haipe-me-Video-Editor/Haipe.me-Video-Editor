"""Camera-move maths shared by the camera effects (vertigo, zoom_through, pull_back, digital_zoom): eases, springs,
zoom warps with real (multi-sample) motion blur, a damped shake, and face anchors. Pure numpy + OpenCV; no
rendering here beyond warping a frame you already have. (Private module: the fx registry skips `_` names.)"""
import math

import numpy as np

from ..graphics.spring import PRESETS, spring

EASES = ("linear", "in", "out", "inout", "expo")


def ease(name: str, u: float) -> float:
    """0..1 -> 0..1. inout is a cubic smoothstep, out/in are cubic, expo is a fast-start exponential out."""
    u = min(max(float(u), 0.0), 1.0)
    if name == "linear":
        return u
    if name == "in":
        return u ** 3
    if name == "out":
        return 1 - (1 - u) ** 3
    if name == "expo":
        return 1.0 if u >= 1 else 1 - 2 ** (-10 * u)
    if name == "inout":
        return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2
    raise ValueError(f"unknown ease {name!r}; one of {EASES}")


_SPRINGS = {}


def spring_ease(preset: str = "snappy"):
    """The house spring (same curves as the GSAP springIn presets) as a Python ease t -> value (may overshoot)."""
    if preset not in _SPRINGS:
        if preset not in PRESETS:
            raise ValueError(f"unknown spring preset {preset!r}; one of {sorted(PRESETS)}")
        _SPRINGS[preset] = spring(*PRESETS[preset])
    return _SPRINGS[preset]


def zoom_matrix(c_src, s: float, c_dst=None, rot_deg: float = 0.0) -> np.ndarray:
    """2x3 affine: scale by s (and rotate) about source point c_src, landing it on c_dst (default c_src)."""
    cx, cy = c_src
    dx, dy = c_dst if c_dst is not None else c_src
    a = math.radians(rot_deg)
    ca, sa = s * math.cos(a), s * math.sin(a)
    return np.array([[ca, -sa, dx - ca * cx + sa * cy], [sa, ca, dy - sa * cx - ca * cy]], np.float64)


def cover_dst(c_src, s: float, c_dst, size) -> tuple:
    """Move c_dst so that scaling the frame by s (>= 1) about c_src still covers the whole output (no edges)."""
    W, H = size
    cx, cy = c_src
    dx, dy = c_dst
    # the scaled frame spans [dx - s*cx, dx + s*(W - cx)]; it must contain [0, W]
    dx = min(max(dx, W - s * (W - cx)), s * cx)
    dy = min(max(dy, H - s * (H - cy)), s * cy)
    return dx, dy


def blur_samples(s0: float, s1: float, max_px: float, cap: int = 24) -> list:
    """Scales to average for a zoom from s0 to s1 within one shutter: geometric steps, ~1 sample per 3 px of the
    longest streak (max_px = distance of the frame corner from the zoom centre, in output pixels)."""
    if s0 <= 0 or s1 <= 0:
        raise ValueError("scales must be positive")
    streak = abs(math.log(s1 / s0)) * max_px
    n = int(min(cap, max(1, math.ceil(streak / 3))))
    if n == 1:
        return [s1]
    return [s0 * (s1 / s0) ** (i / (n - 1)) for i in range(n)]


def zoom_frame(img: np.ndarray, c_src, scales, c_dst=None, rot_deg: float = 0.0, size=None) -> np.ndarray:
    """img zoomed about c_src by each scale in `scales`, averaged (radial motion blur when they differ)."""
    import cv2
    H, W = img.shape[:2]
    size = size or (W, H)
    if np.isscalar(scales):
        scales = [scales]
    if len(scales) == 1:
        return cv2.warpAffine(img, zoom_matrix(c_src, scales[0], c_dst, rot_deg), size, flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)
    acc = np.zeros((size[1], size[0], img.shape[2]), np.float32)
    for s in scales:
        acc += cv2.warpAffine(img, zoom_matrix(c_src, s, c_dst, rot_deg), size, flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)
    return np.clip(acc / len(scales) + 0.5, 0, 255).astype(np.uint8)


def corner_dist(c, size) -> float:
    W, H = size
    return max(math.hypot(x - c[0], y - c[1]) for x in (0, W) for y in (0, H))


def shake(t: float, amp_px: float, dur: float = 0.32, freq: float = 17.0, seed: int = 3) -> tuple:
    """A damped camera shake starting at t=0: (dx, dy, rot_deg). Deterministic; zero before 0 and after dur."""
    if t < 0 or t > dur or amp_px <= 0:
        return 0.0, 0.0, 0.0
    env = (1 - t / dur) ** 2
    ph = [0.0, 1.9, 4.1] if seed == 3 else list(np.random.default_rng(seed).uniform(0, 6.28, 3))
    w = 2 * math.pi * freq
    return (amp_px * env * math.sin(w * t + ph[0]), 0.7 * amp_px * env * math.sin(1.31 * w * t + ph[1]),
            0.35 * env * amp_px / 12 * math.sin(0.87 * w * t + ph[2]))


TARGETS = ("face", "eye", "mouth", "center")


def face_point(P, target: str, size) -> tuple:
    """A point on a (478, 2) MediaPipe face: face (between the eyes), eye (the one nearer frame centre), mouth."""
    W, H = size
    if target == "center" or P is None:
        return W / 2, H / 2
    if target == "mouth":
        return tuple(P[[13, 14]].mean(0))
    if target == "eye":
        l, r = P[[33, 133]].mean(0), P[[362, 263]].mean(0)
        return tuple(l if abs(l[0] - W / 2) < abs(r[0] - W / 2) else r)
    return tuple(P[168])  # face: the bridge between the eyes


def resolve_target(target, landmarks: list, idx, size, fallback=None) -> tuple:
    """target is a name (TARGETS) or [x, y] in 0-1; landmarks per frame; idx the frames to take the median over."""
    W, H = size
    if isinstance(target, (list, tuple)):
        return float(target[0]) * W, float(target[1]) * H
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS} or [x, y]")
    pts = [face_point(landmarks[i], target, size) for i in idx if 0 <= i < len(landmarks) and landmarks[i] is not None]
    if target == "center" or not pts:
        return fallback or (W / 2, H * (0.5 if target == "center" else 0.33))
    return tuple(np.median(np.array(pts), axis=0))


def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)
