import subprocess
import types

import numpy as np

from editor import ffmpeg
from editor.fx import apply as fxapply
from editor.fx import registry


def _dummy():
    def render(ctx):
        with ctx.writer() as w:
            for f in ctx.frames():
                w(255 - f)  # invert: easy to see where the window went
        return ctx.out
    return types.SimpleNamespace(NAME="invert", DOC="test", PARAMS={}, DUR=(0.5, 10), render=render,
                                 __file__=fxapply.__file__)


def test_registry_finds_effect_modules():
    reg = registry()
    assert "wall_text" in reg and all(hasattr(m, "PARAMS") and hasattr(m, "DOC") for m in reg.values())


def test_check_flags_unknown_types_fields_overlaps_and_bounds(monkeypatch):
    monkeypatch.setattr(fxapply, "registry", lambda: {"invert": _dummy()})
    errs = "\n".join(fxapply.check([{"type": "nope", "at": 0, "dur": 1},
                                    {"type": "invert", "at": 1, "dur": 2, "colour": "x"},
                                    {"type": "invert", "at": 2.5, "dur": 1},
                                    {"type": "invert", "at": 9, "dur": 2}], total=10))
    assert "unknown type" in errs and "unknown field" in errs and "overlaps" in errs and "after the video" in errs


def test_apply_replaces_exactly_the_window(tmp_path, monkeypatch):
    monkeypatch.setattr(fxapply, "registry", lambda: {"invert": _dummy()})
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x202020:s=108x192:r=30:d=4",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    out = fxapply.apply_fx(src, [{"type": "invert", "at": 1.0, "dur": 1.0}], tmp_path / "w", {"name": "t"},
                           size=(108, 192), fps=30)
    assert abs(ffmpeg.probe(out)["duration"] - 4.0) < 0.05
    raw = ffmpeg.run_bytes(["-i", str(out), "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    frames = np.frombuffer(raw, np.uint8).reshape(-1, 192, 108).mean(axis=(1, 2))
    bright = np.where(frames > 128)[0]
    assert bright[0] == 30 and bright[-1] == 59  # frames 30-59: exactly the 1.0-2.0 s window


def test_effects_that_recolour_the_footage_are_refused():
    from editor.fx.apply import check
    bad = [{"type": "film_look", "at": 0, "dur": 2}, {"type": "color_pop", "at": 3, "dur": 2},
           {"type": "noir_minimal", "at": 6, "dur": 2}, {"type": "glitch", "at": 9, "dur": 1},
           {"type": "freeze_callout", "at": 11, "dur": 2, "bg": "mono"},
           {"type": "outline", "at": 14, "dur": 2, "bg": "mono"}, {"type": "beat_shake", "at": 17, "dur": 2, "split": True}]
    errs = check(bad)
    assert sum("colour" in e for e in errs) == 7
    ok = [{"type": "freeze_callout", "at": 0, "dur": 2}, {"type": "outline", "at": 3, "dur": 2},
          {"type": "beat_shake", "at": 6, "dur": 2}]
    assert not any("colour" in e for e in check(ok))
