"""UI world: the app's interface floats in the space around the speaker.

A command box (clip thumbnails dropped into it, a prompt typed out, the send button pressed by a cursor) floats in
front of the speaker's chest; secondary cards ("Drop files here") hang in the room behind them, partly hidden by
their head; the room dims and softens so the UI reads as its own plane. Short action words ("DROP", "TRIGGER")
land as captions on the beats. Everything enters on springs, drifts with parallax (near moves more than far) and
leaves together. Thumbnails are stills from the footage itself.
"""
import json
import math

from . import _spatial as sp

NAME = "ui_world"
DOC = ("The product UI floats around the speaker: a command box with clip thumbnails dropping in, a typed prompt "
       "and a pressed button in front of the chest, cards behind the head, action words (DROP, TRIGGER) on the beats. "
       "For 'drop your clips and hit go' / how-the-app-works moments.")
BEST_FOR = ["product", "any"]
DUR = (2.5, 6)
CAPTIONS = "hide"  # the effect fills the caption band; captions return after the window
PARAMS = {
    # panels: {kind: card|input|thumbs|button, title, text, icon}. input/thumbs/button merge into one command box
    # in front of the chest (thumbs become its attachments, button its send button); cards hang behind the head.
    "panels": [{"kind": "card", "title": "Drop files here", "text": "MP4 · MOV"},
               {"kind": "thumbs", "title": "Raw clips"},
               {"kind": "input", "text": "/video cut these into one reel"},
               {"kind": "button", "text": ""}],
    "words": ["DROP", "TRIGGER"],  # action captions: the 1st lands with the thumbnails, the 2nd on the button press
    "images": [],          # thumbnail image paths (screenshots); default stills grabbed from the footage
    "stills_from": None,   # a video to grab the thumbnails from (e.g. the full source); default the window itself
    "n_thumbs": 4,
    "theme": "dark",       # dark (brand UI) | light (paper-white app)
    "dim": 0.38,           # how much the room behind the speaker darkens while the UI is up
    "bottom": 0.745,       # lowest edge of the command box, fraction of the height (captions live below)
    "cursor": True,        # a pointer glides in and presses the button
    "grid": True,          # faint dot grid on the room plane
}

ICONS = {
    "upload": '<path d="M12 16V4m0 0-5 5m5-5 5 5M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2"/>',
    "doc": '<path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "spark": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "play": '<path d="M8 5v14l11-7z"/>',
}


def _icon(name, cls="ico"):
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS.get(name, ICONS["spark"])}</svg>')


def guess_icon(p: dict) -> str:
    if p.get("icon") in ICONS:
        return p["icon"]
    t = f"{p.get('title', '')} {p.get('text', '')}".lower()
    for keys, name in ((("drop", "upload", "file", "ارفع", "ملف"), "upload"), (("user", "member", "مستخدم", "عضو"), "user"),
                       (("campaign", "stat", "chart", "حمل"), "chart"), (("done", "ready", "check", "جاهز"), "check"),
                       (("doc", "brief", "script"), "doc")):
        if any(k in t for k in keys):
            return name
    return "spark"


def split_panels(panels: list) -> dict:
    """Group the panels: the command box (input / thumbs / button merge) and the cards that hang behind."""
    out = {"input": None, "thumbs": None, "button": None, "cards": []}
    for p in panels or []:
        k = (p or {}).get("kind", "card")
        if k in ("input", "thumbs", "button") and out[k] is None:
            out[k] = p
        else:
            out["cards"].append(p)
    return out


def composer_height(k: float, has_thumbs: bool) -> float:
    """Height in px of the command box at scale k (1 = 1080 wide)."""
    return k * (24 + (128 + 16 if has_thumbs else 0) + 64 + 24)


def card_lines(title: str, text_w: float, k: float) -> int:
    """Lines the card title wraps to at 30 px (Sora bold averages ~0.52 em a character)."""
    return max(1, min(3, math.ceil(len(str(title or "")) * 0.52 * 30 * k / max(1.0, text_w))))


def card_height(lines: int, has_meta: bool, k: float) -> float:
    return k * (22 + 56 + 14 + 36 * lines + (30 if has_meta else 0) + 22)


def layout(sc: sp.Scene, groups: dict, bottom: float, k: float) -> dict:
    """Where the command box, the back cards and the action words go. Pure: tests drive it with fake scenes."""
    W, H = sc.W, sc.H
    sx0, sx1, sy0, sy1 = sc.px("x0"), sc.px("x1"), sc.px("y0"), sc.px("y1")
    has_box = any(groups[x] for x in ("input", "thumbs", "button"))
    ch = composer_height(k, bool(groups["thumbs"])) if has_box else 0
    cw = min(sx1 - sx0, 0.80 * W)
    cx = min(max(sc.cx, sx0 + cw / 2), sx1 - cw / 2)
    word_h = 84 * k
    # the box sits just under the chin; if the chin is too low it goes above the head, behind the speaker
    lo = min(bottom * H, sy1 - word_h - 24 * k)
    top = max(sc.chin + 0.022 * H, sy0)
    box_plane = "front"
    if has_box and top + ch > lo:
        if sc.face and sc.face[1] - sy0 >= ch + 20 * k:
            top, box_plane = sy0 + 10 * k, "back"
        else:
            top = max(sy0, lo - ch)
    box = (cx - cw / 2, top, cx + cw / 2, top + ch) if has_box else None
    word_y = (box[3] + 26 * k) if box and box_plane == "front" else max(sc.chin + 0.04 * H, sy0)
    word_y = min(word_y, sy1 - word_h)
    # back cards: the clearest wall above the shoulders, partly tucked behind the head is fine (that is the depth)
    cards, taken = [], [box] if box and box_plane == "back" else []
    for i, p in enumerate(groups["cards"][:3]):
        best = None
        title = str(p.get("title", "") or "")
        for cwf in (0.40, 0.34, 0.29, 0.25):
            w = cwf * W
            full = w - 44 * k
            for yf in [sy0 + 8 * k + j * 0.035 * H for j in range(12)]:
                for xf in (sx0, sx1 - w, sx0 + (sx1 - sx0 - w) * 0.25, sx0 + (sx1 - sx0 - w) * 0.75):
                    right = (xf + w / 2) > sc.cx
                    probe = (xf, yf, xf + w, yf + card_height(2, bool(p.get("text")), k))
                    # text sits on the outer side and only where the wall shows
                    tw = min(full, sp.clear_run(sc, probe, right) - 26 * k)
                    if tw < max(150 * k, 0.55 * full):
                        continue
                    h = card_height(card_lines(title, tw, k), bool(p.get("text")), k)
                    if yf + h > min(sc.chin, sy1):
                        continue
                    r = (xf, yf, xf + w, yf + h)
                    if any(_overlap(r, t) > 0.02 for t in taken):
                        continue
                    vis = 1 - sc.rect_cover(*r)
                    if vis < 0.6:
                        continue
                    score = vis + 1.2 * cwf * vis + 0.6 * tw / W - 0.3 * (yf - sy0) / H
                    if best is None or score > best[0]:
                        best = (score, r, vis, right, tw)
        if best is None:
            break
        r = best[1]
        cards.append({"rect": r, "align": "right" if best[3] else "left", "vis": best[2], "text_w": best[4]})
        taken.append(r)
    return {"box": box, "box_plane": box_plane, "cards": cards, "word_y": word_y, "word_cx": cx}


def _overlap(a, b) -> float:
    if a is None or b is None:
        return 0.0
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return iw * ih / max(1.0, (a[2] - a[0]) * (a[3] - a[1]))


def timing(dur: float, n_chars: int, n_thumbs: int) -> dict:
    """Beats of the choreography in seconds: entrances, the drop, typing, the press, the exit."""
    t_drop = min(0.55, 0.16 * dur + 0.1)
    t_type = t_drop + 0.2 + 0.07 * max(0, n_thumbs - 1) + 0.25
    exit_at = dur - 0.38
    t_press = min(max(0.6 * dur, t_type + 0.75), exit_at - 0.45)
    per = min(0.034, max(0.012, (t_press - 0.2 - t_type) / max(1, n_chars)))
    return {"t_in": 0.08, "t_box": 0.18, "t_drop": t_drop, "t_type": t_type, "per_char": per,
            "t_typed": t_type + per * n_chars, "t_press": t_press, "exit": exit_at}


def render(ctx):
    k = ctx.W / 1080
    groups = split_panels(ctx.param("panels", PARAMS["panels"]))
    sc = sp.scene(ctx)
    lay = layout(sc, groups, float(ctx.param("bottom", PARAMS["bottom"])), k)
    th = sp.theme(ctx.style, ctx.param("theme", PARAMS["theme"]))
    D = ctx.dur
    words = [w for w in (ctx.param("words", PARAMS["words"]) or []) if str(w).strip()]

    # thumbnails
    assets, thumbs = {}, []
    if groups["thumbs"]:
        imgs = [ctx.asset(p) for p in (ctx.param("images") or []) if p]
        n = int(ctx.param("n_thumbs", PARAMS["n_thumbs"]))
        if not imgs:
            face = (sc.cx, (sc.face[1] + sc.chin) / 2) if sc.face else None
            imgs = sp.stills(ctx, n, ctx.param("stills_from"), size=(216, 288), face=face)
        for i, p in enumerate(imgs[:6]):
            name = f"th{i}{p.suffix.lower()}"
            assets[name] = p
            thumbs.append(name)
    typed = str((groups["input"] or {}).get("text", "") or "")
    T = timing(D, len(typed), len(thumbs))

    css = _css(th, k)
    back_html, front_html = [], []
    box_html = _box(groups, thumbs, typed, th, k)
    if lay["box"]:
        x0, y0, x1, y1 = lay["box"]
        el = (f'<div class="drift {"df" if lay["box_plane"] == "front" else "db"}"><div id="box" class="panel box" '
              f'style="left:{x0:.0f}px;top:{y0:.0f}px;width:{x1 - x0:.0f}px">{box_html}</div></div>')
        (front_html if lay["box_plane"] == "front" else back_html).append(el)
    for i, (c, p) in enumerate(zip(lay["cards"], groups["cards"])):
        x0, y0, x1, y1 = c["rect"]
        ar = sp.is_arabic(p.get("title")) or sp.is_arabic(p.get("text"))
        back_html.append(
            f'<div class="drift db"><div class="panel card c{i} {c["align"]}{" ar" if ar else ""}" '
            f'style="left:{x0:.0f}px;top:{y0:.0f}px;width:{x1 - x0:.0f}px;height:{y1 - y0:.0f}px">'
            f'<div class="well">{_icon(guess_icon(p))}</div><div class="tx" style="width:{c["text_w"]:.0f}px"><div class="tt">{sp.esc(p.get("title"))}</div>'
            f'{"<div class=st>" + sp.esc(p.get("text")) + "</div>" if p.get("text") else ""}</div></div></div>')
    if ctx.param("grid", PARAMS["grid"]):
        back_html.insert(0, '<div id="grid"></div>')
    for i, w in enumerate(words[:4]):
        ar = sp.is_arabic(w)
        front_html.append(f'<div class="word w{i}{" ar" if ar else ""}" style="top:{lay["word_y"]:.0f}px;'
                          f'left:{lay["word_cx"]:.0f}px">{sp.esc(w)}</div>')
    if ctx.param("cursor", PARAMS["cursor"]) and lay["box"] and lay["box_plane"] == "front":
        front_html.append('<svg id="cursor" viewBox="0 0 28 28"><path d="M5 3l16 11.5-7 1.3 4.2 8.4-3 1.5-4.2-8.5-5.9 '
                          '4.6z" fill="#fff" stroke="#101114" stroke-width="1.6" stroke-linejoin="round"/></svg>')

    js = _js(T, D, k, lay, len(thumbs), typed, len(words[:4]), len(lay["cards"]))
    layers_back = [ctx.layer(ctx.page("".join(back_html), css, js), "uiw-back", assets)] if back_html else []
    layers_front = [ctx.layer(ctx.page("".join(front_html), css, js), "uiw-front", assets)] if front_html else []
    return sp.composite(ctx, layers_back, layers_front, dim=float(ctx.param("dim", PARAMS["dim"])), desat=0.25,
                        bg_blur=0.6, ramp=(0.35, 0.4))


def _box(groups, thumbs, typed, th, k):
    parts = []
    if groups["thumbs"]:
        title = (groups["thumbs"] or {}).get("title") or ""
        ths = "".join(f'<div class="th t{i}"><img src="{n}"><span class="pl">{_icon("play", "pi")}</span></div>'
                      for i, n in enumerate(thumbs))
        tag = f'<div class="tag{" ar" if sp.is_arabic(title) else ""}">{sp.esc(title)}</div>' if title else ""
        parts.append(f'<div class="att">{ths}{tag}</div>')
    btn = groups["button"]
    btxt = str((btn or {}).get("text", "") or "")
    send = (f'<div id="send" class="send{" pill" if btxt else ""}">{sp.esc(btxt)}'
            f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" '
            f'stroke-linejoin="round"><path d="M12 19V5m0 0-6 6m6-6 6 6"/></svg><i id="ripple"></i></div>')
    ar = sp.is_arabic(typed)
    field = (f'<div class="field{" ar" if ar else ""}"><span id="typed"></span><span id="caret"></span>'
             f'<span id="ph">{"اكتب طلبك" if ar else "Ask, or type / for commands"}</span></div>')
    parts.append(f'<div class="row"><div class="plus">+</div>{field}{send if btn or groups["input"] else ""}</div>')
    parts.append('<div id="bar"></div>')
    return "".join(parts)


def _css(th, k):
    def px(v):
        return f"{v * k:.1f}px"
    return f"""
:root{{--sf:{th['surface']};--sf2:{th['surface2']};--ln:{th['line']};--ink:{th['ink']};--mu:{th['muted']};
  --ac:{th['accent']};--on:{th['on_accent']};--chip:{th['chip']}}}
.drift{{position:absolute;inset:0;will-change:transform}}
.panel{{position:absolute;box-sizing:border-box;will-change:transform,opacity}}
#grid{{position:absolute;inset:-40px;
  background-image:radial-gradient(circle,{sp.rgba(th['accent'], 0.55) if th['accent'].startswith('#') else th['accent']} {px(1.6)},transparent {px(2.2)});
  background-size:{px(46)} {px(46)};
  -webkit-mask-image:radial-gradient(ellipse 75% 55% at 50% 38%,#000 20%,transparent 80%)}}
.card{{display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:{px(14)};padding:{px(22)};
  background:var(--sf);border:1px solid var(--ln);border-radius:{px(30)};box-shadow:{th['shadow']},inset 0 1px 0 rgba(255,255,255,.07);
  color:var(--ink);filter:blur({px(0.6)})}}
.card.right{{align-items:flex-end;text-align:right}}
.card .well{{flex:none;width:{px(56)};height:{px(56)};border-radius:{px(17)};display:grid;place-items:center;
  background:{sp.rgba(th['accent'], 0.12)};border:1.5px dashed {sp.rgba(th['accent'], 0.6)};color:var(--ac)}}
.card .ico{{width:{px(28)};height:{px(28)}}}
.card .tx{{min-width:0}}
.card .tt{{font:700 {px(30)}/1.2 "BrandLT";letter-spacing:-.015em}}
.card .st{{margin-top:{px(10)};font:500 {px(18)}/1 "PlexMono";letter-spacing:.08em;text-transform:uppercase;color:var(--mu)}}
.card.ar .tt,.card.ar .st{{font-family:"BrandAR";letter-spacing:0;text-transform:none;direction:rtl}}
.box{{padding:{px(24)};background:var(--sf2);border:1px solid var(--ln);border-radius:{px(36)};
  box-shadow:{th['shadow']},inset 0 1px 0 rgba(255,255,255,.08);color:var(--ink);overflow:hidden}}
.att{{display:flex;align-items:center;gap:{px(14)};height:{px(128)};margin-bottom:{px(16)}}}
.th{{position:relative;width:{px(96)};height:{px(128)};border-radius:{px(18)};overflow:hidden;flex:none;
  box-shadow:0 0 0 1px var(--ln),0 8px 20px rgba(0,0,0,.4);will-change:transform,opacity}}
.th img{{width:100%;height:100%;object-fit:cover;display:block}}
.th .pl{{position:absolute;right:{px(8)};bottom:{px(8)};width:{px(28)};height:{px(28)};border-radius:50%;
  background:rgba(0,0,0,.55);display:grid;place-items:center;color:#fff}}
.th .pi{{width:{px(13)};height:{px(13)};fill:#fff;stroke:none}}
.tag{{margin-left:{px(10)};padding:{px(11)} {px(16)};border-radius:{px(12)};background:var(--ac);color:var(--on);
  font:700 {px(22)}/1 "BrandLT";letter-spacing:.04em;text-transform:uppercase;white-space:nowrap}}
.tag.ar{{font-family:"BrandAR";letter-spacing:0;text-transform:none}}
.row{{display:flex;align-items:center;gap:{px(16)};height:{px(64)}}}
.plus{{flex:none;width:{px(52)};height:{px(52)};border-radius:50%;border:1px solid var(--ln);display:grid;
  place-items:center;color:var(--mu);font:400 {px(34)}/1 "PlexMono"}}
.field{{flex:1;min-width:0;position:relative;font:500 {px(33)}/1.2 "PlexMono";color:var(--ink);white-space:nowrap;
  overflow:hidden;display:flex;align-items:center;letter-spacing:-.01em}}
.field.ar{{font-family:"TajawalMedium";direction:rtl;font-size:{px(38)}}}
#ph{{position:absolute;left:0;color:var(--mu);opacity:.8}}
.field.ar #ph{{left:auto;right:0}}
#caret{{display:inline-block;width:{px(3)};height:{px(38)};margin-left:{px(2)};background:var(--ac)}}
.send{{flex:none;position:relative;height:{px(64)};min-width:{px(64)};border-radius:{px(32)};background:var(--ac);
  color:var(--on);display:flex;align-items:center;justify-content:center;gap:{px(10)};font:700 {px(26)}/1 "BrandLT";
  will-change:transform;box-shadow:0 {px(6)} {px(18)} {sp.rgba(th['accent'], 0.35)}}}
.send.pill{{padding:0 {px(22)} 0 {px(26)}}}
.send svg{{width:{px(30)};height:{px(30)}}}
#ripple{{position:absolute;inset:0;border-radius:inherit;border:{px(3)} solid var(--ac);opacity:0}}
#bar{{position:absolute;left:{px(24)};right:{px(24)};bottom:0;height:{px(3)};border-radius:{px(2)};
  background:linear-gradient(90deg,transparent,var(--ac));transform-origin:0 50%;transform:scaleX(0);opacity:.9}}
.word{{position:absolute;font:700 {px(80)}/1 "BrandLT";letter-spacing:-.025em;color:#fff;
  white-space:nowrap;text-shadow:0 {px(4)} {px(28)} rgba(0,0,0,.6),0 1px 2px rgba(0,0,0,.45)}}
.word.ar{{font-family:"BrandAR";letter-spacing:0}}
.word .x{{display:inline-block}}
#cursor{{position:absolute;left:0;top:0;width:{px(58)};height:{px(58)};
  filter:drop-shadow(0 {px(4)} {px(8)} rgba(0,0,0,.45));will-change:transform}}
"""


def _js(T, D, k, lay, n_th, typed, n_words, n_cards):
    box = lay["box"]
    g = json.dumps
    js = [f"const D={D:.3f}, T={g(T)}, TYPED={g(typed)}, K={k:.4f};",
          # measure before any tween moves things (the send button is where the cursor goes)
          "const sendEl = document.querySelector('#send'); const SR = sendEl ? sendEl.getBoundingClientRect() : null;",
          "gsap.set('.word', {xPercent: -50});"]
    # room plane and parallax drift: far things move less than near ones
    js.append("if (document.querySelector('#grid')) { tl.fromTo('#grid', {y: 30*K}, {y: -20*K, duration: D, "
              "ease: 'none'}, 0); tl.fromTo('#grid', {opacity: 0}, {opacity: 1, duration: .6, ease: 'power2.out'}, .05); }")
    js.append("tl.fromTo('.db', {x: 10*K, y: 0}, {x: -10*K, y: -6*K, duration: D, ease: 'sine.inOut'}, 0);")
    js.append("tl.fromTo('.df', {x: 18*K, y: 4*K}, {x: -18*K, y: -8*K, duration: D, ease: 'sine.inOut'}, 0);")
    for i in range(n_cards):
        js.append(f"springIn(tl, '.c{i}', {{y: 46*K, scale: .9, rotation: {(-2.5 if i % 2 else 2.5)}, opacity: 0}}, "
                  f"{{y: 0, scale: 1, rotation: 0, opacity: .94, duration: .8}}, 'gentle', T.t_in + {0.12 * i:.2f});")
    if box:
        js.append("if (document.querySelector('#box')) {")
        js.append("springIn(tl, '#box', {y: 60*K, scale: .94, opacity: 0}, {y: 0, scale: 1, opacity: 1, duration: .8}, "
                  "'gentle', T.t_box);")
        for i in range(n_th):
            rot = (-7, 5, -4, 8, -6, 4)[i % 6]
            js.append(f"springIn(tl, '.t{i}', {{y: -70*K, x: {(-40 + 20 * i):.0f}*K, scale: 1.25, rotation: {rot}, "
                      f"opacity: 0}}, {{y: 0, x: 0, scale: 1, rotation: 0, opacity: 1, duration: .6}}, 'snappy', "
                      f"T.t_drop + {0.07 * i:.2f});")
        js.append("if (document.querySelector('.tag')) springIn(tl, '.tag', {scale: .7, opacity: 0}, "
                  "{scale: 1, opacity: 1, duration: .5}, 'bouncy', T.t_drop + .07 * Math.max(0, %d - 1) + .2);" % n_th)
        # typing: a pure function of time (seek-safe)
        js.append("""const ty = document.querySelector('#typed'), ph = document.querySelector('#ph');
  const typer = {n: 0};
  tl.fromTo(typer, {n: 0}, {n: TYPED.length, duration: Math.max(.01, T.t_typed - T.t_type), ease: 'none',
    onUpdate: () => { const c = Math.round(typer.n); ty.textContent = TYPED.slice(0, c);
      ph.style.opacity = c > 0 ? 0 : .8; }}, T.t_type);
  tl.fromTo('#caret', {opacity: 0}, {opacity: 1, duration: .05}, T.t_type - .1);
  const blinks = Math.max(1, Math.floor((T.exit - T.t_typed) / .5));
  tl.fromTo('#caret', {opacity: 1}, {opacity: 0, duration: .25, ease: 'steps(1)', repeat: blinks, yoyo: true,
    repeatDelay: .25, immediateRender: false}, T.t_typed);""")
        js.append("""if (document.querySelector('#cursor') && SR) {
  const tx = SR.left + SR.width * .5, ty2 = SR.top + SR.height * .5;
  tl.fromTo('#cursor', {opacity: 0}, {opacity: 1, duration: .18, ease: 'power1.out'}, T.t_press - .6);
  tl.fromTo('#cursor', {x: tx - 300*K, y: ty2 + 170*K}, {x: tx - 10*K, y: ty2 - 6*K, duration: .57,
    ease: 'power3.inOut', immediateRender: false}, T.t_press - .6);
  tl.to('#cursor', {scale: .82, duration: .08, ease: 'power2.out', transformOrigin: '20% 10%'}, T.t_press - .03);
  tl.to('#cursor', {scale: 1, duration: .2, ease: 'power2.out'}, T.t_press + .07);
}
tl.to('#send', {scale: .9, duration: .08, ease: 'power2.out'}, T.t_press - .03);
springIn(tl, '#send', {scale: .9}, {scale: 1, duration: .45, immediateRender: false}, 'bouncy', T.t_press + .05);
tl.fromTo('#ripple', {scale: 1, opacity: .9}, {scale: 1.7, opacity: 0, duration: .55, ease: 'power2.out'}, T.t_press + .02);
tl.fromTo('#bar', {scaleX: 0}, {scaleX: 1, duration: Math.max(.2, T.exit - T.t_press - .05), ease: 'power1.inOut'},
  T.t_press + .08);""")
        js.append("}")
    # action words: the first on the drop, the second on the press, any others after
    beats = [T["t_drop"] + 0.05, T["t_press"]] + [T["t_press"] + 0.45 * (j + 1) for j in range(2)]
    for i in range(n_words):
        t0 = min(beats[i], T["exit"] - 0.3)
        js.append(f"springIn(tl, '.w{i}', {{y: 26*K, scale: .82, opacity: 0}}, {{y: 0, scale: 1, opacity: 1, "
                  f"duration: .5}}, 'bouncy', {t0:.3f});")
        if i + 1 < n_words:
            t1 = min(beats[i + 1], T["exit"] - 0.3) - 0.12
            js.append(f"tl.to('.w{i}', {{opacity: 0, y: -18*K, scale: .96, duration: .16, ease: 'power2.in'}}, {t1:.3f});")
    out = "{duration: .34, ease: 'power2.in', immediateRender: false}"
    js.append(f"tl.fromTo('.card', {{opacity: .94, scale: 1, y: 0}}, Object.assign({{opacity: 0, scale: .97, y: 14*K}}, "
              f"{out}), T.exit);")
    js.append(f"if (document.querySelector('#box')) tl.fromTo('#box', {{opacity: 1, scale: 1, y: 0}}, "
              f"Object.assign({{opacity: 0, scale: .97, y: 18*K}}, {out}), T.exit);")
    if n_words:
        js.append(f"tl.fromTo('.w{n_words - 1}', {{opacity: 1, scale: 1}}, Object.assign({{opacity: 0, scale: .96}}, "
                  f"{out}), T.exit);")
    js.append(f"if (document.querySelector('#cursor')) tl.fromTo('#cursor', {{opacity: 1}}, "
              f"Object.assign({{opacity: 0}}, {out}), T.exit - .1);")
    js.append(f"if (document.querySelector('#grid')) tl.fromTo('#grid', {{opacity: 1}}, Object.assign({{opacity: 0}}, "
              f"{out}), T.exit);")
    return "\n  ".join(js)
