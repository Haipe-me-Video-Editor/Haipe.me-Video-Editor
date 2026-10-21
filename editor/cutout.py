"""Virtual green screen: cut the speaker out of their background, frame by frame, on the CPU.

Default engine: Robust Video Matting (RVM, mobilenetv3; GPL-3.0 code and weights, downloaded into the cache at run
time, never committed). It is recurrent, so the matte is steady over time, keeps dark clothes solid and drops
furniture far better than MODNet. Then MediaPipe's selfie_multiclass background class gates out what RVM still
half-keeps (a chair's back by the shoulders), and holes enclosed by the silhouette are filled so nothing shows
through a shirt or a pair of glasses. The gate never acts near the head (hair, face, glasses: RVM's own edge keeps
fine hair and thin frames) or on what the hands hold (RVM foreground reachable from the hands: a phone or a
product), see _BackgroundGate. Tested on hair, glasses and held objects. The colour written at the soft edge is
the speaker's own (foreground()), so no rim of the old room comes along onto a new background.
MODNet (Apache-2.0) remains as the fallback (EDITOR_MATTE=modnet). Output: ProRes 4444 with alpha.
"""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from . import color
from .config import CACHE_DIR, FPS

MODEL_URL = "https://huggingface.co/Xenova/modnet/resolve/main/onnx/model.onnx"
MODEL = CACHE_DIR / "models" / "modnet" / "model.onnx"
SHORT_EDGE = 512  # matting resolution; MODNet was trained at 512
SMOOTH = 0.35  # weight of the previous frame's matte (temporal steadiness vs. lag on fast moves)
LOW, HIGH = 0.08, 0.92  # alpha below LOW is background, above HIGH is the speaker


RVM_DIR = CACHE_DIR / "models" / "rvm"
RVM_CODE = "https://raw.githubusercontent.com/PeterL1n/RobustVideoMatting/master/"
RVM_FILES = ["model/__init__.py", "model/model.py", "model/mobilenetv3.py", "model/resnet.py", "model/lraspp.py",
             "model/decoder.py", "model/deep_guided_filter.py", "model/fast_guided_filter.py", "LICENSE"]
RVM_WEIGHTS = "https://huggingface.co/SJTU-TES/RobustVideoMatting/resolve/main/rvm_mobilenetv3.pth"
RVM_SHORT = 270  # RVM's working resolution (short edge): its recommended downsample for 1080p
BG_ON, BG_FULL = 0.55, 0.9  # MediaPipe background confidence where the gate starts / fully removes
HEAD_BAND = 0.03  # around hair, face and accessories the gate stands aside, as a fraction of the width
HOLD_REACH = 0.25  # how far from the hands (walking through RVM's foreground) a held object is kept, of the width
MATTE_VERSION = "rvm4"  # part of every matte cache key: bump when the matte changes


def ensure_rvm() -> Path:
    for f in RVM_FILES:
        dst = RVM_DIR / f
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["curl", "-fsSL", "-o", str(dst), RVM_CODE + f], check=True)
    w = RVM_DIR / "rvm_mobilenetv3.pth"
    if not w.exists():
        part = w.with_suffix(".part")
        subprocess.run(["curl", "-fsSL", "-o", str(part), RVM_WEIGHTS], check=True)
        part.replace(w)
    return RVM_DIR


class _RVM:
    """Robust Video Matting, frame by frame with its recurrent state: full-size alpha 0-1."""

    def __init__(self):
        import torch
        ensure_rvm()
        if str(RVM_DIR) not in sys.path:
            sys.path.insert(0, str(RVM_DIR))
        from model import MattingNetwork  # noqa: E402 (the RVM repository's own package, in the cache)
        self.torch = torch
        torch.set_num_threads(max(1, os.cpu_count() or 1))
        self.net = MattingNetwork("mobilenetv3").eval()
        self.net.load_state_dict(torch.load(RVM_DIR / "rvm_mobilenetv3.pth", map_location="cpu"))
        self.rec = [None] * 4

    def __call__(self, rgb: np.ndarray) -> np.ndarray:
        t = self.torch
        H, W = rgb.shape[:2]
        with t.no_grad():
            x = t.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1)[None].float() / 255
            _, pha, *self.rec = self.net(x, *self.rec, downsample_ratio=min(1.0, RVM_SHORT / min(W, H)))
        return pha[0, 0].numpy()


class _BackgroundGate:
    """1 where MediaPipe is not sure it is background, falling to 0 where it is (smoothed over time), and 1 in two
    protected zones, because the segmenter works at 256 px and calls fine or foreign things background:
    - a band around hair, face and accessories: fine hair and thin glasses frames keep RVM's own edge;
    - what the hands hold: RVM foreground grown from the hands (skin below the chin) through foreground only, up to
      HOLD_REACH of the width. A phone or a product in the hands stays; a chair's back by the shoulders is too far round
      the body to be reached, so it still goes."""

    def __init__(self):
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        from .extras import model_path
        self.mp, self.prev = mp, None  # prev: the six class confidences, smoothed over time
        self.seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(model_path("selfie_multiclass"))),
            output_confidence_masks=True, output_category_mask=False))

    def __call__(self, rgb: np.ndarray, fg: np.ndarray | None = None) -> np.ndarray:
        """rgb: the frame; fg: RVM's alpha for it (0-1, full size), which the held-object zone grows through."""
        import cv2
        H, W = rgb.shape[:2]
        w, h = 288, round(288 * H / W)
        small = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
        res = self.seg.segment(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(small)))
        cm = np.stack([np.squeeze(m.numpy_view()).astype(np.float32) for m in res.confidence_masks])
        self.prev = cm if self.prev is None else 0.6 * self.prev + 0.4 * cm
        gate = 1 - np.clip((cv2.GaussianBlur(self.prev[0], (0, 0), 2) - BG_ON) / (BG_FULL - BG_ON), 0, 1)
        m = None if fg is None else (cv2.resize(fg, (w, h), interpolation=cv2.INTER_AREA) > 0.5).astype(np.uint8)
        gate = np.maximum(gate, protected(self.prev, m))
        return cv2.resize(gate, (W, H), interpolation=cv2.INTER_LINEAR)


def protected(cm: np.ndarray, fg: np.ndarray | None) -> np.ndarray:
    """Where the background gate must stand aside (0-1, at the segmenter's size). cm: MediaPipe's six class
    confidences (background, hair, body skin, face skin, clothes, others); fg: RVM's foreground as 0/1 at the same
    size, or None."""
    import cv2
    _, hair, skin, face, _, other = cm
    w = cm.shape[2]
    zone = np.zeros(cm.shape[1:], np.float32)
    head = ((hair + face + other) > 0.5).astype(np.uint8)
    if head.any():
        k = max(3, int(2 * HEAD_BAND * w)) | 1  # a band HEAD_BAND wide on every side
        zone = cv2.dilate(head, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))).astype(np.float32)
    hands = (skin > 0.5).astype(np.uint8)
    rows = np.where((face > 0.5).any(1))[0]
    if rows.size:  # below the chin only: hands and forearms, never the neck (it would reach the chair)
        hands[:int(rows.max() + 0.35 * (rows.max() - rows.min()))] = 0
    if fg is not None and hands.any():
        held, k3 = hands & fg, np.ones((3, 3), np.uint8)
        for _ in range(int(HOLD_REACH * w)):
            grown = cv2.dilate(held, k3) & fg
            if np.array_equal(grown, held):
                break
            held = grown
        zone = np.maximum(zone, cv2.dilate(held, k3, iterations=2).astype(np.float32))
    return cv2.GaussianBlur(zone, (0, 0), 2)


def fill_holes(alpha: np.ndarray) -> np.ndarray:
    """Everything well inside the silhouette becomes solid: holes (a dark shirt patch, a glasses lens, a black watch
    strap the network drops) and half-transparent patches alike, with no see-through rim left round a filled hole.
    Only the outline keeps the network's soft edge. Inside means far from the room: background reachable from the
    top, left or right edge (the bottom edge counts as inside: the body continues below the frame)."""
    import cv2
    H, W = alpha.shape
    s = 4
    small = cv2.resize(alpha, (W // s, H // s), interpolation=cv2.INTER_AREA)
    solid = (small > 0.5).astype(np.uint8)
    pad = np.pad(solid, ((1, 0), (1, 1)), constant_values=0)  # background border on top, left and right only
    pad = np.pad(pad, ((0, 1), (0, 0)), constant_values=1)
    mask = np.zeros((pad.shape[0] + 2, pad.shape[1] + 2), np.uint8)
    cv2.floodFill(pad, mask, (0, 0), 2)
    room = (pad != 2).astype(np.uint8)  # 0 where the room is, 1 for the person and anything they enclose
    dist = cv2.distanceTransform(room, cv2.DIST_L2, 3)[1:-1, 1:-1] * s  # px from the room, at full scale
    d0, d1 = 0.004 * W, 0.006 * W
    core = np.clip((dist - d0) / d1, 0, 1)
    if core.max() <= 0:
        return alpha
    core = cv2.resize(core.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
    return np.maximum(alpha, core)


def _box(x: np.ndarray, r: int) -> np.ndarray:
    import cv2
    return cv2.blur(x, (2 * r + 1, 2 * r + 1), borderType=cv2.BORDER_REFLECT)


def foreground(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """The speaker's own colour at the soft edge (rgb float 0-1, alpha 0-1, same size). An edge pixel is a mix of
    speaker and room, so a cut-out laid on a new background keeps a rim of the old one (a dark ring round a head
    shot against a dark wall, a blue tint from an LED behind the shoulder). Blur-fusion foreground estimation
    (Forte and Pitie, 2021): local mean speaker and room colours, a large then a small radius, solve the
    compositing equation for the speaker. Only the edge band changes; solid pixels keep the camera's colour."""
    H, W = alpha.shape
    edge = (alpha > 0.01) & (alpha < 0.99)
    if not edge.any():
        return rgb
    a = alpha.astype(np.float32)
    rgb = rgb.astype(np.float32)
    fa, ba_ = rgb * a[..., None], rgb * (1 - a)[..., None]  # speaker and room parts; only the edge of fa changes
    ae, ie = a[edge][:, None], rgb[edge]
    for r in (max(4, W // 24), max(2, W // 360)):
        ma = _box(a, r)[edge][:, None]
        bf = _box(fa, r)[edge] / (ma + 1e-5)
        bb = _box(ba_, r)[edge] / (1 - ma + 1e-5)
        fe = np.clip(bf + ae * (ie - ae * bf - (1 - ae) * bb), 0, 1)
        fa[edge] = fe * ae
    out = rgb.copy()
    out[edge] = fe
    return out


def engine() -> str:
    return os.environ.get("EDITOR_MATTE", "rvm")


def ensure_model() -> Path:
    if not MODEL.exists():
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        part = MODEL.with_suffix(".part")
        subprocess.run(["curl", "-fsSL", "-o", str(part), MODEL_URL], check=True)
        part.replace(MODEL)
    return MODEL


def _session():
    import onnxruntime as ort

    return ort.InferenceSession(str(ensure_model()), providers=["CPUExecutionProvider"])


def matte_size(w: int, h: int) -> tuple[int, int]:
    """Model input size: short edge SHORT_EDGE, both sides multiples of 32."""
    k = SHORT_EDGE / min(w, h)
    return max(32, round(w * k / 32) * 32), max(32, round(h * k / 32) * 32)


def refine(alpha: np.ndarray, prev: np.ndarray | None) -> np.ndarray:
    """Temporal blend, then tighten the edge (levels and a 1px erosion)."""
    if prev is not None:
        alpha = (1 - SMOOTH) * alpha + SMOOTH * prev
    a = np.clip((alpha - LOW) / (HIGH - LOW), 0, 1)
    img = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))
    return np.asarray(img, np.float32) / 255


def glow_ring(alpha: np.ndarray, width: int = 9, blur: float = 5) -> np.ndarray:
    """A soft halo just outside the matte's edge (dilate minus matte, blurred), 0-1."""
    img = Image.fromarray((alpha * 255).astype(np.uint8))
    grown = np.asarray(img.filter(ImageFilter.MaxFilter(width | 1)), np.float32) / 255
    ring = Image.fromarray((np.clip(grown - alpha, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur))
    return np.clip(np.asarray(ring, np.float32) / 255 * 1.8, 0, 1)


def _encoder(out, W: int, H: int):
    return subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-vf", color.RGBA_OUT + ",format=yuva444p10le", "-c:v", "prores_ks",
                             "-profile:v", "4444", "-pix_fmt", "yuva444p10le", *color.TAGS, str(out)],
                            stdin=subprocess.PIPE)


class _Skin:
    """MediaPipe selfie_multiclass: soft mask of bare skin below the face (hands and arms), 0-1 at full size."""

    def __init__(self):
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        from .extras import model_path
        self.mp = mp
        self.seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(model_path("selfie_multiclass"))),
            output_confidence_masks=True, output_category_mask=False))

    def __call__(self, rgb: np.ndarray) -> np.ndarray:
        H, W = rgb.shape[:2]
        res = self.seg.segment(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
        skin = np.squeeze(res.confidence_masks[2].numpy_view())  # 2 = body skin (hands, arms, neck)
        face = np.squeeze(res.confidence_masks[3].numpy_view())  # 3 = face skin
        skin = np.clip((skin - 0.4) / 0.35, 0, 1)  # drop low-confidence haze on clothes
        rows = np.where((face > 0.5).sum(1) > 0)[0]
        if len(rows):  # the neck is not a hand: nothing above the collar passes in front of chest text
            skin[: min(len(skin), rows.max() + int(0.07 * len(skin)))] = 0
        img = Image.fromarray((skin * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
        img = img.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(3))
        return np.clip(np.asarray(img, np.float32) / 255 * 1.3, 0, 1)


def cut_out(src, out, start: float, dur: float, size: tuple, glow: str | None = None, glow_out=None,
            part: str = "person") -> Path:
    """Cut the speaker out of src[start, start+dur] (src is already at the output size) into a clip with alpha.
    With glow (a #rrggbb colour) and glow_out, also write a halo clip that sits around the person.
    part="hands" keeps only bare skin below the face (hands and arms), with MODNet's clean edge: text can then sit
    on the speaker's chest while their fingers pass in front of it (a finance-desk look)."""
    W, H = size
    mw, mh = matte_size(W, H)
    rvm = _RVM() if engine() == "rvm" else None
    gate = _BackgroundGate() if rvm else None
    sess = None if rvm else _session()
    skin = _Skin() if part == "hands" else None
    name = None if rvm else sess.get_inputs()[0].name
    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
                            "-vf", f"fps={FPS},{color.RGB_IN},format=rgb24", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = _encoder(out, W, H)
    genc = _encoder(glow_out, W, H) if glow and glow_out else None
    tint = np.array([int(glow[i:i + 2], 16) for i in (1, 3, 5)], np.uint8) if genc else None
    prev, frame_bytes = None, W * H * 3
    try:
        while True:
            buf = dec.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            rgb = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            if rvm:
                fg = np.clip((rvm(rgb) - 0.03) / 0.94, 0, 1)
                a = fill_holes(fg * gate(rgb, fg))
                prev = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((mw, mh), Image.BILINEAR),
                                  np.float32) / 255
                alpha = Image.fromarray((a * 255).astype(np.uint8))
            else:
                x = np.asarray(Image.fromarray(rgb).resize((mw, mh), Image.BILINEAR), np.float32) / 127.5 - 1
                raw = sess.run(None, {name: x.transpose(2, 0, 1)[None]})[0][0, 0]
                prev = refine(raw, prev)
                alpha = Image.fromarray((prev * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
            if skin is not None:
                alpha = (np.asarray(alpha, np.float32) * skin(rgb)).astype(np.uint8)
            alpha = np.asarray(alpha)
            fg_rgb = (foreground(rgb.astype(np.float32) / 255, alpha.astype(np.float32) / 255) * 255 + 0.5)
            enc.stdin.write(np.dstack([fg_rgb.astype(np.uint8), alpha]).tobytes())
            if genc:
                ring = Image.fromarray((glow_ring(prev) * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
                genc.stdin.write(np.dstack([np.broadcast_to(tint, (H, W, 3)), np.asarray(ring)]).tobytes())
    finally:
        for e in (enc, genc):
            if e:
                e.stdin.close()
                e.wait()
        dec.stdout.close()
        dec.wait()
    if enc.returncode or dec.returncode or (genc and genc.returncode):
        raise RuntimeError(f"cutout of {src} at {start:.2f}s failed")
    return Path(out)


def placement(head: tuple | None, size: tuple) -> dict:
    """Scale and position for the cut-out so the head lands in the band under the desk panel.

    head is the (top, bottom) head band as fractions of the height, or None (a typical selfie is assumed).
    """
    from .graphics.desk import HEAD_HEIGHT, HEAD_TOP

    W, H = size
    top, bottom = head or (0.10, 0.60)
    s = min(0.85, max(0.45, HEAD_HEIGHT / max(bottom - top, 0.05)))
    w, h = int(round(W * s / 2)) * 2, int(round(H * s / 2)) * 2
    return {"w": w, "h": h, "x": (W - w) // 2, "y": int(round(HEAD_TOP * H - top * h))}

