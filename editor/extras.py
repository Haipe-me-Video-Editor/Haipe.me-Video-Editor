"""Free effect libraries and models, installed once per container and checked by `doctor`.

Models (downloaded to the cache, never committed; all free for commercial use):
- birefnet: BiRefNet lite (MIT), high-quality person / object cut-outs for stickers, clones, text behind people.
- rife: RIFE frame interpolation (MIT), smooth slow motion from 30 fps phone clips.
- esrgan: Real-ESRGAN general x4v3 (BSD-3), sharp punch-in zooms and upscales.
- MediaPipe (Apache-2.0): selfie_multiclass (hair / face / body / clothes masks, for relighting), face, pose and
  hand landmarkers (effects that follow a person), via the `mediapipe` Python package.
Browser libraries (vendor/hf/node_modules, used by HyperFrames compositions): gl-transitions (MIT, ~80 GLSL
transitions), lottie-web (MIT, Lottie animations), three (MIT, 3D titles and particles), gsap.
ffmpeg already has vidstab (stabilisation), minterpolate, tmix, lagfun, chromashift, xfade and zoompan; frei0r
plugins (apt) add more. Sound effects: a Mixkit pack (`ensure_sfx`, about 330 files with an index).
Speed on this CPU: BiRefNet ~20-30 s a frame at 1024 (stills, stickers, freeze frames; use MODNet or MediaPipe
for moving video), RIFE ~0.25 s a 448p frame pair, Real-ESRGAN ~0.5 s per 128 px tile (fixed 128x128 input).
`python -m editor extras` installs everything; `python -m editor doctor` checks every piece.
"""
import html
import json
import re
import subprocess
from pathlib import Path

from .config import CACHE_DIR, ROOT_DIR

MODELS_DIR = CACHE_DIR / "models"
HF = "https://huggingface.co"
MP = "https://storage.googleapis.com/mediapipe-models"
MODELS = {
    "birefnet": (f"{HF}/onnx-community/BiRefNet_lite-ONNX/resolve/main/onnx/model.onnx", "birefnet_lite.onnx"),
    "rife": (f"{HF}/SOR2171/RIFE-ONNX/resolve/main/rife2_26h.onnx", "rife.onnx"),
    "esrgan": (f"{HF}/tamnvcc/Real-ESRGAN-General-x4v3_float/resolve/main/onnx/model.onnx", "realesr_general_x4v3.onnx"),
    "selfie_multiclass": (f"{MP}/image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite",
                          "selfie_multiclass_256x256.tflite"),
    "face_landmarker": (f"{MP}/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
                        "face_landmarker.task"),
    "pose_landmarker": (f"{MP}/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
                        "pose_landmarker_full.task"),
    "hand_landmarker": (f"{MP}/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
                        "hand_landmarker.task"),
}
NPM = {"gl-transitions": "1.71.0", "lottie-web": "5.13.0", "three": "0.186.1"}  # pinned: versions weeks old
NODE_MODULES = ROOT_DIR / "vendor" / "hf" / "node_modules"


def model_path(name: str) -> Path:
    """The model's file, downloaded first if setup has not fetched it yet (a skipped or interrupted setup)."""
    path = MODELS_DIR / MODELS[name][1]
    return path if path.exists() else ensure_model(name)


def ensure_model(name: str) -> Path:
    url, file = MODELS[name]
    path = MODELS_DIR / file
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(".part")
        subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(part), url], check=True)
        part.replace(path)
    return path


SFX_DIR = CACHE_DIR / "sfx" / "mixkit"
# Mixkit sound effects (Mixkit Sound Effects Free License: free in videos, no attribution; not for resale as
# sound files). Kept quiet in edits (sfx_volume); the engine's synthesised effects stay the default.
SFX_CATEGORIES = ("whoosh", "transition", "swoosh", "impact", "pop", "camera", "glitch", "click", "magic", "cinematic")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"


def _sfx_listing(page: str) -> list:
    """[(id, title, preview_url)] from a Mixkit sound-effects category page."""
    out = []
    for chunk in page.split('class="item-grid__item"')[1:]:
        url = re.search(r'data-audio-player-preview-url-value="(https://assets\.mixkit\.co/[^"]+\.mp3)"', chunk)
        title = re.search(r'item-grid-card__title[^>]*>(.*?)<', chunk, re.S)
        if url:
            sid = re.search(r"/sfx/(\d+)/", url.group(1)).group(1)
            out.append((sid, html.unescape(title.group(1)).strip() if title else sid, url.group(1)))
    return out


def ensure_sfx() -> dict:
    """Download the Mixkit effects in SFX_CATEGORIES (about 20 each) and write an index; returns the index."""
    index_path = SFX_DIR / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    for cat in SFX_CATEGORIES:
        if index.get(cat):
            continue
        page = subprocess.run(["curl", "-fsSL", "-A", UA, f"https://mixkit.co/free-sound-effects/{cat}/"],
                              capture_output=True, text=True).stdout
        items = []
        for sid, title, url in _sfx_listing(page):
            path = SFX_DIR / cat / f"{sid}.mp3"
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                if subprocess.run(["curl", "-fsSL", "-A", UA, "-o", str(path), url]).returncode:
                    continue
            items.append({"id": sid, "title": title, "file": str(path.relative_to(SFX_DIR))})
        if items:
            index[cat] = items
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=1, ensure_ascii=False))
    return index


def ensure_all() -> list:
    """Download every model and install the browser libraries; returns what was set up."""
    done = [str(ensure_model(n)) for n in MODELS]
    done += [f"sfx:{cat}:{len(v)}" for cat, v in ensure_sfx().items()]
    missing = [f"{p}@{v}" for p, v in NPM.items() if not (NODE_MODULES / p / "package.json").exists()]
    if missing:
        subprocess.run(["npm", "install", "--prefix", str(ROOT_DIR / "vendor" / "hf"), "--no-audit", "--no-fund",
                        "--silent", *missing], check=True)
    return done + [f"npm:{p}" for p in NPM]


def doctor() -> dict:
    """Load every model and library once and report ok / the error, so a broken install shows up before an edit."""
    import numpy as np
    report = {}

    def check(name, fn):
        try:
            report[name] = fn() or "ok"
        except Exception as e:  # report every failure, keep checking the rest
            report[name] = f"FAIL: {type(e).__name__}: {e}"

    def onnx(name):
        import onnxruntime as ort
        s = ort.InferenceSession(str(model_path(name)), providers=["CPUExecutionProvider"])
        return "ok " + ", ".join(f"{i.name}{i.shape}" for i in s.get_inputs())

    for n in [k for k, (_, f) in MODELS.items() if f.endswith(".onnx")]:
        check(n, lambda n=n: onnx(n))

    def mediapipe_models():
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((256, 256, 3), np.uint8))
        vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(model_path("selfie_multiclass"))),
            output_category_mask=True)).segment(img)
        vision.FaceLandmarker.create_from_model_path(str(model_path("face_landmarker"))).detect(img)
        vision.PoseLandmarker.create_from_model_path(str(model_path("pose_landmarker"))).detect(img)
        vision.HandLandmarker.create_from_model_path(str(model_path("hand_landmarker"))).detect(img)
        return f"ok mediapipe {mp.__version__}"

    check("mediapipe", mediapipe_models)
    for p in (*NPM, "gsap"):
        check(f"npm:{p}", lambda p=p: "ok" if (NODE_MODULES / p / "package.json").exists() else "FAIL: not installed")

    def ffmpeg_filters():
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        need = ["vidstabdetect", "vidstabtransform", "minterpolate", "tmix", "lagfun", "chromashift", "xfade", "zoompan"]
        missing = [f for f in need if f" {f} " not in out]
        return "ok" if not missing else f"FAIL: missing {missing}"

    check("ffmpeg filters", ffmpeg_filters)

    def sfx():
        index = json.loads((SFX_DIR / "index.json").read_text())
        n = sum(len(v) for v in index.values())
        return f"ok {n} effects in {len(index)} categories" if n else "FAIL: no effects"

    check("sfx", sfx)
    return report
