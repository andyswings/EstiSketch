"""Headless helpers to merge two collinear walls and to re-home openings on wall split/merge.

An opening (door/window) belongs to exactly one wall, so a window centred on a wall cannot
survive a split at that wall's midpoint. Merging the two halves back into one wall lets the
user place openings across the former junction.

All coordinates are model inches. Openings are ``(wall, opening, ratio)`` tuples where
``ratio`` in ``[0, 1]`` runs from ``wall.start`` to ``wall.end``.
"""
from __future__ import annotations

import math
from typing import Any

Point = tuple[float, float]
Opening = tuple[Any, Any, float]

JOIN_TOLERANCE_IN = 0.5
COLLINEAR_SIN_TOLERANCE = 1e-3


def _length(wall: Any) -> float:
    return math.hypot(wall.end[0] - wall.start[0], wall.end[1] - wall.start[1])


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _orient_pair(first: Any, second: Any) -> tuple[Any, Any] | None:
    """Return ``(a, b)`` so that ``a.end`` meets ``b.start``, or None if not joined."""
    if _dist(first.end, second.start) <= JOIN_TOLERANCE_IN:
        return first, second
    if _dist(second.end, first.start) <= JOIN_TOLERANCE_IN:
        return second, first
    return None


def can_merge_walls(first: Any, second: Any) -> bool:
    """True if two walls are straight, end-to-end, collinear and the same thickness."""
    if getattr(first, "is_curved", False) or getattr(second, "is_curved", False):
        return False
    if abs(float(first.width) - float(second.width)) > 1e-6:
        return False
    if _length(first) < 1e-6 or _length(second) < 1e-6:
        return False
    pair = _orient_pair(first, second)
    if pair is None:
        # Walls drawn in opposite directions share start/start or end/end.
        return False
    a, b = pair
    ax, ay = a.end[0] - a.start[0], a.end[1] - a.start[1]
    bx, by = b.end[0] - b.start[0], b.end[1] - b.start[1]
    cross = (ax * by - ay * bx) / (_length(a) * _length(b))
    dot = ax * bx + ay * by
    return abs(cross) < COLLINEAR_SIN_TOLERANCE and dot > 0.0


def merge_walls(
    first: Any,
    second: Any,
    wall_sets: list[list[Any]],
    doors: list[Opening],
    windows: list[Opening],
) -> Any:
    """Merge ``second`` into ``first`` (kept as the surviving wall object).

    The surviving wall spans both walls, openings on either wall keep their physical
    position, and ``second`` is removed from ``wall_sets``.

    Args:
        first: One wall of the pair; its identifier and attributes survive.
        second: The adjacent collinear wall to absorb.
        wall_sets: Canvas wall sets, modified in place.
        doors: Canvas door tuples, modified in place.
        windows: Canvas window tuples, modified in place.

    Returns:
        The surviving merged wall.

    Raises:
        ValueError: If the walls cannot be merged (see ``can_merge_walls``).
    """
    if not can_merge_walls(first, second):
        raise ValueError("Walls must be straight, collinear, touching and equally thick.")
    lead, trail = _orient_pair(first, second)  # type: ignore[misc]

    new_start, new_end = lead.start, trail.end
    new_len = _dist(new_start, new_end)
    start_h, end_h = lead.height, getattr(trail, "height_at_end", trail.height)

    def _map_ratio(wall: Any, ratio: float) -> float:
        offset_from_lead = (
            ratio * _length(wall) if wall is lead else _length(lead) + ratio * _length(wall)
        )
        return offset_from_lead / new_len

    # Compute new ratios with the original geometry before mutating the wall.
    remapped: dict[int, list[tuple[Opening, float]]] = {}
    for coll in (doors, windows):
        for item in coll:
            if item[0] is first or item[0] is second:
                remapped.setdefault(id(coll), []).append((item, _map_ratio(item[0], item[2])))

    first.start, first.end = new_start, new_end
    first.height, first.height_at_end = start_h, end_h

    for coll in (doors, windows):
        for item, new_ratio in remapped.get(id(coll), []):
            coll[coll.index(item)] = (first, item[1], new_ratio)

    for wall_set in wall_sets:
        if second in wall_set:
            wall_set.remove(second)
    return first


def reassign_openings_after_split(
    original: Any,
    first_half: Any,
    second_half: Any,
    doors: list[Opening],
    windows: list[Opening],
) -> None:
    """Move openings from a split ``original`` wall onto whichever half holds their centre.

    ``first_half`` runs ``original.start`` to the midpoint and ``second_half`` runs from the
    midpoint to ``original.end``; both are straight halves of equal length.
    """
    for coll in (doors, windows):
        for idx, (wall, opening, ratio) in enumerate(list(coll)):
            if wall is not original:
                continue
            if ratio < 0.5:
                coll[idx] = (first_half, opening, ratio * 2.0)
            else:
                coll[idx] = (second_half, opening, (ratio - 0.5) * 2.0)
