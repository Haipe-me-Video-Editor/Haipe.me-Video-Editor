"""checklist_pop (pills beside the speaker) and counter_tally (a page that counts up over a ticking list)."""
import os
from pathlib import Path

import numpy as np
import pytest

from editor.fx import _behind as B
from editor.fx import checklist_pop, counter_tally, registry

W, H = 1080, 1920
FACE = {"cx": 540.0, "cy": 700.0, "fw": 330.0, "eye_y": 650.0, "top": 520.0}


@pytest.mark.parametrize("mod", [checklist_pop, counter_tally])
def test_registered_with_the_planner_fields(mod):
    assert registry()[mod.NAME] is mod
    assert mod.DOC and mod.BEST_FOR and mod.PARAMS and len(mod.DUR) == 2
    assert "at" not in mod.PARAMS and "dur" not in mod.PARAMS


# checklist_pop --------------------------------------------------------------------------------------------------
def test_checklist_pop_items_spread_and_leave_time_to_tick():
    t = checklist_pop.times_for(4, None, 3.0, 0.35)
    assert len(t) == 4 and t == sorted(t) and t[0] > 0
    assert t[-1] + 0.35 < 3.0 - checklist_pop.EXIT
    with pytest.raises(ValueError):
        checklist_pop.times_for(3, [0.2, 0.5], 3.0, 0.35)


def test_checklist_pop_done_pill_carries_the_green_check():
    green = np.array([22, 160, 93])
    todo, done = checklist_pop.pill("Trim", 90, False, green), checklist_pop.pill("Trim", 90, True, green)
    assert todo.shape == done.shape
    def greenish(s):
        rgb = s[..., :3] * 255
        return int(((s[..., 3] > 0.9) & (rgb[..., 1] > 130) & (rgb[..., 0] < 60) & (rgb[..., 2] < 120)).sum())
    assert greenish(done) > 200 and greenish(todo) == 0


def test_checklist_pop_column_sits_below_the_chin_inside_the_safe_zone():
    h = 0.05 * H
    widths = [300, 380, 340, 260]
    x, ys, side = checklist_pop.layout(widths, h, FACE, "auto", W, H)
    assert side == "right"
    assert ys[0] - h / 2 > FACE["cy"] + FACE["fw"] * 0.5
    assert B.SAFE[0] * W <= x and x + max(widths) <= B.SAFE[2] * W + 1
    assert ys[-1] + h / 2 <= B.SAFE[3] * H + 1
    _, _, side = checklist_pop.layout(widths, h, {**FACE, "cx": 700.0}, "auto", W, H)
    assert side == "left"


# counter_tally --------------------------------------------------------------------------------------------------
def test_counter_counts_steadily_from_start_to_total():
    seq = [counter_tally.count_at(t / 10, 0.5, 2.5, 0, 18) for t in range(31)]
    assert seq[0] == 0 and seq[-1] == 18 and seq == sorted(seq)
    assert counter_tally.count_at(1.5, 0.5, 2.5, 0, 18) == 9  # halfway through the count, half the total


def test_tally_card_fits_the_safe_zone_and_lists_column_major():
    g = counter_tally.geometry(W, H, 18, True)
    x0, _y0, x1, y1 = g["card"]
    assert g["cols"] == 2 and g["rows"] == 9
    assert y1 <= B.SAFE[3] * H and x1 <= B.SAFE[2] * W and x0 >= B.SAFE[0] * W - 20
    first, second, tenth = (counter_tally.item_rect(g, k) for k in (0, 1, 9))
    assert second[1] > first[1] and second[0] == first[0]  # 02 under 01
    assert tenth[0] > first[0] and tenth[1] == first[1]    # 10 tops the second column
    assert counter_tally.geometry(W, H, 5, False)["cols"] == 1
    assert "card" not in counter_tally.geometry(W, H, 0, False)


SRC = Path(os.environ.get("FX_TEST_CLIP", "/nonexistent"))


@pytest.mark.slow
@pytest.mark.skipif(not SRC.exists(), reason="set FX_TEST_CLIP to a 9:16 talking-head clip")
@pytest.mark.parametrize("spec", [{"type": "checklist_pop", "items": ["Trim", "Captions", "Post"]},
                                  {"type": "counter_tally", "items": ["a", "b", "c"], "label": "steps"},
                                  {"type": "counter_tally", "total": 40, "caption": "Counter alone"}])
def test_renders_exact_frames(tmp_path, spec):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    out = apply_fx(SRC, [{**spec, "at": 0.5, "dur": 2.5}], tmp_path, {"name": "t"})
    assert abs(ffmpeg.probe(out)["duration"] - ffmpeg.probe(SRC)["duration"]) < 0.1
