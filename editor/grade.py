"""Colour grade for phone footage: neutral white balance, real blacks and whites, then a look.

Phone clips shot indoors under warm lights come out yellow and flat. `measure` samples a clip and finds
(1) the colour cast, from the pixels that should be grey (low saturation, mid brightness), and (2) how far
its darkest and brightest tones sit from black and white. `chain` turns that into an ffmpeg filter chain:
channel gains for the white balance (partial, so the room keeps a little warmth), a levels stretch, then
one of the LOOKS. Everything runs in 16-bit RGB between exact zscale conversions, so nothing bands or shifts.
"""
import subprocess

import numpy as np

from . import color

WB_STRENGTH = 1.0  # share of the cast removed: whites and greys land on true neutral
LEVELS_STRENGTH = 0.7  # share of the gap to true black and white that is closed
GAIN_LIMIT = (0.8, 1.25)
# Real white-balance errors run mostly along the warm-cool axis. A strong green-magenta "error" usually means
# coloured stage or LED light; neutralising it fully turns skin sallow and walls teal, so that part is capped.
TINT_LIMIT = 0.06  # log gain, about 6%
RGB16_IN = color.RGB_IN.replace("format=gbrp", "format=gbrp16le")
# Looks, applied after white balance and levels. Contrast is an S-curve on brightness only (the Y plane), so
# colours keep their saturation: the aim is clean, true colour, not boosted colour. `tint` is a split
# tone (cool shadows, warm highlights) in RGB with luminosity kept; `sharp` is contrast-adaptive sharpening.
LOOKS = {
    "clean": {"contrast": 0.12},
    "punchy": {"contrast": 0.25, "sharp": 0.35},
    "cinematic": {"contrast": 0.18, "tint": "colorbalance=rs=-0.04:bs=0.04:rh=0.03:bh=-0.03:pl=1"},
}


def _s_curve(k: float) -> str:
    """lutyuv expression: an S-curve of strength k on video-range luma (0 = none)."""
    x = "((val-16)/219)"
    return f"lutyuv=y='clip(16+219*({x}-{k}*sin(2*PI*{x})/(2*PI)),16,235)'"


def _sample(src, times: list, width: int = 320) -> np.ndarray:
    """RGB frames (0-1 floats) at the given source seconds, small."""
    frames = []
    for t in times:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                              "-vf", f"scale={width}:-2,{color.RGB_IN},format=rgb24", "-f", "rawvideo", "-"],
                             capture_output=True, check=True).stdout
        if raw:
            frames.append(np.frombuffer(raw, np.uint8).reshape(-1, width, 3))
    if not frames:
        raise RuntimeError(f"could not read frames from {src}")
    return np.concatenate(frames).astype(np.float32) / 255


def white_balance(px: np.ndarray) -> np.ndarray:
    """Per-channel gains that make the scene's neutral surfaces (walls, ceilings, white boards, paper) neutral.

    Iterative grey-pixel search: pixels that are near-grey under the current correction vote for the cast, the
    correction is updated, and the test tightens each round. Starting loose lets a strongly tinted white wall
    count as grey; ending tight keeps skin, wood and coloured products out. Brighter pixels weigh more (light
    surfaces show the light's colour most faithfully); clipped pixels are skipped."""
    px = px.reshape(-1, 3)
    ok = (px.max(1) < 0.98) & (px.min(1) > 0.04)
    p, gains = px[ok], np.ones(3, np.float32)
    for tol in (0.45, 0.3, 0.2, 0.12, 0.08):
        c = p * gains
        luma = c.mean(1)
        grey = ((c.max(1) - c.min(1)) / np.maximum(luma, 1e-3) < tol) & (luma > 0.2)
        if grey.sum() < 0.002 * len(p):
            break
        w = luma[grey] ** 2
        mean = (p[grey] * w[:, None]).sum(0) / w.sum()
        gains = mean.mean() / np.maximum(mean, 1e-3)
    gains = 1 + WB_STRENGTH * (gains / gains[1] - 1)  # green fixed, so brightness barely moves
    lr, lb = np.log(np.clip(gains[[0, 2]], 1e-3, None))
    temp, tint = (lr - lb) / 2, -(lr + lb) / 2  # warm-cool and green-magenta parts of the correction
    tint = float(np.clip(tint, -TINT_LIMIT, TINT_LIMIT))
    gains = np.array([np.exp(temp - tint), 1.0, np.exp(-temp - tint)], np.float32)
    return np.clip(gains, *GAIN_LIMIT)


def measure_rgb(rgb: np.ndarray) -> dict:
    """White-balance gains and levels for an RGB image (0-1 floats, any shape ending in 3)."""
    px = rgb.reshape(-1, 3)
    mx, mn = px.max(1), px.min(1)
    gains = white_balance(px)
    # Levels from the extreme channels, not brightness: a bright red shirt must not be pushed past white.
    lo, hi = np.percentile(mn, 0.5), min(1.0, np.percentile(mx * gains.max(), 99.5))
    return {"gains": [round(float(g), 4) for g in gains],
            "black": round(float(lo) * LEVELS_STRENGTH, 4),
            "white": round(1 - (1 - float(hi)) * LEVELS_STRENGTH, 4)}


def measure(src, start: float, end: float, samples: int = 5) -> dict:
    """Gains and levels for src[start, end], from a few evenly spaced frames."""
    times = np.linspace(start, max(start, end - 0.05), samples)
    return measure_rgb(_sample(src, list(times)))


def chain(m: dict, look: str = "clean") -> str:
    """ffmpeg filters (YUV in, YUV out) that apply the measured correction and the look."""
    r, g, b = m["gains"]
    lo, hi = m["black"], max(m["white"], m["black"] + 0.2)
    parts = [RGB16_IN, f"colorchannelmixer=rr={r}:gg={g}:bb={b}",
             f"colorlevels=rimin={lo}:gimin={lo}:bimin={lo}:rimax={hi}:gimax={hi}:bimax={hi}"]
    spec = LOOKS[look] if look else {}
    if spec.get("tint"):
        parts.append(spec["tint"])
    parts.append(color.RGB_OUT + ",format=yuv444p")
    if spec.get("contrast"):
        parts.append(_s_curve(spec["contrast"]))
    if spec.get("sharp"):
        parts.append(f"cas=strength={spec['sharp']}")
    return ",".join(parts)
