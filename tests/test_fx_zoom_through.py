import itertools

import numpy as np
import pytest

from editor.fx import registry
from editor.fx import zoom_through as zt


def _clip(cut=None, n=40):
    rng = np.random.default_rng(0)
    a = rng.integers(60, 120, (36, 64)).astype(np.float32)
    b = rng.integers(140, 220, (36, 64)).astype(np.float32)
    frames = []
    for i in range(n):
        base = b if cut is not None and i >= cut else a
        frames.append(np.clip(base + rng.normal(0, 3, base.shape), 0, 255))  # motion-ish noise
    return np.stack(frames).astype(np.uint8)


def test_registered():
    assert registry()["zoom_through"] is zt and "cut" in zt.PARAMS


def test_find_cut():
    assert zt.find_cut(_clip(cut=23)) == 23
    assert zt.find_cut(_clip(cut=None)) is None


def test_rush_and_settle_curves():
    tc = 1.0
    r = [zt.rush_scale(i / 30, tc, 0.45, 7.0) for i in range(31)]
    assert r[0] == 1.0 and all(b >= a for a, b in itertools.pairwise(r)) and r[-1] == pytest.approx(7.0)
    s = [zt.settle_scale(tc + i / 30, tc, 0.5, 1.45) for i in range(20)]
    assert s[0] == pytest.approx(1.45) and s[-1] == 1.0 and all(b <= a for a, b in itertools.pairwise(s))
    assert zt.settle_scale(tc - 0.02, tc, 0.5, 1.45) > 1.45  # B's first frame carries the punch's blur
    assert zt.flash_at(tc - 1 / 60, tc, 30, 0.2) == pytest.approx(0.2) and zt.flash_at(tc + 0.5, tc, 30, 0.2) == 0
