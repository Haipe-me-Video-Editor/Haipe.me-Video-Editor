---
name: animate
description: Make a short animated explainer or motion piece (a how-it-works film, a data story, a mood piece, visual effects and add-ons for an explanation) where every frame is drawn in code and the sound is synthesised, from a topic, a length, a format and a few style references. Researches the facts, writes a style bible and a shot list, draws each shot on a canvas, checks snapshots against the bible, then renders a checked MP4. No video or image model and no voice. Use when the user says "animate", "make an animation", "an animated explainer about X", "a cartoon of X", or shares a style reference and asks for a film in that look.
---

# Animate

The engine is in this plugin's root (two levels up). Run `python -m editor <command>` from there. On a fresh
container run `bash scripts/setup.sh` once.

## House rules

- **Everything is drawn in code.** Shapes, light, texture and motion come from `comp/shots.js` on a canvas. No
  video model, image model, stock footage or AI voice. Words on screen are real text.
- **References are for reading the style only.** Look at them, describe them in the style bible, and draw the film
  yourself. Never trace, copy or show a reference in the film (`animate-render` refuses a film that contains one).
- **Code drawing is for explainers, visual effects and add-ons, never for a character.** Diagrams, backgrounds,
  icons, hearts, sparkles, captions and logos are drawn in code. A character the user already has (a mascot, a
  brand figure) is never redrawn in code: code cannot reach the finish of their artwork, and a code redraw of one
  was rejected as "very bad art, it doesn't match" (2026-10-21).
- **A character the user owns is animated from its own renders.** Put the pose renders in `comp/art/` (not
  `refs/`), load them before the timeline is built (`Promise.all([document.fonts.ready, loadArt()])` in
  `index.html`), and move, squash and swap them pose to pose with the pivot at the feet; draw only the world and
  the effects around them in code.
- **Facts are checked.** An explainer states only what the research found, with a source for each fact.
- **Free tools only**, and nothing needs an account or a key.
- Work in a scratch folder, never inside the repo.

## What to ask for

A topic, a length (15 s is a good default), a format (`9:16`, `16:9`, `1:1`, `4:5`) and one to five style references:
a pin, a film frame, an illustration, a screenshot. Image files work best. If the user only describes a style, write
the style bible from their words and show stills before going further. Ask once, then go.

## Steps

1. **Scaffold.** `python -m editor animate-new <film> --topic "<topic>" --seconds 15 --format 9:16 --shots 5
   --refs <images...>`. Pick fonts with `--fonts` (the `--help` list; default Instrument Serif Italic and IBM Plex
   Mono). The folder holds `brief.json`, `style.md`, `shots.json`, `sound.json`, `refs/` and `comp/`.

2. **Style bible.** Open every image in `refs/` and look at it. Fill `style.md`: palette with hex values, shape and
   line, texture and light, motion, words on screen, a "never" list. Write each line so a frame can pass or fail it.

3. **Research.** For an explainer, search the web and confirm each fact in two sources. Put the facts and their
   sources under "Facts to get right". Keep only what the film will show.

4. **Shot list.** Edit `shots.json`: one idea per shot, 2 to 4 s each, shots back to back from 0 with no gaps (the
   engine refuses gaps and overlaps). Each shot has an `id` (a short word, used in `shots.js` and in sound cues), a
   `what` (what the frame shows), a `camera` (most shots: holds) and the `words` on screen (eight words or fewer).
   The last shot is the payoff, not a summary.

5. **Draw.** Write one draw function per shot in `comp/shots.js`, keyed by the shot id. Read
   `examples/sunset/shots.js` first: it is a finished 12 s film and shows every pattern below.
   - A frame is a function of time alone: `s.t` film time, `s.local` seconds into the shot (negative while the shot
     fades in over the last one), `s.p` 0..1 through the shot. Never `Date`, `performance.now()` or unseeded
     `Math.random()`: use `Studio.rng(seed)`, `Studio.noise`, `Studio.fbm`.
   - Per-pixel work (paper, painted backdrops, noise fields) goes inside `Studio.once(key, w, h, paint)`, which runs
     it a single time. Every frame only draws shapes and images, so the render stays fast.
   - Keep something moving in every shot (a drift, a shimmer, a breath). A still stretch over 1.5 s fails the check.
   - Words on screen are DOM text in `#words` (style and markup in `comp/index.html`), tweened on the timeline that
     `buildFilm()` returns. See `examples/sunset/words.html`.
   - Everything is local: no web fonts, no CDN scripts, no fetched images. The render refuses network loads.
   - `Studio` has `span(t, start, dur, ease)` for timed moves, `ease`, `mix` and `rgba` for colour, `grain` and
     `vignette` for finish (see `comp/studio.js`).

6. **Check snapshots, then fix.** `python -m editor animate-snap <film>` captures three frames per shot (early, middle,
   late) into `snaps/` and prints the contact sheets. Open every sheet. For each frame ask: does it match the style
   bible line by line, does it show the shot's `what`, are the words clear of the subject and inside the frame, does
   the subject read at phone size, is there visible change between a shot's three frames, are the facts drawn right.
   Fix `shots.js` and snap again until every frame passes. `--at 4.2,7.5` snaps exact moments.

7. **Sound.** Write `sound.json` (types and options are in `editor/synth.py`): a score of a `pad` plus an `arp` or
   `drone` in one key under the whole film, and an effect on each visual event, timed by shot id (`"at": "s3+0.2"`):
   `whoosh` for movement, `pop` for things appearing, `chime` for a reveal, `riser` into a payoff, `impact` for a
   landing, `wash` for water or wind, `hum` for wings or motors, `tick` for steps. Keep effects 6 to 12 dB above the
   score. A free-licence track the user supplies can go in as `{"type": "file", "path": ...}`. No voice.
   `python -m editor animate-sound <film>` writes `sound.wav` to check before the render.

8. **Render.** `python -m editor animate-render <film>` refuses a film with an undrawn shot or a copied reference,
   lints, renders, mixes the sound to -14 LUFS and runs `qc`. Fix anything qc fails and render again. Deliver
   `out/film.mp4`, and tell the user what the film shows, the facts and their sources, and the fonts used.

## Timing

On a 4-core machine with no GPU, a 12 s 1080x1920 film snaps in about 20 s and renders in about 70 s.
