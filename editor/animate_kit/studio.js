// Studio: a short film drawn on one canvas, every frame a pure function of its time. HyperFrames seeks a paused
// GSAP timeline frame by frame; one linear tween drives `t` and each update redraws the whole frame from it, so a
// frame never depends on the one before it (no Date, no unseeded Math.random, no state carried between frames).
(function () {
  "use strict";
  const TAU = Math.PI * 2;

  // Seeded randomness: the same seed gives the same numbers on every render.
  function rng(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function hash(x, y, seed) {
    let h = Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263) + Math.imul(seed | 0, 2147483647);
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }

  // Smooth value noise in 0..1, and fractal noise built from it.
  function noise(x, y, seed = 0) {
    const xi = Math.floor(x), yi = Math.floor(y);
    const xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const a = hash(xi, yi, seed), b = hash(xi + 1, yi, seed);
    const c = hash(xi, yi + 1, seed), d = hash(xi + 1, yi + 1, seed);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }

  function fbm(x, y, octaves = 4, seed = 0) {
    let sum = 0, amp = 0.5, norm = 0;
    for (let i = 0; i < octaves; i++) {
      sum += amp * noise(x, y, seed + i * 31);
      norm += amp;
      x *= 2.03;
      y *= 2.03;
      amp *= 0.5;
    }
    return sum / norm;
  }

  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, k) => a + (b - a) * k;
  const smooth = (e0, e1, x) => {
    const k = clamp((x - e0) / (e1 - e0));
    return k * k * (3 - 2 * k);
  };
  // Progress of a moment inside a shot: 0 before `start`, 1 after `start + dur`, eased between.
  const span = (t, start, dur, fn = ease.inOut) => fn(clamp((t - start) / dur));

  const ease = {
    linear: (k) => k,
    in: (k) => k * k * k,
    out: (k) => 1 - Math.pow(1 - k, 3),
    inOut: (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
    sine: (k) => -(Math.cos(Math.PI * k) - 1) / 2,
    back: (k) => 1 + 2.70158 * Math.pow(k - 1, 3) + 1.70158 * Math.pow(k - 1, 2),
    expoOut: (k) => (k === 1 ? 1 : 1 - Math.pow(2, -10 * k)),
  };

  function hexRgb(hex) {
    const h = hex.replace("#", "");
    const n = parseInt(h.length === 3 ? h.replace(/./g, "$&$&") : h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const rgba = (hex, a = 1) => {
    const [r, g, b] = hexRgb(hex);
    return `rgba(${r},${g},${b},${a})`;
  };
  // Blend two hex colours; k = 0 gives a, 1 gives b.
  const mix = (a, b, k) => {
    const x = hexRgb(a), y = hexRgb(b);
    return `rgb(${x.map((v, i) => Math.round(lerp(v, y[i], k))).join(",")})`;
  };

  function layer(w, h) {
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    return c;
  }

  // Film grain from four seeded tiles, picked by frame, so it moves like film yet renders the same every time.
  let grainTiles = null;
  function grain(ctx, t, amount = 0.06, fps = 30) {
    if (!grainTiles) {
      grainTiles = [0, 1, 2, 3].map((i) => {
        const c = layer(256, 256), g = c.getContext("2d"), img = g.createImageData(256, 256), r = rng(9001 + i);
        for (let p = 0; p < img.data.length; p += 4) {
          const v = r() * 255;
          img.data[p] = img.data[p + 1] = img.data[p + 2] = v;
          img.data[p + 3] = 255;
        }
        g.putImageData(img, 0, 0);
        return c;
      });
    }
    const f = Math.floor(t * fps), tile = grainTiles[f % 4], r = rng(f + 1);
    ctx.save();
    ctx.globalAlpha = amount;
    ctx.globalCompositeOperation = "overlay";
    ctx.translate(-r() * 256, -r() * 256);
    ctx.fillStyle = ctx.createPattern(tile, "repeat");
    ctx.fillRect(0, 0, ctx.canvas.width + 256, ctx.canvas.height + 256);
    ctx.restore();
  }

  function vignette(ctx, strength = 0.35, color = "#000") {
    const { width: w, height: h } = ctx.canvas;
    const g = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, Math.hypot(w, h) * 0.6);
    g.addColorStop(0, rgba(color, 0));
    g.addColorStop(1, rgba(color, strength));
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  }

  // A texture drawn once (paper, a starfield, a painted backdrop): `paint(ctx, w, h)` runs on first use only.
  const cache = new Map();
  function once(key, w, h, paint) {
    if (!cache.has(key)) {
      const c = layer(w, h);
      paint(c.getContext("2d"), w, h);
      cache.set(key, c);
    }
    return cache.get(key);
  }

  // Build the film. `shots` carry id, start, dur (from shots.json) and a draw function:
  //   draw(ctx, s) with s = { t, local, p, dur, w, h }: t is film time, local is time inside the shot, p is 0..1.
  // Neighbouring shots cross-fade over `blend` seconds. `post(ctx, t)` runs last on every frame (grain, vignette).
  // Returns the paused timeline; add DOM tweens to it, then register it as the last line of the build.
  function film({ canvas, duration, shots, blend = 0.35, post = null, background = "#000" }) {
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    const buffer = layer(w, h), bctx = buffer.getContext("2d");
    const order = shots.slice().sort((a, b) => a.start - b.start);
    const state = { t: 0 };

    function drawShot(target, shot, t) {
      const local = t - shot.start;
      target.save();
      shot.draw(target, { t, local, p: clamp(local / shot.dur), dur: shot.dur, w, h });
      target.restore();
    }

    function frame() {
      const t = state.t;
      ctx.save();
      ctx.fillStyle = background;
      ctx.fillRect(0, 0, w, h);
      ctx.restore();
      let i = order.findIndex((s) => t < s.start + s.dur);
      if (i < 0) i = order.length - 1;
      const cur = order[i], next = order[i + 1];
      drawShot(ctx, cur, t);
      const into = next ? t - (next.start - blend) : -1;
      if (next && blend > 0 && into > 0) {
        bctx.clearRect(0, 0, w, h);
        drawShot(bctx, next, t);
        ctx.save();
        ctx.globalAlpha = ease.sine(clamp(into / blend));
        ctx.drawImage(buffer, 0, 0);
        ctx.restore();
      }
      if (post) {
        ctx.save();
        post(ctx, t);
        ctx.restore();
      }
    }

    const tl = gsap.timeline({ paused: true });
    tl.to(state, { t: duration, duration, ease: "none", onUpdate: frame }, 0);
    frame();
    return tl;
  }

  window.Studio = { TAU, rng, hash, noise, fbm, clamp, lerp, smooth, span, ease, rgba, mix, layer, grain, vignette,
    once, film };
})();
