"""Line art card: the picture cuts to black and a thin white line drawing draws itself on (a rosette, a star, a
circle, a polygon, a wireframe globe, a pendulum, a wave or a spiral), turning slowly, with a small label above and
a dimmer one below. The voice carries on underneath. The quiet beat of the minimal storytelling style."""
import json
import math

from . import _glass as G

NAME = "line_art"
DOC = ("Full black card where a thin white line drawing draws on (rosette, star, circle, polygon, globe, pendulum, "
       "wave, spiral) with small labels; the voice continues. A calm beat between noir_minimal shots. 1-5 s.")
BEST_FOR = ["any", "corporate"]
DUR = (0.8, 10)
PARAMS = {
    "shape": "rosette",  # rosette | star | circle | polygon | globe | pendulum | wave | spiral
    "label": "",         # small text above the drawing
    "caption": "",       # dimmer text below it
    "size": 0.5,         # drawing size, fraction of the width
    "draw": 1.2,         # s for the line to draw on
    "spin": 12,          # degrees the drawing turns over the window
    "color": "#ffffff",
    "bg": "#000000",
}
SHAPES = ("rosette", "star", "circle", "polygon", "globe", "pendulum", "wave", "spiral")


def _poly(pts, closed=True) -> str:
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return d + (" Z" if closed else "")


def _length(pts, closed=True) -> float:
    pts = list(pts) + ([pts[0]] if closed else [])
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def paths(shape: str, r: float) -> list:
    """[(svg path d, length, opacity, width)] centred on 0,0 with radius r: the main line and any faint ones."""
    out = []

    def add(pts, op=1.0, wid=1.0, closed=True):
        out.append((_poly(pts, closed), _length(pts, closed), op, wid))
    ring = lambda rr, n=180: [(rr * math.cos(2 * math.pi * k / n), rr * math.sin(2 * math.pi * k / n)) for k in range(n)]  # noqa: E731
    if shape == "rosette":  # faint spirograph loops round a bold six-petal star, like a pressed flower
        def petals(n, base, amp, rr, ph=0.0, turn=0.0):
            return [((rr * (base + amp * math.cos(n * t + ph))) * math.cos(t + turn),
                     (rr * (base + amp * math.cos(n * t + ph))) * math.sin(t + turn))
                    for t in (2 * math.pi * k / 240 for k in range(240))]
        for j in range(7):
            add(petals(5, 0.72, 0.22, r, j * math.pi / 7, j * math.pi / 23), 0.28, 0.6)
        add(petals(6, 0.62, 0.38, r * 0.58), 1.0, 1.4)
    elif shape == "star":
        add([((r if k % 2 == 0 else r * 0.42) * math.cos(math.pi * k / 5 - math.pi / 2),
              (r if k % 2 == 0 else r * 0.42) * math.sin(math.pi * k / 5 - math.pi / 2)) for k in range(10)], 1, 1.4)
    elif shape == "circle":
        add(ring(r), 1, 1.4)
        add(ring(r * 0.06, 40), 1, 3)
    elif shape == "polygon":
        add([(r * math.cos(2 * math.pi * k / 9 - math.pi / 2), r * math.sin(2 * math.pi * k / 9 - math.pi / 2))
             for k in range(9)], 1, 1.4)
    elif shape == "globe":
        add(ring(r), 1, 1.4)
        for j in range(1, 6):  # meridians
            rx = r * math.cos(math.pi * j / 6)
            add([(rx * math.cos(2 * math.pi * k / 120), r * math.sin(2 * math.pi * k / 120)) for k in range(120)], 0.7)
        for j in (-2, -1, 0, 1, 2):  # parallels
            y = r * j / 3
            hw = math.sqrt(max(r * r - y * y, 0))
            add([(-hw, y), (hw, y)], 0.7, 1.0, closed=False)
    elif shape == "pendulum":
        add([(0, -r), (0, r * 0.7)], 1, 1.4, closed=False)
        add(ring(r * 0.09, 40), 1, 2.2)
    elif shape == "wave":
        add([(-r + 2 * r * k / 200, r * 0.3 * math.sin(4 * math.pi * k / 200)) for k in range(201)], 1, 1.4, False)
    elif shape == "spiral":
        add([(r * k / 400 * math.cos(6 * math.pi * k / 400), r * k / 400 * math.sin(6 * math.pi * k / 400))
             for k in range(401)], 1, 1.4, False)
    else:
        raise ValueError(f"line_art shape must be one of {SHAPES}")
    return out


def render(ctx):
    shape = ctx.param("shape", PARAMS["shape"])
    if shape not in SHAPES:
        raise ValueError(f"line_art shape must be one of {SHAPES}")
    layer = ctx.layer(_page(ctx, shape), "line-art")
    return ctx.stack([ctx.src, layer])


def _page(ctx, shape):
    P = {k: ctx.param(k, v) for k, v in PARAMS.items()}
    W, H = ctx.W, ctx.H
    r = float(P["size"]) * W / 2
    sw = W / 540  # line width unit
    items = paths(shape, r)
    svg = "".join(f'<path class="p" d="{d}" stroke-width="{wid * sw:.2f}" stroke-opacity="{op}" '
                  f'stroke-dasharray="{ln:.1f}" stroke-dashoffset="{ln:.1f}"/>' for d, ln, op, wid in items)
    if shape == "pendulum":  # the bob swings
        svg = f'<g id="swing">{svg}</g>'
    lab, cap = str(P["label"] or ""), str(P["caption"] or "")
    rtl = G.rtl([lab, cap])
    font = "Tajawal" if rtl else "SoraThin"
    body = '<div id="card"></div>' + (f'<div id="lab" class="t">{G.esc(lab)}</div>' if lab else "") + (
        f'<svg id="art" viewBox="{-W / 2} {-H / 2} {W} {H}" width="{W}" height="{H}"><g id="spin">{svg}</g></svg>'
        + (f'<div id="cap" class="t">{G.esc(cap)}</div>' if cap else ""))
    css = f"""
#card{{position:absolute;inset:0;background:{P['bg']}}}
#art{{position:absolute;inset:0}}
.p{{fill:none;stroke:{P['color']};stroke-linecap:round;stroke-linejoin:round}}
.t{{position:absolute;left:0;right:0;text-align:center;font-family:"{font}",sans-serif;color:{P['color']};
  font-size:{W * 0.04:.0f}px;letter-spacing:.02em;opacity:0;direction:{'rtl' if rtl else 'ltr'}}}
#lab{{top:{H / 2 - r - W * 0.16:.0f}px}}
#cap{{top:{H / 2 + r + W * 0.1:.0f}px;opacity:0;color:{P['color']}99}}"""
    draw = float(P["draw"])
    lens = json.dumps([round(ln, 1) for _, ln, _, _ in items])
    js = (f"const L={lens};document.querySelectorAll('.p').forEach((p,i)=>{{"
          f"tl.to(p,{{strokeDashoffset:0,duration:{draw:.2f},ease:'power2.inOut'}},.1+i*{draw * 0.08:.3f});}});"
          f"tl.fromTo('#spin',{{rotation:0,svgOrigin:'0 0'}},{{rotation:{float(P['spin']):.1f},svgOrigin:'0 0',"
          f"duration:{ctx.dur:.3f},ease:'none'}},0);"
          "tl.fromTo('#lab',{opacity:0,y:8},{opacity:1,y:0,duration:.5,ease:'power2.out'},.15);"
          "tl.fromTo('#cap',{opacity:0},{opacity:.6,duration:.6,ease:'power2.out'}," f"{draw * 0.7:.2f});")
    if shape == "pendulum":
        js += (f"tl.fromTo('#swing',{{rotation:-22,svgOrigin:'0 {-r:.1f}'}},{{rotation:22,svgOrigin:'0 {-r:.1f}',"
               f"duration:.9,ease:'sine.inOut',yoyo:true,repeat:{max(1, int(ctx.dur / 0.9))}}},0);")
    return ctx.page(body, css, js, bg=P["bg"])
