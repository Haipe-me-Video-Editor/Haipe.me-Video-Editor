from editor.pack import pack


def test_pack_breaks_on_gaps_and_sentences(words):
    out = pack(words).splitlines()
    assert out[0].startswith("[0000.50-") and out[0].endswith("So um today we launch.")
    assert any(line.endswith("Thanks.") for line in out)
