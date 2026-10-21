"""Styles: JSON design tokens. A name is looked up in editor/styles/ (the built-in, neutral styles), then in the
brands folder (`brands/<name>/style.json`, or EDITOR_BRANDS: your own brand packs, kept outside the engine).
A path to a .json file works too."""
import json
from pathlib import Path

from .config import BRANDS_DIR, STYLES_DIR

PATH_FIELDS = ("logo",)  # file fields a style may set, relative to the style file


def style_path(name: str) -> Path:
    """The JSON file for a style name or path."""
    p = Path(name)
    if p.suffix.lower() == ".json":
        return p
    for cand in (STYLES_DIR / f"{name}.json", BRANDS_DIR / name / "style.json"):
        if cand.exists():
            return cand
    raise FileNotFoundError(f"no style {name!r} in {STYLES_DIR} or {BRANDS_DIR}/{name}/style.json")


def load_style(name: str = "default") -> dict:
    """`name` is a built-in style, a brand pack's style, or a path to a .json file. Relative file fields (logo)
    resolve against the style file's own folder, so the style works from any working directory."""
    p = style_path(name)
    style = json.loads(p.read_text(encoding="utf-8"))
    for field in PATH_FIELDS:
        if style.get(field) and not Path(style[field]).is_absolute():
            style[field] = str((p.resolve().parent / style[field]).resolve())
    return style


def brands() -> list:
    """Names of the installed brand packs."""
    return sorted(p.parent.name for p in BRANDS_DIR.glob("*/style.json")) if BRANDS_DIR.is_dir() else []
