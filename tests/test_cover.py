"""Covers: the frame is chosen for a real expression, the colours set the speaker apart, and every design passes the
readability and safe-zone checks at each platform size."""
import numpy as np
import pytest
from PIL import Image

from editor import cover as cv


def _person(W=1080, H=1920, cut=False):
    """A red-shirted figure: a round head on a body that reaches the frame bottom (and both sides, with cut)."""
    yy, xx = np.mgrid[:H, :W]
    head = ((xx - W / 2) / (W * 0.16)) ** 2 + ((yy - H * 0.35) / (H * 0.11)) ** 2 < 1
    x0, x1 = (0, W) if cut else (W * 0.22, W * 0.78)
    body = (yy > H * 0.45) & (xx >= x0) & (xx < x1)
    alpha = (head | body).astype(np.float32)
    rgb = np.zeros((H, W, 3), np.uint8)
    rgb[head] = (205, 160, 130)
    rgb[body] = (170, 25, 35)
    return rgb, alpha


def test_a_real_expression_beats_a_mid_word_mouth_and_a_blink():
    smile = cv.expression_score({"mouthSmileLeft": 0.7, "mouthSmileRight": 0.7, "jawOpen": 0.2})
    mid_word = cv.expression_score({"jawOpen": 0.35})
    blink = cv.expression_score({"mouthSmileLeft": 0.7, "mouthSmileRight": 0.7, "eyeBlinkLeft": 0.9,
                                 "eyeBlinkRight": 0.9})
    away = cv.expression_score({"mouthSmileLeft": 0.7, "mouthSmileRight": 0.7, "eyeLookOutLeft": 0.9})
    assert smile > cv.expression_score({}) > mid_word
    assert smile > blink and smile > away


def test_pick_spreads_the_frames_out():
    rows = [{"t": 10.0}, {"t": 10.5}, {"t": 11.0}, {"t": 14.0}, {"t": 30.0}]
    assert [r["t"] for r in cv.pick(rows, k=3, gap=2.0)] == [10.0, 14.0, 30.0]


def test_the_background_is_set_against_the_speaker():
    rgb, alpha = _person()
    pal = cv.palette(rgb, alpha)
    h_shirt = cv.dominant_hue(rgb, alpha)
    import colorsys
    h_bg = colorsys.rgb_to_hsv(*(c / 255 for c in pal["bg1"]))[0]
    assert 0.35 < abs(h_bg - h_shirt) < 0.65  # the far side of the colour wheel
    brand = cv.palette(rgb, alpha, accent="#ff3366", bg="#102030")
    assert brand["accent"] == (255, 51, 102) and brand["bg1"] == (16, 32, 48)  # a brand keeps its colours


def test_contrast_and_luminance():
    assert cv.contrast((255, 255, 255), (0, 0, 0)) == pytest.approx(21, abs=0.1)
    assert cv.contrast((255, 255, 255), (255, 255, 255)) == pytest.approx(1)


def test_headline_lines_and_accent():
    assert cv.lines_for("20 years in one repo") == ["20 years", "in one repo"]
    assert cv.lines_for("one") == ["one"]
    assert cv.auto_accent("20 years in one repo", []) == ["20"]
    assert cv.auto_accent("٢٠ سنة في ريبو", []) == ["٢٠"]  # Arabic digits too
    assert cv.auto_accent("one repo", []) == [] and cv.auto_accent("one repo", ["repo"]) == ["repo"]
    assert cv.is_arabic("سنة") and not cv.is_arabic("year")


def test_cut_sides_finds_a_body_cut_by_the_frame():
    assert cv.cut_sides(_person(540, 960, cut=True)[1]) == {"left", "right"}
    assert cv.cut_sides(_person(540, 960)[1]) == {"left", "right"}  # a straight-sided box shirt reads as cut too
    yy, xx = np.mgrid[:960, :540]
    blob = ((((xx - 270) / 200) ** 2 + ((yy - 600) / 360) ** 2) < 1).astype(np.float32)
    assert cv.cut_sides(blob) == set()  # a natural, rounded silhouette is not


@pytest.mark.parametrize("size", ["reel", "youtube", "square"])
@pytest.mark.parametrize("layout", ["punch", "frame", "minimal", "object"])
def test_every_design_passes_its_checks(tmp_path, layout, size):
    rgb, alpha = _person(cut=True)
    frame = np.full((1920, 1080, 3), 60, np.uint8)
    card = tmp_path / "card.png"
    Image.new("RGB", (400, 700), (240, 240, 240)).save(card)
    pal = cv.palette(rgb, alpha)
    img, info = cv.compose(layout, size, (rgb, alpha), frame, "20 years in one repo", [], "Haipe.me", pal,
                           image=card if layout == "object" else None)
    assert img.size == cv.SIZES[size]
    assert cv.check(img, info) == []


def test_arabic_headline_passes_on_a_wide_thumbnail():
    rgb, alpha = _person(cut=True)
    img, info = cv.compose("punch", "youtube", (rgb, alpha), None, "٢٠ سنة في ريبو", [], "", cv.palette(rgb, alpha))
    assert cv.check(img, info) == []
    assert info["text_box"][0] > img.width * 0.45  # an Arabic headline reads from the right


def test_check_catches_the_rules():
    img = Image.new("RGB", (1080, 1920), (40, 90, 120))
    base = {"size": "reel", "title": "20 years in one repo", "cap": 120, "text_box": (200, 300, 700, 600)}
    assert cv.check(img, base) == []
    assert any("words" in p for p in cv.check(img, {**base, "title": "one two three four five six"}))
    assert any("Arabic" in p for p in cv.check(img, {**base, "title": "واحد اثنين ثلاثة أربعة خمسة"}))
    assert any("too small" in p for p in cv.check(img, {**base, "cap": 40}))
    assert any("safe zone" in p for p in cv.check(img, {**base, "text_box": (20, 300, 700, 600)}))
    assert any("face" in p for p in cv.check(img, base, face_h=0.05))
    assert any("repeats" in p for p in cv.check(img, base, video_title="20 years in one repo, finally"))
    white = Image.new("RGB", (1080, 1920), (250, 250, 250))
    assert any("melt" in p for p in cv.check(white, base))
    yt = Image.new("RGB", (1920, 1080), (40, 90, 120))
    under_badge = {"size": "youtube", "title": "20 years", "cap": 160, "text_box": (1600, 950, 1840, 1040)}
    assert any("badge" in p for p in cv.check(yt, under_badge))


def test_save_stays_under_the_limit(tmp_path):
    noise = Image.fromarray(np.random.default_rng(0).integers(0, 255, (1080, 1920, 3), np.uint8))
    p = cv.save(noise, tmp_path / "c.jpg", max_bytes=1_000_000)
    assert p.stat().st_size <= 1_000_000
    with pytest.raises(ValueError):  # never a file the platform will refuse
        cv.save(noise, tmp_path / "d.jpg", max_bytes=50_000)
