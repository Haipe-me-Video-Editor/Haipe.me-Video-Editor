"""Film look: the phone footage finished like a film print. Lifted blacks and a warm grade, halation (a red glow
bleeding off the highlights), moving grain, a gentle gate weave, a vignette, the odd speck of dust and an optional
light leak drifting across the frame. Procedural, on the real footage: no stock overlay, nothing generated."""
import math

import cv2
import numpy as np

from . import _looks as L

NAME = "film_look"
DOC = ("Analog film finish: warm grade, halation, grain, gate weave, vignette, dust, optional light leak. For a "
       "story, a memory or a calm intro; works on any length.")
BEST_FOR = ["any", "playful"]
DUR = (0.5, 60)
PARAMS = {
    "grain": 0.5,      # 0-1
    "halation": 0.5,   # 0-1: red glow around highlights
    "weave": 0.5,      # 0-1: the frame drifts a pixel or two like film in a gate
    "warmth": 0.4,     # 0-1: warm highlights, teal-ish shadows
    "fade": 0.35,      # 0-1: lifted blacks
    "vignette": 0.5,   # 0-1
    "dust": 0.3,       # 0-1: chance of specks on a frame
    "leak": False,     # a warm light leak drifting across the frame
    "enter": 0.0,      # s: fade the look in (0: on from the first frame, for a hard cut)
    "exit": 0.0,
    "seed": 7,
}


def grade(F: np.ndarray, warmth: float, fade: float) -> np.ndarray:
    y = L.luma(F)[..., None]
    lo, hi = np.clip(1 - y * 2, 0, 1), np.clip(y * 2 - 1, 0, 1)
    warm = np.array([0.06, 0.02, -0.05], np.float32) * warmth
    cool = np.array([-0.03, 0.01, 0.03], np.float32) * warmth
    G = F + hi * warm + lo * cool
    G = fade * 0.09 + G * (1 - fade * 0.13)  # lifted blacks, softer whites
    return np.clip(G, 0, 1)


def halate(F: np.ndarray, amount: float) -> np.ndarray:
    H, W = F.shape[:2]
    hi = np.clip((L.luma(F) - 0.72) / 0.28, 0, 1)
    small = cv2.resize(hi, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    glow = cv2.resize(cv2.GaussianBlur(small, (0, 0), W / 240), (W, H))
    return L.screen(F, glow[..., None] * np.array([1.0, 0.32, 0.18], np.float32) * 0.55 * amount)


def vignette_mask(H: int, W: int, amount: float) -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    return (1 - amount * 0.55 * np.clip((r - 0.45) / 0.55, 0, 1) ** 1.6)[..., None]


def grain_field(H: int, W: int, rng, amount: float) -> np.ndarray:
    g = rng.normal(0, 1, (H // 2, W // 2)).astype(np.float32)
    g = cv2.resize(cv2.GaussianBlur(g, (0, 0), 0.7), (W, H))
    return g * 0.045 * amount


def dust(H: int, W: int, rng, chance: float) -> np.ndarray:
    m = np.zeros((H, W), np.float32)
    if rng.random() > chance:
        return m
    for _ in range(rng.integers(1, 4)):
        c = (int(rng.uniform(0, W)), int(rng.uniform(0, H)))
        if rng.random() < 0.7:
            cv2.circle(m, c, int(rng.uniform(1, W / 500 + 2)), 1.0, -1, cv2.LINE_AA)
        else:  # a hair
            ang, ln = rng.uniform(0, math.pi), rng.uniform(W / 60, W / 18)
            d = (int(c[0] + ln * math.cos(ang)), int(c[1] + ln * math.sin(ang)))
            cv2.line(m, c, d, 0.8, max(1, W // 900), cv2.LINE_AA)
    return cv2.GaussianBlur(m, (0, 0), 0.6)


def leak_light(H: int, W: int, t: float, dur: float) -> np.ndarray:
    u = t / max(dur, 1e-6)
    cx, cy = W * (1.15 - 0.9 * u), H * (0.2 + 0.25 * math.sin(u * math.pi))
    yy, xx = np.mgrid[0:H // 8, 0:W // 8].astype(np.float32) * 8
    d = np.sqrt(((xx - cx) / (W * 0.55)) ** 2 + ((yy - cy) / (H * 0.35)) ** 2)
    blob = np.exp(-d * d * 2.2) * (0.6 + 0.4 * math.sin(t * 2.3) ** 2)
    blob = cv2.resize(blob, (W, H))
    return blob[..., None] * np.array([1.0, 0.55, 0.2], np.float32) * 0.6


def render(ctx):
    P = {k: ctx.param(k, v) for k, v in PARAMS.items()}
    rng = np.random.default_rng(int(P["seed"]))
    H, W = ctx.H, ctx.W
    vig = vignette_mask(H, W, float(P["vignette"]))
    weave_px = float(P["weave"]) * W / 540
    with ctx.writer() as w:
        for i, f in enumerate(ctx.frames()):
            t = i / ctx.fps
            p = L.envelope(t, (ctx.n - 1) / ctx.fps, float(P["enter"]), float(P["exit"]))
            F = f.astype(np.float32) / 255
            if p <= 1e-3:
                w(f)
                continue
            if weave_px > 0:
                dx = weave_px * (0.6 * math.sin(t * 5.1) + 0.4 * math.sin(t * 13.7 + 1))
                dy = weave_px * 0.8 * math.sin(t * 3.3 + 2) + rng.normal(0, weave_px * 0.15)
                M = np.float32([[1.012, 0, -W * 0.006 + dx], [0, 1.012, -H * 0.006 + dy]])
                F = cv2.warpAffine(F, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            G = grade(F, float(P["warmth"]), float(P["fade"]))
            G = halate(G, float(P["halation"]))
            if P["leak"]:
                G = L.screen(G, leak_light(H, W, t, ctx.dur))
            G = G * vig + grain_field(H, W, rng, float(P["grain"]))[..., None]
            specks = dust(H, W, rng, float(P["dust"]))
            G = G * (1 - specks[..., None] * 0.85) + specks[..., None] * 0.04
            w(L.to8(F + (G - F) * p if p < 1 else G))
    return ctx.out
