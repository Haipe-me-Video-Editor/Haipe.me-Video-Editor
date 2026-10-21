import os
from pathlib import Path

import numpy as np
import pytest

from editor.fx import _behind as B
from editor.fx import frame_break as F
from editor.fx import registry

W, H = 1080, 1920
CLOSE = {"top": 170.0, "left": 200.0, "right": 820.0, "cx": 520.0, "eye_y": 580.0, "fw": 520.0, "chin": 1050.0}


def test_registered_with_params():
    assert registry()["frame_break"] is F and {"bg", "ui", "handle", "width", "pop"} <= set(F.PARAMS)


@pytest.mark.parametrize("width", [0.5, 0.6, 0.7])
def test_card_and_popped_head_fill_the_safe_zone(width):
    g = F.geometry(W, H, CLOSE, 900, width=width)
    s, ox, oy = g["s"], g["ox"], g["oy"]
    crown = s * CLOSE["top"] + oy
    top, bottom = s * g["y0"] + oy, s * (g["y0"] + g["h"]) + oy
    left, right = s * g["x0"] + ox, s * (g["x0"] + g["w"]) + ox
    assert crown >= B.SAFE[1] * H - 1 and bottom <= B.SAFE[3] * H + 1
    assert crown < top < s * CLOSE["eye_y"] + oy  # the card edge crosses between crown and eyes
    assert left >= 0 and right <= W and right - left <= max(width, 0.4) * W * 1.35
    assert 0 <= g["x0"] and g["x0"] + g["w"] <= W + 1e-6 and g["y0"] + g["h"] <= H + 1e-6  # inside the source


def test_rounded_mask_area_and_corners():
    m = F.rounded_mask(200, 300, 20, 30, 180, 270, 30)
    area = 160 * 240 - (4 - np.pi) * 30 ** 2
    assert abs(m.sum() - area) / area < 0.01
    assert m[30, 20] < 0.05 and m[150, 100] == 1


def test_ui_overlay_draws_inside_the_card():
    ui = F.ui_overlay(300, 500, "acme")
    assert ui.shape == (500, 300, 4) and ui[..., 3].max() > 0.8
    assert ui[:200, :, 3].max() < 0.05  # nothing in the top of the card (that is where the head is)


def test_shoulder_row_from_occupancy():
    occ = np.zeros((H // B.CELL, W // B.CELL), np.float32)
    occ[110:, :] = 1
    occ[20:110, 40:95] = 1
    assert F.shoulder_row(occ, CLOSE) == 110 * B.CELL


SRC = Path(os.environ.get("FX_TEST_CLIP", "/nonexistent"))


@pytest.mark.slow
@pytest.mark.skipif(not SRC.exists(), reason="set FX_TEST_CLIP to a 9:16 talking-head clip")
def test_renders_exact_frames(tmp_path):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    out = apply_fx(SRC, [{"type": "frame_break", "at": 1.0, "dur": 2.0}], tmp_path, {"name": "t"})
    assert abs(ffmpeg.probe(out)["duration"] - ffmpeg.probe(SRC)["duration"]) < 0.1
