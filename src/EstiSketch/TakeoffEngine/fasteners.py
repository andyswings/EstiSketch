"""Phase 7: Fasteners (framing nails and drywall screws; sheathing and roofing nails live with their trades)."""
from __future__ import annotations

from typing import Any, Dict, List

from .interior import interior_drywall_pre_waste_sqft
from .line_item import LineItem

FASTENER_DEFAULTS: Dict[str, float] = {
    "framing_nails_per_sqft": 1.5,
    "drywall_screws_per_sqft": 1.0,
}


def _floor_plan_area_sqft(m: Dict[str, Any]) -> float:
    """Outside floor plan footprint (slab area, falling back to interior floor area)."""
    area = float(m.get("slab_area_sqft", 0.0))
    if area <= 0:
        area = float(m.get("interior_floor_area_sqft", 0.0))
    return area


def _framing_nails(m: Dict[str, Any], a: Dict[str, float]) -> float:
    return _floor_plan_area_sqft(m) * a["framing_nails_per_sqft"]


def _drywall_screws(m: Dict[str, Any], a: Dict[str, float]) -> float:
    return interior_drywall_pre_waste_sqft(m, a) * a["drywall_screws_per_sqft"]


def fastener_items() -> List[LineItem]:
    return [
        LineItem(
            "framing_nails",
            "Framing nails",
            "Fasteners",
            "ea",
            _framing_nails,
            explanation="Floor plan area (outside footprint) x framing nails per sq ft (default 1.5).",
            requires=["slab_area_sqft"],
        ),
        LineItem(
            "drywall_screws",
            "Drywall screws",
            "Fasteners",
            "ea",
            _drywall_screws,
            explanation="Pre-waste drywall area (interior walls + ceiling) x screws per sq ft (default 1.0).",
            requires=["interior_wall_flat_sqft", "interior_gable_area_sqft", "interior_floor_area_sqft"],
        ),
    ]
