"""Damped-spring eases (editor/graphics/spring.py): the JS that runs in compositions and its Python mirror."""
import json
import re
import shutil
import subprocess

import pytest

from editor.graphics import spring as sp
from editor.graphics.composition import composition_html
from editor.graphics.desk import desk_html
from editor.graphics.kit import kit_html
from editor.style import load_style

STYLE = load_style("finance")
FONTS = {"latin": "a.ttf", "arabic": "b.ttf"}
GRID = [i / 2000 for i in range(2001)]
# Peak overshoot band per preset (fraction past the target).
BANDS = {"gentle": (0.01, 0.03), "snappy": (0.06, 0.08), "bouncy": (0.10, 0.13)}


def _js_samples() -> dict:
    """Evaluate SPRING_JS in node: every preset and the default spring, sampled on GRID."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = sp.SPRING_JS + f"""
const grid = {json.dumps(GRID)};
const out = {{}};
for (const k in SPRING) out[k] = grid.map(SPRING[k]);
out.default = grid.map(spring());
out.overdamped = grid.map(spring(100, 40, 1));
out.critical = grid.map(spring(100, 20, 1));
console.log(JSON.stringify(out));"""
    return json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)


@pytest.fixture(scope="module")
def js():
    return _js_samples()


@pytest.mark.parametrize("name", list(sp.PRESETS))
def test_js_presets_end_exactly_at_one_and_overshoot_in_band(js, name):
    v = js[name]
    assert v[0] == 0 and v[-1] == 1
    lo, hi = BANDS[name]
    assert lo <= max(v) - 1 <= hi
    assert abs(max(v) - 1 - sp.overshoot(*sp.PRESETS[name])) < 0.002  # matches the analytic peak


@pytest.mark.parametrize("name", list(sp.PRESETS) + ["default", "overdamped", "critical"])
def test_js_settles_before_the_end(js, name):
    # the last 3% of the tween is the settled tail: within 0.1% (+ the normalising correction) of the target
    assert all(abs(x - 1) < 2 * sp.SETTLE_EPS for x in js[name][-60:])


@pytest.mark.parametrize("name", ["default", "overdamped", "critical"])
def test_js_damped_springs_never_overshoot(js, name):
    v = js[name]
    assert max(v) <= 1 + 1e-9 and all(b >= a - 1e-9 for a, b in zip(v, v[1:]))


def test_python_mirror_matches_the_js(js):
    for name, args in sp.PRESETS.items():
        ease = sp.spring(*args)
        assert max(abs(ease(t) - x) for t, x in zip(GRID, js[name])) < 1e-9
    assert max(abs(sp.spring()(t) - x) for t, x in zip(GRID, js["default"])) < 1e-9


def test_gentle_rises_monotonically_and_never_dips_back_visibly():
    ease = sp.spring(*sp.PRESETS["gentle"])
    v = [ease(t) for t in GRID]
    peak = v.index(max(v))
    assert all(b >= a for a, b in zip(v[:peak], v[1:peak + 1]))  # one clean rise to the peak
    first_cross = next(i for i, x in enumerate(v) if x >= 1)
    assert min(v[first_cross:]) > 1 - sp.SETTLE_EPS  # after landing it never sinks back below the target
    assert max(v) - 1 < 0.025


def test_spring_in_rejects_unknown_presets():
    with pytest.raises(ValueError):
        sp.spring_in("#card", "y:40", "y:0,duration:.45", "wobbly", 0)


def _script(html: str) -> str:
    return html[html.index("const tl"):]


@pytest.mark.parametrize("spec, preset", [
    ({"type": "hook", "text": "Stop scrolling"}, "gentle"),
    ({"type": "quote", "text": "Less is more", "by": "Mies"}, "gentle"),
    ({"type": "headline", "text": "Oil hits record"}, "gentle"),
    ({"type": "list", "items": ["one", "two"]}, "gentle"),
    ({"type": "stat", "value": "73%", "label": "drop"}, "gentle"),
    ({"type": "lower_third", "name": "Ada", "sub": "CTO"}, "snappy"),
    ({"type": "ticker", "name": "Bitcoin", "ticker": "BTC"}, "snappy"),
    ({"type": "chapter", "text": "Part 2"}, "snappy"),
    ({"type": "credit", "text": "CNBC"}, "snappy"),
])
def test_card_entrances_spring_and_keep_their_timing(spec, preset):
    d = 3.0
    html = composition_html({**spec, "dur": d}, STYLE, (1080, 1920), FONTS)
    assert html.count("function spring(") == 1  # the helper is injected once
    s = _script(html)
    # the card still lands at .45 s and leaves on a smooth ease at the same time as before
    assert 'springIn(tl,"#card",' in s and f'duration:.45}},"{preset}",0);' in s
    assert f'tl.to("#card", {{y: -20, opacity: 0, duration: .3, ease: "power2.in"}}, {d - 0.3});' in s
    assert "power3.out" not in s and "back.out" not in s


def test_stat_number_and_list_items_land_snappy():
    stat = _script(composition_html({"type": "stat", "dur": 2.0, "value": "9", "label": "x"}, STYLE, (1080, 1920), FONTS))
    assert 'springIn(tl,"#card .num",{scale:.8},{scale:1,duration:.35},"snappy",0.1);' in stat  # lands at .45 too
    lst = _script(composition_html({"type": "list", "dur": 3.0, "items": ["a", "b"]}, STYLE, (1080, 1920), FONTS))
    assert 'springIn(tl,"#card .item",{x:30,opacity:0},{x:0,opacity:1,duration:.35,stagger:.18},"snappy",0.25);' in lst


@pytest.mark.parametrize("fx", ["words", "pop", "bloom"])
def test_kinetic_pops_are_bouncy(fx):
    s = _script(composition_html({"type": "kinetic", "dur": 2.5, "text": "Big news", "fx": fx}, STYLE,
                                 (1080, 1920), FONTS))
    assert '"bouncy"' in s and "back.out" not in s


def test_kit_and_desk_pages_carry_the_helper():
    kit = kit_html({"type": "badge", "dur": 2.0, "icon": "chart"}, STYLE, (1080, 1920),
                   {"ar": "a.ttf", "latin": "b.ttf"}, None)
    assert kit.count("function spring(") == 1 and '"bouncy"' in kit and "back.out" not in kit
    desk = desk_html({"dur": 3.0, "card": {"type": "steps", "title": "How", "items": ["one", "two"]}},
                     STYLE, (1080, 1920), {"latin": "a", "arabic": "b", "display": "c", "mono": "d"}, None)
    assert desk.count("function spring(") == 1 and 'springIn(tl,"#panel",' in desk


def test_exits_never_spring():
    for html in (composition_html({"type": "hook", "dur": 3.0, "text": "x"}, STYLE, (1080, 1920), FONTS),):
        for m in re.finditer(r'tl\.to\("[^"]+",\s*\{[^}]*opacity:\s*0[^}]*\}', html):
            assert "SPRING" not in m.group(0) and "power2.in" in m.group(0)
