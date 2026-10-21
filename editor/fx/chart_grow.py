"""Chart grow: a line or bar chart that grows on the wall behind the speaker (their head passes in front of it).

The look: day letters across the top, faint vertical guides, a glowing line rising
left to right with dots popping as it reaches them, and a pill tag ("SCALE ↗") hanging on a dashed drop line over
one point. Here the line draws by a moving clip with a head dot that carries a counting value; bars rise on springs
with their values counting up. Data comes only from the spec (values, labels, unit): nothing is invented.

Placement: on a wide/mid shot the chart goes on the wall above the head, behind the person matte. On a close-up
the wall is all head, so `place: auto` switches to a frosted-glass chart card in the free space under the chin.
"""
import json
import math

from . import _glass as G

NAME = "chart_grow"
DOC = ("A line/bar chart that grows behind the speaker (or on a glass card on close-ups), values counting up, "
       "with an optional pill tag. Data only from values/labels.")
BEST_FOR = ["finance", "product", "corporate", "any"]
DUR = (2.0, 10)
PARAMS = {
    "values": [],        # 2-12 numbers (required): the data, in order
    "labels": [],        # one short label per value (days, months, names); optional
    "kind": "line",      # line | bars
    "unit": "",          # suffix on the numbers: "%", "k", " users"
    "prefix": "",        # prefix on the numbers: "$"
    "tag": "",           # pill text over one point, e.g. "SCALE ↗"
    "tag_at": None,      # index of the tagged point (default the last); bars: the highlighted bar
    "value": True,       # show the counting value (line: at the growing tip; bars: over each bar)
    "caption": "",       # small tracked caption, e.g. "Sample data · weekly users"
    "y_min": None,       # baseline value; default 0 for bars, a padded minimum for lines
    "place": "auto",     # auto | wall (behind the person) | card (frosted card in free space)
}

CARD_W = 896


def card_h(kind, show_val) -> int:
    """Natural card height: a line card carries a big headline value, a bar card only its caption."""
    return 470 if kind == "line" and show_val else 440


def validate(values, labels, kind):
    if not isinstance(values, (list, tuple)) or len(values) < 2:
        raise ValueError("chart_grow needs values: a list of at least 2 numbers (it never invents data)")
    if len(values) > 12:
        raise ValueError("chart_grow: at most 12 values")
    try:
        vals = [float(v) for v in values]
    except (TypeError, ValueError):
        raise ValueError(f"chart_grow: values must be numbers, got {values!r}") from None
    if any(math.isnan(v) or math.isinf(v) for v in vals):
        raise ValueError("chart_grow: values must be finite")
    if labels and len(labels) != len(vals):
        raise ValueError(f"chart_grow: {len(labels)} labels for {len(vals)} values")
    if kind not in ("line", "bars"):
        raise ValueError("chart_grow: kind is line or bars")
    return vals


def value_range(vals, kind, y_min=None):
    hi = max(vals)
    if y_min is not None:
        lo = float(y_min)
    elif kind == "bars":
        lo = min(0.0, min(vals))
    else:  # a line shows the movement: its floor sits just under the lowest value
        lo = min(vals) - 0.12 * (hi - min(vals) or abs(hi) or 1)
    if hi <= lo:
        hi = lo + 1
    return lo, hi


def points(vals, box, kind, y_min=None, head=0.18):
    """Pixel (x, y) per value inside box (x0, y0, x1, y1); `head` keeps headroom above the max for the tag."""
    x0, y0, x1, y1 = box
    lo, hi = value_range(vals, kind, y_min)
    n = len(vals)
    if kind == "bars":
        step = (x1 - x0) / n
        xs = [x0 + step * (i + 0.5) for i in range(n)]
    else:
        xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
    top = y0 + (y1 - y0) * head
    return [(x, y1 - (v - lo) / (hi - lo) * (y1 - top)) for x, v in zip(xs, vals)]


def bar_path(x, y, w, base) -> str:
    """A bar standing on the baseline with only its top corners rounded."""
    r = min(14.0, w / 4, (base - y) / 2)
    x0, x1 = x - w / 2, x + w / 2
    return (f"M{x0:.1f},{base:.1f} L{x0:.1f},{y + r:.1f} Q{x0:.1f},{y:.1f} {x0 + r:.1f},{y:.1f} "
            f"L{x1 - r:.1f},{y:.1f} Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f} L{x1:.1f},{base:.1f} Z")


def decimals(vals) -> int:
    return 0 if all(float(v).is_integer() for v in vals) else (1 if all(round(v, 1) == v for v in vals) else 2)


def inv_sine_inout(y: float) -> float:
    """Progress p where GSAP's sine.inOut reaches y (the line's x fraction): times when the tip reaches a point."""
    y = min(1.0, max(0.0, y))
    return math.acos(1 - 2 * y) / math.pi


def wall_box(W, H, hd):
    """The plot box on the wall above the head, or None when the wall there is too small (a close-up)."""
    regs = G.free_regions(W, H, hd)
    _, y0, _, y1 = regs["above"]
    if y1 - y0 < 0.17 * H:
        return None
    return (0.08 * W, y0, 0.85 * W, min(y1, y0 + 0.36 * H))


def render(ctx):
    kind = ctx.param("kind", "line")
    vals = validate(ctx.param("values"), ctx.param("labels") or [], kind)
    hd = G.head(ctx)
    mode = ctx.param("place", "auto")
    box = wall_box(ctx.W, ctx.H, hd) if mode in ("auto", "wall") else None
    if mode == "wall" and box is None:  # forced: the band just under the safe top, head or not
        box = (0.08 * ctx.W, G.SAFE_TOP * ctx.H, 0.85 * ctx.W, (G.SAFE_TOP + 0.3) * ctx.H)
    if box is not None:
        layer = ctx.layer(_page(ctx, vals, kind, box, None), "chart")
        return ctx.stack([ctx.src, layer, ctx.person()])
    spot = G.place(ctx.W, ctx.H, hd, CARD_W, card_h(kind, ctx.param("value", True)))
    layer = ctx.layer(_page(ctx, vals, kind, None, spot), "chart")
    return G.glass_stack(ctx, layer, blur=30)


def _fmt_js(prefix, unit, dec):
    return (f"v => {json.dumps(prefix)} + (+v).toLocaleString('en-US', {{minimumFractionDigits: {dec}, "
            f"maximumFractionDigits: {dec}}}) + {json.dumps(unit)}")


def _page(ctx, vals, kind, wall, spot):
    b = G.brand(ctx.style)
    labels = [str(x) for x in (ctx.param("labels") or [])]
    n = len(vals)
    unit, prefix = ctx.param("unit", "") or "", ctx.param("prefix", "") or ""
    tag = ctx.param("tag", "") or ""
    tag_at = ctx.param("tag_at")
    tag_at = n - 1 if tag_at is None else int(tag_at)
    if not 0 <= tag_at < n:
        raise ValueError(f"chart_grow: tag_at {tag_at} outside 0-{n - 1}")
    show_val = ctx.param("value", True)
    caption = ctx.param("caption", "") or ""
    dec = decimals(vals)
    fmt = lambda v: f"{prefix}{v:,.{dec}f}{unit}"
    ink, hi = b["ink"], b["hi"]
    d = ctx.dur
    card = spot is not None

    # ---- geometry (all in page pixels; the card case lays out at natural size and scales the group) --------
    if card:
        ox, oy, s = spot["x"], spot["y"], spot["scale"]
        pad = 40
        CARD_H = card_h(kind, show_val)
        big_on = kind == "line" and show_val
        head_h = 28 + (34 if caption else 0) + (68 if big_on else 0)
        lab_h = 52 if labels else 10
        box = (pad + 8, head_h + 20, CARD_W - pad - 8, CARD_H - pad + 6 - lab_h)
        lab_y = box[3] + 18
    else:
        ox, oy, s = 0, 0, 1
        cap_h = 40 if caption else 0
        lab_h = 40 if labels else 0
        x0, y0, x1, y1 = wall
        lab_y = y0 + cap_h
        box = (x0, y0 + cap_h + lab_h + 14, x1, y1)
    room = ((96 if card else 128) if tag and kind == "line" else 30) + (70 if kind == "bars" and show_val else 0)  # space over the max for tag/value
    pts = points(vals, box, kind, ctx.param("y_min"), head=min(0.45, room / max(1.0, box[3] - box[1])))
    base_y = box[3]  # the baseline value always sits on the box bottom
    bx0, by0, bx1, by1 = box

    # colours: a market look colours each rise/fall; other styles stay on their accent
    def seg_col(i):  # colour of the move into point i
        if b["kind"] != "market" or i == 0:
            return b["up"] if b["kind"] == "market" else b["line"]
        return b["up"] if vals[i] >= vals[i - 1] else b["down"]
    line_col = (b["up"] if vals[-1] >= vals[0] else b["down"]) if b["kind"] == "market" else b["line"]

    t0 = 0.35                              # chart furniture in, then the data grows
    D = min(1.9, max(0.9, d * 0.42))       # growth duration
    els, js = [], []
    grid = "".join(f'<line class="g" x1="{x:.1f}" y1="{by0 - 8:.1f}" x2="{x:.1f}" y2="{by1:.1f}"/>' for x, _ in pts) \
        if kind == "line" else ""
    svg = [f'<line class="base" x1="{bx0:.1f}" y1="{base_y:.1f}" x2="{bx1:.1f}" y2="{base_y:.1f}"/>', grid]

    if kind == "line":
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        area = f"M{pts[0][0]:.1f},{base_y:.1f} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + \
               f" L{pts[-1][0]:.1f},{base_y:.1f} Z"
        svg += [
            (f'<defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{line_col}" '
             f'stop-opacity=".30"/><stop offset="1" stop-color="{line_col}" stop-opacity="0"/></linearGradient>'
             f'<clipPath id="cp"><rect id="cr" x="{bx0 - 20:.1f}" y="{by0 - 60:.1f}" width="0" '
             f'height="{by1 - by0 + 120:.1f}"/></clipPath></defs>'),
            (f'<g clip-path="url(#cp)"><path class="area" d="{area}" fill="url(#ag)"/>'
             f'<polyline class="glow" points="{poly}" stroke="{line_col}"/>'
             f'<polyline class="ln" points="{poly}" stroke="{line_col}"/></g>'),
        ]
        if b["kind"] == "market":  # overlay each falling segment in the down colour
            for i in range(1, n):
                if vals[i] < vals[i - 1]:
                    (xa, ya), (xb, yb) = pts[i - 1], pts[i]
                    svg[-1] = svg[-1].replace(
                        "</g>", f'<line class="ln" x1="{xa:.1f}" y1="{ya:.1f}" x2="{xb:.1f}" y2="{yb:.1f}" '
                                f'stroke="{b["down"]}"/></g>')
        for i, (x, y) in enumerate(pts):
            c = hi if i == tag_at and tag else seg_col(i)
            svg.append(f'<g class="pt" id="pt{i}" transform="translate({x:.1f} {y:.1f})"><g class="pi">'
                       f'<circle r="11" fill="{G.rgba(b["tint"], .9)}" stroke="{c}" stroke-width="4"/>'
                       f'<circle r="4" fill="{ink}"/></g></g>')
        svg.append(f'<g id="tip" transform="translate({pts[0][0]:.1f} {pts[0][1]:.1f})"><circle r="17" '
                   f'fill="{G.rgba(line_col, .25)}"/><circle r="8" fill="{ink}"/></g>')
        xs = [x for x, _ in pts]
        ys = [y for _, y in pts]
        fr = [(x - bx0) / (bx1 - bx0) for x in xs]
        js.append(f"""
  const XS = {json.dumps([round(x, 1) for x in xs])}, YS = {json.dumps([round(y, 1) for y in ys])},
        VS = {json.dumps(vals)}, X0 = {bx0:.1f}, X1 = {bx1:.1f}, fmt = {_fmt_js(prefix, unit, dec)};
  const cr = document.getElementById('cr'), tip = document.getElementById('tip'),
        tv = document.getElementById('tv'), bigv = document.getElementById('bigv'), st = {{p: 0}};
  function at(p) {{
    const x = X0 + (X1 - X0) * p;
    let i = 0; while (i < XS.length - 2 && x > XS[i + 1]) i++;
    const f = Math.max(0, Math.min(1, (x - XS[i]) / (XS[i + 1] - XS[i])));
    return [x, YS[i] + (YS[i + 1] - YS[i]) * f, VS[i] + (VS[i + 1] - VS[i]) * f];
  }}
  function draw() {{
    const [x, y, v] = at(st.p);
    cr.setAttribute('width', Math.max(0, x - X0 + 20));
    tip.setAttribute('transform', `translate(${{x.toFixed(1)}} ${{y.toFixed(1)}})`);
    if (bigv) bigv.textContent = fmt(v);
    if (tv) {{ tv.textContent = fmt(v); tv.parentNode.style.transform =
      `translate(${{Math.max(x, {G.SAFE_LEFT * ctx.W:.1f} + 22 + tv.textContent.length * 28).toFixed(1)}}px, `
      + `${{y.toFixed(1)}}px)`; }}
  }}
  draw();
  tl.to(st, {{p: 1, duration: {D:.3f}, ease: 'sine.inOut', onUpdate: draw}}, {t0:.3f});
  tl.fromTo('#tip', {{opacity: 0}}, {{opacity: 1, duration: .2}}, {t0:.3f});""")
        for i, f in enumerate(fr):
            at = t0 + D * inv_sine_inout(f) - 0.04
            js.append(f"springIn(tl,'#pt{i} .pi',{{scale:0}},{{scale:1,duration:.45}},'bouncy',{max(t0, at):.3f});")
        js.append(f"tl.to('#tip',{{opacity:0,duration:.25,ease:'power2.out'}},{t0 + D + 0.05:.3f});")
        tag_time = t0 + D * inv_sine_inout(fr[tag_at])
    else:
        step = (bx1 - bx0) / n
        bw = min(112, step * 0.5)
        for i, (x, y) in enumerate(pts):
            c = hi if (i == tag_at and (tag or b["kind"] != "market")) else seg_col(i)
            if b["kind"] != "market" and i != tag_at:
                c = G.rgba(b["line"], .55)
            y = min(y, base_y - 4)
            svg.append(f'<g id="bar{i}" class="bar"><path d="{bar_path(x, y, bw, base_y)}" fill="{c}"/></g>')
        js.append(f"const fmt = {_fmt_js(prefix, unit, dec)};")
        for i, (x, _) in enumerate(pts):  # SVG transforms need their origin in user space: the bar's foot
            js.append(f"gsap.set('#bar{i}', {{svgOrigin: '{x:.1f} {base_y:.1f}'}});")
        for i, (x, y) in enumerate(pts):
            at = t0 + i * min(0.16, D / n)
            js.append(f"springIn(tl,'#bar{i}',{{scaleY:0}},{{scaleY:1,duration:.75}},'snappy',{at:.3f});")
            if show_val:
                js.append(f"(() => {{ const el = document.getElementById('bv{i}'), o = {{v: 0}};"
                          f" el.textContent = fmt(0);"
                          f" tl.to(o, {{v: {vals[i]}, duration: .62, ease: 'power3.out',"
                          f" onUpdate: () => el.textContent = fmt(o.v)}}, {at:.3f});"
                          f" tl.fromTo(el, {{opacity: 0}}, {{opacity: 1, duration: .25}}, {at:.3f}); }})();")
                js.append(f"springIn(tl,'#bv{i}',{{y:{base_y - y:.1f}}},{{y:0,duration:.75}},'snappy',{at:.3f});")
        tag_time = t0 + tag_at * min(0.16, D / n) + 0.45

    # ---- labels, value readouts, tag ---------------------------------------------------------------------------
    lab_html = ""
    if labels:
        for i, (x, _) in enumerate(pts):
            em = " em" if (i == tag_at and tag) else ""
            lab_html += f'<div class="lab{em}" style="left:{x:.1f}px;top:{lab_y:.1f}px">{G.esc(labels[i])}</div>'
        js.append("springIn(tl,'.lab',{y:10,opacity:0},{y:0,opacity:1,duration:.5,stagger:.04},'snappy',.1);")
    if kind == "bars" and show_val:
        for i, (x, y) in enumerate(pts):
            els.append(f'<div class="bv" id="bv{i}" style="left:{x:.1f}px;top:{y - 68:.1f}px"></div>')
    if kind == "line" and show_val and not card:
        els.append('<div class="tvw"><div class="tv" id="tv"></div></div>')
    if tag:
        tx, ty = pts[tag_at]
        top_y = ty - (80 if kind == "bars" and show_val else 22) - (70 if card else 96)
        if not card:
            top_y = max(G.SAFE_TOP * ctx.H, top_y)
        pill_w = 34 + len(tag) * 19
        lim = (CARD_W - 20) if card else (1 - G.SAFE_RIGHT) * ctx.W
        px = min(tx - pill_w / 2, lim - pill_w)
        px = max(px, 20 if card else G.SAFE_LEFT * ctx.W)
        if kind == "bars":  # beside the bar's value, no drop line: the bar itself points at it
            half = min(112, (bx1 - bx0) / n * 0.5) / 2
            px = tx + half + 14 if tx + half + 14 + pill_w <= lim else tx - half - 14 - pill_w
            top_y = ty - (64 if show_val else 25)
        else:
            els.append(f'<div id="drop" style="left:{tx - 1:.1f}px;top:{top_y + 50:.1f}px;'
                       f'height:{max(0, ty - top_y - 64):.1f}px"></div>')
            js.append(f"tl.fromTo('#drop',{{scaleY:0}},{{scaleY:1,duration:.35,ease:'power2.out'}},{tag_time:.3f});")
        els.append(f'<div id="pill" style="left:{px:.1f}px;top:{top_y:.1f}px">{G.esc(tag)}</div>')
        js.append(f"springIn(tl,'#pill',{{y:18,scale:.6,opacity:0}},{{y:0,scale:1,opacity:1,duration:.6}},'bouncy',"
                  f"{tag_time + 0.12:.3f});")
    head = ""
    if card:
        big = ""
        if show_val and kind == "line":
            big = f'<div class="big"><span id="bigv">{G.esc(fmt(vals[0]))}</span></div>'
        cap = f'<div class="cap"><span class="dot"></span>{G.esc(caption)}</div>' if caption else ""
        head = f'<div class="head">{cap}{big}</div>'
        js.insert(0, "springIn(tl,'#card',{y:40,scale:.95,opacity:0},{y:0,scale:1,opacity:1,duration:.75},'gentle',0);")
        js.insert(1, "springIn(tl,'.head > *',{y:14,opacity:0},{y:0,opacity:1,duration:.5,stagger:.06},'snappy',.1);")
    elif caption:
        els.append(f'<div class="cap wallcap" style="left:{bx0:.1f}px;top:{wall[1]:.1f}px"><span class="dot"></span>'
                   f'{G.esc(caption)}</div>')
        js.insert(0, "springIn(tl,'.wallcap',{y:12,opacity:0},{y:0,opacity:1,duration:.5},'snappy',.05);")
    js.insert(0, "tl.fromTo('.base,.g',{opacity:0},{opacity:1,duration:.4,ease:'power2.out',stagger:.03},.05);")
    js.append(f"tl.to('#all',{{opacity:0,y:-18,duration:.38,ease:'power2.in'}},{d - 0.4:.3f});")

    W, H = (CARD_W, card_h(kind, show_val)) if card else (ctx.W, ctx.H)
    font = "BrandAR" if G.rtl(labels + [caption]) else "BrandLT"
    shadow = "" if card else "text-shadow:0 2px 14px rgba(0,0,0,.55);"
    css = f"""
#all{{position:absolute;left:0;top:0;width:{ctx.W}px;height:{ctx.H}px}}
#card{{position:absolute;left:{ox:.1f}px;top:{oy:.1f}px;width:{W}px;height:{H}px;transform-origin:0 0}}
#cardin{{position:absolute;inset:0;transform:scale({s:.4f});transform-origin:0 0;width:{W}px;height:{H}px}}
.glass{{position:absolute;inset:0;border-radius:36px;background:linear-gradient(180deg,rgba(255,255,255,.07),
  rgba(255,255,255,0) 35%),{G.rgba(b['tint'], G.GLASS_A)};box-shadow:inset 0 0 0 1.5px rgba(255,255,255,.13),
  inset 0 1.5px 0 rgba(255,255,255,.16)}}
svg{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;overflow:visible}}
.base{{stroke:{G.rgba(ink, .32)};stroke-width:2}}
.g{{stroke:{G.rgba(ink, .13)};stroke-width:1.5}}
.ln{{fill:none;stroke-width:8;stroke-linecap:round;stroke-linejoin:round}}
.glow{{fill:none;stroke-width:18;stroke-linecap:round;stroke-linejoin:round;opacity:.22;filter:blur(7px)}}
.pi{{transform:scale(0)}}
.lab{{position:absolute;transform:translateX(-50%);font-family:"{font}",sans-serif;font-weight:600;font-size:31px;
  color:{G.rgba(ink, .8)};white-space:nowrap;letter-spacing:.04em;{shadow}}}
.lab.em{{color:{ink}}}
.bv{{position:absolute;transform:translateX(-50%);font-weight:800;font-size:50px;color:{ink};
  font-variant-numeric:tabular-nums;letter-spacing:-.02em;white-space:nowrap;{shadow}}}
.tvw{{position:absolute;left:0;top:0}}
.tv{{position:absolute;right:22px;bottom:16px;font-weight:800;font-size:46px;color:{ink};white-space:nowrap;
  font-variant-numeric:tabular-nums;letter-spacing:-.02em;{shadow}}}
#pill{{position:absolute;height:50px;line-height:50px;padding:0 20px;border-radius:99px;background:{hi};
  color:{b['on_hi']};font-weight:800;font-size:29px;letter-spacing:.04em;white-space:nowrap;
  box-shadow:0 6px 18px rgba(0,0,0,.28)}}
#drop{{position:absolute;width:0;border-left:2.5px dashed {G.rgba(hi, .9)};transform-origin:top}}
.head{{position:absolute;left:40px;right:40px;top:30px}}
.cap{{display:flex;align-items:center;gap:12px;font-size:23px;font-weight:600;letter-spacing:.18em;
  text-transform:uppercase;color:{G.rgba(ink, .72)};white-space:nowrap}}
.wallcap{{position:absolute;{shadow}}}
.dot{{width:9px;height:9px;border-radius:50%;background:{hi};flex:none}}
.big{{margin-top:4px;font-size:60px;line-height:64px;font-weight:800;letter-spacing:-.03em;color:{ink};font-variant-numeric:tabular-nums}}"""
    inner = (f'<svg viewBox="0 0 {W} {H}">{"".join(svg)}</svg>{lab_html}{"".join(els)}')
    if card:
        body = f'<div id="all"><div id="card"><div id="cardin"><div class="glass"></div>{head}{inner}</div></div></div>'
    else:
        body = f'<div id="all">{inner}</div>'
    return ctx.page(body, css, "\n  ".join(js))
