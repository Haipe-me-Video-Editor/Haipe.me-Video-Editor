import json

import pytest

from editor import captions
from editor.style import load_style

STYLE = load_style()
SIZE = (1080, 1920)
SEGS = [{"src": "a", "in": 0.44, "out": 0.79, "zoom": 1.0}, {"src": "a", "in": 1.04, "out": 2.49, "zoom": 1.1}]


def test_words_are_mapped_onto_the_cut_timeline(words):
    tw = captions.timeline_words(SEGS, words)
    assert [w["w"] for w in tw] == ["So", "today", "we", "launch."]
    assert tw[1]["start"] == pytest.approx(0.41)


def test_chunk_respects_word_count_punctuation_and_gaps():
    ws = [{"w": t, "start": i * 0.3, "end": i * 0.3 + 0.25} for i, t in
          enumerate(["one", "two", "three", "four", "five", "six."])]
    assert [[w["w"] for w in ln] for ln in captions.chunk(ws, max_words=4)] == \
        [["one", "two", "three", "four"], ["five", "six."]]
    assert len(captions.chunk([{"w": "a", "start": 0, "end": 0.2}, {"w": "b", "start": 1.0, "end": 1.2}])) == 2


def test_source_mode_one_event_per_word_with_highlight_and_rtl_safe_encoding(words):
    lines = captions.build_lines(SEGS, words, STYLE, SIZE)
    ass = captions.to_ass(lines, STYLE, SIZE)
    assert "PlayResX: 1080" in ass and ass.count("Dialogue:") == 4
    assert r"{\1c&H1A7AFF&}" in ass
    assert all(ln.endswith(",-1") for ln in ass.splitlines() if ln.startswith("Style:"))
    assert r"\kf" not in ass


def test_arabic_lines_use_the_arabic_font():
    ln = [{"start": 0, "end": 1, "hook": False, "tr": None,
           "words": [{"w": "ذهبنا", "start": 0, "end": 0.5}, {"w": "المكتبة", "start": 0.5, "end": 1}]}]
    ass = captions.to_ass(ln, STYLE, SIZE)
    assert ",CapA," in ass and "IBM Plex Sans Arabic" in ass


def test_bilingual_needs_translations_and_puts_arabic_on_top(words):
    lines = captions.build_lines(SEGS, words, STYLE, SIZE)
    with pytest.raises(ValueError):
        captions.to_ass(lines, STYLE, SIZE, mode="bilingual")
    for ln in lines:
        ln["tr"] = "اليوم نطلق"
    ass = captions.to_ass(lines, STYLE, SIZE, mode="bilingual")
    assert ",TopA," in ass and ",BotL," in ass


def test_translated_single_language_mode_shows_translation_only(words):
    lines = captions.build_lines(SEGS, words, STYLE, SIZE)
    for ln in lines:
        ln["tr"] = "اليوم نطلق"
    ass = captions.to_ass(lines, STYLE, SIZE, mode="ar")
    assert ass.count("Dialogue:") == len(lines) and "launch" not in ass


def test_layout_check_flags_long_lines():
    long = [{"start": 0, "end": 1, "hook": False, "tr": None, "words": [{"w": "x" * 45, "start": 0, "end": 1}]}]
    assert captions.check_layout(long, STYLE, SIZE)
    ok = [{"start": 0, "end": 1, "hook": False, "tr": None, "words": [{"w": "short", "start": 0, "end": 1}]}]
    assert captions.check_layout(ok, STYLE, SIZE) == []


def _w(text, start, end):
    return {"w": text, "start": start, "end": end}


def _line(words, tr=None, hook=False):
    return {"start": words[0]["start"], "end": words[-1]["end"], "hook": hook, "tr": tr, "words": words}


def test_western_digits_in_every_caption_text():
    ln = [_line([_w("بعد", 0, 0.5), _w("٣", 0.5, 1.0)], tr="٣ أيام")]
    ass = captions.to_ass(ln, STYLE, SIZE, mode="bilingual")
    assert "3 أيام" in ass
    assert not any(c in ass for c in "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹")


def test_chunk_avoids_one_word_orphans_but_keeps_pause_isolated_words():
    ws = [_w(t, i * 0.3, i * 0.3 + 0.25) for i, t in enumerate(["one", "two", "three", "four", "five"])]
    assert [[w["w"] for w in ln] for ln in captions.chunk(ws, max_words=4)] == \
        [["one", "two", "three"], ["four", "five"]]
    stop = [_w(t, i * 0.3, i * 0.3 + 0.25) for i, t in enumerate(["one", "two", "three.", "four"])]
    assert [[w["w"] for w in ln] for ln in captions.chunk(stop, min_words=2, max_words=3)] == \
        [["one", "two", "three."], ["four"]]
    pause = [_w("a", 0, 0.2), _w("b", 0.2, 0.4), _w("c", 0.4, 0.6), _w("d", 2.0, 2.2)]
    assert [len(ln) for ln in captions.chunk(pause, max_words=3)] == [3, 1]


def test_unknown_caption_mode_raises():
    ln = [_line([_w("hello", 0, 1)])]
    with pytest.raises(ValueError):
        captions.to_ass(ln, STYLE, SIZE, mode="french")
    with pytest.raises(ValueError):
        captions.check_layout(ln, STYLE, SIZE, mode="french")


def test_word_on_a_shared_segment_boundary_appears_once():
    segs = [{"src": "a", "in": 0.0, "out": 1.0, "zoom": 1.0}, {"src": "a", "in": 1.0, "out": 2.0, "zoom": 1.0}]
    tw = captions.timeline_words(segs, [_w("edge", 0.9, 1.1)])
    assert [w["w"] for w in tw] == ["edge"]


def test_ar_mode_needs_translation_for_english_source():
    ln = [_line([_w("hello", 0, 1)])]
    with pytest.raises(ValueError):
        captions.to_ass(ln, STYLE, SIZE, mode="ar")


def test_en_mode_shows_the_english_translation_of_arabic_source_only():
    lns = [_line([_w("ذهبنا", 0, 0.5), _w("المكتبة", 0.5, 1)], tr="we went to the library"),
           _line([_w("مرحبا", 1, 2)], tr="hello")]
    ass = captions.to_ass(lns, STYLE, SIZE, mode="en")
    assert ass.count("Dialogue:") == 2 and "we went to the library" in ass
    assert "ذهبنا" not in ass and "مرحبا" not in ass


def test_highlight_moves_one_word_per_event():
    ln = [_line([_w("alpha", 0, 0.4), _w("beta", 0.4, 0.8), _w("gamma", 0.8, 1.2)])]
    events = [e for e in captions.to_ass(ln, STYLE, SIZE).splitlines() if e.startswith("Dialogue:")]
    assert len(events) == 3
    for k, word in enumerate(["alpha", "beta", "gamma"]):
        assert f"{{\\1c&H1A7AFF&}}{word}{{" in events[k]
        assert events[k].count("&H1A7AFF&") == 1


def test_layout_check_flags_a_caption_below_the_safe_area():
    low = dict(STYLE, caption_margin_v=0.05)
    ok = [_line([_w("short", 0, 1)])]
    assert any("safe area" in i for i in captions.check_layout(ok, low, SIZE))


FULL = [{"src": "a", "in": 0.4, "out": 2.5}, {"src": "a", "in": 3.4, "out": 4.4}, {"src": "a", "in": 7.1, "out": 9.5}]


def _text(ln):
    return " ".join(w["w"] for w in ln["words"])


def _translated(path, plan, words):
    """Build the cache, then fill every line's tr the way Claude does."""
    captions.ensure_lines(path, plan, words, STYLE, SIZE)
    doc = json.loads(path.read_text(encoding="utf-8"))
    for ln in doc["lines"]:
        ln["tr"] = "T " + _text(ln)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc


def test_caption_cache_keeps_translations_when_one_segment_changes(tmp_path, words):
    path, plan = tmp_path / "captions.json", {"format": "9:16", "segments": [dict(s) for s in FULL]}
    old = _translated(path, plan, words)
    assert captions.ensure_lines(path, plan, words, STYLE, SIZE) == old["lines"]  # same key: untouched
    plan["segments"][2]["out"] = 8.0  # drops "now." and "Thanks."
    lines = captions.ensure_lines(path, plan, words, STYLE, SIZE)
    old_texts = {_text(ln) for ln in old["lines"]}
    kept = [ln for ln in lines if _text(ln) in old_texts]
    assert kept and all(ln["tr"] == "T " + _text(ln) for ln in kept)
    assert any(ln["tr"] is None for ln in lines if _text(ln) not in old_texts)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["lines"] == lines and saved["key"] != old["key"] and "segments_hash" in saved


def test_caption_cache_is_invalidated_by_a_transcript_change(tmp_path, words):
    path, plan = tmp_path / "captions.json", {"format": "9:16", "segments": FULL}
    _translated(path, plan, words)
    fixed = [dict(w) for w in words]
    fixed[-1]["w"] = "Thank you."
    lines = captions.ensure_lines(path, plan, fixed, STYLE, SIZE)
    assert any("Thank you." in _text(ln) for ln in lines)
    assert all((ln["tr"] is None) == ("Thank you." in _text(ln)) for ln in lines)


def test_caption_cache_key_covers_format_and_caption_style(words):
    plan = {"format": "9:16", "segments": FULL}
    key = captions.cache_key(plan, words, STYLE)
    assert captions.cache_key(dict(plan, format="1:1"), words, STYLE) != key
    assert captions.cache_key(plan, words, dict(STYLE, caption_size=0.06)) != key
    assert captions.cache_key(plan, words, dict(STYLE, accent="#ff0000")) == key  # colour is not cached


def test_sync_lines_carries_tr_to_the_first_unused_identical_line():
    old = {"lines": [_line([_w("go", 0, 1)], tr="A"), _line([_w("go", 2, 3)], tr="B")]}
    new = [_line([_w("go", 5, 6)]), _line([_w("go", 7, 8)]), _line([_w("go", 9, 9.5)])]
    assert [ln["tr"] for ln in captions.sync_lines(old, new)] == ["A", "B", None]


def test_a_caption_line_never_runs_across_a_cut():
    segs = [{"src": "a.mp4", "in": 0.0, "out": 1.0}, {"src": "a.mp4", "in": 5.0, "out": 6.0}]
    words = [{"w": "one", "start": 0.2, "end": 0.5}, {"w": "two", "start": 0.6, "end": 0.95},
             {"w": "three", "start": 5.05, "end": 5.4}, {"w": "four", "start": 5.5, "end": 5.9}]
    lines = captions.chunk(captions.timeline_words(segs, words), max_words=4)
    assert [[w["w"] for w in ln] for ln in lines] == [["one", "two"], ["three", "four"]]


def test_chunk_br_and_glue_steer_lines_by_hand():
    w = lambda t, s, **k: {"w": t, "start": s, "end": s + 0.2, "seg": 0, **k}
    words = [w("على", 0.0, glue=True), w("منصة", 0.25, glue=True), w("الموقع", 0.5, br=True), w("حق", 0.75), w("الخمس", 1.0, glue=True),
             w("فائزين", 1.25, br=True), w("على", 1.5, glue=True), w("الـ", 1.75, glue=True), w("Silver", 2.0, glue=True),
             w("Sticker", 2.25)]
    lines = [" ".join(x["w"] for x in ln) for ln in captions.chunk(words, max_words=3, max_chars=12)]
    assert lines == ["على منصة الموقع", "حق الخمس فائزين", "على الـ Silver Sticker"]


def test_timeline_words_carry_br_and_glue():
    tw = captions.timeline_words([{"in": 0.0, "out": 2.0}], [{"w": "a", "start": 0.1, "end": 0.3, "br": True},
                                                             {"w": "b", "start": 0.4, "end": 0.6, "glue": True}])
    assert tw[0].get("br") and tw[1].get("glue") and "glue" not in tw[0]
