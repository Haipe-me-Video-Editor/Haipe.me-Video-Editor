// How each shot looks. Timing lives in shots.json (copied into timing.js by the engine); this file only draws.
// Draw every frame from time alone: s.t (film time), s.local (seconds into the shot; negative while the shot fades
// in over the one before it), s.p (0..1 through the shot). Seeded randomness only: Studio.rng(seed).
// A shot with no draw function shows a loud placeholder in snapshots, and `animate-render` refuses the film.
const S = Studio;

const PALETTE = {
  // the style bible's colours, by name
  ink: "#14110f",
  paper: "#f3ede2",
  accent: "#e4572e",
};

function placeholder(id, what) {
  return function (ctx, s) {
    ctx.fillStyle = S.mix("#2a2a2a", "#3a3a3a", s.p);
    ctx.fillRect(0, 0, s.w, s.h);
    ctx.fillStyle = "#ff3df2";
    ctx.font = `${Math.round(s.w / 14)}px sans-serif`;
    ctx.textAlign = "center";
    ctx.fillText(`${id}: not drawn yet`, s.w / 2, s.h / 2);
    ctx.font = `${Math.round(s.w / 32)}px sans-serif`;
    ctx.fillText(what || "", s.w / 2, s.h / 2 + s.w / 12);
  };
}

const DRAW = {
  // one entry per shot in shots.json:
$DRAW
};

// Called once the fonts are ready (index.html registers the timeline this returns).
function buildFilm() {
  const shots = FILM.shots.map((shot) => ({ ...shot, draw: DRAW[shot.id] || placeholder(shot.id, shot.what) }));
  const tl = S.film({
    canvas: document.getElementById("film"),
    duration: FILM.duration,
    shots,
    blend: FILM.blend,
    background: PALETTE.ink,
    post: (ctx, t) => {
      S.vignette(ctx, 0.28);
      S.grain(ctx, t, 0.05, FILM.fps);
    },
  });
  // Words on screen are DOM text in #words, tweened on this same timeline, for example:
  // tl.from("#title", { opacity: 0, y: 40, duration: 0.7, ease: "power3.out" }, 1.2);
  return tl;
}
