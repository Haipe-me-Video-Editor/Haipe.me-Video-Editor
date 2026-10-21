"""Voice clean-up and enhancement, tuned by ear on real recordings.

The default is "E3", chosen in A/B listening on phone recordings.
- Hum and whine: narrow notches remove the mains hum (50/100 Hz; set 60/120 for 60 Hz countries) and a fixed appliance whine (~1.6 kHz, e.g. an air conditioner).
- Noise: RNNoise (arnndn, a neural speech denoiser) plus a spectral pass that tracks steady room noise.
- Tone: gentle EQ for warmth and clarity, an exciter that restores the brightness a phone mic loses, and
  soft 1.7:1 compression.

A heavier chain (full RNNoise, spectral pass, de-esser) gates the room too hard and sounds over-processed. Every value can be overridden per voice (a style's "voice" object).
"""
import os
import subprocess
from pathlib import Path

from .config import CACHE_DIR, PACKAGE_DIR, STUDIO_PYTHON

RNNOISE_URL = "https://raw.githubusercontent.com/richardpl/arnndn-models/master/std.rnnn"
RNNOISE = CACHE_DIR / "models" / "rnnoise" / "std.rnnn"

DEFAULT = {
    "highpass": 70,            # Hz, 2-pole: rumble below the voice
    "notches": [50, 100, 1615],  # Hz: mains hum and its harmonic, a fixed appliance whine
    "denoise": 0.9,            # RNNoise mix, 0 (off) to 1 (full)
    "residual_nr": 18,         # dB of spectral reduction on steady noise left over; 0 turns it off
    "warmth_db": 1.0,          # at 160 Hz
    "mud_db": -1.0,            # at 350 Hz: boxy room sound
    "presence_db": 2.0,        # at 3.2 kHz: clarity
    "exciter": 1.5,            # harmonics above 3.5 kHz; 0 turns it off
    "deess": 0,                # 0-1
    "comp_ratio": 1.7,         # gentle; 1 turns compression off
    "comp_threshold_db": -20,
}


def ensure_model():
    if not RNNOISE.exists():
        RNNOISE.parent.mkdir(parents=True, exist_ok=True)
        part = RNNOISE.with_suffix(".part")
        subprocess.run(["curl", "-fsSL", "-o", str(part), RNNOISE_URL], check=True)
        part.replace(RNNOISE)
    return RNNOISE


def chain(settings: dict | None = None, model=None) -> str:
    """The ffmpeg audio filter chain for a voice, as one comma-joined string."""
    v = {**DEFAULT, **(settings or {})}
    parts = ["aresample=48000"]  # RNNoise is trained at 48 kHz
    if v["highpass"]:
        parts.append(f"highpass=f={v['highpass']}:p=2")
    parts += [f"bandreject=f={f}:t=q:w={12 if f > 500 else 8}" for f in v["notches"] or []]
    if v["denoise"]:
        parts.append(f"arnndn=m={model or ensure_model()}:mix={v['denoise']}")
    if v["residual_nr"]:
        parts.append(f"afftdn=nr={v['residual_nr']}:nf=-55:tn=1")
    if v["warmth_db"]:
        parts.append(f"equalizer=f=160:t=q:w=1:g={v['warmth_db']}")
    if v["mud_db"]:
        parts.append(f"equalizer=f=350:t=q:w=1.5:g={v['mud_db']}")
    if v["presence_db"]:
        parts.append(f"equalizer=f=3200:t=q:w=1.2:g={v['presence_db']}")
    if v["exciter"]:
        parts.append(f"aexciter=level_in=1:level_out=1:amount={v['exciter']}:drive=6:blend=0:freq=3500:ceil=16000")
    if v["deess"]:
        parts.append(f"deesser=i={v['deess']}")
    if v["comp_ratio"] and v["comp_ratio"] > 1:
        parts.append(f"acompressor=threshold={v['comp_threshold_db']}dB:ratio={v['comp_ratio']}:attack=20:release=250")
    return ",".join(parts)


# After the studio restore: light mic tone (warmth, less box, de-essed), gentle 2:1 compression, -14 LUFS for social.
STUDIO_POST = ("highpass=f=70:p=2,equalizer=f=120:t=q:w=0.9:g=1.5,equalizer=f=300:t=q:w=1.2:g=-1.5,deesser=i=0.3,"
               "acompressor=threshold=-22dB:ratio=2:attack=8:release=150:makeup=1,alimiter=limit=0.84:level=false")
STUDIO_LUFS = -14


def studio_restore(src, out_wav, workdir) -> Path:
    """The studio pick: Resemble Enhance (AI denoise + studio restoration), then STUDIO_POST and
    loudness. CPU: about 8 s per second of audio. src is any audio or video file; out_wav is 48 kHz mono."""
    if not STUDIO_PYTHON.exists():
        raise RuntimeError("studio voice venv missing; run scripts/setup.sh")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    raw, restored = workdir / "voice_in48.wav", workdir / "voice_restored.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "48000",
                    "-c:a", "pcm_s16le", str(raw)], check=True)
    p = subprocess.run([str(STUDIO_PYTHON), "-I", str(PACKAGE_DIR / "voice_studio.py"), "--wav", str(raw),
                        "--out", str(restored)], capture_output=True, text=True,
                       env={**os.environ, "HF_HUB_DISABLE_XET": "1"})
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-800:])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(restored), "-af",
                    f"{STUDIO_POST},aresample=48000,loudnorm=I={STUDIO_LUFS}:TP=-1.5:LRA=9", "-ar", "48000", "-ac", "1",
                    str(out_wav)], check=True)
    return Path(out_wav)


def mux(video, wav, out) -> Path:
    """Video stream copied untouched; the new voice as 256 kb/s AAC."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(wav), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", str(out)],
                   check=True)
    return Path(out)
