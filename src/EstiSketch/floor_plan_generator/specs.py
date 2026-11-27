"""Data models and safety caps for the automatic floor plan generator."""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_STYLES: int = 4
MAX_OPTIONS_PER_STYLE: int = 4
MAX_TOTAL_PLANS: int = 12

VALID_BATHROOM_COUNTS: tuple[float, ...] = (1.0, 1.5, 2.0, 2.5, 3.0, 3.5)
VALID_LAYOUT_CONCEPTS: tuple[str, ...] = ("style_default", "open", "traditional")


@dataclass(frozen=True)
class HomeStyleSpec:
    """Architectural style definition governing geometry, roof, openings, and finishes.

    All dimensional attributes are in model **inches** unless noted otherwise.
    """

    key: str
    name: str
    description: str
    main_wall_height_in: float
    upper_wall_height_in: float
    exterior_finish: str
    roof_type: str  # "gable" or "hip"
    roof_pitch_rise: int
    roof_overhang_in: float
    roof_material: str
    primary_window_type: str
    secondary_window_type: str
    window_width_in: float
    window_height_in: float
    public_floor_type: str
    public_floor_pattern: str
    kitchen_floor_pattern: str
    bath_floor_pattern: str
    bedroom_floor_pattern: str
    open_concept: bool
    front_entry_door_width_in: float = 36.0


@dataclass(frozen=True)
class FloorPlanRequest:
    """User specification for generating multi-style, multi-option floor plans."""

    bedrooms: int = 3
    bathrooms: float = 2.0
    levels: int = 1
    garage_cars: int = 2
    min_sqft: int = 1400
    max_sqft: int = 2200
    include_office: bool = False
    include_dining: bool = True
    include_laundry: bool = True
    open_floor_plan: str = "style_default"
    styles: tuple[str, ...] = ("craftsman", "modern")
    options_per_style: int = 2
    seed: int = 42

    def normalized(self) -> FloorPlanRequest:
        """Return a clamped and validated copy enforcing safe generation limits."""
        beds = max(1, min(5, int(self.bedrooms)))
        baths = min(
            VALID_BATHROOM_COUNTS,
            key=lambda b: abs(b - float(self.bathrooms)),
        )
        lvls = 2 if int(self.levels) >= 2 else 1
        cars = max(0, min(3, int(self.garage_cars)))
        lo_sqft = max(700, min(4500, int(self.min_sqft)))
        hi_sqft = max(lo_sqft, min(5000, int(self.max_sqft)))

        raw_concept = str(self.open_floor_plan).strip().lower()
        concept = raw_concept if raw_concept in VALID_LAYOUT_CONCEPTS else "style_default"

        dedup_styles: list[str] = []
        for s in self.styles:
            cleaned = str(s).strip().lower()
            if cleaned and cleaned not in dedup_styles:
                dedup_styles.append(cleaned)
        if not dedup_styles:
            dedup_styles = ["craftsman"]
        dedup_styles = dedup_styles[:MAX_STYLES]

        opts = max(1, min(MAX_OPTIONS_PER_STYLE, int(self.options_per_style)))
        return FloorPlanRequest(
            bedrooms=beds,
            bathrooms=baths,
            levels=lvls,
            garage_cars=cars,
            min_sqft=lo_sqft,
            max_sqft=hi_sqft,
            include_office=bool(self.include_office),
            include_dining=bool(self.include_dining),
            include_laundry=bool(self.include_laundry),
            open_floor_plan=concept,
            styles=tuple(dedup_styles),
            options_per_style=opts,
            seed=int(self.seed),
        )


@dataclass
class GeneratedFloorPlan:
    """One generated floor plan candidate ready for preview, editing, and saving."""

    plan_id: str
    style_key: str
    style_name: str
    option_index: int
    variant_name: str
    summary: str
    living_sqft: float
    garage_sqft: float
    bedrooms: int
    bathrooms: float
    levels: int
    garage_cars: int
    roof_summary: str
    layout_violations: list[str] = field(default_factory=list)
    canvas: object = None
