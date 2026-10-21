"""Run ffmpeg and read media facts with ffprobe."""
import json
import subprocess
from pathlib import Path

from .config import ffmpeg_bin, ffprobe_bin


class FFmpegError(RuntimeError):
    pass


def run(args: list, cwd: Path | None = None) -> str:
    """Run ffmpeg; return its log (stderr). Raise FFmpegError with the log tail on failure."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", *map(str, args)]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if p.returncode != 0:
        raise FFmpegError(f"ffmpeg exited {p.returncode}\n$ {' '.join(cmd)}\n{p.stderr[-4000:]}")
    return p.stderr


def run_bytes(args: list) -> bytes:
    """Run ffmpeg writing raw output to stdout; return it."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", *map(str, args)]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise FFmpegError(f"ffmpeg exited {p.returncode}\n$ {' '.join(cmd)}\n{p.stderr.decode()[-4000:]}")
    return p.stdout


def probe(path) -> dict:
    p = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {path}: {p.stderr.strip()}")
    data = json.loads(p.stdout)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    info = {
        "duration": float(data["format"].get("duration", 0.0)),
        "has_audio": audio is not None,
        "width": None, "height": None, "fps": None, "pix_fmt": None, "transfer": None,
    }
    if video:
        w, h = int(video["width"]), int(video["height"])
        if abs(_rotation(video)) in (90, 270):  # phone footage stores portrait as rotated landscape
            w, h = h, w
        num, den = (video.get("avg_frame_rate") or "0/1").split("/")
        info.update(width=w, height=h, pix_fmt=video.get("pix_fmt"), transfer=video.get("color_transfer"),
                    fps=float(num) / float(den) if float(den) else None)
    return info


def read_pcm(path, sr: int = 16000):
    """Decode the audio track to mono float32 samples."""
    import numpy as np
    p = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
                        "-f", "s16le", "-"], capture_output=True)
    if p.returncode != 0:
        raise FFmpegError(f"could not decode audio from {path}: {p.stderr.decode()[-500:]}")
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _rotation(stream: dict) -> int:
    for side in stream.get("side_data_list", []):
        if "rotation" in side:
            return int(side["rotation"])
    return int(stream.get("tags", {}).get("rotate", 0))
