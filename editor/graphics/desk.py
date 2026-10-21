"""Desk mode: an explainer panel over a moving brand background, the speaker cut out in front of it.

A finance-desk layout turned vertical. This composition is opaque and covers the whole frame: background and
panel. render.py then lays the speaker, cut out of their own background by cutout.py, over the lower part.
Panels hold the explainer cards: a ticker profile, numbered steps, a theme grid, a price chart drawn from
given points, or a screenshot the user supplied.
"""
import html
import re
import shutil
from pathlib import Path

from .. import fonts
from ..captions import WESTERN_DIGITS, is_arabic
from ..config import GSAP_JS, ROOT_DIR
from .render import RENDER_ARGS, _hf, check_output
from .spring import SPRING_TAG, spring_in

PANEL = (0.125, 0.47)  # panel top and bottom; the top 12.5% stays clear for platform UI
HEAD_TOP, HEAD_HEIGHT = 0.60, 0.30  # where the cut-out head band lands, as fractions of the height
DISPLAY_FONT, MONO_FONT = "Bebas Neue", "IBM Plex Mono"
STEP_COLOURS = ("#ef4444", "#3b82f6", "#22c55e", "#f59e0b")

CSS = """
@font-face{font-family:"BrandLT";src:url("%(latin)s");font-weight:700}
@font-face{font-family:"BrandAR";src:url("%(arabic)s");font-weight:700}
@font-face{font-family:"BrandDS";src:url("%(display)s")}
@font-face{font-family:"BrandMono";src:url("%(mono)s")}
body{margin:0;background:%(bg)s}
#root{position:relative;width:100%%;height:100%%;overflow:hidden;color:%(ink)s;font-family:"BrandLT","BrandAR",sans-serif}
.clip{position:absolute;inset:0}
#bg{position:absolute;inset:0;background:radial-gradient(120%% 70%% at 30%% 20%%,%(bg2)s 0,%(bg)s 75%%)}
.streak{position:absolute;width:160%%;height:9%%;left:-30%%;transform:rotate(-24deg);opacity:.22;
  background:linear-gradient(90deg,transparent,%(mood)s 45%%,transparent)}
#grid{position:absolute;inset:0;opacity:.07;background-image:linear-gradient(%(ink)s 1px,transparent 1px),
  linear-gradient(90deg,%(ink)s 1px,transparent 1px);background-size:6vmin 6vmin}
#mark{position:absolute;width:70vmin;height:70vmin;right:-14vmin;top:4%%;opacity:.07;border-radius:50%%}
#panel{position:absolute;top:%(ptop)s%%;height:%(pheight)s%%;left:5%%;right:12%%;box-sizing:border-box;
  display:flex;flex-direction:column;justify-content:center;gap:2.4vmin;padding:4vmin 4.4vmin;border-radius:2vmin;
  background:rgba(13,16,24,.94);border:1px solid rgba(255,255,255,.08);box-shadow:0 2vmin 6vmin rgba(0,0,0,.5)}
.ds{font-family:"BrandDS","BrandAR",sans-serif;font-weight:400;line-height:.95}
.mono{font-family:"BrandMono","BrandAR",monospace;letter-spacing:.35vmin;text-transform:uppercase;color:#8b93a3}
.eyebrow{font-size:2.4vmin;color:%(down)s;font-weight:700}
.title{font-size:8.4vmin}.title .hi{color:%(down)s}
.tk{font-size:17vmin}
.sub{font-size:2.3vmin;line-height:1.5}
.chips{display:flex;gap:2vmin}.chip{flex:1;background:rgba(255,255,255,.05);border-radius:1.2vmin;padding:2vmin 2.2vmin}
.chip .v{font-size:7vmin}.chip .l{font-size:1.9vmin;margin-top:.8vmin;line-height:1.4}
.body{font-size:3.3vmin;line-height:1.45;color:#c9ced8}.body b{color:%(ink)s}
.tags{display:flex;flex-wrap:wrap;gap:1.4vmin}.tags span{font-size:1.9vmin;color:%(accent)s;border:1px solid %(accent)s;
  padding:.8vmin 1.4vmin;border-radius:.6vmin}
.step{display:flex;align-items:center;gap:2.6vmin;background:rgba(255,255,255,.04);border-inline-start:.7vmin solid;
  border-radius:1vmin;padding:2vmin 2.6vmin}
.step .n{font-size:6.4vmin}.step .t{font-size:4.6vmin;text-transform:uppercase}
.themes{display:grid;grid-template-columns:1fr 1fr;gap:2vmin}
.theme{position:relative;background:rgba(255,255,255,.04);border-radius:1.2vmin;padding:2.4vmin}
.theme .k{font-size:1.9vmin;color:%(down)s}.theme .t{font-size:4.6vmin;margin:.8vmin 0}
.theme .b{font-size:2.6vmin;line-height:1.4;color:#c9ced8}.theme .b b{color:%(ink)s}
.theme .w{position:absolute;top:1.2vmin;inset-inline-end:2vmin;font-size:7vmin;opacity:.08}
.price{display:flex;align-items:baseline;gap:2.4vmin}.price .v{font-size:12vmin}.price .c{font-size:4.4vmin;font-weight:700}
.up{color:%(up)s}.down{color:%(down)s}
svg{width:100%%;flex:1;min-height:0;overflow:visible}
.axis{display:flex;justify-content:space-between;font-size:2vmin}
#shot{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:1.4vmin;background:#fff}
#shot img{max-width:100%%;max-height:100%%;object-fit:contain}
.src{font-size:2vmin}
"""
CSS = re.sub(r"(\.?\d+(?:\.\d+)?)vmin", r"calc(\1vmin*var(--k))", CSS)
CSS = CSS.replace("#root{", "#root{--k:1;", 1)


def _w(v):
    if isinstance(v, str):
        return v.translate(WESTERN_DIGITS)
    if isinstance(v, list):
        return [_w(x) for x in v]
    if isinstance(v, dict):
        return {k: _w(x) for k, x in v.items()}
    return v


def _rich(text: str) -> str:
    """Escape, then **bold** the key phrases."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text))


def _title(text: str, hi: str | None) -> str:
    e = html.escape(text)
    if hi and hi in text:
        e = e.replace(html.escape(hi), f'<span class="hi">{html.escape(hi)}</span>', 1)
    return e


def _texts(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return " ".join(_texts(x) for x in v)
    if isinstance(v, dict):
        return " ".join(_texts(x) for k, x in v.items() if k not in ("type", "src", "color"))
    return ""


def chart_path(points: list, w: float = 100, h: float = 40) -> str:
    lo, hi = min(points), max(points)
    span = (hi - lo) or 1
    step = w / (len(points) - 1)
    return " ".join(f"{i * step:.2f},{h - (p - lo) / span * h:.2f}" for i, p in enumerate(points))


def _theme_body(item: dict) -> str:
    return f'<div class="b">{_rich(item["body"])}</div>' if item.get("body") else ""


def _card(card: dict, style: dict, image: str | None) -> str:
    e = html.escape
    t = card["type"]
    eyebrow = f'<div class="mono eyebrow item">{e(card["eyebrow"])}</div>' if card.get("eyebrow") else ""
    if t == "profile":
        colour = {"up": style.get("up", "#22c55e"), "down": style.get("down", "#ef4444")}.get(
            card.get("color"), style["accent"])
        sub = "<br>".join(e(x) for x in (card.get("name"), card.get("desc")) if x)
        chips = "".join(f'<div class="chip"><div class="ds v" style="color:{colour}">{e(s["value"])}</div>'
                        f'<div class="mono l">{e(s["label"])}</div></div>' for s in card.get("stats", []))
        body = f'<div class="body item">{_rich(card["body"])}</div>' if card.get("body") else ""
        tags = ('<div class="tags mono item">' + "".join(f"<span>{e(x)}</span>" for x in card["tags"]) + "</div>"
                if card.get("tags") else "")
        sub = f'<div class="mono sub item">{sub}</div>' if sub else ""
        chips = f'<div class="chips item">{chips}</div>' if chips else ""
        return f'{eyebrow}<div class="ds tk item" style="color:{colour}">{e(card["ticker"])}</div>{sub}{chips}{body}{tags}'
    if t == "steps":
        steps = "".join(f'<div class="step item" style="border-color:{c}"><span class="ds n" style="color:{c}">'
                        f'{i + 1:02d}</span><span class="t">{e(x)}</span></div>'
                        for i, (x, c) in enumerate(zip(card["items"], STEP_COLOURS)))
        return f'{eyebrow}<div class="ds title item">{_title(card["title"], card.get("hi"))}</div>{steps}'
    if t == "themes":
        cells = "".join(f'<div class="theme"><span class="ds w">{i + 1:02d}</span><div class="mono k">— {i + 1:02d}</div>'
                        f'<div class="ds t">{e(x["title"])}</div>{_theme_body(x)}</div>'
                        for i, x in enumerate(card["items"]))
        return (f'{eyebrow}<div class="ds title item">{_title(card["title"], card.get("hi"))}</div>'
                f'<div class="themes item">{cells}</div>')
    if t == "chart":
        d = card.get("dir") or ("up" if card["points"][-1] >= card["points"][0] else "down")
        colour = style.get("up", "#22c55e") if d == "up" else style.get("down", "#ef4444")
        line = chart_path(card["points"])
        area = f"0,40 {line} 100,40"
        change = f'<span class="c {d}">{"▲" if d == "up" else "▼"} {e(card["change"])}</span>' if card.get("change") else ""
        axis = ('<div class="mono axis item">' + "".join(f"<span>{e(x)}</span>" for x in card["labels"]) + "</div>"
                if card.get("labels") else "")
        head = f'{e(card["name"])}{" · " + e(card["ticker"]) if card.get("ticker") else ""}'
        return (f'{eyebrow}<div class="mono sub item">{head}</div>'
                f'<div class="price item"><span class="ds v">{e(card["value"])}</span>{change}</div>'
                f'<svg class="item" viewBox="0 -2 100 44" preserveAspectRatio="none">'
                f'<defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{colour}" '
                f'stop-opacity=".35"/><stop offset="1" stop-color="{colour}" stop-opacity="0"/></linearGradient>'
                f'<clipPath id="reveal"><rect id="rv" x="-2" y="-10" width="0" height="60"/></clipPath></defs>'
                f'<g clip-path="url(#reveal)">'
                f'<polygon id="area" points="{area}" fill="url(#fill)"/>'
                f'<polyline id="line" points="{line}" fill="none" stroke="{colour}" stroke-width="6" '
                f'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/></g></svg>{axis}')
    if t == "image":
        src = f'<div class="mono src item">{e(card["source"])}</div>' if card.get("source") else ""
        title = f'<div class="ds title item">{_title(card["title"], card.get("hi"))}</div>' if card.get("title") else ""
        return f'{eyebrow}{title}<div id="shot" class="item"><img id="img" src="{e(image)}" alt=""></div>{src}'
    raise ValueError(f"unknown desk card {t!r}")


def desk_html(spec: dict, style: dict, size: tuple, font_files: dict, image: str | None = None,
              logo: str | None = None) -> str:
    card = _w(spec["card"])
    rtl = is_arabic(_texts(card))
    d = spec["dur"]
    mood = {"bull": style.get("up", "#22c55e"), "bear": style.get("down", "#ef4444")}.get(spec.get("mood"),
                                                                                         style["accent"])
    css = CSS % {**font_files, "ink": style["ink"], "accent": style["accent"], "bg": style.get("bg", "#101114"),
                 "bg2": style.get("bg2", style.get("bg", "#101114")), "up": style.get("up", "#22c55e"),
                 "down": style.get("down", "#ef4444"), "mood": mood,
                 "ptop": PANEL[0] * 100, "pheight": round((PANEL[1] - PANEL[0]) * 100, 2)}
    mark = f'<img id="mark" src="{html.escape(logo)}" alt="">' if logo else ""
    streaks = "".join(f'<div class="streak" style="top:{y}%"></div>' for y in (8, 30, 52))
    shift = -30 if rtl else 30
    draw = ('tl.to("#rv",{attr:{width:104},duration:1.4,ease:"power2.inOut"},.5);'
            if card["type"] == "chart" else "")
    enter = (spring_in("#panel", "y:40,opacity:0", "y:0,opacity:1,duration:.45", "gentle", 0)
             + spring_in("#panel .item", f"x:{shift},opacity:0", "x:0,opacity:1,duration:.4,stagger:.14", "snappy", .2))
    push = (f'tl.fromTo("#img",{{scale:1}},{{scale:1.06,duration:{d},ease:"sine.inOut"}},0);'
            if card["type"] == "image" else "")
    return f"""<!doctype html>
<html lang="{'ar' if rtl else 'en'}"><head><meta charset="UTF-8"><script src="gsap.min.js"></script>{SPRING_TAG}
<style>{css}</style></head><body>
<div id="root" data-composition-id="g" data-start="0" data-width="{size[0]}" data-height="{size[1]}" data-duration="{d}"{' dir="rtl"' if rtl else ''}>
<section class="clip" data-start="0" data-duration="{d}"><div id="bg"></div><div id="grid"></div>{streaks}{mark}
<div id="panel">{_card(card, style, image)}</div></section></div>
<script>
document.fonts.ready.then(() => {{
  for (const f of ["BrandLT", "BrandDS"]) if (!document.fonts.check('700 40px "' + f + '"')) throw new Error("font " + f + " did not load");
  const fit = () => {{ const p = document.getElementById("panel"); let k = 1;
    while (p.scrollHeight > p.clientHeight + 1 && k > .55) {{ k -= .03; document.getElementById("root").style.setProperty("--k", k); }} }};
  fit();
  const tl = gsap.timeline({{paused: true}});
  tl.fromTo(".streak", {{xPercent: -20}}, {{xPercent: 20, duration: {d}, ease: "none", stagger: .4}}, 0);
  {enter}
  tl.fromTo("#panel", {{scale: 1}}, {{scale: 1.025, duration: {d}, ease: "sine.inOut"}}, 0);
  {draw}{push}
  window.__timelines["g"] = tl;
}});
</script></body></html>
"""


def render_desk(spec: dict, style: dict, size: tuple, out_path, project=None) -> Path:
    out_path = Path(out_path).resolve()
    comp = out_path.with_suffix(".hf")
    comp.mkdir(parents=True, exist_ok=True)
    files = {"latin": fonts.ensure_font(style["font"]), "arabic": fonts.ensure_font(style["arabic_font"]),
             "display": fonts.ensure_font(DISPLAY_FONT), "mono": fonts.ensure_font(MONO_FONT)}
    for f in (*files.values(), GSAP_JS):
        shutil.copy2(f, comp / f.name)
    image = logo = None
    if spec["card"]["type"] == "image":
        src = Path(spec["card"]["src"])
        src = Path(project) / src if project and not src.is_absolute() else src
        image = "shot" + src.suffix.lower()
        shutil.copy2(src, comp / image)
    if style.get("logo"):
        src = ROOT_DIR / style["logo"]
        logo = "logo" + src.suffix
        shutil.copy2(src, comp / logo)
    (comp / "index.html").write_text(
        desk_html(spec, style, size, {k: f.name for k, f in files.items()}, image, logo), encoding="utf-8")
    _hf(["lint", "."], comp)
    _hf(["render", ".", *RENDER_ARGS, "-o", str(out_path)], comp)
    check_output(out_path, spec["dur"])
    return out_path
