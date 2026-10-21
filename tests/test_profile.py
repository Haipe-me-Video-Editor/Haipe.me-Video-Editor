from editor import config, profile

ROOT = profile.INTERVIEW.parents[1]


def test_no_profile_points_at_the_interview(tmp_path):
    p = tmp_path / "profile.md"
    assert profile.load(p) is None
    assert "interview" in profile.note(p, "public") and str(profile.INTERVIEW) in profile.note(p, "public")
    assert profile.note(p, "internal") == ""  # the internal engine never asks for an interview
    p.write_text("  \n")  # an empty file is no profile
    assert profile.load(p) is None and profile.snapshot(tmp_path, p) is None


def test_a_profile_is_read_and_copied_into_the_project(tmp_path):
    p = tmp_path / "profile.md"
    p.write_text("# Creator profile\n- Captions: bilingual\n", encoding="utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    assert profile.load(p).endswith("bilingual")
    assert str(p) in profile.note(p)
    assert profile.snapshot(proj, p).read_text(encoding="utf-8") == p.read_text(encoding="utf-8")


def test_the_interview_ships_with_the_questions_and_the_profile_shape():
    path = profile.INTERVIEW if profile.INTERVIEW.exists() else ROOT / "public" / "docs" / "interview.md"
    text = path.read_text(encoding="utf-8")
    assert "## The questions" in text and "# Creator profile" in text and "Notes from edits" in text


def test_a_finished_video_is_uploaded_only_when_asked(monkeypatch):
    from types import SimpleNamespace

    from editor.cli import _upload
    monkeypatch.setattr(config, "EDITION", "public")
    monkeypatch.delenv("EDITOR_UPLOAD", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    assert not _upload(SimpleNamespace(upload=False, no_upload=False))
    assert _upload(SimpleNamespace(upload=True, no_upload=False))
    monkeypatch.setenv("EDITOR_UPLOAD", "gofile")
    assert _upload(SimpleNamespace(upload=False, no_upload=False))
    assert not _upload(SimpleNamespace(upload=False, no_upload=True))


def test_a_cloud_session_still_uploads_unless_told_not_to(monkeypatch):
    from types import SimpleNamespace

    from editor.cli import _upload
    monkeypatch.setattr(config, "EDITION", "public")
    monkeypatch.delenv("EDITOR_UPLOAD", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    assert _upload(SimpleNamespace(upload=False, no_upload=False))  # the user cannot open the cloud disk
    monkeypatch.setenv("EDITOR_UPLOAD", "off")
    assert not _upload(SimpleNamespace(upload=False, no_upload=False))


def test_the_internal_engine_always_delivers_a_link(monkeypatch):
    from types import SimpleNamespace

    from editor.cli import _upload
    monkeypatch.setattr(config, "EDITION", "internal")
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.setenv("EDITOR_UPLOAD", "off")
    assert _upload(SimpleNamespace(upload=False, no_upload=False))  # as it always has
    assert not _upload(SimpleNamespace(upload=False, no_upload=True))
