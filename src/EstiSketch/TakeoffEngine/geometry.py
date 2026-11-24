"""Pure 2D helpers for takeoff measurements (inches)."""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Pt = Tuple[float, float]


def snap_to(value: float, step: float) -> float:
    """Snap a dimension to the nearest `step` (sketch jitter such as 479.94" -> 480.0")."""
    if not step:
        return value
    return round(value / step) * step


def signed_area(pts: Sequence[Pt]) -> float:
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def collapse_collinear(pts: Sequence[Pt], tol: float = 0.05) -> List[Pt]:
    """Remove duplicate and collinear vertices of a closed polygon."""
    out = list(pts)
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            seg = math.hypot(c[0] - a[0], c[1] - a[1]) or 1.0
            if math.hypot(b[0] - a[0], b[1] - a[1]) < tol or abs(cross) / seg < tol:
                del out[i]
                changed = True
                break
    return out


def offset_polygon(pts: Sequence[Pt], dists: Sequence[float]) -> List[Pt]:
    """Offset a closed polygon outward; dists[i] is the distance for edge pts[i]->pts[i+1] (miter joins)."""
    n = len(pts)
    sign = 1.0 if signed_area(pts) > 0 else -1.0  # CCW => outward normal is right-hand side
    lines = []
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        ln = math.hypot(dx, dy)
        nx, ny = sign * dy / ln, -sign * dx / ln
        d = dists[i]
        lines.append(((x1 + nx * d, y1 + ny * d), (dx, dy)))
    out = []
    for i in range(n):
        (p, r), (q, s) = lines[i - 1], lines[i]
        den = r[0] * s[1] - r[1] * s[0]
        if abs(den) < 1e-9:
            out.append(q)
            continue
        t = ((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / den
        out.append((p[0] + r[0] * t, p[1] + r[1] * t))
    return out


def is_rectangle(pts: Sequence[Pt], tol_deg: float = 1.0) -> bool:
    if len(pts) != 4:
        return False
    for i in range(4):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % 4]
        v1 = (a[0] - b[0], a[1] - b[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if not l1 or not l2:
            return False
        cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)
        if abs(math.degrees(math.acos(max(-1, min(1, cos)))) - 90.0) > tol_deg:
            return False
    return True


def edge_lengths(pts: Sequence[Pt]) -> List[float]:
    return [math.hypot(pts[(i + 1) % len(pts)][0] - pts[i][0], pts[(i + 1) % len(pts)][1] - pts[i][1])
            for i in range(len(pts))]


def point_line_distance(p: Pt, a: Pt, b: Pt) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(dx, dy) or 1.0
    return abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / ln
