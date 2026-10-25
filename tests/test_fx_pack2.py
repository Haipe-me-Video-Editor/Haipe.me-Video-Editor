"""The reel-inspired effects: photo_drop, shatter, lens, portal, viewfinder, news_bars."""
import itertools
import math
import os
from pathlib import Path

import numpy as np
import pytest

from editor.fx import _behind as B
from editor.fx import lens, news_bars, photo_drop, portal, registry, shatter, viewfinder

W, H = 1080, 1920
NEW = {"photo_drop": photo_drop, "shatter": shatter, "lens": lens, "portal": portal, "viewfinder": viewfinder,
       "news_bars": news_bars}
FACE = {"cx": 540.0, "cy": 700.0, "fw": 330.0, "eye_y": 650.0, "top": 520.0}


@pytest.mark.parametrize("name", sorted(NEW))
def test_registered_with_the_planner_fields(name):
    mod = registry()[name]
    assert mod is NEW[name]
    assert mod.DOC and mod.BEST_FOR and mod.PARAMS and len(mod.DUR) == 2
    assert "at" not in mod.PARAMS and "dur" not in mod.PARAMS  # those are the window's own fields


# photo_drop -----------------------------------------------------------------------------------------------------
def test_photo_drop_starts_and_ends_on_the_full_frame():
    s, rot, dy, fade = photo_drop.pose(0.0, 3.0, 0.7, -4, "bouncy", True, H)
    assert (s, rot, dy, fade) == (1.0, 0.0, 0.0, 0.0)
    s, rot, dy, _ = photo_drop.pose(3.0, 3.0, 0.7, -4, "bouncy", True, H)
    assert abs(s - 1) < 1e-6 and abs(rot) < 1e-6 and abs(dy) < 1e-6


def test_photo_drop_rests_at_its_size_and_tilt():
    s, rot, dy, fade = photo_drop.pose(1.5, 3.0, 0.7, -4, "bouncy", True, H)
    assert abs(s - 0.7) < 1e-3 and abs(rot + 4) < 0.05 and abs(dy) < 1 and fade == 1


def test_photo_drop_borders():
    assert photo_drop.borders(W, H, 0.04, "border") == pytest.approx((43.2, 43.2, 43.2))
    _l, t, b = photo_drop.borders(W, H, 0.04, "polaroid")
    assert b > 3 * t
    with pytest.raises(ValueError):
        photo_drop.borders(W, H, 0.04, "frame")


# shatter --------------------------------------------------------------------------------------------------------
def test_shatter_cells_tile_the_frame():
    rng = np.random.default_rng(1)
    pts = shatter.seeds(W, H, (540, 650), 44, rng)
    polys = shatter.cells(W, H, pts)
    def shoelace(p):
        x, y = p[:, 0].astype(np.float64), p[:, 1].astype(np.float64)
        return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2
    area = sum(shoelace(p) for p in polys)
    assert len(polys) == len(pts) and abs(area - W * H) / (W * H) < 0.01


def test_shatter_splinters_are_small_at_the_impact():
    rng = np.random.default_rng(1)
    impact = (540, 650)
    polys = shatter.cells(W, H, shatter.seeds(W, H, impact, 44, rng))
    def size(p):
        return float(np.ptp(p, axis=0).max())
    near = [size(p) for p in polys if np.hypot(*(p.mean(0) - impact)) < 250]
    far = [size(p) for p in polys if np.hypot(*(p.mean(0) - impact)) > 700]
    assert near and far and np.median(near) < np.median(far)


def test_shatter_shard_is_in_place_at_the_hit():
    rng = np.random.default_rng(2)
    poly = np.float32([[100, 100], [300, 120], [200, 300]])
    M = shatter.shard_matrix(shatter.motion(poly, (540, 650), H, rng), 0.0, H)
    assert np.allclose(M, [[1, 0, 0], [0, 1, 0]], atol=1e-9)


# lens -----------------------------------------------------------------------------------------------------------
def test_lens_magnifies_the_centre_and_covers_a_disc():
    F = np.zeros((400, 400, 3), np.float32)
    F[::20] = 1.0  # horizontal lines every 20 px
    img, cov = lens.refract(F, (200, 200), 100, 2.0, 0.0)
    assert abs(cov.sum() - math.pi * 100 ** 2) / (math.pi * 100 ** 2) < 0.02
    col = img[150:250, 200, 1]
    lines_in = int((np.diff((col > 0.5).astype(int)) == 1).sum())
    assert lines_in <= 3  # 100 px of picture shows ~5 lines untouched; magnified 2x, about half


def test_lens_sweep_path_settles_and_leaves():
    start, settle, end = (-300, 700), (540, 650), (1400, 600)
    c, _sc, _ = lens.path_at(0.0, 3.0, start, settle, end, "sweep")
    assert c == pytest.approx(start)
    c, _, _ = lens.path_at(1.5, 3.0, start, settle, end, "sweep")
    assert c == pytest.approx(settle, abs=2)
    c, _, _ = lens.path_at(3.0, 3.0, start, settle, end, "sweep")
    assert c == pytest.approx(end)
    assert lens.path_at(0.0, 3.0, start, settle, end, "face")[1] == pytest.approx(0, abs=1e-6)


# portal ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("corner", ["tl", "tr", "bl", "br"])
def test_portal_window_starts_inside_the_safe_zone(corner):
    R = 0.13 * W
    x, y = portal.corner_centre(corner, R, W, H)
    assert B.SAFE[0] * W <= x - R and x + R <= B.SAFE[2] * W
    assert B.SAFE[1] * H <= y - R and y + R <= B.SAFE[3] * H


def test_portal_disc_area():
    d = portal.disc(400, 400, (200, 200), 80)
    assert abs(d.sum() - math.pi * 80 ** 2) / (math.pi * 80 ** 2) < 0.01


# viewfinder -----------------------------------------------------------------------------------------------------
def test_viewfinder_steps_spread_inside_the_window():
    t = viewfinder.step_times([1, 1.8, 3, 1], [], 3.0)
    assert len(t) == 3 and t == sorted(t) and t[0] > 0 and t[-1] + viewfinder.STEP < 3.0
    with pytest.raises(ValueError):
        viewfinder.step_times([1, 2], [0.5, 1.0], 3.0)


def test_viewfinder_zoom_lands_on_each_level():
    zooms, times = [1.0, 1.8, 3.0, 1.0], [0.5, 1.2, 2.0]
    assert viewfinder.zoom_at(0.2, zooms, times) == 1.0
    assert viewfinder.zoom_at(1.1, zooms, times) == pytest.approx(1.8, abs=1e-3)
    assert viewfinder.zoom_at(1.9, zooms, times) == pytest.approx(3.0, abs=1e-3)
    assert viewfinder.zoom_at(2.9, zooms, times) == pytest.approx(1.0, abs=1e-3)


def test_viewfinder_timecode():
    assert viewfinder.timecode(12.5, 30) == "00:00:12:15"
    assert viewfinder.timecode(3725.0, 25) == "01:02:05:00"


# news_bars ------------------------------------------------------------------------------------------------------
def test_news_bars_items_get_tags_and_capitals():
    out = news_bars.normalise(["one", {"tag": "live", "text": "two"}], ["BREAKING", "JUST IN"])
    assert out == [{"tag": "BREAKING", "text": "ONE"}, {"tag": "LIVE", "text": "TWO"}]
    with pytest.raises(ValueError):
        news_bars.normalise([], ["X"])
    with pytest.raises(ValueError):
        news_bars.normalise(["x"] * 9, ["X"])


def test_news_bars_stay_off_the_face_while_there_is_room():
    face = {"cx": 540.0, "cy": 800.0, "fw": 260.0, "eye_y": 760.0, "top": 650.0}  # a smaller head, more room
    hs = [110.0, 180.0, 110.0, 110.0]  # one two-line strip among one-line ones
    ys = news_bars.slots(hs, face, W, H)
    head_top, chin = face["top"] - face["fw"] * 0.35, face["cy"] + face["fw"] * 0.75
    assert len(ys) == 4
    assert all(y + h / 2 <= head_top or y - h / 2 >= chin for y, h in zip(ys, hs))
    assert all(B.SAFE[1] * H <= y - h / 2 and y + h / 2 <= B.SAFE[3] * H for y, h in zip(ys, hs))
    spans = sorted((y - h / 2, y + h / 2) for y, h in zip(ys, hs))
    assert all(a[1] <= b[0] for a, b in itertools.pairwise(spans))  # no two strips overlap


def test_news_bars_overflow_goes_over_the_mouth_not_the_eyes():
    ys = news_bars.slots([130.0] * 8, FACE, W, H)
    assert len(ys) == 8 and all(abs(y - FACE["eye_y"]) > 0.056 * H for y in ys)


def test_news_bars_long_headline_wraps_to_fit():
    one = news_bars.sprite("BREAKING", "SHORT ONE", 100, np.array([255, 120, 20]), 0.0, 800)
    two = news_bars.sprite("BREAKING", "A HEADLINE THAT WRAPS ONTO TWO LINES", 100, np.array([255, 120, 20]), 0.0, 800)
    for spr in (one, two):
        cols = np.nonzero((spr[..., 3] > 0.9).any(axis=0))[0]
        assert spr.shape[2] == 4 and cols.size and cols[-1] - cols[0] <= 800
    rows = lambda spr: np.ptp(np.nonzero((spr[..., 3] > 0.9).any(axis=1))[0])
    assert rows(two) > rows(one) * 1.4  # the long one became a taller, two-line bar
    with pytest.raises(ValueError, match="too long"):
        news_bars.sprite("LIVE", "WORDS " * 40, 100, np.array([255, 120, 20]), 0.0, 800)


SRC = Path(os.environ.get("FX_TEST_CLIP", "/nonexistent"))


@pytest.mark.slow
@pytest.mark.skipif(not SRC.exists(), reason="set FX_TEST_CLIP to a 9:16 talking-head clip")
@pytest.mark.parametrize("spec", [{"type": "photo_drop"}, {"type": "shatter"}, {"type": "lens"}, {"type": "portal"},
                                  {"type": "viewfinder"}, {"type": "news_bars", "items": ["one", "two"]}])
def test_renders_exact_frames(tmp_path, spec):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    out = apply_fx(SRC, [{**spec, "at": 0.5, "dur": 2.0}], tmp_path, {"name": "t"})
    assert abs(ffmpeg.probe(out)["duration"] - ffmpeg.probe(SRC)["duration"]) < 0.1
