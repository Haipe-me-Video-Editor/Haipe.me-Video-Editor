// Why the sky turns orange at sunset. Flat gouache on paper, warm light, the camera holds in every shot.
const S = Studio;

const PALETTE = {
  ink: "#1b1a2e",
  paper: "#f3ede2",
  skyTop: "#4f93c8",
  skyLow: "#c4e2ee",
  sea: "#2a5f8c",
  seaDeep: "#173a5c",
  sun: "#ffd66e",
  blue: "#78c2ff",
  orange: "#f08a3c",
  red: "#c8442f",
  dusk: "#3a2a5a",
};

// Paper fibre, painted once at quarter size and laid over every shot.
function paper(ctx, s, alpha = 0.16) {
  const tex = S.once("paper", 270, 480, (g, w, h) => {
    const img = g.createImageData(w, h);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        const v = 200 + 55 * S.fbm(x / 9, y / 9, 4, 3);
        const i = (y * w + x) * 4;
        img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
        img.data[i + 3] = 255;
      }
    g.putImageData(img, 0, 0);
  });
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.globalCompositeOperation = "multiply";
  ctx.drawImage(tex, 0, 0, s.w, s.h);
  ctx.restore();
}

function vgrad(ctx, s, stops, y0 = 0, y1 = s.h) {
  const g = ctx.createLinearGradient(0, y0, 0, y1);
  stops.forEach(([k, c]) => g.addColorStop(k, c));
  ctx.fillStyle = g;
  ctx.fillRect(0, y0, s.w, y1 - y0);
}

function disc(ctx, x, y, r, color, glow = 0) {
  if (glow) {
    const g = ctx.createRadialGradient(x, y, r * 0.8, x, y, r * glow);
    g.addColorStop(0, S.rgba(color, 0.45));
    g.addColorStop(1, S.rgba(color, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, r * glow, 0, S.TAU);
    ctx.fill();
  }
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, S.TAU);
  ctx.fill();
}

// Sea with seeded shimmer strokes that slide sideways with time.
function sea(ctx, s, top, colors, shimmer, shimmerX = s.w / 2, spread = 260) {
  vgrad(ctx, s, colors, top, s.h);
  const r = S.rng(42);
  ctx.lineCap = "round";
  for (let i = 0; i < 70; i++) {
    const depth = r();
    const y = top + 20 + depth * depth * (s.h - top - 40);
    const near = Math.abs(r() - 0.5) * 2;
    const x = shimmerX + (r() - 0.5) * spread * (0.4 + depth * 1.6) + Math.sin(s.t * 1.3 + i) * 14;
    const len = 30 + r() * 90 * (0.5 + depth);
    ctx.strokeStyle = S.rgba(shimmer, (0.25 + 0.5 * (1 - near)) * (0.6 + 0.4 * Math.sin(s.t * 2.1 + i * 1.7)));
    ctx.lineWidth = 3 + depth * 6;
    ctx.beginPath();
    ctx.moveTo(x - len / 2, y);
    ctx.lineTo(x + len / 2, y);
    ctx.stroke();
  }
}

// A light packet: a short wave drawn along a direction.
function squiggle(ctx, x, y, angle, len, color, alpha, phase) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.strokeStyle = S.rgba(color, alpha);
  ctx.lineWidth = 6;
  ctx.lineCap = "round";
  ctx.beginPath();
  for (let i = 0; i <= 24; i++) {
    const u = i / 24;
    const px = (u - 0.5) * len, py = Math.sin(u * S.TAU * 2 + phase) * 9;
    i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  }
  ctx.stroke();
  ctx.restore();
}

const BANDS = ["#e5484d", "#f08a3c", "#f7cf4a", "#6cc070", "#78c2ff", "#6b6fe0"];

const DRAW = {
  noon(ctx, s) {
    vgrad(ctx, s, [[0, PALETTE.skyTop], [1, PALETTE.skyLow]], 0, 1320);
    const sy = 560 + Math.sin(s.t * 0.8) * 6;
    // rays: dashed strokes that travel down from the sun
    ctx.save();
    ctx.setLineDash([60, 46]);
    ctx.lineDashOffset = -s.t * 160;
    ctx.lineCap = "round";
    for (let i = 0; i < 9; i++) {
      const a = Math.PI / 2 + (i - 4) * 0.16;
      ctx.strokeStyle = S.rgba(PALETTE.paper, 0.55);
      ctx.lineWidth = 7;
      ctx.beginPath();
      ctx.moveTo(540 + Math.cos(a) * 190, sy + Math.sin(a) * 190);
      ctx.lineTo(540 + Math.cos(a) * 900, sy + Math.sin(a) * 900);
      ctx.stroke();
    }
    ctx.restore();
    disc(ctx, 540, sy, 130 * (0.92 + 0.08 * S.span(s.local, 0, 0.8, S.ease.back)), PALETTE.sun, 2.3);
    sea(ctx, s, 1320, [[0, PALETTE.sea], [1, PALETTE.seaDeep]], PALETTE.paper, 540, 200);
    paper(ctx, s);
  },

  scatter(ctx, s) {
    vgrad(ctx, s, [[0, "#1c2a46"], [1, "#24395e"]]);
    const beamY = 960, head = S.lerp(-80, s.w + 200, S.span(s.local, 0, 1.6, S.ease.out));
    const r = S.rng(7);
    const mols = [];
    for (let i = 0; i < 46; i++) {
      const x = 60 + r() * 960, y = 380 + r() * 1160;
      mols.push({ x: x + 10 * Math.sin(s.t * 2 + i), y: y + 10 * Math.cos(s.t * 1.7 + i * 2), r: 9 + r() * 9,
        dir: r() * S.TAU, near: Math.abs(y - beamY) < 130 });
    }
    // the beam: six colour bands; blue and violet thin out the further they travel
    const bandH = 16;
    BANDS.forEach((c, i) => {
      const y = beamY - (BANDS.length / 2) * bandH + i * bandH;
      const g = ctx.createLinearGradient(0, 0, s.w, 0);
      const lose = i >= 4 ? 0.82 : 0.08;
      g.addColorStop(0, S.rgba(c, 0.95));
      g.addColorStop(1, S.rgba(c, 0.95 * (1 - lose)));
      ctx.fillStyle = g;
      ctx.fillRect(0, y, Math.max(0, head), bandH);
    });
    for (const m of mols) {
      ctx.fillStyle = S.rgba(PALETTE.paper, m.near ? 0.9 : 0.45);
      ctx.beginPath();
      ctx.arc(m.x, m.y, m.r, 0, S.TAU);
      ctx.fill();
      if (!m.near || head < m.x) continue;
      // the beam reached this molecule: blue light leaves it in its own direction
      const since = s.local - ((m.x + 80) / (s.w + 280)) * 1.6 * 0.55;
      for (let k = 0; k < 2; k++) {
        const age = since - k * 0.45;
        if (age <= 0) continue;
        const d = 40 + age * 420, a = m.dir + k * 2.1;
        squiggle(ctx, m.x + Math.cos(a) * d, m.y + Math.sin(a) * d, a, 70, PALETTE.blue,
          S.clamp(1 - age / 1.6) * 0.95, s.t * 10);
      }
    }
    paper(ctx, s, 0.1);
  },

  path(ctx, s) {
    vgrad(ctx, s, [[0, PALETTE.ink], [1, "#2a2950"]]);
    const r = S.rng(99);
    for (let i = 0; i < 90; i++) {
      const x = r() * s.w, y = r() * 900, tw = 0.4 + 0.6 * S.noise(i, s.t * 1.5, 5);
      ctx.fillStyle = S.rgba(PALETTE.paper, 0.6 * tw);
      ctx.fillRect(x, y, 3, 3);
    }
    const cx = 540, cy = 2600, R = 1500, A = 1640;
    ctx.fillStyle = S.rgba(PALETTE.blue, 0.22);
    ctx.beginPath();
    ctx.arc(cx, cy, A, 0, S.TAU);
    ctx.fill();
    disc(ctx, cx, cy, R, "#2f6a8f");
    // the viewer standing on top of the Earth
    disc(ctx, 540, 1092, 16, PALETTE.paper);
    // noon: straight down, a short trip through the air
    const noon = S.span(s.local, 0.1, 0.7);
    ctx.lineCap = "round";
    ctx.strokeStyle = S.rgba(PALETTE.sun, 0.95);
    ctx.lineWidth = 12;
    ctx.beginPath();
    ctx.moveTo(540, 600);
    ctx.lineTo(540, S.lerp(600, 1070, noon));
    ctx.stroke();
    disc(ctx, 540, 560, 54, PALETTE.sun, 2);
    // sunset: in from the side, a long trip through the air, losing its blue on the way
    const set = S.span(s.local, 0.9, 1.4);
    const x1 = S.lerp(0, 520, set);
    const g = ctx.createLinearGradient(0, 0, 520, 0);
    g.addColorStop(0, PALETTE.paper);
    g.addColorStop(0.5, "#ffd08a");
    g.addColorStop(1, PALETTE.orange);
    ctx.strokeStyle = g;
    ctx.beginPath();
    ctx.moveTo(0, 1092);
    ctx.lineTo(x1, 1092);
    ctx.stroke();
    for (let i = 0; i < 6; i++) {
      const born = 0.9 + i * 0.2, age = s.local - born;
      if (age <= 0) continue;
      const x = 40 + i * 80, a = -Math.PI / 2 + (i % 2 ? 0.5 : -0.5);
      squiggle(ctx, x + Math.cos(a) * age * 300, 1092 + Math.sin(a) * age * 300, a, 54, PALETTE.blue,
        S.clamp(1 - age / 1.4), s.t * 10);
    }
    disc(ctx, -20, 1092, 70, PALETTE.orange, 2.2);
    paper(ctx, s, 0.1);
  },

  sunset(ctx, s) {
    const horizon = 1300;
    vgrad(ctx, s, [[0, PALETTE.dusk], [0.38, "#8e3b5a"], [0.6, PALETTE.red], [0.82, PALETTE.orange], [1, "#ffcf7a"]],
      0, horizon);
    // long low clouds, lit from below
    const r = S.rng(5);
    for (let i = 0; i < 5; i++) {
      const y = 380 + r() * 620, w = 380 + r() * 420, x = ((r() * 1400 + s.t * (12 + i * 5)) % 1500) - 200;
      ctx.fillStyle = S.rgba(i % 2 ? "#e9846b" : "#f3a76b", 0.55);
      ctx.beginPath();
      ctx.ellipse(x, y, w / 2, 22 + r() * 16, 0, 0, S.TAU);
      ctx.fill();
    }
    const sy = S.lerp(1140, 1330, S.span(s.local, 0, s.dur, S.ease.sine));
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, s.w, horizon);
    ctx.clip();
    disc(ctx, 540, sy, 150, "#ffb347", 2.6);
    ctx.restore();
    // three birds crossing
    for (let i = 0; i < 3; i++) {
      const bx = S.lerp(-60, 1140, (s.local / s.dur) * 0.9 + i * 0.12), by = 620 + i * 60 + Math.sin(s.t + i) * 10;
      const flap = Math.sin(s.t * 9 + i * 2) * 14;
      ctx.strokeStyle = S.rgba(PALETTE.ink, 0.85);
      ctx.lineWidth = 5;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(bx - 26, by - flap);
      ctx.quadraticCurveTo(bx - 10, by - 8, bx, by);
      ctx.quadraticCurveTo(bx + 10, by - 8, bx + 26, by - flap);
      ctx.stroke();
    }
    sea(ctx, s, horizon, [[0, "#5a2d4a"], [1, "#21182e"]], "#ffb15c", 540, 150);
    paper(ctx, s);
  },
};

function buildFilm() {
  const shots = FILM.shots.map((shot) => ({ ...shot, draw: DRAW[shot.id] }));
  const tl = S.film({
    canvas: document.getElementById("film"),
    duration: FILM.duration,
    shots,
    blend: FILM.blend,
    background: PALETTE.ink,
    post: (ctx, t) => {
      S.vignette(ctx, 0.3);
      S.grain(ctx, t, 0.05, FILM.fps);
    },
  });
  FILM.shots.forEach((shot, i) => {
    const el = document.getElementById(`w-${shot.id}`);
    tl.fromTo(el, { opacity: 0, y: 36 }, { opacity: 1, y: 0, duration: 0.7, ease: "power3.out" }, shot.start + 0.25);
    if (i < FILM.shots.length - 1) tl.to(el, { opacity: 0, y: -20, duration: 0.4, ease: "power2.in" }, shot.start + shot.dur - 0.45);
  });
  tl.fromTo("#credit", { opacity: 0 }, { opacity: 0.8, duration: 0.8 }, 9.6);
  return tl;
}
