"""One-take films: no dissolves, one camera, and a check that fails any shot hand-over that jumps."""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from editor import animate

KIT = Path(animate.__file__).with_name("animate_kit")
EXAMPLE = Path(__file__).parents[1] / "skills" / "animate" / "examples" / "onetake"


@pytest.fixture
def no_downloads(monkeypatch, tmp_path):
    font = tmp_path / "stand-in.ttf"
    font.write_bytes(b"font")
    monkeypatch.setattr(animate.fonts, "ensure_font", lambda family: font)


def test_onetake_scaffold_has_no_dissolve_and_says_so(tmp_path, no_downloads):
    film = animate.new(tmp_path / "film", "A dot grows", seconds=6, shots=3, onetake=True)
    brief = json.loads((film / "brief.json").read_text())
    assert brief["mode"] == "onetake" and brief["blend"] == 0
    timing = (film / "comp" / "timing.js").read_text()
    assert '"mode": "onetake"' in timing and '"blend": 0' in timing
    assert "const CAMERA = null;" in (film / "comp" / "shots.js").read_text()
    plain = animate.new(tmp_path / "plain", "A dot grows", seconds=6, shots=3)
    assert json.loads((plain / "brief.json").read_text())["mode"] == "shots"


def test_cut_is_a_yes_or_no():
    with pytest.raises(SystemExit, match="cut is true"):
        animate.check_shots([{"id": "a", "start": 0, "dur": 2}, {"id": "b", "start": 2, "dur": 2, "cut": "yes"}])


def test_handovers_skip_a_meant_cut_and_straddle_the_boundary():
    shots = [{"id": "a", "start": 0, "dur": 2}, {"id": "b", "start": 2, "dur": 2},
             {"id": "c", "start": 4, "dur": 1, "cut": True}]
    h = animate.handovers(shots, 30)
    assert [(x["from"], x["to"]) for x in h] == [("a", "b")]
    before, last, first, after = h[0]["times"]
    assert last < 2 <= first and first == 2 and before < last and after > first


def test_change_measures_cuts_and_motion_apart():
    rng = np.random.default_rng(0)
    a = rng.uniform(0.2, 0.3, (240, 135)).astype(np.float32)
    assert animate.change(a, a) == 0
    moved = np.roll(a, 1, axis=1)
    cut = 1 - a
    assert animate.change(a, moved) < animate.change(a, cut)
    dot = a.copy()
    dot[100:130, 60:90] = 1.0  # a thing appearing from nowhere in a few cells
    assert animate.change(a, dot) > animate.JUMP_FLOOR


def test_judge_allows_a_fast_move_and_fails_a_cut_between_still_frames():
    assert animate.judge(0.002, 0.004, 0.003)          # calm hand-over
    assert animate.judge(0.12, 0.2, 0.1)               # a whip pan: big, but no bigger than the motion
    assert not animate.judge(0.001, 0.5, 0.001)        # a hard cut between still frames


def test_the_example_film_is_a_one_take_film_that_tiles():
    shots = animate.check_shots(json.loads((EXAMPLE / "shots.json").read_text()))
    assert not any(s.get("cut") for s in shots)
    js = (EXAMPLE / "shots.js").read_text()
    assert all(f"  {s['id']}(ctx, s)" in js for s in shots)
    assert "camera: CAMERA" in js and "S.keys(" in js
    cues = json.loads((EXAMPLE / "sound.json").read_text())["cues"]
    starts = {s["id"]: s["start"] for s in shots}
    assert all(0 <= animate.synth.resolve_at(c.get("at", 0), starts) < animate.duration(shots) for c in cues)


NODE = shutil.which("node")


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_studio_keys_and_morph_carry_values_through_time():
    studio = json.dumps(str(KIT / "studio.js"))
    script = """
      global.window = {};
      require(STUDIO);
      const S = window.Studio;
      const k = [[0, { x: 0, fill: "#000000" }], [2, { x: 100, fill: "#ffffff" }, S.ease.linear]];
      const out = {
        before: S.keys(-1, k).x, mid: S.keys(1, k).x, after: S.keys(5, k).x, colour: S.keys(1, k).fill,
        num: S.keys(0.5, [[0, 10], [1, 20, S.ease.linear]]),
        dot: S.morph({ x: 0, y: 0, w: 20, h: 20, r: 10 }, { x: 0, y: 0, w: 200, h: 400, r: 40 }, 0.5),
        clamp: S.morph({ w: 1, h: 1 }, { w: 3, h: 3 }, 2).w,
      };
      console.log(JSON.stringify(out));
    """.replace("STUDIO", studio)
    out = json.loads(subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True).stdout)
    assert (out["before"], out["mid"], out["after"]) == (0, 50, 100)
    assert out["colour"] == "rgb(128,128,128)" and out["num"] == 15
    assert out["dot"] == {"x": 0, "y": 0, "w": 110, "h": 210, "r": 25, "alpha": 1} and out["clamp"] == 3


def _draw(film, body):
    js = film / "comp" / "shots.js"
    js.write_text(js.read_text().replace("const DRAW = {", "const DRAW = {\n" + body))


@pytest.mark.slow
def test_check_passes_a_flowing_film_and_fails_a_cut(tmp_path):
    film = animate.new(tmp_path / "flow", "A dot crosses", seconds=4, fmt="1:1", shots=2, onetake=True)
    # both shots draw the same dot from film time: it crosses the boundary without a jump
    same = """
  s1(ctx, s) { ctx.fillStyle = "#334"; ctx.fillRect(0, 0, s.w, s.h); ctx.fillStyle = "#f84";
    ctx.beginPath(); ctx.arc(S.lerp(150, s.w - 150, s.t / 4), s.h / 2, 120, 0, S.TAU); ctx.fill(); },
  s2(ctx, s) { DRAW.s1(ctx, s); },"""
    _draw(film, same)
    results = animate.continuity(film)
    assert len(results) == 1 and results[0]["ok"], results
    cut = animate.new(tmp_path / "cut", "A dot jumps", seconds=4, fmt="1:1", shots=2, onetake=True)
    _draw(cut, same.replace("s2(ctx, s) { DRAW.s1(ctx, s); },",
                            's2(ctx, s) { ctx.fillStyle = "#9cf"; ctx.fillRect(0, 0, s.w, s.h); },'))
    results = animate.continuity(cut)
    assert not results[0]["ok"] and results[0]["jump"] > 0.3, results
    with pytest.raises(SystemExit, match="one take broken"):
        animate.require_continuity(cut)
    shots = json.loads((cut / "shots.json").read_text())
    shots[1]["cut"] = True
    (cut / "shots.json").write_text(json.dumps(shots))
    assert animate.continuity(cut) == []  # a meant cut is not checked
