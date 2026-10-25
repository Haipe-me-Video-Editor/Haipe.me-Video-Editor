"""Brand kit graphics: every colour comes from the style (accent, card_bg, ink, plus `kit_tones` overrides).

Full-frame transparent HyperFrames compositions, positioned by the plan rather than by layout.place:
- stack:   lines of keywords; each line can be plain text, a glass pill, a chrome hero word, a giant index number
           or neon English. Lines blur-rise in one by one (`t`), and the whole stack leaves together.
- card:    full-screen definition card (dark card, hairlines, 3D X marks) that slides up over the speaker,
           with a main line and small lines above and below that blur in on their own beats.
- badge:   glowing diamond with a white icon (comment, share, chart), optional pill under it.
- bars:    two-column comparison (e.g. a rate on two dates) with a ticking counter and a change label.
           Only real numbers from the script go in it.
- leak:    warm light-leak flash for transitions (red tint, white flare, orange fall-off), ~0.4 s.
- endcard: white logo end card that comes up from black through grey and fades to grey at the end.
"""
import html
import json

from .spring import SPRING_TAG, spring_in

KIT_TYPES = ("stack", "card", "badge", "bars", "leak", "endcard", "tiles", "poll", "balance", "wave", "mark",
             "sticker", "title", "flag")

# Fonts each kit composition can use; render.py copies these files next to index.html.
KIT_FONTS = {"ar": "Tajawal Medium", "arb": "Tajawal", "arh": "Lalezar", "hero": "Anton", "latin": "Montserrat",
             "word": "Sora", "thin": "Sora ExtraLight",
             "tech": "Orbitron"}

ICONS = {
    "comment": '<path d="M20 22h60a10 10 0 0 1 10 10v34a10 10 0 0 1-10 10H46l-18 14v-14h-8a10 10 0 0 1-10-10V32a10 10 0 0 1 10-10z" fill="#fff"/>',
    "share": '<path d="M62 16l26 24-26 24V50c-22 0-36 6-48 24 4-26 18-42 48-46z" fill="#fff"/>',
    "chart": '<path d="M14 82h72M22 70V52M40 70V38M58 70V46M76 70V24" stroke="#fff" stroke-width="10" stroke-linecap="round" fill="none"/>',
    "wallet": '<path d="M16 30h62a8 8 0 0 1 8 8v36a8 8 0 0 1-8 8H16a8 8 0 0 1-8-8V38a8 8 0 0 1 8-8zM60 50h26v16H60a8 8 0 0 1 0-16zM18 30l46-14 6 14" fill="none" stroke="#fff" stroke-width="7" stroke-linejoin="round"/>',
    "vault": '<rect x="12" y="16" width="76" height="66" rx="10" fill="none" stroke="#fff" stroke-width="7"/><circle cx="50" cy="49" r="16" fill="none" stroke="#fff" stroke-width="7"/><path d="M50 33v-6M50 71v-6M34 49h-6M72 49h-6M22 82v8M78 82v8" stroke="#fff" stroke-width="7" stroke-linecap="round"/>',
    "scale": '<path d="M50 14v70M24 84h52M14 30h72M14 30l-10 26h20zM86 30l-10 26h20z" fill="none" stroke="#fff" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"/>',
    "flow": '<path d="M10 34h56l-12-12M90 66H34l12 12" fill="none" stroke="#fff" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>',
    "ship": '<path d="M14 62h72l-10 18H24zM26 62V44h48v18M38 44V30h24v14" fill="none" stroke="#fff" stroke-width="7" stroke-linejoin="round"/>',
    "doc": '<path d="M24 12h36l18 18v58H24zM60 12v18h18M36 50h28M36 64h28" fill="none" stroke="#fff" stroke-width="7" stroke-linejoin="round"/>',
    "exit": '<path d="M44 16H18v68h26M40 50h46M72 34l16 16-16 16" fill="none" stroke="#fff" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>',
    "send": '<path d="M12 48l76-34-26 74-12-30z" fill="none" stroke="#fff" stroke-width="7" stroke-linejoin="round"/>',
    "pyramid": '<path d="M50 14L8 84h84z" fill="none" stroke="#fff" stroke-width="7" stroke-linejoin="round"/><path d="M50 14l14 70" stroke="#fff" stroke-width="5" opacity=".55"/>',
    "plane": '<path d="M46 10c4 0 6 4 6 8v22l34 18v9l-34-9v19l10 7v7l-16-5-16 5v-7l10-7V58l-34 9v-9l34-18V18c0-4 2-8 6-8z" fill="#fff"/>',
    "box": '<path d="M50 10l38 18v44L50 90 12 72V28zM12 28l38 18 38-18M50 46v44" fill="none" stroke="#fff" stroke-width="7" stroke-linejoin="round"/>',
    "news": '<rect x="10" y="18" width="80" height="64" rx="8" fill="none" stroke="#fff" stroke-width="7"/><path d="M22 34h56M22 50h26M22 64h26M58 50h20v14H58z" stroke="#fff" stroke-width="6" fill="none"/>',
    "file": '<path d="M24 8h36l22 22v62H24z" fill="currentColor"/><path d="M60 8v22h22z" fill="#fff" opacity=".45"/>'
            '<path d="M36 52h32M36 64h32M36 76h20" stroke="#fff" stroke-width="5" stroke-linecap="round"/>',
    "bell": '<path d="M50 14a8 8 0 0 1 8 8v3c12 4 20 15 20 28v14l8 10H14l8-10V53c0-13 8-24 20-28v-3a8 8 0 0 1 8-8zM40 82h20a10 10 0 0 1-20 0z" fill="#fff"/>',
}


def _e(s) -> str:
    return html.escape(str(s))


def _mix(a: str, b: str, t: float) -> str:
    """Hex colour t of the way from a to b."""
    ca, cb = (tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) for h in (a, b))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def _colors(style: dict) -> dict:
    """The kit's palette: the style's colours plus tones derived from the accent (light, pale, deep, two bevel
    shades) and the card background (glow, night). A style's `kit_tones` overrides any of them by name."""
    acc = style.get("accent", "#ff7a1a")
    card = style.get("card_bg", "#1b1d22")
    c = {"accent": acc, "accent2": style.get("accent2", acc), "neon": style.get("neon", _mix(acc, "#000000", .3)),
         "ink": style.get("ink", "#FFFFFF"), "card_bg": card, "haze": style.get("haze", _mix(card, acc, .35)),
         "up": style.get("up", "#2ecc71"), "down": style.get("down", "#ff4d4f"),
         "light": _mix(acc, "#ffffff", .45), "pale": _mix(acc, "#ffffff", .85), "line": _mix(acc, "#ffffff", .6),
         "deep": _mix(acc, "#000000", .25), "bevel1": _mix(acc, "#000000", .6), "bevel2": _mix(acc, "#000000", .42),
         "glow": _mix(card, acc, .14), "glow2": _mix(card, acc, .08), "night": _mix(card, "#000000", .6), "end_ink": "#1f2430"}
    c.update(style.get("kit_tones", {}))
    return c


def _font_faces(font_files: dict) -> str:
    return "".join(f'@font-face{{font-family:"K{k}";src:url("{f}")}}' for k, f in font_files.items())


def _line_css(line: dict, c: dict, u: float) -> tuple[str, str]:
    """Inline style for a stack line and its class."""
    color = line.get("color", "ink")
    font = line.get("font", "hero" if color == "chrome" else "ar")
    size = line.get("size", 60) * u
    css = [f"font-family:K{font},sans-serif", f"font-size:{size:.1f}px"]
    cls = "ln"
    if line.get("stroke") or line.get("ring"):
        # die-cut sticker lettering: a solid fill, an optional edge under it, and an outer cut line built from four
        # zero-blur shadows (each one grows the last), then a soft lift. Solid colours only: a clipped gradient
        # would be covered by its own edge.
        fill = c.get(color, c["ink"]) if color in ("accent", "accent2", "neon", "up", "down") else c["ink"]
        css.append(f"color:{fill}")
        if line.get("stroke"):
            sc, sw = line["stroke"]
            css.append(f"-webkit-text-stroke:{sw * u * 2:.1f}px {sc};paint-order:stroke fill")
        if line.get("ring"):
            rc, rw = line["ring"]
            r = rw * u
            css.append("filter:" + " ".join(f"drop-shadow({dx * r:.1f}px {dy * r:.1f}px 0 {rc})"
                                            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
                       + f" drop-shadow(0 {6 * u:.0f}px {10 * u:.0f}px rgba(0,0,0,.35))")
        if line.get("pill"):
            cls += " pill"
        if line.get("tracking") is not None:
            css.append(f"letter-spacing:{line['tracking'] * u:.1f}px")
        return cls, ";".join(css)
    if color == "chrome":
        cls += " chrome"
    elif color == "accent":
        cls += " grad"
        css.append(f"background-image:linear-gradient(180deg,{c['accent']} 0%,{c['accent2']} 100%)")
        css.append(f"filter:drop-shadow(0 0 {18 * u:.0f}px {c['accent']}99)")
    elif color == "neon":
        css.append(f"color:{c['neon']}")
        css.append(f"text-shadow:0 0 {4 * u:.0f}px {c['accent']},0 0 {16 * u:.0f}px {c['neon']},0 0 {36 * u:.0f}px {c['neon']}aa")
    elif color in ("up", "down"):
        css.append(f"color:{c[color]}")
        css.append(f"text-shadow:0 0 {6 * u:.0f}px {c[color]},0 0 {24 * u:.0f}px {c[color]}99")
    else:
        css.append(f"color:{c['ink']}")
        css.append(f"text-shadow:0 0 {14 * u:.0f}px rgba(255,255,255,.35),0 {3 * u:.0f}px {14 * u:.0f}px rgba(0,0,0,.45)")
    if line.get("pill"):
        cls += " pill"
    elif line.get("box"):  # a tag: the text on a block of the accent (or the colour given) with a soft glow
        fill = c["accent"] if line["box"] is True else c.get(line["box"], line["box"])
        glow = c.get(f"{line['box']}_glow", "rgba(255,255,255,.35)") if isinstance(line["box"], str) else f"{fill}99"
        css = [x for x in css if not x.startswith(("background-image", "filter", "color", "text-shadow"))]
        cls = "ln"
        css += [f"color:{c['ink']}", f"background:{fill}", f"padding:{.06 * size:.0f}px {.22 * size:.0f}px {.1 * size:.0f}px",
                f"border-radius:{c.get('tag_radius', .08) if not isinstance(line['box'], str) else c.get(line['box'] + '_radius', .08)}em",
                f"box-shadow:0 0 {26 * u:.0f}px {glow}",
                f"text-shadow:0 0 {8 * u:.0f}px rgba(255,255,255,.75),0 0 {22 * u:.0f}px rgba(200,170,255,.6)"]
    if line.get("tracking") is not None:
        css.append(f"letter-spacing:{line['tracking'] * u:.1f}px")
    return cls, ";".join(css)


BASE_CSS = """
body{margin:0;background:transparent}
#root{position:relative;width:100%%;height:100%%;overflow:hidden}
.clip{position:absolute;inset:0}
.ln{display:inline-block;white-space:nowrap;line-height:1.05;will-change:transform,filter,opacity}
.chrome{background-image:linear-gradient(180deg,#fff 0%%,#fff 48%%,#b4b4b4 80%%,#8c8c8c 100%%);
  -webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 %(g)spx rgba(255,255,255,.55));
  padding:.22em .06em .08em;margin:-.22em -.06em -.08em}
.grad{-webkit-background-clip:text;background-clip:text;color:transparent;padding:.22em .06em .08em;margin:-.22em -.06em -.08em}
.pill{padding:%(py)spx %(px)spx;border-radius:999px;line-height:1.25;
  background:linear-gradient(180deg,rgba(58,52,74,.86),rgba(30,26,42,.84));
  border:%(bw)spx solid rgba(255,255,255,.42);box-shadow:0 %(sy)spx %(sb)spx rgba(0,0,0,.3),inset 0 1px 0 rgba(255,255,255,.25)}
"""


def _doc(size: tuple, dur: float, css: str, body: str, script: str, font_files: dict, rtl: bool) -> str:
    W, H = size
    fams = ",".join(f'"K{k}"' for k in font_files)
    return f"""<!doctype html>
<html lang="{'ar' if rtl else 'en'}"><head><meta charset="UTF-8"><script src="gsap.min.js"></script>{SPRING_TAG}
<style>{_font_faces(font_files)}{css}</style></head><body>
<div id="root" data-composition-id="g" data-start="0" data-width="{W}" data-height="{H}" data-duration="{dur}">
<section class="clip" data-start="0" data-duration="{dur}">{body}</section></div>
<script>
Promise.all([{fams}].map(f => document.fonts.load('40px "' + f + '"'))).then(() => {{
  for (const f of [{fams}]) if (!document.fonts.check('40px "' + f + '"')) throw new Error("font " + f + " did not load");
  const tl = gsap.timeline({{paused: true}});
  {script}
  tl.set({{}}, {{}}, {dur});
  window.__timelines["g"] = tl;
}});
</script></body></html>
"""


def _enter(sel: str, t: float, anim: str, u: float) -> str:
    """Spring entrances (editor/graphics/spring.py): the move springs, clip-path/blur/fade stay smooth."""
    if anim == "wipe":
        return spring_in(sel, f'clipPath:"inset(100% 0% 0% 0%)",y:{60 * u:.0f},opacity:1',
                         'clipPath:"inset(0% 0% 0% 0%)",y:0,duration:.55', "gentle", t)
    if anim == "pop":
        return spring_in(sel, f'scale:.55,opacity:0,filter:"blur({10 * u:.0f}px)"',
                         'scale:1,opacity:1,filter:"blur(0px)",duration:.4', "bouncy", t)
    if anim == "type":  # typed on: revealed left to right (a tag's block grows with its text)
        return (f'tl.fromTo("{sel}",{{clipPath:"inset(-20% 100% -20% 0%)",opacity:1}},'
                f'{{clipPath:"inset(-20% 0% -20% 0%)",duration:.5,ease:"steps(10)"}},{t:.3f});')
    if anim == "stretch":  # a kashida title opening out from its centre
        return spring_in(sel, f'scaleX:.45,opacity:0,filter:"blur({12 * u:.0f}px)"',
                         'scaleX:1,opacity:1,filter:"blur(0px)",duration:.5', "gentle", t)
    return spring_in(sel, f'y:{70 * u:.0f},opacity:0,filter:"blur({16 * u:.0f}px)"',
                     'y:0,opacity:1,filter:"blur(0px)",duration:.45', "gentle", t)


def _leave(sel: str, t: float, u: float) -> str:
    return (f'tl.to("{sel}",{{y:{30 * u:.0f},opacity:0,filter:"blur({12 * u:.0f}px)",duration:.3,ease:"power2.in"}},'
            f'{max(t, 0.05):.3f});')


def _stack(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    W, H = size
    u = W / 1080
    c = _colors(style)
    x, y = spec.get("pos", [0.5, 0.62])
    align = spec.get("align", "center")
    gap = spec.get("gap", 10) * u
    d = spec["dur"]
    items, script = [], []
    rtl = False
    for i, line in enumerate(spec["lines"]):
        cls, css = _line_css(line, c, u)
        txt = str(line["text"])
        rtl = rtl or any("؀" <= ch <= "ۿ" for ch in txt)
        dx = line.get("dx", 0) * u
        if line.get("opacity") is not None:
            css += f";opacity:{line['opacity']}"
        inner = (f'<svg viewBox="0 0 100 100" style="width:{line.get("size", 60) * u:.0f}px;height:{line.get("size", 60) * u:.0f}px;'
                 f'color:{c.get(line.get("color"), line.get("color", c["ink"]))};filter:drop-shadow(0 0 {10 * u:.0f}px currentColor)">'
                 f'{ICONS[line["icon"]]}</svg>' if line.get("icon")
                 else f'<span class="{cls}" style="{css}" dir="auto">{_e(txt)}</span>')
        items.append(f'<div class="row" style="text-align:{line.get("align", align)};transform:translateX({dx:.0f}px)">'
                     f'<span id="l{i}" class="lw" style="display:inline-block">{inner}</span></div>')
        script.append(_enter(f"#l{i}", line.get("t", 0.0), line.get("anim", "rise"), u))
        if line.get("strike") is not None:
            items[-1] = items[-1].replace('</span></span></div>', f'</span><i id="k{i}" class="strike"></i></span></div>')
            script.append(f'tl.fromTo("#k{i}",{{scaleX:0}},{{scaleX:1,duration:.35,ease:"power3.inOut"}},{line["strike"]});')
            script.append(f'tl.to("#l{i} .ln",{{opacity:.85,duration:.3}},{line["strike"]});')
        if line.get("out") is not None:
            script.append(_leave(f"#l{i}", line["out"], u))
    script.append(_leave(".lw", spec.get("out", d - 0.3), u))
    anchor = {"center": "-50%", "left": "0%", "right": "-100%"}[align]
    css = (BASE_CSS % {"g": f"{16 * u:.0f}", "py": f"{20 * u:.0f}", "px": f"{90 * u:.0f}", "bw": f"{1.8 * u:.1f}",
                       "sy": f"{6 * u:.0f}", "sb": f"{24 * u:.0f}"}
           + f".lw{{position:relative}}.strike{{position:absolute;left:-4%;right:-4%;top:52%;height:{14 * u:.0f}px;border-radius:{8 * u:.0f}px;"
             f"background:{c['accent']};box-shadow:0 0 {24 * u:.0f}px {c['accent']};transform-origin:right center}}"
           + f"#st{{position:absolute;left:{x * 100:.2f}%;top:{y * 100:.2f}%;"
             f"transform:translate({anchor},-50%) rotate({spec.get('rotate', 0)}deg);"
             f"display:flex;flex-direction:column;gap:{gap:.0f}px;min-width:max-content}}")
    if style.get("pill_bg"):  # the brand's own glass for pills (fill, hairline, corner)
        css += (f".pill{{background:{style['pill_bg']};border-color:{style.get('pill_border', 'rgba(255,255,255,.42)')};"
                f"border-radius:{style.get('pill_radius', 999) * u:.0f}px}}")
    if spec.get("shade"):  # dark halo hugging each line's glyphs, arriving with its line: reads on busy or bright footage
        css += (f".row{{filter:drop-shadow(0 0 {14 * u:.0f}px rgba(8,5,14,.9)) "
                f"drop-shadow(0 0 {34 * u:.0f}px rgba(8,5,14,.65))}}")
    bg = ""
    if spec.get("bg"):  # full-screen: brand grid behind the lines (covers the speaker)
        css += (f"#sbg{{position:absolute;inset:0;background-image:linear-gradient({c['accent']}22 1px,transparent 1px),"
                f"linear-gradient(90deg,{c['accent']}22 1px,transparent 1px),radial-gradient(110% 70% at 50% 45%,{c['glow']} 0,{c['card_bg']} 60%,{c['night']} 100%);"
                f"background-size:{60 * u:.0f}px {60 * u:.0f}px,{60 * u:.0f}px {60 * u:.0f}px,100% 100%}}")
        bg = '<div id="sbg"></div>'
        bi = spec.get("bg_in", .12)
        script.insert(0, 'tl.set("#sbg",{opacity:1},0);' if bi <= 0 else f'tl.fromTo("#sbg",{{opacity:0}},{{opacity:1,duration:{bi}}},0);')
        script.append(f'tl.fromTo("#sbg",{{backgroundPosition:"0px 0px,0px 0px,0 0"}},{{backgroundPosition:"0px {120 * u:.0f}px,{60 * u:.0f}px 0px,0 0",duration:{d:.2f},ease:"none"}},0);')
    return _doc(size, d, css, f'{bg}<div id="st">{"".join(items)}</div>', "\n  ".join(script), font_files, rtl)


def _x_mark(cls: str, u: float, c: dict) -> str:
    """A chunky extruded X in the accent: a bright face over two darker bevel copies."""
    bar = 92 * u
    length = 330 * u

    def bars(color, dx, dy):
        return "".join(f'<div style="position:absolute;left:{-length / 2 + dx:.0f}px;top:{-bar / 2 + dy:.0f}px;'
                       f'width:{length:.0f}px;height:{bar:.0f}px;border-radius:{10 * u:.0f}px;background:{color};'
                       f'transform:rotate({r}deg)"></div>' for r in (45, -45))
    face = f"linear-gradient(135deg,{c['light']} 0%,{c['accent']} 45%,{c['deep']} 100%)"
    return (f'<div class="xm {cls}" style="position:absolute;width:0;height:0">'
            f'{bars(c["bevel1"], 26 * u, 22 * u)}{bars(c["bevel2"], 13 * u, 11 * u)}{bars(face, 0, 0)}</div>')


def _card(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    W, H = size
    u = W / 1080
    c = _colors(style)
    d = spec["dur"]
    lines = spec["lines"]  # [{text, role: top|main|bottom, t}]
    rows = []
    script = [  # ~10% of the height per frame for 4 frames, then a slow settle
              'tl.fromTo("#cardbg",{yPercent:75},{yPercent:30,duration:.15,ease:"none"},0);',
              'tl.to("#cardbg",{yPercent:0,duration:.9,ease:"power2.out"},.15);',
              f'tl.fromTo("#cardbg",{{filter:"blur({12 * u:.0f}px)"}},{{filter:"blur(0px)",duration:.25,ease:"power1.in"}},0);',
              # exit: straight up and off in 0.3 s with a vertical smear, X marks carried along, no flash
              f'tl.to("#cardbg",{{yPercent:-100,duration:.3,ease:"power2.in"}},{d - 0.3:.2f});',
              f'tl.to("#txt",{{filter:"blur({6 * u:.0f}px)",duration:.2}},{d - 0.3:.2f});',
              spring_in(".xm.a", "rotation:-60,scale:.4,opacity:0", "rotation:0,scale:1,opacity:1,duration:.7", "gentle", .15),
              spring_in(".xm.b", "rotation:60,scale:.4,opacity:0", "rotation:0,scale:1,opacity:1,duration:.7", "gentle", .25),
              f'tl.to(".xm.a",{{rotation:8,x:{14 * u:.0f},duration:{max(d - .9, .5):.2f},ease:"sine.inOut"}},.85);',
              f'tl.to(".xm.b",{{rotation:-8,x:{-14 * u:.0f},duration:{max(d - .95, .5):.2f},ease:"sine.inOut"}},.95);',
              f'tl.fromTo("#haze",{{scale:.85,opacity:.6}},{{scale:1.1,opacity:1,duration:{d:.2f},ease:"none"}},0);']
    for i, ln in enumerate(lines):
        role = ln.get("role", "main")
        fs = {"main": 128, "top": 58, "bottom": 58}[role] * ln.get("scale", 1.0) * u
        just = {"main": "center", "top": "flex-end" if ln.get("side") == "right" else "flex-start",
                "bottom": "flex-start" if ln.get("side") == "left" else "flex-end"}[role]
        color = {"accent": c["accent"]}.get(ln.get("color"), c["ink"])
        rows.append(f'<div style="display:flex;justify-content:{just}"><span id="c{i}" class="ln" dir="auto" '
                    f'style="font-family:Kar;font-size:{fs:.0f}px;color:{color};'
                    f'opacity:{0.92 if role != "main" else 1};text-shadow:0 0 {12 * u:.0f}px rgba(255,255,255,.25)">'
                    f'{_e(ln["text"])}</span></div>')
        script.append(spring_in(f"#c{i}", f'opacity:0,filter:"blur({18 * u:.0f}px)",y:{20 * u:.0f}',
                                'opacity:1,filter:"blur(0px)",y:0,duration:.6', "gentle", ln.get("t", .35)))
    lines_svg = "".join(f'<line x1="{a}" y1="{b}" x2="{cc}" y2="{dd}" stroke="{c["line"]}" stroke-opacity=".2" stroke-width="1.6"/>'
                        for a, b, cc, dd in ((36, 40, 52, 1880), (1040, 30, 1030, 1890), (60, 700, 700, 560),
                                             (420, 1700, 1040, 1420), (250, 300, 900, 380), (300, 520, 360, 980),
                                             (640, 1000, 980, 1180), (120, 1300, 520, 1250), (700, 160, 860, 640),
                                             (90, 980, 230, 1520), (780, 1500, 900, 1760)))
    css = (BASE_CSS % {"g": "16", "py": "14", "px": "54", "bw": "1.6", "sy": "6", "sb": "24"}
           + f"#cardbg{{position:absolute;inset:0;background:{c['card_bg']}}}"
           f"#haze{{position:absolute;left:0%;top:20%;width:100%;height:50%;border-radius:50%;"
           f"background:radial-gradient(closest-side,{c['haze']}d9,{c['haze']}00);filter:blur({50 * u:.0f}px)}}"
           f"#grain{{position:absolute;inset:0;opacity:.18;background-image:radial-gradient(#ffffff22 1px,transparent 1px);"
           f"background-size:{5 * u:.0f}px {5 * u:.0f}px}}"
           f"#edge{{position:absolute;left:0;right:0;top:0;height:{140 * u:.0f}px;"
           f"background:linear-gradient(180deg,rgba(23,17,32,0),{c['card_bg']});transform:translateY(-100%)}}"
           f"#ring{{position:absolute;left:58%;top:47%;width:{470 * u:.0f}px;height:{470 * u:.0f}px;border-radius:50%;"
           f"border:{2.2 * u:.1f}px solid {c['line']}40}}"
           f"#txt{{position:absolute;left:8%;right:8%;top:{spec.get('y', 0.42) * 100:.1f}%;transform:translateY(-50%);"
           f"display:flex;flex-direction:column;gap:{14 * u:.0f}px}}"
           f".xm.a{{left:{30 * u:.0f}px;top:{20 * u:.0f}px}}.xm.b{{left:{W - 70 * u:.0f}px;top:{H - 210 * u:.0f}px}}")
    body = (f'<div id="cardbg"><div id="edge"></div><div id="haze"></div><div id="grain"></div><div id="ring"></div>'
            f'<svg width="{W}" height="{H}" viewBox="0 0 1080 1920" style="position:absolute;inset:0">{lines_svg}</svg>'
            f'{_x_mark("a", u * 1.3, c)}{_x_mark("b", u * 1.45, c)}<div id="txt">{"".join(rows)}</div></div>')
    return _doc(size, d, css, body, "\n  ".join(script), font_files, True)


def _badge(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    W, H = size
    u = W / 1080
    c = _colors(style)
    d = spec["dur"]
    x, y = spec.get("pos", [0.5, 0.5])
    s = spec.get("size", 300) * u
    icon = ICONS[spec.get("icon", "comment")]
    num = spec.get("num")  # a numbered step: the figure in the diamond instead of an icon
    pill = ""
    script = [spring_in("#dia", f'scale:.5,opacity:0,filter:"blur({12 * u:.0f}px)"',
                        'scale:1,opacity:1,filter:"blur(0px)",duration:.45', "bouncy", 0),
              spring_in("#ico", "scale:.3,opacity:0", "scale:1,opacity:1,duration:.4", "bouncy", .2),
              f'tl.to("#dia",{{y:{-10 * u:.0f},duration:{max(d - .6, .4):.2f},ease:"sine.inOut"}},.45);']
    if spec.get("text"):
        cls, css = _line_css({"text": spec["text"], "pill": True, "size": spec.get("text_size", 58)}, c, u)
        pill = f'<div id="bp" style="position:absolute;left:{-W / 2:.0f}px;width:{W:.0f}px;text-align:center;top:{s * 0.82:.0f}px"><span class="{cls}" style="{css}" dir="auto">{_e(spec["text"])}</span></div>'
        script.append(_enter("#bp", spec.get("text_t", 0.25), "rise", u))
    script.append(_leave("#dia, #bp", d - 0.3, u))
    css = (BASE_CSS % {"g": "16", "py": f"{14 * u:.0f}", "px": f"{54 * u:.0f}", "bw": f"{1.6 * u:.1f}", "sy": "6", "sb": "24"}
           + f"#wrap{{position:absolute;left:{x * 100:.2f}%;top:{y * 100:.2f}%;width:0;height:0}}"
           f"#dia{{position:absolute;left:{-s / 2:.0f}px;top:{-s / 2:.0f}px;width:{s:.0f}px;height:{s:.0f}px}}"
           f"#sq{{position:absolute;inset:{s * 0.15:.0f}px;border-radius:{s * spec.get('radius', 0.1):.0f}px;transform:rotate(45deg);"
           + (f"background:radial-gradient(circle at 50% 50%,{c['pale']}f2 0%,{c['light']}d9 45%,{c['neon']}a6 100%);"
              f"border:{2 * u:.1f}px solid #ffffffb3;"
              f"box-shadow:0 0 {50 * u:.0f}px {c['neon']},0 0 {120 * u:.0f}px {c['neon']}aa,inset 0 0 {24 * u:.0f}px #ffffff88}}"
              if spec.get("look") == "glow" else
              f"background:linear-gradient(135deg,{c['light']} 0%,{c['accent']} 45%,{c['deep']} 100%);"
              f"box-shadow:0 0 {60 * u:.0f}px {c['accent']}e6,0 0 {140 * u:.0f}px {c['accent']}80,inset 0 0 {30 * u:.0f}px #ffffff55}}")
           + f"#ico{{position:absolute;left:{s * 0.27:.0f}px;top:{s * 0.27:.0f}px;width:{s * 0.46:.0f}px;height:{s * 0.46:.0f}px;"
           f"filter:drop-shadow(0 0 {14 * u:.0f}px #fff)}}")
    glyph = (f'<div id="ico" style="left:0;top:0;width:{s:.0f}px;height:{s:.0f}px;display:flex;align-items:center;'
             f'justify-content:center;color:#fff;font-family:K{spec.get("num_font", "latin")};font-size:{s * 0.36:.0f}px;'
             f'line-height:1">{_e(num)}</div>' if num is not None else f'<svg id="ico" viewBox="0 0 100 100">{icon}</svg>')
    body = f'<div id="wrap"><div id="dia"><div id="sq"></div>{glyph}</div>{pill}</div>'
    return _doc(size, d, css, body, "\n  ".join(script), font_files, True)


def _bars(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    """Two real values side by side: bars grow, the second value counts up from the first."""
    W, H = size
    u = W / 1080
    c = _colors(style)
    d = spec["dur"]
    a, b = spec["values"]  # [{value, label, t}], value numeric
    hi = max(a["value"], b["value"])
    base = spec.get("floor", min(a["value"], b["value"]) * 0.8)

    def h(v):
        return 640 * u * (v - base) / (hi - base)  # leaves the top third free for the title and the change figure
    dec = spec.get("decimals", 2)
    col_up = c["down"] if spec.get("bad_up", True) else c["up"]
    body = (f'<div id="bg"></div>'
            f'<div id="title" class="t" dir="auto">{_e(spec.get("title", ""))}</div>'
            f'<div id="sub" class="t" dir="ltr">{_e(spec.get("pair", ""))}</div>'
            f'<div class="col" id="ca" style="left:{180 * u:.0f}px"><div class="num" id="na" dir="ltr">{a["value"]:.{dec}f}</div>'
            f'<div class="bar" id="ba" style="height:{h(a["value"]):.0f}px"></div><div class="lab" dir="auto">{_e(a["label"])}</div></div>'
            f'<div class="col" id="cb" style="left:{600 * u:.0f}px"><div class="num" id="nb" dir="ltr">{a["value"]:.{dec}f}</div>'
            f'<div class="bar hot" id="bb" style="height:{h(b["value"]):.0f}px"></div><div class="lab" dir="auto">{_e(b["label"])}</div></div>'
            f'<svg id="arrow" width="{W}" height="{H}" style="position:absolute;inset:0">'
            f'<path id="ap" d="M{445 * u:.0f},{1475 - h(a["value"]) + 20 * u:.0f} Q{545 * u:.0f},{1480 - h(b["value"]) + 60 * u:.0f} '
            f'{635 * u:.0f},{1480 - h(b["value"]) + 30 * u:.0f}" '
            f'stroke="{c["accent"]}" stroke-width="{10 * u:.0f}" fill="none" stroke-linecap="round" '
            f'style="filter:drop-shadow(0 0 {12 * u:.0f}px {c["accent"]})"/></svg>'
            + (f'<div id="chg" dir="ltr">{_e(spec["change"])}</div>' if spec.get("change") else "")
            + (f'<div id="chs" dir="auto"><span class="pill">{_e(spec["change_sub"])}</span></div>' if spec.get("change_sub") else ""))
    css = (BASE_CSS % {"g": "16", "py": "14", "px": "54", "bw": "1.6", "sy": "6", "sb": "24"}
           + f"#bg{{position:absolute;inset:0;background:{c['night']};"
           f"background:radial-gradient(120% 80% at 50% 30%,{c['glow2']} 0,{c['night']} 75%);"
           f"background-image:linear-gradient({c['accent']}26 1px,transparent 1px),linear-gradient(90deg,{c['accent']}26 1px,transparent 1px),"
           f"radial-gradient(120% 80% at 50% 30%,{c['glow2']} 0,{c['night']} 75%);"
           f"background-size:{60 * u:.0f}px {60 * u:.0f}px}}"
           f".t{{position:absolute;left:0;right:0;text-align:center;color:#fff}}"
           f"#title{{top:{250 * u:.0f}px;font-family:Karb;font-size:{96 * u:.0f}px}}"
           f"#sub{{top:{380 * u:.0f}px;font-family:Klatin;font-size:{44 * u:.0f}px;letter-spacing:{8 * u:.0f}px;color:{c['accent']}}}"
           f".col{{position:absolute;bottom:{360 * u:.0f}px;width:{300 * u:.0f}px;display:flex;flex-direction:column;align-items:center;gap:{18 * u:.0f}px}}"
           f".bar{{width:{200 * u:.0f}px;border-radius:{18 * u:.0f}px {18 * u:.0f}px 0 0;transform-origin:bottom;"
           f"background:linear-gradient(180deg,#ffffffcc,#ffffff33);box-shadow:0 0 {30 * u:.0f}px #ffffff33}}"
           f".bar.hot{{background:linear-gradient(180deg,{c['accent']},{c['neon']});box-shadow:0 0 {50 * u:.0f}px {c['accent']}aa}}"
           f".num{{font-family:Ktech;font-size:{96 * u:.0f}px;color:#fff;text-shadow:0 0 {16 * u:.0f}px #ffffff66}}"
           f"#nb{{color:{col_up};text-shadow:0 0 {18 * u:.0f}px {col_up}aa}}"
           f".lab{{font-family:Kar;font-size:{60 * u:.0f}px;color:#fff;opacity:.95}}"
           f"#chg{{position:absolute;left:0;right:0;text-align:center;top:{455 * u:.0f}px;font-family:Khero;font-size:{120 * u:.0f}px;"
           f"background-image:linear-gradient(180deg,{c['accent']},{c['accent2']});-webkit-background-clip:text;background-clip:text;"
           f"color:transparent;filter:drop-shadow(0 0 {20 * u:.0f}px {c['accent']})}}"
           f"#chs{{position:absolute;left:0;right:0;text-align:center;top:{610 * u:.0f}px}}"
           f"#chs .pill{{display:inline-block;font-family:Kar;font-size:{56 * u:.0f}px;color:#fff;padding:{16 * u:.0f}px {70 * u:.0f}px;"
           f"border-radius:999px;background:linear-gradient(180deg,rgba(58,52,74,.86),rgba(30,26,42,.84));"
           f"border:{1.8 * u:.1f}px solid rgba(255,255,255,.42)}}")
    plen = 900 * u
    ta, tb = a.get("t", 0.6), b.get("t", 2.0)
    script = [
        'tl.fromTo("#bg",{opacity:0},{opacity:1,duration:.25},0);',
        _enter("#title", 0.15, "rise", u), _enter("#sub", 0.3, "rise", u),
        f'tl.fromTo("#ca",{{opacity:0}},{{opacity:1,duration:.3}},{a.get("frame_t", ta)});',
        f'tl.fromTo("#na",{{opacity:0}},{{opacity:1,duration:.2}},{ta});',
        spring_in("#ba", "scaleY:.06", "scaleY:1,duration:.7", "gentle", ta),
        f'tl.fromTo("#cb",{{opacity:0}},{{opacity:1,duration:.2}},{tb});',
        f'tl.fromTo("#bb",{{scaleY:{h(a["value"]) / max(h(b["value"]), 1):.3f}}},{{scaleY:1,duration:1.2,ease:"power2.inOut"}},{tb});',
        f'const cnt={{v:{a["value"]}}};tl.to(cnt,{{v:{b["value"]},duration:1.2,ease:"power2.inOut",'
        f'onUpdate:()=>{{document.getElementById("nb").textContent=cnt.v.toFixed({dec})}}}},{tb});',
        f'tl.fromTo("#ap",{{strokeDasharray:{plen:.0f},strokeDashoffset:{plen:.0f}}},{{strokeDashoffset:0,duration:.8,ease:"power2.out"}},{tb + 0.6});',
    ]
    if spec.get("change"):
        script.append(_enter("#chg", spec.get("change_t", tb + 1.3), "pop", u))
    if spec.get("change_sub"):
        script.append(_enter("#chs", spec.get("change_sub_t", tb + 2.0), "rise", u))
    return _doc(size, d, css, body, "\n  ".join(script), font_files, True)


def _sweep(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    """A diagonal band of accent-coloured light that crosses the frame; the frame is fully covered at spec['peak']."""
    W, H = size
    c = _colors(style)
    d = spec["dur"]
    p = min(spec.get("peak", 0.16), d - 0.05)
    css = (BASE_CSS % {"g": "16", "py": "14", "px": "54", "bw": "1.6", "sy": "6", "sb": "24"}
           + f"#band{{position:absolute;left:-150%;top:-50%;width:140%;height:200%;transform:rotate(18deg);opacity:0;"
           f"background:linear-gradient(90deg,{c['neon']}00 0%,{c['accent']}cc 30%,{c['pale']} 50%,{c['accent']}cc 70%,{c['neon']}00 100%)}}"
           f"#wash{{position:absolute;inset:0;opacity:0;background:radial-gradient(circle at 50% 45%,{c['pale']} 0%,{c['accent']} 70%,{c['neon']} 100%)}}")
    script = ['tl.set("#band",{opacity:1},0);',
              f'tl.fromTo("#band",{{xPercent:0}},{{xPercent:190,duration:{d:.3f},ease:"power2.inOut"}},0);',
              f'tl.fromTo("#wash",{{opacity:0}},{{opacity:.92,duration:{p * 0.8:.3f},ease:"power2.in"}},{p * 0.2:.3f});',
              f'tl.to("#wash",{{opacity:0,duration:{max(d - p - 0.02, 0.1):.3f},ease:"power2.out"}},{p + 0.02:.3f});']
    return _doc(size, d, css, '<div id="wash"></div><div id="band"></div>', "\n  ".join(script), font_files, False)


def _leak(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    """Red tint -> warm white flare -> orange fall-off. The flare peaks at spec['peak'] (default 0.12 s), which
    should sit on the cut."""
    d = spec["dur"]
    p = spec.get("peak", 0.12)
    side = spec.get("side", "left")
    ox = "15%" if side == "left" else "85%"
    css = (BASE_CSS % {"g": "16", "py": "14", "px": "54", "bw": "1.6", "sy": "6", "sb": "24"}
           + "#red{opacity:0;position:absolute;inset:0;background:radial-gradient(ellipse at %s 50%%,rgba(255,40,70,.75),rgba(200,0,60,.45) 60%%,rgba(120,0,40,.25))}" % ox
           + "#flare{opacity:0;position:absolute;inset:-10%%;background:radial-gradient(ellipse at %s 45%%,rgba(255,252,240,1) 0%%,rgba(255,236,200,.97) 40%%,rgba(255,190,120,.85) 75%%)}" % ox
           + "#org{opacity:0;position:absolute;inset:0;background:radial-gradient(ellipse at %s 40%%,rgba(255,170,60,.85),rgba(255,120,30,.5) 55%%,rgba(255,90,20,.15))}" % ox)
    script = [f'tl.fromTo("#red",{{opacity:0}},{{opacity:1,duration:{p * 0.5:.3f},ease:"none"}},0);',
              f'tl.to("#red",{{opacity:0,duration:.06}},{p * 0.8:.3f});',
              f'tl.fromTo("#flare",{{opacity:0,scale:.9}},{{opacity:1,scale:1,duration:{p * 0.5:.3f},ease:"power2.in"}},{p * 0.5:.3f});',
              f'tl.to("#flare",{{opacity:0,duration:.1,ease:"power1.out"}},{p + 0.03:.3f});',
              f'tl.fromTo("#org",{{opacity:0}},{{opacity:1,duration:.05}},{p:.3f});',
              f'tl.to("#org",{{opacity:0,duration:{max(d - p - 0.05, 0.1):.3f},ease:"power2.out"}},{p + 0.05:.3f});']
    return _doc(size, d, css, '<div id="red"></div><div id="org"></div><div id="flare"></div>',
                "\n  ".join(script), font_files, False)


def _endcard(spec: dict, style: dict, size: tuple, font_files: dict, logo: str | None) -> str:
    W, H = size
    u = W / 1080
    c = _colors(style)
    d = spec["dur"]
    lockup = (f'<img id="logo" src="{_e(logo)}" style="width:{spec.get("logo_w", 0.66) * 100:.0f}%">' if logo else
              f'<div id="logo" style="font-family:Klatin;font-size:{60 * u:.0f}px;color:{c["end_ink"]}">{_e(spec.get("text", ""))}</div>')
    css = (BASE_CSS % {"g": "16", "py": "14", "px": "54", "bw": "1.6", "sy": "6", "sb": "24"}
           + "#wb{position:absolute;inset:0;background:#000;display:flex;align-items:center;justify-content:center}"
           + "#veil{position:absolute;inset:0;background:#4a4a4a;opacity:0}")
    if spec.get("slide"):  # a white panel sweeps in from the left over the last shot, the logo blurs in on it
        css += (f"#wb{{background:transparent}}#pn{{position:absolute;inset:0;background:#fff;box-shadow:{60 * u:.0f}px 0 {50 * u:.0f}px #fff}}#logo{{position:relative}}")
        lockup = '<div id="pn"></div>' + lockup
        script = [f'tl.fromTo("#pn",{{xPercent:-120}},{{xPercent:0,duration:{spec.get("slide", .45)},ease:"power2.inOut"}},0);',
                  'tl.fromTo("#logo",{opacity:0,filter:"blur(%.0fpx)"},{opacity:1,filter:"blur(0px)",duration:.55,'
                  'ease:"power2.out"},.25);' % (10 * u)]
    elif spec.get("from_white"):  # entered through a light burn: the flare's white is already the card
        script = ['tl.set("#wb",{backgroundColor:"#ffffff"},0);',
                  'tl.fromTo("#logo",{opacity:0,filter:"blur(%.0fpx)"},{opacity:1,filter:"blur(0px)",duration:.55,'
                  'ease:"power2.out"},.2);' % (10 * u)]
    else:
        script = ['tl.fromTo("#wb",{backgroundColor:"#000000"},{backgroundColor:"#3c3c3c",duration:.12,ease:"none"},.1);',
                  'tl.to("#wb",{backgroundColor:"#ffffff",duration:.55,ease:"power2.out"},.22);',
                  spring_in("#logo", "opacity:0,scale:.96", "opacity:1,scale:1,duration:.55", "gentle", .22),
                  'tl.to("#logo",{scale:1.02,duration:%.2f,ease:"sine.out"},.77);' % max(d - 1.1, 0.3)]
    fade = spec.get("fade", 0.9)  # the closing veil: grey by default, black with fade_to
    css = css.replace("#veil{position:absolute;inset:0;background:#4a4a4a",
                      f"#veil{{position:absolute;inset:0;background:{spec.get('fade_to', '#4a4a4a')}")
    script.append('tl.fromTo("#veil",{opacity:0},{opacity:%s,duration:%.2f,ease:"%s"},%.2f);'  # to a colour: linear
                  % (1 if spec.get("fade_to") else .8, fade - 0.05, "none" if spec.get("fade_to") else "power1.in",
                     d - fade))
    return _doc(size, d, css, f'<div id="wb">{lockup}</div><div id="veil"></div>', "\n  ".join(script),
                font_files, False)


def _glass_css(c: dict, u: float) -> str:
    return (f".glass{{background:linear-gradient(160deg,rgba(255,255,255,.14),rgba(255,255,255,.04));"
            f"border:{1.6 * u:.1f}px solid rgba(255,255,255,.22);border-radius:{34 * u:.0f}px;"
            f"box-shadow:0 {18 * u:.0f}px {50 * u:.0f}px rgba(0,0,0,.35),inset 0 0 {30 * u:.0f}px {c['accent']}22;"
            f"backdrop-filter:blur({8 * u:.0f}px)}}"
            f".ib{{border-radius:{24 * u:.0f}px;background:linear-gradient(135deg,{c['light']},{c['accent']} 55%,{c['deep']});"
            f"box-shadow:0 0 {30 * u:.0f}px {c['accent']}cc;display:flex;align-items:center;justify-content:center}}")


def _tiles(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    """A grid of glass tiles (icon + label) that pop in one by one; optional heading above."""
    W, H = size
    u = W / 1080
    c = _colors(style)
    d = spec["dur"]
    x, y = spec.get("pos", [0.5, 0.3])
    cols = spec.get("cols", 2)
    tw = spec.get("tile_w", 440) * u
    th = spec.get("tile_h", 250) * u
    gap = 28 * u
    head = spec.get("title")
    rows = []
    script = []
    if head:
        script.append(_enter("#th", spec.get("title_t", 0.0), "rise", u))
    for i, it in enumerate(spec["items"]):
        icon = ICONS.get(it.get("icon", "chart"), ICONS["chart"])
        rows.append(f'<div id="t{i}" class="glass tile"><div class="ib" style="width:{96 * u:.0f}px;height:{96 * u:.0f}px">'
                    f'<svg viewBox="0 0 100 100" style="width:62%;height:62%">{icon}</svg></div>'
                    f'<div class="tl" dir="auto">{_e(it["text"])}</div>'
                    + (f'<div class="tn">{i + 1:02d}</div>' if spec.get("numbers", True) else "") + '</div>')
        script.append(spring_in(f"#t{i}", f'scale:.7,opacity:0,y:{50 * u:.0f},filter:"blur({12 * u:.0f}px)"',
                                'scale:1,opacity:1,y:0,filter:"blur(0px)",duration:.5', "snappy",
                                it.get("t", 0.3 + i * 0.4)))
    script.append(f'tl.to("#tg, #th",{{opacity:0,y:{-20 * u:.0f},filter:"blur({10 * u:.0f}px)",duration:.3,ease:"power2.in"}},{d - 0.3:.2f});')
    css = (BASE_CSS % {"g": "16", "py": "14", "px": "54", "bw": "1.6", "sy": "6", "sb": "24"} + _glass_css(c, u)
           + f"#wrap{{position:absolute;left:{x * 100:.2f}%;top:{y * 100:.2f}%;width:{cols * tw + (cols - 1) * gap:.0f}px;"
           f"margin-left:{-(cols * tw + (cols - 1) * gap) / 2:.0f}px;display:flex;flex-direction:column;gap:{gap:.0f}px}}"
           f"#th{{text-align:center;font-family:Karb;font-size:{64 * u:.0f}px;color:#fff;text-shadow:0 0 {16 * u:.0f}px {c['accent']}}}"
           f"#tg{{display:grid;grid-template-columns:repeat({cols},{tw:.0f}px);gap:{gap:.0f}px;direction:rtl}}"
           f".tile{{background:linear-gradient(160deg,rgba(52,30,86,.92),rgba(20,13,34,.94)) !important;position:relative;height:{th:.0f}px;box-sizing:border-box;padding:{26 * u:.0f}px;display:flex;flex-direction:column;"
           f"justify-content:space-between;align-items:flex-start}}"
           f".tl{{font-family:Karb;font-size:{46 * u:.0f}px;color:#fff;line-height:1.15;align-self:stretch;text-align:right}}"
           f".tn{{position:absolute;top:{18 * u:.0f}px;left:{24 * u:.0f}px;font-family:Khero;font-size:{60 * u:.0f}px;color:{c['accent']};opacity:.85}}")
    body = ('<div id="wrap">' + (f'<div id="th" dir="auto">{_e(head)}</div>' if head else "")
            + f'<div id="tg">{"".join(rows)}</div></div>')
    return _doc(size, d, css, body, "\n  ".join(script), font_files, True)


def _poll(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    """An Instagram-style question card with two options; the choice highlight swings between them."""
    W, H = size
    u = W / 1080
    c = _colors(style)
    d = spec["dur"]
    x, y = spec.get("pos", [0.5, 0.35])
    w = 820 * u
    a, b = spec["options"]
    ta, tb = spec.get("t_a", 0.5), spec.get("t_b", 1.2)
    css = (BASE_CSS % {"g": "16", "py": "14", "px": "54", "bw": "1.6", "sy": "6", "sb": "24"} + _glass_css(c, u)
           + f"#pc{{position:absolute;left:{x * 100:.2f}%;top:{y * 100:.2f}%;width:{w:.0f}px;margin-left:{-w / 2:.0f}px;"
           f"box-sizing:border-box;padding:{40 * u:.0f}px;display:flex;flex-direction:column;gap:{26 * u:.0f}px;"
           f"background:linear-gradient(160deg,{c['glow']}f2,{c['night']}f2)}}"
           f"#q{{font-family:Karb;font-size:{62 * u:.0f}px;color:#fff;text-align:center;line-height:1.2}}"
           f".op{{position:relative;height:{118 * u:.0f}px;border-radius:{60 * u:.0f}px;border:{2.4 * u:.1f}px solid rgba(255,255,255,.3);"
           f"display:flex;align-items:center;justify-content:center;overflow:hidden;font-family:Karb;font-size:{56 * u:.0f}px;color:#fff}}"
           f".op i{{position:absolute;inset:0;background:linear-gradient(90deg,{c['neon']},{c['accent']});transform-origin:right;transform:scaleX(0)}}"
           f".op span{{position:relative}}")
    body = (f'<div id="pc" class="glass"><div id="q" dir="auto">{_e(spec["question"])}</div>'
            f'<div class="op" id="oa"><i></i><span dir="auto">{_e(a)}</span></div>'
            f'<div class="op" id="ob"><i></i><span dir="auto">{_e(b)}</span></div></div>')
    script = [spring_in("#pc", f'scale:.8,opacity:0,y:{60 * u:.0f},filter:"blur({14 * u:.0f}px)"',
                        'scale:1,opacity:1,y:0,filter:"blur(0px)",duration:.5', "snappy", 0),
              _enter("#oa", min(ta, 0.45), "rise", u), _enter("#ob", min(tb, 0.6), "rise", u),
              f'tl.to("#oa i",{{scaleX:1,duration:.45,ease:SPRING.gentle}},{ta + 0.25});',
              f'tl.to("#oa i",{{scaleX:0,duration:.35,ease:"power2.in"}},{tb + 0.2});',
              f'tl.to("#ob i",{{scaleX:1,duration:.45,ease:SPRING.gentle}},{tb + 0.35});',
              f'tl.to("#pc",{{opacity:0,y:{-30 * u:.0f},filter:"blur({10 * u:.0f}px)",duration:.3,ease:"power2.in"}},{d - 0.3:.2f});']
    return _doc(size, d, css, body, "\n  ".join(script), font_files, True)


def _balance(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    """Opaque desk background with a balance scale in the panel zone (top ~12-50%). Demand items land on one pan,
    supply items on the other, and the beam tips by the given degrees per item. Used as a desk card: the speaker
    cut-out stands under it."""
    W, H = size
    u = W / 1080 * spec.get("scale", 1.0)
    c = _colors(style)
    d = spec["dur"]
    cx, py = W / 2, spec.get("pivot_y", 0.30) * H
    build = spec.get("build_t", 0.35)  # when the stand starts drawing (0 under a covering transition)
    L = spec.get("beam", 760) * u
    sides = {"right": spec["right"], "left": spec["left"]}   # {label, items:[{text, icon, t}], deg}
    chips, script, events = [], [], []
    for side, sgn in (("right", 1), ("left", -1)):
        info = sides[side]
        for k, it in enumerate(info["items"]):
            cid = f"{side[0]}{k}"
            icon = ICONS.get(it.get("icon", "chart"), ICONS["chart"])
            chips.append(f'<div class="chip" id="{cid}" data-side="{side}" data-k="{k}"><div class="ib ci">'
                         f'<svg viewBox="0 0 100 100" style="width:64%;height:64%">{icon}</svg></div>'
                         f'<span dir="auto">{_e(it["text"])}</span></div>')
            events.append((it["t"], cid, sgn * info.get("deg", 5)))
        # labels ride the pans (draw() sets their x/y), so they only fade in: a y tween would fight draw(). Without
        # a time a label arrives with its pan (on a continuing desk it is simply there).
        lab_t = info.get("t")
        if lab_t is None and not spec.get("instant"):
            lab_t = build + 0.12
        script.append(f'tl.fromTo("#lab_{side}",{{opacity:0}},{{opacity:1,duration:.3,ease:"power2.out"}},{lab_t});'
                      if lab_t is not None else f'tl.set("#lab_{side}",{{opacity:1}},0);')
    angle = sum(dl for t, cid, dl in events if t is None)
    for t, cid, delta in events:
        if t is None:
            script.append(f'tl.set("#{cid}",{{opacity:1}},0);')
    events = sorted(e for e in events if e[0] is not None)
    script.append(f'st.a={angle:.2f};draw();')
    chip_h, gap_c = 98 * u, 8 * u
    most = max(len(spec["right"]["items"]), len(spec["left"]["items"]), 1)
    rope = most * (chip_h + gap_c) + 40 * u  # the chip stack hangs fully below the beam
    for t, cid, delta in events:
        angle += delta
        k = int(next(x for x in chips if f'id="{cid}"' in x).split('data-k="')[1].split('"')[0])
        # the chip drops from just under the pan's yoke, never from above the pan (it crossed the strings)
        drop = max(30 * u, rope - 4 * u - (k + 1) * chip_h - k * gap_c - 14 * u)
        script.append(f'tl.fromTo("#{cid}",{{y:{-drop:.0f},opacity:0,scale:.85}},{{y:0,opacity:1,scale:1,duration:.45,'
                      f'ease:"bounce.out"}},{t});tl.to("#{cid}",{{opacity:1,duration:.08}},{t});')
        script.append(f'tl.to(st,{{a:{angle:.2f},duration:.9,ease:"elastic.out(1,.45)",onUpdate:draw}},{t + 0.17});')
    if spec.get("verdict"):
        script.append(_enter("#verdict", spec.get("verdict_t", d - 2.2), "pop", u))
    base_y = max(0.5 * H, py + rope + 110 * u)  # the stand's foot sits below the hanging pans
    css = (BASE_CSS % {"g": "16", "py": "14", "px": "54", "bw": "1.6", "sy": "6", "sb": "24"} + _glass_css(c, u)
           + f"#bg{{position:absolute;inset:0;background:radial-gradient(120% 70% at 50% 25%,{c['glow']} 0,{c['card_bg']} 70%,{c['night']} 100%)}}"
           f"#grid{{position:absolute;inset:0;opacity:.09;background-image:linear-gradient({c['accent']} 1px,transparent 1px),"
           f"linear-gradient(90deg,{c['accent']} 1px,transparent 1px);background-size:{60 * u:.0f}px {60 * u:.0f}px}}"
           f".streak{{position:absolute;width:160%;height:8%;left:-30%;transform:rotate(-22deg);opacity:.16;"
           f"background:linear-gradient(90deg,transparent,{c['accent']} 45%,transparent)}}"
           f"#ttl{{position:absolute;top:{0.135 * H:.0f}px;left:0;right:0;text-align:center}}"
           f"#ttl .e{{font-family:Klatin;font-size:{30 * u:.0f}px;letter-spacing:{8 * u:.0f}px;color:{c['accent']}}}"
           f"#ttl .h{{font-family:Karb;font-size:{66 * u:.0f}px;color:#fff;margin-top:{6 * u:.0f}px}}"
           f"#post{{position:absolute;left:{cx - 9 * u:.0f}px;top:{py:.0f}px;width:{18 * u:.0f}px;height:{base_y - py:.0f}px;"
           f"background:linear-gradient(180deg,{c['pale']},{c['accent']});border-radius:{9 * u:.0f}px}}"
           f"#base{{position:absolute;left:{cx - 150 * u:.0f}px;top:{base_y - 14 * u:.0f}px;width:{300 * u:.0f}px;height:{28 * u:.0f}px;"
           f"border-radius:{14 * u:.0f}px;background:linear-gradient(90deg,{c['neon']},{c['accent']});box-shadow:0 0 {30 * u:.0f}px {c['accent']}}}"
           f"#beam{{position:absolute;left:{cx - L / 2:.0f}px;top:{py - 9 * u:.0f}px;width:{L:.0f}px;height:{18 * u:.0f}px;border-radius:{9 * u:.0f}px;"
           f"background:linear-gradient(90deg,{c['pale']},{c['accent']},{c['pale']});box-shadow:0 0 {26 * u:.0f}px {c['accent']}}}"
           f"#hub{{position:absolute;left:{cx - 26 * u:.0f}px;top:{py - 26 * u:.0f}px;width:{52 * u:.0f}px;height:{52 * u:.0f}px;border-radius:50%;"
           f"background:#fff;box-shadow:0 0 {30 * u:.0f}px #fff}}"
           f".pan{{position:absolute;width:{330 * u:.0f}px;height:0}}"
           f".pan .rope{{position:absolute;top:0;width:{3 * u:.0f}px;height:{rope:.0f}px;background:#d9c2ff99}}"
           f".pan .rope.l{{left:{8 * u:.0f}px}}.pan .rope.r{{left:{319 * u:.0f}px}}"
           f".pan .yoke{{position:absolute;left:{8 * u:.0f}px;top:0;width:{314 * u:.0f}px;height:{3 * u:.0f}px;background:#d9c2ff99}}"
           f".pan .tray{{position:absolute;left:0;top:{rope:.0f}px;width:{330 * u:.0f}px;height:{22 * u:.0f}px;border-radius:0 0 {40 * u:.0f}px {40 * u:.0f}px;"
           f"background:linear-gradient(180deg,{c['pale']},{c['accent']});box-shadow:0 0 {24 * u:.0f}px {c['accent']}}}"
           f".pan .stackc{{position:absolute;left:0;width:{330 * u:.0f}px;top:{rope - 4 * u:.0f}px;transform:translateY(-100%);display:flex;flex-direction:column-reverse;gap:{8 * u:.0f}px;align-items:center}}"
           f".chip{{opacity:0;display:flex;align-items:center;gap:{12 * u:.0f}px;height:{chip_h:.0f}px;padding:0 {22 * u:.0f}px 0 {12 * u:.0f}px;"
           f"border-radius:{43 * u:.0f}px;background:rgba(20,14,34,.85);border:{1.6 * u:.1f}px solid rgba(255,255,255,.25);"
           f"font-family:Karb;font-size:{42 * u:.0f}px;color:#fff;white-space:nowrap;direction:rtl}}"
           f".ci{{width:{74 * u:.0f}px;height:{74 * u:.0f}px;border-radius:50%}}"
           f".lab{{position:absolute;width:{330 * u:.0f}px;text-align:center;font-family:Karh;font-size:{64 * u:.0f}px;color:#fff;"
           f"text-shadow:0 0 {20 * u:.0f}px {c['accent']}}}"
           f"#verdict{{position:absolute;left:0;right:0;top:{0.405 * H:.0f}px;text-align:center;font-family:Karb;font-size:{50 * u:.0f}px}}"
           f"#verdict .up{{color:{c['up']};text-shadow:0 0 {14 * u:.0f}px {c['up']}}}#verdict .dn{{color:{c['down']};text-shadow:0 0 {14 * u:.0f}px {c['down']}}}")
    right_chips = "".join(x for x in chips if 'data-side="right"' in x)
    left_chips = "".join(x for x in chips if 'data-side="left"' in x)
    verdict = ""
    if spec.get("verdict"):
        v = spec["verdict"]
        verdict = f'<div id="verdict"><span class="up">{_e(v[0])}</span>&nbsp;&nbsp;&nbsp;<span class="dn">{_e(v[1])}</span></div>'
    body = (f'<div id="bg"></div><div id="grid"></div><div class="streak" style="top:20%"></div><div class="streak" style="top:62%"></div>'
            f'<div id="ttl"><div class="e">{_e(spec.get("eyebrow", ""))}</div><div class="h" dir="auto">{_e(spec.get("title", ""))}</div></div>'
            f'<div id="post"></div><div id="base"></div><div id="beam"></div><div id="hub"></div>'
            f'<div class="lab" id="lab_right" dir="auto">{_e(sides["right"]["label"])}</div>'
            f'<div class="lab" id="lab_left" dir="auto">{_e(sides["left"]["label"])}</div>'
            f'<div class="pan" id="pan_right"><div class="yoke"></div><div class="rope l"></div><div class="rope r"></div><div class="tray"></div><div class="stackc">{right_chips}</div></div>'
            f'<div class="pan" id="pan_left"><div class="yoke"></div><div class="rope l"></div><div class="rope r"></div><div class="tray"></div><div class="stackc">{left_chips}</div></div>'
            f'{verdict}')
    draw = (f'const st={{a:0}};const cx={cx:.1f},py={py:.1f},L={L:.1f},pw={330 * u:.1f};'
            f'function draw(){{const r=st.a*Math.PI/180;gsap.set("#beam",{{rotation:st.a}});'
            f'for(const [id,s] of [["right",1],["left",-1]]){{const x=cx+s*L/2*Math.cos(r),y=py+s*L/2*Math.sin(r);'
            f'gsap.set("#pan_"+id,{{x:x-pw/2,y:y}});gsap.set("#lab_"+id,{{x:x-pw/2,y:y+{rope + 36 * u:.0f}}});}}}}'
            f'draw();')
    if spec.get("instant"):  # continues a balance already on screen: no entrance
        script.insert(0, 'tl.fromTo(".streak",{xPercent:-8},{xPercent:8,duration:%.2f,ease:"none"},0);' % d)
    else:
        bg_in = spec.get("bg_in", .3)
        script.insert(0, ('tl.set("#bg, #grid",{opacity:1},0);' if bg_in <= 0 else
                          f'tl.fromTo("#bg, #grid",{{opacity:0}},{{opacity:1,duration:{bg_in:.2f}}},0);')
                         + 'tl.fromTo(".streak",{xPercent:-8},{xPercent:8,duration:%.2f,ease:"none"},0);' % d
                         + _enter("#ttl", min(0.2, build), "rise", u)
                         + spring_in("#post, #base, #beam, #hub", "opacity:0,scaleY:.2",
                                     f"opacity:1,scaleY:1,duration:{0.5 if build >= .3 else .25},"
                                     f"stagger:{0.06 if build >= .3 else .02}", "gentle", build)
                         + f'tl.fromTo(".pan",{{opacity:0}},{{opacity:1,duration:.25}},{build + 0.12});')
    script.insert(0, draw)
    return _doc(size, d, css, body, "\n  ".join(script), font_files, True)


WAVE_PATHS = ("M100 0 C 30 250,170 750,100 1000 C 30 1250,170 1750,100 2000",
              "M100 0 C 168 240,40 760,100 1000 C 168 1240,40 1760,100 2000",
              "M100 0 C 55 300,150 700,100 1000 C 55 1300,150 1700,100 2000")
WAVE_LANES = ((6, 22, 1), (36, 30, -1), (64, 26, 1))  # left %, seconds per loop, direction


def _wave_parts(spec: dict, style: dict, size: tuple, opaque: bool = True) -> tuple[str, str, list]:
    """(css, body, script) for the flowing-wave ambience: three vertical line streams drifting over the brand ground,
    each tiling every half of its height so it loops with no jump. Colours and opacities: the style's `wave` list."""
    u = size[0] / 1080
    d = spec["dur"]
    acc = style.get("accent", "#ff7a1a")
    lines = style.get("wave") or [[acc, .5], [style.get("live", _mix(acc, "#ffffff", .3)), .34],
                                  [_mix(acc, "#ffffff", .55), .22]]
    ground = style.get("bg", "#101114") if opaque else "transparent"
    css = (f"#wv{{position:absolute;inset:0;background:{ground};overflow:hidden}}"
           f".w{{position:absolute;top:0;height:200%;width:40%}}"
           f".w path{{fill:none;stroke-width:{1.4 * spec.get('weight', 1.6) * u:.2f}px;vector-effect:non-scaling-stroke}}")
    body, script = [], []
    for i, ((left, period, sign), (color, alpha), path) in enumerate(zip(WAVE_LANES, lines, WAVE_PATHS)):
        body.append(f'<svg id="w{i}" class="w" viewBox="0 0 200 2000" preserveAspectRatio="none" '
                    f'style="left:{left}%;opacity:{alpha}"><path d="{path}" stroke="{color}"/></svg>')
        start = -((spec.get("phase", 0.0) % period) / period * 50)
        if sign < 0:  # flows the other way: start half a loop up and travel down
            start = -50 - start
        span = d / period * 50 * sign
        script.append(f'tl.fromTo("#w{i}",{{yPercent:{start:.3f}}},{{yPercent:{start - span:.3f},duration:{d},'
                      f'ease:"none"}},0);')
    return css, f'<div id="wv">{"".join(body)}</div>', script


def _wave(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    css, body, script = _wave_parts(spec, style, size, spec.get("opaque", True))
    return _doc(size, spec["dur"], css, body, "\n  ".join(script), font_files, False)


def _mark(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    """A bar logo mark on its badge, then the wordmark and an optional line, over the wave.

    The mark comes from the style's `mark`: {"view": 100, "radius": 24, "badge": "#hex", "word": "name",
    "bars": [[colour, x, height], ...], "bar_w": 14, "top": 10}, e.g. four rising bars
    [["#4c6ef5", 12, 30], ["#4c6ef5", 34, 50], ["#4c6ef5", 56, 70], ["#4c6ef5", 78, 90]]. The bars grow down from their tops one after
    another, the wordmark follows, and the bars give one soft pulse before the end. Never recoloured."""
    mk = style.get("mark")
    if not mk:
        raise ValueError("kit 'mark' needs a style with a `mark` (bar geometry and colours)")
    W, H = size
    u = W / 1080
    d = spec["dur"]
    c = _colors(style)
    badge = spec.get("size", 220) * u
    view, bw, top = mk.get("view", 100), mk.get("bar_w", 14), mk.get("top", 10)
    bars = mk["bars"]
    svg = (f'<svg id="mk" viewBox="0 0 {view} {view}" style="width:{badge:.0f}px;height:{badge:.0f}px">'
           f'<rect width="{view}" height="{view}" rx="{mk.get("radius", 24)}" fill="{mk.get("badge", "#000000")}" '
           'stroke="rgba(255,255,255,.14)" stroke-width="1.5"/>'
           + "".join(f'<rect class="bar" id="b{i}" x="{x}" y="{top}" width="{bw}" height="{h}" rx="{bw / 2}" fill="{col}"/>'
                     for i, (col, x, h) in enumerate(bars)) + "</svg>")
    word = _e(spec.get("word", mk.get("word", "")))
    line = f'<div id="tg">{_e(spec["text"])}</div>' if spec.get("text") else ""
    wcss, wave, wscript = _wave_parts(spec, style, size) if spec.get("wave", True) else ("", "", [])
    css = (wcss + f"#lk{{position:absolute;left:50%;top:{spec.get('y', 0.46) * 100:.1f}%;transform:translate(-50%,-50%);"
           f"display:flex;flex-direction:column;align-items:center;gap:{40 * u:.0f}px}}"
           f"#row{{display:flex;align-items:center;gap:{badge * .31:.0f}px}}"
           f"#wm{{font-family:Kword,sans-serif;font-size:{badge * .6:.0f}px;letter-spacing:.005em;color:{c['ink']};line-height:1}}"
           f"#tg{{font-family:Kthin,Kword,sans-serif;font-size:{spec.get('text_size', 46) * u:.0f}px;color:{c['ink']};"
           f"opacity:.86;letter-spacing:-.01em}}"
           f".bar{{transform-box:fill-box;transform-origin:50% 0%}}")
    t0 = 0.25
    script = [*wscript, spring_in("#mk", "scale:.9,opacity:0", "scale:1,opacity:1,duration:.5", "gentle", t0)]
    for i in range(len(bars)):
        script.append(spring_in(f"#b{i}", "scaleY:0", "scaleY:1,duration:.55", "snappy", t0 + .18 + i * .12))
    script.append(spring_in("#wm", f"x:{-30 * u:.0f},opacity:0", "x:0,opacity:1,duration:.5", "gentle", t0 + .7))
    if line:
        script.append(f'tl.fromTo("#tg",{{opacity:0,y:{14 * u:.0f}}},{{opacity:.86,y:0,duration:.6,ease:"power2.out"}},'
                      f'{t0 + 1.15:.2f});')
    pulse = max(d - 1.3, t0 + 1.8)
    for i in range(len(bars)):  # one soft pulse, a wave through the bars
        script.append(f'tl.to("#b{i}",{{scaleY:.82,duration:.22,ease:"sine.inOut",yoyo:true,repeat:1}},'
                      f'{pulse + i * .1:.2f});')
    if spec.get("fade_out", True):
        script.append(f'tl.to("#lk",{{opacity:0,duration:.35,ease:"power2.in"}},{d - .4:.2f});')
    return _doc(size, d, css, f'{wave}<div id="lk"><div id="row">{svg}<div id="wm">{word}</div>'
                f'</div>{line}</div>', "\n  ".join(script), font_files, False)


def _sticker(spec: dict, style: dict, size: tuple, font_files: dict, img: str | None) -> str:
    """An image (a logo when it is named, a character reaction) as a die-cut sticker: a white cut line built from four
    zero-blur shadows and a soft lift, a bouncy pop in, a gentle wiggle while it holds, a quick pop out."""
    W, H = size
    u = W / 1080
    d = spec["dur"]
    x, y = spec.get("pos", [0.75, 0.3])
    w = spec.get("w", 0.28) * W
    rot = spec.get("rot", -6)
    edge = spec.get("edge", "#FFFFFF")
    r = spec.get("edge_px", 7) * u
    ring = "" if edge in (None, "none") else " ".join(
        f"drop-shadow({dx * r:.1f}px {dy * r:.1f}px 0 {edge})" for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    css = (f"#sk{{position:absolute;left:{x * 100:.2f}%;top:{y * 100:.2f}%;width:{w:.0f}px;"
           f"transform:translate(-50%,-50%) rotate({rot}deg)}}"
           f"#sk img{{width:100%;display:block;filter:{ring} drop-shadow(0 {8 * u:.0f}px {12 * u:.0f}px rgba(0,0,0,.35))}}")
    script = [spring_in("#sk img", "scale:0,rotation:-14", "scale:1,rotation:0,duration:.5", "bouncy", 0.0)]
    if spec.get("wiggle", True) and d > 1.2:
        script.append('tl.to("#sk img",{rotation:4,duration:.18,ease:"sine.inOut",yoyo:true,repeat:3},.6);')
    script.append(f'tl.to("#sk img",{{scale:0,rotation:10,duration:.22,ease:"back.in(2)"}},{max(d - .25, .5):.2f});')
    return _doc(size, d, css, f'<div id="sk"><img src="{_e(img or "")}"></div>', "\n  ".join(script), font_files,
                False)


def _title(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    """A slam title: a tilted dark slab with a halftone texture and an offset
    accent slab behind it slam in from the side; the word lands as ransom-note tiles (each Latin letter on its own
    tile, alternating light-on-dark, dark-on-light and light-on-accent, with its own size and tilt); jagged shards
    cut across the corners; a small sub-line hangs off the slab; while it holds the halftone dots drift and
    the accent slab sways. Arabic stays one tile per word, so its letters keep
    their joins. `letters: "sticker"` (in the spec or the style's `title`) keeps the slab but sets the word in the
    brand's own face instead: solid light letters set like a heading, every letter the same size and upright. Colours: style `title` {dark, accent, light} or the style's bg / accent / ink."""
    import random
    W, H = size
    u = W / 1080
    d = spec["dur"]
    t = {**{"dark": "#121212", "accent": style.get("accent", "#ff7a1a"), "light": "#FFFFFF"}, **style.get("title", {})}
    x, y = spec.get("pos", [0.5, 0.3])
    tilt = spec.get("tilt", -7)
    size_px = spec.get("size", 150) * u
    text = str(spec["text"])
    rng = random.Random(spec.get("seed", len(text)))
    arabic = any("؀" <= ch <= "ۿ" for ch in text)
    looks = [(t["light"], t["dark"]), (t["dark"], t["light"]), (t["light"], t["accent"])]
    sticker = spec.get("letters", t.get("letters", "tiles")) == "sticker"
    tiles = []
    units = text.split() if arabic else list(text)
    for i, ch in enumerate(units):
        if ch == " ":
            tiles.append(f'<i class="gap" style="width:{size_px * .28:.0f}px"></i>')
            continue
        if sticker:
            tiles.append(f'<b class="tl lt" style="font-family:{"Karb" if arabic else "Klatin"},sans-serif">'
                         f'{_e(ch)}</b>')
            continue
        fg, bg = looks[(i + rng.randint(0, 2)) % 3] if not arabic else (t["light"], t["accent"] if i % 2 else t["dark"])
        sc = 1.0 if arabic else rng.choice((0.78, 0.92, 1.0, 1.18, 1.3))
        rot = rng.uniform(-10, 10) if not arabic else rng.uniform(-3, 3)
        dy = 0 if arabic else rng.uniform(-0.12, 0.12) * size_px  # letters ride above and below the line
        font = "Karb" if arabic else "Klatin"
        rim = f";outline:{max(2, 3 * u):.0f}px solid {t['light']}" if bg == t["accent"] else ""  # accent on dark reads
        tiles.append(f'<b class="tl" style="color:{fg};background:{bg};font-family:{font},sans-serif;'
                     f'font-size:{size_px * sc:.0f}px;transform:translateY({dy:.0f}px) rotate({rot:.1f}deg){rim}">'
                     f'{_e(ch)}</b>')
    sub = (f'<div id="sub"><span>{_e(spec["sub"])}</span></div>' if spec.get("sub") else "")
    lettering = ""
    if sticker:  # solid letters set like a heading, tracked tight; no outline (an edge plus a cut line reads hollow)
        lettering = (f".lt{{color:{t['light']};font-size:{size_px:.0f}px;padding:0;box-shadow:none;"
                     f"margin-right:-.01em}}#row{{gap:{size_px * .28 if arabic else 0:.0f}px}}")  # Arabic: whole words, spaced
    dots = (f"radial-gradient({t['accent']}55 {2.2 * u:.1f}px,transparent {2.6 * u:.1f}px) 0 0/{11 * u:.0f}px "
            f"{11 * u:.0f}px")
    css = (f"#tt{{position:absolute;left:{x * 100:.2f}%;top:{y * 100:.2f}%;transform:translate(-50%,-50%) "
           f"rotate({tilt}deg)}}"
           f"#ti{{position:relative}}#slab,#slab2,#slab3{{position:absolute;left:-{70 * u:.0f}px;right:-{70 * u:.0f}px;top:-{34 * u:.0f}px;"
           f"bottom:-{34 * u:.0f}px;clip-path:polygon(4% 0,100% 6%,96% 100%,0 92%)}}"
           f"#slab{{background:{t['dark']}}}"
           f"#dots{{position:absolute;left:-{180 * u:.0f}px;top:-{180 * u:.0f}px;right:0;bottom:0;background:{dots}}}"
           f"#slab3{{background:{t['light']};transform:scale(1.035,1.13) rotate(-1.2deg)}}"
           f"#slab2{{background:{t['accent']};transform:translate({22 * u:.0f}px,{18 * u:.0f}px)}}"
           f"#row{{position:relative;display:flex;align-items:center;gap:{8 * u:.0f}px;white-space:nowrap;"
           f"flex-direction:{'row-reverse' if arabic else 'row'}}}"  # Arabic words run right to left
           f".tl{{display:inline-block;font-weight:900;line-height:1;padding:{6 * u:.0f}px {12 * u:.0f}px "
           f"{4 * u:.0f}px;box-shadow:{5 * u:.0f}px {5 * u:.0f}px 0 {t['dark']}}}"
           f".gap{{display:inline-block}}"
           f"{lettering}"
           f".shard{{position:absolute;background:{t['light']};height:{10 * u:.0f}px}}"
           f"#sub{{position:absolute;right:-{40 * u:.0f}px;bottom:-{78 * u:.0f}px;transform:rotate({-tilt * 0.6:.1f}deg)}}"
           f"#sub span{{display:inline-block;background:{t['light']};color:{t['dark']};font-family:Klatin,sans-serif;"
           f"font-weight:900;font-size:{size_px * .3:.0f}px;padding:{6 * u:.0f}px {16 * u:.0f}px;"
           f"box-shadow:{5 * u:.0f}px {5 * u:.0f}px 0 {t['accent']}}}")
    shards = (f'<i class="shard" id="sh0" style="width:{220 * u:.0f}px;left:-{120 * u:.0f}px;top:-{58 * u:.0f}px;'
              f'transform:rotate(-14deg)"></i>'
              f'<i class="shard" id="sh1" style="width:{160 * u:.0f}px;right:-{110 * u:.0f}px;bottom:-{50 * u:.0f}px;'
              f'transform:rotate(-14deg);background:{t["accent"]}"></i>')
    script = ['tl.fromTo("#slab2",{xPercent:-120},{xPercent:0,duration:.16,ease:"power4.out"},0);',
              'tl.fromTo("#slab3",{xPercent:120},{xPercent:0,duration:.16,ease:"power4.out"},.03);',
              'tl.fromTo("#slab",{xPercent:120},{xPercent:0,duration:.16,ease:"power4.out"},.04);',
              f'tl.fromTo("#ti",{{x:{-14 * u:.0f}}},{{x:0,duration:.18,ease:"elastic.out(1.2,.35)"}},.2);',
              'tl.fromTo(".tl",{scale:2.4,opacity:0},{scale:1,opacity:1,duration:.14,ease:"power3.out",stagger:.045},.12);',
              'tl.fromTo(".shard",{scaleX:0},{scaleX:1,duration:.18,ease:"power4.out",stagger:.06},.22);']
    if sub:
        script.append('tl.fromTo("#sub",{y:40,opacity:0},{y:0,opacity:1,duration:.2,ease:"back.out(2)"},.42);')
    hold = max(d - .6, .4)  # the background breathes while it holds: the dots drift, the accent slab sways
    script.append(f'tl.fromTo("#dots",{{x:0,y:0}},{{x:{min(hold, 6) * 26 * u:.0f},y:{min(hold, 6) * 26 * u:.0f},'
                  f'duration:{hold:.2f},ease:"none"}},.3);')
    ox, oy = 22 * u, 18 * u  # the accent slab's resting offset (its CSS translate), stated so GSAP keeps it
    script.append(f'tl.fromTo("#slab2",{{x:{ox:.0f},y:{oy:.0f}}},{{x:{ox + 9 * u:.0f},y:{oy - 6 * u:.0f},duration:.9,'
                  f'ease:"sine.inOut",yoyo:true,repeat:{max(1, int(hold / .9))},immediateRender:false}},.35);')
    if d > 1.4:  # never quite still: a small restless jitter while it holds
        script.append(f'tl.fromTo("#row",{{rotation:-.8}},{{rotation:.8,duration:.24,ease:"steps(2)",yoyo:true,'
                      f'repeat:{max(1, int((d - 1.1) / .24))}}},.6);')
    script.append(f'tl.fromTo("#ti",{{xPercent:0}},{{xPercent:-160,duration:.2,ease:"power3.in",immediateRender:false}},'
                  f'{max(d - .22, .6):.2f});')
    body = (f'<div id="tt"><div id="ti"><i id="slab2"></i><i id="slab3"></i><i id="slab"><i id="dots"></i></i>{shards}<div id="row">{"".join(tiles)}'
            f'</div>{sub}</div></div>')
    return _doc(size, d, css, body, "\n  ".join(script), font_files, arabic)


def _glow_card(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    """Full-screen purple light (bright in one corner, deep violet across, near-black in the other) with a statement
    in white. A `scroll` line runs across the frame left to right (the end of an Arabic sentence arrives last), then
    settles small in the middle at `settle`; `sub` lines blur in under it."""
    W, H = size
    u = W / 1080
    c = _colors(style)
    d = spec["dur"]
    y = spec.get("y", 0.47)
    css = (BASE_CSS % {"g": "16", "py": "14", "px": "54", "bw": "1.6", "sy": "6", "sb": "24"}
           + f"#gbg{{position:absolute;inset:-10%;background:radial-gradient(60% 45% at 100% 0%,{c['light']} 0%,{c['accent']}00 100%),"
           f"radial-gradient(70% 55% at 0% 100%,{c['accent']}cc 0%,{c['accent']}00 100%),"
           f"radial-gradient(80% 60% at 75% 70%,{c['night']} 0%,{c['night']}00 100%),"
           f"linear-gradient(160deg,{c['neon']} 0%,{c['bevel2']} 45%,{c['bevel1']} 100%)}}"
           f".gl{{position:absolute;left:0;width:100%;text-align:center;white-space:nowrap;color:#fff;"
           f"text-shadow:0 0 {10 * u:.0f}px rgba(255,255,255,.65),0 0 {28 * u:.0f}px {c['light']}aa}}"
           f"#gm{{top:{y * 100:.1f}%;transform:translateY(-50%)}}#gm span{{display:inline-block}}")
    bi = spec.get("bg_in", .12)  # 0: the card is simply there (entered under a light burn's white)
    rows, script = [], ['tl.set("#gbg",{opacity:1},0);' if bi <= 0 else f'tl.fromTo("#gbg",{{opacity:0}},{{opacity:1,duration:{bi}}},0);',
                        f'tl.fromTo("#gbg",{{x:0,y:0}},{{x:{-40 * u:.0f},y:{30 * u:.0f},duration:{d:.2f},ease:"none"}},0);']
    for i, ln in enumerate(spec["lines"]):
        fs = ln.get("size", 64) * u
        font = ln.get("font", "alm")
        if ln.get("scroll"):  # starts with its first word near the right edge, ends with its last near the left
            a, b = ln["scroll"]
            rows.append(f'<div class="gl" id="gm"><span id="g{i}" dir="rtl" style="font-family:K{font};font-size:{fs:.0f}px">'
                        f'{_e(ln["text"])}</span></div>')
            script.append(f'tl.fromTo("#g{i}",{{opacity:0,filter:"blur({10 * u:.0f}px)"}},{{opacity:1,filter:"blur(0px)",duration:.3}},{a:.2f});')
            script.append(f'tl.fromTo("#g{i}",{{x:()=>{W * 0.4:.0f}-document.getElementById("g{i}").offsetWidth/2}},'
                          f'{{x:()=>document.getElementById("g{i}").offsetWidth/2-{W * 0.4:.0f},duration:{b - a:.2f},ease:"none"}},{a:.2f});')
            if ln.get("settle") is not None:
                s = ln["settle"]
                script.append(f'tl.to("#g{i}",{{x:0,scale:{ln.get("settle_scale", .62)},duration:.25,ease:"power2.out"}},{s:.2f});')
        else:
            top = ln.get("y", y + 0.045)
            rows.append(f'<div class="gl" style="top:{top * 100:.1f}%;transform:translateY(-50%)"><span id="g{i}" dir="auto" '
                        f'style="display:inline-block;font-family:K{font};font-size:{fs:.0f}px">{_e(ln["text"])}</span></div>')
            script.append(spring_in(f"#g{i}", f'opacity:0,filter:"blur({14 * u:.0f}px)",y:{16 * u:.0f}',
                                    'opacity:1,filter:"blur(0px)",y:0,duration:.45', "gentle", ln.get("t", .3)))
    return _doc(size, d, css, f'<div id="gbg"></div>{"".join(rows)}', "\n  ".join(script), font_files, True)


def _flag(spec: dict, style: dict, size: tuple, font_files: dict) -> str:
    """A waving cloth flag drawn on a canvas in vertical strips (a travelling sine wave lifts and shades each one),
    tilted and slid in from the frame edge. design: 'jp' (white, red disc)."""
    W, H = size
    u = W / 1080
    d = spec["dur"]
    x, y = spec.get("pos", [0.2, 0.2])
    fw = spec.get("w", 0.36) * W
    fh = fw * 2 / 3
    pad = fh * 0.25
    css = (BASE_CSS % {"g": "16", "py": "14", "px": "54", "bw": "1.6", "sy": "6", "sb": "24"}
           + f"#fw{{position:absolute;left:{x * 100:.2f}%;top:{y * 100:.2f}%;transform:translate(-50%,-50%) rotate({spec.get('rotate', -14)}deg)}}"
           f"#fc{{display:block;filter:drop-shadow(0 {10 * u:.0f}px {18 * u:.0f}px rgba(0,0,0,.45))}}")
    cw, ch = round(fw + pad * 2), round(fh + pad * 2)
    script = f"""
  const cv=document.getElementById("fc"),cx=cv.getContext("2d"),st={{p:0}};
  const src=document.createElement("canvas");src.width={round(fw)};src.height={round(fh)};
  const sx=src.getContext("2d");sx.fillStyle="#f4f4f6";sx.fillRect(0,0,src.width,src.height);
  sx.fillStyle="#c8102e";sx.beginPath();sx.arc(src.width/2,src.height/2,src.height*0.3,0,Math.PI*2);sx.fill();
  function draw(){{cx.clearRect(0,0,{cw},{ch});const n=60,sw=src.width/n;
    for(let i=0;i<n;i++){{const k=i/n,ph=st.p*6.0-k*7.0,amp={fh * 0.09:.1f}*k,dy=Math.sin(ph)*amp,sh=Math.cos(ph)*k;
      cx.drawImage(src,i*sw,0,sw+1,src.height,{pad:.1f}+i*sw,{pad:.1f}+dy,sw+1,src.height);
      cx.fillStyle=sh>0?"rgba(255,255,255,"+(sh*0.22).toFixed(3)+")":"rgba(0,0,0,"+(-sh*0.35).toFixed(3)+")";
      cx.fillRect({pad:.1f}+i*sw,{pad:.1f}+dy,sw+1,src.height);}}}}
  tl.to(st,{{p:{d:.2f},duration:{d:.2f},ease:"none",onUpdate:draw}},0);draw();
  tl.fromTo("#fm",{{xPercent:-70,opacity:0}},{{xPercent:0,opacity:1,duration:.45,ease:"power3.out"}},0);
  tl.to("#fm",{{xPercent:-90,opacity:0,duration:.3,ease:"power2.in"}},{max(d - .3, .1):.2f});"""
    return _doc(size, d, css, f'<div id="fw"><div id="fm"><canvas id="fc" width="{cw}" height="{ch}"></canvas></div></div>', script,
                font_files, False)


def kit_html(spec: dict, style: dict, size: tuple, font_files: dict, logo: str | None = None) -> str:
    t = spec["type"]
    if t == "stack":
        return _stack(spec, style, size, font_files)
    if t == "card":
        return (_glow_card if spec.get("look") == "glow" else _card)(spec, style, size, font_files)
    if t == "flag":
        return _flag(spec, style, size, font_files)
    if t == "badge":
        return _badge(spec, style, size, font_files)
    if t == "bars":
        return _bars(spec, style, size, font_files)
    if t == "leak":
        return _sweep(spec, style, size, font_files) if spec.get("variant") == "sweep" else _leak(spec, style, size, font_files)
    if t == "tiles":
        return _tiles(spec, style, size, font_files)
    if t == "poll":
        return _poll(spec, style, size, font_files)
    if t == "balance":
        return _balance(spec, style, size, font_files)
    if t == "endcard":
        return _endcard(spec, style, size, font_files, logo)
    if t == "wave":
        return _wave(spec, style, size, font_files)
    if t == "mark":
        return _mark(spec, style, size, font_files)
    if t == "sticker":
        return _sticker(spec, style, size, font_files, logo)
    if t == "title":
        return _title(spec, style, size, font_files)
    raise ValueError(f"unknown kit graphic {t!r}")


def describe(spec: dict) -> str:
    return json.dumps({k: v for k, v in spec.items() if k not in ("slot",)}, ensure_ascii=False)
