"""Pull-back reveal: the camera pulls back out of the shot to show it was playing inside an app all along (window
chrome, a step list, a timeline, a progress bar) floating on a clean desk with a deep shadow and a slight 3D swing.
Then it holds (the list ticks off, the playhead runs) and, by default, pushes back in so the edit continues.

Two looks: `editor` (an editing app: steps on the left, the clip, a timeline with the real time code) and `trading`
(a live-session panel: topics, a LIVE badge, a session progress bar). `ui: auto` picks trading for a style whose `data_look` is market.
The UI is a HyperFrames layer drawn at rest with a transparent hole where the video sits; the camera move (one
homography per frame) is applied to the layer and the footage together, so they never drift apart.
"""
import html
import math

import numpy as np

from . import _camera as cam

NAME = "pull_back"
DOC = ("Pull back from the shot to reveal it playing inside an app window (editor or trading-desk look), hold while "
       "its step list ticks off, then push back in. For 'here is how I made this' / behind-the-scenes beats.")
BEST_FOR = ["product", "finance", "corporate", "any"]
DUR = (2.4, 12)
PARAMS = {
    "title": None,       # window title; default "Untitled project" (editor) / "Live session" (trading)
    "items": None,       # 2-6 short lines for the side list; default generic steps / topics
    "ui": "auto",        # auto | editor | trading
    "end": "push_in",    # push_in (back to full frame by the end) | hold (end the window on a cut)
    "pull": 1.1,         # pull-back length, s
    "push": 0.7,         # push-in length, s
    "tilt": 7.0,         # 3D swing during the moves, degrees (0 = flat)
    "badge": None,       # title-bar chip; default "Export" (editor) / "For education only" (trading)
}
DEFAULT_ITEMS = {"editor": ["Transcript", "Best takes", "Captions", "Colour", "Export"],
                 "trading": ["Market overview", "Key levels", "Risk check", "Questions"]}
DEFAULT_TITLE = {"editor": "Untitled project", "trading": "Live session"}


# ---- geometry -----------------------------------------------------------------------------------------------------
def layout(W: int, H: int) -> dict:
    """Rest layout in output pixels. The pane has the frame's aspect, so at zoom W/pw it is exactly the frame."""
    pad = round(0.02 * W)
    x0, y0, w = round(0.059 * W), round(0.134 * H), round(0.815 * W)
    title_h = round(0.054 * W)
    g = math.gcd(W, H)  # the pane is a whole multiple of the frame's aspect, so the zoom maps it exactly
    m = max(1, round(0.47 * W / (W // g)))
    pw, ph = m * W // g, m * H // g
    px, py = x0 + w - pad - pw, y0 + title_h + pad
    th = round(0.095 * H)
    h = title_h + pad + ph + pad + th + pad
    return {"win": (x0, y0, w, h), "pane": (px, py, pw, ph), "title_h": title_h, "pad": pad,
            "side": (x0 + pad, py, px - pad - (x0 + pad), ph), "tl": (px - (px - x0) + pad, py + ph + pad,
                                                                     w - 2 * pad, th)}


def pull_k(t: float, dur: float, pull: float, push: float, end: str = "push_in") -> float:
    """Camera progress: 0 = inside the pane (the original frame), 1 = at rest. Spring out, eased back in."""
    k = cam.spring_ease("gentle")(t / pull) if t > 0 else 0.0
    if end == "push_in" and t > dur - push:
        k = min(k, 1 - cam.ease("inout", (t - (dur - push)) / push))
    return k


def times(dur: float, pull: float, push: float, end: str) -> tuple:
    """(pull, push) shrunk to fit short windows, leaving at least 35% of the window to hold."""
    budget = dur * 0.65
    tot = pull + (push if end == "push_in" else 0)
    if tot > budget:
        f = budget / tot
        pull, push = pull * f, push * f
    return pull, push


def zoom0(lay: dict, W: int, H: int) -> float:
    return W / lay["pane"][2]


def plane_matrix(k: float, lay: dict, W: int, H: int, tilt_deg: float = 0.0) -> np.ndarray:
    """3x3 homography from rest (plane) coordinates to the output for camera progress k."""
    Z0 = zoom0(lay, W, H)
    px, py, pw, ph = lay["pane"]
    pc = np.array([px + pw / 2, py + ph / 2])
    c = np.array([W / 2, H / 2])
    F = (Z0 * pc - c) / (Z0 - 1)  # the fixed point of the zoom: pc lands on the centre at Z0, rest at 1
    s = Z0 ** (1 - k)
    M = np.array([[s, 0, F[0] * (1 - s)], [0, s, F[1] * (1 - s)], [0, 0, 1]], np.float64)
    th = math.radians(tilt_deg) * math.sin(math.pi * min(max(k, 0.0), 1.0))
    if abs(th) < 1e-5:
        return M
    x0, y0, w, h = lay["win"]
    o = M @ np.array([x0 + w / 2, y0 + h / 2, 1.0])
    f = 2.4 * W  # a long lens: gentle perspective
    R = np.array([[f * math.cos(th), 0, 0], [0, f, 0], [math.sin(th), 0.25 * math.sin(th), f]])
    T, Ti = np.eye(3), np.eye(3)
    T[:2, 2], Ti[:2, 2] = o[:2], -o[:2]
    P = T @ R @ Ti
    return P / P[2, 2] @ M


# ---- the UI layer -------------------------------------------------------------------------------------------------
def _hex(c: str) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a: str, b: str, k: float) -> str:
    x, y = _hex(a), _hex(b)
    return "#" + "".join(f"{round(x[i] + (y[i] - x[i]) * k):02x}" for i in range(3))


def _rgba(c: str, a: float) -> str:
    r, g, b = _hex(c)
    return f"rgba({r},{g},{b},{a})"


def palette(style: dict, ui: str) -> dict:
    bg, ink, acc = style.get("bg", "#101114"), style.get("ink", "#ffffff"), style.get("accent", "#ff7a1a")
    base = _mix(bg, style["bg2"], 0.35) if style.get("bg2") else bg
    return {"desk": bg, "win": _mix(base, ink, 0.055), "side": _mix(base, ink, 0.03), "ink": ink, "acc": acc,
            "live": style.get("live") or style.get("down") or "#ef4444", "line": _rgba(ink, 0.09),
            "muted": _rgba(ink, 0.5), "faint": _rgba(ink, 0.22),
            "on_acc": "#0b0d10" if sum(_hex(acc)) > 380 else "#ffffff"}


CHECK = ("<svg viewBox='0 0 24 24'><path d='M6 12.5l4 4 8-9' fill='none' stroke='currentColor' stroke-width='3' "
         "stroke-linecap='round' stroke-linejoin='round'/></svg>")


def page_parts(ctx, ui: str, title: str, items: list, badge: str, lay: dict, pull: float, push: float,
               end: str, logo: bool) -> tuple:
    """(body, css, js) of the UI layer."""
    W, d = ctx.W, ctx.dur
    pal = palette(ctx.style, ui)
    x0, y0, w, h = lay["win"]
    px, py, pw, ph = lay["pane"]
    _, sy, sw, sh = lay["side"]
    _, ty, tw, tht = lay["tl"]
    th_, pad = lay["title_h"], lay["pad"]
    u = W / 1080  # type scale
    R = round(28 * u)
    pr = round(16 * u)
    esc = html.escape
    # rows
    rows = []
    for i, it in enumerate(items):
        lead = (f"<span class='num'>{i + 1:02d}</span>" if ui == "trading" else f"<span class='ck'>{CHECK}</span>")
        rows.append(f"<div class='row' id='r{i}'><b class='on'></b>{lead}<span class='tx' dir='auto'>{esc(it)}</span>"
                    "</div>")
    if ui == "trading":
        head = f"<div class='sh'><span>Today's topics</span><span class='cnt' id='cnt'>0/{len(items)}</span></div>"
        brand = ("<img class='logo' src='logo.jpg'>" if logo else "<span class='mark'></span>")
        bar_l = f"<div class='bl'>{brand}<span class='ttl' dir='auto'>{esc(title)}</span></div>"
        bar_r = f"<div class='pill mute'>{esc(badge)}</div>"
        segs = "".join(f"<div class='sg'><div class='seg'><div class='fill'></div></div><div class='sl' dir='auto'>"
                       f"{esc(it)}</div></div>" for it in items)
        bottom = (f"<div id='tl'><div class='tlh'><span>Session</span><span class='tc' id='tc'>00:00</span></div>"
                  f"<div class='segs'>{segs}</div></div>")
        over = "<div id='pov'><div class='lb'><i></i>LIVE</div></div>"
    else:
        head = f"<div class='sh'><span>Steps</span><span class='cnt' id='cnt'>0/{len(items)}</span></div>"
        bar_l = ("<div class='bl'><span class='dot' style='background:#ff5f57'></span><span class='dot' "
                 "style='background:#febc2e'></span><span class='dot' style='background:#28c840'></span></div>")
        bar_r = f"<div class='pill acc'>{esc(badge)}</div>"
        rng = np.random.default_rng(7)
        clips = [0.22, 0.17, 0.27, 0.14, 0.2]
        vt = "".join(f"<div class='cl' style='width:{c * 100:.1f}%'></div>" for c in clips)
        bars = "".join(f"<i style='height:{18 + 82 * abs(math.sin(i * 0.37)) * rng.uniform(0.35, 1):.0f}%'></i>"
                       for i in range(96))
        bottom = (f"<div id='tl'><div class='tlh'><span class='tc' id='tc'>00:00</span><span class='tc2'>"
                  f"{int(d // 60):02d}:{int(d) % 60:02d}</span></div><div class='ruler'></div>"
                  f"<div class='trk v'>{vt}</div><div class='trk a'>{bars}</div><div class='ph' id='ph'></div></div>")
        over = ""
    title_html = (f"<div class='ttlc' dir='auto'>{esc(title)}</div>" if ui == "editor" else "")
    body = f"""<div id='win'>
  <div id='hole'></div><div id='edge'></div>{over}
  <div id='bar'>{bar_l}{title_html}{bar_r}</div>
  <div id='side'>{head}{''.join(rows)}</div>
  {bottom}
</div>"""
    fs = round(25 * u)
    css = f"""
#win{{position:absolute;left:{x0}px;top:{y0}px;width:{w}px;height:{h}px;border-radius:{R}px;overflow:hidden;
  box-shadow:0 46px 120px rgba(0,0,0,.55),0 14px 34px rgba(0,0,0,.35),0 0 0 1px {pal['line']};font-family:"BrandLT","BrandAR",sans-serif;color:{pal['ink']}}}
#hole{{position:absolute;left:{px - x0}px;top:{py - y0}px;width:{pw}px;height:{ph}px;border-radius:0;
  box-shadow:0 0 0 {2 * h}px {pal['win']}}}
#edge{{position:absolute;left:{px - x0}px;top:{py - y0}px;width:{pw}px;height:{ph}px;border-radius:0;
  box-shadow:inset 0 0 0 1px {pal['line']};opacity:0}}
#bar{{position:absolute;left:0;top:0;right:0;height:{th_}px;display:flex;align-items:center;justify-content:space-between;
  padding:0 {pad}px;box-sizing:border-box;border-bottom:1px solid {pal['line']};background:{pal['win']};z-index:2}}
.bl{{display:flex;align-items:center;gap:{round(9 * u)}px}}
.dot{{width:{round(14 * u)}px;height:{round(14 * u)}px;border-radius:50%;opacity:.85}}
.ttlc{{position:absolute;left:0;right:0;text-align:center;font-size:{round(21 * u)}px;font-weight:600;pointer-events:none}}
.ttl{{font-size:{round(22 * u)}px;font-weight:700;letter-spacing:.01em}}
.logo{{width:{round(34 * u)}px;height:{round(34 * u)}px;border-radius:50%;object-fit:cover}}
.mark{{width:{round(14 * u)}px;height:{round(14 * u)}px;border-radius:4px;background:{pal['acc']}}}
.pill{{font-size:{round(18 * u)}px;font-weight:700;padding:{round(7 * u)}px {round(16 * u)}px;border-radius:999px;
  display:flex;align-items:center;gap:{round(8 * u)}px;letter-spacing:.02em}}
.pill.acc{{background:{pal['acc']};color:{pal['on_acc']}}}
.pill.mute{{background:{_rgba(pal['ink'], 0.07)};color:{pal['muted']};font-weight:600}}
.pill.live{{background:{_rgba(pal['live'], 0.16)};color:{pal['live']}}}
.pill.live i,.lb i{{width:{round(10 * u)}px;height:{round(10 * u)}px;border-radius:50%;background:{pal['live']};display:block}}
#side{{position:absolute;left:{pad}px;top:{sy - y0}px;width:{sw}px;height:{sh}px;z-index:2}}
.sh{{display:flex;justify-content:space-between;align-items:center;font-size:{round(17 * u)}px;font-weight:600;
  text-transform:uppercase;letter-spacing:.08em;color:{pal['muted']};margin:{round(6 * u)}px 0 {round(16 * u)}px}}
.cnt{{font-family:"PlexMono";letter-spacing:0;color:{pal['acc']};background:{_rgba(pal['acc'], 0.12)};
  padding:{round(3 * u)}px {round(10 * u)}px;border-radius:999px;text-transform:none}}
.row{{display:flex;align-items:center;gap:{round(14 * u)}px;padding:{round(13 * u)}px {round(12 * u)}px;
  border-radius:{round(14 * u)}px;font-size:{fs}px;line-height:1.2;color:{pal['muted']};margin-bottom:{round(6 * u)}px;
  position:relative}}
.row .tx{{flex:1;min-width:0}}
.row b.on{{position:absolute;inset:0;border-radius:inherit;background:{_rgba(pal['ink'], 0.07)};opacity:0}}
.row b.on::before{{content:"";position:absolute;left:0;top:24%;bottom:24%;width:3px;border-radius:3px;
  background:{pal['acc'] if ui == 'trading' else 'transparent'}}}
.row>span{{position:relative}}
.ck{{flex:none;width:{round(30 * u)}px;height:{round(30 * u)}px;border-radius:50%;box-shadow:inset 0 0 0 2px {pal['faint']};
  display:grid;place-items:center;color:{pal['on_acc']};position:relative}}
.ck svg{{width:72%;height:72%;opacity:0;transform:scale(.4)}}
.ck::after{{content:"";position:absolute;inset:0;border-radius:50%;background:{pal['acc']};transform:scale(0);
  transform:scale(var(--f,0));z-index:-1}}
.ck{{isolation:isolate}}
.num{{flex:none;font-family:"PlexMono";font-size:{round(18 * u)}px;color:{pal['acc']};width:{round(30 * u)}px}}
#tl{{position:absolute;left:{pad}px;top:{ty - y0}px;width:{tw}px;height:{tht}px;border-radius:{round(16 * u)}px;
  background:{pal['side']};box-shadow:inset 0 0 0 1px {pal['line']};z-index:2;overflow:hidden}}
.tlh{{display:flex;justify-content:space-between;align-items:center;padding:{round(12 * u)}px {round(18 * u)}px 0;
  font-size:{round(17 * u)}px;color:{pal['muted']};font-weight:600;text-transform:uppercase;letter-spacing:.08em}}
.tc,.tc2{{font-family:"PlexMono";letter-spacing:0;font-weight:500}}
.tc{{color:{pal['ink']}}}
.ruler{{margin:{round(10 * u)}px {round(18 * u)}px 0;height:{round(10 * u)}px;
  background:repeating-linear-gradient(90deg,{pal['faint']} 0 1px,transparent 1px {round(24 * u)}px)}}
.trk{{margin:{round(8 * u)}px {round(18 * u)}px 0;display:flex;gap:{round(4 * u)}px;height:{round(44 * u)}px}}
.trk.v .cl{{height:100%;border-radius:{round(8 * u)}px;background:linear-gradient(180deg,{_rgba(pal['acc'], 0.34)},
  {_rgba(pal['acc'], 0.18)});box-shadow:inset 0 0 0 1px {_rgba(pal['acc'], 0.55)}}}
.trk.a{{height:{round(34 * u)}px;align-items:center;gap:{round(2 * u)}px}}
.trk.a i{{flex:1;background:{pal['faint']};border-radius:2px}}
.segs{{display:flex;gap:{round(12 * u)}px;margin:{round(40 * u)}px {round(18 * u)}px 0}}
.sg{{flex:1;min-width:0}}
.sl{{margin-top:{round(12 * u)}px;font-size:{round(16 * u)}px;color:{pal['muted']};white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}}
.seg{{height:{round(14 * u)}px;border-radius:999px;background:{_rgba(pal['ink'], 0.1)};overflow:hidden}}
.seg .fill{{height:100%;width:0;background:{pal['acc']};border-radius:999px}}
.ph{{position:absolute;top:{round(44 * u)}px;bottom:{round(10 * u)}px;left:{round(18 * u)}px;width:2px;background:{pal['acc']};
  box-shadow:0 0 0 1px {_rgba(pal['desk'], 0.4)}}}
.ph::before{{content:"";position:absolute;left:-{round(7 * u)}px;top:-{round(4 * u)}px;width:{round(16 * u)}px;
  height:{round(10 * u)}px;border-radius:3px;background:{pal['acc']}}}
#pov{{position:absolute;left:{px - x0}px;top:{py - y0}px;width:{pw}px;height:{ph}px;pointer-events:none;opacity:0}}
.lb{{position:absolute;left:{round(16 * u)}px;top:{round(16 * u)}px;display:flex;align-items:center;gap:{round(8 * u)}px;
  background:{pal['live']};color:#fff;font-weight:800;font-size:{round(17 * u)}px;letter-spacing:.06em;
  padding:{round(6 * u)}px {round(12 * u)}px;border-radius:{round(8 * u)}px}}
.lb i{{background:#fff}}"""
    # timing: items arrive during the pull, then tick off one by one through the hold
    t_in = 0.25 * pull
    hold_end = d - (push if end == "push_in" else 0.15)
    t0 = max(pull * 0.95, t_in + 0.4)
    step = max(0.18, (hold_end - t0 - 0.2) / max(1, len(items)))
    track = tw - round(36 * u)
    js = [(f"tl.fromTo('#hole,#edge', {{borderRadius: 0}}, {{borderRadius: {pr}, duration: {0.5 * pull:.3f}, "
           f"ease: 'power2.out'}}, 0.02);"),
          f"tl.to('#edge,#pov', {{opacity: 1, duration: {0.4 * pull:.3f}, ease: 'power1.out'}}, {0.1 * pull:.3f});",
          (f"springIn(tl, '#side .row, #side .sh', {{x: -{round(18 * u)}, opacity: 0}}, "
           f"{{x: 0, opacity: 1, duration: .6, stagger: .06}}, 'snappy', {t_in:.3f});"),
          (f"if (document.getElementById('ph')) tl.fromTo('#ph', {{x: 0}}, {{x: {track}, duration: {d:.3f}, "
           "ease: 'none'}, 0);"),
          "const clock = {v: 0}, tcEl = document.getElementById('tc'), cnt = document.getElementById('cnt');",
          "const fmt = v => String(Math.floor(v / 60)).padStart(2, '0') + ':' + String(Math.floor(v % 60)).padStart(2, '0');",
          f"const DONE = {[round(t0 + (i + 1) * step, 3) for i in range(len(items))]};",
          # one clock drives the time code and the done count, so any frame rendered in any order is right
          (f"tl.fromTo(clock, {{v: 0}}, {{v: {d:.3f}, duration: {d:.3f}, ease: 'none', onUpdate: () => {{ "
           f"tcEl.textContent = fmt(clock.v); cnt.textContent = DONE.filter(x => x <= clock.v).length + "
           f"'/{len(items)}'; "
           "}}, 0);")]
    for i in range(len(items)):
        a = t0 + i * step  # item i is active from a, done at a + step
        js.append(f"tl.to('#r{i}', {{color: '{pal['ink']}', duration: .25, ease: 'power1.out'}}, {a:.3f});")
        js.append(f"tl.fromTo('#r{i} b.on', {{opacity: 0}}, {{opacity: 1, duration: .25, ease: 'power1.out'}}, {a:.3f});")
        js.append(f"tl.to('#r{i} b.on', {{opacity: 0, duration: .3, ease: 'power1.inOut'}}, {a + step:.3f});")
        if ui == "editor":
            js.append(f"tl.fromTo('#r{i} .ck', {{'--f': 0}}, {{'--f': 1, duration: .28, ease: 'back.out(2)'}}, "
                      f"{a + step - 0.12:.3f});")
            js.append(f"springIn(tl, '#r{i} .ck svg', {{scale: .4, opacity: 0}}, {{scale: 1, opacity: 1, "
                      f"duration: .45}}, 'bouncy', {a + step - 0.05:.3f});")
        else:
            js.append(f"tl.fromTo('.sg:nth-child({i + 1}) .fill', {{width: '0%'}}, {{width: '100%', "
                      f"duration: {step:.3f}, ease: 'none'}}, {a:.3f});")
    if end == "push_in":
        js.append(f"tl.to('#hole,#edge', {{borderRadius: 0, duration: {0.6 * push:.3f}, ease: 'power2.in'}}, "
                  f"{d - 0.6 * push:.3f});")
        js.append(f"tl.to('#edge,#pov', {{opacity: 0, duration: {0.4 * push:.3f}, ease: 'power1.in'}}, "
                  f"{d - push:.3f});")
    return body, css, "\n  ".join(js)


def desk(ctx, lay: dict) -> np.ndarray:
    """The clean background: the style's base colour, a soft light behind the window, a vignette, fine grain."""
    W, H = ctx.W, ctx.H
    pal = palette(ctx.style, "editor")
    base = cam.hex_rgb(pal["desk"])
    lift = cam.hex_rgb(_mix(pal["desk"], pal["acc"], 0.10))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    x0, y0, w, h = lay["win"]
    g = np.exp(-(((xx - (x0 + w / 2)) / (0.75 * W)) ** 2 + ((yy - (y0 + h * 0.4)) / (0.5 * H)) ** 2))
    vig = 1 - 0.35 * np.clip(((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2 - 0.05, 0, 1) * 2
    img = (base + (lift - base) * g[..., None]) * vig[..., None]
    img += np.random.default_rng(1).normal(0, 1.6, (H, W, 1)).astype(np.float32)
    return np.clip(img + 0.5, 0, 255).astype(np.uint8)


def render(ctx):
    import cv2
    W, H, fps = ctx.W, ctx.H, ctx.fps
    ui = ctx.param("ui", PARAMS["ui"])
    if ui == "auto":
        ui = "trading" if ctx.style.get("data_look") == "market" else "editor"
    if ui not in ("editor", "trading"):
        raise ValueError("pull_back ui is auto, editor or trading")
    end = ctx.param("end", PARAMS["end"])
    if end not in ("push_in", "hold"):
        raise ValueError("pull_back end is push_in or hold")
    items = list(ctx.param("items") or DEFAULT_ITEMS[ui])[:6]
    title = ctx.param("title") or DEFAULT_TITLE[ui]
    badge = ctx.param("badge") or ("For education only" if ui == "trading" else "Export")
    tilt = float(ctx.param("tilt", PARAMS["tilt"]))
    pull, push = times(ctx.dur, float(ctx.param("pull", PARAMS["pull"])), float(ctx.param("push", PARAMS["push"])), end)
    lay = layout(W, H)
    assets = {}
    if ui == "trading" and ctx.style.get("logo"):
        try:
            assets["logo.jpg"] = ctx.asset(ctx.style["logo"])
        except FileNotFoundError:
            pass
    body, css, js = page_parts(ctx, ui, title, items, badge, lay, pull, push, end, bool(assets))
    layer = ctx.layer(ctx.page(body, css, js), "pullback-ui", assets)
    bg = desk(ctx, lay)
    px, py, pw, ph = lay["pane"]
    A = np.array([[pw / W, 0, px], [0, ph / H, py], [0, 0, 1]], np.float64)  # the frame -> the pane, at rest
    ones = np.full((H, W), 255, np.uint8)
    with ctx.writer() as wr:
        for i, (f, ui_f) in enumerate(zip(ctx.frames(), ctx.frames(layer, rgba=True))):
            k = pull_k(i / fps, (ctx.n - 1) / fps, pull, push, end)
            if k <= 1e-4:
                wr(f)
                continue
            P = plane_matrix(k, lay, W, H, tilt)
            Hv = P @ A
            vid = cv2.warpPerspective(np.ascontiguousarray(f), Hv, (W, H), flags=cv2.INTER_LINEAR,
                                      borderMode=cv2.BORDER_REPLICATE)
            vm = cv2.warpPerspective(ones, Hv, (W, H), flags=cv2.INTER_LINEAR).astype(np.float32) / 255
            out = cv2.blendLinear(bg, vid, 1 - vm, vm)
            u = cv2.warpPerspective(np.ascontiguousarray(ui_f), P, (W, H), flags=cv2.INTER_LINEAR)
            ua = u[..., 3].astype(np.float32) / 255
            wr(cv2.blendLinear(out, np.ascontiguousarray(u[..., :3]), 1 - ua, ua))
    return ctx.out
