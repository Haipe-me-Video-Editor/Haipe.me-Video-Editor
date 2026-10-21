"""Talking-head cut decisions. Pure functions over word timings; no media access."""
import difflib
import re

FILLERS = {"um", "uh", "erm", "er", "ah", "hmm", "mm"}
MAX_GAP = 0.35        # longer pauses are cut
PAD_IN, PAD_OUT = 0.06, 0.09   # together they leave a natural ~0.15 s pause
MIN_LEN = 0.25        # drop stray slivers
SENTENCE_GAP = 0.6
ENERGY_HOP = 0.01     # seconds per value in the RMS envelope
VOICED_DB = -35.0     # a gap louder than this on average holds an untranscribed sound
MIN_VOICED_GAP = 0.12
SENTENCE_END = (".", "?", "!", "؟")
RETAKE_PREFIX_RATIO = 0.75  # a finished shorter take must closely match the start of the next one


def _norm(word: str) -> str:
    return re.sub(r"[^\w']+", "", word.lower())


def _ends_sentence(word: str) -> bool:
    return word.rstrip().endswith(SENTENCE_END)


def remove_fillers(words: list, removed: list) -> list:
    out, i = [], 0
    while i < len(words):
        w, n = words[i], _norm(words[i]["w"])
        if n in FILLERS:
            removed.append({"kind": "filler", "start": w["start"], "end": w["end"], "text": w["w"].strip()})
            _break_next(words, i + 1)
            i += 1
            continue
        if n == "you" and i + 1 < len(words) and _norm(words[i + 1]["w"]) == "know":
            before = w["start"] - (words[i - 1]["end"] if i > 0 else 0.0)
            after = (words[i + 2]["start"] if i + 2 < len(words) else float("inf")) - words[i + 1]["end"]
            if before >= 0.2 and after >= 0.2:
                removed.append({"kind": "filler", "start": w["start"], "end": words[i + 1]["end"], "text": "you know"})
                _break_next(words, i + 2)
                i += 2
                continue
        out.append(w)
        i += 1
    return out


def _break_next(words: list, index: int) -> None:
    if index < len(words):
        words[index]["break_before"] = True


def mark_voiced_gaps(words: list, db, removed: list, hop: float = ENERGY_HOP) -> None:
    """Local Whisper drops 'um'/'uh'. A short gap that still carries sound is one: force a cut there."""
    for prev, nxt in zip(words, words[1:]):
        gap = nxt["start"] - prev["end"]
        if not MIN_VOICED_GAP <= gap <= MAX_GAP or nxt.get("break_before"):
            continue
        frames = db[int(prev["end"] / hop):int(nxt["start"] / hop)]
        if len(frames) and float(frames.mean()) > VOICED_DB:
            nxt["break_before"] = True
            removed.append({"kind": "filler", "start": prev["end"], "end": nxt["start"], "text": "(untranscribed sound)"})


def sentences(words: list, gap: float = SENTENCE_GAP) -> list:
    groups = [[]]
    for w in words:
        if groups[-1] and w["start"] - groups[-1][-1]["end"] > gap:
            groups.append([])
        groups[-1].append(w)
        if _ends_sentence(w["w"]):
            groups.append([])
    return [g for g in groups if g]


def _is_retake(g: list, nxt: list) -> bool:
    """Same opening is not enough: g must be unfinished, or a shorter take that repeats the start of nxt."""
    if not g[-1]["w"].rstrip().endswith(SENTENCE_END):
        return True
    if len(g) >= len(nxt):
        return False
    a = [_norm(x["w"]) for x in g]
    b = [_norm(x["w"]) for x in nxt[:len(g)]]
    return difflib.SequenceMatcher(None, a, b).ratio() >= RETAKE_PREFIX_RATIO


def remove_retakes(groups: list, removed: list) -> list:
    """When a sentence restarts, keep the last take."""
    keep = []
    for i, g in enumerate(groups):
        nxt = groups[i + 1] if i + 1 < len(groups) else None
        if nxt:
            k = min(3, len(g), len(nxt))
            if k >= 2 and [_norm(x["w"]) for x in g[:k]] == [_norm(x["w"]) for x in nxt[:k]] and _is_retake(g, nxt):
                removed.append({"kind": "retake", "start": g[0]["start"], "end": g[-1]["end"],
                                "text": " ".join(x["w"].strip() for x in g)})
                nxt[0]["break_before"] = True
                continue
        keep.append(g)
    return keep


def spans_from_words(words: list, duration: float | None = None, removed: list | None = None) -> list:
    spans = []
    for w in words:
        if spans and not w.get("break_before") and w["start"] - spans[-1][1] <= MAX_GAP:
            spans[-1][1] = w["end"]
        else:
            spans.append([w["start"], w["end"]])
    out = []
    for core_a, core_b in spans:
        a, b = max(0.0, core_a - PAD_IN), core_b + PAD_OUT
        if duration is not None:
            b = min(duration, b)
        for r in removed or []:  # padding must not pull removed audio back in
            rs, re_ = r["start"], r["end"]
            if rs < b and re_ > a:
                if re_ <= core_a:
                    a = max(a, re_)
                elif rs >= core_b:
                    b = min(b, rs)
        if out and a < out[-1][1]:
            a = out[-1][1]
        if b - a >= MIN_LEN:
            out.append([a, b])
    return out


def spans_from_silences(silences: list, duration: float, keep_pause: float = 0.15) -> list:
    spans, cur = [], 0.0
    for s, e in sorted(silences):
        b = min(duration, s + keep_pause / 2)
        if b - cur >= MIN_LEN:
            spans.append([cur, b])
        cur = max(cur, e - keep_pause / 2)
    if duration - cur >= MIN_LEN:
        spans.append([cur, duration])
    return spans


def plan_cuts(src: str, duration: float, words: list | None = None, silences: list | None = None, energy=None):
    removed = []
    if words:
        ws = [dict(w) for w in words]  # never mutate the caller's transcript
        kept = remove_fillers(ws, removed)
        if energy is not None:
            mark_voiced_gaps(kept, energy, removed)
        kept = [w for g in remove_retakes(sentences(kept), removed) for w in g]
        spans = spans_from_words(kept, duration=duration, removed=removed)
    else:
        spans = spans_from_silences(silences or [], duration)
    segments = [{"src": src, "in": round(a, 3), "out": round(b, 3), "zoom": 1.0 if i % 2 == 0 else 1.1}
                for i, (a, b) in enumerate(spans)]
    return segments, removed
