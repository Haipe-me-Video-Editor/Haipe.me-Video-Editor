import json
from pathlib import Path

import pytest

from editor import analyze, captions, editjson, ffmpeg
from editor.cli import main
from editor.pack import pack

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.slow
def test_clip_to_reviewed_bilingual_video(tmp_path, talking_clip):
    proj = tmp_path / "proj"
    main(["new", str(proj), str(talking_clip), "--brief", "test"])
    main(["analyze", str(proj), "--transcript-file", str(FIX / "words.json")])
    assert (proj / "transcript_packed.md").read_text().startswith("[0000.50-")
    main(["draft", str(proj), "--captions", "bilingual"])
    plan = editjson.load(proj / "edit.json")
    assert len(plan["segments"]) == 5 and plan["captions"]["mode"] == "bilingual"
    plan["graphics"].append({"type": "list", "at": 0.5, "dur": 1.5, "items": ["One", "Two"]})
    plan["sfx"].append({"at": 0.5, "kind": "whoosh"})
    editjson.save(proj / "edit.json", plan)
    main(["captions", str(proj)])
    cap = json.loads((proj / "work" / "captions.json").read_text(encoding="utf-8"))
    for ln in cap["lines"]:  # Claude fills translations here
        ln["tr"] = "نطلق اليوم"
    (proj / "work" / "captions.json").write_text(json.dumps(cap, ensure_ascii=False), encoding="utf-8")
    main(["render", str(proj)])
    with pytest.raises(SystemExit) as done:
        main(["review", str(proj)])
    review = json.loads((proj / "review.json").read_text())
    assert done.value.code == 0, review
    assert review["passed"] and review["cut_views"]
    assert (proj / "out" / "final.mp4").exists() and (proj / "out" / "final-nomusic.mp4").exists()
    assert "filler" in (proj / "out" / "notes.txt").read_text()


def _project(tmp_path, clip=None, words=None):
    """A project folder as `new` + `analyze --transcript-file` leave it, without proxies or sheets."""
    proj = tmp_path / "proj"
    (proj / "raw").mkdir(parents=True)
    words = json.loads((FIX / "words.json").read_text()) if words is None else words
    (proj / "transcript.json").write_text(json.dumps(
        {"language": "en", "engine": "file", "notes": [], "error": None, "words": words}), encoding="utf-8")
    if clip:
        src = proj / "raw" / clip.name
        src.write_bytes(clip.read_bytes())
        info = ffmpeg.probe(src)
        (proj / "project.json").write_text(json.dumps(
            {"source": f"raw/{clip.name}", "proxy": f"raw/{clip.name}", "brief": "", "probe": info}))
        (proj / "silences.json").write_text(json.dumps(analyze.silences(src, duration=info["duration"])))
    return proj, words


def test_draft_writes_a_timeline_transcript(tmp_path, talking_clip):
    proj, words = _project(tmp_path, talking_clip)
    main(["draft", str(proj)])
    plan = editjson.load(proj / "edit.json")
    text = (proj / "transcript_timeline.md").read_text(encoding="utf-8")
    assert text == pack(captions.timeline_words(plan["segments"], words))
    first = float(text[1:8])
    assert text.startswith("[0000.") and first < 0.3  # timeline time, not the source 0000.50


def test_timeline_command_follows_segment_changes(tmp_path, talking_clip):
    proj, words = _project(tmp_path, talking_clip)
    main(["draft", str(proj)])
    before = (proj / "transcript_timeline.md").read_text(encoding="utf-8")
    plan = editjson.load(proj / "edit.json")
    plan["segments"] = plan["segments"][1:]
    editjson.save(proj / "edit.json", plan)
    main(["timeline", str(proj)])
    after = (proj / "transcript_timeline.md").read_text(encoding="utf-8")
    assert after != before and after == pack(captions.timeline_words(plan["segments"], words))


def _captioned(tmp_path):
    proj, words = _project(tmp_path)
    plan = editjson.new_plan([{"src": "raw/a.mp4", "in": 0.4, "out": 2.5}, {"src": "raw/a.mp4", "in": 3.4, "out": 4.4},
                              {"src": "raw/a.mp4", "in": 7.1, "out": 9.5}])
    plan["captions"]["mode"] = "bilingual"
    editjson.save(proj / "edit.json", plan)
    return proj


def test_rerunning_captions_keeps_translations_of_identical_lines(tmp_path):
    proj = _captioned(tmp_path)
    cap_path = proj / "work" / "captions.json"
    main(["captions", str(proj)])
    cap = json.loads(cap_path.read_text(encoding="utf-8"))
    for k, ln in enumerate(cap["lines"]):
        ln["tr"] = f"ترجمة {k}"
    cap_path.write_text(json.dumps(cap, ensure_ascii=False), encoding="utf-8")
    main(["captions", str(proj)])
    again = json.loads(cap_path.read_text(encoding="utf-8"))
    assert [ln["tr"] for ln in again["lines"]] == [f"ترجمة {k}" for k in range(len(cap["lines"]))]


def test_align_without_words_says_why(tmp_path):
    proj, _ = _project(tmp_path, words=None)
    tr = json.loads((proj / "transcript.json").read_text(encoding="utf-8"))
    tr["words"] = None
    (proj / "transcript.json").write_text(json.dumps(tr), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        main(["align", str(proj)])
    assert e.value.code == "align: transcript.json has no words to align (transcription was skipped or failed)"
