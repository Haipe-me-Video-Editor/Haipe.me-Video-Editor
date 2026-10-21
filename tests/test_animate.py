"""The animation studio: a scaffold that renders from the start, a shot list that owns all timing, and a render
that refuses a half-drawn film or one that carries a reference image."""
import json
import shutil
from pathlib import Path

import pytest

from editor import animate, ffmpeg

EXAMPLE = Path(__file__).parents[1] / "skills" / "animate" / "examples" / "sunset"


@pytest.fixture
def no_downloads(monkeypatch, tmp_path):
    """Fonts come from a local stand-in instead of the font cache or the network."""
    font = tmp_path / "stand-in.ttf"
    font.write_bytes(b"font")
    monkeypatch.setattr(animate.fonts, "ensure_font", lambda family: font)


def _film(tmp_path, **kw):
    return animate.new(tmp_path / "film", "How a kite flies", **{"seconds": 12, "shots": 4, **kw})


def test_a_new_film_holds_everything_it_needs(tmp_path, no_downloads):
    ref = tmp_path / "pin.jpg"
    ref.write_bytes(b"\xff\xd8 a style reference")
    film = _film(tmp_path, refs=[ref], fmt="16:9")
    for name in ("brief.json", "style.md", "shots.json", "sound.json", "refs/pin.jpg", "comp/index.html",
                 "comp/shots.js", "comp/studio.js", "comp/timing.js", "comp/gsap.min.js"):
        assert (film / name).exists(), name
    brief = json.loads((film / "brief.json").read_text())
    assert (brief["width"], brief["height"], brief["refs"]) == (1920, 1080, ["refs/pin.jpg"])
    shots = json.loads((film / "shots.json").read_text())
    assert [s["start"] for s in shots] == [0, 3, 6, 9] and sum(s["dur"] for s in shots) == 12
    page = (film / "comp" / "index.html").read_text()
    assert 'data-width="1920"' in page and 'data-duration="12"' in page and "$" not in page
    assert 'window.__timelines["main"]' in page  # registered inline, where lint looks for it


def test_a_new_film_never_overwrites_one(tmp_path, no_downloads):
    _film(tmp_path)
    with pytest.raises(SystemExit, match="already holds a film"):
        _film(tmp_path)


def test_bad_requests_get_a_plain_answer(tmp_path, no_downloads):
    with pytest.raises(SystemExit, match="format"):
        _film(tmp_path, fmt="2:3")
    with pytest.raises(SystemExit, match="image files"):
        _film(tmp_path, refs=[tmp_path / "missing.png"])


@pytest.mark.parametrize("shots, problem", [
    ([], "no shots"),
    ([{"id": "a", "start": 0, "dur": 2}, {"id": "b", "start": 2.5, "dur": 2}], "no gap or overlap"),
    ([{"id": "a", "start": 0, "dur": 2}, {"id": "b", "start": 1.5, "dur": 2}], "no gap or overlap"),
    ([{"id": "a", "start": 0.5, "dur": 2}], "no gap or overlap"),
    ([{"id": "a", "start": 0, "dur": 2}, {"id": "a", "start": 2, "dur": 2}], "unique id"),
    ([{"id": "3d", "start": 0, "dur": 2}], "unique id"),
    ([{"id": "a", "start": 0, "dur": 0}], "above 0"),
])
def test_shots_must_tile_the_film(shots, problem):
    with pytest.raises(SystemExit, match=problem):
        animate.check_shots(shots)


def test_the_shot_list_sets_the_film_length(tmp_path, no_downloads):
    film = _film(tmp_path)
    shots = json.loads((film / "shots.json").read_text())
    shots.append({"id": "s5", "start": 12, "dur": 2.5, "what": "a bow"})
    (film / "shots.json").write_text(json.dumps(shots))
    data = animate.sync(film)
    assert data["duration"] == 14.5 and data["shots"][-1]["id"] == "s5"
    assert 'data-duration="14.5"' in (film / "comp" / "index.html").read_text()
    assert '"duration": 14.5' in (film / "comp" / "timing.js").read_text()


def test_snapshots_land_inside_each_shot_away_from_the_fades():
    times = animate.snap_times([{"id": "a", "start": 0, "dur": 2}, {"id": "b", "start": 2, "dur": 4}])
    assert times == [(0.4, "a"), (1.0, "a"), (1.7, "a"), (2.8, "b"), (4.0, "b"), (5.4, "b")]


def test_the_render_refuses_an_undrawn_shot(tmp_path, no_downloads):
    film = _film(tmp_path)
    with pytest.raises(SystemExit, match="draws no s1, s2, s3, s4"):
        animate.check_drawn(film)
    js = film / "comp" / "shots.js"
    js.write_text(js.read_text().replace("const DRAW = {", "const DRAW = {\n" + "".join(
        f"  s{i}(ctx, s) {{}},\n" for i in range(1, 4))))
    with pytest.raises(SystemExit, match="draws no s4$|draws no s4:"):
        animate.check_drawn(film)


def test_the_render_refuses_a_film_that_carries_a_reference(tmp_path, no_downloads):
    ref = tmp_path / "frame.png"
    ref.write_bytes(b"\x89PNG someone else's picture")
    film = _film(tmp_path, refs=[ref], shots=1)
    js = film / "comp" / "shots.js"
    js.write_text(js.read_text().replace("const DRAW = {", "const DRAW = {\n  s1(ctx, s) {},"))
    animate.check_drawn(film)
    shutil.copy2(ref, film / "comp" / "backdrop.png")
    with pytest.raises(SystemExit, match="is the reference frame.png"):
        animate.check_drawn(film)


def test_sound_needs_cues_and_times_them_by_shot(tmp_path, no_downloads):
    film = _film(tmp_path)
    with pytest.raises(SystemExit, match="no cues"):
        animate.sound(film)
    (film / "sound.json").write_text(json.dumps({"cues": [{"type": "chime", "at": "s3+0.5"}]}))
    import soundfile as sf
    x, sr = sf.read(animate.sound(film))
    assert x.shape == (12 * sr, 2)
    assert abs(x[:int(6.4 * sr)]).max() == 0 and abs(x[int(6.5 * sr):int(7 * sr)]).max() > 0.01


def test_the_example_film_matches_its_own_shot_list():
    shots = animate.check_shots(json.loads((EXAMPLE / "shots.json").read_text()))
    js = (EXAMPLE / "shots.js").read_text()
    for s in shots:
        assert f"  {s['id']}(ctx, s) {{" in js
        assert f'id="w-{s["id"]}"' in (EXAMPLE / "words.html").read_text()
    cues = json.loads((EXAMPLE / "sound.json").read_text())["cues"]
    starts = {s["id"]: s["start"] for s in shots}
    assert all(0 <= animate.synth.resolve_at(c.get("at", 0), starts) < animate.duration(shots) for c in cues)


@pytest.mark.slow
def test_a_small_film_snaps_and_renders_to_a_checked_mp4(tmp_path):
    film = animate.new(tmp_path / "film", "A dot crosses", seconds=3, fmt="1:1", shots=1)
    js = film / "comp" / "shots.js"
    js.write_text(js.read_text().replace("const DRAW = {", """const DRAW = {
  s1(ctx, s) {
    ctx.fillStyle = S.mix("#203040", "#f08a3c", s.p);
    ctx.fillRect(0, 0, s.w, s.h);
    ctx.fillStyle = "#f3ede2";
    ctx.beginPath();
    ctx.arc(S.lerp(100, s.w - 100, s.p), s.h / 2, 80, 0, S.TAU);
    ctx.fill();
  },"""))
    (film / "sound.json").write_text(json.dumps({"cues": [{"type": "pad", "at": 0, "dur": 3, "gain": -12},
                                                         {"type": "chime", "at": "s1+1"}]}))
    sheets = animate.snap(film)
    assert sheets and all(p.exists() for p in sheets)
    frames = json.loads((film / "snaps" / "frames.json").read_text())
    assert [f["at"] for f in frames][:3] == [0.6, 1.5, 2.55] and {f["shot"] for f in frames} == {"s1"}
    assert all((film / "snaps" / f["file"]).exists() for f in frames)
    out = animate.render(film)
    info = ffmpeg.probe(out)
    assert (info["width"], info["height"]) == (1080, 1080) and abs(info["duration"] - 3) < 0.1
