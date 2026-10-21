import subprocess

import pytest

from editor import voice


def test_studio_post_chain_is_valid_ffmpeg():
    p = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=0.5:sample_rate=48000",
                        "-af", voice.STUDIO_POST, "-f", "null", "-"], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_studio_restore_needs_its_venv(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "STUDIO_PYTHON", tmp_path / "missing" / "python")
    with pytest.raises(RuntimeError, match="setup.sh"):
        voice.studio_restore(tmp_path / "a.wav", tmp_path / "b.wav", tmp_path)
