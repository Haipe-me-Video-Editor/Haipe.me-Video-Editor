"""Green screen: the speaker cut out and set over a full-frame background: a screenshot / image from the spec
(an app screen you supply), or a built-in brand backdrop (an app-style page with headline, body
and a task list from the spec; a market-style chart page). Light wrap, a matched soft shadow and a slight colour
match keep it from looking pasted; the background drifts in slowly (parallax)."""
import html
import math

import cv2
import numpy as np
from PIL import Image

from . import _cutkit as K

NAME = "green_screen"
DOC = ("Speaker cut out over a full-frame backdrop: a supplied screenshot (`image`) or a built-in brand page "
       "(app page with headline/body/items, or a market chart page). For 'here is the app / the chart' moments.")
BEST_FOR = ["product", "finance", "any"]
DUR = (1.5, 10)
PARAMS = {
    "image": None,         # a screenshot / image path (project, repo or absolute); overrides the built-in backdrop
    "backdrop": "auto",    # auto / app / chart / plain (auto: chart for a market data_look, else app)
    "text": "",            # headline on the built-in page (\\N for a line break)
    "hi": [],              # headline words drawn in the accent colour
    "body": "",            # one or two lines under the headline
    "items": [],           # up to 3 short rows on the app page (the first is highlighted as the current one)
    "tag": "",             # small pill above the headline ("TODAY", "NEW")
    "brand": None,         # name in the window bar (default the style's name)
    "pair": "BTC / USD",   # chart page label
    "value": "",           # chart page big number, only if the spec has a real one (never invented)
    "change": "",          # chart page change pill, e.g. "+2.4%" (only from the spec)
    "trend": "up",         # chart page direction: up / down
    "scale": None,         # speaker size; default puts the head top ~55% down the frame
    "place": "front",      # front: smaller, head halfway down, a presenter before the screen; stay: the speaker
                           # keeps their size and place in the shot and only the background changes
    "side": "center",      # left / center / right
    "theme": "light",      # app page: light (white window on a brand frame) or dark
    "zoom": 0.05,          # slow background push-in over the window (0 = still)
    "wrap": 0.55,          # light wrap strength
    "shadow": 0.5,         # shadow strength
    "match": 0.14,         # colour match of the speaker to the backdrop
}

HEAD_TOP = 0.5   # where the top of the head lands (the page keeps its words above this)
FACE_W = 0.41     # the face's width after scaling, fraction of the frame width


def placement(W, H, box, face, scale, side, place="front"):
    """Scale and offset for the speaker: face about FACE_W wide, head top at HEAD_TOP, centred on `side`; the
    body runs off the bottom of the frame like a presenter standing in front of the screen. `place="stay"` leaves
    the speaker exactly where the shot has them."""
    if place == "stay":
        return K.IDENTITY.copy(), 1.0
    if face:
        fx0, fy0, fx1, fy1 = face
        fw, top = (fx1 - fx0), fy0 - 0.28 * (fy1 - fy0)  # landmarks stop at the forehead; the skull is higher
        cx = (fx0 + fx1) / 2
    else:
        fw, top, cx = 0.4 * W, box[1] * H, (box[0] + box[2]) / 2 * W
    top = max(top, box[1] * H)
    s = float(scale or np.clip(FACE_W * W / max(fw, 1), 0.4, 1.0))
    target = {"left": 0.4, "center": 0.5, "right": 0.6}[side] * W
    tx = target - s * cx
    ty = HEAD_TOP * H - s * top
    ty = max(ty, H - s * H) if box[3] > 0.98 else ty  # a body cut by the frame bottom must still reach it
    return np.array([[s, 0, tx], [0, s, ty]], np.float32), s


def render(ctx):
    p = {k: ctx.param(k, v) for k, v in PARAMS.items()}
    W, H, fps = ctx.W, ctx.H, ctx.fps
    cm = K.clean_mattes(ctx)
    occ = K.occupancy(K.small_mattes(ctx, every=2, scale=4), 50)
    box = K.bbox(occ) or (0.15, 0.1, 0.85, 1.0)
    face = K.face_box(ctx)
    side = p["side"] if p["side"] in ("left", "right", "center") else "center"
    M_t, s = placement(W, H, box, face, p["scale"], side, p["place"])
    cut = {"left": box[0] < 0.02, "right": box[2] > 0.98}
    # straight cut edges (shoulders running out of the original frame) that now land mid-frame melt away
    lands_left = M_t[0, 2] > 2 and cut["left"]
    lands_right = M_t[0, 2] + s * W < W - 2 and cut["right"]

    backdrop = background_source(ctx, p)
    sp_in, T_IN, T_OUT = K.spring("snappy"), 0.6, 0.32
    with ctx.writer() as write:
        for i, (frame, bg, fa) in enumerate(zip(ctx.frames(), backdrop, ctx.mattes())):
            t = i / fps
            k = sp_in(t / T_IN) * (1 - K.ease_in((t - (ctx.dur - T_OUT)) / (T_OUT - 1 / fps), 2.5))
            M = K.lerp_m(K.IDENTITY, M_t, k)
            bmix = float(K.smoothstep(0.0, 0.45, k))
            A = K.tighten(K.fine_alpha(cm[i], fa))
            if bmix <= 0.002:
                write(frame)
                continue
            fade_w = 0.12 * W * min(1.0, k * 1.5)
            A_f = K.edge_fade(A, {"left": lands_left, "right": lands_right}, fade_w) if fade_w > 1 else A
            rgb = K.decontaminate(frame, A).astype(np.uint8)
            pr = K.warp(rgb, M, W, H)
            a = K.warp(A_f, M, W, H)
            base = K.over8(frame, bg, np.full((H, W), bmix, np.float32)) if bmix < 1 else bg
            out = composite(base, pr, a, p, W, H, strength=bmix)
            write(out)
    return ctx.out


def composite(bg, pr, a, p, W, H, strength=1.0):
    """Speaker (pr, alpha a, both already placed) over bg with shadow, light wrap and a colour match."""
    # shadow: soft, a little below, like a key light above the camera
    sh = K.shift(K.blur(a, W * 0.03, down=4), 0, W * 0.012)
    out = K.over8(bg, (0, 0, 0), np.clip(sh * p["shadow"] * 0.75 * strength, 0, 0.6) * (1 - a))
    small = cv2.resize(bg, (W // 8, H // 8), interpolation=cv2.INTER_AREA)
    # colour match: pull the speaker a little toward the backdrop's cast (lower half, where they stand)
    lower = small[small.shape[0] // 2:].reshape(-1, 3).astype(np.float32).mean(0)
    cast = lower / max(1.0, lower.mean())
    m = p["match"] * strength
    person = pr.astype(np.float32) * (1 - m + m * np.clip(cast, 0.6, 1.5))[None, None, :]
    # light wrap: the backdrop's light spills over the speaker's edge
    bgb = cv2.resize(cv2.GaussianBlur(small, (0, 0), 3), (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    inner = K.blur(a, W * 0.006, down=2)
    band = np.clip((a - inner) * 2.0, 0, 1) * p["wrap"] * 0.6 * strength
    person = person * (1 - band[..., None]) + np.maximum(person, bgb) * band[..., None]
    return K.over8(out, np.clip(person, 0, 255).astype(np.uint8), a)


# ---- backdrops ------------------------------------------------------------------------------------------------

def background_source(ctx, p):
    """A generator of n opaque RGB backdrop frames."""
    if p["image"]:
        return image_frames(ctx, ctx.asset(p["image"]), p["zoom"])
    kind = p["backdrop"]
    if kind == "auto":
        kind = "chart" if ctx.style.get("data_look") == "market" else "app"
    page = {"app": app_page, "chart": chart_page, "plain": plain_page}.get(kind, app_page)(ctx, p)
    layer = ctx.layer(page, f"gs-{kind}")
    return (f[..., :3] for f in ctx.frames(layer, rgba=True))


def fit_image(img: np.ndarray, W: int, H: int) -> np.ndarray:
    """Cover-fit an image to W x H; one far from 9:16 sits whole (fit to width) over a blurred, dimmed cover."""
    h, w = img.shape[:2]
    ar, target = w / h, W / H
    cover_k = max(W / w, H / h)
    cover = cv2.resize(img, (int(math.ceil(w * cover_k)), int(math.ceil(h * cover_k))), interpolation=cv2.INTER_AREA
                       if cover_k < 1 else cv2.INTER_CUBIC)
    y0, x0 = (cover.shape[0] - H) // 2, (cover.shape[1] - W) // 2
    cover = cover[y0:y0 + H, x0:x0 + W]
    if abs(ar / target - 1) < 0.18:
        return cover
    back = (cv2.GaussianBlur(cover, (0, 0), W * 0.03) * 0.55).astype(np.uint8)
    k = W * 0.9 / w if ar > target else H * 0.62 / h
    fg = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
    fy = int(H * 0.15)
    fx = (W - fg.shape[1]) // 2
    out = back.copy()
    hh = min(fg.shape[0], H - fy)
    out[fy:fy + hh, fx:fx + fg.shape[1]] = fg[:hh]
    return out


def image_frames(ctx, path, zoom: float):
    img = np.asarray(Image.open(path).convert("RGB"))
    W, H = ctx.W, ctx.H
    base = fit_image(img, W, H)
    for i in range(ctx.n):
        z = 1 + zoom * K.ease_out(i / max(1, ctx.n - 1), 1.6)  # a slow push-in that settles
        Mz = np.array([[z, 0, W / 2 * (1 - z)], [0, z, H * 0.35 * (1 - z)]], np.float32)
        yield cv2.warpAffine(base, Mz, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def _colours(ctx, theme: str = "dark"):
    """Page colours from the style. "light" is a white app window on a deep brand-tinted frame (dark clothes
    separate from it); "dark" is the style's own background."""
    st = ctx.style
    bg, ink, acc = K.rgb(st.get("bg", "#101114")), K.rgb(st.get("ink", "#ffffff")), K.rgb(st.get("accent", "#ff7a1a"))
    frame = bg
    if theme == "light":
        ink, surface = K.rgb("#101114"), K.rgb("#fbfbf8")
    else:
        surface = K.mix(bg, ink, 0.06)
    acc_ink = K.hexc(K.rgb("#0b0c0e") if K.luma(acc) > 120 else K.rgb("#ffffff"))
    i3 = tuple(ink.astype(int))
    return {"bg": K.hexc(frame), "ink": K.hexc(ink), "acc": K.hexc(acc), "surface": K.hexc(surface),
            "line": "rgba(%d,%d,%d,.10)" % i3, "muted": "rgba(%d,%d,%d,.58)" % i3,
            "dots": "rgba(255,255,255,.10)", "acc_ink": acc_ink, "glow": "rgba(%d,%d,%d,.30)" % tuple(acc.astype(int)),
            "frame2": K.hexc(K.rgb(st["bg2"]) if st.get("bg2") else K.mix(bg, acc, 0.28)),
            "up": st.get("up", "#22c55e"), "down": st.get("down", "#ef4444"), "theme": theme}


def _headline(text, hi):
    his = {w.lower().strip(".,!?") for w in (hi or [])}
    lines = (text or "").split("\\N")
    out = []
    for line in lines:
        words = "".join(f"<span class='w{' hi' if w.lower().strip('.,!?') in his else ''}'>{html.escape(w)}</span> "
                        for w in line.split())
        out.append(f"<div class='hl'>{words}</div>")
    return "".join(out)


def _dir(text):
    return " dir='rtl'" if K.has_arabic(text or "") else ""


BASE_CSS = """
#stage{position:absolute;inset:0;background:linear-gradient(165deg,%(frame2)s 0%%,%(bg)s 46%%,%(bg)s 60%%,%(frame2)s 100%%);
  transform-origin:50%% 35%%;will-change:transform}
#stage:before{content:"";position:absolute;inset:0;
  background:radial-gradient(60%% 38%% at 88%% 6%%,%(glow)s,transparent 70%%),
             radial-gradient(55%% 30%% at 6%% 96%%,%(glow)s,transparent 70%%)}
#dots{position:absolute;inset:0;opacity:.6;
  background-image:radial-gradient(%(dots)s 1.6px,transparent 1.8px);background-size:36px 36px}
"""


def app_page(ctx, p):
    c = _colours(ctx, p.get("theme") or "light")
    W, H = ctx.W, ctx.H
    name = str(ctx.style.get("name", "app"))
    brand = html.escape(p["brand"] or ("app" if name == "default" else name))
    tag = p["tag"]
    items = [str(x) for x in (p["items"] or [])][:3]
    rows = "".join(
        f"<div class='row{' done' if j == 0 else ''}'{_dir(t)}><span class='ck'><i></i></span>"
        f"<span class='rt'>{html.escape(t)}</span></div>" for j, t in enumerate(items))
    body = p["body"]
    left, right = int(W * 0.06), int(W * 0.14)
    css = BASE_CSS % c + f"""
#card{{position:absolute;left:{left}px;right:{right}px;top:{int(H * 0.125)}px;height:{int(H * 0.665)}px;
  background:{c['surface']};border:1.5px solid {c['line']};border-radius:40px;
  box-shadow:0 40px 90px rgba(0,0,0,.45);overflow:hidden}}
#bar{{height:84px;display:flex;align-items:center;padding:0 34px;border-bottom:1.5px solid {c['line']};
  font-size:28px;letter-spacing:.02em;color:{c['muted']}}}
#bar i{{width:16px;height:16px;border-radius:50%;background:{c['line']};margin-right:12px;display:inline-block}}
#bar b{{margin-left:auto;margin-right:auto;transform:translateX(-40px);color:{c['ink']};font-weight:700}}
#content{{padding:46px 54px 0}}
#tag{{display:inline-block;background:{c['acc']};color:{c['acc_ink']};font-size:26px;font-weight:700;
  letter-spacing:.12em;padding:12px 22px;border-radius:999px;margin-bottom:28px}}
.hl{{font-size:{int(W * 0.07)}px;font-weight:700;line-height:1.06;letter-spacing:-.02em;color:{c['ink']}}}
.hl .w{{display:inline-block}}
.hl .hi{{color:{c['acc'] if c['theme'] == 'dark' else c['ink']};
  background:{'none' if c['theme'] == 'dark' else f"linear-gradient(transparent 62%, {c['acc']} 62%, {c['acc']} 92%, transparent 92%)"}}}
#body{{margin-top:22px;font-size:33px;line-height:1.4;color:{c['muted']};max-width:92%}}
#rows{{margin-top:30px}}
.row{{display:flex;align-items:center;gap:22px;height:70px;border-top:1.5px solid {c['line']};font-size:32px;
  color:{c['muted']}}}
.row.done{{color:{c['ink']}}}
.ck{{width:40px;height:40px;border-radius:50%;border:2.5px solid {c['line']};display:flex;align-items:center;
  justify-content:center;font-size:24px;flex:none}}
.row.done .ck{{border-color:{c['acc']}}}
.row.done .ck i{{width:20px;height:20px;border-radius:50%;background:{c['acc']}}}
.row.done{{font-weight:700}}
"""
    body_html = ("<div id='content'>" + (f"<div id='tag'{_dir(tag)}>{html.escape(tag)}</div>" if tag else "")
                 + f"<div id='hl'{_dir(p['text'])}>{_headline(p['text'], p['hi'])}</div>"
                 + (f"<div id='body'{_dir(body)}>{html.escape(body)}</div>" if body else "")
                 + (f"<div id='rows'>{rows}</div>" if rows else "") + "</div>")
    page = (f"<div id='stage'><div id='dots'></div><div id='card'><div id='bar'><i></i><i></i><i></i>"
            f"<b>{brand}</b></div>{body_html}</div></div>")
    js = _stage_js(ctx, p) + """
  springIn(tl, '#card', {y: 90, opacity: 0}, {y: 0, opacity: 1, duration: .8}, 'gentle', .12);
  springIn(tl, '#tag', {scale: .6, opacity: 0}, {scale: 1, opacity: 1, duration: .5}, 'bouncy', .42);
  springIn(tl, '.hl .w', {y: 40, opacity: 0}, {y: 0, opacity: 1, duration: .55, stagger: .06}, 'snappy', .5);
  tl.fromTo('#body', {opacity: 0, y: 16}, {opacity: 1, y: 0, duration: .5, ease: 'power3.out'}, .78);
  springIn(tl, '.row', {x: -30, opacity: 0}, {x: 0, opacity: 1, duration: .5, stagger: .08}, 'snappy', .9);"""
    return ctx.page(page, css, js, bg=c["bg"])


def _stage_js(ctx, p):
    z = float(p["zoom"] or 0)
    return (f"\n  tl.fromTo('#stage', {{scale: 1}}, {{scale: {1 + z:.4f}, duration: {ctx.dur:.3f}, ease: 'sine.out'}}, 0);"
            if z > 0 else "")


def candles(n: int, trend: str, seed: int = 5):
    """A deterministic illustrative candle series (shape only: the page shows no prices unless the spec gives one).
    A random walk with its own drift removed and the asked-for trend put in, so "up" always reads as up."""
    rng = np.random.default_rng(seed)
    j = np.arange(n + 1, dtype=np.float64)
    walk = np.cumsum(rng.normal(0, 2.6, n + 1))
    walk -= np.polyval(np.polyfit(j, walk, 1), j)
    walk += (0.6 if trend != "down" else -0.6) * j + 50
    out = []
    for k in range(n):
        o, c = float(walk[k]), float(walk[k + 1])
        hi = max(o, c) + abs(rng.normal(0, 1.0))
        lo = min(o, c) - abs(rng.normal(0, 1.0))
        out.append((o, hi, lo, c))
    return out


def chart_page(ctx, p):
    c = _colours(ctx)
    W, H = ctx.W, ctx.H
    # the chart ends above the speaker's head (HEAD_TOP); a big value line takes room from it
    cw, ch = int(W * 0.80), int(H * (0.165 - (0.055 if p["value"] else 0)))
    data = candles(26, p["trend"])
    lo = min(d[2] for d in data)
    hi = max(d[1] for d in data)
    sy = lambda v: ch - (v - lo) / (hi - lo) * (ch * 0.86) - ch * 0.07
    step = cw / len(data)
    svg = []
    for g in range(5):
        y = ch * (0.1 + 0.2 * g)
        svg.append(f"<line x1='0' x2='{cw}' y1='{y:.1f}' y2='{y:.1f}' stroke='{c['line']}' stroke-width='1.5'/>")
    for j, (o, h_, l_, cl) in enumerate(data):
        x = step * (j + 0.5)
        col = c["up"] if cl >= o else c["down"]
        top, bot = sy(max(o, cl)), sy(min(o, cl))
        svg.append(f"<g class='cd'><line x1='{x:.1f}' x2='{x:.1f}' y1='{sy(h_):.1f}' y2='{sy(l_):.1f}' "
                   f"stroke='{col}' stroke-width='3'/><rect x='{x - step * 0.3:.1f}' y='{top:.1f}' "
                   f"width='{step * 0.6:.1f}' height='{max(3, bot - top):.1f}' rx='3' fill='{col}'/></g>")
    pts = " ".join(f"{step * (j + 0.5):.1f},{sy(d[3]):.1f}" for j, d in enumerate(data))
    svg.append(f"<polyline id='trend' points='{pts}' fill='none' stroke='{c['acc']}' stroke-width='4' "
               f"stroke-linejoin='round' stroke-linecap='round' opacity='.9'/>")
    path_len = sum(math.hypot(step, sy(b[3]) - sy(a[3])) for a, b in zip(data, data[1:])) + 10
    tabs = "".join(f"<span class='tab{' on' if t == '1D' else ''}'>{t}</span>" for t in ("1H", "4H", "1D", "1W"))
    change = p["change"]
    up = not str(change).strip().startswith("-")
    left = int(W * 0.06)
    css = BASE_CSS % c + f"""
#panel{{position:absolute;left:{left}px;width:{cw + 80}px;top:{int(H * 0.135)}px;height:{int(H * 0.655)}px;
  background:{c['surface']};border:1.5px solid {c['line']};border-radius:36px;box-shadow:0 40px 90px rgba(0,0,0,.45)}}
#head{{padding:40px 40px 0;display:flex;align-items:center;gap:18px}}
#pair{{font-size:34px;font-weight:700;color:{c['ink']};letter-spacing:.02em}}
#chg{{font-size:28px;font-weight:700;padding:8px 16px;border-radius:12px;
  background:{c['up'] if up else c['down']}22;color:{c['up'] if up else c['down']}}}
#val{{padding:14px 40px 0;font-size:{int(W * 0.085)}px;font-weight:700;color:{c['ink']};letter-spacing:-.02em}}
#hl2{{padding:18px 40px 0}}
#hl2 .hl{{font-size:{int(W * 0.06)}px}}
#tabs{{display:flex;gap:10px;padding:26px 40px 10px}}
.tab{{font-size:24px;font-weight:700;color:{c['muted']};padding:10px 18px;border-radius:12px}}
.tab.on{{background:{c['acc']};color:{c['acc_ink']}}}
#chart{{display:block;margin:14px 0 0 40px}}
.hl{{font-weight:700;line-height:1.08;letter-spacing:-.02em;color:{c['ink']}}}
.hl .w{{display:inline-block}} .hl .hi{{color:{c['acc']}}}
"""
    head = (f"<div id='head'><span id='pair'>{html.escape(p['pair'] or '')}</span>"
            + (f"<span id='chg'>{html.escape(str(change))}</span>" if change else "") + "</div>")
    val = f"<div id='val'>{html.escape(str(p['value']))}</div>" if p["value"] else ""
    hl = f"<div id='hl2'{_dir(p['text'])}>{_headline(p['text'], p['hi'])}</div>" if p["text"] else ""
    page = (f"<div id='stage'><div id='dots'></div><div id='panel'>{head}{val}{hl}<div id='tabs'>{tabs}</div>"
            f"<svg id='chart' width='{cw}' height='{ch}' viewBox='0 0 {cw} {ch}'>{''.join(svg)}</svg></div></div>")
    js = _stage_js(ctx, p) + f"""
  springIn(tl, '#panel', {{y: 90, opacity: 0}}, {{y: 0, opacity: 1, duration: .8}}, 'gentle', .12);
  springIn(tl, '#head, #val, #hl2 .w, .tab', {{y: 26, opacity: 0}}, {{y: 0, opacity: 1, duration: .5, stagger: .04}}, 'snappy', .4);
  tl.fromTo('.cd', {{scaleY: 0, opacity: 0, transformOrigin: '50% 100%'}}, {{scaleY: 1, opacity: 1, duration: .35,
    stagger: .03, ease: 'power3.out'}}, .6);
  tl.fromTo('#trend', {{strokeDasharray: {path_len:.0f}, strokeDashoffset: {path_len:.0f}}},
    {{strokeDashoffset: 0, duration: 1.1, ease: 'power2.inOut'}}, .75);"""
    return ctx.page(page, css, js, bg=c["bg"])


def plain_page(ctx, p):
    c = _colours(ctx)
    W, H = ctx.W, ctx.H
    css = BASE_CSS % c + f"""
#hl3{{position:absolute;left:{int(W * 0.08)}px;right:{int(W * 0.16)}px;top:{int(H * 0.2)}px}}
.hl{{font-size:{int(W * 0.09)}px;font-weight:700;line-height:1.04;letter-spacing:-.02em;color:{c['ink']}}}
.hl .w{{display:inline-block}} .hl .hi{{color:{c['acc']}}}
#b3{{margin-top:30px;font-size:36px;line-height:1.4;color:{c['muted']}}}"""
    page = (f"<div id='stage'><div id='dots'></div><div id='hl3'{_dir(p['text'])}>{_headline(p['text'], p['hi'])}"
            + (f"<div id='b3'>{html.escape(p['body'])}</div>" if p["body"] else "") + "</div></div>")
    js = _stage_js(ctx, p) + """
  springIn(tl, '.hl .w', {y: 50, opacity: 0}, {y: 0, opacity: 1, duration: .6, stagger: .07}, 'snappy', .3);
  tl.fromTo('#b3', {opacity: 0}, {opacity: 1, duration: .5, ease: 'power3.out'}, .7);"""
    return ctx.page(page, css, js, bg=c["bg"])
