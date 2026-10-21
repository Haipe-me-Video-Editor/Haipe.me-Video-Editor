"""Tight sentence-to-sentence cut and per-shot reframing for talking-head reels (the tight-cut standard).

- Speech is measured at 10 ms (energy VAD on the source). Every pause of LONG or more is cut to a join PRE before
  the next word and POST after the last one; shorter breaths inside a sentence stay. Short pauses that end a
  sentence are cut too, when named (`cut_pauses`): read the candidates `pause_report` lists against the transcript.
- Hiss endings ("س", "ص") fall under the energy threshold, so each out point is extended while the 3 kHz+ band is
  still above its noise floor (up to 0.3 s), unless capped (`tail_caps`, e.g. when the speaker looks down right after).
- Your own take cuts (`keep_cuts`) are kept as cut points.
- Each shot is reframed from face tracking to the reference: face FACE_W of the frame width, hair top HEADROOM below
  the frame top, face centred at FACE_X. Shots alternate with one PUNCH tighter, so every jump cut reads as a punch-in.
- `TimeMap.M(src_seconds)` maps a source time to the timeline: plan graphics, B-roll and sound in source seconds.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

from .config import ffmpeg_bin

LONG, PRE, POST = 0.45, 0.05, 0.10
MERGE_GAP = 0.22  # VAD runs closer than this are one phrase (breaths inside words and phrases)
FACE_W, HEADROOM, FACE_X, PUNCH = 0.255, 0.09, 0.48, 1.14
MAX_ZOOM = 2.2
HF_TAIL_MAX, HF_ON_DB = 0.30, 8.0
END_HOLD = 0.3  # after the last word, before the end card


def _pcm(src, af: str) -> np.ndarray:
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(src), "-ac", "1", "-ar", "16000", "-af", af,
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def _db(x: np.ndarray, hop: int = 160) -> np.ndarray:
    n = len(x) // hop
    return 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)


def speech_phrases(src) -> list:
    """[[start, end], ...] in seconds: speech runs at 10 ms, with gaps under MERGE_GAP merged."""
    e = _db(_pcm(src, "highpass=f=120,lowpass=f=4000"))
    return phrases_from_energy(e)


def phrases_from_energy(e: np.ndarray) -> list:
    on = e > np.percentile(e, 90) - 22
    n = len(on)
    for i in range(1, n - 3):  # close 1-3 frame dropouts inside words
        if not on[i] and on[i - 1] and on[i + 1:i + 4].any():
            on[i] = True
    runs, i = [], 0
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]:
                j += 1
            runs.append([i / 100, j / 100])
            i = j
        else:
            i += 1
    if not runs:
        return []
    merged = [runs[0]]
    for a, b in runs[1:]:
        if a - merged[-1][1] < MERGE_GAP:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [[round(a, 2), round(b, 2)] for a, b in merged if b - a >= 0.12]


def hf_track(src) -> np.ndarray:
    """10 ms dB of the source's 3 kHz+ band (where hiss endings live)."""
    return _db(_pcm(src, "highpass=f=3000"))


def hf_tail(hf: np.ndarray, t: float) -> float:
    """Seconds the high band stays above its noise floor after t (plus 40 ms), capped at HF_TAIL_MAX."""
    on = np.percentile(hf, 10) + HF_ON_DB
    i = j = int(round(t * 100))
    while j < i + int(HF_TAIL_MAX * 100) and j < len(hf) and hf[j] > on:
        j += 1
    return min(HF_TAIL_MAX, (j - i) / 100 + (0.04 if j > i else 0.0))


def cut_spans(phrases: list, start: float, end: float, keep_cuts=(), cut_pauses=(), hf=None, tail_caps=None,
              end_hold: float = END_HOLD) -> tuple[list, dict]:
    """Kept [in, out] spans in source seconds, and {nominal out: extended out} for out points moved by hiss tails."""
    phrases = [p for p in phrases if p[1] > start and p[0] < end]
    if not phrases:
        return [], {}
    tail_caps = tail_caps or {}
    groups = [list(phrases[0])]
    for a, b in phrases[1:]:
        sentence_end = any(abs(groups[-1][1] - c) < 0.05 for c in cut_pauses)
        if a - groups[-1][1] < LONG and not sentence_end:
            groups[-1][1] = b
        else:
            groups.append([a, b])
    spans = [[max(start, a - PRE), min(end, b + POST)] for a, b in groups]
    spans[0][0] = start
    nominal = {}
    if hf is not None:
        for sp in spans:
            ext = round(min(end, sp[1] + min(hf_tail(hf, sp[1]), tail_caps.get(round(sp[1], 2), 1.0))), 3)
            if ext > sp[1] + 0.005:
                nominal[round(sp[1], 2)] = ext
            sp[1] = ext
    spans[-1][1] = min(end, spans[-1][1] + end_hold)
    out = []
    for a, b in spans:  # split at your own cuts (they sit in pauses, so this only adds cut points)
        edges = [a] + [c for c in keep_cuts if a < c < b] + [b]
        out += [[round(x, 3), round(y, 3)] for x, y in zip(edges, edges[1:]) if y - x > 0.05]
    return out, nominal


def pause_report(phrases: list, words: list, start: float, end: float) -> list:
    """Kept pauses (MERGE_GAP..LONG) with the words around them, to decide which ones end a sentence.
    words: [[start, end, text], ...]."""
    rows = []
    for (a0, b0), (a1, _) in zip(phrases, phrases[1:]):
        gap = a1 - b0
        if start < b0 < end and MERGE_GAP <= gap < LONG:
            before = " ".join(w[2].strip() for w in words if b0 - 1.2 < w[1] <= b0 + 0.05)
            after = " ".join(w[2].strip() for w in words if a1 - 0.05 <= w[0] < a1 + 1.0)
            rows.append({"at": b0, "gap": round(gap, 2), "before": before, "after": after})
    return rows


def framing_track(src, fps: int = 5) -> list:
    """[{t, fw, cx, top, chin}] as fractions of the source frame: face width and centre (face landmarker), hair top
    (selfie segmenter's hair class). Rows without a face carry only t."""
    import mediapipe as mp
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core.base_options import BaseOptions

    from . import ffmpeg
    from .extras import model_path
    info = ffmpeg.probe(src)
    W = 270
    H = round(info["height"] * W / info["width"] / 2) * 2
    fl = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path("face_landmarker")))))
    seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
        base_options=BaseOptions(model_asset_path=str(model_path("selfie_multiclass"))), output_category_mask=True))
    p = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-i", str(src), "-vf", f"fps={fps},scale={W}:{H}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    rows, i = [], 0
    while True:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        img = np.frombuffer(b, np.uint8).reshape(H, W, 3)
        mi = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img))
        r = fl.detect(mi)
        row = {"t": round(i / fps, 2)}
        if r.face_landmarks:
            L = r.face_landmarks[0]
            xs = [q.x for q in L]
            cat = np.squeeze(seg.segment(mi).category_mask.numpy_view())
            hair = np.where((cat == 1).any(1))[0]
            row.update(fw=round(max(xs) - min(xs), 4), cx=round((min(xs) + max(xs)) / 2, 4),
                       top=round(hair.min() / H if len(hair) else min(q.y for q in L) - 0.04, 4),
                       chin=round(L[152].y, 4))
        rows.append(row)
        i += 1
    p.wait()
    return rows


def frame_shot(rows: list, a: float, b: float, tight: bool, face_w=FACE_W, headroom=HEADROOM, face_x=FACE_X,
               punch=PUNCH) -> tuple[float, list]:
    """Zoom and focus [x, y] for the shot [a, b] from the face rows (medians over the shot)."""
    good = [r for r in rows if r.get("fw", 0) > 0.15]
    sel = [r for r in good if a <= r["t"] <= b] or ([min(good, key=lambda r: abs(r["t"] - (a + b) / 2))] if good else [])
    if not sel:
        return 1.0, [0.5, 0.5]
    fw = float(np.median([r["fw"] for r in sel]))
    cx = float(np.median([r["cx"] for r in sel]))
    top = float(np.median([r["top"] for r in sel]))
    z = min(MAX_ZOOM, max(1.0, face_w / fw)) * (punch if tight else 1.0)
    fy = top - headroom / z + 0.5 / z
    fx = cx + (0.5 - face_x) / z
    lo, hi = 0.5 / z, 1 - 0.5 / z
    return round(z, 3), [round(min(max(fx, lo), hi), 3), round(min(max(fy, lo), hi), 3)]


class TimeMap:
    """Source seconds -> timeline seconds for a list of kept spans."""

    def __init__(self, spans: list, nominal: dict | None = None):
        self.rows, t = [], 0.0
        for a, b in spans:
            self.rows.append((a, b, t))
            t += b - a
        self.total = t
        self.nominal = {float(k): v for k, v in (nominal or {}).items()}

    def M(self, s: float) -> float:
        """A time inside a removed pause maps to the next kept frame; a nominal out point to its extended one."""
        s = self.nominal.get(round(s, 2), s)
        for a, b, t0 in self.rows:
            if s < a:
                return round(t0, 3)
            if s <= b:
                return round(t0 + s - a, 3)
        return round(self.total, 3)

    @classmethod
    def load(cls, project) -> "TimeMap":
        d = json.loads((Path(project) / "work" / "tightcut.json").read_text())
        return cls(d["spans"], d.get("nominal"))


def build(project, src: str, start: float, end: float, keep_cuts=(), cut_pauses=(), tail_caps=None,
          words=None, framing=True) -> dict:
    """Run the whole step for project/src and write work/tightcut.json. Returns that record."""
    project = Path(project)
    work = project / "work"
    work.mkdir(exist_ok=True)
    path = project / src
    phrases = speech_phrases(path)
    spans, nominal = cut_spans(phrases, start, end, keep_cuts, cut_pauses, hf_track(path), tail_caps)
    rows = []
    if framing:
        fpath = work / "framing.json"
        if fpath.exists() and json.loads(fpath.read_text()).get("src") == src:
            rows = json.loads(fpath.read_text())["rows"]
        else:
            rows = framing_track(path)
            fpath.write_text(json.dumps({"src": src, "rows": rows}))
    segments = []
    for i, (a, b) in enumerate(spans):
        seg = {"src": src, "in": a, "out": b}
        if rows:
            z, focus = frame_shot(rows, a, b, tight=bool(i % 2))
            seg.update(zoom=z, focus=focus)
        segments.append(seg)
    rec = {"src": src, "start": start, "end": end, "phrases": phrases, "spans": spans,
           "nominal": {str(k): v for k, v in nominal.items()}, "segments": segments,
           "pauses": pause_report(phrases, words or [], start, end)}
    (work / "tightcut.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    return rec
