"""App capture: screencast frames become a constant-rate clip; steps are checked before anything runs."""
import pytest

from editor import capture, ffmpeg


def test_screencast_frames_hold_until_the_next_one(tmp_path):
    frames = []
    for i, (t, colour) in enumerate(((0.0, "red"), (0.5, "blue"), (1.5, "green"))):
        f = tmp_path / f"f{i}.jpg"
        ffmpeg.run(["-f", "lavfi", "-i", f"color=c={colour}:s=390x693", "-frames:v", "1", f])
        frames.append((100.0 + t, f))
    out = tmp_path / "rec.mp4"
    capture._encode(frames, out, (1080, 1920))
    info = ffmpeg.probe(out)
    assert (info["width"], info["height"]) == (1080, 1920)
    assert info["duration"] == pytest.approx(2.0, abs=0.1)  # 0.5 + 1.0 + the last frame's 0.5 s hold


def test_unknown_step_is_refused():
    with pytest.raises(ValueError):
        capture._run_steps(None, [{"jump": 1}], None)


def test_the_cursor_eases_in_and_out():
    assert capture.ease(0) == 0 and capture.ease(1) == 1 and capture.ease(0.5) == 0.5
    assert capture.ease(0.1) < 0.1 and capture.ease(0.9) > 0.9  # slow start, slow stop


@pytest.mark.slow
def test_point_glides_a_cursor_and_zooms_on_the_words(tmp_path):
    page = tmp_path / "p.html"
    page.write_text('<body style="font:20px sans-serif;padding:40px"><p>Intro</p><a href="#">Editing playbook</a>'
                    '<div style="height:900px"></div></body>')
    out = tmp_path / "rec.mp4"
    capture.capture(page.as_uri(), out, [{"point": "text=Editing playbook", "dur": 0.5, "zoom": 2},
                                         {"wait": 0.3}, {"unzoom": 0.3}], wait=0.2)
    assert ffmpeg.probe(out)["duration"] > 1.0
    with pytest.raises(ValueError):
        capture.capture(page.as_uri(), tmp_path / "x.png", [{"point": "text=Nowhere at all", "dur": 0.1}], wait=0.1)
