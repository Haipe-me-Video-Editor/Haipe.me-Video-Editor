"""Frozen-picture and per-graphic motion checks in review."""
import pytest

from editor import analyze, ffmpeg, review
from tests.test_review import _plan, _reviewed

LOG = """[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 0.0333
[freezedetect @ 0x1] lavfi.freezedetect.freeze_duration: 2.9
[freezedetect @ 0x1] lavfi.freezedetect.freeze_end: 2.9667
[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 7.5
"""


def test_parse_freezes_closes_a_freeze_that_runs_to_the_end():
    assert analyze.parse_freezes(LOG, 9.0) == [[0.033, 2.967], [7.5, 9.0]]
    assert analyze.parse_freezes(LOG.split("[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 7.5")[0],
                                 lambda: 1 / 0) == [[0.033, 2.967]]  # duration only looked up when needed


def test_judge_motion_flags_a_dead_hold_and_a_still_entrance():
    fps = review.MOTION_FPS
    moving = [2.0] * 30
    assert not review.judge_motion(moving)["dead_hold"] and not review.judge_motion(moving)["no_entrance"]
    held = [3.0] * 6 + [0.05] * 18  # moves for 1 s, then still for 3 s
    j = review.judge_motion(held)
    assert j["dead_hold"] and not j["no_entrance"]
    assert j["longest_static"] == 3.0 and j["static_at"] == [1.0, 4.0]
    still_start = [0.0] * round(review.ENTRANCE_WINDOW * fps) + [2.0] * 10
    assert review.judge_motion(still_start)["no_entrance"]
    short = [0.0] * round(review.STATIC_HOLD_MAX * fps)  # exactly the limit is still fine
    assert not review.judge_motion(short)["dead_hold"]


def test_motion_profile_is_mean_abs_difference():
    import numpy as np
    f = np.zeros((3, 4, 4), np.uint8)
    f[1] += 10
    assert review.motion_profile(f) == [10.0, 10.0]
    assert review.motion_profile(f[:1]) == []


def test_review_fails_on_frozen_picture(tmp_path, monkeypatch):
    checks = _reviewed(tmp_path, monkeypatch, _plan(out=8.0, enabled=False), freezes=[(3.0, 5.0)])
    assert not checks["no_frozen_frames"]["ok"]
    assert checks["no_frozen_frames"]["detail"] == "frozen 3.0–5.0s"
    assert "graphics_motion" not in checks  # no graphics in the plan


def test_review_reports_static_graphics(tmp_path, monkeypatch):
    plan = {**_plan(out=8.0, enabled=False), "graphics": [{"type": "stat", "at": 1.0, "dur": 5.0}]}
    monkeypatch.setattr(review, "graphic_motion", lambda final, p: [
        {"index": 0, "type": "stat", "at": 1.0, "dur": 5.0, "longest_static": 3.5, "static_at": [1.0, 4.5],
         "entrance_peak": 4.0, "dead_hold": True, "no_entrance": False}])
    checks = _reviewed(tmp_path, monkeypatch, plan)
    assert checks["no_frozen_frames"]["ok"]
    assert not checks["graphics_motion"]["ok"]
    assert checks["graphics_motion"]["detail"] == "graphics[0] stat at 1.0s: still for 3.5s from 2.0s"


@pytest.fixture(scope="module")
def still_then_moving(tmp_path_factory):
    """5 s: 3 s of flat colour, then 2 s of moving test pattern."""
    out = tmp_path_factory.mktemp("fz") / "still.mp4"
    ffmpeg.run(["-f", "lavfi", "-i", "color=c=0x334455:s=320x568:r=30:d=3",
                "-f", "lavfi", "-i", "testsrc2=size=320x568:rate=30:duration=2",
                "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", out])
    return out


def test_freezedetect_finds_the_still_head(still_then_moving):
    found = analyze.frozen_ranges(still_then_moving, review.FREEZE_NOISE, review.FREEZE_MIN)
    assert len(found) == 1
    a, b = found[0]
    assert a < 0.1 and 2.8 < b < 3.2


def test_graphic_motion_on_a_real_clip(still_then_moving):
    plan = {"graphics": [{"type": "hook", "at": 0.0, "dur": 3.0}, {"type": "stat", "at": 3.0, "dur": 2.0}]}
    still, moving = review.graphic_motion(still_then_moving, plan)
    assert still["dead_hold"] and still["no_entrance"] and still["longest_static"] > review.STATIC_HOLD_MAX
    assert not moving["dead_hold"] and not moving["no_entrance"]
