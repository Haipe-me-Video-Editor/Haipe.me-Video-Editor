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
