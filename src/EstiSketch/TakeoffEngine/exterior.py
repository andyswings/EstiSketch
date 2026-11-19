"""Phase 4 line items: exterior sheathing, wrap, siding, trim, paint."""
from __future__ import annotations

from typing import Dict, List

from .checks import Check
from .line_item import LineItem

EXTERIOR_DEFAULTS: Dict[str, float] = {
    "deduct_openings": 0.0,          # 1 = subtract door/window area from exterior area (not your habit)
    "sheathing_waste_pct": 3.0,
    "sheet_sqft": 32.0,              # 4x8
    "sheathing_nails_per_sqft": 3.0,  # 300 per 100 sq ft
    "house_wrap_waste_pct": 5.0,
    "house_wrap_roll_sqft": 900.0,   # 9' x 100'
    "siding_waste_pct": 10.0,
    "trim_waste_pct": 10.0,
    "exterior_paint_sqft_per_gal": 300.0,
}

REQ = ["exterior_wall_area_sqft"]


def net_exterior_area(m, a) -> float:
    area = m["exterior_wall_area_sqft"]
    if a["deduct_openings"]:
        area -= m["exterior_opening_area_sqft"]
    return area


def sheathing_sheets(m, a) -> float:
    return net_exterior_area(m, a) * (1 + a["sheathing_waste_pct"] / 100.0) / a["sheet_sqft"]


def exterior_items() -> List[LineItem]:
    import math
    return [
        LineItem("wall_sheathing", "7/16\" OSB wall sheathing (4x8)", "Exterior", "sheet", sheathing_sheets,
                 explanation="Gross exterior wall area incl. gables (openings not deducted) + waste, / 32 sq ft.",
                 requires=REQ),
        LineItem("sheathing_nails", "Sheathing nails", "Exterior", "ea",
                 lambda m, a: math.ceil(sheathing_sheets(m, a) - 1e-9) * a["sheet_sqft"] * a["sheathing_nails_per_sqft"],
                 explanation="Whole sheets x 32 sq ft x nails per sq ft.", requires=REQ),
        LineItem("house_wrap_sqft", "House wrap (sq ft)", "Exterior", "sqft",
                 lambda m, a: net_exterior_area(m, a) * (1 + a["house_wrap_waste_pct"] / 100.0),
                 explanation="Gross exterior wall area + overage.", requires=REQ),
        LineItem("house_wrap_rolls", "House wrap (rolls)", "Exterior", "roll",
                 lambda m, a: net_exterior_area(m, a) * (1 + a["house_wrap_waste_pct"] / 100.0) / a["house_wrap_roll_sqft"],
                 explanation="Wrap area with overage / roll coverage.", requires=REQ),
        LineItem("siding", "Siding (sq ft)", "Exterior", "sqft",
                 lambda m, a: net_exterior_area(m, a) * (1 + a["siding_waste_pct"] / 100.0),
                 explanation="Gross exterior wall area incl. gables + waste.", requires=REQ),
        LineItem("exterior_trim", "Corner / window / door trim (ft)", "Exterior", "ft",
                 lambda m, a: (m["exterior_corner_trim_ft"] + m["exterior_opening_trim_ft"])
                 * (1 + a["trim_waste_pct"] / 100.0),
                 explanation="Corner trim (corners x wall height) + window perimeters + door sides and head, + waste.",
                 requires=["exterior_corner_trim_ft", "exterior_opening_trim_ft"]),
        LineItem("exterior_paint", "Exterior paint (gallons)", "Exterior", "gal",
                 lambda m, a: net_exterior_area(m, a) / a["exterior_paint_sqft_per_gal"],
                 explanation="Pre-waste exterior area / coverage per gallon.", requires=REQ),
    ]


def exterior_checks() -> List[Check]:
    def none(m, r):
        return "no exterior walls found (walls must form a closed loop); exterior lines are zero" \
            if not m.get("exterior_wall_area_sqft") else ""
    return [Check("exterior walls", none)]
