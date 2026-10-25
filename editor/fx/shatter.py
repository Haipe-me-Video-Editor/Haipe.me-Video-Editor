"""Shatter: the picture breaks like a pane of glass. Cracks race out from an impact point (the face by default),
then on the hit the frame splits into shards that fly towards the camera and away from the impact, spinning, under
gravity, while the live shot carries on behind them with a white flash and a small punch. The shards carry the frame
frozen at the hit, each with a bright glass edge.

Shards are the Voronoi cells of seeds packed densely round the impact and sparsely at the edges, so small splinters
burst from the centre and big panes fall away at the sides. The cracks drawn before the hit are exactly the shard
edges, revealed outward from the impact, so the break follows the cracks the viewer has just seen.
"""
import math

import cv2
import numpy as np

from . import _behind as B
from . import _camera as cam

NAME = "shatter"
DOC = ("The frame cracks from an impact point (the face by default) and shatters into glass shards that fly at the "
       "camera, revealing the live shot behind with a flash. For a hard reveal, a 'that changes everything' line, "
       "or a transition beat. Put `hit` on the word.")
BEST_FOR = ["playful", "product", "any"]
DUR = (0.8, 4)
PARAMS = {
    "hit": 0.35,         # seconds into the window when the glass breaks (cracks spread during `crack` before it)
    "crack": 0.25,       # crack spread time before the hit, s (0: no warning cracks)
    "impact": "face",    # face | center | [x, y] in 0-1
    "pieces": 44,        # number of shards (24 .. 90)
    "reveal": "live",    # live (the shot carries on behind) | black | white
    "flash": 0.7,        # white flash strength on the hit, 0-1
    "seed": 7,           # shard layout; change it for a different break
}
GRAVITY = 2.6       # in frame heights per s^2
SPEED = 1.2         # base outward speed, frame heights per s
LIFE = 0.7          # seconds until a shard has faded out


def seeds(W: int, H: int, impact, n: int, rng) -> np.ndarray:
    """Voronoi seeds: a tight cluster at the impact thinning out with distance (rings of growing radius)."""
    ix, iy = impact
    R = max(math.hypot(x - ix, y - iy) for x in (0, W) for y in (0, H))
    pts = [(ix, iy)]
    rings = max(3, round(math.sqrt(n) * 0.9))
    left = n - 1
    for k in range(1, rings + 1):
        r = R * (k / rings) ** 1.6
        m = max(3, round(left * (k ** 0.6) / sum(j ** 0.6 for j in range(k, rings + 1))))
        left -= m
        for a in rng.uniform(0, 2 * math.pi, m) + rng.uniform(0, 1):
            rr = r * rng.uniform(0.82, 1.12)
            pts.append((ix + rr * math.cos(a), iy + rr * math.sin(a)))
    P = np.array(pts, np.float32)
    keep = (P[:, 0] > 1) & (P[:, 0] < W - 1) & (P[:, 1] > 1) & (P[:, 1] < H - 1)
    return P[keep]


def cells(W: int, H: int, pts: np.ndarray) -> list:
    """Voronoi cells of `pts`, clipped to the frame: a list of (k, 2) float32 polygons that tile it exactly."""
    sub = cv2.Subdiv2D((-W, -H, 3 * W, 3 * H))
    for p in pts:
        sub.insert((float(p[0]), float(p[1])))
    facets, _ = sub.getVoronoiFacetList([])
    frame = np.array([[0, 0], [W, 0], [W, H], [0, H]], np.float32)
    out = []
    for f in facets:
        area, poly = cv2.intersectConvexConvex(np.asarray(f, np.float32), frame)
        if area > 4 and poly is not None:
            out.append(poly.reshape(-1, 2).astype(np.float32))
    return out


def crack_map(W: int, H: int, polys: list) -> np.ndarray:
    """Every shard edge as a bright hairline with a darker rim, float32 (H, W) in 0..1 (drawn at 2x, then down)."""
    S = 2
    m = np.zeros((H * S, W * S), np.uint8)
    for p in polys:
        cv2.polylines(m, [np.round(p * S).astype(np.int32)], True, 255, 3, cv2.LINE_AA)
    return cv2.resize(m, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32) / 255


def motion(poly: np.ndarray, impact, H: int, rng) -> dict:
    """A shard's flight: outward velocity (faster near the impact), spin, approach to camera, a flip that glints."""
    c = poly.mean(0)
    d = c - np.float32(impact)
    dist = float(np.hypot(*d)) + 1e-3
    near = math.exp(-dist / (0.18 * H))
    v = d / dist * SPEED * H * (0.8 + 0.6 * rng.uniform()) * (1 + 1.4 * near)
    return {"c": c, "v": v, "spin": rng.uniform(-1, 1) * (120 + 380 * near), "z": rng.uniform(1.0, 2.2) * (1 + near),
            "flip": rng.uniform(4, 11) * rng.choice([-1, 1]), "delay": dist / (8.0 * H)}


def shard_matrix(m: dict, tau: float, H: int) -> np.ndarray:
    """2x3 affine for a shard tau seconds after the hit, in frame coordinates (about its centroid)."""
    tau = max(0.0, tau - m["delay"])
    s = 1 + m["z"] * tau
    sx = s * math.cos(m["flip"] * tau)  # a flip about the shard's own axis: it thins, then shows its back
    th = math.radians(m["spin"] * tau)
    ca, sa = math.cos(th), math.sin(th)
    A = np.array([[ca * sx, -sa * s], [sa * sx, ca * s]], np.float64)
    pos = m["c"] + m["v"] * tau + np.array([0, 0.5 * GRAVITY * H * tau * tau])
    t = pos - A @ m["c"]
    return np.hstack([A, t[:, None]])


def render(ctx):
    W, H = ctx.W, ctx.H
    hit = float(ctx.param("hit", PARAMS["hit"]))
    crack = float(ctx.param("crack", PARAMS["crack"]))
    n = int(ctx.param("pieces", PARAMS["pieces"]))
    if not 24 <= n <= 90:
        raise ValueError("shatter pieces must be in [24, 90]")
    if not 0 <= hit < ctx.dur:
        raise ValueError("shatter hit must fall inside the window")
    reveal = ctx.param("reveal", PARAMS["reveal"])
    if reveal not in ("live", "black", "white"):
        raise ValueError("shatter reveal is live, black or white")
    flash = float(ctx.param("flash", PARAMS["flash"]))
    target = ctx.param("impact", PARAMS["impact"])
    lm = ctx.landmarks(every=2) if target == "face" else []
    h0 = int(hit * ctx.fps)
    impact = cam.resolve_target(target, lm, range(max(0, h0 - 6), min(ctx.n, h0 + 6)), (W, H))
    rng = np.random.default_rng(int(ctx.param("seed", PARAMS["seed"])))
    polys = cells(W, H, seeds(W, H, impact, n, rng))
    cracks = crack_map(W, H, polys)
    moves = [motion(p, impact, H, rng) for p in polys]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dist = np.hypot(xx - impact[0], yy - impact[1])
    reach = cam.corner_dist(impact, (W, H))
    frozen, sprites = None, []
    with ctx.writer() as write:
        for i, frame in enumerate(ctx.frames()):
            t = i / ctx.fps
            F = frame.astype(np.float32) / 255
            if t < hit:
                u = B.progress(t, hit - crack, crack) if crack > 0 else 0.0
                if u <= 0:
                    write(frame)
                    continue
                r = reach * B.ease_out(u) ** 0.8
                vis = cracks * np.clip((r - dist) / 40 + 0.5, 0, 1)
                out = F * (1 - 0.55 * cv2.GaussianBlur(vis, (0, 0), 2.2)[..., None])  # a dark rim either side
                out = out * (1 - vis[..., None]) + vis[..., None] * 0.97
                write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
                continue
            if frozen is None:
                frozen = F.copy()
                for p in polys:
                    x0, y0 = np.floor(p.min(0)).astype(int)
                    x1, y1 = np.ceil(p.max(0)).astype(int)
                    x0, y0, x1, y1 = max(x0 - 2, 0), max(y0 - 2, 0), min(x1 + 2, W), min(y1 + 2, H)
                    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
                    cv2.fillPoly(m, [np.round((p - [x0, y0]) * 4).astype(np.int32)], 255, cv2.LINE_AA, shift=2)
                    a = m.astype(np.float32) / 255
                    edge = np.zeros_like(m)
                    cv2.polylines(edge, [np.round((p - [x0, y0]) * 4).astype(np.int32)], True, 255, 2, cv2.LINE_AA,
                                  shift=2)
                    rgb = frozen[y0:y1, x0:x1] * (1 - 0.5 * edge[..., None] / 255) + 0.5 * edge[..., None] / 255
                    sprites.append((np.dstack([rgb, a]).astype(np.float32), x0, y0))
            tau = t - hit
            # behind the glass: the live shot (with a small punch and a flash), or a flat colour
            if reveal == "live":
                punch = 1 + 0.05 * math.exp(-tau / 0.12)
                out = cv2.warpAffine(F, cam.zoom_matrix(impact, punch), (W, H), flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_REFLECT)
            else:
                out = np.full((H, W, 3), 0.0 if reveal == "black" else 1.0, np.float32)
            out = out + (1 - out) * flash * math.exp(-tau / 0.09)
            order = sorted(range(len(sprites)), key=lambda k: moves[k]["z"])  # nearer (faster-growing) on top
            fade = 1 - B.ease_in(B.progress(tau, LIFE * 0.45, LIFE * 0.55))
            for k in order:
                spr, x0, y0 = sprites[k]
                M = shard_matrix(moves[k], tau, H)
                M[:, 2] += M[:, :2] @ np.array([x0, y0], np.float64)  # sprite-local in, frame out
                h_, w_ = spr.shape[:2]
                corners = np.array([[0, 0, 1], [w_, 0, 1], [0, h_, 1], [w_, h_, 1]], np.float64) @ M.T
                X0, Y0 = np.floor(corners.min(0)).astype(int)
                X1, Y1 = np.ceil(corners.max(0)).astype(int)
                X0, Y0, X1, Y1 = max(X0, 0), max(Y0, 0), min(X1, W), min(Y1, H)
                if X1 <= X0 or Y1 <= Y0:
                    continue
                Ml = M.copy()
                Ml[:, 2] -= [X0, Y0]
                piece = cv2.warpAffine(spr, Ml, (X1 - X0, Y1 - Y0), flags=cv2.INTER_LINEAR,
                                       borderMode=cv2.BORDER_CONSTANT)
                a = piece[..., 3:4] * fade
                # glass catches the light as it flips: brighten with the flip angle
                glint = 0.25 * max(0.0, math.sin(moves[k]["flip"] * max(0.0, tau - moves[k]["delay"]))) ** 4
                rgb = piece[..., :3] + (1 - piece[..., :3]) * glint
                reg = out[Y0:Y1, X0:X1]
                reg[:] = reg * (1 - a) + rgb * a
            write((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    return ctx.out
