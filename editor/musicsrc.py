"""Free music from online libraries, for a video without a track of the user's own. Every source and licence here
allows use in a commercial video: Mixkit (Mixkit Free License, no credit needed), Incompetech (Kevin MacLeod,
CC BY 4.0), and CC0 / CC BY tracks found through Openverse (Jamendo, ccMixter, Freesound, Wikimedia Commons) and
ccMixter itself. Non-commercial, no-derivatives and share-alike licences are refused. A track that needs a credit
gets its credit line in the folder's credits.json; the edit's `music.credit` carries it to out/credits.txt.

    python -m editor music-find "<mood or genre>" <dir> [--sources mixkit incompetech openverse ccmixter] [--n 3]
        [--min-dur 20]

Then pick from the folder as usual (`draft --music-dir <dir>`, or `music.credit_for` for a chosen file).
"""
import html
import json
import re
import urllib.parse
from pathlib import Path

from .stock import _get, _get_json, _open, _write_credits

SOURCES = ("mixkit", "incompetech", "openverse", "ccmixter")
OK = {"mixkit", "cc0", "by"}  # every licence a commercial video can use; NC, ND and SA never pass
MIXKIT = "https://mixkit.co/free-stock-music/"
# Mixkit is browsed by genre page; moods map to the genres that carry them
MOODS = {"upbeat": ["dance-pop", "electropop", "house"], "happy": ["pop", "dance-pop"], "chill": ["chillout", "lo-fi-beats"],
         "calm": ["ambient", "chillout"], "corporate": ["corporate-music"], "cinematic": ["film-score", "trailer-music"],
         "energetic": ["edm", "electro-house"], "luxury": ["deep-house", "lounge"], "modern": ["electronica", "future-bass"],
         "tech": ["tech-house", "electronica"], "dramatic": ["trailer-music"], "fun": ["funk", "disco"],
         "romantic": ["easy-listening"], "sad": ["minimalism"], "hip hop": ["hip-hop", "trap"]}
INCOMPETECH = "https://incompetech.com/music/royalty-free/"
OPENVERSE = "https://api.openverse.org/v1/audio/"
CCMIXTER = "https://ccmixter.org/api/query"


def _words(q: str) -> list:
    return [w for w in re.split(r"[^a-z0-9-]+", q.lower()) if w]


def mixkit_genres(query: str, known: list) -> list:
    """The Mixkit genre pages for a query: genres named in it, then the genres its mood words map to."""
    q = query.lower()
    out = [g for g in known if g in q.replace(" ", "-") or g.replace("-", " ") in q]
    for mood, genres in MOODS.items():
        if mood in q:
            out += genres
    return list(dict.fromkeys(out)) or ["electronica"]


def _mixkit_page(page: str) -> list:
    hits = []
    for chunk in page.split('class="item-grid__item"')[1:]:
        url = re.search(r'data-audio-player-preview-url-value="(https://assets\.mixkit\.co/music/(\d+)/\d+\.mp3)"', chunk)
        title = re.search(r'item-grid-card__title[^>]*>(.*?)<', chunk, re.DOTALL)
        by = re.search(r'item-grid-music-preview__author[^>]*>\s*by\s*(.*?)<', chunk, re.DOTALL)
        if url:
            hits.append({"source": "mixkit", "id": url.group(2), "title": html.unescape(title.group(1)).strip() if title else
                         url.group(2), "author": html.unescape(by.group(1)).strip() if by else "Mixkit", "license": "mixkit",
                         "license_url": "https://mixkit.co/license/#musicFree", "page_url": MIXKIT, "url": url.group(1),
                         "attribution_required": False})
    return hits


def search_mixkit(query: str, n: int) -> list:
    home = _get(MIXKIT).decode("utf-8", "replace")
    known = sorted(set(re.findall(r'href="/free-stock-music/([a-z-]+)/"', home)) - {"tag", "mood"})
    hits = []
    for g in mixkit_genres(query, known):
        try:
            page = _mixkit_page(_get(f"{MIXKIT}{g}/").decode("utf-8", "replace"))
        except OSError:
            continue
        for h in page:
            h["page_url"] = f"{MIXKIT}{g}/"
        hits += page[:n]
        if len(hits) >= n:
            break
    return hits[:n]


def incompetech_matches(query: str, pieces: list) -> list:
    """Kevin MacLeod's pieces ranked by how many query words their title, feel, genre and description share."""
    words = _words(query)
    scored = []
    for p in pieces:
        text = " ".join(str(p.get(k) or "") for k in ("title", "feel", "description", "instruments")).lower()
        s = sum(w in text for w in words)
        if s:
            scored.append((-s, p["title"], p))
    return [p for *_, p in sorted(scored)]


def search_incompetech(query: str, n: int) -> list:
    pieces = _get_json(INCOMPETECH + "pieces.json", timeout=40)
    hits = []
    for p in incompetech_matches(query, pieces)[:n]:
        m, s = (str(p.get("length") or "0:0").split(":") + ["0"])[-2:]
        hits.append({"source": "incompetech", "id": p["filename"], "title": p["title"], "author": "Kevin MacLeod",
                     "license": "by", "license_url": "https://creativecommons.org/licenses/by/4.0/",
                     "page_url": "https://incompetech.com/music/royalty-free/music.html",
                     "url": INCOMPETECH + "mp3-royaltyfree/" + urllib.parse.quote(p["filename"]),
                     "attribution_required": True, "duration": int(m) * 60 + int(s)})
    return hits


def search_openverse(query: str, n: int) -> list:
    """Openverse matches every word, so a mood of several words falls back to its words one at a time."""
    results = []
    for q in [query] + (_words(query) if len(_words(query)) > 1 else []):
        params = urllib.parse.urlencode({"q": q, "category": "music", "license": "cc0,by", "page_size": max(n * 2, 4)})
        results = _get_json(f"{OPENVERSE}?{params}", timeout=60).get("results", [])
        if results:
            break
    hits = []
    for r in results:
        if (r.get("license") or "").lower() not in OK or not r.get("url"):
            continue
        hits.append({"source": f"openverse:{r.get('source')}", "id": r["id"], "title": r.get("title") or r["id"],
                     "author": r.get("creator") or "", "license": r["license"].lower(),
                     "license_url": r.get("license_url"), "page_url": r.get("foreign_landing_url"), "url": r["url"],
                     "attribution_required": r["license"].lower() != "cc0",
                     "duration": (r.get("duration") or 0) / 1000 or None})
    return hits[:n]


def search_ccmixter(query: str, n: int) -> list:
    q = urllib.parse.urlencode({"f": "json", "limit": n * 2, "lic": "by", "tags": "instrumental", "search": query,
                                "search_type": "any", "sort": "rank"})
    hits = []
    for r in _get_json(f"{CCMIXTER}?{q}", timeout=40):
        f = next((f for f in r.get("files", []) if f.get("download_url", "").endswith(".mp3")), None)
        if not f or "noncommercial" in (r.get("license_name") or "").lower() or "by-nc" in (r.get("license_url") or ""):
            continue
        hits.append({"source": "ccmixter", "id": str(r["upload_id"]), "title": r.get("upload_name"),
                     "author": r.get("user_real_name") or r.get("user_name"), "license": "by",
                     "license_url": r.get("license_url"), "page_url": r.get("file_page_url"), "url": f["download_url"],
                     "attribution_required": True})
    return hits[:n]


SEARCH = {"mixkit": search_mixkit, "incompetech": search_incompetech, "openverse": search_openverse,
          "ccmixter": search_ccmixter}


def attribution(hit: dict) -> str | None:
    """The credit line a CC BY track needs (None for Mixkit and CC0)."""
    if not hit.get("attribution_required"):
        return None
    lic = {"by": "CC BY"}.get(hit["license"], hit["license"].upper())
    return f'"{hit["title"]}" by {hit["author"]} ({hit["source"].split(":")[-1]}), {lic} {hit.get("license_url") or ""}'.strip()


def file_name(hit: dict) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", f'{hit["source"].split(":")[-1]}-{hit["title"]}'.lower()).strip("-")[:60]
    return f"{stem}.mp3"


def search(query: str, sources=SOURCES, n: int = 3) -> tuple:
    """(hits, notes): n candidates per source; a source that fails is skipped with a note, never fatal."""
    hits, notes = [], []
    for s in sources:
        try:
            hits += [h for h in SEARCH[s](query, n) if h["license"] in OK]
        except Exception as e:  # noqa: BLE001  a library that is down or blocked must not stop the others
            notes.append(f"{s}: skipped ({type(e).__name__})")
    return hits, notes


def find(query: str, dest_dir, sources=SOURCES, n: int = 3, min_dur: float = 0) -> list:
    """Download the candidates into dest_dir (skipping ones already there) and record each in credits.json with
    its credit line. Returns [(path, hit)]."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    hits, notes = search(query, sources, n)
    for note in notes:
        print(note)
    out = []
    for h in hits:
        if min_dur and h.get("duration") and h["duration"] < min_dur:
            continue
        path = dest / file_name(h)
        if not path.exists():
            try:
                with _open(h["url"], {"Referer": h.get("page_url") or h["url"]}, timeout=90) as r:  # ccMixter wants one
                    data = r.read()
            except OSError as e:
                print(f'{h["source"]}: "{h["title"]}" not downloaded ({type(e).__name__})')
                continue
            if len(data) < 20_000:
                continue
            path.write_bytes(data)
        _write_credits(dest, path.name, h)
        out.append((path, h))
    return out


def credit_for(path) -> str | None:
    """The credit line recorded for a downloaded track (None when it needs none or was not downloaded here)."""
    p = Path(path)
    try:
        entry = json.loads((p.parent / "credits.json").read_text()).get(p.name) or {}
    except (OSError, ValueError):
        return None
    return attribution(entry) if entry.get("title") and entry.get("license") else None


def cmd(a) -> None:
    for path, h in find(a.query, a.dest, tuple(a.sources), a.n, a.min_dur):
        need = "credit: " + attribution(h) if h.get("attribution_required") else "no credit needed"
        print(f'{path}  [{h["source"]}, {h["license"]}] {need}')
