"""Brand fonts as TTF for libass and HyperFrames. Sora and Montserrat come from npm; Arabic TTFs from google/fonts on GitHub."""
import io
import os
import subprocess
import tarfile
import tempfile
import threading
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

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
    "Montserrat SemiBold": ("npm", "@fontsource/montserrat", "montserrat-latin-600-normal.woff2"),
    "Montserrat Medium": ("npm", "@fontsource/montserrat", "montserrat-latin-500-normal.woff2"),
    "Almarai": ("url", f"{GF}/almarai/Almarai-Bold.ttf"),
    "Almarai ExtraBold": ("url", f"{GF}/almarai/Almarai-ExtraBold.ttf"),
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
    # a heavy square Kufi for Arabic highlight words: Cairo at its blackest, narrowed to the tall condensed
    # proportions of a commercial display Kufi that has no free release
    "Cairo Black Narrow": ("url", f"{GF}/cairo/Cairo%5Bslnt,wght%5D.ttf", {"wght": 1000, "slnt": 0}, 0.60),
}


def _fetch(family: str, part: Path) -> None:
    kind, *where = SOURCES[family]
    if kind == "url":
        subprocess.run(["curl", "-fsSL", "-o", str(part), where[0]], check=True)
        font = TTFont(part)
        if len(where) > 1:  # a variable font: pin its axes to one static cut, then narrow it
            font = instancer.instantiateVariableFont(font, where[1])
            if len(where) > 2:
                _narrow(font, where[2])
    else:
        package, filename = where
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["npm", "pack", package, "--silent"], cwd=tmp, check=True, capture_output=True)
            with tarfile.open(next(Path(tmp).glob("*.tgz"))) as tf:
                data = tf.extractfile(tf.getmember(f"package/files/{filename}")).read()
        font = TTFont(io.BytesIO(data))
        font.flavor = None
    _name_as(font, family)
    font.save(part)


def _narrow(font: TTFont, sx: float) -> None:
    """Scale every horizontal measure by sx: outlines, advances and side bearings, and the kerning and mark anchors
    in GPOS (so Arabic dots stay on their letters)."""
    glyf, hmtx = font["glyf"], font["hmtx"]
    for name in font.getGlyphOrder():
        g = glyf[name]
        if g.isComposite():
            for comp in g.components:
                comp.x = round(comp.x * sx)
        elif g.numberOfContours > 0:
            g.coordinates.scale((sx, 1))
            g.coordinates.toInt()
        adv, lsb = hmtx[name]
        hmtx[name] = (round(adv * sx), round(lsb * sx))

    seen = set()

    def walk(obj):
        if id(obj) in seen or obj is None or isinstance(obj, (int, float, str, bytes)):
            return
        seen.add(id(obj))
        if isinstance(obj, (list, tuple)):
            for x in obj:
                walk(x)
            return
        for key, val in list(getattr(obj, "__dict__", {}).items()):
            if key in ("XCoordinate", "XPlacement", "XAdvance") and isinstance(val, (int, float)):
                setattr(obj, key, round(val * sx))
            else:
                walk(val)

    if "GPOS" in font:
        walk(font["GPOS"].table)


def _name_as(font: TTFont, family: str) -> None:
    """libass finds a caption font by its family name, so the file must call itself `family`. Fontsource subsets
    carry names like "Montserrat Thin ExtraBold", and some Google Fonts files name the bold cut "Almarai Bold" /
    "Regular" in the Windows table: libass then silently draws the captions in a fallback font."""
    name = font["name"]
    name.removeNames(nameID=16)
    name.removeNames(nameID=17)
    for nid, value in ((1, family), (2, "Bold"), (4, f"{family} Bold")):
        name.setName(value, nid, 3, 1, 0x409)
        name.setName(value, nid, 1, 0, 0)


def _named_right(path: Path, family: str) -> bool:
    with TTFont(path, lazy=True) as f:
        return f["name"].getName(1, 3, 1, 0x409) is not None and str(f["name"].getName(1, 3, 1, 0x409)) == family


def ensure_font(family: str) -> Path:
    if family not in SOURCES:
        raise ValueError(f"unknown font family {family!r}; supported: {sorted(SOURCES)}")
    FONT_CACHE.mkdir(parents=True, exist_ok=True)
    ttf = FONT_CACHE / f"{family.replace(' ', '-').lower()}-700.ttf"
    if ttf.exists() and not _named_right(ttf, family):  # cached before the names were fixed
        font = TTFont(ttf)
        _name_as(font, family)
        part = ttf.with_name(f"{ttf.stem}.{os.getpid()}-{threading.get_ident()}.part")
        font.save(part)
        os.replace(part, ttf)
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
