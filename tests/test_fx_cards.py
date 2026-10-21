"""Tech cards: terminal, code_card, rank_list (timing and markup; the layout crop)."""
import pytest

from editor.fx import _split as S
from editor.fx import code_card, rank_list, registry, terminal


def test_registered():
    reg = registry()
    assert reg["terminal"] is terminal and reg["code_card"] is code_card and reg["rank_list"] is rank_list


def test_terminal_lines_follow_each_other_and_fit_the_window():
    ts = terminal.times_for(["$ run this", "✓ done", "$ and that one too", "✓ saved"], 3.0)
    assert ts == sorted(ts) and ts[0] > 0 and ts[-1] < 3.0 * 0.8 + 0.2
    assert terminal.times_for(["a", "b"], 2, [0.5, 1.0]) == [0.5, 1.0]
    with pytest.raises(ValueError):
        terminal.times_for(["a"], 2, [0.1, 0.2])


def test_code_is_escaped_and_coloured():
    h = code_card.colour("if (x < 3) throw 'no' // why")
    assert "&lt;" in h and "<script" not in h
    assert h.count("<span") == 5  # if, 3, the string, throw, the comment
    assert code_card.colour("<b>") == "&lt;b&gt;"


def test_rank_list_lights_in_order():
    assert rank_list.light_times(3, 3.0) == sorted(rank_list.light_times(3, 3.0))
    with pytest.raises(ValueError):
        rank_list.light_times(3, 3.0, [1, 2])


def test_the_speaker_crop_never_cuts_the_head():
    assert S.crop_top(None, 1920) == S.SPLIT_Y
    close = {"top": 120, "fw": 420}  # hairline near the top of a close-up
    assert S.crop_top(close, 1920) == 0.0
    medium = {"top": 700, "fw": 300}
    assert 0 < S.crop_top(medium, 1920) < (700 - 0.45 * 300) / 1920
