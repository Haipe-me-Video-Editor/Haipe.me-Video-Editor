import pytest

from editor import ffmpeg, music, score


@pytest.mark.slow
def test_score_has_requested_length(tmp_path):
    p = score.write_score(tmp_path / "s.wav", 8.0)
    assert ffmpeg.probe(p)["duration"] == pytest.approx(8.0, abs=0.05)


@pytest.mark.slow
def test_tempo_of_generated_score_is_found(tmp_path):
    p = score.write_score(tmp_path / "s.wav", 20.0, bpm=96)
    tempo = music.analyze_track(p)["tempo"]
    assert min(abs(tempo - 96 * k) for k in (0.5, 1, 2)) < 6


def test_sfx_kinds(tmp_path):
    for kind in ("whoosh", "pop"):
        assert ffmpeg.probe(score.write_sfx(tmp_path / f"{kind}.wav", kind))["duration"] > 0.05


def test_index_reuses_unchanged_tracks(tmp_path, monkeypatch):
    lib = tmp_path / "music"
    lib.mkdir()
    score.write_score(lib / "calm piano.wav", 6.0)
    calls = []
    monkeypatch.setattr(music, "analyze_track", lambda p: calls.append(p) or
                        {"duration": 6.0, "tempo": 96.0, "beats": [], "energy": 0.05})
    first = music.build_index(lib, tmp_path / "index.json")
    second = music.build_index(lib, tmp_path / "index.json")
    assert len(calls) == 1 and first == second
    assert first[0]["tags"] == ["calm", "piano"]


def test_choose_prefers_long_enough_matching_energy():
    idx = [{"file": "a.wav", "duration": 20, "energy": 0.02, "tempo": 80},
           {"file": "b.wav", "duration": 90, "energy": 0.15, "tempo": 120},
           {"file": "c.wav", "duration": 90, "energy": 0.03, "tempo": 90}]
    assert music.choose(idx, 60, energy="low")["file"] == "c.wav"
    assert music.choose(idx, 60)["file"] == "b.wav"
    assert music.choose([], 30) is None


def test_index_refreshes_tags_on_rename(tmp_path, monkeypatch):
    lib = tmp_path / "music"
    lib.mkdir()
    score.write_score(lib / "calm piano.wav", 6.0)
    calls = []
    monkeypatch.setattr(music, "analyze_track", lambda p: calls.append(p) or
                        {"duration": 6.0, "tempo": 96.0, "beats": [], "energy": 0.05})
    first = music.build_index(lib, tmp_path / "index.json")
    assert first[0]["tags"] == ["calm", "piano"]

    # Rename the file
    (lib / "calm piano.wav").rename(lib / "upbeat drums.wav")
    second = music.build_index(lib, tmp_path / "index.json")
    assert len(calls) == 1  # No new analysis call
    assert second[0]["tags"] == ["upbeat", "drums"]  # Tags updated


def test_index_handles_corrupt_cache(tmp_path, monkeypatch):
    lib = tmp_path / "music"
    lib.mkdir()
    score.write_score(lib / "track1.wav", 6.0)
    score.write_score(lib / "track2.wav", 6.0)

    # Write invalid JSON
    (tmp_path / "index.json").write_text("{not json")
    calls = []
    monkeypatch.setattr(music, "analyze_track", lambda p: calls.append(p) or
                        {"duration": 6.0, "tempo": 96.0, "beats": [], "energy": 0.05})

    entries = music.build_index(lib, tmp_path / "index.json")
    assert len(entries) == 2
    assert len(calls) == 2  # Both tracks analyzed


def test_index_skips_bad_cache_entries(tmp_path, monkeypatch):
    lib = tmp_path / "music"
    lib.mkdir()
    score.write_score(lib / "track.wav", 6.0)

    # Write cache with invalid entry structure
    (tmp_path / "index.json").write_text('["not a dict", {"no_sha1": true}]')
    calls = []
    monkeypatch.setattr(music, "analyze_track", lambda p: calls.append(p) or
                        {"duration": 6.0, "tempo": 96.0, "beats": [], "energy": 0.05})

    entries = music.build_index(lib, tmp_path / "index.json")
    assert len(entries) == 1
    assert len(calls) == 1


def test_changed_file_is_reanalysed(tmp_path, monkeypatch):
    lib = tmp_path / "music"
    lib.mkdir()
    score.write_score(lib / "track.wav", 6.0)
    calls = []

    def mock_analyze(p):
        calls.append(p)
        # Return different durations based on which call
        return {"duration": 6.0 if len(calls) == 1 else 8.0,
                "tempo": 96.0, "beats": [], "energy": 0.05}

    monkeypatch.setattr(music, "analyze_track", mock_analyze)

    music.build_index(lib, tmp_path / "index.json")
    assert len(calls) == 1

    # Overwrite file with different content
    score.write_score(lib / "track.wav", 8.0)
    second = music.build_index(lib, tmp_path / "index.json")
    assert len(calls) == 2  # New analysis call
    assert second[0]["duration"] == 8.0


def test_score_rejects_non_positive_duration(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="duration must be positive"):
        score.write_score(tmp_path / "bad.wav", 0.0)
    with pytest.raises(ValueError, match="duration must be positive"):
        score.write_score(tmp_path / "bad.wav", -1.0)
