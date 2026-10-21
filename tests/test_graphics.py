from pathlib import Path

import pytest

from editor import ffmpeg
from editor.graphics import render as gr
from editor.graphics.composition import composition_html
from editor.graphics.render import render_graphic
from editor.style import load_style

STYLE = load_style()
FONTS = {"latin": "latin.ttf", "arabic": "arabic.ttf"}


def test_composition_follows_the_hyperframes_contract():
    html = composition_html({"type": "list", "dur": 2.0, "items": ["Pick a day", "<b>x</b>"]}, STYLE, (1080, 1920), FONTS)
    assert 'data-composition-id="g"' in html and 'data-duration="2.0"' in html
    assert 'window.__timelines["g"]' in html and "gsap.min.js" in html
    assert "@font-face" in html and "&lt;b&gt;" in html  # text is escaped
    assert "cdn" not in html.lower()


def test_arabic_text_is_rtl_with_arabic_font():
    html = composition_html({"type": "hook", "dur": 1.0, "text": "اليوم نطلق"}, STYLE, (1080, 1920), FONTS)
    assert 'dir="rtl"' in html and "BrandAR" in html


def test_graphic_text_uses_western_digits():
    spec = {"type": "stat", "dur": 1.0, "value": "٣٠٪", "label": "زيادة"}
    html = composition_html(spec, STYLE, (1080, 1920), FONTS)
    assert ">30٪<" in html and "٣" not in html


def test_lower_third_mirrors_for_rtl():
    ar = composition_html({"type": "lower_third", "dur": 1.0, "name": "سارة"}, STYLE, (1080, 1920), FONTS)
    en = composition_html({"type": "lower_third", "dur": 1.0, "name": "Sara"}, STYLE, (1080, 1920), FONTS)
    assert 'data-duration="1.0" dir="rtl">' in ar and 'class="card lower"' in ar
    assert ".lower{width:auto;" in ar  # inside the flex slot, an RTL root starts it on the right
    assert 'data-duration="1.0">' in en  # LTR root keeps the left-anchored lower third


def _fake_hf(monkeypatch, duration=1.0):
    calls = []
    monkeypatch.setattr(gr, "_hf", lambda args, cwd: calls.append((args[0], Path(cwd))))
    monkeypatch.setattr(gr.ffmpeg, "probe", lambda p: {"pix_fmt": "yuva444p12le", "duration": duration})
    return calls


def _custom(root, html='<script src="gsap.min.js"></script>'):
    comp = root / "work" / "custom-1"
    comp.mkdir(parents=True)
    (comp / "index.html").write_text(html, encoding="utf-8")
    return comp


def test_custom_dir_is_relative_to_the_project(tmp_path, monkeypatch):
    calls = _fake_hf(monkeypatch)
    comp = _custom(tmp_path / "proj")
    spec = {"type": "custom", "dir": "work/custom-1", "at": 0, "dur": 1.0}
    render_graphic(spec, STYLE, (1080, 1920), tmp_path / "g.mov", project=tmp_path / "proj")
    assert calls == [("lint", comp.resolve()), ("render", comp.resolve())]
    calls.clear()
    render_graphic(dict(spec, dir=str(comp)), STYLE, (1080, 1920), tmp_path / "g.mov", project=tmp_path / "elsewhere")
    assert calls[0] == ("lint", comp.resolve())


@pytest.mark.parametrize("name, text", [
    ("index.html", '<script src="https://cdn.jsdelivr.net/npm/gsap.js"></script>'),
    ("index.html", "<link href='http://fonts.googleapis.com/css2?family=Sora' rel=stylesheet>"),
    ("style.css", '@import "https://fonts.googleapis.com/css2?family=Sora";'),
    ("style.css", "@font-face{src:url( https://example.com/f.woff2)}"),
    ("app.js", 'img.src = "x"; el.style.background = "url(\'http://x.test/a.png\')"'),
    ("app.mjs", 'import { gsap } from "https://esm.sh/gsap";'),
    ("app.js", 'const m = await import("https://esm.sh/gsap");'),
    ("app.js", 'fetch("https://api.example.com/data.json")'),
    ("index.html", '<img srcset="https://x.test/a.png 2x">'),
    ("logo.svg", '<svg><image href="https://x.test/a.png"/></svg>'),
])
def test_custom_graphics_refuse_remote_assets(tmp_path, monkeypatch, name, text):
    calls = _fake_hf(monkeypatch)
    comp = _custom(tmp_path)
    (comp / name).write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="local"):
        render_graphic({"type": "custom", "dir": str(comp), "dur": 1.0}, STYLE, (1080, 1920), tmp_path / "g.mov")
    assert calls == []


def test_links_in_text_are_not_assets(tmp_path, monkeypatch):
    _fake_hf(monkeypatch)
    comp = _custom(tmp_path, '<p>see https://example.app</p><script src="gsap.min.js"></script>')
    render_graphic({"type": "custom", "dir": str(comp), "dur": 1.0}, STYLE, (1080, 1920), tmp_path / "g.mov")


def test_render_refuses_a_wrong_length(tmp_path, monkeypatch):
    _fake_hf(monkeypatch, duration=1.5)
    comp = _custom(tmp_path)
    with pytest.raises(RuntimeError, match="1.50s"):
        render_graphic({"type": "custom", "dir": str(comp), "dur": 1.0}, STYLE, (1080, 1920), tmp_path / "g.mov")


@pytest.mark.slow
@pytest.mark.parametrize("spec", [
    {"type": "list", "dur": 1.0, "items": ["Pick a day", "Set the reach"]},
    {"type": "hook", "dur": 1.0, "text": "اليوم نطلق"},
])
def test_render_is_transparent_and_right_length(tmp_path, spec):
    out = render_graphic(spec, STYLE, (1080, 1920), tmp_path / "g.mov")
    info = ffmpeg.probe(out)
    assert "a" in (info["pix_fmt"] or "")[:5]  # yuva… / rgba / argb carry alpha
    assert info["duration"] == pytest.approx(spec["dur"], abs=0.1)


def test_card_sits_in_its_slot_and_scales():
    spec = {"type": "quote", "dur": 2.0, "text": "We learn", "slot": {"top": 0.7, "height": 0.1, "scale": 0.8}}
    html = composition_html(spec, STYLE, (1080, 1920), FONTS)
    assert "#slot{position:absolute;top:70.0%;height:10.0%;left:6%;right:12%" in html
    assert "--k:0.8" in html and "font-size:calc(6.4vmin*var(--k))" in html
    assert '<div id="slot"><div id="card" class="card quote">' in html


FINANCE = load_style("finance")


@pytest.mark.parametrize("spec, marker", [
    ({"type": "ticker", "name": "Bitcoin", "ticker": "BTC", "fact": "new high"}, 'class="sym">BTC<'),
    ({"type": "headline", "text": "Oil hits record", "source": "Reuters", "tag": "LIVE"}, 'class="tag">LIVE<'),
    ({"type": "kinetic", "text": "Oil could hit $150", "hi": ["$150"]}, 'class="w hi u item">$150<'),
])
def test_finance_cards_render_in_the_slot(spec, marker):
    html = composition_html({**spec, "dur": 2.0}, FINANCE, (1080, 1920), FONTS)
    assert marker in html and '<div id="slot">' in html


def test_stat_direction_colours_and_arrows_the_value():
    html = composition_html({"type": "stat", "dur": 1.0, "value": "20%", "label": "drop", "dir": "down"},
                            FINANCE, (1080, 1920), FONTS)
    assert 'class="card stat down"><div class="num">▼ 20%<' in html and ".stat.down .num{color:#ff4d4f}" in html


def test_fixed_cards_skip_the_slot():
    credit = composition_html({"type": "credit", "dur": 2.0, "text": "CNBC"}, FINANCE, (1080, 1920), FONTS)
    assert "// CNBC" in credit and 'id="slot"' not in credit.split("<body>")[1]
    outro = composition_html({"type": "outro", "dur": 2.0, "handle": "@yourbrand"}, FINANCE, (1080, 1920),
                             FONTS, "logo.jpg")
    assert 'src="logo.jpg"' in outro and "@yourbrand" in outro


def test_outro_copies_the_brand_logo(tmp_path, monkeypatch):
    _fake_hf(monkeypatch, duration=2.0)
    monkeypatch.setattr(gr.fonts, "ensure_font", lambda family: tmp_path / "f.ttf")
    (tmp_path / "f.ttf").write_bytes(b"")
    import numpy as np
    from PIL import Image
    logo = tmp_path / "brand" / "logo.jpg"
    logo.parent.mkdir()
    Image.fromarray(np.random.default_rng(0).integers(0, 255, (64, 64, 3), dtype=np.uint8)).save(logo)
    render_graphic({"type": "outro", "at": 0, "dur": 2.0}, {**FINANCE, "logo": str(logo)}, (1080, 1920),
                   tmp_path / "g.mov")
    assert (tmp_path / "g.hf" / "logo.jpg").stat().st_size > 1000


@pytest.mark.parametrize("fx, marker", [("pop", '"bouncy",0)'), ("shine", "--sx"), ("neon", "rnd()"),
                                        ("bloom", 'id="bloom"')])
def test_kinetic_letter_effects(fx, marker):
    html = composition_html({"type": "kinetic", "dur": 2.5, "text": "Event night", "hi": ["night"], "fx": fx},
                            FINANCE, (1080, 1920), FONTS)
    assert marker in html
    if fx in ("pop", "neon"):
        assert '<span class="u item">E</span>' in html  # Latin animates letter by letter


def test_arabic_kinetic_never_splits_letters():
    html = composition_html({"type": "kinetic", "dur": 2.0, "text": "ليلة الحدث", "fx": "pop"}, FINANCE,
                            (1080, 1920), FONTS)
    assert '<span class="w u item">ليلة</span>' in html


def test_text_behind_sits_in_its_own_band():
    html = composition_html({"type": "kinetic", "dur": 2.0, "text": "GALA", "place": "behind"}, FINANCE,
                            (1080, 1920), FONTS)
    assert '<div id="behind">' in html and "kinetic latin behind" in html


def test_centre_title_is_big_text_without_a_cutout():
    html = composition_html({"type": "kinetic", "dur": 2.0, "text": "EVENT", "place": "center"}, FINANCE,
                            (1080, 1920), FONTS)
    assert '<div id="center">' in html and "kinetic latin behind" in html
