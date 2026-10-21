from editor import color


def test_hdr_is_detected_from_the_transfer():
    assert color.is_hdr({"transfer": "arib-std-b67"}) and color.is_hdr({"transfer": "smpte2084"})
    assert not color.is_hdr({"transfer": "bt709"}) and not color.is_hdr({})


def test_rgb_conversions_name_the_bt709_matrix():
    assert "matrixin=709" in color.RGB_IN and "matrix=709:range=limited" in color.RGB_OUT and "gbrap" in color.RGBA_OUT
    assert color.TAGS[color.TAGS.index("-colorspace") + 1] == "bt709"
    assert "tonemap=tonemap=mobius" in color.SDR_CHAIN and color.SDR_CHAIN.endswith("format=yuv420p")
