#!/usr/bin/env bash
# One-time setup per container. Safe to re-run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${EDITOR_CACHE:-$HOME/.cache/claude-video-editor}"
TORCH_INDEX="https://download.pytorch.org/whl/cpu"
mkdir -p "$CACHE"
# macOS (Homebrew) and recent Ubuntu refuse pip installs into the system Python (PEP 668). There the packages go in
# a private .venv in the repo; an active virtualenv or conda env, or a Python that allows it, is used as is.
if [ -z "${VIRTUAL_ENV:-}${CONDA_PREFIX:-}" ] && python3 -c 'import os, sys, sysconfig
sys.exit(0 if os.path.exists(os.path.join(sysconfig.get_paths()["stdlib"], "EXTERNALLY-MANAGED")) else 1)'; then
  [ -x "$ROOT/.venv/bin/python" ] || python3 -m venv "$ROOT/.venv"
  export VIRTUAL_ENV="$ROOT/.venv" PATH="$ROOT/.venv/bin:$PATH"
  echo "Python packages go in $ROOT/.venv: run the editor with $ROOT/.venv/bin/python -m editor"
fi
pip install -q -r "$ROOT/requirements.txt"
npm install --prefix "$ROOT/vendor/hf" --no-audit --no-fund --silent hyperframes@0.8.138 gsap@3 \
  gl-transitions@1.71.0 lottie-web@5.13.0 three@0.186.1
# Browsers, fetched once into the user's cache (no account): the headless Chrome HyperFrames renders with, and the
# Chromium that `capture` records app screens with. A machine that already has them (a cloud container) skips both.
if ! (cd "$ROOT" && python3 -c 'import pathlib, sys; from editor import config; sys.exit(0 if pathlib.Path(config.HEADLESS_SHELL).exists() else 1)'); then
  "$ROOT/vendor/hf/node_modules/.bin/hyperframes" browser ensure >/dev/null || echo "HyperFrames browser not fetched: the first render tries again"
fi
if ! (cd "$ROOT" && python3 -c 'import sys; from editor import capture; sys.exit(0 if capture.available() else 1)'); then
  python3 -m playwright install chromium >/dev/null || echo "Chromium for app captures not fetched: capture stays off"
fi
# Effects toolbox. MediaPipe needs EGL/GLES at import; frei0r adds ffmpeg effect plugins. mediapipe's pip
# metadata asks for opencv-contrib-python, which would clash with opencv-python-headless (both are cv2), so it
# goes in without deps and its real deps are listed by hand.
if command -v apt-get >/dev/null; then
  apt-get install -y -q libegl1 libgles2 libportaudio2 frei0r-plugins >/dev/null 2>&1 \
    || { apt-get update -q >/dev/null 2>&1 && apt-get install -y -q libegl1 libgles2 libportaudio2 frei0r-plugins >/dev/null 2>&1; } \
    || echo "apt packages for MediaPipe/frei0r not installed"
fi
pip install -q --no-deps "mediapipe==1.1.0"
pip install -q "absl-py~=2.3" "sounddevice~=0.5" "flatbuffers~=25.9" certifi matplotlib  # mediapipe imports matplotlib
(cd "$ROOT" && python3 -m editor extras >/dev/null && python3 -m editor doctor) || echo "effects toolbox incomplete: run python -m editor doctor"
# Person cut-outs: Robust Video Matting (GPL-3.0 code + weights) is fetched into the cache, never into the repo.
(cd "$ROOT" && python3 -c "from editor import cutout; cutout.ensure_rvm()") || echo "RVM matte not installed: cut-outs fall back to MODNet"
if curl -fsS -o /dev/null --max-time 10 "$TORCH_INDEX/torch/"; then
  pip install -q --index-url "$TORCH_INDEX" "torch==2.8.*" "torchaudio==2.8.*" "torchvision==0.23.*"
  # whisperx pulls antlr4-python3-runtime, which ships only setup.py and fails to build with
  # Debian's setuptools; --use-pep517 builds it in isolation. Debian's PyYAML has no RECORD
  # file, so pip can't upgrade it in place.
  pip install -q --ignore-installed PyYAML
  pip install -q --use-pep517 -r "$ROOT/requirements-ml.txt"
  # WhisperX alignment splits sentences with NLTK's punkt_tab. NLTK refuses proxied fetches
  # unless told the proxy is trusted; the cloud session's egress proxy is.
  NLTK_ALLOW_PROXIED_URLOPEN=1 python3 -c 'import nltk, sys; sys.exit(0 if nltk.download("punkt_tab", quiet=True) else 1)'
  # Studio voice (Resemble Enhance, MIT): own venv on the system torch. It imports deepspeed only for training, so a
  # stub stands in; its fsolve call needs a scalar under numpy 2.
  if ! "$CACHE/venv-re/bin/python" -c 'from resemble_enhance.enhancer.inference import enhance' >/dev/null 2>&1; then
    [ -x "$CACHE/venv-re/bin/python" ] || python3 -m venv --system-site-packages "$CACHE/venv-re"
    if [ -n "${VIRTUAL_ENV:-}" ]; then  # torch lives in that env, not the system: let venv-re see it
      re_site="$("$CACHE/venv-re/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
      python3 -c 'import site; print(site.getsitepackages()[0])' > "$re_site/parent-env.pth"
    fi
    "$CACHE/venv-re/bin/pip" install -q --no-deps resemble-enhance
    "$CACHE/venv-re/bin/pip" install -q celluloid omegaconf ptflops rich resampy tabulate
    "$CACHE/venv-re/bin/python" "$ROOT/scripts/patch_resemble.py"
  fi
  echo "setup ok (with speech models)"
else
  echo "setup ok WITHOUT speech models: allow download.pytorch.org in network settings, then rerun"
fi
