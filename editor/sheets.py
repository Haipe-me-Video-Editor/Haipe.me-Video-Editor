"""Contact sheets: one image of evenly spaced thumbnails, so Claude can see a clip cheaply."""
from pathlib import Path

from . import ffmpeg


def contact_sheet(src, out, cols: int = 4, rows: int = 3, thumb_w: int = 240,
                  start: float = 0.0, end: float | None = None) -> list:
    end = end if end is not None else ffmpeg.probe(src)["duration"]
    n = cols * rows
    span = max(end - start, 0.1)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(["-ss", start, "-t", span, "-i", src,
                "-vf", f"fps={n / span},scale={thumb_w}:-2,tile={cols}x{rows}",
                "-frames:v", "1", "-q:v", "4", out])
    return [round(start + span * i / n, 2) for i in range(n)]
