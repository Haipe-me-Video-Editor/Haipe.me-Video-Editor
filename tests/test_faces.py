from editor import faces


def test_head_band_follows_zoom_and_only_the_graphic_span():
    data = {"source": [1080, 1920], "samples": [
        {"t": 1.0, "box": [0.3, 0.2, 0.7, 0.5]}, {"t": 6.0, "box": [0.3, 0.6, 0.7, 0.9]}]}
    segs = [{"src": "a", "in": 0.0, "out": 3.0, "zoom": 1.0}, {"src": "a", "in": 5.0, "out": 8.0, "zoom": 1.5}]
    assert faces.head_band(data, segs, 0.0, 2.0, (1080, 1920)) == (0.2, 0.5)
    top, bottom = faces.head_band(data, segs, 3.5, 2.0, (1080, 1920))  # source 5.5-7.5, zoom 1.5
    assert round(top, 3) == round((0.6 * 1.5 - 0.25), 3) and bottom == 1.0
    assert faces.head_band(data, segs, 3.0, 0.2, (1080, 1920)) is None  # source 5.0-5.2: no sample
