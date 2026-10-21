"""Rank list: numbered rows (#1, #2, #3...) in the top half over the speaker, or full frame; each row lights up on
the word that names it while the others dim and blur, the way a fast explainer counts through its points."""
from . import _glass as G
from . import _split as S

NAME = "rank_list"
DOC = ("Numbered rows (#1 #2 #3...) that light up one at a time on their spoken times, others dimmed and blurred. "
       "Top half over the speaker or full frame; 1.5-8 s.")
BEST_FOR = ["product", "any", "corporate"]
DUR = (1.0, 12)
PARAMS = {
    "items": [],      # 2-5 short lines
    "times": None,    # seconds into the window each row lights (default: spread evenly)
    "place": "top",
}
CAPTIONS = "keep"


def light_times(n: int, dur: float, times=None) -> list:
    if times:
        if len(times) != n:
            raise ValueError("rank_list: times needs one entry per item")
        return [float(t) for t in times]
    return [round(0.25 + i * (dur * 0.85 - 0.25) / max(1, n), 3) for i in range(n)]


def render(ctx):
    items = [str(t) for t in (ctx.param("items") or []) if str(t).strip()]
    if not 2 <= len(items) <= 5:
        raise ValueError("rank_list needs 2-5 items")
    place = ctx.param("place", PARAMS["place"])
    if place not in S.PLACES:
        raise ValueError(f"rank_list place must be one of {S.PLACES}")
    ts = light_times(len(items), ctx.dur, ctx.param("times"))
    return ctx.stack([S.base(ctx, place), ctx.layer(_page(ctx, items, ts, place), "rank")])


def _page(ctx, items, ts, place):
    b = S.box(ctx, place)
    u = ctx.W / 1080
    rtl = G.rtl(items)
    rows = "".join(f'<div class="row" id="r{i}"><b>#{i + 1}</b><span>{G.esc(t)}</span></div>'
                   for i, t in enumerate(items))
    gap = 22 * u
    rh = (b["h"] - gap * (len(items) + 1)) / len(items)
    css = f"""
#list{{position:absolute;left:{b['x']:.0f}px;top:{b['y']:.0f}px;width:{b['w']:.0f}px;height:{b['h']:.0f}px;
  display:flex;flex-direction:column;justify-content:center;gap:{gap:.0f}px;direction:{'rtl' if rtl else 'ltr'};
  font-family:"{'BrandAR' if rtl else 'BrandLT'}",sans-serif}}
.row{{height:{min(rh, 130 * u):.0f}px;border-radius:{18 * u:.0f}px;background:#f4f4f2;color:#16181d;display:flex;
  align-items:center;gap:{24 * u:.0f}px;padding:0 {34 * u:.0f}px;font-size:{46 * u:.0f}px;font-weight:700;
  opacity:.28;filter:blur({3 * u:.1f}px);box-shadow:0 {10 * u:.0f}px {30 * u:.0f}px rgba(0,0,0,.25)}}
.row b{{color:{ctx.style.get('accent', '#ff7a1a')};font-weight:800}}"""
    js = ["tl.fromTo('.row',{y:24,opacity:0},{y:0,opacity:.28,duration:.35,stagger:.06,ease:'power2.out'},0);"]
    for i, t in enumerate(ts):
        js.append(f"tl.to('.row',{{opacity:.28,scale:.97,filter:'blur({3 * u:.1f}px)',duration:.2}},{t:.3f});")
        js.append(f"springIn(tl,'#r{i}',{{scale:.97}},{{scale:1.03,duration:.35}},'snappy',{t:.3f});")
        js.append(f"tl.to('#r{i}',{{opacity:1,filter:'blur(0px)',duration:.2}},{t:.3f});")
    return ctx.page(f'<div id="list">{rows}</div>', css, "\n  ".join(js))
