"""Phrase-level packed transcript: Claude's reading view, about 1/10 the tokens of raw word JSON."""


def pack(words: list, gap: float = 0.5) -> str:
    lines, cur = [], []
    for w in words:
        if cur and w["start"] - cur[-1]["end"] >= gap:
            lines.append(cur)
            cur = []
        cur.append(w)
        if w["w"].rstrip().endswith((".", "?", "!", "؟")):
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return "\n".join(f"[{ln[0]['start']:07.2f}-{ln[-1]['end']:07.2f}] " + " ".join(w["w"] for w in ln) for ln in lines) + "\n"
