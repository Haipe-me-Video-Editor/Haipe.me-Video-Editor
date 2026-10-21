# The first-run interview

A short conversation, once, so every edit after it fits the person it is for. Run it right after setup, or when
`python -m editor new` prints `note: no creator profile yet`, or whenever the user asks to be interviewed again.
It takes about three minutes.

## How to ask

- One question at a time, in the user's language (Arabic speakers get Arabic). Wait for the answer.
- Offer two to four example answers with each question so it is quick to reply, and accept anything.
- "Skip" and "you decide" are fine answers: write `default` and move on.
- Never ask for a password, a token or an API key here. Keys go in the shell profile, never in the chat.
- If they send a reference (a reel they like, a logo, a font file, a colour), keep it and say what you took from it.

## The questions

1. **You.** What should I call you, and what's your handle? What do you make videos about?
2. **Where they go.** Which platforms do you post on? (Instagram Reels, TikTok, YouTube Shorts, long YouTube, LinkedIn)
3. **Language.** What language do you speak in your videos, and what captions do you want? (Arabic, English, both
   side by side, the spoken language only.) If Arabic, which dialect?
4. **Audience.** Who watches you, and what do they come for? (to learn a skill, for news, to be entertained, to buy)
5. **The look.** Which feels most like you? (clean and minimal, bold and high-energy, cinematic and calm, corporate
   and trustworthy, playful and hand-made.) Any creators or reels whose editing you love?
6. **Brand.** Do you have colours, fonts or a logo? Send them or describe them. Should your handle show at the end?
7. **Pacing.** Tight jump cuts with no pauses, or room to breathe? How long are your videos usually?
8. **Sound.** Music under your voice: yes or no, and what kind? Sound effects on graphics: lots, a few, none?
9. **Never.** Anything I should never do? (no music, no zooms on my face, no emojis on screen, no slang in
   captions, never cut out a certain phrase)
10. **Delivery.** Where should finished videos go: a folder on this computer (the default, nothing leaves it), or
    also a download link (Gofile: anyone holding the link can open it)? Is a render that takes a while fine for
    the best quality, or do you want it fast?

## What to write

Save the answers to the profile file (`python -m editor profile` prints its path; by default
`~/.config/claude-video-editor/profile.md`, outside the repo so updates never touch it). Use this shape and the
user's own words where you can:

```markdown
# Creator profile
- Name / handle:
- Makes videos about:
- Platforms:
- Spoken language / dialect:
- Captions:
- Audience:
- Look:
- References:
- Brand (colours, fonts, logo, end card):
- Pacing / usual length:
- Music:
- Sound effects:
- Never:
- Delivery:
- Quality vs speed:

## Notes from edits
(Add a line here whenever the user corrects an edit: what they asked for, so it is never repeated.)
```

Then read it back to the user in a few lines and ask if anything is wrong. Fix it, save, and say they can change
it any time by asking.

## Using it

- Before planning any edit, read the profile. Its answers are the defaults: the caption mode, the style, the
  pacing, the music, the sound and the "never" list. What the user asks for in the job itself always wins.
- With brand colours or fonts, make a brand pack (`brands/<handle>/style.json`, see "Brand packs" in the skill) and
  use `--style <handle>`. Ask before using a font file they did not send.
- When the user corrects an edit, add the lesson under "Notes from edits" so the next edit starts from it.
