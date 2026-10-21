"""orbit: ring geometry and per-frame card paths (pure), plus a slow render."""
import math

import numpy as np
import pytest

from editor.fx import _spatial as sp
from editor.fx import orbit as o

W, H, G = 1080, 1920, sp.GRID


def scene(kind):
    cov = np.zeros((H // G, W // G), np.float32)
    mask = np.zeros_like(cov)
    if kind == "close":
        cov[int(0.12 * H / G):int(0.55 * H / G), int(0.22 * W / G):int(0.74 * W / G)] = 1
        cov[int(0.52 * H / G):, :] = 1
        yy, xx = np.mgrid[0:H // G, 0:W // G]
        mask[((xx - 0.48 * W / G) / (0.30 * W / G)) ** 2 + ((yy - 0.37 * H / G) / (0.23 * H / G)) ** 2 <= 1] = 1
        face, chin, cx, fw = (110, 70, 900, 1170), 1140, 545, 520
    else:
        cov[int(0.30 * H / G):, int(0.35 * W / G):int(0.65 * W / G)] = 1
        mask[int(0.30 * H / G):int(0.42 * H / G), int(0.43 * W / G):int(0.57 * W / G)] = 1
        face, chin, cx, fw = (440, 560, 640, 800), 790, 540, 150
    return sp.Scene(W, H, cov, face, chin, cx, fw, face_mask=mask)


def test_perspective_near_is_bigger_than_far():
    assert o.scale_at(1, 1) > 1 > o.scale_at(-1, 1)


@pytest.mark.parametrize("kind", ["close", "wide"])
def test_near_cards_never_touch_the_face_and_ring_stays_safe(kind):
    sc = scene(kind)
    geo = o.ring_geometry(sc, o.PARAMS["tilt"])
    F = o.frames(geo, 7, 105, 30, o.PARAMS["speed"])
    assert len(F) == 105 and all(len(r) == 7 for r in F)
    for row in F[30:-14]:  # settled ring (after the spring-out, before the fly-out)
        for x, y, s, ry, op, bl, z in row:
            hw, hh = geo["w"] * s / 2, geo["h"] * s / 2
            assert x - hw >= sp.SAFE["x0"] * W - 2 and x + hw <= sp.SAFE["x1"] * W + 2
            assert y + hh <= sp.SAFE["y1"] * H + 2 and y - hh >= sp.SAFE["y0"] * H - 2
            if z > 0.08 and op > 0.05:
                assert sc.face_hit(x - hw, y - hh, x + hw, y + hh) == 0.0


def test_wide_shots_get_bigger_cards_than_close_ups():
    assert o.ring_geometry(scene("wide"), 34)["h"] > o.ring_geometry(scene("close"), 34)["h"]


def test_far_cards_are_higher_smaller_softer():
    geo = o.ring_geometry(scene("wide"), 34)
    row = o.frames(geo, 8, 60, 30, 0.0)[-20]  # speed 0: card 0 at the front, card 4 at the back
    front, back = row[0], row[4]
    assert front[6] > 0.9 and back[6] < -0.9
    assert back[1] < front[1] and back[2] < front[2] and back[5] > front[5] == 0


def test_cards_move_continuously():
    geo = o.ring_geometry(scene("wide"), 34)
    F = o.frames(geo, 6, 90, 30, 0.15)
    for a, b in zip(F[30:-15], F[31:-14]):
        for ca, cb in zip(a, b):
            assert math.hypot(ca[0] - cb[0], ca[1] - cb[1]) < 0.03 * W


def test_entrance_and_exit_fade():
    geo = o.ring_geometry(scene("wide"), 34)
    F = o.frames(geo, 6, 90, 30, 0.15)
    assert all(c[4] == 0 for c in F[0]) and all(c[4] < 0.05 for c in F[-1])


@pytest.mark.slow
def test_orbit_renders_exact_frames(talking_clip, tmp_path):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    from editor.style import load_style
    out = apply_fx(talking_clip, [{"type": "orbit", "at": 1.0, "dur": 2.0, "items": ["One", "Two", "Three"]}],
                   tmp_path / "w", load_style("default"), out=tmp_path / "o.mp4")
    assert abs(ffmpeg.probe(out)["duration"] - 10.0) < 0.1


def test_track_halves_meet_at_the_sides():
    geo = o.ring_geometry(scene("wide"), 34)
    f, b = o.track_points(geo, "front"), o.track_points(geo, "back")
    assert abs(f[-1][0] - b[0][0]) < 1 and abs(f[0][0] - b[-1][0]) < 1
    assert max(y for _, y in f) > max(y for _, y in b)  # the near half hangs lower (the ring leans to camera)


def test_card_frame_and_background():
    from editor.fx.orbit import _frame_css
    css = _frame_css({"color": "#4c6ef5", "width": 0.05, "inner": "#FFFFFF"}, "#f0f0f0", {"w": 200}, 1)
    assert "inset 0 0 0 10.0px #4c6ef5" in css and "#FFFFFF" in css and ".cd.tp img{object-fit:contain" in css
    assert _frame_css(None, None, {"w": 200}, 1) == ""
