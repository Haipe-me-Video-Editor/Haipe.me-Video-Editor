import types

import numpy as np
import pytest

from editor.fx import pull_back as pb
from editor.fx import registry
from editor.style import load_style


def test_registered():
    assert registry()["pull_back"] is pb and {"title", "items", "ui", "end"} <= set(pb.PARAMS)


def test_layout_pane_has_frame_aspect_and_window_respects_safe_zones():
    W, H = 1080, 1920
    lay = pb.layout(W, H)
    _, _, pw, ph = lay["pane"]
    assert abs(pw / ph - W / H) < 0.002
    x0, y0, w, h = lay["win"]
    assert y0 >= 0.13 * H and y0 + h <= 0.8 * H and x0 + w <= 0.88 * W and x0 > 0
    assert lay["side"][2] > 0.25 * W  # room for real list text


def test_camera_starts_on_the_frame_and_rests_at_identity():
    W, H = 1080, 1920
    lay = pb.layout(W, H)
    px, py, pw, ph = lay["pane"]
    A = np.array([[pw / W, 0, px], [0, ph / H, py], [0, 0, 1]])
    P0 = pb.plane_matrix(0.0, lay, W, H, tilt_deg=7) @ A
    assert np.allclose(P0, np.eye(3), atol=1e-6)  # k=0: the footage is exactly the original frame
    assert np.allclose(pb.plane_matrix(1.0, lay, W, H, tilt_deg=7), np.eye(3), atol=1e-6)
    mid = pb.plane_matrix(0.5, lay, W, H, tilt_deg=7)
    assert abs(mid[2, 0]) > 1e-6  # the swing adds perspective mid-move


def test_pull_curve_and_time_budget():
    assert pb.pull_k(0, 3.5, 1.1, 0.7) == 0
    assert pb.pull_k(2.0, 3.5, 1.1, 0.7) == pytest.approx(1, abs=0.01)
    assert pb.pull_k(3.5, 3.5, 1.1, 0.7) == pytest.approx(0, abs=1e-6)
    assert pb.pull_k(3.5, 3.5, 1.1, 0.7, "hold") == pytest.approx(1, abs=0.01)
    pull, push = pb.times(2.4, 1.1, 0.7, "push_in")
    assert pull + push <= 2.4 * 0.65 + 1e-9


@pytest.mark.parametrize("style,ui", [("default", "editor"), ("finance", "trading")])
def test_page_escapes_text_and_uses_the_style(style, ui):
    st = load_style(style)
    ctx = types.SimpleNamespace(W=1080, H=1920, dur=3.5, style=st)
    lay = pb.layout(1080, 1920)
    body, css, js = pb.page_parts(ctx, ui, "A <b> title", ["one & two", "ثلاثة"], "Export", lay, 1.1, 0.7,
                                  "push_in", False)
    assert "A &lt;b&gt; title" in body and "one &amp; two" in body and "ثلاثة" in body
    assert st["accent"].lower() in css.lower()
    assert "DONE" in js and "borderRadius" in js
