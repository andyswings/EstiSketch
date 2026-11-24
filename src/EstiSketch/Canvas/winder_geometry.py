"""Pure geometry for winder (pie-shaped) stair treads. No GTK/Cairo dependencies."""
import math
from typing import List, Tuple

Point = Tuple[float, float]

MAX_WINDERS = 5


def winder_treads(width: float, count: int, turn: str = "left") -> List[List[Point]]:
    """Return ``count`` wedge polygons that tile a ``width`` x ``width`` turn square.

    Coordinates are in the stair's local frame relative to the square's entry
    edge: ``u`` runs along the first flight's direction (0..width) and ``v``
    runs across the stair (0..width, ``v=0`` is the stair's left edge).

    The wedges fan around the inner corner of the turn in equal angle steps and
    are ordered from the entry edge (first winder) to the exit edge (last).

    Args:
        width: Stair width in inches (turn square is width x width).
        count: Number of winder treads (>= 1).
        turn: ``"left"`` or ``"right"``.

    Returns:
        List of polygons, each a list of (u, v) vertices.
    """
    if count < 1:
        return []

    # Pivot at the inner corner (left turn: u=0, v=0). Angle phi is measured
    # from the exit edge (+u axis, phi=0) to the entry edge (+v axis, phi=90deg).
    def boundary_point(phi: float) -> Point:
        if phi <= math.pi / 4 + 1e-12:
            return (width, width * math.tan(phi))
        return (width / math.tan(phi), width)

    polys: List[List[Point]] = []
    for i in range(count):
        phi_hi = (math.pi / 2) * (1 - i / count)        # entry side of this wedge
        phi_lo = (math.pi / 2) * (1 - (i + 1) / count)  # exit side of this wedge
        pts: List[Point] = [(0.0, 0.0), boundary_point(phi_hi)]
        if phi_lo < math.pi / 4 < phi_hi:
            pts.append((width, width))  # wedge spans the outer corner
        pts.append(boundary_point(phi_lo))
        polys.append(pts)

    if turn == "right":
        polys = [[(u, width - v) for (u, v) in poly] for poly in polys]
    return polys


def polygon_area(poly: List[Point]) -> float:
    """Absolute area of a simple polygon (shoelace formula)."""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def polygon_centroid(poly: List[Point]) -> Point:
    """Simple vertex-average centroid, adequate for placing step numbers."""
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))


def l_stair_layout(total_steps: int, steps_before_landing: int, tread_depth: float,
                   landing_depth: float, width: float, winder_count: int = 0) -> dict:
    """Shared layout math for L-shaped stairs (used by rendering and hit-testing).

    Without winders this reproduces the original landing-based layout. With
    winders, ``winder_count`` steps are taken out of ``total_steps`` for the
    turn, the flat landing becomes a ``width`` x ``width`` winder square, and
    each flight's run is ``steps * tread_depth``.

    Returns:
        dict with steps_before, steps_after, run_before, run_after,
        landing_depth, winder_count (clamped).
    """
    winders = int(winder_count or 0)
    winders = max(0, min(winders, MAX_WINDERS, max(total_steps - 2, 0)))
    flight_total = total_steps - winders

    if 0 < steps_before_landing < flight_total:
        steps_before = steps_before_landing
    else:
        steps_before = flight_total // 2
    steps_after = flight_total - steps_before

    if winders:
        run_before = steps_before * tread_depth
        run_after = steps_after * tread_depth
        landing_depth = width
    else:
        run_before = (steps_before - 1) * tread_depth if steps_before > 0 else 0
        run_after = (steps_after - 1) * tread_depth if steps_after > 0 else 0

    return {
        "steps_before": steps_before,
        "steps_after": steps_after,
        "run_before": run_before,
        "run_after": run_after,
        "landing_depth": landing_depth,
        "winder_count": winders,
    }
