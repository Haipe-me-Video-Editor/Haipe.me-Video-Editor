import pytest

from editor.fx import _glass as G
from editor.fx import list_tracker as L
from editor.fx import registry


def test_registered_with_params():
    assert registry()["list_tracker"] is L
    assert {"items", "current", "title", "counter", "prev", "enter", "exit", "size"} <= set(L.PARAMS)


def test_cells_number_down_the_first_column_then_the_second():
    assert [L.cell(i, 5) for i in range(5)] == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]
    assert [L.cell(i, 4) for i in range(4)] == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_states_and_numbers():
    assert [L.state(i, 2) for i in range(4)] == ["past", "past", "cur", "next"]
    assert L.num(7, 17) == "07" and L.num(3, 120) == "003"


def test_fit_shrinks_then_windows_rows():
    band = 0.215 * 1920 - 0.13 * 1920
    s, vis = L.fit(4, True, band)
    assert vis == 2 and s <= 1
    s, vis = L.fit(6, True, band)
    assert vis == 3 and s >= L.MIN_SCALE
    s, vis = L.fit(17, True, band)
    assert s == L.MIN_SCALE and 1 <= vis < L.rows(17)                 # long list: a scrolling window
    assert L.natural_h(vis, True) * s <= band + 1e-6


def test_scroll_keeps_the_current_row_in_view():
    n, vis = 17, 3
    for i in range(n):
        top = L.scroll_top(i, n, vis)
        assert 0 <= top <= L.rows(n) - vis
        assert top <= L.cell(i, n)[1] < top + vis
    assert L.scroll_top(5, 6, 3) == 0                                  # everything visible: never scrolls


def test_framing_classes():
    H = 1920
    close = G.head_from(198, 790, 582, 345, 455, 1094, 557)
    wide = G.head_from(450, 630, 1050, 960, 1010, 1180, 180)
    tight = G.head_from(150, 900, 420, 250, 330, 1000, 620)
    assert L.framing(close, H) == "close" and L.framing(wide, H) == "wide" and L.framing(tight, H) == "tight"
    # a few pixels of head motion between neighbouring windows does not change the class (continuity)
    nudged = G.head_from(190, 800, 570, 330, 440, 1080, 560)
    assert L.framing(nudged, H) == "close"


def test_band_stays_above_the_brows_on_a_close_up():
    close = G.head_from(198, 790, 582, 345, 455, 1094, 557)
    assert L.BAND_BOTTOM["close"] * 1920 < close["brow"] - 20


class _Ctx:
    """Just enough of Ctx to build a page without rendering."""
    W, H, dur = 1080, 1920, 2.5

    def __init__(self, **spec):
        self.spec = spec
        self.style = {"name": "acme", "accent": "#00a676", "ink": "#f0f0f0", "bg": "#111111"}

    def param(self, k, d=None):
        return self.spec.get(k, d)

    def page(self, body, css, js):
        return body + "\n<style>" + css + "</style>\n<script>" + js + "</script>"


ITEMS = ["Lorem ipsum", "Plan A review", "Launch day", "Final results"]


def test_chained_windows_share_one_layout():
    """Window k (exit false) and window k+1 (enter false) draw the same panel: only the highlight differs."""
    a = L._page(_Ctx(items=ITEMS, title="Roadmap"), ITEMS, 1, 0, True, False, "close")
    b = L._page(_Ctx(items=ITEMS, title="Roadmap"), ITEMS, 2, 1, False, False, "close")
    css = lambda p: p.split("<style>")[1].split("</style>")[0]
    assert css(a) == css(b)
    assert "#panel',{opacity:0" not in a                             # exit false: stays up
    assert "springIn(tl,'#panel'" not in b                           # enter false: no entrance
    assert "#hl" in b and "'#dB'" in b                                 # the highlight moves, the counter rolls


def test_render_validates(tmp_path):
    with pytest.raises(ValueError):
        L.render(_Ctx(items=["one"]))
    with pytest.raises(ValueError):
        L.render(_Ctx(items=ITEMS, current=9))
