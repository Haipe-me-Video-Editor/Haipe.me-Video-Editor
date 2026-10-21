import pytest

from editor import cuts


def _spans(segments):
    return [(s["in"], s["out"]) for s in segments]


def test_fillers_and_retakes_are_cut(words):
    segments, removed = cuts.plan_cuts("raw/talk.mp4", 10.0, words=words)
    assert _spans(segments) == pytest.approx(
        [(0.44, 0.79), (1.04, 2.49), (4.94, 6.04), (7.14, 8.59), (8.84, 9.49)])
    assert [s["zoom"] for s in segments] == [1.0, 1.1, 1.0, 1.1, 1.0]
    assert {r["kind"] for r in removed} == {"filler", "retake"}
    assert [r["text"] for r in removed if r["kind"] == "retake"] == ["Our new app"]


def test_filler_audio_never_survives_inside_a_segment(words):
    segments, _ = cuts.plan_cuts("raw/talk.mp4", 10.0, words=words)
    for s in segments:
        assert not (s["in"] < 0.9 < s["out"])  # middle of "um"


def test_same_opening_with_different_endings_is_not_a_retake():
    ws = [{"w": "I", "start": 0.0, "end": 0.1}, {"w": "think", "start": 0.15, "end": 0.4},
          {"w": "yes.", "start": 0.45, "end": 0.8},
          {"w": "I", "start": 1.6, "end": 1.7}, {"w": "think", "start": 1.75, "end": 2.0},
          {"w": "no.", "start": 2.05, "end": 2.4}]
    _, removed = cuts.plan_cuts("raw/a.mp4", 3.0, words=ws)
    assert removed == []


def test_you_know_only_cut_when_standalone():
    ws = [{"w": "it", "start": 0.0, "end": 0.2}, {"w": "you", "start": 0.5, "end": 0.6},
          {"w": "know", "start": 0.62, "end": 0.8}, {"w": "works.", "start": 1.1, "end": 1.5},
          {"w": "Do", "start": 2.0, "end": 2.1}, {"w": "you", "start": 2.12, "end": 2.2},
          {"w": "know", "start": 2.22, "end": 2.4}, {"w": "him?", "start": 2.42, "end": 2.7}]
    removed = []
    kept = cuts.remove_fillers(ws, removed)
    assert [r["text"] for r in removed] == ["you know"]
    assert [w["w"] for w in kept] == ["it", "works.", "Do", "you", "know", "him?"]


def test_voiced_gap_without_a_word_is_cut_but_silent_gap_is_kept():
    import numpy as np
    ws = [{"w": "one", "start": 0.0, "end": 0.4}, {"w": "two", "start": 0.65, "end": 1.0},
          {"w": "three", "start": 1.25, "end": 1.6}]
    db = np.full(200, -60.0)
    db[42:63] = -20.0  # sound in the 0.42-0.63 s gap with no transcribed word: an untranscribed "um"
    segments, removed = cuts.plan_cuts("raw/a.mp4", 2.0, words=ws, energy=db)
    assert len(segments) == 2  # split around the voiced gap; the silent 1.0-1.25 gap stays inside
    assert removed[0]["text"] == "(untranscribed sound)"


def test_silence_fallback_without_words():
    sil = [[0.0, 0.5], [2.5, 3.5], [6.0, 7.2], [9.5, 10.0]]
    segments, removed = cuts.plan_cuts("raw/talk.mp4", 10.0, silences=sil)
    assert _spans(segments) == pytest.approx([(0.425, 2.575), (3.425, 6.075), (7.125, 9.575)])
    assert removed == []


def _overlaps(seg, start, end):
    return seg["in"] < end and start < seg["out"]


def test_no_segment_overlaps_any_removed_interval(words):
    segments, removed = cuts.plan_cuts("raw/talk.mp4", 10.0, words=words)
    assert removed
    for r in removed:
        for s in segments:
            assert not _overlaps(s, r["start"], r["end"]), (s, r)


def test_voiced_gap_is_not_re_admitted_by_padding():
    import numpy as np
    ws = [{"w": "one", "start": 0.0, "end": 0.4}, {"w": "two", "start": 0.65, "end": 1.0},
          {"w": "three", "start": 1.25, "end": 1.6}]
    db = np.full(200, -60.0)
    db[42:63] = -20.0
    segments, _ = cuts.plan_cuts("raw/a.mp4", 2.0, words=ws, energy=db)
    assert not any(_overlaps(s, 0.42, 0.63) for s in segments)
    assert _spans(segments) == pytest.approx([(0.0, 0.4), (0.65, 1.69)])


def test_transcribed_filler_right_after_a_word_is_not_re_admitted():
    ws = [{"w": "so", "start": 0.0, "end": 0.3}, {"w": "um", "start": 0.35, "end": 0.5},
          {"w": "today", "start": 0.9, "end": 1.3}]
    segments, removed = cuts.plan_cuts("raw/a.mp4", 2.0, words=ws)
    assert [r["text"] for r in removed] == ["um"]
    assert not any(_overlaps(s, 0.35, 0.5) for s in segments)


def test_long_sentences_sharing_an_opening_are_not_retakes():
    ws = [{"w": "I", "start": 0.0, "end": 0.1}, {"w": "think", "start": 0.15, "end": 0.4},
          {"w": "we", "start": 0.45, "end": 0.6}, {"w": "should", "start": 0.65, "end": 0.9},
          {"w": "ship.", "start": 0.95, "end": 1.3},
          {"w": "I", "start": 1.6, "end": 1.7}, {"w": "think", "start": 1.75, "end": 2.0},
          {"w": "we", "start": 2.05, "end": 2.2}, {"w": "should", "start": 2.25, "end": 2.5},
          {"w": "wait.", "start": 2.55, "end": 2.9}]
    segments, removed = cuts.plan_cuts("raw/a.mp4", 3.5, words=ws)
    assert removed == []
    # both sentences kept: the 0.3 s gap is under MAX_GAP so they form one segment
    assert len(segments) == 1 and segments[0]["in"] == 0.0 and segments[0]["out"] >= 2.9


def test_punctuated_prefix_take_is_a_retake():
    ws = [{"w": "Our", "start": 0.0, "end": 0.2}, {"w": "new", "start": 0.25, "end": 0.45},
          {"w": "app.", "start": 0.5, "end": 0.9},
          {"w": "Our", "start": 1.5, "end": 1.7}, {"w": "new", "start": 1.75, "end": 1.95},
          {"w": "app", "start": 2.0, "end": 2.3}, {"w": "is", "start": 2.35, "end": 2.5},
          {"w": "live.", "start": 2.55, "end": 3.0}]
    segments, removed = cuts.plan_cuts("raw/a.mp4", 4.0, words=ws)
    assert [r["text"] for r in removed] == ["Our new app."]
    assert [r["kind"] for r in removed] == ["retake"]
    assert len(segments) == 1 and segments[0]["in"] >= 1.4
