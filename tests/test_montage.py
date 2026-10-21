from editor import montage


def _rows(n, sharp_at=None):
    return [{"t": i * montage.STEP, "sharp": 900.0 if sharp_at and sharp_at[0] <= i < sharp_at[1] else 50.0,
             "motion": 5.0, "bright": 120.0, "loud": -20.0} for i in range(n)]


def test_best_moments_finds_the_sharp_window_without_overlaps():
    clips = {"raw/a.mp4": {"scores": _rows(40, (20, 26)), "duration": 20, "has_audio": True}}
    found = montage.best_moments(clips, length=2.0, top=5)
    assert found[0]["src"] == "raw/a.mp4" and 10.0 <= found[0]["in"] <= 11.0
    spans = sorted((m["in"], m["out"]) for m in found)
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))


def test_beat_cut_lands_every_cut_on_a_beat():
    beats = [0.5 * i for i in range(1, 40)]
    moments = [{"src": "raw/a.mp4", "in": 10.0 * i, "out": 10.0 * i + 2, "score": 1} for i in range(20)]
    segs = montage.beat_cut(moments, beats, total=6.0, beats_per_shot=2)
    t, cuts = 0.0, []
    for s in segs:
        t += s["out"] - s["in"]
        cuts.append(round(t, 3))
    assert cuts[-1] == 6.0 and all(round(c * 2) == c * 2 for c in cuts) and all(s["mute"] for s in segs)
