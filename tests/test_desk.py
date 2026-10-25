from editor import captions, cutout, editjson
from editor.graphics.desk import chart_path, desk_html
from editor.render import video_filter
from editor.style import load_style

STYLE = load_style("finance")
FONTS = {"latin": "l.ttf", "arabic": "a.ttf", "display": "d.ttf", "mono": "m.ttf"}
SIZE = (1080, 1920)


def _plan(desks, **extra):
    plan = editjson.new_plan([{"src": "raw/a.mp4", "in": 0.0, "out": 20.0}])
    plan["desks"] = desks
    plan.update(extra)
    return plan


def test_valid_desks_pass_and_bad_ones_are_explained():
    good = [{"at": 2, "dur": 5, "card": {"type": "steps", "title": "Cycle", "items": ["a", "b"]}},
            {"at": 8, "dur": 4, "mood": "bull", "card": {"type": "chart", "name": "BTC", "value": "1", "points": [1, 2]}}]
    assert editjson.validate(_plan(good)) == []
    bad = [{"at": 1, "dur": 1, "mood": "sad", "card": {"type": "profile", "ticker": "X", "stats": [{"value": "1"}]}},
           {"at": 5, "dur": 3, "card": {"type": "chart", "name": "BTC", "value": "1", "points": [1]}}]
    errs = editjson.validate(_plan(bad, graphics=[{"type": "hook", "text": "hi", "at": 6, "dur": 1}]))
    for msg in (">= 1.5", "at least 2 seconds", "mood must be", "up to 3 objects", "at least 2 numbers",
                "overlaps graphics[0]"):
        assert any(msg in e for e in errs), msg


def test_desk_html_renders_each_card_and_bolds_key_phrases():
    profile = {"type": "profile", "ticker": "BTC", "stats": [{"value": "+12%", "label": "growth"}],
               "body": "They hit **record** highs", "tags": ["CASH RICH"]}
    html = desk_html({"dur": 3, "card": profile}, STYLE, SIZE, FONTS, logo="logo.jpg")
    assert "<b>record</b>" in html and ">BTC<" in html and 'id="mark"' in html and "--k" in html
    steps = desk_html({"dur": 3, "card": {"type": "steps", "title": "دورة النمو", "hi": "النمو",
                                          "items": ["أ", "ب"]}}, STYLE, SIZE, FONTS)
    assert 'dir="rtl"' in steps and '<span class="hi">النمو</span>' in steps and ">02<" in steps
    chart = desk_html({"dur": 3, "card": {"type": "chart", "name": "BTC", "value": "1.5", "change": "10%", "points": [3, 2, 1]}},
                      STYLE, SIZE, FONTS)
    assert "▼" in chart and STYLE["down"] in chart


def test_chart_path_spans_the_box():
    pts = chart_path([1, 3, 2]).split()
    assert pts[0] == "0.00,40.00" and pts[1] == "50.00,0.00" and pts[-1].startswith("100.00,")


def test_cutout_puts_the_head_under_the_panel():
    pl = cutout.placement((0.10, 0.60), SIZE)
    assert pl["w"] < SIZE[0] and abs(pl["y"] + 0.10 * pl["h"] - 0.60 * SIZE[1]) <= 1
    assert cutout.matte_size(1080, 1920) == (512, 896)


def test_captions_lift_between_panel_and_head_only_during_a_desk():
    lines = [{"start": 0.5, "end": 1.5, "hook": False, "tr": None, "words": [{"w": "a", "start": 0.5, "end": 1.4}]},
             {"start": 3.0, "end": 4.0, "hook": False, "tr": None, "words": [{"w": "b", "start": 3.0, "end": 3.9}]}]
    ass = captions.to_ass(lines, STYLE, SIZE, "source", [{"at": 2.5, "dur": 3}])
    events = [x for x in ass.splitlines() if x.startswith("Dialogue")]
    assert events[0].split(",")[7] == "0"
    assert int(events[1].split(",")[7]) == round((1 - captions.DESK_CAPTION_BOTTOM) * SIZE[1])


def test_video_filter_lays_the_cutout_over_the_desk():
    plan = _plan([])
    pl = {"w": 640, "h": 1136, "x": 220, "y": 1040}
    vf = video_filter(plan, {"raw/a.mp4": 0}, [], [], SIZE, desk_inputs=[({"at": 2.0, "dur": 4.0}, 1, 2, pl)])
    assert "[1:v]setpts=PTS-STARTPTS+2.0/TB,scale=out_color_matrix=bt709:out_range=tv,format=yuva420p[dk0]" in vf \
           and "scale=640:1136,scale=out_color_matrix=bt709:out_range=tv,format=yuva420p[fg0]" in vf
    assert "overlay=x=220:y=1040:enable='between(t,2.0,6.0)'" in vf
