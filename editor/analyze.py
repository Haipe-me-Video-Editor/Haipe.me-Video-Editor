"""Measurements taken by ffmpeg filters, parsed from its log."""
import json
import re

from . import ffmpeg


def silences(path, noise_db: float = -35, min_dur: float = 0.35, duration: float | None = None) -> list:
    log = ffmpeg.run(["-i", path, "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}", "-vn", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+(?:e[-+]?\d+)?)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+(?:e[-+]?\d+)?)", log)]
    if len(ends) < len(starts):  # silence runs to the end of the file
        ends.append(duration if duration is not None else ffmpeg.probe(path)["duration"])
    return [[round(max(0.0, s), 3), round(e, 3)] for s, e in zip(starts, ends)]


def loudness(path, target: float = -14.0) -> dict:
    log = ffmpeg.run(["-i", path, "-af", f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json",
                      "-vn", "-f", "null", "-"])
    blob = json.loads(log[log.rindex("{"):log.rindex("}") + 1])
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    return {k: float(blob[k]) for k in keys}


def scenes(path, threshold: float = 0.3) -> list:
    log = ffmpeg.run(["-i", path, "-vf", f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"])
    return [round(float(x), 3) for x in re.findall(r"pts_time:([\d.]+(?:e[-+]?\d+)?)", log)]


def black_frames(path) -> list:
    log = ffmpeg.run(["-i", path, "-vf", "blackdetect=d=0.3:pix_th=0.10", "-an", "-f", "null", "-"])
    return [round(float(x), 3) for x in re.findall(r"black_start:([\d.]+(?:e[-+]?\d+)?)", log)]


def frozen_ranges(path, noise: float = 0.001, min_dur: float = 1.5, duration: float | None = None) -> list:
    """[[start, end], ...] where the picture does not change (ffmpeg freezedetect; noise 0.001 = -60 dB)."""
    log = ffmpeg.run(["-i", path, "-vf", f"freezedetect=n={noise}:d={min_dur}", "-an", "-f", "null", "-"])
    return parse_freezes(log, duration if duration is not None else (lambda: ffmpeg.probe(path)["duration"]))


def parse_freezes(log: str, duration) -> list:
    """Freeze ranges from a freezedetect log. A freeze that runs to the end has no freeze_end: it ends at
    `duration` (a number, or a callable that returns one, called only then)."""
    num = r"(-?[\d.]+(?:e[-+]?\d+)?)"
    starts = [float(x) for x in re.findall(r"freeze_start: " + num, log)]
    ends = [float(x) for x in re.findall(r"freeze_end: " + num, log)]
    if len(ends) < len(starts):
        ends.append(duration() if callable(duration) else duration)
    return [[round(max(0.0, a), 3), round(b, 3)] for a, b in zip(starts, ends)]


def rms_db(path, hop: float = 0.01):
    """Loudness envelope in dBFS, one value per `hop` seconds."""
    import numpy as np
    pcm = ffmpeg.read_pcm(path, 16000)
    n = max(1, int(hop * 16000))
    frames = len(pcm) // n
    x = pcm[:frames * n].reshape(frames, n)
    return 20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-9)
