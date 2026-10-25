"""Overlays: a clip or image composited over the edit at a time and place, above graphics and under captions.

For a character or sticker that has its own animation (a character reacting, peeking in from the edge, a logo pop) and
for full-frame stingers that cover a cut. edit.json `overlays[]` entries:

    {"file", "at", "dur", "src_in"?: 0, "key"?: "alpha"|"green", "color"?: "#00ff00",
     "x"?: 0.5, "y"?: 0.5, "w"?: 1.0, "flip"?: false}

- `key: "alpha"` (default for .mov, .webm, .png, .webp): the file's own transparency. VP8/VP9 WebM alpha is read with
  libvpx, since ffmpeg's built-in VP9 decoder drops it.
- `key: "green"`: a green-screen clip. The screen colour is read from the clip's corners at `src_in` unless `color`
  is given (screens vary: the same generator returns greens from (80, 239, 83) to (148, 209, 129)), then keyed in
  YUV with a soft edge and the green spill taken back out of the outline.
- `w` is the overlay's width as a fraction of the frame; `x`, `y` place its centre (fractions of the frame).
- `flip` mirrors it (a character entering from the other side).
- `layer: "under"` puts it under the graphics (a character behind sticker text); the default is over them.
"""
import subprocess
from pathlib import Path

import numpy as np

from .config import FPS, TO_YUV, ffmpeg_bin, ffprobe_bin

STILL_EXTS = {".png", ".webp", ".jpg", ".jpeg"}
ALPHA_EXTS = {".mov", ".webm", ".png", ".webp"}
KEYS = ("alpha", "green")
GREEN_SIMILARITY = 0.16  # chromakey distance in UV space; wide enough for compressed edges, narrow enough for skin
GREEN_BLEND = 0.08


def key_of(item: dict) -> str:
    return item.get("key") or ("alpha" if Path(item["file"]).suffix.lower() in ALPHA_EXTS else "green")


def _codec(path) -> str:
    p = subprocess.run([ffprobe_bin(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return p.stdout.strip()


def decoder_args(path) -> list:
    """WebM alpha needs libvpx: the native vp8/vp9 decoders ignore the alpha side channel."""
    if Path(path).suffix.lower() != ".webm":
        return []
    return {"vp9": ["-c:v", "libvpx-vp9"], "vp8": ["-c:v", "libvpx"]}.get(_codec(path), [])


def screen_color(path, at: float = 0.0) -> str:
    """The green screen's colour: the median of the four 24 px corners of the frame at `at`."""
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", f"{at:.3f}", "-i", str(path), "-frames:v", "1",
                          "-vf", "scale=360:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    w = 360
    h = len(raw) // (w * 3)
    if not h:
        raise ValueError(f"could not read a frame from {path} at {at:.2f}s")
    img = np.frombuffer(raw[: w * h * 3], np.uint8).reshape(h, w, 3)
    c = 24
    corners = np.concatenate([img[:c, :c], img[:c, -c:], img[-c:, :c], img[-c:, -c:]]).reshape(-1, 3)
    r, g, b = np.median(corners, axis=0).astype(int)
    if not (g > r + 40 and g > b + 40):
        raise ValueError(f"{Path(path).name} corners are rgb({r},{g},{b}), not a green screen; pass 'color' or "
                         "use key 'alpha'")
    return f"#{r:02x}{g:02x}{b:02x}"


def input_args(item: dict, path) -> list:
    at, dur = item["at"], item["dur"]
    if Path(path).suffix.lower() in STILL_EXTS:
        return ["-loop", "1", "-t", f"{dur + 0.2:.3f}", "-itsoffset", f"{at:.3f}", "-i", str(path)]
    # no input -ss: next to -itsoffset it seeks in the shifted timeline and is ignored; src_in is a trim in the graph
    return [*decoder_args(path), "-t", f"{item.get('src_in', 0.0) + dur + 0.2:.3f}", "-itsoffset", f"{at:.3f}",
            "-i", str(path)]


def filter_parts(inputs: list, cur: str, size: tuple, tag: str = "ov") -> tuple[list, str]:
    """inputs: (item, input index, screen colour or None). Returns filter parts and the new current label."""
    W, H = size
    parts = []
    for j, (item, k, color) in enumerate(inputs):
        at, dur = item["at"], item["dur"]
        w = 2 * round(W * item.get("w", 1.0) / 2)
        src_in = 0.0 if Path(item["file"]).suffix.lower() in STILL_EXTS else item.get("src_in", 0.0)
        chain = [f"setpts=PTS-STARTPTS,trim=start={src_in:.3f}", f"setpts=PTS-STARTPTS+{at}/TB", f"fps={FPS}"]
        if color:
            chain += [f"format=yuv444p,chromakey=color=0x{color.lstrip('#')}:similarity={GREEN_SIMILARITY}"
                      f":blend={GREEN_BLEND}", "format=rgba", "despill=type=green:mix=0.6:expand=0.1"]
        chain += [f"scale={w}:-2:flags=lanczos", "format=rgba", TO_YUV]
        if item.get("flip"):
            chain.append("hflip")
        parts.append(f"[{k}:v]{','.join(chain)}[{tag}{j}]")
        x, y = item.get("x", 0.5), item.get("y", 0.5)
        parts.append(f"[{cur}][{tag}{j}]overlay=x='{W * x:.1f}-overlay_w/2':y='{H * y:.1f}-overlay_h/2'"
                     f":enable='between(t,{at:.3f},{at + dur:.3f})':eof_action=pass:format=yuv420[{tag}o{j}]")
        cur = f"{tag}o{j}"
    if inputs:
        parts.append(f"[{cur}]format=yuv420p[{tag}out]")
        cur = f"{tag}out"
    return parts, cur
