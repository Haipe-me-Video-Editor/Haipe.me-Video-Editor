import json
import subprocess

from editor import critique


def _project(tmp_path):
    (tmp_path / "out").mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=270x480:rate=10:duration=6",
                    "-pix_fmt", "yuv420p", str(tmp_path / "out" / "final.mp4")], check=True)
    plan = {"graphics": [{"type": "stat", "at": 1.0, "dur": 2.5, "value": "70%"}],
            "broll": [{"query": "city", "at": 3.6, "dur": 2.0}]}
    (tmp_path / "edit.json").write_text(json.dumps(plan))
    return tmp_path, plan


def test_sample_times_cover_entrance_landing_hold_and_exit_inside_the_window():
    ts = critique.sample_times(10.0, 3.0)
    assert len(ts) == 6 and ts == sorted(ts) and ts[0] >= 10.0 and ts[-1] < 13.0


def test_build_scores_and_check_keep_unchanged_scores(tmp_path):
    proj, plan = _project(tmp_path)
    path = critique.build(proj)
    data = json.loads(path.read_text())
    assert [i["key"] for i in data["items"]] == ["graphics[0]", "broll[0]"]
    assert (proj / data["items"][0]["sheet"]).exists()
    assert len(critique.check(proj)) == 2  # nothing scored yet
    data["items"][0].update(score=9, notes="clean")
    data["items"][1].update(score=6, notes="too dark")
    path.write_text(json.dumps(data))
    assert critique.check(proj) == ["broll[0] (city @ 3.6s) scored 6: too dark"]
    plan["broll"][0]["dur"] = 1.8  # the fix: only the changed item is re-scored
    (proj / "edit.json").write_text(json.dumps(plan))
    data = json.loads(critique.build(proj).read_text())
    assert data["round"] == 2 and data["items"][0]["score"] == 9 and data["items"][1]["score"] is None
    assert data["items"][1]["tries"] == 2
