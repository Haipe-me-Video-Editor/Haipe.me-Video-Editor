"""Brand kit graphics: HTML is built for every type, and edit.json validates their fields."""

import pytest

from editor import editjson
from editor.style import load_style
from editor.graphics.kit import KIT_FONTS, KIT_TYPES, kit_html

STYLE = load_style("default")
FONTS = {k: f"{k}.ttf" for k in KIT_FONTS}
SIZE = (1080, 1920)

SPECS = {
    "stack": {"lines": [{"text": "ABC/XYZ", "color": "chrome", "font": "hero", "size": 230},
                        {"text": "المؤشر ارتفع اليوم", "pill": True, "t": 0.4},
                        {"text": "صدفة", "font": "arh", "strike": 0.8}]},
    "card": {"lines": [{"text": "اليوم نطلق", "role": "top"}, {"text": "الخطة الجديدة", "role": "main"}]},
    "badge": {"icon": "comment", "text": "اكتب رأيك"},
    "bars": {"values": [{"value": 10.0, "label": "1 يناير"}, {"value": 12.0, "label": "1 فبراير"}], "change": "+20%"},
    "leak": {},
    "endcard": {"text": "ACME"},
    "tiles": {"items": [{"text": "الخطة", "icon": "wallet"}, {"text": "النتائج", "icon": "vault"}]},
    "poll": {"question": "الخطة أ أم الخطة ب؟", "options": ["الخطة أ", "الخطة ب الجديدة"]},
    "balance": {"right": {"label": "المزايا", "items": [{"text": "السرعة", "icon": "box", "t": 1}]},
                "left": {"label": "العيوب", "items": [{"text": "التكلفة", "icon": "doc", "t": 2}]}},
    "wave": {},
    "mark": {"text": "Made with care."},
    "sticker": {"src": "logo.png", "pos": [0.8, 0.3], "w": 0.25},
    "title": {"text": "LOREM", "sub": "النتائج"},
    "flag": {"pos": [0.2, 0.2], "w": 0.36},
}

MARK = {"word": "acme", "badge": "#000000", "view": 100, "bars": [["#4c6ef5", 12, 30], ["#4c6ef5", 34, 50], ["#4c6ef5", 56, 70], ["#4c6ef5", 78, 90]]}


@pytest.mark.parametrize("kind", KIT_TYPES)
def test_every_kit_type_builds_a_timed_composition(kind):
    style = {**STYLE, "mark": MARK} if kind == "mark" else STYLE
    page = kit_html({"type": kind, "dur": 3.0, **SPECS[kind]}, style, SIZE, FONTS)
    assert 'data-duration="3.0"' in page and 'window.__timelines["g"]' in page
    assert "http://" not in page and "https://" not in page  # local files only
    for k in KIT_FONTS:  # every face is loaded before the timeline registers
        assert f'"K{k}"' in page


def test_sweep_variant_and_hands_place_are_accepted():
    page = kit_html({"type": "leak", "variant": "sweep", "dur": 0.4}, STYLE, SIZE, FONTS)
    assert "#band" in page
    p = editjson.new_plan([{"src": "a.mp4", "in": 0, "out": 10}], style="default")
    p["graphics"] = [{"type": "stack", "at": 1, "dur": 2, "place": "hands", "lines": [{"text": "70"}]},
                     {"type": "leak", "variant": "sweep", "at": 3, "dur": 0.4}]
    assert editjson.validate(p) == []


def test_stack_shade_is_a_halo_on_each_line():
    page = kit_html({"type": "stack", "dur": 2.0, "shade": True, "lines": [{"text": "لعنوان كبير", "t": 0.4}]},
                    STYLE, SIZE, FONTS)
    assert ".row{filter:drop-shadow" in page
    assert ".row{filter" not in kit_html({"type": "stack", "dur": 2.0, "lines": [{"text": "x"}]}, STYLE, SIZE, FONTS)


def test_title_tiles_latin_by_letter_and_arabic_by_word_in_the_style_colours():
    style = {**STYLE, "title": {"dark": "#111111", "accent": "#4c6ef5", "light": "#FFFFFF"}}
    page = kit_html({"type": "title", "dur": 2.4, "text": "NEW DAY"}, style, SIZE, FONTS)
    assert page.count('class="tl"') == 6 and page.count('class="gap"') == 1  # one tile per letter, spaces kept
    assert "#4c6ef5" in page and "#111111" in page
    assert 'id="sub"' not in page and 'tl.fromTo("#row"' in page  # no sub-line asked for; a long hold jitters
    assert 'tl.fromTo("#dots"' in page and 'tl.fromTo("#slab2",{x:' in page  # the background drifts and sways while it holds
    ar = kit_html({"type": "title", "dur": 1.2, "text": "اليوم نطلق"}, style, SIZE, FONTS)
    assert ar.count('class="tl"') == 2 and "نطلق" in ar  # Arabic stays whole words so the letters keep their joins
    assert 'tl.fromTo("#row"' not in ar
    assert kit_html({"type": "title", "dur": 2, "text": "HI"}, style, SIZE, FONTS) == \
        kit_html({"type": "title", "dur": 2, "text": "HI"}, style, SIZE, FONTS)  # same look on every render


def test_title_sticker_letters_keep_the_slab_and_set_the_word_in_the_style_face():
    style = {**STYLE, "title": {"dark": "#111111", "accent": "#4c6ef5", "light": "#FFFFFF", "letters": "sticker"}}
    page = kit_html({"type": "title", "dur": 2.4, "text": "LAUNCHES"}, style, SIZE, FONTS)
    assert page.count('class="tl lt"') == 8 and 'class="tl" ' not in page  # no ransom tiles
    assert "rotate(" not in page.split('<div id="row">')[1].split("</div>")[0]  # every letter upright
    assert 'id="slab"' in page and "-webkit-text-stroke" not in page  # filled letters, never outlines
    tiles = kit_html({"type": "title", "dur": 2.4, "text": "LAUNCHES", "letters": "tiles"}, style, SIZE, FONTS)
    assert 'class="tl lt"' not in tiles  # the spec can still ask for tiles


@pytest.mark.parametrize("g, ok", [
    ({"type": "title", "text": "LOREM"}, True),
    ({"type": "title", "text": ""}, False),
    ({"type": "stack", "lines": [{"text": "x"}]}, True),
    ({"type": "stack", "lines": []}, False),
    ({"type": "card", "lines": [{"role": "main"}]}, False),
    ({"type": "bars", "values": [{"value": 1, "label": "a"}, {"value": 2, "label": "b"}]}, True),
    ({"type": "bars", "values": [{"value": "1"}]}, False),
])
def test_kit_fields_are_validated(g, ok):
    p = editjson.new_plan([{"src": "a.mp4", "in": 0, "out": 10}], style="default")
    p["graphics"] = [{**g, "at": 1, "dur": 2}]
    assert (editjson.validate(p) == []) is ok


def test_sfx_can_use_a_sound_file_with_its_own_gain():
    p = editjson.new_plan([{"src": "a.mp4", "in": 0, "out": 10}])
    p["sfx"] = [{"at": 1, "kind": "whoosh", "file": "assets/w.mp3", "gain": 0.8}]
    assert editjson.validate(p) == []
    p["sfx"][0]["gain"] = 3
    assert editjson.validate(p) != []


def test_sfx_peak_finds_the_hit_not_the_file_start(tmp_path):
    import subprocess
    from editor.render import sfx_peak
    f = tmp_path / "late_hit.wav"  # 1.2 s of silence, then a short burst
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=1.2", "-f", "lavfi",
                    "-i", "sine=f=440:d=0.2:r=48000", "-filter_complex", "[0][1]concat=n=2:v=0:a=1", str(f)], check=True)
    assert abs(sfx_peak(f) - 1.2) < 0.03


def test_title_sticker_letters_keep_arabic_words_apart():
    style = {**STYLE, "title": {"dark": "#1A1A2E", "accent": "#3355AA", "light": "#FFFFFF", "letters": "sticker"}}
    page = kit_html({"type": "title", "dur": 2.0, "text": "العب مجاناً"}, style, SIZE, FONTS)
    assert page.count('class="tl lt"') == 2 and "#row{gap:42px}" in page
    assert "flex-direction:row-reverse" in page        # the first word sits on the right, where Arabic starts
    latin = kit_html({"type": "title", "dur": 2.0, "text": "PLAY"}, style, SIZE, FONTS)
    assert "#row{gap:0px}" in latin and "flex-direction:row}" in latin


def test_stack_tags_kashida_icons_and_tilt():
    page = kit_html({"type": "stack", "dur": 2.0, "rotate": -8, "lines": [
        {"text": "Spot Market", "font": "latin", "box": "accent", "anim": "type"},
        {"text": "متداولــــين", "anim": "stretch", "t": 0.4},
        {"text": "file", "icon": "file", "color": "#2F7BF5", "opacity": 0.9}]}, STYLE, SIZE, FONTS)
    assert f"background:{STYLE['accent']}" in page  # the tag's solid block in the accent
    assert 'clipPath:"inset(-20% 100% -20% 0%)"' in page and "scaleX:.45" in page
    assert "rotate(-8deg)" in page and "<svg viewBox" in page and "color:#2F7BF5" in page


def test_endcard_can_enter_from_white_and_fade_to_black():
    page = kit_html({"type": "endcard", "dur": 7.8, "text": "ACME", "from_white": True, "fade_to": "#000000",
                     "fade": 1.3}, STYLE, SIZE, FONTS)
    assert 'tl.set("#wb",{backgroundColor:"#ffffff"},0)' in page and "background:#000000" in page
    assert "6.50);" in page  # the veil starts fade seconds before the end


def test_push_duration_and_music_end_are_validated():
    p = editjson.new_plan([{"src": "a.mp4", "in": 0, "out": 10, "zoom": 1.1, "push": 1.2, "push_dur": 0.4}])
    p["music"] = {"src": None, "end": 8.0}
    assert editjson.validate(p) == []
    p["segments"][0]["push_dur"] = 0
    p["music"]["end"] = -1
    errs = editjson.validate(p)
    assert any("push_dur" in e for e in errs) and any("music.end" in e for e in errs)


def test_badge_takes_a_number_and_a_glow_look():
    html = kit_html({"type": "badge", "at": 0, "dur": 2, "num": "3", "look": "glow"}, STYLE, SIZE, FONTS)
    assert ">3</div>" in html and "radial-gradient" in html


def test_glow_card_scrolls_its_line_then_settles_it():
    html = kit_html({"type": "card", "look": "glow", "at": 0, "dur": 5, "lines": [
        {"text": "جملة طويلة", "scroll": [0.25, 3.75], "settle": 3.8}, {"text": "Price Discovery", "t": 3.85}]},
        STYLE, SIZE, FONTS)
    assert "offsetWidth" in html and "scale:0.62" in html and "Price Discovery" in html


def test_endcard_slide_brings_a_white_panel_in_from_the_left():
    html = kit_html({"type": "endcard", "at": 0, "dur": 3, "slide": 0.45}, STYLE, SIZE, FONTS)
    assert 'id="pn"' in html and "xPercent:-120" in html
