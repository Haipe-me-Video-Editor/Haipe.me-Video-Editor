"""Deliver finished videos to the user.

Nothing is uploaded unless asked (`--upload` or EDITOR_UPLOAD=gofile). `gofile()` uploads to Gofile and returns a
download page that anyone holding the link can open. Gofile pages have a Download button that
works on phones (on iOS: Download → Files → Share → Save Video). Chat attachments stop at 30 MB. Also send the file in chat when it fits under 30 MB.

Optional, needs setup: `upload()` puts the file into your Google Drive (the folder set in the script).

Uses your own Apps Script web app (scripts/drive-upload.gs): it returns a one-time resumable upload
link, and the file goes straight to Google with it. Needs the environment variables DRIVE_UPLOAD_URL and
DRIVE_UPLOAD_KEY. Never print or log them.
"""
import json
import os
import subprocess
from pathlib import Path


def configured() -> bool:
    return bool(os.environ.get("DRIVE_UPLOAD_URL") and os.environ.get("DRIVE_UPLOAD_KEY"))


def upload(path, name: str | None = None, mime: str = "video/mp4") -> dict:
    """Upload path; return Google's file record ({id, name, webViewLink})."""
    if not configured():
        raise RuntimeError("Drive delivery isn't set up: add DRIVE_UPLOAD_URL and DRIVE_UPLOAD_KEY "
                           "(see scripts/drive-upload.gs)")
    path = Path(path)
    body = json.dumps({"key": os.environ["DRIVE_UPLOAD_KEY"], "name": name or path.name, "mimeType": mime,
                       "size": path.stat().st_size})
    # Apps Script answers a POST with a 302 to its result page; curl -L fetches that with GET, as it should.
    r = subprocess.run(["curl", "-sS", "-L", "-H", "Content-Type: application/json",
                        "--data-binary", "@-", os.environ["DRIVE_UPLOAD_URL"]],
                       input=body, capture_output=True, text=True, check=True)
    session = json.loads(r.stdout)
    if not session.get("uploadUrl"):
        raise RuntimeError(f"Drive refused the upload session (status {session.get('status')}, "
                           f"error {session.get('error')})")
    r = subprocess.run(["curl", "-sS", "-X", "PUT", "-H", f"Content-Type: {mime}", "--upload-file", str(path),
                        session["uploadUrl"]], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def gofile(path) -> str:
    """Upload to Gofile; return the download page URL. The page is public to anyone with the link."""
    r = subprocess.run(["curl", "-sS", "-m", "60", "https://api.gofile.io/servers"], capture_output=True, text=True,
                       check=True)
    server = json.loads(r.stdout)["data"]["servers"][0]["name"]
    r = subprocess.run(["curl", "-sS", "-m", "3600", "-F", f"file=@{path}",
                        f"https://{server}.gofile.io/contents/uploadfile"], capture_output=True, text=True, check=True)
    data = json.loads(r.stdout)
    if data.get("status") != "ok":
        raise RuntimeError(f"Gofile upload failed: {data.get('status')}")
    return data["data"]["downloadPage"]

