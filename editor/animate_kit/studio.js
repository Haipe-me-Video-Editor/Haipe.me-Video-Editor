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

  // ---- one take: values that carry from beat to beat --------------------------------------------------------------
  // A value over time from keys [[t0, v0], [t1, v1], ...] (sorted by time). A value is a number, a hex colour or an
  // object of numbers and colours; each segment eases with `fn` (or the key's own third entry). Before the first key
  // it holds v0, after the last it holds the last value: a property is defined at every moment of the film.
  function keys(t, list, fn = ease.inOut) {
    if (!list.length) throw new Error("Studio.keys needs at least one key");
    if (t <= list[0][0]) return list[0][1];
    for (let i = 1; i < list.length; i++) {
      const [t1, v1, f] = list[i];
      if (t <= t1) {
        const [t0, v0] = list[i - 1];
        return blendValue(v0, v1, (f || fn)(clamp((t - t0) / Math.max(t1 - t0, 1e-6))));
      }
    }
    return list[list.length - 1][1];
  }

  function blendValue(a, b, k) {
    if (typeof a === "number") return lerp(a, b, k);
    if (typeof a === "string") return a === b ? a : mix(a, b, k);
    const out = {};
    for (const key of Object.keys(a)) out[key] = key in b ? blendValue(a[key], b[key], k) : a[key];
    for (const key of Object.keys(b)) if (!(key in a)) out[key] = b[key];
    return out;
  }

  // One shape growing into the next: a box is { x, y, w, h, r, fill, alpha } (x, y its centre, r its corner radius;
  // a dot is a box with r = w / 2). morph(a, b, k) passes through every size between, so a dot becomes a cursor, the
  // cursor a field, the field a window, with nothing cut in between.
  const morph = (a, b, k) => blendValue({ r: 0, alpha: 1, ...a }, { r: 0, alpha: 1, ...b }, clamp(k));

  function box(ctx, b, stroke = null, lineWidth = 0) {
    const r = Math.max(0, Math.min(b.r || 0, b.w / 2, b.h / 2));
    ctx.save();
    ctx.globalAlpha *= b.alpha === undefined ? 1 : b.alpha;
    ctx.beginPath();
    ctx.roundRect(b.x - b.w / 2, b.y - b.h / 2, b.w, b.h, r);
    if (b.fill) {
      ctx.fillStyle = b.fill;
      ctx.fill();
    }
    if (stroke && lineWidth) {
      ctx.strokeStyle = stroke;
      ctx.lineWidth = lineWidth;
      ctx.stroke();
    }
    ctx.restore();
  }

  // The camera of a one-take film is one path over the whole film, so it never resets at a shot's edge:
  // camera(t) -> { x, y, zoom, rot } (the point it looks at, how close, a tilt in degrees). Shots draw in world
  // coordinates, where the frame's centre at zoom 1 is (w / 2, h / 2).
  function applyCamera(ctx, cam, w, h) {
    ctx.translate(w / 2, h / 2);
    ctx.rotate(((cam.rot || 0) * Math.PI) / 180);
    ctx.scale(cam.zoom || 1, cam.zoom || 1);
    ctx.translate(-(cam.x === undefined ? w / 2 : cam.x), -(cam.y === undefined ? h / 2 : cam.y));
  }

  // Build the film. `shots` carry id, start, dur (from shots.json) and a draw function:
  //   draw(ctx, s) with s = { t, local, p, dur, w, h, cam }: t is film time, local is time inside the shot, p is 0..1.
  // Neighbouring shots cross-fade over `blend` seconds (a one-take film uses 0: each shot hands its last frame to the
  // next). `camera(t)` (optional) moves the whole film; `s.screen(fn)` draws fn(ctx) in frame coordinates, outside
  // the camera (a HUD, a caption plate). `post(ctx, t)` runs last on every frame (grain, vignette).
  // `background: null` leaves the canvas transparent, to draw over <video> clips placed under it.
  // Returns the paused timeline; add DOM tweens to it, then register it as the last line of the build.
  function film({ canvas, duration, shots, blend = 0.35, post = null, background = "#000", camera = null }) {
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    const buffer = layer(w, h), bctx = buffer.getContext("2d");
    const order = shots.slice().sort((a, b) => a.start - b.start);
    const state = { t: 0 };

    function drawShot(target, shot, t) {
      const local = t - shot.start;
      const cam = camera ? camera(t) : null;
      target.save();
      if (cam) applyCamera(target, cam, w, h);
      const screen = (fn) => {
        target.save();
        target.setTransform(1, 0, 0, 1, 0, 0);
        fn(target);
        target.restore();
      };
      shot.draw(target, { t, local, p: clamp(local / shot.dur), dur: shot.dur, w, h, cam, screen });
      target.restore();
    }

    function frame() {
      const t = state.t;
      if (background) {
        ctx.save();
        ctx.fillStyle = background;
        ctx.fillRect(0, 0, w, h);
        ctx.restore();
      } else {
        ctx.clearRect(0, 0, w, h); // a transparent layer over video clips or DOM
      }
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
    once, keys, morph, box, applyCamera, film };
})();
