"""Pure geometry helpers for wall face alignment and mixed-thickness joins.

Kept free of GTK/Cairo so they can be unit tested headlessly.
"""
import math
from typing import List, Optional, Tuple

Point = Tuple[float, float]


def _unit(start: Point, end: Point) -> Optional[Point]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    return dx / length, dy / length


def wall_join_polygon(
        a_start: Point, a_end: Point, a_width: float,
        b_start: Point, b_end: Point, b_width: float,
        miter_limit: float = 10.0) -> Optional[List[Point]]:
    """Polygon that fills the outer-corner notch where wall A meets wall B.

    Wall A ends where wall B starts (``a_end`` == ``b_start``). When the two
    walls have different thicknesses, stroking each with butt caps leaves the
    outer corner open. The returned polygon is the region bounded by the
    corner point, the outer face of each wall at the corner and the
    intersection of the two outer face lines (the miter point).

    Returns None for collinear/degenerate joins, or when the miter exceeds
    ``miter_limit`` times the larger wall width.
    """
    a = _unit(a_start, a_end)
    b = _unit(b_start, b_end)
    if a is None or b is None:
        return None
    cross = a[0] * b[1] - a[1] * b[0]
    if abs(cross) < 1e-6:
        return None

    corner = a_end
    # Outer side is opposite the turn direction (normal = (-dy, dx)).
    side = -1.0 if cross > 0 else 1.0
    na = (-a[1] * side, a[0] * side)
    nb = (-b[1] * side, b[0] * side)
    pa = (corner[0] + na[0] * a_width / 2.0, corner[1] + na[1] * a_width / 2.0)
    pb = (corner[0] + nb[0] * b_width / 2.0, corner[1] + nb[1] * b_width / 2.0)

    vx = pb[0] - pa[0]
    vy = pb[1] - pa[1]
    t = (vx * b[1] - vy * b[0]) / cross
    miter = (pa[0] + t * a[0], pa[1] + t * a[1])
    if math.hypot(miter[0] - corner[0], miter[1] - corner[1]) > \
            miter_limit * max(a_width, b_width):
        return None
    return [corner, pa, miter, pb]


def face_flush_offsets(existing_width: float, new_width: float,
                       tol: float = 0.01) -> List[Tuple[float, float, str]]:
    """Centerline offsets that align a parallel new wall with an existing wall.

    Returns ``(offset, face_side, kind)`` tuples where ``offset`` is the signed
    distance (along the existing wall's left normal) from the existing
    centerline to the new centerline, ``face_side`` is +1/-1 for the existing
    wall's left/right face being matched (0 for centerlines), and ``kind`` is:

    * ``"center"`` - both centerlines coincide;
    * ``"flush"`` - new wall overlaps/continues the existing one with one face
      coplanar;
    * ``"abut"`` - new wall sits alongside, touching face to face.
    """
    out: List[Tuple[float, float, str]] = [(0.0, 0.0, "center")]
    for side in (1.0, -1.0):
        flush = side * (existing_width - new_width) / 2.0
        if abs(flush) > tol:
            out.append((flush, side, "flush"))
        out.append((side * (existing_width + new_width) / 2.0, side, "abut"))
    return out
