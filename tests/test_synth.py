"""Sound made in code: notes and cue times read the way the skill writes them, every cue type makes sound, and the
same cue list always gives the same file."""
import numpy as np
import pytest

from editor import synth


def test_note_names_become_their_frequencies():
    assert synth.freq("A4") == pytest.approx(440.0)
    assert synth.freq("A3") == pytest.approx(220.0)
    assert synth.freq("C#5") == pytest.approx(554.37, abs=0.01)
    assert synth.freq("Db5") == pytest.approx(synth.freq("C#5"))
    assert synth.freq(1300) == 1300.0
    with pytest.raises(ValueError, match="A4"):
        synth.freq("H2")


def test_cue_times_are_seconds_or_a_shot_with_an_offset():
    starts = {"s1": 0.0, "noon": 3.0}
    assert synth.resolve_at(2.5, starts) == 2.5
    assert synth.resolve_at("noon", starts) == 3.0
    assert synth.resolve_at("noon+0.25", starts) == 3.25
    assert synth.resolve_at("noon - 0.4", starts) == pytest.approx(2.6)
    with pytest.raises(ValueError, match="noon"):
        synth.resolve_at("dusk+1", starts)


@pytest.mark.parametrize("kind", sorted(set(synth.CUES) - {"file"}))
def test_every_cue_type_makes_a_clean_sound(kind):
    x = synth.CUES[kind]({"dur": 1.0}, np.random.default_rng(1))
    assert len(x) > 0 and np.all(np.isfinite(x))
    assert np.max(np.abs(x)) > 1e-3


def test_a_mix_is_exactly_the_film_long_stereo_and_never_clips():
    spec = {"seed": 3, "reverb": 0.3, "cues": [
        {"type": "pad", "at": 0, "dur": 4, "notes": ["A3", "E4"], "gain": -6},
        {"type": "impact", "at": "s2", "gain": 0},
        {"type": "chime", "at": "s2+0.3", "gain": 0, "pan": 1},
        {"type": "whoosh", "at": 3.8, "dur": 1.0, "gain": 0},  # runs past the end: trimmed
    ]}
    x = synth.render(spec, 4.0, {"s1": 0.0, "s2": 2.0})
    assert x.shape == (4 * synth.SR, 2)
    assert np.max(np.abs(x)) <= 1.0
    after = x[int(2.31 * synth.SR):int(2.5 * synth.SR)]
    assert np.abs(after[:, 1]).mean() > np.abs(after[:, 0]).mean()  # the chime is panned right


def test_the_same_cues_always_give_the_same_sound():
    spec = {"seed": 9, "cues": [{"type": "wash", "at": 0, "dur": 2}, {"type": "arp", "at": 0, "dur": 2}]}
    assert np.array_equal(synth.render(spec, 2.0), synth.render(spec, 2.0))


def test_a_bad_cue_says_what_is_wrong():
    with pytest.raises(ValueError, match="unknown type 'boom'"):
        synth.render({"cues": [{"type": "boom"}]}, 1.0)
    with pytest.raises(ValueError, match="needs a dur"):
        synth.render({"cues": [{"type": "pad"}]}, 1.0)
