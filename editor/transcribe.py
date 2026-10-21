"""Speech to text with word timings.

English: faster-whisper large-v3-turbo with the glossary as hotwords, then alignment.
Arabic or mixed: Whisper forced to "ar", then WhisperX alignment with the Arabic wav2vec2 model. A copy of the engine
can carry a second Arabic text engine (`arabic_engine()`): its text is aligned instead, with Whisper as the fallback.
Never raises: failures come back as `error`, fallbacks as `notes`.
"""
from pathlib import Path

from . import ffmpeg
from .config import PACKAGE_DIR

WHISPER_MODEL = "large-v3-turbo"


def load_glossary(path=None) -> list:
    p = Path(path) if path else PACKAGE_DIR / "glossary_default.txt"
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


def interpolate(words: list) -> list:
    out = [dict(w) for w in words]
    i, n = 0, len(out)
    while i < n:
        if out[i].get("start") is not None:
            i += 1
            continue
        j = i
        while j < n and out[j].get("start") is None:
            j += 1
        if i > 0:
            prev = out[i - 1]
            lo = prev["end"] if prev.get("end") is not None else prev["start"]
        else:
            lo = out[j]["start"] if j < n else 0.0
        hi = out[j]["start"] if j < n else lo + 0.3 * (j - i)
        hi = max(hi, lo)
        step = (hi - lo) / (j - i)
        for k in range(i, j):
            out[k]["start"], out[k]["end"] = round(lo + step * (k - i), 3), round(lo + step * (k - i + 1), 3)
        i = j
    return out


def segments_from_words(words: list, gap: float = 0.6) -> list:
    segs = []
    for w in words:
        if segs and w["start"] - segs[-1]["end"] <= gap:
            segs[-1]["end"] = w["end"]
            segs[-1]["text"] += " " + w["w"]
        else:
            segs.append({"start": w["start"], "end": w["end"], "text": w["w"]})
    return segs


def _whisper(model):
    if model is not None:
        return model
    from faster_whisper import WhisperModel
    return WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")


def whisper_words(wav, language: str, glossary: list, model=None) -> list:
    segments, _ = _whisper(model).transcribe(
        str(wav), language=language, vad_filter=True, condition_on_previous_text=False,
        word_timestamps=True, hallucination_silence_threshold=2.0, beam_size=5,
        hotwords=" ".join(glossary)[:400] or None)
    return [{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
            for seg in segments for w in (seg.words or [])]


def detect_language(wav, model=None) -> str:
    _, info = _whisper(model).transcribe(str(wav), language=None, vad_filter=True)
    return info.language


def arabic_engine():
    """(name, segments(wav, workdir)) of a second Arabic text engine when this copy has one, else None (Whisper
    does the Arabic)."""
    try:
        from . import asr_extra
    except ImportError:
        return None
    return asr_extra.NAME, asr_extra.segments


def arabic_check_lines(wav, work) -> list:
    """That engine's text as a check on Whisper's words, for a transcript file ([] when this copy has none)."""
    eng = arabic_engine()
    if eng is None:
        return []
    name, segments = eng
    head = ["", f"# {name} (text only; better on dialect speech and English loanwords)", ""]
    try:
        return head + [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments(wav, work)]
    except Exception as e:  # the check is a help, never a reason to stop
        return head + [f"({name} failed: {str(e)[-300:]})"]


def align(wav, segments: list, language: str, whisperx_module=None) -> list:
    wx = whisperx_module
    if wx is None:
        import whisperx as wx
    audio = wx.load_audio(str(wav))
    model_a, meta = wx.load_align_model(language_code=language, device="cpu")
    res = wx.align(segments, model_a, meta, audio, "cpu", return_char_alignments=False)
    words = [{"w": w["word"].strip(), "start": w.get("start"), "end": w.get("end")}
             for s in res["segments"] for w in s.get("words", [])]
    return interpolate([{**w, "start": None if w["start"] is None else round(float(w["start"]), 3),
                         "end": None if w["end"] is None else round(float(w["end"]), 3)} for w in words])


def transcribe(src, workdir, language: str = "auto", glossary: list | None = None,
               whisper_model=None, aligner=align, arabic="auto") -> dict:
    """`arabic`: (name, segments(wav, workdir)) for Arabic text, None for Whisper only, "auto" for arabic_engine()."""
    notes = []
    arabic = arabic_engine() if arabic == "auto" else arabic
    try:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        wav = workdir / "audio16k.wav"
        ffmpeg.run(["-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav])
        glossary = load_glossary() if glossary is None else glossary
        loaded = []

        def model():
            if not loaded:
                loaded.append(_whisper(whisper_model))
            return loaded[0]

        lang = detect_language(wav, model()) if language == "auto" else language
        whisper_fallback = None
        if lang == "ar":
            try:
                if arabic is None:
                    raise LookupError
                segments, engine = arabic[1](wav, workdir), f"{arabic[0]}+align"
            except Exception as e:
                if arabic is not None:
                    notes.append(f"{arabic[0]} unavailable ({type(e).__name__}: {e}); used Whisper for Arabic.")
                # Latin hotwords make Whisper translate Arabic speech into English; keep Arabic-script terms only.
                arabic_terms = [t for t in glossary if any("؀" <= c <= "ۿ" for c in t)]
                whisper_fallback = whisper_words(wav, "ar", arabic_terms, model())
                segments, engine = segments_from_words(whisper_fallback), "whisper+align"
        else:
            whisper_fallback = whisper_words(wav, lang, glossary, model())
            segments, engine = segments_from_words(whisper_fallback), "whisper+align"
        try:
            words = aligner(wav, segments, lang)
        except Exception as e:
            if whisper_fallback is None:
                raise
            notes.append(f"Alignment unavailable ({type(e).__name__}: {e}); kept Whisper word times.")
            words, engine = whisper_fallback, "whisper"
        return {"language": lang, "engine": engine, "words": words, "notes": notes, "error": None}
    except Exception as e:
        return {"language": None, "engine": None, "words": None, "notes": notes, "error": f"{type(e).__name__}: {e}"}
