"""Perspective + edge-bow correction for photographed blueprints.

The user marks four corners (TL, TR, BR, BL) of the real plan rectangle in
the photo plus an optional "bow" handle on each edge's midpoint. The output
image is the rectangle those handles describe, straightened:

    source(u, v) = H(u, v)                       # exact perspective (homography)
                   + bow blend of the four edge displacements

where (u, v) are coordinates inside the unit output rectangle. Edge handles
displace the edge midpoint (u=.5 on top/bottom, v=.5 on left/right) and the
displacement fades to zero at the corners and linearly toward the opposite
edge, so a curved page edge becomes straight while lines in the interior
follow it smoothly. Pure numpy; no GTK so it is unit-testable.
"""
import math
from typing import Sequence, Tuple

import numpy as np

Point = Sequence[float]

# Edge order used everywhere: top, right, bottom, left
EDGE_NAMES = ("top", "right", "bottom", "left")
MAX_OUTPUT_DIM = 8000


def homography_from_points(src: Sequence[Point], dst: Sequence[Point]) -> np.ndarray:
    """3x3 matrix mapping each ``src`` point to the matching ``dst`` point."""
    a = []
    b = []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    try:
        h = np.linalg.solve(np.array(a, float), np.array(b, float))
    except np.linalg.LinAlgError as exc:
        raise ValueError("Corners are degenerate (collinear points).") from exc
    return np.append(h, 1.0).reshape(3, 3)


def _unit_to_quad(corners: Sequence[Point]) -> np.ndarray:
    return homography_from_points(
        [(0, 0), (1, 0), (1, 1), (0, 1)], corners)


def _apply_h(h: np.ndarray, u, v):
    u = np.asarray(u, float)
    v = np.asarray(v, float)
    denom = h[2, 0] * u + h[2, 1] * v + h[2, 2]
    x = (h[0, 0] * u + h[0, 1] * v + h[0, 2]) / denom
    y = (h[1, 0] * u + h[1, 1] * v + h[1, 2]) / denom
    return x, y


def edge_anchors(corners: Sequence[Point]):
    """Straight-edge midpoints (perspective-correct) for top/right/bottom/left."""
    h = _unit_to_quad(corners)
    pts = []
    for u, v in ((0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5)):
        x, y = _apply_h(h, u, v)
        pts.append((float(x), float(y)))
    return pts


def source_point(corners, offsets, u, v):
    """Source-image position for output unit coordinates ``(u, v)``.

    ``offsets``: four (dx, dy) displacements for top, right, bottom, left.
    Accepts scalars or numpy arrays for ``u``/``v``.
    """
    h = _unit_to_quad(corners)
    x, y = _apply_h(h, u, v)
    u = np.asarray(u, float)
    v = np.asarray(v, float)
    bu = 4.0 * u * (1.0 - u)
    bv = 4.0 * v * (1.0 - v)
    weights = ((1.0 - v) * bu, u * bv, v * bu, (1.0 - u) * bv)
    for w, (dx, dy) in zip(weights, offsets):
        x = x + w * dx
        y = y + w * dy
    return x, y


def output_size(corners: Sequence[Point]) -> Tuple[int, int, float]:
    """Output (width, height) in pixels plus the down-scale factor applied
    when the natural size exceeds ``MAX_OUTPUT_DIM`` (1.0 otherwise)."""
    (tl, tr, br, bl) = corners
    w = max(math.dist(tl, tr), math.dist(bl, br))
    h = max(math.dist(tl, bl), math.dist(tr, br))
    if w < 2 or h < 2:
        raise ValueError("Corners are too close together.")
    shrink = 1.0
    longest = max(w, h)
    if longest > MAX_OUTPUT_DIM:
        shrink = MAX_OUTPUT_DIM / longest
    return max(2, round(w * shrink)), max(2, round(h * shrink)), shrink


def warp_image(rgba: np.ndarray, corners, offsets, out_w: int, out_h: int,
               block_rows: int = 128) -> np.ndarray:
    """Resample ``rgba`` (H x W x 4, uint8) into an ``out_h x out_w`` image.

    Bilinear sampling; positions outside the source are fully transparent.
    Works on premultiplied data unchanged (linear in all channels).
    """
    src_h, src_w = rgba.shape[:2]
    out = np.zeros((out_h, out_w, 4), np.uint8)
    us = (np.arange(out_w) + 0.5) / out_w
    for y0 in range(0, out_h, block_rows):
        y1 = min(out_h, y0 + block_rows)
        vs = (np.arange(y0, y1) + 0.5) / out_h
        uu, vv = np.meshgrid(us, vs)
        sx, sy = source_point(corners, offsets, uu, vv)
        sx = sx - 0.5
        sy = sy - 0.5
        x0 = np.floor(sx).astype(np.int64)
        y0i = np.floor(sy).astype(np.int64)
        fx = (sx - x0)[..., None].astype(np.float32)
        fy = (sy - y0i)[..., None].astype(np.float32)

        def tap(xi, yi):
            inside = ((xi >= 0) & (xi < src_w) & (yi >= 0) & (yi < src_h))
            vals = rgba[np.clip(yi, 0, src_h - 1), np.clip(xi, 0, src_w - 1)]
            return vals.astype(np.float32) * inside[..., None]

        px = (tap(x0, y0i) * (1 - fx) * (1 - fy) +
              tap(x0 + 1, y0i) * fx * (1 - fy) +
              tap(x0, y0i + 1) * (1 - fx) * fy +
              tap(x0 + 1, y0i + 1) * fx * fy)
        out[y0:y1] = np.clip(px + 0.5, 0, 255).astype(np.uint8)
    return out
