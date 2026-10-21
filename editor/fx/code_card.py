"""Code card: a code editor window (line numbers, light syntax colour) in the top half over the speaker, or full
frame, with a highlight that moves to the line being talked about. For "this rule says..." moments."""
import html
import re

from . import _glass as G
from . import _split as S

NAME = "code_card"
DOC = ("Code editor card with line numbers and light syntax colour; a highlight lands on `focus` lines at their "
       "times. Top half over the speaker or full frame; 1.5-8 s.")
BEST_FOR = ["product", "any"]
DUR = (1.0, 12)
PARAMS = {
    "code": "",          # the code, lines separated by \\n (keep it to ~10 short lines)
    "focus": [],         # [{"line": 3, "t": 1.2}, ...]: 1-based line, seconds into the window
    "title": "rules.js",
    "place": "top",
}
CAPTIONS = "keep"
TOKENS = [(r"//.*$|#.*$", "#6b7280"), (r"'[^']*'|\"[^\"]*\"|`[^`]*`", "#f3c97a"),
          (r"\b(if|else|throw|new|return|const|let|function|import|from|def|class|for|in)\b", "#c792ea"),
          (r"\b\d+(\.\d+)?\b", "#f78c6c")]


def colour(line: str) -> str:
    """One line as HTML with spans for comments, strings, keywords and numbers (escaped; first match wins)."""
    out, i = [], 0
    pat = re.compile("|".join(f"(?P<t{k}>{p})" for k, (p, _) in enumerate(TOKENS)), re.M)
    for m in pat.finditer(line):
        out.append(html.escape(line[i:m.start()]))
        col = TOKENS[int(m.lastgroup[1:])][1]
        out.append(f'<span style="color:{col}">{html.escape(m.group())}</span>')
        i = m.end()
    out.append(html.escape(line[i:]))
    return "".join(out)


def render(ctx):
    code = str(ctx.param("code") or "")
    lines = code.split("\n")
    if not code.strip():
        raise ValueError("code_card needs code")
    if len(lines) > 14:
        raise ValueError("code_card: at most 14 lines (it must stay readable on a phone)")
    place = ctx.param("place", PARAMS["place"])
    if place not in S.PLACES:
        raise ValueError(f"code_card place must be one of {S.PLACES}")
    focus = ctx.param("focus") or []
    for f in focus:
        if not 1 <= int(f["line"]) <= len(lines):
            raise ValueError(f"code_card: focus line {f['line']} is outside the code")
    return ctx.stack([S.base(ctx, place), ctx.layer(_page(ctx, lines, focus, place), "code")])


def _page(ctx, lines, focus, place):
    b = S.box(ctx, place)
    u = ctx.W / 1080
    lh = 30 * u * 1.6
    rows = "".join(f'<div class="ln"><span class="no">{i + 1}</span>{colour(l)}</div>' for i, l in enumerate(lines))
    css = S.card_css(ctx, b, ctx.style.get("accent", "#ff7a1a")) + f"""
#body{{position:relative;padding:{22 * u:.0f}px 0;font:500 {30 * u:.0f}px/1.6 "PlexMono",monospace;color:#d6d6dc}}
.ln{{white-space:pre;padding:0 {28 * u:.0f}px;height:{lh:.1f}px;position:relative;z-index:1}}
.no{{display:inline-block;width:{50 * u:.0f}px;color:rgba(255,255,255,.28)}}
#hl{{position:absolute;left:0;right:0;top:{22 * u:.0f}px;height:{lh:.1f}px;opacity:0;
  background:{G.rgba(ctx.style.get('accent', '#ff7a1a'), .22)};box-shadow:inset {5 * u:.0f}px 0 0 {ctx.style.get('accent', '#ff7a1a')}}}"""
    js = ["springIn(tl,'#card',{y:30,scale:.96,opacity:0},{y:0,scale:1,opacity:1,duration:.45},'snappy',0);",
          "tl.fromTo('.ln',{opacity:0,x:-10},{opacity:1,x:0,duration:.25,stagger:.04},.15);"]
    for k, f in enumerate(sorted(focus, key=lambda f: float(f["t"]))):
        y = (int(f["line"]) - 1) * lh
        t = float(f["t"])
        js.append(f"tl.to('#hl',{{opacity:1,duration:.15}},{t:.3f});" if k == 0 else "")
        js.append(f"tl.to('#hl',{{y:{y:.1f},duration:{0.01 if k == 0 else 0.3},ease:'power3.out'}},{t:.3f});")
    body = (f'<div id="card">{S.bar(str(ctx.param("title", PARAMS["title"])))}<div id="body"><div id="hl"></div>'
            f'{rows}</div></div>')
    return ctx.page(body, css, "\n  ".join(j for j in js if j))
