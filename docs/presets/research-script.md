# Preset: research-first scripting (before the user records)

Use it when the user asks for a script, talking points or "what should I say about X", above all for finance and
explainer videos (read `finance.md` too). Free only: Claude's own web search and fetch, a social-data connector if
one is attached, the user's own files. No paid data or AI writing tools.

## 1. Research (before writing a word)

- Run 8-15 searches across angles: the news itself, the numbers, the backstory with dates, what critics say,
  what it means for a normal person's money. Use `extended` search for anything from the last 7 days and for prices.
- **Every number and claim needs a source with a date.** A number used on screen needs two independent sources
  (or one primary source: the company, the exchange, the regulator, the official filing). Prices: give the time.
- Keep a fact sheet: `facts[]` with `{claim, value?, source_url, source_name, date, confidence: high|medium}`.
  Drop anything you can't source. Never round a number into a different meaning; never invent a quote.
- Check what already performs: the top 5-10 recent videos on the topic (TikTok / Instagram / YouTube): their
  hooks, length and the comments' questions. Note them; don't copy them.

## 2. Script (finance structure, 45-90 s for a reel)

1. **Hook (≤ 3 s):** the stakes and the direction, with the biggest number if there is one.
2. Why it matters to the viewer's money.
3. Backstory in one or two dated lines.
4. The reasons: numbered, each with a hard figure.
5. The actionable answer ("how do you play this?"), framed as education.
6. Scenarios (bull / bear) in one line each.
7. Close: "do your own research" and the channel's disclaimer.

Write it in the language and dialect the user will speak, short spoken sentences, loanwords where they'd naturally
say them. Give a gloss in another language if they ask.

## 3. Deliverable

A document the user can read on their phone while recording (a shared doc if a docs connector is attached):
- the script, beat by beat, each beat with its on-screen idea (stat card, desk card, B-roll query, bars);
- a sources table (claim → source, date);
- "say it this way" notes for any number that is easy to misread.

Keep `<work>/script.json` next to it so the edit can reuse the plan after recording:
`{"topic", "beats": [{"line", "visual": {"type": "stat"|"desk"|"broll"|"kinetic"|null, ...}, "facts": [ids]}],
"facts": [...]}`. After the recording, place graphics from the beats whose lines were actually said (match on the
transcript), and only with values from `facts`.
