"""Brand fonts as TTF for libass and HyperFrames. Sora and Montserrat come from npm; Arabic TTFs from google/fonts on GitHub."""
import io
import os
import subprocess
import tarfile
import tempfile
import threading
from pathlib import Path

from fontTools.ttLib import TTFont

from .config import FONT_CACHE

GF = "https://raw.githubusercontent.com/google/fonts/main/ofl"
SOURCES = {
    "Sora": ("npm", "@fontsource/sora", "sora-latin-700-normal.woff2"),
    "Sora Light": ("npm", "@fontsource/sora", "sora-latin-300-normal.woff2"),
    "Sora ExtraLight": ("npm", "@fontsource/sora", "sora-latin-200-normal.woff2"),
    "Roboto": ("npm", "@fontsource/roboto", "roboto-latin-700-normal.woff2"),
    "Roboto Black": ("npm", "@fontsource/roboto", "roboto-latin-900-normal.woff2"),
    "IBM Plex Sans Arabic": ("url", f"{GF}/ibmplexsansarabic/IBMPlexSansArabic-Bold.ttf"),
    "Tajawal": ("url", f"{GF}/tajawal/Tajawal-Bold.ttf"),
    "Montserrat": ("npm", "@fontsource/montserrat", "montserrat-latin-800-normal.woff2"),
    "Bebas Neue": ("url", f"{GF}/bebasneue/BebasNeue-Regular.ttf"),
    "IBM Plex Mono": ("url", f"{GF}/ibmplexmono/IBMPlexMono-Medium.ttf"),
    "Tajawal Medium": ("url", f"{GF}/tajawal/Tajawal-Medium.ttf"),
    "Tajawal ExtraBold": ("url", f"{GF}/tajawal/Tajawal-ExtraBold.ttf"),
    "Tajawal Black": ("url", f"{GF}/tajawal/Tajawal-Black.ttf"),
    "Anton": ("url", f"{GF}/anton/Anton-Regular.ttf"),
    "Lalezar": ("url", f"{GF}/lalezar/Lalezar-Regular.ttf"),
    "Orbitron": ("url", f"{GF}/orbitron/Orbitron%5Bwght%5D.ttf"),
    "Instrument Serif": ("url", f"{GF}/instrumentserif/InstrumentSerif-Regular.ttf"),
    "Instrument Serif Italic": ("url", f"{GF}/instrumentserif/InstrumentSerif-Italic.ttf"),
    "Amiri": ("url", f"{GF}/amiri/Amiri-Regular.ttf"),
}


def _fetch(family: str, part: Path) -> None:
    kind, *where = SOURCES[family]
    if kind == "url":
        subprocess.run(["curl", "-fsSL", "-o", str(part), where[0]], check=True)
        return
    package, filename = where
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["npm", "pack", package, "--silent"], cwd=tmp, check=True, capture_output=True)
        with tarfile.open(next(Path(tmp).glob("*.tgz"))) as tf:
            data = tf.extractfile(tf.getmember(f"package/files/{filename}")).read()
    font = TTFont(io.BytesIO(data))
    font.flavor = None
    # Fontsource subsets can carry names like "Montserrat Thin ExtraBold"; libass matches captions by family.
    name = font["name"]
    name.removeNames(nameID=16)
    name.removeNames(nameID=17)
    for nid, value in ((1, family), (2, "Bold"), (4, f"{family} Bold")):
        name.setName(value, nid, 3, 1, 0x409)
    font.save(part)


def ensure_font(family: str) -> Path:
    if family not in SOURCES:
        raise ValueError(f"unknown font family {family!r}; supported: {sorted(SOURCES)}")
    FONT_CACHE.mkdir(parents=True, exist_ok=True)
    ttf = FONT_CACHE / f"{family.replace(' ', '-').lower()}-700.ttf"
    if ttf.exists():
        return ttf
    part = ttf.with_name(f"{ttf.stem}.{os.getpid()}-{threading.get_ident()}.part")  # graphics render in parallel
    try:
        _fetch(family, part)
        TTFont(part).close()
        os.replace(part, ttf)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return ttf
