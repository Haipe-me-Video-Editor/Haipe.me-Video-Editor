"""Cover story: the frame becomes a magazine cover. A huge serif masthead sits behind the speaker's head (the head
overlaps it, as on real covers), with an issue line, cover lines and a barcode around the edges.

On a wide shot with headroom the room stays and the masthead goes on the wall above the head. On a close-up (no
wall above the head) the room gives way to a studio backdrop in the style's colours and the speaker is lowered
so the crown of the head lands across the lower half of the masthead; the whole cover springs in and unwinds at
the end. The masthead letters (numpy, a system Didone/serif) spring together from wide tracking; the cover lines
and barcode are a HyperFrames layer in front of the speaker, kept off the face.
"""
import datetime
import hashlib
import html
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import _behind as B

NAME = "cover_story"
DOC = ("Turns the frame into a magazine cover: huge serif masthead behind the speaker's head, cover lines, issue "
       "line and barcode around the edges. For a big announcement or a 'this is the story' moment.")
BEST_FOR = ["product", "finance", "corporate", "any"]
DUR = (2.0, 8)
PARAMS = {
    "masthead": "EDIT",  # 1 word, 3-8 letters reads best (Arabic works too)
    "lines": [],         # cover lines; the first is the lead story (big), the rest small. Use the speaker's words.
    "kicker": "",        # small label over the lead line (default "COVER STORY"); "" + no lines = none
    "issue": "",         # e.g. "No. 07 · OCT 2026"; default the brand + this month
    "backdrop": "auto",  # auto | room (keep the room) | studio (style-coloured backdrop, speaker lowered)
    "color": None,       # masthead colour (default from the style)
    "barcode": True,
}

ENTER_BG, MOVE, EXIT = 0.18, 0.75, 0.45


def look(style: dict) -> dict:
    """Studio backdrop centre/edge, masthead, issue and kicker colours: from the style's colours, with any key
    overridden by the style's `cover_story` dict."""
    bg, acc = style.get("bg", "#0b0c0e"), style.get("accent", "#ffffff")
    return {"centre": style.get("bg2", "#3a3d44"), "edge": bg, "mast": acc, "issue": acc, "kick_bg": acc,
            "kick_fg": bg, "line": style.get("ink", "#ffffff"), **style.get("cover_story", {})}


def plan(W: int, H: int, head: dict, backdrop: str, mast_cap: float) -> dict:
    """Where the masthead goes and how far the speaker drops. The crown should sit ~45% down the masthead."""
    top_safe = B.SAFE[1] * H
    mast_top = top_safe + H * 0.006
    want_crown = mast_top + mast_cap * 0.55
    room_ok = head["top"] >= want_crown - mast_cap * 0.1
    if backdrop == "room" or (backdrop == "auto" and room_ok):
        return {"studio": False, "dy": 0.0, "mast_top": max(mast_top, min(head["top"] - mast_cap * 0.55,
                                                                           head["top"] - mast_cap * 0.3))}
    dy = float(np.clip(want_crown - head["top"], 0, H * 0.16))
    return {"studio": True, "dy": dy, "mast_top": mast_top}


def masthead_sprites(text: str, font_path, cap: float, max_w: float):
    """Letters of the masthead at cap height `cap`, squeezed (never stretched) to fit max_w:
    [(alpha, x, y)] with x, y relative to the masthead's top-left, plus its (w, h)."""
    em = cap / 0.68
    for _ in range(3):
        f = ImageFont.truetype(str(font_path), int(em))
        b = f.getbbox("H", anchor="ls")
        real_cap = -b[1]
        em *= cap / max(real_cap, 1)
    f = ImageFont.truetype(str(font_path), int(em))
    arabic = B.is_arabic(text)
    units = [text] if arabic else list(text)
    track = -0.01 * em
    adv = [f.getlength(u) for u in units]
    width = sum(adv) + track * (len(units) - 1)
    sx = min(1.0, max_w / max(width, 1))
    if sx < 0.62:  # too long even squeezed: shrink the type instead
        em *= sx / 0.62
        return masthead_sprites(text, font_path, cap * sx / 0.62, max_w)
    asc = -f.getbbox(text, anchor="ls")[1]
    desc = max(f.getbbox(text, anchor="ls")[3], 0)
    h = math.ceil(asc + desc + 4)
    out, x = [], 0.0
    for u, a in zip(units, adv):
        if u.strip():
            im = Image.new("L", (math.ceil(a + em * 0.3), h), 0)
            ImageDraw.Draw(im).text((em * 0.15, asc + 2), u, font=f, fill=255, anchor="ls")
            arr = np.asarray(im, np.float32) / 255
            if sx < 1:
                arr = cv2.resize(arr, (max(1, round(arr.shape[1] * sx)), h), interpolation=cv2.INTER_AREA)
            out.append((arr, (x - em * 0.15) * sx, 0.0))
        x += a + track
    return out, (width * sx, h), asc


def barcode_svg(seed: str, w: int, h: int, ink: str) -> str:
    """A decorative EAN-style barcode drawn from a hash of the seed (not a real code)."""
    bits = "".join(f"{b:08b}" for b in hashlib.sha1(seed.encode()).digest())
    bars, x, unit = [], 4.0, (w - 8) / 95
    pattern = "101" + bits[:42] + "01010" + bits[42:84] + "101"
    for i, c in enumerate(pattern[:95]):
        if c == "1":
            guard = i < 3 or 45 <= i < 50 or i >= 92
            bars.append(f'<rect x="{x:.2f}" y="4" width="{unit:.2f}" height="{h - (8 if guard else 18)}" fill="{ink}"/>')
        x += unit
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">{"".join(bars)}</svg>'


def front_page(ctx, lk: dict, geo: dict, lines: list, kicker: str, issue: str, barcode: bool) -> str:
    W = ctx.W
    esc = html.escape
    lead, rest = (lines[0], lines[1:]) if lines else ("", [])
    lead_html = (f"<div class='kick'><span>{esc(kicker)}</span></div>" if kicker and lead else "") + \
        (f"<div class='lead'>{esc(lead)}</div>" if lead else "")
    rest_html = "".join(f"<div class='small'>{esc(r)}</div>" for r in rest)
    rule = "<div class='rule'></div>" if lead and rest else ""
    issue_html = "".join(f"<span>{esc(p)}</span>" for p in geo["issue_parts"])
    code = ""
    if barcode:
        code = (f"<div id='bar'>{barcode_svg(issue or 'cover', 170, 74, '#0b0c0e')}"
                f"<div class='num'>{esc(geo['code'])}</div></div>")
    lfs = W * 0.06
    css = f"""
#cl{{position:absolute;left:{geo['col_x']:.0f}px;top:{geo['col_y']:.0f}px;width:{geo['col_w']:.0f}px;color:{lk['line']};
  text-shadow:0 2px 14px rgba(0,0,0,.45)}}
.kick span{{display:inline-block;background:{lk['kick_bg']};color:{lk['kick_fg']};font:800 {W * 0.021:.0f}px "Montserrat";
  letter-spacing:.16em;padding:.42em .7em .36em;border-radius:3px;text-shadow:none;margin-bottom:{W * 0.014:.0f}px}}
.lead{{font:800 {lfs:.0f}px/1.0 "BrandLT";letter-spacing:-.02em;text-transform:none}}
.rule{{width:{W * 0.12:.0f}px;height:3px;background:{lk['kick_bg']};margin:{W * 0.022:.0f}px 0 {W * 0.016:.0f}px}}
.small{{font:600 {W * 0.031:.0f}px/1.25 "BrandLT";opacity:.94;margin-top:{W * 0.006:.0f}px}}
#issue{{position:absolute;{geo['issue_side']}:{geo['issue_x']:.0f}px;top:{geo['issue_y']:.0f}px;color:{geo['issue_color']};
  text-align:{geo['issue_side']};
  font:700 {W * 0.019:.0f}px/1.5 "Montserrat";letter-spacing:.22em;text-transform:uppercase}}
#issue span{{display:block}}
#bar{{position:absolute;left:{geo['bar_x']:.0f}px;top:{geo['bar_y']:.0f}px;background:#fff;border-radius:4px;
  padding:6px 8px 4px;box-shadow:0 6px 24px rgba(0,0,0,.28)}}
#bar svg{{display:block}}
#bar .num{{font:500 15px "PlexMono";color:#0b0c0e;letter-spacing:.3em;text-align:center;margin-top:-12px;
  background:#fff;position:relative}}"""
    body = (f"<div id='issue'>{issue_html}</div><div id='cl'>{lead_html}{rule}{rest_html}</div>{code}")
    d = ctx.dur
    t0 = MOVE * 0.55
    js = f"""
  springIn(tl, '#issue span', {{x: -24, opacity: 0}}, {{x: 0, opacity: 1, duration: .5, stagger: .07}}, 'snappy', {t0:.2f});
  springIn(tl, '#cl .kick', {{y: 14, opacity: 0}}, {{y: 0, opacity: 1, duration: .45}}, 'snappy', {t0 + .1:.2f});
  springIn(tl, '#cl .lead', {{x: -36, opacity: 0}}, {{x: 0, opacity: 1, duration: .6}}, 'snappy', {t0 + .18:.2f});
  springIn(tl, '#cl .rule', {{scaleX: 0, transformOrigin: '0 50%'}}, {{scaleX: 1, duration: .5}}, 'gentle', {t0 + .3:.2f});
  springIn(tl, '#cl .small', {{x: -24, opacity: 0}}, {{x: 0, opacity: 1, duration: .5, stagger: .08}}, 'snappy', {t0 + .34:.2f});
  springIn(tl, '#bar', {{y: 30, opacity: 0}}, {{y: 0, opacity: 1, duration: .55}}, 'gentle', {t0 + .45:.2f});
  tl.to(['#cl', '#issue', '#bar'], {{opacity: 0, y: -10, duration: .3, ease: 'power2.in'}}, {d - EXIT - 0.05:.3f});"""
    return ctx.page(body, css, js)


def issue_layout(issue: str, W: int, head: dict, y: float) -> dict:
    """The issue line goes in the gap beside the head under the masthead (left, else right), one part per line;
    parts that do not fit are dropped from the front (the brand), never drawn over the head."""
    from PIL import ImageFont

    from .. import fonts
    fs = W * 0.019
    f = ImageFont.truetype(str(fonts.ensure_font("Montserrat")), int(fs))
    parts = [p.strip().upper() for p in issue.split("·") if p.strip()]

    def width(p):  # letter-spacing .22em
        return f.getlength(p) + 0.22 * fs * len(p)
    gap_l = head["cx"] - 0.5 * head["fw"] - B.SAFE[0] * W - W * 0.03
    gap_r = B.SAFE[2] * W - (head["cx"] + 0.5 * head["fw"]) - W * 0.03
    while parts:
        need = max(width(p) for p in parts)
        if need <= gap_l:
            return {"issue_parts": parts, "issue_side": "left", "issue_x": B.SAFE[0] * W + W * 0.014, "issue_y": y}
        if need <= gap_r:
            return {"issue_parts": parts, "issue_side": "right", "issue_x": W - B.SAFE[2] * W + W * 0.006,
                    "issue_y": y}
        parts = parts[1:]
    return {"issue_parts": [], "issue_side": "left", "issue_x": 0, "issue_y": y}


def first_frame(ctx) -> np.ndarray:
    import subprocess
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(ctx.src), "-vf", f"scale={ctx.W}:{ctx.H}",
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True,
                         check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(ctx.H, ctx.W, 3)


def solid_body(m: np.ndarray, from_row: int) -> np.ndarray:
    """Fill the matte's see-through holes below `from_row` (the chin): every pixel under person pixels in its
    column is person too (a seated speaker is solid down to the frame edge). Softened so the fill never shows."""
    from_row = int(np.clip(from_row, 0, m.shape[0] - 1))
    lo = m[from_row:]
    small = cv2.resize(lo, (lo.shape[1] // 4, max(lo.shape[0] // 4, 1)), interpolation=cv2.INTER_AREA)
    filled = np.maximum.accumulate(np.clip((small - 0.15) / 0.5, 0, 1), axis=0)
    filled = cv2.GaussianBlur(filled, (0, 0), 2)
    filled = cv2.resize(filled, (lo.shape[1], lo.shape[0]), interpolation=cv2.INTER_LINEAR)
    out = m.copy()
    out[from_row:] = np.maximum(lo, filled)
    return out


def render(ctx):
    W, H = ctx.W, ctx.H
    B.prime(ctx)
    occ = B.occupancy(ctx)
    face = ctx.face()
    B.publish(ctx)
    head = B.head_box(occ, face, W, H)
    lk = look(ctx.style)
    text = (ctx.param("masthead") or PARAMS["masthead"]).strip()
    arabic = B.is_arabic(text)
    if not arabic:
        text = text.upper()
    font = B.font_file(ctx, "Lalezar" if arabic else "Serif")
    mast_cap = H * 0.118
    P = plan(W, H, head, ctx.param("backdrop", "auto"), mast_cap)
    max_w = (B.SAFE[2] - B.SAFE[0]) * W
    letters, (mw, mh), asc = masthead_sprites(text, font, mast_cap, max_w)
    mx = (B.SAFE[0] + B.SAFE[2]) / 2 * W - mw / 2
    my = P["mast_top"] - (asc - mast_cap) - 2
    mast_rgb = B.hex_rgb(ctx.param("color") or lk["mast"])
    first = first_frame(ctx)
    if not P["studio"] and not ctx.param("color"):  # on the room: dark or light ink, whichever reads
        y0, y1 = int(max(my, 0)), int(min(my + mh, H))
        lum = float(first[y0:y1].mean()) / 255
        mast_rgb = B.hex_rgb("#0b0c0e") if lum > 0.55 else B.hex_rgb("#f6f4ef")
    issue_color = lk["issue"] if P["studio"] else ("#0b0c0e" if mast_rgb.mean() < 0.5 else "#f6f4ef")

    # layout of the front elements, after the drop
    dy = P["dy"]
    chin = head["chin"] + dy
    col_x = B.SAFE[0] * W + W * 0.012
    col_w = W * 0.46
    col_y = max(chin + H * 0.02, H * 0.56)
    n_small = max(len(ctx.param("lines", [])) - 1, 0)
    col_h = W * 0.06 * 2.1 + W * 0.05 + n_small * W * 0.042 + W * 0.06
    col_y = min(col_y, B.SAFE[3] * H - col_h)
    today = datetime.datetime.now().astimezone().date()
    brand = ctx.style.get("cover_name") or "THE EDIT"
    issue = ctx.param("issue") or f"{brand} · {today.strftime('%b').upper()} {today.year}"
    geo = {"col_x": col_x, "col_y": col_y, "col_w": col_w,
           **issue_layout(issue, W, head, my + mh + H * 0.008),
           "issue_color": issue_color,
           "bar_x": B.SAFE[2] * W - 186 - W * 0.01, "bar_y": B.SAFE[3] * H - 96,
           "code": f"{today.year % 100:02d}{today.month:02d}{int(hashlib.sha1(text.encode()).hexdigest(), 16) % 9000 + 1000}"}
    lines = list(ctx.param("lines", []) or [])
    kicker = ctx.param("kicker") if ctx.param("kicker") is not None and ctx.param("kicker") != "" else (
        "COVER STORY" if lines else "")
    if arabic and not lines:
        kicker = ""
    front = ctx.layer(front_page(ctx, lk, geo, lines, kicker, issue, bool(ctx.param("barcode", True))), "cover")

    # studio backdrop: radial light behind the head, a touch of grain
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = head["cx"], P["mast_top"] + mast_cap * 1.6
    r = np.sqrt(((xx - cx) / (W * 0.85)) ** 2 + ((yy - cy) / (H * 0.62)) ** 2)
    g = np.clip(r, 0, 1) ** 1.6
    back = (B.hex_rgb(lk["centre"]) * (1 - g[..., None]) + B.hex_rgb(lk["edge"]) * g[..., None]).astype(np.float32)
    del xx, yy, r, g
    rng = np.random.default_rng(7)
    grain = [rng.normal(0, 0.012, (H // 2, W // 2)).astype(np.float32) for _ in range(3)]

    notbg = B.NotBackground() if P["studio"] else None
    enter_mast = B.spring("gentle")
    move = B.spring("gentle")
    d = ctx.dur
    with ctx.writer() as write:
        for i, (frame, m, fr) in enumerate(zip(ctx.frames(), B.person_alpha(ctx), ctx.frames(front, rgba=True))):
            t = i / ctx.fps
            F = frame.astype(np.float32) / 255
            out_t = B.progress(t, d - EXIT, EXIT)
            if P["studio"]:
                b = B.ease_out(B.progress(t, 0, ENTER_BG)) * (1 - B.ease_in(B.progress(t, d - 0.16, 0.16)))
                k = move(B.progress(t, ENTER_BG * 0.8, MOVE)) * (1 - B.ease_in(B.progress(t, d - EXIT, EXIT - 0.12)))
                shift = dy * k
            else:
                b, shift = 0.0, 0.0
            # base: the room, fading to the backdrop
            if b > 0:
                gtile = cv2.resize(grain[i % 3], (W, H), interpolation=cv2.INTER_NEAREST)[..., None]
                base = F * (1 - b) + (back + gtile) * b
            else:
                base = F.copy()
            # the person, lowered (with a solid body: on a clean backdrop a see-through shirt shows)
            if P["studio"] and b > 0:
                m = m * (1 - b + b * notbg(frame))  # MODNet keeps the chair back; the class map drops it
                hard = np.clip((m - 0.3) / 0.4, 0, 1)  # no half-transparent fringe on a clean backdrop
                m = solid_body(m * (1 - b) + hard * b, int(head["chin"]))
            if shift > 0.25:
                M = np.float32([[1, 0, 0], [0, 1, shift]])
                P_rgb = cv2.warpAffine(F, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                P_a = cv2.warpAffine(m, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            else:
                P_rgb, P_a = F, m
            if P["studio"] and b > 0:  # soft shadow of the speaker on the backdrop
                sh = cv2.GaussianBlur(cv2.resize(P_a, (W // 4, H // 4), interpolation=cv2.INTER_AREA), (0, 0), 6)
                sh = cv2.warpAffine(sh, np.float32([[1, 0, W * 0.0075], [0, 1, H * 0.003]]), (W // 4, H // 4),
                                    borderMode=cv2.BORDER_REPLICATE)
                sh = cv2.resize(sh, (W, H))
                base *= 1 - (0.22 * b * sh)[..., None]
            # masthead behind the head
            for j, (a, lx, ly) in enumerate(letters):
                tk = t - 0.12 - 0.05 * j
                if tk <= 0:
                    continue
                p = enter_mast(min(tk / 0.8, 1.0))
                fade = B.ease_out(tk / 0.4) * (1 - B.ease_in(out_t))
                if fade < 0.003:
                    continue
                spread = (lx + a.shape[1] / 2 - mw / 2) * 0.22 * (1 - p)
                sp, ox, oy = B.warp_sprite(a, spread, mast_cap * 0.18 * (1 - p) - out_t * mast_cap * 0.08)
                X, Y = int(mx + lx + ox), int(my + ly + oy)
                h_, w_ = sp.shape
                xa, ya, xb, yb = max(X, 0), max(Y, 0), min(X + w_, W), min(Y + h_, H)
                if xb <= xa or yb <= ya:
                    continue
                al = (sp[ya - Y:yb - Y, xa - X:xb - X] * fade)[..., None]
                base[ya:yb, xa:xb] = base[ya:yb, xa:xb] * (1 - al) + mast_rgb * al
            out = base * (1 - P_a[..., None]) + P_rgb * P_a[..., None]
            fa = fr[..., 3:4].astype(np.float32) / 255
            if fa.max() > 0:
                out = out * (1 - fa) + fr[..., :3].astype(np.float32) / 255 * fa
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out
