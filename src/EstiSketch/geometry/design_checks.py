"""Headless architectural layout checks and interactive fixture wall-clamping.

Validates:
- Furniture/fixtures against exterior and interior wall penetration.
- Floor-standing fixtures against door swing zones.
- Staircases for level top/bottom landings, second-story elevation flushness,
  unobstructed landing access, and door-swing clearance.

All coordinates and dimensions are in model inches. This module has no GTK,
Cairo, or Blender dependencies so it runs directly under ``pytest``.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

from .arc_wall import arc_wall_point, arc_wall_tangent
from .room_holes import stair_footprint_parts
from .wall_chain import collinear_chain, pocket_door_extents

Point = tuple[float, float]

_NON_SWING_DOORS = frozenset({"frame", "pocket", "sliding", "garage"})
_HINGED_SWING_DOORS = frozenset({"single", "double"})
_SINK_VANITY_SYMBOLS = frozenset({
    "vanity_single",
    "vanity_double",
    "pedestal_sink",
    "utility_sink",
    "sink_base_cabinet",
})
_KITCHEN_SINK_SYMBOLS = frozenset({
    "sink_base_cabinet",
    "kitchen_sink_single",
    "kitchen_sink_double",
})
_CIRCULATION_ROOM_TYPES = frozenset({"hallway", "corridor", "foyer", "entry"})
_UTILITY_CLOSET_ROOM_TYPES = frozenset({"closet", "pantry", "utility", "laundry", "garage"})
_LAUNDRY_SYMBOLS = frozenset({"washer", "dryer"})
_EPS = 1e-6


@dataclass(frozen=True)
class LayoutIssue:
    """Structured architectural layout violation for headless & GUI reporting."""

    category: str
    severity: str
    message: str
    level_id: str = ""
    location_in: Point | None = None
    object_id: str = ""


def _point_in_poly(pt: Point, poly: list[Point]) -> bool:
    """Ray-casting point-in-polygon check."""
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def _wall_polygon(wall: Any) -> list[Point] | None:
    """Return 4-corner footprint (inches) of a straight structural wall, or None."""
    if getattr(wall, "symbolic", False) or getattr(wall, "is_curved", False):
        return None
    x1, y1 = float(wall.start[0]), float(wall.start[1])
    x2, y2 = float(wall.end[0]), float(wall.end[1])
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length <= 1e-4:
        return None
    half_w = float(getattr(wall, "width", 0.0) or 0.0) / 2.0
    if half_w <= 1e-4:
        return None
    nx = -dy / length * half_w
    ny = dx / length * half_w
    return [
        (x1 + nx, y1 + ny),
        (x2 + nx, y2 + ny),
        (x2 - nx, y2 - ny),
        (x1 - nx, y1 - ny),
    ]


def _sat_overlap(poly_a: list[Point], poly_b: list[Point]) -> tuple[float, Point] | None:
    """Return ``(penetration_in, unit_axis)`` if convex polygons overlap, else None."""
    if len(poly_a) < 3 or len(poly_b) < 3:
        return None
    min_depth = float("inf")
    best_axis = (1.0, 0.0)
    for poly in (poly_a, poly_b):
        n = len(poly)
        for i in range(n):
            p1 = poly[i]
            p2 = poly[(i + 1) % n]
            ex, ey = p2[0] - p1[0], p2[1] - p1[1]
            elen = math.hypot(ex, ey)
            if elen <= 1e-9:
                continue
            ax, ay = -ey / elen, ex / elen
            min_a = min(p[0] * ax + p[1] * ay for p in poly_a)
            max_a = max(p[0] * ax + p[1] * ay for p in poly_a)
            min_b = min(p[0] * ax + p[1] * ay for p in poly_b)
            max_b = max(p[0] * ax + p[1] * ay for p in poly_b)
            overlap = min(max_a, max_b) - max(min_a, min_b)
            if overlap <= 1e-9:
                return None
            if overlap < min_depth:
                min_depth = overlap
                best_axis = (ax, ay)
    return (min_depth, best_axis)


def _is_floor_standing_fixture(fx: Any) -> bool:
    """True when a fixture occupies floor circulation space."""
    if getattr(fx, "is_upper", False):
        return False
    if getattr(fx, "mount_surface", "floor") == "countertop":
        return False
    if getattr(fx, "symbol_type", "") == "wall_oven":
        return False
    return True


def _fixture_polygon(fx: Any) -> list[Point]:
    if hasattr(fx, "world_corners"):
        return [(float(p[0]), float(p[1])) for p in fx.world_corners(include_overhang=False)]
    return []


def clamp_fixture_out_of_walls(
    fx: Any,
    walls: Iterable[Any],
    orig_pos: Point | None = None,
    margin_in: float = 0.0,
) -> bool:
    """Push ``fx`` out of any overlapping straight structural walls in place.

    For exterior walls, ``orig_pos`` determines which side of the wall the fixture
    stays on so furniture cannot be placed or dragged out through exterior walls.

    Args:
        fx: Fixture object exposing ``x``, ``y``, and ``world_corners()``.
        walls: Structural walls on the active level/layer.
        orig_pos: Optional pre-move ``(x, y)`` position in inches.
        margin_in: Optional extra clearance outside the wall face in inches.

    Returns:
        True if ``fx`` was moved to resolve a wall overlap.
    """
    wall_list = [w for w in walls if _wall_polygon(w) is not None]
    if not wall_list:
        return False

    clamped = False
    for _ in range(4):
        moved_in_pass = False
        for wall in wall_list:
            wall_poly = _wall_polygon(wall)
            fx_poly = _fixture_polygon(fx)
            if wall_poly is None or len(fx_poly) < 3:
                continue
            ov = _sat_overlap(fx_poly, wall_poly)
            if ov is None or ov[0] <= 0.05:
                continue

            x1, y1 = float(wall.start[0]), float(wall.start[1])
            x2, y2 = float(wall.end[0]), float(wall.end[1])
            dx, dy = x2 - x1, y2 - y1
            wlen = math.hypot(dx, dy)
            ux, uy = dx / wlen, dy / wlen
            nx, ny = -uy, ux
            half_t = float(getattr(wall, "width", 0.0) or 0.0) / 2.0 + margin_in

            is_ext = bool(getattr(wall, "exterior_wall", False))
            ref_x, ref_y = (
                orig_pos if (is_ext and orig_pos is not None) else (float(fx.x), float(fx.y))
            )
            side_dot = (ref_x - x1) * nx + (ref_y - y1) * ny
            if abs(side_dot) <= 1e-3:
                side_dot = (float(fx.x) - x1) * nx + (float(fx.y) - y1) * ny
            sign_n = 1.0 if side_dot >= 0.0 else -1.0

            n_vals = [(p[0] - x1) * nx + (p[1] - y1) * ny for p in fx_poly]
            if sign_n > 0.0:
                push_n = max(0.0, half_t - min(n_vals))
            else:
                push_n = max(0.0, max(n_vals) + half_t)

            u_vals = [(p[0] - x1) * ux + (p[1] - y1) * uy for p in fx_poly]
            ref_u = (ref_x - x1) * ux + (ref_y - y1) * uy
            push_u = float("inf")
            sign_u = 1.0
            if ref_u < 0.0:
                push_u = max(0.0, max(u_vals) + margin_in)
                sign_u = -1.0
            elif ref_u > wlen:
                push_u = max(0.0, (wlen + margin_in) - min(u_vals))
                sign_u = 1.0

            if push_u < push_n and push_u > 0.0:
                fx.x = float(fx.x) + sign_u * push_u * ux
                fx.y = float(fx.y) + sign_u * push_u * uy
                moved_in_pass = True
            elif push_n > 0.0:
                fx.x = float(fx.x) + sign_n * push_n * nx
                fx.y = float(fx.y) + sign_n * push_n * ny
                moved_in_pass = True
        if not moved_in_pass:
            break
        clamped = True
    return clamped


def fixture_wall_violations(
    fixtures: Iterable[Any],
    walls: Iterable[Any],
    layer_to_level: dict[str, str],
    tolerance_in: float = 0.75,
) -> list[str]:
    """Return error descriptions for any fixture penetrating a same-level wall."""
    violations: list[str] = []
    wall_polys: list[tuple[Any, str, list[Point]]] = []
    for wall in walls:
        poly = _wall_polygon(wall)
        if poly is not None:
            wlvl = layer_to_level.get(getattr(wall, "layer_id", ""), "")
            wall_polys.append((wall, wlvl, poly))

    for fx in fixtures:
        fx_poly = _fixture_polygon(fx)
        if len(fx_poly) < 3:
            continue
        flvl = layer_to_level.get(getattr(fx, "layer_id", ""), "")
        for wall, wlvl, wpoly in wall_polys:
            if flvl and wlvl and flvl != wlvl:
                continue
            ov = _sat_overlap(fx_poly, wpoly)
            if ov is not None and ov[0] > tolerance_in:
                kind = "exterior" if getattr(wall, "exterior_wall", False) else "interior"
                violations.append(
                    f"Fixture {fx.symbol_type} at ({fx.x:.1f}, {fx.y:.1f}) penetrates "
                    f"{kind} wall {wall.start}->{wall.end} by {ov[0]:.2f}\""
                )
    return violations


def door_swing_polygon(wall: Any, door: Any, ratio: float) -> list[Point] | None:
    """Return the swept clear-floor polygon (inches) of a swinging door, or None."""
    if wall is None or getattr(door, "door_type", "") in _NON_SWING_DOORS:
        return None
    cx, cy = arc_wall_point(wall, ratio)
    tx, ty = arc_wall_tangent(wall, ratio)
    tlen = math.hypot(tx, ty)
    if tlen <= 1e-6:
        return None
    tx, ty = tx / tlen, ty / tlen
    px, py = -ty, tx
    orient = getattr(door, "orientation", "inswing")
    dtype = getattr(door, "door_type", "single")
    # Single bi-fold in door_window_renderer.py swings toward -p for inswing and +p for outswing.
    if dtype == "bi-fold":
        nx, ny = (-px, -py) if orient == "inswing" else (px, py)
    else:
        nx, ny = (px, py) if orient == "inswing" else (-px, -py)

    w = float(getattr(door, "width", 36.0) or 36.0)
    hw = w / 2.0
    if "double" in dtype and "bi-fold" in dtype:
        leaf_len = w / 4.0
    elif "double" in dtype or "bi-fold" in dtype:
        leaf_len = hw
    else:
        leaf_len = w
    half_t = float(getattr(wall, "width", 4.5) or 4.5) / 2.0

    p0 = (cx - hw * tx + half_t * nx, cy - hw * ty + half_t * ny)
    p1 = (cx + hw * tx + half_t * nx, cy + hw * ty + half_t * ny)
    p2 = (p1[0] + leaf_len * nx, p1[1] + leaf_len * ny)
    p3 = (p0[0] + leaf_len * nx, p0[1] + leaf_len * ny)
    return [p0, p1, p2, p3]


def fixture_door_violations(
    fixtures: Iterable[Any],
    doors: Iterable[tuple[Any, Any, float]],
    layer_to_level: dict[str, str],
    tolerance_in: float = 1.0,
) -> list[str]:
    """Return error descriptions for any floor-standing fixture blocking a door swing."""
    violations: list[str] = []
    floor_fx = [fx for fx in fixtures if _is_floor_standing_fixture(fx)]
    for wall, door, ratio in doors:
        swing_poly = door_swing_polygon(wall, door, ratio)
        if swing_poly is None:
            continue
        dlvl = layer_to_level.get(getattr(door, "layer_id", ""), "")
        cx, cy = arc_wall_point(wall, ratio)
        for fx in floor_fx:
            flvl = layer_to_level.get(getattr(fx, "layer_id", ""), "")
            if dlvl and flvl and dlvl != flvl:
                continue
            fx_poly = _fixture_polygon(fx)
            ov = _sat_overlap(fx_poly, swing_poly)
            if ov is not None and ov[0] > tolerance_in:
                violations.append(
                    f"Fixture {fx.symbol_type} at ({fx.x:.1f}, {fx.y:.1f}) blocks "
                    f"{door.door_type} door at ({cx:.1f}, {cy:.1f}) by {ov[0]:.2f}\""
                )
    return violations


def _transform_local_rect(
    origin: Point,
    angle: float,
    u0: float,
    v0: float,
    u1: float,
    v1: float,
) -> list[Point]:
    """Build rectangle with edge 3->0 along ``u0`` (stair-adjoining) and 1->2 at ``u1``."""
    ca, sa = math.cos(angle), math.sin(angle)
    pts = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    return [(origin[0] + u * ca - v * sa, origin[1] + u * sa + v * ca) for u, v in pts]


def stair_landing_rects(
    stair: Any, landing_depth_in: float = 36.0
) -> tuple[list[Point], list[Point], Point, Point]:
    """Return ``(bottom_rect, top_rect, bottom_out_dir, top_out_dir)`` in inches.

    In both returned rectangles, vertices ``[0, 1, 2, 3]`` are ordered so edge
    ``3->0`` adjoins the stair treads and edges ``0->1``, ``1->2``, ``2->3`` are
    the three outer landing edges.
    """
    from ..Canvas.winder_geometry import l_stair_layout

    width = float(getattr(stair, "width", 36.0) or 36.0)
    hw = width / 2.0
    ang = float(getattr(stair, "direction_angle", 0.0) or 0.0)
    sx, sy = float(stair.start_point[0]), float(stair.start_point[1])
    ca, sa = math.cos(ang), math.sin(ang)

    bottom_rect = _transform_local_rect((sx, sy), ang, 0.0, -hw, -landing_depth_in, hw)
    bottom_dir = (-ca, -sa)

    stype = getattr(stair, "stair_type", "straight")
    turn = getattr(stair, "turn_direction", "left")

    if stype == "L-shaped":
        lay = l_stair_layout(
            int(getattr(stair, "num_steps", 14)),
            int(getattr(stair, "steps_before_landing", 0)),
            float(getattr(stair, "tread_depth", 10.0)),
            float(getattr(stair, "landing_depth", 36.0)),
            width,
            int(getattr(stair, "winder_count", 0)),
        )
        rb, ra, ld = lay["run_before"], lay["run_after"], lay["landing_depth"]
        if turn == "left":
            loc_o = (rb + ld - hw, -hw)
            rot2 = -math.pi / 2.0
        else:
            loc_o = (rb + ld - hw, hw)
            rot2 = math.pi / 2.0
        o_world = (sx + loc_o[0] * ca - loc_o[1] * sa, sy + loc_o[0] * sa + loc_o[1] * ca)
        ang2 = ang + rot2
        top_rect = _transform_local_rect(o_world, ang2, ra, -hw, ra + landing_depth_in, hw)
        top_dir = (math.cos(ang2), math.sin(ang2))
    elif stype == "U-shaped":
        well = float(getattr(stair, "inner_radius", 0.0) or 0.0)
        total = int(getattr(stair, "num_steps", 14))
        sbl = int(getattr(stair, "steps_before_landing", 0))
        before = sbl if 0 < sbl < total else total // 2
        after = total - before
        tread = float(getattr(stair, "tread_depth", 10.0))
        rb = (before - 1) * tread if before > 0 else 0.0
        ra = (after - 1) * tread if after > 0 else 0.0
        v_off = -(width + well) if turn == "left" else (width + well)
        o_world = (sx + rb * ca - v_off * sa, sy + rb * sa + v_off * ca)
        ang2 = ang + math.pi
        top_rect = _transform_local_rect(o_world, ang2, ra, -hw, ra + landing_depth_in, hw)
        top_dir = (-ca, -sa)
    else:
        run = float(getattr(stair, "total_run", 120.0) or 120.0)
        top_rect = _transform_local_rect((sx, sy), ang, run, -hw, run + landing_depth_in, hw)
        top_dir = (ca, sa)

    return (bottom_rect, top_rect, bottom_dir, top_dir)


def _rect_center(rect: list[Point]) -> Point:
    return (
        sum(p[0] for p in rect) / len(rect),
        sum(p[1] for p in rect) / len(rect),
    )


def _edge_clear_access_width(
    edge_a: Point,
    edge_b: Point,
    landing_center: Point,
    level_walls: list[tuple[Any, list[Point]]],
    doors_by_wall: dict[int, list[tuple[Any, float]]],
) -> float:
    """Return widest unobstructed contiguous gap (inches) along outer edge ``a->b``."""
    ex, ey = edge_b[0] - edge_a[0], edge_b[1] - edge_a[1]
    elen = math.hypot(ex, ey)
    if elen <= 1e-4:
        return 0.0
    ux, uy = ex / elen, ey / elen
    nx, ny = -uy, ux
    mid = ((edge_a[0] + edge_b[0]) / 2.0, (edge_a[1] + edge_b[1]) / 2.0)
    if (mid[0] - landing_center[0]) * nx + (mid[1] - landing_center[1]) * ny < 0.0:
        nx, ny = -nx, -ny

    blocked: list[tuple[float, float]] = []
    for wall, wpoly in level_walls:
        n_vals = [(p[0] - edge_a[0]) * nx + (p[1] - edge_a[1]) * ny for p in wpoly]
        if max(n_vals) < -1.0 or min(n_vals) > 6.0:
            continue
        u_vals = [(p[0] - edge_a[0]) * ux + (p[1] - edge_a[1]) * uy for p in wpoly]
        s_lo = max(0.0, min(u_vals))
        s_hi = min(elen, max(u_vals))
        if s_hi - s_lo <= 0.5:
            continue

        # Subtract any door openings along this wall from its blocked span.
        wall_blocks = [(s_lo, s_hi)]
        for door, ratio in doors_by_wall.get(id(wall), []):
            dc = arc_wall_point(wall, ratio)
            dt = arc_wall_tangent(wall, ratio)
            dw = float(getattr(door, "width", 36.0) or 36.0) / 2.0
            d0 = (dc[0] - dw * dt[0], dc[1] - dw * dt[1])
            d1 = (dc[0] + dw * dt[0], dc[1] + dw * dt[1])
            du0 = (d0[0] - edge_a[0]) * ux + (d0[1] - edge_a[1]) * uy
            du1 = (d1[0] - edge_a[0]) * ux + (d1[1] - edge_a[1]) * uy
            d_lo, d_hi = min(du0, du1), max(du0, du1)
            next_blocks: list[tuple[float, float]] = []
            for b0, b1 in wall_blocks:
                if d_hi <= b0 + 0.1 or d_lo >= b1 - 0.1:
                    next_blocks.append((b0, b1))
                else:
                    if d_lo > b0 + 0.1:
                        next_blocks.append((b0, d_lo))
                    if d_hi < b1 - 0.1:
                        next_blocks.append((d_hi, b1))
            wall_blocks = next_blocks
        blocked.extend(wall_blocks)

    if not blocked:
        return elen
    blocked.sort()
    merged: list[tuple[float, float]] = [blocked[0]]
    for b0, b1 in blocked[1:]:
        if b0 <= merged[-1][1] + 0.1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b1))
        else:
            merged.append((b0, b1))

    best_gap = 0.0
    cursor = 0.0
    for b0, b1 in merged:
        best_gap = max(best_gap, b0 - cursor)
        cursor = max(cursor, b1)
    best_gap = max(best_gap, elen - cursor)
    return best_gap


def stair_landing_and_access_violations(
    stairs: Iterable[Any],
    walls: Iterable[Any],
    rooms: Iterable[Any],
    doors: Iterable[tuple[Any, Any, float]],
    fixtures: Iterable[Any],
    levels: Iterable[Any],
    layer_to_level: dict[str, str],
    min_landing_depth_in: float = 36.0,
    min_access_width_in: float = 32.0,
) -> list[str]:
    """Validate stair top/bottom landings, upper-floor flushness, and access."""
    violations: list[str] = []
    level_by_id = {lvl.id: lvl for lvl in levels}
    walls_by_lvl: dict[str, list[tuple[Any, list[Point]]]] = {}
    for w in walls:
        wp = _wall_polygon(w)
        if wp is not None:
            wlvl = layer_to_level.get(getattr(w, "layer_id", ""), "")
            walls_by_lvl.setdefault(wlvl, []).append((w, wp))

    rooms_by_lvl: dict[str, list[Any]] = {}
    for r in rooms:
        rlvl = layer_to_level.get(getattr(r, "layer_id", ""), "")
        rooms_by_lvl.setdefault(rlvl, []).append(r)

    fx_by_lvl: dict[str, list[tuple[Any, list[Point]]]] = {}
    for fx in fixtures:
        if _is_floor_standing_fixture(fx):
            flvl = layer_to_level.get(getattr(fx, "layer_id", ""), "")
            fx_by_lvl.setdefault(flvl, []).append((fx, _fixture_polygon(fx)))

    doors_by_wall: dict[int, list[tuple[Any, float]]] = {}
    for wall, door, ratio in doors:
        if wall is not None:
            doors_by_wall.setdefault(id(wall), []).append((door, ratio))

    for stair in stairs:
        sid = getattr(stair, "identifier", "stair")
        start_lvl_id = getattr(stair, "start_level_id", "") or layer_to_level.get(
            getattr(stair, "layer_id", ""), ""
        )
        end_lvl_id = getattr(stair, "end_level_id", "") or start_lvl_id

        # 1. Flushness with upper-story floor
        s_lvl = level_by_id.get(start_lvl_id)
        e_lvl = level_by_id.get(end_lvl_id)
        if s_lvl is not None and e_lvl is not None and s_lvl.id != e_lvl.id:
            expected_rise = float(e_lvl.elevation) - float(s_lvl.elevation)
            actual_rise = float(getattr(stair, "total_rise", 0.0) or 0.0)
            if abs(actual_rise - expected_rise) > 0.5:
                violations.append(
                    f"Stair {sid} total_rise {actual_rise:.2f}\" is not flush with "
                    f"level elevation difference {expected_rise:.2f}\""
                )

        bottom_rect, top_rect, _, _ = stair_landing_rects(stair, min_landing_depth_in)
        landing_specs = [
            ("bottom", bottom_rect, start_lvl_id, False),
            ("top", top_rect, end_lvl_id, True),
        ]

        for label, rect, lvl_id, check_holes in landing_specs:
            lvl_walls = walls_by_lvl.get(lvl_id, [])
            for w, wp in lvl_walls:
                ov = _sat_overlap(rect, wp)
                if ov is not None and ov[0] > 0.75:
                    violations.append(
                        f"Stair {sid} {label} landing intersects wall {w.start}->{w.end} "
                        f"by {ov[0]:.2f}\""
                    )

            for fx, fp in fx_by_lvl.get(lvl_id, []):
                ov = _sat_overlap(rect, fp)
                if ov is not None and ov[0] > 1.0:
                    violations.append(
                        f"Stair {sid} {label} landing blocked by {fx.symbol_type} "
                        f"at ({fx.x:.1f}, {fx.y:.1f})"
                    )

            center = _rect_center(rect)
            lvl_rooms = rooms_by_lvl.get(lvl_id, [])
            if lvl_rooms:
                containing = [
                    r for r in lvl_rooms
                    if len(getattr(r, "points", [])) >= 3 and _point_in_poly(center, r.points)
                ]
                if not containing:
                    violations.append(
                        f"Stair {sid} {label} landing at ({center[0]:.1f}, {center[1]:.1f}) "
                        f"is outside any room on level {lvl_id}"
                    )
                elif check_holes:
                    for r in containing:
                        for hole in getattr(r, "holes", []):
                            if getattr(hole, "ceiling_only", False):
                                continue
                            hpts = getattr(hole, "points", [])
                            if len(hpts) >= 3 and _point_in_poly(center, hpts):
                                violations.append(
                                    f"Stair {sid} top landing falls inside floor opening "
                                    f"in room '{getattr(r, 'name', '')}'"
                                )
                                break

            best_clear = max(
                _edge_clear_access_width(rect[k], rect[(k + 1) % 4], center, lvl_walls, doors_by_wall)
                for k in range(3)
            )
            if best_clear < min_access_width_in - 1e-3:
                violations.append(
                    f"Stair {sid} {label} landing is enclosed (max clear access {best_clear:.1f}\" "
                    f"< {min_access_width_in:.1f}\")"
                )

        # 5. Doors on start level must not swing into stair treads
        stair_parts = stair_footprint_parts(stair)
        for wall, door, ratio in doors:
            dlvl = layer_to_level.get(getattr(door, "layer_id", ""), "")
            if start_lvl_id and dlvl and dlvl != start_lvl_id:
                continue
            spoly = door_swing_polygon(wall, door, ratio)
            if spoly is None:
                continue
            for part in stair_parts:
                ov = _sat_overlap(spoly, part)
                if ov is not None and ov[0] > 1.0:
                    violations.append(
                        f"Door {door.door_type} swings into stair {sid} by {ov[0]:.2f}\""
                    )
                    break

    return violations


def _same_level(lvl_a: str, lvl_b: str) -> bool:
    return not (lvl_a and lvl_b and lvl_a != lvl_b)


def _fixture_local_rect(
    fx: Any,
    lx0: float,
    ly0: float,
    lx1: float,
    ly1: float,
) -> list[Point]:
    """Transform local rectangle ``[lx0..lx1] x [ly0..ly1]`` (inches) to world polygon."""
    rad = math.radians(float(getattr(fx, "rotation", 0.0) or 0.0))
    ca, sa = math.cos(rad), math.sin(rad)
    cx, cy = float(fx.x), float(fx.y)
    pts = [(lx0, ly0), (lx1, ly0), (lx1, ly1), (lx0, ly1)]
    return [(cx + lx * ca - ly * sa, cy + lx * sa + ly * ca) for lx, ly in pts]


def _check_rect_clear(
    rect: list[Point],
    owner: Any,
    owner_label: str,
    lvl_id: str,
    wall_polys: list[tuple[Any, str, list[Point]]],
    floor_fx_polys: list[tuple[Any, str, list[Point]]],
    skip_wall_ids: set[int] | None = None,
    tolerance_in: float = 1.0,
) -> list[str]:
    """Check that ``rect`` is clear of same-level walls and floor-standing fixtures."""
    violations: list[str] = []
    skip_ids = skip_wall_ids or set()
    for wall, wlvl, wpoly in wall_polys:
        if id(wall) in skip_ids or not _same_level(lvl_id, wlvl):
            continue
        ov = _sat_overlap(rect, wpoly)
        if ov is not None and ov[0] > tolerance_in:
            violations.append(
                f"{owner_label} clearance blocked by wall {wall.start}->{wall.end} "
                f"by {ov[0]:.2f}\""
            )
    for other_fx, olvl, fpoly in floor_fx_polys:
        if other_fx is owner or not _same_level(lvl_id, olvl):
            continue
        ov = _sat_overlap(rect, fpoly)
        if ov is not None and ov[0] > tolerance_in:
            violations.append(
                f"{owner_label} clearance blocked by {other_fx.symbol_type} "
                f"at ({other_fx.x:.1f}, {other_fx.y:.1f}) by {ov[0]:.2f}\""
            )
    return violations


def pocket_door_violations(
    doors: Iterable[tuple[Any, Any, float]],
    walls: Iterable[Any],
    windows: Iterable[tuple[Any, Any, float]],
    layer_to_level: dict[str, str],
    tolerance_in: float = 0.5,
) -> list[str]:
    """Verify each pocket door's ``2 * width + 2\"`` frame fits unobstructed in its wall chain."""
    violations: list[str] = []
    wall_list = list(walls)
    all_openings: list[tuple[Any, str, Any, float, float, str]] = []
    for w, d, r in doors:
        if w is not None:
            all_openings.append((
                w,
                "door",
                d,
                float(r),
                float(getattr(d, "width", 36.0) or 36.0),
                layer_to_level.get(getattr(d, "layer_id", ""), ""),
            ))
    for w, win, r in windows:
        if w is not None:
            all_openings.append((
                w,
                "window",
                win,
                float(r),
                float(getattr(win, "width", 36.0) or 36.0),
                layer_to_level.get(getattr(win, "layer_id", ""), ""),
            ))

    for wall, door, ratio in doors:
        if wall is None or getattr(door, "door_type", "") != "pocket":
            continue
        if getattr(wall, "is_curved", False):
            continue
        dx = float(wall.end[0]) - float(wall.start[0])
        dy = float(wall.end[1]) - float(wall.start[1])
        wlen = math.hypot(dx, dy)
        if wlen <= 1e-4:
            continue
        ux, uy = dx / wlen, dy / wlen
        ox, oy = float(wall.start[0]), float(wall.start[1])
        dlvl = layer_to_level.get(getattr(door, "layer_id", ""), "")
        same_lvl_walls = [
            w for w in wall_list
            if _same_level(dlvl, layer_to_level.get(getattr(w, "layer_id", ""), ""))
        ]
        chain = collinear_chain(wall, same_lvl_walls)
        chain_ids = {id(w) for w in chain}

        def proj(pt: Point) -> float:
            return (float(pt[0]) - ox) * ux + (float(pt[1]) - oy) * uy

        chain_lo = min(min(proj(w.start), proj(w.end)) for w in chain)
        chain_hi = max(max(proj(w.start), proj(w.end)) for w in chain)
        centre = float(ratio) * wlen
        door_w = float(getattr(door, "width", 36.0) or 36.0)
        left_ext, right_ext = pocket_door_extents(door_w, getattr(door, "swing", "left"))
        pkt_lo = centre - left_ext
        pkt_hi = centre + right_ext

        if pkt_lo < chain_lo - tolerance_in or pkt_hi > chain_hi + tolerance_in:
            violations.append(
                f"Pocket door ({door_w:g}\", frame {2.0 * door_w + 2.0:g}\") at "
                f"({ox + ux * centre:.1f}, {oy + uy * centre:.1f}) extends past wall ends "
                f"[{chain_lo:.1f}, {chain_hi:.1f}] with pocket [{pkt_lo:.1f}, {pkt_hi:.1f}]"
            )

        for owall, okind, oobj, oratio, ow, olvl in all_openings:
            if oobj is door or id(owall) not in chain_ids or not _same_level(dlvl, olvl):
                continue
            oc = arc_wall_point(owall, oratio)
            oc_proj = proj(oc)
            o_lo = oc_proj - ow / 2.0
            o_hi = oc_proj + ow / 2.0
            ov = min(pkt_hi, o_hi) - max(pkt_lo, o_lo)
            if ov > tolerance_in:
                violations.append(
                    f"Pocket door at ({ox + ux * centre:.1f}, {oy + uy * centre:.1f}) "
                    f"cavity conflicts with {okind} on same wall run by {ov:.2f}\""
                )

    return violations


def bathroom_clearance_violations(
    doors: Iterable[tuple[Any, Any, float]],
    fixtures: Iterable[Any],
    rooms: Iterable[Any],
    walls: Iterable[Any],
    layer_to_level: dict[str, str],
    min_door_clear_in: float = 24.0,
    min_toilet_front_in: float = 21.0,
    check_fixtures: bool = True,
) -> list[str]:
    """Check bathroom door ingress/egress landing clearance and toilet 21\" front clearance."""
    violations: list[str] = []
    wall_list = list(walls)
    wall_polys = [
        (w, layer_to_level.get(getattr(w, "layer_id", ""), ""), wp)
        for w in wall_list
        if (wp := _wall_polygon(w)) is not None
    ]
    floor_fx_polys = [
        (fx, layer_to_level.get(getattr(fx, "layer_id", ""), ""), _fixture_polygon(fx))
        for fx in fixtures
        if _is_floor_standing_fixture(fx)
    ]
    bath_rooms = []
    for r in rooms:
        if len(getattr(r, "points", [])) < 3:
            continue
        rtype = (getattr(r, "room_type", "") or "").lower()
        rname = (getattr(r, "name", "") or "").lower()
        if rtype == "bathroom" or "bath" in rname:
            bath_rooms.append((r, layer_to_level.get(getattr(r, "layer_id", ""), "")))

    for wall, door, ratio in doors:
        if wall is None or not bath_rooms:
            continue
        cx, cy = arc_wall_point(wall, ratio)
        tx, ty = arc_wall_tangent(wall, ratio)
        tlen = math.hypot(tx, ty)
        if tlen <= 1e-6:
            continue
        tx, ty = tx / tlen, ty / tlen
        px, py = -ty, tx
        dlvl = layer_to_level.get(getattr(door, "layer_id", ""), "")
        half_t = float(getattr(wall, "width", 4.5) or 4.5) / 2.0
        half_w = max(9.0, (float(getattr(door, "width", 30.0) or 30.0) - 2.0) / 2.0)

        same_lvl_baths = [
            r for r, rlvl in bath_rooms if _same_level(dlvl, rlvl)
        ]
        if not same_lvl_baths:
            continue

        same_lvl_walls = [
            w for w in wall_list
            if _same_level(dlvl, layer_to_level.get(getattr(w, "layer_id", ""), ""))
        ]
        skip_ids = {id(w) for w in collinear_chain(wall, same_lvl_walls)}

        for side in (1.0, -1.0):
            nx, ny = side * px, side * py
            probe = (cx + (half_t + 6.0) * nx, cy + (half_t + 6.0) * ny)
            if not any(_point_in_poly(probe, r.points) for r in same_lvl_baths):
                continue
            d0 = half_t + 0.5
            d1 = half_t + min_door_clear_in
            landing = [
                (cx - half_w * tx + d0 * nx, cy - half_w * ty + d0 * ny),
                (cx + half_w * tx + d0 * nx, cy + half_w * ty + d0 * ny),
                (cx + half_w * tx + d1 * nx, cy + half_w * ty + d1 * ny),
                (cx - half_w * tx + d1 * nx, cy - half_w * ty + d1 * ny),
            ]
            label = f"Bathroom door ({door.door_type}) at ({cx:.1f}, {cy:.1f}) ingress/egress"
            violations.extend(
                _check_rect_clear(
                    landing, door, label, dlvl, wall_polys,
                    floor_fx_polys if check_fixtures else [],
                    skip_wall_ids=skip_ids,
                )
            )

    for fx, flvl, _poly in floor_fx_polys:
        if getattr(fx, "symbol_type", "") != "toilet":
            continue
        hw = float(fx.width) / 2.0
        hd = float(fx.depth) / 2.0
        front_rect = _fixture_local_rect(
            fx, -hw + 1.0, hd + 0.5, hw - 1.0, hd + min_toilet_front_in
        )
        label = f"Toilet at ({fx.x:.1f}, {fx.y:.1f}) {min_toilet_front_in:g}\" front"
        violations.extend(
            _check_rect_clear(front_rect, fx, label, flvl, wall_polys, floor_fx_polys)
        )

    return violations


def sink_and_vanity_clearance_violations(
    fixtures: Iterable[Any],
    walls: Iterable[Any],
    layer_to_level: dict[str, str],
    min_front_clear_in: float = 21.0,
) -> list[str]:
    """Check ``21\"`` clear floor space in front of sinks and bathroom vanities."""
    violations: list[str] = []
    wall_polys = [
        (w, layer_to_level.get(getattr(w, "layer_id", ""), ""), wp)
        for w in walls
        if (wp := _wall_polygon(w)) is not None
    ]
    floor_fx_polys = [
        (fx, layer_to_level.get(getattr(fx, "layer_id", ""), ""), _fixture_polygon(fx))
        for fx in fixtures
        if _is_floor_standing_fixture(fx)
    ]

    for fx, flvl, _poly in floor_fx_polys:
        sym = getattr(fx, "symbol_type", "")
        if sym not in _SINK_VANITY_SYMBOLS:
            continue
        hw = float(fx.width) / 2.0
        hd = float(fx.depth) / 2.0
        overhang = float(getattr(fx, "countertop_overhang", 0.0) or 0.0)
        has_ct = bool(getattr(fx, "has_countertop", False)) and overhang > 0.0
        front_y = hd + (overhang if has_ct else 0.0)
        front_rect = _fixture_local_rect(
            fx, -hw + 1.0, front_y + 0.5, hw - 1.0, front_y + min_front_clear_in
        )
        label = f"Sink/vanity {sym} at ({fx.x:.1f}, {fx.y:.1f}) {min_front_clear_in:g}\" front"
        violations.extend(
            _check_rect_clear(front_rect, fx, label, flvl, wall_polys, floor_fx_polys)
        )
    return violations


def bathtub_drain_wall_violations(
    fixtures: Iterable[Any],
    walls: Iterable[Any],
    layer_to_level: dict[str, str],
    max_gap_in: float = 2.5,
) -> list[str]:
    """Verify every bathtub's drain end (local ``-X``) butts against a same-level plumbing wall."""
    violations: list[str] = []
    wall_axes: list[tuple[Any, str, list[Point], Point]] = []
    for wall in walls:
        wpoly = _wall_polygon(wall)
        if wpoly is None:
            continue
        dx = float(wall.end[0]) - float(wall.start[0])
        dy = float(wall.end[1]) - float(wall.start[1])
        wlen = math.hypot(dx, dy)
        if wlen <= 1e-4:
            continue
        wlvl = layer_to_level.get(getattr(wall, "layer_id", ""), "")
        wall_axes.append((wall, wlvl, wpoly, (dx / wlen, dy / wlen)))

    for fx in fixtures:
        if getattr(fx, "symbol_type", "") != "bathtub":
            continue
        flvl = layer_to_level.get(getattr(fx, "layer_id", ""), "")
        hw = float(fx.width) / 2.0
        hd = float(fx.depth) / 2.0
        probe = _fixture_local_rect(fx, -hw - max_gap_in, -hd * 0.5, -hw + 1.0, hd * 0.5)
        rad = math.radians(float(getattr(fx, "rotation", 0.0) or 0.0))
        tub_ux, tub_uy = math.cos(rad), math.sin(rad)

        has_drain_wall = False
        for _w, wlvl, wpoly, (wux, wuy) in wall_axes:
            if not _same_level(flvl, wlvl):
                continue
            if abs(wux * tub_ux + wuy * tub_uy) >= 0.35:
                continue
            if _sat_overlap(probe, wpoly) is not None:
                has_drain_wall = True
                break

        if not has_drain_wall:
            violations.append(
                f"Bathtub at ({fx.x:.1f}, {fx.y:.1f}) drain end (-X local) must butt "
                f"against a wall for plumbing (gap > {max_gap_in:g}\")"
            )
    return violations


def laundry_appliance_violations(
    fixtures: Iterable[Any],
    doors: Iterable[tuple[Any, Any, float]],
    walls: Iterable[Any],
    layer_to_level: dict[str, str],
    min_front_clear_in: float = 30.0,
) -> list[str]:
    """Verify washers and dryers have ``30\"`` unobstructed front door-opening clearance."""
    violations: list[str] = []
    wall_polys = [
        (w, layer_to_level.get(getattr(w, "layer_id", ""), ""), wp)
        for w in walls
        if (wp := _wall_polygon(w)) is not None
    ]
    floor_fx_polys = [
        (fx, layer_to_level.get(getattr(fx, "layer_id", ""), ""), _fixture_polygon(fx))
        for fx in fixtures
        if _is_floor_standing_fixture(fx)
    ]

    door_info_by_wall: dict[int, list[tuple[float, float, list[Point] | None, str]]] = {}
    for wall, door, ratio in doors:
        if wall is None:
            continue
        cx, cy = arc_wall_point(wall, ratio)
        wx = float(wall.end[0]) - float(wall.start[0])
        wy = float(wall.end[1]) - float(wall.start[1])
        wlen = math.hypot(wx, wy)
        if wlen <= 1e-4:
            continue
        ux, uy = wx / wlen, wy / wlen
        c_u = (cx - float(wall.start[0])) * ux + (cy - float(wall.start[1])) * uy
        half_dw = float(getattr(door, "width", 36.0) or 36.0) / 2.0
        dlvl = layer_to_level.get(getattr(door, "layer_id", ""), "")
        spoly = door_swing_polygon(wall, door, ratio)
        door_info_by_wall.setdefault(id(wall), []).append(
            (c_u - half_dw, c_u + half_dw, spoly, dlvl)
        )

    for fx, flvl, fx_poly in floor_fx_polys:
        sym = getattr(fx, "symbol_type", "")
        if sym not in _LAUNDRY_SYMBOLS:
            continue
        hw = float(fx.width) / 2.0
        hd = float(fx.depth) / 2.0
        front_rect = _fixture_local_rect(
            fx, -hw + 1.0, hd + 0.5, hw - 1.0, hd + min_front_clear_in
        )

        # 1. Check other floor-standing fixtures in front of washer/dryer
        for other_fx, olvl, fpoly in floor_fx_polys:
            if other_fx is fx or not _same_level(flvl, olvl):
                continue
            ov = _sat_overlap(front_rect, fpoly)
            if ov is not None and ov[0] > 1.0:
                violations.append(
                    f"Laundry {sym} at ({fx.x:.1f}, {fx.y:.1f}) front access blocked by "
                    f"{other_fx.symbol_type} by {ov[0]:.2f}\""
                )

        # 2. Check walls blocking front access (unless span is covered by a passable door opening
        #    whose swing does not obstruct the appliance front).
        for wall, wlvl, wpoly in wall_polys:
            if not _same_level(flvl, wlvl):
                continue
            ov = _sat_overlap(front_rect, wpoly)
            if ov is None or ov[0] <= 1.0:
                continue
            wx = float(wall.end[0]) - float(wall.start[0])
            wy = float(wall.end[1]) - float(wall.start[1])
            wlen = math.hypot(wx, wy) or 1.0
            ux, uy = wx / wlen, wy / wlen
            r_u = [
                (p[0] - float(wall.start[0])) * ux + (p[1] - float(wall.start[1])) * uy
                for p in front_rect
            ]
            span_lo = max(0.0, min(r_u))
            span_hi = min(wlen, max(r_u))
            covered = False
            for d_lo, d_hi, spoly, dlvl in door_info_by_wall.get(id(wall), []):
                if not _same_level(flvl, dlvl):
                    continue
                if d_lo - 1.0 <= span_lo and span_hi <= d_hi + 1.0:
                    hits_front = spoly is not None and (_sat_overlap(front_rect, spoly) or (0.0,))[0] > 1.0
                    hits_fx = spoly is not None and (_sat_overlap(fx_poly, spoly) or (0.0,))[0] > 1.0
                    if not (hits_front or hits_fx):
                        covered = True
                        break
            if not covered:
                violations.append(
                    f"Laundry {sym} at ({fx.x:.1f}, {fx.y:.1f}) front door clearance "
                    f"({min_front_clear_in:g}\") blocked by wall {wall.start}->{wall.end}"
                )

    return violations


def _collect_opening_ingress_egress_issues(
    fixtures: Iterable[Any],
    doors: Iterable[tuple[Any, Any, float]],
    walls: Iterable[Any],
    layer_to_level: dict[str, str],
    min_clear_in: float = 24.0,
    tolerance_in: float = 1.0,
) -> list[LayoutIssue]:
    """Check every door/opening on both sides for unobstructed ingress/egress."""
    del walls
    issues: list[LayoutIssue] = []
    floor_fx_polys = [
        (fx, layer_to_level.get(getattr(fx, "layer_id", ""), ""), _fixture_polygon(fx))
        for fx in fixtures
        if _is_floor_standing_fixture(fx)
    ]

    for wall, door, ratio in doors:
        if wall is None:
            continue
        cx, cy = arc_wall_point(wall, ratio)
        tx, ty = arc_wall_tangent(wall, ratio)
        tlen = math.hypot(tx, ty)
        if tlen <= 1e-6:
            continue
        tx, ty = tx / tlen, ty / tlen
        px, py = -ty, tx
        dlvl = layer_to_level.get(getattr(door, "layer_id", ""), "")
        half_t = float(getattr(wall, "width", 4.5) or 4.5) / 2.0
        dw = float(getattr(door, "width", 36.0) or 36.0)
        half_w = max(10.0, (dw - 4.0) / 2.0)

        for side in (1.0, -1.0):
            nx, ny = side * px, side * py
            d0 = half_t + 0.5
            d1 = half_t + min_clear_in
            landing = [
                (cx - half_w * tx + d0 * nx, cy - half_w * ty + d0 * ny),
                (cx + half_w * tx + d0 * nx, cy + half_w * ty + d0 * ny),
                (cx + half_w * tx + d1 * nx, cy + half_w * ty + d1 * ny),
                (cx - half_w * tx + d1 * nx, cy - half_w * ty + d1 * ny),
            ]
            for fx, flvl, fpoly in floor_fx_polys:
                if not _same_level(dlvl, flvl):
                    continue
                ov = _sat_overlap(landing, fpoly)
                if ov is not None and ov[0] > tolerance_in:
                    msg = (
                        f"Fixture {fx.symbol_type} at ({fx.x:.1f}, {fx.y:.1f}) blocks "
                        f"{door.door_type} opening at ({cx:.1f}, {cy:.1f}) ingress/egress "
                        f"by {ov[0]:.2f}\""
                    )
                    issues.append(
                        LayoutIssue(
                            category="Opening Ingress/Egress",
                            severity="error",
                            message=msg,
                            level_id=dlvl,
                            location_in=(cx, cy),
                            object_id=str(getattr(fx, "identifier", "") or ""),
                        )
                    )
    return issues


def opening_ingress_egress_violations(
    fixtures: Iterable[Any],
    doors: Iterable[tuple[Any, Any, float]],
    walls: Iterable[Any],
    layer_to_level: dict[str, str],
    min_clear_in: float = 24.0,
    tolerance_in: float = 1.0,
) -> list[str]:
    """Verify no floor-standing fixture blocks ingress/egress at any door or opening."""
    return [
        i.message
        for i in _collect_opening_ingress_egress_issues(
            fixtures, doors, walls, layer_to_level, min_clear_in, tolerance_in
        )
    ]


def _collect_kitchen_sink_window_issues(
    fixtures: Iterable[Any],
    walls: Iterable[Any],
    windows: Iterable[tuple[Any, Any, float]],
    layer_to_level: dict[str, str],
    max_wall_gap_in: float = 4.0,
    max_center_offset_in: float = 2.0,
) -> list[LayoutIssue]:
    """Verify exterior-wall kitchen sinks have a centered window in that wall."""
    issues: list[LayoutIssue] = []
    wall_list = list(walls)
    fx_list = list(fixtures)
    sink_bases = [
        fx for fx in fx_list if getattr(fx, "symbol_type", "") == "sink_base_cabinet"
    ]

    ext_walls: list[tuple[Any, str, Point, Point, float, float]] = []
    for wall in wall_list:
        if getattr(wall, "symbolic", False) or getattr(wall, "is_curved", False):
            continue
        if not getattr(wall, "exterior_wall", False):
            continue
        dx = float(wall.end[0]) - float(wall.start[0])
        dy = float(wall.end[1]) - float(wall.start[1])
        wlen = math.hypot(dx, dy)
        if wlen <= 1e-4:
            continue
        half_t = float(getattr(wall, "width", 6.0) or 6.0) / 2.0
        wlvl = layer_to_level.get(getattr(wall, "layer_id", ""), "")
        ext_walls.append((wall, wlvl, (float(wall.start[0]), float(wall.start[1])),
                          (dx / wlen, dy / wlen), wlen, half_t))

    win_list = [
        (w, win, float(ratio), layer_to_level.get(getattr(win, "layer_id", ""), ""))
        for w, win, ratio in windows
        if w is not None
    ]

    for fx in fx_list:
        sym = getattr(fx, "symbol_type", "")
        if sym not in _KITCHEN_SINK_SYMBOLS:
            continue
        flvl = layer_to_level.get(getattr(fx, "layer_id", ""), "")
        # Skip drop-in sink stacked directly on top of a sink_base_cabinet on same level
        if sym != "sink_base_cabinet":
            has_base = False
            for sb in sink_bases:
                sblvl = layer_to_level.get(getattr(sb, "layer_id", ""), "")
                if _same_level(flvl, sblvl):
                    if math.hypot(float(sb.x) - float(fx.x), float(sb.y) - float(fx.y)) <= 6.0:
                        has_base = True
                        break
            if has_base:
                continue

        rad = math.radians(float(getattr(fx, "rotation", 0.0) or 0.0))
        fx_ux, fx_uy = math.cos(rad), math.sin(rad)
        back_nx, back_ny = math.sin(rad), -math.cos(rad)
        hd = float(getattr(fx, "depth", 24.0) or 24.0) / 2.0
        back_pt = (float(fx.x) + hd * back_nx, float(fx.y) + hd * back_ny)

        matched_wall: tuple[Any, Point, Point] | None = None
        best_gap = float("inf")
        for wall, wlvl, (wx0, wy0), (wux, wuy), wlen, half_t in ext_walls:
            if not _same_level(flvl, wlvl):
                continue
            if abs(fx_ux * wux + fx_uy * wuy) < 0.85:
                continue
            u = (back_pt[0] - wx0) * wux + (back_pt[1] - wy0) * wuy
            if u < -1.0 or u > wlen + 1.0:
                continue
            wnx, wny = -wuy, wux
            back_n = (back_pt[0] - wx0) * wnx + (back_pt[1] - wy0) * wny
            dx_wall = wx0 + u * wux - float(fx.x)
            dy_wall = wy0 + u * wuy - float(fx.y)
            dot_to_wall = dx_wall * back_nx + dy_wall * back_ny
            if dot_to_wall <= 0.0:
                continue
            face_gap = abs(back_n) - half_t
            if -1.5 <= face_gap <= max_wall_gap_in and abs(face_gap) < best_gap:
                best_gap = abs(face_gap)
                matched_wall = (wall, (wx0, wy0), (wux, wuy))

        if matched_wall is None:
            continue

        host_wall, origin, uvec = matched_wall
        same_lvl_walls = [
            w for w in wall_list
            if _same_level(flvl, layer_to_level.get(getattr(w, "layer_id", ""), ""))
        ]
        chain = collinear_chain(host_wall, same_lvl_walls)
        chain_ids = {id(w) for w in chain}
        sink_u = (float(fx.x) - origin[0]) * uvec[0] + (float(fx.y) - origin[1]) * uvec[1]
        sink_w = float(getattr(fx, "width", 36.0) or 36.0)

        nearby_windows: list[tuple[float, float]] = []
        for ow, win, ratio, wlvl in win_list:
            if id(ow) not in chain_ids or not _same_level(flvl, wlvl):
                continue
            wc = arc_wall_point(ow, ratio)
            win_u = (wc[0] - origin[0]) * uvec[0] + (wc[1] - origin[1]) * uvec[1]
            win_w = float(getattr(win, "width", 36.0) or 36.0)
            dist = abs(win_u - sink_u)
            if dist <= max(sink_w, 36.0) / 2.0 + win_w / 2.0:
                nearby_windows.append((dist, win_u))

        if not nearby_windows:
            issues.append(
                LayoutIssue(
                    category="Kitchen Sink Window",
                    severity="error",
                    message=(
                        f"Kitchen sink ({sym}) at ({fx.x:.1f}, {fx.y:.1f}) is on an exterior "
                        f"wall without a window centered above it"
                    ),
                    level_id=flvl,
                    location_in=(float(fx.x), float(fx.y)),
                    object_id=str(getattr(fx, "identifier", "") or ""),
                )
            )
            continue

        min_offset, _ = min(nearby_windows, key=lambda item: item[0])
        if min_offset > max_center_offset_in:
            issues.append(
                LayoutIssue(
                    category="Kitchen Sink Window",
                    severity="warning",
                    message=(
                        f"Window above exterior kitchen sink ({sym}) at ({fx.x:.1f}, {fx.y:.1f}) "
                        f"is off-center by {min_offset:.1f}\" (> {max_center_offset_in:g}\")"
                    ),
                    level_id=flvl,
                    location_in=(float(fx.x), float(fx.y)),
                    object_id=str(getattr(fx, "identifier", "") or ""),
                )
            )
    return issues


def kitchen_sink_window_violations(
    fixtures: Iterable[Any],
    walls: Iterable[Any],
    windows: Iterable[tuple[Any, Any, float]],
    layer_to_level: dict[str, str],
    max_wall_gap_in: float = 4.0,
    max_center_offset_in: float = 2.0,
) -> list[str]:
    """Verify kitchen sinks placed on exterior walls have a centered window above them."""
    return [
        i.message
        for i in _collect_kitchen_sink_window_issues(
            fixtures, walls, windows, layer_to_level, max_wall_gap_in, max_center_offset_in
        )
    ]


def _is_circulation_room(room: Any) -> bool:
    rtype = (getattr(room, "room_type", "") or "").lower()
    rname = (getattr(room, "name", "") or "").lower()
    if rtype in _CIRCULATION_ROOM_TYPES:
        return True
    return any(tok in rname for tok in ("hall", "foyer", "corridor"))


def _is_utility_or_closet_room(room: Any) -> bool:
    rtype = (getattr(room, "room_type", "") or "").lower()
    rname = (getattr(room, "name", "") or "").lower()
    if rtype in _UTILITY_CLOSET_ROOM_TYPES:
        return True
    return any(tok in rname for tok in ("closet", "pantry", "laundry"))


def _collect_door_swing_direction_issues(
    doors: Iterable[tuple[Any, Any, float]],
    rooms: Iterable[Any],
    layer_to_level: dict[str, str],
) -> list[LayoutIssue]:
    """Verify hinged doors swing inward into rooms rather than outward or into hallways."""
    issues: list[LayoutIssue] = []
    rooms_by_lvl: dict[str, list[Any]] = {}
    for r in rooms:
        if len(getattr(r, "points", [])) >= 3:
            rlvl = layer_to_level.get(getattr(r, "layer_id", ""), "")
            rooms_by_lvl.setdefault(rlvl, []).append(r)

    for wall, door, ratio in doors:
        if wall is None or getattr(door, "door_type", "") not in _HINGED_SWING_DOORS:
            continue
        spoly = door_swing_polygon(wall, door, ratio)
        if spoly is None:
            continue
        cx, cy = arc_wall_point(wall, ratio)
        sc = _rect_center(spoly)
        vx, vy = sc[0] - cx, sc[1] - cy
        vlen = math.hypot(vx, vy)
        if vlen <= 1e-6:
            continue
        nx, ny = vx / vlen, vy / vlen
        half_t = float(getattr(wall, "width", 4.5) or 4.5) / 2.0
        dlvl = layer_to_level.get(getattr(door, "layer_id", ""), "")
        cand_rooms = [
            r for rlvl, rlist in rooms_by_lvl.items() if _same_level(dlvl, rlvl) for r in rlist
        ]
        if not cand_rooms:
            continue

        swing_probe = (cx + (half_t + 8.0) * nx, cy + (half_t + 8.0) * ny)
        opp_probe = (cx - (half_t + 8.0) * nx, cy - (half_t + 8.0) * ny)

        swing_room = next((r for r in cand_rooms if _point_in_poly(swing_probe, r.points)), None)
        other_room = next((r for r in cand_rooms if _point_in_poly(opp_probe, r.points)), None)

        if swing_room is None and other_room is not None:
            issues.append(
                LayoutIssue(
                    category="Door Swing Direction",
                    severity="error",
                    message=(
                        f"Door {door.door_type} at ({cx:.1f}, {cy:.1f}) swings outward "
                        f"outside '{other_room.name or other_room.room_type}'"
                    ),
                    level_id=dlvl,
                    location_in=(cx, cy),
                    object_id=str(getattr(door, "identifier", "") or ""),
                )
            )
        elif swing_room is not None and other_room is not None and swing_room is not other_room:
            bad_hall_swing = (
                _is_circulation_room(swing_room),
                not _is_circulation_room(other_room),
                not _is_utility_or_closet_room(other_room),
            )
            if all(bad_hall_swing):
                issues.append(
                    LayoutIssue(
                        category="Door Swing Direction",
                        severity="warning",
                        message=(
                            f"Door {door.door_type} at ({cx:.1f}, {cy:.1f}) swings into "
                            f"'{swing_room.name or swing_room.room_type}' instead of into "
                            f"'{other_room.name or other_room.room_type}'"
                        ),
                        level_id=dlvl,
                        location_in=(cx, cy),
                        object_id=str(getattr(door, "identifier", "") or ""),
                    )
                )
    return issues


def door_swing_direction_violations(
    doors: Iterable[tuple[Any, Any, float]],
    rooms: Iterable[Any],
    layer_to_level: dict[str, str],
) -> list[str]:
    """Verify hinged doors swing inward into habitable rooms, not outward or into hallways."""
    return [i.message for i in _collect_door_swing_direction_issues(doors, rooms, layer_to_level)]


def _segments_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    def _ccw(p1: Point, p2: Point, p3: Point) -> float:
        return (p2[0] - p1[0]) * (p3[1] - p1[1]) - (p2[1] - p1[1]) * (p3[0] - p1[0])

    d1 = _ccw(b1, b2, a1)
    d2 = _ccw(b1, b2, a2)
    d3 = _ccw(a1, a2, b1)
    d4 = _ccw(a1, a2, b2)
    return ((d1 > 1e-4 and d2 < -1e-4) or (d1 < -1e-4 and d2 > 1e-4)) and (
        (d3 > 1e-4 and d4 < -1e-4) or (d3 < -1e-4 and d4 > 1e-4)
    )


def _collect_kitchen_island_and_walkway_issues(
    fixtures: Iterable[Any],
    walls: Iterable[Any],
    rooms: Iterable[Any],
    layer_to_level: dict[str, str],
    min_walkway_in: float = 36.0,
    tolerance_in: float = 1.0,
) -> list[LayoutIssue]:
    """Check 36\"+ clearances around kitchen islands, kitchen aisles, and hallways."""
    issues: list[LayoutIssue] = []
    wall_polys = [
        (w, layer_to_level.get(getattr(w, "layer_id", ""), ""), wp)
        for w in walls
        if (wp := _wall_polygon(w)) is not None
    ]
    floor_fx_polys = [
        (fx, layer_to_level.get(getattr(fx, "layer_id", ""), ""), _fixture_polygon(fx))
        for fx in fixtures
        if _is_floor_standing_fixture(fx)
    ]

    # Part A: Kitchen island 36" clearance on all 4 sides
    for fx, flvl, _poly in floor_fx_polys:
        if getattr(fx, "symbol_type", "") != "island_cabinet":
            continue
        hw = float(getattr(fx, "width", 72.0) or 72.0) / 2.0
        hd = float(getattr(fx, "depth", 36.0) or 36.0) / 2.0
        oh = (
            float(getattr(fx, "countertop_overhang", 0.0) or 0.0)
            if getattr(fx, "has_countertop", False)
            else 0.0
        )
        side_rects = [
            ("front", _fixture_local_rect(fx, -hw + 1.0, hd + oh + 0.5, hw - 1.0, hd + oh + min_walkway_in)),
            ("back", _fixture_local_rect(fx, -hw + 1.0, -hd - min_walkway_in, hw - 1.0, -hd - 0.5)),
            ("left", _fixture_local_rect(fx, -hw - min_walkway_in, -hd + 1.0, -hw - 0.5, hd + oh - 1.0)),
            ("right", _fixture_local_rect(fx, hw + 0.5, -hd + 1.0, hw + min_walkway_in, hd + oh - 1.0)),
        ]
        for side_name, rect in side_rects:
            label = f"Kitchen island at ({fx.x:.1f}, {fx.y:.1f}) {side_name} {min_walkway_in:g}\""
            for msg in _check_rect_clear(
                rect, fx, label, flvl, wall_polys, floor_fx_polys, tolerance_in=tolerance_in
            ):
                issues.append(
                    LayoutIssue(
                        category="Kitchen Island & Walkway",
                        severity="error",
                        message=msg,
                        level_id=flvl,
                        location_in=(float(fx.x), float(fx.y)),
                        object_id=str(getattr(fx, "identifier", "") or ""),
                    )
                )

    # Part B: Opposing kitchen work aisles (galley runs / facing walls >= 36")
    kitchen_cats = {"kitchen_cabinet", "kitchen_appliance"}
    seen_aisle_pairs: set[tuple[int, int]] = set()
    for fx, flvl, _poly in floor_fx_polys:
        sym = getattr(fx, "symbol_type", "")
        if getattr(fx, "category", "") not in kitchen_cats:
            continue
        if sym in ("island_cabinet", "corner_base_cabinet"):
            continue
        hw = float(getattr(fx, "width", 24.0) or 24.0) / 2.0
        hd = float(getattr(fx, "depth", 24.0) or 24.0) / 2.0
        oh = (
            float(getattr(fx, "countertop_overhang", 0.0) or 0.0)
            if getattr(fx, "has_countertop", False)
            else 0.0
        )
        front_y = hd + oh
        aisle_rect = _fixture_local_rect(
            fx, -hw + 2.0, front_y + 0.5, hw - 2.0, front_y + min_walkway_in
        )
        rad = math.radians(float(getattr(fx, "rotation", 0.0) or 0.0))
        fx_ux, fx_uy = math.cos(rad), math.sin(rad)
        fx_fnx, fx_fny = -math.sin(rad), math.cos(rad)

        for wall, wlvl, wpoly in wall_polys:
            if not _same_level(flvl, wlvl):
                continue
            wdx = float(wall.end[0]) - float(wall.start[0])
            wdy = float(wall.end[1]) - float(wall.start[1])
            wlen = math.hypot(wdx, wdy)
            if wlen <= 1e-4 or abs((wdx / wlen) * fx_ux + (wdy / wlen) * fx_uy) < 0.7:
                continue
            ov = _sat_overlap(aisle_rect, wpoly)
            if ov is not None and ov[0] > tolerance_in:
                issues.append(
                    LayoutIssue(
                        category="Kitchen Island & Walkway",
                        severity="error",
                        message=(
                            f"Kitchen {sym} at ({fx.x:.1f}, {fx.y:.1f}) aisle clearance "
                            f"(< {min_walkway_in:g}\") blocked by wall {wall.start}->{wall.end} "
                            f"by {ov[0]:.2f}\""
                        ),
                        level_id=flvl,
                        location_in=(float(fx.x), float(fx.y)),
                        object_id=str(getattr(fx, "identifier", "") or ""),
                    )
                )

        for other, olvl, opoly in floor_fx_polys:
            if other is fx or not _same_level(flvl, olvl):
                continue
            if getattr(other, "symbol_type", "") == "island_cabinet":
                continue  # Already checked in Part A
            if getattr(other, "category", "") not in kitchen_cats:
                continue
            orad = math.radians(float(getattr(other, "rotation", 0.0) or 0.0))
            o_fnx, o_fny = -math.sin(orad), math.cos(orad)
            if fx_fnx * o_fnx + fx_fny * o_fny > -0.5:
                continue
            pair_key = (min(id(fx), id(other)), max(id(fx), id(other)))
            if pair_key in seen_aisle_pairs:
                continue
            ov = _sat_overlap(aisle_rect, opoly)
            if ov is not None and ov[0] > tolerance_in:
                seen_aisle_pairs.add(pair_key)
                issues.append(
                    LayoutIssue(
                        category="Kitchen Island & Walkway",
                        severity="error",
                        message=(
                            f"Kitchen work aisle between {sym} at ({fx.x:.1f}, {fx.y:.1f}) and "
                            f"{other.symbol_type} at ({other.x:.1f}, {other.y:.1f}) is "
                            f"under {min_walkway_in:g}\" by {ov[0]:.2f}\""
                        ),
                        level_id=flvl,
                        location_in=(float(fx.x), float(fx.y)),
                        object_id=str(getattr(fx, "identifier", "") or ""),
                    )
                )

    # Part C: Hallways and circulation rooms >= 36" clear width
    for room in rooms:
        pts = getattr(room, "points", [])
        if len(pts) < 3:
            continue
        rtype = (getattr(room, "room_type", "") or "").lower()
        rname = (getattr(room, "name", "") or "").lower()
        if rtype not in ("hallway", "corridor") and "hall" not in rname:
            continue
        rlvl = layer_to_level.get(getattr(room, "layer_id", ""), "")
        lvl_walls: list[tuple[Any, Point, Point, float, float]] = []
        for wall, wlvl, _wpoly in wall_polys:
            if not _same_level(rlvl, wlvl):
                continue
            wx0, wy0 = float(wall.start[0]), float(wall.start[1])
            wx1, wy1 = float(wall.end[0]), float(wall.end[1])
            wlen = math.hypot(wx1 - wx0, wy1 - wy0)
            if wlen < 12.0:
                continue
            lvl_walls.append((wall, (wx0, wy0), (wx1, wy1), wlen, float(wall.width or 4.5)))

        # Find parallel wall pairs facing across the hallway
        border_walls: list[tuple[Any, Point, Point, Point, float, float]] = []
        for wall, p0, p1, wlen, wthick in lvl_walls:
            ux, uy = (p1[0] - p0[0]) / wlen, (p1[1] - p0[1]) / wlen
            nx, ny = -uy, ux
            mid = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
            d_probe = wthick / 2.0 + 4.0
            in_pos = _point_in_poly((mid[0] + d_probe * nx, mid[1] + d_probe * ny), pts)
            in_neg = _point_in_poly((mid[0] - d_probe * nx, mid[1] - d_probe * ny), pts)
            if in_pos or in_neg:
                border_walls.append((wall, p0, p1, (ux, uy), wlen, wthick))

        flagged_hall = False
        for i in range(len(border_walls)):
            if flagged_hall:
                break
            w1, p10, p11, u1, _l1, t1 = border_walls[i]
            m1 = ((p10[0] + p11[0]) / 2.0, (p10[1] + p11[1]) / 2.0)
            for j in range(i + 1, len(border_walls)):
                w2, p20, p21, u2, _l2, t2 = border_walls[j]
                if abs(u1[0] * u2[0] + u1[1] * u2[1]) < 0.95:
                    continue
                # Check overlap along u1
                a_lo = min(0.0, (p11[0] - p10[0]) * u1[0] + (p11[1] - p10[1]) * u1[1])
                a_hi = max(0.0, (p11[0] - p10[0]) * u1[0] + (p11[1] - p10[1]) * u1[1])
                b0 = (p20[0] - p10[0]) * u1[0] + (p20[1] - p10[1]) * u1[1]
                b1 = (p21[0] - p10[0]) * u1[0] + (p21[1] - p10[1]) * u1[1]
                b_lo, b_hi = min(b0, b1), max(b0, b1)
                span_lo = max(a_lo, b_lo)
                span_hi = min(a_hi, b_hi)
                if span_hi - span_lo < 18.0:
                    continue
                perp_dist = abs((p20[0] - p10[0]) * (-u1[1]) + (p20[1] - p10[1]) * u1[0])
                clear_w = perp_dist - (t1 + t2) / 2.0
                if clear_w <= 2.0:
                    continue
                if clear_w < min_walkway_in - tolerance_in:
                    m2 = ((p20[0] + p21[0]) / 2.0, (p20[1] + p21[1]) / 2.0)
                    mid_span = ((m1[0] + m2[0]) / 2.0, (m1[1] + m2[1]) / 2.0)
                    if not _point_in_poly(mid_span, pts):
                        continue
                    blocked_mid = any(
                        _segments_intersect(m1, m2, op0, op1)
                        for ow, op0, op1, _, _ in lvl_walls
                        if ow is not w1 and ow is not w2
                    )
                    if blocked_mid:
                        continue
                    issues.append(
                        LayoutIssue(
                            category="Kitchen Island & Walkway",
                            severity="error",
                            message=(
                                f"High-traffic hallway '{room.name or 'Hallway'}' clear width is "
                                f"{clear_w:.1f}\" (< {min_walkway_in:g}\" required)"
                            ),
                            level_id=rlvl,
                            location_in=mid_span,
                            object_id=str(getattr(room, "identifier", "") or ""),
                        )
                    )
                    flagged_hall = True
                    break

    return issues


def kitchen_island_and_walkway_violations(
    fixtures: Iterable[Any],
    walls: Iterable[Any],
    rooms: Iterable[Any],
    layer_to_level: dict[str, str],
    min_walkway_in: float = 36.0,
    tolerance_in: float = 1.0,
) -> list[str]:
    """Verify 36\"+ walking clearances around kitchen islands, kitchen aisles, and hallways."""
    return [
        i.message
        for i in _collect_kitchen_island_and_walkway_issues(
            fixtures, walls, rooms, layer_to_level, min_walkway_in, tolerance_in
        )
    ]


def _collect_room_access_issues(
    rooms: Iterable[Any],
    walls: Iterable[Any],
    doors: Iterable[tuple[Any, Any, float]],
    stairs: Iterable[Any],
    layer_to_level: dict[str, str],
    min_open_gap_in: float = 30.0,
) -> list[LayoutIssue]:
    """Verify every room has at least one door, opening, open passage, or stair landing."""
    issues: list[LayoutIssue] = []
    wall_polys_by_lvl: dict[str, list[tuple[Any, list[Point]]]] = {}
    for w in walls:
        wp = _wall_polygon(w)
        if wp is not None:
            wlvl = layer_to_level.get(getattr(w, "layer_id", ""), "")
            wall_polys_by_lvl.setdefault(wlvl, []).append((w, wp))

    room_list: list[tuple[Any, str]] = [
        (r, layer_to_level.get(getattr(r, "layer_id", ""), ""))
        for r in rooms
        if len(getattr(r, "points", [])) >= 3
    ]

    door_probes: list[tuple[str, Point, Point]] = []
    for wall, door, ratio in doors:
        if wall is None:
            continue
        cx, cy = arc_wall_point(wall, ratio)
        tx, ty = arc_wall_tangent(wall, ratio)
        tlen = math.hypot(tx, ty)
        if tlen <= 1e-6:
            continue
        nx, ny = -ty / tlen, tx / tlen
        half_t = float(getattr(wall, "width", 4.5) or 4.5) / 2.0
        dlvl = layer_to_level.get(getattr(door, "layer_id", ""), "")
        door_probes.append((
            dlvl,
            (cx + (half_t + 6.0) * nx, cy + (half_t + 6.0) * ny),
            (cx - (half_t + 6.0) * nx, cy - (half_t + 6.0) * ny),
        ))

    stair_probes: list[tuple[str, Point]] = []
    for st in stairs:
        s_lvl = getattr(st, "start_level_id", "") or layer_to_level.get(
            getattr(st, "layer_id", ""), ""
        )
        e_lvl = getattr(st, "end_level_id", "") or s_lvl
        brect, trect, _, _ = stair_landing_rects(st, 36.0)
        stair_probes.append((s_lvl, _rect_center(brect)))
        stair_probes.append((e_lvl, _rect_center(trect)))

    for room, rlvl in room_list:
        pts = room.points
        has_door = any(
            _same_level(rlvl, dlvl) and (_point_in_poly(p1, pts) or _point_in_poly(p2, pts))
            for dlvl, p1, p2 in door_probes
        )
        if has_door:
            continue

        has_stair = any(
            _same_level(rlvl, slvl) and _point_in_poly(sc, pts)
            for slvl, sc in stair_probes
        )
        if has_stair:
            continue

        # Check for open-concept passage (wall-free gap >= min_open_gap_in into another room)
        same_lvl_walls = [
            (w, wp)
            for wlvl, wlist in wall_polys_by_lvl.items()
            if _same_level(rlvl, wlvl)
            for w, wp in wlist
        ]
        other_rooms = [
            oroom for oroom, olvl in room_list if oroom is not room and _same_level(rlvl, olvl)
        ]
        has_open_passage = False
        npts = len(pts)
        for idx in range(npts):
            if has_open_passage:
                break
            a = pts[idx]
            b = pts[(idx + 1) % npts]
            ex, ey = b[0] - a[0], b[1] - a[1]
            elen = math.hypot(ex, ey)
            if elen < min_open_gap_in:
                continue
            ux, uy = ex / elen, ey / elen
            nx, ny = -uy, ux
            mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            if _point_in_poly((mid[0] + 2.0 * nx, mid[1] + 2.0 * ny), pts):
                out_nx, out_ny = -nx, -ny
            else:
                out_nx, out_ny = nx, ny

            blocked: list[tuple[float, float]] = []
            for _w, wp in same_lvl_walls:
                n_vals = [(p[0] - a[0]) * out_nx + (p[1] - a[1]) * out_ny for p in wp]
                if max(n_vals) < -6.0 or min(n_vals) > 6.0:
                    continue
                u_vals = [(p[0] - a[0]) * ux + (p[1] - a[1]) * uy for p in wp]
                s0 = max(0.0, min(u_vals))
                s1 = min(elen, max(u_vals))
                if s1 - s0 > 0.5:
                    blocked.append((s0, s1))
            blocked.sort()
            merged: list[tuple[float, float]] = []
            for s0, s1 in blocked:
                if merged and s0 <= merged[-1][1] + 0.5:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], s1))
                else:
                    merged.append((s0, s1))

            gaps: list[tuple[float, float]] = []
            cur = 0.0
            for s0, s1 in merged:
                if s0 - cur >= min_open_gap_in:
                    gaps.append((cur, s0))
                cur = max(cur, s1)
            if elen - cur >= min_open_gap_in:
                gaps.append((cur, elen))

            for g0, g1 in gaps:
                gm = (g0 + g1) / 2.0
                probe_out = (a[0] + gm * ux + 8.0 * out_nx, a[1] + gm * uy + 8.0 * out_ny)
                if any(_point_in_poly(probe_out, oroom.points) for oroom in other_rooms):
                    has_open_passage = True
                    break

        if not has_open_passage:
            rc = _rect_center(pts)
            rlabel = getattr(room, "name", "") or getattr(room, "room_type", "") or "Unnamed Room"
            issues.append(
                LayoutIssue(
                    category="Room Access",
                    severity="error",
                    message=f"Room '{rlabel}' has no door, opening, or open passage for access",
                    level_id=rlvl,
                    location_in=rc,
                    object_id=str(getattr(room, "identifier", "") or ""),
                )
            )
    return issues


def room_access_violations(
    rooms: Iterable[Any],
    walls: Iterable[Any],
    doors: Iterable[tuple[Any, Any, float]],
    stairs: Iterable[Any],
    layer_to_level: dict[str, str],
    min_open_gap_in: float = 30.0,
) -> list[str]:
    """Verify every room has at least one door, opening, open passage, or stair landing."""
    return [
        i.message
        for i in _collect_room_access_issues(
            rooms, walls, doors, stairs, layer_to_level, min_open_gap_in
        )
    ]


def validate_project_layout_detailed(canvas: Any) -> list[LayoutIssue]:
    """Run all architectural layout checks on ``canvas`` and return structured issues."""
    layer_to_level = {
        getattr(layer, "id", ""): getattr(layer, "level_id", "")
        for layer in getattr(canvas, "layers", [])
    }
    walls: list[Any] = []
    seen_ids: set[int] = set()
    for ws in getattr(canvas, "wall_sets", []):
        for w in ws:
            if id(w) not in seen_ids:
                seen_ids.add(id(w))
                walls.append(w)
    for w in getattr(canvas, "walls", []):
        if id(w) not in seen_ids:
            seen_ids.add(id(w))
            walls.append(w)

    fixtures = list(getattr(canvas, "fixtures", []))
    doors = list(getattr(canvas, "doors", []))
    windows = list(getattr(canvas, "windows", []))
    rooms = list(getattr(canvas, "rooms", []))
    stairs = list(getattr(canvas, "stairs", []))
    levels = list(getattr(canvas, "levels", []))

    issues: list[LayoutIssue] = []

    def _wrap(category: str, messages: list[str], severity: str = "error") -> None:
        for msg in messages:
            issues.append(LayoutIssue(category=category, severity=severity, message=msg))

    _wrap("Wall Penetration", fixture_wall_violations(fixtures, walls, layer_to_level))
    _wrap("Door Swing vs Fixture", fixture_door_violations(fixtures, doors, layer_to_level))
    issues.extend(
        _collect_opening_ingress_egress_issues(fixtures, doors, walls, layer_to_level)
    )
    _wrap("Pocket Door", pocket_door_violations(doors, walls, windows, layer_to_level))
    _wrap(
        "Bathroom Clearance",
        bathroom_clearance_violations(
            doors, fixtures, rooms, walls, layer_to_level, check_fixtures=False
        ),
    )
    _wrap("Sink & Vanity", sink_and_vanity_clearance_violations(fixtures, walls, layer_to_level))
    _wrap("Bathtub Plumbing", bathtub_drain_wall_violations(fixtures, walls, layer_to_level))
    _wrap("Laundry Clearance", laundry_appliance_violations(fixtures, doors, walls, layer_to_level))
    issues.extend(
        _collect_kitchen_sink_window_issues(fixtures, walls, windows, layer_to_level)
    )
    issues.extend(_collect_door_swing_direction_issues(doors, rooms, layer_to_level))
    issues.extend(
        _collect_kitchen_island_and_walkway_issues(fixtures, walls, rooms, layer_to_level)
    )
    issues.extend(_collect_room_access_issues(rooms, walls, doors, stairs, layer_to_level))
    _wrap(
        "Stairs & Landings",
        stair_landing_and_access_violations(
            stairs, walls, rooms, doors, fixtures, levels, layer_to_level
        ),
    )
    return issues


def validate_project_layout(canvas: Any) -> list[str]:
    """Run all architectural layout checks on a canvas or headless project."""
    return [issue.message for issue in validate_project_layout_detailed(canvas)]
