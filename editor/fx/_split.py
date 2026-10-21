"""Shared layout for the tech cards (terminal, code_card, rank_list): the card fills the top half of the frame and the
speaker's head and chest stay in the bottom half, the split-screen look of fast explainer reels; or the card takes
the whole frame. (Private module: the fx registry skips `_` names.)"""
from pathlib import Path

from .. import ffmpeg

PLACES = ("top", "full")
SPLIT_Y = 0.08  # the speaker's half starts this far down the frame (as broll frame "top")


def base(ctx, place: str) -> Path:
    """The picture under the card: the speaker moved into the bottom half (top) or plain black (full)."""
    out = ctx.work / f"split-{place}.mp4"
    if out.exists():
        return out
    W, H = ctx.W, ctx.H
    h2 = H // 2 // 2 * 2
    if place == "top":
        y0 = int(round(crop_top(ctx.face(), H) * H / 2)) * 2
        vf = f"fps={ctx.fps},scale={W}:{H},crop={W}:{H - h2}:0:{y0},pad={W}:{H}:0:{h2}:black,format=yuv420p"
        ffmpeg.run(["-i", ctx.src, "-vf", vf, "-frames:v", str(ctx.n), "-an", "-c:v", "libx264", "-crf", "14",
                    "-preset", "veryfast", out])
    else:
        ffmpeg.run(["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={ctx.fps}", "-frames:v", str(ctx.n),
                    "-c:v", "libx264", "-crf", "14", "-preset", "veryfast", "-pix_fmt", "yuv420p", out])
    return out


def crop_top(face: dict | None, H: int) -> float:
    """Where the speaker's half starts (0-1 of the height): a little above the crown, so the head is never cut;
    SPLIT_Y without a face. `face` is Ctx.face() (top = the hairline landmark, fw = the face width)."""
    if not face:
        return SPLIT_Y
    crown = face["top"] - 0.45 * face["fw"]
    return float(min(0.5, max(0.0, crown / H - 0.025)))


def box(ctx, place: str) -> dict:
    """Where the card sits (px): the top half with a margin, or the middle of the full frame."""
    W, H = ctx.W, ctx.H
    if place == "top":
        return {"x": W * 0.06, "y": H * 0.05, "w": W * 0.88, "h": H * 0.40}
    return {"x": W * 0.06, "y": H * 0.25, "w": W * 0.88, "h": H * 0.45}


def card_css(ctx, b: dict, accent: str) -> str:
    """The dark window every tech card sits in, with its three dots."""
    u = ctx.W / 1080
    return f"""
#card{{position:absolute;left:{b['x']:.0f}px;top:{b['y']:.0f}px;width:{b['w']:.0f}px;height:{b['h']:.0f}px;
  border-radius:{22 * u:.0f}px;background:#0f1115;box-shadow:0 {18 * u:.0f}px {60 * u:.0f}px rgba(0,0,0,.55),
  inset 0 0 0 {1.5 * u:.1f}px rgba(255,255,255,.08);overflow:hidden}}
#bar{{height:{58 * u:.0f}px;display:flex;align-items:center;gap:{12 * u:.0f}px;padding:0 {24 * u:.0f}px;
  background:#16181d;color:rgba(255,255,255,.55);font:500 {24 * u:.0f}px "PlexMono",monospace}}
#bar i{{width:{18 * u:.0f}px;height:{18 * u:.0f}px;border-radius:50%;display:inline-block}}
#bar span{{margin-left:{14 * u:.0f}px}}
.acc{{color:{accent}}}"""


def bar(title: str) -> str:
    from . import _glass as G
    return ('<div id="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i>'
            f'<i style="background:#28c840"></i><span>{G.esc(title)}</span></div>')
