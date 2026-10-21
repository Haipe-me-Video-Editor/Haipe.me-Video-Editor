"""Real app screens for an edit: a page opened in the local Chromium at phone size, saved as a sharp screenshot or
as a screen recording driven by a short script (scroll, tap, type, wait). Use it instead of drawing a screen.

    python -m editor capture <url> <out.png|.mp4> [--steps steps.json] [--device phone|desktop] [--wait 1.5]

`steps.json` is a list run in order, e.g.
    [{"wait": 1}, {"scroll": 600, "dur": 1.2}, {"tap": "text=Get started"}, {"type": ["#q", "hello"]},
     {"wait": 2}, {"shot": "after-tap.png"}]
- wait: seconds; scroll: pixels down (negative up), eased over `dur` seconds; tap: a Playwright selector;
  type: [selector, text]; shot: an extra screenshot path (relative to the output's folder).
- point: a selector (e.g. "text=Editing playbook"): a visible cursor glides to it over `dur` (default 0.8 s) and,
  with `zoom` (e.g. 1.8), the page then zooms in on it so the words are readable; `click: true` clicks it too.
  unzoom: seconds to ease back to the whole page.
A recording is written at 1080x1920 (phone) or 1920x1080 (desktop), H.264, ready to use as B-roll or inside a
phone frame. Brand rules decide what may be captured (e.g. never live customer data); this tool only captures.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

DEVICES = {  # CSS viewport, device pixel ratio, output size for recordings
    "phone": {"viewport": (390, 693), "dpr": 3, "out": (1080, 1920)},
    "desktop": {"viewport": (1280, 720), "dpr": 1.5, "out": (1920, 1080)},
}
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"  # preinstalled in cloud containers; else Playwright's own
UA_PHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.0 Mobile/15E148 Safari/604.1")


def _browser(p):
    exe = CHROMIUM if Path(CHROMIUM).exists() else None
    return p.chromium.launch(executable_path=exe, args=["--hide-scrollbars", "--disable-gpu"])


def _run_steps(page, steps: list, out_dir: Path) -> list:
    shots = []
    for s in steps:
        if "wait" in s:
            page.wait_for_timeout(int(float(s["wait"]) * 1000))
        elif "scroll" in s:
            px, dur = float(s["scroll"]), float(s.get("dur", 1.0))
            frames = max(1, int(dur * 30))
            done = 0.0
            for i in range(1, frames + 1):  # eased, like a thumb, not a jump
                t = i / frames
                target = px * (1 - (1 - t) ** 3)
                page.mouse.wheel(0, target - done)
                done = target
                page.wait_for_timeout(int(1000 / 30))
        elif "tap" in s:
            page.locator(s["tap"]).first.click()
        elif "type" in s:
            sel, text = s["type"]
            page.locator(sel).first.type(text, delay=70)
        elif "point" in s:
            _point(page, s["point"], float(s.get("dur", 0.8)), s.get("zoom"), bool(s.get("click")))
        elif "unzoom" in s:
            _zoom_to(page, 1.0, None, float(s["unzoom"]) or 0.5)
        elif "shot" in s:
            path = out_dir / s["shot"]
            page.screenshot(path=str(path))
            shots.append(path)
        else:
            raise ValueError(f"unknown capture step {s!r}")
    return shots


CURSOR_JS = """() => {
  if (document.getElementById('__cur')) return;
  const c = document.createElement('div');
  c.id = '__cur';
  c.innerHTML = '<svg width="28" height="34" viewBox="0 0 28 34"><path d="M2 2 L2 28 L9 21 L14 32 L19 30 L14 19 L24 19 Z" ' +
    'fill="#111" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/></svg>';
  Object.assign(c.style, {position: 'fixed', left: '0px', top: '0px', zIndex: 2147483647, pointerEvents: 'none',
    transform: 'translate(-3px,-2px)', filter: 'drop-shadow(0 2px 4px rgba(0,0,0,.35))', transition: 'none'});
  c.dataset.x = String(innerWidth * 0.5); c.dataset.y = String(innerHeight * 0.75);
  c.style.left = c.dataset.x + 'px'; c.style.top = c.dataset.y + 'px';
  document.documentElement.appendChild(c);
}"""


def ease(t: float) -> float:
    """Smooth start and stop, like a hand on a trackpad."""
    t = min(max(t, 0.0), 1.0)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def _point(page, selector: str, dur: float, zoom=None, click: bool = False) -> None:
    """Glide the drawn cursor to the element's centre, then zoom on it (and click)."""
    page.evaluate(CURSOR_JS)
    el = page.locator(selector).first
    try:
        el.wait_for(state="visible", timeout=8000)
    except Exception as e:  # Playwright's TimeoutError: say what is missing instead
        raise ValueError(f"capture point: {selector!r} is not on the page") from e
    el.scroll_into_view_if_needed()
    box = el.bounding_box()
    if not box:
        raise ValueError(f"capture point: {selector!r} is not on the page")
    x1, y1 = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    x0, y0 = page.evaluate("() => [+document.getElementById('__cur').dataset.x, +document.getElementById('__cur').dataset.y]")
    frames = max(1, int(dur * 30))
    for i in range(1, frames + 1):
        k = ease(i / frames)
        x, y = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
        page.evaluate("([x, y]) => { const c = document.getElementById('__cur'); c.dataset.x = x; c.dataset.y = y;"
                      " c.style.left = x + 'px'; c.style.top = y + 'px'; }", [x, y])
        page.wait_for_timeout(int(1000 / 30))
    if click:
        el.click()
    if zoom:
        _zoom_to(page, float(zoom), (x1, y1), 0.6)


def _zoom_to(page, scale: float, at, dur: float) -> None:
    """Ease the whole page (cursor included) to `scale`, panning the point `at` (viewport px) to the middle of the
    screen, so what is being talked about ends up big and centred; scale 1.0 eases back to the whole page."""
    z0, tx0, ty0 = page.evaluate("() => { const d = document.documentElement.dataset;"
                                 " return [+(d.zs || 1), +(d.tx || 0), +(d.ty || 0)]; }")
    if scale == 1.0 or at is None:
        tx1, ty1 = 0.0, 0.0
    else:
        vw, vh, sy = page.evaluate("() => [innerWidth, innerHeight, scrollY]")
        px, py = at[0], at[1] + sy  # document coordinates: the transform is applied to the whole document
        tx1, ty1 = vw / 2 - px * scale, sy + vh * 0.45 - py * scale
    frames = max(1, int(dur * 30))
    for i in range(1, frames + 1):
        k = ease(i / frames)
        z, tx, ty = z0 + (scale - z0) * k, tx0 + (tx1 - tx0) * k, ty0 + (ty1 - ty0) * k
        page.evaluate("([z, tx, ty]) => { const d = document.documentElement; Object.assign(d.dataset, {zs: z, tx, ty});"
                      " d.style.transformOrigin = '0 0';"
                      " d.style.transform = z === 1 && !tx && !ty ? '' : `translate(${tx}px, ${ty}px) scale(${z})`; }",
                      [z, tx, ty])
        page.wait_for_timeout(int(1000 / 30))


def capture(url: str, out, steps: list | None = None, device: str = "phone", wait: float = 1.5) -> dict:
    """Screenshot (out ends .png/.jpg) or recording (out ends .mp4) of `url`. Returns {"out", "shots"}.
    Recordings use Chromium's own screencast (each repainted frame with its timestamp), so they need no extra
    binaries; the frames are laid out on a 30 fps timeline by their timestamps."""
    from playwright.sync_api import sync_playwright
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    d = DEVICES[device]
    vw, vh = d["viewport"]
    video = out.suffix.lower() == ".mp4"
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = _browser(p)
        opts = {"viewport": {"width": vw, "height": vh}, "device_scale_factor": d["dpr"]}
        if device == "phone":
            opts.update(is_mobile=True, has_touch=True, user_agent=UA_PHONE)
        ctx = browser.new_context(**opts)
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(int(wait * 1000))
        frames = []
        if video:
            cdp = ctx.new_cdp_session(page)

            def on_frame(ev):
                import base64
                f = Path(tmp) / f"f{len(frames):05d}.jpg"
                f.write_bytes(base64.b64decode(ev["data"]))
                frames.append((ev["metadata"]["timestamp"], f))
                cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            cdp.on("Page.screencastFrame", on_frame)
            W, H = d["out"]
            cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": W, "maxHeight": H,
                                              "everyNthFrame": 1})
            page.wait_for_timeout(300)
        shots = _run_steps(page, steps or [], out.parent)
        if video:
            page.wait_for_timeout(500)
            cdp.send("Page.stopScreencast")
        else:
            page.screenshot(path=str(out))
        ctx.close()
        browser.close()
        if video:
            _encode(frames, out, d["out"])
    return {"out": out, "shots": shots}


def _encode(frames: list, out: Path, size: tuple) -> None:
    """Screencast frames (timestamp, jpeg) to a constant 30 fps H.264 clip: each frame holds until the next one."""
    if len(frames) < 2:
        raise RuntimeError("the page sent fewer than 2 frames; nothing moved while recording")
    W, H = size
    lst = out.with_suffix(".frames.txt")
    t0 = frames[0][0]
    lines = []
    for (t, f), (t_next, _) in zip(frames, frames[1:] + [(frames[-1][0] + 0.5, None)]):
        lines += [f"file '{f}'", f"duration {max(t_next - t, 1 / 30):.4f}"]
    lines.append(f"file '{frames[-1][1]}'")
    lst.write_text("\n".join(lines) + "\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf",
                    f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                    f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "16",
                    "-preset", "medium", "-an", "-movflags", "+faststart", str(out)], check=True)
    lst.unlink()
    _ = t0


def cmd(a) -> None:
    steps = json.loads(Path(a.steps).read_text()) if a.steps else []
    r = capture(a.url, a.out, steps, a.device, a.wait)
    print(r["out"], *r["shots"])


def available() -> bool:
    import importlib.util
    if importlib.util.find_spec("playwright") is None:
        return False
    if Path(CHROMIUM).exists() or shutil.which("chromium"):
        return True
    try:  # the Chromium `python -m playwright install chromium` put in its own cache (scripts/setup.sh does that)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:  # no driver or no browser: capture is off, the rest of the editor is not affected
        return False
