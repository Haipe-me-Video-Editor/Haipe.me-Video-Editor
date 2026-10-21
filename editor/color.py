"""Colour handling: every file the engine writes is standard Rec.709 SDR, tagged as such.

iPhones record HDR by default (HLG or Dolby Vision, 10-bit, BT.2020). Treated as ordinary video those
colours come out pale and greyish, so HDR sources are tone-mapped to SDR once, on import (`to_sdr`).
Converting between YUV and RGB must name the BT.709 matrix: ffmpeg's default is the old BT.601 formula,
which shifts skin tones. Use RGB_IN / RGB_OUT (RGBA_OUT) around any raw RGB processing, and TAGS on every encode.
"""
from pathlib import Path

HDR_TRANSFERS = ("arib-std-b67", "smpte2084")  # HLG, PQ
# HLG/PQ -> linear light -> BT.709 primaries -> gentle Mobius tone map -> Rec.709. npl=150 keeps the
# speaker's warm skin tone and bright-but-not-blown highlights closest to how the phone shows the clip.
SDR_CHAIN = ("zscale=t=linear:npl=150,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=mobius:desat=0,"
             "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")
TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
# zscale, not scale: swscale's YUV<->RGB round trip still shifted a test frame by ~1.8 lightness with a colour
# cast even with the matrices named; zscale's round trip is exact to ~0.01.
RGB_IN = "zscale=matrixin=709:rangein=limited:range=full,format=gbrp"   # then format=bgr24/rgb24 for raw RGB
RGB_OUT = "format=gbrp,zscale=matrix=709:range=limited:rangein=full"    # then format=yuv420p
RGBA_OUT = "format=gbrap,zscale=matrix=709:range=limited:rangein=full"  # with alpha, then format=yuva444p10le


def is_hdr(info: dict) -> bool:
    return (info.get("transfer") or "") in HDR_TRANSFERS


def to_sdr(src, dst, crf: int = 14) -> Path:
    """A Rec.709 SDR copy of an HDR clip (audio copied), for editing."""
    from . import ffmpeg
    ffmpeg.run(["-i", src, "-vf", SDR_CHAIN, "-c:v", "libx264", "-preset", "medium", "-crf", crf,
                "-pix_fmt", "yuv420p", *TAGS, "-c:a", "copy", dst])
    return Path(dst)
