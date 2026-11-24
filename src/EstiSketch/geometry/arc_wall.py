"""Pure-Python geometric helpers for curved (arc) walls.

Kept free of GTK/Cairo so snapping, projection, intersections, and door/window
cutouts can be unit-tested headlessly.
"""
import math
from typing import Dict, List, Optional, Tuple

Point = Tuple[float, float]


def is_curved_wall(wall) -> bool:
    """Return True if ``wall`` is a valid circular-arc wall."""
    return bool(
        wall is not None
        and getattr(wall, "is_curved", False)
        and getattr(wall, "arc_center", None) is not None
        and (getattr(wall, "arc_radius", None) or 0.0) > 1e-6
    )


def normalize_signed_angle(delta: float) -> float:
    """Wrap an angular span ``delta`` (radians) into ``(-pi, pi]``."""
    while delta > math.pi:
        delta -= 2.0 * math.pi
    while delta <= -math.pi:
        delta += 2.0 * math.pi
    return delta


def arc_wall_params(wall) -> Optional[Tuple[float, float, float, float, float]]:
    """Return ``(cx, cy, radius, start_angle, angle_diff)`` for a curved wall."""
    if not is_curved_wall(wall):
        return None
    cx, cy = wall.arc_center
    radius = float(wall.arc_radius)
    start_angle = math.atan2(wall.start[1] - cy, wall.start[0] - cx)
    end_angle = math.atan2(wall.end[1] - cy, wall.end[0] - cx)
    angle_diff = normalize_signed_angle(end_angle - start_angle)
    return (cx, cy, radius, start_angle, angle_diff)


def angle_in_arc(angle: float, start_angle: float, angle_diff: float, eps: float = 1e-7) -> bool:
    """Return True if ``angle`` lies along the directed arc from ``start_angle`` spanning ``angle_diff``."""
    two_pi = 2.0 * math.pi
    if angle_diff >= 0.0:
        rel = (angle - start_angle) % two_pi
        return rel <= angle_diff + eps or rel >= two_pi - eps
    rel = (start_angle - angle) % two_pi
    return rel <= (-angle_diff) + eps or rel >= two_pi - eps


def arc_wall_length(wall) -> float:
    """Return true arc length (inches) for curved walls, or Euclidean length for straight walls."""
    params = arc_wall_params(wall)
    if params is not None:
        _, _, radius, _, angle_diff = params
        return abs(angle_diff) * radius
    return math.hypot(wall.end[0] - wall.start[0], wall.end[1] - wall.start[1])


def arc_wall_point(wall, ratio: float, radial_offset: float = 0.0) -> Point:
    """Return point ``(x, y)`` along a wall at ``ratio`` with optional radial offset."""
    params = arc_wall_params(wall)
    if params is not None:
        cx, cy, radius, start_angle, angle_diff = params
        r_eff = max(1e-3, radius + radial_offset)
        theta = start_angle + ratio * angle_diff
        return (cx + r_eff * math.cos(theta), cy + r_eff * math.sin(theta))
    a, b = wall.start, wall.end
    px = a[0] + ratio * (b[0] - a[0])
    py = a[1] + ratio * (b[1] - a[1])
    if abs(radial_offset) > 1e-9:
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length > 1e-9:
            nx, ny = -dy / length, dx / length
            return (px + nx * radial_offset, py + ny * radial_offset)
    return (px, py)


def arc_wall_tangent(wall, ratio: float) -> Point:
    """Return unit tangent direction vector ``(dx, dy)`` at ``ratio`` along the wall."""
    params = arc_wall_params(wall)
    if params is not None:
        _, _, _, start_angle, angle_diff = params
        theta = start_angle + ratio * angle_diff
        tangent_angle = theta + math.pi / 2.0 if angle_diff >= 0.0 else theta - math.pi / 2.0
        return (math.cos(tangent_angle), math.sin(tangent_angle))
    dx = wall.end[0] - wall.start[0]
    dy = wall.end[1] - wall.start[1]
    length = math.hypot(dx, dy)
    if length > 1e-9:
        return (dx / length, dy / length)
    return (1.0, 0.0)


def arc_wall_left_normal(wall, ratio: float) -> Point:
    """Return unit left-hand normal ``(-ty, tx)`` at ``ratio`` along the wall."""
    tx, ty = arc_wall_tangent(wall, ratio)
    return (-ty, tx)


def arc_wall_face_radii(wall) -> Optional[Tuple[float, float]]:
    """Return ``(r_left, r_right)`` concentric radii for left/right faces of a curved wall."""
    params = arc_wall_params(wall)
    if params is None:
        return None
    _, _, radius, _, angle_diff = params
    hw = float(getattr(wall, "width", 5.5) or 5.5) / 2.0
    # For CCW arc (angle_diff >= 0), tangent is +90 deg so left normal points inward (-radial).
    # For CW arc (angle_diff < 0), tangent is -90 deg so left normal points outward (+radial).
    radial_sign_for_left = -1.0 if angle_diff >= 0.0 else 1.0
    r_left = max(1e-3, radius + radial_sign_for_left * hw)
    r_right = max(1e-3, radius - radial_sign_for_left * hw)
    return (r_left, r_right)


def arc_wall_project(
    wall,
    point: Point,
    radial_offset: float = 0.0,
) -> Tuple[float, float, Point]:
    """Project ``point`` onto a curved wall arc (optionally shifted by ``radial_offset``).

    Returns ``(ratio, distance, closest_point)``.
    """
    params = arc_wall_params(wall)
    if params is None:
        x1, y1 = wall.start
        x2, y2 = wall.end
        dx, dy = x2 - x1, y2 - y1
        len_sq = dx * dx + dy * dy
        if len_sq <= 1e-12:
            return 0.5, math.hypot(point[0] - x1, point[1] - y1), (x1, y1)
        t = max(0.0, min(1.0, ((point[0] - x1) * dx + (point[1] - y1) * dy) / len_sq))
        cx_pt = (x1 + t * dx, y1 + t * dy)
        return t, math.hypot(point[0] - cx_pt[0], point[1] - cx_pt[1]), cx_pt

    cx, cy, radius, start_angle, angle_diff = params
    r_eff = max(1e-3, radius + radial_offset)
    px, py = point
    dx, dy = px - cx, py - cy
    pt_dist = math.hypot(dx, dy)
    if pt_dist > 1e-9:
        ang = math.atan2(dy, dx)
        if abs(angle_diff) > 1e-9 and angle_in_arc(ang, start_angle, angle_diff):
            two_pi = 2.0 * math.pi
            if angle_diff >= 0.0:
                rel = (ang - start_angle) % two_pi
                if rel > two_pi - 1e-6:
                    rel = 0.0
                ratio = max(0.0, min(1.0, rel / angle_diff))
            else:
                rel = (start_angle - ang) % two_pi
                if rel > two_pi - 1e-6:
                    rel = 0.0
                ratio = max(0.0, min(1.0, rel / (-angle_diff)))
            closest = (cx + r_eff * math.cos(ang), cy + r_eff * math.sin(ang))
            return ratio, abs(pt_dist - r_eff), closest

    p0 = arc_wall_point(wall, 0.0, radial_offset=radial_offset)
    p1 = arc_wall_point(wall, 1.0, radial_offset=radial_offset)
    d0 = math.hypot(px - p0[0], py - p0[1])
    d1 = math.hypot(px - p1[0], py - p1[1])
    if d0 <= d1:
        return 0.0, d0, p0
    return 1.0, d1, p1


def clamp_opening_ratio(
    wall,
    ratio: float,
    opening_width: Optional[float],
) -> float:
    """Clamp opening placement ``ratio`` so ``opening_width`` stays within wall length."""
    wall_len = arc_wall_length(wall)
    lo, hi = 0.0, 1.0
    if opening_width and wall_len > 1e-6 and opening_width < wall_len:
        half = (opening_width / 2.0) / wall_len
        lo, hi = half, 1.0 - half
    return max(lo, min(hi, ratio))


def tangent_points_from_point(
    base: Point,
    wall,
    include_faces: bool = True,
) -> List[Tuple[Point, str]]:
    """Return exact tangent points from ``base`` onto curved ``wall`` arc(s).

    Each item is ``((tx, ty), kind)`` where ``kind`` is ``"centerline"``,
    ``"outer_face"``, or ``"inner_face"``.
    """
    params = arc_wall_params(wall)
    if params is None:
        return []
    cx, cy, radius, start_angle, angle_diff = params
    bx, by = base
    d = math.hypot(bx - cx, by - cy)
    alpha = math.atan2(by - cy, bx - cx)

    radii_specs = [(radius, "centerline")]
    if include_faces:
        hw = float(getattr(wall, "width", 0.0) or 0.0) / 2.0
        if hw > 1e-6:
            radii_specs.append((radius + hw, "outer_face"))
            if radius - hw > 1e-3:
                radii_specs.append((radius - hw, "inner_face"))

    results: List[Tuple[Point, str]] = []
    for r_eff, kind in radii_specs:
        if d <= r_eff + 1e-4:
            continue
        cos_beta = max(-1.0, min(1.0, r_eff / d))
        beta = math.acos(cos_beta)
        for sign in (1.0, -1.0):
            theta = alpha + sign * beta
            if angle_in_arc(theta, start_angle, angle_diff):
                pt = (cx + r_eff * math.cos(theta), cy + r_eff * math.sin(theta))
                results.append((pt, kind))
    return results


def tangent_continuation_snap(
    cursor: Point,
    base: Point,
    wall,
    threshold: float,
) -> Optional[Tuple[Point, Tuple[Point, Point]]]:
    """Snap ``cursor`` onto the tangent ray extending from ``base`` if ``base`` is an endpoint of ``wall``."""
    if not is_curved_wall(wall):
        return None
    endpoint_ratio = None
    if math.hypot(base[0] - wall.start[0], base[1] - wall.start[1]) <= 1e-3:
        endpoint_ratio = 0.0
    elif math.hypot(base[0] - wall.end[0], base[1] - wall.end[1]) <= 1e-3:
        endpoint_ratio = 1.0
    if endpoint_ratio is None:
        return None

    tx, ty = arc_wall_tangent(wall, endpoint_ratio)
    vx, vy = cursor[0] - base[0], cursor[1] - base[1]
    proj = vx * tx + vy * ty
    if abs(proj) <= 1e-3:
        return None
    perp_dist = abs(vx * (-ty) + vy * tx)
    if perp_dist >= threshold:
        return None
    snapped = (base[0] + proj * tx, base[1] + proj * ty)
    return snapped, (base, snapped)


def line_arc_intersections(p1: Point, p2: Point, wall) -> List[Point]:
    """Return intersection points between finite segment ``p1->p2`` and curved ``wall``."""
    params = arc_wall_params(wall)
    if params is None:
        return []
    cx, cy, radius, start_angle, angle_diff = params
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    fx, fy = p1[0] - cx, p1[1] - cy
    a = dx * dx + dy * dy
    if a <= 1e-12:
        return []
    b = 2.0 * (fx * dx + fy * dy)
    c = (fx * fx + fy * fy) - radius * radius
    disc = b * b - 4.0 * a * c
    if disc < -1e-9:
        return []
    disc = max(0.0, disc)
    sqrt_disc = math.sqrt(disc)
    ts = [(-b - sqrt_disc) / (2.0 * a)]
    if sqrt_disc > 1e-9:
        ts.append((-b + sqrt_disc) / (2.0 * a))

    out: List[Point] = []
    for t in ts:
        if -1e-7 <= t <= 1.0 + 1e-7:
            t_clamped = max(0.0, min(1.0, t))
            pt = (p1[0] + t_clamped * dx, p1[1] + t_clamped * dy)
            ang = math.atan2(pt[1] - cy, pt[0] - cx)
            if angle_in_arc(ang, start_angle, angle_diff):
                out.append(pt)
    return out


def arc_arc_intersections(wall1, wall2) -> List[Point]:
    """Return intersection points between two curved walls."""
    p1 = arc_wall_params(wall1)
    p2 = arc_wall_params(wall2)
    if p1 is None or p2 is None:
        return []
    x0, y0, r0, s0, d0 = p1
    x1, y1, r1, s1, d1 = p2
    dx, dy = x1 - x0, y1 - y0
    d = math.hypot(dx, dy)
    if d <= 1e-9 or d > r0 + r1 + 1e-7 or d < abs(r0 - r1) - 1e-7:
        return []
    a = (r0 * r0 - r1 * r1 + d * d) / (2.0 * d)
    h_sq = max(0.0, r0 * r0 - a * a)
    h = math.sqrt(h_sq)
    xm = x0 + a * dx / d
    ym = y0 + a * dy / d
    candidates = [(xm + h * (-dy / d), ym + h * (dx / d))]
    if h > 1e-9:
        candidates.append((xm - h * (-dy / d), ym - h * (dx / d)))

    out: List[Point] = []
    for pt in candidates:
        ang0 = math.atan2(pt[1] - y0, pt[0] - x0)
        ang1 = math.atan2(pt[1] - y1, pt[0] - x1)
        if angle_in_arc(ang0, s0, d0) and angle_in_arc(ang1, s1, d1):
            out.append(pt)
    return out


def arc_opening_cutout(
    wall,
    ratio: float,
    opening_width: float,
) -> Optional[Dict[str, object]]:
    """Compute annular sector & chord jamb geometry for an opening in a curved wall.

    Matching chord distance ``hypot(jamb_end - jamb_start) == opening_width``
    ensures straight door leaves and window frames seat flush against the radial
    jamb end-caps without leaving curved black wall slivers.
    """
    params = arc_wall_params(wall)
    if params is None or opening_width <= 0.0:
        return None
    cx, cy, radius, start_angle, angle_diff = params
    if abs(angle_diff) <= 1e-7 or radius <= 1e-6:
        return None

    half_span = math.asin(min(0.999, opening_width / (2.0 * radius)))
    half_span = min(half_span, abs(angle_diff) / 2.0)

    theta_center = start_angle + ratio * angle_diff
    sign = 1.0 if angle_diff >= 0.0 else -1.0
    theta_start = theta_center - sign * half_span
    theta_end = theta_center + sign * half_span
    theta_lo = min(theta_start, theta_end)
    theta_hi = max(theta_start, theta_end)

    jamb_start = (cx + radius * math.cos(theta_start), cy + radius * math.sin(theta_start))
    jamb_end = (cx + radius * math.cos(theta_end), cy + radius * math.sin(theta_end))
    return {
        "cx": cx,
        "cy": cy,
        "radius": radius,
        "theta_lo": theta_lo,
        "theta_hi": theta_hi,
        "theta_start": theta_start,
        "theta_end": theta_end,
        "jamb_start": jamb_start,
        "jamb_end": jamb_end,
        "half_span": half_span,
    }
