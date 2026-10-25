"""Turn edit.json into finished videos with ffmpeg: audio and video built separately, then muxed."""
import hashlib
import json
import math
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import analyze, captions, color, cutout, faces, ffmpeg, fonts, grade, layout, overlays, quality, score, voice
from .broll import IMAGE_EXTS
from .config import FORMATS, FPS, TO_YUV
from .editjson import SFX_VOLUME, seg_len, timeline_duration
from .graphics.desk import render_desk
from .graphics.kit import KIT_TYPES
from .graphics.render import render_graphic


def _even(x: float) -> int:
    return int(round(x / 2)) * 2


def _r(x: float) -> float:
    return round(x, 3)


def _atempo_chain(speed: float) -> list:
    """atempo takes 0.5-2.0 per stage; chain stages for slower or faster speeds."""
    out = []
    while speed > 2.0:
        out.append(2.0)
        speed /= 2.0
    while speed < 0.5:
        out.append(0.5)
        speed /= 0.5
    return out + ([round(speed, 4)] if abs(speed - 1.0) > 1e-6 else [])


def voice_filter(plan: dict, src_index: dict, voice_settings: dict | None = None, model=None,
                 silent_srcs: set = frozenset()) -> str:
    """Voice from every segment, cleaned. Muted segments, and sources with no audio track, become silence."""
    parts, labels = [], []
    for i, s in enumerate(plan["segments"]):
        k, d = src_index[s["src"]], seg_len(s)
        if s.get("mute") or s["src"] in silent_srcs:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{d:.3f},asetpts=PTS-STARTPTS[a{i}]")
            labels.append(f"[a{i}]")
            continue
        tempo = "".join(f"atempo={f}," for f in _atempo_chain(s.get("speed", 1.0)))
        parts.append(f"[{k}:a]atrim=start={s['in']}:end={s['out']},asetpts=PTS-STARTPTS,{tempo}"
                     f"afade=t=in:d=0.03,afade=t=out:st={max(d - 0.03, 0):.3f}:d=0.03[a{i}]")
        labels.append(f"[a{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1,{voice.chain(voice_settings, model)}[voice]")
    return ";".join(parts)


BAR_FRAC = 0.11  # each cinematic bar covers 11% of the height: clear of captions (12%-80%)
VIGNETTE_ANGLE = 0.9  # radians; ffmpeg's vignette is invisible at 0
LOOK_EASE = 0.35  # seconds to ease a look in and out


def _ease(at: float, dur: float) -> str:
    """ffmpeg expression: 0 -> 1 -> 0 over [at, at+dur], smoothstep in and out."""
    p = f"clip(min((t-{_r(at)})/{LOOK_EASE},({_r(at + dur)}-t)/{LOOK_EASE}),0,1)"
    return f"({p})*({p})*(3-2*({p}))"


def looks_filter(looks: list, cur: str, size: tuple) -> tuple[list, str]:
    """Vignette and cinematic bars over the footage, under graphics and captions.
    Bars are black strips that slide in from the top and bottom edges."""
    W, H = size
    hb = _even(H * BAR_FRAC)
    parts = []
    for j, x in enumerate(looks):
        at, dur, e = x["at"], x["dur"], _ease(x["at"], x["dur"])
        on = f"enable='between(t,{_r(at)},{_r(at + dur)})'"
        if x["type"] == "blur":  # focus pull: the frame goes soft so text on top pops
            k = _ease(at, dur).replace("t", "T")
            parts.append(f"[{cur}]split[fb{j}a][fb{j}b];[fb{j}b]gblur=sigma={x.get('sigma', 22)}[fb{j}c];"
                         f"[fb{j}a][fb{j}c]blend=all_expr='A*(1-{k})+B*({k})':{on}[lk{j}]")
            cur = f"lk{j}"
            continue
        if x["type"] == "vignette":
            parts.append(f"[{cur}]vignette=angle='{VIGNETTE_ANGLE}*{e}':eval=frame:{on}[lk{j}]")
        else:
            parts.append(f"color=c=black:s={W}x{hb}:r={FPS},split[bt{j}][bb{j}]")
            parts.append(f"[{cur}][bt{j}]overlay=x=0:y='-{hb}+{hb}*{e}':{on}:shortest=1[lt{j}]")
            parts.append(f"[lt{j}][bb{j}]overlay=x=0:y='{H}-{hb}*{e}':{on}:shortest=1[lk{j}]")
        cur = f"lk{j}"
    return parts, cur


def segment_frames(segments: list) -> list:
    """Frames per segment, so that every cut falls on the frame nearest its planned time. Rounding each segment
    on its own (fps alone rounds up) drifted a 40-shot montage half a second off the beat by the end."""
    frames, t, done = [], 0.0, 0
    for s in segments:
        t += seg_len(s)
        n = max(1, round(t * FPS) - done)
        frames.append(n)
        done += n
    return frames


def segment_inputs(plan: dict) -> list:
    """One input per segment, seeked to its in point: each is decoded only for its own span. Trimming one
    shared input instead buffers every later segment's frames (a 4K source filled 10 GB that way)."""
    out = []
    for s in plan["segments"]:
        span = (s["out"] - s["in"]) + 2 * s.get("speed", 1.0) / FPS
        out += ["-ss", f"{s['in']:.3f}", "-t", f"{span:.3f}", "-i", s["src"]]
    return out


def segments_filter(plan: dict, src_index: dict, size: tuple, seeked: bool = False) -> list:
    """The cut talking head at the output size, as filter parts ending in [base]. With seeked, input i is
    segment i already seeked to its in point (segment_inputs)."""
    W, H = size
    parts, labels = [], []
    for i, (s, frames) in enumerate(zip(plan["segments"], segment_frames(plan["segments"]))):
        z = s.get("zoom", 1.0)
        fx, fy = s.get("focus", (0.5, 0.5))
        speed = s.get("speed", 1.0)
        pts = "PTS-STARTPTS" if speed == 1.0 else f"(PTS-STARTPTS)/{speed}"
        # The source is read one frame long and cut to an exact frame count, so cuts stay where the plan put them.
        end = round(s["out"] + speed / FPS, 3)
        cut = (f"[{i}:v]trim=start=0:end={round(end - s['in'], 3)}" if seeked
               else f"[{src_index[s['src']]}:v]trim=start={s['in']}:end={end}")
        if s.get("push"):  # slow push-in across the segment: zoom eases from z to push
            zz = f"({z}+({s['push']}-{z})*(1-pow(1-min(t/{frames / FPS:.3f},1),2)))"
            size_expr = f"w='2*trunc({W}*{zz}/2)':h='2*trunc({H}*{zz}/2)':eval=frame"
        else:
            size_expr = f"{_even(W * z)}:{_even(H * z)}:force_original_aspect_ratio=increase"
        parts.append(f"{cut},setpts={pts},fps={FPS},"
                     f"trim=end_frame={frames},setpts=PTS-STARTPTS,"
                     f"scale={size_expr},"
                     f"crop={W}:{H}:x='min(max(iw*{fx}-ow/2,0),iw-ow)':y='min(max(ih*{fy}-oh/2,0),ih-oh)',"
                     + (s["_grade"] + "," if s.get("_grade") else "") + f"setsar=1,format=yuv420p[v{i}]")
        labels.append(f"[v{i}]")
    strength = plan.get("retouch", 0)
    parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[{'raw' if strength else 'base'}]")
    if strength:
        parts.append(retouch_filter("raw", "base", strength, size))
    return parts


# Skin tones in YCbCr, any complexion; brightness above 90 keeps dark features (frames, brows, facial hair) out.
SKIN = "255*between(cb(X,Y),77,127)*between(cr(X,Y),133,173)*gt(lum(X,Y),90)"


def retouch_filter(src: str, dst: str, strength: float, size: tuple) -> str:
    """Light skin smoothing: an edge-preserving blur of brightness only, blended in where the colour is skin, at
    `strength`. Colour (the chroma planes) is never touched, so skin tone can't shift. Eyes, brows, lips, beard,
    hair and glasses fall outside the skin mask and stay sharp."""
    W, H = size
    return (f"[{src}]format=yuv444p,split=3[rt_o][rt_s][rt_m];"
            f"[rt_s]scale={_even(W / 2)}:{_even(H / 2)},bilateral=sigmaS=5:sigmaR=0.07:planes=1,scale={W}:{H}[rt_b];"
            f"[rt_m]scale={_even(W / 4)}:{_even(H / 4)},geq=lum='{SKIN}':cb='{SKIN}':cr='{SKIN}',gblur=sigma=2,"
            f"scale={W}:{H},lutyuv=y=val*{strength}:u=val*{strength}:v=val*{strength}[rt_k];"
            f"[rt_o][rt_b][rt_k]maskedmerge=planes=1,format=yuv420p[{dst}]")


def desks_filter(desk_inputs: list, cur: str) -> tuple[list, str]:
    """Each desk: the opaque background-and-panel clip, then the cut-out speaker over it."""
    parts = []
    for j, (item, kb, kf, pl) in enumerate(desk_inputs):
        at, dur = item["at"], item["dur"]
        on = f"enable='between(t,{_r(at)},{_r(at + dur)})'"
        parts.append(f"[{kb}:v]setpts=PTS-STARTPTS+{at}/TB,{TO_YUV}[dk{j}]")
        parts.append(f"[{cur}][dk{j}]overlay={on}:eof_action=repeat[odk{j}]")
        parts.append(f"[{kf}:v]setpts=PTS-STARTPTS+{at}/TB,scale={pl['w']}:{pl['h']},{TO_YUV}[fg{j}]")
        parts.append(f"[odk{j}][fg{j}]overlay=x={pl['x']}:y={pl['y']}:{on}:eof_action=repeat[ofg{j}]")
        cur = f"ofg{j}"
    return parts, cur


def person_filter(person_inputs: list, cur: str) -> tuple[list, str]:
    """Effects on the cut-out speaker: a halo around them, or a spotlight (background dimmed and drained)."""
    parts = []
    for j, (item, kf, kg) in enumerate(person_inputs):
        at, dur = item["at"], item["dur"]
        on = f"enable='between(t,{_r(at)},{_r(at + dur)})'"
        if item["type"] == "spotlight":
            parts.append(f"[{cur}]eq=saturation=0.3:brightness=-0.13:{on}[ps{j}]")
            cur = f"ps{j}"
        if kg is not None:
            parts.append(f"[{kg}:v]setpts=PTS-STARTPTS+{at}/TB,{TO_YUV}[pg{j}]")
            parts.append(f"[{cur}][pg{j}]overlay={on}:eof_action=pass[pgo{j}]")
            cur = f"pgo{j}"
        parts.append(f"[{kf}:v]setpts=PTS-STARTPTS+{at}/TB,{TO_YUV}[pf{j}]")
        parts.append(f"[{cur}][pf{j}]overlay={on}:eof_action=pass[pfo{j}]")
        cur = f"pfo{j}"
    return parts, cur


FRAME = 1 / FPS

# The light burn, keyed frame by frame (30 fps, cut on 0):
# (seconds from the cut, red/green/blue multipliers, light strength). The light is screened on top,
# shading from deep orange (weak) to warm white (strong), brighter on the side it comes from.
LEAK_KEYS = [(-0.20, 1.00, 1.00, 1.00, 0.00), (-0.167, 1.00, 0.80, 0.75, 0.02), (-0.133, 1.00, 0.32, 0.28, 0.08),
             (-0.10, 1.00, 0.30, 0.18, 0.22), (-0.067, 1.00, 0.55, 0.20, 0.55), (-0.033, 1.00, 0.80, 0.45, 0.85),
             (0.0, 1.00, 1.00, 1.00, 0.97), (0.033, 1.00, 0.65, 0.30, 0.55), (0.067, 1.00, 0.45, 0.30, 0.20),
             (0.10, 1.00, 0.55, 0.50, 0.06), (0.133, 1.00, 0.85, 0.82, 0.00), (0.167, 1.00, 1.00, 1.00, 0.00)]
LEAK_LO, LEAK_HI = (255, 120, 30), (255, 240, 215)  # light colour at low and full strength


def _lerp_expr(keys: list, d: str) -> str:
    """ffmpeg expression: piecewise-linear value of keys [(t, v)] at time expression d."""
    out = f"{keys[-1][1]}"
    for (t0, v0), (t1, v1) in reversed(list(zip(keys, keys[1:]))):
        out = f"if(lt({d},{t1}),{v0}+({v1 - v0})*({d}-({t0}))/{t1 - t0},{out})"
    return f"if(lt({d},{keys[0][0]}),{keys[0][1]},{out})"


SWEEP_COLOR = "#ff7a1a"  # the default style's accent; render() passes the style's own accent


def _sweep_rgb(color: str) -> tuple[tuple, tuple]:
    """Edge and core of the sweep band: the colour itself, and the colour most of the way to white."""
    h = color.lstrip("#")
    edge = tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))
    return edge, tuple(round(v + 0.89 * (255 - v)) for v in edge)


def _sweep_expr(ch: str, c: float, color: str = SWEEP_COLOR) -> str:
    i = "rgb".index(ch)
    edge, core = _sweep_rgb(color)
    d = f"(T-{_r(c)})"
    pos = f"(-0.35+2.0*({d}+0.22)/0.44)"  # band centre along the diagonal, 0 = top-left, 1.5 = bottom-right
    band = f"exp(-pow(X/W+0.5*Y/H-{pos},2)/0.018)"
    wash = f"0.8*max(0,1-abs({d})/0.075)"  # the frame flashes in the band colour on the cut itself
    k = f"min(1,{band}+{wash})"
    col = f"({edge[i]}+({core[i] - edge[i]})*{band})"
    return f"clip(A+(255-A)*({k})*{col}/255,0,255)"


def _leak_expr(ch: str, c: float) -> str:
    i = "rgb".index(ch)
    d = f"(T-{_r(c)})"
    m = _lerp_expr([(k[0], k[1 + i]) for k in LEAK_KEYS], d)
    k = _lerp_expr([(k[0], k[4]) for k in LEAK_KEYS], d)
    col = f"({LEAK_LO[i]}+({LEAK_HI[i] - LEAK_LO[i]})*pow({k},3))"  # stays orange until the flare peaks
    side = "(0.7+0.3*(1-X/W))"  # light enters from the left edge
    return f"clip(A*({m})+(255-A*({m}))*({k})*{side}*{col}/255,0,255)"


def transitions_filter(transitions: list, cur: str, size: tuple) -> tuple[list, str]:
    """Hits on the cuts: flash (to white), whip (horizontal blur), zoom (punch-in), dip (black), glitch (RGB split)."""
    W, H = size
    parts = []
    for j, x in enumerate(transitions):
        c = x["at"]

        def win(a, b):
            return f"enable='between(t,{_r(c + a)},{_r(c + b)})'"
        if x["type"] == "flash":
            parts.append(f"[{cur}]eq=brightness='0.85*max(0,1-abs(t-{_r(c)})/0.1)':eval=frame:{win(-0.1, 0.1)}[tr{j}]")
        elif x["type"] == "whip":
            parts.append(f"[{cur}]avgblur=sizeX=18:sizeY=1:{win(-3 * FRAME, 3 * FRAME)},"
                         f"avgblur=sizeX=40:sizeY=1:{win(-FRAME, FRAME)}[tr{j}]")
        elif x["type"] == "zoom":
            k = f"(1+0.14*max(0,1-abs(t-{_r(c)})/0.2))"
            # scale has no timeline support; outside the window k is 1, so the frame passes unchanged
            parts.append(f"[{cur}]scale=w='2*trunc({W}*{k}/2)':h='2*trunc({H}*{k}/2)':eval=frame,crop={W}:{H},"
                         f"setsar=1,gblur=sigma=6:{win(-FRAME, FRAME)}[tr{j}]")
        elif x["type"] == "leak":  # light burn: red, orange, warm white on the cut, orange haze, clean
            parts.append(f"[{cur}]format=gbrp,split[lk{j}a][lk{j}b];[lk{j}a][lk{j}b]blend="
                         + ":".join(f"c{p}_expr='{_leak_expr(ch, c)}'" for p, ch in enumerate("gbr"))
                         + f":{win(LEAK_KEYS[0][0], LEAK_KEYS[-1][0])},format=yuv420p[tr{j}]")
        elif x["type"] == "sweep":  # light sweep: a light band in the accent colour crosses the frame, flashing on the cut
            parts.append(f"[{cur}]format=gbrp,split[sw{j}a][sw{j}b];[sw{j}a][sw{j}b]blend="
                         + ":".join(f"c{p}_expr='{_sweep_expr(ch, c, x.get("color", SWEEP_COLOR))}'" for p, ch in enumerate("gbr"))
                         + f":{win(-0.22, 0.22)},format=yuv420p[tr{j}]")
        elif x["type"] == "settle":  # the shot opens pushed in and eases out to 1.0 (a strong hook)
            k = f"(1+{x.get('amount', 0.15)}*gte(t,{_r(c)})*pow(max(0,1-(t-{_r(c)})/{x.get('dur', 0.6)}),2))"
            parts.append(f"[{cur}]scale=w='2*trunc({W}*{k}/2)':h='2*trunc({H}*{k}/2)':eval=frame,crop={W}:{H},"
                         f"setsar=1[tr{j}]")
        elif x["type"] == "dip":
            parts.append(f"[{cur}]drawbox=c=black:t=fill:{win(-2 * FRAME, FRAME)}[tr{j}]")
        else:  # glitch
            parts.append(f"[{cur}]rgbashift=rh=-14:bh=14:gv=6:{win(-2 * FRAME, 2 * FRAME)}[tr{j}]")
        cur = f"tr{j}"
    return parts, cur


def gfx_window(at: float, dur: float) -> str:
    """A graphic shows on frames round(at*FPS) .. round((at+dur)*FPS) - 1: snapped to frames the way segment cuts are
    (segment_frames), and excluding its end frame, which belongs to whatever comes next. A graphic ending on a cut
    whose time falls between frames otherwise showed a ghost of itself on the next shot's first frame."""
    f0, f1 = round(at * FPS), round((at + dur) * FPS)
    return f"gte(t,{(f0 - 0.5) / FPS:.4f})*lt(t,{(f1 - 0.5) / FPS:.4f})"


def graphic_window(at: float, dur: float, end: float) -> str:
    """gfx_window, except a graphic that runs to the end of the video keeps only its start bound. Its end bound
    switched the last frame off: once the graphic's clip ends, overlay evaluates `enable` at a later time than the
    frame's own, so an end card showed the footage under it on the video's final frame."""
    if at + dur < end - 0.5 / FPS:
        return gfx_window(at, dur)
    return f"gte(t,{(round(at * FPS) - 0.5) / FPS:.4f})"


def scene_window(at: float, dur: float, broll_windows: list) -> str:
    """ffmpeg enable expression: the graphic's frames minus every B-roll window's frames."""
    expr = gfx_window(at, dur)
    for a, b in broll_windows:
        if a <= at + dur and b >= at:
            expr += f"*not({gfx_window(a, b - a)})"
    return expr


SPLIT_Y = 0.08  # split-screen B-roll: the speaker's half starts this far down the frame (head and chest)


def video_filter(plan: dict, src_index: dict | int, broll_inputs: list, gfx_inputs: list, size: tuple,
                 ass_path: str | None = None, fonts_dir: str | None = None, desk_inputs: list = (),
                 person_inputs: list = (), overlay_inputs: list = ()) -> str:
    W, H = size
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,format=yuv420p"
    # an int is the input index of the already-cut base video
    parts = [f"[{src_index}:v]setpts=PTS-STARTPTS,format=yuv420p[base]"] if isinstance(src_index, int) \
        else segments_filter(plan, src_index, size)
    cur = "base"
    for j, (item, k) in enumerate(broll_inputs):
        at, dur = item["at"], item["dur"]
        # decoded 0.1 s past its slot: a 50 or 23.976 fps clip resampled to 30 fps can end a frame early and let
        # the talking head flash through at a join (the overlay window still ends exactly at at + dur)
        src_in = 0.0 if Path(item.get("resolved", "")).suffix.lower() in IMAGE_EXTS else item.get("src_in", 0.0)
        on = f"enable='{gfx_window(at, dur)}'"
        if item.get("frame") == "top":  # split screen: the shot on top, the speaker's head and chest below
            h2 = H // 2 // 2 * 2
            y0 = int(round(float(item.get("split_y", SPLIT_Y)) * H / 2)) * 2
            half = f"scale={W}:{h2}:force_original_aspect_ratio=increase,crop={W}:{h2},setsar=1,format=yuv420p"
            parts.append(f"[{k}:v]setpts=PTS-STARTPTS,trim=start={src_in:.3f}:duration={dur + 0.1:.3f},"
                         f"setpts=PTS-STARTPTS+{at}/TB,fps={FPS},{half}[b{j}]")
            parts.append(f"[{cur}]split[sp{j}a][sp{j}b];[sp{j}b]crop={W}:{H - h2}:0:{min(y0, h2)}[sp{j}c]")
            parts.append(f"[sp{j}a][sp{j}c]overlay=0:{h2}:{on}[sp{j}d]")
            parts.append(f"[sp{j}d][b{j}]overlay=0:0:{on}:eof_action=pass[ob{j}]")
        else:
            parts.append(f"[{k}:v]setpts=PTS-STARTPTS,trim=start={src_in:.3f}:duration={dur + 0.1:.3f},"
                         f"setpts=PTS-STARTPTS+{at}/TB,fps={FPS},{fit}[b{j}]")
            parts.append(f"[{cur}][b{j}]overlay={on}:eof_action=pass[ob{j}]")
        cur = f"ob{j}"
    look_parts, cur = looks_filter(plan.get("looks", []), cur, size)
    parts += look_parts
    desk_parts, cur = desks_filter(list(desk_inputs), cur)
    parts += desk_parts
    person_parts, cur = person_filter(list(person_inputs), cur)
    parts += person_parts
    # Text behind the person (hands or whole body) belongs to the talking-head shot: it goes in under the
    # transitions, so a light burn grades text and cut-out with the footage, and it is switched off on every frame
    # B-roll shows (B-roll windows include their end frame; a cut-out starting on that frame floated over the
    # B-roll inside the burn).
    broll_windows = [(item["at"], item["at"] + item["dur"]) for item, _ in broll_inputs]
    scene = [(j, x) for j, x in enumerate(gfx_inputs) if len(x) > 2 and x[2] is not None]
    for j, (item, k, kf) in scene:
        on = f"enable='{scene_window(item['at'], item['dur'], broll_windows)}'"
        parts.append(f"[{k}:v]setpts=PTS-STARTPTS+{item['at']}/TB,{TO_YUV}[g{j}]")
        parts.append(f"[{cur}][g{j}]overlay={on}:eof_action=pass[og{j}]")
        parts.append(f"[{kf}:v]setpts=PTS-STARTPTS+{item['at']}/TB,{TO_YUV}[gf{j}]")
        parts.append(f"[og{j}][gf{j}]overlay={on}:eof_action=pass[ogf{j}]")
        cur = f"ogf{j}"
    tr_parts, cur = transitions_filter(plan.get("transitions", []), cur, size)  # under graphics: cards cover the burn
    parts += tr_parts
    under = [x for x in overlay_inputs if x[0].get("layer") == "under"]
    ov_parts, cur = overlays.filter_parts(under, cur, size, "ou")
    parts += ov_parts
    in_scene = {j for j, _ in scene}
    end = timeline_duration(plan)
    for j, (item, k, *fg) in enumerate(gfx_inputs):
        if j in in_scene:
            continue
        at, dur = item["at"], item["dur"]
        on = f"enable='{graphic_window(at, dur, end)}'"
        parts.append(f"[{k}:v]setpts=PTS-STARTPTS+{at}/TB,{TO_YUV}[g{j}]")
        parts.append(f"[{cur}][g{j}]overlay={on}:eof_action=repeat[og{j}]")
        cur = f"og{j}"
    ov_parts, cur = overlays.filter_parts([x for x in overlay_inputs if x[0].get("layer") != "under"], cur, size)
    parts += ov_parts
    if ass_path:
        parts.append(f"[{cur}]ass=filename={ass_path}:fontsdir={fonts_dir}:shaping=complex[vout]")
    else:
        parts.append(f"[{cur}]null[vout]")
    return ";".join(parts)


def normalize(src, dst, target: float = -14.0) -> Path:
    m = analyze.loudness(src, target)
    if not math.isfinite(m["input_i"]):
        shutil.copy2(src, dst)
        return Path(dst)
    af = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    ffmpeg.run(["-i", src, "-af", af, "-ar", "48000", dst])
    return Path(dst)


MUSIC_LUFS = -33  # music bed before ducking: sits ~27 dB under the voice
DUCK = {"threshold": 0.02, "ratio": 8, "release": 350}  # deep: the bed all but leaves while the voice speaks


def _music_gain_db(music, target: float = MUSIC_LUFS) -> float:
    level = analyze.loudness(music)["input_i"]
    return round(target - level, 1) if math.isfinite(level) else 0.0


def _mix(voice, music, plan: dict, sfx_files: list, total: float, dst) -> None:
    inputs, parts, mix, k = ["-i", voice], [], ["[v]"], 1
    if music:
        start = plan["music"].get("start", 0.0)  # seconds into the track: begin on its best section
        inputs += [*(["-ss", f"{start:.3f}"] if start else []), "-i", music]
        parts.append("[0:a]asplit=2[v][sc]")
        parts.append(f"[1:a]aresample=48000,aformat=channel_layouts=stereo,aloop=loop=-1:size=2000000000,"
                     f"atrim=0:{total},asetpts=PTS-STARTPTS,volume={_music_gain_db(music, plan['music'].get('lufs', MUSIC_LUFS))}dB,"
                     f"afade=t=in:d=0.6,afade=t=out:st={max(total - 1.5, 0):.3f}:d=1.5[mus]")
        duck = {**DUCK, **plan["music"].get("duck", {})}  # how far the bed dips under the voice
        parts.append(f"[mus][sc]sidechaincompress=threshold={duck['threshold']}:ratio={duck['ratio']}:attack=15:"
                     f"release={duck['release']}[duck]")
        mix.append("[duck]")
        k = 2
    else:
        parts.append("[0:a]anull[v]")
    for j, (x, f) in enumerate(zip(plan["sfx"], sfx_files)):
        inputs += ["-i", f]
        # `at` is when the hit is heard: the file's own lead-in before its peak is taken off (a stock impact can
        # peak 2 s into its file). align: "start" keeps the old behaviour (file start at `at`).
        lead = 0.0 if x.get("align") == "start" else sfx_peak(f)
        start = x["at"] - lead
        trim = f"atrim=start={-start:.3f},asetpts=PTS-STARTPTS," if start < 0 else ""
        ms = int(max(start, 0) * 1000)
        gain = plan.get('sfx_volume', SFX_VOLUME) * x.get("gain", 1.0)
        parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,{trim}adelay={ms}|{ms},volume={gain}[s{j}]")
        mix.append(f"[s{j}]")
        k += 1
    if len(mix) == 1:
        parts.append("[v]anull[out]")
    else:
        parts.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0[out]")
    ffmpeg.run([*inputs, "-filter_complex", ";".join(parts), "-map", "[out]", "-ar", "48000", "-ac", "2", dst])


def sfx_peak(path) -> float:
    """Seconds from the start of a sound file to its hit: the first point the envelope reaches 70% of its peak
    (a long riser counts its loudest moment; a whoosh its centre)."""
    import subprocess

    import numpy as np
    from .config import ffmpeg_bin
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(path),
                          "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
    x = np.abs(np.frombuffer(raw, np.float32))
    if not len(x):
        return 0.0
    env = np.convolve(x, np.ones(160) / 160, "same")
    return float(np.argmax(env >= 0.7 * env.max())) / 16000


def _transcript(project: Path) -> dict:
    p = project / "transcript.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"words": None, "language": None}


def write_text_outputs(out: Path, plan: dict, extra_notes: list = ()) -> None:
    """notes.txt always; credits.txt only while the current music needs a credit (a stale one is removed)."""
    (out / "notes.txt").write_text("\n".join([*plan.get("notes", []), *extra_notes]) + "\n", encoding="utf-8")
    credits = out / "credits.txt"
    if plan["music"].get("credit"):
        credits.write_text(plan["music"]["credit"] + "\n", encoding="utf-8")
    else:
        credits.unlink(missing_ok=True)


def load_faces(project: Path, src: str):
    """faces.json from analyze, or detect now; None when OpenCV is missing or detection fails."""
    path = project / "faces.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        data = faces.detect(project / src)
    except Exception:
        return None
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def _key(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _stat(path: Path) -> list:
    st = path.stat()
    return [st.st_size, int(st.st_mtime)]


def build_base(project: Path, plan: dict, size: tuple) -> Path:
    """work/base.mp4: the cut, reframed talking head (no overlays). Rebuilt only when the segments, their sources or
    the output size change; work/base.key holds the fingerprint (also the root of every cut-out's cache key)."""
    project = Path(project)
    base, keyf = project / "work" / "base.mp4", project / "work" / "base.key"
    srcs = list(dict.fromkeys(s["src"] for s in plan["segments"]))
    graph = ";".join(segments_filter(plan, {s: i for i, s in enumerate(srcs)}, size, seeked=True))
    key = _key(segment_inputs(plan), graph, [_stat(project / s) for s in srcs], size)
    if base.exists() and keyf.exists() and keyf.read_text() == key:
        return base
    keyf.unlink(missing_ok=True)
    ffmpeg.run([*segment_inputs(plan), "-filter_complex", graph,
                "-map", "[base]", "-an", "-c:v", "libx264", *quality.inter("veryfast", 14), "-pix_fmt", "yuv420p",
                *color.TAGS, "-r", FPS, base], cwd=project)
    keyf.write_text(key)
    return base


def cached_cutout(base: Path, at: float, dur: float, size: tuple, part: str = "person", glow: str | None = None):
    """cutout.cut_out of base[at, at+dur], reused while base.mp4 and the window are unchanged: a re-render after a
    text fix redoes only the cut-outs whose timing moved. Returns (clip, glow clip or None)."""
    work = base.parent
    root = (work / "base.key").read_text() if (work / "base.key").exists() else _key(_stat(base))
    k = _key(root, round(at, 3), round(dur, 3), size, part, glow, cutout.SMOOTH, cutout.LOW, cutout.HIGH, cutout.MATTE_VERSION, cutout.engine())
    d = work / "cut"
    d.mkdir(exist_ok=True)
    clip, ring = d / f"{part}-{k}.mov", (d / f"glow-{k}.mov" if glow else None)
    if not clip.exists() or (ring and not ring.exists()):
        tmp, gtmp = clip.with_suffix(".part.mov"), (ring.with_suffix(".part.mov") if ring else None)
        cutout.cut_out(base, tmp, at, dur, size, glow, gtmp, part=part)
        tmp.replace(clip)
        if ring:
            gtmp.replace(ring)
    return clip, ring


def jobs() -> int:
    """Graphics rendered at once (each is a headless Chromium): EDITOR_JOBS, else half the cores."""
    return max(1, int(os.environ.get("EDITOR_JOBS") or (os.cpu_count() or 2) // 2))


def render(project, plan: dict, style: dict, draft: bool = False) -> dict:
    """draft: a fast encode for feedback rounds (veryfast, lighter quality); the final render keeps medium/CRF 20."""
    project = Path(project).resolve()
    size = FORMATS[plan["format"]]
    total = timeline_duration(plan)
    work, out = project / "work", project / "out"
    work.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    missing = [f for f in [*(x["file"] for x in plan["sfx"] if x.get("file")),
                            *(b["resolved"] for b in plan["broll"] if b.get("resolved")),
                            *([plan["music"]["src"]] if plan["music"].get("src") else []),
                            *(o["file"] for o in plan.get("overlays", []))]
               if not (Path(f) if Path(f).is_absolute() else project / f).exists()]
    if missing:  # fail before minutes of graphics and cut-outs, not at the final mix
        raise FileNotFoundError(f"edit.json points at missing files: {missing}")
    srcs = list(dict.fromkeys(s["src"] for s in plan["segments"]))
    src_index = {s: i for i, s in enumerate(srcs)}
    src_inputs = [arg for s in srcs for arg in ("-i", s)]
    silent = {s for s in srcs if not ffmpeg.probe(project / s)["has_audio"]}
    tr = _transcript(project)
    if plan.get("grade"):  # measured per segment: each shot gets its own white balance and levels
        look = plan["grade"].get("look", "clean")
        plan = {**plan, "segments": [{**seg, "_grade": grade.chain(grade.measure(project / seg["src"], seg["in"],
                                                                                   seg["out"], 3), look)}
                                     for seg in plan["segments"]]}
    if any(x["type"] == "sweep" for x in plan.get("transitions", [])):  # the sweep is lit in the style's accent
        plan = {**plan, "transitions": [{"color": style.get("accent", SWEEP_COLOR), **x} if x["type"] == "sweep" else x
                                        for x in plan["transitions"]]}

    fonts_dir = work / "fonts"
    fonts_dir.mkdir(exist_ok=True)
    for family in (style["font"], style["arabic_font"]):
        f = fonts.ensure_font(family)
        shutil.copy2(f, fonts_dir / f.name)

    ass_rel, extra_notes = None, []
    desks = plan.get("desks", [])
    face_data = load_faces(project, srcs[0]) if plan["graphics"] or desks else None
    if plan["graphics"] and face_data is None:
        extra_notes.append("No face data: graphics placed for a typical talking-head framing.")
    t0 = time.time()

    def stage(name):
        nonlocal t0
        print(f"[render] {name}: {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
        t0 = time.time()

    specs = []
    for i, g in enumerate(plan["graphics"]):
        slot = layout.place(g, plan, face_data, style, size)
        if slot.get("note"):
            extra_notes.append(slot.pop("note"))
        specs.append((i, g, slot))
    with ThreadPoolExecutor(jobs()) as pool:  # each graphic is its own Chromium; unchanged ones come from the cache
        files = list(pool.map(lambda x: render_graphic({**x[1], "slot": x[2]}, style, size, work / f"gfx-{x[0]}.mov",
                                                        project), specs))
    gfx = [(g, f) for (_, g, _), f in zip(specs, files)]
    stage(f"graphics ({len(gfx)}, {jobs()} at once)")

    desk_files, person_files, behind_files = [], [], {}
    person = plan.get("person", [])
    behind = [i for i, g in enumerate(plan["graphics"]) if g.get("place") in ("behind", "hands")]
    base = build_base(project, plan, size)
    stage("base cut")
    picture = base
    if plan.get("fx"):  # signature effects replace their windows of the cut picture; cut-outs still read the base
        from .fx.apply import apply_fx
        picture = apply_fx(base, plan["fx"], work / "fx", style, size, float(FPS), project,
                           out=work / "base-fx.mp4")
        stage(f"fx ({len(plan['fx'])})")
    if desks or person or behind:
        for i, d in enumerate(desks):
            head = faces.head_band(face_data, plan["segments"], d["at"], d["dur"], size) if face_data else None
            bg = (render_graphic({**d["card"], "at": d["at"], "dur": d["dur"]}, style, size, work / f"desk-{i}.mov", project)
                  if d["card"]["type"] in KIT_TYPES else render_desk(d, style, size, work / f"desk-{i}.mov", project))
            desk_files.append((d, bg, cached_cutout(base, d["at"], d["dur"], size)[0], cutout.placement(head, size)))
        for i, x in enumerate(person):
            glow = x.get("color", style["accent"]) if x["type"] == "glow" else None
            fg, ring = cached_cutout(base, x["at"], x["dur"], size, glow=glow)
            person_files.append((x, fg, ring))
        for i in behind:
            g = plan["graphics"][i]
            behind_files[i] = cached_cutout(base, g["at"], g["dur"], size,
                                            part="hands" if g.get("place") == "hands" else "person")[0]
        stage(f"cut-outs ({len(desks) + len(person) + len(behind)})")

    if plan["captions"].get("enabled") and not tr.get("words"):
        extra_notes.append("Captions were on but transcript.json has no words, so the video has no captions.")
    if plan["captions"].get("enabled") and tr.get("words"):
        lines = captions.ensure_lines(work / "captions.json", plan, tr["words"], style, size)
        if plan.get("fx"):  # effects that fill the caption band take the captions off for their window
            from .fx.apply import hides_captions
            gaps = [(f["at"], f["at"] + f["dur"]) for f in plan["fx"] if hides_captions(f)]
            lines = [ln for ln in lines if not any(ln["start"] < b and ln["end"] > a for a, b in gaps)]
        (work / "captions.ass").write_text(captions.to_ass(lines, style, size, plan["captions"].get("mode", "source"),
                                                           desks), encoding="utf-8")
        ass_rel = "work/captions.ass"

    voice = work / "voice.wav"
    ffmpeg.run([*src_inputs, "-filter_complex", voice_filter(plan, src_index, style.get("voice"), silent_srcs=silent),
                "-map", "[voice]",
                "-ar", "48000", "-ac", "2", voice], cwd=project)
    sfx_files = [str(project / x["file"]) if x.get("file") and not Path(x["file"]).is_absolute() else x["file"]
                 if x.get("file") else score.write_sfx(work / f"sfx-{j}-{x['kind']}.wav", x["kind"])
                 for j, x in enumerate(plan["sfx"])]
    music = plan["music"].get("src")
    music = str(project / music) if music and not Path(music).is_absolute() else music
    _mix(voice, None, plan, sfx_files, total, work / "mix-nomusic.wav")
    if music:
        _mix(voice, music, plan, sfx_files, total, work / "mix.wav")
    else:
        shutil.copy2(work / "mix-nomusic.wav", work / "mix.wav")
    normalize(work / "mix.wav", work / "audio.wav")
    normalize(work / "mix-nomusic.wav", work / "audio-nomusic.wav")
    stage("audio")

    inputs, broll_inputs, gfx_inputs, k = ["-i", picture], [], [], 1
    for b in plan["broll"]:
        if not b.get("resolved"):
            continue
        p = b["resolved"]
        if Path(p).suffix.lower() in IMAGE_EXTS:
            inputs += ["-loop", "1", "-t", b["dur"], "-itsoffset", f"{b['at']:.3f}", "-i", p]
        else:  # offset at the input: the clip is read only from its own start, never buffered from t=0
            # read from the file's start and cut in the graph (trim): an input -ss next to -itsoffset seeks in the
            # shifted timeline, so it was silently ignored and every clip played from 0
            inputs += ["-t", f"{b.get('src_in', 0.0) + b['dur'] + 0.5:.3f}", "-itsoffset", f"{b['at']:.3f}", "-i", p]
        broll_inputs.append((b, k))
        k += 1
    # -itsoffset starts each overlay clip at its own time, so ffmpeg reads it only when it is needed instead of
    # buffering its frames from t=0 (dozens of 1080x1920 alpha clips filled 14 GB that way)
    def late(at, path):
        return ["-itsoffset", f"{at:.3f}", "-i", path]
    for i, (g, p) in enumerate(gfx):
        inputs += late(g["at"], p)
        kg, kf, k = k, None, k + 1
        if i in behind_files:
            inputs += late(g["at"], behind_files[i])
            kf, k = k, k + 1
        gfx_inputs.append((g, kg, kf))
    desk_inputs = []
    for d, bg, fg, pl in desk_files:
        inputs += late(d["at"], bg) + late(d["at"], fg)
        desk_inputs.append((d, k, k + 1, pl))
        k += 2
    person_inputs = []
    for x, fg, glow in person_files:
        inputs += late(x["at"], fg) + (late(x["at"], glow) if glow else [])
        person_inputs.append((x, k, k + 1 if glow else None))
        k += 2 if glow else 1
    overlay_inputs = []
    for o in plan.get("overlays", []):
        p = Path(o["file"]) if Path(o["file"]).is_absolute() else project / o["file"]
        screen = (o.get("color") or overlays.screen_color(p, o.get("src_in", 0.0))) \
            if overlays.key_of(o) == "green" else None
        inputs += overlays.input_args(o, p)
        overlay_inputs.append((o, k, screen))
        k += 1
    vf = video_filter(plan, 0, broll_inputs, gfx_inputs, size, ass_rel, "work/fonts", desk_inputs,
                      person_inputs, overlay_inputs)
    video = work / "video.mp4"
    graph = work / "video_filter.txt"  # read from a file: long edits overflow the command line
    graph.write_text(vf, encoding="utf-8")
    ffmpeg.run([*inputs, "-filter_complex_script", graph, "-map", "[vout]", "-an", "-c:v", "libx264",
                *quality.final(draft), "-pix_fmt", "yuv420p", *color.TAGS, "-r", FPS, "-t", total, video], cwd=project)

    final, nomusic = out / "final.mp4", out / "final-nomusic.mp4"
    for audio, dst in ((work / "audio.wav", final), (work / "audio-nomusic.wav", nomusic)):
        ffmpeg.run(["-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", quality.audio_kbps(), "-shortest", "-movflags", "+faststart", dst])
    write_text_outputs(out, plan, extra_notes)
    stage("composite and encode")
    return {"final": final, "nomusic": nomusic}
