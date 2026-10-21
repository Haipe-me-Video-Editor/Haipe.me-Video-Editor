"""Render a graphic with HyperFrames (local headless Chromium) to a transparent MOV."""
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

from .. import ffmpeg, fonts
from ..config import GSAP_JS, HF_CLI, ROOT_DIR, hf_env
from .composition import composition_html
from .kit import KIT_FONTS, KIT_TYPES, kit_html

RENDER_ARGS = ["--format", "mov"]  # ProRes 4444 with alpha; see docs/hyperframes-notes.md
REMOTE = re.compile(r"""(?:\bsrc\s*=|\bsrcset\s*=|\bhref\s*=|url\(|@import|\bfrom|\bimport\s*\(|\bfetch\s*\()"""
                    r"""\s*["'`]?\s*https?://""", re.IGNORECASE)
CHECKED_EXTS = (".html", ".htm", ".css", ".js", ".mjs", ".svg")


def _hf(args: list, cwd: Path) -> None:
    p = subprocess.run([str(HF_CLI), *args], cwd=cwd, env=hf_env(), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"hyperframes {' '.join(args)} failed:\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")


def check_local(comp: Path) -> None:
    """Refuse a composition that loads anything over the network (GSAP, fonts and images must be local files)."""
    for f in sorted(comp.rglob("*")):
        if f.suffix.lower() in CHECKED_EXTS and f.is_file():
            m = REMOTE.search(f.read_text(encoding="utf-8", errors="replace"))
            if m:
                raise ValueError(f"{f.relative_to(comp)} loads {m.group(0)!r}...: custom graphics must use local "
                                 "files only (vendor GSAP, fonts and images into the folder)")


def _render_kit(spec: dict, style: dict, size: tuple, out_path: Path, project) -> Path:
    """Kit graphics are cached by content: the page (and logo) hash names the clip under work/gfx/, so an unchanged
    graphic is never rendered twice, even when the plan inserts or reorders graphics. Returns the cached clip."""
    # a style can swap a face (e.g. "latin": "Roboto Black") or add one under a new key ("thin": "Sora ExtraLight")
    files = {key: fonts.ensure_font(family) for key, family in {**KIT_FONTS, **style.get("kit_fonts", {})}.items()}
    logo = None
    src = spec.get("logo") or spec.get("src") or (style.get("logo") if spec["type"] == "endcard" else None)
    if src:
        src = Path(src) if Path(src).is_absolute() else (Path(project) / src if project and (Path(project) / src).exists() else ROOT_DIR / src)
        logo = "logo" + src.suffix
    page = kit_html(spec, style, size, {k: f.name for k, f in files.items()}, logo)
    h = hashlib.sha1(page.encode())
    if logo:
        h.update(src.read_bytes())
    clip = out_path.parent / "gfx" / f"{spec['type']}-{h.hexdigest()[:16]}.mov"
    if clip.exists():
        return clip
    comp = clip.with_suffix(".hf")
    comp.mkdir(parents=True, exist_ok=True)
    for f in files.values():
        shutil.copy2(f, comp / f.name)
    shutil.copy2(GSAP_JS, comp / GSAP_JS.name)
    if logo:
        shutil.copy2(src, comp / logo)
    (comp / "index.html").write_text(page, encoding="utf-8")
    part = clip.with_suffix(".part.mov")
    _hf(["lint", "."], comp)
    _hf(["render", ".", *RENDER_ARGS, "-o", str(part)], comp)
    check_output(part, spec["dur"])
    part.replace(clip)
    return clip


def render_graphic(spec: dict, style: dict, size: tuple, out_path, project=None) -> Path:
    out_path = Path(out_path).resolve()
    if spec["type"] in KIT_TYPES:
        return _render_kit(spec, style, size, out_path, project)
    if spec["type"] == "custom":
        comp = Path(spec["dir"])
        comp = (Path(project) / comp if project and not comp.is_absolute() else comp).resolve()
        check_local(comp)
    else:
        comp = out_path.with_suffix(".hf")
        comp.mkdir(parents=True, exist_ok=True)
        latin, arabic = fonts.ensure_font(style["font"]), fonts.ensure_font(style["arabic_font"])
        for f in (latin, arabic, GSAP_JS):
            shutil.copy2(f, comp / f.name)
        logo = None
        if spec["type"] == "outro":
            if not style.get("logo"):
                raise ValueError(f"style {style.get('name')!r} has no 'logo'; the outro card needs one")
            src = ROOT_DIR / style["logo"]
            logo = "logo" + src.suffix
            shutil.copy2(src, comp / logo)
        (comp / "index.html").write_text(
            composition_html(spec, style, size, {"latin": latin.name, "arabic": arabic.name}, logo), encoding="utf-8")
    _hf(["lint", "."], comp)
    _hf(["render", ".", *RENDER_ARGS, "-o", str(out_path)], comp)
    check_output(out_path, spec["dur"])
    return out_path


def check_output(out_path: Path, dur: float) -> None:
    info = ffmpeg.probe(out_path)
    pix = info["pix_fmt"] or ""
    if "a" not in pix[:5]:
        raise RuntimeError(f"{out_path.name} has no alpha channel (pix_fmt {pix}); check RENDER_ARGS")
    if abs(info["duration"] - dur) > 0.1:
        raise RuntimeError(f"{out_path.name} is {info['duration']:.2f}s but the graphic is {dur}s; "
                           "check the composition's data-duration")
