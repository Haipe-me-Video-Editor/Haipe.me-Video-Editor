"""The creator profile: what the first-run interview learned about the person this editor works for (who they are,
their audience, their look, their pacing, what never to do). One Markdown file outside the repo, so a `git pull` or a
fresh clone never touches it, read before every edit. The interview itself is in docs/interview.md of the public
copy (public/docs/interview.md in the internal repo)."""
import os
import shutil
from pathlib import Path

from . import config

PROFILE = Path(os.environ.get("EDITOR_PROFILE", Path.home() / ".config" / "claude-video-editor" / "profile.md"))
INTERVIEW = Path(__file__).resolve().parent.parent / "docs" / "interview.md"  # public/docs/interview.md here


def load(path=None) -> str | None:
    """The profile's text, or None when there is none yet (or it is empty)."""
    p = Path(path or PROFILE)
    text = p.read_text(encoding="utf-8").strip() if p.is_file() else ""
    return text or None


def note(path=None, edition: str | None = None) -> str:
    """One line for the start of a job: where the profile is, or (public edition) that the interview has not been
    done. The internal edition never asks for an interview: its brand skills carry each client's look."""
    p = Path(path or PROFILE)
    if load(p):
        return f"profile: {p} (read it before planning)"
    if (edition or config.EDITION) == "internal":
        return ""
    return f"note: no creator profile yet. Offer the short interview in {INTERVIEW} before planning."


def snapshot(proj, path=None) -> Path | None:
    """Copy the profile into the project (profile.md), so a job keeps the answers it was edited with."""
    p = Path(path or PROFILE)
    if not load(p):
        return None
    dst = Path(proj) / "profile.md"
    shutil.copy2(p, dst)
    return dst
