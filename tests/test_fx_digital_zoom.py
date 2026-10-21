import itertools
import subprocess

import numpy as np
import pytest

from editor import ffmpeg
from editor.fx import _camera as cam
from editor.fx import apply as fxapply
from editor.fx import digital_zoom as dz
from editor.fx import registry


def test_registered_with_params():
    assert registry()["digital_zoom"] is dz
    assert {"amount", "mode", "target", "hit", "shake", "release"} <= set(dz.PARAMS)


def test_snap_curve_hits_amount_then_releases():
    c = [dz.zoom_curve(i / 30, 2.0, 1.3, "snap", hit=0.2) for i in range(61)]
    assert c[0] == 1.0 and c[5] == 1.0  # before the hit
    assert max(c) >= 1.3 and max(c) < 1.3 + 0.3 * 0.1  # spring overshoot stays small
    assert abs(c[30] - 1.3) < 0.01  # held
    assert abs(c[60] - 1.0) < 1e-6  # released by the end
    assert min(c) >= 1.0  # never shows past the frame edge


def test_hold_and_push():
    assert abs(dz.zoom_curve(2.0, 2.0, 1.4, "snap", release=False) - 1.4) < 1e-3
    p = [dz.zoom_curve(i / 30, 3.0, 1.2, "push", release=False) for i in range(91)]
    assert all(b >= a - 1e-9 for a, b in itertools.pairwise(p)) and abs(p[-1] - 1.2) < 1e-6
    with pytest.raises(ValueError):
        dz.zoom_curve(0.5, 2, 1.3, "wobble")


def test_camera_helpers():
    M = cam.zoom_matrix((300, 400), 2.0, (540, 960))
    assert np.allclose(M @ [300, 400, 1], [540, 960])
    for c, s in [((10, 10), 1.3), ((1000, 1800), 1.1), ((540, 600), 3)]:
        dx, dy = cam.cover_dst(c, s, (0, 0), (1080, 1920))
        M = cam.zoom_matrix(c, s, (dx, dy))
        corners = M @ np.array([[0, 0, 1], [1080, 1920, 1]]).T
        assert corners[0, 0] <= 1e-6 and corners[1, 0] <= 1e-6  # top-left still covered
        assert corners[0, 1] >= 1080 - 1e-6 and corners[1, 1] >= 1920 - 1e-6
    assert cam.blur_samples(1.0, 1.0, 1000) == [1.0]
    assert 1 < len(cam.blur_samples(1.0, 1.5, 1000)) <= 24
    assert cam.ease("inout", 0) == 0 and cam.ease("inout", 1) == 1 and cam.ease("expo", 1) == 1
    assert cam.shake(-0.1, 20) == (0, 0, 0) and cam.shake(1.0, 20) == (0, 0, 0)
    assert cam.resolve_target([0.5, 0.25], [], [], (1080, 1920)) == (540, 480)


@pytest.mark.slow
def test_renders_exact_window(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=216x384:r=30:d=3", "-pix_fmt",
                    "yuv420p", str(src)], check=True)
    out = fxapply.apply_fx(src, [{"type": "digital_zoom", "at": 1.0, "dur": 1.0, "target": "center", "shake": 0.5}],
                           tmp_path / "w", {"name": "t"}, size=(216, 384), fps=30)
    assert abs(ffmpeg.probe(out)["duration"] - 3.0) < 0.05
