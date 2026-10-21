import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from editor.fx import glass_type as G
from editor.fx import registry


def test_registered_with_params_and_duration():
    assert registry()["glass_type"] is G and {"text", "font", "place", "depth", "tilt", "frost"} <= set(G.PARAMS)
    assert G.DUR[0] >= 1.5


def _disc(r=40, pad=20):
    m = np.zeros((2 * (r + pad), 2 * (r + pad)), np.float32)
    cv2.circle(m, (r + pad, r + pad), r, 1.0, -1, lineType=cv2.LINE_AA)
    return m


def test_bevel_normals_point_outward_and_face_is_flat():
    m = _disc()
    maps = G.letter_maps(m, em=200)
    nx, ny, h = maps[..., 1], maps[..., 2], maps[..., 3]
    c = m.shape[0] // 2
    assert h[c, c] > 0.95 and abs(nx[c, c]) < 1e-3  # flat face in the middle
    assert nx[c, c + 37] > 0.05 and nx[c, c - 37] < -0.05  # right edge faces right, left edge faces left
    assert ny[c + 37, c] > 0.05 and ny[c - 37, c] < -0.05


def test_scatter_is_deterministic_and_bounded():
    a, b = G.scatter(6, 200, "PLATFORM"), G.scatter(6, 200, "PLATFORM")
    assert a == b and a != G.scatter(6, 200, "RESULTS")
    assert all(abs(dx) <= 200 and abs(dy) <= 260 and abs(r) <= 22 and 1.2 <= s <= 1.5 for dx, dy, r, s in a)


@pytest.mark.parametrize("far", ["left", "right", "top", "bottom"])
def test_keystone_shrinks_only_the_far_edge(far):
    w, h = 400, 200
    M = G.homography(w, h, far, 0.2)
    pts = cv2.perspectiveTransform(np.float32([[[0, 0], [w, 0], [w, h], [0, h]]]), M)[0]
    near = {"left": [1, 2], "right": [0, 3], "top": [2, 3], "bottom": [0, 1]}[far]
    assert np.allclose(pts[near], np.float32([[0, 0], [w, 0], [w, h], [0, h]])[near], atol=1e-3)
    assert pts[:, 0].min() >= -1e-3 and pts[:, 0].max() <= w + 1e-3  # stays inside the canvas
    assert pts[:, 1].min() >= -1e-3 and pts[:, 1].max() <= h + 1e-3


def test_shade_makes_an_opaque_lit_slab_with_a_shadow_beside_it():
    bg = np.full((160, 260, 3), 0.4, np.float32)
    m = np.zeros((160, 260), np.float32)
    m[40:110, 60:180] = 1
    maps = np.zeros((160, 260, 4), np.float32)
    lm = G.letter_maps(m, em=120)
    maps[:] = lm
    tint = np.ones((160, 260, 3), np.float32)
    u = np.zeros((160, 260), np.float32)
    layer, alpha, shadow = G.shade(bg, maps, tint, np.array([6.0, 4.0]), 6, 120, 1.0, u, u, 0.0, 9.0)
    assert alpha[75, 120] > 0.99 and layer[75, 120].mean() > 0.4  # glass brighter than the wall behind it
    assert alpha[75, 184] > 0.3  # extrusion visible on the vanishing-point side
    assert shadow[118, 140] > 0.05 and shadow[20, 20] < 0.01


SRC = Path(os.environ.get("FX_TEST_CLIP", "/nonexistent"))


@pytest.mark.slow
@pytest.mark.skipif(not SRC.exists(), reason="set FX_TEST_CLIP to a 9:16 talking-head clip")
def test_renders_exact_frames(tmp_path):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    out = apply_fx(SRC, [{"type": "glass_type", "at": 1.0, "dur": 2.0, "text": "PLATFORM"}], tmp_path, {"name": "t"})
    assert abs(ffmpeg.probe(out)["duration"] - ffmpeg.probe(SRC)["duration"]) < 0.1
