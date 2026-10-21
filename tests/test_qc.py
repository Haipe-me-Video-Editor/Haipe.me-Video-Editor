from editor import ffmpeg
from editor.qc import _moov_first, qc


def _clip(path, video="testsrc2=size=108x192:rate=30:duration=4", audio="sine=f=440:d=4:sample_rate=48000",
          af="volume=-20dB", extra=("-movflags", "+faststart")):
    ffmpeg.run(["-f", "lavfi", "-i", video, "-f", "lavfi", "-i", audio, "-af", af, "-c:v", "libx264", "-preset",
                "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", *extra, path])
    return path


def _by_name(r):
    return {c["name"]: c for c in r["checks"]}


def test_a_clean_master_passes_format_and_sync(tmp_path):
    c = _by_name(qc(_clip(tmp_path / "a.mp4"), size=(108, 192), min_kbps=None))
    assert all(c[k]["ok"] for k in ("size", "constant_fps", "codec", "audio", "fast_start", "av_in_sync",
                                    "no_black_frames", "no_frozen_frames"))
    assert not c["loudness"]["ok"]  # a quiet test tone is far from -14 LUFS


def test_catches_black_frames_wrong_size_missing_faststart_and_clipping(tmp_path):
    v = _clip(tmp_path / "b.mp4", video="color=black:size=108x192:rate=30:duration=4", af="volume=24dB", extra=())
    c = _by_name(qc(v, size=(1080, 1920), min_kbps=None))
    assert not c["size"]["ok"] and not c["no_black_frames"]["ok"] and not c["true_peak"]["ok"]
    assert not _moov_first(v) and not c["fast_start"]["ok"]


def test_duration_must_match_the_source_unless_cut(tmp_path):
    src = _clip(tmp_path / "src.mp4")
    short = _clip(tmp_path / "short.mp4", video="testsrc2=size=108x192:rate=30:duration=3",
                  audio="sine=f=440:d=3:sample_rate=48000")
    assert not _by_name(qc(short, source=src, size=(108, 192), min_kbps=None))["duration_matches_source"]["ok"]
    assert "duration_matches_source" not in _by_name(qc(short, source=src, size=(108, 192), min_kbps=None, cut=True))
