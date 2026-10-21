import pytest
from editor import broll, ffmpeg


def _clip(path, seconds=3):
    ffmpeg.run(["-f", "lavfi", "-i", f"testsrc2=size=1080x1920:rate=30:duration={seconds}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path])


def test_index_tag_search_resolve(tmp_path):
    lib = tmp_path / "broll"
    lib.mkdir()
    _clip(lib / "rooftop.mp4")
    _clip(lib / "cafe.mp4")
    index_path = tmp_path / "broll-index.json"
    idx = broll.index_clips(lib, index_path)
    assert {e["file"] for e in idx} == {"rooftop.mp4", "cafe.mp4"}
    assert all(e["orientation"] == "portrait" and e["tags"] == [] for e in idx)

    broll.tag(index_path, "rooftop.mp4", ["rooftop", "dusk", "friends"], subject="friends toasting", mood="warm")
    broll.tag(index_path, "cafe.mp4", ["cafe", "coffee"], subject="barista pouring")
    idx = broll.index_clips(lib, index_path)  # re-index keeps tags
    assert broll.search(idx, "friends on a rooftop at dusk")[0]["file"] == "rooftop.mp4"

    plan = {"broll": [{"at": 1.0, "dur": 2.0, "query": "rooftop dusk", "resolved": None},
                      {"at": 4.0, "dur": 2.0, "query": "spaceship", "resolved": None}]}
    notes = broll.resolve(plan, idx, lib)
    assert plan["broll"][0]["resolved"].endswith("rooftop.mp4")
    assert plan["broll"][1]["resolved"] is None
    assert len(notes) == 1 and "spaceship" in notes[0]


def test_index_clips_handles_invalid_json(tmp_path):
    lib = tmp_path / "broll"
    lib.mkdir()
    _clip(lib / "test.mp4")
    index_path = tmp_path / "broll-index.json"

    # Write invalid JSON
    index_path.write_text("{invalid json")

    # Should not raise, should treat as absent and re-index
    idx = broll.index_clips(lib, index_path)
    assert len(idx) == 1
    assert idx[0]["file"] == "test.mp4"


def test_index_clips_handles_non_list(tmp_path):
    lib = tmp_path / "broll"
    lib.mkdir()
    _clip(lib / "test.mp4")
    index_path = tmp_path / "broll-index.json"

    # Write valid JSON but not a list
    index_path.write_text('{"not": "a list"}')

    # Should not raise, should treat as absent and re-index
    idx = broll.index_clips(lib, index_path)
    assert len(idx) == 1
    assert idx[0]["file"] == "test.mp4"


def test_index_clips_handles_missing_file_key(tmp_path):
    lib = tmp_path / "broll"
    lib.mkdir()
    _clip(lib / "test.mp4")
    index_path = tmp_path / "broll-index.json"

    # Write valid JSON list but entries don't have "file" key
    index_path.write_text('[{"name": "test"}]')

    # Should not raise, should treat as absent and re-index
    idx = broll.index_clips(lib, index_path)
    assert len(idx) == 1
    assert idx[0]["file"] == "test.mp4"


def test_tag_raises_on_missing_file(tmp_path):
    lib = tmp_path / "broll"
    lib.mkdir()
    _clip(lib / "test.mp4")
    index_path = tmp_path / "broll-index.json"

    broll.index_clips(lib, index_path)

    # Trying to tag a file not in the index should raise ValueError
    with pytest.raises(ValueError, match="not in the B-roll index"):
        broll.tag(index_path, "nonexistent.mp4", ["tag"])


def test_index_clips_skip_bad_entries_keep_valid_tags(tmp_path):
    """Test that one malformed entry does not discard valid tagged entries."""
    lib = tmp_path / "broll"
    lib.mkdir()
    _clip(lib / "good.mp4")
    _clip(lib / "also_good.mp4")
    index_path = tmp_path / "broll-index.json"

    # First indexing
    idx = broll.index_clips(lib, index_path)

    # Tag the first clip
    broll.tag(index_path, "good.mp4", ["rooftop", "dusk"], subject="friends toasting")

    # Manually corrupt the index by adding a bad entry and a dict without "file" key
    import json
    data = json.loads(index_path.read_text())
    data.append(42)  # Bad entry
    data.append({"nofile": 1})  # Dict without "file" key
    index_path.write_text(json.dumps(data))

    # Re-index: should keep the tags on "good.mp4" despite bad entries
    idx = broll.index_clips(lib, index_path)
    good_entry = next((e for e in idx if e["file"] == "good.mp4"), None)
    assert good_entry is not None
    assert good_entry["tags"] == ["rooftop", "dusk"]
    assert good_entry["subject"] == "friends toasting"


def test_index_clips_backup_corrupt_index(tmp_path):
    """Test that a corrupt index is backed up before being overwritten."""
    lib = tmp_path / "broll"
    lib.mkdir()
    _clip(lib / "test.mp4")
    index_path = tmp_path / "broll-index.json"

    # Write invalid JSON
    corrupt_data = "{invalid json"
    index_path.write_text(corrupt_data)

    # Re-index
    broll.index_clips(lib, index_path)

    # Check that a .corrupt backup exists with the original bytes
    corrupt_path = index_path.with_suffix(index_path.suffix + ".corrupt")
    assert corrupt_path.exists()
    assert corrupt_path.read_text() == corrupt_data


def test_search_ignores_stopwords(tmp_path):
    """Test that stopwords are filtered out in search."""
    lib = tmp_path / "broll"
    lib.mkdir()
    _clip(lib / "coffee.mp4")
    index_path = tmp_path / "broll-index.json"

    idx = broll.index_clips(lib, index_path)
    broll.tag(index_path, "coffee.mp4", ["cafe", "coffee"], subject="barista pouring a coffee")
    idx = broll.index_clips(lib, index_path)

    # Query "a spaceship" should not match "barista pouring a coffee"
    # because "a" and "spaceship" are stopwords or not in the subject
    results = broll.search(idx, "a spaceship")
    assert results == []


def test_search_arabic_words(tmp_path):
    """Test that Arabic words are matched correctly."""
    lib = tmp_path / "broll"
    lib.mkdir()
    _clip(lib / "coffee_morning.mp4")
    index_path = tmp_path / "broll-index.json"

    idx = broll.index_clips(lib, index_path)
    broll.tag(index_path, "coffee_morning.mp4", ["قهوة"], subject="قهوة الصباح")
    idx = broll.index_clips(lib, index_path)

    # Query "قهوة الصباح" should match the entry with tag "قهوة"
    results = broll.search(idx, "قهوة الصباح")
    assert len(results) == 1
    assert results[0]["file"] == "coffee_morning.mp4"


def test_arabic_punctuation_is_not_part_of_words():
    assert broll._words("قهوة، الصباح؟ 12") == {"قهوة", "الصباح", "12"}


def test_resolve_src_in_defaults_to_zero(tmp_path):
    """Test that resolve handles src_in:None correctly."""
    lib = tmp_path / "broll"
    lib.mkdir()
    _clip(lib / "rooftop.mp4")
    index_path = tmp_path / "broll-index.json"

    idx = broll.index_clips(lib, index_path)
    broll.tag(index_path, "rooftop.mp4", ["rooftop"], subject="friends toasting")
    idx = broll.index_clips(lib, index_path)

    # Plan with src_in set to None
    plan = {"broll": [{"at": 1.0, "dur": 2.0, "query": "rooftop", "resolved": None, "src_in": None}]}
    broll.resolve(plan, idx, lib)

    # Should resolve src_in to 0.0
    assert plan["broll"][0]["src_in"] == 0.0
