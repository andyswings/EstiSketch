"""Phase 2 line items: foundation and slab."""
from __future__ import annotations

import math
from typing import Dict, List

from .checks import Check
from .line_item import LineItem, NONE

FOUNDATION_DEFAULTS: Dict[str, float] = {
    "dimension_snap_in": 0.25,
    # thickened edge
    "thickened_width_in": 12.0,
    "thickened_thickness_in": 8.0,
    "thickened_count_full_depth": 0.0,   # 1 = count full depth on top of slab (old spreadsheet method)
    # rebar
    "rebar_piece_len_ft": 20.0,
    "rebar_lap_ft": 2.0,
    "rebar_grid_spacing_ft": 2.0,
    "rebar_edge_runs": 2.0,
    "chair_spacing_ft": 4.0,
    # forms
    "form_board_len_ft": 16.0,
    "form_board_actual_depth_in": 3.5,   # 2x4
    "stake_spacing_ft": 3.0,
    "stake_stock_ft": 3.0,               # stock length per stake (stake + brace)
    # concrete
    "concrete_extra_yd": 1.0,
    # anchor bolts / sill
    "plate_len_ft": 16.0,
    "bolt_max_spacing_ft": 6.0,
    "bolt_end_offset_in": 9.0,
}


def _thickened(m):
    return [s for s in m["slabs"] if s["edge_type"] == "thickened"]


def _rebar(m, a):
    pieces_len = a["rebar_piece_len_ft"] - a["rebar_lap_ft"]
    edge = sum(s["perimeter_ft"] for s in _thickened(m)) * a["rebar_edge_runs"]
    # grid: runs each way = 2 * area / spacing (equals W/s*L + L/s*W for a rectangle)
    grid = sum(2.0 * s["area_sqft"] / a["rebar_grid_spacing_ft"]
               for s in m["slabs"] if s["reinforcement"] == "rebar_grid")
    return (edge + grid) / pieces_len


def _chairs(m, a):
    return sum(s["perimeter_ft"] for s in _thickened(m)) / a["chair_spacing_ft"]


def _forms(m, a):
    p = sum(s["perimeter_ft"] for s in m["slabs"])
    boards = math.ceil(p / a["form_board_len_ft"] - 1e-9)
    stakes = math.ceil(p / a["stake_spacing_ft"] - 1e-9)
    stake_boards = math.ceil(stakes * a["stake_stock_ft"] / a["form_board_len_ft"] - 1e-9)
    return boards + stake_boards


def _concrete_cf(m, a):
    cf = 0.0
    for s in m["slabs"]:
        cf += s["area_sqft"] * s["thickness_in"] / 12.0
        if s["edge_type"] == "thickened":
            depth = a["thickened_thickness_in"]
            if not a["thickened_count_full_depth"]:
                depth -= s["thickness_in"]
            cf += s["perimeter_ft"] * (a["thickened_width_in"] / 12.0) * max(depth, 0.0) / 12.0
    return cf


def _concrete(m, a):
    return _concrete_cf(m, a) / 27.0 + a["concrete_extra_yd"]


def bolts_for_piece(length_ft: float, max_spacing_ft: float, end_offset_in: float) -> int:
    """Anchor bolts for one bottom-plate piece: one `end_offset_in` from each end, rest <= max spacing."""
    span = length_ft - 2 * end_offset_in / 12.0
    if span <= 0:
        return 1
    return int(math.ceil(span / max_spacing_ft - 1e-9)) + 1


def plate_pieces(run_ft: float, plate_len_ft: float) -> List[float]:
    """Lay a plate run out in full-length lumber with the remainder as the last piece."""
    pieces, left = [], run_ft
    while left > plate_len_ft + 1e-9:
        pieces.append(plate_len_ft)
        left -= plate_len_ft
    if left > 1e-9:
        pieces.append(left)
    return pieces


def _j_bolts(m, a):
    total = 0
    for run in m["plate_runs_ft"]:
        for piece in plate_pieces(run, a["plate_len_ft"]):
            total += bolts_for_piece(piece, a["bolt_max_spacing_ft"], a["bolt_end_offset_in"])
    return total


def foundation_items() -> List[LineItem]:
    return [
        LineItem("rebar_20", "1/2\" x 20' Rebar", "Foundation", "ea", _rebar,
                 explanation="Thickened edge: perimeter x runs. Grid: 2 x area / spacing. "
                             "Total divided by (piece length - lap), rounded up once.",
                 requires=["slabs"]),
        LineItem("rebar_chairs", "2 bar rebar chairs", "Foundation", "ea", _chairs,
                 explanation="Thickened-edge perimeter / chair spacing.", requires=["slabs"]),
        LineItem("form_boards", "2x4x16' form boards and stakes", "Foundation", "ea", _forms,
                 explanation="Perimeter / board length (rounded up) plus stakes: perimeter / stake spacing "
                             "(rounded up) x stock per stake / board length (rounded up).",
                 rounding=NONE, requires=["slabs"]),
        LineItem("concrete_yd", "Concrete (yards)", "Foundation", "yd", _concrete,
                 explanation="(Slab area x thickness + thickened edge extra depth) / 27 + extra yard, rounded up.",
                 requires=["slabs"]),
        LineItem("j_bolts", "J bolts", "Foundation", "ea", _j_bolts,
                 explanation="Bottom plates laid out in lumber lengths; one bolt 9\" from each piece end, "
                             "remaining spaced no more than max spacing.",
                 rounding=NONE, requires=["slabs", "plate_runs_ft"]),
    ]


def foundation_checks() -> List[Check]:
    def no_slab(m, r):
        return "no slab found in the plan; foundation lines are zero" if not m["slabs"] else ""

    def non_rect(m, r):
        n = sum(1 for s in m["slabs"] if not s["rectangular"])
        return f"{n} slab(s) are not rectangular; area uses polygon math, check the concrete" if n else ""

    return [Check("slab present", no_slab, "error"), Check("slab shape", non_rect)]


def form_board_check(assumptions) -> Check:
    """Warns when the chosen form board is shallower than the slab edge."""
    def test(m, r):
        depth = assumptions.get("form_board_actual_depth_in")
        thick = max((s["thickness_in"] for s in m["slabs"]), default=0.0)
        if thick > depth + 0.5 + 0.01:  # a nominal 2x4 (3.5") holds a 4" slab
            return f"form boards are {depth}\" deep but slab is {thick}\" thick; use deeper boards (e.g. 2x6)"
        return ""
    return Check("form board depth", test)
