"""Terminal card: a terminal window in the top half (the speaker below) or full frame, where the commands type
themselves out and the result lines pop in with a green tick, timed to the voice. For "it runs this, then this"."""
from . import _glass as G
from . import _split as S

NAME = "terminal"
DOC = ("Terminal window typing commands ($ lines type out, other lines pop in, a leading ✓ goes green), top half "
       "over the speaker or full frame. For showing what the tool runs; 1.5-8 s.")
BEST_FOR = ["product", "any"]
DUR = (1.0, 12)
PARAMS = {
    "lines": [],         # ["$ media record \\", "  github.com/you/repo", "✓ saved cursor.mp4"]
    "times": None,       # seconds into the window each line starts (default: spread over the window)
    "title": "Terminal",
    "place": "top",      # top (the speaker stays below) | full
    "cps": 38,           # typing speed for $ lines, characters a second
}
CAPTIONS = "keep"


def times_for(lines: list, dur: float, times=None, cps: float = 38) -> list:
    """When each line starts: given, or one after another (typed lines take their typing time) to fill ~80%."""
    if times:
        if len(times) != len(lines):
            raise ValueError("terminal: times needs one entry per line")
        return [float(t) for t in times]
    cost = [len(l) / cps + 0.12 if l.lstrip().startswith("$") else 0.18 for l in lines]
    scale = min(1.0, dur * 0.8 / max(sum(cost), 1e-6))
    out, t = [], 0.15
    for c in cost:
        out.append(round(t, 3))
        t += c * scale
    return out


def render(ctx):
    lines = [str(l) for l in (ctx.param("lines") or [])]
    if not lines:
        raise ValueError("terminal needs lines")
    place = ctx.param("place", PARAMS["place"])
    if place not in S.PLACES:
        raise ValueError(f"terminal place must be one of {S.PLACES}")
    cps = float(ctx.param("cps", PARAMS["cps"]))
    ts = times_for(lines, ctx.dur, ctx.param("times"), cps)
    return ctx.stack([S.base(ctx, place), ctx.layer(_page(ctx, lines, ts, place, cps), "terminal")])


def _page(ctx, lines, ts, place, cps):
    b = S.box(ctx, place)
    u = ctx.W / 1080
    accent = ctx.style.get("up", "#2ecc71")
    rows, js = [], []
    for i, (l, t) in enumerate(zip(lines, ts)):
        typed = l.lstrip().startswith("$")
        tick = l.lstrip().startswith(("✓", "✔"))
        text = G.esc(l)
        if tick:
            text = text.replace("✓", '<b class="acc">✓</b>', 1).replace("✔", '<b class="acc">✔</b>', 1)
        rows.append(f'<div class="ln" id="l{i}"><span class="tx">{text}</span></div>')
        if typed:  # reveal character by character: a clip-path wipe paced to the line length
            d = max(0.2, len(l) / cps)
            js.append(f"tl.set('#l{i}',{{opacity:1}},{t:.3f});"
                      f"tl.fromTo('#l{i} .tx',{{clipPath:'inset(0 100% 0 0)'}},{{clipPath:'inset(0 0% 0 0)',"
                      f"duration:{d:.2f},ease:'steps({max(1, len(l))})'}},{t:.3f});")
        else:
            js.append(f"tl.fromTo('#l{i}',{{opacity:0,y:{8 * u:.0f}}},{{opacity:1,y:0,duration:.18}},{t:.3f});")
    css = S.card_css(ctx, b, accent) + f"""
#body{{padding:{26 * u:.0f}px {30 * u:.0f}px;font:500 {30 * u:.0f}px/1.55 "PlexMono",monospace;color:#e8e8ea}}
.ln{{opacity:0;white-space:pre}}
.tx{{display:inline-block}}"""
    js.insert(0, "springIn(tl,'#card',{y:30,scale:.96,opacity:0},{y:0,scale:1,opacity:1,duration:.45},'snappy',0);")
    body = f'<div id="card">{S.bar(str(ctx.param("title", PARAMS["title"])))}<div id="body">{"".join(rows)}</div></div>'
    return ctx.page(body, css, "\n  ".join(js))
