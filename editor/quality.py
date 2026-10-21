"""Encoder settings for every H.264 step. Normal renders are tuned for speed and a social upload; a master render
(`render --master`, or EDITOR_MASTER=1) keeps every intermediate near-lossless and encodes the final at CRF 10, so
nothing the platforms will see has been lost before their own encode."""
import os

from .config import FINAL_CRF


def master() -> bool:
    return os.environ.get("EDITOR_MASTER") == "1"


def inter(preset: str = "medium", crf: int = 14) -> list:
    """An intermediate clip (the cut base, an effect window, a graphic): the caller's speed-tuned default, or
    near-lossless on a master render."""
    return ["-preset", "medium", "-crf", "6"] if master() else ["-preset", preset, "-crf", str(crf)]


def final(draft: bool = False) -> list:
    """The finished video."""
    if master():
        return ["-preset", "slow", "-crf", "10", "-profile:v", "high"]
    return ["-preset", "veryfast" if draft else "medium", "-crf", "23" if draft else str(FINAL_CRF)]


def audio_kbps() -> str:
    return "320k" if master() else "192k"
