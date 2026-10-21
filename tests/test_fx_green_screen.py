import os
from pathlib import Path

import numpy as np
import pytest

from editor.fx import _cutkit as K
from editor.fx import core, registry
from editor.fx import green_screen as G


def test_registered_with_params_and_duration():
    assert registry()["green_screen"] is G and {"image", "backdrop", "text", "wrap", "shadow"} <= set(G.PARAMS)


def test_placement_stay_keeps_the_speaker_where_the_shot_has_them():
    M, s = G.placement(1080, 1920, (0, 0.08, 1, 1), (380, 300, 700, 700), None, "center", place="stay")
    assert s == 1.0 and np.allclose(M, [[1, 0, 0], [0, 1, 0]])


def test_placement_lands_the_head_and_keeps_the_body_on_the_bottom_edge():
    W, H = 1080, 1920
    face = (270, 300, 810, 900)  # a close-up: face 0.5 W wide
    M, s = G.placement(W, H, (0, 0.08, 1, 1), face, None, "center")
    top = max(face[1] - 0.28 * (face[3] - face[1]), 0.08 * H)
    assert abs(M[1, 1] * top + M[1, 2] - G.HEAD_TOP * H) < 2
    assert M[1, 2] + s * H >= H - 1  # the body still runs off the bottom
    assert abs(s * 540 + M[0, 2] - 540) < 1
    # a wide shot is not blown up past full size
    _, s2 = G.placement(W, H, (0.35, 0.3, 0.65, 1), (480, 640, 600, 780), None, "left")
    assert s2 <= 1.0


@pytest.mark.parametrize("shape", [(1920, 1080), (2340, 1080), (1080, 1920)])
def test_fit_image_fills_the_frame(shape):
    img = (np.random.default_rng(0).random((*shape, 3)) * 255).astype(np.uint8)
    out = G.fit_image(img, 108, 192)
    assert out.shape == (192, 108, 3)


def test_candles_are_deterministic_and_follow_the_trend():
    up, again, down = G.candles(26, "up"), G.candles(26, "up"), G.candles(26, "down")
    assert up == again
    assert up[-1][3] > up[0][0] and down[-1][3] < down[0][0]
    assert all(h >= max(o, c) and lo <= min(o, c) for o, h, lo, c in up)


def test_composite_keeps_the_person_and_shades_around_them():
    W, H = 216, 384
    bg = np.full((H, W, 3), 240, np.uint8)
    pr = np.zeros((H, W, 3), np.uint8)
    pr[:] = (90, 60, 40)
    a = np.zeros((H, W), np.float32)
    a[200:, 60:156] = 1
    out = G.composite(bg, pr, a, dict(G.PARAMS), W, H)
    assert out.dtype == np.uint8 and out.shape == (H, W, 3)
    assert abs(int(out[320, 108, 0]) - 90) < 25  # the speaker, barely tinted
    assert out[195, 108].mean() < 236  # a soft shadow just outside them
    assert out[20, 10].mean() > 236  # backdrop untouched far away


def _ctx(tmp_path, style):
    ctx = core.Ctx(tmp_path / "w.mp4", tmp_path / "o.mp4", {"type": "green_screen", "at": 0, "dur": 2}, style,
                   tmp_path / "work")
    return ctx


@pytest.mark.parametrize("kind", ["app", "chart", "plain"])
def test_pages_carry_the_spec_text_escaped(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(core, "_font_file", lambda fam: "f.ttf")
    ctx = _ctx(tmp_path, {"name": "acme", "accent": "#00a676", "bg": "#111111", "ink": "#f0f0f0"})
    p = dict(G.PARAMS, text="Lorem <ipsum>\\Nlaunches", hi=["launches"], body="b & c", items=["One", "Two"],
             tag="NEW", value="", change="")
    page = {"app": G.app_page, "chart": G.chart_page, "plain": G.plain_page}[kind](ctx, p)
    assert "Lorem" in page and "&lt;ipsum&gt;" in page and "<ipsum>" not in page
    assert "Math.random" not in page and "springIn" in page
    if kind == "chart":
        assert "id='val'" not in page and "id='chg'" not in page  # no invented price or change


def test_arabic_text_is_set_right_to_left(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "_font_file", lambda fam: "f.ttf")
    ctx = _ctx(tmp_path, {"name": "acme"})
    page = G.app_page(ctx, dict(G.PARAMS, text="اليوم نطلق"))
    assert "dir='rtl'" in page


def test_combine_mattes_drops_furniture_and_fills_holes():
    W = 200
    modnet = np.zeros((300, W), np.float32)
    modnet[100:, 50:150] = 1
    modnet[100:160, 150:200] = 1   # the chair back MODNet kept
    modnet[220:260, 80:120] = 0    # a hole in a dark shirt
    sem = np.zeros_like(modnet)
    sem[100:, 50:150] = 1          # the semantic person: no chair, no hole
    out = K.combine_mattes(modnet, sem, W)
    assert out[130, 185] < 0.05 and out[240, 100] > 0.95 and out[200, 100] > 0.95


SRC = Path(os.environ.get("FX_TEST_CLIP", "/nonexistent"))


@pytest.mark.slow
@pytest.mark.skipif(not SRC.exists(), reason="set FX_TEST_CLIP to a 9:16 talking-head clip")
def test_renders_exact_frames(tmp_path):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    out = apply_fx(SRC, [{"type": "green_screen", "at": 1.0, "dur": 1.5, "text": "Hello"}], tmp_path,
                   {"name": "t", "accent": "#00a676"})
    assert abs(ffmpeg.probe(out)["duration"] - ffmpeg.probe(SRC)["duration"]) < 0.1
