import os
from pathlib import Path

import numpy as np
import pytest

from editor.fx import _cutkit as K
from editor.fx import doodle_boil as D
from editor.fx import registry

W, H = 270, 480


def _matte(cx=135, top=120, r=70):
    """A head-and-shoulders blob that runs off the bottom of the frame."""
    yy, xx = np.mgrid[0:H, 0:W]
    head = ((xx - cx) ** 2 + (yy - top - r) ** 2) < r ** 2
    body = (yy > top + 1.6 * r) & (np.abs(xx - cx) < 1.2 * r + (yy - top - 1.6 * r) * 0.5)
    return (head | body).astype(np.float32)


def test_registered_with_params_and_duration():
    mod = registry()["doodle_boil"]
    assert mod is D and D.DUR[0] >= 1 and {"text", "doodles", "boil", "offset"} <= set(D.PARAMS)


def test_outline_hugs_the_matte_at_the_offset_and_skips_the_frame_edge():
    A = _matte()
    runs = D.outline_runs(A, 8, W, H, (135, 190), 1.0)
    assert runs
    pts = np.vstack(runs)
    assert pts[:, 1].max() < H - 5  # never drawn along the bottom edge where the body is cut
    import cv2
    dist = cv2.distanceTransform((A < 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    d = dist[np.clip(pts[:, 1].astype(int), 0, H - 1), np.clip(pts[:, 0].astype(int), 0, W - 1)]
    assert 4 < np.median(d) < 13  # roughly `offset` px outside the body


def test_sweep_reveals_from_the_top_down():
    A = _matte()
    half = np.vstack(D.outline_runs(A, 8, W, H, (135, 190), 0.4))
    full = np.vstack(D.outline_runs(A, 8, W, H, (135, 190), 1.0))
    assert len(half) < len(full) and half[:, 1].mean() < full[:, 1].mean()


def test_interior_gaps_are_not_outlined():
    A = _matte()
    gap = A.copy()
    gap[400:470, 120:150] = 0  # the matte opened a hole up from the bottom edge (arm and chest apart)
    interior = D.body_interior(A, 8 * A.shape[1] / W)
    with_gap = np.vstack(D.outline_runs(gap, 8, W, H, (135, 190), 1.0, interior))
    assert not ((with_gap[:, 1] > 405) & (np.abs(with_gap[:, 0] - 135) < 10)).any()


def test_split_joins_a_run_that_wraps_around():
    P = np.array([[i, 0] for i in range(10)], np.float32)
    keep = np.array([1, 1, 0, 0, 1, 1, 1, 1, 1, 1], bool)
    runs = D._split(P, keep)
    assert len(runs) == 1 and len(runs[0]) == 8 and runs[0][0][0] == 4


def test_layout_keeps_doodles_off_the_face_and_in_the_safe_zone():
    occ = _matte()  # quarter-size map of a 1080x1920 frame
    face = (100 * 4, 125 * 4, 170 * 4, 230 * 4)
    p = dict(D.PARAMS, text="5 BETA\\NTESTERS")
    plan = D.layout(p, occ, face, 1080, 1920)
    kinds = [it[0] for it in plan["items"]]
    assert "word" in kinds and "underline" in kinds
    for kind, strokes, *_ in plan["items"]:
        lo, hi = K.bounds(strokes)
        if kind == "arrow":
            continue
        assert lo[1] >= 0.12 * 1920 and hi[1] <= 0.82 * 1920 and hi[0] <= 0.9 * 1080
        overlap_x = min(hi[0], face[2]) - max(lo[0], face[0])
        overlap_y = min(hi[1], face[3]) - max(lo[1], face[1])
        assert overlap_x <= 0 or overlap_y <= 0, kind


def test_every_glyph_draws_and_text_is_centred():
    for ch, (adv, strokes) in K.GLYPHS.items():
        g = K.glyph_strokes(ch, 100)
        assert g is not None and (ch == " " or g[1])
    strokes, (w, h) = K.text_strokes("AB\\NC", 50)
    lo, hi = K.bounds(strokes)
    assert w > 0 and h > 50 and lo[0] > -10 and hi[0] < w + 10


def test_reveal_is_monotonic_in_length():
    s = [np.array([[0, 0], [100, 0]], np.float32), np.array([[0, 10], [0, 110]], np.float32)]
    lens = [sum(K.length(x) for x in K.reveal(s, p)) for p in (0, .25, .5, .75, 1)]
    assert lens == sorted(lens) and abs(lens[2] - 100) < 1 and abs(lens[-1] - 200) < 1


def test_wobble_is_deterministic_per_step_and_changes_between_steps():
    s = [np.linspace([0, 0], [300, 0], 40).astype(np.float32)]
    a, b, c = K.wobble(s, 3, 1), K.wobble(s, 3, 1), K.wobble(s, 3, 2)
    assert np.allclose(a[0], b[0]) and not np.allclose(a[0], c[0])
    assert np.abs(a[0] - s[0]).max() < 6  # a boil, not a scramble


SRC = Path(os.environ.get("FX_TEST_CLIP", "/nonexistent"))


@pytest.mark.slow
@pytest.mark.skipif(not SRC.exists(), reason="set FX_TEST_CLIP to a 9:16 talking-head clip")
def test_renders_exact_frames(tmp_path):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    out = apply_fx(SRC, [{"type": "doodle_boil", "at": 1.0, "dur": 1.5, "text": "HI"}], tmp_path, {"name": "t"})
    assert abs(ffmpeg.probe(out)["duration"] - ffmpeg.probe(SRC)["duration"]) < 0.1
