"""Free stock B-roll: search Mixkit, Internet Archive and Wikimedia Commons, then download. None of them needs an
account or a key.

Only free sources, never AI-generated clips, and only licenses that allow commercial use (no NC/ND). A failing
source is skipped with a note. `download()` keeps credits.json next to the files for attribution.
"""
import html
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LONG_FORM = {"archive"}  # whole films: max_dur doesn't apply, trim a section instead

BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
# Wikimedia wants a contact URL in the user agent: set EDITOR_CONTACT to your repo or email
WIKI_UA = f"video-editor/1.0 ({os.environ.get('EDITOR_CONTACT', 'https://github.com')})"
ARCHIVE_MAX_BYTES = 200 * 1024 * 1024
ARCHIVE_COLLECTIONS = ("prelinger", "stock_footage")  # curated PD/CC footage; open uploads mislabel films as CC0

LICENSES = {
    "mixkit": ("Mixkit Free License", "https://mixkit.co/license/#videoFree"),
}

_AI = re.compile(r"\bai[\s_-]*(?:generated|created)\b"
                 r"|\b(?:generated|made|created) (?:by|with|using) (?:an? )?(?:ai|artificial intelligence)\b"
                 r"|\b(?:midjourney|stable[\s_-]diffusion|dall-?e|text[\s_-]to[\s_-]video)\b", re.I)


def _is_ai(*texts) -> bool:
    return any(_AI.search(t) for t in texts if isinstance(t, str))


SECRET_VARS: list = []  # environment variables whose values never appear in a note


def _scrub(text: str) -> str:
    for var in SECRET_VARS:
        if os.environ.get(var):
            text = text.replace(os.environ[var], "***")
    return text


def _open(url: str, headers: dict | None = None, timeout: float = 20, tries: int = 4):
    """urlopen with a browser User-Agent; retries 429/503 (Wikimedia rate-limits shared IPs in bursts)."""
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, **(headers or {})})
    for attempt in range(tries):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == tries - 1:
                raise
            time.sleep(min(_num(e.headers.get("Retry-After")) or 1.0, 15.0) + attempt)


def _get(url: str, headers: dict | None = None, timeout: float = 20, tries: int = 4) -> bytes:
    with _open(url, headers, timeout, tries) as r:
        return r.read()


def _get_json(url: str, headers: dict | None = None, timeout: float = 20):
    return json.loads(_get(url, headers, timeout))


def _size_1080(w, h) -> tuple:
    """Dimensions of the 1080p rendition of a w×h master: fit in 1920×1080 (or 1080×1920), never upscaled."""
    if not w or not h:
        return w, h
    k = min(1.0, 1920 / max(w, h), 1080 / min(w, h))
    return round(w * k / 2) * 2, round(h * k / 2) * 2


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _hit(source, id, title, url, **kw) -> dict:
    h = {"source": source, "id": str(id), "title": (title or "").strip(), "url": url, "preview_url": None,
         "thumb_url": None, "alt_urls": [], "duration": None, "width": None, "height": None, "size": None,
         "license": LICENSES.get(source, ("", ""))[0], "license_url": LICENSES.get(source, ("", ""))[1],
         "author": "", "page_url": "", "tags": [], "attribution_required": False}
    h.update(kw)
    return h


# --- Mixkit -------------------------------------------------------------------------------------------------------

def _mixkit_text(block: str, pattern: str) -> str:
    m = re.search(pattern, block, re.S)
    return html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""


def _parse_mixkit(page: str) -> list:
    out, seen = [], set()
    for block in re.split(r'<div class="item-grid-card[\s"]', page)[1:]:
        m = re.search(r"assets\.mixkit\.co/videos/(\d+)/\1-360\.mp4", block)
        if not m or m.group(1) in seen:
            continue
        vid = m.group(1)
        seen.add(vid)
        title = (_mixkit_text(block, r'class="item-grid-video-player__overlay-link"[^>]*>(.*?)</a>')
                 or _mixkit_text(block, r'class="item-grid-card__title">.*?<a[^>]*>(.*?)</a>')
                 or _mixkit_text(block, r'<img[^>]*alt="([^"]*)"').rstrip("."))
        desc = (_mixkit_text(block, r'class="item-grid-video-player__overlay-video-description">(.*?)</span>')
                or _mixkit_text(block, r'class="item-grid-card__description">(.*?)</p>'))
        if _is_ai(title, desc):
            continue
        href = re.search(r'href="(/free-stock-video/[^"]+)"', block)
        dims = re.search(r'<img[^>]*width="(\d+)" height="(\d+)"', block)
        portrait = "item-grid-video-player--vertical" in block or bool(dims and int(dims[2]) > int(dims[1]))
        base = f"https://assets.mixkit.co/videos/{vid}/{vid}"
        out.append(_hit("mixkit", vid, title or f"Mixkit {vid}", f"{base}-1080.mp4", preview_url=f"{base}-360.mp4",
                        thumb_url=f"{base}-thumb-360-0.jpg", alt_urls=[f"{base}-720.mp4"],
                        width=1080 if portrait else 1920, height=1920 if portrait else 1080, author="Mixkit",
                        page_url=f"https://mixkit.co{href[1]}" if href else "", tags=[]))
    return out


def _search_mixkit(query: str, n: int) -> list:
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    page = _get(f"https://mixkit.co/free-stock-video/{slug}/").decode("utf-8", "replace")
    return _parse_mixkit(page)


# --- Internet Archive ---------------------------------------------------------------------------------------------

def _cc_license(url: str) -> tuple | None:
    """(name, url) for a PD/CC license that allows commercial use and edits, else None."""
    u = (url or "").strip().lower()
    if "creativecommons.org" not in u:
        return None
    m = re.search(r"creativecommons\.org/(licenses|publicdomain)/([a-z0-9.+-]+)(?:/([0-9.]+))?", u)
    if not m:
        return None
    kind, code, ver = m.groups()
    if code in ("publicdomain", "mark") or (kind == "publicdomain" and code != "zero"):
        return "Public Domain", url
    if code == "zero":
        return "CC0", url
    parts = code.split("-")
    if parts[0] != "by" or any(p in ("nc", "nd") for p in parts) or not set(parts) <= {"by", "sa"}:
        return None
    return f"CC {code.upper()}{' ' + ver if ver else ''}", url


def _parse_archive_search(data: dict) -> list:
    """Search docs with an allowed license, as [{identifier, title, license, license_url}]."""
    out = []
    for d in (data.get("response") or {}).get("docs") or []:
        lic = _cc_license(d.get("licenseurl") or "")
        title = d.get("title") if isinstance(d.get("title"), str) else " ".join(d.get("title") or [])
        if lic and d.get("identifier") and not _is_ai(title):
            out.append({"identifier": d["identifier"], "title": title or d["identifier"], "license": lic[0],
                        "license_url": lic[1]})
    return out


def _seconds(v):
    if isinstance(v, str) and ":" in v:
        try:
            s = 0.0
            for part in v.split(":"):
                s = s * 60 + float(part)
            return s
        except ValueError:
            return None
    return _num(v)


def _parse_archive_meta(data: dict, doc: dict | None = None) -> dict | None:
    """Best mp4 (h.264, under ARCHIVE_MAX_BYTES, tallest) of an item as a hit, or None."""
    meta = data.get("metadata") or {}
    ident = meta.get("identifier") or (doc or {}).get("identifier")
    if not ident:
        return None
    subjects = meta.get("subject") or []
    subjects = [s.strip().lower() for s in (subjects if isinstance(subjects, list) else re.split(r"[;,]", subjects))
                if s.strip()]
    if _is_ai(meta.get("title"), meta.get("description"), " ".join(subjects)):
        return None
    lic = _cc_license(meta.get("licenseurl") or "") or (
        (doc["license"], doc["license_url"]) if doc and "licenseurl" not in meta else None)
    if not lic:
        return None
    best, rank = None, None
    for f in data.get("files") or []:
        name, fmt = f.get("name") or "", (f.get("format") or "").lower()
        size = _num(f.get("size")) or 0
        if not name.lower().endswith(".mp4") or size > ARCHIVE_MAX_BYTES:
            continue
        r = ("h.264" in fmt, f.get("source") == "derivative", _num(f.get("height")) or 0, -size)
        if rank is None or r > rank:
            best, rank = f, r
    if not best:
        return None
    creator = meta.get("creator")
    creator = ", ".join(creator) if isinstance(creator, list) else (creator or "")
    title = meta.get("title") if isinstance(meta.get("title"), str) else (doc or {}).get("title", ident)
    w, h = _num(best.get("width")), _num(best.get("height"))
    return _hit("archive", ident, title, f"https://archive.org/download/{ident}/{urllib.parse.quote(best['name'])}",
                thumb_url=f"https://archive.org/services/img/{ident}", duration=_seconds(best.get("length")),
                width=int(w) if w else None, height=int(h) if h else None,
                size=int(_num(best.get("size")) or 0) or None, license=lic[0], license_url=lic[1], author=creator,
                page_url=f"https://archive.org/details/{ident}", tags=subjects,
                attribution_required=lic[0] not in ("Public Domain", "CC0"))


def _search_archive(query: str, n: int) -> list:
    query = re.sub(r"[^\w\s-]+", " ", query).strip()
    q = (f"(title:({query}) OR subject:({query}) OR description:({query})) AND mediatype:movies "
         f"AND collection:({' OR '.join(ARCHIVE_COLLECTIONS)}) "
         f"AND (licenseurl:*creativecommons* OR licenseurl:*publicdomain*)")
    params = urllib.parse.urlencode([("q", q), ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "licenseurl"),
                                     ("fl[]", "downloads"), ("rows", 20), ("output", "json"),
                                     ("sort[]", "downloads desc")])
    docs = _parse_archive_search(_get_json(f"https://archive.org/advancedsearch.php?{params}"))[:max(n * 2, n + 4)]

    def meta(doc):
        try:
            data = _get_json(f"https://archive.org/metadata/{urllib.parse.quote(doc['identifier'])}")
            return _parse_archive_meta(data, doc)
        except (OSError, ValueError):
            return None

    with ThreadPoolExecutor(6) as pool:
        return [h for h in pool.map(meta, docs) if h]


# --- Wikimedia Commons --------------------------------------------------------------------------------------------

def _strip_html(s) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip() if isinstance(s, str) else ""


def _commons_license(code: str, short: str) -> str | None:
    for s in (code or "", short or ""):
        s = s.strip().lower()
        if not s:
            continue
        if re.search(r"(?:^|[\s-])(?:nc|nd)(?:$|[\s-])", s):
            return None
        if (s.startswith(("pd", "public domain", "cc0", "cc-zero", "cc zero"))
                or re.match(r"cc[\s-]by(?:[\s-]sa)?(?:[\s-][\d.]+)?\b", s)):
            return short or code
    return None


def _parse_commons(data: dict) -> list:
    out = []
    pages = sorted(((data.get("query") or {}).get("pages") or {}).values(), key=lambda p: p.get("index", 0))
    for p in pages:
        info = (p.get("videoinfo") or p.get("imageinfo") or [{}])[0]
        if not info.get("url") or not str(info.get("mime", "")).startswith("video/"):
            continue
        original = info["url"].split("?")[0]
        derivs = sorted((d for d in info.get("derivatives") or []
                         if "webm" in (d.get("transcodekey") or "") and (d.get("height") or 0) <= 1080),
                        key=lambda d: d.get("height") or 0, reverse=True)
        best = derivs[0] if derivs else {"src": original, "width": info.get("width"), "height": info.get("height")}
        small = next((d for d in reversed(derivs) if (d.get("height") or 0) >= 360), None)
        meta = {k: (v or {}).get("value") for k, v in (info.get("extmetadata") or {}).items()}
        cats = str(meta.get("Categories") or "")
        title = _strip_html(meta.get("ObjectName")) or re.sub(r"^File:|\.[a-z0-9]+$", "", p.get("title", ""))
        if _is_ai(cats, _strip_html(meta.get("ImageDescription")), title):
            continue
        lic = _commons_license(meta.get("License") or "", meta.get("LicenseShortName") or "")
        if not lic:
            continue
        out.append(_hit("commons", p.get("pageid"), title, best["src"], thumb_url=info.get("thumburl"),
                        preview_url=small["src"] if small else None,
                        alt_urls=[original] if best["src"] != original else [],
                        duration=_num(info.get("duration")), width=best.get("width"), height=best.get("height"),
                        size=info.get("size") if best["src"] == original else
                        int((best.get("bandwidth") or 0) * (_num(info.get("duration")) or 0) / 8) or None,
                        license=lic, license_url=meta.get("LicenseUrl") or "",
                        author=_strip_html(meta.get("Artist")) or _strip_html(meta.get("Credit")),
                        page_url=info.get("descriptionurl") or "",
                        tags=[c.lower() for c in cats.split("|") if c][:15],
                        attribution_required=str(meta.get("AttributionRequired", "")).lower() == "true"))
    return out


def _search_commons(query: str, n: int) -> list:
    params = urllib.parse.urlencode({"action": "query", "generator": "search", "gsrsearch": f"{query} filetype:video",
                                     "gsrnamespace": 6, "prop": "videoinfo", "viurlwidth": 480,
                                     "viprop": "url|size|mime|extmetadata|derivatives", "format": "json",
                                     "gsrlimit": 20})
    return _parse_commons(json.loads(_get(f"https://commons.wikimedia.org/w/api.php?{params}", {"User-Agent": WIKI_UA},
                                          tries=7)))


SEARCHERS = {"mixkit": _search_mixkit, "archive": _search_archive, "commons": _search_commons}
try:
    from . import stock_extra  # more sources that only some copies of the engine carry
except ImportError:
    pass
else:
    SEARCHERS = {**stock_extra.SEARCHERS, **SEARCHERS}
ALL = tuple(SEARCHERS)


# --- Public API ---------------------------------------------------------------------------------------------------

def _keep(h: dict, min_dur, max_dur, portrait) -> bool:
    d = h.get("duration")
    if d is not None:
        if min_dur is not None and d < min_dur:
            return False
        if max_dur is not None and d > max_dur and h["source"] not in LONG_FORM:
            return False
    if portrait is not None and h.get("width") and h.get("height"):
        return (h["height"] > h["width"]) == portrait
    return True


def search(query: str, sources: tuple = ALL, per_source: int = 8, min_dur: float | None = 2.0,
           max_dur: float | None = 60.0, portrait: bool | None = None, notes: list | None = None) -> list:
    """Hits from each source, interleaved in relevance order. A failing source adds a line to notes instead.

    Each hit: {source, id, title, url, preview_url, thumb_url, alt_urls, duration, width, height, size, license,
    license_url, author, page_url, tags, attribution_required}. max_dur skips archive (whole films).
    """
    unknown = [s for s in sources if s not in SEARCHERS]
    if unknown:
        raise ValueError(f"unknown stock source(s): {', '.join(unknown)}; pick from {', '.join(ALL)}")
    notes = notes if notes is not None else []

    def run(src):
        try:
            hits = [h for h in SEARCHERS[src](query, per_source) if _keep(h, min_dur, max_dur, portrait)]
            return hits[:per_source]
        except Exception as e:  # one source failing must not break the others
            notes.append(_scrub(f"{src}: {type(e).__name__}: {e}"))
            return []

    with ThreadPoolExecutor(len(sources) or 1) as pool:
        per = list(pool.map(run, sources))
    for src, hits in zip(sources, per):
        if not hits and not any(n.startswith(f"{src}:") for n in notes):
            notes.append(f"{src}: no matches")
    out, seen = [], set()
    for i in range(max((len(h) for h in per), default=0)):
        for hits in per:
            if i < len(hits) and hits[i]["url"] not in seen:
                seen.add(hits[i]["url"])
                out.append(hits[i])
    return out


def _filename(hit: dict, url: str) -> str:
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    ext = ext if ext in (".mp4", ".webm", ".ogv", ".mov", ".m4v", ".mkv") else ".mp4"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(hit["id"])).strip("._")[:80] or "clip"
    return f"{hit['source']}-{safe}{ext}"


def _write_credits(dest: Path, name: str, hit: dict) -> None:
    path = dest / "credits.json"
    credits = {}
    if path.exists():
        try:
            credits = json.loads(path.read_text())
            if not isinstance(credits, dict):
                raise ValueError
        except ValueError:
            path.with_suffix(".json.corrupt").write_bytes(path.read_bytes())
            credits = {}
    credits[name] = {k: hit.get(k) for k in ("source", "id", "title", "license", "license_url", "author",
                                              "page_url", "url", "attribution_required")}
    path.write_text(json.dumps(credits, indent=2, ensure_ascii=False))


def download(hit: dict, dest_dir, timeout: float = 120) -> Path:
    """Download the hit to <dest_dir>/<source>-<id>.<ext> (skipped if present) and record it in credits.json."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    ua = WIKI_UA if hit["source"] == "commons" else BROWSER_UA
    urls = [hit["url"], *hit.get("alt_urls", [])]
    existing = [dest / _filename(hit, u) for u in urls if (dest / _filename(hit, u)).exists()]
    if existing:
        _write_credits(dest, existing[0].name, hit)
        return existing[0]
    err = None
    for url in urls:
        out = dest / _filename(hit, url)
        part = out.with_name(out.name + ".part")
        try:
            with _open(url, {"User-Agent": ua}, timeout, tries=6 if hit["source"] == "commons" else 3) as r, \
                    open(part, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
        except urllib.error.HTTPError as e:
            part.unlink(missing_ok=True)
            err = e
            if e.code in (403, 404, 410, 429):
                continue
            raise
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        part.rename(out)
        _write_credits(dest, out.name, {**hit, "url": url})
        return out
    raise RuntimeError(f"{hit['source']} {hit['id']}: no downloadable file ({err})")


def contact_sheet(hits: list, out_jpg, cols: int = 4, cell: int = 320) -> Path:
    """Grid of hit thumbnails, each labelled '#n source duration', to pick clips by eye."""
    from PIL import Image, ImageDraw, ImageFont

    ch = cell * 9 // 16

    def thumb(h):
        if not h.get("thumb_url"):
            return None
        try:
            ua = WIKI_UA if h["source"] == "commons" else BROWSER_UA
            im = Image.open(io.BytesIO(_get(h["thumb_url"], {"User-Agent": ua}))).convert("RGB")
            im.thumbnail((cell, ch))
            return im
        except Exception:
            return None

    with ThreadPoolExecutor(8) as pool:
        thumbs = list(pool.map(thumb, hits))
    rows = max(1, -(-len(hits) // cols))
    sheet = Image.new("RGB", (cols * cell, rows * (ch + 24)), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=14)
    except TypeError:
        font = ImageFont.load_default()
    for i, (h, im) in enumerate(zip(hits, thumbs)):
        x, y = (i % cols) * cell, (i // cols) * (ch + 24)
        if im:
            sheet.paste(im, (x + (cell - im.width) // 2, y + (ch - im.height) // 2))
        dur = f" {h['duration']:.0f}s" if h.get("duration") else ""
        draw.text((x + 4, y + ch + 4), f"#{i} {h['source']}{dur} {h['title'][:28]}", fill=(235, 235, 235), font=font)
    out_jpg = Path(out_jpg)
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_jpg, quality=88)
    return out_jpg
