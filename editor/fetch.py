"""Get the user's video from a share link, for when the agent cannot see their files (it runs in the cloud, or the
video is on a phone): a Google Drive or Dropbox link shared as "anyone with the link", or a direct link to the file.
Needs no account or key: only links their owner already opened to anyone are fetched. The file is checked to be a
real video before it is kept.

    python -m editor fetch "<link>" <dir>
"""
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp", ".mts"}
NOT_SHARED = ("This link opens a page, not the video. It is probably not shared with anyone who has the link. In "
              "Google Drive: right-click the video, Share, set General access to \"Anyone with the link\", then Copy "
              "link and send that link again. In Dropbox: Share, \"Anyone with the link\", Copy link.")


class FetchError(RuntimeError):
    """A link that gave no video, with what the user can do about it."""


def drive_id(url: str) -> str | None:
    """The file id of a Google Drive share link (file/d/<id>, open?id=<id>, uc?id=<id>), else None."""
    host = urllib.parse.urlparse(url).netloc.lower()
    if not host.endswith(("drive.google.com", "docs.google.com", "drive.usercontent.google.com")):
        return None
    m = re.search(r"/file/d/([\w-]{10,})", url) or re.search(r"[?&]id=([\w-]{10,})", url)
    return m.group(1) if m else None


def download_url(url: str) -> str:
    """The address that serves the file itself, not its preview page."""
    url = url.strip().strip("<>\"'")
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https"):
        raise FetchError("that is not a web link: send the share link (it starts with https://)")
    host = p.netloc.lower()
    if host.endswith(("drive.google.com", "docs.google.com")) and "/folders/" in p.path:
        raise FetchError("that is a folder link: share the video file itself (right-click the file, Share, Copy link)")
    fid = drive_id(url)
    if fid:
        return f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
    if host.endswith("dropbox.com"):
        q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if k not in ("dl", "raw")] + [("dl", "1")]
        return urllib.parse.urlunparse(p._replace(query=urllib.parse.urlencode(q)))
    return url


def _name(resp, url: str) -> str:
    cd = resp.headers.get("Content-Disposition") or ""
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.I) or re.search(r'filename="?([^";]+)"?', cd, re.I)
    raw = urllib.parse.unquote(m.group(1)) if m else Path(urllib.parse.urlparse(resp.geturl() or url).path).name
    stem, ext = Path(raw).stem, Path(raw).suffix.lower()
    safe = re.sub(r"[^\w.-]+", "_", stem, flags=re.UNICODE).strip("._")[:80] or "video"
    return safe + (ext if ext in VIDEO_EXT else ".mp4")


def has_video(path) -> bool:
    """Whether ffprobe finds a video stream in the file."""
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return p.returncode == 0 and "video" in p.stdout


def _open(url: str, timeout: float = 60):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout)


def fetch(link: str, dest_dir, opener=_open) -> Path:
    """Download the video behind a share link into dest_dir and return its path. Raises FetchError, in words the
    user can act on, when the link gives a page instead of the file or the file is not a video."""
    url = download_url(link)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        resp = opener(url)
    except urllib.error.HTTPError as e:
        raise FetchError(NOT_SHARED if e.code in (401, 403, 404) else f"the link failed ({e.code} {e.reason})")
    except urllib.error.URLError as e:
        raise FetchError(f"could not reach the link ({e.reason})")
    with resp:
        if (resp.headers.get("Content-Type") or "").lower().startswith("text/html"):
            raise FetchError(NOT_SHARED)
        out = dest / _name(resp, url)
        part = out.with_name(out.name + ".part")
        try:
            with open(part, "wb") as f:
                shutil.copyfileobj(resp, f, 1 << 20)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
    if not has_video(part):
        part.unlink(missing_ok=True)
        raise FetchError("the link gave a file, but it is not a video: check that you shared the right file")
    part.replace(out)
    return out


def cmd(a) -> None:
    try:
        print(fetch(a.link, a.dest))
    except FetchError as e:
        raise SystemExit(f"fetch: {e}")
