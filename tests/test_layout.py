from editor import layout

STYLE = {"caption_size": 0.072, "hook_scale": 1.4, "caption_margin_v": 0.30}
SIZE = (1080, 1920)


def _plan(mode="bilingual"):
    return {"segments": [{"src": "raw/a.mp4", "in": 0.0, "out": 10.0, "zoom": 1.0}],
            "captions": {"enabled": True, "mode": mode}}


def _faces(y0, y1):
    return {"source": [1080, 1920], "samples": [{"t": t / 2, "box": [0.2, y0, 0.8, y1]} for t in range(20)]}


def test_card_goes_below_the_captions_when_the_head_fills_the_top():
    spec = {"type": "quote", "text": "We learn, we move on.", "at": 2.0, "dur": 2.0}
    slot = layout.place(spec, _plan(), _faces(0.05, 0.60), STYLE, SIZE)
    c0, c1 = layout.caption_band(STYLE, SIZE, "bilingual")
    assert slot["top"] >= c1 and slot["top"] + slot["height"] <= layout.SAFE_BOTTOM + 1e-9
    assert layout.MIN_SCALE <= slot["scale"] < 1.0 and "note" not in slot  # two lines, shrunk to fit


def test_card_goes_above_a_low_head_and_stays_in_the_safe_zone():
    spec = {"type": "hook", "text": "Big news", "at": 0.5, "dur": 2.0}
    slot = layout.place(spec, _plan(), _faces(0.40, 0.58), STYLE, SIZE)
    assert slot["top"] == layout.SAFE_TOP and slot["top"] + slot["height"] <= 0.40


def test_a_long_list_in_a_small_gap_is_scaled_and_flagged():
    spec = {"type": "list", "items": ["one thing", "another thing", "a third thing"], "at": 1.0, "dur": 3.0}
    slot = layout.place(spec, _plan(), _faces(0.05, 0.60), STYLE, SIZE)
    assert slot["scale"] < layout.MIN_SCALE and "cramped" in slot["note"]


def test_no_face_data_assumes_a_talking_head():
    spec = {"type": "quote", "text": "Hi", "at": 1.0, "dur": 1.0}
    slot = layout.place(spec, _plan(), None, STYLE, SIZE)
    assert slot["top"] >= layout.ASSUMED_HEAD[1]


def test_fixed_cards_take_no_free_space_and_new_cards_fit():
    for t in ("credit", "chapter", "outro"):
        slot = layout.place({"type": t, "text": "x", "at": 1.0, "dur": 2.0}, _plan(), _faces(0.1, 0.6), STYLE, SIZE)
        assert slot["scale"] == 1.0 and "note" not in slot
    for spec in ({"type": "ticker", "name": "Bitcoin", "ticker": "BTC"},
                 {"type": "headline", "text": "Oil hits record", "source": "Reuters"},
                 {"type": "kinetic", "text": "Oil to $150"}):
        assert layout.card_height_vmin(spec, 70) > 0
        slot = layout.place({**spec, "at": 1.0, "dur": 2.0}, _plan(), _faces(0.1, 0.5), STYLE, SIZE)
        assert "note" not in slot
