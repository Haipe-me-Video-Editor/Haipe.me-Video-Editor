"""Sound made in code for animated films: a score and effects synthesised from a cue list, no samples, no voice.
Every cue is deterministic (seeded noise), so the same sound.json always gives the same file.

    {"seed": 7, "reverb": 0.25, "cues": [
      {"type": "pad", "at": 0, "dur": 15, "notes": ["A3", "E4", "C5"], "gain": -18},
      {"type": "arp", "at": "s2", "dur": 8, "notes": ["A4", "C5", "E5"], "bpm": 96, "voice": "pluck", "gain": -16},
      {"type": "whoosh", "at": "s3-0.4", "dur": 0.8, "pan": 0.3, "gain": -10},
      {"type": "chime", "at": "s3+0.2", "note": "E6", "gain": -12}]}

`at` is seconds, or a shot id from shots.json with an optional offset ("s3", "s3+0.2", "s3-0.4"). `gain` is dB,
`pan` -1 (left) to 1 (right). The types are in CUES.
"""
import re
from pathlib import Path

import numpy as np

SR = 48000
NOTE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d)$")
SEMITONE = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
AT = re.compile(r"^\s*([A-Za-z][\w-]*)\s*(?:([+-])\s*([\d.]+))?\s*$")


def freq(note) -> float:
    """Hz for a note name ("A4" = 440, "C#5", "Eb3") or a number already in Hz."""
    if isinstance(note, (int, float)):
        return float(note)
    m = NOTE.match(str(note).strip())
    if not m:
        raise ValueError(f"not a note: {note!r} (write it like A4, C#5 or Eb3)")
    letter, acc, octave = m.groups()
    n = SEMITONE[letter.lower()] + {"#": 1, "b": -1, "": 0}[acc] + (int(octave) + 1) * 12
    return 440.0 * 2 ** ((n - 69) / 12)


def resolve_at(at, starts: dict) -> float:
    """Seconds for a cue's `at`: a number, or a shot id with an optional +/- offset."""
    if isinstance(at, (int, float)):
        return float(at)
    m = AT.match(str(at))
    if not m or m.group(1) not in starts:
        raise ValueError(f"cue time {at!r}: use seconds or a shot id from shots.json ({', '.join(starts)})")
    sign = -1 if m.group(2) == "-" else 1
    return starts[m.group(1)] + sign * float(m.group(3) or 0)


def _t(dur: float) -> np.ndarray:
    return np.arange(int(round(dur * SR))) / SR


def _env(n: int, attack: float, release: float) -> np.ndarray:
    """Linear attack, flat, linear release, over n samples."""
    e = np.ones(n)
    a, r = min(int(attack * SR), n), min(int(release * SR), n)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[n - r:] *= np.linspace(1, 0, r)
    return e


def _decay(n: int, seconds: float) -> np.ndarray:
    """Exponential fall to -60 dB over `seconds`, with a 3 ms attack so nothing clicks."""
    e = np.exp(-6.9 * np.arange(n) / (seconds * SR))
    a = min(int(0.003 * SR), n)
    e[:a] *= np.linspace(0, 1, a)
    return e


def _phase(f) -> np.ndarray:
    """Phase for a frequency that may change over time (an array of Hz per sample)."""
    return 2 * np.pi * np.cumsum(f) / SR


def _bandnoise(n: int, lo, hi, rng) -> np.ndarray:
    """White noise kept between lo..hi Hz, where lo and hi may sweep (arrays of Hz per sample): short overlapping
    frames, each masked in the spectrum around its own band."""
    size, hop = 2048, 512
    total = n + size
    noise = rng.standard_normal(total)
    win = np.hanning(size)
    out = np.zeros(total)
    bins = np.fft.rfftfreq(size, 1 / SR)
    lo, hi = np.broadcast_to(lo, n), np.broadcast_to(hi, n)
    for start in range(0, n, hop):
        i = min(start + size // 2, n - 1)
        spec = np.fft.rfft(noise[start:start + size] * win)
        a, b = max(lo[i], 20.0), max(hi[i], lo[i] + 40.0)
        mask = np.clip(np.minimum(bins - a, b - bins) / (0.25 * (b - a)) + 1, 0, 1)
        out[start:start + size] += np.fft.irfft(spec * mask, size) * win
    out = out[:n]
    peak = np.max(np.abs(out)) or 1.0
    return out / peak


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(2, min(cutoff, SR / 2 - 100), fs=SR, output="sos"), x)


def _soft(f: float, t: np.ndarray, harmonics: int = 8) -> np.ndarray:
    """A warm saw-like tone from a few harmonics (no aliasing)."""
    out = np.zeros_like(t)
    for k in range(1, harmonics + 1):
        if f * k < SR / 2 - 1000:
            out += np.sin(2 * np.pi * f * k * t) / k
    return out


def pad(c, rng):
    """Held chord: detuned soft saws, slow swell. notes, dur, attack (1.5), release (2), bright (2200 Hz)."""
    t = _t(c["dur"])
    out = np.zeros_like(t)
    for note in c.get("notes", ["A3", "E4"]):
        f = freq(note)
        for cents in (-7, 0, 7):
            out += _soft(f * 2 ** (cents / 1200), t + rng.random())
    out = _lowpass(out, c.get("bright", 2200)) * (1 + 0.08 * np.sin(2 * np.pi * 0.17 * t))
    return out * _env(len(t), c.get("attack", 1.5), c.get("release", 2.0))


def drone(c, rng):
    """Low steady tone with slow movement: note (A2), dur."""
    t = _t(c["dur"])
    f = freq(c.get("note", "A2"))
    out = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.003 * t) + 0.2 * np.sin(2 * np.pi * f * 3 * t)
    return out * (1 + 0.15 * np.sin(2 * np.pi * 0.11 * t)) * _env(len(t), c.get("attack", 2.0), c.get("release", 2.5))


def chime(c, rng):
    """A struck bell: note (E6), dur (2.5)."""
    dur = c.get("dur", 2.5)
    t = _t(dur)
    f = freq(c.get("note", "E6"))
    out = np.zeros_like(t)
    for ratio, amp, life in ((1, 1, 1), (2.0, 0.5, 0.7), (2.76, 0.4, 0.5), (5.4, 0.22, 0.3), (8.93, 0.12, 0.18)):
        if f * ratio < SR / 2 - 1000:
            out += amp * np.sin(2 * np.pi * f * ratio * t) * _decay(len(t), dur * life)
    return out


def pluck(c, rng):
    """A plucked string (Karplus-Strong): note (A4), dur (1.2), damp (0.996)."""
    n = int(c.get("dur", 1.2) * SR)
    period = max(2, int(round(SR / freq(c.get("note", "A4")))))
    damp = c.get("damp", 0.996)
    out = np.zeros(n + 2 * period + 2)
    out[:period + 1] = rng.uniform(-1, 1, period + 1)
    # y[i] = damp * (y[i-P] + y[i-P-1]) / 2, a period at a time: each block reads only the samples before it
    for start in range(period + 1, len(out), period):
        end = min(start + period, len(out))
        k = end - start
        out[start:end] = damp * 0.5 * (out[start - period:start - period + k] + out[start - period - 1:start - period - 1 + k])
    return _lowpass(out[:n], 6000) * _decay(n, c.get("dur", 1.2))


def soft(c, rng):
    """A soft mallet note: note (A4), dur (0.8)."""
    dur = c.get("dur", 0.8)
    t = _t(dur)
    f = freq(c.get("note", "A4"))
    return (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)) * _decay(len(t), dur)


def arp(c, rng):
    """Notes played in turn: notes, dur, bpm (90), step (0.5 = eighths), voice (pluck|chime|soft|glock), length
    (0.9 s)."""
    step = 60 / c.get("bpm", 90) * c.get("step", 0.5)
    voice = {"pluck": pluck, "chime": chime, "soft": soft, "glock": glock}[c.get("voice", "pluck")]
    n = int(c["dur"] * SR)
    out = np.zeros(n + int(4 * SR))
    notes = c.get("notes", ["A4", "C5", "E5"])
    for i in range(int(c["dur"] / step)):
        hit = voice({"note": notes[i % len(notes)], "dur": c.get("length", 0.9)}, rng)
        at = int(i * step * SR)
        out[at:at + len(hit)] += hit * (1.0 if i % 4 == 0 else 0.75)
    return out[:n + int(c.get("length", 0.9) * SR)]


def whoosh(c, rng):
    """Air moving past: dur (0.8), from (300 Hz), to (3000 Hz). The band sweeps and the level swells then falls."""
    n = int(c.get("dur", 0.8) * SR)
    sweep = np.geomspace(c.get("from", 300), c.get("to", 3000), n)
    shape = np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5
    return _bandnoise(n, sweep * 0.6, sweep * 1.6, rng) * shape


def riser(c, rng):
    """Tension that climbs to its end: dur (2), from (200 Hz), to (2400 Hz)."""
    n = int(c.get("dur", 2.0) * SR)
    sweep = np.geomspace(c.get("from", 200), c.get("to", 2400), n)
    rise = np.linspace(0, 1, n) ** 2
    return (0.6 * _bandnoise(n, sweep * 0.7, sweep * 1.4, rng) + 0.4 * np.sin(_phase(sweep))) * rise


def impact(c, rng):
    """A low hit: dur (0.9), note (55 Hz)."""
    n = int(c.get("dur", 0.9) * SR)
    f0 = freq(c.get("note", 55))
    body = np.sin(_phase(f0 * (1 + 1.5 * np.exp(-np.arange(n) / (0.03 * SR))))) * _decay(n, c.get("dur", 0.9))
    snap = _bandnoise(n, 200, 4000, rng) * _decay(n, 0.08)
    return body + 0.4 * snap


def pop(c, rng):
    """A small bright pop, for things appearing: note (900 Hz)."""
    n = int(0.09 * SR)
    f0 = freq(c.get("note", 900))
    return np.sin(_phase(f0 * np.geomspace(1, 0.35, n))) * _decay(n, 0.09)


def drip(c, rng):
    """A water drop: note (700 Hz)."""
    n = int(0.12 * SR)
    f0 = freq(c.get("note", 700))
    return np.sin(_phase(f0 * np.geomspace(1, 2.4, n))) * _decay(n, 0.12)


def tick(c, rng):
    """A dry click, for a cursor, a clock or a step: no options."""
    n = int(0.012 * SR)
    return _bandnoise(n, 2500, 9000, rng) * _decay(n, 0.012)


def hum(c, rng):
    """A buzz with a flutter, like wings or a motor: dur, note (180 Hz), flutter (40 Hz)."""
    t = _t(c["dur"])
    f = freq(c.get("note", 180))
    buzz = _soft(f, t, 12) * (0.6 + 0.4 * np.sin(2 * np.pi * c.get("flutter", 40) * t))
    return _lowpass(buzz, 2500) * _env(len(t), 0.15, 0.3)


def wash(c, rng):
    """Soft continuous noise, like water, wind or a room: dur, low (200 Hz), high (1800 Hz)."""
    n = int(c["dur"] * SR)
    t = np.arange(n) / SR
    drift = 1 + 0.3 * np.sin(2 * np.pi * 0.13 * t + rng.random() * 6)
    return _bandnoise(n, c.get("low", 200) * drift, c.get("high", 1800) * drift, rng) * _env(n, 1.0, 1.5)


def boing(c, rng):
    """A springy cartoon bounce, for a hop or a squash: note (220 Hz), dur (0.45), wobble (14 Hz)."""
    dur = c.get("dur", 0.45)
    n = int(dur * SR)
    t = np.arange(n) / SR
    f0 = freq(c.get("note", 220))
    rise = 0.7 + 0.9 * (1 - np.exp(-t / 0.05))
    wobble = 1 + 0.18 * np.sin(2 * np.pi * c.get("wobble", 14) * t) * np.exp(-t / (0.5 * dur))
    sweep = f0 * rise * wobble
    return (np.sin(_phase(sweep)) + 0.2 * np.sin(2 * _phase(sweep))) * _decay(n, dur)


def glock(c, rng):
    """A glockenspiel bar: bright, short and pure. note (C6), dur (1.2)."""
    dur = c.get("dur", 1.2)
    t = _t(dur)
    f = freq(c.get("note", "C6"))
    out = np.zeros_like(t)
    for ratio, amp, life in ((1, 1, 1), (2.76, 0.25, 0.25), (5.4, 0.1, 0.1)):
        if f * ratio < SR / 2 - 1000:
            out += amp * np.sin(2 * np.pi * f * ratio * t) * _decay(len(t), dur * life)
    return out


def kick(c, rng):
    """A soft round kick drum: note (52 Hz), dur (0.35)."""
    n = int(c.get("dur", 0.35) * SR)
    f0 = freq(c.get("note", 52))
    body = np.sin(_phase(f0 * (1 + 2.2 * np.exp(-np.arange(n) / (0.025 * SR))))) * _decay(n, c.get("dur", 0.35))
    return body + 0.15 * _bandnoise(n, 800, 3000, rng) * _decay(n, 0.01)


def snare(c, rng):
    """A dusty snare or rim: dur (0.2), tone (190 Hz)."""
    n = int(c.get("dur", 0.2) * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * c.get("tone", 190) * t) * _decay(n, 0.08)
    return 0.5 * tone + _bandnoise(n, 1200, 7000, rng) * _decay(n, c.get("dur", 0.2))


def hat(c, rng):
    """A closed hi-hat: dur (0.05)."""
    n = int(c.get("dur", 0.05) * SR)
    return _bandnoise(n, 6000, 14000, rng) * _decay(n, c.get("dur", 0.05))


DRUMS = {"kick": kick, "snare": snare, "hat": hat}
DRUM_LEVEL = {"kick": 1.0, "snare": 0.55, "hat": 0.25}
LOFI = {"kick": "x.......x.x.....", "snare": "....x.......x...", "hat": "x.x.x.x.x.x.x.x."}


def beat(c, rng):
    """A drum loop from step patterns, one character per 16th note ("x" hit, "o" soft hit, "." rest):
    dur, bpm (120), swing (0 to 0.3: late off-beats, the lo-fi lean), and one pattern per drum, e.g.
    {"kick": "x.......x.x.....", "snare": "....x.......x...", "hat": "x.x.x.x.x.x.x.x."} (the default when no
    pattern is given). Patterns repeat."""
    step = 60 / c.get("bpm", 120) / 4
    n = int(c["dur"] * SR)
    out = np.zeros(n + SR)
    patterns = {k: c[k] for k in DRUMS if k in c} or LOFI
    for name, voice in DRUMS.items():
        pattern = patterns.get(name, "")
        if not pattern:
            continue
        hits = {"x": voice({}, rng), "o": 0.5 * voice({}, rng)}
        for i in range(int(c["dur"] / step)):
            hit = hits.get(pattern[i % len(pattern)])
            if hit is None:
                continue
            at = int((i + (c.get("swing", 0) if i % 2 else 0)) * step * SR)
            out[at:at + len(hit)] += hit * DRUM_LEVEL[name]
    return out[:n]


def crackle(c, rng):
    """Vinyl crackle and hiss under a lo-fi beat: dur, density (40 pops a second)."""
    n = int(c["dur"] * SR)
    out = 0.15 * _bandnoise(n, 2000, 9000, rng)
    pops = rng.integers(0, n, int(c.get("density", 40) * c["dur"]))
    out[pops] += rng.uniform(-1, 1, len(pops)) * 3
    return _lowpass(out, 7000) * _env(n, 0.5, 0.5)


def audio_file(c, rng):
    """A local audio file, such as a free-licence track: path, dur (optional trim)."""
    from . import ffmpeg
    x = ffmpeg.read_pcm(c["path"], SR)
    return x[:int(c["dur"] * SR)] if c.get("dur") else x


CUES = {"pad": pad, "drone": drone, "chime": chime, "pluck": pluck, "soft": soft, "arp": arp, "whoosh": whoosh,
        "riser": riser, "impact": impact, "pop": pop, "drip": drip, "tick": tick, "hum": hum, "wash": wash,
        "boing": boing, "glock": glock, "kick": kick, "snare": snare, "hat": hat, "beat": beat, "crackle": crackle,
        "file": audio_file}


def _reverb(mix: np.ndarray, amount: float, rng) -> np.ndarray:
    """A plain room: seeded decaying noise as the impulse, a different one per side so it opens up."""
    from scipy.signal import fftconvolve
    n = int(1.8 * SR)
    out = mix.copy()
    for ch in range(2):
        ir = rng.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n)
        ir = _lowpass(ir, 5000)
        ir /= np.sqrt(np.sum(ir ** 2))
        out[:, ch] += amount * fftconvolve(mix[:, ch], ir)[:len(mix)]
    return out


def render(spec: dict, duration: float, starts: dict | None = None) -> np.ndarray:
    """Stereo float32 (samples, 2) of exactly `duration` seconds."""
    starts = starts or {}
    rng = np.random.default_rng(spec.get("seed", 7))
    n = int(round(duration * SR))
    mix = np.zeros((n, 2))
    for i, c in enumerate(spec.get("cues", [])):
        kind = c.get("type")
        if kind not in CUES:
            raise ValueError(f"cue {i}: unknown type {kind!r}; types: {', '.join(CUES)}")
        if kind in ("pad", "drone", "arp", "hum", "wash", "beat", "crackle") and "dur" not in c:
            raise ValueError(f"cue {i} ({kind}) needs a dur in seconds")
        at = resolve_at(c.get("at", 0), starts)
        x = CUES[kind](c, rng)
        x = x / (np.max(np.abs(x)) or 1.0) * 10 ** (c.get("gain", -12) / 20)
        start = int(round(at * SR))
        if start >= n or start + len(x) <= 0:
            continue
        if start < 0:
            x, start = x[-start:], 0
        x = x[:n - start]
        pan = float(np.clip(c.get("pan", 0), -1, 1))
        left, right = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        mix[start:start + len(x), 0] += x * left * np.sqrt(2)
        mix[start:start + len(x), 1] += x * right * np.sqrt(2)
    if spec.get("reverb"):
        mix = _reverb(mix, float(spec["reverb"]), rng)
    fade = min(int(0.05 * SR), n)
    if fade:
        mix[n - fade:] *= np.linspace(1, 0, fade)[:, None]
    return _limit(mix).astype(np.float32)


def _limit(x: np.ndarray, knee: float = 0.8) -> np.ndarray:
    """Untouched below the knee; above it, peaks bend smoothly toward 1.0 and never pass it."""
    over = np.abs(x) > knee
    out = x.copy()
    out[over] = np.sign(x[over]) * (knee + (1 - knee) * np.tanh((np.abs(x[over]) - knee) / (1 - knee)))
    return out


def write(spec: dict, duration: float, out, starts: dict | None = None) -> Path:
    import soundfile as sf
    out = Path(out)
    sf.write(out, render(spec, duration, starts), SR, subtype="FLOAT")
    return out
