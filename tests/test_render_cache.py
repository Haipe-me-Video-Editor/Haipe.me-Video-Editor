import pytest
"""Re-renders reuse what did not change: the base cut, cut-outs, and kit graphics (by content, not by index)."""
from pathlib import Path

from editor import cutout, editjson
from editor.style import load_style
from editor import render as R
from editor.graphics import render as G

STYLE = load_style("default")


def _plan(out=5.0):
    return editjson.new_plan([{"src": "raw/a.mp4", "in": 0.0, "out": out}], style="default")


def test_base_cut_is_rebuilt_only_when_segments_change(tmp_path, monkeypatch):
    (tmp_path / "raw").mkdir()
    (tmp_path / "work").mkdir()
    (tmp_path / "raw" / "a.mp4").write_bytes(b"x")
    runs = []
    monkeypatch.setattr(R.ffmpeg, "run", lambda args, cwd=None: (runs.append(1), Path(args[-1]).write_bytes(b"v")))
    R.build_base(tmp_path, _plan(), (1080, 1920))
    R.build_base(tmp_path, _plan(), (1080, 1920))
    assert len(runs) == 1
    R.build_base(tmp_path, _plan(4.0), (1080, 1920))
    assert len(runs) == 2


def test_cutouts_are_reused_for_the_same_window(tmp_path, monkeypatch):
    base = tmp_path / "base.mp4"
    base.write_bytes(b"v")
    (tmp_path / "base.key").write_text("k1")
    calls = []

    def fake(src, out, at, dur, size, glow=None, glow_out=None, part="person"):
        calls.append((at, part))
        Path(out).write_bytes(b"c")
        return Path(out)
    monkeypatch.setattr(cutout, "cut_out", fake)
    a, _ = R.cached_cutout(base, 1.0, 2.0, (1080, 1920), part="hands")
    b, _ = R.cached_cutout(base, 1.0, 2.0, (1080, 1920), part="hands")
    assert a == b and len(calls) == 1 and a.exists()
    R.cached_cutout(base, 1.5, 2.0, (1080, 1920), part="hands")
    (tmp_path / "base.key").write_text("k2")  # a new cut invalidates every cut-out
    R.cached_cutout(base, 1.0, 2.0, (1080, 1920), part="hands")
    assert len(calls) == 3


def test_kit_graphics_are_cached_by_content_not_index(tmp_path, monkeypatch):
    renders = []

    def fake_hf(args, cwd):
        if args[0] == "render":
            renders.append(cwd)
            Path(args[-1]).write_bytes(b"m")
    monkeypatch.setattr(G, "_hf", fake_hf)
    monkeypatch.setattr(G, "check_output", lambda p, d: None)
    monkeypatch.setattr(G.fonts, "ensure_font", lambda fam: tmp_path / f"{fam}.ttf")
    monkeypatch.setattr(G.shutil, "copy2", lambda a, b: None)
    spec = {"type": "stack", "dur": 1.0, "lines": [{"text": "مرحبا"}]}
    a = G.render_graphic(spec, STYLE, (1080, 1920), tmp_path / "gfx-3.mov")
    b = G.render_graphic(spec, STYLE, (1080, 1920), tmp_path / "gfx-4.mov")  # same graphic, new index
    assert a == b and len(renders) == 1
    G.render_graphic({**spec, "lines": [{"text": "النتائج"}]}, STYLE, (1080, 1920), tmp_path / "gfx-4.mov")
    assert len(renders) == 2


def test_jobs_follow_the_env(monkeypatch):
    monkeypatch.setenv("EDITOR_JOBS", "3")
    assert R.jobs() == 3


def test_text_behind_the_person_is_graded_by_transitions_and_never_over_broll():
    plan = _plan(10.0)
    plan["transitions"] = [{"type": "leak", "at": 4.0}]
    g = {"type": "stack", "at": 4.0, "dur": 2.0, "place": "hands", "lines": [{"text": "x"}]}
    vf = R.video_filter(plan, 0, [({"at": 1.0, "dur": 3.0}, 1)], [(g, 2, 3)], (1080, 1920))
    assert vf.index("[3:v]") < vf.index("blend=")  # the cut-out goes in before the light burn
    assert "gte(t,3.9833)*lt(t,5.9833)*not(gte(t,0.9833)*lt(t,3.9833))" in vf  # off on every B-roll frame
    assert R.scene_window(4.0, 2.0, [(7.0, 9.0)]) == "gte(t,3.9833)*lt(t,5.9833)"


def test_a_graphic_never_shows_on_its_end_frame():
    g = {"type": "stack", "at": 1.0, "dur": 2.0, "lines": [{"text": "x"}]}
    vf = R.video_filter(_plan(10.0), 0, [], [(g, 1, None)], (1080, 1920))
    assert "enable='gte(t,0.9833)*lt(t,2.9833)'" in vf


def test_a_graphic_ending_between_frames_stops_where_the_cut_lands():
    # a cut at 2.64 s lands on frame 79 (2.6333 s); a graphic ending at 2.64 must be gone by then
    assert R.gfx_window(0.2, 2.44) == "gte(t,0.1833)*lt(t,2.6167)"


def test_a_graphic_that_runs_to_the_end_of_the_video_holds_the_last_frame():
    # an end bound there switched the final frame off and showed the footage under the end card
    g = {"type": "stack", "at": 7.0, "dur": 3.0, "lines": [{"text": "x"}]}
    vf = R.video_filter(_plan(10.0), 0, [], [(g, 1, None)], (1080, 1920))
    assert "enable='gte(t,6.9833)'" in vf
    assert R.graphic_window(7.0, 2.0, 10.0) == R.gfx_window(7.0, 2.0)


def test_an_end_card_must_run_to_the_end_of_the_video():
    p = _plan(10.0)
    p["graphics"] = [{"type": "endcard", "at": 7.0, "dur": 2.9}]
    assert any("end card" in e for e in editjson.validate(p))
    p["graphics"][0]["dur"] = 3.0
    assert editjson.validate(p) == []


def test_a_graphic_within_three_frames_of_a_cut_is_rejected():
    p = editjson.new_plan([{"src": "a.mp4", "in": 0.0, "out": 2.64}, {"src": "a.mp4", "in": 3.0, "out": 6.0}],
                          style="default")
    p["graphics"] = [{"type": "stack", "at": 0.0, "dur": 2.67, "lines": [{"text": "x"}]}]
    assert any("after the cut" in e for e in editjson.validate(p))
    p["graphics"][0]["dur"] = 2.64
    assert editjson.validate(p) == []
    p["graphics"] = [{"type": "stack", "at": 2.6, "dur": 1.0, "lines": [{"text": "x"}]}]
    assert any("before the cut" in e for e in editjson.validate(p))


def test_the_vertical_size_can_be_raised_for_a_2k_master():
    from editor.config import vertical_size
    assert vertical_size(None) == (1080, 1920)
    assert vertical_size("1440x2560") == (1440, 2560)
    with pytest.raises(ValueError):
        vertical_size("1440x2500")
