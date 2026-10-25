"""Nothing the editor adds may sit under TikTok's UI: every module reads one safe zone, and placement keeps cards
inside it even when the user asks for a bigger card."""
import pytest

from editor import layout, safezone
from editor.fx import _behind as B
from editor.fx import _glass as G
from editor.fx import _spatial
from editor.fx import doodle_boil

W, H = 1080, 1920


def test_zone_clears_tiktoks_ui():
    # TikTok, 1080x1920: caption/username/sound block ~25% at the bottom, button column ~13% on the right
    assert safezone.Y1 <= 0.75 and safezone.X1 <= 0.87 and safezone.Y0 >= 0.10


@pytest.mark.parametrize("x0,y0,x1,y1", [
    (layout.SAFE_LEFT, layout.SAFE_TOP, 1 - layout.SAFE_RIGHT, layout.SAFE_BOTTOM),
    (_spatial.SAFE["x0"], _spatial.SAFE["y0"], _spatial.SAFE["x1"], _spatial.SAFE["y1"]),
    B.SAFE,
    (G.SAFE_LEFT, G.SAFE_TOP, 1 - G.SAFE_RIGHT, 1 - G.SAFE_BOTTOM),
    doodle_boil.SAFE,
])
def test_every_module_stays_inside_the_zone(x0, y0, x1, y1):
    assert x0 >= safezone.X0 - 1e-9 and y0 >= safezone.Y0 - 1e-9
    assert x1 <= safezone.X1 + 1e-9 and y1 <= safezone.Y1 + 1e-9


def test_a_bigger_card_is_capped_and_kept_inside():
    spot = {"region": "below", "scale": 0.8, "x": 300.0, "y": 1100.0, "w": 640.0, "h": 280.0}
    out = G.rescale(spot, W, H, 800, 350, 1.45)  # 1160 px wide at 1.45: wider than the safe width
    assert safezone.inside((out["x"], out["y"], out["x"] + out["w"], out["y"] + out["h"]), W, H)
    assert out["scale"] < 1.45
    out = G.rescale(spot, W, H, 400, 300, 1.4)  # fits at 1.4, but grown in place it would cross the caption block
    assert out["scale"] == pytest.approx(1.4)
    assert out["y"] + out["h"] <= safezone.Y1 * H + 1e-6
