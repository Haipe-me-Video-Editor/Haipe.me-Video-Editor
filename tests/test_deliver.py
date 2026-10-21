import pytest

from editor import deliver


def test_upload_needs_the_drive_settings(monkeypatch, tmp_path):
    monkeypatch.delenv("DRIVE_UPLOAD_URL", raising=False)
    monkeypatch.delenv("DRIVE_UPLOAD_KEY", raising=False)
    assert not deliver.configured()
    with pytest.raises(RuntimeError, match="isn't set up"):
        deliver.upload(tmp_path / "v.mp4")
