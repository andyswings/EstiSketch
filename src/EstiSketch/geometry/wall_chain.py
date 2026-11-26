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


def pocket_door_total_width(callout_width_in: float) -> float:
    """Return total rough frame width (inches) for a pocket door: ``2 * width + 2``."""
    return 2.0 * float(callout_width_in) + 2.0


def pocket_door_extents(
    callout_width_in: float,
    swing: str = "left",
) -> tuple[float, float]:
    """Return ``(left_ext_in, right_ext_in)`` from clear opening center along wall ``d``.

    The clear opening spans ``[-w/2, +w/2]`` and the recessed pocket cavity extends by an
    additional ``w + 2`` inches toward ``-d`` (``swing == "left"``) or ``+d``
    (``swing == "right"``), giving a total span of ``2 * w + 2`` inches.
    """
    w = float(callout_width_in)
    if swing == "right":
        return (0.5 * w, 1.5 * w + 2.0)
    return (1.5 * w + 2.0, 0.5 * w)


def resolve_opening_on_chain(
    wall: Any,
    ratio: float,
    opening_width: float | None,
    candidates: Iterable[Any],
    left_ext: float | None = None,
    right_ext: float | None = None,
) -> tuple[Any, float]:
    """Resolve a placement on ``wall`` into the correct host wall and ratio.

    Args:
        wall: The wall the cursor was nearest to (straight).
        ratio: Unclamped centre position along ``wall`` (0 = start, 1 = end); may be
            outside [0, 1] when the cursor is beyond the wall's end.
        opening_width: Opening width in inches, or None to skip fitting.
        candidates: All walls that could continue ``wall`` (visible and unlocked).
        left_ext: Optional distance (inches) required before ``centre`` along ``wall``'s
            direction (used for pocket doors whose cavity extends into the wall).
        right_ext: Optional distance (inches) required after ``centre`` along ``wall``'s
            direction.

    Returns:
        ``(host, host_ratio)``: the wall containing the opening's centre and the ratio of
        that centre along it. The centre is clamped so the opening (plus any pocket cavity)
        stays inside the whole chain. ``host_ratio`` lies in [0, 1].
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
    if left_ext is not None and right_ext is not None:
        ext_l = float(left_ext)
        ext_r = float(right_ext)
        if ext_l + ext_r < hi - lo:
            centre = max(lo + ext_l, min(hi - ext_r, centre))
        else:
            centre = max(lo, min(hi, lo + (hi - lo - ext_l - ext_r) * 0.5 + ext_l))
    elif opening_width and opening_width < hi - lo:
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


def opening_chain_overlaps(
    host_wall: Any,
    ratio: float,
    opening_width: float,
    candidates: Iterable[Any],
) -> list[tuple[Any, float]]:
    """Return how much of an opening's width overlaps each collinear wall segment.

    Args:
        host_wall: Host wall holding ``(host_wall, opening, ratio)``.
        ratio: Normalized centre position along ``host_wall`` (0 = start, 1 = end).
        opening_width: Opening clear width in inches.
        candidates: Candidate walls on the same level/layer that may continue ``host_wall``.

    Returns:
        List of ``(wall, overlap_width_in)`` for every collinear chain wall with a
        positive overlap (inches), keeping ``host_wall`` first when present. Curved
        or degenerate walls fall back to ``[(host_wall, max(0.0, opening_width))]``.
    """
    width_in = max(0.0, float(opening_width))
    length = _length(host_wall)
    if not _is_straight(host_wall) or length < 1e-6 or width_in <= 0.0:
        return [(host_wall, width_in)]

    ux = (host_wall.end[0] - host_wall.start[0]) / length
    uy = (host_wall.end[1] - host_wall.start[1]) / length
    ox, oy = host_wall.start
    centre = float(ratio) * length
    half = width_in / 2.0
    op_lo = centre - half
    op_hi = centre + half

    overlaps: list[tuple[Any, float]] = []
    for member in collinear_chain(host_wall, candidates):
        p_s = (member.start[0] - ox) * ux + (member.start[1] - oy) * uy
        p_e = (member.end[0] - ox) * ux + (member.end[1] - oy) * uy
        w_lo = min(p_s, p_e)
        w_hi = max(p_s, p_e)
        ov = min(op_hi, w_hi) - max(op_lo, w_lo)
        if ov > 1e-6:
            overlaps.append((member, ov))

    if not overlaps:
        return [(host_wall, width_in)]
    return overlaps
