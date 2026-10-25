"""Picking the right take from a long raw: voices, retakes, stumbles, tight spans and the selects time map."""
import numpy as np

from editor import takes as T


def W(text, start, step=0.4, gap=0.05, lv=None):
    """Words of `text` from `start`, each `step` long with `gap` between them."""
    out, t = [], start
    for w in text.split():
        out.append({"w": w, "start": round(t, 3), "end": round(t + step - gap, 3), **({"lv": lv} if lv else {})})
        t += step
    return out


def test_norm_folds_spelling_variants_and_keeps_digits():
    assert T.norm("أَصْلـ") == T.norm("اصل")
    assert T.norm("القيمة،") == T.norm("القيمه")
    assert T.norm("١٠٠$") == "100"


def test_asr_loops_are_cut_down():
    words = W("والفرق " * 12 + "يغير", 0.0)
    assert [w["w"] for w in T.drop_loops(words)] == ["والفرق"] * 3 + ["يغير"]


def test_two_voices_split_by_level_per_phrase():
    words = W("يعني بتدفع القيمة الكاملة", 0.0) + W("اوكي تاني", 3.0) + W("للكمية اللي انت اخترتها", 5.0)
    levels = [-12.0] * 4 + [-24.0, -23.0] + [-13.0] * 4
    T.mark_speaker(words, levels)
    assert [w["off"] for w in words] == [False] * 4 + [True] * 2 + [False] * 4


def test_one_voice_has_no_split():
    assert T.split_level([-12.0, -13.5, -11.0, -14.0] * 5) is None


def test_the_last_complete_take_wins_and_chatter_goes():
    words = (W("يعني بتدفع", 0.0) + W("يعني بتدفع القيمة كاملة للكمية", 2.0) + W("اوكي", 6.0)
             + W("يعني بتدفع القيمة الكاملة للكمية اللي انت اخترتها", 8.0))
    us = T.units(words)  # the lone "okay" is trimmed away entirely
    v = T.pick(us)
    assert [x["keep"] for x in v] == [False, False, True]
    assert v[0]["why"] == "chatter" and v[1]["why"] == "earlier take"


def test_words_to_the_crew_come_off_a_take_and_mark_talk_inside_it():
    take = W("والفرق يغير كل شيء في قرارك حلو ممتاز", 0.0)
    assert [w["w"] for w in T.trim_talk(take)][-1] == "قرارك"
    assert T.is_chatter(W("يبقى اوكي يعني انا قلت هنا", 0.0))


def test_off_camera_voice_is_never_kept():
    words = W("خلينا نعيدها من الاول", 0.0) + W("سبعة من كل عشر متداولين", 3.0)
    for w in words[:4]:
        w["off"] = True
    v = T.pick(T.units(words))
    assert [x["keep"] for x in v] == [False, True] and v[0]["why"] == "off-camera voice"


def test_a_stumble_after_a_good_take_goes():
    words = W("والعقد ده تقدر تستخدمه للمضاربة او التحوط", 0.0) + W("للمضاربة او التحوط", 4.0)
    v = T.pick(T.units(words))
    assert [x["keep"] for x in v] == [True, False]


def test_new_lines_that_share_a_word_are_both_kept():
    words = W("اما في المشتقات انت ما بتشتري الاصل", 0.0) + W("من مزايا المشتقات مرونة اكبر", 4.0)
    assert [x["keep"] for x in T.pick(T.units(words))] == [True, True]


def test_spans_are_tight_and_long_pauses_inside_are_cut():
    words = W("هنا الفرق", 1.0) + W("الحقيقي مش حجم", 2.2)  # 0.45 s pause between the two runs
    us = [words]
    sp = T.spans(us, [{"keep": True}])
    assert sp == [[0.95, 1.85], [2.15, 3.45]]


def test_overrides_by_unit_number():
    v = T.apply_overrides([{"keep": True}, {"keep": False}], keep=[1], drop=[0])
    assert [x["keep"] for x in v] == [False, True]


def test_selects_plan_merges_overlaps_and_maps_time():
    pieces = T.selects_plan([[10.0, 12.0], [12.5, 14.0], [100.0, 101.0]], handle=0.4)
    assert pieces == [{"in": 9.6, "out": 14.4, "at": 0.0}, {"in": 99.6, "out": 101.4, "at": 4.8}]
    assert T.to_selects(pieces, 100.0) == 5.2


def test_speech_chunks_split_at_pauses_and_cap_length():
    db = np.full(6000, -80.0)
    db[100:900] = -20.0       # 1-9 s
    db[1000:4500] = -20.0     # 10-45 s: longer than max_len, kept whole as one region
    ch = T.speech_chunks(db, max_len=25.0)
    assert ch[0] == [0.85, 9.15] and len(ch) == 2


def test_lens_pose_is_the_held_pose():
    rows = [{"t": i * 0.5, "yaw": 2.0, "pitch": -5.0} for i in range(40)] + \
           [{"t": 20 + i * 0.5, "yaw": 35.0, "pitch": -2.0} for i in range(10)]
    ref = T.lens_pose(rows)
    assert abs(ref[0] - 2.0) < 1 and abs(ref[1] + 5.0) < 1
    assert T.lens_share(rows, 0, 10, ref) == 1.0 and T.lens_share(rows, 20, 24, ref) == 0.0
