# Haipe.me Video Editor: guide for the AI agent

This file is for whichever AI coding agent the user runs (Claude Code, Codex, ChatGPT's agent, Cursor, Gemini,
Copilot or any other). Everything here is plain shell and Markdown: no tool-specific feature is required.

You are working with someone who wants their videos edited. Most of them are not programmers: do every technical
step yourself, explain in plain words, ask short questions only when you must, and never ask them to edit a file,
open a terminal or make an account.

## Where this runs

It needs an agent that can run shell commands: Claude Code (terminal, desktop app or on the web) or Codex (CLI,
app or cloud), or another coding agent with a shell. A plain chat (ChatGPT or Claude.ai without code tools) or a
browser agent cannot run it; say so plainly if that is where the user is.

On the user's own computer nothing else is needed. In a cloud session the downloads below must be allowed. If a
download is refused as a blocked host, tell the user the one setting, in these words:
- Claude Code on the web: open the environment's settings and set Network access to Full.
- Codex in the cloud: open the environment's settings and turn Agent internet access on.
The hosts setup uses: pypi.org, files.pythonhosted.org, registry.npmjs.org, download.pytorch.org, huggingface.co
(and its download hosts), storage.googleapis.com, cdn.playwright.dev, github.com; editing uses mixkit.co,
archive.org, commons.wikimedia.org and gofile.io.

## Install (when asked to "install this" or "set it up")

1. Clone the repo if it is not already here:
   `git clone https://github.com/Haipe-me-Video-Editor/Haipe.me-Video-Editor.git` and work inside it.
2. Check the computer: macOS or Linux (on Windows, WSL2 with Ubuntu), about 25 GB free disk, Python 3.11 to 3.13 (the
   speech models have no wheels for newer yet),
   Node.js 20+, git, and ffmpeg built with libass (`ffmpeg -filters | grep -w ass`). Install what is missing with the
   system's package manager (Homebrew on macOS, apt on Ubuntu), telling the user what you are installing and why.
3. Run `bash scripts/setup.sh`. It installs the Python packages (into a private `.venv` in this folder when the
   system Python refuses outside installs, as on macOS and recent Ubuntu), the effects toolbox and the free models,
   and ends with the doctor table and "setup ok". It takes a while (several GB of models); tell the user. Fix
   anything the doctor marks missing, then run it again.
4. No accounts, tokens or keys are needed for anything, and none is ever asked for.
5. Run the quick tests with the same Python: `python -m pytest -q -m "not slow"` (`.venv/bin/python` if setup
   made a `.venv`).
6. Then offer the interview (below). Details and optional keys: `docs/INSTALL.md`.

## The interview (once, after install, or whenever asked)

Before the first edit, interview the user so every edit fits them: follow `docs/interview.md`. It is about ten
short questions, one at a time, and the answers are saved to their creator profile outside the repo
(`python -m editor profile` shows it). If they would rather skip it, edit with the defaults and offer it again
after the first video.

## Editing

For every edit, follow `skills/edit-video/SKILL.md` step by step, and read the creator profile first: its answers
are the defaults for captions, style, pacing, music and the things never to do. What the user asks for in the job
wins. Run the engine with `python -m editor <command>` from this folder (with `.venv/bin/python` if setup made a
`.venv`). Where the skill says to spawn a critic sub-agent and your tool has none, do that critic pass yourself:
watch the contact sheets as a harsh reviewer and fix the top five problems.

## Animating

When the user asks for an animation or an animated explainer rather than an edit of their footage, follow
`skills/animate/SKILL.md`. Every frame is drawn in code and the sound is synthesised, so it needs nothing beyond
setup.

## Updating

When asked to update: `git pull`, then `bash scripts/setup.sh` again if `requirements*.txt` or `scripts/setup.sh`
changed. The profile and the user's brand packs are not touched by an update.
