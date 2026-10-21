from editor import clips


def test_clip_subs_shift_and_clamp_to_the_clip():
    subs = [[1.0, 2.0, "before"], [9.5, 11.0, "straddles start"], [12.0, 13.0, "inside"], [19.8, 21.0, "tail"]]
    out = clips.clip_subs(subs, 10.0, 20.0)
    assert out == [[0.0, 1.0, "straddles start"], [2.0, 3.0, "inside"]]  # the 0.2 s tail is dropped


def test_check_clips_flags_bad_ranges_names_and_titles():
    good = [{"name": "launch", "start": 0.0, "end": 22.0, "title": "Acme app\\Nlaunch day"}]
    assert clips.check_clips(good, 68.0) == []
    bad = [{"name": "a b", "start": 5, "end": 8}, {"name": "x", "start": 60, "end": 80},
           {"name": "y", "start": 0, "end": 20, "title": "a title that is far too long for one line"}]
    errs = "\n".join(clips.check_clips(bad, 68.0))
    assert "unique" in errs and "outside" in errs and "title" in errs


def test_title_is_a_top_hook_event_with_line_breaks():
    (ev,) = clips.title_events("Acme app\\Nlaunch day")
    assert ",HookL," in ev and "\\an8" in ev and "Acme app\\Nlaunch day" in ev
    assert clips.title_events("") == []
