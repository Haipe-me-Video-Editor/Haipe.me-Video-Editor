"""Shared maths for the look effects (outline, color_pop, freeze_callout, motion_echo, film_look, beat_shake,
glitch): the in/out envelope, background treatments and the stroke around the person. Pure numpy + OpenCV on
float frames 0-1. (Private module: the fx registry skips `_` names.)"""
import cv2
import numpy as np


def hex_rgb(c: str | None, default: str = "#ffffff") -> np.ndarray:
    """'#rrggbb' as float 0-1."""
    c = (c or default).lstrip("#")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255


def envelope(t: float, dur: float, enter: float, exit: float) -> float:
    """0 -> 1 over `enter` seconds from the window's start, 1 -> 0 over `exit` before its end (smoothstep)."""
    def s(u):
        u = min(max(u, 0.0), 1.0)
        return u * u * (3 - 2 * u)
    a = s(t / enter) if enter > 0 else 1.0
    b = s((dur - t) / exit) if exit > 0 else 1.0
    return min(a, b)


def luma(F: np.ndarray) -> np.ndarray:
    return F[..., 0] * 0.299 + F[..., 1] * 0.587 + F[..., 2] * 0.114


BG_MODES = ("keep", "mono", "dim", "blur", "tint")


def treat_bg(F: np.ndarray, mode: str, tint=None) -> np.ndarray:
    """The frame as the room should look behind the speaker: keep, mono (contrasty black and white), dim, blur
    (soft and darker, a depth-of-field look) or tint (a duotone in `tint`)."""
    if mode == "keep":
        return F
    if mode == "mono":
        y = np.clip((luma(F) - 0.5) * 1.15 + 0.47, 0, 1)
        return np.repeat(y[..., None], 3, axis=2)
    if mode == "dim":
        return F * 0.35
    if mode == "blur":
        H, W = F.shape[:2]
        small = cv2.resize(F, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        return cv2.resize(cv2.GaussianBlur(small, (0, 0), W / 160), (W, H)) * 0.75
    if mode == "tint":
        y = luma(F)[..., None]
        c = hex_rgb(tint) if isinstance(tint, str) or tint is None else np.asarray(tint, np.float32)
        return np.clip(y * c * 1.25, 0, 1)
    raise ValueError(f"background mode must be one of {BG_MODES}")


def ring(alpha: np.ndarray, width: float, soft: float = 1.0) -> np.ndarray:
    """A stroke `width` px wide just outside the matte (0-1): what a sticker border or a neon line traces."""
    if width < 0.5:
        return np.zeros_like(alpha)
    k = int(2 * round(width) + 1)
    a8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
    grown = cv2.dilate(a8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))).astype(np.float32) / 255
    if soft > 0:  # soften the outer edge only: blurring the whole ring would wash out a thin stroke's core
        grown = np.maximum(cv2.GaussianBlur(grown, (0, 0), soft), alpha)
    return np.clip(grown - alpha, 0, 1)


def over(dst: np.ndarray, colour, a: np.ndarray) -> np.ndarray:
    """dst with `colour` (a triple or an image) laid over at alpha a (H, W)."""
    a = a[..., None]
    return dst * (1 - a) + np.asarray(colour, np.float32) * a


def screen(dst: np.ndarray, light) -> np.ndarray:
    """Screen blend: light only brightens (glows, leaks, halation)."""
    return 1 - (1 - dst) * (1 - np.clip(light, 0, 1))


def to8(F: np.ndarray) -> np.ndarray:
    return (np.clip(F, 0, 1) * 255 + 0.5).astype(np.uint8)
