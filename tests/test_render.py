from editor import render


def _plan():
    return {"format": "9:16",
            "segments": [{"src": "raw/a.mp4", "in": 0.44, "out": 0.79, "zoom": 1.0},
                         {"src": "raw/a.mp4", "in": 1.04, "out": 2.49, "zoom": 1.1}],
            "broll": [{"at": 0.5, "dur": 1.0, "query": "x", "resolved": "/lib/x.mp4", "src_in": 0.0}],
            "graphics": [{"type": "list", "at": 0.2, "dur": 1.0, "items": ["a"]}],
            "captions": {"enabled": True}, "music": {"src": None}, "sfx": [], "notes": []}


def test_voice_filter_trims_and_concats_every_segment():
    f = render.voice_filter(_plan(), {"raw/a.mp4": 0}, model="m.rnnn")
    assert "atrim=start=0.44:end=0.79" in f and "atrim=start=1.04:end=2.49" in f
    assert "concat=n=2:v=0:a=1" in f and f.endswith("[voice]")
    assert "afade=t=in:d=0.03" in f
    assert "afade=t=out:st=0.320:d=0.03" in f and "afade=t=out:st=1.420:d=0.03" in f


def test_video_filter_layers_broll_graphics_and_captions():
    p = _plan()
    f = render.video_filter(p, {"raw/a.mp4": 0}, [(p["broll"][0], 1)], [(p["graphics"][0], 2)],
                            (1080, 1920), "work/captions.ass", "work/fonts")
    assert "trim=start=1.04:end=2.523" in f  # one frame extra, cut to an exact frame count
    assert "scale=1188:2112" in f  # 1.1 zoom, even dimensions
    assert "overlay=enable='gte(t,0.4833)*lt(t,1.4833)'" in f  # B-roll snapped to frames like the cuts
    assert "overlay=enable='gte(t,0.1833)*lt(t,1.1833)'" in f  # frame-snapped, end frame excluded
    assert f.endswith("ass=filename=work/captions.ass:fontsdir=work/fonts:shaping=complex[vout]")
    assert "setpts=PTS-STARTPTS+0.5/TB" in f and "setpts=PTS-STARTPTS+0.2/TB" in f
    assert "format=rgba" not in f


def test_credits_follow_the_current_music_and_notes_keep_arabic(tmp_path):
    p = _plan()
    p["music"] = {"src": "m.mp3", "credit": "Track by Someone (CC BY 4.0)"}
    p["notes"] = ["قص المقدمة"]
    render.write_text_outputs(tmp_path, p)
    assert (tmp_path / "credits.txt").read_text(encoding="utf-8").startswith("Track by Someone")
    p["music"] = {"src": None}
    render.write_text_outputs(tmp_path, p, ["captions skipped"])
    assert not (tmp_path / "credits.txt").exists()
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "قص المقدمة\ncaptions skipped\n"


def test_looks_sit_between_footage_and_graphics_with_eased_bars_and_vignette():
    p = _plan()
    p["looks"] = [{"type": "bars", "at": 0.3, "dur": 1.2}, {"type": "vignette", "at": 0.5, "dur": 1.0}]
    f = render.video_filter(p, {"raw/a.mp4": 0}, [(p["broll"][0], 1)], [(p["graphics"][0], 2)],
                            (1080, 1920), "work/captions.ass", "work/fonts")
    assert "color=c=black:s=1080x212" in f  # 11% of 1920, even
    assert "y='-212+212*" in f and "y='1920-212*" in f
    assert "vignette=angle='0.9*" in f and "eval=frame" in f
    assert "enable='between(t,0.3,1.5)'" in f
    assert f.index("[ob0]") < f.index("[lt0]") < f.index("vignette") < f.index("[g0]")


def test_slow_and_muted_segments_in_the_filters():
    from editor.render import _atempo_chain, video_filter, voice_filter
    plan = {"segments": [{"src": "a.mp4", "in": 0.0, "out": 2.0, "speed": 0.25}], "broll": [],
            "graphics": [], "looks": []}
    af = voice_filter(plan, {"a.mp4": 0}, model="m.rnnn")
    assert "atempo=0.5,atempo=0.5," in af and "st=7.970" in af
    plan["segments"][0]["mute"] = True
    assert "anullsrc=r=48000:cl=stereo,atrim=0:8.000" in voice_filter(plan, {"a.mp4": 0}, model="m.rnnn")
    assert "setpts=(PTS-STARTPTS)/0.25" in video_filter(plan, {"a.mp4": 0}, [], [], (1080, 1920))
    assert _atempo_chain(1.0) == [] and _atempo_chain(3.0) == [2.0, 1.5]


def test_retouch_blends_smoothing_only_through_a_skin_mask():
    from editor.render import video_filter
    plan = {"segments": [{"src": "a.mp4", "in": 0.0, "out": 2.0}], "broll": [], "graphics": [], "looks": [],
            "retouch": 0.35}
    vf = video_filter(plan, {"a.mp4": 0}, [], [], (1080, 1920))
    assert "concat=n=1:v=1:a=0[raw]" in vf and "bilateral=" in vf and "lutyuv=y=val*0.35" in vf
    assert "[rt_o][rt_b][rt_k]maskedmerge=planes=1,format=yuv420p[base]" in vf and "gt(lum(X,Y),90)" in vf
    plan.pop("retouch")
    assert "maskedmerge" not in video_filter(plan, {"a.mp4": 0}, [], [], (1080, 1920))


def test_transitions_and_person_effects_in_the_filter():
    from editor.render import video_filter
    plan = {"segments": [{"src": "a.mp4", "in": 0.0, "out": 6.0}], "broll": [], "graphics": [], "looks": [],
            "transitions": [{"type": t, "at": 1.0 + i} for i, t in enumerate(("flash", "whip", "zoom", "dip", "glitch"))]}
    vf = video_filter(plan, {"a.mp4": 0}, [], [], (1080, 1920),
                      person_inputs=[({"type": "spotlight", "at": 0.5, "dur": 1}, 1, None),
                                     ({"type": "glow", "at": 2, "dur": 1}, 2, 3)])
    assert "eq=saturation=0.3" in vf and "[3:v]setpts=PTS-STARTPTS+2/TB[pg1]" in vf
    for marker in ("eq=brightness=", "avgblur=sizeX=40", "eval=frame,crop=1080:1920", "drawbox=c=black",
                   "rgbashift=rh=-14"):
        assert marker in vf
    assert "scale=w=" in vf and ":enable=" not in vf.split("scale=w=")[1].split(",crop")[0]


def test_muted_and_silent_sources_become_generated_silence():
    from editor.render import voice_filter
    plan = {"segments": [{"src": "a.mp4", "in": 0.0, "out": 2.0, "mute": True},
                         {"src": "b.mov", "in": 0.0, "out": 1.5},
                         {"src": "c.mp4", "in": 1.0, "out": 2.0}]}
    af = voice_filter(plan, {"a.mp4": 0, "b.mov": 1, "c.mp4": 2}, model="m.rnnn", silent_srcs={"b.mov"})
    assert "anullsrc=r=48000:cl=stereo,atrim=0:2.000" in af and "anullsrc=r=48000:cl=stereo,atrim=0:1.500" in af
    assert "[0:a]" not in af and "[1:a]" not in af and "[2:a]atrim=start=1.0:end=2.0" in af


def test_zoom_crops_around_the_focus_point():
    from editor.render import segments_filter
    plan = {"segments": [{"src": "a.mp4", "in": 0.0, "out": 1.0, "zoom": 2.0, "focus": [0.5, 0.3]},
                         {"src": "a.mp4", "in": 1.0, "out": 2.0}]}
    f = ";".join(segments_filter(plan, {"a.mp4": 0}, (1080, 1920)))
    assert "scale=2160:3840" in f and "y='min(max(ih*0.3-oh/2,0),ih-oh)'" in f
    assert "x='min(max(iw*0.5-ow/2,0),iw-ow)'" in f  # no focus: centred, as before


def test_sfx_volume_sets_the_gain_on_every_effect(monkeypatch):
    from editor import render as r
    seen = []
    monkeypatch.setattr(r.ffmpeg, "run", lambda args: seen.append(" ".join(map(str, args))))
    plan = {"sfx": [{"kind": "hit", "at": 1.0}], "sfx_volume": 0.1, "music": {}}
    r._mix("v.wav", None, plan, ["hit.wav"], 5.0, "out.wav")
    assert "adelay=1000|1000,volume=0.1[s0]" in seen[0]


def test_segment_frames_keep_every_cut_on_its_planned_frame():
    from editor.render import FPS, segment_frames, segments_filter
    segs = [{"src": "a.mp4", "in": 0.0, "out": 0.535}] * 40
    frames = segment_frames(segs)
    assert sum(frames) == round(40 * 0.535 * FPS) and set(frames) <= {16, 17}
    f = ";".join(segments_filter({"segments": segs[:1]}, {"a.mp4": 0}, (1080, 1920)))
    assert "trim=end_frame=16" in f


def test_split_broll_puts_the_shot_on_top_and_the_speaker_below():
    p = _plan()
    p["broll"][0]["frame"] = "top"
    f = render.video_filter(p, {"raw/a.mp4": 0}, [(p["broll"][0], 1)], [], (1080, 1920))
    assert "scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960" in f  # the shot fills the top half
    assert "crop=1080:960:0:154" in f  # head and chest from 8% down the frame
    assert "overlay=0:960:enable='gte(t,0.4833)*lt(t,1.4833)'" in f  # the speaker's half goes in the lower half
    assert "overlay=0:0:enable='gte(t,0.4833)*lt(t,1.4833)'" in f
