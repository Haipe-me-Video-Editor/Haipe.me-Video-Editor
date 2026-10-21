"""Command line for every stage. Claude edits transcript.json, edit.json and work/captions.json between stages."""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from . import analyze, broll, captions, color, config, cuts, editjson, faces, ffmpeg, music, profile, score
from .config import FORMATS
from .pack import pack
from .render import render
from .review import review
from .sheets import contact_sheet
from .style import load_style
from .transcribe import align, load_glossary, segments_from_words, transcribe

SHEET_WINDOW = 30.0


def _meta(proj: Path) -> dict:
    return json.loads((proj / "project.json").read_text())


def _tr(proj: Path) -> dict:
    return json.loads((proj / "transcript.json").read_text(encoding="utf-8"))


def _save_tr(proj: Path, tr: dict) -> None:
    (proj / "transcript.json").write_text(json.dumps(tr, ensure_ascii=False, indent=2), encoding="utf-8")
    if tr.get("words"):
        (proj / "transcript_packed.md").write_text(pack(tr["words"]), encoding="utf-8")


def cmd_new(a):
    proj = Path(a.project)
    (proj / "raw").mkdir(parents=True, exist_ok=True)
    (proj / "proxy").mkdir(exist_ok=True)
    src = Path(a.source)
    dst = proj / "raw" / src.name
    shutil.copy2(src, dst)
    info = ffmpeg.probe(dst)
    if not info["has_audio"]:
        sys.exit(f"{src.name} has no audio track; talking-head mode needs speech.")
    if color.is_hdr(info):  # iPhone HDR: tone-map once so every later step works in standard colour
        print(f"note: {src.name} is HDR ({info['transfer']}); converting to standard Rec.709 colour for editing.")
        dst = color.to_sdr(dst, proj / "raw" / f"{src.stem}-sdr.mp4")
        info = ffmpeg.probe(dst)
    ffmpeg.run(["-i", dst, "-vf", "scale='if(gt(iw,ih),-2,720)':'if(gt(iw,ih),720,-2)'",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k",
                proj / "proxy" / f"{src.stem}.mp4"])
    (proj / "project.json").write_text(json.dumps(
        {"source": f"raw/{dst.name}", "proxy": f"proxy/{src.stem}.mp4", "brief": a.brief, "probe": info}, indent=2))
    profile.snapshot(proj)
    if profile.note():
        print(profile.note())


def cmd_motion(a):
    """A project with no speaker: announcements, news cards, promos. The base is a brand background clip (looped
    or trimmed to --dur) or a solid colour; graphics, overlays, B-roll, music and sound go on it as usual."""
    proj = Path(a.project)
    (proj / "raw").mkdir(parents=True, exist_ok=True)
    (proj / "work").mkdir(exist_ok=True)
    W, H = FORMATS[a.format]
    dst = proj / "raw" / "base.mp4"
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30,format=yuv420p"
    src = ["-stream_loop", "-1", "-i", a.bg] if a.bg else ["-f", "lavfi", "-i", f"color=c={a.color}:s={W}x{H}:r=30"]
    ffmpeg.run([*src, "-t", f"{a.dur:.3f}", "-vf", fit, "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "14",
                *color.TAGS, dst])
    info = ffmpeg.probe(dst)
    (proj / "project.json").write_text(json.dumps(
        {"source": "raw/base.mp4", "proxy": "raw/base.mp4", "brief": a.brief, "probe": info, "motion": True},
        indent=2))
    _save_tr(proj, {"language": None, "engine": None, "notes": [], "words": None, "error": None})
    (proj / "faces.json").write_text(json.dumps({"source": [W, H], "samples": []}))  # no face: cards keep their slots
    plan = editjson.new_plan([{"src": "raw/base.mp4", "in": 0.0, "out": round(info["duration"], 3)}], fmt=a.format)
    plan.update(retouch=0, captions={**plan["captions"], "enabled": False})
    plan["notes"].append("Motion project: no speaker. Base: " + (Path(a.bg).name if a.bg else a.color) + ".")
    editjson.save(proj / "edit.json", plan)
    print(f"{proj / 'edit.json'}: {info['duration']:.2f}s base; add graphics, overlays, sfx and music, then render")


def cmd_analyze(a):
    proj = Path(a.project)
    meta = _meta(proj)
    src, proxy, dur = proj / meta["source"], proj / meta["proxy"], meta["probe"]["duration"]
    (proj / "silences.json").write_text(json.dumps(analyze.silences(src, duration=dur)))
    (proj / "loudness.json").write_text(json.dumps(analyze.loudness(src)))
    (proj / "scenes.json").write_text(json.dumps(analyze.scenes(proxy)))
    if a.transcript_file:
        tr = {"language": "en", "engine": "file", "notes": [], "error": None,
              "words": json.loads(Path(a.transcript_file).read_text(encoding="utf-8"))}
    elif a.no_transcribe:
        tr = {"language": None, "engine": None, "notes": [], "words": None, "error": "transcription skipped"}
    else:
        glossary = load_glossary(a.glossary) if a.glossary else None
        tr = transcribe(src, proj / "work", language=a.language, glossary=glossary)
    _save_tr(proj, tr)
    try:
        (proj / "faces.json").write_text(json.dumps(faces.detect(src)))
    except Exception as e:  # graphics then fall back to a typical talking-head framing
        tr.setdefault("notes", []).append(f"Face detection unavailable ({type(e).__name__}: {e}).")
    index, start, i = [], 0.0, 0
    while start < dur:
        end = min(dur, start + SHEET_WINDOW)
        f = f"sheets/src-{i:02d}.jpg"
        index.append({"file": f, "start": start, "end": end,
                      "times": contact_sheet(proxy, proj / f, start=start, end=end)})
        start, i = end, i + 1
    (proj / "sheets" / "index.json").write_text(json.dumps(index, indent=2))
    for note in tr.get("notes", []) + ([tr["error"]] if tr.get("error") else []):
        print(f"note: {note}")


def cmd_align(a):
    proj = Path(a.project)
    tr = _tr(proj)
    if not tr.get("words"):
        sys.exit("align: transcript.json has no words to align (transcription was skipped or failed)")
    wav = proj / "work" / "audio16k.wav"
    if not wav.exists():
        ffmpeg.run(["-i", proj / _meta(proj)["source"], "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav])
    tr["words"] = align(wav, segments_from_words(tr["words"]), tr["language"] or "en")
    tr["engine"] = (tr.get("engine") or "") + "+realigned"
    _save_tr(proj, tr)


def _notes(removed: list, dur: float, total: float, tr: dict) -> list:
    notes = [f"Cut from {dur:.1f}s to {total:.1f}s."]
    fillers = [r for r in removed if r["kind"] == "filler"]
    if fillers:
        notes.append(f"Removed {len(fillers)} filler(s): " + ", ".join(sorted({r['text'] for r in fillers})) + ".")
    for r in removed:
        if r["kind"] == "retake":
            notes.append(f'Dropped a retake at {r["start"]:.1f}s: "{r["text"]}".')
    notes += tr.get("notes", [])
    if tr.get("error"):
        notes.append(f"No transcript ({tr['error']}): cut on silences only, no captions.")
    return notes


def write_timeline_transcript(proj: Path, plan: dict, words: list | None) -> None:
    """transcript_timeline.md: the packed transcript in timeline seconds, for placing overlays."""
    if words:
        (proj / "transcript_timeline.md").write_text(pack(captions.timeline_words(plan["segments"], words)),
                                                     encoding="utf-8")


def cmd_draft(a):
    proj = Path(a.project)
    meta = _meta(proj)
    dur = meta["probe"]["duration"]
    tr = _tr(proj)
    sil = json.loads((proj / "silences.json").read_text())
    energy = analyze.rms_db(proj / meta["source"], cuts.ENERGY_HOP)
    segments, removed = cuts.plan_cuts(meta["source"], dur, words=tr.get("words"), silences=sil, energy=energy)
    plan = editjson.new_plan(segments, fmt=a.format)
    plan["captions"].update(enabled=bool(tr.get("words")), mode=a.captions)
    total = editjson.timeline_duration(plan)
    (proj / "work").mkdir(exist_ok=True)
    track = None
    if a.music_dir:
        track = music.choose(music.build_index(Path(a.music_dir), proj / "music-index.json"), total)
    if track:
        plan["music"]["src"] = str((Path(a.music_dir) / track["file"]).resolve())
    else:
        score.write_score(proj / "work" / "score.wav", total + 0.5)
        plan["music"]["src"] = "work/score.wav"
    plan["notes"] = _notes(removed, dur, total, tr)
    editjson.save(proj / "edit.json", plan)
    write_timeline_transcript(proj, plan, tr.get("words"))
    print(f"draft: {len(segments)} segments, {total:.1f}s")


def cmd_timeline(a):
    proj = Path(a.project)
    write_timeline_transcript(proj, editjson.load(proj / "edit.json"), _tr(proj).get("words"))


def cmd_captions(a):
    proj = Path(a.project)
    plan = editjson.load(proj / "edit.json")
    tr = _tr(proj)
    lines = captions.ensure_lines(proj / "work" / "captions.json", plan, tr["words"], load_style(a.style),
                                  FORMATS[plan["format"]], rebuild=True)
    mode = plan["captions"]["mode"]
    need = mode == "bilingual" or (mode in ("ar", "en") and mode != tr.get("language"))
    print(f"{len(lines)} caption lines" + ("; fill 'tr' on every line in work/captions.json" if need else ""))


def cmd_render(a):
    proj = Path(a.project)
    if getattr(a, "master", False):
        os.environ["EDITOR_MASTER"] = "1"  # read by every encode step (editor/quality.py)
    out = render(proj, editjson.load(proj / "edit.json"), load_style(a.style), draft=getattr(a, "draft", False))
    print(f"rendered {out['final']}")


def _floats(text: str | None) -> list:
    return [float(x) for x in text.split(",") if x.strip()] if text else []


def cmd_tightcut(a):
    """Cut sentence to sentence and reframe every shot; writes work/tightcut.json and edit.json's segments."""
    from . import tightcut
    proj = Path(a.project)
    src = a.src or _meta(proj)["source"]
    words = None
    if (proj / "transcript.json").exists():
        words = [[w["start"], w["end"], w["w"]] for w in _tr(proj).get("words") or [] if w.get("start") is not None]
    end = a.end if a.end is not None else ffmpeg.probe(proj / src)["duration"]
    caps = dict(zip(_floats(a.cap_tail)[::2], _floats(a.cap_tail)[1::2]))
    rec = tightcut.build(proj, src, a.start, end, keep_cuts=_floats(a.keep_cuts), cut_pauses=_floats(a.cut_pauses),
                         tail_caps=caps, words=words, framing=not a.no_framing)
    path = proj / "edit.json"
    plan = editjson.load(path) if path.exists() else editjson.new_plan(rec["segments"], fmt=a.format)
    plan["segments"] = rec["segments"]
    editjson.save(path, plan)
    total = sum(b - x for x, b in rec["spans"])
    print(f"tightcut: {len(rec['spans'])} shots, {end - a.start:.1f}s -> {total:.1f}s; extended out points "
          f"{rec['nominal'] or 'none'}")
    if rec["pauses"]:
        print("kept short pauses (cut the ones that end a sentence with --cut-pauses):")
        for p in rec["pauses"]:
            print(f"  {p['at']:7.2f}  {p['gap']:.2f}s  {p['before']} | {p['after']}")


def cmd_kwcheck(a):
    from .kwcheck import check
    sheets = check(Path(a.project), load_style(a.style), only={int(x) for x in a.only.split(",")} if a.only else None)
    print("look at: " + ", ".join(sheets))


def cmd_review(a):
    proj = Path(a.project)
    result = review(proj, editjson.load(proj / "edit.json"), load_style(a.style))
    for c in result["checks"]:
        print(f"{'PASS' if c['ok'] else 'FAIL'}  {c['name']}: {c['detail']}")
    print("look at: " + ", ".join([result["sheet"], *result["cut_views"]]))
    sys.exit(0 if result["passed"] else 1)


def cmd_run(a):
    cmd_new(a)
    cmd_analyze(a)
    cmd_draft(a)
    cmd_captions(a)
    cmd_render(a)
    cmd_review(a)


def cmd_broll_index(a):
    entries = broll.index_clips(a.broll_dir, a.index)
    print(f"{len(entries)} clips, {sum(1 for e in entries if not e['tags'])} need tags")


def cmd_broll_sheets(a):
    for e in broll.index_clips(a.broll_dir, a.index):
        if e["tags"] or e["kind"] == "image":
            continue
        out = Path(a.broll_dir) / ".sheets" / f"{Path(e['file']).stem}.jpg"
        contact_sheet(Path(a.broll_dir) / e["file"], out, cols=3, rows=2)
        print(f"{e['file']} -> {out}")


def cmd_broll_tag(a):
    broll.tag(a.index, a.file, a.tags.split(","), a.subject, a.mood, a.setting)


def cmd_broll_resolve(a):
    proj = Path(a.project)
    plan = editjson.load(proj / "edit.json")
    notes = broll.resolve(plan, broll.index_clips(a.broll_dir, a.index), a.broll_dir)
    plan["notes"] += notes
    editjson.save(proj / "edit.json", plan)
    print("\n".join(notes) or "all B-roll resolved")


def cmd_extras(a):
    from . import extras
    print("\n".join(extras.ensure_all()))


def cmd_doctor(a):
    from . import extras
    report = extras.doctor()
    for name, status in report.items():
        print(f"{name:20} {status}")
    if any(str(v).startswith("FAIL") for v in report.values()):
        raise SystemExit(1)


def cmd_retouch(a):
    from .fonts import ensure_font
    from .retouch import retouch_video
    fonts = str(ensure_font("Sora").parent) if a.ass else None
    print(retouch_video(a.source, a.out, a.preset, ass=a.ass, fonts_dir=fonts, chat=a.chat))


def cmd_studio_voice(a):
    from . import voice
    out = Path(a.out)
    wav = voice.studio_restore(a.source, out.with_suffix(".voice.wav"), out.parent / "work-voice")
    print(voice.mux(a.video or a.source, wav, out))


def cmd_reel_prep(a):
    from . import reel
    print(reel.prep(a.source, a.work))


def _upload(a) -> bool:
    """Internal edition: always (unless --no-upload), as it always has. Public edition: only when asked (--upload,
    EDITOR_UPLOAD=gofile) or when the file cannot be handed over any other way, a cloud session whose disk the user
    cannot open (EDITOR_UPLOAD=off stops that). A Gofile page is open to anyone holding its link, so on a user's own
    computer a video never leaves it by default."""
    if a.no_upload:
        return False
    if config.EDITION == "internal":  # the internal engine always delivers a link
        return True
    mode = os.environ.get("EDITOR_UPLOAD", "").lower()
    cloud = os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true"
    return a.upload or mode == "gofile" or (cloud and mode != "off")


def cmd_reel_deliver(a):
    from . import reel
    from .deliver import gofile
    out = reel.deliver(a.source, a.work, a.out_dir, style=a.style)
    if not a.no_qc:
        from .qc import gate
        gate(out["master"], source=a.source)
    print(f"master {out['master']}\npreview {out['preview']}")
    if _upload(a):
        print(f"gofile {gofile(out['master'])}")


def cmd_qc(a):
    from .qc import qc, report
    w, h = (int(x) for x in a.size.split("x"))
    r = qc(a.video, source=a.source, size=(w, h), min_kbps=None if a.preview else a.min_kbps, cut=a.cut)
    print(report(r))
    raise SystemExit(0 if r["passed"] else 1)


def cmd_clips_prep(a):
    from . import clips
    print(clips.prep(a.source, a.work, a.language))


def cmd_clips_render(a):
    from . import clips
    from .deliver import gofile
    for c in clips.render(a.source, a.work, a.out_dir, voice=a.voice, retouch=not a.no_retouch, only=a.only,
                         style=a.style):
        print(f"{c['name']}: master {c['master']}  preview {c['preview']}")
        if not a.no_qc:
            from .qc import gate
            gate(c["master"], cut=True)
        if _upload(a):
            print(f"  gofile {gofile(c['master'])}")


def cmd_stock(a):
    from . import stock
    notes = []
    hits = stock.search(a.query, tuple(a.sources) if a.sources else stock.ALL, per_source=a.n,
                        portrait=True if a.portrait else None, notes=notes)
    dest = Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "hits.json").write_text(json.dumps(hits, ensure_ascii=False, indent=1))
    stock.contact_sheet(hits, dest / "sheet.jpg")
    for i, h in enumerate(hits):
        print(f"{i:3d} {h['source']:8s} {h['duration'] or 0:5.1f}s {h['width']}x{h['height']} {h['title'][:60]}")
    for n in notes:
        print("note:", n)
    print(f"sheet {dest / 'sheet.jpg'}; download with: stock-get {dest} <numbers>")


def cmd_stock_get(a):
    from . import stock
    hits = json.loads((Path(a.dest) / "hits.json").read_text())
    for i in a.numbers:
        print(stock.download(hits[int(i)], a.dest))


def cmd_critique(a):
    from . import critique
    if a.check:
        probs = critique.check(a.project)
        for pr in probs:
            print("FAIL", pr)
        print("critique: all items scored", critique.PASS, "or more" if not probs else f"{len(probs)} open")
        raise SystemExit(1 if probs else 0)
    path = critique.build(a.project, a.video)
    data = json.loads(path.read_text())
    todo = [i for i in data["items"] if i["score"] is None]
    print(f"round {data['round']}: {len(data['items'])} items, {len(todo)} to score -> {path}")
    for i in todo:
        print(f"  {i['sheet']}  {i['key']} {i['label']}")


def cmd_profile(a):
    """Print the creator profile, or say where the interview is when there is none."""
    text = profile.load()
    print(f"{profile.PROFILE}\n\n{text}" if text else profile.note())


def cmd_fx_list(a):
    from .fx import registry
    for name, mod in sorted(registry().items()):
        lo, hi = getattr(mod, "DUR", (0.5, 30))
        print(f"{name:14s} {lo}-{hi}s  best for {', '.join(getattr(mod, 'BEST_FOR', []))}\n    {mod.DOC}")
        for k, v in mod.PARAMS.items():
            print(f"      {k} = {v!r}")


def cmd_fx_apply(a):
    from .fx.apply import apply_fx
    fx = json.loads(Path(a.fx).read_text(encoding="utf-8"))
    fx = fx.get("fx", fx) if isinstance(fx, dict) else fx
    print(apply_fx(a.video, fx, Path(a.out).parent / "fx-work", load_style(a.style), fps=a.fps,
                   project=a.project, out=a.out))


def cmd_fx_sample(a):
    """One effect on a piece of a clip, with a second of context either side, for a quick look."""
    from .fx.apply import apply_fx
    spec = {"type": a.type, **json.loads(a.params or "{}")}
    pad = 1.0
    start = max(0.0, a.at - pad)
    piece = Path(a.out).with_suffix(".piece.mp4")
    ffmpeg.run(["-ss", f"{start:.3f}", "-i", a.video, "-t", f"{a.dur + 2 * pad:.3f}", "-vf",
                f"fps={a.fps},scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", "-c:v", "libx264",
                "-crf", "12", "-preset", "veryfast", "-c:a", "aac", piece])
    spec.update(at=round(a.at - start, 3), dur=a.dur)
    print(apply_fx(piece, [spec], Path(a.out).parent / "fx-work", load_style(a.style), fps=a.fps,
                   project=a.project, out=a.out))


def main(argv: list | None = None) -> None:
    ap = argparse.ArgumentParser(prog="editor")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *positional):
        p = sub.add_parser(name)
        for arg in positional:
            p.add_argument(arg)
        p.set_defaults(fn=fn)
        return p

    def analyze_opts(p):
        p.add_argument("--language", default="auto", choices=["auto", "ar", "en"])
        p.add_argument("--glossary")
        p.add_argument("--no-transcribe", action="store_true")
        p.add_argument("--transcript-file")

    def draft_opts(p):
        p.add_argument("--format", default="9:16", choices=sorted(FORMATS))
        p.add_argument("--music-dir")
        p.add_argument("--captions", default="source", choices=list(editjson.CAPTION_MODES))

    add("profile", cmd_profile)
    p = add("new", cmd_new, "project", "source")
    p.add_argument("--brief", default="")
    p = add("motion", cmd_motion, "project")
    p.add_argument("--dur", type=float, required=True, help="length in seconds")
    p.add_argument("--bg", help="background clip, looped or trimmed to --dur (default: a solid colour)")
    p.add_argument("--color", default="#101114", help="solid background colour when there is no --bg")
    p.add_argument("--format", default="9:16", choices=sorted(FORMATS))
    p.add_argument("--brief", default="")
    p = add("run", cmd_run, "project", "source")
    p.add_argument("--brief", default="")
    p.add_argument("--style", default="default")
    analyze_opts(p)
    draft_opts(p)
    analyze_opts(add("analyze", cmd_analyze, "project"))
    add("align", cmd_align, "project")
    draft_opts(add("draft", cmd_draft, "project"))
    add("timeline", cmd_timeline, "project")
    p = add("retouch", cmd_retouch, "source", "out")
    p.add_argument("--preset", default="natural", choices=["gentle", "natural"])
    p.add_argument("--ass")
    p.add_argument("--chat", action="store_true", help="cap the bitrate to fit the 30 MB chat limit")
    add("reel-prep", cmd_reel_prep, "source", "work")
    from . import capture
    p = add("capture", capture.cmd, "url", "out")
    p.add_argument("--steps", help="JSON list of steps: wait, scroll, tap, type, shot")
    p.add_argument("--device", default="phone", choices=["phone", "desktop"])
    p.add_argument("--wait", type=float, default=1.5, help="seconds to let the page settle")
    from . import cover
    p = add("cover", cover.cmd, "video", "out_dir")
    p.add_argument("--title", required=True, help="the headline: 2-5 words")
    p.add_argument("--accent", nargs="*", default=[], help="words drawn in the accent colour")
    p.add_argument("--sub", help="a small line under the headline")
    p.add_argument("--style", help="brand or style name: its accent and cover_bg colours are used")
    p.add_argument("--layouts", nargs="*", default=list(cover.LAYOUTS), choices=list(cover.LAYOUTS))
    p.add_argument("--sizes", nargs="*", default=["reel", "youtube"], choices=list(cover.SIZES))
    p.add_argument("--at", type=float, help="use the frame at this second instead of picking one")
    p.add_argument("--image", help="a product photo, screenshot or result for the object layout")
    p.add_argument("--video-title", help="the post's title: the check flags a headline that repeats it")
    from . import stylepick
    p = add("style-pick", stylepick.cmd, "project")
    p.add_argument("--check", action="store_true", help="check edit.json against the variety rules instead")
    add("fx-list", cmd_fx_list)
    p = add("fx-apply", cmd_fx_apply, "video", "fx", "out")
    p.add_argument("--style", default="default")
    p.add_argument("--fps", type=float, default=30)
    p.add_argument("--project")
    p = add("fx-sample", cmd_fx_sample, "video", "type", "out")
    p.add_argument("--at", type=float, required=True)
    p.add_argument("--dur", type=float, required=True)
    p.add_argument("--params", help="JSON object of the effect's fields")
    p.add_argument("--style", default="default")
    p.add_argument("--fps", type=float, default=30)
    p.add_argument("--project")
    p = add("critique", cmd_critique, "project")
    p.add_argument("--video", help="score this render instead of out/final.mp4")
    p.add_argument("--check", action="store_true", help="fail unless every item scored 8+")
    from . import fetch
    add("fetch", fetch.cmd, "link", "dest")
    from . import animate
    animate.register(add)
    from . import stock
    p = add("stock", cmd_stock, "query", "dest")
    p.add_argument("--sources", nargs="*", choices=list(stock.ALL))
    p.add_argument("--n", type=int, default=8, help="results per source")
    p.add_argument("--portrait", action="store_true")
    p = add("stock-get", cmd_stock_get, "dest")
    p.add_argument("numbers", nargs="+")
    p = add("clips-prep", cmd_clips_prep, "source", "work")
    p.add_argument("--language", default="ar", choices=["ar", "en"])
    p = add("qc", cmd_qc, "video")
    p.add_argument("--source", help="the original clip: the length must match unless --cut")
    p.add_argument("--cut", action="store_true", help="the edit removed time; skip the length check")
    p.add_argument("--size", default="1080x1920")
    p.add_argument("--min-kbps", type=int, default=8000, help="video bitrate floor for a master")
    p.add_argument("--preview", action="store_true", help="a chat preview: skip the bitrate floor")
    p = add("clips-render", cmd_clips_render, "source", "work", "out_dir")
    p.add_argument("--style", default="default", help="style name (built-in or brand pack) or a .json path")
    p.add_argument("--voice", default="studio", choices=["studio", "original"])
    p.add_argument("--no-retouch", action="store_true")
    p.add_argument("--only", nargs="*", help="render just these clip names")
    p.add_argument("--upload", action="store_true",
                   help="also upload the master to Gofile (anyone with the link can download it)")
    p.add_argument("--no-upload", action="store_true", help="never upload, even with EDITOR_UPLOAD=gofile")
    p.add_argument("--no-qc", action="store_true", help="deliver even if the quality check fails")
    p = add("reel-deliver", cmd_reel_deliver, "source", "work", "out_dir")
    p.add_argument("--style", default="default", help="style name (built-in or brand pack) or a .json path")
    p.add_argument("--upload", action="store_true",
                   help="also upload the master to Gofile (anyone with the link can download it)")
    p.add_argument("--no-upload", action="store_true", help="never upload, even with EDITOR_UPLOAD=gofile")
    p.add_argument("--no-qc", action="store_true", help="deliver even if the quality check fails")
    p = add("studio-voice", cmd_studio_voice, "source", "out")
    p.add_argument("--video", help="take the picture from this file (e.g. the retouched copy); audio from source")
    for name, fn in (("captions", cmd_captions), ("render", cmd_render), ("review", cmd_review)):
        p = add(name, fn, "project")
        p.add_argument("--style", default="default")
        if name == "render":
            p.add_argument("--draft", action="store_true", help="fast encode for feedback rounds")
            p.add_argument("--master", action="store_true", help="maximum quality: near-lossless steps, CRF 10, 320k audio")
    p = add("tightcut", cmd_tightcut, "project")
    p.add_argument("--src", help="source inside the project (default: project.json's source)")
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--end", type=float)
    p.add_argument("--keep-cuts", help="your own cut points to keep, comma-separated seconds")
    p.add_argument("--cut-pauses", help="short pauses that end a sentence (their start times), comma-separated")
    p.add_argument("--cap-tail", help="t,max pairs: cap the hiss-tail extension at out point t")
    p.add_argument("--no-framing", action="store_true")
    p.add_argument("--format", default="9:16", choices=sorted(FORMATS))
    p = add("kwcheck", cmd_kwcheck, "project")
    p.add_argument("--style", default="default")
    p.add_argument("--only", help="graphic indices, comma-separated")
    add("broll-index", cmd_broll_index, "broll_dir", "index")
    add("broll-sheets", cmd_broll_sheets, "broll_dir", "index")
    p = add("broll-tag", cmd_broll_tag, "index", "file")
    p.add_argument("--tags", required=True)
    for opt in ("--subject", "--mood", "--setting"):
        p.add_argument(opt, default="")
    add("broll-resolve", cmd_broll_resolve, "project", "broll_dir", "index")
    add("extras", cmd_extras)
    add("doctor", cmd_doctor)
    try:
        from . import cli_extra  # commands only some copies of the engine carry
    except ImportError:
        pass
    else:
        cli_extra.register(add)
    a = ap.parse_args(argv)
    a.fn(a)
