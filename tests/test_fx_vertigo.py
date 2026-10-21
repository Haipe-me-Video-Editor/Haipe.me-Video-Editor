import numpy as np
import pytest

from editor.fx import registry
from editor.fx import vertigo as vt


def test_registered():
    assert registry()["vertigo"] is vt and {"amount", "direction", "ease"} <= set(vt.PARAMS)


@pytest.mark.parametrize("direction", ["in", "out"])
def test_bg_scale_starts_and_ends_at_one_and_never_below(direction):
    s = [vt.bg_scale(i / 30, 3.0, 0.3, direction) for i in range(91)]
    assert s[0] == pytest.approx(1.0) and s[-1] == pytest.approx(1.0, abs=1e-6)
    assert min(s) >= 1.0 - 1e-9 and max(s) == pytest.approx(1.3, abs=0.01)


def test_hold_keeps_the_peak():
    assert vt.bg_scale(3.0, 3.0, 0.25, "in", back=False) == pytest.approx(1.25)
    with pytest.raises(ValueError):
        vt.bg_scale(1, 3, 0.2, "sideways")


def test_plate_median_skips_the_person_and_fills_the_rest():
    stack = np.full((5, 20, 20, 3), 100, np.uint8)
    valid = np.ones((5, 20, 20), bool)
    stack[:, :, :8] = 250        # the person, always on the left...
    valid[:, :, :8] = False
    stack[2, :, 10:] = 0          # ...and one frame of something passing on the right
    plate, seen = vt.masked_median(stack, valid)
    assert seen[:, 8:].all() and not seen[:, :8].any()
    assert np.allclose(plate[:, 8:], 100)
    filled = vt.fill_holes(plate, seen)
    assert np.all(np.abs(filled[:, :8] - 100) < 20)  # inpainted from the room, not from the person
