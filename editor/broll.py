"""B-roll library: index once, Claude tags from contact sheets, then text search, no image tokens."""
import json
import re
from pathlib import Path

from . import ffmpeg

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MEDIA_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"} | IMAGE_EXTS

STOPWORDS = {"a", "an", "the", "on", "at", "in", "of", "to", "and", "or", "with", "for", "is", "it", "my", "our", "your", "this", "that", "from", "by", "في", "على", "من", "إلى", "و", "مع"}


def _words(text: str) -> set:
    words = set(re.findall(r"[a-z0-9ء-ٟٮ-ۓ]+", text.lower()))  # Arabic letters + marks only
    return words - STOPWORDS


def index_clips(broll_dir, index_path) -> list:
    broll_dir, index_path = Path(broll_dir), Path(index_path)
    old = {}
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text())
            if isinstance(data, list):
                old = {e["file"]: e for e in data if isinstance(e, dict) and isinstance(e.get("file"), str)}
            else:
                # Not a list: back it up before overwriting
                corrupt_path = index_path.with_suffix(index_path.suffix + ".corrupt")
                corrupt_path.write_bytes(index_path.read_bytes())
        except (json.JSONDecodeError, ValueError):
            # Invalid JSON: back it up before overwriting
            corrupt_path = index_path.with_suffix(index_path.suffix + ".corrupt")
            corrupt_path.write_bytes(index_path.read_bytes())

    entries = []
    for p in sorted(broll_dir.rglob("*")):
        rel = p.relative_to(broll_dir)
        if p.suffix.lower() not in MEDIA_EXTS or any(part.startswith(".") for part in rel.parts):
            continue
        if str(rel) in old:
            entries.append(old[str(rel)])
            continue
        info = ffmpeg.probe(p)
        image = p.suffix.lower() in IMAGE_EXTS
        entries.append({"file": str(rel), "kind": "image" if image else "video",
                        "duration": None if image else info["duration"],
                        "orientation": "portrait" if (info["height"] or 0) > (info["width"] or 0) else "landscape",
                        "tags": [], "subject": "", "mood": "", "setting": ""})
    index_path.write_text(json.dumps(entries, indent=2))
    return entries


def tag(index_path, file: str, tags: list, subject: str = "", mood: str = "", setting: str = "") -> dict:
    index_path = Path(index_path)
    entries = json.loads(index_path.read_text())
    try:
        entry = next(e for e in entries if e["file"] == file)
    except StopIteration:
        raise ValueError(f"{file} is not in the B-roll index; run index_clips first")
    entry.update(tags=[t.strip().lower() for t in tags if t.strip()], subject=subject, mood=mood, setting=setting)
    index_path.write_text(json.dumps(entries, indent=2))
    return entry


def search(index: list, query: str, n: int = 3, min_dur: float = 0.0) -> list:
    q = _words(query)
    scored = []
    for e in index:
        if not e["tags"] and not e["subject"]:
            continue
        if e["kind"] == "video" and (e["duration"] or 0) < min_dur:
            continue
        hay = _words(" ".join(e["tags"]) + f" {e['subject']} {e['mood']} {e['setting']}")
        hits = len(q & hay)
        if hits:
            scored.append((hits, e["kind"] == "video", e))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [e for *_, e in scored[:n]]


def resolve(plan: dict, index: list, broll_dir) -> list:
    notes = []
    used = {b["resolved"] for b in plan["broll"] if b.get("resolved")}
    for b in plan["broll"]:
        if b.get("resolved"):
            continue
        for e in search(index, b["query"], n=10, min_dur=b["dur"]):
            path = str((Path(broll_dir) / e["file"]).resolve())
            if path not in used:
                b["resolved"], b["src_in"] = path, b.get("src_in") or 0.0
                used.add(path)
                if is_ai(path):
                    notes.append(f"AI-generated B-roll at {b['at']:.1f}s ({Path(path).name}): no real footage had it.")
                break
        else:
            b["resolved"] = None
            notes.append(f'No B-roll matched "{b["query"]}" at {b["at"]:.1f}s; that moment stays on camera.')
    return notes


def is_ai(path) -> bool:
    """Whether a B-roll file was generated (its folder's credits.json says source ai)."""
    p = Path(path)
    try:
        credits = json.loads((p.parent / "credits.json").read_text())
    except (OSError, ValueError):
        return False
    return isinstance(credits, dict) and (credits.get(p.name) or {}).get("source") == "ai"
