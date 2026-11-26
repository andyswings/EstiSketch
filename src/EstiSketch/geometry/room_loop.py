"""Headless planar wall-loop detection and inward face-offsetting helpers.

Used when double-clicking inside a closed loop of walls to generate a ``Room``
whose boundary follows the *interior faces* of the enclosing walls (centerline
inset by half each wall's thickness) rather than the wall centerlines.

All coordinates and dimensions are in model **inches**; this module is free of
GTK, Cairo, and Blender dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Sequence

Point = tuple[float, float]


def polygon_signed_area(poly: Sequence[Point]) -> float:
    """Return the signed area of ``poly`` in square inches (shoelace formula)."""
    n = len(poly)
    if n < 3:
        return 0.0
    area2 = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        area2 += x1 * y2 - x2 * y1
    return 0.5 * area2


def point_in_polygon(pt: Point, poly: Sequence[Point]) -> bool:
    """Return True when ``pt`` lies strictly inside ``poly`` (ray casting)."""
    px, py = pt
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > py) != (yj > py):
            x_hit = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < x_hit:
                inside = not inside
        j = i
    return inside


def inset_polygon(
    poly: Sequence[Point],
    offsets: Sequence[float],
) -> list[Point]:
    """Offset each edge ``poly[i] -> poly[i+1]`` inward by ``offsets[i]`` inches.

    Orientation-independent: works identically for clockwise and counter-clockwise
    polygons and handles varying wall thicknesses per edge. Zero-length consecutive
    duplicate vertices are collapsed before offsetting so miter intersections never
    fall back to an un-offset centerline point.

    Args:
        poly: Ordered polygon vertices (inches).
        offsets: Inward offset distance per edge in inches (typically ``wall.width / 2``).

    Returns:
        Inset polygon vertices in inches.
    """
    n_raw = len(poly)
    if n_raw < 3:
        return list(poly)

    clean_pts: list[Point] = []
    clean_offsets: list[float] = []
    for i in range(n_raw):
        p1 = poly[i]
        p2 = poly[(i + 1) % n_raw]
        if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) >= 1e-6:
            clean_pts.append((float(p1[0]), float(p1[1])))
            off = float(offsets[i]) if i < len(offsets) else 0.0
            clean_offsets.append(off)

    n = len(clean_pts)
    if n < 3 or not any(o > 0.0 for o in clean_offsets):
        return list(poly)

    area = polygon_signed_area(clean_pts)
    if abs(area) < 1e-6:
        return list(clean_pts)
    sign = 1.0 if area > 0.0 else -1.0

    lines: list[tuple[Point, Point]] = []
    for i in range(n):
        x1, y1 = clean_pts[i]
        x2, y2 = clean_pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        nx, ny = -uy * sign, ux * sign
        o = clean_offsets[i]
        lines.append(((x1 + nx * o, y1 + ny * o), (ux, uy)))

    result: list[Point] = []
    for i in range(n):
        (px, py), (pdx, pdy) = lines[(i - 1) % n]
        (cx, cy), (cdx, cdy) = lines[i]
        det = pdx * cdy - pdy * cdx
        if abs(det) < 1e-6:
            result.append((cx, cy))
            continue
        t = ((cx - px) * cdy - (cy - py) * cdx) / det
        result.append((px + pdx * t, py + pdy * t))
    return result


@dataclass
class _Segment:
    p1: Point
    p2: Point
    width: float


def _project_param_on_segment(
    pt: Point,
    a: Point,
    b: Point,
    tol: float,
) -> float | None:
    """Return normalized ``t in (0, 1)`` if ``pt`` lies on segment ``a-b`` within ``tol``."""
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-9:
        return None
    length = math.sqrt(len_sq)
    t = ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / len_sq
    if t <= 0.0 or t >= 1.0:
        return None
    px = a[0] + t * dx
    py = a[1] + t * dy
    if math.hypot(pt[0] - px, pt[1] - py) > tol:
        return None
    dist_from_ends = min(t, 1.0 - t) * length
    if dist_from_ends <= tol:
        return None
    return t


def _segment_intersection_params(
    s1: _Segment,
    s2: _Segment,
) -> tuple[float, float] | None:
    """Return ``(t1, t2)`` in ``(0, 1)`` for properly crossing straight segments."""
    x1, y1 = s1.p1
    x2, y2 = s1.p2
    x3, y3 = s2.p1
    x4, y4 = s2.p2
    dx1, dy1 = x2 - x1, y2 - y1
    dx2, dy2 = x4 - x3, y4 - y3
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < 1e-9:
        return None
    rx, ry = x3 - x1, y3 - y1
    t1 = (rx * dy2 - ry * dx2) / denom
    t2 = (rx * dy1 - ry * dx1) / denom
    if 1e-4 < t1 < 1.0 - 1e-4 and 1e-4 < t2 < 1.0 - 1e-4:
        return (t1, t2)
    return None


def _build_planar_segments(
    walls: Sequence[Any],
    snap_tol: float,
) -> list[_Segment]:
    """Extract straight walls and split at every T-junction and crossing."""
    raw: list[_Segment] = []
    for w in walls:
        if getattr(w, "is_curved", False):
            continue
        p1 = (float(w.start[0]), float(w.start[1]))
        p2 = (float(w.end[0]), float(w.end[1]))
        if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) < 1e-3:
            continue
        width = float(getattr(w, "width", 0.0) or 0.0)
        raw.append(_Segment(p1=p1, p2=p2, width=width))

    split_params: list[list[float]] = [[0.0, 1.0] for _ in raw]
    endpoints = [pt for seg in raw for pt in (seg.p1, seg.p2)]

    for idx, seg in enumerate(raw):
        for pt in endpoints:
            t = _project_param_on_segment(pt, seg.p1, seg.p2, snap_tol)
            if t is not None:
                split_params[idx].append(t)

    for i in range(len(raw)):
        for j in range(i + 1, len(raw)):
            hit = _segment_intersection_params(raw[i], raw[j])
            if hit is not None:
                split_params[i].append(hit[0])
                split_params[j].append(hit[1])

    pieces: list[_Segment] = []
    for seg, params in zip(raw, split_params):
        params.sort()
        dedup = [params[0]]
        for t in params[1:]:
            if t - dedup[-1] > 1e-4:
                dedup.append(t)
        dx = seg.p2[0] - seg.p1[0]
        dy = seg.p2[1] - seg.p1[1]
        for a_t, b_t in zip(dedup, dedup[1:]):
            q1 = (seg.p1[0] + a_t * dx, seg.p1[1] + a_t * dy)
            q2 = (seg.p1[0] + b_t * dx, seg.p1[1] + b_t * dy)
            if math.hypot(q2[0] - q1[0], q2[1] - q1[1]) >= 1e-3:
                pieces.append(_Segment(p1=q1, p2=q2, width=seg.width))
    return pieces


def _minimal_faces(
    pieces: list[_Segment],
    snap_tol: float,
) -> list[tuple[list[Point], list[float], float]]:
    """Return ``(pts, widths, abs_area)`` for every minimal bounded face cycle."""
    vertices: list[Point] = []

    def _vertex_id(pt: Point) -> int:
        for vid, existing in enumerate(vertices):
            if math.hypot(pt[0] - existing[0], pt[1] - existing[1]) <= snap_tol:
                return vid
        vertices.append(pt)
        return len(vertices) - 1

    edge_widths: dict[tuple[int, int], float] = {}
    for seg in pieces:
        u = _vertex_id(seg.p1)
        v = _vertex_id(seg.p2)
        if u == v:
            continue
        key = (u, v) if u < v else (v, u)
        edge_widths[key] = max(edge_widths.get(key, 0.0), seg.width)

    adj: dict[int, set[int]] = {i: set() for i in range(len(vertices))}
    for u, v in edge_widths:
        adj[u].add(v)
        adj[v].add(u)

    # Prune dangling trees (degree <= 1) which cannot belong to any closed room loop.
    pruned = True
    while pruned:
        pruned = False
        for vid, nbrs in list(adj.items()):
            if len(nbrs) == 1:
                only = next(iter(nbrs))
                nbrs.clear()
                adj[only].discard(vid)
                pruned = True

    sorted_adj: dict[int, list[int]] = {}
    for vid, nbrs in adj.items():
        if not nbrs:
            continue
        vx, vy = vertices[vid]
        sorted_adj[vid] = sorted(
            nbrs,
            key=lambda nb: math.atan2(vertices[nb][1] - vy, vertices[nb][0] - vx),
        )

    half_edges = [(u, v) for u, nbrs in sorted_adj.items() for v in nbrs]
    visited: set[tuple[int, int]] = set()
    faces: list[tuple[list[Point], list[float], float]] = []

    for start_he in half_edges:
        if start_he in visited:
            continue
        cycle: list[tuple[int, int]] = []
        cur = start_he
        valid = True
        while cur not in visited:
            visited.add(cur)
            cycle.append(cur)
            u, v = cur
            nbrs = sorted_adj.get(v, [])
            if len(nbrs) < 2:
                valid = False
                break
            idx = nbrs.index(u)
            nxt_v = nbrs[(idx - 1) % len(nbrs)]
            cur = (v, nxt_v)
            if cur == start_he:
                break
            if len(cycle) > len(half_edges) + 2:
                valid = False
                break

        if not valid or cur != start_he or len(cycle) < 3:
            continue

        pts = [vertices[u] for u, _ in cycle]
        area = polygon_signed_area(pts)
        # Positive signed area corresponds to bounded interior faces for (idx - 1) turns
        # in ascending atan2 order; outer unbounded boundaries have area < 0.
        if area <= 1.0:
            continue

        widths = [
            edge_widths[(u, v) if u < v else (v, u)]
            for u, v in cycle
        ]
        faces.append((pts, widths, area))

    return faces


def find_enclosed_room_inner_polygon(
    walls: Sequence[Any],
    click_pt: Point,
    snap_tol: float = 1.0,
) -> list[Point] | None:
    """Find the smallest enclosed room containing ``click_pt`` and inset to inner faces.

    Handles single closed wall sets, multi-wall-set loops, split walls, and interior
    partition walls meeting exterior walls at T-junctions. Curved walls are handled
    separately by the curved-wall-set path in ``CanvasGeometryMixin``.

    Args:
        walls: Visible straight/curved walls (inches). Curved walls are skipped here.
        click_pt: Pointer click position in model inches.
        snap_tol: Vertex snapping tolerance in inches.

    Returns:
        Inside-face polygon vertices in inches, or ``None`` if ``click_pt`` is not
        enclosed or the wall thicknesses collapse the enclosed face.
    """
    pieces = _build_planar_segments(walls, snap_tol=snap_tol)
    if len(pieces) < 3:
        return None

    faces = _minimal_faces(pieces, snap_tol=snap_tol)
    containing = [face for face in faces if point_in_polygon(click_pt, face[0])]
    if not containing:
        return None

    pts, widths, outer_area = min(containing, key=lambda item: item[2])
    inner = inset_polygon(pts, [w / 2.0 for w in widths])
    if len(inner) < 3:
        return None
    inner_area = polygon_signed_area(inner)
    if inner_area <= 1.0 or inner_area > outer_area + 1e-3:
        return None
    return inner
