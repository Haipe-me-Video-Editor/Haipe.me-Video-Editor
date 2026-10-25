"""Caption lines from word timings, rendered as ASS for libass. Arabic-safe: Encoding=-1 and per-word colour swaps."""
import hashlib
import json
import re
from pathlib import Path

from .editjson import CAPTION_MODES, seg_len, segments_hash

MARGIN_X = 60
CHAR_W = 0.58
MAX_LINE_CHARS = 42
BILINGUAL_TOP = 0.067  # top-line size as a fraction of the short side; bottom line is 1/1.4 of it
WESTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
DESK_CAPTION_BOTTOM = 0.565  # while a desk is up, captions sit between its panel and the speaker's head
STYLE_KEYS = ("font", "arabic_font", "caption_size", "hook_scale", "caption_margin_v")
ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def is_arabic(text: str) -> bool:
    return bool(ARABIC.search(text))


def font_size(style: dict, size: tuple, hook: bool = False) -> int:
    return round(style["caption_size"] * min(size) * (style["hook_scale"] if hook else 1.0))


def margin_v(style: dict, size: tuple) -> int:
    return round(style["caption_margin_v"] * size[1])


def max_chars_for(style: dict, size: tuple, hook: bool = False) -> int:
    fit = int((size[0] - 2 * MARGIN_X) / (font_size(style, size, hook) * CHAR_W))
    return max(8, min(MAX_LINE_CHARS, fit))


def timeline_words(segments: list, words: list) -> list:
    out, offset = [], 0.0
    for n, seg in enumerate(segments):
        for w in words:
            mid = (w["start"] + w["end"]) / 2
            if seg["in"] <= mid < seg["out"] and not seg.get("mute"):
                s, e, k = max(w["start"], seg["in"]), min(w["end"], seg["out"]), seg.get("speed", 1.0)
                out.append({"w": w["w"].strip(), "start": round(offset + (s - seg["in"]) / k, 3),
                            "end": round(offset + (e - seg["in"]) / k, 3), "seg": n,
                            **{f: True for f in ("br", "glue") if w.get(f)}})
        offset += seg_len(seg)
    return out


def chunk(words: list, min_words: int = 2, max_words: int = 4, max_chars: int = 20, max_gap: float = 0.45) -> list:
    """Words into caption lines. A transcript word can steer this by hand: `br` ends a line after it, `glue` keeps
    it on the same line as the next word (whatever the length or count limits say)."""
    lines, cur = [], []
    for w in words:
        if cur and (cur[-1].get("br") or w.get("seg") != cur[-1].get("seg")  # a line never runs across a cut
                    or (not cur[-1].get("glue")
                        and (len(cur) >= max_words or len(" ".join(x["w"] for x in cur + [w])) > max_chars
                             or w["start"] - cur[-1]["end"] > max_gap))):
            lines.append(cur)
            cur = []
        cur.append(w)
        if len(cur) >= min_words and w["w"].endswith((".", ",", "?", "!", "،", "؟")) and not w.get("glue"):
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    for prev, line in zip(lines, lines[1:]):
        if (len(line) == 1 and len(prev) >= 3 and line[0]["start"] - prev[-1]["end"] <= max_gap
                and line[0].get("seg") == prev[-1].get("seg")
                and not prev[-1].get("br") and not prev[-2].get("glue")
                and not prev[-1]["w"].endswith((".", "?", "!", "؟"))
                and len(" ".join(x["w"] for x in [prev[-1]] + line)) <= max_chars):
            line.insert(0, prev.pop())
    return lines


def build_lines(segments: list, words: list, style: dict, size: tuple, hook_until: float = 3.0) -> list:
    tw = timeline_words(segments, words)
    total = round(sum(seg_len(s) for s in segments), 3)
    lines = []
    for group, hook in (([w for w in tw if w["start"] < hook_until], True),
                        ([w for w in tw if w["start"] >= hook_until], False)):
        for ws in chunk(group, max_chars=max_chars_for(style, size, hook)):
            lines.append({"start": ws[0]["start"], "end": ws[-1]["end"], "words": ws, "hook": hook, "tr": None})
    for a, b in zip(lines, lines[1:]):
        a["end"] = round(min(a["end"] + 0.15, b["start"]), 3)
    if lines:
        lines[-1]["end"] = round(min(lines[-1]["end"] + 0.15, total), 3)
    return lines


def cache_key(plan: dict, words: list, style: dict) -> str:
    """Everything the caption lines depend on; a change means work/captions.json must be rebuilt."""
    data = [segments_hash(plan), words or [], plan["format"], {k: style[k] for k in STYLE_KEYS}]
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _words_text(line: dict) -> str:
    return " ".join(w["w"] for w in line["words"])


def sync_lines(old_doc: dict | None, new_lines: list) -> list:
    """Carry each old line's tr to the first unused new line with the same words; the rest stay None."""
    pool = [ln for ln in (old_doc or {}).get("lines", []) if ln.get("tr")]
    for ln in new_lines:
        text = _words_text(ln)
        for k, old in enumerate(pool):
            if old is not None and _words_text(old) == text:
                ln["tr"], pool[k] = old["tr"], None
                break
    return new_lines


def ensure_lines(path, plan: dict, words: list, style: dict, size: tuple, rebuild: bool = False) -> list:
    """Lines cached in work/captions.json; rebuilt when the key changes (or on request), keeping translations."""
    path = Path(path)
    key = cache_key(plan, words, style)
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if old and old.get("key") == key and not rebuild:
        return old["lines"]
    lines = sync_lines(old, build_lines(plan["segments"], words or [], style, size))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"key": key, "segments_hash": segments_hash(plan), "lines": lines},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return lines


def _t(t: float) -> str:
    cs = max(0, int(round(t * 100)))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _bgr(hex_rgb: str) -> str:
    """An ASS colour (BBGGRR) that lands on the true colour. libass in ffmpeg converts subtitle colours to YUV with
    BT.601 whatever the video is tagged, and the videos are BT.709 (a deep plum came out visibly off its colour), so
    the colour written is the one whose BT.601 YUV is the true colour's BT.709 YUV."""
    h = hex_rgb.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b                                   # BT.709
    cb, cr = (b - y) / 1.8556, (r - y) / 1.5748
    r2, b2 = y + 1.402 * cr, y + 1.772 * cb                                   # read back with BT.601
    g2 = (y - 0.299 * r2 - 0.114 * b2) / 0.587
    r, g, b = (max(0, min(255, round(v * 255))) for v in (r2, g2, b2))
    return f"{b:02X}{g:02X}{r:02X}"


def _esc(text: str) -> str:
    return text.translate(WESTERN_DIGITS).replace("\\", "").replace("{", "(").replace("}", ")")


def _sizes(style: dict, size: tuple) -> dict:
    top = round(BILINGUAL_TOP * min(size))
    bot = round(top / 1.4)
    mv = margin_v(style, size)
    return {"Cap": (font_size(style, size), mv), "Hook": (font_size(style, size, True), mv),
            "Top": (top, mv + round(bot * 1.35)), "Bot": (bot, mv)}


def _need_tr(line: dict) -> str:
    if not line.get("tr"):
        raise ValueError(f"caption line at {line['start']:.2f}s needs a translation (fill 'tr' in work/captions.json)")
    return line["tr"]


def to_ass(lines: list, style: dict, size: tuple, mode: str = "source", desks: list = ()) -> str:
    """ASS subtitles. While a desk is up, lines move up between the panel and the speaker's head."""
    if mode not in CAPTION_MODES:
        raise ValueError(f"unknown caption mode {mode!r}; use one of {CAPTION_MODES}")
    W, H = size
    ink = _bgr(style["ink"])
    # the outline under every caption: black by default; a brand can set its own colour and weight (a sticker edge)
    edge, edge_w = _bgr(style.get("caption_outline", "#000000")), style.get("caption_outline_w", 0.06)
    # the word being spoken: the accent fill by default; a style can give it its own edge and a small pop as it starts
    act = style.get("caption_active", {})
    act_edge = _bgr(act["outline"]) if act.get("outline") else None
    pop = act.get("pop")
    on = ("{\\1c&H" + _bgr(act.get("fill", style["accent"])) + "&" + ("\\3c&H" + act_edge + "&" if act_edge else "")
          + (f"\\fscx{pop * 100:.0f}\\fscy{pop * 100:.0f}\\t(0,120,\\fscx100\\fscy100)" if pop else "") + "}")
    off = ("{\\1c&H" + ink + "&" + ("\\3c&H" + edge + "&" if act_edge else "") + ("\\fscx100\\fscy100" if pop else "")
           + "}")
    out = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2",
           "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
           "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
           "MarginL, MarginR, MarginV, Encoding"]
    for name, (fs, mv) in _sizes(style, size).items():
        for suffix, font in (("L", style["font"]), ("A", style["arabic_font"])):
            out.append(f"Style: {name}{suffix},{font},{fs},&H00{ink},&H00{ink},&H00{edge},&H64000000,-1,0,0,0,"
                       f"100,100,0,0,1,{max(2, round(fs * edge_w))},0,2,{MARGIN_X},{MARGIN_X},{mv},-1")
    out += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    sizes = _sizes(style, size)
    lift = round((1 - DESK_CAPTION_BOTTOM) * H) - sizes["Cap"][1]

    def event(start, end, style_name, text):
        on_desk = any(d["at"] - 0.01 <= start < d["at"] + d["dur"] for d in desks)
        mv = sizes[style_name[:-1]][1] + lift if on_desk else 0
        out.append(f"Dialogue: 0,{_t(start)},{_t(end)},{style_name},,0,0,{mv},,{text}")

    for ln in lines:
        src_text = " ".join(w["w"] for w in ln["words"])
        src_ar = is_arabic(src_text)
        base = "Hook" if ln["hook"] else "Cap"
        if mode in ("ar", "en") and (mode == "ar") != src_ar:
            tr = _need_tr(ln)
            event(ln["start"], ln["end"], base + ("A" if is_arabic(tr) else "L"), _esc(tr))
            continue
        if mode == "bilingual":
            tr = _need_tr(ln)
            tr_ar = is_arabic(tr)
            event(ln["start"], ln["end"], ("Top" if tr_ar else "Bot") + ("A" if tr_ar else "L"), _esc(tr))
            src_style = ("Top" if src_ar else "Bot") + ("A" if src_ar else "L")
        else:
            src_style = base + ("A" if src_ar else "L")
        ws = ln["words"]
        for k, w in enumerate(ws):
            start = ln["start"] if k == 0 else w["start"]
            end = ws[k + 1]["start"] if k + 1 < len(ws) else ln["end"]
            if end > start:
                text = " ".join(f"{on}{_esc(x['w'])}{off}" if j == k else _esc(x["w"]) for j, x in enumerate(ws))
                event(start, end, src_style, text)
    return "\n".join(out) + "\n"


def check_layout(lines: list, style: dict, size: tuple, mode: str = "source") -> list:
    if mode not in CAPTION_MODES:
        raise ValueError(f"unknown caption mode {mode!r}; use one of {CAPTION_MODES}")
    W, H = size
    sizes = _sizes(style, size)
    issues = []

    def check(text, fs, mv, at):
        if len(text) > MAX_LINE_CHARS or len(text) * fs * CHAR_W > W - 2 * MARGIN_X:
            issues.append(f"line too wide at {at:.1f}s: {text!r}")
        if H - mv - fs * 1.2 < 0.12 * H or H - mv > 0.80 * H:
            issues.append(f"line outside the safe area at {at:.1f}s")

    for ln in lines:
        src = " ".join(w["w"] for w in ln["words"])
        if mode == "bilingual" and ln.get("tr"):
            for text in (src, ln["tr"]):
                fs, mv = sizes["Top" if is_arabic(text) else "Bot"]
                check(text, fs, mv, ln["start"])
        else:
            text = ln["tr"] if mode in ("ar", "en") and (mode == "ar") != is_arabic(src) and ln.get("tr") else src
            fs, mv = sizes["Hook" if ln["hook"] else "Cap"]
            check(text, fs, mv, ln["start"])
    return issues
