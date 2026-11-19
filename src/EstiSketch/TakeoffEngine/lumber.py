"""Lumber helpers: cut-list packing, size selection, stock lengths."""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple


def pack_boards(pieces_in: Sequence[float], stock_in: float, kerf_in: float = 0.125,
                short_tol_in: float = 0.25) -> Tuple[int, List[float]]:
    """First-fit-decreasing cut packing. Returns (boards needed, pieces too long for the stock).

    N pieces from one board need N-1 cuts, so kerf is charged (N-1) times; a board may come up to
    `short_tol_in` short in total (a carpenter trims a hair off one piece)."""
    oversize = [p for p in pieces_in if p > stock_in + short_tol_in]
    bins: List[List[float]] = []
    for p in sorted((p for p in pieces_in if p <= stock_in + short_tol_in), reverse=True):
        for b in bins:
            if sum(b) + p + len(b) * kerf_in <= stock_in + short_tol_in:
                b.append(p)
                break
        else:
            bins.append([p])
    return len(bins), oversize


def split_run(length_in: float, stock_in: float) -> List[float]:
    """Lay a run out in full-length boards plus a remainder."""
    pieces, left = [], length_in
    while left > stock_in + 1e-9:
        pieces.append(stock_in)
        left -= stock_in
    if left > 1e-9:
        pieces.append(left)
    return pieces


def lumber_size_for_thickness(thickness_in: float) -> str:
    """Nominal framing size for a wall thickness."""
    if thickness_in <= 4.5:
        return "2x4"
    if thickness_in <= 6.4:
        return "2x6"
    if thickness_in <= 8.25:
        return "2x8"
    return "2x10"


def interp(profile: Sequence[Tuple[float, float]], x: float) -> float:
    """Linear interpolation of a [(s, h)] profile."""
    pts = sorted(profile)
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, h0), (x1, h1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return h0 if x1 == x0 else h0 + (h1 - h0) * (x - x0) / (x1 - x0)
    return pts[-1][1]
