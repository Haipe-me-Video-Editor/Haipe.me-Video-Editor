"""ui_world: layout, grouping and timing (pure), plus a slow render on a synthetic clip."""
import numpy as np
import pytest

from editor.fx import _spatial as sp
from editor.fx import ui_world as u

W, H, G = 1080, 1920, sp.GRID


def scene(kind="close"):
    """A fake speaker: 'close' = head fills the top half (a typical close-up framing), 'wide' = small figure."""
    cov = np.zeros((H // G, W // G), np.float32)
    if kind == "close":
        cov[int(0.12 * H / G):int(0.55 * H / G), int(0.22 * W / G):int(0.74 * W / G)] = 1
        cov[int(0.52 * H / G):, :] = 1
        face, chin, cx, fw = (110, 70, 900, 1170), 1130, 545, 520
    else:
        cov[int(0.30 * H / G):int(0.42 * H / G), int(0.42 * W / G):int(0.58 * W / G)] = 1
        cov[int(0.42 * H / G):, int(0.30 * W / G):int(0.70 * W / G)] = 1
        face, chin, cx, fw = (440, 560, 640, 800), 790, 540, 150
    return sp.Scene(W, H, cov, face, chin, cx, fw)


def test_panels_group_into_command_box_and_cards():
    g = u.split_panels(u.PARAMS["panels"] + [{"kind": "card", "title": "Second"}])
    assert g["input"] and g["thumbs"] and g["button"] is not None and len(g["cards"]) == 2
    assert u.split_panels([])["cards"] == []


@pytest.mark.parametrize("kind", ["close", "wide"])
def test_layout_keeps_box_off_face_and_inside_safe_zone(kind):
    sc = scene(kind)
    lay = u.layout(sc, u.split_panels(u.PARAMS["panels"]), 0.745, 1.0)
    x0, y0, x1, y1 = lay["box"]
    assert lay["box_plane"] == "front"
    assert y0 >= sc.chin  # under the chin: the face stays clear
    assert x0 >= sp.SAFE["x0"] * W - 1 and x1 <= sp.SAFE["x1"] * W + 1 and y1 <= sp.SAFE["y1"] * H
    assert lay["word_y"] + 84 <= sp.SAFE["y1"] * H + 1
    for c in lay["cards"]:
        r = c["rect"]
        assert r[1] >= sp.SAFE["y0"] * H - 1 and r[2] <= sp.SAFE["x1"] * W + 1
        assert c["vis"] >= 0.66


def test_cards_go_where_the_wall_shows():
    sc = scene("close")
    lay = u.layout(sc, u.split_panels([{"kind": "card", "title": "Drop files here"},
                                       {"kind": "card", "title": "Launch day"}]), 0.745, 1.0)
    assert lay["box"] is None and 1 <= len(lay["cards"]) <= 2
    for c in lay["cards"]:
        assert 1 - sc.rect_cover(*c["rect"]) >= 0.66
        assert c["align"] in ("left", "right")


def test_timing_beats_are_ordered_and_fit_short_windows():
    for dur in (2.5, 3.5, 6.0):
        t = u.timing(dur, 30, 4)
        assert 0 < t["t_drop"] < t["t_type"] < t["t_typed"] <= t["t_press"] < t["exit"] < dur
        assert t["exit"] - t["t_press"] >= 0.44


def test_icons_guess_from_text():
    assert u.guess_icon({"title": "Drop files here"}) == "upload"
    assert u.guess_icon({"title": "Users"}) == "user"
    assert u.guess_icon({"title": "x", "icon": "chart"}) == "chart"


def test_theme_tokens_for_any_palette():
    for style in ({"accent": "#a3e635", "bg": "#111111", "ink": "#f0f0f0"}, {"accent": "#e4572e", "bg": "#222222"},
                  {"accent": "#4c6ef5", "bg": "#1a1a1a", "ink": "#FFFFFF"}, {}):
        th = sp.theme(style)
        assert th["accent"].startswith("#") and th["surface"].startswith("rgba(")
    assert sp.theme({"accent": "#a3e635"})["on_accent"] == "#101114"  # dark ink on a bright lime
    assert sp.theme({"accent": "#4c6ef5"})["on_accent"] == "#ffffff"


def test_fill_matte_closes_holes_in_the_body():
    a = np.zeros((200, 100), np.float32)
    a[60:, 20:80] = 1
    a[120:140, 40:60] = 0  # a hole (a hand gap in the shirt)
    a[150:, 45:55] = 0     # a gap open at the bottom edge only
    m = sp.fill_matte(a)
    assert m[130, 50] > 0.9 and m[190, 50] > 0.9 and m[10, 50] < 0.05 and m[100, 5] < 0.05


@pytest.mark.slow
def test_ui_world_renders_exact_frames(talking_clip, tmp_path):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    from editor.style import load_style
    out = apply_fx(talking_clip, [{"type": "ui_world", "at": 1.0, "dur": 2.5}], tmp_path / "w",
                   load_style("default"), out=tmp_path / "o.mp4")
    assert abs(ffmpeg.probe(out)["duration"] - 10.0) < 0.1
