"""Shared plumbing for the fx pack: frames in and out, the person matte, face landmarks, HyperFrames layers and
layer stacking. An effect only decides what to draw; everything here is frame-exact and cached per window."""
import contextlib
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from .. import cutout, ffmpeg, fonts, quality
from ..config import GSAP_JS, ROOT_DIR
from ..graphics.render import RENDER_ARGS, _hf, check_output
from ..graphics.spring import SPRING_TAG

# Families every fx page can use by name (CSS font-family), plus BrandLT / BrandAR from the style.
FONT_FAMILIES = {"Sora": "Sora", "Montserrat": "Montserrat", "Anton": "Anton", "BebasNeue": "Bebas Neue",
                 "Tajawal": "Tajawal", "TajawalMedium": "Tajawal Medium", "PlexArabic": "IBM Plex Sans Arabic",
                 "PlexMono": "IBM Plex Mono", "Orbitron": "Orbitron", "Lalezar": "Lalezar"}
# Faces loaded only by the pages that name them (the serif looks), so the effects above never wait on them.
EXTRA_FAMILIES = {"InstrumentSerif": "Instrument Serif", "InstrumentItalic": "Instrument Serif Italic",
                  "AmiriSerif": "Amiri", "SoraThin": "Sora ExtraLight"}  # never a generic name (serif, ...)


class Ctx:
    """One effect window. `src` is the window as its own clip (size and fps of the output, frame-exact), `out` the
    clip the effect must write (same size, fps and frame count, opaque). `spec` is the edit.json entry."""

    def __init__(self, src, out, spec: dict, style: dict, work, size=(1080, 1920), fps: float = 30, project=None):
        self.src, self.out, self.spec, self.style = Path(src), Path(out), spec, style
        self.work = Path(work)
        self.work.mkdir(parents=True, exist_ok=True)
        self.size, self.fps = tuple(size), fps
        self.W, self.H = self.size
        self.dur = float(spec["dur"])
        self.n = int(round(self.dur * fps))
        self.project = Path(project) if project else None

    # ---- parameters -------------------------------------------------------------------------------------------
    def param(self, key, default=None):
        return self.spec.get(key, default)

    def asset(self, rel) -> Path:
        """A file named in the spec (a screenshot, a logo), relative to the project, the repo or absolute."""
        p = Path(rel)
        for base in ([self.project] if self.project else []) + [ROOT_DIR, Path.cwd()]:
            if not p.is_absolute() and (base / p).exists():
                return (base / p).resolve()
        if p.exists():
            return p.resolve()
        raise FileNotFoundError(f"{self.spec.get('type')}: asset {rel} not found")

    # ---- frames -----------------------------------------------------------------------------------------------
    def frames(self, path=None, rgba: bool = False):
        """RGB (or RGBA) uint8 frames of `path` (default the window), exactly self.n of them."""
        path = Path(path or self.src)
        fmt, ch = ("rgba", 4) if rgba else ("rgb24", 3)
        p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", str(path), "-vf",
                              f"fps={self.fps},scale={self.W}:{self.H},format={fmt}", "-frames:v", str(self.n),
                              "-f", "rawvideo", "-pix_fmt", fmt, "-"], stdout=subprocess.PIPE)
        size = self.W * self.H * ch
        last = None
        try:
            for _ in range(self.n):
                buf = p.stdout.read(size)
                if len(buf) < size:  # a clip a frame short repeats its last frame rather than shifting the cut
                    if last is None:
                        raise RuntimeError(f"{path} gave no frames")
                    yield last
                    continue
                last = np.frombuffer(buf, np.uint8).reshape(self.H, self.W, ch)
                yield last
        finally:
            p.stdout.close()
            p.wait()

    @contextlib.contextmanager
    def writer(self, out=None, alpha: bool = False):
        """with ctx.writer() as w: w(frame) — RGB to an H.264 clip (self.out by default), or RGBA to ProRes 4444."""
        out = Path(out or self.out)
        fmt = "rgba" if alpha else "rgb24"
        codec = (["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"] if alpha else
                 ["-c:v", "libx264", *quality.inter(), "-pix_fmt", "yuv420p"])
        p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", fmt, "-s",
                              f"{self.W}x{self.H}", "-r", str(self.fps), "-i", "-", *codec, str(out)],
                             stdin=subprocess.PIPE)
        count = [0]

        def write(frame):
            p.stdin.write(np.ascontiguousarray(frame, np.uint8).tobytes())
            count[0] += 1
        try:
            yield write
        finally:
            p.stdin.close()
            p.wait()
        if p.returncode:
            raise RuntimeError(f"encoding {out} failed")
        if count[0] != self.n:
            raise RuntimeError(f"{self.spec.get('type')}: wrote {count[0]} frames, the window has {self.n}")

    # ---- the person -------------------------------------------------------------------------------------------
    def person(self, part: str = "person") -> Path:
        """The speaker cut out of the window (MODNet, temporally smoothed): ProRes 4444 with alpha. Cached by the
        window's pixels in a folder shared by every window of the run (hard links: a matte is ~250 MB), so a
        change to an effect's text or code never pays for MODNet (~0.5 s a frame) again."""
        out = self.work / f"cut-{part}.mov"
        if out.exists():
            return out
        h = hashlib.sha1(f"{cutout.MATTE_VERSION}:{cutout.engine()}:{part}:{self.W}x{self.H}@{self.fps}:{self.n}".encode())
        with open(self.src, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        shared = self.work.parent / "_person" / f"{h.hexdigest()[:20]}.mov"
        if not shared.exists():
            shared.parent.mkdir(parents=True, exist_ok=True)
            tmp = shared.with_suffix(".part.mov")
            cutout.cut_out(self.src, tmp, 0, self.dur, self.size, part=part)
            tmp.replace(shared)
        _link(shared, out)
        return out

    def mattes(self, part: str = "person"):
        """Per-frame person alpha as float32 (H, W) in 0..1."""
        for f in self.frames(self.person(part), rgba=True):
            yield f[..., 3].astype(np.float32) / 255

    def landmarks(self, every: int = 1) -> list:
        """Per-frame face landmarks ((478, 2) pixel arrays, or None), from MediaPipe in video mode, smoothed."""
        cache = self.work / f"landmarks-{every}.npz"
        if cache.exists():
            d = np.load(cache, allow_pickle=True)
            return list(d["L"])
        import cv2

        from ..retouch import Smoother, landmarker, landmarks
        lm, smooth, out = landmarker(True), Smoother(), []
        for i, f in enumerate(self.frames()):
            if i % every:
                out.append(out[-1] if out else None)
                continue
            out.append(smooth.update(landmarks(lm, f, int(i * 1000 / self.fps))))
        np.savez(cache, L=np.array(out, dtype=object))
        _ = cv2
        return out

    def face(self) -> dict:
        """Median face over the window: centre (cx, cy), width fw and eye line y, in pixels (or a typical framing)."""
        pts = [p for p in self.landmarks(every=3) if p is not None]
        if not pts:
            return {"cx": self.W / 2, "cy": self.H * 0.33, "fw": self.W * 0.38, "eye_y": self.H * 0.3, "top": self.H * 0.15}
        P = np.median(np.stack(pts), axis=0)
        return {"cx": float(P[:, 0].mean()), "cy": float(P[:, 1].mean()), "fw": float(np.linalg.norm(P[454] - P[234])),
                "eye_y": float(P[[33, 263], 1].mean()), "top": float(P[10, 1])}

    # ---- HyperFrames layers -----------------------------------------------------------------------------------
    def page(self, body: str, css: str = "", js: str = "", bg: str = "transparent") -> str:
        """A full HyperFrames page at the window's size and duration. `js` builds on `tl` (a paused GSAP timeline)
        and may use springIn(tl, targets, from, to, preset, at) with presets gentle / snappy / bouncy."""
        latin, arabic = self.style.get("font", "Sora"), self.style.get("arabic_font", "IBM Plex Sans Arabic")
        used = {k: v for k, v in EXTRA_FAMILIES.items() if f'"{k}"' in body + css + js or f"'{k}'" in body + css + js}
        faces = {**FONT_FAMILIES, **used, "BrandLT": latin, "BrandAR": arabic}
        ff = "".join(f'@font-face{{font-family:"{k}";src:url("{_font_file(v)}");font-weight:100 900}}'
                     for k, v in faces.items())
        d = round(self.dur, 3)
        loads = ", ".join(f"document.fonts.load('700 40px \"{k}\"')" for k in faces)
        checks = " && ".join(f"document.fonts.check('700 40px \"{k}\"')" for k in faces)
        return f"""<!doctype html>
<html><head><meta charset="UTF-8"><script src="gsap.min.js"></script>{SPRING_TAG}
<style>{ff}
html,body{{margin:0;background:{bg}}}
#root{{position:relative;width:{self.W}px;height:{self.H}px;overflow:hidden;font-family:"BrandLT",sans-serif;
  color:{self.style.get('ink', '#fff')}}}
.clip{{position:absolute;inset:0}}
{css}</style></head><body>
<div id="root" data-composition-id="fx" data-start="0" data-width="{self.W}" data-height="{self.H}" data-duration="{d}">
<section class="clip" data-start="0" data-duration="{d}">{body}</section></div>
<script>
Promise.all([{loads}]).then(() => {{
  if (!({checks})) throw new Error("fx fonts did not load");
  const tl = gsap.timeline({{paused: true}});
  {js}
  window.__timelines["fx"] = tl;
}});
</script></body></html>
"""

    def layer(self, page: str, name: str, assets: dict | None = None) -> Path:
        """Render a page (from self.page) to a transparent ProRes clip; `assets` maps file names used in the page
        to local paths. Cached by content, so re-renders with unchanged text are free."""
        assets = {k: Path(v) for k, v in (assets or {}).items()}
        h = hashlib.sha1(page.encode())
        for k, v in sorted(assets.items()):
            h.update(k.encode())
            h.update(v.read_bytes())
        clip = self.work / f"{name}-{h.hexdigest()[:12]}.mov"
        if clip.exists():
            return clip
        comp = clip.with_suffix(".hf")
        comp.mkdir(parents=True, exist_ok=True)
        shutil.copy2(GSAP_JS, comp / GSAP_JS.name)
        extra = {v for k, v in EXTRA_FAMILIES.items() if f'font-family:"{k}"' in page or f"'{k}'" in page}
        for fam in set(FONT_FAMILIES.values()) | extra | {self.style.get("font", "Sora"),
                                                          self.style.get("arabic_font", "IBM Plex Sans Arabic")}:
            f = fonts.ensure_font(fam)
            shutil.copy2(f, comp / f.name)
        for k, v in assets.items():
            shutil.copy2(v, comp / k)
        (comp / "index.html").write_text(page, encoding="utf-8")
        part = clip.with_suffix(".part.mov")
        _hf(["lint", "."], comp)
        _hf(["render", ".", *RENDER_ARGS, "-o", str(part)], comp)
        check_output(part, self.dur)
        part.replace(clip)
        return clip

    # ---- composition ------------------------------------------------------------------------------------------
    def stack(self, layers: list, out=None) -> Path:
        """Overlay clips in order (the first is the opaque bottom; later ones carry alpha) into an opaque clip of
        exactly self.n frames. A layer may be a path or (path, x, y) to place it."""
        out = Path(out or self.out)
        args, chain = [], []
        for i, lay in enumerate(layers):
            path, x, y = (lay, 0, 0) if isinstance(lay, (str, Path)) else lay
            args += ["-i", str(path)]
            chain.append(f"[{i}:v]fps={self.fps},setpts=PTS-STARTPTS{',format=yuva444p' if i else ''}[l{i}]")
        cur = "l0"
        for i, lay in enumerate(layers[1:], 1):
            x, y = (0, 0) if isinstance(lay, (str, Path)) else lay[1:]
            chain.append(f"[{cur}][l{i}]overlay={x}:{y}:eof_action=repeat:format=auto[s{i}]")
            cur = f"s{i}"
        chain.append(f"[{cur}]scale={self.W}:{self.H},format=yuv420p[v]")
        ffmpeg.run([*args, "-filter_complex", ";".join(chain), "-map", "[v]", "-frames:v", str(self.n),
                    "-c:v", "libx264", *quality.inter(), "-r", str(self.fps), out])
        return out


def _link(src: Path, dst: Path) -> None:
    import os
    try:
        if dst.exists():
            dst.unlink()
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _font_file(family: str) -> str:
    return fonts.ensure_font(family).name


def spec_key(spec: dict, module) -> str:
    """Cache key of a rendered window: the spec plus the effect's own source code."""
    here = Path(__file__).parent
    src = Path(module.__file__).read_bytes() + b"".join(p.read_bytes() for p in sorted(here.glob("_*.py")))
    src += Path(__file__).read_bytes() + Path(cutout.__file__).read_bytes()
    return hashlib.sha1(json.dumps(spec, sort_keys=True).encode() + src).hexdigest()[:16]
