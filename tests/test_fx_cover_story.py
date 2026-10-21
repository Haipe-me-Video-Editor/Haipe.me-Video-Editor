import os
from pathlib import Path

import numpy as np
import pytest

from editor.fx import _behind as B
from editor.fx import cover_story as C
from editor.fx import registry

W, H = 1080, 1920
CLOSE = {"top": 170.0, "left": 200.0, "right": 820.0, "cx": 500.0, "eye_y": 560.0, "fw": 500.0, "chin": 1000.0}
WIDE = {"top": 820.0, "left": 450.0, "right": 630.0, "cx": 540.0, "eye_y": 930.0, "fw": 150.0, "chin": 1050.0}


def test_registered_with_params():
    assert registry()["cover_story"] is C and {"masthead", "lines", "issue", "backdrop"} <= set(C.PARAMS)


def test_close_up_goes_studio_and_drops_the_crown_into_the_masthead():
    cap = H * 0.118
    p = C.plan(W, H, CLOSE, "auto", cap)
    assert p["studio"] and p["dy"] > 0
    crown = CLOSE["top"] + p["dy"]
    assert p["mast_top"] < crown < p["mast_top"] + cap  # the head overlaps the masthead
    assert p["mast_top"] >= B.SAFE[1] * H


def test_wide_shot_keeps_the_room():
    p = C.plan(W, H, WIDE, "auto", H * 0.118)
    assert not p["studio"] and p["dy"] == 0 and p["mast_top"] + H * 0.118 > WIDE["top"]
    assert C.plan(W, H, CLOSE, "room", H * 0.118)["studio"] is False


def test_every_style_has_a_look_and_a_style_can_override_it():
    lk = C.look({"name": "x", "bg": "#101010", "accent": "#ff8800"})
    assert all(k in lk for k in ("centre", "edge", "mast", "kick_bg", "kick_fg", "line")) and lk["mast"] == "#ff8800"
    assert C.look({"accent": "#ff8800", "cover_story": {"mast": "#000000"}})["mast"] == "#000000"


def test_masthead_squeezes_to_fit_and_keeps_its_height():
    f = B.serif_font()
    if f is None:
        pytest.skip("no system serif")
    letters, (w, _h), asc = C.masthead_sprites("PLATFORM", f, 220, 900)
    assert w <= 901 and len(letters) == 8 and asc >= 0.75 * 220  # squeezed, then shrunk a little
    short, (w2, _), _ = C.masthead_sprites("EDIT", f, 220, 900)
    assert w2 < 900 and len(short) == 4


def test_barcode_is_deterministic():
    a, b = C.barcode_svg("No. 7", 170, 74, "#000"), C.barcode_svg("No. 7", 170, 74, "#000")
    assert a == b and a.count("<rect") > 20 and a != C.barcode_svg("No. 8", 170, 74, "#000")


def test_issue_line_never_sits_on_the_head():
    lay = C.issue_layout("THE MARKETS WEEKLY · OCT 2026", W, CLOSE, 500)
    assert lay["issue_parts"] == ["OCT 2026"] and lay["issue_side"] == "left"
    assert C.issue_layout("A · B", W, {**CLOSE, "cx": 540, "fw": 1100}, 500)["issue_parts"] == []


def test_solid_body_fills_holes_below_the_chin_only():
    m = np.zeros((400, 200), np.float32)
    m[100:, 40:160] = 1
    m[250:300, 80:120] = 0.1  # a see-through patch in the shirt
    m[60:80, 90:110] = 1      # something above the chin stays as it is
    out = C.solid_body(m, 150)
    assert out[275, 100] > 0.9 and out[120, 10] == 0 and out[70, 95] == 1 and out[30, 100] == 0


SRC = Path(os.environ.get("FX_TEST_CLIP", "/nonexistent"))


@pytest.mark.slow
@pytest.mark.skipif(not SRC.exists(), reason="set FX_TEST_CLIP to a 9:16 talking-head clip")
def test_renders_exact_frames(tmp_path):
    from editor import ffmpeg
    from editor.fx.apply import apply_fx
    out = apply_fx(SRC, [{"type": "cover_story", "at": 1.0, "dur": 2.0, "masthead": "EDIT", "lines": ["One"]}],
                   tmp_path, {"name": "acme"})
    assert abs(ffmpeg.probe(out)["duration"] - ffmpeg.probe(SRC)["duration"]) < 0.1
