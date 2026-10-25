import json

import pytest

from editor import editjson
from editor.style import load_style


def _plan():
    return editjson.new_plan([{"src": "raw/a.mp4", "in": 1.0, "out": 3.0, "zoom": 1.0},
                              {"src": "raw/a.mp4", "in": 4.0, "out": 7.0, "zoom": 1.1}])


def test_new_plan_is_valid_and_measures_timeline():
    p = _plan()
    assert editjson.validate(p) == []
    assert editjson.timeline_duration(p) == 5.0


def test_validation_catches_bad_entries():
    p = _plan()
    p["segments"][0]["out"] = 0.5
    p["broll"].append({"at": 4.0, "dur": 2.0, "query": "rooftop", "resolved": None})
    p["graphics"].append({"type": "confetti", "at": 0.0, "dur": 1.0})
    p["sfx"].append({"at": 1.0, "kind": "airhorn"})
    p["captions"]["mode"] = "fr"
    errors = " | ".join(editjson.validate(p))
    for needle in ("segments[0]", "broll[0]", "graphics[0]", "sfx[0]", "captions.mode"):
        assert needle in errors


def test_save_refuses_invalid(tmp_path):
    p = _plan()
    p["format"] = "4:3"
    with pytest.raises(ValueError):
        editjson.save(tmp_path / "edit.json", p)


def test_round_trip(tmp_path):
    p = _plan()
    editjson.save(tmp_path / "edit.json", p)
    assert editjson.load(tmp_path / "edit.json") == p


def test_default_style_is_neutral_and_complete():
    s = load_style()
    assert s["name"] == "default" and s["font"] == "Roboto" and s["accent"] == "#ff7a1a"


def test_segment_with_huge_span_reports_error():
    p = editjson.new_plan([{"src": "a", "in": -1.7e308, "out": 1.7e308}])
    errs = editjson.validate(p)
    assert any("span is too large" in e for e in errs)


def test_segments_summing_past_float_range_report_error():
    p = editjson.new_plan([{"src": "a", "in": 0, "out": 1.7e308},
                           {"src": "a", "in": 0, "out": 1.7e308}])
    p["sfx"] = [{"kind": "whoosh", "at": 1.0}]
    errs = editjson.validate(p)
    assert any("timeline duration is too large" in e for e in errs)


def test_graphic_at_dur_past_float_range_reports_error():
    p = _plan()
    p["graphics"] = [{"type": "custom", "dir": "g", "at": 1.7e308, "dur": 1.7e308}]
    errs = editjson.validate(p)
    assert any("at/dur span is too large" in e for e in errs)


def test_segments_hash_is_deterministic():
    p = _plan()
    h1 = editjson.segments_hash(p)
    h2 = editjson.segments_hash(p)
    assert h1 == h2


def test_segments_hash_changes_on_segment_out_change():
    p = _plan()
    h1 = editjson.segments_hash(p)
    p["segments"][0]["out"] = 5.0
    h2 = editjson.segments_hash(p)
    assert h1 != h2


def test_empty_segments_error():
    p = _plan()
    p["segments"] = []
    errs = editjson.validate(p)
    assert any("segments is empty" in e for e in errs)


def test_zoom_out_of_range():
    p = _plan()
    p["segments"][0]["zoom"] = 3.0
    errs = editjson.validate(p)
    assert any("zoom" in e for e in errs)


def test_focus_point_for_off_centre_zoom():
    p = _plan()
    p["segments"][0].update(zoom=2.4, focus=[0.5, 0.31])
    assert editjson.validate(p) == []
    for bad in ([0.5], [1.2, 0.3], "middle"):
        p["segments"][0]["focus"] = bad
        assert any("focus" in e for e in editjson.validate(p))


def test_custom_graphic_without_dir():
    p = _plan()
    p["graphics"].append({"type": "custom", "at": 0.0, "dur": 1.0})
    errs = editjson.validate(p)
    assert any("custom graphics need a 'dir'" in e for e in errs)


def test_broll_with_empty_query():
    p = _plan()
    p["broll"].append({"at": 1.0, "dur": 1.0, "query": ""})
    errs = editjson.validate(p)
    assert any("query is required" in e for e in errs)


def test_sfx_at_beyond_timeline():
    p = _plan()
    p["sfx"].append({"at": 6.0, "kind": "whoosh"})
    errs = editjson.validate(p)
    assert any("at must be inside the timeline" in e for e in errs)


def test_malformed_segment_missing_out():
    p = _plan()
    p["segments"][0].pop("out")
    errs = editjson.validate(p)
    assert any("segments[0]: in/out must be numbers" in e for e in errs)


def test_malformed_segment_missing_in():
    p = _plan()
    p["segments"][0].pop("in")
    errs = editjson.validate(p)
    assert len(errs) > 0
    assert any("in/out must be numbers" in e for e in errs)


def test_malformed_segment_out_not_number():
    p = _plan()
    p["segments"][0]["out"] = "three"
    errs = editjson.validate(p)
    assert len(errs) > 0
    assert any("in/out must be numbers" in e for e in errs)


def test_malformed_segment_in_is_bool():
    p = _plan()
    p["segments"][0]["in"] = True
    errs = editjson.validate(p)
    assert len(errs) > 0
    assert any("in/out must be numbers" in e for e in errs)


def test_malformed_broll_missing_dur():
    p = _plan()
    p["broll"].append({"at": 1.0, "query": "test"})
    errs = editjson.validate(p)
    assert len(errs) > 0
    assert any("at/dur must be numbers" in e for e in errs)


def test_malformed_broll_dur_not_number():
    p = _plan()
    p["broll"].append({"at": 1.0, "dur": "long", "query": "test"})
    errs = editjson.validate(p)
    assert len(errs) > 0
    assert any("at/dur must be numbers" in e for e in errs)


def test_malformed_graphics_missing_at():
    p = _plan()
    p["graphics"].append({"type": "hook", "dur": 1.0})
    errs = editjson.validate(p)
    assert len(errs) > 0
    assert any("at/dur must be numbers" in e for e in errs)


def test_malformed_sfx_at_none():
    p = _plan()
    p["sfx"].append({"at": None, "kind": "whoosh"})
    errs = editjson.validate(p)
    assert len(errs) > 0
    assert any("at must be a number" in e for e in errs)


def test_malformed_segments_not_a_list():
    p = _plan()
    p["segments"] = {"0": {"src": "raw/a.mp4", "in": 1.0, "out": 3.0}}
    errs = editjson.validate(p)
    assert any("segments must be a list" in e for e in errs)


def test_save_raises_valueerror_not_keyerror_for_missing_out(tmp_path):
    p = _plan()
    p["segments"][0].pop("out")
    with pytest.raises(ValueError):
        editjson.save(tmp_path / "edit.json", p)
    assert not (tmp_path / "edit.json").exists()


def _with(**changes):
    p = _plan()
    p.update(changes)
    return p


def _zoom(v):
    p = _plan()
    p["segments"][0]["zoom"] = v
    return p


@pytest.mark.parametrize("plan", [
    None,
    [],
    _with(segments=["x"]),
    _with(segments=[None]),
    _zoom("big"),
    _zoom(None),
    _with(broll=None),
    _with(broll=["x"]),
    _with(graphics=[3]),
    _with(sfx=[None]),
    _with(captions=None),
    _with(format=["9:16"]),
    _with(segments=[{"src": "a", "in": -10**308, "out": 10**308}]),
    _with(graphics=[{"type": "hook", "at": 10**308, "dur": 10**308}]),
], ids=["plan-None", "plan-list", "seg-str", "seg-None", "zoom-str", "zoom-None",
        "broll-None", "broll-str", "graphics-int", "sfx-None", "captions-None",
        "format-list", "seg-huge-span", "graphics-huge-at-dur"])
def test_validate_never_raises(plan, tmp_path):
    errs = editjson.validate(plan)
    assert errs and all(isinstance(e, str) for e in errs)
    with pytest.raises(ValueError):
        editjson.save(tmp_path / "edit.json", plan)


def test_not_a_list_does_not_also_report_empty():
    errs = editjson.validate(_with(segments="x"))
    assert any("segments must be a list" in e for e in errs)
    assert not any("segments is empty" in e for e in errs)


@pytest.mark.parametrize("key", ["broll", "graphics"])
@pytest.mark.parametrize("item", [
    {"at": 0.0, "dur": 0.0},
    {"at": 0.0, "dur": -1.0},
    {"at": -1.0, "dur": 1.0},
    {"at": 4.0, "dur": 2.0},
])
def test_overlay_must_fit_timeline(key, item):
    item = {**item, "query": "q", "type": "hook"}
    p = _plan()
    p[key].append(item)
    assert any(f"{key}[0]: must fit inside" in e for e in editjson.validate(p))


@pytest.mark.parametrize("key", ["broll", "graphics"])
def test_overlay_bad_times_still_run_other_checks(key):
    p = _plan()
    p[key].append({"at": "x", "dur": None, "query": "", "type": "custom"})
    errs = " | ".join(editjson.validate(p))
    assert f"{key}[0]: at/dur must be numbers" in errs
    if key == "broll":
        assert "broll[0]: query is required" in errs
    else:
        assert "graphics[0]: custom graphics need a 'dir'" in errs


def test_sfx_bad_at_still_checks_kind():
    p = _plan()
    p["sfx"].append({"at": None, "kind": "airhorn"})
    errs = " | ".join(editjson.validate(p))
    assert "sfx[0]: at must be a number" in errs
    assert "sfx[0]: kind must be one of" in errs


def test_sfx_negative_at_is_error():
    p = _plan()
    p["sfx"].append({"at": -0.5, "kind": "pop"})
    assert any("sfx[0]: at must be inside" in e for e in editjson.validate(p))


@pytest.mark.parametrize("at, ok", [(5.005, True), (5.02, False)])
def test_sfx_end_tolerance(at, ok):
    p = _plan()
    p["sfx"].append({"at": at, "kind": "pop"})
    assert (editjson.validate(p) == []) is ok


def test_invalid_format_through_validate():
    p = _plan()
    p["format"] = "4:3"
    assert any("format must be one of" in e for e in editjson.validate(p))


def test_reversed_segment_does_not_shrink_total():
    p = editjson.new_plan([{"src": "a", "in": 0.0, "out": 2.0},
                           {"src": "a", "in": 5.0, "out": 4.0}])
    p["broll"].append({"at": 0.0, "dur": 1.5, "query": "q"})
    errs = editjson.validate(p)
    assert any("segments[1]: out must be after in" in e for e in errs)
    assert not any("must fit inside" in e for e in errs)


def test_segments_hash_ignores_key_order():
    a = editjson.new_plan([{"src": "a", "in": 1.0, "out": 2.0, "zoom": 1.0}])
    b = editjson.new_plan([{"zoom": 1.0, "out": 2.0, "in": 1.0, "src": "a"}])
    assert editjson.segments_hash(a) == editjson.segments_hash(b)


def test_segments_hash_ignores_private_render_keys():
    # render adds `_grade` to each segment when a grade is set; that must not make captions.json stale
    a = editjson.new_plan([{"src": "a", "in": 1.0, "out": 2.0, "zoom": 1.0}])
    b = editjson.new_plan([{"src": "a", "in": 1.0, "out": 2.0, "zoom": 1.0, "_grade": "eq=contrast=1.1"}])
    assert editjson.segments_hash(a) == editjson.segments_hash(b)


def test_load_validates_and_lists_every_error(tmp_path):
    p = _plan()
    p["format"] = "4:3"
    p["segments"][0]["src"] = ""
    (tmp_path / "edit.json").write_text(json.dumps(p), encoding="utf-8")
    with pytest.raises(ValueError) as e:
        editjson.load(tmp_path / "edit.json")
    assert "format must be one of" in str(e.value) and "segments[0]: src" in str(e.value)


@pytest.mark.parametrize("src", ["", None, 3, ["raw/a.mp4"]])
def test_segment_src_must_be_a_non_empty_string(src):
    p = _plan()
    p["segments"][0]["src"] = src
    assert any("segments[0]: src must be a non-empty string" in e for e in editjson.validate(p))


@pytest.mark.parametrize("src_in, ok", [(None, True), (0.0, True), (1.25, True),
                                        ("0,movie=evil", False), (-0.5, False), (True, False)])
def test_broll_src_in_must_be_a_non_negative_number(src_in, ok):
    p = _plan()
    p["broll"].append({"at": 1.5, "dur": 2.0, "query": "rooftop", "src_in": src_in})
    assert (editjson.validate(p) == []) is ok


@pytest.mark.parametrize("at, dur, ok", [(1.5, 1.5, True), (1.0, 2.0, False), (2.0, 0.8, True), (2.0, 0.4, False),
                                         (1.5, 9.0, True), (1.5, 10.5, False), (0.5, 4.5, False)])
def test_broll_follows_the_shot_rules(at, dur, ok):
    """0.5-10 s: quick list shots up to long held explainers; never in the first 1.5 s."""
    p = _plan()
    p["segments"][1]["out"] = 13.0
    p["broll"].append({"at": at, "dur": dur, "query": "rooftop"})
    assert (editjson.validate(p) == []) is ok


@pytest.mark.parametrize("graphic, field", [
    ({"type": "hook"}, "text"),
    ({"type": "hook", "text": ""}, "text"),
    ({"type": "lower_third", "name": 5}, "name"),
    ({"type": "list", "items": []}, "items"),
    ({"type": "list", "items": ["ok", ""]}, "items"),
    ({"type": "list", "items": "one"}, "items"),
    ({"type": "stat", "label": "users"}, "value"),
    ({"type": "stat", "value": "30%"}, "label"),
    ({"type": "quote", "text": None}, "text"),
    ({"type": "custom", "dir": ""}, "dir"),
])
def test_graphics_need_their_text_fields(graphic, field):
    p = _plan()
    p["graphics"].append({**graphic, "at": 0.5, "dur": 1.5})
    assert any(e.startswith("graphics[0]:") and f"'{field}'" in e for e in editjson.validate(p))


def test_complete_graphics_are_valid():
    p = _plan()
    p["graphics"] = [{"type": "hook", "text": "a", "at": 0, "dur": 1},
                     {"type": "lower_third", "name": "a", "at": 0, "dur": 1},
                     {"type": "list", "items": ["a", "b"], "at": 0, "dur": 1},
                     {"type": "stat", "value": "30%", "label": "a", "at": 0, "dur": 1},
                     {"type": "quote", "text": "a", "at": 0, "dur": 1},
                     {"type": "custom", "dir": "work/custom-1", "at": 0, "dur": 1}]
    assert editjson.validate(p) == []


def test_captions_need_a_single_source_clip():
    p = _plan()
    p["segments"][1]["src"] = "raw/b.mp4"
    assert any("captions support one source clip per project for now" in e for e in editjson.validate(p))
    p["captions"]["enabled"] = False
    assert editjson.validate(p) == []


def test_save_writes_readable_utf8(tmp_path):
    p = _plan()
    p["notes"] = ["قص المقدمة"]
    editjson.save(tmp_path / "edit.json", p)
    assert "قص المقدمة" in (tmp_path / "edit.json").read_text(encoding="utf-8")
    assert editjson.load(tmp_path / "edit.json") == p


def test_looks_are_validated():
    from editor import editjson
    plan = editjson.new_plan([{"src": "raw/a.mp4", "in": 0.0, "out": 5.0}])
    plan["looks"] = [{"type": "bars", "at": 1.0, "dur": 2.0}, {"type": "vignette", "at": 0.0, "dur": 5.0}]
    assert editjson.validate(plan) == []
    plan["looks"] = [{"type": "sepia", "at": 1.0, "dur": 0.5}, {"type": "bars", "at": 4.0, "dur": 2.0}]
    errs = " ".join(editjson.validate(plan))
    assert "looks[0]: type must be one of" in errs and "looks[0]: dur must be at least 1 second" in errs
    assert "looks[1]: must fit inside" in errs


def test_finance_graphics_validate():
    plan = editjson.new_plan([{"src": "raw/a.mp4", "in": 0.0, "out": 10.0}])
    plan["graphics"] = [{"type": "ticker", "name": "Bitcoin", "at": 1, "dur": 2},
                        {"type": "stat", "value": "5%", "label": "drop", "dir": "sideways", "at": 3, "dur": 2},
                        {"type": "kinetic", "text": "Oil up", "hi": "Oil", "at": 5, "dur": 2},
                        {"type": "outro", "at": 8, "dur": 2}]
    errs = editjson.validate(plan)
    assert any("ticker needs a non-empty string 'ticker'" in e for e in errs)
    assert any("'dir' must be 'up' or 'down'" in e for e in errs)
    assert any("'hi' must be a list" in e for e in errs)
    assert len(errs) == 3


def test_speed_changes_timeline_length_and_is_validated():
    plan = editjson.new_plan([{"src": "a.mp4", "in": 0.0, "out": 4.0, "speed": 0.5},
                              {"src": "a.mp4", "in": 4.0, "out": 8.0, "speed": 2.0, "mute": True}])
    assert editjson.timeline_duration(plan) == 10.0 and editjson.validate(plan) == []
    plan["segments"][0]["speed"] = 8
    plan["segments"][1]["mute"] = "yes"
    errs = editjson.validate(plan)
    assert any("speed must be between" in e for e in errs) and any("mute must be" in e for e in errs)


def test_sfx_volume_range():
    p = _plan()
    p["sfx_volume"] = 0.1
    assert editjson.validate(p) == []
    p["sfx_volume"] = 2
    assert any("sfx_volume" in e for e in editjson.validate(p))


def test_blur_look_push_and_open_broll_are_accepted():
    from editor import editjson
    plan = editjson.new_plan([{"src": "raw/a.mp4", "in": 0.0, "out": 9.0, "zoom": 1.1, "push": 1.2}])
    plan["looks"] = [{"type": "blur", "at": 1.0, "dur": 1.5}]
    plan["broll"] = [{"at": 0.0, "dur": 3.0, "query": "city skyline", "open": True}]
    assert editjson.validate(plan) == []
    plan["broll"][0].pop("open")
    plan["segments"][0]["push"] = 3
    errs = " ".join(editjson.validate(plan))
    assert "open: true" in errs and "push must be" in errs


def test_music_duck_is_optional_and_checked():
    from editor import editjson
    plan = {"version": 1, "format": "9:16", "segments": [{"src": "raw/a.mp4", "in": 0, "out": 5}],
            "music": {"src": "m.mp3", "duck": {"ratio": 3, "threshold": 0.08}}}
    assert not [e for e in editjson.validate(plan) if "duck" in e]
    plan["music"]["duck"] = {"ratio": 50}
    assert [e for e in editjson.validate(plan) if "duck" in e]


def test_split_broll_may_open_the_video_and_checks_its_fields():
    p = _plan()
    p["segments"][1]["out"] = 13.0
    p["broll"].append({"at": 0.2, "dur": 1.0, "query": "site", "frame": "top"})  # the face is still on screen
    assert editjson.validate(p) == []
    p["broll"][-1]["frame"] = "left"
    assert any("frame must be one of" in e for e in editjson.validate(p))
    p["broll"][-1].update(frame="top", split_y=0.8)
    assert any("split_y" in e for e in editjson.validate(p))


def test_segments_hash_ignores_render_time_fields():
    p = editjson.new_plan([{"src": "a.mp4", "in": 0, "out": 5}])
    graded = {**p, "segments": [{**p["segments"][0], "_grade": "curves=..."}]}
    assert editjson.segments_hash(p) == editjson.segments_hash(graded)
