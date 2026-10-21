"""Where each graphic card goes: in empty space, inside the social-media safe zone, off the face.

The safe zone keeps clear of the platform UI on Reels, TikTok and Shorts: the top bar, the
caption/description block at the bottom and the like/comment column on the right. Inside it,
the head band (from faces.py) and the caption band are blocked; a card takes the free slot it
fits best and is scaled down to fit it. Fractions are of the frame height unless noted.
"""
import math

from . import captions, faces as faces_mod

SAFE_TOP, SAFE_BOTTOM = 0.13, 0.80
SAFE_LEFT, SAFE_RIGHT = 0.06, 0.12  # fractions of the width; the right edge holds the UI buttons
PAD = 0.015  # gap kept between a card and the face or the captions
MIN_SCALE = 0.6  # below this the text gets too small to read on a phone
ASSUMED_HEAD = (0.10, 0.60)  # talking-head selfie framing, used when no face was detected

# Card metrics in vmin, mirroring composition.CSS: font size, line height, extra height per entry.
PADDING_V = 8.0  # 4vmin top and bottom
_LINE = {"hook": (9.0, 1.1), "quote": (6.4, 1.25), "item": (5.6, 1.25), "name": (5.4, 1.25),
         "sub": (3.6, 1.25), "num": (20.0, 1.0), "label": (5.0, 1.25), "by": (3.8, 1.25),
         "headline": (6.0, 1.15), "src": (3.0, 1.25), "kinetic": (9.0, 1.1)}
FIXED = ("credit", "chapter", "outro", "stack", "card", "badge", "bars", "leak", "endcard", "tiles", "poll", "balance",
         "wave", "mark", "sticker", "title")  # fixed spot or full frame
CHAR_EM = 0.55  # average glyph width in em, Latin and Arabic alike (Arabic runs a little narrower)
ARABIC_LH = 1.15  # Arabic line boxes are taller


def _lines(text: str, font_vmin: float, width_vmin: float) -> int:
    return max(1, math.ceil(len(text) * CHAR_EM * font_vmin / width_vmin))


def card_height_vmin(spec: dict, inner_width_vmin: float) -> float:
    """Estimated card height in vmin at scale 1."""
    t, arabic = spec["type"], captions.is_arabic(" ".join(
        v if isinstance(v, str) else " ".join(v) for v in spec.values() if isinstance(v, (str, list))))
    lh = ARABIC_LH if arabic else 1.0

    def block(key, text):
        fs, k = _LINE[key]
        return _lines(text, fs, inner_width_vmin) * fs * k * lh

    if t == "hook":
        body = block("hook", spec["text"])
    elif t == "quote":
        body = block("quote", "“" + spec["text"] + "”") + (block("by", spec["by"]) + 2.4 if spec.get("by") else 0)
    elif t == "list":
        body = sum(block("item", x) for x in spec["items"]) + 2.0 * (len(spec["items"]) + 1)
    elif t == "stat":
        body = _LINE["num"][0] + 2.0 + block("label", spec["label"])
    elif t == "headline":
        body = (block("headline", spec["text"]) + (block("src", spec["source"]) + 1.6 if spec.get("source") else 0)
                + (5.8 if spec.get("tag") else 0))
        return body + 7.2  # 3.6vmin padding top and bottom
    elif t == "kinetic":
        return block("kinetic", spec["text"]) + 2.0  # no card padding
    elif t == "ticker":
        return block("name", spec["name"]) + block("sub", spec["ticker"] + " · " + spec.get("fact", "")) + 0.8 + 4.8
    elif t == "lower_third":
        body = block("name", spec["name"]) + (block("sub", spec["sub"]) + 0.8 if spec.get("sub") else 0)
        return body + 4.8  # 2.4vmin padding top and bottom
    else:
        return 0.0
    return body + PADDING_V


def caption_band(style: dict, size: tuple, mode: str):
    """(top, bottom) of the caption block, with the bigger hook lines allowed for."""
    W, H = size
    mv = captions.margin_v(style, size)
    if mode == "bilingual":
        top = round(captions.BILINGUAL_TOP * min(size))
        bot = round(top / 1.4)
        height = top * 1.3 + bot * 1.35 + bot * 0.3
    else:
        height = captions.font_size(style, size, True) * 1.3
    return (H - mv - height) / H, (H - mv) / H


def _free(blocked: list) -> list:
    """Free (top, bottom) intervals inside the safe zone."""
    free, y = [], SAFE_TOP
    for a, b in sorted(blocked):
        if a > y:
            free.append((y, min(a, SAFE_BOTTOM)))
        y = max(y, b)
    if y < SAFE_BOTTOM:
        free.append((y, SAFE_BOTTOM))
    return [(a, b) for a, b in free if b - a > 0.01]


def place(spec: dict, plan: dict, faces: dict | None, style: dict, size: tuple) -> dict:
    """{"top", "height"} as fractions of the frame height, "scale" (≤ 1) and a note when cramped."""
    W, H = size
    if spec["type"] in FIXED or spec.get("place") in ("behind", "center"):
        return {"top": SAFE_TOP, "height": SAFE_BOTTOM - SAFE_TOP, "scale": 1.0}
    vmin = min(size) / 100
    head = faces_mod.head_band(faces, plan["segments"], spec["at"], spec["dur"], size) if faces else None
    head = head or ASSUMED_HEAD
    blocked = [(head[0] - PAD, head[1] + PAD)]
    cap = plan.get("captions", {})
    if cap.get("enabled"):
        c0, c1 = caption_band(style, size, cap.get("mode", "source"))
        blocked.append((c0 - PAD, c1 + PAD))
    inner = (1 - SAFE_LEFT - SAFE_RIGHT) * W / vmin - 10.0  # slot width minus 5vmin side padding
    need = card_height_vmin(spec, inner) * vmin / H
    slots = _free(blocked)
    if not slots:
        return {"top": SAFE_TOP, "height": 0.12, "scale": MIN_SCALE,
                "note": f"{spec['type']} at {spec['at']:.1f}s: no free space off the face; placed at the top."}
    # Prefer the slot where the card shrinks least; on a tie, the one nearer the top.
    a, b = max(slots, key=lambda s: (min(1.0, (s[1] - s[0]) / need), -s[0]))
    scale = min(1.0, (b - a) / need)
    out = {"top": round(a, 4), "height": round(b - a, 4), "scale": round(scale, 3)}
    if scale < MIN_SCALE:
        out["note"] = (f"{spec['type']} at {spec['at']:.1f}s is cramped (scaled to {scale:.0%}) in the free space "
                       f"{a:.0%}-{b:.0%}: shorten the text or use a more compact graphic.")
    return out
