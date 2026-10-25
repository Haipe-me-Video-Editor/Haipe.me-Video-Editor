"""Free music: only licences a commercial video can use, the credit line a CC BY track needs, and a library that is
down never stops the others. The network is stood in for."""
import json

from editor import musicsrc as ms

MIXKIT_PAGE = """<div class="item-grid__item"><div data-audio-player-preview-url-value="https://assets.mixkit.co/music/130/130.mp3">
<h2 class="item-grid-card__title"> Tech House vibes </h2><p class="item-grid-music-preview__author"> by Alejandro Maga&ntilde;a </p>
</div></div>"""


def test_mixkit_page_and_genres():
    hits = ms._mixkit_page(MIXKIT_PAGE)
    assert hits[0]["title"] == "Tech House vibes" and hits[0]["author"] == "Alejandro Magaña"
    assert hits[0]["license"] == "mixkit" and not hits[0]["attribution_required"]
    known = ["deep-house", "lo-fi-beats", "electronica", "pop"]
    assert ms.mixkit_genres("lo-fi beats", known)[0] == "lo-fi-beats"
    assert ms.mixkit_genres("something calm", known) == ["ambient", "chillout"]
    assert ms.mixkit_genres("zzz", known) == ["electronica"]


def test_incompetech_ranks_by_shared_words():
    pieces = [{"title": "Medieval", "feel": "Ren Faire", "filename": "a.mp3"},
              {"title": "Cloud Dancer", "feel": "Bright, Uplifting", "description": "upbeat electronic", "filename": "b.mp3"}]
    assert [p["title"] for p in ms.incompetech_matches("upbeat electronic", pieces)] == ["Cloud Dancer"]


def test_only_commercial_safe_licences_and_the_credit_line(monkeypatch):
    rows = [{"id": "1", "title": "Free", "creator": "A", "license": "cc0", "url": "https://x/1.mp3"},
            {"id": "2", "title": "Credit me", "creator": "B", "license": "by", "license_url": "https://cc/by/4.0/",
             "url": "https://x/2.mp3", "source": "jamendo"},
            {"id": "3", "title": "No ads", "creator": "C", "license": "by-nc", "url": "https://x/3.mp3"},
            {"id": "4", "title": "Share alike", "creator": "D", "license": "by-sa", "url": "https://x/4.mp3"}]
    monkeypatch.setattr(ms, "_get_json", lambda url, timeout=0: {"results": rows})
    hits = ms.search_openverse("upbeat", 5)
    assert [h["title"] for h in hits] == ["Free", "Credit me"]
    assert ms.attribution(hits[0]) is None
    assert ms.attribution(hits[1]) == '"Credit me" by B (jamendo), CC BY https://cc/by/4.0/'


def test_a_library_that_fails_is_skipped(monkeypatch):
    def down(q, n):
        raise OSError("blocked")
    monkeypatch.setitem(ms.SEARCH, "mixkit", down)
    monkeypatch.setitem(ms.SEARCH, "incompetech", lambda q, n: [{"source": "incompetech", "title": "T", "author": "K",
                                                                  "license": "by", "attribution_required": True}])
    hits, notes = ms.search("upbeat", ("mixkit", "incompetech"), 2)
    assert len(hits) == 1 and notes == ["mixkit: skipped (OSError)"]


def test_find_downloads_and_records_the_credit(tmp_path, monkeypatch):
    hit = {"source": "incompetech", "id": "b.mp3", "title": "Cloud Dancer", "author": "Kevin MacLeod", "license": "by",
           "license_url": "https://creativecommons.org/licenses/by/4.0/", "page_url": "https://incompetech.com",
           "url": "https://incompetech.com/b.mp3", "attribution_required": True, "duration": 220}
    monkeypatch.setattr(ms, "search", lambda q, s, n: ([hit, {**hit, "id": "short", "title": "Short", "duration": 9}], []))

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"\0" * 30_000

    seen = {}
    monkeypatch.setattr(ms, "_open", lambda url, headers=None, timeout=0: seen.update(headers or {}) or R())
    got = ms.find("upbeat", tmp_path, ("incompetech",), 2, min_dur=20)
    assert [p.name for p, _ in got] == ["incompetech-cloud-dancer.mp3"]  # the 9 s track is skipped
    assert seen["Referer"] == "https://incompetech.com"
    credits = json.loads((tmp_path / "credits.json").read_text())
    assert credits["incompetech-cloud-dancer.mp3"]["license"] == "by"
    assert ms.credit_for(got[0][0]).startswith('"Cloud Dancer" by Kevin MacLeod')
    assert ms.credit_for(tmp_path / "missing.mp3") is None
