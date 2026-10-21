import itertools

import pytest

from editor.fx import _glass as G
from editor.fx import checklist as C
from editor.fx import registry


def test_registered_with_params():
    mod = registry()["checklist"]
    assert mod is C and {"items", "title", "ticks", "reveal", "place", "scale"} <= set(C.PARAMS)


def test_default_ticks_spread_inside_the_window():
    t = C.tick_times(4, 3.5)
    assert len(t) == 4 and t == sorted(t)
    assert t[0] > 0.6 and t[-1] <= 3.5 - 0.9
    gaps = [b - a for a, b in itertools.pairwise(t)]
    assert max(gaps) - min(gaps) < 1e-6


def test_explicit_ticks_validated():
    assert C.tick_times(3, 4, [1, 2]) == [1.0, 2.0]          # fewer ticks than items: "2 of 3"
    with pytest.raises(ValueError):
        C.tick_times(2, 4, [1, 2, 3])                        # more ticks than items
    with pytest.raises(ValueError):
        C.tick_times(3, 4, [2, 1])                           # out of order
    with pytest.raises(ValueError):
        C.tick_times(3, 4, [1, 3.9])                         # after the exit starts


def test_progressive_reveal_follows_ticks():
    ticks = [1.0, 1.6, 2.2]
    r = C.reveal_times(4, ticks, "progressive")
    assert r[0] < ticks[0] and r[1] > ticks[0] and r[2] > ticks[1] and r[3] > ticks[2]
    r = C.reveal_times(4, ticks[:1], "progressive")
    assert r[2] is None and r[3] is None                     # never ticked into view: stay placeholders
    assert all(x is not None for x in C.reveal_times(4, ticks, "all"))


def test_card_size_grows_with_content_and_caps_at_safe_width():
    w1, h1 = C.card_size(["Short"], "To do")
    w2, h2 = C.card_size(["A much much longer line of text for the card"] * 4, "To do")
    assert w2 > w1 and h2 > h1 and w2 <= C.W0


def test_placement_close_up_goes_under_the_chin_and_clear_of_the_face():
    W, H = 1080, 1920
    hd = G.head_from(198, 790, 582, 345, 455, 1094, 557)     # a close-up
    spot = G.place(W, H, hd, 860, 450)
    assert spot["region"] == "below"
    assert spot["y"] >= hd["chin"] and spot["y"] + spot["h"] <= (1 - G.SAFE_BOTTOM) * H + 0.5
    assert spot["x"] + spot["w"] <= (1 - G.SAFE_RIGHT) * W + 0.5


def test_placement_wide_shot_goes_above_the_head():
    W, H = 1080, 1920
    hd = G.head_from(450, 630, 1050, 960, 1010, 1180, 180)  # small head low in the frame
    spot = G.place(W, H, hd, 860, 450)
    assert spot["region"] == "above" and spot["scale"] == 1.0
    assert spot["y"] >= G.SAFE_TOP * H and spot["y"] + spot["h"] <= hd["skull"]


def test_glass_composite_frosts_only_under_the_card():
    import numpy as np
    src = np.zeros((64, 64, 3), np.uint8)
    src[:, ::2] = 255                                         # stripes: blur turns them grey
    layer = np.zeros((64, 64, 4), np.uint8)
    layer[16:48, 16:48, 3] = int(255 * G.GLASS_A)             # a bare card (black tint at the glass alpha)
    out = G.glass_composite(src, layer, blur=8)
    assert (out[:8, :8] == src[:8, :8]).all()                 # outside: untouched
    inside = out[24:40, 24:40].astype(int)
    assert inside.std() < 20                                  # inside: frosted (stripes gone)


def test_data_look_palettes():
    market = G.brand({"data_look": "market", "accent": "#a3e635", "up": "#2a9d8f", "down": "#d62828"})
    assert market["kind"] == "market" and market["line"] == "#2a9d8f"
    assert market["hi"] == "#a3e635" and market["up"] == "#2a9d8f" and market["down"] == "#d62828"
    assert G.brand({"data_look": "accent", "accent": "#00a676"})["line"] == "#00a676"
    card = G.brand({"data_look": "card", "accent": "#4c6ef5", "card_bg": "#222222"})
    assert card["hi"] == "#4c6ef5" and card["tint"] == "#222222"
    assert G.brand({"name": "anything", "accent": "#00a676"})["kind"] == "generic"
    assert G.on_colour("#a3e635") != G.on_colour("#222222")


def test_arabic_detection():
    assert G.rtl(["اليوم نطلق", "الخطة الجديدة", "Plan"]) and not G.rtl(["Launch", "Results", "الخطة"])
