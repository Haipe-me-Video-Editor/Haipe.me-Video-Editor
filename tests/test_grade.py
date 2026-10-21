import numpy as np

from editor import editjson, grade
from editor.render import segments_filter


def test_yellow_cast_is_pulled_back_toward_neutral():
    img = np.full((40, 40, 3), [0.62, 0.55, 0.42], np.float32)  # warm grey wall
    m = grade.measure_rgb(img)
    r, g, b = m["gains"]
    assert r < 1 < b
    fixed = img[0, 0] * m["gains"]
    assert np.ptp(fixed) < np.ptp(img[0, 0]) * 0.4


def test_levels_never_push_a_saturated_colour_past_white():
    img = np.zeros((40, 40, 3), np.float32)
    img[:20] = [0.98, 0.1, 0.1]  # bright red shirt
    img[20:] = [0.5, 0.5, 0.5]
    assert grade.measure_rgb(img)["white"] >= 0.97


def test_chain_keeps_saturation_by_putting_contrast_on_luma_only():
    c = grade.chain({"gains": [0.95, 1.0, 1.05], "black": 0.02, "white": 0.95}, "clean")
    assert "colorchannelmixer=rr=0.95:gg=1.0:bb=1.05" in c and "lutyuv=y=" in c
    assert "vibrance" not in c and "curves" not in c


def test_graded_segments_carry_their_chain_into_the_filter():
    plan = {"segments": [{"src": "a.mp4", "in": 0.0, "out": 1.0, "_grade": "GRADE"}]}
    assert "GRADE,setsar=1" in ";".join(segments_filter(plan, {"a.mp4": 0}, (1080, 1920)))


def test_grade_validation():
    p = editjson.new_plan([{"src": "raw/a.mp4", "in": 0.0, "out": 2.0}])
    p["grade"] = {"look": "punchy"}
    assert editjson.validate(p) == []
    p["grade"] = {"look": "neon"}
    assert any("grade" in e for e in editjson.validate(p))


def test_white_wall_lands_on_neutral_with_coloured_objects_around():
    rng = np.random.default_rng(1)
    img = np.empty((60, 60, 3), np.float32)
    img[:30] = [0.80, 0.74, 0.60]  # white wall under warm light
    img[30:45] = [0.70, 0.15, 0.12]  # red product
    img[45:] = rng.uniform(0.1, 0.9, (15, 60, 3))  # busy stand
    g = grade.white_balance(img)
    wall = img[0, 0] * g
    assert np.ptp(wall) / wall.mean() < 0.03


def test_strong_magenta_light_is_only_partly_neutralised():
    img = np.full((40, 40, 3), [0.75, 0.55, 0.72], np.float32)  # a wall under magenta light
    r, g, b = grade.white_balance(img)
    assert -(np.log(r) + np.log(b)) / 2 <= grade.TINT_LIMIT + 1e-4  # green-magenta part capped at about 6%
