"""Tight sentence cuts, hiss tails, per-shot framing and the source->timeline map."""
import numpy as np

from editor import tightcut as T


def energy(spans, total=10.0):
    """10 ms dB frames: -20 dB inside the given speech spans, -80 dB elsewhere."""
    e = np.full(int(total * 100), -80.0)
    for a, b in spans:
        e[int(a * 100):int(b * 100)] = -20.0
    return e


def test_phrases_merge_short_gaps_and_keep_long_ones():
    ph = T.phrases_from_energy(energy([(0.5, 1.5), (1.6, 2.5), (3.5, 4.5)]))
    assert ph == [[0.5, 2.5], [3.5, 4.5]]


def test_long_pauses_are_cut_tight_and_breaths_stay():
    phrases = [[0.5, 2.0], [2.3, 3.0], [4.0, 5.0]]  # 0.3 s breath, then a 1.0 s pause
    spans, nominal = T.cut_spans(phrases, 0.0, 10.0, end_hold=0.0)
    assert spans == [[0.0, 3.1], [3.95, 5.1]] and nominal == {}


def test_a_short_pause_that_ends_a_sentence_is_cut_when_named():
    phrases = [[0.5, 2.0], [2.3, 3.0]]
    spans, _ = T.cut_spans(phrases, 0.0, 10.0, cut_pauses=[2.0], end_hold=0.0)
    assert spans == [[0.0, 2.1], [2.25, 3.1]]


def test_own_cuts_are_kept_as_cut_points():
    spans, _ = T.cut_spans([[0.5, 3.0]], 0.0, 10.0, keep_cuts=[1.7], end_hold=0.0)
    assert spans == [[0.0, 1.7], [1.7, 3.1]]


def test_hiss_tail_extends_the_out_point_and_can_be_capped():
    hf = np.full(1000, -80.0)
    hf[310:322] = -40.0  # hiss runs 0.12 s past the out point (word end 3.0 + POST = 3.1)
    phrases = [[0.5, 3.0], [5.0, 6.0]]
    spans, nominal = T.cut_spans(phrases, 0.0, 10.0, hf=hf, end_hold=0.0)
    assert spans[0][1] == 3.26 and nominal == {3.1: 3.26}  # 0.12 s of hiss + 40 ms
    capped, _ = T.cut_spans(phrases, 0.0, 10.0, hf=hf, tail_caps={3.1: 0.05}, end_hold=0.0)
    assert capped[0][1] == 3.15


def test_the_last_word_is_held_before_the_end_card():
    spans, _ = T.cut_spans([[0.5, 3.0]], 0.0, 10.0)
    assert spans[-1][1] == round(3.1 + T.END_HOLD, 3)


def test_timemap_maps_source_to_timeline():
    m = T.TimeMap([[0.0, 3.0], [4.0, 6.0]], {"2.9": 3.0})
    assert m.M(1.0) == 1.0
    assert m.M(3.5) == 3.0  # inside a removed pause: the next kept frame
    assert m.M(5.0) == 4.0
    assert m.M(2.9) == 3.0  # a nominal out point lands on its extended edge
    assert m.total == 5.0


def test_framing_puts_the_face_at_the_reference_size_and_alternates_a_punch_in():
    rows = [{"t": t / 5, "fw": 0.2, "cx": 0.55, "top": 0.17} for t in range(50)]
    z, (fx, fy) = T.frame_shot(rows, 0.0, 5.0, tight=False)
    assert abs(z - T.FACE_W / 0.2) < 0.01
    assert abs((0.17 - fy) * z + 0.5 - T.HEADROOM) < 0.01  # hair top lands HEADROOM below the frame top
    assert abs((0.55 - fx) * z + 0.5 - T.FACE_X) < 0.01  # face centre lands at FACE_X
    zt, _ = T.frame_shot(rows, 0.0, 5.0, tight=True)
    assert abs(zt / z - T.PUNCH) < 0.01


def test_pause_report_lists_kept_pauses_with_their_words():
    words = [[1.5, 2.0, "الخطة"], [2.3, 2.6, "هنا"]]
    rows = T.pause_report([[0.5, 2.0], [2.3, 3.0]], words, 0.0, 10.0)
    assert rows == [{"at": 2.0, "gap": 0.3, "before": "الخطة", "after": "هنا"}]
