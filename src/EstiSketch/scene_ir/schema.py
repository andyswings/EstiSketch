"""Versioned SceneIR schema dataclasses and JSON serialization helpers.

``SceneIR`` (schema version 1) is the canonical 3D-ready intermediate
representation exchanged between EstiSketch Python project extraction and the
Rust native 3D engine (plus future renderers). All geometric coordinates and
dimensions in ``SceneIR`` are stored in **meters** using centered Y-up/Z-up
world coordinates (``z`` up), except ``plan_center_in`` which records the 2D
EstiSketch origin offset in **inches**.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass

from .parsed import Point2D, Point3D, RgbColor

SCENE_IR_SCHEMA_VERSION: int = 1


def _to_json_value(value: object) -> object:
    """Recursively convert SceneIR dataclasses, tuples, and dicts to JSON primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        out: dict[str, object] = {}
        for f in fields(value):
            out[f.name] = _to_json_value(getattr(value, f.name))
        return out
    if isinstance(value, (list, tuple)):
        return [_to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _to_json_value(v) for k, v in value.items()}
    return str(value)


@dataclass
class SunIR:
    """Sun/north orientation configuration in degrees."""

    north_angle_deg: float = 0.0
    azimuth_deg: float = 145.0
    elevation_deg: float = 48.0


@dataclass
class LevelIR:
    """Building floor level in meters."""

    id: str
    name: str
    elevation_m: float
    height_m: float
    floor_thickness_m: float


@dataclass
class OpeningCutIR:
    """Axis-aligned cut interval along a host wall segment in meters."""

    opening_id: str
    x0_m: float
    x1_m: float
    z0_m: float
    z1_m: float


@dataclass
class WallSegmentIR:
    """Single straight wall segment with miter angles and finishes in meters/radians."""

    seg_index: int
    start_m: Point2D
    end_m: Point2D
    thickness_m: float
    height_start_m: float
    height_end_m: float
    left_angle_rad: float
    right_angle_rad: float
    exterior: bool
    left_finish: str
    right_finish: str
    left_color: RgbColor | None = None
    right_color: RgbColor | None = None
    left_baseboard: bool = False
    right_baseboard: bool = False
    opening_cuts: list[OpeningCutIR] = field(default_factory=list)


@dataclass
class WallIR:
    """Logical wall (1 segment for straight walls, N segments for curved walls)."""

    id: str
    level_id: str
    layer_id: str
    visible: bool
    locked: bool
    segments: list[WallSegmentIR] = field(default_factory=list)
    custom_3d_override: dict[str, object] | None = None


@dataclass
class OpeningIR:
    """Door or window hosted on a wall segment (meters)."""

    id: str
    kind: str  # "door" | "window"
    host_wall_id: str
    host_seg_index: int
    x_local_m: float
    z_local_m: float
    width_m: float
    depth_m: float
    height_m: float
    style: str
    swing: str
    orientation: str


@dataclass
class RoomIR:
    """Floor/ceiling room volume and cutout polygons (meters)."""

    id: str
    level_id: str
    name: str
    outer_m: list[Point2D]
    floor_holes_m: list[list[Point2D]] = field(default_factory=list)
    ceiling_holes_m: list[list[Point2D]] = field(default_factory=list)
    z_top_m: float = 0.0
    thickness_m: float = 0.254
    ceiling_z_m: float = 2.4384
    floor_pattern: str = "none"
    pattern_rotation_deg: float = 0.0
    pattern_scale: float = 1.0


@dataclass
class RoofFacetIR:
    """Single solved 3D roof slope polygon (meters)."""

    vertices_m: list[Point3D]
    pitch_rise: float


@dataclass
class GableInfillIR:
    """Triangular gable-end wall infill above a gable wall plate (meters)."""

    p_start_m: Point2D
    p_end_m: Point2D
    p_peak_m: Point2D
    z_base_m: float
    z_peak_m: float
    thickness_m: float
    finish: str


@dataclass
class RoofIR:
    """Solved 3D roof assembly with facets and gable infills (meters)."""

    id: str
    level_id: str
    material: str
    thickness_m: float = 0.2032
    facets: list[RoofFacetIR] = field(default_factory=list)
    gable_infills: list[GableInfillIR] = field(default_factory=list)


@dataclass
class FooterIR:
    """Continuous/mitered concrete foundation footer strip (meters)."""

    id: str
    level_id: str
    footprint_m: list[Point2D]
    z_top_m: float
    depth_m: float


@dataclass
class RimBandIR:
    """Upper-story exterior floor rim band prism (meters)."""

    id: str
    level_id: str
    footprint_m: list[Point2D]
    z_bottom_m: float
    height_m: float


@dataclass
class StairIR:
    """3D staircase definition and railing paths (meters/radians)."""

    id: str
    level_id: str
    stair_type: str
    loc_m: Point3D
    rot_z_rad: float
    width_m: float
    total_rise_m: float
    num_steps: int
    tread_depth_m: float
    total_run_m: float
    turn_direction: str
    landing_depth_m: float
    steps_before_landing: int
    winder_count: int
    inner_radius_m: float
    rotation_degrees: float
    has_left_rail: bool
    has_right_rail: bool
    rail_height_m: float
    railing_paths_m: list[list[Point3D]] = field(default_factory=list)


@dataclass
class FixtureIR:
    """3D cabinet, plumbing fixture, appliance, or furniture piece (meters/radians)."""

    id: str
    level_id: str
    symbol_type: str
    category: str
    loc_m: Point3D
    rot_z_rad: float
    width_m: float
    depth_m: float
    height_m: float
    has_countertop: bool
    countertop_overhang_m: float
    countertop_thickness_m: float
    countertop_material: str
    has_backsplash: bool
    fill_color: RgbColor | None = None
    countertop_color: RgbColor | None = None


@dataclass
class CustomAssetIR:
    """Reference to an external custom 3D asset (meters/radians)."""

    id: str
    path: str
    loc_m: Point3D
    rot_z_rad: float
    scale: Point3D = (1.0, 1.0, 1.0)


@dataclass
class SceneIR:
    """Complete SceneIR v1 snapshot ready for serialization to JSON/Rust."""

    schema_version: int = SCENE_IR_SCHEMA_VERSION
    plan_center_in: Point2D = (0.0, 0.0)
    sun: SunIR = field(default_factory=SunIR)
    levels: list[LevelIR] = field(default_factory=list)
    walls: list[WallIR] = field(default_factory=list)
    openings: list[OpeningIR] = field(default_factory=list)
    rooms: list[RoomIR] = field(default_factory=list)
    roofs: list[RoofIR] = field(default_factory=list)
    footers: list[FooterIR] = field(default_factory=list)
    rim_bands: list[RimBandIR] = field(default_factory=list)
    stairs: list[StairIR] = field(default_factory=list)
    fixtures: list[FixtureIR] = field(default_factory=list)
    custom_assets: list[CustomAssetIR] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize the SceneIR snapshot into plain JSON-compatible containers."""
        raw = _to_json_value(self)
        return raw if isinstance(raw, dict) else {}

    def to_json(self, indent: int | None = None) -> str:
        """Serialize the SceneIR snapshot to a UTF-8 JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


@dataclass
class SceneDeltaIR:
    """Incremental SceneIR diff carrying changed/added entities and removed IDs."""

    schema_version: int = SCENE_IR_SCHEMA_VERSION
    plan_center_in: Point2D = (0.0, 0.0)
    sun: SunIR = field(default_factory=SunIR)
    levels: list[LevelIR] = field(default_factory=list)
    walls: list[WallIR] = field(default_factory=list)
    openings: list[OpeningIR] = field(default_factory=list)
    rooms: list[RoomIR] = field(default_factory=list)
    roofs: list[RoofIR] = field(default_factory=list)
    footers: list[FooterIR] = field(default_factory=list)
    rim_bands: list[RimBandIR] = field(default_factory=list)
    stairs: list[StairIR] = field(default_factory=list)
    fixtures: list[FixtureIR] = field(default_factory=list)
    custom_assets: list[CustomAssetIR] = field(default_factory=list)
    removed_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize the SceneDeltaIR into plain JSON-compatible containers."""
        raw = _to_json_value(self)
        return raw if isinstance(raw, dict) else {}

    def to_json(self, indent: int | None = None) -> str:
        """Serialize the SceneDeltaIR to a UTF-8 JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)
