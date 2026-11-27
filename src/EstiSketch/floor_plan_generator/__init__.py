"""Headless multi-style, multi-option automatic floor plan generator."""

from .builder import generate_floor_plans, populate_canvas_from_plan
from .specs import (
    MAX_OPTIONS_PER_STYLE,
    MAX_STYLES,
    MAX_TOTAL_PLANS,
    VALID_BATHROOM_COUNTS,
    VALID_LAYOUT_CONCEPTS,
    FloorPlanRequest,
    GeneratedFloorPlan,
    HomeStyleSpec,
)
from .styles import HOME_STYLES, get_style, list_styles

__all__ = [
    "FloorPlanRequest",
    "GeneratedFloorPlan",
    "HOME_STYLES",
    "HomeStyleSpec",
    "MAX_OPTIONS_PER_STYLE",
    "MAX_STYLES",
    "MAX_TOTAL_PLANS",
    "VALID_BATHROOM_COUNTS",
    "VALID_LAYOUT_CONCEPTS",
    "generate_floor_plans",
    "get_style",
    "list_styles",
    "populate_canvas_from_plan",
]
