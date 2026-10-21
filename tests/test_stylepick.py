"""Style picker: the talk and the picture choose the style; the check flags flat or repetitive plans."""
import json

from editor import stylepick as sp


def _talk(**topics):
    return {"wps": 2.6, "duration": 60, "edit_s": 50, "language": "en",
            "topics": {**{k: 0.0 for k in sp.TOPICS}, **topics}}


def test_the_talk_decides_the_style():
    medium = {"shot": "medium", "movement": 0.1, "busy": 0.2, "headroom": 0.2}
    assert sp.choose(medium, _talk(tools=4))[0] == "rapid_visual"
    assert sp.choose(medium, _talk(money=4))[0] == "data_explainer"
    assert sp.choose(medium, {**_talk(story=4), "wps": 1.8})[0] == "minimal_story"
    assert sp.choose({**medium, "movement": 0.9}, {**_talk(), "wps": 3.6})[0] == "energetic"
    assert sp.choose(medium, _talk(), "I like calm, cinematic edits")[0] == "minimal_story"  # the profile leans it


def test_topics_are_found_in_arabic_and_english(tmp_path):
    words = [{"w": w, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, w in
             enumerate("حطيت الكود في الريبو على github وخليت claude يركب البرنامج".split())]
    (tmp_path / "transcript.json").write_text(json.dumps({"language": "ar", "words": words}), encoding="utf-8")
    t = sp.talk(tmp_path)
    assert t["topics"]["tools"] > t["topics"]["money"] and t["edit_s"] <= t["duration"]


def test_the_palette_drops_what_the_footage_cannot_carry(tmp_path):
    (tmp_path / "faces.json").write_text(json.dumps({"source": [1080, 1920], "samples": [
        {"t": i * 0.5, "box": [0.2, 0.0, 0.8, 0.45]} for i in range(10)]}))  # a still close-up, no headroom
    (tmp_path / "transcript.json").write_text(json.dumps({"words": [
        {"w": "story", "start": 0, "end": 0.5}, {"w": "i was", "start": 1, "end": 1.5}]}))
    p = sp.plan(tmp_path, "high energy and fun")
    allfx = {e for v in p["palette"].values() for e in v}
    assert p["footage"]["shot"] == "close" and not allfx & (sp.NEEDS_HEADROOM | sp.NEEDS_MOVEMENT)
    assert p["effects"] >= 3 and p["rhythm"]["hook"] and p["brand"]


def test_check_flags_repeats_too_few_kinds_flat_stretches_and_no_hook():
    edit = {"segments": [{"in": 0, "out": 40}], "graphics": [], "broll": [], "transitions": [],
            "fx": [{"type": "digital_zoom", "at": 3}, {"type": "digital_zoom", "at": 8},
                   {"type": "digital_zoom", "at": 30}]}
    probs = "\n".join(sp.check(edit, {"effects": 4}))
    assert "twice within 10 s" in probs and "used 3 times" in probs and "different effect types" in probs
    assert "first 1.5 s" in probs and "8.0-30.0s" in probs
    good = {"segments": [{"in": 0, "out": 30}], "graphics": [{"at": 0.4}], "broll": [], "transitions": [],
            "fx": [{"type": t, "at": a} for t, a in (("word_stack", 2), ("outline", 9), ("terminal", 16),
                                                      ("digital_zoom", 22), ("glitch", 27))]}
    assert sp.check(good, {"effects": 5}) == []
