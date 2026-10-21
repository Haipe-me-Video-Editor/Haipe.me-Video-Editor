"""Orbit: a ring of cards (screenshots, clip stills, short text tiles) circles the speaker in 3D.

The ring sits around the chest, tilted towards the camera: cards on the far half pass behind the speaker (the
person matte hides them), cards on the near half pass in front, larger and sharp; far cards are smaller, softer and
dimmer. Every card position is computed here in Python (true perspective, the ring's spring-out entrance and
fly-out exit), so the geometry is testable and the page only applies it frame by frame.
"""
import json
import math

from ..graphics.spring import PRESETS, spring
from . import _spatial as sp

NAME = "orbit"
DOC = ("A ring of cards (clip stills, screenshots or 1-4 word text tiles) orbits the speaker in 3D: far cards pass "
       "behind them, near cards in front. For 'all of this, in one place' / range / many-options moments.")
BEST_FOR = ["product", "finance", "any"]
DUR = (2.0, 7)
CAPTIONS = "hide"  # the effect fills the caption band; captions return after the window
PARAMS = {
    "items": [],           # card contents: image paths (png/jpg/webp) or short text; default stills from the clip
    "n": 7,                # number of cards when items is empty (or fewer than n: text/images repeat)
    "stills_from": None,   # video to grab the default stills from (e.g. the full source); default the window
    "speed": 0.15,         # turns per second (positive: the near side moves left to right)
    "tilt": 34,            # degrees the ring leans towards the camera
    "radius": None,        # ring radius as a fraction of the width; default as wide as the safe zone allows
    "card": None,          # card height as a fraction of the width; default the largest that clears the chin
    "y": None,             # ring centre as a fraction of the height; default just under the chin
    "dim": 0.16,           # the room darkens a little while the ring is up
    "theme": "dark",
    "aspect": None,        # card height / width; default portrait 16:9, landscape 3:4 in tight close-ups
    "track": True,         # a hairline along the ring's path (far half behind the speaker, near half in front)
    "frame": None,         # a card frame: {"color": "#4c6ef5", "width": 0.012, "inner": "#FFFFFF"}
                           # (width a fraction of the card width; inner a thin line inside the frame)
    "card_bg": None,       # colour behind image cards (shows through transparent images, e.g. a product cut-out)
    "track_color": None,   # the ring line's colour (default the style's ink)
}

FOCAL = 5.5       # camera distance in ring radii: sets how much bigger near cards are than far ones
ASPECT = 16 / 9   # card height / width


def scale_at(z: float, R: float) -> float:
    """Perspective scale of a point at depth z (towards the camera positive) on a ring of radius R."""
    f = FOCAL * R
    return f / (f - z)


def ring_geometry(sc: sp.Scene, tilt_deg: float, radius=None, card=None, y=None, aspect: float = ASPECT) -> dict:
    """Centre, radius and card size for a scene. The ring rides as high as it can (so its far half passes behind
    the head and shoulders, where the room shows) while no near-half card ever touches the face, and the whole
    ring stays inside the safe zone; cards shrink until that fits. Pure; tests drive it with fake scenes."""
    W, H = sc.W, sc.H
    sx0, sx1, sy0, sy1 = sc.px("x0"), sc.px("x1"), sc.px("y0"), sc.px("y1")
    tilt = math.radians(tilt_deg)
    sf, sb = scale_at(1, 1), scale_at(-1, 1)
    sizes = [card] if card else [0.34, 0.31, 0.28, 0.25, 0.22, 0.19, 0.16]
    best = None
    for hf in sizes:
        h = hf * W
        w = h / aspect
        R = radius * W if radius else min(0.40 * W, (sx1 - sx0 - w * sf) / 2)
        cx = min(max(sc.cx, sx0 + R + w * sf / 2), sx1 - R - w * sf / 2)
        slack = 0.016 * R  # the bob and the spring's overshoot
        lo_cy = sy0 + R * math.sin(tilt) * sb + h * sb * 1.03 / 2 + slack   # far cards stay under the top line
        hi_cy = sy1 - R * math.sin(tilt) * sf - h * sf * 1.03 / 2 - slack   # near cards stay over the bottom line
        if y is not None:
            cys = [y * H]
        else:
            cys = [lo_cy + (hi_cy - lo_cy) * j / 60 for j in range(61)] if hi_cy >= lo_cy else []
        for cy in cys:
            if _clear(sc, cx, cy, R, w, h, tilt):
                best = {"cx": cx, "cy": cy, "R": R, "w": w, "h": h, "tilt": tilt, "sb": sb, "sf": sf, "aspect": aspect}
                break
        if best:
            break
    if best is None:  # nothing clears the face (an extreme close-up): smallest cards, as low as the safe zone allows
        h = sizes[-1] * W
        w = h / aspect
        R = radius * W if radius else min(0.40 * W, (sx1 - sx0 - w * sf) / 2)
        cx = min(max(sc.cx, sx0 + R + w * sf / 2), sx1 - R - w * sf / 2)
        cy = y * H if y is not None else sy1 - R * math.sin(tilt) * sf - h * sf * 1.03 / 2 - 0.016 * R
        best = {"cx": cx, "cy": cy, "R": R, "w": w, "h": h, "tilt": tilt, "sb": sb, "sf": sf, "aspect": aspect}
    return best


def _clear(sc, cx, cy, R, w, h, tilt) -> bool:
    """True when no card on the near half (and the hand-over band at the sides) touches the face."""
    for i in range(0, 360, 6):
        th = math.radians(i)
        z = R * math.cos(th)
        if z < -0.08 * R:
            continue
        s = scale_at(z, R)
        x, yy = cx + R * math.sin(th) * s, cy + z * math.sin(tilt) * s
        m = 0.015 * R * s + 4  # the bob, plus a hair
        if sc.face_hit(x - w * s / 2 - m, yy - h * s / 2 - m, x + w * s / 2 + m, yy + h * s / 2 + m) > 0.0:
            return False
    return True


def best_geometry(sc, tilt_deg, radius=None, card=None, y=None, aspect=None) -> dict:
    """Portrait cards (phone screenshots) when there is room; in a tight close-up, where the chin leaves little
    height, landscape cards if they come out clearly bigger."""
    if aspect:
        return ring_geometry(sc, tilt_deg, radius, card, y, float(aspect))
    tall = ring_geometry(sc, tilt_deg, radius, card, y, ASPECT)
    if tall["h"] >= 0.25 * sc.W:
        return tall
    wide = ring_geometry(sc, tilt_deg, radius, card, y, 0.75)
    return wide if wide["w"] * wide["h"] > 1.3 * tall["w"] * tall["h"] else tall


def track_points(geo: dict, side: str) -> list:
    """The ring's path on screen (where card centres travel), split into its far ('back') or near ('front') half."""
    R, cx, cy, tilt = geo["R"], geo["cx"], geo["cy"], geo["tilt"]
    pts = []
    for i in range(0, 181, 4):
        th = math.radians(i - 90) if side == "front" else math.radians(i + 90)
        z = R * math.cos(th)
        s = scale_at(z, R)
        pts.append((cx + R * math.sin(th) * s, cy + z * math.sin(tilt) * s))
    return pts


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def frames(geo: dict, n_cards: int, n_frames: int, fps: float, speed: float, sc: sp.Scene | None = None) -> list:
    """Per frame, per card: [x, y, scale, rotateY deg, opacity, blur px, depth -1..1]. Cards spring up in place
    (scale, a little extra spin) one after another over the first ~0.9 s, and drift outwards as they fade over the
    last 0.4 s."""
    ease = spring(*PRESETS["gentle"])
    dur = n_frames / fps
    R, cx, cy, tilt = geo["R"], geo["cx"], geo["cy"], geo["tilt"]
    out = []
    for f in range(n_frames):
        t = f / fps
        row = []
        for i in range(n_cards):
            t0 = 0.06 + 0.06 * i
            e = ease(min(1.0, max(0.0, (t - t0) / 0.9)))
            x_out = _smooth((t - (dur - 0.42)) / 0.42)
            r = R * (1 + 0.10 * x_out)  # the ring never contracts towards the face: cards grow in place
            th = 2 * math.pi * (i / n_cards + speed * t) + 0.35 * (1 - e)
            X, Z = r * math.sin(th), r * math.cos(th)
            s = scale_at(Z, R)
            bob = math.sin(2 * math.pi * (0.35 * t + i / n_cards)) * 0.012 * R
            x = cx + X * s
            y = cy + (Z * math.sin(tilt) + bob) * s
            depth = Z / R
            far = max(0.0, -depth)
            pop = min(1.0, max(0.0, (t - t0) / 0.28))
            op = (1 - 0.28 * far) * _smooth(pop) * (1 - x_out)
            size = s * (0.55 + 0.45 * e) * (1 - 0.12 * x_out)
            if sc is not None and depth > -0.08:  # last guard (extreme close-ups): a near card fades off the face
                hw, hh = geo["w"] * size / 2, geo["h"] * size / 2
                op *= max(0.0, 1 - 6 * sc.face_hit(x - hw, y - hh, x + hw, y + hh))
            ry = -math.degrees(math.sin(th)) * 0.42
            row.append([round(x, 1), round(y, 1), round(size, 4), round(ry, 2), round(op, 3), round(2.6 * far, 2),
                        round(depth, 3)])
        out.append(row)
    return out


def render(ctx):
    sc = sp.scene(ctx)
    geo = best_geometry(sc, float(ctx.param("tilt", PARAMS["tilt"])), ctx.param("radius"), ctx.param("card"),
                        ctx.param("y"), ctx.param("aspect"))
    th = sp.theme(ctx.style, ctx.param("theme", PARAMS["theme"]))
    items = [x for x in (ctx.param("items") or []) if str(x).strip()]
    n = max(3, min(10, len(items) or int(ctx.param("n", PARAMS["n"]))))
    assets, cards = {}, []
    if not items:
        face = (sc.cx, (sc.face[1] + sc.chin) / 2) if sc.face else None
        size = (270, 480) if geo["aspect"] > 1 else (400, 300)
        items = [str(p) for p in sp.stills(ctx, n, ctx.param("stills_from"), size=size, face=face)]
    for i in range(n):
        it = items[i % len(items)]
        if sp.image_like(it):
            p = ctx.asset(it)
            name = f"o{i % len(items)}{p.suffix.lower()}"
            assets[name] = p
            tp = " tp" if p.suffix.lower() in (".png", ".webp") else ""  # may be transparent: sits on card_bg
            cards.append(f'<div class="cd{tp}" id="c{i}"><img src="{name}"></div>')
        else:
            ar = sp.is_arabic(it)
            cards.append(f'<div class="cd tx{" ar" if ar else ""}" id="c{i}"><i class="dot"></i>'
                         f'<span>{sp.esc(it)}</span></div>')
    F = frames(geo, n, ctx.n, ctx.fps, float(ctx.param("speed", PARAMS["speed"])), sc)
    k = ctx.W / 1080
    css = f"""
#ring{{position:absolute;inset:0;perspective:{1600 * k:.0f}px}}
#track{{position:absolute;left:0;top:0}}
.cd{{position:absolute;left:0;top:0;width:{geo['w']:.0f}px;height:{geo['h']:.0f}px;margin:{-geo['h'] / 2:.0f}px 0 0 {-geo['w'] / 2:.0f}px;
  border-radius:{20 * k:.0f}px;overflow:hidden;opacity:0;will-change:transform,opacity,filter;
  box-shadow:0 0 0 {1.5 * k:.1f}px rgba(255,255,255,.22),0 {18 * k:.0f}px {44 * k:.0f}px rgba(0,0,0,.45);backface-visibility:hidden}}
.cd img{{width:100%;height:100%;object-fit:cover;display:block}}
{_frame_css(ctx.param("frame"), ctx.param("card_bg"), geo, k)}
.cd.tx{{background:{th['surface2']};display:flex;flex-direction:column;justify-content:flex-end;padding:{18 * k:.0f}px;
  box-sizing:border-box;color:{th['ink']};font:700 {max(22, geo['w'] * 0.16):.0f}px/1.08 "BrandLT";letter-spacing:-.02em}}
.cd.tx.ar{{font-family:"BrandAR";direction:rtl;letter-spacing:0;line-height:1.3}}
.cd .dot{{position:absolute;left:{18 * k:.0f}px;top:{18 * k:.0f}px;width:{12 * k:.0f}px;height:{12 * k:.0f}px;border-radius:50%;
  background:{th['accent']};box-shadow:0 0 {14 * k:.0f}px {th['accent']}}}
.cd.tx.ar .dot{{left:auto;right:{18 * k:.0f}px}}
"""
    D = ctx.dur

    def page(side):
        track = ""
        if ctx.param("track", PARAMS["track"]):
            pts = track_points(geo, side)
            if len(pts) > 1:
                d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                track = (f'<svg id="track" width="{ctx.W}" height="{ctx.H}" viewBox="0 0 {ctx.W} {ctx.H}">'
                         f'<path d="{d}" fill="none" stroke="{ctx.param("track_color") or th["ink"]}" stroke-opacity="{.16 if side == "back" else .26}" '
                         f'stroke-width="{2 * k:.1f}" stroke-linecap="round"/></svg>')
        body = f'{track}<div id="ring">{"".join(cards)}</div>'
        fade = (f"""
  if (document.querySelector('#track')) {{
    tl.fromTo('#track', {{opacity: 0}}, {{opacity: 1, duration: .6, ease: 'power2.out'}}, .1);
    tl.fromTo('#track', {{opacity: 1}}, {{opacity: 0, duration: .35, ease: 'power2.in', immediateRender: false}}, {D - 0.4:.3f});
  }}""")
        js = f"""const F = {json.dumps(F, separators=(',', ':'))}, SIDE = {1 if side == 'front' else -1};
  const els = Array.from(document.querySelectorAll('.cd'));
  const apply = (fi) => {{
    const row = F[Math.max(0, Math.min(F.length - 1, Math.round(fi)))];
    row.forEach((c, i) => {{
      const [x, y, s, ry, op, bl, z] = c;
      // a card belongs to the near layer when z > 0; a short crossfade at the sides hides the hand-over
      const w = Math.max(0, Math.min(1, (z * SIDE) / 0.12 + 0.5));
      const el = els[i];
      el.style.transform = `translate(${{x}}px, ${{y}}px) scale(${{s}}) rotateY(${{ry}}deg)`;
      el.style.opacity = (op * w).toFixed(3);
      el.style.filter = bl > 0.05 ? `blur(${{bl}}px) brightness(${{(1 - bl * 0.07).toFixed(3)}})` : 'none';
      el.style.zIndex = String(Math.round(1000 + z * 500));
    }});
  }};
  const clock = {{f: 0}};
  apply(0);
  tl.fromTo(clock, {{f: 0}}, {{f: {ctx.n - 1}, duration: {(ctx.n - 1) / ctx.fps:.4f}, ease: 'none',
    onUpdate: () => apply(clock.f)}}, 0);""" + fade
        return ctx.page(body, css, js)

    back = ctx.layer(page("back"), "orbit-back", assets)
    front = ctx.layer(page("front"), "orbit-front", assets)
    return sp.composite(ctx, [back], [front], dim=float(ctx.param("dim", PARAMS["dim"])), desat=0.1, bg_blur=0.35,
                        frost=0.0, ramp=(0.4, 0.45))


def _frame_css(frame, card_bg, geo, k) -> str:
    """Optional card styling: a solid frame with a thin inner line (a card frame) and a background colour."""
    css = ""
    if card_bg:
        css += f".cd{{background:{card_bg}}}.cd.tp img{{object-fit:contain;padding:6%;box-sizing:border-box}}"
    if frame:
        bw = max(2.0, frame.get("width", 0.012) * geo["w"])
        inner = frame.get("inner")
        ring = f"inset 0 0 0 {bw:.1f}px {frame.get('color', '#ffffff')}"
        if inner:
            ring += f",inset 0 0 0 {bw + max(1.5, bw * 0.28):.1f}px {inner}"
        css += (f".cd::after{{content:'';position:absolute;inset:0;border-radius:inherit;box-shadow:{ring};"
                f"pointer-events:none}}.cd{{box-shadow:0 {18 * k:.0f}px {44 * k:.0f}px rgba(0,0,0,.45)}}")
    return css
