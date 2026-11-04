// A reel, from one dot, in one take. Every shape grows out of the one before it, and every carried value is driven
// by film time (s.t) through Studio.keys, so a shot's last frame and the next shot's first frame are the same frame.
const S = Studio;

const PALETTE = {
  night: "#1e1e28",
  accent: "#ff5a36",
  screen: "#2a2a36",
  rim: "#4a4a5e",
  takes: ["#ff5a36", "#ffb347", "#4fb3a9", "#7b8cff"],
};

const CX = 540, CY = 980;          // the world's centre: the dot sits here at the start and the end
const BEAT = 0.5;                  // 120 bpm, the same tempo as sound.json's beat
const SLOT = (i) => CX + (i - 1.5) * 128;  // where take i sits on the timeline

// The record button: a dot that breathes, swells into a button, then stretches into the phone screen.
function button(t) {
  const breathe = 1 + 0.12 * Math.sin(t * 5) * (1 - S.span(t, 1.2, 0.5));
  return S.keys(t, [
    [0, { x: CX, y: CY, w: 28 * breathe, h: 28 * breathe, r: 14 * breathe, fill: PALETTE.accent, alpha: 1 }],
    [1.3, { x: CX, y: CY, w: 28, h: 28, r: 14, fill: PALETTE.accent, alpha: 1 }],
    [2.0, { x: CX, y: CY, w: 240, h: 240, r: 120, fill: PALETTE.accent, alpha: 1 }, S.ease.back],
    [3.2, { x: CX, y: CY, w: 240, h: 240, r: 120, fill: PALETTE.accent, alpha: 1 }],
    [4.4, { x: CX, y: CY, w: 580, h: 980, r: 64, fill: PALETTE.screen, alpha: 1 }, S.ease.inOut],
    [7.6, { x: CX, y: CY, w: 580, h: 980, r: 64, fill: PALETTE.screen, alpha: 1 }],
    [8.4, { x: CX, y: CY, w: 640, h: 1080, r: 72, fill: PALETTE.night, alpha: 0 }],
  ]);
}

// Take i: slides onto the timeline, stands up as a bar that jumps on the beat, then folds back into the dot.
function take(i, t) {
  const land = 4.9 + i * 0.6;
  const base = { x: SLOT(i), y: CY + 260, w: 116, h: 64, r: 14, fill: PALETTE.takes[i], alpha: 1 };
  const k = Math.max(0, t - 8.0) / BEAT;                  // beats since the bars stood up
  const hit = t > 8.0 && k < 3.9 ? Math.exp(-4 * (k % 1)) * (0.55 + 0.45 * Math.abs(Math.sin(i * 1.7 + Math.floor(k)))) : 0;
  const bar = { x: SLOT(i), y: CY, w: 84, h: 220 + 320 * hit, r: 42, fill: PALETTE.takes[i], alpha: 1 };
  return S.keys(t, [
    [land - 0.35, { ...base, x: SLOT(i) - 90, alpha: 0 }],
    [land, base, S.ease.out],
    [7.6, base],
    [8.2, { ...bar, h: 220 }, S.ease.back],
    [10.0, bar],
    [10.7, { x: CX + (i - 1.5) * 34, y: CY, w: 34, h: 12, r: 6, fill: PALETTE.accent, alpha: 1 }, S.ease.inOut],
    [11.6, { x: CX, y: CY, w: 28, h: 28, r: 14, fill: PALETTE.accent, alpha: 1 }, S.ease.inOut],
  ]);
}

// One camera for the whole film: holds, eases back for the phone, pushes in on the timeline, tilts on the beat.
function CAMERA(t) {
  const cam = S.keys(t, [
    [0, { x: CX, y: CY, zoom: 1.0, rot: 0 }],
    [1.8, { x: CX, y: CY, zoom: 1.15, rot: 0 }],
    [4.2, { x: CX, y: CY, zoom: 1.0, rot: 0 }],
    [7.2, { x: CX, y: CY + 40, zoom: 1.1, rot: 0 }],
    [8.3, { x: CX, y: CY, zoom: 1.1, rot: -3 }],
    [10.0, { x: CX, y: CY, zoom: 1.1, rot: 2 }],
    [11.6, { x: CX, y: CY, zoom: 1.0, rot: 0 }],
  ]);
  return cam;
}

function glow(ctx, b, strength) {
  if (strength <= 0) return;
  const r = Math.max(b.w, b.h) * 0.9 + 40;
  const g = ctx.createRadialGradient(b.x, b.y, 0, b.x, b.y, r);
  g.addColorStop(0, S.rgba(PALETTE.accent, 0.35 * strength));
  g.addColorStop(1, S.rgba(PALETTE.accent, 0));
  ctx.fillStyle = g;
  ctx.fillRect(b.x - r, b.y - r, 2 * r, 2 * r);
}

// The whole world at film time t. Every shot draws this; a shot only adds what lives inside it.
function world(ctx, s) {
  const t = s.t;
  ctx.fillStyle = PALETTE.night;
  ctx.fillRect(-s.w, -s.h, s.w * 3, s.h * 3);
  const b = button(t);
  const accentness = 1 - S.span(t, 3.2, 1.0);           // the glow belongs to the dot and the button
  glow(ctx, b, accentness);
  // the record ring: one pulse while the button sits, gone before the stretch
  const ring = S.span(t, 2.15, 0.9, S.ease.out);
  if (t > 2.1 && t < 3.3) {
    ctx.strokeStyle = S.rgba(PALETTE.accent, 0.6 * (1 - ring));
    ctx.lineWidth = 10;
    ctx.beginPath();
    ctx.arc(CX, CY, 130 + 120 * ring, 0, S.TAU);
    ctx.stroke();
  }
  S.box(ctx, b, S.rgba(PALETTE.rim, S.span(t, 3.4, 0.8) * (1 - S.span(t, 7.6, 0.6))), 6);
  // the timeline track inside the phone, there while the takes are
  const track = S.span(t, 4.4, 0.4) * (1 - S.span(t, 7.6, 0.4));
  if (track > 0) {
    S.box(ctx, { x: CX, y: CY + 260, w: 540, h: 92, r: 18, fill: "#353542", alpha: track });
    ctx.fillStyle = S.rgba("#f3ede2", 0.55 * track);   // the playhead sweeps across the takes
    const px = S.lerp(CX - 250, CX + 250, S.span(t, 4.9, 2.6, S.ease.linear));
    ctx.fillRect(px - 3, CY + 200, 6, 120);
  }
  for (let i = 0; i < 4; i++) {
    const k = take(i, t);
    if (k.alpha > 0.001) S.box(ctx, k);
  }
}

const DRAW = {
  dot(ctx, s) { world(ctx, s); },
  record(ctx, s) { world(ctx, s); },
  clips(ctx, s) { world(ctx, s); },
  beat(ctx, s) { world(ctx, s); },
  back(ctx, s) { world(ctx, s); },
};

function buildFilm() {
  const shots = FILM.shots.map((shot) => ({ ...shot, draw: DRAW[shot.id] }));
  const tl = S.film({
    canvas: document.getElementById("film"),
    duration: FILM.duration,
    shots,
    blend: FILM.blend,
    camera: CAMERA,
    background: PALETTE.night,
    post: (ctx, t) => {
      S.vignette(ctx, 0.3);
      S.grain(ctx, t, 0.04, FILM.fps);
    },
  });
  FILM.shots.forEach((shot, i) => {
    const el = document.getElementById(`w-${shot.id}`);
    tl.fromTo(el, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }, shot.start + 0.2);
    if (i < FILM.shots.length - 1) tl.to(el, { opacity: 0, y: -16, duration: 0.35, ease: "power2.in" }, shot.start + shot.dur - 0.45);
  });
  return tl;
}
