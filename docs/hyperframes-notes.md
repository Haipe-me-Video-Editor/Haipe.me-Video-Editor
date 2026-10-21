# HyperFrames notes (hyperframes@0.8.138, local render)

Measured in the Claude cloud container (4 cores, no GPU, headless Chromium 141 via `chrome-headless-shell`).

## Commands

Environment (set by `editor.config.hf_env()`):

```bash
export HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1 HYPERFRAMES_NO_UPDATE_CHECK=1 HYPERFRAMES_SKIP_SKILLS=1
# PRODUCER_HEADLESS_SHELL_PATH is set only when a preinstalled headless Chrome exists (config.HEADLESS_SHELL);
# otherwise HyperFrames uses the browser `hyperframes browser ensure` downloaded (scripts/setup.sh runs it).
H=vendor/hf/node_modules/.bin/hyperframes
```

Lint and render, run inside the composition folder:

```bash
$H lint .
$H render . --format mov -o g.mov
```

## Spike result (10 s, 1080x1920, one h1 fading in)

- `lint`: 0 errors, 2 warnings (`studio_missing_editable_id`, `nested_structure_needs_subcomposition`). Warnings do not fail the render, and the generated compositions get the same two warnings.
- Render wall time: 27.9 s (`rendered in 26.7s`; setup 3.7 s, capture 4.7 s, encode 18.1 s). A 1 s or 2 s graphic takes about 6 s and 13 s.
- Render summary line 2: `screenshot capture · software gpu · compile 0.0s · extract 0.0s · audio 0.0s · probe 0.0s · setup 3.7s · capture 4.7s · encode 18.1s · assemble 0.0s`. The next line says `BeginFrame did not run`, so this container renders in `screenshot` mode with software GL.
- ffprobe: `codec_name=prores`, `pix_fmt=yuva444p12le`, 1080x1920, `duration=10.000000`.

## Alpha

`--format mov` alone produces ProRes 4444 with an alpha channel (`needsAlpha: true` in the render trace) as long as the page background is transparent. No extra transparency flag is needed, so `RENDER_ARGS = ["--format", "mov"]`.

## Deviations from the brief

None. Lint accepted the brief's generated HTML (warnings only), so `composition.py` is the brief's code verbatim.
