"""The look effects: outline, color_pop, freeze_callout, motion_echo, film_look, beat_shake, glitch."""
import subprocess

import numpy as np
import pytest

from editor import ffmpeg
from editor.fx import _looks as L
from editor.fx import apply as fxapply
from editor.fx import beat_shake, color_pop, film_look, freeze_callout, glitch, motion_echo, outline, registry

NEW = ("outline", "color_pop", "freeze_callout", "motion_echo", "film_look", "beat_shake", "glitch")


def _scene(h=192, w=108):
    """A grey room with a red 'speaker' disc in the middle, and its matte."""
    F = np.full((h, w, 3), 0.5, np.float32)
    F[..., 2] = 0.8  # a blue-ish room
    yy, xx = np.mgrid[0:h, 0:w]
    a = (((yy - h * 0.55) / (h * 0.25)) ** 2 + ((xx - w / 2) / (w * 0.3)) ** 2 <= 1).astype(np.float32)
    F[a > 0] = (0.8, 0.1, 0.1)
    return F, a


def test_all_registered_with_params_and_docs():
    reg = registry()
    for name in NEW:
        mod = reg[name]
        assert mod.DOC and mod.PARAMS is not None and len(mod.DUR) == 2


def test_envelope_ramps_in_and_out():
    assert L.envelope(0, 2, 0.2, 0.2) == 0 and L.envelope(1, 2, 0.2, 0.2) == 1 and L.envelope(2, 2, 0.2, 0.2) == 0
    assert L.envelope(0, 2, 0, 0) == 1  # no ramps: on from the first frame to the last


def test_ring_sits_just_outside_the_matte():
    _, a = _scene()
    r = L.ring(a, 4, soft=0)
    assert r[a > 0].max() == 0 and r.max() == 1
    assert L.ring(a, 0.2).max() == 0


def test_background_modes_leave_the_speaker_alone():
    F, a = _scene()
    for mode in ("mono", "dim", "blur", "tint"):
        out = color_pop.frame(F, a, 1.0, mode, L.hex_rgb("#ff7a1a"))
        assert np.allclose(out[a > 0], F[a > 0])  # the speaker keeps their colour
        assert not np.allclose(out[a == 0], F[a == 0])  # the room changes
    mono = color_pop.frame(F, a, 1.0, "mono")
    room = mono[a == 0]
    assert np.allclose(room[:, 0], room[:, 2])  # grey
    with pytest.raises(ValueError):
        L.treat_bg(F, "sepia")


def test_outline_strokes_outside_in_the_chosen_colour():
    F, a = _scene()
    out = outline.frame(F, a, 1.0, "sticker", L.hex_rgb("#ffffff"), 4, 0.8, "keep")
    core = L.ring(a, 2, soft=0) > 0.99  # the stroke's inner half: its outer edge is softened on purpose
    assert np.allclose(out[core], 1.0, atol=0.05) and np.allclose(out[a > 0], F[a > 0])
    neon = outline.frame(F, a, 1.0, "neon", L.hex_rgb("#00ffff"), 6, 1.0, "dim")
    assert neon[a == 0][..., 1].max() > F[a == 0][..., 1].max() * 0.35  # glow lights the dimmed room
    assert np.array_equal(outline.frame(F, a, 0.0, "sticker", (1, 1, 1), 4, 0.8, "mono"), F)


def test_freeze_lifts_the_speaker_bigger_with_a_border():
    F, a = _scene()
    out = freeze_callout.lift_frame(F, a, (54, 105), 1.1, 1.0, "mono", 3)
    still_red = (out[..., 0] > 0.7) & (out[..., 1] < 0.2)
    assert still_red.sum() > (a > 0).sum()  # bigger than before, still in colour
    assert (out > 0.97).all(axis=2).any()  # the white border


def test_echoes_sit_behind_the_speaker_and_fade():
    F, a = _scene()
    ghost = np.zeros_like(a)
    ghost[10:40, 10:40] = 1
    col = np.zeros_like(F)
    col[..., 1] = 1  # a green ghost
    out = motion_echo.composite(F, a, [(col, ghost, 0.5)], 1.0)
    assert np.isclose(out[20, 20, 1], 0.75)  # 0.5 * green over 0.5 grey
    both = ghost.copy()
    both[:] = 1
    out = motion_echo.composite(F, a, [(col, both, 1.0)], 1.0)
    assert np.allclose(out[a > 0], F[a > 0])  # never over the speaker as they are now


def test_film_grade_lifts_blacks_and_halation_only_brightens():
    black = np.zeros((64, 36, 3), np.float32)
    assert film_look.grade(black, 0.4, 1.0).min() > 0.05
    F, _ = _scene()
    assert (film_look.halate(F, 1.0) >= F - 1e-6).all()
    v = film_look.vignette_mask(64, 36, 1.0)
    assert v[32, 18, 0] == 1 and v[0, 0, 0] < 0.6


def test_shake_only_around_hits_and_always_overscanned():
    dx, dy, rot, s, split = beat_shake.motion(1.0, [0.2], 0.5, 0.04, 1080)
    assert (dx, dy, rot) == (0, 0, 0) and s == beat_shake.OVERSCAN and split == 0
    dx, dy, rot, s, split = beat_shake.motion(0.25, [0.2], 0.5, 0.04, 1080)
    assert abs(dx) + abs(dy) > 0 and s > beat_shake.OVERSCAN and split > 0


def test_glitch_peaks_on_the_hit_and_keeps_the_frame_size():
    assert glitch.strength(0.5, 0.5, 0.2) == 1 and glitch.strength(0.8, 0.5, 0.2) == 0
    f = (np.random.default_rng(0).random((96, 54, 3)) * 255).astype(np.uint8)
    g = glitch.damage(f, 1.0, np.random.default_rng(1))
    assert g.shape == f.shape and not np.array_equal(g, f)
    assert np.array_equal(glitch.damage(f, 0.0, np.random.default_rng(1)), f)
    m = glitch.mosh(f, f, f, 0.5)
    assert m.shape == f.shape


def test_glitch_weak_edges_of_the_window_on_a_full_size_frame():
    # A 1920 px tall frame at strength 0.02-0.06 once gave a slice-height range with high < low.
    f = np.zeros((1920, 1080, 3), np.uint8)
    for k in (0.03, 0.045, 0.058):
        assert glitch.damage(f, k, np.random.default_rng(1)).shape == f.shape


@pytest.mark.slow
@pytest.mark.parametrize("spec", [{"type": "film_look", "leak": True}, {"type": "beat_shake", "hits": [0.1, 0.5]},
                                  {"type": "glitch", "mosh": True}])
def test_frame_only_looks_render_the_exact_window(tmp_path, spec):
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=216x384:r=30:d=2", "-pix_fmt",
                    "yuv420p", str(src)], check=True)
    out = fxapply.apply_fx(src, [{**spec, "at": 0.5, "dur": 1.0}], tmp_path / "w", {"name": "t"}, size=(216, 384),
                           fps=30)
    assert abs(ffmpeg.probe(out)["duration"] - 2.0) < 0.05


def test_noir_puts_a_grey_speaker_on_black_with_a_glow():
    from editor.fx import noir_minimal as nm
    F, a = _scene()
    out = nm.frame(F, a, 1.0, 0.8, True, 1.0, (0, 0, 0))
    inside = out[a > 0]
    assert np.allclose(inside[:, 0], inside[:, 1])  # black and white
    far = out[:8, :8]
    assert far.max() < 0.02  # the room is gone
    near = L.ring(a, 3, soft=0) > 0.5
    assert out[near].mean() > 0.05  # the halo hugs the silhouette
    assert nm.orb(192, 108, 0.5, 2.0).max() == 1


def test_line_art_shapes_are_closed_paths_with_lengths():
    from editor.fx import line_art as la
    for shape in la.SHAPES:
        ps = la.paths(shape, 100)
        assert ps and all(d.startswith("M") and ln > 0 for d, ln, _, _ in ps)
    circle = la.paths("circle", 100)[0][1]
    assert abs(circle - 2 * np.pi * 100) < 2
    with pytest.raises(ValueError):
        la.paths("teapot", 10)


def test_word_stack_groups_and_sizes():
    from editor.fx import word_stack as ws
    g = ws.groups([{"t": 0.5, "text": "b"}, {"t": 0.1, "text": "a"}, {"t": 1.0, "text": "c", "new": True}])
    assert [[w["text"] for w in x] for x in g] == [["a", "b"], ["c"]]
    assert len(ws.groups([{"t": i, "text": "w"} for i in range(4)])) == 2  # at most 3 lines a stack
    long, short = ws.size_for("transparent", "outline", 1080), ws.size_for("HOW", "bold", 1080)
    assert long < short <= 1080 * 0.25 and long * 11 * 0.66 <= 1080 * 0.85
    assert ws.font_for("gradient", False) == "InstrumentItalic" and ws.font_for("gradient", True) == "AmiriSerif"
    P = np.zeros((478, 2), np.float32)
    P[10], P[152] = (540, 760), (540, 1160)
    assert ws.stack_y(P, 1920) == 0.10  # headroom: high, the head over the last line
    P[10], P[152] = (540, 140), (540, 760)
    assert ws.stack_y(P, 1920) > 760 / 1920  # close-up: on the chest


def test_freeze_label_keeps_off_the_face():
    P = np.zeros((478, 2), np.float32)
    P[10], P[152] = (540, 700), (540, 1100)  # a medium shot: room above the head
    assert freeze_callout.label_y(P, 1920) < (700 - 0.45 * 400) / 1920
    P[10], P[152] = (540, 120), (540, 760)  # a close-up: no room above, so under the chin
    assert freeze_callout.label_y(P, 1920) > 760 / 1920
    assert freeze_callout.label_y(None, 1920) == 0.13
