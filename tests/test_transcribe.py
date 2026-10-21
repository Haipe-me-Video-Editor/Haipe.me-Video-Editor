from types import SimpleNamespace as NS

import pytest

from editor import transcribe as tx


class FakeWhisper:
    def __init__(self, lang="en"):
        self.lang, self.calls = lang, []

    def transcribe(self, path, **kw):
        self.calls.append(kw)
        seg = NS(words=[NS(word=" Hello", start=0.1, end=0.42), NS(word=" Acme.", start=0.5, end=0.9)])
        return iter([seg]), NS(language=self.lang)


def fake_align(wav, segments, language):
    return [{"w": "Hello", "start": 0.12, "end": 0.40}, {"w": "Acme.", "start": 0.52, "end": 0.88}]


def test_glossary_file_skips_comments(tmp_path):
    (tmp_path / "g.txt").write_text("# names\nAcme\n\nZed Town\n")
    assert tx.load_glossary(tmp_path / "g.txt") == ["Acme", "Zed Town"]
    assert tx.load_glossary() == []  # the built-in list is empty: brands bring their own


def test_interpolate_fills_missing_times():
    ws = [{"w": "a", "start": 0.0, "end": 0.2}, {"w": "b", "start": None, "end": None},
          {"w": "c", "start": None, "end": None}, {"w": "d", "start": 1.0, "end": 1.2}]
    out = tx.interpolate(ws)
    assert [w["start"] for w in out] == pytest.approx([0.0, 0.2, 0.6, 1.0])
    assert all(a["end"] <= b["start"] + 1e-9 for a, b in zip(out, out[1:]))


def test_english_uses_whisper_with_glossary_then_alignment(talking_clip, tmp_path):
    model = FakeWhisper("en")
    out = tx.transcribe(talking_clip, tmp_path, language="en", glossary=["Acme"], whisper_model=model,
                        aligner=fake_align)
    assert out["error"] is None and out["engine"] == "whisper+align"
    kw = model.calls[-1]
    assert "Acme" in kw["hotwords"] and kw["condition_on_previous_text"] is False
    assert kw["language"] == "en" and kw["vad_filter"] is True
    assert kw["word_timestamps"] is True
    assert kw["hallucination_silence_threshold"] == 2.0 and kw["beam_size"] == 5
    assert out["words"][1]["start"] == 0.52


def test_arabic_prefers_the_second_engine(talking_clip, tmp_path):
    extra_segs = [{"start": 0.0, "end": 1.0, "text": "مرحبا"}]
    received = []

    def recording_align(wav, segments, language):
        received.append(segments)
        return fake_align(wav, segments, language)

    model = FakeWhisper("ar")
    out = tx.transcribe(talking_clip, tmp_path, language="ar", whisper_model=model,
                        aligner=recording_align, arabic=("extra", lambda wav, wd: extra_segs))
    assert out["engine"] == "extra+align" and out["notes"] == []
    assert received == [extra_segs]
    assert model.calls == []


def test_arabic_falls_back_to_whisper_when_the_second_engine_fails(talking_clip, tmp_path):
    def broken(wav, wd):
        raise RuntimeError("venv missing")
    out = tx.transcribe(talking_clip, tmp_path, language="ar", whisper_model=FakeWhisper("ar"),
                        aligner=fake_align, arabic=("extra", broken))
    assert out["engine"] == "whisper+align" and "extra unavailable" in out["notes"][0]


def test_arabic_whisper_fallback_gets_no_latin_hotwords(talking_clip, tmp_path):
    def broken(wav, wd):
        raise RuntimeError("venv missing")
    model = FakeWhisper("ar")
    tx.transcribe(talking_clip, tmp_path, language="ar", glossary=["Acme", "Zed Town", "أكمي"],
                  whisper_model=model, aligner=fake_align, arabic=("extra", broken))
    assert model.calls[-1]["language"] == "ar"
    assert model.calls[-1]["hotwords"] == "أكمي"


def test_auto_detects_language(talking_clip, tmp_path):
    out = tx.transcribe(talking_clip, tmp_path, whisper_model=FakeWhisper("en"), aligner=fake_align)
    assert out["language"] == "en"


def test_failure_returns_error(tmp_path):
    out = tx.transcribe(tmp_path / "missing.mp4", tmp_path, language="en", whisper_model=FakeWhisper())
    assert out["words"] is None and out["error"]


def test_interpolate_overlap_never_ends_before_start():
    ws = [{"w": "a", "start": 0.0, "end": 1.0}, {"w": "b", "start": None, "end": None},
          {"w": "c", "start": 0.5, "end": 0.9}]
    out = tx.interpolate(ws)
    assert all(w["end"] >= w["start"] for w in out)


def test_interpolate_previous_word_without_end_uses_its_start():
    ws = [{"w": "a", "start": 0.4, "end": None}, {"w": "b", "start": None, "end": None},
          {"w": "c", "start": 1.0, "end": 1.2}]
    out = tx.interpolate(ws)
    assert out[1]["start"] == pytest.approx(0.4) and out[1]["end"] == pytest.approx(1.0)


def test_align_cleans_words_and_interpolates_untimed():
    wx = NS(
        load_audio=lambda path: "audio",
        load_align_model=lambda language_code, device: ("model", "meta"),
        align=lambda segs, model, meta, audio, device, return_char_alignments: {
            "segments": [{"words": [{"word": " Hi ", "start": 0.1234, "end": 0.5}, {"word": "there"}]}]},
    )
    out = tx.align("x.wav", [{"start": 0.0, "end": 1.0, "text": "Hi there"}], "en", whisperx_module=wx)
    assert [w["w"] for w in out] == ["Hi", "there"]
    assert (out[0]["start"], out[0]["end"]) == (0.123, 0.5)
    assert out[1]["start"] >= 0.5 and out[1]["end"] > out[1]["start"]


def broken_align(wav, segments, language):
    raise RuntimeError("no wav2vec2 model")


def test_english_alignment_failure_keeps_whisper_times(talking_clip, tmp_path):
    out = tx.transcribe(talking_clip, tmp_path, language="en", whisper_model=FakeWhisper("en"),
                        aligner=broken_align)
    assert out["error"] is None and out["engine"] == "whisper"
    assert out["notes"][0].startswith("Alignment unavailable")
    assert "no wav2vec2 model" in out["notes"][0]
    assert out["words"] == [{"w": "Hello", "start": 0.1, "end": 0.42}, {"w": "Acme.", "start": 0.5, "end": 0.9}]


def test_arabic_alignment_failure_without_whisper_fallback_is_an_error(talking_clip, tmp_path):
    out = tx.transcribe(talking_clip, tmp_path, language="ar", whisper_model=FakeWhisper("ar"),
                        aligner=broken_align, arabic=("extra", lambda wav, wd: [{"start": 0.0, "end": 1.0, "text": "مرحبا"}]))
    assert out["words"] is None and "no wav2vec2 model" in out["error"]


def test_whisper_constructed_once_per_transcribe(talking_clip, tmp_path, monkeypatch):
    built = []
    fake = FakeWhisper("en")

    def counting_factory(model):
        if model is not None:
            return model
        built.append(1)
        return fake

    monkeypatch.setattr(tx, "_whisper", counting_factory)
    out = tx.transcribe(talking_clip, tmp_path, language="auto", aligner=fake_align)
    assert out["error"] is None and out["language"] == "en"
    assert len(built) == 1
    assert len(fake.calls) == 2  # detect_language + whisper_words share the one model


def test_whisper_not_loaded_when_arabic_engine_and_alignment_succeed(talking_clip, tmp_path, monkeypatch):
    def forbidden(model):
        raise AssertionError("Whisper must not be loaded")

    monkeypatch.setattr(tx, "_whisper", forbidden)
    out = tx.transcribe(talking_clip, tmp_path, language="ar", aligner=fake_align,
                        arabic=("extra", lambda wav, wd: [{"start": 0.0, "end": 1.0, "text": "مرحبا"}]))
    assert out["error"] is None and out["engine"] == "extra+align"


def test_a_copy_without_a_second_arabic_engine_uses_whisper_and_says_nothing(talking_clip, tmp_path, monkeypatch):
    monkeypatch.setattr(tx, "arabic_engine", lambda: None)
    out = tx.transcribe(talking_clip, tmp_path, language="ar", whisper_model=FakeWhisper("ar"), aligner=fake_align)
    assert out["engine"] == "whisper+align" and out["notes"] == []  # nothing for anyone to act on
    assert tx.arabic_check_lines(tmp_path / "a.wav", tmp_path) == []


def test_a_failing_check_engine_is_noted_in_the_transcript_not_raised(tmp_path, monkeypatch):
    def broken(wav, wd):
        raise RuntimeError("venv missing")
    monkeypatch.setattr(tx, "arabic_engine", lambda: ("extra", broken))
    lines = tx.arabic_check_lines(tmp_path / "a.wav", tmp_path)
    assert any("extra failed" in ln for ln in lines)
