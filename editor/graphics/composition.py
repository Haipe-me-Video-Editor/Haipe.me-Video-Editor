"""HyperFrames compositions for the built-in graphic types. Transparent root, local GSAP and fonts only."""
import html
import re

from .. import safezone
from ..captions import WESTERN_DIGITS, is_arabic
from .spring import SPRING_TAG, spring_in

CSS = """
@font-face{font-family:"BrandLT";src:url("%(latin)s");font-weight:700}
@font-face{font-family:"BrandAR";src:url("%(arabic)s");font-weight:700}
body{margin:0;background:transparent}
#root{position:relative;width:100%%;height:100%%;overflow:hidden;font-family:%(family)s,sans-serif;color:%(ink)s;--k:%(scale)s}
.clip{position:absolute;inset:0}
#slot{position:absolute;top:%(top)s%%;height:%(height)s%%;left:6%%;right:12%%;display:flex;align-items:center}
.card{position:relative;width:100%%;box-sizing:border-box;padding:4vmin 5vmin;border-radius:2.2vmin;
  background:rgba(7,8,10,.82);border:1px solid rgba(255,255,255,.14)}
.hook{font-weight:700;font-size:9vmin;line-height:1.1}
.lower{width:auto;padding:2.4vmin 3.6vmin}
.lower .name{font-weight:700;font-size:5.4vmin}.lower .sub{font-size:3.6vmin;opacity:.8;margin-top:.8vmin}
.list .item{display:flex;gap:2.6vmin;align-items:baseline;font-size:5.6vmin;font-weight:700;margin:2vmin 0}
.list .n{color:%(accent)s}
.stat{text-align:center}.stat .num{font-size:20vmin;font-weight:700;color:%(accent)s;line-height:1}
.stat .label{font-size:5vmin;margin-top:2vmin}
.quote{font-size:6.4vmin;font-weight:700;line-height:1.25}.quote .by{font-size:3.8vmin;font-weight:400;opacity:.8;margin-top:2.4vmin}
.stat.up .num{color:%(up)s}.stat.down .num{color:%(down)s}
.ticker{width:auto;padding:2.4vmin 3.6vmin}
.ticker .name{font-weight:700;font-size:5.4vmin}.ticker .row{font-size:3.6vmin;margin-top:.8vmin}
.ticker .sym{color:%(accent)s;font-weight:700}.ticker .fact{opacity:.8}
.headline{background:#fff;color:#0d0f14;border:0;border-inline-start:1.6vmin solid %(accent)s;padding:3.6vmin 4.4vmin}
.headline .tag{display:inline-block;background:%(down)s;color:#fff;font-size:3vmin;padding:.6vmin 1.6vmin;border-radius:.8vmin;margin-bottom:1.6vmin}
.headline .text{font-weight:700;font-size:6vmin;line-height:1.15}.headline .src{font-size:3vmin;color:#5a6270;margin-top:1.6vmin}
.kinetic{background:none;border:0;padding:0;text-align:center;font-weight:700;font-size:9vmin;line-height:1.1;
  text-shadow:0 .5vmin 2.4vmin rgba(0,0,0,.75)}
.kinetic .w{display:inline-block;margin:0 .9vmin;white-space:nowrap}.kinetic .hi{color:%(accent)s}
.kinetic.latin{text-transform:uppercase}
.kinetic .u{display:inline-block;will-change:transform}
.kinetic.behind{font-size:17vmin;line-height:.95;letter-spacing:-.4vmin}
#behind,#center{position:absolute;top:16%%;height:30%%;left:5%%;right:12%%;display:flex;align-items:center;justify-content:center}
#center{top:30%%;height:36%%;background:radial-gradient(ellipse closest-side,rgba(0,0,0,.5),transparent)}
#center .kinetic{font-size:13vmin}
.kinetic .shine{position:absolute;inset:0;color:#fff;pointer-events:none;
  -webkit-mask-image:linear-gradient(100deg,transparent 42%%,#000 50%%,transparent 58%%);-webkit-mask-size:300%% 100%%;
  -webkit-mask-position:var(--sx,150%%) 0;text-shadow:0 0 2vmin #fff}
#bloom{position:absolute;left:50%%;top:50%%;width:40vmin;height:40vmin;margin:-20vmin 0 0 -20vmin;border-radius:50%%;
  background:radial-gradient(circle,#fff 0,rgba(255,255,255,.85) 25%%,rgba(255,255,255,0) 70%%);opacity:0}
.fixed{position:absolute;inset:0}
#credit{position:absolute;left:7%%;bottom:%(credit_bottom)s%%;transform:rotate(-90deg);transform-origin:left bottom;white-space:nowrap;
  font-weight:700;font-size:2.8vmin;letter-spacing:.3vmin;text-transform:uppercase;text-shadow:0 .3vmin 1.2vmin rgba(0,0,0,.8)}
#chapter{position:absolute;top:14%%;left:0;right:0;display:flex;justify-content:center}
#chapter .pill{display:flex;gap:1.6vmin;align-items:center;font-weight:700;font-size:3.6vmin;padding:1.4vmin 3vmin;
  border-radius:99vmin;background:rgba(7,8,10,.82);border:1px solid rgba(255,255,255,.14)}
#chapter .dot{width:1.8vmin;height:1.8vmin;border-radius:50%%;background:%(accent)s}
#outro{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4vmin;
  background:radial-gradient(circle at 50%% 42%%,%(bg2)s 0,%(bg)s 70%%)}
#outro img{width:48vmin;height:48vmin;border-radius:50%%;box-shadow:0 2vmin 8vmin rgba(0,0,0,.6)}
#outro .handle{font-weight:700;font-size:7vmin}#outro .disc{font-size:3.4vmin;opacity:.75;max-width:80%%;text-align:center}
"""
# A fixed card's wrapper fills the frame: GSAP transforms it, which makes it the containing block.
# Every size scales with --k so a card can shrink into the free space it was given.
CSS = re.sub(r"(\.?\d+(?:\.\d+)?)vmin", r"calc(\1vmin*var(--k))", CSS)
DEFAULT_SLOT = {"top": 16, "height": 40, "scale": 1}


def _texts(spec: dict) -> str:
    vals = []
    for v in spec.values():
        vals += v if isinstance(v, list) else [v] if isinstance(v, str) else []
    return " ".join(vals)


def _body(spec: dict) -> tuple[str, bool]:
    e = html.escape
    t = spec["type"]
    if t == "hook":
        return f'<div id="card" class="card hook">{e(spec["text"])}</div>', False
    if t == "lower_third":
        sub = f'<div class="sub">{e(spec["sub"])}</div>' if spec.get("sub") else ""
        return f'<div id="card" class="card lower"><div class="name">{e(spec["name"])}</div>{sub}</div>', False
    if t == "list":
        items = "".join(f'<div class="item"><span class="n">{i + 1}</span><span>{e(x)}</span></div>'
                        for i, x in enumerate(spec["items"]))
        return f'<div id="card" class="card list">{items}</div>', True
    if t == "stat":
        return f'<div id="card" class="card stat"><div class="num">{e(spec["value"])}</div><div class="label">{e(spec["label"])}</div></div>', False
    if t == "quote":
        by = f'<div class="by">{e(spec["by"])}</div>' if spec.get("by") else ""
        return f'<div id="card" class="card quote">“{e(spec["text"])}”{by}</div>', False
    if t == "ticker":
        fact = f' · <span class="fact">{e(spec["fact"])}</span>' if spec.get("fact") else ""
        return (f'<div id="card" class="card ticker"><div class="name">{e(spec["name"])}</div>'
                f'<div class="row"><span class="sym">{e(spec["ticker"])}</span>{fact}</div></div>'), False
    if t == "headline":
        tag = f'<div class="tag">{e(spec["tag"])}</div>' if spec.get("tag") else ""
        src = f'<div class="src">{e(spec["source"])}</div>' if spec.get("source") else ""
        return f'<div id="card" class="card headline">{tag}<div class="text">{e(spec["text"])}</div>{src}</div>', False
    if t == "kinetic":
        return _kinetic(spec), True
    raise ValueError(f"unknown graphic type {t!r}")


def _kinetic(spec: dict) -> str:
    """Big text. fx: words (word by word), pop (letters spring in), shine (a light sweep), neon (letters
    flicker on, then glow), bloom (a white burst that pops the text bigger). Arabic animates whole words,
    because splitting Arabic into letters breaks the joined script."""
    e = html.escape
    fx = spec.get("fx", "words")
    arabic = is_arabic(spec["text"])
    hi = {_word_key(w) for x in spec.get("hi", []) for w in x.split()}
    by_letter = fx in ("pop", "neon") and not arabic
    words = []
    for w in spec["text"].split():
        cls = "w" + (" hi" if _word_key(w) in hi else "")
        inner = "".join(f'<span class="u item">{e(c)}</span>' for c in w) if by_letter else e(w)
        words.append(f'<span class="{cls}{"" if by_letter else " u item"}">{inner}</span>')
    text = "".join(words)
    shine = f'<div class="shine" aria-hidden="true">{text.replace(" item", "")}</div>' if fx == "shine" else ""
    bloom = '<div id="bloom"></div>' if fx == "bloom" else ""
    cls = "card kinetic" + ("" if arabic else " latin") + (" behind" if spec.get("place") in ("behind", "center") else "")
    return f'<div id="card" class="{cls}" style="position:relative">{text}{shine}{bloom}</div>'


def _kinetic_timeline(spec: dict, accent: str, d: float) -> str:
    fx = spec.get("fx", "words")
    if fx == "pop":
        return (spring_in("#card .item", "scale:0,yPercent:40,opacity:0", "scale:1,yPercent:0,opacity:1,duration:.32,"
                          "stagger:.035", "bouncy", 0) +
                'tl.fromTo("#card .hi",{scale:1},{scale:1.12,duration:.12,yoyo:true,repeat:1,ease:"power2.out"},">");')
    if fx == "shine":
        return (spring_in("#card .item", "opacity:0,y:20", "opacity:1,y:0,duration:.3,stagger:.06", "snappy", 0) +
                f'tl.fromTo("#card .shine",{{"--sx":"150%"}},{{"--sx":"-50%",duration:.9,ease:"power2.inOut",'
                f'repeat:{max(0, int((d - 1.6) // 1.4))},repeatDelay:.5}},.5);')
    if fx == "neon":
        glow = f"0 0 .6vmin #fff,0 0 2vmin {accent},0 0 5vmin {accent}"
        return ('const rnd=(s=>()=>(s=(s*16807)%2147483647)/2147483647)(7);'
                'tl.set("#card .item",{opacity:.18,textShadow:"none"},0);'
                'document.querySelectorAll("#card .item").forEach((el,i)=>{let t=.05+rnd()*.5;'
                'for(let k=0;k<4;k++){const on=k%2===0;'
                f'tl.set(el,{{opacity:on?1:.18,textShadow:on?"{glow}":"none"}},t);t+=.033+rnd()*.12;}}'
                f'tl.set(el,{{opacity:1,textShadow:"{glow}"}},Math.max(t,1.1));}});')
    if fx == "bloom":
        return ('tl.fromTo("#card .item",{opacity:0},{opacity:1,duration:.15,stagger:.04},0);'
                'tl.fromTo("#bloom",{scale:0,opacity:0},{scale:3,opacity:1,duration:.14,ease:"power2.in"},.45);'
                'tl.to("#bloom",{opacity:0,duration:.25,ease:"power2.out"},.59);'
                + spring_in("#card", 'scale:1,textShadow:"none"',
                            f'scale:1.4,textShadow:"0 0 3vmin #fff,0 0 6vmin {accent}",duration:.45', "bouncy", .55))
    return spring_in("#card .item", "scale:.6,opacity:0", "scale:1,opacity:1,duration:.22,stagger:.09", "bouncy", 0)


def _word_key(w: str) -> str:
    return re.sub(r"[^\w%$٪]", "", w).lower()


def _fixed(spec: dict, logo: str | None) -> str:
    """Graphics that sit at a fixed spot instead of the free-space slot."""
    e = html.escape
    t = spec["type"]
    if t == "credit":
        return f'<div id="card" class="fixed"><div id="credit">// {e(spec["text"])}</div></div>'
    if t == "chapter":
        return f'<div id="card" class="fixed"><div id="chapter"><div class="pill"><span class="dot"></span>{e(spec["text"])}</div></div></div>'
    if t == "outro":
        handle = f'<div class="handle" dir="ltr">{e(spec["handle"])}</div>' if spec.get("handle") else ""
        disc = f'<div class="disc">{e(spec["disclaimer"])}</div>' if spec.get("disclaimer") else ""
        return f'<div id="card" class="fixed"><div id="outro"><img id="logo" src="{e(logo)}" alt="">{handle}{disc}</div></div>'
    raise ValueError(f"unknown graphic type {t!r}")


FIXED_TYPES = ("credit", "chapter", "outro")
# Spring preset for each card's entrance (editor/graphics/spring.py): cards and panels settle "gentle",
# small labels and pills land "snappy". Exits stay on power2.in.
ENTRANCE = {"lower_third": "snappy", "ticker": "snappy", "credit": "snappy", "chapter": "snappy"}


def _wrap(spec: dict, body: str) -> str:
    if spec["type"] in FIXED_TYPES:
        return body
    if spec["type"] == "kinetic" and spec.get("place") in ("behind", "center"):
        return f'<div id="{spec["place"]}">{body}</div>'
    return f'<div id="slot">{body}</div>'


def _western(v):
    if isinstance(v, str):
        return v.translate(WESTERN_DIGITS)
    return [_western(x) for x in v] if isinstance(v, list) else v


def composition_html(spec: dict, style: dict, size: tuple, font_files: dict, logo: str | None = None) -> str:
    spec = {k: _western(v) for k, v in spec.items()}
    rtl = is_arabic(_texts(spec))
    t = spec["type"]
    if t in FIXED_TYPES:
        body, has_items = _fixed(spec, logo), False
    else:
        body, has_items = _body(spec)
        if t == "stat" and spec.get("dir") in ("up", "down"):
            arrow = "▲ " if spec["dir"] == "up" else "▼ "
            body = body.replace('class="card stat"><div class="num">', f'class="card stat {spec["dir"]}"><div class="num">{arrow}')
    d = spec["dur"]
    shift = 30 if not rtl else -30
    slot = spec.get("slot")
    slot = {"top": slot["top"] * 100, "height": slot["height"] * 100, "scale": slot["scale"]} if slot else DEFAULT_SLOT
    css = CSS % {"latin": font_files["latin"], "arabic": font_files["arabic"],
                 "family": '"BrandAR"' if rtl else '"BrandLT"', "ink": style["ink"], "accent": style["accent"],
                 "credit_bottom": round(safezone.BOTTOM * 100 + 1, 1),
                 "up": style.get("up", "#22c55e"), "down": style.get("down", "#ef4444"),
                 "bg": style.get("bg", "#101114"), "bg2": style.get("bg2", style.get("bg", "#101114")),
                 "top": round(slot["top"], 2), "height": round(slot["height"], 2), "scale": slot["scale"]}
    stagger = spring_in("#card .item", f"x:{shift},opacity:0", "x:0,opacity:1,duration:.35,stagger:.18", "snappy",
                        .25) if has_items else ""
    if t == "kinetic":
        stagger = _kinetic_timeline(spec, style["accent"], d)
    elif t == "stat":  # the number lands a beat after its card, on the card's own landing frame (.45 s)
        stagger = spring_in("#card .num", "scale:.8", "scale:1,duration:.35", "snappy", .1)
    enter = "y:40,opacity:0"
    if t == "credit":
        enter = "x:-30,opacity:0"
    elif t == "kinetic":
        enter = "opacity:1"
    elif t == "outro":
        enter = "opacity:0"
        stagger = (spring_in("#logo", "scale:.4,rotationY:-180,opacity:0", "scale:1,rotationY:0,opacity:1,duration:.8",
                             "gentle", .1)
                   + spring_in("#outro .handle, #outro .disc", "y:20,opacity:0", "y:0,opacity:1,duration:.4,stagger:.15",
                               "snappy", .6))
    enter = spring_in("#card", enter, "x:0,y:0,opacity:1,duration:.45", ENTRANCE.get(t, "gentle"), 0)
    family = "BrandAR" if rtl else "BrandLT"
    # the end card holds to the last frame; fading it out would flash the speaker back in as the video ends
    exit = "" if t == "outro" else (f'tl.to("#card", {{y: -20, opacity: 0, duration: .3, ease: "power2.in"}}, '
                                    f'{max(d - 0.3, 0.5)});')
    return f"""<!doctype html>
<html lang="{'ar' if rtl else 'en'}"><head><meta charset="UTF-8"><script src="gsap.min.js"></script>{SPRING_TAG}
<style>{css}</style></head><body>
<div id="root" data-composition-id="g" data-start="0" data-width="{size[0]}" data-height="{size[1]}" data-duration="{d}"{' dir="rtl"' if rtl else ''}>
<section class="clip" data-start="0" data-duration="{d}">{_wrap(spec, body)}</section></div>
<script>
document.fonts.ready.then(() => {{
  if (!document.fonts.check('700 40px "{family}"')) throw new Error("font {family} did not load");
  const tl = gsap.timeline({{paused: true}});
  {enter}
  {stagger}
  {exit}
  window.__timelines["g"] = tl;
}});
</script></body></html>
"""
