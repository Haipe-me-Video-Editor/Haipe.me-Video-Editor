import io
import json
import urllib.error

import pytest

from editor import stock

MIXKIT = """
<div class="item-grid-card"
    data-algolia-analytics-object-id="video-49878">
  <div class="item-grid-video-player item-grid-video-player--vertical item-grid-video-player--masonry-item">
    <img src="https://assets.mixkit.co/videos/49878/49878-thumb-360-0.jpg" alt="Big city at night." width="460" height="818">
    <video src="https://assets.mixkit.co/videos/49878/49878-360.mp4"></video>
    <span class="item-grid-video-player__overlay-video-title">Big city at night</span>
    <span class="item-grid-video-player__overlay-video-description">Aerial view &amp; lights</span>
    <a href="/free-stock-video/big-city-at-night-49878/" class="item-grid-video-player__overlay-link">
        Big city at night
    </a>
  </div>
</div>
<div class="item-grid-card item-grid-card--show-meta"
    data-algolia-analytics-object-id="video-261">
  <img src="https://assets.mixkit.co/videos/261/261-thumb-360-0.jpg" alt="Office meeting." width="460" height="259">
  <video src="https://assets.mixkit.co/videos/261/261-360.mp4"></video>
  <a href="/free-stock-video/office-meeting-261/" class="item-grid-video-player__overlay-link">
    Office meeting
  </a>
</div>
<div class="item-grid-card">
  <video src="https://assets.mixkit.co/videos/9/9-360.mp4"></video>
  <a href="/free-stock-video/x-9/" class="item-grid-video-player__overlay-link">Dream city, AI-generated</a>
</div>
"""

ARCHIVE_SEARCH = {"response": {"numFound": 4, "docs": [
    {"identifier": "CityTheP1939", "title": "City, The", "licenseurl": "http://creativecommons.org/licenses/publicdomain/"},
    {"identifier": "nc1", "title": "NC film", "licenseurl": "https://creativecommons.org/licenses/by-nc-sa/4.0/"},
    {"identifier": "sa1", "title": "SA film", "licenseurl": "http://creativecommons.org/licenses/by-sa/3.0/"},
    {"identifier": "nd1", "title": "ND film", "licenseurl": "http://creativecommons.org/licenses/by-nd/3.0/"},
]}}

ARCHIVE_META = {"metadata": {"identifier": "CityTheP1939", "title": "City, The (Part I)", "creator": "ADF",
                             "licenseurl": "http://creativecommons.org/licenses/publicdomain/", "subject": "city; urban"},
                "files": [
                    {"name": "City.mpeg", "format": "MPEG2", "source": "original", "size": "900000000"},
                    {"name": "City_512kb.mp4", "format": "512Kb MPEG4", "source": "derivative", "size": "40000000",
                     "length": "600.5", "width": "320", "height": "240"},
                    {"name": "City The.mp4", "format": "h.264", "source": "derivative", "size": "90000000",
                     "length": "10:00", "width": "640", "height": "480"},
                    {"name": "City_huge.mp4", "format": "h.264 HD", "source": "derivative", "size": "900000000",
                     "width": "1920", "height": "1080"},
                ]}


def _commons_page(pageid, index, title, license, short, cats="Videos", artist="<a href='x'>Jo &amp; Al</a>",
                  derivatives=True):
    info = {"size": 5000000, "width": 3840, "height": 2160, "duration": 12.5, "mime": "video/webm",
            "url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/{title}.webm?utm_source=x",
            "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{title}.webm",
            "thumburl": f"https://upload.wikimedia.org/thumb/{title}.jpg",
            "extmetadata": {"ObjectName": {"value": title}, "Categories": {"value": cats},
                            "Artist": {"value": artist}, "License": {"value": license},
                            "LicenseShortName": {"value": short}, "AttributionRequired": {"value": "true"}}}
    if derivatives:
        base = f"https://upload.wikimedia.org/wikipedia/commons/transcoded/a/ab/{title}.webm/{title}.webm"
        info["derivatives"] = [
            {"src": info["url"], "width": 3840, "height": 2160},
            {"src": f"{base}.360p.vp9.webm", "transcodekey": "360p.vp9.webm", "width": 640, "height": 360},
            {"src": f"{base}.1080p.vp9.webm", "transcodekey": "1080p.vp9.webm", "width": 1920, "height": 1080,
             "bandwidth": 8000000},
            {"src": f"{base}.2160p.vp9.webm", "transcodekey": "2160p.vp9.webm", "width": 3840, "height": 2160},
        ]
    return {"pageid": pageid, "index": index, "title": f"File:{title}.webm", "videoinfo": [info]}


COMMONS = {"query": {"pages": {
    "3": _commons_page(3, 2, "Second", "cc0", "CC0", derivatives=False),
    "1": _commons_page(1, 1, "First", "cc-by-sa-4.0", "CC BY-SA 4.0"),
    "5": _commons_page(5, 3, "NC", "cc-by-nc-4.0", "CC BY-NC 4.0"),
    "6": _commons_page(6, 4, "ND", "cc-by-nd-4.0", "CC BY-ND 4.0"),
    "7": _commons_page(7, 5, "Fake", "cc0", "CC0", cats="AI-generated videos|CC-Zero"),
    "8": _commons_page(8, 6, "Gfdl", "gfdl", "GFDL"),
}}}


def test_mixkit_parses_ids_titles_and_orientation():
    hits = stock._parse_mixkit(MIXKIT)
    assert [h["id"] for h in hits] == ["49878", "261"]
    a, b = hits
    assert a["title"] == "Big city at night" and a["url"] == "https://assets.mixkit.co/videos/49878/49878-1080.mp4"
    assert a["alt_urls"] == ["https://assets.mixkit.co/videos/49878/49878-720.mp4"]
    assert (a["width"], a["height"]) == (1080, 1920) and (b["width"], b["height"]) == (1920, 1080)
    assert b["title"] == "Office meeting" and b["page_url"] == "https://mixkit.co/free-stock-video/office-meeting-261/"


def test_archive_search_keeps_commercial_licenses():
    docs = stock._parse_archive_search(ARCHIVE_SEARCH)
    assert [d["identifier"] for d in docs] == ["CityTheP1939", "sa1"]
    assert docs[0]["license"] == "Public Domain" and docs[1]["license"] == "CC BY-SA 3.0"


def test_archive_meta_picks_h264_under_cap():
    h = stock._parse_archive_meta(ARCHIVE_META, stock._parse_archive_search(ARCHIVE_SEARCH)[0])
    assert h["url"] == "https://archive.org/download/CityTheP1939/City%20The.mp4"
    assert (h["width"], h["height"], h["duration"]) == (640, 480, 600.0)
    assert h["author"] == "ADF" and h["license"] == "Public Domain" and not h["attribution_required"]
    assert h["tags"] == ["city", "urban"] and h["page_url"] == "https://archive.org/details/CityTheP1939"
    nc = {**ARCHIVE_META, "metadata": {**ARCHIVE_META["metadata"],
                                       "licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/"}}
    assert stock._parse_archive_meta(nc) is None
    assert stock._parse_archive_meta({"metadata": ARCHIVE_META["metadata"], "files": ARCHIVE_META["files"][:1]}) is None


@pytest.mark.parametrize("url,name", [
    ("http://creativecommons.org/licenses/publicdomain/", "Public Domain"),
    ("http://creativecommons.org/publicdomain/mark/1.0/", "Public Domain"),
    ("https://creativecommons.org/publicdomain/zero/1.0/", "CC0"),
    ("https://creativecommons.org/licenses/by/4.0/", "CC BY 4.0"),
    ("http://creativecommons.org/licenses/by-sa/3.0/", "CC BY-SA 3.0"),
    ("https://creativecommons.org/licenses/by-nc/4.0/", None),
    ("https://creativecommons.org/licenses/by-nc-nd/4.0/", None),
    ("https://creativecommons.org/licenses/by-nd/2.5/", None),
    ("http://creativecommons.org/licenses/sampling+/1.0/", None),
    ("https://example.com/license", None),
])
def test_cc_license(url, name):
    got = stock._cc_license(url)
    assert (got[0] if got else None) == name


def test_commons_licenses_order_and_transcode():
    hits = stock._parse_commons(COMMONS)
    assert [h["title"] for h in hits] == ["First", "Second"]
    first, second = hits
    assert first["url"].endswith("First.webm.1080p.vp9.webm") and (first["width"], first["height"]) == (1920, 1080)
    assert first["alt_urls"] == ["https://upload.wikimedia.org/wikipedia/commons/a/ab/First.webm"]
    assert first["preview_url"].endswith("360p.vp9.webm") and first["size"] == 12500000
    assert first["license"] == "CC BY-SA 4.0" and first["author"] == "Jo & Al" and first["attribution_required"]
    assert second["url"] == "https://upload.wikimedia.org/wikipedia/commons/a/ab/Second.webm" and second["alt_urls"] == []
    assert second["license"] == "CC0" and second["duration"] == 12.5


def test_ai_text_detection():
    assert stock._is_ai("AI-generated videos") and stock._is_ai("made with AI") and stock._is_ai("midjourney")
    assert not stock._is_ai("ai") and not stock._is_ai("airport, rain") and not stock._is_ai("said hi")


def _fake(source, n, dur=10.0, w=1920, h=1080):
    return [stock._hit(source, i, f"{source}{i}", f"https://{source}/{i}.mp4", duration=dur, width=w, height=h)
            for i in range(n)]


def test_search_interleaves_isolates_failures_and_filters(monkeypatch):
    def boom(q, n):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(stock, "SEARCHERS", {
        "first": lambda q, n: _fake("first", 3), "down": boom,
        "mixkit": lambda q, n: _fake("mixkit", 1) + _fake("mixkit", 1, w=1080, h=1920),
        "archive": lambda q, n: _fake("archive", 2, dur=900.0),
        "commons": lambda q, n: _fake("commons", 2, dur=900.0) + _fake("commons", 1, 1.0)})
    notes = []
    hits = stock.search("city", sources=tuple(stock.SEARCHERS), per_source=2, notes=notes)
    assert [(h["source"], h["id"]) for h in hits] == [("first", "0"), ("mixkit", "0"), ("archive", "0"),
                                                      ("first", "1"), ("archive", "1")]
    assert any(n.startswith("down: URLError") for n in notes) and "commons: no matches" in notes
    portrait = stock.search("city", sources=("mixkit",), portrait=True)
    assert [(h["width"], h["height"]) for h in portrait] == [(1080, 1920)]
    with pytest.raises(ValueError, match="pexels"):
        stock.search("city", sources=("pexels",))


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_download_part_rename_skip_fallback_and_credits(monkeypatch, tmp_path):
    calls = []

    def fake_open(url, headers=None, timeout=20, tries=4):
        calls.append(url)
        if url.endswith("-1080.mp4"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return _Resp(b"video-bytes")

    monkeypatch.setattr(stock, "_open", fake_open)
    hit = stock._parse_mixkit(MIXKIT)[1]
    out = stock.download(hit, tmp_path / "dl")
    assert out == tmp_path / "dl" / "mixkit-261.mp4" and out.read_bytes() == b"video-bytes"
    assert calls == [hit["url"], *hit["alt_urls"]] and not list(out.parent.glob("*.part"))
    credits = json.loads((out.parent / "credits.json").read_text())
    assert credits["mixkit-261.mp4"]["license"] == "Mixkit Free License"
    assert credits["mixkit-261.mp4"]["url"].endswith("-720.mp4")
    assert credits["mixkit-261.mp4"]["page_url"] == "https://mixkit.co/free-stock-video/office-meeting-261/"

    calls.clear()
    assert stock.download(hit, tmp_path / "dl") == out and calls == []

    commons = stock._parse_commons(COMMONS)[0]
    p = stock.download(commons, tmp_path / "dl")
    assert p.name == "commons-1.webm"
    credits = json.loads((out.parent / "credits.json").read_text())
    assert set(credits) == {"mixkit-261.mp4", "commons-1.webm"} and credits["commons-1.webm"]["author"] == "Jo & Al"


def test_download_cleans_up_part_on_error(monkeypatch, tmp_path):
    class Broken(_Resp):
        def read(self, *a):
            raise ConnectionResetError("cut")

    monkeypatch.setattr(stock, "_open", lambda *a, **k: Broken(b""))
    with pytest.raises(ConnectionResetError):
        stock.download(stock._parse_mixkit(MIXKIT)[0], tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_contact_sheet_grid(monkeypatch, tmp_path):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 36), (200, 50, 50)).save(buf, "JPEG")
    monkeypatch.setattr(stock, "_get", lambda url, headers=None, timeout=20, tries=4: buf.getvalue())
    hits = stock._parse_mixkit(MIXKIT) + stock._parse_commons(COMMONS)
    out = stock.contact_sheet(hits, tmp_path / "sheet.jpg", cols=2, cell=160)
    im = Image.open(out)
    assert im.size == (320, 2 * (90 + 24))


def test_every_source_here_needs_no_key():
    assert set(stock.ALL) >= {"mixkit", "archive", "commons"}
