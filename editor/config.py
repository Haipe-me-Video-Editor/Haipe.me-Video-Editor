"""Paths to external tools and project-wide constants. Override tool paths with env vars."""
import os
import shutil
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "graphics"
STYLES_DIR = PACKAGE_DIR / "styles"
BRANDS_DIR = Path(os.environ.get("EDITOR_BRANDS", PACKAGE_DIR.parent / "brands"))  # private brand packs
FONT_CACHE = Path(os.environ.get("EDITOR_FONT_CACHE", Path.home() / ".cache" / "claude-video-editor" / "fonts"))

FPS = 30
# Every RGB layer (graphics, overlays, cut-outs) goes to YUV with the BT.709 matrix before it is laid on the picture.
# Left to ffmpeg, the conversion uses BT.601 (a deep plum came out visibly off its colour), and an RGBA overlay with
# format=auto turns the whole picture to RGB, which clips saturated footage (a violet wall went lighter and greyer).
TO_YUV = "scale=out_color_matrix=bt709:out_range=tv,format=yuva420p"
FORMATS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}


def vertical_size(value: str | None) -> tuple:
    """The 9:16 output size: EDITOR_SIZE (e.g. "1440x2560", 2K from a 4K source) or the 1080x1920 default. Every
    effect, graphic and caption scales from it."""
    if not value:
        return FORMATS["9:16"]
    w, h = (int(v) for v in value.lower().split("x"))
    if w % 2 or h % 2 or w * 16 != h * 9:
        raise ValueError(f"EDITOR_SIZE must be an even 9:16 size like 1440x2560, not {value!r}")
    return w, h


FORMATS["9:16"] = vertical_size(os.environ.get("EDITOR_SIZE"))
FINAL_CRF = int(os.environ.get("EDITOR_CRF", "20"))  # x264 CRF of the final encode; 15 for a high-quality master

# Which edition this copy is. The repo is the internal engine; scripts/publish_public.py writes "public" into the
# public copy, where a finished video stays on the user's computer unless they ask for a link, and the first-run
# interview is offered. Nothing else differs.
EDITION = "public"


class MissingTool(RuntimeError):
    pass


def ffmpeg_bin() -> str:
    path = os.environ.get("EDITOR_FFMPEG") or shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
    except ImportError as e:
        raise MissingTool("ffmpeg not found. Install ffmpeg or `pip install imageio-ffmpeg`.") from e
    return imageio_ffmpeg.get_ffmpeg_exe()


def ffprobe_bin() -> str:
    path = os.environ.get("EDITOR_FFPROBE") or shutil.which("ffprobe")
    if not path:
        raise MissingTool("ffprobe not found. Install ffmpeg; it ships ffprobe.")
    return path


ROOT_DIR = PACKAGE_DIR.parent
CACHE_DIR = Path(os.environ.get("EDITOR_CACHE", Path.home() / ".cache" / "claude-video-editor"))
STUDIO_PYTHON = Path(os.environ.get("EDITOR_STUDIO_PYTHON", CACHE_DIR / "venv-re" / "bin" / "python"))
HF_CLI = ROOT_DIR / "vendor" / "hf" / "node_modules" / ".bin" / "hyperframes"
GSAP_JS = ROOT_DIR / "vendor" / "hf" / "node_modules" / "gsap" / "dist" / "gsap.min.js"
# A headless Chrome already on the machine (a cloud container's Playwright install). Anywhere else HyperFrames uses
# the one scripts/setup.sh fetched with `hyperframes browser ensure` into its own cache.
HEADLESS_SHELL = os.environ.get(
    "EDITOR_HEADLESS_SHELL", "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell")


def hf_env() -> dict:
    """Environment for HyperFrames: local render only, no telemetry, local tools."""
    env = dict(os.environ)
    env.update(HYPERFRAMES_NO_TELEMETRY="1", DO_NOT_TRACK="1", HYPERFRAMES_NO_UPDATE_CHECK="1",
               HYPERFRAMES_SKIP_SKILLS="1", HYPERFRAMES_FFMPEG_PATH=ffmpeg_bin(), HYPERFRAMES_FFPROBE_PATH=ffprobe_bin())
    if Path(HEADLESS_SHELL).exists():
        env["PRODUCER_HEADLESS_SHELL_PATH"] = HEADLESS_SHELL
    env.pop("HYPERFRAMES_API_KEY", None)
    return env
