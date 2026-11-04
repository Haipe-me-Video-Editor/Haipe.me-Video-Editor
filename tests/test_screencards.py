import json

import numpy as np
import pytest
from PIL import Image

from editor import screencards

# Low captions: a style with these settings rendered two caption lines at y 1361-1497 on a 1080x1920 frame.
STYLE = {"caption_margin_v": 0.22, "caption_size": 0.072, "accent": "#33ccff"}


def _spec(tmp_path, cards):
    Image.new("RGB", (1170, 2532), (240, 242, 246)).save(tmp_path / "screen.png")  # a 390x844 capture at 3x
    for c in cards:
        c.setdefault("image", "screen.png")
    (tmp_path / "screens.json").write_text(json.dumps({"label": "Sample data shown.", "dpr": 3, "cards": cards}))
    return tmp_path / "screens.json"


def _font():
    from editor.fonts import ensure_font
    return str(ensure_font("Sora Light"))


def test_cards_end_above_two_lines_of_captions():
    top, bottom = screencards.card_area(STYLE)
    assert top == 285 and 1290 < bottom < 1361 - 30


def test_overlapping_cards_and_crops_outside_the_capture_are_refused(tmp_path):
    path = _spec(tmp_path, [{"at": 1, "end": 3, "crop": [0, 0, 390, 600]},
                            {"at": 2.5, "end": 4, "crop": [0, 0, 390, 900]}])
    with pytest.raises(ValueError) as e:
        screencards.load(path)
    assert "overlaps" in str(e.value) and "outside" in str(e.value)


@pytest.mark.slow
def test_frame_is_untouched_outside_a_card_and_carded_inside(tmp_path):
    path = _spec(tmp_path, [{"at": 1, "end": 3, "crop": [0, 0, 390, 600], "ring": [20, 100, 370, 160]}])
    comp = screencards.Compositor(screencards.load(path), STYLE, _font())
    f = np.random.default_rng(0).integers(0, 255, (1920, 1080, 3), dtype=np.uint8)
    assert comp.frame(f, 0.5) is f and comp.frame(f, 3.6) is f
    out = comp.frame(f, 2.0)
    top, bottom = comp.area
    mid = out[(top + bottom) // 2, 540]
    assert abs(int(mid.mean()) - 242) < 6  # the light screen, not the noisy speaker
    assert out[1800].std() < f[1800].std() / 3  # the speaker below is blurred
