from editor import quality


def test_normal_renders_keep_their_speed_settings(monkeypatch):
    monkeypatch.delenv("EDITOR_MASTER", raising=False)
    assert quality.final() == ["-preset", "medium", "-crf", "20"]
    assert quality.final(draft=True) == ["-preset", "veryfast", "-crf", "23"]
    assert quality.inter("veryfast", 10) == ["-preset", "veryfast", "-crf", "10"]
    assert quality.audio_kbps() == "192k"


def test_a_master_render_is_near_lossless_at_every_step(monkeypatch):
    monkeypatch.setenv("EDITOR_MASTER", "1")
    assert quality.final(draft=True)[3] == "10" and "slow" in quality.final()
    assert quality.inter("veryfast", 14) == ["-preset", "medium", "-crf", "6"]
    assert quality.audio_kbps() == "320k"
