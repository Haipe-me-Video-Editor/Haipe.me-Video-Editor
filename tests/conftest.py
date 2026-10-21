import json
from pathlib import Path

import pytest

from editor import ffmpeg

SPEECH = [(0.5, 2.5), (3.5, 6.0), (7.2, 9.5)]
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def talking_clip(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("fx") / "talk.mp4"
    gate = "+".join(f"between(t,{a},{b})" for a, b in SPEECH)
    ffmpeg.run([
        "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=10",
        "-f", "lavfi", "-i", f"aevalsrc='0.3*sin(2*PI*220*t)*({gate})':s=48000:d=10",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", out,
    ])
    return out


@pytest.fixture(scope="module")
def black_and_test_clip(tmp_path_factory) -> Path:
    """4s clip: 1.5s black followed by 2.5s testsrc2."""
    out = tmp_path_factory.mktemp("fx") / "black_test.mp4"
    # Create black frame segment (1.5s at 30fps, 320x240)
    black_part = "color=black:s=320x240:r=30:d=1.5"
    # Create test pattern segment (2.5s at 30fps, 320x240)
    test_part = "testsrc2=size=320x240:rate=30:duration=2.5"
    # Concat filter to join them
    ffmpeg.run([
        "-f", "lavfi", "-i", black_part,
        "-f", "lavfi", "-i", test_part,
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        out,
    ])
    return out


@pytest.fixture
def words() -> list:
    return json.loads((FIXTURES / "words.json").read_text())
