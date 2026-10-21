import pytest

from editor import ffmpeg


def test_probe_reports_shape_and_audio(talking_clip):
    info = ffmpeg.probe(talking_clip)
    assert info["width"] == 1080 and info["height"] == 1920
    assert info["fps"] == pytest.approx(30, abs=0.01)
    assert info["duration"] == pytest.approx(10, abs=0.1)
    assert info["has_audio"] is True


def test_read_pcm_gives_mono_samples(talking_clip):
    pcm = ffmpeg.read_pcm(talking_clip)
    assert pcm.ndim == 1 and abs(len(pcm) / 16000 - 10) < 0.1


def test_run_raises_with_log_on_failure(tmp_path):
    with pytest.raises(ffmpeg.FFmpegError) as err:
        ffmpeg.run(["-i", tmp_path / "missing.mp4", tmp_path / "x.mp4"])
    assert "missing.mp4" in str(err.value)
