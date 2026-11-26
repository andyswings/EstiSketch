"""Place doors/windows anywhere along a run of collinear walls, even across a split.

An opening is stored as ``(host_wall, opening, ratio)`` and is drawn from the host wall's
own line, so its ``ratio`` may place the jambs past the host's ends: the 2D renderer simply
extends along the same line and the white cutout also erases the neighbouring collinear
wall. The host is the wall that contains the opening's centre. Walls keep their own
(asymmetric) heights, which is why walls are not merged for this.

All coordinates are model inches; this module has no GUI dependencies.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

JOIN_TOLERANCE_IN = 0.5
LINE_TOLERANCE_IN = 0.5


def _is_straight(wall: Any) -> bool:
    return not getattr(wall, "is_curved", False)


def _length(wall: Any) -> float:
    return math.hypot(wall.end[0] - wall.start[0], wall.end[1] - wall.start[1])


def _close(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= JOIN_TOLERANCE_IN


def _on_line(wall: Any, origin: tuple[float, float], ux: float, uy: float) -> bool:
    """True if both endpoints of ``wall`` lie on the infinite line (origin, u)."""
    for px, py in (wall.start, wall.end):
        if abs((px - origin[0]) * uy - (py - origin[1]) * ux) > LINE_TOLERANCE_IN:
            return False
    return True


def collinear_chain(wall: Any, candidates: Iterable[Any]) -> list[Any]:
    """Return ``wall`` plus every straight wall end-to-end collinear with it.

    Args:
        wall: A straight host wall.
        candidates: Walls to search (may include ``wall``).

    Returns:
        Chain members connected through shared endpoints and lying on ``wall``'s line.
        Curved or zero-length walls yield just ``[wall]``.
    """
    length = _length(wall)
    if not _is_straight(wall) or length < 1e-6:
        return [wall]
    ux = (wall.end[0] - wall.start[0]) / length
    uy = (wall.end[1] - wall.start[1]) / length
    pool = [
        w for w in candidates
        if w is not wall and _is_straight(w) and _length(w) > 1e-6
        and _on_line(w, wall.start, ux, uy)  # noqa: W503
    ]
    chain = [wall]
    grew = True
    while grew:
        grew = False
        for other in list(pool):
            if any(_close(e1, e2) for member in chain
                   for e1 in (member.start, member.end) for e2 in (other.start, other.end)):
                chain.append(other)
                pool.remove(other)
                grew = True
    return chain


def resolve_opening_on_chain(
    wall: Any,
    ratio: float,
    opening_width: float | None,
    candidates: Iterable[Any],
) -> tuple[Any, float]:
    """Resolve a placement on ``wall`` into the correct host wall and ratio.

    Args:
        wall: The wall the cursor was nearest to (straight).
        ratio: Unclamped centre position along ``wall`` (0 = start, 1 = end); may be
            outside [0, 1] when the cursor is beyond the wall's end.
        opening_width: Opening width in inches, or None to skip fitting.
        candidates: All walls that could continue ``wall`` (visible and unlocked).

    Returns:
        ``(host, host_ratio)``: the wall containing the opening's centre and the ratio of
        that centre along it. The centre is clamped so the opening stays inside the whole
        chain. ``host_ratio`` lies in [0, 1].
    """
    chain = collinear_chain(wall, candidates)
    length = _length(wall)
    if length < 1e-6:
        return wall, 0.5
    ux = (wall.end[0] - wall.start[0]) / length
    uy = (wall.end[1] - wall.start[1]) / length
    ox, oy = wall.start

    def proj(pt: tuple[float, float]) -> float:
        return (pt[0] - ox) * ux + (pt[1] - oy) * uy

    spans = [(min(proj(w.start), proj(w.end)), max(proj(w.start), proj(w.end)), w)
             for w in chain]
    lo = min(s[0] for s in spans)
    hi = max(s[1] for s in spans)
    centre = ratio * length
    if opening_width and opening_width < hi - lo:
        half = opening_width / 2.0
        centre = max(lo + half, min(hi - half, centre))
    else:
        centre = max(lo, min(hi, centre)) if not opening_width else (lo + hi) / 2.0

    host = next((s[2] for s in spans if s[0] - 1e-9 <= centre <= s[1] + 1e-9), wall)
    p_start, p_end = proj(host.start), proj(host.end)
    if abs(p_end - p_start) < 1e-9:
        return host, 0.5
    host_ratio = (centre - p_start) / (p_end - p_start)
    return host, max(0.0, min(1.0, host_ratio))
