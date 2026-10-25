---
name: edit-video
description: Edit talking-head video in English, Arabic or both like a professional editor — cuts silences, fillers and retakes; accurate captions in the spoken language, Arabic, English or bilingual; HyperFrames motion graphics; B-roll from the user's library; music ducked under speech; then renders and quality-checks a 9:16 video. Free tools only; real footage first. Use when the user drops or shares a clip, says "edit this video", "make a reel from this", or names this skill. If a brand skill (`<brand>-video`) matches the video, follow it too: it adds that brand's overrides on top of this skill.
---

# Edit video

The engine is in this plugin's root (two levels up). Run `python -m editor <command>` from there.
On a fresh container run `bash scripts/setup.sh` once. The work is automatic: never stop to ask
for approval mid-edit. Every creative decision goes in `edit.json` `notes`.
`run <project> <clip>` chains new, analyze, draft, captions, render and review with no planning.
It cannot fill translations, so for `ar`, `en` or `bilingual` captions use the steps below.

## House rules

- **Free tools only.** No subscriptions or paid services. Free-licence assets are fine. Nothing here needs an
  account, a sign-in or a key, and none is ever asked for.
- **Real footage only.** Graphics are made in code. AI *analysis* models (cut-outs, tracking, upscaling, slow motion)
  are fine: they process real footage. No AI-generated video, AI voices or AI stills.
- **Footage colour never changes**, on any edit, under any condition. See "Colour never
  changes" under the editing rules.
- **Samples before full renders.** Show stills or a 10-20 s sample to test a look; render the full video only as
  the deliverable. For taste calls (looks, music, voice), show options side by side and use what the user picks.
- **Never commit** footage, music, models or secrets. Never put a token in chat or in a file.
- HyperFrames runs locally only: no cloud render, no TTS, no API key, telemetry off.
- Work in a scratch folder, never inside the repo.

## Steps

0. **Creator profile.** `python -m editor profile`: if it shows one, its answers are the defaults for captions,
   style, pacing, music, sound and the "never" list (the user's words for this job win), and a correction from the
   user goes under its "Notes from edits". With no profile and a `docs/interview.md` in the repo (the public
   edition), offer that short interview first, once; if they skip it, use the defaults. The internal edition has no
   interview: the brief and the brand skill decide.
1. **Get the video.** A file path or a file dropped into the chat: use it. A share link (the agent runs in the cloud,
   or the video is on their phone): `python -m editor fetch "<link>" <scratch>/in` downloads it from Google Drive,
   Dropbox or a direct file link and checks it is a video. When it says the link opens a page, the file is not
   shared yet: tell them its words (Share, General access, "Anyone with the link", Copy link) and wait for the new
   link. Never ask for a password or for access to their account.
   Then `new <project> <clip> --brief "<the user's words>"`. It copies the profile into the project as `profile.md`.
2. `analyze <project> [--language ar|en] [--glossary <file>]`. Print every `note:` line to the user.
   If the speaker mixes Arabic and English, pass `--language ar` (auto-detect can route mixed speech to the English model).
3. **Correct the transcript.** Read `transcript_packed.md` and the glossary. Fix misheard names
   by replacing words one for one in `transcript.json` (never merge, split or retime), then
   run `align <project>`. Flag repeated phrases, text in silence and Latin script on Arabic audio.
4. `draft <project> --captions <mode> [--music-dir <dir>]`. Mode: what the user asked for;
   otherwise `source`. For an Arabic speaker and an English-speaking audience (or the reverse),
   use `bilingual`. It also writes `transcript_timeline.md`: the transcript in timeline seconds.
5. **Pick the style:** `style-pick <project>` reads the footage and the talk and writes `style-plan.json`: the
   named style that fits, the effects this footage can carry, how many, and the rhythm (hook, change every few
   seconds, a re-hook at the middle). Use it unless the user asked for a style, the profile's "never" list rules
   something out, or a brand skill says otherwise (brand rules always win for anything branded). Tell the user the
   style in one line. Never make a plain cut-and-captions edit unless they ask for one: every video gets the
   style's signature effects, varied.
   **Plan.** Read only `transcript_timeline.md`, `sheets/index.json` with its sheets, and `edit.json`
   (plus `transcript_packed.md` when you trim or reorder segments, which use source seconds).
   Never extract individual frames. Place graphics, B-roll and SFX from `transcript_timeline.md`.
   Edit `edit.json` by the rules below and save it with `editor.editjson.save`, which validates.
   After changing segments, run `timeline <project>` and re-read `transcript_timeline.md`.
6. **B-roll** (if the user has a library): `broll-index <broll_dir> <index>`,
   `broll-sheets <broll_dir> <index>` → view each sheet once →
   `broll-tag <index> <file> --tags a,b [--subject ..]`, then `broll-resolve <project> <broll_dir> <index>`.
   Free stock (see "Free stock footage") is mainly for finance explainers and talking-head videos, above all when
   the user asks for it.
   Before rendering, `style-pick <project> --check`: fix every `VARIETY:` line (a repeat, too few kinds, a flat
   stretch, no hook in the first 1.5 s), then check again.
7. `captions <project>`. If it asks for translations, fill `tr` on every line of
   `work/captions.json`: natural, short, same meaning, Western digits, glossary spellings.
8. `render <project>`. `--draft` for fast feedback rounds; `--master` for the delivered file (near-lossless at
   every step, CRF 10, 320k audio). Work from a small proxy of a huge camera file, then swap the project's
   source to a 1080 master made from the original (same frames, so every time stays) for the `--master` render.
9. **Scored self-review:** `critique <project>` → view each `review/item-NN.jpg` once, score it 1-10 against the
   rubric in `review/scores.json` (readable, not AI slop, placed with intent, physical motion, true words, no dead
   frames), fix and re-render anything under 8, run `critique` again (max 2 rounds), then `critique <project> --check`.
   `review <project>`. Fix every FAIL in `edit.json` or `work/captions.json` and re-render.
   View `sheets/final.jpg` and every `verify/cut-*.png` once: look for flashes at cuts,
   waveform spikes, captions hidden behind overlays, and wrong overlay frames. For anything
   to be published, spawn one critic sub-agent with the final video path, `edit.json` and the
   brief. Tell it to roast, not praise, and return ranked problems with timecodes and the 5
   fixes to do first. Apply them. At most 3 fix passes; then report what remains.
10. Append a section to `<project>/project.md`: strategy, decisions, open items. Deliver with
    `editor.deliver.gofile(out/final.mp4)` (a download page that works on phones) and also attach the file when it
    is under 30 MB. Public edition (`editor.config.EDITION == "public"`) on the user's own computer: give the local
    path instead, and upload only when the user or the profile's "Delivery" asks for a link (anyone with a Gofile
    link can open it: say so the first time). Deliver `out/final.mp4`, mention `out/final-nomusic.mp4`, and paste
    `out/notes.txt`.
11. **Cover.** For anything to be published, make the cover too (see "Covers and thumbnails"): run `cover` on the
    raw clip, view `preview.jpg` once, fix every problem it prints, and deliver the covers beside the video.

## Long raw with retakes (takes, selects)

A shoot file where the presenter says every line several times, with someone directing off camera, is not cut with
`draft`: first find the right take of each line.
- `python -m editor takes <raw> <dir>` transcribes the speech chunk by chunk (one Whisper pass over a half-hour file
  loops on a word and drops whole minutes), splits the presenter (on the lav) from the off-camera voice by level,
  keeps the **last complete take** of each line (earlier attempts, false starts and stumbles go), and tracks the head
  at every keyframe: a kept take said off the lens (reading) is marked COVER, to go under B-roll. It writes
  `takes.md` and `takes.json`; the transcript and the gaze are cached in `<dir>`.
- Read `takes.md` against the script's logic before cutting. It is a proposal: chat with the crew that repeats no
  line can look like a take, and a line can need its best halves from two takes. Fix picks with
  `--keep n,n --drop n,n`.
- `python -m editor selects <raw> <dir>` cuts the kept spans (0.4 s handles) from the camera original into one
  upright file (a camera on its side is detected and turned) and writes `selects.json`, the spans in that file's
  time. Make the project from the selects file.
- Joins measured on a professional cut of such a shoot: about 0.05 s before the first word, 0.10 s after the last,
  no pause over ~0.22 s left inside a take.

## Styles and presets

A style is a JSON file of design tokens (fonts, colours, caption settings, kit settings). Pass `--style <name>` to
`captions`, `render`, `review`, `kwcheck`, `reel-deliver` and `clips-render`. Built-in, neutral styles live in
`editor/styles/`: `default` (dark, orange accent) and `finance` (dark, blue accent, green up / red down). A path to
any `.json` file works too (relative `logo` paths resolve from the file's folder).

Presets are planning guides in `docs/presets/`:
- **Finance, markets, crypto:** read `docs/presets/finance.md` before planning; `--style finance` unless a brand
  style applies.
- **Event coverage / recaps (music only):** read `docs/presets/event-recap.md`. The footage keeps its camera colour
  (house rule): no grade.
- **Scripts before recording:** `docs/presets/research-script.md`.

## Brand packs

A brand gets its own pack, kept outside the engine:
- `brands/<brand>/style.json`: the brand's tokens, plus any brand look the effects read (`data_look`,
  `cover_story`, `cover_name`). `--style <brand>` finds it: a built-in name is looked up in `editor/styles/` first,
  then in `brands/<brand>/style.json`. Set `EDITOR_BRANDS` to keep the brands folder somewhere else.
- `brands/<brand>/preset.md` and its assets (logo, fonts, reference notes), and `brands/<brand>/glossary.txt`
  (names that must be spelled exactly; pass it to `analyze --glossary`).
- `skills/<brand>-video/SKILL.md`: a short skill that says "follow `edit-video`, then apply these overrides" and
  holds only the brand's recipe: its style name, allowed and forbidden effects, music and sound rules, and words on
  screen.

To add a brand: create `brands/<brand>/style.json` (copy a built-in style and change it), write
`brands/<brand>/preset.md`, then add `skills/<brand>-video/SKILL.md` with front matter whose description names the
brand ("Use for any <brand> video ..."). Brand material (names, colours, logos, handles, footage, links) never goes
into the engine, the built-in styles or this skill. When you learn something general while editing for a brand,
put it here, brand-free, and keep only the brand specifics in its own skill.

## No-cut subtitle copy (reel-prep / reel-deliver)

For a talking-head clip the user wants as recorded, with translated subtitles, retouch and studio voice:
1. `python -m editor reel-prep <clip> <work>` (starts the studio voice in the background; writes `<work>/words.md`).
2. Read `words.md`; write `<work>/subs.json` = `[[start, end, "line\\Nline"], ...]` (source seconds, one idea per cue,
   ≤ 2 lines of ≤ 21 chars, timed to the words; Whisper starts after a pause can be early). Translate by meaning
   in natural language, not word for word.
3. `python -m editor reel-deliver <clip> <work> <out> [--style <name>] [--upload]` → prints the master, the preview
   and a Gofile link (public edition on the user's computer: only with `--upload` or `EDITOR_UPLOAD=gofile`).
Send the master (or its Gofile link) and attach the preview; say the preview is compressed. List any phrase whose
meaning was a judgment call.

## Motion videos (no speaker) and overlays

`python -m editor motion <project> --dur <s> [--bg <loop.mp4> | --color <#hex>]` makes a silent base (a brand
loop looped to length, or a colour) with edit.json ready; add graphics, overlays, sfx and music, then `render`.
`overlays[]` composite a clip or image over the edit: `{file, at, dur, src_in?, key?: alpha|green, color?, x?, y?,
w?, flip?, layer?: over|under}`. `green` keys a green-screen clip (screen colour read from its corners); `alpha`
uses the file's transparency (.mov, VP8/VP9 .webm, .png). `w` is the width as a fraction of the frame, `x`/`y`
place its centre, `layer: "under"` puts it beneath the graphics. Use them for a character's clips, peeks, stingers
and logo end cards. `music.start` begins the track that many seconds in; music-only videos use `"lufs": -18`.
Kit extras: `wave` (the flowing-line background), `mark` (a logo mark end card, drawn from the style's `mark` bars), and on `stack` lines
`stroke: [colour, px]` and `ring: [colour, px]` for die-cut sticker lettering. `sticker` `{src, pos, w}` pops an
image (a logo, a character pose) in with a white die-cut edge. `title` `{text, sub?, pos?, tilt?, size?, seed?}` is a
slam title: a tilted halftone slab with an offset accent slab and a light border slams in, the word lands as
ransom-note tiles (one per Latin letter, one per Arabic word), `sub` hangs off the corner, and it jitters while it
holds while the dots drift and the accent slab sways; colours from the style's `title` {dark, accent, light}.
`letters: "sticker"` (spec or style) keeps the slab but sets the word in the brand's own face as solid letters set
like a heading, upright and the same size. A style can set `kit_fonts`, `pill_bg`/`pill_border`/`pill_radius`,
`wave`, `title`, `caption_outline`/`caption_outline_w` and `caption_active` {fill, outline, pop} for the spoken word.
Sound palettes beyond the defaults: playful (`boing plip bloop zip sparkle chime tada wahwah bonk wobble poof whoop
squeak`) and calm (`shimmer swell triad`). A brand's skill says which palette it uses.

## Real app screens (capture)

Never draw an app screen: capture it. `python -m editor capture <url> <out.png|.mp4> [--steps steps.json]
[--device phone|desktop]` opens the page in the local Chromium at phone size (390x693 CSS, 3x) and saves a sharp
screenshot, or a 1080x1920 recording from Chromium's screencast while `steps` run (`wait`, eased `scroll`, `tap` a
selector, `type`, extra `shot`s). Capture demo builds or public pages only, never a real customer's data, and never
an action that writes data on a live site (a sign-up, a cart, a purchase) without the owner's yes. Use the result
as B-roll, inside a phone frame, or as an orbit card.
When the speaker names a website or a page, show it: record it with a `point` step on the exact words they talk
about (`{"point": "text=Editing playbook", "dur": 0.8, "zoom": 2}`: a drawn cursor glides there, the page zooms in
and centres it so it is readable; `unzoom` eases back), timed so the zoom lands on the word.

## Face retouch

For a talking head, offer it; preset `natural` is the tested default:
`python -m editor retouch <clip> <out.mp4> [--preset natural|gentle] [--ass <captions.ass>]`. Run it on the source clip
before `new` (it keeps audio, outputs 1080x1920). Leave edit.json `retouch` at 0.

## Clip Factory (several reels from one long video)

`python -m editor clips-prep <video> <work>` → read `<work>/transcript.md`, pick 20-60 s self-contained moments
(strongest line first, no setup needed to follow), write `<work>/clips.json` `[{"name", "start", "end", "title"?}]`
(title ≤ 2 lines of 15 chars, `\\N` between) and `<work>/subs.json` (cues for those ranges, same rules as
`reel-prep`: one idea per cue, ≤ 2 lines of ≤ 21 chars, timed to the words).
`python -m editor clips-render <video> <work> <out> [--only names] [--voice studio|original] [--no-retouch]
[--style <name>]`: cut, 9:16 reframe on the face for wide sources, retouch + subtitles + title, studio voice per
clip, HQ + preview and a Gofile link each (public edition: the link with `--upload`). Studio voice is ~9 s per
second of clip on CPU: a 30 s clip takes ~6 min.

## Free music

When the user has no track of their own (and no brand music), `python -m editor music-find "<mood or genre>" <dir>
[--sources mixkit incompetech openverse ccmixter] [--n 3] [--min-dur 20]` downloads a few candidates from each free
library: Mixkit (no credit needed), Incompetech (Kevin MacLeod) and CC0 / CC BY music through Openverse (Jamendo,
ccMixter, Freesound, Wikimedia Commons) and ccMixter. Only licences a commercial video can use pass: non-commercial,
no-derivatives and share-alike tracks are refused. Each file is recorded in `<dir>/credits.json`; `draft --music-dir
<dir>` picks from the folder and carries a CC BY track's credit line to `out/credits.txt`: paste it into the post's
caption. Prefer Mixkit and CC0 for ads and posts where a caption credit is awkward. Pick by mood, not by name: check
the tempo and energy, start on a bar (`music.start`), and cut on the beat. A library that is down is skipped.

## Free stock footage

`python -m editor stock "<query>" <dir> [--sources mixkit archive commons] [--portrait]` lists hits,
writes `hits.json` and `sheet.jpg` (view it once), then `python -m editor stock-get <dir> <numbers>` downloads them
(licences and authors in `<dir>/credits.json`; credit Commons and Archive CC-BY/BY-SA authors in the caption).
AI-generated clips and NC/ND licences are filtered out. Pexels and NASA are not used. Concrete one- or two-word
queries work best. Then index the folder with `broll-index` as usual. None of these sources needs an account or a key.


**No dubbing or AI voices.** Subtitles are the way to reach speakers of another language.

## Covers and thumbnails

The cover decides whether anyone taps, so it is part of every delivery.
`python -m editor cover <raw clip> <out_dir> --title "3 to 5 words" [--accent <word> ...] [--sub "small line"]
[--style <brand>] [--layouts punch frame minimal object] [--sizes reel youtube square] [--at <seconds>]
[--image product.png] [--video-title "<the video's title>"]`

Run it on the **raw clip**, never the finished edit: a frame from the edit can catch the speaker inside a card or a
window, and the cut-out then carries its straight edges. It scores 40 frames for expression and sharpness, cuts the
speaker out of the best one, builds each layout at each size, checks it, and writes `cover-<layout>-<size>.jpg`,
`covers.json` (the frame and every problem) and `preview.jpg` (the covers at profile-grid, sidebar and phone size).
Give `--at` when the user names a moment or the chosen frame is wrong.

What the evidence says, and what the command does about it:

- **The face.** A large study of breakout thumbnails (vidIQ) and later data (Search Engine Journal) find that a
  face helps when it is big, well lit and shows a real expression; the "shocked face" is folklore. So the picker
  rewards a smile or engaged brows with open eyes on the lens and marks down a mouth caught mid-word, a blink and
  a look away. Face height: at least 30% of a YouTube thumbnail, 16% of a 9:16 cover.
- **The words.** 5 words at most (Arabic: 4 words and 22 letters, its words carry attached particles). They must
  add to the title, never repeat it (`--video-title` checks). Lead with a number when there is one: it becomes the
  accent word. Cap height at least 10% of a YouTube thumbnail's height, 4.5% of a 9:16 cover's: anything smaller
  cannot be read at the 168 px sidebar size or in a 3-column grid.
- **Contrast and colour.** White words with a dark edge on a soft dark scrim, 4.5:1 or better. The background is
  the far side of the colour wheel from the speaker's own clothes, deep and saturated, so the person separates
  from it. One bright accent (yellow by default) for the key word. The outer edge is never near white or near
  black, where it would melt into the app's light or dark theme. A brand's `accent` and `cover_bg` replace these.
- **Arabic.** Shaped right to left, about 1.2 times larger than Latin for the same reading size, a thin edge and a
  heavier shadow instead of a thick outline (a thick one fills the dots), and the layout mirrored: the headline on
  the right where the eye enters, the speaker on the left.
- **Where things go.** 9:16: face and words inside x 120-780, y 285-1248 of 1080x1920, the one rectangle that
  survives Instagram's 4:5 feed and 3:4 grid crops and both apps' buttons and captions (Socialync safe-zone
  guides). YouTube: nothing in the bottom-right corner (the duration badge) or the top-right corner (the hover
  icons). A body cut off by the source frame is moved flush to the cover's edge or faded out, never outlined.
- **Sizes.** YouTube 1920x1080 JPEG under 2 MB (YouTube Help 72431). Reels and Shorts 1080x1920; the Instagram
  grid shows the middle 3:4 and the feed 4:5. Square 1080x1080 for carousels and other feeds.

Layouts (all built from the same frame, so the user can pick):

- `punch`: the speaker cut out with a white sticker edge on a complementary gradient, big headline. The default.
- `frame`: the same over the real room, blurred and darkened, so the cover still says where this was filmed.
- `minimal`: the speaker with a soft glow on a tinted gradient, serif italic headline. For calm, story and premium
  content. The speaker keeps their own colour (house rule).
- `object` (needs `--image`): the product, screenshot or result as a tilted card beside the speaker. Use it when
  the video is about a thing the viewer can see.

Show the user `preview.jpg` and name the layout you would post and why. On YouTube, upload two or three of them to
Test & Compare (YouTube Help 13861714), which picks the winner by watch time: that test is worth more than any
rule here. YouTube Shorts thumbnails cannot be A/B tested (YouTube Help 12340300). For a branded video, the brand
skill's colours and type win; the rules above still apply to size, words and placement.

## Studio voice

The best-sounding voice chain in tests: `python -m editor studio-voice <clip> <out.mp4> [--video <retouched.mp4>]`
(AI denoise + studio restoration, then -14 LUFS). Slow on CPU (~8 s per second of audio): start it first.
A/B any voice change on 20 s samples before using it.

## Effects toolbox (installed by setup)

`python -m editor doctor` checks all of it. Models live in the cache (`editor/extras.py` has paths and speeds):
BiRefNet (best cut-outs, slow: stills, stickers, freeze frames), MODNet / MediaPipe selfie_multiclass (masks on
moving video, hair / face / body / clothes), MediaPipe face, pose and hand landmarkers (effects that follow a
person), RIFE (smooth slow motion), Real-ESRGAN (sharp punch-in zooms). Browser libraries for HyperFrames
compositions in `vendor/hf/node_modules`: gl-transitions, lottie-web, three, gsap. ffmpeg: vidstab
(stabilise shaky phone shots), minterpolate, tmix, lagfun, chromashift, xfade, zoompan, frei0r. Sound: a Mixkit
effects pack in the cache (`sfx/mixkit/index.json`, by category); keep it quiet (`sfx_volume`). All free for
commercial use; never commit the models or sound files.

## Signature effects (fx pack)

38 effects in `editor/fx/`, one module each, built in code on real footage (no AI pixels).
`python -m editor fx-list` prints every effect, its duration range, params and `BEST_FOR` tags (`any`, `finance`,
`product`, `playful`, `corporate`). Put them in edit.json as
`"fx": [{"type": "wall_text", "at": 4.2, "dur": 3, "text": "FOCUS"}]` (timeline seconds; windows can't overlap;
`captions: keep|hide`). `fx-sample <clip> <type> <out> --at --dur --params '{...}'` renders one window to show the
user first; `fx-apply` runs a whole fx list on any 9:16 clip. A brand's look for an effect (cover_story palettes,
chart colours) lives in its style JSON (`data_look`, `cover_story`, `cover_name`); a brand skill says which tags fit.

When to use them (one effect every 8-15 s at most; each must land on a line that earns it):
- **Section word / big claim:** `wall_text` (word behind the head), `glass_type` (frosted type), `headline_wall`.
- **Announcement / "this is the story":** `cover_story`, `frame_break`, `news_bars` (breaking-news strips with
  BREAKING / JUST IN tags slam in round the face; `items` are the headlines, from the script).
- **Numbers (finance, data):** `chart_grow` (values only from the script, never invented), `list_tracker`,
  `counter_tally` (a clean page: a big number counts up to the total over a ticking list; recaps, "all N").
- **Steps, plans, "all you need":** `checklist` (dark frosted card), `checklist_pop` (white pills pop up
  beside the chin and tick green one by one; for a short list said out loud).
- **Energy on a word:** `digital_zoom` (snap on the word), `vertigo`, `zoom_through` (between sections),
  `shatter` (cracks from the face, the frame breaks into glass; `hit` on the word).
- **"Look closer" / a detail:** `lens` (a ball of liquid glass settles on the face and magnifies it),
  `viewfinder` (camera screen with REC and a focus box, punching in 1x > 1.8x > 3x > 1x), `portal` (a round
  close-up pops up in a corner, then swallows the frame).
- **Section change / a memory:** `photo_drop` (the shot becomes a tilted print dropped on a table, then swings
  back).
- **Opening / ending reveal:** `pull_back`.
- **App or product moments:** `ui_world`, `orbit` (both hide captions while on).
- **Playful brands only:** `paper_cut`, `doodle_boil`, `green_screen` (swap the background for stock).
- **Sober / corporate brands:** charts, lists, `checklist`, `cover_story` and gentle zooms only.
- **Punchline / pattern interrupt:** `outline` (sticker border or neon glow round the speaker), `freeze_callout`
  (freeze, the room blurs, speaker lifts out bigger, a label pops in).
- **Rhythm:** `beat_shake` on music drops or stressed words (pass `hits`; never on a timer), `motion_echo` on a big
  gesture.
- **Tech and how-to:** `terminal` (commands typing out, ✓ results), `code_card` (the line being read lights up),
  `rank_list` (#1 #2 #3 lighting in turn); `place: "top"` keeps the speaker below, `full` fills the frame.
- **Refused (they change the footage's colour):** `film_look`, `color_pop`, `noir_minimal`, `glitch`.

Two named styles (popular short-form looks; use them when asked by name or when the profile's look fits):
- **Minimal storytelling** ("clean, minimal line art"): slow camera moves (`pull_back`, `vertigo`) on the story
  beats, the speaker in their own colour, cut to `line_art` cards (a white line drawing drawing itself on black, small `label` / `caption`) for the quiet beats
  between. Keep captions small and the music soft; no stickers, no bright colours.
- **Kinetic transparent captions** ("captions that move with your words"): `word_stack` on the two or three words
  that carry each line: `outline` for the setup word, `gradient` (italic serif, pastel) for the payoff, `bold` for
  a call to action, timed to the words from `transcript_timeline.md` (`t` is seconds into the window). The normal
  captions stay small below the face.

- **Rapid visual explainer** ("a visual for every phrase"): for tool, tech and how-to reels. Split screen almost
  throughout: the speaker in the lower half and a new visual in the upper half on every phrase, about 1 s each
  (`broll` with `frame: "top"`, set `split_y` to just above the crown on a close-up). The visuals, in this order:
  the real thing being named (`capture` with a `point` step on the exact words, a real clip the user supplied),
  free stock, the tech cards (`terminal` for commands, `code_card` with `focus` on the line being read, `rank_list`
  counting #1 #2 #3, all with `place: "top"`). Short bold captions of two or three words, one accent word; a sound
  on every new shot (a soft tick or whoosh), quieter than the voice.

Retention craft (every edit): open on the payoff or the most visual moment, never a greeting; something on screen
changes every 1-3 s (a cut, a zoom, a word, a graphic); re-hook at the middle with a new promise or a reveal; end
abruptly on the last useful line, or loop the last frame into the first; assume it is watched muted, so the
captions must carry the message on their own. Sound effects follow what is on screen, never a timer.

Cut-outs use Robust Video Matting (`editor/cutout.py`, `EDITOR_MATTE=modnet` to fall back), with the speaker's own
colour estimated at the soft edge (no rim of the old room on a new background), gated by MediaPipe's
background class so chairs and furniture never join the person. The gate stands aside around hair, face and
glasses and for what the hands hold (a phone or a product), so hair, glasses arms and held objects keep
RVM's own edge; tested on hair, glasses and held objects. Weak spots: on tight close-ups `wall_text` /
`glass_type` turn the word sideways, `orbit` cards get small and `doodle_boil` may draw on the chest; prefer medium
shots for those, or sample first. An object held out more than a quarter of the frame width from the hand may
still be gated: sample it.

## Editing rules (edit.json)

Two time bases. Source seconds: `segments[*].in/out` and `transcript_packed.md` (use it only to
correct the transcript). Timeline seconds: every other time (`graphics`, `broll`, `sfx` `at`)
and `transcript_timeline.md`.

- **Hook:** the first 3 s carry the strongest line. If a clearly stronger line comes later,
  move that segment to the front (cold open) and add a note.
- **Graphics:** built-in types and their fields: `hook{text}`, `lower_third{name, sub?}`,
  `list{items[]}`, `stat{value, label, dir?: up|down}`, `quote{text, by?}`, `ticker{name, ticker, fact?}`,
  `headline{text, source?, tag?}`, `kinetic{text, hi?[], fx?, place?}` (big word-by-word text, `hi` words in the
  accent; `place: center` makes it a big centred title, `behind` puts it behind the person),
  and three at fixed spots: `credit{text}` (vertical `// SOURCE` on B-roll), `chapter{text}` (section pill
  at the top) and `outro{handle?, disclaimer?}` (full-frame logo end card; the style needs a `logo`). Each has
  `at` and `dur`. For
  anything else (maps, phone mockups of real app screens, zoom callouts, split screens,
  talking-head cards), author a HyperFrames project in `<project>/work/custom-<n>/` with the
  vendored `hyperframes-core`, `hyperframes-animation` and `talking-head-recut` skills, and add
  `{"type": "custom", "dir": "work/custom-<n>", "at": ..., "dur": ...}` (`dir` is relative to the
  project). Skip those skills' "confirm with the user" steps. Never use HeyGen cloud render, TTS
  or an API key. Vendor GSAP and fonts locally: a composition that loads `http(s)://` is refused.
- **Desks (explainer mode):** `desks[]` entries `{at, dur, mood?: brand|bull|bear, card}` switch the frame
  to an explainer panel over a moving brand background, with the speaker cut out of their own background
  (no box) and standing under the panel; captions move up between the two. Cards:
  `profile{ticker, name?, desc?, stats?[{value, label}] ≤3, body?, tags?[], color?: up|down}`,
  `steps{title, hi?, eyebrow?, items[] 2-4}`, `themes{title, hi?, items[{title, body?}] 2-4}`,
  `chart{name, ticker?, value, change?, dir?, points[], labels?[]}` (points are real data from the user, never
  invented) and `image{src, title?, source?}` (a screenshot the user supplied). `**bold**` marks key phrases
  in body text. `at` ≥ 1.5, `dur` ≥ 2; no graphics or B-roll during a desk. The cutout runs on the CPU
  (about 0.5 s a frame), so keep desks to the explanation-heavy parts.
- **Placement is automatic:** `analyze` writes `faces.json` and `render` puts every built-in card
  in the free space off the speaker's head and the captions, inside the social safe zone, shrinking it to fit.
  The zone is TikTok's, the tightest platform (`editor/safezone.py`, the one place it is set): the top 13%, the
  bottom 25% (username, caption, sound) and the right 13% (the button column) stay clear. Effects, credits and a
  card the user asks to enlarge (`scale`) obey it too. Hand-placed kit stacks (`pos`) are not moved for you:
  after a render, `scripts/qc/safezone.py <project> --style <style>` measures every graphic's drawn pixels and
  every caption line against the zone and must PASS. Free space is often a
  narrow band, so keep card text short (hook and quote ≤ 4–5 words, lists ≤ 3 short items) and
  fix every "cramped" note `render` prints by shortening the text or picking a compact type.
- **Motion craft:** cubic easing, never linear. Start a graphic so its landing frame hits the
  spoken payoff word. One new element at a time. Hold the last frame ≥ 1 s. 1.5–4 s each,
  never two at once. Assert fonts loaded.
- **B-roll:** 30–50% of a reel at visual moments, 1.5–4 s each, on phrase boundaries, never in
  the first 1.5 s. Concrete `query`. A `whoosh` at each entry.
- **Punch-in:** a segment's `zoom` (1.0–2.5) crops around `focus: [x, y]` (fractions of the source frame;
  default the centre). Use it to land on a face or a reaction, e.g. `"zoom": 2.4, "focus": [0.5, 0.31]`.
  `push` eases the zoom to a new value across the segment, or over `push_dur` seconds and then holds: split a take
  where the move starts for an eased push on an emphasis line without a cut.
- **Ending:** `music.end` stops the bed at a time (a short fade, then silence: a logo sting takes over).
  `endcard {from_white: true, fade_to: "#000000", fade: 1.3}` enters through a light burn's white and closes to
  black; `endcard {slide: 0.4}` sweeps a white panel in from the left over the last shot instead. A one-frame cover
  (the grid thumbnail) is an `overlays` entry `{file, at: 0, dur: 0.02}`.
- **More kit pieces:** `badge {num, look: "glow"}` (a numbered step in a glowing diamond), `card {look: "glow"}` (a
  purple statement card whose line scrolls across, then settles), `flag` (a waving flag drawn in the browser).
- **Captions off under a keyword:** a graphic with `hide_captions: true` takes the caption lines it overlaps off,
  so the same words never show twice.
- **Looks:** `looks[]` entries `{type: "bars"|"vignette", at, dur}` (timeline seconds, `dur` ≥ 1).
  `bars` slides cinematic black bars in from the top and bottom: use it to mark the serious
  moments (an admission, a hard truth, the core message), 2–5 s each, at most 2–3 per minute.
  `vignette` darkens the edges for an emotional or reflective line; use it occasionally, not on
  every serious moment. Both sit under graphics and captions and ease in and out on their own.
- **Colour never changes.** The footage keeps the colour the camera recorded, on every edit, under any condition:
  no grade, no white balance or per-shot correction, no tint, no black and white, no colour effect. The engine refuses
  `grade` and the effects that recolour footage (`film_look`, `color_pop`, `noir_minimal`, `glitch`, and the
  black-and-white or tinted options of `freeze_callout`, `outline`, `motion_echo`, `beat_shake`, and `lens` with a
  colour `fringe`). Graphics, B-roll and
  the light-burn transitions sit over the footage; they never change it. Before delivering, run
  `scripts/qc/colour.py <project>`: it compares the final with the source at the same crop and fails on any shift.
- **Sound:** every effect is tied to something visible; at most one per second. `pop` only on
  one or two emphasis words.
- **Never** use AI-generated footage. Never invent facts, numbers or quotes: every word in a graphic comes from the
  transcript, the brief or the glossary.
