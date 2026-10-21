import numpy as np

from editor import beauty


def test_slim_narrows_the_middle_and_keeps_vertical_lines_straight():
    img = np.zeros((200, 400, 3), np.uint8)
    img[:, 150] = 255           # a vertical line inside the slimmed band
    img[:, 5] = 255             # one near the edge, outside it
    out = beauty.slim(img, cx=200, k=0.05)
    cols = [np.flatnonzero(out[y, :, 0] > 128) for y in (0, 100, 199)]
    assert all(np.array_equal(c, cols[0]) for c in cols)          # straight: the same columns on every row
    inner = cols[0][(cols[0] > 100) & (cols[0] < 300)]
    assert inner.size and abs(inner.mean() - 200) < 50 - 1        # pulled toward the centre (was 50 px away)
    assert 5 in cols[0]                                           # the edge is untouched


def test_makeup_leaves_the_frame_alone_without_a_face():
    img = np.full((50, 50, 3), 120, np.uint8)
    assert beauty.makeup(img, None) is img
