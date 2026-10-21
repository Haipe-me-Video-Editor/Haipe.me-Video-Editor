import json

import numpy as np

from editor import captions, review
from editor.style import load_style


def test_cut_times_are_cumulative():
    plan = {"segments": [{"in": 0, "out": 1.0}, {"in": 5, "out": 5.5}, {"in": 9, "out": 10}]}
    assert review.cut_times(plan) == [1.0, 1.5]


def test_find_pops_flags_a_spike_at_a_cut_only():
    db = np.full(300, -30.0)
    db[100] = -5.0  # 1.0 s
    assert review.find_pops(db, 0.01, [1.0, 2.0]) == [1.0]


def _reviewed(tmp_path, monkeypatch, plan, cap_plan=None, freezes=()):
    """Run review() on a one-segment plan with the media probes faked; return its checks by name."""
    words = [{"w": w, "start": 0.2 + i * 0.4, "end": 0.5 + i * 0.4} for i, w in enumerate(["one", "two", "three"])]
    (tmp_path / "transcript.json").write_text(json.dumps({"words": words}), encoding="utf-8")
    (tmp_path / "work").mkdir()
    (tmp_path / "sheets").mkdir()
    if cap_plan:
        captions.ensure_lines(tmp_path / "work" / "captions.json", cap_plan, words, load_style(), (1080, 1920))
    dur = plan["segments"][0]["out"]
    monkeypatch.setattr(review.ffmpeg, "probe", lambda p: {"duration": dur})
    monkeypatch.setattr(review.analyze, "black_frames", lambda p: [])
    monkeypatch.setattr(review.analyze, "frozen_ranges", lambda *a, **k: [list(f) for f in freezes])
    monkeypatch.setattr(review.analyze, "silences", lambda *a, **k: [])
    monkeypatch.setattr(review.analyze, "rms_db", lambda *a: np.full(300, -30.0))
    monkeypatch.setattr(review.analyze, "loudness", lambda p: {"input_i": -14.0})
    monkeypatch.setattr(review, "contact_sheet", lambda *a, **k: [])
    return {c["name"]: c for c in review.review(tmp_path, plan, load_style())["checks"]}


def _plan(out=2.0, enabled=True):
    return {"format": "9:16", "segments": [{"src": "raw/a.mp4", "in": 0.0, "out": out}],
            "captions": {"enabled": enabled, "mode": "source"}}


def test_review_checks_fresh_captions(tmp_path, monkeypatch):
    checks = _reviewed(tmp_path, monkeypatch, _plan(), cap_plan=_plan())
    assert checks["captions_safe_area"]["ok"]


def test_review_fails_stale_captions(tmp_path, monkeypatch):
    checks = _reviewed(tmp_path, monkeypatch, _plan(out=1.8), cap_plan=_plan())
    assert not checks["captions_safe_area"]["ok"]
    assert checks["captions_safe_area"]["detail"] == "captions.json is stale; run captions"


def test_review_skips_captions_when_they_are_off(tmp_path, monkeypatch):
    plan = _plan(enabled=False)
    plan.pop("captions")
    assert "captions_safe_area" not in _reviewed(tmp_path, monkeypatch, plan, cap_plan=_plan())
