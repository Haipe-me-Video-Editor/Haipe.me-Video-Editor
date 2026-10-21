# Preset: finance and markets

Use this preset for crypto, stocks, markets and personal-finance explainers. Pass `--style finance` to
`captions`, `render` and `review` (a brand style replaces it when a brand skill applies). For the script itself,
see `research-script.md`.

## What works (studied from popular long-form finance channels)

**Script structure:**
1. Hook with the stakes and the direction.
2. Why it matters to your money.
3. Roadmap.
4. Dated backstory.
5. The last 24 hours.
6. Numbered reasons with hard figures and comparisons.
7. "How do you play this?"
8. Scenarios.
9. "Do your own research".

The most replayed parts are the actionable answer and the biggest number.

**Three modes, cut hard between them:**
1. **Full-screen talking head:** the hook, opinions, transitions. No graphics.
2. **Desk (explainer):** a moving themed background, a big content panel, the host beside or under it. A panel
   stays up while the host explains it, with a slow push-in.
3. **Full-screen B-roll:** footage and news clips with a small vertical source credit, and big centred text with
   the key words in the accent over it.

**What the desk panels hold:**
- **Evidence, as real screenshots:** a price chart (name, price, % change, line), news cards (source, headline,
  snippet, time ago), a map, company web pages.
- **Custom data cards:** numbered steps, each in its own colour; a 2×2 theme grid; a ticker profile (a giant
  ticker, the company and its description, three stat chips, a paragraph with bold key phrases, tag chips).
- **Sponsor:** a clear disclosure banner.

## Our version (9:16)

- **Full-screen talking head:** kept as is, with captions.
- **Desk** (`desks[]` in edit.json):
  - the panel sits on top (12.5–47% of the height) over a moving brand background;
  - the speaker is **cut out of their own background** (virtual green screen on CPU, no box) and stands below
    with their head at about 60%;
  - captions move up between the two;
  - `mood`: `brand`, `bull` (green) or `bear` (red).
- **Cards:** `profile` (the ticker profile), `steps`, `themes`, `chart` (drawn from real data points the user
  gives), `image` (screenshots the user supplies: charts, headlines, maps).
- **B-roll:** with `credit` and `kinetic` text.

## Planning rules

| Moment in the script | Graphic |
|---|---|
| A reason, framework or "how it works" part (5–30 s) | A **desk** with `steps` or `themes` |
| Deep dive on one coin or company | A **desk** with `profile` (stats only from the speaker's words) |
| Price action the speaker shows | A **desk** with `chart` (points from the user) or `image` (their screenshot) |
| News the speaker cites | A **desk** with `image` of the user's screenshot, or a `headline` card |
| Hook (0–3 s) | `kinetic` with the stakes word in `hi`, plus `bars` if it is a warning |
| A company, coin or token named | `ticker {name, ticker, fact?}` |
| A news event | `headline {text, source?, tag?}`: the speaker's own words, and a source only if they name it. Never fake an outlet's article. |
| Every number spoken | `stat {value, label, dir?}`: `dir` "up" (green ▲) or "down" (red ▼) |
| Numbered reasons and sections | `chapter {text}`, for example "Reason 1 of 3" |
| B-roll from a named source | `credit {text}` for the B-roll's whole duration |
| Punch line over B-roll | `kinetic` (big text over B-roll, not over the face) |
| Warning or hard truth | `bars`, plus `stat` with `dir: "down"` |
| "How to play it" (the peak) | A zoom punch-in (`segments[].zoom` 1.15–1.25), then `list` with up to 3 short items |
| Last 2–3 s | `outro {handle, disclaimer}`: the channel's handle and its "education only" disclaimer |

- **Density:** a new visual every 3–5 s; never two at once (fixed `credit` and `chapter` may sit under one card).
- **Never invent numbers, prices or quotes.** Every figure comes from the transcript or the brief.
- **No AI footage.** B-roll comes from the user's library or free stock (`stock`), with AI clips filtered out.
- **Desks:** roughly 30–50% of a finance video, on the explanation-heavy parts; the hook stays full-screen talking head.
- **Ask the user** for screenshots (charts, headlines, maps) and price data, because desks need real evidence.
- **fx that fit** (`BEST_FOR` `finance`): `chart_grow`, `list_tracker`, `checklist`, `cover_story`, gentle zooms.
- **Not built yet:** a timeline card, a map card, a red circle callout, a split card for two stacked headlines.
