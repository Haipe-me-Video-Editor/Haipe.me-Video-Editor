"""Original background music and SFX, synthesised in code: always available, no licence questions."""
import wave
from pathlib import Path

import numpy as np

SR = 48000
CHORDS = [[50, 57, 62, 66], [47, 54, 59, 62], [43, 50, 55, 59], [45, 52, 57, 61]]  # D Bm G A
MOTIF = [(0, 74), (1.5, 78), (2.5, 81), (3.0, 78)]  # (beat, midi)


def _hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _env(n: int, a: float, r: float) -> np.ndarray:
    e = np.ones(n)
    na, nr = min(n, int(a * SR)), min(n, int(r * SR))
    if na:
        e[:na] = np.linspace(0, 1, na, endpoint=False)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _write(path, left: np.ndarray, right: np.ndarray) -> Path:
    pcm = (np.clip(np.stack([left, right], axis=1), -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return Path(path)


def write_score(path, duration: float, bpm: float = 96) -> Path:
    if duration <= 0:
        raise ValueError("duration must be positive")
    n = int(duration * SR)
    L, R = np.zeros(n), np.zeros(n)
    beat, bar = 60 / bpm, 240 / bpm

    def add(sig, start, gain, pan=0.0):
        i = int(start * SR)
        if i >= n:
            return
        sig = sig[: n - i]
        L[i:i + len(sig)] += sig * gain * np.cos((pan + 1) * np.pi / 4)
        R[i:i + len(sig)] += sig * gain * np.sin((pan + 1) * np.pi / 4)

    bars = int(np.ceil(duration / bar))
    for b in range(bars):
        chord = CHORDS[0] if b == bars - 1 else CHORDS[b % 4]
        m = int((bar + 0.6) * SR)
        t = np.arange(m) / SR
        pad = sum(np.sin(2 * np.pi * _hz(note + d) * t) + 0.3 * np.sin(4 * np.pi * _hz(note + d) * t)
                  for note in chord for d in (-0.07, 0.0, 0.07)) / (len(chord) * 3)
        add(pad * _env(m, 0.45, 0.7), b * bar, 0.22, -0.2)
        add(pad * _env(m, 0.45, 0.7), b * bar + 0.02, 0.22, 0.2)
        mb = int(bar * SR)
        tb = np.arange(mb) / SR
        add(np.sin(2 * np.pi * _hz(chord[0] - 12) * tb) * _env(mb, 0.05, 0.4), b * bar, 0.16)
        if b % 3 != 2:
            shift = (0, -3, -5, -1)[b % 4]
            for at, note in MOTIF:
                mp = int(1.6 * SR)
                tp = np.arange(mp) / SR
                f = _hz(note + shift)
                tone = (np.sin(2 * np.pi * f * tp) + 0.45 * np.sin(4 * np.pi * f * tp) * np.exp(-tp * 3))
                add(tone * np.exp(-tp * 2.4) * np.minimum(1, tp / 0.006), b * bar + at * beat, 0.075, 0.15)
    for k in range(int(duration / beat)):
        tb_ = k * beat
        if tb_ < bar or tb_ > duration - 1.4:
            continue
        m = int(0.28 * SR)
        t = np.arange(m) / SR
        f = 52 * (1 + 1.2 * np.exp(-t * 40))
        add(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14), tb_, 0.40 if k % 4 == 0 else 0.22)
    for d, g in ((0.031, 0.30), (0.071, 0.22), (0.167, 0.12), (0.29, 0.25)):  # one shared room
        k = int(d * SR)
        L[k:] += L[:-k] * g
        R[k:] += R[:-k] * g * 0.95
    t_all = np.arange(n) / SR
    fade = np.minimum(1, t_all / 0.25) * np.clip((duration - t_all) / 1.4, 0, 1)
    L, R = np.tanh(L * fade * 1.6) / 1.6, np.tanh(R * fade * 1.6) / 1.6
    peak = max(np.max(np.abs(L)), np.max(np.abs(R)), 1e-9)
    return _write(path, L * 0.89 / peak, R * 0.89 / peak)


def _sweep_noise(rng, n: int, f0: float, f1: float) -> np.ndarray:
    """White noise through a band whose centre glides from f0 to f1 (one FFT band per short block)."""
    out, block = np.zeros(n), 1024
    noise = rng.standard_normal(n + block)
    for i in range(0, n, block // 2):
        seg = noise[i:i + block] * np.hanning(block)
        spec = np.fft.rfft(seg)
        f = np.fft.rfftfreq(block, 1 / SR)
        c = f0 * (f1 / f0) ** (min(i, n) / n)
        spec *= np.exp(-((np.log2(np.maximum(f, 1)) - np.log2(c)) ** 2) / 0.5)
        part = np.fft.irfft(spec, block)[: max(0, min(block, n - i))]
        out[i:i + len(part)] += part
    return out / (np.abs(out).max() + 1e-9)


def write_sfx(path, kind: str) -> Path:
    """Sound effects synthesised to the recipes measured in popular edits (see docs/presets/event-recap.md)."""
    rng = np.random.default_rng(7)
    extra = _playful(kind, rng) if kind in PLAYFUL_SFX else _calm(kind, rng) if kind in CALM_SFX else None
    if extra is not None:
        extra = extra * 0.89 / max(np.abs(extra).max(), 1e-9)  # every palette sound peaks at -1 dBFS
        return _write(path, extra, extra)

    def tt(sec):
        return np.arange(int(sec * SR)) / SR

    if kind == "whoosh":  # band-passed noise sweeping up, Hann envelope
        t = tt(0.5)
        sig = _sweep_noise(rng, len(t), 300, 3000) * np.sin(np.pi * t / 0.5) ** 2 * 0.5
    elif kind == "pop":
        t = tt(0.12)
        sig = np.sin(2 * np.pi * 880 * t) * np.exp(-t * 45) * 0.6
    elif kind == "thump":  # sine falling 120 -> 50 Hz, ~80 ms decay
        t = tt(0.35)
        f = 50 + 70 * np.exp(-t * 25)
        sig = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 12) * 0.9
    elif kind == "hit":  # low cinematic hit: sub thump plus a short noise crack
        t = tt(1.6)
        f = 40 + 90 * np.exp(-t * 8)
        sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.2)
        crack = rng.standard_normal(len(t)) * np.exp(-t * 60) * 0.35
        sig = (sub + crack) * 0.8
    elif kind == "tick":  # 1 kHz falling to 700 Hz over 60 ms
        t = tt(0.07)
        f = 1000 - 300 * t / 0.07
        sig = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 50) * 0.5
    elif kind == "riser":  # glide 500 -> 1100 Hz over 0.45 s, then a ding
        t = tt(0.45)
        glide = np.sin(2 * np.pi * np.cumsum(500 + 600 * t / 0.45) / SR) * np.linspace(0.1, 0.5, len(t))
        t2 = tt(0.8)
        ding = (np.sin(2 * np.pi * 2600 * t2) + 0.5 * np.sin(2 * np.pi * 5200 * t2)) * np.exp(-t2 / 0.25) * 0.35
        sig = np.concatenate([glide, ding])
    elif kind == "ding":  # 2.6 + 5.2 kHz, exponential decay
        t = tt(0.8)
        sig = (np.sin(2 * np.pi * 2600 * t) + 0.5 * np.sin(2 * np.pi * 5200 * t)) * np.exp(-t / 0.25) * 0.4
    elif kind == "shutter":  # camera flash: two clicks and a short noise burst
        t = tt(0.25)
        sig = rng.standard_normal(len(t)) * (np.exp(-t * 90) + 0.6 * np.exp(-np.maximum(t - 0.09, 0) * 120)
                                             * (t > 0.09)) * 0.5
    elif kind == "glitch":  # digital zap: square bursts with random pitch jumps
        t = tt(0.3)
        f = np.repeat(rng.uniform(200, 1800, 12), int(np.ceil(len(t) / 12)))[: len(t)]
        sig = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * 0.25 * (t < 0.28)
    elif kind == "coin":  # bright ring with inharmonic partials
        t = tt(0.45)
        sig = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((8700, .5), (6100, .3), (11300, .2))) * np.exp(-t * 9)
    else:
        raise ValueError(f"unknown sfx kind {kind!r}")
    return _write(path, sig, sig)


# ---- extra sound palettes, chosen per brand by its preset ----
# Playful: cartoon sounds for a playful style (a character hopping, a box opening, a reveal). Calm: soft, airy
# accents for a premium brand where pops and boings would be wrong. Same rules as the rest: tied to something visible.


def _t(sec: float) -> np.ndarray:
    return np.arange(int(sec * SR)) / SR


def _glide(f0: float, f1: float, sec: float, curve: float = 1.0) -> np.ndarray:
    """Sine whose pitch moves from f0 to f1; curve > 1 holds low then rises late."""
    t = _t(sec)
    return np.sin(2 * np.pi * np.cumsum(f0 + (f1 - f0) * (t / sec) ** curve) / SR)


def _decay(n: int, attack: float, tau: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(t / max(attack, 1e-4), 1) * np.exp(-t / tau)


def _bell(f: float, sec: float, tau: float) -> np.ndarray:
    """A soft bell: the note plus a quickly fading inharmonic partial."""
    t = _t(sec)
    return (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t / 0.08)) \
        * _decay(len(t), 0.002, tau)


def _tone(f: float, sec: float, harmonics: int = 6, vib: float = 0.0) -> np.ndarray:
    """A rounded brassy tone: harmonics at 1/n, optional vibrato depth (fraction of pitch) at 5.5 Hz."""
    t = _t(sec)
    phase = np.cumsum(f * (1 + vib * np.sin(2 * np.pi * 5.5 * t))) / SR
    return sum(np.sin(2 * np.pi * k * phase) / k for k in range(1, harmonics + 1)) / 1.8


def _room(sig: np.ndarray, rng, decay: float = 0.35, mix: float = 0.22) -> np.ndarray:
    """A short synthetic room tail so the bells don't sound dry."""
    ir = rng.standard_normal(int(decay * SR)) * np.exp(-np.arange(int(decay * SR)) / SR / (decay / 5))
    wet = np.convolve(sig, ir / np.abs(ir).sum() * 6)[: len(sig) + len(ir)]
    out = np.zeros(len(wet))
    out[: len(sig)] += sig
    return out * (1 - mix) + wet * mix


def _place(parts: list) -> np.ndarray:
    """Sum (start seconds, signal) pairs into one buffer."""
    n = max(int(at * SR) + len(sig) for at, sig in parts)
    out = np.zeros(n)
    for at, sig in parts:
        i = int(at * SR)
        out[i:i + len(sig)] += sig
    return out


def _playful(kind: str, rng):
    if kind == "boing":  # spring: pitch rises with a decaying wobble
        t = _t(0.45)
        f = (170 + 560 * (t / 0.45) ** 0.6) * (1 + 0.07 * np.sin(2 * np.pi * 16 * t) * np.exp(-t / 0.2))
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * _decay(len(t), 0.004, 0.17) * 0.75
    if kind == "plip":  # a water drop: a quick upward chirp
        return _glide(520, 1500, 0.07, 2.2) * _decay(int(0.07 * SR), 0.001, 0.025) * 0.7
    if kind == "bloop":  # a bubble: dips then rises
        t = _t(0.16)
        f = 420 - 160 * np.sin(np.pi * t / 0.16) + 700 * (t / 0.16) ** 3
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * _decay(len(t), 0.003, 0.07) * 0.75
    if kind == "zip":  # a tear or zipper: a rising tone over rising noise
        n = int(0.28 * SR)
        return (_glide(380, 1500, 0.28, 2) * 0.6 + _sweep_noise(rng, n, 1500, 6000) * 0.5) \
            * np.minimum(np.arange(n) / (0.12 * SR), 1) * np.exp(-np.arange(n) / SR / 0.2) * 0.45
    if kind == "sparkle":  # a quick climbing run of bells (pentatonic, C6 up)
        notes = [1046.5, 1174.7, 1318.5, 1568.0, 1760.0, 2093.0]
        return _room(_place([(i * 0.045, _bell(f, 0.6, 0.18) * 0.28) for i, f in enumerate(notes)]), rng)
    if kind == "chime":  # a C major arpeggio of bells, for a reveal or a glint
        notes = [1046.5, 1318.5, 1568.0, 2093.0]
        return _room(_place([(i * 0.07, _bell(f, 1.0, 0.35) * 0.3) for i, f in enumerate(notes)]), rng)
    if kind == "tada":  # two short brass stabs, then a held major chord an octave up
        stab = [262, 330, 392]
        held = [523, 659, 784, 1047]
        short = sum(_tone(f, 0.12) for f in stab) * _decay(int(0.12 * SR), 0.005, 0.08)
        long_ = sum(_tone(f, 0.9, vib=0.006) for f in held) * _env(int(0.9 * SR), 0.01, 0.5)
        return _room(_place([(0, short * 0.22), (0.14, short * 0.22), (0.3, long_ * 0.2)]), rng, 0.5, 0.18)
    if kind == "wahwah":  # the sad trombone: four falling notes, the last one wobbling
        notes = [392.0, 370.0, 349.2, 329.6]
        parts = [(i * 0.42, _tone(f, 0.36) * _env(int(0.36 * SR), 0.03, 0.12) * 0.3) for i, f in enumerate(notes[:3])]
        parts.append((1.26, _tone(notes[3], 1.1, vib=0.03) * _env(int(1.1 * SR), 0.03, 0.5) * 0.3))
        return _place(parts)
    if kind == "bonk":  # a wooden knock: two partials and a click
        t = _t(0.18)
        sig = (np.sin(2 * np.pi * 620 * t) + 0.5 * np.sin(2 * np.pi * 1730 * t)) * _decay(len(t), 0.0008, 0.03)
        sig[: int(0.004 * SR)] += rng.standard_normal(int(0.004 * SR)) * 0.4
        return sig * 0.75
    if kind == "wobble":  # jelly: five fading swings between two notes
        parts = []
        for i in range(5):
            t = _t(0.14)
            tri = 2 * np.abs(2 * ((t * (330 if i % 2 == 0 else 392)) % 1) - 1) - 1
            parts.append((i * 0.11, tri * _decay(len(t), 0.003, 0.05) * 0.45 * (1 - i * 0.16)))
        return _place(parts)
    if kind == "poof":  # a soft puff of air, for something appearing or vanishing
        n = int(0.32 * SR)
        return _sweep_noise(rng, n, 2500, 500) * _decay(n, 0.01, 0.09) * 0.5
    if kind == "whoop":  # a slide whistle going up
        t = _t(0.38)
        f = (420 + 1300 * (t / 0.38) ** 1.4) * (1 + 0.012 * np.sin(2 * np.pi * 7 * t))
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.03, 0.08) * 0.4
    if kind == "squeak":  # a squeezed toy
        t = _t(0.16)
        f = 1700 + 700 * np.sin(np.pi * t / 0.16)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.01, 0.05) * 0.35
    return None


def _calm(kind: str, rng):
    if kind == "shimmer":  # an airy glint: high noise and a faint bright cluster, slow in and out
        n = int(1.1 * SR)
        t = np.arange(n) / SR
        air = _sweep_noise(rng, n, 5000, 9000) * 0.35
        cluster = sum(np.sin(2 * np.pi * f * t) for f in (2349.3, 2793.8, 3520.0)) * 0.05
        return _room((air + cluster) * np.sin(np.pi * t / 1.1) ** 2, rng, 0.6, 0.3) * 0.6
    if kind == "swell":  # a soft rising swell that peaks on the cut (place it with align: peak)
        n = int(0.9 * SR)
        t = np.arange(n) / SR
        rise = (t / 0.9) ** 3 * (t < 0.82) + (t >= 0.82) * np.exp(-(t - 0.82) / 0.03)
        return (_sweep_noise(rng, n, 400, 4000) * 0.6 + _glide(220, 440, 0.9, 2) * 0.15) * rise * 0.6
    if kind == "triad":  # three soft notes one after another, then held together: a quiet logo sting
        notes = [587.3, 740.0, 880.0]  # D5 F#5 A5
        parts = [(i * 0.16, (np.sin(2 * np.pi * f * _t(1.6)) * 0.6 + _tone(f, 1.6, 3) * 0.2)
                  * _env(int(1.6 * SR), 0.02, 1.0) * 0.16) for i, f in enumerate(notes)]
        return _room(_place(parts), rng, 0.8, 0.3)
    return None


PLAYFUL_SFX = ("boing", "plip", "bloop", "zip", "sparkle", "chime", "tada", "wahwah", "bonk", "wobble", "poof",
               "whoop", "squeak")
CALM_SFX = ("shimmer", "swell", "triad")
