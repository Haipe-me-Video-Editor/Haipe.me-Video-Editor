import pytest

from editor.fx import _glass as G
from editor.fx import chart_grow as C
from editor.fx import registry


def test_registered_with_params():
    assert registry()["chart_grow"] is C
    assert {"values", "labels", "kind", "unit", "tag", "place"} <= set(C.PARAMS)


@pytest.mark.parametrize("values,labels,kind", [
    (None, [], "line"), ([], [], "line"), ([5], [], "line"),            # no data: never invented
    ([1, "x"], [], "line"), ([1, float("nan")], [], "line"),
    ([1, 2], ["a"], "line"),                                           # labels must match
    ([1, 2], [], "pie"), (list(range(13)), [], "line"),
])
def test_validate_rejects_bad_data(values, labels, kind):
    with pytest.raises(ValueError):
        C.validate(values, labels, kind)


def test_validate_accepts_numbers_and_numeric_strings():
    assert C.validate([5, "4"], ["Male", "Pets"], "bars") == [5.0, 4.0]


def test_points_map_values_into_the_box():
    box = (100, 200, 900, 600)
    pts = C.points([0, 5, 10], box, "line", head=0.2)
    xs, ys = zip(*pts)
    assert xs[0] == 100 and xs[-1] == 900
    assert ys[0] > ys[1] > ys[2]                                     # higher value, higher on screen
    assert ys[2] == pytest.approx(200 + 400 * 0.2)                    # the max leaves headroom
    bars = C.points([5, 4], box, "bars")
    assert bars[0][0] == pytest.approx(300) and bars[1][0] == pytest.approx(700)  # centred in their slots
    assert bars[0][1] < bars[1][1] < 600                              # bars from a zero floor


def test_value_range():
    assert C.value_range([5, 4], "bars")[0] == 0                      # bars always from zero
    lo, hi = C.value_range([3, 8], "line")
    assert 2 < lo < 3 and hi == 8                                     # a line hugs its data
    assert C.value_range([3, 8], "line", y_min=0)[0] == 0


def test_decimals():
    assert C.decimals([1, 2, 3]) == 0 and C.decimals([1, 2.5]) == 1 and C.decimals([1.25]) == 2


def test_tip_timing_inverts_the_ease():
    import math
    for y in (0, 0.2, 0.5, 0.9, 1):
        p = C.inv_sine_inout(y)
        assert -(math.cos(math.pi * p) - 1) / 2 == pytest.approx(y)


def test_wall_box_only_when_the_wall_is_visible():
    W, H = 1080, 1920
    close = G.head_from(198, 790, 582, 345, 455, 1094, 557)
    wide = G.head_from(450, 630, 1050, 960, 1010, 1180, 180)
    assert C.wall_box(W, H, close) is None                            # a close-up: card instead
    _, y0, x1, y1 = C.wall_box(W, H, wide)
    assert y0 >= G.SAFE_TOP * H and y1 <= wide["skull"] and x1 <= (1 - G.SAFE_RIGHT) * W


def test_card_height():
    assert C.card_h("line", True) > C.card_h("bars", True)


def test_bar_path_stands_on_the_baseline():
    d = C.bar_path(100, 200, 60, 400)
    assert d.startswith("M70.0,400.0") and d.endswith("L130.0,400.0 Z")   # flat foot on the baseline
    assert "Q" in C.bar_path(100, 398, 60, 400)                         # tiny bars stay valid
