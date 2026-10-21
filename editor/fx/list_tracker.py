"""List tracker: the list video's own index, a small glass panel at the top of the frame listing every item in two
numbered columns, the current one lit in the accent colour (slightly larger) and the rest dimmed, with an optional
big "03/12" counter.

Built to run as a persistent overlay across many back-to-back windows: the layout depends only on the items, the
title and a coarse framing class (never on the exact face position of one window), so window k+1 with
`enter: false` starts on exactly the frame window k ended on, and only the highlight moves (a quick spring), the
counter rolls and, for long lists, the visible rows scroll. The panel sits above the head and shrinks (then shows
a scrolling window of rows) when the head is high, keeping clear of the brows and eyes.
"""
import math

from . import _glass as G

NAME = "list_tracker"
DOC = ("Top-of-frame glass index of a list video: all items in two numbered columns, the current one lit, "
       "big 03/12 counter. Chain back-to-back windows (enter/exit false) for a persistent tracker.")
BEST_FOR = ["product", "finance", "corporate", "any"]
DUR = (0.8, 30)
PARAMS = {
    "items": [],          # every item of the list, short (2-4 words), in order (required, 2-24)
    "current": 0,         # index of the item being talked about now
    "title": "",          # small caps header, e.g. "the roadmap"; empty: no header
    "counter": "big",     # big ("03/12" beside the list) | small (in the header) | none
    "prev": None,         # index lit when the window starts (default: current - 1 when enter is false)
    "enter": True,        # false: start fully shown (continuing a previous list_tracker window)
    "exit": True,         # false: stay up at the end (the next window continues it)
    "size": "auto",       # auto | wide | close | tight: the framing class; pin it for a run across shots
}

PANEL_W = 896      # natural width: the full 9:16 safe width
PAD_X, PAD_Y = 24, 14
ROW_H = 39
HEAD_H = 28        # title row
COUNTER_W = 186
COL_GAP = 26
MIN_SCALE = 0.72

# bottom of the band the panel may use, by framing class, as a fraction of the height
BAND_BOTTOM = {"wide": 0.34, "close": 0.215, "tight": 0.19}


def framing(hd: dict, H: float) -> str:
    """Coarse framing class from the head: wide when the head starts well down the frame, tight when the brows
    are high. Coarse on purpose: neighbouring windows of one shot land in the same class."""
    if hd["skull"] > 0.36 * H:
        return "wide"
    if hd["brow"] < 0.225 * H:
        return "tight"
    return "close"


def rows(n: int) -> int:
    return math.ceil(n / 2)


def cell(i: int, n: int) -> tuple:
    """(column, row) of item i: numbered down the first column, then the second."""
    r = rows(n)
    return (0, i) if i < r else (1, i - r)


def natural_h(n_rows: int, title: bool) -> float:
    return 2 * PAD_Y + (HEAD_H + 4 if title else 0) + n_rows * ROW_H


def fit(n: int, title: bool, band_h: float) -> tuple:
    """(scale, visible rows) so the panel fits the band: shrink to MIN_SCALE, then window the rows."""
    R = rows(n)
    s = min(1.0, band_h / natural_h(R, title))
    if s >= MIN_SCALE:
        return s, R
    s = MIN_SCALE
    head = 2 * PAD_Y + (HEAD_H + 4 if title else 0)
    return s, max(1, min(R, int((band_h / s - head) // ROW_H)))


def scroll_top(i: int, n: int, visible: int) -> int:
    """First visible row so item i's row is in view (kept near the middle), clamped to the list."""
    R = rows(n)
    if visible >= R:
        return 0
    r = cell(i, n)[1]
    return max(0, min(R - visible, r - (visible - 1) // 2))


def state(i: int, current: int) -> str:
    return "cur" if i == current else ("past" if i < current else "next")


def num(k: int, n: int) -> str:
    return str(k).zfill(max(2, len(str(n))))


def render(ctx):
    items = [str(t).strip() for t in (ctx.param("items") or [])]
    if len(items) < 2 or not all(items):
        raise ValueError("list_tracker needs items: 2-24 non-empty lines")
    if len(items) > 24:
        raise ValueError("list_tracker: at most 24 items")
    n = len(items)
    cur = int(ctx.param("current", 0))
    if not 0 <= cur < n:
        raise ValueError(f"list_tracker: current {cur} outside 0-{n - 1}")
    enter, leave = bool(ctx.param("enter", True)), bool(ctx.param("exit", True))
    prev = ctx.param("prev")
    if prev is None:
        prev = cur if enter else max(0, cur - 1)
    prev = int(prev)
    if not 0 <= prev < n:
        raise ValueError(f"list_tracker: prev {prev} outside 0-{n - 1}")
    size = ctx.param("size", "auto")
    if size == "auto":
        size = framing(G.head(ctx), ctx.H)
    if size not in BAND_BOTTOM:
        raise ValueError("list_tracker: size is auto, wide, close or tight")
    page = _page(ctx, items, cur, prev, enter, leave, size)
    return G.glass_stack(ctx, ctx.layer(page, "tracker"), blur=26)


def _page(ctx, items, cur, prev, enter, leave, size):
    b = G.brand(ctx.style)
    n = len(items)
    title = ctx.param("title", "") or ""
    counter = ctx.param("counter", "big")
    if counter not in ("big", "small", "none"):
        raise ValueError("list_tracker: counter is big, small or none")
    is_rtl = G.rtl(items)
    font = "BrandAR" if is_rtl else "BrandLT"
    ink, hi = b["ink"], b["hi"]
    top = G.SAFE_TOP * ctx.H
    band_h = BAND_BOTTOM[size] * ctx.H - top
    s, vis = fit(n, bool(title or counter == "small"), band_h)
    has_head = bool(title or counter == "small")
    R = rows(n)
    big = counter == "big"
    list_x = PAD_X + (COUNTER_W if big else 0)
    col_w = (PANEL_W - list_x - PAD_X - COL_GAP) / 2
    list_y = PAD_Y + (HEAD_H + 4 if has_head else 0)
    ph = natural_h(vis, has_head)
    longest = max(len(t) for t in items)
    num_w = 44
    fs = max(19.0, min(27.0, (col_w - num_w - 16) / (longest * (0.5 if is_rtl else 0.56))))
    px = (ctx.W - PANEL_W * s) / 2  # centred in the frame; the panel never reaches the right safe margin
    px = min(px, (1 - G.SAFE_RIGHT) * ctx.W - PANEL_W * s)

    def X(x, w=0):  # mirror for right-to-left lists
        return PANEL_W - x - w if is_rtl else x

    cells = []
    for i, t in enumerate(items):
        c, r = cell(i, n)
        x = list_x + c * (col_w + COL_GAP)
        st = state(i, prev)
        cells.append(f'<div class="it {st}" id="i{i}" style="left:{X(x, col_w):.1f}px;top:{r * ROW_H:.1f}px;'
                     f'width:{col_w:.1f}px"><span class="n">{num(i + 1, n)}</span>'
                     f'<span class="t">{G.esc(t)}</span></div>')
    hc, hr = cell(prev, n)
    hx = list_x + hc * (col_w + COL_GAP) - 12
    s0, s1 = scroll_top(prev, n, vis), scroll_top(cur, n, vis)
    hl = (f'<div id="hl" style="left:{X(hx, col_w + 24):.1f}px;top:0;width:{col_w + 24:.1f}px;'
          f'transform:translate(0px,{hr * ROW_H:.1f}px)"></div>')
    fade = ""
    if vis < R:  # soft edges where rows scroll out of the window
        fade = ("-webkit-mask-image:linear-gradient(180deg,transparent 0,#000 14px,#000 calc(100% - 14px),transparent);"
                "mask-image:linear-gradient(180deg,transparent 0,#000 14px,#000 calc(100% - 14px),transparent);")
    dB = (f'<span class="d" id="dB" style="opacity:0">{num(cur + 1, n)}</span>'
          if prev != cur else "")
    head = ""
    if has_head:
        small = (f'<span class="sc"><span class="roll"><span class="d" id="dA">{num(prev + 1, n)}</span>'
                 f'{dB}</span>/{num(n, n)}</span>'
                 if counter == "small" else "")
        head = (f'<div class="hd" style="left:{list_x:.1f}px;right:{PAD_X}px">'
                f'<span class="dot"></span><span class="ttl">{G.esc(title)}</span>{small}</div>')
    bigc = ""
    if big:
        bigc = (f'<div class="big" style="left:{X(PAD_X, COUNTER_W - 22):.1f}px;width:{COUNTER_W - 22}px">'
                f'<span class="roll bigroll"><span class="d" id="dA">{num(prev + 1, n)}</span>'
                f'{dB}</span><span class="of">/{num(n, n)}</span></div>'
                f'<div class="vr" style="left:{X(list_x - 16):.1f}px"></div>')
    body = f"""<div id="pos"><div id="panel">{head}{bigc}
<div class="win" style="left:0;right:0;top:{list_y:.1f}px;height:{vis * ROW_H:.1f}px;{fade}">
<div id="list" style="transform:translate(0px,{-s0 * ROW_H:.1f}px)">{hl}{''.join(cells)}</div></div></div></div>"""
    big_fs = min(92.0, ph - 2 * PAD_Y + 10)
    css = f"""
#pos{{position:absolute;left:{px:.1f}px;top:{top:.1f}px;width:{PANEL_W}px;height:{ph:.1f}px;transform:scale({s:.4f});
  transform-origin:0 0}}
#panel{{position:absolute;inset:0;border-radius:28px;font-family:"{font}",sans-serif;
  background:linear-gradient(180deg,rgba(255,255,255,.07),rgba(255,255,255,0) 45%),{G.rgba(b['tint'], G.GLASS_A)};
  box-shadow:inset 0 0 0 1.5px rgba(255,255,255,.13),inset 0 1.5px 0 rgba(255,255,255,.15)}}
.hd{{position:absolute;top:{PAD_Y - 2}px;height:{HEAD_H}px;display:flex;align-items:center;gap:11px;
  direction:{'rtl' if is_rtl else 'ltr'};font-size:19px;font-weight:600;letter-spacing:.2em;text-transform:uppercase;
  color:{G.rgba(ink, .66)}}}
.dot{{width:8px;height:8px;border-radius:50%;background:{hi};flex:none}}
.ttl{{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.sc{{flex:none;font-weight:700;letter-spacing:.04em;color:{ink};font-variant-numeric:tabular-nums;display:flex}}
.roll{{position:relative;display:inline-block;overflow:hidden;vertical-align:bottom}}
.sc .roll{{height:{HEAD_H}px;width:1.35em}}
.roll .d{{position:absolute;left:0;right:0;top:0;text-align:center}}
.big{{position:absolute;top:{PAD_Y}px;bottom:{PAD_Y}px;display:flex;align-items:center;justify-content:center;
  font-variant-numeric:tabular-nums;direction:ltr;white-space:nowrap}}
.bigroll{{height:{big_fs * 1.02:.1f}px;width:{big_fs * 1.24:.1f}px;font-size:{big_fs:.1f}px;line-height:{big_fs * 1.02:.1f}px;
  font-weight:800;letter-spacing:-.04em;color:{hi}}}
.of{{font-size:{max(22, big_fs * 0.34):.1f}px;font-weight:700;color:{G.rgba(ink, .5)};margin-left:4px;align-self:flex-end;
  margin-bottom:{big_fs * 0.2:.1f}px}}
.vr{{position:absolute;top:{PAD_Y + 4}px;bottom:{PAD_Y + 4}px;width:1.5px;background:rgba(255,255,255,.14)}}
.win{{position:absolute;overflow:hidden}}
#list{{position:absolute;left:0;top:0;width:{PANEL_W}px;height:{R * ROW_H}px}}
#hl{{position:absolute;height:{ROW_H - 4}px;margin-top:2px;border-radius:12px;background:{G.rgba(hi, .16)};
  box-shadow:inset 0 0 0 1.2px {G.rgba(hi, .38)}}}
.it{{position:absolute;height:{ROW_H}px;display:flex;align-items:center;gap:12px;white-space:nowrap;
  direction:{'rtl' if is_rtl else 'ltr'};transform-origin:{'right' if is_rtl else 'left'} center}}
.it .n{{flex:none;width:{num_w}px;font-size:{fs * 0.78:.1f}px;font-weight:700;font-variant-numeric:tabular-nums;
  letter-spacing:.02em;text-align:center}}
.it .t{{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;font-size:{fs:.1f}px;font-weight:600;letter-spacing:-.01em}}
{_state_css(ink, hi)}"""
    js = []
    d = ctx.dur
    if enter:
        js.append("springIn(tl,'#panel',{y:-28,scale:.96,opacity:0},{y:0,scale:1,opacity:1,duration:.7},'gentle',0);")
        js.append("springIn(tl,'.it > span',{y:10,opacity:0},{y:0,opacity:1,duration:.45,stagger:.02},'snappy',.12);")
        if big or counter == "small":
            js.append("springIn(tl,'.big,.hd',{y:12,opacity:0},{y:0,opacity:1,duration:.5},'snappy',.08);")
    if prev != cur:
        t = 0.32 if enter else 0.06
        js += _move(n, prev, cur, s0, s1, col_w, t, X, ink, hi)
    if leave:
        js.append(f"tl.to('#panel',{{opacity:0,y:-22,duration:.34,ease:'power2.in'}},{d - 0.36:.3f});")
    if not js:  # a static hold still needs a timeline that spans the window
        js.append(f"tl.set('#panel',{{opacity:1}},{d:.3f});")
    return ctx.page(body, css, "\n  ".join(js))


STATES = {"cur": (1.0, 1.06), "past": (0.55, 1.0), "next": (0.36, 1.0)}


def _state_css(ink, hi):
    return "\n".join(
        f".it.{k}{{opacity:{o};transform:scale({sc})}}" for k, (o, sc) in STATES.items()) + \
        f"\n.it .n{{color:{G.rgba(ink, .7)}}}\n.it .t{{color:{ink}}}\n.it.cur .n,.it.cur .t{{color:{hi}}}"


def _move(n, prev, cur, s0, s1, col_w, t, X, ink, hi):
    """Tweens that take the tracker from `prev` lit to `cur` lit, starting at t."""
    js = []
    pc, pr = cell(prev, n)
    cc, cr = cell(cur, n)
    dx = (cc - pc) * (col_w + COL_GAP) * (-1 if X(0) else 1)
    js.append(f"springIn(tl,'#hl',{{x:0,y:{pr * ROW_H}}},{{x:{dx:.1f},y:{cr * ROW_H},duration:.55}},'snappy',{t:.3f});")
    if s0 != s1:
        js.append(f"springIn(tl,'#list',{{y:{-s0 * ROW_H}}},{{y:{-s1 * ROW_H},duration:.6}},'gentle',{t:.3f});")
    for i in range(n):
        a, z = state(i, prev), state(i, cur)
        if a == z:
            continue
        (oa, sa), (oz, sz) = STATES[a], STATES[z]
        js.append(f"tl.fromTo('#i{i}',{{opacity:{oa}}},{{opacity:{oz},duration:.3,ease:'power2.out'}},{t:.3f});")
        if sa != sz:
            js.append(f"springIn(tl,'#i{i}',{{scale:{sa}}},{{scale:{sz},duration:.5}},'snappy',{t:.3f});")
        if "cur" in (a, z):  # the lit item changes colour: number and text to/from the accent
            c_from, c_to = (hi, ink) if a == "cur" else (ink, hi)
            n_from, n_to = (hi, G.rgba(ink, .7)) if a == "cur" else (G.rgba(ink, .7), hi)
            js.append(f"tl.fromTo('#i{i} .t',{{color:'{c_from}'}},{{color:'{c_to}',duration:.3,ease:'power2.out'}},{t:.3f});")
            js.append(f"tl.fromTo('#i{i} .n',{{color:'{n_from}'}},{{color:'{n_to}',duration:.3,ease:'power2.out'}},{t:.3f});")
    js.append(f"tl.fromTo('#dA',{{yPercent:0,opacity:1}},{{yPercent:-100,opacity:0,duration:.45,ease:'power3.out'}},"
              f"{t:.3f});")
    js.append(f"springIn(tl,'#dB',{{yPercent:100,opacity:0}},{{yPercent:0,opacity:1,duration:.5}},'snappy',{t + 0.04:.3f});")
    return js
