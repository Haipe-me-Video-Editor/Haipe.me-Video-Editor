"""headline_wall: item parsing, wall placement, text fitting, lighting (pure), plus a slow render."""
import numpy as np
import pytest

from editor.fx import _spatial as sp
from editor.fx import headline_wall as hw

W, H, G = 1080, 1920, sp.GRID


def scene(kind):
    cov = np.zeros((H // G, W // G), np.float32)
    if kind == "close":
        cov[int(0.12 * H / G):int(0.55 * H / G), int(0.22 * W / G):int(0.74 * W / G)] = 1
        cov[int(0.52 * H / G):, :] = 1
        face, chin, cx, fw = (110, 70, 900, 1170), 1130, 545, 520
    else:
        cov[int(0.30 * H / G):, int(0.38 * W / G):int(0.62 * W / G)] = 1
        face, chin, cx, fw = (440, 560, 640, 800), 790, 540, 150
    return sp.Scene(W, H, cov, face, chin, cx, fw)


def test_items_normalise_kinds_and_only_given_sources():
    items = hw.normalise(["A", {"text": "B", "kind": "sticky"}, {"text": " "}, {"text": "C", "kind": "bogus"}])
    assert [i["text"] for i in items] == ["A", "B", "C"]
    assert items[1]["kind"] == "sticky" and all(i["kind"] in hw.KINDS for i in items)
    assert not any(i.get("source") for i in items)  # no invented outlets
    assert hw.normalise(["A"], source="example.app")[0]["source"] == "example.app"


@pytest.mark.parametrize("kind", ["close", "wide"])
def test_notes_land_on_clear_wall_with_their_text_visible(kind):
    sc = scene(kind)
    items = hw.normalise(["Plan A ships this week", "New onboarding checklist", "Lorem ipsum dolor sit",
                          "Need 5 beta testers"])
    lay = hw.layout(sc, items)
    placed = [L for L in lay if L]
    assert len(placed) >= (3 if kind == "close" else 4)
    for L in placed:
        x0, y0, x1, y1 = L["rect"]
        assert x0 >= sp.SAFE["x0"] * W - 1 and x1 <= sp.SAFE["x1"] * W + 1 and y0 >= sp.SAFE["y0"] * H - 1
        assert L["text_w"] >= 0.5 * (x1 - x0) * 0.74
        side = (x1 - L["text_w"], y0, x1, y1) if L["side"] == "right" else (x0, y0, x0 + L["text_w"], y1)
        assert sc.rect_cover(*side) < 0.25


def test_fit_font_wraps_and_shrinks():
    s1, l1 = hw.fit_font("Need 5 beta testers", 400, 300, [60, 50, 40, 30])
    s2, l2 = hw.fit_font("Need 5 beta testers", 150, 300, [60, 50, 40, 30])
    assert s1 >= s2 and l2 >= l1 >= 1


def test_room_tint_is_gentle_and_follows_the_light():
    dark_blue = hw.tint_from([0.05, 0.08, 0.25], 0.3)
    warm = hw.tint_from([0.6, 0.5, 0.4], 0.3)
    assert all(0.7 <= g <= 1.0 for g in list(dark_blue) + list(warm))
    assert dark_blue[2] > dark_blue[0] and warm[0] > warm[2]
    assert np.allclose(hw.tint_from([0.2, 0.3, 0.4], 0.0), 1.0)


def test_sticky_paper_is_pale():
    assert sp.luminance(hw.sticky_color({"accent": "#a3e635"})) > 0.6
    assert sp.luminance(hw.sticky_color({"accent": "#4c6ef5"})) > 0.5


def test_needs_items():
    class Ctx:
        def param(self, k, d=None):
            return d
    with pytest.raises(ValueError):
        hw.render(Ctx())


@pytest.mark.slow
def test_headline_wall_renders_exact_frames(talking_clip, tmp_path):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    from editor.style import load_style
    out = apply_fx(talking_clip, [{"type": "headline_wall", "at": 1.0, "dur": 2.0, "items": ["One", "Two"]}],
                   tmp_path / "w", load_style("default"), out=tmp_path / "o.mp4")
    assert abs(ffmpeg.probe(out)["duration"] - 10.0) < 0.1
