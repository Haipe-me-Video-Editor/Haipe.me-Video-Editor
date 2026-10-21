import os
from pathlib import Path

import numpy as np
import pytest

from editor import fonts
from editor.fx import _behind as B
from editor.fx import registry
from editor.fx import wall_text as WT

W, H = 1080, 1920
GW, GH = W // B.CELL, H // B.CELL


def _occ(head_cx, head_top, head_r, shoulder_y):
    """Synthetic person: a round head and shoulders spanning the frame below shoulder_y (grid cells)."""
    yy, xx = np.mgrid[0:GH, 0:GW]
    head = ((xx - head_cx) / head_r) ** 2 + ((yy - head_top - head_r * 1.3) / (head_r * 1.3)) ** 2 <= 1
    body = yy >= shoulder_y
    return (head | body).astype(np.float32)


def _font():
    p = fonts.FONT_CACHE / "anton-700.ttf"
    if not p.exists():
        pytest.skip("Anton not cached (fonts download in slow tests)")
    return p


def test_registered_with_smart_placement_params():
    assert registry()["wall_text"] is WT and {"text", "place", "size", "y", "hi"} <= set(WT.PARAMS)


def test_spring_ease_settles_and_exit_is_smooth():
    s = B.spring("snappy")
    assert s(0) == 0 and s(1) == 1 and max(s(t / 100) for t in range(101)) > 1.0
    assert B.ease_in(0) == 0 and B.ease_in(1) == 1 and B.ease_in(0.5) < 0.5


def test_split_lines_offers_one_line_and_a_balanced_split():
    assert B.split_lines("LAUNCH DAY") == [[["LAUNCH", "DAY"]], [["LAUNCH"], ["DAY"]]]
    assert B.split_lines("BIG\\NLAUNCH DAY") == [[["BIG"], ["LAUNCH", "DAY"]]]


def test_blocked_grid_bans_the_unsafe_margins():
    b = B.blocked_grid(np.zeros((GH, GW), np.float32), W, H)
    assert b[: int(B.SAFE[1] * GH) - 1].all() and b[int(B.SAFE[3] * GH) + 1:].all()
    assert b[:, int(B.SAFE[2] * GW) + 1:].all() and not b[GH // 2, GW // 2]


def test_wide_shot_goes_horizontal_above_the_head():
    occ = _occ(GW / 2, GH * 0.42, GW * 0.09, GH * 0.62)  # small person low in frame: lots of wall above
    blocked = B.blocked_grid(occ, W, H, margin_cells=0)
    blk = B.Block([["PLATFORM"]], _font())
    best = B.solve(blocked, [blk], (W / 2, H * 0.45), (0.05 * W, 0.3 * W), max_letter=0.3, max_total=0.12)
    assert best["rotate"] == 0
    crown = H * 0.42
    assert best["y"] + best["h"] / 2 < crown and best["hidden"] <= 0.12  # above the crown, the crown may tuck in
    assert best["em"] > 0.15 * W


def test_close_up_turns_the_word_up_the_free_side():
    occ = _occ(GW * 0.47, GH * 0.08, GW * 0.25, GH * 0.47)  # head fills the top half, wall only at the sides
    blocked = B.blocked_grid(occ, W, H, margin_cells=0)
    blk = B.Block([["PLATFORM"]], _font())
    best = B.solve(blocked, [blk], (W * 0.47, H * 0.2), (0.05 * W, 0.3 * W), max_letter=0.3, max_total=0.12)
    assert best["rotate"] == 1 and best["x"] + best["w"] / 2 < W * 0.47  # reads up the left side
    m = np.rot90(blk.mask(), 1)
    pos = B.fit(blocked, m, best["scale"], (W * 0.47 / B.CELL, H * 0.2 / B.CELL), max_letter=0.3, max_total=0.12)
    assert pos is not None and pos[2] <= 0.12


def test_no_rotation_when_not_allowed_and_none_when_nothing_fits():
    occ = _occ(GW * 0.47, GH * 0.08, GW * 0.25, GH * 0.47)
    blocked = B.blocked_grid(occ, W, H, margin_cells=0)
    blk = B.Block([["PLATFORM"]], _font())
    best = B.solve(blocked, [blk], (W * 0.47, H * 0.2), (0.05 * W, 0.3 * W), allow_rotate=False)
    assert best is None or best["rotate"] == 0
    full = np.ones((GH, GW), np.float32)
    assert B.solve(full, [blk], (W / 2, H / 2), (0.05 * W, 0.3 * W)) is None


def test_word_sprites_line_up_with_the_block():
    blk = B.Block([["LAUNCH"], ["RESULTS"]], _font())
    sp = blk.word_sprites(0.5)
    assert [s["word"] for s in sp] == ["LAUNCH", "RESULTS"] and sp[0]["y"] < sp[1]["y"]
    rot = blk.word_sprites(0.5, rotate=1)
    assert rot[0]["alpha"].shape[0] > rot[0]["alpha"].shape[1]  # turned: taller than wide


def test_arabic_detection():
    assert B.is_arabic("مرحبا") and not B.is_arabic("PLATFORM")


SRC = Path(os.environ.get("FX_TEST_CLIP", "/nonexistent"))


@pytest.mark.slow
@pytest.mark.skipif(not SRC.exists(), reason="set FX_TEST_CLIP to a 9:16 talking-head clip")
def test_renders_exact_frames(tmp_path):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    out = apply_fx(SRC, [{"type": "wall_text", "at": 1.0, "dur": 1.5, "text": "LAUNCH DAY"}], tmp_path,
                   {"name": "t"})
    assert abs(ffmpeg.probe(out)["duration"] - ffmpeg.probe(SRC)["duration"]) < 0.1
