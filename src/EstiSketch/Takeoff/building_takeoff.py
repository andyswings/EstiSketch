#!/usr/bin/env python3
"""
building_takeoff.py

Comprehensive Material Takeoff & Supplier Quotation Engine for EstiSketch.
Extracts canvas geometry (walls, doors, windows, rooms, roofs) and computes:
  - Width Summary & Detailed Wall Reports
  - Wall Framing (Studs, Double Top Plates, PT Bottom Plates)
  - Concrete Slab Sill Seal Gasket & Foundation Anchor J-Bolts
  - Exterior Wall Sheathing (OSB / Plywood)
  - Exterior House Wrap (Weather Barrier) & Staples
  - Roof Takeoff Integration (Shingles, Underlayment, Drip Edge, Fascia, Trusses / Rafters)
  - Supplier Quote Itemization & Multi-Format Export (TXT, CSV, PDF)
"""

import math
import os
import csv
import time
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

from .roof_takeoff import RoofSection, CombinedRoofTakeoff, format_takeoff_report

# Unit Conversion Constants
CM_PER_INCH = 2.54
CM_PER_FOOT = 30.48
INCHES_PER_FOOT = 12.0
PIXELS_PER_INCH = 2.0  # Default EstiSketch canvas scale: 2 pixels = 1 inch

try:
    from reportlab.lib.pagesizes import letter  # type: ignore
    from reportlab.lib import colors  # type: ignore
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle  # type: ignore
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # type: ignore
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def format_ft_in(inches: float) -> str:
    """Format inches as feet and inches string (e.g. 6' 2")."""
    total_inches = round(inches, 2)
    feet = int(total_inches // INCHES_PER_FOOT)
    rem_inches = total_inches % INCHES_PER_FOOT
    if abs(rem_inches - round(rem_inches)) < 0.05:
        return f"{feet}' {int(round(rem_inches))}\""
    return f"{feet}' {rem_inches:.1f}\""


# Rough opening extra studs lookup
ROUGH_OPENING_EXTRA_STUDS = {
    16: 3, 24: 3, 30: 3, 36: 2, 42: 2, 48: 1, 54: 1, 60: 3,
    66: 2, 72: 2, 78: 2, 84: 1, 90: 1, 96: 2, 102: 2, 108: 2,
    114: 1, 120: 1, 126: 1, 132: 0, 138: 0, 144: 1, 150: 1, 156: 1,
    162: 0, 168: 0, 174: 0, 180: 1, 186: 1, 192: 0
}


def get_opening_extra_studs(width_in: float) -> int:
    """Lookup number of extra framing studs required for an opening width (in inches)."""
    w_rounded = round(width_in)
    sorted_keys = sorted(ROUGH_OPENING_EXTRA_STUDS.keys())
    for key in sorted_keys:
        if key >= w_rounded:
            return ROUGH_OPENING_EXTRA_STUDS[key]
    return ROUGH_OPENING_EXTRA_STUDS[sorted_keys[-1]]


def width_to_lumber_size(width_in: float) -> str:
    """Map wall width in inches to standard framing lumber size string."""
    w_round = round(width_in, 1)
    if abs(w_round - 3.5) < 0.75:
        return "2x4"
    elif abs(w_round - 5.5) < 0.75:
        return "2x6"
    elif abs(w_round - 7.25) < 0.75:
        return "2x8"
    else:
        return f'{width_in:.1f}" Lumber'


def height_to_stud_length(height_ft: float) -> str:
    """Format stud length based on wall height in feet."""
    if abs(height_ft - 8.0) < 0.5:
        return "8' (92-5/8\" Precut)"
    elif abs(height_ft - 9.0) < 0.5:
        return "9' (104-5/8\" Precut)"
    elif abs(height_ft - 10.0) < 0.5:
        return "10'"
    else:
        return f"{format_ft_in(height_ft * INCHES_PER_FOOT)}"


def width_to_sill_seal_size(width_in: float) -> str:
    """Map wall width in inches to standard sill seal roll width string."""
    w_round = round(width_in, 1)
    if abs(w_round - 3.5) < 0.75:
        return "3-1/2\" x 50'"
    elif abs(w_round - 5.5) < 0.75:
        return "5-1/2\" x 50'"
    elif abs(w_round - 7.25) < 0.75:
        return "7-1/2\" x 50'"
    else:
        return f'{width_in:.1f}" x 50\''


def get_wall_anchor_bolts(length_in: float) -> int:
    """Calculate 1/2" x 10" J-Anchor Bolts required for exterior wall segment on slab."""
    if length_in <= 24.0:
        return 2
    d_in = length_in - 24.0
    intermediate_bolts = max(0, math.ceil(d_in / 48.0) - 1)
    return 2 + intermediate_bolts


def is_point_in_polygon(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
    """Ray casting algorithm to test if point (x, y) is inside polygon."""
    num_pts = len(polygon)
    if num_pts < 3:
        return False
    j = num_pts - 1
    c = False
    for i in range(num_pts):
        pi = polygon[i]
        pj = polygon[j]
        if ((pi[1] > y) != (pj[1] > y)) and \
           (x < (pj[0] - pi[0]) * (y - pi[1]) / (pj[1] - pi[1]) + pi[0]):
            c = not c
        j = i
    return c


def extract_walls_from_canvas(canvas) -> List[Dict]:
    """
    Extract wall geometry and openings directly from EstiSketch Canvas object.
    
    Returns a list of wall dictionaries with standard keys:
    id, start_cm, end_cm, start_ft, end_ft, length_cm, length_ft, width_in, height_ft,
    is_exterior, type, doors, windows, etc.
    """
    walls = []
    ppi = getattr(canvas, "pixels_per_inch", 2.0)
    if not ppi or ppi <= 0:
        ppi = 2.0

    # Build room polygons from canvas rooms if available
    room_polygons = []
    if hasattr(canvas, "rooms") and canvas.rooms:
        for r in canvas.rooms:
            pts = getattr(r, "points", [])
            if len(pts) >= 3:
                room_polygons.append(pts)

    # Flatten wall_sets
    all_walls = []
    if hasattr(canvas, "wall_sets") and canvas.wall_sets:
        for wset in canvas.wall_sets:
            if isinstance(wset, list):
                all_walls.extend(wset)
            else:
                all_walls.append(wset)
    elif hasattr(canvas, "walls") and canvas.walls:
        all_walls = list(canvas.walls)

    if not all_walls:
        return []

    # Find bounding box for exterior detection fallback
    min_x = min(min(w.start[0], w.end[0]) for w in all_walls)
    max_x = max(max(w.start[0], w.end[0]) for w in all_walls)
    min_y = min(min(w.start[1], w.end[1]) for w in all_walls)
    max_y = max(max(w.start[1], w.end[1]) for w in all_walls)

    for idx, w in enumerate(all_walls, 1):
        x1, y1 = w.start[0], w.start[1]
        x2, y2 = w.end[0], w.end[1]

        # Calculate length in inches & feet
        dx = x2 - x1
        dy = y2 - y1
        len_px = math.hypot(dx, dy)
        length_in = len_px / ppi
        length_ft = length_in / INCHES_PER_FOOT
        length_cm = length_in * CM_PER_INCH

        width_in = float(getattr(w, "width", 5.5))
        height_in = float(getattr(w, "height", getattr(canvas, "default_wall_height", 96.0)))
        height_ft = height_in / INCHES_PER_FOOT
        height_cm = height_in * CM_PER_INCH

        wall_id = str(getattr(w, "identifier", f"W-{idx:02d}"))

        # Exterior detection logic:
        # Check if wall is on bounding edge or outside room polygons
        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0
        
        # Norm vector perpendicular
        length_val = max(1e-5, len_px)
        nx = -dy / length_val * (width_in * ppi / 2.0 + 4.0)
        ny = dx / length_val * (width_in * ppi / 2.0 + 4.0)

        side1_in = any(is_point_in_polygon(mid_x + nx, mid_y + ny, poly) for poly in room_polygons)
        side2_in = any(is_point_in_polygon(mid_x - nx, mid_y - ny, poly) for poly in room_polygons)

        if room_polygons:
            is_ext = not (side1_in and side2_in)
        else:
            tol_px = 15.0
            is_ext = (
                abs(min(x1, x2) - min_x) < tol_px or
                abs(max(x1, x2) - max_x) < tol_px or
                abs(min(y1, y2) - min_y) < tol_px or
                abs(max(y1, y2) - max_y) < tol_px or
                width_in >= 5.0
            )

        walls.append({
            'id': wall_id,
            'start_cm': (x1 / ppi * CM_PER_INCH, y1 / ppi * CM_PER_INCH),
            'end_cm': (x2 / ppi * CM_PER_INCH, y2 / ppi * CM_PER_INCH),
            'start_ft': (x1 / ppi / INCHES_PER_FOOT, y1 / ppi / INCHES_PER_FOOT),
            'end_ft': (x2 / ppi / INCHES_PER_FOOT, y2 / ppi / INCHES_PER_FOOT),
            'length_cm': length_cm,
            'length_ft': length_ft,
            'length_ft_in': format_ft_in(length_in),
            'width_cm': width_in * CM_PER_INCH,
            'width_in': width_in,
            'height_cm': height_cm,
            'height_ft': height_ft,
            'height_ft_in': format_ft_in(height_in),
            'is_tapered': False,
            'h_start_cm': height_cm,
            'h_end_cm': height_cm,
            'h_start_ft_in': format_ft_in(height_in),
            'h_end_ft_in': format_ft_in(height_in),
            'base_height_cm': height_cm,
            'base_height_ft': height_ft,
            'tri_height_cm': 0.0,
            'tri_height_ft': 0.0,
            'tri_height_ft_in': "0' 0\"",
            'is_exterior': is_ext,
            'type': 'Exterior' if is_ext else 'Interior',
            'doors': [],
            'windows': []
        })

    # Map doors and windows from canvas
    if hasattr(canvas, "doors") and canvas.doors:
        for item in canvas.doors:
            if isinstance(item, (tuple, list)) and len(item) >= 3:
                w_obj, door_obj, ratio = item[0], item[1], item[2]
                w_id = str(getattr(w_obj, "identifier", ""))
                d_width_in = float(getattr(door_obj, "width", 36.0))
                d_height_in = float(getattr(door_obj, "height", 80.0))
                d_name = getattr(door_obj, "name", "Door")
            else:
                continue

            for wall_dict in walls:
                if wall_dict['id'] == w_id:
                    wall_dict['doors'].append({
                        'id': getattr(door_obj, "id", f"D-{len(wall_dict['doors'])+1}"),
                        'name': d_name,
                        'type': 'Door',
                        'width_cm': d_width_in * CM_PER_INCH,
                        'width_in': d_width_in,
                        'width_ft_in': format_ft_in(d_width_in),
                        'height_cm': d_height_in * CM_PER_INCH,
                        'height_in': d_height_in,
                        'height_ft_in': format_ft_in(d_height_in),
                        'position_t': float(ratio),
                        'position_ft': float(ratio) * wall_dict['length_ft']
                    })

    if hasattr(canvas, "windows") and canvas.windows:
        for item in canvas.windows:
            if isinstance(item, (tuple, list)) and len(item) >= 3:
                w_obj, win_obj, ratio = item[0], item[1], item[2]
                w_id = str(getattr(w_obj, "identifier", ""))
                win_width_in = float(getattr(win_obj, "width", 36.0))
                win_height_in = float(getattr(win_obj, "height", 48.0))
                win_name = getattr(win_obj, "name", "Window")
            else:
                continue

            for wall_dict in walls:
                if wall_dict['id'] == w_id:
                    wall_dict['windows'].append({
                        'id': getattr(win_obj, "id", f"W-{len(wall_dict['windows'])+1}"),
                        'name': win_name,
                        'type': 'Window',
                        'width_cm': win_width_in * CM_PER_INCH,
                        'width_in': win_width_in,
                        'width_ft_in': format_ft_in(win_width_in),
                        'height_cm': win_height_in * CM_PER_INCH,
                        'height_in': win_height_in,
                        'height_ft_in': format_ft_in(win_height_in),
                        'position_t': float(ratio),
                        'position_ft': float(ratio) * wall_dict['length_ft']
                    })

    return walls


def generate_width_summary_report(walls: List[Dict]) -> str:
    """Generate summary report grouping wall lengths by wall width."""
    if not walls:
        return "No walls found in project canvas."

    by_width = defaultdict(list)
    total_length_ft = sum(w['length_ft'] for w in walls)

    for w in walls:
        width_key = round(w['width_in'], 2)
        by_width[width_key].append(w)

    lines = []
    lines.append("=" * 80)
    lines.append(" WALL SUMMARY BY WIDTH REPORT")
    lines.append("=" * 80)
    lines.append(f"Total Walls Count:          {len(walls)}")
    lines.append(f"Grand Total Wall Length:     {total_length_ft:.2f} ft ({format_ft_in(total_length_ft * INCHES_PER_FOOT)})")
    lines.append("-" * 80)

    for width_in, wall_list in sorted(by_width.items(), reverse=True):
        group_len_ft = sum(w['length_ft'] for w in wall_list)
        ext_count = sum(1 for w in wall_list if w['is_exterior'])
        int_count = len(wall_list) - ext_count
        pct = (group_len_ft / total_length_ft * 100.0) if total_length_ft > 0 else 0.0

        lines.append(f"• {width_in:.2f}\" Wide Walls:")
        lines.append(f"    - Total Length: {group_len_ft:.2f} ft ({format_ft_in(group_len_ft * INCHES_PER_FOOT)}) [{pct:.1f}% of total]")
        lines.append(f"    - Wall Count:   {len(wall_list)} wall(s) (Exterior: {ext_count}, Interior: {int_count})")
        lines.append("-" * 80)

    return "\n".join(lines)


def generate_wall_report(walls: List[Dict]) -> str:
    """Generate detailed listing of all walls with doors and windows."""
    if not walls:
        return "No walls found in project canvas."

    ext_walls = [w for w in walls if w['is_exterior']]
    int_walls = [w for w in walls if not w['is_exterior']]

    lines = []
    lines.append("=" * 80)
    lines.append(" DETAILED WALL LISTING REPORT")
    lines.append("=" * 80)
    lines.append(f"Total Walls: {len(walls)} | Exterior Walls: {len(ext_walls)} | Interior Walls: {len(int_walls)}")
    lines.append("-" * 80)

    for idx, wall in enumerate(walls, 1):
        type_str = f"[{wall['type'].upper()}]"
        lines.append(f"Wall #{idx:02d} (ID: {wall['id']}) {type_str}")
        lines.append(f"  • Type:   {wall['type']}")
        lines.append(f"  • Length: {wall['length_ft']:.2f} ft ({wall['length_ft_in']})")
        lines.append(f"  • Width:  {wall['width_in']:.2f} in")
        lines.append(f"  • Height: {wall['height_ft']:.2f} ft ({wall['height_ft_in']})")

        doors = wall['doors']
        if doors:
            lines.append(f"  • Doors ({len(doors)}):")
            for d in doors:
                lines.append(f"      - {d['name']}: Width = {d['width_in']:.2f} in ({d['width_ft_in']}) [Pos: {d['position_ft']:.1f} ft]")
        else:
            lines.append("  • Doors: None")

        windows = wall['windows']
        if windows:
            lines.append(f"  • Windows ({len(windows)}):")
            for w in windows:
                lines.append(f"      - {w['name']}: Width = {w['width_in']:.2f} in ({w['width_ft_in']}) [Pos: {w['position_ft']:.1f} ft]")
        else:
            lines.append("  • Windows: None")

        lines.append("-" * 80)

    return "\n".join(lines)


def generate_framing_report(walls: List[Dict], stud_spacing: float = 16.0, plate_length_in: float = 192.0) -> str:
    """Calculate framing stud counts, double top plates, bottom PT plates, sill seal, & J-bolts."""
    if not walls:
        return "No walls found in project canvas."

    ext_walls = [w for w in walls if w['is_exterior']]
    by_width_studs = defaultdict(int)
    by_width_walls = defaultdict(list)

    total_basic_studs = 0
    total_corner_extra_studs = 0
    total_opening_extra_studs = 0
    total_studs = 0

    plate_len_ft = plate_length_in / INCHES_PER_FOOT

    for w in walls:
        length_in = w['length_cm'] / CM_PER_INCH
        basic_studs = math.ceil(length_in / stud_spacing) + 1

        if w['is_exterior']:
            corner_extra = 2
            corner_note = "Exterior wall (+2 studs)"
        else:
            corner_extra = 1
            corner_note = "Interior wall (+1 stud)"

        openings = w['doors'] + w['windows']
        opening_extra = sum(get_opening_extra_studs(op['width_in']) for op in openings)

        wall_total = basic_studs + corner_extra + opening_extra
        total_basic_studs += basic_studs
        total_corner_extra_studs += corner_extra
        total_opening_extra_studs += opening_extra
        total_studs += wall_total

        width_key = round(w['width_in'], 2)
        by_width_studs[width_key] += wall_total
        by_width_walls[width_key].append(w)

    lines = []
    lines.append("=" * 80)
    lines.append(" FRAMING MATERIAL REPORT (STUDS & PLATES)")
    lines.append("=" * 80)
    lines.append(f"Stud Spacing: {stud_spacing:.1f}\" OC (On Center) | Stock Plate Length: {plate_len_ft:.0f}'")
    lines.append(f"Total Walls Count: {len(walls)}")
    lines.append(f"GRAND TOTAL STUDS REQUIRED: {total_studs} studs")
    lines.append(f"  • Basic Line Studs:          {total_basic_studs} studs")
    lines.append(f"  • Corner/Tie-in Extra Studs:  {total_corner_extra_studs} studs")
    lines.append(f"  • Door/Window Opening Studs: {total_opening_extra_studs} studs")

    lines.append("-" * 80)
    lines.append(f"GRAND TOTAL FRAMING BOARDS NEEDED ({plate_len_ft:.0f}' STOCK LENGTHS):")

    total_bottom_pt_boards = 0
    total_top_std_boards = 0

    for width_in, w_list in sorted(by_width_walls.items(), reverse=True):
        group_bottom_ft = sum(w['length_ft'] for w in w_list)
        group_top_ft = group_bottom_ft * 2.0
        total_bottom_pt_boards += math.ceil(group_bottom_ft / plate_len_ft)
        total_top_std_boards += math.ceil(group_top_ft / plate_len_ft)

    lines.append(f"  • {plate_len_ft:.0f}' Pressure-Treated Bottom Plates: {total_bottom_pt_boards} board(s)")
    lines.append(f"  • {plate_len_ft:.0f}' Standard Double Top Plates:     {total_top_std_boards} board(s)")
    lines.append("-" * 80)

    lines.append("SILL SEAL GASKET REQUIREMENTS (CONCRETE SLAB FOUNDATION):")
    for width_in, w_list in sorted(by_width_walls.items(), reverse=True):
        group_len_ft = sum(w['length_ft'] for w in w_list)
        sill_rolls = math.ceil(group_len_ft / 50.0)
        sill_size = width_to_sill_seal_size(width_in)
        lumber = width_to_lumber_size(width_in)
        lines.append(f"  • {sill_size} Sill Seal Rolls ({lumber} Wall Gasket): {group_len_ft:.2f} ft linear -> {sill_rolls} Roll(s) (50' roll)")

    lines.append("-" * 80)
    total_anchor_bolts = sum(get_wall_anchor_bolts(w['length_cm'] / CM_PER_INCH) for w in ext_walls)
    lines.append("FOUNDATION ANCHOR \"J\" BOLT REQUIREMENTS (EXTERIOR WALLS ONLY):")
    lines.append(f"  • Exterior Walls Counted: {len(ext_walls)}")
    lines.append(f"  • Total Anchor J-Bolts Needed: {total_anchor_bolts} Pcs (1/2\" x 10\" J-Bolts)")
    lines.append("-" * 80)

    return "\n".join(lines)


def generate_sheathing_report(walls: List[Dict], sheet_width_ft: float = 4.0, sheet_height_ft: float = 8.0, thickness: str = '7/16"') -> str:
    """Calculate exterior sheathing sheet counts (OSB/Plywood)."""
    ext_walls = [w for w in walls if w['is_exterior']]
    if not ext_walls:
        return "No exterior walls found for sheathing calculation."

    sheet_sqft = sheet_width_ft * sheet_height_ft
    total_gross_sqft = 0.0
    total_opening_sqft = 0.0

    for w in ext_walls:
        gross = w['length_ft'] * w['height_ft']
        op_sqft = sum((op['width_in'] * op['height_in']) / 144.0 for op in (w['doors'] + w['windows']))
        total_gross_sqft += gross
        total_opening_sqft += op_sqft

    net_sqft = max(0.0, total_gross_sqft - total_opening_sqft)
    gross_sheets = math.ceil(total_gross_sqft / sheet_sqft)
    net_sheets = math.ceil(net_sqft / sheet_sqft)

    lines = []
    lines.append("=" * 80)
    lines.append(" EXTERIOR WALL SHEATHING REPORT")
    lines.append("=" * 80)
    lines.append(f"Sheet Dimensions: {sheet_width_ft:.0f}' x {sheet_height_ft:.0f}' x {thickness} ({sheet_sqft:.0f} sq ft per panel)")
    lines.append(f"Exterior Walls Counted: {len(ext_walls)}")
    lines.append("-" * 80)
    lines.append(f"Total Gross Wall Area:       {total_gross_sqft:.2f} sq ft")
    lines.append(f"Total Door/Window Openings:  {total_opening_sqft:.2f} sq ft")
    lines.append(f"Total Net Wall Area:         {net_sqft:.2f} sq ft")
    lines.append("-" * 80)
    lines.append("SHEATHING PANELS REQUIRED:")
    lines.append(f"  • Gross Area Order (Recommended): {gross_sheets} Sheet(s)")
    lines.append(f"  • Net Area Order (Exact minimum):  {net_sheets} Sheet(s)")
    lines.append("-" * 80)

    return "\n".join(lines)


def generate_housewrap_report(walls: List[Dict], roll_width_ft: float = 9.0, roll_length_ft: float = 150.0, overlap_pct: float = 10.0) -> str:
    """Calculate exterior house wrap rolls and staple boxes."""
    ext_walls = [w for w in walls if w['is_exterior']]
    if not ext_walls:
        return "No exterior walls found for house wrap calculation."

    roll_sqft = roll_width_ft * roll_length_ft
    total_gross_sqft = sum(w['length_ft'] * w['height_ft'] for w in ext_walls)
    effective_sqft = total_gross_sqft * (1.0 + overlap_pct / 100.0)
    rolls_needed = math.ceil(effective_sqft / roll_sqft) if roll_sqft > 0 else 0

    total_staples = rolls_needed * 1550
    staple_boxes = math.ceil(total_staples / 1250.0) if total_staples > 0 else 0

    lines = []
    lines.append("=" * 80)
    lines.append(" EXTERIOR HOUSE WRAP REPORT")
    lines.append("=" * 80)
    lines.append(f"Roll Dimensions: {roll_width_ft:.0f}' x {roll_length_ft:.0f}' ({roll_sqft:.0f} sq ft/roll)")
    lines.append(f"Overlap Allowance: {overlap_pct:.0f}%")
    lines.append("-" * 80)
    lines.append(f"Total Gross Wall Area: {total_gross_sqft:.2f} sq ft")
    lines.append(f"Effective Area (+{overlap_pct:.0f}%): {effective_sqft:.2f} sq ft")
    lines.append("-" * 80)
    lines.append(f"HOUSE WRAP ROLLS NEEDED: {rolls_needed} Roll(s)")
    lines.append(f"T50 STAPLE BOXES NEEDED: {staple_boxes} Box(es) (1,250 ct/box)")
    lines.append("-" * 80)

    return "\n".join(lines)


def generate_roof_takeoff(canvas, config) -> Dict:
    """Calculate roof material takeoff from canvas roof polylines."""
    roof_sections = []

    if hasattr(canvas, "roofs") and canvas.roofs:
        for idx, r in enumerate(canvas.roofs, 1):
            name = getattr(r, "name", f"Roof Section #{idx}")
            rtype = getattr(r, "roof_type", "gable")
            pitch = float(getattr(r, "pitch", 6.0))
            overhang = float(getattr(r, "overhang", 24.0))

            w_ft = float(getattr(r, "width", 24.0))
            l_ft = float(getattr(r, "length", 30.0))

            framing_type = getattr(config, "ROOF_FRAMING_TYPE", "truss")
            rafter_spacing = float(getattr(config, "ROOF_RAFTER_SPACING_IN", 16.0))
            use_lvl_ridge = bool(getattr(config, "ROOF_USE_LVL_RIDGE", False))

            sec = RoofSection(
                name=name,
                roof_type=rtype,
                pitch_rise=pitch,
                sketched_overhang_in=overhang,
                footprint_width_ft=w_ft,
                footprint_length_ft=l_ft,
                num_eave_sides=3 if rtype == 'hip' else 2,
                framing_type=framing_type,
                rafter_spacing_in=rafter_spacing,
                use_lvl_ridge=use_lvl_ridge
            )
            roof_sections.append(sec)

    if not roof_sections:
        # Fallback default roof section if canvas doesn't have explicit roofs yet
        roof_sections.append(RoofSection(
            name="Main Roof Plan",
            roof_type="gable",
            pitch_rise=6.0,
            sketched_overhang_in=24.0,
            footprint_width_ft=28.0,
            footprint_length_ft=40.0
        ))

    combined = CombinedRoofTakeoff(
        project_name="EstiSketch Roof Takeoff",
        sections=roof_sections,
        waste_percent=float(getattr(config, "ROOF_WASTE_PCT", 10.0)),
        sheathing_thickness=str(getattr(config, "ROOF_SHEATHING_THICKNESS", '5/8"')),
        sheathing_type=str(getattr(config, "ROOF_SHEATHING_TYPE", 'OSB'))
    )

    return combined.generate_material_takeoff()


def get_supplier_quote_items(canvas, config, custom_items: Optional[List[Dict]] = None) -> List[Dict]:
    """
    Aggregate all project building materials into itemized quote line items.
    Each item dict: {id, description, qty, unit, notes, is_auto, is_excluded}
    """
    walls = extract_walls_from_canvas(canvas)
    stud_spacing = float(getattr(config, "DEFAULT_STUD_SPACING", 16.0))
    plate_len_in = float(getattr(config, "MAX_WALL_PLATE_INCHES", 192.0))
    plate_len_ft = plate_len_in / INCHES_PER_FOOT

    sheet_w_ft = float(getattr(config, "SHEATHING_WIDTH_FT", 4.0))
    sheet_h_ft = float(getattr(config, "SHEATHING_HEIGHT_FT", 8.0))
    sheath_thick = str(getattr(config, "SHEATHING_THICKNESS", '7/16"'))
    sheath_mat = str(getattr(config, "SHEATHING_MATERIAL_TYPE", 'OSB'))

    wrap_w_ft = float(getattr(config, "HOUSEWRAP_ROLL_WIDTH_FT", 9.0))
    wrap_l_ft = float(getattr(config, "HOUSEWRAP_ROLL_LENGTH_FT", 150.0))
    wrap_pct = float(getattr(config, "HOUSEWRAP_OVERLAP_PCT", 10.0))

    items = []
    item_counter = 1

    if walls:
        stud_groups = defaultdict(int)
        by_width_walls = defaultdict(list)
        ext_walls = [w for w in walls if w['is_exterior']]

        for w in walls:
            length_in = w['length_cm'] / CM_PER_INCH
            basic_studs = math.ceil(length_in / stud_spacing) + 1
            corner_extra = 2 if w['is_exterior'] else 1
            openings = w['doors'] + w['windows']
            opening_extra = sum(get_opening_extra_studs(op['width_in']) for op in openings)

            wall_total = basic_studs + corner_extra + opening_extra
            width_key = round(w['width_in'], 2)
            height_key = round(w['height_ft'], 1)
            stud_groups[(width_key, height_key)] += wall_total
            by_width_walls[width_key].append(w)

        # 1. Wall Studs
        for (width_in, height_ft), count in sorted(stud_groups.items(), key=lambda x: (x[0][0], x[0][1]), reverse=True):
            lumber = width_to_lumber_size(width_in)
            h_str = height_to_stud_length(height_ft)
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': f"{lumber} Wall Studs ({h_str})",
                'qty': count,
                'unit': 'Pcs',
                'notes': f'Framing studs @ {stud_spacing:.0f}" OC',
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

        # 2. Wall Plates
        for width_in, w_list in sorted(by_width_walls.items(), reverse=True):
            group_bottom_ft = sum(w['length_ft'] for w in w_list)
            bottom_boards = math.ceil(group_bottom_ft / plate_len_ft)
            top_boards = math.ceil((group_bottom_ft * 2.0) / plate_len_ft)
            lumber = width_to_lumber_size(width_in)

            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': f"{lumber} x {plate_len_ft:.0f}' Pressure-Treated Lumber (Bottom Plate)",
                'qty': bottom_boards,
                'unit': 'Boards',
                'notes': f"Treated bottom plate ({group_bottom_ft:.1f}' linear total)",
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': f"{lumber} x {plate_len_ft:.0f}' Standard SPF Lumber (Double Top Plate)",
                'qty': top_boards,
                'unit': 'Boards',
                'notes': f"Double top plate ({(group_bottom_ft * 2.0):.1f}' linear total)",
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

        # 3. Sill Seal Gasket & J-Bolts
        for width_in, w_list in sorted(by_width_walls.items(), reverse=True):
            group_bottom_ft = sum(w['length_ft'] for w in w_list)
            sill_rolls = math.ceil(group_bottom_ft / 50.0)
            sill_size = width_to_sill_seal_size(width_in)
            lumber = width_to_lumber_size(width_in)

            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': f"{sill_size} Polyethylene Foam Sill Seal Gasket Roll ({lumber} Wall Gasket)",
                'qty': sill_rolls,
                'unit': 'Rolls',
                'notes': f"Sill seal under bottom plates ({group_bottom_ft:.1f}' linear total)",
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

        total_anchor_bolts = sum(get_wall_anchor_bolts(w['length_cm'] / CM_PER_INCH) for w in ext_walls)
        if total_anchor_bolts > 0:
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': '1/2" x 10" "J" Anchor Bolts with Nut & Washer',
                'qty': total_anchor_bolts,
                'unit': 'Pcs',
                'notes': 'Exterior wall sill attachment to concrete slab',
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

        # 4. Wall Sheathing
        sheet_sqft = sheet_w_ft * sheet_h_ft
        total_gross_sqft = sum(w['length_ft'] * w['height_ft'] for w in ext_walls)
        gross_sheets = math.ceil(total_gross_sqft / sheet_sqft) if total_gross_sqft > 0 else 0
        if gross_sheets > 0:
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': f"{sheet_w_ft:.0f}' x {sheet_h_ft:.0f}' x {sheath_thick} {sheath_mat} Sheathing Panels",
                'qty': gross_sheets,
                'unit': 'Sheets',
                'notes': f'Exterior wall sheathing coverage ({total_gross_sqft:.1f} sq ft)',
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

        # 5. House Wrap & Staples
        if total_gross_sqft > 0:
            eff_sqft = total_gross_sqft * (1.0 + wrap_pct / 100.0)
            roll_sqft = wrap_w_ft * wrap_l_ft
            wrap_rolls = math.ceil(eff_sqft / roll_sqft)
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': f"{wrap_w_ft:.0f}' x {wrap_l_ft:.0f}' House Wrap Rolls (Weather Barrier)",
                'qty': wrap_rolls,
                'unit': 'Rolls',
                'notes': f'Exterior wall weather barrier ({total_gross_sqft:.1f} sq ft + {wrap_pct:.0f}% overlap)',
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

            staple_boxes = math.ceil((wrap_rolls * 1550) / 1250.0)
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': 'T50 3/8" Heavy Duty Staples (1,250 ct Box)',
                'qty': staple_boxes,
                'unit': 'Boxes',
                'notes': 'House wrap installation fasteners',
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

    # 6. Roof Materials
    roof_data = generate_roof_takeoff(canvas, config)
    if roof_data:
        if roof_data.get('shingle_bundles_needed', 0) > 0:
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': 'Architectural Roof Shingles (3 Bundles / Square)',
                'qty': roof_data['shingle_bundles_needed'],
                'unit': 'Bundles',
                'notes': f"Roof shingles ({roof_data['total_squares_needed']} Squares for {roof_data['total_gross_area_sqft']:.1f} sq ft gross area)",
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

        if roof_data.get('synthetic_underlayment_rolls', 0) > 0:
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': 'Synthetic Roof Underlayment Rolls (1,000 sq ft / roll)',
                'qty': roof_data['synthetic_underlayment_rolls'],
                'unit': 'Rolls',
                'notes': 'Roof deck moisture barrier',
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

        if roof_data.get('ice_water_rolls', 0) > 0:
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': 'Self-Adhering Ice & Water Shield Membrane (200 sq ft / roll)',
                'qty': roof_data['ice_water_rolls'],
                'unit': 'Rolls',
                'notes': f"Eave & valley leak protection ({roof_data['ice_water_sqft']:.1f} sq ft)",
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

        if roof_data.get('drip_edge_sticks', 0) > 0:
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': 'Drip Edge Metal Flashing (10\' Sticks)',
                'qty': roof_data['drip_edge_sticks'],
                'unit': 'Sticks',
                'notes': f"Eave & rake edge flashing ({roof_data['total_drip_edge_lf']:.1f}' linear total)",
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

        if roof_data.get('ridge_cap_bundles', 0) > 0:
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': 'Ridge & Hip Cap Shingles (35 LF Coverage / Bundle)',
                'qty': roof_data['ridge_cap_bundles'],
                'unit': 'Bundles',
                'notes': f"Ridge & hip capping ({roof_data['total_hip_ridge_cap_lf']:.1f}' linear total)",
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

        if roof_data.get('total_sheathing_sheets', 0) > 0:
            r_thick = roof_data.get('sheathing_thickness', '5/8"')
            r_type = roof_data.get('sheathing_type', 'OSB')
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': f"4' x 8' x {r_thick} {r_type} Roof Sheathing Decking",
                'qty': roof_data['total_sheathing_sheets'],
                'unit': 'Sheets',
                'notes': 'Roof deck sheathing',
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

        if roof_data.get('fascia_16ft_boards', 0) > 0:
            items.append({
                'id': f"ITEM-{item_counter:03d}",
                'description': "2x6 x 16' Standard SPF Lumber (Roof Sub-Fascia)",
                'qty': roof_data['fascia_16ft_boards'],
                'unit': 'Boards',
                'notes': f"Sub-fascia trim ({roof_data['total_fascia_lf']:.1f}' linear total)",
                'is_auto': True,
                'is_excluded': False
            })
            item_counter += 1

    # Include custom line items
    if custom_items:
        for c in custom_items:
            item_copy = dict(c)
            if not item_copy.get('id'):
                item_copy['id'] = f"ITEM-{item_counter:03d}"
                item_counter += 1
            items.append(item_copy)

    return items


def export_supplier_quote_txt(items: List[Dict], config, project_name: str = "EstiSketch Project", output_path: str = "supplier_quote.txt") -> str:
    """Export formatted supplier quote to Plain Text file."""
    lines = []
    lines.append("=" * 80)
    lines.append(f" BUILDING SUPPLIER MATERIAL QUOTE REQUEST")
    lines.append(f" Project: {project_name}")
    lines.append(f" Date:    {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 80)
    lines.append(f"{'#':<4} {'Type':<8} {'Qty':<6} {'Unit':<8} {'Description':<42}")
    lines.append("-" * 80)

    active_items = [it for it in items if not it.get('is_excluded', False)]
    for idx, item in enumerate(active_items, 1):
        itype = "[MANUAL]" if not item.get('is_auto') else "[AUTO]"
        desc = item.get('description', '')[:40]
        qty = item.get('qty', 0)
        unit = item.get('unit', 'Pcs')[:6]
        lines.append(f"{idx:<4} {itype:<8} {qty:<6} {unit:<8} {desc:<42}")
        if item.get('notes'):
            lines.append(f"     Notes: {item['notes']}")

    lines.append("=" * 80)
    lines.append(f"Total Active Items: {len(active_items)}")
    lines.append("=" * 80)

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def export_supplier_quote_csv(items: List[Dict], config, project_name: str = "EstiSketch Project", output_path: str = "supplier_quote.csv") -> None:
    """Export supplier quote to CSV spreadsheet file."""
    active_items = [it for it in items if not it.get('is_excluded', False)]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Item #", "Type", "Description", "Quantity", "Unit", "Notes"])
        for idx, item in enumerate(active_items, 1):
            itype = "Manual" if not item.get('is_auto') else "Auto"
            writer.writerow([
                idx,
                itype,
                item.get('description', ''),
                item.get('qty', 0),
                item.get('unit', 'Pcs'),
                item.get('notes', '')
            ])


def export_supplier_quote_pdf(items: List[Dict], config, project_name: str = "EstiSketch Project", output_path: str = "supplier_quote.pdf") -> None:
    """Export supplier quote to PDF file (using ReportLab if available or fallback generator)."""
    active_items = [it for it in items if not it.get('is_excluded', False)]

    if REPORTLAB_AVAILABLE:
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1E293B'))
        meta_style = ParagraphStyle('MetaText', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#64748B'))
        cell_style = ParagraphStyle('TableCell', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#0F172A'))
        header_style = ParagraphStyle('TableHeader', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', textColor=colors.white)

        elements = []
        elements.append(Paragraph(f"Building Material Supplier Quote Request", title_style))
        elements.append(Paragraph(f"Project: {project_name} | Generated: {time.strftime('%Y-%m-%d %H:%M')}", meta_style))
        elements.append(Spacer(1, 15))

        table_data = [[
            Paragraph("#", header_style),
            Paragraph("Type", header_style),
            Paragraph("Description", header_style),
            Paragraph("Qty", header_style),
            Paragraph("Unit", header_style),
            Paragraph("Notes", header_style)
        ]]

        for idx, item in enumerate(active_items, 1):
            itype = "Manual" if not item.get('is_auto') else "Auto"
            table_data.append([
                Paragraph(str(idx), cell_style),
                Paragraph(itype, cell_style),
                Paragraph(item.get('description', ''), cell_style),
                Paragraph(str(item.get('qty', 0)), cell_style),
                Paragraph(item.get('unit', 'Pcs'), cell_style),
                Paragraph(item.get('notes', ''), cell_style)
            ])

        t = Table(table_data, colWidths=[24, 45, 220, 40, 45, 166])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t)
        doc.build(elements)
    else:
        # Fallback text file export if ReportLab is missing
        txt_path = output_path.replace(".pdf", ".txt")
        export_supplier_quote_txt(items, config, project_name, txt_path)
