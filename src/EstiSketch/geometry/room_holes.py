"""Derived room holes (floor openings) generated from stairs.

Holes are never authored directly: they are regenerated from their source
object (``Hole.source_id``) so they follow it when it moves, changes shape,
changes level or is deleted.  All coordinates and areas are in inches / sq in.

Pure-Python (no Cairo/GTK) so it can be tested headlessly.
"""
import math
from typing import List, Optional, Tuple

from ..components import Hole

Point = Tuple[float, float]

STAIR_SOURCE_PREFIX = "stair:"
MIN_HOLE_AREA_SQIN = 1.0
SQIN_PER_SQFT = 144.0


# --------------------------------------------------------------------------
# Basic polygon helpers
# --------------------------------------------------------------------------
def signed_area(poly: List[Point]) -> float:
    n = len(poly)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def polygon_area(poly: List[Point]) -> float:
    return abs(signed_area(poly))


def union_area(polys: List[List[Point]]) -> float:
    """Exact area of the union of (possibly overlapping, possibly concave) polygons.

    Vertical slab sweep: between consecutive x-coordinates of all vertices and
    all edge crossings no edges cross or end, so the union's cross-section
    length is linear in x and its mean is the length at the slab midpoint.
    """
    polys = [p for p in polys if len(p) >= 3]
    if not polys:
        return 0.0
    edges = []
    for poly in polys:
        n = len(poly)
        edges.extend((poly[i], poly[(i + 1) % n]) for i in range(n))
    xs = {pt[0] for poly in polys for pt in poly}
    for i in range(len(edges)):
        (x1, y1), (x2, y2) = edges[i]
        for j in range(i + 1, len(edges)):
            (x3, y3), (x4, y4) = edges[j]
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(den) < 1e-12:
                continue
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
            u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / den
            if 0.0 < t < 1.0 and 0.0 < u < 1.0:
                xs.add(x1 + t * (x2 - x1))
    xs = sorted(xs)

    def covered_length(x: float) -> float:
        intervals = []
        for poly in polys:
            ys = []
            n = len(poly)
            for i in range(n):
                (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
                if (xa <= x < xb) or (xb <= x < xa):
                    ys.append(ya + (x - xa) / (xb - xa) * (yb - ya))
            ys.sort()
            intervals.extend((ys[k], ys[k + 1]) for k in range(0, len(ys) - 1, 2))
        intervals.sort()
        total, cur_lo, cur_hi = 0.0, None, None
        for lo, hi in intervals:
            if cur_hi is None or lo > cur_hi:
                if cur_hi is not None:
                    total += cur_hi - cur_lo
                cur_lo, cur_hi = lo, hi
            else:
                cur_hi = max(cur_hi, hi)
        if cur_hi is not None:
            total += cur_hi - cur_lo
        return total

    area = 0.0
    for a, b in zip(xs, xs[1:]):
        if b - a > 1e-9:
            area += (b - a) * covered_length((a + b) / 2.0)
    return area


def clip_polygon_convex(subject: List[Point], clip: List[Point]) -> List[Point]:
    """Sutherland-Hodgman: clip ``subject`` (any polygon) by convex ``clip``.

    For a concave subject the result may contain zero-width bridge edges; this
    does not change its area or even-odd fill.
    """
    if len(subject) < 3 or len(clip) < 3:
        return []
    if signed_area(clip) < 0:
        clip = list(reversed(clip))

    def inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-9

    def intersect(p1, p2, a, b):
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = a
        x4, y4 = b
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < 1e-12:
            return p2
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    output = list(subject)
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]
        inp, output = output, []
        if not inp:
            break
        prev = inp[-1]
        for cur in inp:
            if inside(cur, a, b):
                if not inside(prev, a, b):
                    output.append(intersect(prev, cur, a, b))
                output.append(cur)
            elif inside(prev, a, b):
                output.append(intersect(prev, cur, a, b))
            prev = cur
    return output


# --------------------------------------------------------------------------
# Stair footprint
# --------------------------------------------------------------------------
def _xf(start: Point, angle: float, pts: List[Point]) -> List[Point]:
    c, s = math.cos(angle), math.sin(angle)
    return [(start[0] + u * c - v * s, start[1] + u * s + v * c) for u, v in pts]


def _rect(u0, v0, u1, v1) -> List[Point]:
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def _sub_frame(origin: Point, rot: float, pts: List[Point]) -> List[Point]:
    c, s = math.cos(rot), math.sin(rot)
    return [(origin[0] + a * c - b * s, origin[1] + a * s + b * c) for a, b in pts]


def stair_footprint_parts(stair) -> List[List[Point]]:
    """Non-overlapping convex polygons (model inches) covering the stair."""
    from ..Canvas.winder_geometry import l_stair_layout

    stype = getattr(stair, "stair_type", "straight")
    width = stair.width
    hw = width / 2.0
    start = stair.start_point
    ang = stair.direction_angle
    turn = getattr(stair, "turn_direction", "left")

    if stype == "spiral":
        r = getattr(stair, "inner_radius", 6.0) + width
        n = 32
        return [[(start[0] + r * math.cos(2 * math.pi * i / n),
                  start[1] + r * math.sin(2 * math.pi * i / n)) for i in range(n)]]

    if stype == "L-shaped":
        lay = l_stair_layout(stair.num_steps, getattr(stair, "steps_before_landing", 0),
                             stair.tread_depth, getattr(stair, "landing_depth", 36.0),
                             width, getattr(stair, "winder_count", 0))
        rb, ra, ld = lay["run_before"], lay["run_after"], lay["landing_depth"]
        local = []
        if rb > 0:
            local.append(_rect(0, -hw, rb, hw))
        local.append(_rect(rb, -hw, rb + ld, hw))
        if ra > 0:
            if turn == "left":
                o, rot = (rb + ld - hw, -hw), -math.pi / 2
            else:
                o, rot = (rb + ld - hw, hw), math.pi / 2
            local.append(_sub_frame(o, rot, _rect(0, -hw, ra, hw)))
        return [_xf(start, ang, p) for p in local]

    if stype == "U-shaped":
        ld = getattr(stair, "landing_depth", 36.0)
        well = getattr(stair, "inner_radius", 0.0)
        total = stair.num_steps
        sbl = getattr(stair, "steps_before_landing", 0)
        before = sbl if 0 < sbl < total else total // 2
        after = total - before
        rb = (before - 1) * stair.tread_depth if before > 0 else 0
        ra = (after - 1) * stair.tread_depth if after > 0 else 0
        span = 2 * width + well
        local = []
        if rb > 0:
            local.append(_rect(0, -hw, rb, hw))
        if turn == "left":
            local.append(_rect(rb, -hw - well - width, rb + ld, -hw - well - width + span))
            o = (rb, -(width + well))
        else:
            local.append(_rect(rb, -hw, rb + ld, -hw + span))
            o = (rb, width + well)
        if ra > 0:
            local.append(_sub_frame(o, math.pi, _rect(0, -hw, ra, hw)))
        return [_xf(start, ang, p) for p in local]

    # straight
    return [_xf(start, ang, _rect(0, -hw, stair.total_run, hw))]


# --------------------------------------------------------------------------
# Level / room lookup and synchronisation
# --------------------------------------------------------------------------
def room_level_id(canvas, room) -> str:
    layer = canvas.get_layer_by_id(room.layer_id) if hasattr(canvas, "get_layer_by_id") else None
    return getattr(layer, "level_id", "") if layer else ""


def stair_source_id(stair) -> str:
    return STAIR_SOURCE_PREFIX + (stair.identifier or str(id(stair)))


def compute_stair_holes(canvas, stair, cut_lower_ceiling: bool) -> List[Tuple[object, Hole]]:
    """Return ``(room, Hole)`` pairs generated by one stair."""
    out = []
    parts = stair_footprint_parts(stair)
    margin = float(getattr(stair, "opening_clearance", 0.0) or 0.0)
    if margin > 0:
        parts = [_expand_rect(p, margin) for p in parts]
    source = stair_source_id(stair)
    targets = []
    if getattr(stair, "end_level_id", ""):
        targets.append((stair.end_level_id, False))
    if cut_lower_ceiling and getattr(stair, "start_level_id", ""):
        targets.append((stair.start_level_id, True))
    for level_id, ceiling_only in targets:
        for room in canvas.rooms:
            if len(room.points) < 3 or room_level_id(canvas, room) != level_id:
                continue
            for part in parts:
                clipped = clip_polygon_convex(list(room.points), part)
                if polygon_area(clipped) >= MIN_HOLE_AREA_SQIN:
                    out.append((room, Hole(source_id=source, points=clipped,
                                           ceiling_only=ceiling_only)))
    return out


def _expand_rect(poly: List[Point], margin: float) -> List[Point]:
    """Offset every edge of a convex polygon outward by ``margin`` inches."""
    if signed_area(poly) < 0:
        poly = list(reversed(poly))
    n = len(poly)
    lines = []  # (point on offset edge, direction)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        d = math.hypot(dx, dy) or 1.0
        nx, ny = dy / d, -dx / d  # outward normal for CCW
        lines.append(((x1 + nx * margin, y1 + ny * margin), (dx, dy)))
    res = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-12:
            res.append(p2)
            continue
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        res.append((p1[0] + t * d1[0], p1[1] + t * d1[1]))
    return res


def sync_stair_holes(canvas) -> bool:
    """Regenerate every stair-derived hole on ``canvas.rooms``.

    Manual holes (other ``source_id`` prefixes) are left untouched.  Returns
    True if anything changed.  Cheap enough to call before draw / takeoff / save.
    """
    cut_lower = bool(getattr(canvas, "cut_lower_ceiling_under_stairs", False))
    new = {}
    for stair in getattr(canvas, "stairs", []):
        for room, hole in compute_stair_holes(canvas, stair, cut_lower):
            new.setdefault(id(room), []).append(hole)

    changed = False
    for room in canvas.rooms:
        kept = [h for h in room.holes if not h.source_id.startswith(STAIR_SOURCE_PREFIX)]
        old_stair = [h for h in room.holes if h.source_id.startswith(STAIR_SOURCE_PREFIX)]
        fresh = new.get(id(room), [])
        if not _same_holes(old_stair, fresh):
            changed = True
        room.holes = kept + fresh
    return changed


def _same_holes(a: List[Hole], b: List[Hole]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x.source_id != y.source_id or x.ceiling_only != y.ceiling_only:
            return False
        if len(x.points) != len(y.points):
            return False
        for p, q in zip(x.points, y.points):
            if abs(p[0] - q[0]) > 1e-6 or abs(p[1] - q[1]) > 1e-6:
                return False
    return True


# --------------------------------------------------------------------------
# Areas
# --------------------------------------------------------------------------
def room_gross_area_sqft(room) -> float:
    return polygon_area(room.points) / SQIN_PER_SQFT


def room_floor_area_sqft(room) -> float:
    """Floor area net of floor openings (overlaps counted once; ceiling-only holes ignored)."""
    holes = union_area([h.points for h in room.holes if not h.ceiling_only])
    return max(polygon_area(room.points) - holes, 0.0) / SQIN_PER_SQFT


def room_ceiling_area_sqft(room) -> float:
    """Ceiling area net of every hole, including lower-ceiling cutouts."""
    holes = union_area([h.points for h in room.holes])
    return max(polygon_area(room.points) - holes, 0.0) / SQIN_PER_SQFT


def room_slab_volume_cuft(room) -> Optional[float]:
    if not getattr(room, "is_slab", False):
        return None
    return room_floor_area_sqft(room) * (room.slab_thickness / 12.0)
