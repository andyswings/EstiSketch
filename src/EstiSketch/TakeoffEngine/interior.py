"""Phase 6: Doors & Windows schedule and Interior finishes (drywall, tape, mud, trim, flooring, paint)."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .checks import Check
from .line_item import LineItem, NONE
from .lumber import pack_boards

INTERIOR_DEFAULTS: Dict[str, float] = {
    "ceiling_vaulted": 1.0,              # 1 = vaulted at roof pitch, 0 = flat ceiling
    "include_gable_walls_in_interior": 1.0,
    "use_interior_dimensions": 1.0,      # 1 = inside face of walls; 0 = outside dimensions
    "drywall_waste_pct": 10.0,
    "drywall_sheet_sqft": 32.0,          # 4x8 sheet (48 for 4x12)
    "drywall_tape_roll_ft": 500.0,       # 250 or 500 ft rolls
    "drywall_tape_sqft_per_500ft": 1200.0,
    "drywall_mud_gal_per_sqft": 0.009,
    "drywall_mud_pail_gal": 4.5,
    "window_sill_stock_ft": 8.0,
    "window_sill_overhang_in": 4.0,      # each side (total +8" over window width)
    "casing_stock_ft": 16.0,
    "casing_waste_pct": 10.0,
    "baseboard_stock_ft": 16.0,
    "baseboard_waste_pct": 10.0,
    "flooring_waste_pct": 10.0,
    "interior_paint_sqft_per_gal": 350.0,
    "paint_coats": 1.0,
    "trim_paint_width_in": 4.0,
    "door_paint_sqft_per_side": 21.0,
    "kerf_in": 0.125,
    "cut_short_tolerance_in": 0.25,
}


def _roof_slope_factor(m: Dict[str, Any]) -> float:
    roof = m.get("roof", {})
    if roof.get("supported"):
        rise = float(roof.get("pitch_rise", 0.0))
        run = float(roof.get("pitch_run", 12.0)) or 12.0
        return math.sqrt(1.0 + (rise / run) ** 2)
    slope = float(m.get("wall_slope", 0.0))
    return math.sqrt(1.0 + slope ** 2)


def interior_wall_area_sqft(m: Dict[str, Any], a: Dict[str, float]) -> float:
    """Pre-waste interior wall area (exterior walls' inside face + gable ends + both sides of partitions)."""
    if a["use_interior_dimensions"]:
        base = m["interior_wall_flat_sqft"]
        gable = m["interior_gable_area_sqft"] if a["include_gable_walls_in_interior"] else 0.0
    else:
        ext = [r for r in m.get("wall_runs", []) if r["exterior"]]
        base = sum(r["length_in"] * r["base_height_in"] for r in ext) / 144.0
        gable = m.get("exterior_gable_area_sqft", 0.0) if a["include_gable_walls_in_interior"] else 0.0
    return base + gable + m.get("partition_wall_sqft", 0.0)


def interior_ceiling_area_sqft(m: Dict[str, Any], a: Dict[str, float]) -> float:
    """Pre-waste ceiling area (flat or vaulted at roof pitch)."""
    floor = m["interior_floor_area_sqft"] if a["use_interior_dimensions"] else m.get("slab_area_sqft", 0.0)
    if floor <= 0:
        floor = sum(m.get("floor_areas_sqft", {}).values())
    if a["ceiling_vaulted"]:
        return floor * _roof_slope_factor(m)
    return floor


def interior_drywall_pre_waste_sqft(m: Dict[str, Any], a: Dict[str, float]) -> float:
    return interior_wall_area_sqft(m, a) + interior_ceiling_area_sqft(m, a)


def _openings_schedule_rows(m: Dict[str, Any], a: Dict[str, float]) -> List[Tuple[str, str, float]]:
    counts: Dict[Tuple[str, str, int, int], int] = {}
    for o in m["openings"]:
        key = (o["kind"], o.get("subtype", ""), int(round(o["width_in"])), int(round(o["height_in"])))
        counts[key] = counts.get(key, 0) + 1
    rows: List[Tuple[str, str, float]] = []
    # Windows first (largest first), then doors
    for (kind, subtype, w, h), n in sorted(counts.items(), key=lambda kv: (kv[0][0] != "window", -kv[0][2], -kv[0][3], kv[0][1])):
        sub = f"{subtype} " if subtype else ""
        label = f"{w}\"x{h}\" {sub}{kind}{'s' if n != 1 else ''}"
        rows.append((f"{kind}_{subtype or 'std'}_{w}x{h}", label, float(n)))
    return rows


def _window_sills(m: Dict[str, Any], a: Dict[str, float]) -> float:
    windows = [o for o in m["openings"] if o["kind"] == "window"]
    if not windows:
        return 0.0
    pieces = [o["width_in"] + 2.0 * a["window_sill_overhang_in"] for o in windows]
    n, _ = pack_boards(pieces, a["window_sill_stock_ft"] * 12.0, a["kerf_in"], a["cut_short_tolerance_in"])
    return float(n)


def _casing_linear_ft(m: Dict[str, Any]) -> float:
    total_in = 0.0
    for o in m["openings"]:
        if o["kind"] == "window":
            # Full perimeter (casing on sides + head + apron under sill)
            total_in += 2.0 * (o["width_in"] + o["height_in"])
        else:
            # Exterior door cased on interior side (2 legs + head); interior door cased on both sides
            sides = 1.0 if o["exterior"] else 2.0
            total_in += sides * (2.0 * o["height_in"] + o["width_in"])
    return total_in / 12.0


def _window_casing_boards(m: Dict[str, Any], a: Dict[str, float]) -> float:
    lf = _casing_linear_ft(m)
    if lf <= 0:
        return 0.0
    return lf * (1.0 + a["casing_waste_pct"] / 100.0) / a["casing_stock_ft"]


def _baseboard_linear_ft(m: Dict[str, Any], a: Dict[str, float]) -> float:
    perim = m["interior_perimeter_ft"] if a["use_interior_dimensions"] else m.get("wall_lf_outside", 0.0)
    return perim + m.get("partition_length_ft", 0.0)


def _baseboard_boards(m: Dict[str, Any], a: Dict[str, float]) -> float:
    lf = _baseboard_linear_ft(m, a)
    if lf <= 0:
        return 0.0
    return lf * (1.0 + a["baseboard_waste_pct"] / 100.0) / a["baseboard_stock_ft"]


def _flooring_rows(m: Dict[str, Any], a: Dict[str, float]) -> List[Tuple[str, str, float]]:
    areas: Dict[str, float] = m.get("floor_areas_sqft", {})
    if not areas:
        return []
    waste = 1.0 + a["flooring_waste_pct"] / 100.0
    if not a["use_interior_dimensions"] and len(areas) == 1 and m.get("slab_area_sqft", 0.0) > 0:
        ft = next(iter(areas))
        return [(ft, f"sq ft {ft.capitalize()} flooring", math.ceil(m["slab_area_sqft"] * waste - 1e-9))]
    rows = []
    for ft, area in sorted(areas.items()):
        if area <= 0:
            continue
        rows.append((ft, f"sq ft {ft.capitalize()} flooring", float(math.ceil(area * waste - 1e-9))))
    return rows


def _drywall_tape_rolls(m: Dict[str, Any], a: Dict[str, float]) -> float:
    area = interior_drywall_pre_waste_sqft(m, a)
    if area <= 0:
        return 0.0
    coverage = a["drywall_tape_sqft_per_500ft"] * (a["drywall_tape_roll_ft"] / 500.0)
    return area / coverage


def _drywall_mud_pails(m: Dict[str, Any], a: Dict[str, float]) -> float:
    area = interior_drywall_pre_waste_sqft(m, a)
    if area <= 0:
        return 0.0
    return (area * a["drywall_mud_gal_per_sqft"]) / a["drywall_mud_pail_gal"]


def _trim_paint_gal(m: Dict[str, Any], a: Dict[str, float]) -> float:
    lf = _casing_linear_ft(m) + _baseboard_linear_ft(m, a)
    if lf <= 0:
        return 0.0
    sqft = lf * (a["trim_paint_width_in"] / 12.0) * a["paint_coats"]
    return sqft / a["interior_paint_sqft_per_gal"]


def _ext_door_paint_qt(m: Dict[str, Any], a: Dict[str, float]) -> float:
    ext_doors = [o for o in m["openings"] if o["kind"] == "door" and o["exterior"]]
    if not ext_doors:
        return 0.0
    sqft = len(ext_doors) * 2.0 * a["door_paint_sqft_per_side"] * a["paint_coats"]
    return (sqft / a["interior_paint_sqft_per_gal"]) * 4.0  # quarts


def interior_items() -> List[LineItem]:
    REQ_WALL = ["interior_wall_flat_sqft", "interior_gable_area_sqft", "interior_floor_area_sqft"]
    return [
        LineItem("doors_windows", "Doors & Windows", "Doors & Windows", "ea", lambda m, a: 0.0,
                 explanation="Attached doors and windows grouped by type and size (orphaned openings excluded).",
                 multi=_openings_schedule_rows, rounding=NONE, requires=["openings"]),
        LineItem("drywall_sqft", "sq ft Drywall", "Interior", "sqft",
                 lambda m, a: interior_drywall_pre_waste_sqft(m, a) * (1.0 + a["drywall_waste_pct"] / 100.0),
                 explanation="Interior walls (incl. gable ends) + ceiling (vaulted or flat) + waste.",
                 requires=REQ_WALL),
        LineItem("drywall_sheets", "4x8 Drywall sheets", "Interior", "sheet",
                 lambda m, a: interior_drywall_pre_waste_sqft(m, a) * (1.0 + a["drywall_waste_pct"] / 100.0)
                 / a["drywall_sheet_sqft"],
                 explanation="Drywall sq ft (with waste) / sheet area.", requires=REQ_WALL),
        LineItem("drywall_tape", "500 ft rolls drywall tape", "Interior", "roll", _drywall_tape_rolls,
                 explanation="Pre-waste drywall area / coverage per roll (1,200 sq ft per 500' roll), rounded up.",
                 requires=REQ_WALL),
        LineItem("drywall_mud", "4.5 gallon pails drywall mud", "Interior", "pail", _drywall_mud_pails,
                 explanation="Pre-waste drywall area x 0.009 gal/sq ft / 4.5 gal per pail, rounded up.",
                 requires=REQ_WALL),
        LineItem("window_sills", "5/4\"x6x8' Window sills", "Interior", "ea", _window_sills,
                 explanation="Window widths + overhangs on each side, packed into 8' stock.",
                 rounding=NONE, hide_if_zero=True, requires=["openings"]),
        LineItem("window_casing", "16' Window & door casing", "Interior", "ea", _window_casing_boards,
                 explanation="Window perimeters + interior door casing + waste, divided by 16' stock.",
                 hide_if_zero=True, requires=["openings"]),
        LineItem("baseboard", "16' Baseboard", "Interior", "ea", _baseboard_boards,
                 explanation="Interior wall perimeter + partitions + waste, divided by 16' stock.",
                 requires=["interior_perimeter_ft"]),
        LineItem("flooring", "Flooring", "Interior", "sqft", lambda m, a: 0.0,
                 explanation="Room floor area by floor type + waste.",
                 multi=_flooring_rows, rounding=NONE, requires=["floor_areas_sqft"]),
        LineItem("ceiling_paint", "Gallons Ceiling Paint", "Interior", "gal",
                 lambda m, a: interior_ceiling_area_sqft(m, a) * a["paint_coats"] / a["interior_paint_sqft_per_gal"],
                 explanation="Pre-waste ceiling area x coats / coverage per gallon.", requires=REQ_WALL),
        LineItem("wall_paint", "Gallons Wall Paint", "Interior", "gal",
                 lambda m, a: interior_wall_area_sqft(m, a) * a["paint_coats"] / a["interior_paint_sqft_per_gal"],
                 explanation="Pre-waste interior wall area x coats / coverage per gallon.", requires=REQ_WALL),
        LineItem("interior_trim_paint", "Gallons Interior Trim Paint", "Interior", "gal", _trim_paint_gal,
                 explanation="Interior casing + baseboard effective paint area / coverage per gallon.",
                 hide_if_zero=True, requires=["openings", "interior_perimeter_ft"]),
        LineItem("exterior_door_paint", "Quarts Exterior Door Paint", "Interior", "qt", _ext_door_paint_qt,
                 explanation="Exterior doors (both sides) / coverage per quart.",
                 hide_if_zero=True, requires=["openings"]),
    ]


def interior_checks(assumptions) -> List[Check]:
    def no_rooms(m, r):
        if not m.get("floor_areas_sqft"):
            return "no rooms defined in the plan; flooring lines are empty"
        return ""

    def vaulted_no_roof(m, r):
        if assumptions.get("ceiling_vaulted") and not m.get("roof", {}).get("supported") and m.get("wall_slope", 0.0) <= 0:
            return "ceiling is set to vaulted but no roof pitch or sloped walls were found; using flat ceiling"
        return ""

    return [Check("rooms present", no_rooms), Check("vaulted ceiling pitch", vaulted_no_roof)]
