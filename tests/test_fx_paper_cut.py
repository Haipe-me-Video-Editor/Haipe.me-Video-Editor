import os
from pathlib import Path

import numpy as np
import pytest

from editor.fx import _cutkit as K
from editor.fx import paper_cut as P
from editor.fx import registry

STYLES = [
    {"name": "green", "accent": "#00a676", "bg": "#111111", "live": "#ff3b3b"},
    {"name": "lime", "accent": "#a3e635", "bg": "#222222", "live": "#d62828"},
    {"name": "blue", "accent": "#4c6ef5", "bg": "#1a1a1a", "down": "#e4572e"},
]


def test_registered_with_params_and_duration():
    assert registry()["paper_cut"] is P and {"text", "caption", "side", "scale"} <= set(P.PARAMS)


@pytest.mark.parametrize("style", STYLES)
def test_palette_marks_differ_from_the_accent(style):
    pal = P.palette(style)
    assert np.abs(pal["mark"] - pal["accent"]).sum() >= 90
    assert all(v.shape == (3,) for v in pal.values())


def test_stop_motion_holds_two_or_three_frames():
    steps = K.steps_of(90)
    runs = np.diff(np.flatnonzero(np.diff(steps)))
    assert len(steps) == 90 and set(runs) <= {2, 3}


def test_place_keeps_cut_edges_on_the_frame_edge():
    W, H = 1080, 1920
    M = K.place(W, H, (0.0, 0.08, 1.0, 1.0), 0.62, "left", bleed=10)
    left, right = M[0, 2], M[0, 2] + 0.62 * W
    bottom = M[1, 2] + 0.62 * H
    assert left <= 0 and bottom >= H and right < W  # the left / bottom cut stay hidden; the right cut is the sticker
    M = K.place(W, H, (0.3, 0.3, 0.7, 1.0), 0.8, "right")
    assert abs(M[0, 2] + 0.8 * 0.5 * W - 0.64 * W) < 1


def test_torn_polygon_follows_the_rectangle():
    poly = P.torn_poly([(100, 100), (300, 100), (300, 200), (100, 200)], 1, 5)
    assert len(poly) > 40
    assert 85 < poly[:, 0].min() < 115 and 285 < poly[:, 0].max() < 315


def test_collage_sprites_arrive_in_steps_and_mirror_for_the_right(monkeypatch):
    W, H = 216, 384
    monkeypatch.setattr(P, "ransom", lambda *a, **k: ([{"rgba": np.zeros((10, 10, 4), np.uint8), "x": 5, "y": 5,
                                                         "id": 100}], (5, 5, 15, 15)))
    pal = P.palette(STYLES[0])
    left = P.collage(W, H, pal, 0, "left", "5", "")
    right = P.collage(W, H, pal, 0, "right", "5", "")
    assert min(s["at"] for s in left) == 1 and any(s["id"] == 100 for s in left)
    lx = {s["id"]: s["x"] + s["rgba"].shape[1] / 2 for s in left}
    rx = {s["id"]: s["x"] + s["rgba"].shape[1] / 2 for s in right}
    assert abs(lx[2] + rx[2] - W) < 2  # the torn piece is mirrored
    assert lx[100] == rx[100]  # text is not


def test_sticker_border_surrounds_the_person():
    W, H = 216, 384
    bg = np.full((H, W, 3), 200, np.uint8)
    frame = np.full((H, W, 3), 30, np.uint8)
    A = np.zeros((H, W), np.float32)
    A[150:, 60:150] = 1
    out = P.sticker(bg, frame, A, K.IDENTITY, 8, np.zeros((H, W), np.float32), W, H)
    assert out[300, 100].max() < 60  # the person
    assert out[145, 100].min() > 235  # white border just above them
    assert out[50, 20].mean() < 205 and out[50, 20].mean() > 180  # paper, untouched far away


def test_compose_is_stable_within_a_step_and_moves_between_steps():
    W, H = 120, 200
    paper = np.full((H, W, 3), 230, np.uint8)
    rgba = np.zeros((40, 40, 4), np.uint8)
    rgba[10:30, 10:30] = (255, 0, 0, 255)
    sp = [{"rgba": rgba, "x": 40, "y": 60, "id": 1, "at": 0}]
    a, b, c = P.compose(paper, sp, 3, 0, W, H), P.compose(paper, sp, 3, 0, W, H), P.compose(paper, sp, 4, 0, W, H)
    assert np.array_equal(a, b) and not np.array_equal(a, c)


SRC = Path(os.environ.get("FX_TEST_CLIP", "/nonexistent"))


@pytest.mark.slow
@pytest.mark.skipif(not SRC.exists(), reason="set FX_TEST_CLIP to a 9:16 talking-head clip")
def test_renders_exact_frames(tmp_path):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    out = apply_fx(SRC, [{"type": "paper_cut", "at": 1.0, "dur": 1.5, "text": "5"}], tmp_path, {"name": "t"})
    assert abs(ffmpeg.probe(out)["duration"] - ffmpeg.probe(SRC)["duration"]) < 0.1


def test_drop_islands_keeps_the_body_and_removes_specks():
    a = np.zeros((200, 100), np.float32)
    a[80:, 20:80] = 1
    a[10:14, 5:9] = 1
    out = K.drop_islands(a, 0.003)
    assert out[150, 50] == 1 and out[12, 7] == 0


def test_fill_holes_closes_the_shirt_but_not_the_gap_under_a_raised_arm():
    a = np.zeros((200, 100), np.float32)
    a[60:, 20:80] = 1
    a[120:140, 40:60] = 0      # a hole in the shirt
    a[150:, 45:55] = 0         # a gap open to the bottom edge counts as enclosed (the body is cut there)
    a[60:100, 0:20] = 1        # an arm out to the side...
    a[100:110, 0:20] = 0       # ...with background under it, open to the left edge
    out = K.fill_holes(a)
    assert out[130, 50] > 0.9 and out[105, 10] < 0.1


def test_style_controls_drop_marks_and_recolour():
    from editor.fx import paper_cut as pc
    pal = pc.palette({"accent": "#00a676"}, {"piece": "#4c6ef5", "tape": "#f0f0f0"})
    assert list(pal["piece"]) == [0x4C, 0x6E, 0xF5] and list(pal["tape"]) == [0xF0, 0xF0, 0xF0]
    all_ids = {sp["id"] for sp in pc.collage(216, 384, pal, 0, "left", "", "")}
    no_star = {sp["id"] for sp in pc.collage(216, 384, pal, 0, "left", "", "", marks=["hatch", "loops"])}
    assert 9 in all_ids and 9 not in no_star  # the asterisk is gone
    assert {5, 7, 8} & no_star == set()       # and so are the accent hatch and the crosses
