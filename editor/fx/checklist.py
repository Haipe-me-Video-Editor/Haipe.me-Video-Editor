"""Checklist: a frosted-glass to-do card beside (or under) the speaker; items tick off one by one.

The look: a dark glass card, "• ALL YOU NEED TO DO" in small tracked caps, an "n of N"
counter, a segmented progress bar, round checkboxes; upcoming items are placeholder bars that reveal as the one
before is ticked. Here the card is real frosted glass (the footage blurred behind it), placed in free space from
the face landmarks so it never covers the face, and every tick is a spring: the check fills, draws, rings out,
the progress segment fills and the counter rolls.
"""
import itertools

from . import _glass as G

NAME = "checklist"
DOC = ("Frosted to-do card beside/under the speaker; items tick off one by one with a progress counter. "
       "For 'all you need to do', plans, steps, roadmaps.")
BEST_FOR = ["product", "finance", "corporate", "any"]
DUR = (2.0, 12)
PARAMS = {
    "items": [],               # 1-6 short lines (required)
    "title": "All you need to do",
    "ticks": None,             # seconds into the window when each item ticks; default evenly spread. May be shorter
                               # than items (the rest stay open, e.g. "2 of 3")
    "reveal": "progressive",   # "progressive": upcoming items are placeholder bars until the one before ticks;
                               # "all": every item readable from the start
    "place": "auto",           # auto | above | below | left | right: free space next to the head
    "scale": None,             # override the card scale (1 = natural size)
}

W0 = 896          # natural card width cap (px at scale 1): the full safe width
ROW = 78          # row height
PAD = 32
TXT = 45          # item font size
BOX = 48          # checkbox diameter
HDR_Y = 28        # header top


def tick_times(n: int, dur: float, ticks=None) -> list:
    """When each item ticks. Explicit ticks are validated (sorted, inside the window, at most n); the default
    spreads all n between the entrance (~0.5 s) and a hold before the exit."""
    if ticks is not None:
        ticks = [float(t) for t in ticks]
        if len(ticks) > n:
            raise ValueError(f"checklist: {len(ticks)} ticks for {n} items")
        if any(b < a for a, b in itertools.pairwise(ticks)):
            raise ValueError("checklist: ticks must be in order")
        if ticks and (ticks[0] < 0.25 or ticks[-1] > dur - 0.3):
            raise ValueError(f"checklist: ticks must fall between 0.25 and {dur - 0.3:.2f} s")
        return ticks
    a, b = 0.55, max(0.8, dur - 0.95)
    step = (b - a) / n
    return [round(a + step * (i + 1), 3) for i in range(n)]


def reveal_times(n: int, ticks: list, mode: str, enter: float = 0.18) -> list:
    """When each item's text appears (None: stays a placeholder bar)."""
    if mode == "all":
        return [enter + 0.07 * i for i in range(n)]
    out = [enter]
    for i in range(1, n):
        out.append(ticks[i - 1] + 0.16 if i - 1 < len(ticks) else None)
    return out


def text_w(text: str, size: float) -> float:
    """Rough rendered width of a line (Sora/Montserrat semibold average glyph ~0.56 em; Arabic ~0.5 em)."""
    return len(text) * size * (0.5 if G.is_arabic(text) else 0.56)


def card_size(items, title) -> tuple:
    longest = max([text_w(t, TXT) for t in items] + [text_w(title, 24) * 1.35 + 170])
    w = min(W0, max(600, longest + BOX + 24 + 2 * PAD + 24))
    h = HDR_Y + 34 + 16 + 7 + 16 + ROW * len(items) + PAD * 0.55
    return round(w), round(h)


def render(ctx):
    items = [str(t).strip() for t in (ctx.param("items") or []) if str(t).strip()]
    if not items:
        raise ValueError("checklist needs items (1-6 lines)")
    if len(items) > 6:
        raise ValueError("checklist: at most 6 items")
    title = ctx.param("title", PARAMS["title"]) or ""
    ticks = tick_times(len(items), ctx.dur, ctx.param("ticks"))
    reveal = ctx.param("reveal", PARAMS["reveal"])
    if reveal not in ("progressive", "all"):
        raise ValueError("checklist: reveal is progressive or all")
    shows = reveal_times(len(items), ticks, reveal)
    w0, h0 = card_size(items, title)
    hd = G.head(ctx)
    where = ctx.param("place", "auto")
    prefer = ("above", "left", "right", "below") if where == "auto" else (where,)
    spot = G.place(ctx.W, ctx.H, hd, w0, h0, prefer=prefer, max_scale=1.0)
    if ctx.param("scale"):
        spot = G.rescale(spot, ctx.W, ctx.H, w0, h0, float(ctx.param("scale")))
    page = _page(ctx, items, title, ticks, shows, spot, w0, h0)
    layer = ctx.layer(page, "checklist")
    return G.glass_stack(ctx, layer, blur=30)


def _page(ctx, items, title, ticks, shows, spot, w0, h0):
    b = G.brand(ctx.style)
    n = len(items)
    is_rtl = G.rtl(items + [title])
    font = "BrandAR" if is_rtl else "BrandLT"
    hi, ink, tint = b["hi"], b["ink"], b["tint"]
    s = spot["scale"]
    side = {"left": -1, "right": 1}.get(spot["region"], 0)
    # placeholder widths: deterministic, varied like real lines
    ph = [0.42 + 0.33 * ((i * 37 + len(t) * 13) % 10) / 10 for i, t in enumerate(items)]
    rows = "".join(f"""
<div class="row" id="r{i}">
  <div class="box"><i class="ring"></i><i class="burst" id="b{i}"></i><i class="fill" id="f{i}"></i>
    <svg viewBox="0 0 48 48"><path class="chk" id="c{i}" d="M14 24.6 L21 31.4 L34.4 16.8"/></svg></div>
  <div class="txt"><span class="ph" id="p{i}" style="width:{ph[i] * 100:.0f}%"></span><span class="t" id="t{i}">{G.esc(t)}</span></div>
</div>""" for i, t in enumerate(items))
    segs = "".join(f'<div class="seg"><div class="sf" id="s{i}"></div></div>' for i in range(n))
    roll = "".join(f"<span>{k}</span>" for k in range(n + 1))
    of = "من" if is_rtl else "of"
    hdr_y = HDR_Y
    items_y = hdr_y + 34 + 16 + 7 + 16
    css = f"""
#pos{{position:absolute;left:{spot['x']:.1f}px;top:{spot['y']:.1f}px;width:{w0}px;height:{h0}px;
  transform:scale({s:.4f});transform-origin:0 0}}
#card{{position:absolute;inset:0;border-radius:34px;direction:{'rtl' if is_rtl else 'ltr'};font-family:"{font}",sans-serif;
  background:linear-gradient(180deg,rgba(255,255,255,.075),rgba(255,255,255,0) 38%),{G.rgba(tint, G.GLASS_A)};
  box-shadow:inset 0 0 0 1.5px rgba(255,255,255,.13),inset 0 1.5px 0 rgba(255,255,255,.16);overflow:hidden}}
.hd{{position:absolute;left:{PAD}px;right:{PAD}px;top:{hdr_y:.0f}px;height:34px;display:flex;align-items:center;gap:12px;
  font-size:24px;letter-spacing:.18em;text-transform:uppercase;font-weight:600;color:{G.rgba(ink, .72)}}}
.dot{{width:9px;height:9px;border-radius:50%;background:{hi};flex:none}}
.ttl{{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;{'letter-spacing:0;font-size:24px;' if is_rtl else ''}}}
.cnt{{flex:none;display:flex;align-items:center;gap:.32em;letter-spacing:.02em;text-transform:none;font-weight:700;
  font-size:25px;color:{ink};background:rgba(255,255,255,.08);padding:4px 14px;border-radius:99px;
  font-variant-numeric:tabular-nums}}
.roll{{display:inline-block;height:32px;overflow:hidden;line-height:32px}}
.roll .col{{display:flex;flex-direction:column}}
.roll span{{display:block;height:32px;text-align:center}}
.bar{{position:absolute;left:{PAD}px;right:{PAD}px;top:{hdr_y + 34 + 16:.0f}px;height:7px;display:flex;gap:8px}}
.seg{{flex:1;border-radius:9px;background:rgba(255,255,255,.12);overflow:hidden}}
.sf{{width:100%;height:100%;background:{hi};border-radius:9px;transform:scaleX(0);
  transform-origin:{'right' if is_rtl else 'left'} center}}
.items{{position:absolute;left:{PAD - 14}px;right:{PAD - 14}px;top:{items_y:.0f}px}}
#hl{{position:absolute;left:0;right:0;top:3px;height:{ROW - 6}px;border-radius:22px;background:rgba(255,255,255,.075);
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.06)}}
.row{{position:relative;height:{ROW}px;display:flex;align-items:center;gap:22px;padding:0 14px;box-sizing:border-box}}
.row .box{{position:relative;width:{BOX}px;height:{BOX}px;flex:none}}
.box i{{position:absolute;inset:0;border-radius:50%;box-sizing:border-box}}
.box svg{{position:absolute;inset:0;width:{BOX}px;height:{BOX}px;overflow:visible}}
.ring{{border:2.8px solid rgba(255,255,255,.4)}}
.burst{{border:3px solid {hi};opacity:0}}
.fill{{background:{hi};transform:scale(0)}}
.chk{{fill:none;stroke:{b['on_hi']};stroke-width:4.2;stroke-linecap:round;stroke-linejoin:round;
  stroke-dasharray:32;stroke-dashoffset:32}}
.txt{{position:relative;flex:1;height:60px;min-width:0}}
.ph{{position:absolute;{'right' if is_rtl else 'left'}:0;top:25px;height:10px;border-radius:9px;background:rgba(255,255,255,.13)}}
.t{{position:absolute;left:0;right:0;top:0;line-height:60px;font-size:{TXT}px;font-weight:600;color:{ink};
  letter-spacing:-.012em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:0}}"""
    body = f"""<div id="pos"><div id="card">
<div class="hd"><span class="dot"></span><span class="ttl">{G.esc(title)}</span>
  <span class="cnt"><span class="roll"><span class="col" id="roll">{roll}</span></span><span>{of} {n}</span></span></div>
<div class="bar">{segs}</div>
<div class="items"><div id="hl"></div>{rows}</div></div></div>"""
    d = ctx.dur
    js = [
        (f"springIn(tl,'#card',{{x:{side * 60},y:{0 if side else 46},scale:.94,opacity:0}},"
         f"{{x:0,y:0,scale:1,opacity:1,duration:.75}},'gentle',0);"),
        "springIn(tl,'.hd,.bar',{y:14,opacity:0},{y:0,opacity:1,duration:.55,stagger:.05},'snappy',.12);",
        "springIn(tl,'.row .box,.ph',{scale:.6,opacity:0},{scale:1,opacity:1,duration:.5,stagger:.04},'snappy',.16);",
        "tl.fromTo('#hl',{opacity:0},{opacity:1,duration:.3},.3);",
    ]
    for i, t in enumerate(shows):
        if t is None:
            continue
        js.append(f"tl.to('#p{i}',{{opacity:0,duration:.18,ease:'power2.out'}},{t:.3f});")
        js.append(f"springIn(tl,'#t{i}',{{y:16,opacity:0}},{{y:0,opacity:1,duration:.5}},'snappy',{t:.3f});")
    for i, t in enumerate(ticks):
        later = ",immediateRender:false" if i else ""  # several tweens on one property: only the first sets it
        js += [
            f"springIn(tl,'#f{i}',{{scale:0}},{{scale:1,duration:.5}},'bouncy',{t:.3f});",
            f"tl.to('#c{i}',{{strokeDashoffset:0,duration:.26,ease:'power2.out'}},{t + 0.1:.3f});",
            f"tl.fromTo('#b{i}',{{scale:1,opacity:.85}},{{scale:1.85,opacity:0,duration:.55,ease:'power2.out'}},{t + 0.04:.3f});",
            f"tl.to('#t{i}',{{color:'{G.rgba(ink, .6)}',duration:.3,ease:'power2.out'}},{t + 0.08:.3f});",
            f"tl.to('#s{i}',{{scaleX:1,duration:.42,ease:'power3.out'}},{t + 0.04:.3f});",
            f"springIn(tl,'#roll',{{y:{-32 * i}}},{{y:{-32 * (i + 1)},duration:.5{later}}},'snappy',{t + 0.05:.3f});",
        ]
        if i + 1 < len(items):  # the highlight moves on to the next open item
            js.append(f"springIn(tl,'#hl',{{y:{ROW * i}}},{{y:{ROW * (i + 1)},duration:.55{later}}},'snappy',"
                      f"{t + 0.12:.3f});")
        else:
            js.append(f"tl.to('#hl',{{opacity:0,duration:.3,ease:'power2.out'}},{t + 0.12:.3f});")
    js.append(f"tl.to('#card',{{opacity:0,y:-24,scale:.97,duration:.36,ease:'power2.in'}},{d - 0.38:.3f});")
    return ctx.page(body, css, "\n  ".join(js))
