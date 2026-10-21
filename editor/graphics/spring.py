"""Damped-spring eases for GSAP, injected into every built-in composition.

A spring's position curve is the closed-form solution of a damped harmonic oscillator released from rest:
a pure function of progress, so it is seek-safe (HyperFrames renders frames out of order). The time axis is
scaled so the motion has settled (|x - 1| < SETTLE_EPS) at t = 1, and the ease is exactly 1 at t = 1: a tween
keeps its duration and lands on the same frame it did with a power ease. Stiffness only sets the time scale,
so after normalising, the damping ratio zeta = damping / (2 sqrt(stiffness * mass)) decides the shape.

House rules (skills/hyperframes-animation/adapters/gsap-easing-and-stagger.md, "Spring Eases"):
- springs on ENTRANCES only; exits stay on smooth `power2.in`.
- an overshooting curve goes on transforms only: `springIn` splits opacity, filter, clip-path and colours onto
  a smooth tween at the same position, so they never overshoot.
"""
import json
import math

SETTLE_EPS = 0.001  # the spring has settled when it stays within 0.1% of its target
SCAN_STEPS = 4000   # fixed-step settle scan: deterministic, runs once per page

# (stiffness, damping, mass). Measured peak overshoot after normalising, see tests/test_spring.py.
PRESETS = {
    "gentle": (170, 20, 1),    # zeta 0.77, ~2.3% overshoot: felt, not seen. Cards and panels.
    "snappy": (400, 26, 1),    # zeta 0.65, ~6.8%: pills, labels, list items, stat numbers.
    "bouncy": (400, 22.5, 1),  # zeta 0.56, ~11.8%: emphasis pops only (kinetic words, badges).
}

# GSAP properties that are transforms; everything else in a springIn tween (opacity, filter, clipPath,
# textShadow, colours, CSS variables) goes on the smooth tween.
TRANSFORMS = ("x", "y", "z", "xPercent", "yPercent", "scale", "scaleX", "scaleY", "rotation", "rotationX",
              "rotationY", "rotationZ", "skewX", "skewY")
SMOOTH = "power3.out"  # the fade keeps the curve it had before springs

SPRING_JS = """
function spring(stiffness = 170, damping = 26, mass = 1) {
  const w0 = Math.sqrt(stiffness / mass), z = damping / (2 * Math.sqrt(stiffness * mass)), a = z * w0;
  let x, rate;
  if (Math.abs(z - 1) < 1e-6) {
    x = s => 1 - Math.exp(-w0 * s) * (1 + w0 * s); rate = w0;
  } else if (z < 1) {
    const wd = w0 * Math.sqrt(1 - z * z);
    x = s => 1 - Math.exp(-a * s) * (Math.cos(wd * s) + (a / wd) * Math.sin(wd * s)); rate = a;
  } else {
    const wo = w0 * Math.sqrt(z * z - 1), r1 = -a + wo, r2 = -a - wo;
    x = s => 1 - (r2 * Math.exp(r1 * s) - r1 * Math.exp(r2 * s)) / (r2 - r1); rate = -r1;
  }
  const scan = 12 / rate;
  let T = scan;
  for (let i = %(steps)d; i >= 0; i--) {
    if (Math.abs(1 - x(i / %(steps)d * scan)) > %(eps)s) { T = (i + 1) / %(steps)d * scan; break; }
  }
  const xT = x(T);
  return t => t <= 0 ? 0 : t >= 1 ? 1 : x(t * T) + t * (1 - xT);
}
const SPRING = {%(presets)s};
const SPRING_TRANSFORMS = new Set(%(transforms)s);
const SPRING_PARAMS = new Set(["duration", "stagger", "delay", "repeat", "repeatDelay", "yoyo", "immediateRender"]);
function springIn(tl, targets, from, to, preset, at) {
  const sf = {}, st = {}, mf = {}, mt = {};
  let smooth = false;
  for (const k in to) {
    if (SPRING_PARAMS.has(k)) { st[k] = to[k]; mt[k] = to[k]; }
    else if (SPRING_TRANSFORMS.has(k) || typeof to[k] === "function") mt[k] = to[k];
    else { st[k] = to[k]; smooth = true; }
  }
  for (const k in from) (SPRING_TRANSFORMS.has(k) ? mf : sf)[k] = from[k];
  if (smooth) tl.fromTo(targets, sf, Object.assign(st, {ease: "%(smooth)s"}), at);
  tl.fromTo(targets, mf, Object.assign(mt, {ease: SPRING[preset]}), at);
  return tl;
}
""" % {"steps": SCAN_STEPS, "eps": SETTLE_EPS, "smooth": SMOOTH, "transforms": json.dumps(list(TRANSFORMS)),
       "presets": ", ".join(f"{k}: spring({s}, {d}, {m})" for k, (s, d, m) in PRESETS.items())}

SPRING_TAG = f"<script>{SPRING_JS}</script>"


def spring_in(sel: str, frm: str, to: str, preset: str, at) -> str:
    """JS for a spring entrance; `frm` and `to` are GSAP vars without braces, e.g. 'y:40,opacity:0'."""
    if preset not in PRESETS:
        raise ValueError(f"unknown spring preset {preset!r}")
    return f'springIn(tl,{json.dumps(sel)},{{{frm}}},{{{to}}},"{preset}",{at});'


def spring(stiffness: float = 170, damping: float = 26, mass: float = 1):
    """Python mirror of the JS `spring` (for tests and timing maths): returns the ease t -> value."""
    w0, z = math.sqrt(stiffness / mass), damping / (2 * math.sqrt(stiffness * mass))
    a = z * w0
    if abs(z - 1) < 1e-6:
        def x(s): return 1 - math.exp(-w0 * s) * (1 + w0 * s)
        rate = w0
    elif z < 1:
        wd = w0 * math.sqrt(1 - z * z)
        def x(s): return 1 - math.exp(-a * s) * (math.cos(wd * s) + (a / wd) * math.sin(wd * s))
        rate = a
    else:
        wo = w0 * math.sqrt(z * z - 1)
        r1, r2 = -a + wo, -a - wo
        def x(s): return 1 - (r2 * math.exp(r1 * s) - r1 * math.exp(r2 * s)) / (r2 - r1)
        rate = -r1
    scan, T = 12 / rate, 12 / rate
    for i in range(SCAN_STEPS, -1, -1):
        if abs(1 - x(i / SCAN_STEPS * scan)) > SETTLE_EPS:
            T = (i + 1) / SCAN_STEPS * scan
            break
    xT = x(T)
    return lambda t: 0.0 if t <= 0 else 1.0 if t >= 1 else x(t * T) + t * (1 - xT)


def overshoot(stiffness: float, damping: float, mass: float = 1) -> float:
    """Peak overshoot past the target as a fraction (analytic, before normalising): 0 when not underdamped."""
    z = damping / (2 * math.sqrt(stiffness * mass))
    return math.exp(-math.pi * z / math.sqrt(1 - z * z)) if z < 1 else 0.0
