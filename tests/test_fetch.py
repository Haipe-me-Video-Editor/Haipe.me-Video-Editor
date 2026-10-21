"""Getting the user's video from a share link: the right download address, a plain answer when the link is not
shared, and only a real video kept."""
import io
import subprocess

import pytest

from editor import fetch as fe


@pytest.mark.parametrize("link", [
    "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view?usp=sharing",
    "https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUv",
    "https://drive.google.com/uc?id=1AbCdEfGhIjKlMnOpQrStUv&export=download",
])
def test_every_drive_link_shape_goes_to_the_file_itself(link):
    assert fe.download_url(link) == ("https://drive.usercontent.google.com/download?id=1AbCdEfGhIjKlMnOpQrStUv"
                                     "&export=download&confirm=t")


def test_dropbox_links_ask_for_the_file_and_other_links_pass_through():
    assert fe.download_url("https://www.dropbox.com/scl/fi/abc/clip.mov?rlkey=k1&dl=0") == \
        "https://www.dropbox.com/scl/fi/abc/clip.mov?rlkey=k1&dl=1"
    assert fe.download_url("https://example.com/v.mp4") == "https://example.com/v.mp4"


def test_a_folder_or_a_non_link_gets_a_plain_answer():
    with pytest.raises(fe.FetchError, match="folder"):
        fe.download_url("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp")
    with pytest.raises(fe.FetchError, match="web link"):
        fe.download_url("my video.mov")


class _Resp(io.BytesIO):
    def __init__(self, data, headers, url="https://x/y"):
        super().__init__(data)
        self.headers, self._url = headers, url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_a_link_that_is_not_shared_says_how_to_share_it(tmp_path):
    page = _Resp(b"<html>sign in</html>", {"Content-Type": "text/html; charset=utf-8"})
    with pytest.raises(fe.FetchError, match="Anyone with the link"):
        fe.fetch("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view", tmp_path, opener=lambda u: page)
    assert list(tmp_path.iterdir()) == []


def test_a_video_is_kept_under_its_own_name_and_anything_else_is_refused(tmp_path):
    clip = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=24:d=1", "-pix_fmt", "yuv420p",
                    str(clip)], check=True)
    head = {"Content-Type": "video/mp4", "Content-Disposition": "attachment; filename*=UTF-8''My%20clip%201.MOV"}
    out = fe.fetch("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view", tmp_path / "in",
                   opener=lambda u: _Resp(clip.read_bytes(), head))
    assert out.name == "My_clip_1.mov" and fe.has_video(out)
    with pytest.raises(fe.FetchError, match="not a video"):
        fe.fetch("https://example.com/notes.mp4", tmp_path / "in",
                 opener=lambda u: _Resp(b"just text", {"Content-Type": "application/octet-stream"}))
    assert sorted(p.name for p in (tmp_path / "in").iterdir()) == ["My_clip_1.mov"]  # no half file left behind
