import subprocess
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont
from PIL import Image

from editor import captions, fonts
from editor.fonts import ensure_font
from editor.style import load_style


@pytest.mark.slow
@pytest.mark.parametrize("family", ["Sora", "IBM Plex Sans Arabic"])
def test_fonts_fetch_as_ttf(family):
    path = ensure_font(family)
    names = {r.toUnicode() for r in TTFont(path)["name"].names if r.nameID == 1}
    assert path.suffix == ".ttf" and any(family.split()[0] in n for n in names)


@pytest.mark.slow
def test_arabic_ass_renders_with_libass(tmp_path):
    style = load_style()
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    for fam in (style["font"], style["arabic_font"]):
        p = ensure_font(fam)
        (fonts / p.name).write_bytes(p.read_bytes())
    ln = [{"start": 0, "end": 1, "hook": False, "tr": "We went to Acme Library",
           "words": [{"w": "ذهبنا", "start": 0, "end": 0.3}, {"w": "Acme", "start": 0.3, "end": 0.6},
                     {"w": "Library", "start": 0.6, "end": 1.0}]}]
    (tmp_path / "c.ass").write_text(captions.to_ass(ln, style, (1080, 1920), mode="bilingual"), encoding="utf-8")
    base = ["ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i", "color=black:s=1080x1920:d=1"]
    (tmp_path / "empty.ass").write_text(captions.to_ass([], style, (1080, 1920)), encoding="utf-8")
    for ass, png in (("c.ass", "out.png"), ("empty.ass", "blank.png")):
        subprocess.run(base + ["-vf", f"ass={ass}:fontsdir=fonts:shaping=complex", "-frames:v", "1", png],
                       cwd=tmp_path, check=True, capture_output=True)
    assert bright_pixels(tmp_path / "out.png") > 2000
    assert bright_pixels(tmp_path / "blank.png") < 50


def bright_pixels(png) -> int:
    img = Image.open(png).convert("L")
    w, h = img.size
    band = img.crop((0, int(h * 0.12), w, int(h * 0.80)))
    return sum(band.histogram()[129:])


def test_failed_download_leaves_no_font_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(fonts, "FONT_CACHE", tmp_path)

    def fake_run(cmd, **kw):
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"not a font, truncated")

    monkeypatch.setattr(fonts.subprocess, "run", fake_run)
    with pytest.raises(Exception):
        ensure_font("IBM Plex Sans Arabic")
    assert list(tmp_path.iterdir()) == []


def test_unknown_family_names_the_supported_ones(tmp_path, monkeypatch):
    monkeypatch.setattr(fonts, "FONT_CACHE", tmp_path)
    with pytest.raises(ValueError, match="Tajawal"):
        ensure_font("Comic Sans")


def test_a_font_is_named_after_its_family_for_libass(tmp_path):
    # Google's Almarai-Bold.ttf names itself "Almarai Bold" / "Regular" in the Windows table: libass could not find
    # "Almarai" by name and drew the captions in a fallback face.
    from fontTools.ttLib.tables._n_a_m_e import table__n_a_m_e
    font = TTFont()
    font["name"] = table__n_a_m_e()
    font["name"].names = []
    font["name"].setName("Almarai Bold", 1, 3, 1, 0x409)
    font["name"].setName("Regular", 2, 3, 1, 0x409)
    font["name"].setName("Almarai", 16, 3, 1, 0x409)
    fonts._name_as(font, "Almarai")
    n = font["name"]
    assert str(n.getName(1, 3, 1, 0x409)) == "Almarai" and str(n.getName(2, 3, 1, 0x409)) == "Bold"
    assert n.getName(16, 3, 1, 0x409) is None and str(n.getName(1, 1, 0, 0)) == "Almarai"


def test_narrow_scales_outlines_advances_and_mark_anchors():
    # the narrowed highlight face: every horizontal measure shrinks, so Arabic dots stay on their letters
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib.tables import otTables
    pen = TTGlyphPen(None)
    pen.moveTo((100, 0)), pen.lineTo((100, 500)), pen.lineTo((500, 500)), pen.lineTo((500, 0)), pen.closePath()
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "a"])
    fb.setupCharacterMap({0x61: "a"})
    fb.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "a": pen.glyph()})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "a": (600, 100)})
    fb.setupHorizontalHeader()
    font = fb.font
    anchor = otTables.Anchor()
    anchor.Format, anchor.XCoordinate, anchor.YCoordinate = 1, 300, 700
    gpos = type("T", (), {})()
    gpos.table = type("L", (), {})()
    gpos.table.anchors = [anchor]
    font.tables["GPOS"] = gpos
    fonts._narrow(font, 0.5)
    assert font["hmtx"]["a"] == (300, 50)
    assert min(x for x, _ in font["glyf"]["a"].coordinates) == 50
    assert max(x for x, _ in font["glyf"]["a"].coordinates) == 250
    assert (anchor.XCoordinate, anchor.YCoordinate) == (150, 700)
