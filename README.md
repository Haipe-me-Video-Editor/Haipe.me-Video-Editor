# Haipe.me Video Editor

A skill and engine for any AI coding agent that edits talking-head video like a professional editor. Drop a clip,
say "edit this video", and your agent cuts it, captions it, adds motion graphics, B-roll and music, renders a 9:16 video
and checks its own work.

## What it does

- **Cuts:** silences, fillers and retakes, tight sentence-to-sentence jump cuts, punch-ins on faces.
- **Captions:** accurate transcripts in English, Arabic or both (bilingual), translated by meaning.
- **Motion graphics:** built-in cards (hook, stat, list, quote, ticker, headline, chapter, outro), explainer
  desks with the speaker cut out, slam titles, stickers, and any custom HyperFrames composition.
- **Signature effects:** 30 code-built effects (text behind the head, frosted type, charts, checklists, camera
  moves, product orbits, paper collage, sticker and neon outlines, freeze-frame callouts, colour pop, film look,
  beat shake, glitch and datamosh, motion trails, and more).
- **Named styles:** minimal storytelling (speaker in black and white on black, line-art cards) and kinetic
  transparent captions (big words behind the head that land on the voice), rapid visual explainer (split screen,
  a new visual on every phrase: screen recordings with a moving cursor, terminal and code cards, ranked lists).
- **B-roll:** from your own library, or free stock (Mixkit, Internet Archive, Wikimedia Commons) with AI clips
  filtered out.
- **Sound:** free music from Mixkit, Incompetech, Jamendo, ccMixter and more (commercial-safe licences only, credits
  written for you), music ducked under speech, sound effects tied to what is on screen, studio voice restoration,
  -14 LUFS delivery.
- **Look:** per-shot colour correction, face retouch, event recaps cut on the beat.
- **Style picker:** reads the footage (shot size, movement, the room) and the talk (tools, money, a story, a
  product, steps) and picks the editing style and a varied set of effects, so you never have to choose.
- **Covers and thumbnails:** picks the frame with the best real expression, cuts you out and builds covers for
  Reels, YouTube and square feeds, with colours set against yours, words sized to read at grid size, nothing
  under the app's buttons, and a preview of how they look on a phone.
- **Animated films:** a short explainer or story where every frame is drawn in code and the sound is made in
  code, from a topic and a few style references. The agent researches the facts, writes a style bible and a shot
  list, draws each shot, checks snapshots against the bible and renders a checked MP4.
- **Review:** a scored self-review, frame checks around every cut, and a critic pass before delivery.
- **Extras:** several reels from one long video (Clip Factory), no-cut subtitle copies, research-first scripts,
  real app screen captures.

## Free tools only

ffmpeg, Chromium, faster-whisper / WhisperX, open models for cut-outs, tracking, slow motion and upscaling, and
free-licence music and stock. No subscriptions, no paid APIs, no accounts or keys, no AI voices and no AI-generated
video: AI models only analyse your real footage.

## Install

New here? Read `GUIDE.pdf`: seven short pages, in English and Arabic, from install to your first finished video.
In short: open your AI coding agent (Claude Code, Codex or any other), paste this repo's link and ask it to install
it, ask it to interview you, then give it a video (a file on your computer, or a Google Drive or Dropbox link shared
with "anyone with the link"). No accounts or keys are needed. AI agents: read `AGENTS.md` first.


You need macOS or Linux (on Windows use WSL2), Python 3.11 to 3.13, Node.js 20+, ffmpeg with libass, git and an AI
coding agent (Claude Code, Codex or any other). Your agent can install the rest for you.
Then:

```bash
git clone https://github.com/Haipe-me-Video-Editor/Haipe.me-Video-Editor.git
cd Haipe.me-Video-Editor
bash scripts/setup.sh
```

Full steps (disk, models, optional keys, plugin install): `docs/INSTALL.md`.

## The interview

Before the first edit, ask the agent to interview you. It asks about ten short questions (who you are, your
audience, your look, pacing, music, what never to do) and saves the answers to a profile outside the repo, read
before every edit. `python -m editor profile` shows it. The questions are in `docs/interview.md`.

## The skills

- `skills/edit-video/SKILL.md`: the master editing skill. The agent follows it for every edit.
- `skills/animate/SKILL.md`: animated films drawn in code (`animate-new`, `animate-snap`, `animate-sound`,
  `animate-render`), with a finished example in `skills/animate/examples/sunset/`.
- `skills/hyperframes-core`, `skills/hyperframes-animation`, `skills/talking-head-recut`: vendored HyperFrames
  skills for custom motion graphics (Apache-2.0, see `NOTICE`).
- Presets in `docs/presets/`: finance and markets, event recaps, research-first scripting.

## Brand packs

Built-in styles are neutral: `--style default` and `--style finance`. To edit for your own brand, add a pack:

- `brands/<brand>/style.json`: fonts, colours, caption and kit settings (copy `editor/styles/default.json`).
- `brands/<brand>/preset.md`: the brand's look and rules.
- `skills/<brand>-video/SKILL.md`: "follow `edit-video`, then apply these overrides".

Then pass `--style <brand>`. Set `EDITOR_BRANDS` to keep your brand packs in another folder. The public repo ships
no brand packs; keep yours private.

## Licence

MIT (`LICENSE`). Third-party notices are in `NOTICE`. Never commit footage, music, models or secrets.
