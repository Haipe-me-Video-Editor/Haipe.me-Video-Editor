import pytest

from editor import analyze, sheets


def test_silences_match_fixture_gaps(talking_clip):
    found = analyze.silences(talking_clip, duration=10.0)
    expected = [[0.0, 0.5], [2.5, 3.5], [6.0, 7.2], [9.5, 10.0]]
    assert len(found) == len(expected)
    for (fs, fe), (es, ee) in zip(found, expected):
        assert fs == pytest.approx(es, abs=0.1) and fe == pytest.approx(ee, abs=0.1)


def test_loudness_reports_integrated_level(talking_clip):
    m = analyze.loudness(talking_clip)
    assert -40 < m["input_i"] < 0
    assert set(m) >= {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}


def test_no_black_frames_in_test_pattern(talking_clip):
    assert analyze.black_frames(talking_clip) == []


def test_contact_sheet_is_one_image(talking_clip, tmp_path):
    out = tmp_path / "sheet.jpg"
    times = sheets.contact_sheet(talking_clip, out)
    assert out.exists() and out.stat().st_size > 1000
    assert len(times) == 12 and times == sorted(times)


def test_black_frames_detects_initial_black(black_and_test_clip):
    """Test that black_frames detects the ~1.5s black period at start."""
    found = analyze.black_frames(black_and_test_clip)
    assert len(found) > 0
    # First black frame should be at approximately 0.0
    assert found[0] == pytest.approx(0.0, abs=0.1)


def test_scenes_detects_transition(black_and_test_clip):
    """Test that scenes detects the scene change at ~1.5s."""
    found = analyze.scenes(black_and_test_clip)
    assert len(found) > 0
    # Scene change should be detected around 1.5s
    assert found[0] == pytest.approx(1.5, abs=0.15)


def test_silences_with_exponent_notation(monkeypatch):
    """Test that silences regex accepts exponent notation (e.g., 4.2e-05)."""
    fake_log = "[silencedetect] silence_start: 4.2e-05\n[silencedetect] silence_end: 1.5 | silence_duration: 1.5\n"
    monkeypatch.setattr(analyze.ffmpeg, "run", lambda args: fake_log)
    result = analyze.silences("x", duration=2.0)
    # 4.2e-05 rounds to 0.0 at 3 decimals
    assert result == [[0.0, 1.5]]
