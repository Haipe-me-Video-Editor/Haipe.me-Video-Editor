"""Beauty pass on top of the face retouch (approved on stills before use): a sheer lip
tint, a fine lash line on the upper lids, and a slight slimming. All minimal; nothing may read as edited.
Slimming is a horizontal remap only (x' depends on x alone), so every vertical line behind the person stays straight.

    python -m editor.beauty still frame.png ...        # before|after jpgs beside each frame, for approval
    python -m editor.beauty video in.mov out.mov keep  # keep: a text file of ffmpeg between(t,a,b) ranges
"""
import re
import subprocess
import sys

import cv2
import numpy as np

from .retouch import CHEEKS, LIPS, Smoother, landmarker, landmarks, retouch_frame
INNER_LIPS = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95]
UPPER_LID = {"r": [33, 246, 161, 160, 159, 158, 157, 173, 133], "l": [263, 466, 388, 387, 386, 385, 384, 398, 362]}
LIP = (5.5, 1.2, -2.5)    # LAB shift at full mask: a* (rose), b* (a touch warm), L (a touch deeper)
LASH = 0.55               # how much the lash line darkens
SLIM = 0.05               # 5% narrower across her body and face

def _mask(shape, pts, blur):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(pts).astype(np.int32)], 255)
    return cv2.GaussianBlur(m, (0, 0), blur).astype(np.float32) / 255

def makeup(bgr, P, lip=1.0, lash=1.0):
    if P is None:
        return bgr
    H, W = bgr.shape[:2]
    fw = float(np.linalg.norm(P[CHEEKS[0]] - P[CHEEKS[1]]))
    x0, y0 = np.maximum(P.min(0) - 0.1 * fw, 0).astype(int)
    x1, y1 = np.minimum(P.max(0) + 0.1 * fw, (W, H)).astype(int)
    Q = P - (x0, y0)
    crop = bgr[y0:y1, x0:x1].astype(np.float32) / 255
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    shape = lab.shape[:2]
    if lip:
        m = np.clip(_mask(shape, Q[LIPS], fw * 0.005) - _mask(shape, Q[INNER_LIPS], fw * 0.004), 0, 1) * lip
        lab[..., 1] += m * LIP[0]; lab[..., 2] += m * LIP[1]; lab[..., 0] += m * LIP[2]
    if lash:
        m = np.zeros(shape, np.float32)
        for k in ("r", "l"):
            pts = Q[UPPER_LID[k]].copy()
            ew = float(np.linalg.norm(pts[0] - pts[-1]))
            pts[:, 1] -= ew * 0.02                       # sits on the lash roots, just above the lid edge
            th = max(1, int(round(ew * 0.055)))
            cv2.polylines(m, [np.round(pts).astype(np.int32)], False, 1.0, th, cv2.LINE_AA)
        m = cv2.GaussianBlur(m, (0, 0), 0.7) * LASH * lash
        lab[..., 0] *= (1 - m)
    out = np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2BGR) * 255 + 0.5, 0, 255).astype(np.uint8)
    res = bgr.copy(); res[y0:y1, x0:x1] = out
    return res

_maps = {}
def slim(bgr, cx, k=SLIM):
    """x' = cx + (x-cx)(1+k) across her (|x-cx| < R1), easing back to no change by R2: she is k narrower."""
    H, W = bgr.shape[:2]
    key = (int(round(cx)), W, H, k)
    if key not in _maps:
        R1, R2 = 0.30 * W, 0.50 * W
        x = np.arange(W, dtype=np.float32); d = x - key[0]; ad = np.abs(d)
        u = np.clip((ad - R1) / (R2 - R1), 0, 1); ease = 1 - u * u * (3 - 2 * u)
        disp = np.where(ad < R1, k * d, np.sign(d) * k * R1 * ease)
        mx = np.tile((x + disp)[None], (H, 1)).astype(np.float32)
        my = np.tile(np.arange(H, dtype=np.float32)[:, None], (1, W))
        _maps.clear(); _maps[key] = (mx, my)
    mx, my = _maps[key]
    return cv2.remap(bgr, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)

def beauty(bgr, P, cx):
    out = retouch_frame(bgr, P, 0.85, 0.9, 0.5) if P is not None else bgr
    out = makeup(out, P)
    return slim(out, cx)

def _still(paths):
    lm = landmarker(video=False)
    for p in paths:
        bgr = cv2.imread(p); P = landmarks(lm, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        cx = float(P[1][0]) if P is not None else bgr.shape[1] / 2
        out = beauty(bgr, P, cx)
        fx0, fy0 = (P.min(0) - 60).astype(int); fx1, fy1 = (P.max(0) + 60).astype(int)
        a = cv2.resize(bgr[fy0:fy1, fx0:fx1], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        b = cv2.resize(out[fy0:fy1, fx0:fx1], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        cv2.imwrite(p.replace(".png", "-face.jpg"), np.hstack([a, b]))
        cv2.imwrite(p.replace(".png", "-full.jpg"), np.hstack([bgr, out])[::2, ::2])
        print(p, "face", P is not None)

def ranges_from_keep(path):
    return [(float(a), float(b)) for a, b in re.findall(r"between\(t,([\d.]+),([\d.]+)\)", open(path).read())]

def video(src, dst, keep):
    """Two passes over the kept ranges of `src` (black elsewhere passes through): landmarks first, so the slimming
    centre can be smoothed over time with no lag, then the beauty pass. Writes a same-length master."""
    W, H, FPS = 1080, 1920, 30000 / 1001
    rng = ranges_from_keep(keep)
    inside = lambda t: any(a - 0.02 <= t <= b + 0.02 for a, b in rng)
    def frames():
        pr = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                              stdout=subprocess.PIPE)
        i = 0
        while True:
            b = pr.stdout.read(W * H * 3)
            if len(b) < W * H * 3: break
            yield i, np.frombuffer(b, np.uint8).reshape(H, W, 3)
            i += 1
    # pass 1: landmarks on kept frames, smoothed within each range (a cut resets the smoother)
    lm, sm, P_of, last_in = landmarker(video=True), Smoother(), {}, False
    for i, f in frames():
        t = i / FPS
        if not inside(t):
            last_in = False; continue
        if not last_in: sm = Smoother()
        last_in = True
        P_of[i] = sm.update(landmarks(lm, cv2.cvtColor(f, cv2.COLOR_BGR2RGB), int(t * 1000)))
    # the slimming centre: her nose x, filled across misses and smoothed (sigma ~0.5 s) within each range
    cx = {}
    for a, b in rng:
        idx = [i for i in P_of if a - 0.02 <= i / FPS <= b + 0.02]
        if not idx: continue
        xs = np.array([P_of[i][1][0] if P_of[i] is not None else np.nan for i in idx], np.float64)
        if np.isnan(xs).all(): xs[:] = W / 2
        good = ~np.isnan(xs); xs = np.interp(np.arange(len(xs)), np.flatnonzero(good), xs[good])
        k = np.exp(-0.5 * (np.arange(-45, 46) / 15.0) ** 2); k /= k.sum()
        sm_x = np.convolve(np.pad(xs, 45, mode="edge"), k, mode="valid")
        cx.update(dict(zip(idx, sm_x)))
    print("landmarks", len(P_of), "faces", sum(p is not None for p in P_of.values()), flush=True)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", "30000/1001", "-i", "-", "-i", src, "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
                            "-preset", "slow", "-crf", "8", "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
                            "-color_trc", "bt709", "-colorspace", "bt709", "-c:a", "copy", dst], stdin=subprocess.PIPE)
    for i, f in frames():
        enc.stdin.write((beauty(f, P_of[i], cx[i]) if i in P_of else f).tobytes())
    enc.stdin.close(); enc.wait()
    print("done", dst)

if __name__ == "__main__":
    if sys.argv[1] == "still":
        _still(sys.argv[2:])
    elif sys.argv[1] == "video":
        video(sys.argv[2], sys.argv[3], sys.argv[4])
