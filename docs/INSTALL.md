# Install

Everything the editor knows is in this repository: the engine (`editor/`), the skill that tells Claude how to edit
(`skills/edit-video/SKILL.md`), the presets (`docs/presets/*.md`) and the built-in styles (`editor/styles/*.json`).
Footage, music, models and keys are never in the repo; setup downloads the free models.

## 1. Computer

- macOS or Linux. On Windows, use WSL2 (Ubuntu) and run everything inside it.
- About 25 GB free disk (speech, voice and retouch models), 16 GB RAM. A CPU is enough; it's just slower.
- An AI coding agent: Claude Code, Codex or any other. Ask it to install this repo and it sets up the rest (git,
  Python 3.11 to 3.13, Node.js 20+, ffmpeg with libass) by itself.
- Nothing to sign up for: no accounts, tokens or keys, and nothing ever asks for one. Transcripts in Arabic and
  English and free stock footage (Mixkit, Internet Archive, Wikimedia Commons) all work as they are.

Where it runs: Claude Code or Codex, on your own computer (nothing else needed) or in the cloud. In the cloud, the
agent needs internet: on Claude Code on the web set the environment's Network access to Full; in Codex turn on Agent
internet access for the environment. A plain chat without code tools cannot run it.

## 2. Install

```bash
git clone https://github.com/Haipe-me-Video-Editor/Haipe.me-Video-Editor.git
cd Haipe.me-Video-Editor
bash scripts/setup.sh          # ends with the doctor table and "setup ok (with speech models)"
python3 -m pytest -q -m "not slow"
```

`python -m editor doctor` re-checks the effects toolbox any time.

Or as a Claude Code plugin in any project folder: `/plugin marketplace add Haipe-me-Video-Editor/Haipe.me-Video-Editor`, then
`/plugin install claude-video-editor@haipe-me`.
Run `scripts/setup.sh` from the plugin folder once.

## 3. Brand packs (optional)

To edit in your own brand's look, add `brands/<brand>/style.json`, `brands/<brand>/preset.md` and
`skills/<brand>-video/SKILL.md` (see "Brand packs" in the skill), or set `EDITOR_BRANDS` to a folder of packs kept
elsewhere. Brand files supplied by a client (logos, fonts, stings) are the client's: share them only with the
client's permission.

## 4. Use

Open Claude Code in the repo folder and say, for example:

> Edit `~/Videos/clip.mov` as a finance explainer.

Claude follows `skills/edit-video/SKILL.md` and the matching preset or brand skill. Results match when the same
version of the repo is used, so pull before each job (`git pull`) and use a strong model for planning.
