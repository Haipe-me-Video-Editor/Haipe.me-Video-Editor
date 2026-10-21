from editor import reel


def test_check_subs_flags_long_lines_overlaps_and_short_cues():
    subs = [[0.0, 1.0, "Hello all!"], [0.9, 2.0, "x" * 30], [2.0, 2.2, "a\\Nb\\Nc"]]
    errs = "\n".join(reel.check_subs(subs, limit=21))
    assert "overlaps" in errs and "30 chars" in errs and "shorter than 0.5" in errs and "more than 2 lines" in errs
    assert reel.check_subs([[0.0, 1.0, "Hello all!"], [1.0, 2.5, "Today we look at\\Nthe new results"]]) == []


def test_ass_keeps_line_breaks_closes_small_gaps_and_sits_low():
    ass = reel.to_ass([[0.2, 1.3, "Hello all!"], [1.5, 3.4, "Today we look at\\Nthe new results"]])
    events = [l for l in ass.splitlines() if l.startswith("Dialogue")]
    assert events[0].startswith("Dialogue: 0,0:00:00.20,0:00:01.50,CapL")  # 0.2 s gap closed
    assert "look at\\Nthe new" in events[1]
    assert ",422,-1" in next(l for l in ass.splitlines() if l.startswith("Style: CapL"))  # captions low (0.22)
