"""Convert an EstiSketch XML project into a native Home Builder 5 Blender scene.

Usage inside Blender:
    blender --python estisketch_to_hb5.py -- <project.xml> [--save-blend <out.blend>]

The XML parsing and coordinate conversion helpers (Layer 1) do not import
``bpy`` so they can be unit-tested directly under standard Python.
"""

from __future__ import annotations

import math
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

INCH_TO_M = 0.0254


# ---------------------------------------------------------------------------
# Layer 1: Pure-Python XML parser & geometry math (no bpy dependency)
# ---------------------------------------------------------------------------


@dataclass
class ParsedLevel:
    """Building level parsed from an EstiSketch project."""

    id: str
    name: str
    elevation: float  # inches
    height: float  # inches
    floor_thickness: float = 10.0  # inches


@dataclass
class ParsedWall:
    """Wall segment parsed from an EstiSketch project."""

    identifier: str
    set_index: int
    wall_index: int
    start: Tuple[float, float]  # inches
    end: Tuple[float, float]  # inches
    width: float  # inches
    height: float  # inches
    height_at_end: float  # inches
    exterior_wall: bool
    level_id: str
    layer_id: str
    is_curved: bool = False
    arc_center: Optional[Tuple[float, float]] = None
    arc_radius: Optional[float] = None
    symbolic: bool = False
    interior_finish: str = "Drywall"
    exterior_finish: str = ""
    left_finish: str = "Drywall"
    right_finish: str = "Drywall"
    left_color: Optional[Tuple[float, float, float]] = None
    right_color: Optional[Tuple[float, float, float]] = None
    left_baseboard: bool = False
    right_baseboard: bool = False
    footer: bool = False
    footer_left_offset: float = 6.0
    footer_right_offset: float = 6.0
    footer_depth: float = 8.0


@dataclass
class ParsedRoom:
    """Room / floor slab parsed from an EstiSketch project."""

    identifier: str
    name: str
    points: List[Tuple[float, float]]  # inches
    height: float  # inches
    level_id: str
    floor_type: str = "default"
    is_slab: bool = False
    slab_thickness: float = 4.0  # inches
    floor_pattern: str = "none"
    pattern_rotation: float = 0.0
    pattern_scale: float = 1.0
    room_type: str = ""
    wall_finish: str = "Paint"


@dataclass
class ParsedDoor:
    """Door opening parsed from an EstiSketch project."""

    identifier: str
    set_index: int
    wall_index: int
    ratio: float
    door_type: str
    width: float  # inches
    height: float  # inches
    swing: str
    orientation: str
    level_id: str


@dataclass
class ParsedWindow:
    """Window opening parsed from an EstiSketch project."""

    identifier: str
    set_index: int
    wall_index: int
    ratio: float
    window_type: str
    width: float  # inches
    height: float  # inches
    level_id: str


@dataclass
class ParsedRoofEdge:
    """Wall-bound edge metadata for a parsed roof."""

    wall_identifier: str
    edge_type: str
    pitch_rise: Optional[float] = None
    overhang: Optional[float] = None


@dataclass
class ParsedRoof:
    """Roof parsed from an EstiSketch project."""

    identifier: str
    level_id: str
    layer_id: str
    roof_type: str
    pitch_rise: float
    pitch_run: float
    overhang: float
    material: str
    edges: List[ParsedRoofEdge] = field(default_factory=list)
    ridge_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = field(default_factory=list)
    hip_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = field(default_factory=list)
    valley_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = field(default_factory=list)
    rake_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = field(default_factory=list)
    eave_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = field(default_factory=list)
    outline_points: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class SolvedRoofFacet:
    """Closed 3D planar/faceted roof slope in EstiSketch inches."""

    vertices_3d: List[Tuple[float, float, float]]
    pitch_rise: float


@dataclass
class SolvedGableInfill:
    """Triangular gable-end wall infill above a flat-topped gable wall (inches)."""

    p_start: Tuple[float, float]
    p_end: Tuple[float, float]
    p_peak: Tuple[float, float]
    z_base: float
    z_peak: float
    thickness: float
    level_id: str


@dataclass
class SolvedRoofGeometry:
    """Solved 3D facets and gable infills for a roof."""

    roof_id: str
    level_id: str
    material: str
    facets: List[SolvedRoofFacet] = field(default_factory=list)
    gable_infills: List[SolvedGableInfill] = field(default_factory=list)


@dataclass
class ParsedStair:
    """Staircase parsed from an EstiSketch project."""

    identifier: str
    layer_id: str
    level_id: str
    start_point: Tuple[float, float]
    direction_angle: float  # radians
    start_level_id: str
    end_level_id: str
    stair_type: str  # straight, l-shaped, u-shaped, spiral
    width: float  # inches
    total_rise: float  # inches
    riser_height: float  # inches
    num_steps: int
    tread_depth: float  # inches
    total_run: float  # inches
    nosing: float  # inches
    has_left_rail: bool
    has_right_rail: bool
    rail_height: float  # inches
    turn_direction: str  # left, right
    landing_depth: float  # inches
    steps_before_landing: int
    winder_count: int
    opening_clearance: float  # inches
    inner_radius: float  # inches
    rotation_degrees: float


@dataclass
class ParsedFloorOpening:
    """Manual floor or ceiling opening parsed from an EstiSketch project."""

    identifier: str
    level_id: str
    opening_type: str
    label: str
    ceiling_only: bool
    points: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class RoomHoleCutout:
    """Derived floor or ceiling cutout polygon (in EstiSketch inches) for a room."""

    points: List[Tuple[float, float]]
    cuts_floor: bool
    cuts_ceiling: bool
    source_id: str


@dataclass
class ParsedFixture:
    """Architectural cabinet, plumbing fixture, appliance, or furniture piece."""

    identifier: str
    symbol_type: str
    category: str
    level_id: str
    layer_id: str
    x: float  # inches
    y: float  # inches
    width: float  # inches
    depth: float  # inches
    height: float  # inches
    rotation: float  # degrees
    elevation: float  # inches above floor
    mount_surface: str
    has_countertop: bool
    countertop_overhang: float  # inches
    countertop_thickness: float  # inches
    countertop_material: str
    has_backsplash: bool
    door_swing: str
    fill_color: Optional[Tuple[float, float, float]] = None
    countertop_color: Optional[Tuple[float, float, float]] = None


@dataclass
class ParsedProject:
    """Container for all parsed EstiSketch elements needed for 3D conversion."""

    levels: List[ParsedLevel] = field(default_factory=list)
    walls: List[ParsedWall] = field(default_factory=list)
    rooms: List[ParsedRoom] = field(default_factory=list)
    doors: List[ParsedDoor] = field(default_factory=list)
    windows: List[ParsedWindow] = field(default_factory=list)
    roofs: List[ParsedRoof] = field(default_factory=list)
    stairs: List[ParsedStair] = field(default_factory=list)
    floor_openings: List[ParsedFloorOpening] = field(default_factory=list)
    fixtures: List[ParsedFixture] = field(default_factory=list)
    cut_lower_ceiling_under_stairs: bool = False
    north_angle: float = 0.0
    skipped_openings: List[str] = field(default_factory=list)


def _attr_float(elem: ET.Element, name: str, default: float) -> float:
    val = elem.get(name)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _attr_int(elem: ET.Element, name: str, default: int) -> int:
    val = elem.get(name)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _elem_text(parent: ET.Element, tag: str, default: str = "") -> str:
    child = parent.find(tag)
    if child is not None and child.text is not None:
        return child.text.strip()
    return default


def _elem_float(parent: ET.Element, tag: str, default: float) -> float:
    text = _elem_text(parent, tag, "")
    if not text:
        return default
    try:
        return float(text)
    except (ValueError, TypeError):
        return default


def _elem_bool(parent: ET.Element, tag: str, default: bool = False) -> bool:
    text = _elem_text(parent, tag, "")
    if not text:
        return default
    return text.lower() in ("true", "1", "yes")


def _is_visible(elem: ET.Element) -> bool:
    return elem.get("visible", "True").strip().lower() != "false"


def _resolve_level_id(
    layer_id: str,
    layer_to_level: Dict[str, str],
    default_level_id: str,
) -> str:
    if layer_id and layer_id in layer_to_level and layer_to_level[layer_id]:
        return layer_to_level[layer_id]
    return default_level_id


def _parse_hex_rgb(text: str) -> Optional[Tuple[float, float, float]]:
    s = (text or "").strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16) / 255.0, int(s[2:4], 16) / 255.0, int(s[4:6], 16) / 255.0)
    except ValueError:
        return None


def parse_estisketch_xml(xml_path: str) -> ParsedProject:
    """Parse an EstiSketch ``.xml`` project file into pure-Python dataclasses."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    levels: List[ParsedLevel] = []
    levels_elem = root.find("Levels")
    if levels_elem is not None:
        for lvl_el in levels_elem.findall("Level"):
            levels.append(
                ParsedLevel(
                    id=lvl_el.get("id", "") or f"level_{len(levels)}",
                    name=lvl_el.get("name", "") or f"Level {len(levels) + 1}",
                    elevation=_attr_float(lvl_el, "elevation", 0.0),
                    height=_attr_float(lvl_el, "height", 96.0),
                    floor_thickness=_attr_float(lvl_el, "floor_thickness", 10.0),
                )
            )
    if not levels:
        levels.append(ParsedLevel(id="level_0", name="Level 1", elevation=0.0, height=96.0))
    default_level_id = levels[0].id

    layer_to_level: Dict[str, str] = {}
    layers_elem = root.find("Layers")
    if layers_elem is not None:
        for layer_el in layers_elem.findall("Layer"):
            lid = layer_el.get("id", "")
            if lid:
                layer_to_level[lid] = layer_el.get("level_id", "") or default_level_id

    walls: List[ParsedWall] = []
    valid_wall_refs: set[Tuple[int, int]] = set()
    wall_sets_elem = root.find("WallSets")
    if wall_sets_elem is not None:
        for set_idx, ws_el in enumerate(wall_sets_elem.findall("WallSet")):
            for wall_idx, wall_el in enumerate(ws_el.findall("Wall")):
                is_symbolic = _elem_bool(wall_el, "Symbolic", False)
                has_footer = _elem_bool(wall_el, "Footer", False)
                if not _is_visible(wall_el) or (is_symbolic and not has_footer):
                    continue
                start_el = wall_el.find("Start")
                end_el = wall_el.find("End")
                if start_el is None or end_el is None:
                    continue
                start = (_attr_float(start_el, "x", 0.0), _attr_float(start_el, "y", 0.0))
                end = (_attr_float(end_el, "x", 0.0), _attr_float(end_el, "y", 0.0))
                height = _elem_float(wall_el, "Height", 96.0)
                height_at_end = _elem_float(wall_el, "HeightAtEnd", height)
                layer_id = _elem_text(wall_el, "LayerId", "")
                level_id = _resolve_level_id(layer_id, layer_to_level, default_level_id)

                is_curved = _elem_bool(wall_el, "IsCurved", False)
                arc_center = None
                arc_radius = None
                if is_curved:
                    ac_el = wall_el.find("ArcCenter")
                    if ac_el is not None:
                        arc_center = (_attr_float(ac_el, "x", 0.0), _attr_float(ac_el, "y", 0.0))
                    arc_radius = _elem_float(wall_el, "ArcRadius", 0.0) or None

                wall_id = wall_el.get("identifier") or _elem_text(wall_el, "Identifier", "")
                walls.append(
                    ParsedWall(
                        identifier=wall_id or f"wall_{set_idx}_{wall_idx}",
                        set_index=set_idx,
                        wall_index=wall_idx,
                        start=start,
                        end=end,
                        width=_elem_float(wall_el, "Width", 5.5),
                        height=height,
                        height_at_end=height_at_end,
                        exterior_wall=_elem_bool(wall_el, "ExteriorWall", False),
                        level_id=level_id,
                        layer_id=layer_id,
                        is_curved=is_curved,
                        arc_center=arc_center,
                        arc_radius=arc_radius,
                        symbolic=is_symbolic,
                        interior_finish=_elem_text(wall_el, "InteriorFinish", "Drywall") or "Drywall",
                        exterior_finish=_elem_text(wall_el, "ExteriorFinish", ""),
                        left_finish=_elem_text(wall_el, "LeftFinish", "Drywall") or "Drywall",
                        right_finish=_elem_text(wall_el, "RightFinish", "Drywall") or "Drywall",
                        left_color=_parse_hex_rgb(_elem_text(wall_el, "LeftColor", "")),
                        right_color=_parse_hex_rgb(_elem_text(wall_el, "RightColor", "")),
                        left_baseboard=_elem_bool(wall_el, "LeftBaseboard", False),
                        right_baseboard=_elem_bool(wall_el, "RightBaseboard", False),
                        footer=has_footer,
                        footer_left_offset=_elem_float(wall_el, "FooterLeftOffset", 6.0),
                        footer_right_offset=_elem_float(wall_el, "FooterRightOffset", 6.0),
                        footer_depth=_elem_float(wall_el, "FooterDepth", 8.0),
                    )
                )
                if not is_symbolic:
                    valid_wall_refs.add((set_idx, wall_idx))

    rooms: List[ParsedRoom] = []
    rooms_elem = root.find("Rooms")
    if rooms_elem is not None:
        for room_idx, room_el in enumerate(rooms_elem.findall("Room")):
            if not _is_visible(room_el):
                continue
            pts_el = room_el.find("Points")
            points: List[Tuple[float, float]] = []
            if pts_el is not None:
                for pt_el in pts_el.findall("Point"):
                    points.append((_attr_float(pt_el, "x", 0.0), _attr_float(pt_el, "y", 0.0)))
            if len(points) < 3:
                continue
            layer_id = _elem_text(room_el, "LayerId", "")
            room_id = room_el.get("identifier") or _elem_text(room_el, "Identifier", "")
            rooms.append(
                ParsedRoom(
                    identifier=room_id or f"room_{room_idx}",
                    name=_elem_text(room_el, "Name", "") or f"Room {room_idx + 1}",
                    points=points,
                    height=_elem_float(room_el, "Height", 96.0),
                    level_id=_resolve_level_id(layer_id, layer_to_level, default_level_id),
                    floor_type=_elem_text(room_el, "FloorType", "default"),
                    is_slab=_elem_bool(room_el, "IsSlab", False),
                    slab_thickness=_elem_float(room_el, "SlabThickness", 4.0),
                    floor_pattern=_elem_text(room_el, "FloorPattern", "none") or "none",
                    pattern_rotation=_elem_float(room_el, "PatternRotation", 0.0),
                    pattern_scale=max(0.25, min(4.0, _elem_float(room_el, "PatternScale", 1.0))),
                    room_type=_elem_text(room_el, "RoomType", ""),
                    wall_finish=_elem_text(room_el, "WallFinish", "Paint") or "Paint",
                )
            )

    skipped_openings: List[str] = []
    doors: List[ParsedDoor] = []
    doors_elem = root.find("Doors")
    if doors_elem is not None:
        for door_idx, door_el in enumerate(doors_elem.findall("Door")):
            if not _is_visible(door_el):
                continue
            door_id = door_el.get("identifier") or _elem_text(door_el, "Identifier", "") or f"door_{door_idx}"
            wref = door_el.find("WallReference")
            if wref is None:
                skipped_openings.append(f"door:{door_id} (no WallReference)")
                continue
            set_idx = _attr_int(wref, "set_index", -1)
            wall_idx = _attr_int(wref, "wall_index", -1)
            if (set_idx, wall_idx) not in valid_wall_refs:
                skipped_openings.append(f"door:{door_id} (set={set_idx}, wall={wall_idx})")
                continue
            layer_id = _elem_text(door_el, "LayerId", "")
            doors.append(
                ParsedDoor(
                    identifier=door_id,
                    set_index=set_idx,
                    wall_index=wall_idx,
                    ratio=_elem_float(door_el, "AttachedToWallRatio", 0.5),
                    door_type=_elem_text(door_el, "DoorType", "single").lower(),
                    width=_elem_float(door_el, "Width", 36.0),
                    height=_elem_float(door_el, "Height", 80.0),
                    swing=_elem_text(door_el, "Swing", "left").lower(),
                    orientation=_elem_text(door_el, "Orientation", "inswing").lower(),
                    level_id=_resolve_level_id(layer_id, layer_to_level, default_level_id),
                )
            )

    windows: List[ParsedWindow] = []
    windows_elem = root.find("Windows")
    if windows_elem is not None:
        for win_idx, win_el in enumerate(windows_elem.findall("Window")):
            if not _is_visible(win_el):
                continue
            win_id = win_el.get("identifier") or _elem_text(win_el, "Identifier", "") or f"window_{win_idx}"
            wref = win_el.find("WallReference")
            if wref is None:
                skipped_openings.append(f"window:{win_id} (no WallReference)")
                continue
            set_idx = _attr_int(wref, "set_index", -1)
            wall_idx = _attr_int(wref, "wall_index", -1)
            if (set_idx, wall_idx) not in valid_wall_refs:
                skipped_openings.append(f"window:{win_id} (set={set_idx}, wall={wall_idx})")
                continue
            layer_id = _elem_text(win_el, "LayerId", "")
            windows.append(
                ParsedWindow(
                    identifier=win_id,
                    set_index=set_idx,
                    wall_index=wall_idx,
                    ratio=_elem_float(win_el, "AttachedToWallRatio", 0.5),
                    window_type=_elem_text(win_el, "WindowType", "sliding").lower(),
                    width=_elem_float(win_el, "Width", 36.0),
                    height=_elem_float(win_el, "Height", 36.0),
                    level_id=_resolve_level_id(layer_id, layer_to_level, default_level_id),
                )
            )

    wall_level_by_id = {w.identifier: w.level_id for w in walls}
    roofs: List[ParsedRoof] = []
    roofs_elem = root.find("Roofs")
    if roofs_elem is not None:
        def _parse_lines(parent: ET.Element, tag: str) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
            out: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
            container = parent.find(tag)
            if container is None:
                return out
            for el in container.findall("Line"):
                p1 = (_attr_float(el, "x1", 0.0), _attr_float(el, "y1", 0.0))
                p2 = (_attr_float(el, "x2", 0.0), _attr_float(el, "y2", 0.0))
                if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) > 1e-4:
                    out.append((p1, p2))
            return out

        for roof_idx, r_el in enumerate(roofs_elem.findall("Roof")):
            if not _is_visible(r_el):
                continue
            edges: List[ParsedRoofEdge] = []
            edges_el = r_el.find("Edges")
            if edges_el is not None:
                for e_el in edges_el.findall("Edge"):
                    e_pitch = _attr_float(e_el, "pitch_rise", 0.0) if "pitch_rise" in e_el.attrib else None
                    e_oh = _attr_float(e_el, "overhang", 0.0) if "overhang" in e_el.attrib else None
                    edges.append(
                        ParsedRoofEdge(
                            wall_identifier=e_el.get("wall_identifier", ""),
                            edge_type=(e_el.get("edge_type", "eave") or "eave").lower(),
                            pitch_rise=e_pitch,
                            overhang=e_oh,
                        )
                    )

            layer_id = r_el.get("layer_id", "") or ""
            if layer_id and layer_id in layer_to_level and layer_to_level[layer_id]:
                level_id = layer_to_level[layer_id]
            else:
                inferred_lvl = ""
                for edge in edges:
                    if edge.wall_identifier in wall_level_by_id:
                        inferred_lvl = wall_level_by_id[edge.wall_identifier]
                        break
                level_id = inferred_lvl or default_level_id

            outline_pts: List[Tuple[float, float]] = []
            out_el = r_el.find("Outline")
            if out_el is not None:
                for pt_el in out_el.findall("Point"):
                    outline_pts.append((_attr_float(pt_el, "x", 0.0), _attr_float(pt_el, "y", 0.0)))

            roofs.append(
                ParsedRoof(
                    identifier=r_el.get("identifier", "") or f"roof_{roof_idx}",
                    level_id=level_id,
                    layer_id=layer_id,
                    roof_type=(r_el.get("roof_type", "gable") or "gable").lower(),
                    pitch_rise=_attr_float(r_el, "pitch_rise", 6.0),
                    pitch_run=_attr_float(r_el, "pitch_run", 12.0) or 12.0,
                    overhang=_attr_float(r_el, "overhang", 12.0),
                    material=(r_el.get("material", "asphalt_shingle") or "asphalt_shingle").lower(),
                    edges=edges,
                    ridge_lines=_parse_lines(r_el, "RidgeLines"),
                    hip_lines=_parse_lines(r_el, "HipLines"),
                    valley_lines=_parse_lines(r_el, "ValleyLines"),
                    rake_lines=_parse_lines(r_el, "RakeLines"),
                    eave_lines=_parse_lines(r_el, "EaveLines"),
                    outline_points=outline_pts,
                )
            )

    stairs: List[ParsedStair] = []
    stairs_elem = root.find("Stairs")
    if stairs_elem is not None:
        for s_idx, s_el in enumerate(stairs_elem.findall("Stair")):
            if not _is_visible(s_el):
                continue
            layer_id = s_el.get("layer_id", "") or ""
            start_level_id = s_el.get("start_level_id", "") or ""
            end_level_id = s_el.get("end_level_id", "") or ""
            level_id = (
                layer_to_level.get(layer_id, "")
                or start_level_id
                or default_level_id
            )
            stairs.append(
                ParsedStair(
                    identifier=s_el.get("identifier", "") or f"stair_{s_idx}",
                    layer_id=layer_id,
                    level_id=level_id,
                    start_point=(_attr_float(s_el, "start_x", 0.0), _attr_float(s_el, "start_y", 0.0)),
                    direction_angle=_attr_float(s_el, "direction_angle", 0.0),
                    start_level_id=start_level_id or level_id,
                    end_level_id=end_level_id,
                    stair_type=(s_el.get("stair_type", "straight") or "straight").lower(),
                    width=_attr_float(s_el, "width", 36.0),
                    total_rise=_attr_float(s_el, "total_rise", 106.0),
                    riser_height=_attr_float(s_el, "riser_height", 7.57),
                    num_steps=max(1, _attr_int(s_el, "num_steps", 14)),
                    tread_depth=_attr_float(s_el, "tread_depth", 11.0),
                    total_run=_attr_float(s_el, "total_run", 143.0),
                    nosing=_attr_float(s_el, "nosing", 1.0),
                    has_left_rail=(s_el.get("has_left_rail", "True").strip().lower() == "true"),
                    has_right_rail=(s_el.get("has_right_rail", "True").strip().lower() == "true"),
                    rail_height=_attr_float(s_el, "rail_height", 36.0),
                    turn_direction=(s_el.get("turn_direction", "left") or "left").lower(),
                    landing_depth=_attr_float(s_el, "landing_depth", 36.0),
                    steps_before_landing=_attr_int(s_el, "steps_before_landing", 0),
                    winder_count=_attr_int(s_el, "winder_count", 0),
                    opening_clearance=_attr_float(s_el, "opening_clearance", 0.0),
                    inner_radius=_attr_float(s_el, "inner_radius", 6.0),
                    rotation_degrees=_attr_float(s_el, "rotation_degrees", 270.0),
                )
            )

    floor_openings: List[ParsedFloorOpening] = []
    fo_elem = root.find("FloorOpenings")
    if fo_elem is not None:
        for fo_idx, f_el in enumerate(fo_elem.findall("FloorOpening")):
            if not _is_visible(f_el):
                continue
            pts_el = f_el.find("Points")
            pts: List[Tuple[float, float]] = []
            if pts_el is not None:
                for pt_el in pts_el.findall("Point"):
                    pts.append((_attr_float(pt_el, "x", 0.0), _attr_float(pt_el, "y", 0.0)))
            if len(pts) < 3:
                continue
            layer_id = f_el.get("layer_id", "") or ""
            floor_openings.append(
                ParsedFloorOpening(
                    identifier=f_el.get("identifier", "") or f"opening_{fo_idx}",
                    level_id=_resolve_level_id(layer_id, layer_to_level, default_level_id),
                    opening_type=(f_el.get("opening_type", "opening") or "opening").lower(),
                    label=f_el.get("label", "") or "",
                    ceiling_only=(f_el.get("ceiling_only", "False").strip().lower() == "true"),
                    points=pts,
                )
            )

    fixtures: List[ParsedFixture] = []
    fx_elem = root.find("Fixtures")
    if fx_elem is not None:
        for fx_idx, f_el in enumerate(fx_elem.findall("Fixture")):
            if not _is_visible(f_el):
                continue
            layer_id = f_el.get("layer_id", "") or ""
            fixtures.append(
                ParsedFixture(
                    identifier=f_el.get("identifier", "") or f"fixture_{fx_idx}",
                    symbol_type=(f_el.get("symbol_type", "base_cabinet") or "base_cabinet").lower(),
                    category=(f_el.get("category", "") or "").lower(),
                    level_id=_resolve_level_id(layer_id, layer_to_level, default_level_id),
                    layer_id=layer_id,
                    x=_attr_float(f_el, "x", 0.0),
                    y=_attr_float(f_el, "y", 0.0),
                    width=_attr_float(f_el, "width", 24.0),
                    depth=_attr_float(f_el, "depth", 24.0),
                    height=_attr_float(f_el, "height", 34.5),
                    rotation=_attr_float(f_el, "rotation", 0.0),
                    elevation=_attr_float(f_el, "elevation", 0.0),
                    mount_surface=(f_el.get("mount_surface", "auto") or "auto").lower(),
                    has_countertop=(f_el.get("has_countertop", "False").strip().lower() == "true"),
                    countertop_overhang=_attr_float(f_el, "countertop_overhang", 0.0),
                    countertop_thickness=_attr_float(f_el, "countertop_thickness", 1.5),
                    countertop_material=(f_el.get("countertop_material", "quartz") or "quartz").lower(),
                    has_backsplash=(f_el.get("has_backsplash", "True").strip().lower() == "true"),
                    door_swing=(f_el.get("door_swing", "left") or "left").lower(),
                    fill_color=_parse_hex_rgb(f_el.get("fill_color", "")),
                    countertop_color=_parse_hex_rgb(f_el.get("countertop_color", "")),
                )
            )

    cut_lower = root.get("cut_lower_ceiling_under_stairs", "False").strip().lower() == "true"
    north_angle = _attr_float(root, "north_angle", 0.0)

    return ParsedProject(
        levels=levels,
        walls=walls,
        rooms=rooms,
        doors=doors,
        windows=windows,
        roofs=roofs,
        stairs=stairs,
        floor_openings=floor_openings,
        fixtures=fixtures,
        cut_lower_ceiling_under_stairs=cut_lower,
        north_angle=north_angle,
        skipped_openings=skipped_openings,
    )


def compute_plan_center(project: ParsedProject) -> Tuple[float, float]:
    """Return the bounding-box center ``(cx, cy)`` in inches across walls and rooms."""
    xs: List[float] = []
    ys: List[float] = []
    for w in project.walls:
        xs.extend((w.start[0], w.end[0]))
        ys.extend((w.start[1], w.end[1]))
    for r in project.rooms:
        for x, y in r.points:
            xs.append(x)
            ys.append(y)
    if not xs:
        return (0.0, 0.0)
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def inches_to_blender_xy(
    x_in: float, y_in: float, cx: float, cy: float
) -> Tuple[float, float]:
    """Convert EstiSketch 2D Y-down inches to centered Blender Y-up meters."""
    return ((x_in - cx) * INCH_TO_M, -(y_in - cy) * INCH_TO_M)


def tessellate_curved_wall_points(
    start: Tuple[float, float],
    end: Tuple[float, float],
    arc_center: Optional[Tuple[float, float]],
    arc_radius: Optional[float],
    max_seg_deg: float = 12.0,
) -> List[Tuple[float, float]]:
    """Return polyline vertices along a curved wall arc (or ``[start, end]``)."""
    if arc_center is None or arc_radius is None or arc_radius <= 1e-6:
        return [start, end]

    cx, cy = arc_center
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    a1 = math.atan2(end[1] - cy, end[0] - cx)
    delta = (a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi
    if abs(delta) < 1e-4:
        return [start, end]

    steps = max(2, int(math.ceil(math.degrees(abs(delta)) / max_seg_deg)))
    pts = [start]
    for i in range(1, steps):
        t = i / steps
        ang = a0 + delta * t
        pts.append((cx + arc_radius * math.cos(ang), cy + arc_radius * math.sin(ang)))
    pts.append(end)
    return pts


def compute_opening_local_x(ratio: float, wall_len_m: float, width_m: float) -> float:
    """Compute clamped local X start offset along a wall for a centered opening."""
    if wall_len_m <= 0.0:
        return 0.0
    max_x = max(0.0, wall_len_m - max(0.0, width_m))
    raw_x = ratio * wall_len_m - width_m / 2.0
    return max(0.0, min(raw_x, max_x))


@dataclass
class WallOpeningCut:
    """Local span along a single wall segment overlapped by a door or window."""

    wall: ParsedWall
    x_start_m: float
    x_end_m: float
    same_direction: bool
    min_height_m: float


@dataclass
class OpeningChainPlacement:
    """Opening placement across a straight chain of collinear connected walls."""

    x_local_m: float
    width_m: float
    min_height_m: float
    cuts: List[WallOpeningCut]


def collinear_parsed_wall_chain(
    host_pw: ParsedWall,
    all_walls: List[ParsedWall],
    join_tol_in: float = 0.5,
    line_tol_in: float = 0.5,
) -> List[ParsedWall]:
    """Return ``host_pw`` plus all straight same-level walls connected collinearly."""
    hx = host_pw.end[0] - host_pw.start[0]
    hy = host_pw.end[1] - host_pw.start[1]
    host_len = math.hypot(hx, hy)
    if host_pw.is_curved or host_pw.symbolic or host_len <= 1e-6:
        return [host_pw]

    ux, uy = hx / host_len, hy / host_len
    ox, oy = host_pw.start

    def _on_line(w: ParsedWall) -> bool:
        for px, py in (w.start, w.end):
            if abs((px - ox) * uy - (py - oy) * ux) > line_tol_in:
                return False
        return True

    def _close(a: Tuple[float, float], b: Tuple[float, float]) -> bool:
        return math.hypot(a[0] - b[0], a[1] - b[1]) <= join_tol_in

    def _is_candidate(w: ParsedWall) -> bool:
        if w is host_pw or w.symbolic or w.is_curved or w.level_id != host_pw.level_id:
            return False
        if math.hypot(w.end[0] - w.start[0], w.end[1] - w.start[1]) <= 1e-6:
            return False
        return _on_line(w)

    candidates = [w for w in all_walls if _is_candidate(w)]

    chain = [host_pw]
    grew = True
    while grew:
        grew = False
        for cand in list(candidates):
            if any(
                _close(m_pt, c_pt)
                for member in chain
                for m_pt in (member.start, member.end)
                for c_pt in (cand.start, cand.end)
            ):
                chain.append(cand)
                candidates.remove(cand)
                grew = True
    return chain


def resolve_opening_chain_placement(
    host_pw: ParsedWall,
    ratio: float,
    opening_width_in: float,
    all_walls: List[ParsedWall],
) -> OpeningChainPlacement:
    """Resolve placement and per-wall cuts for an opening that may straddle split walls."""
    hx = host_pw.end[0] - host_pw.start[0]
    hy = host_pw.end[1] - host_pw.start[1]
    host_len_in = math.hypot(hx, hy)
    if host_len_in <= 1e-6:
        return OpeningChainPlacement(
            x_local_m=0.0,
            width_m=max(0.1, opening_width_in * INCH_TO_M),
            min_height_m=min(host_pw.height, host_pw.height_at_end) * INCH_TO_M,
            cuts=[],
        )

    ux, uy = hx / host_len_in, hy / host_len_in
    ox, oy = host_pw.start

    def _proj(pt: Tuple[float, float]) -> float:
        return (pt[0] - ox) * ux + (pt[1] - oy) * uy

    chain = collinear_parsed_wall_chain(host_pw, all_walls)
    projected: List[Tuple[ParsedWall, float, float, float, float]] = []
    for w in chain:
        ps = _proj(w.start)
        pe = _proj(w.end)
        projected.append((w, ps, pe, min(ps, pe), max(ps, pe)))

    chain_lo = min(item[3] for item in projected)
    chain_hi = max(item[4] for item in projected)
    chain_len_in = max(0.0, chain_hi - chain_lo)

    width_m = max(0.1, min(opening_width_in * INCH_TO_M, chain_len_in * INCH_TO_M))
    eff_width_in = width_m / INCH_TO_M
    raw_start_in = ratio * host_len_in - eff_width_in / 2.0
    max_start_in = max(chain_lo, chain_hi - eff_width_in)
    open_start_in = max(chain_lo, min(raw_start_in, max_start_in))
    open_end_in = open_start_in + eff_width_in

    cuts: List[WallOpeningCut] = []
    for w, ps, pe, s_lo, s_hi in projected:
        ov_lo = max(open_start_in, s_lo)
        ov_hi = min(open_end_in, s_hi)
        if ov_hi - ov_lo <= 1e-3:
            continue
        w_len_in = abs(pe - ps)
        if w_len_in <= 1e-6:
            continue
        same_dir = pe >= ps
        if same_dir:
            wx0_in = ov_lo - ps
            wx1_in = ov_hi - ps
        else:
            wx0_in = ps - ov_hi
            wx1_in = ps - ov_lo
        wx0_in = max(0.0, min(w_len_in, wx0_in))
        wx1_in = max(0.0, min(w_len_in, wx1_in))
        t0 = wx0_in / w_len_in
        t1 = wx1_in / w_len_in
        h0 = w.height + (w.height_at_end - w.height) * t0
        h1 = w.height + (w.height_at_end - w.height) * t1
        cuts.append(
            WallOpeningCut(
                wall=w,
                x_start_m=wx0_in * INCH_TO_M,
                x_end_m=wx1_in * INCH_TO_M,
                same_direction=same_dir,
                min_height_m=min(h0, h1) * INCH_TO_M,
            )
        )

    min_height_m = (
        min(c.min_height_m for c in cuts)
        if cuts
        else min(host_pw.height, host_pw.height_at_end) * INCH_TO_M
    )
    return OpeningChainPlacement(
        x_local_m=open_start_in * INCH_TO_M,
        width_m=width_m,
        min_height_m=min_height_m,
        cuts=cuts,
    )


@dataclass
class StripSegment:
    """2D oriented strip segment (meters) with offsets along its left normal."""

    p0: Tuple[float, float]
    p1: Tuple[float, float]
    y0: float
    y1: float


def _intersect_2d_lines(
    p: Tuple[float, float],
    dp: Tuple[float, float],
    q: Tuple[float, float],
    dq: Tuple[float, float],
) -> Optional[Tuple[float, float]]:
    """Return intersection of lines ``p + t*dp`` and ``q + u*dq``, or None if parallel."""
    det = dp[0] * dq[1] - dp[1] * dq[0]
    if abs(det) < 1e-5:
        return None
    dx = q[0] - p[0]
    dy = q[1] - p[1]
    t = (dx * dq[1] - dy * dq[0]) / det
    return (p[0] + t * dp[0], p[1] + t * dp[1])


def _is_duplicate_seg(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    q0: Tuple[float, float],
    q1: Tuple[float, float],
    tol: float,
) -> bool:
    """True when two segments share both endpoints in either order within ``tol``."""
    same = math.hypot(p0[0] - q0[0], p0[1] - q0[1]) <= tol
    same_end = math.hypot(p1[0] - q1[0], p1[1] - q1[1]) <= tol
    if same and same_end:
        return True
    swap = math.hypot(p0[0] - q1[0], p0[1] - q1[1]) <= tol
    swap_end = math.hypot(p1[0] - q0[0], p1[1] - q0[1]) <= tol
    return swap and swap_end


def compute_mitered_strip_polygons(
    segments: List[StripSegment],
    join_tol_m: float = 0.015,
    miter_limit: float = 4.0,
) -> List[List[Tuple[float, float]]]:
    """Compute mitered 2D quad polygons for connected 2D strips (footers, rim bands).

    At clean 2-way non-collinear corners, adjacent inner and outer strip edges are
    intersected so corners join seamlessly without gaps or notches. Free ends,
    collinear continuations, duplicate coincident segments, and T-/3-way junctions
    keep square ends.

    Args:
        segments: List of ``StripSegment`` in meters.
        join_tol_m: Endpoint matching tolerance in meters.
        miter_limit: Maximum corner extension as a multiple of strip offset width.

    Returns:
        List of 4-vertex polygons ``[s0, e0, e1, s1]`` parallel to ``segments``
        (or ``[]`` for degenerate zero-length segments).
    """
    meta: List[Optional[Tuple[Tuple[float, float], Tuple[float, float]]]] = []
    for seg in segments:
        dx = seg.p1[0] - seg.p0[0]
        dy = seg.p1[1] - seg.p0[1]
        length = math.hypot(dx, dy)
        if length < 1e-4:
            meta.append(None)
        else:
            d = (dx / length, dy / length)
            n = (-d[1], d[0])
            meta.append((d, n))

    def _pt_close(a: Tuple[float, float], b: Tuple[float, float]) -> bool:
        return math.hypot(a[0] - b[0], a[1] - b[1]) <= join_tol_m

    def _miter_endpoint(
        idx: int,
        pt: Tuple[float, float],
        is_start: bool,
        cur_0: Tuple[float, float],
        cur_1: Tuple[float, float],
    ) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        seg = segments[idx]
        d, n = meta[idx]  # type: ignore[misc]
        non_collinear: List[int] = []
        for j, other in enumerate(segments):
            if j == idx or meta[j] is None:
                continue
            if _is_duplicate_seg(seg.p0, seg.p1, other.p0, other.p1, join_tol_m):
                continue
            if not (_pt_close(other.p0, pt) or _pt_close(other.p1, pt)):
                continue
            od, _ = meta[j]  # type: ignore[misc]
            cross = d[0] * od[1] - d[1] * od[0]
            if abs(cross) < 1e-3:
                return (cur_0, cur_1)
            non_collinear.append(j)

        unique_nbs: List[int] = []
        for j in non_collinear:
            oj = segments[j]
            if not any(
                _is_duplicate_seg(
                    oj.p0, oj.p1, segments[k].p0, segments[k].p1, join_tol_m
                )
                for k in unique_nbs
            ):
                unique_nbs.append(j)

        if len(unique_nbs) != 1:
            return (cur_0, cur_1)

        nb_idx = unique_nbs[0]
        other = segments[nb_idx]
        od, on = meta[nb_idx]  # type: ignore[misc]
        same_flow = _pt_close(other.p1, pt) if is_start else _pt_close(other.p0, pt)
        other_y0, other_y1 = (other.y0, other.y1) if same_flow else (other.y1, other.y0)

        max_off = max(
            abs(seg.y0), abs(seg.y1), abs(other.y0), abs(other.y1), 0.1
        )
        max_dist = miter_limit * max_off

        ix0 = _intersect_2d_lines(
            (pt[0] + n[0] * seg.y0, pt[1] + n[1] * seg.y0),
            d,
            (pt[0] + on[0] * other_y0, pt[1] + on[1] * other_y0),
            od,
        )
        ix1 = _intersect_2d_lines(
            (pt[0] + n[0] * seg.y1, pt[1] + n[1] * seg.y1),
            d,
            (pt[0] + on[0] * other_y1, pt[1] + on[1] * other_y1),
            od,
        )
        out_0 = ix0 if (ix0 is not None and math.hypot(ix0[0] - pt[0], ix0[1] - pt[1]) <= max_dist) else cur_0
        out_1 = ix1 if (ix1 is not None and math.hypot(ix1[0] - pt[0], ix1[1] - pt[1]) <= max_dist) else cur_1
        return (out_0, out_1)

    result: List[List[Tuple[float, float]]] = []
    for idx, seg in enumerate(segments):
        m = meta[idx]
        if m is None:
            result.append([])
            continue
        d, n = m
        sq_s0 = (seg.p0[0] + n[0] * seg.y0, seg.p0[1] + n[1] * seg.y0)
        sq_s1 = (seg.p0[0] + n[0] * seg.y1, seg.p0[1] + n[1] * seg.y1)
        sq_e0 = (seg.p1[0] + n[0] * seg.y0, seg.p1[1] + n[1] * seg.y0)
        sq_e1 = (seg.p1[0] + n[0] * seg.y1, seg.p1[1] + n[1] * seg.y1)

        s0, s1 = _miter_endpoint(idx, seg.p0, True, sq_s0, sq_s1)
        e0, e1 = _miter_endpoint(idx, seg.p1, False, sq_e0, sq_e1)

        dot0 = (e0[0] - s0[0]) * d[0] + (e0[1] - s0[1]) * d[1]
        dot1 = (e1[0] - s1[0]) * d[0] + (e1[1] - s1[1]) * d[1]
        if dot0 <= 1e-5 or dot1 <= 1e-5:
            result.append([sq_s0, sq_e0, sq_e1, sq_s1])
        else:
            result.append([s0, e0, e1, s1])
    return result


def _flip_parsed_wall(pw: ParsedWall, project: ParsedProject) -> None:
    """Reverse a wall's direction while preserving finishes, footers, and openings."""
    pw.start, pw.end = pw.end, pw.start
    pw.height, pw.height_at_end = pw.height_at_end, pw.height
    pw.left_finish, pw.right_finish = pw.right_finish, pw.left_finish
    pw.left_color, pw.right_color = pw.right_color, pw.left_color
    pw.left_baseboard, pw.right_baseboard = pw.right_baseboard, pw.left_baseboard
    pw.footer_left_offset, pw.footer_right_offset = (
        pw.footer_right_offset,
        pw.footer_left_offset,
    )
    key = (pw.set_index, pw.wall_index)
    for pd in project.doors:
        if (pd.set_index, pd.wall_index) == key:
            pd.ratio = 1.0 - pd.ratio
            if pd.orientation == "inswing":
                pd.orientation = "outswing"
            elif pd.orientation == "outswing":
                pd.orientation = "inswing"
            if pd.swing == "left":
                pd.swing = "right"
            elif pd.swing == "right":
                pd.swing = "left"
    for pw_win in project.windows:
        if (pw_win.set_index, pw_win.wall_index) == key:
            pw_win.ratio = 1.0 - pw_win.ratio


def orient_interior_wall_chains(
    project: ParsedProject, join_tol_in: float = 0.5
) -> int:
    """Orient connected interior wall L-/Z-chains head-to-tail for HB5 mitering.

    Only flips straight, non-symbolic interior walls at clean 2-wall non-collinear
    corners (skipping T-junctions and exterior walls). Returns the count of flipped walls.
    """
    walls_by_level: Dict[str, List[ParsedWall]] = {}
    for pw in project.walls:
        if pw.exterior_wall or pw.symbolic or pw.is_curved:
            continue
        if math.hypot(pw.end[0] - pw.start[0], pw.end[1] - pw.start[1]) <= 1e-4:
            continue
        walls_by_level.setdefault(pw.level_id, []).append(pw)

    flipped = 0
    for lvl_walls in walls_by_level.values():
        clusters: List[Tuple[float, float]] = []
        wall_clusters: List[Tuple[int, int]] = []

        def _cluster_id(pt: Tuple[float, float]) -> int:
            for cid, cpt in enumerate(clusters):
                if math.hypot(pt[0] - cpt[0], pt[1] - cpt[1]) <= join_tol_in:
                    return cid
            clusters.append(pt)
            return len(clusters) - 1

        at_cluster: Dict[int, List[int]] = {}
        for idx, pw in enumerate(lvl_walls):
            c_s = _cluster_id(pw.start)
            c_e = _cluster_id(pw.end)
            wall_clusters.append((c_s, c_e))
            at_cluster.setdefault(c_s, []).append(idx)
            if c_e != c_s:
                at_cluster.setdefault(c_e, []).append(idx)

        eligible_corners: Dict[int, Tuple[int, int]] = {}
        adj: Dict[int, List[Tuple[int, int]]] = {i: [] for i in range(len(lvl_walls))}
        for cid, members in at_cluster.items():
            if len(members) != 2:
                continue
            ia, ib = members[0], members[1]
            wa, wb = lvl_walls[ia], lvl_walls[ib]
            dax, day = wa.end[0] - wa.start[0], wa.end[1] - wa.start[1]
            dbx, dby = wb.end[0] - wb.start[0], wb.end[1] - wb.start[1]
            la, lb = math.hypot(dax, day), math.hypot(dbx, dby)
            if la <= 1e-4 or lb <= 1e-4:
                continue
            cross = (dax * dby - day * dbx) / (la * lb)
            if abs(cross) <= 1e-3:
                continue
            eligible_corners[cid] = (ia, ib)
            adj[ia].append((cid, ib))
            adj[ib].append((cid, ia))

        visited: set[int] = set()

        def _walk_from(start_idx: int) -> None:
            nonlocal flipped
            nbs = adj[start_idx]
            if not nbs:
                visited.add(start_idx)
                return
            first_cid = nbs[0][0]
            w0 = lvl_walls[start_idx]
            c_s, c_e = wall_clusters[start_idx]
            if len(nbs) == 1 and c_s == first_cid and c_e != first_cid:
                _flip_parsed_wall(w0, project)
                wall_clusters[start_idx] = (c_e, c_s)
                flipped += 1

            curr = start_idx
            visited.add(curr)
            while True:
                curr_end_cid = wall_clusters[curr][1]
                next_idx = None
                for cid, nb in adj[curr]:
                    if cid == curr_end_cid and nb not in visited:
                        next_idx = nb
                        break
                if next_idx is None:
                    break
                wn = lvl_walls[next_idx]
                nc_s, nc_e = wall_clusters[next_idx]
                if nc_e == curr_end_cid and nc_s != curr_end_cid:
                    _flip_parsed_wall(wn, project)
                    wall_clusters[next_idx] = (nc_e, nc_s)
                    flipped += 1
                visited.add(next_idx)
                curr = next_idx

        for idx in range(len(lvl_walls)):
            if idx not in visited and len(adj[idx]) == 1:
                _walk_from(idx)
        for idx in range(len(lvl_walls)):
            if idx not in visited and len(adj[idx]) >= 1:
                _walk_from(idx)

    return flipped


def solve_hb5_miter_angles(
    a_rot: float,
    a_thick: float,
    b_rot: float,
    b_thick: float,
    max_shear_ratio: float = 8.0,
) -> Tuple[float, float]:
    """Solve HB5 ``(Right Angle on A, Left Angle on B)`` closing outer faces at a corner."""
    turn = b_rot - a_rot
    while turn > math.pi:
        turn -= 2.0 * math.pi
    while turn <= -math.pi:
        turn += 2.0 * math.pi
    if abs(turn) < 1e-6:
        return (0.0, 0.0)

    ca, sa = math.cos(a_rot), math.sin(a_rot)
    cb, sb = math.cos(b_rot), math.sin(b_rot)
    nax, nay = -sa, ca
    nbx, nby = -sb, cb

    det = ca * (-sb) - (-cb) * sa
    if abs(det) < 1e-9:
        return (-turn / 2.0, turn / 2.0)

    rhs_x = b_thick * nbx - a_thick * nax
    rhs_y = b_thick * nby - a_thick * nay
    shear_a = (rhs_x * (-sb) - (-cb) * rhs_y) / det
    shear_b = (ca * rhs_y - rhs_x * sa) / det

    if abs(shear_a) > max_shear_ratio * a_thick or abs(shear_b) > max_shear_ratio * b_thick:
        return (-turn / 2.0, turn / 2.0)

    right_a = math.atan2(shear_a, a_thick) if a_thick else 0.0
    left_b = math.atan2(shear_b, b_thick) if b_thick else 0.0
    return (right_a, left_b)


def compute_level_wall_miters(
    wall_entries: List[Tuple[str, Tuple[float, float], Tuple[float, float], float, bool]],
    join_tol_m: float = 0.015,
) -> Dict[str, Tuple[float, float]]:
    """Compute ``{key: (left_angle, right_angle)}`` for wall segments on one level."""
    left_angles: Dict[str, float] = {item[0]: 0.0 for item in wall_entries}
    right_angles: Dict[str, float] = {item[0]: 0.0 for item in wall_entries}

    dirs: List[Optional[Tuple[float, float, float]]] = []
    for _, p0, p1, _, _ in wall_entries:
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length < 1e-4:
            dirs.append(None)
        else:
            dirs.append((dx / length, dy / length, math.atan2(dy, dx)))

    def _pt_close(a: Tuple[float, float], b: Tuple[float, float]) -> bool:
        return math.hypot(a[0] - b[0], a[1] - b[1]) <= join_tol_m

    def _has_collinear_at(idx: int, pt: Tuple[float, float]) -> bool:
        d_i = dirs[idx]
        if d_i is None:
            return False
        _, p0_i, p1_i, _, _ = wall_entries[idx]
        for j, (_, p0_j, p1_j, _, _) in enumerate(wall_entries):
            if j == idx or dirs[j] is None:
                continue
            if _is_duplicate_seg(p0_i, p1_i, p0_j, p1_j, join_tol_m):
                continue
            if not (_pt_close(p0_j, pt) or _pt_close(p1_j, pt)):
                continue
            d_j = dirs[j]
            assert d_j is not None
            cross = d_i[0] * d_j[1] - d_i[1] * d_j[0]
            if abs(cross) < 1e-3:
                return True
        return False

    for i, (key_a, p0_a, p1_a, thick_a, ext_a) in enumerate(wall_entries):
        d_a = dirs[i]
        if d_a is None or _has_collinear_at(i, p1_a):
            continue

        cands: List[Tuple[int, str, float, float, bool]] = []
        for j, (key_b, p0_b, p1_b, thick_b, ext_b) in enumerate(wall_entries):
            if j == i or dirs[j] is None:
                continue
            if _is_duplicate_seg(p0_a, p1_a, p0_b, p1_b, join_tol_m):
                continue
            if not _pt_close(p0_b, p1_a):
                continue
            d_b = dirs[j]
            assert d_b is not None
            cross = d_a[0] * d_b[1] - d_a[1] * d_b[0]
            if abs(cross) < 1e-3 or _has_collinear_at(j, p0_b):
                continue
            cands.append((j, key_b, thick_b, d_b[2], ext_b))

        same_kind = [c for c in cands if c[4] == ext_a]
        if same_kind:
            cands = same_kind
        if len(cands) == 1:
            _, key_b, thick_b, rot_b, _ = cands[0]
            ra, lb = solve_hb5_miter_angles(d_a[2], thick_a, rot_b, thick_b)
            right_angles[key_a] = ra
            left_angles[key_b] = lb

    return {k: (left_angles[k], right_angles[k]) for k in left_angles}


def compute_sun_rotation_euler(north_angle_deg: float) -> Tuple[float, float, float]:
    """Return Blender sun ``rotation_euler`` adjusted clockwise by project ``north_angle``."""
    return (math.radians(48.0), math.radians(15.0), math.radians(-35.0 - north_angle_deg))


def compute_window_sill_height_m(
    win_height_m: float,
    wall_min_h_m: float,
    head_height_m: float = 80.0 * INCH_TO_M,
) -> float:
    """Compute window sill height so standard & awning windows align cleanly to an ~80\" head."""
    max_sill = max(0.0, wall_min_h_m - win_height_m - 0.05)
    target_head = min(head_height_m, max(win_height_m + 0.05, wall_min_h_m - 0.10))
    return max(0.0, min(target_head - win_height_m, max_sill))


def compute_baseboard_spans(
    wall_len_m: float,
    door_intervals: List[Tuple[float, float]],
    min_span_m: float = 0.03,
) -> List[Tuple[float, float]]:
    """Return uninterrupted ``(start_m, end_m)`` baseboard spans along a wall segment."""
    if wall_len_m < min_span_m:
        return []
    cleaned: List[Tuple[float, float]] = []
    for x0, x1 in door_intervals:
        a = max(0.0, min(x0, x1))
        b = min(wall_len_m, max(x0, x1))
        if b - a > 1e-4:
            cleaned.append((a, b))
    cleaned.sort()

    spans: List[Tuple[float, float]] = []
    cursor = 0.0
    for a, b in cleaned:
        if a - cursor >= min_span_m:
            spans.append((cursor, a))
        cursor = max(cursor, b)
    if wall_len_m - cursor >= min_span_m:
        spans.append((cursor, wall_len_m))
    return spans


def resolve_curved_wall_segment(
    seg_lengths: List[float], ratio: float
) -> Tuple[int, float]:
    """Map an opening ratio ``[0, 1]`` along a multi-segment wall to ``(seg_index, local_ratio)``."""
    if not seg_lengths:
        return (0, 0.5)
    total = sum(seg_lengths)
    if total <= 1e-6:
        return (0, 0.5)
    clamped = max(0.0, min(1.0, ratio))
    target = clamped * total
    acc = 0.0
    for idx, slen in enumerate(seg_lengths):
        if target <= acc + slen + 1e-9 or idx == len(seg_lengths) - 1:
            local_r = (target - acc) / slen if slen > 1e-6 else 0.5
            return (idx, max(0.0, min(1.0, local_r)))
        acc += slen
    return (len(seg_lengths) - 1, 0.5)


@dataclass
class _EavePlaneDef:
    start: Tuple[float, float]
    end: Tuple[float, float]
    inward_normal: Tuple[float, float]
    slope: float
    pitch_rise: float
    z_plate: float

    def elevation_at(self, x: float, y: float) -> float:
        dx = x - self.start[0]
        dy = y - self.start[1]
        return self.z_plate + self.slope * (dx * self.inward_normal[0] + dy * self.inward_normal[1])


def _pt_in_poly_2d(px: float, py: float, poly: List[Tuple[float, float]]) -> bool:
    if len(poly) < 3:
        return False
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-18) + x1):
            inside = not inside
    return inside


def _dist_pt_to_seg_2d(
    p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]
) -> Tuple[float, float]:
    """Return ``(distance, clamped_t)`` from point ``p`` to segment ``a -> b``."""
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        return (math.hypot(p[0] - a[0], p[1] - a[1]), 0.0)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    proj = (a[0] + t * dx, a[1] + t * dy)
    return (math.hypot(p[0] - proj[0], p[1] - proj[1]), t)


def _line_intersect_2d(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    p4: Tuple[float, float],
) -> Optional[Tuple[float, float, float, float]]:
    """Return ``(ix, iy, t, u)`` for lines ``p1->p2`` and ``p3->p4``, or ``None``."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1), t, u)


def _clean_polygon_pts(pts: List[Tuple[float, float]], tol: float = 0.25) -> List[Tuple[float, float]]:
    cleaned: List[Tuple[float, float]] = []
    for pt in pts:
        if not cleaned or math.hypot(pt[0] - cleaned[-1][0], pt[1] - cleaned[-1][1]) > tol:
            cleaned.append((float(pt[0]), float(pt[1])))
    if len(cleaned) >= 2 and math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1]) <= tol:
        cleaned.pop()
    return cleaned


def _order_walls_polygon(walls: List[ParsedWall]) -> List[Tuple[float, float]]:
    """Order bound perimeter walls into a closed 2D loop of vertices."""
    if len(walls) < 3:
        return []
    segs = [(w.start, w.end) for w in walls]
    ordered = [segs[0]]
    rem = list(segs[1:])
    while rem:
        cur_end = ordered[-1][1]
        matched_idx = -1
        flip = False
        best_d = 2.0
        for idx, (s, e) in enumerate(rem):
            ds = math.hypot(s[0] - cur_end[0], s[1] - cur_end[1])
            de = math.hypot(e[0] - cur_end[0], e[1] - cur_end[1])
            if ds < best_d:
                best_d = ds
                matched_idx = idx
                flip = False
            if de < best_d:
                best_d = de
                matched_idx = idx
                flip = True
        if matched_idx < 0:
            break
        s, e = rem.pop(matched_idx)
        ordered.append((e, s) if flip else (s, e))
    if len(ordered) != len(segs):
        return []
    if math.hypot(ordered[-1][1][0] - ordered[0][0][0], ordered[-1][1][1] - ordered[0][0][1]) > 2.0:
        return []
    return _clean_polygon_pts([s for s, _ in ordered])


def _polygon_signed_area_2d(pts: List[Tuple[float, float]]) -> float:
    n = len(pts)
    if n < 3:
        return 0.0
    return 0.5 * sum(
        pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
        for i in range(n)
    )


def _extract_planar_faces(
    outline: List[Tuple[float, float]],
    interior_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]],
    snap_tol: float = 0.75,
) -> Tuple[List[Tuple[float, float]], List[List[int]]]:
    """Decompose an outline polygon + interior roof lines into minimal 2D faces."""
    outline_clean = _clean_polygon_pts(outline, tol=0.25)
    if len(outline_clean) < 3:
        return [], []
    if not interior_lines:
        return outline_clean, [list(range(len(outline_clean)))]

    raw_segs: List[Tuple[Tuple[float, float], Tuple[float, float]]] = [
        (outline_clean[i], outline_clean[(i + 1) % len(outline_clean)])
        for i in range(len(outline_clean))
    ]
    for s, e in interior_lines:
        if math.hypot(e[0] - s[0], e[1] - s[1]) > 0.5:
            raw_segs.append((s, e))

    # Collect initial endpoints + pairwise intersections between segments
    cand_pts: List[Tuple[float, float]] = []
    for s, e in raw_segs:
        cand_pts.append(s)
        cand_pts.append(e)
    for i in range(len(raw_segs)):
        for j in range(i + 1, len(raw_segs)):
            res = _line_intersect_2d(raw_segs[i][0], raw_segs[i][1], raw_segs[j][0], raw_segs[j][1])
            if res is not None:
                ix, iy, t, u = res
                if -0.02 <= t <= 1.02 and -0.02 <= u <= 1.02:
                    cand_pts.append((ix, iy))

    # Cluster into canonical vertices V
    verts: List[Tuple[float, float]] = []

    def _get_vid(pt: Tuple[float, float]) -> int:
        best_i = -1
        best_d = snap_tol
        for vi, v in enumerate(verts):
            d = math.hypot(pt[0] - v[0], pt[1] - v[1])
            if d <= best_d:
                best_d = d
                best_i = vi
        if best_i >= 0:
            return best_i
        verts.append((float(pt[0]), float(pt[1])))
        return len(verts) - 1

    for pt in cand_pts:
        _get_vid(pt)

    # Split each segment at all vertices lying along its span
    edges_set: set[Tuple[int, int]] = set()
    for s, e in raw_segs:
        dx = e[0] - s[0]
        dy = e[1] - s[1]
        seg_len = math.hypot(dx, dy)
        if seg_len <= 1e-4:
            continue
        ux, uy = dx / seg_len, dy / seg_len
        on_seg: List[Tuple[float, int]] = []
        for vi, v in enumerate(verts):
            proj = (v[0] - s[0]) * ux + (v[1] - s[1]) * uy
            if -snap_tol <= proj <= seg_len + snap_tol:
                perp = abs((v[0] - s[0]) * (-uy) + (v[1] - s[1]) * ux)
                if perp <= snap_tol:
                    on_seg.append((proj, vi))
        on_seg.sort(key=lambda item: item[0])
        ordered_vids: List[int] = []
        for _, vi in on_seg:
            if not ordered_vids or ordered_vids[-1] != vi:
                ordered_vids.append(vi)
        for k in range(len(ordered_vids) - 1):
            u_id, v_id = ordered_vids[k], ordered_vids[k + 1]
            if u_id != v_id:
                edge = (u_id, v_id) if u_id < v_id else (v_id, u_id)
                edges_set.add(edge)

    if not edges_set:
        return outline_clean, [list(range(len(outline_clean)))]

    # Build CCW-sorted adjacency lists
    adj: Dict[int, List[int]] = {}
    for u_id, v_id in edges_set:
        adj.setdefault(u_id, []).append(v_id)
        adj.setdefault(v_id, []).append(u_id)
    for u_id, nbrs in adj.items():
        ux, uy = verts[u_id]
        nbrs.sort(key=lambda vid: math.atan2(verts[vid][1] - uy, verts[vid][0] - ux))

    # Half-edge traversal for minimal cycles
    used_dir: set[Tuple[int, int]] = set()
    cycles: List[Tuple[float, List[int]]] = []
    max_steps = len(verts) * 2 + 4
    for u_id, v_id in list(edges_set):
        for start_dir in ((u_id, v_id), (v_id, u_id)):
            if start_dir in used_dir:
                continue
            cur_u, cur_v = start_dir
            face_vids = [cur_u]
            steps = 0
            closed = False
            while steps < max_steps:
                used_dir.add((cur_u, cur_v))
                nbrs = adj.get(cur_v, [])
                if len(nbrs) < 2:
                    break
                pos = nbrs.index(cur_u)
                nxt = nbrs[(pos - 1) % len(nbrs)]
                cur_u, cur_v = cur_v, nxt
                if (cur_u, cur_v) == start_dir:
                    closed = True
                    break
                face_vids.append(cur_u)
                steps += 1
            if closed and len(face_vids) >= 3:
                area = _polygon_signed_area_2d([verts[i] for i in face_vids])
                if abs(area) > 10.0:
                    cycles.append((area, face_vids))

    # In standard XY with CCW-sorted adjacency, interior faces have positive signed area
    # and the outer unbounded cycle has negative signed area.
    interior_faces = [f for area, f in cycles if area > 0.0]
    if not interior_faces and cycles:
        # Fallback if winding inverted: drop single largest-magnitude face
        cycles.sort(key=lambda item: abs(item[0]))
        interior_faces = [f for _, f in cycles[:-1]] or [cycles[0][1]]

    return verts, interior_faces


def solve_roof_3d(roof: ParsedRoof, project: ParsedProject) -> SolvedRoofGeometry:
    """Reconstruct watertight 3D roof facets and gable-end wall infills in inches."""
    level_by_id = {lvl.id: lvl for lvl in project.levels}
    wall_by_id = {w.identifier: w for w in project.walls if not w.symbolic}

    def _wall_plate_z(w: ParsedWall) -> float:
        lvl = level_by_id.get(w.level_id, project.levels[0])
        return lvl.elevation + min(w.height, w.height_at_end)

    def _wall_top_max_z(w: ParsedWall) -> float:
        lvl = level_by_id.get(w.level_id, project.levels[0])
        return lvl.elevation + max(w.height, w.height_at_end)

    bound_walls: List[ParsedWall] = [
        wall_by_id[e.wall_identifier]
        for e in roof.edges
        if e.wall_identifier in wall_by_id
    ]
    eave_edges = [e for e in roof.edges if e.edge_type == "eave"]

    if bound_walls:
        default_z_plate = _wall_plate_z(bound_walls[0])
        for edge in eave_edges:
            if edge.wall_identifier in wall_by_id:
                default_z_plate = _wall_plate_z(wall_by_id[edge.wall_identifier])
                break
    else:
        lvl = level_by_id.get(roof.level_id, project.levels[0])
        default_z_plate = lvl.elevation + lvl.height

    outline = _clean_polygon_pts(roof.outline_points, tol=0.25)
    if len(outline) < 3 and bound_walls:
        xs = [c for w in bound_walls for c in (w.start[0], w.end[0])]
        ys = [c for w in bound_walls for c in (w.start[1], w.end[1])]
        oh = roof.overhang
        outline = [
            (min(xs) - oh, min(ys) - oh),
            (max(xs) + oh, min(ys) - oh),
            (max(xs) + oh, max(ys) + oh),
            (min(xs) - oh, max(ys) + oh),
        ]

    wall_poly = _order_walls_polygon(bound_walls)
    test_poly = wall_poly if len(wall_poly) >= 3 else outline
    test_step = 6.0 if len(wall_poly) >= 3 else max(6.0, roof.overhang + 12.0)
    poly_cx = sum(p[0] for p in outline) / len(outline) if outline else 0.0
    poly_cy = sum(p[1] for p in outline) / len(outline) if outline else 0.0

    # Match eave lines to bound eave edges/walls to obtain per-eave pitch & plate Z
    raw_eave_segs: List[Tuple[Tuple[float, float], Tuple[float, float]]] = list(roof.eave_lines)
    if not raw_eave_segs:
        for edge in eave_edges:
            if edge.wall_identifier in wall_by_id:
                w = wall_by_id[edge.wall_identifier]
                raw_eave_segs.append((w.start, w.end))

    eave_defs: List[_EavePlaneDef] = []
    pitch_run = roof.pitch_run or 12.0
    for s, e in raw_eave_segs:
        dx = e[0] - s[0]
        dy = e[1] - s[1]
        seg_len = math.hypot(dx, dy)
        if seg_len <= 1e-4:
            continue
        mx, my = (s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0

        matched_edge: Optional[ParsedRoofEdge] = None
        matched_wall: Optional[ParsedWall] = None
        best_score = 1e9
        for edge in eave_edges:
            w = wall_by_id.get(edge.wall_identifier)
            if w is None:
                continue
            wmx = (w.start[0] + w.end[0]) / 2.0
            wmy = (w.start[1] + w.end[1]) / 2.0
            d_mid = math.hypot(mx - wmx, my - wmy)
            if d_mid < best_score and d_mid <= max(24.0, w.width + roof.overhang):
                best_score = d_mid
                matched_edge = edge
                matched_wall = w

        p_rise = (
            matched_edge.pitch_rise
            if (matched_edge and matched_edge.pitch_rise is not None)
            else roof.pitch_rise
        )
        slope = p_rise / pitch_run
        z_plate = _wall_plate_z(matched_wall) if matched_wall is not None else default_z_plate

        ux, uy = dx / seg_len, dy / seg_len
        n1 = (-uy, ux)
        n2 = (uy, -ux)
        in1 = _pt_in_poly_2d(mx + test_step * n1[0], my + test_step * n1[1], test_poly)
        in2 = _pt_in_poly_2d(mx + test_step * n2[0], my + test_step * n2[1], test_poly)
        if in1 and not in2:
            n_in = n1
        elif in2 and not in1:
            n_in = n2
        else:
            dot1 = (poly_cx - mx) * n1[0] + (poly_cy - my) * n1[1]
            n_in = n1 if dot1 >= 0.0 else n2

        eave_defs.append(
            _EavePlaneDef(
                start=s,
                end=e,
                inward_normal=n_in,
                slope=slope,
                pitch_rise=p_rise,
                z_plate=z_plate,
            )
        )

    interior_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = (
        list(roof.ridge_lines) + list(roof.hip_lines) + list(roof.valley_lines)
    )

    # Legacy XML fallback (e.g., simple_house.xml where RidgeLines is empty)
    synthesized_ridges: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    if not interior_lines and len(eave_defs) == 2 and len(outline) >= 3:
        ep0, ep1 = eave_defs[0], eave_defs[1]
        a0 = ep0.slope * ep0.inward_normal[0]
        b0 = ep0.slope * ep0.inward_normal[1]
        d0 = ep0.z_plate - (a0 * ep0.start[0] + b0 * ep0.start[1])
        a1 = ep1.slope * ep1.inward_normal[0]
        b1 = ep1.slope * ep1.inward_normal[1]
        d1 = ep1.z_plate - (a1 * ep1.start[0] + b1 * ep1.start[1])
        da, db, dc = a0 - a1, b0 - b1, d0 - d1
        norm2 = da * da + db * db
        if norm2 > 1e-12:
            p0_r = (-dc * da / norm2, -dc * db / norm2)
            p1_r = (p0_r[0] - db, p0_r[1] + da)
            hits: List[Tuple[float, Tuple[float, float]]] = []
            for k in range(len(outline)):
                oa = outline[k]
                ob = outline[(k + 1) % len(outline)]
                res = _line_intersect_2d(p0_r, p1_r, oa, ob)
                if res is not None:
                    ix, iy, t, u = res
                    if -1e-4 <= u <= 1.0 + 1e-4:
                        hits.append((t, (ix, iy)))
            hits.sort(key=lambda item: item[0])
            uniq_hits: List[Tuple[float, float]] = []
            for _, pt in hits:
                if not uniq_hits or math.hypot(pt[0] - uniq_hits[-1][0], pt[1] - uniq_hits[-1][1]) > 0.5:
                    uniq_hits.append(pt)
            if len(uniq_hits) >= 2:
                seg = (uniq_hits[0], uniq_hits[-1])
                interior_lines.append(seg)
                synthesized_ridges.append(seg)

    verts_2d, face_indices = _extract_planar_faces(outline, interior_lines)
    if not verts_2d or not face_indices:
        return SolvedRoofGeometry(roof_id=roof.identifier, level_id=roof.level_id, material=roof.material)

    # Determine governing eave for each planar face
    face_eave: List[Optional[_EavePlaneDef]] = []
    for f_vids in face_indices:
        fcx = sum(verts_2d[vi][0] for vi in f_vids) / len(f_vids)
        fcy = sum(verts_2d[vi][1] for vi in f_vids) / len(f_vids)
        best_eave: Optional[_EavePlaneDef] = None
        best_score = -1e9
        for ep in eave_defs:
            edx = ep.end[0] - ep.start[0]
            edy = ep.end[1] - ep.start[1]
            elen = math.hypot(edx, edy)
            if elen <= 1e-4:
                continue
            eux, euy = edx / elen, edy / elen
            emx, emy = (ep.start[0] + ep.end[0]) / 2.0, (ep.start[1] + ep.end[1]) / 2.0
            inward_d = (fcx - ep.start[0]) * ep.inward_normal[0] + (fcy - ep.start[1]) * ep.inward_normal[1]

            edge_bonus = 0.0
            for k in range(len(f_vids)):
                va = verts_2d[f_vids[k]]
                vb = verts_2d[f_vids[(k + 1) % len(f_vids)]]
                fdx, fdy = vb[0] - va[0], vb[1] - va[1]
                flen = math.hypot(fdx, fdy)
                if flen <= 1e-4:
                    continue
                if abs((fdx / flen) * eux + (fdy / flen) * euy) > 0.98:
                    dist_e, _ = _dist_pt_to_seg_2d((emx, emy), va, vb)
                    if dist_e <= roof.overhang + 16.0:
                        edge_bonus = max(edge_bonus, 1000.0 - dist_e)

            score = edge_bonus + (100.0 - inward_d if inward_d >= -2.0 else -500.0 + inward_d)
            if score > best_score:
                best_score = score
                best_eave = ep
        face_eave.append(best_eave)

    # Evaluate shared vertex heights taking max across incident faces (watertight junctions)
    vert_zs: Dict[int, float] = {}
    for f_idx, f_vids in enumerate(face_indices):
        ep = face_eave[f_idx]
        for vi in f_vids:
            vx, vy = verts_2d[vi]
            z = ep.elevation_at(vx, vy) if ep is not None else default_z_plate
            if vi not in vert_zs or z > vert_zs[vi]:
                vert_zs[vi] = z

    facets: List[SolvedRoofFacet] = []
    for f_idx, f_vids in enumerate(face_indices):
        ep = face_eave[f_idx]
        p_rise = ep.pitch_rise if ep is not None else roof.pitch_rise
        v3d = [(verts_2d[vi][0], verts_2d[vi][1], vert_zs[vi]) for vi in f_vids]
        facets.append(SolvedRoofFacet(vertices_3d=v3d, pitch_rise=p_rise))

    # Automatic gable-end wall infill for flat-topped gable walls without taller walls above
    gable_infills: List[SolvedGableInfill] = []
    ridge_candidates = list(roof.ridge_lines) + synthesized_ridges
    for edge in roof.edges:
        if edge.edge_type != "gable":
            continue
        pw = wall_by_id.get(edge.wall_identifier)
        if pw is None or abs(pw.height - pw.height_at_end) > 2.0:
            continue
        z_base = _wall_top_max_z(pw)
        a = pw.start
        b = pw.end
        w_dx = b[0] - a[0]
        w_dy = b[1] - a[1]
        w_len = math.hypot(w_dx, w_dy)
        if w_len <= 1.0:
            continue
        w_ux, w_uy = w_dx / w_len, w_dy / w_len

        # Skip if another collinear wall rises directly above this gable wall (e.g., 2nd story)
        covered_by_upper = False
        for ow in project.walls:
            if ow.symbolic or ow.identifier == pw.identifier:
                continue
            o_base = level_by_id.get(ow.level_id, project.levels[0]).elevation
            o_top = _wall_top_max_z(ow)
            if o_base > z_base + 14.0 or o_top <= z_base + 12.0:
                continue
            odx = ow.end[0] - ow.start[0]
            ody = ow.end[1] - ow.start[1]
            olen = math.hypot(odx, ody)
            if olen <= 1.0:
                continue
            if abs((odx / olen) * w_ux + (ody / olen) * w_uy) < 0.98:
                continue
            perp = abs((ow.start[0] - a[0]) * (-w_uy) + (ow.start[1] - a[1]) * w_ux)
            if perp > max(pw.width, ow.width) + 2.0:
                continue
            p0 = (ow.start[0] - a[0]) * w_ux + (ow.start[1] - a[1]) * w_uy
            p1 = (ow.end[0] - a[0]) * w_ux + (ow.end[1] - a[1]) * w_uy
            overlap = min(w_len, max(p0, p1)) - max(0.0, min(p0, p1))
            if overlap >= 0.5 * w_len:
                covered_by_upper = True
                break
        if covered_by_upper:
            continue

        # Find ridge intersection point along gable wall A -> B
        p_peak: Optional[Tuple[float, float]] = None
        for r_s, r_e in ridge_candidates:
            res = _line_intersect_2d(a, b, r_s, r_e)
            if res is None:
                continue
            ix, iy, t_wall, u_ridge = res
            if 0.05 < t_wall < 0.95 and -0.05 <= u_ridge <= 1.05:
                p_peak = (ix, iy)
                break
        if p_peak is None:
            p_peak = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)

        # Evaluate roof elevation at p_peak along solved facet edges or eave planes
        z_peak = z_base
        for facet in facets:
            fverts = facet.vertices_3d
            for k in range(len(fverts)):
                v0 = fverts[k]
                v1 = fverts[(k + 1) % len(fverts)]
                dist, t_seg = _dist_pt_to_seg_2d(p_peak, (v0[0], v0[1]), (v1[0], v1[1]))
                if dist <= 1.5:
                    z_eval = v0[2] + t_seg * (v1[2] - v0[2])
                    if z_eval > z_peak:
                        z_peak = z_eval
        if z_peak <= z_base + 0.5 and eave_defs:
            z_peak = max(ep.elevation_at(p_peak[0], p_peak[1]) for ep in eave_defs)

        if z_peak > z_base + 2.0:
            gable_infills.append(
                SolvedGableInfill(
                    p_start=a,
                    p_end=b,
                    p_peak=p_peak,
                    z_base=z_base,
                    z_peak=z_peak,
                    thickness=pw.width,
                    level_id=pw.level_id,
                )
            )

    return SolvedRoofGeometry(
        roof_id=roof.identifier,
        level_id=roof.level_id,
        material=roof.material,
        facets=facets,
        gable_infills=gable_infills,
    )


def _l_stair_layout_in(
    total_steps: int,
    steps_before_landing: int,
    tread_depth: float,
    landing_depth: float,
    width: float,
    winder_count: int = 0,
) -> Dict[str, float]:
    """Compute flight step counts and run lengths for an L-shaped stair."""
    winders = max(0, min(int(winder_count or 0), 5, max(total_steps - 2, 0)))
    flight_total = max(1, total_steps - winders)
    if 0 < steps_before_landing < flight_total:
        steps_before = steps_before_landing
    else:
        steps_before = flight_total // 2
    steps_after = flight_total - steps_before
    if winders > 0:
        run_before = steps_before * tread_depth
        run_after = steps_after * tread_depth
        actual_ld = width
    else:
        run_before = (steps_before - 1) * tread_depth if steps_before > 0 else 0.0
        run_after = (steps_after - 1) * tread_depth if steps_after > 0 else 0.0
        actual_ld = landing_depth
    return {
        "steps_before": steps_before,
        "steps_after": steps_after,
        "run_before": run_before,
        "run_after": run_after,
        "landing_depth": actual_ld,
        "winder_count": winders,
    }


def _winder_tread_polys_local(
    width: float, count: int, turn: str = "left"
) -> List[List[Tuple[float, float]]]:
    """Return wedge polygons tiling a ``width x width`` turn square."""
    if count < 1:
        return []

    def _bpt(phi: float) -> Tuple[float, float]:
        if phi <= math.pi / 4.0 + 1e-12:
            return (width, width * math.tan(phi))
        return (width / math.tan(phi), width)

    polys: List[List[Tuple[float, float]]] = []
    for i in range(count):
        phi_hi = (math.pi / 2.0) * (1.0 - i / count)
        phi_lo = (math.pi / 2.0) * (1.0 - (i + 1) / count)
        pts: List[Tuple[float, float]] = [(0.0, 0.0), _bpt(phi_hi)]
        if phi_lo < math.pi / 4.0 < phi_hi:
            pts.append((width, width))
        pts.append(_bpt(phi_lo))
        polys.append(pts)
    if turn == "right":
        polys = [[(u, width - v) for (u, v) in poly] for poly in polys]
    return polys


def _expand_convex_poly_2d(
    poly: List[Tuple[float, float]], margin: float
) -> List[Tuple[float, float]]:
    if margin <= 1e-6 or len(poly) < 3:
        return poly
    pts = list(poly)
    if _polygon_signed_area_2d(pts) < 0:
        pts.reverse()
    n = len(pts)
    lines = []
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        d = math.hypot(dx, dy) or 1.0
        nx, ny = dy / d, -dx / d
        lines.append(((x1 + nx * margin, y1 + ny * margin), (x2 + nx * margin, y2 + ny * margin)))
    out: List[Tuple[float, float]] = []
    for i in range(n):
        p1, p2 = lines[i - 1]
        p3, p4 = lines[i]
        res = _line_intersect_2d(p1, p2, p3, p4)
        out.append((res[0], res[1]) if res is not None else p3)
    return out


def compute_stair_footprint_parts(stair: ParsedStair) -> List[List[Tuple[float, float]]]:
    """Return convex footprint polygon(s) in EstiSketch inches for ``stair``."""
    width = max(12.0, stair.width)
    hw = width / 2.0
    sx, sy = stair.start_point
    ang = stair.direction_angle
    ca, sa = math.cos(ang), math.sin(ang)

    def _xf(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        return [(sx + u * ca - v * sa, sy + u * sa + v * ca) for u, v in pts]

    def _rect(u0: float, v0: float, u1: float, v1: float) -> List[Tuple[float, float]]:
        return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]

    def _sub(ox: float, oy: float, rot: float, pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        cr, sr = math.cos(rot), math.sin(rot)
        return [(ox + a * cr - b * sr, oy + a * sr + b * cr) for a, b in pts]

    stype = stair.stair_type
    if stype == "spiral":
        r = max(6.0, stair.inner_radius) + width
        n = 24
        parts = [[
            (sx + r * math.cos(2.0 * math.pi * i / n), sy + r * math.sin(2.0 * math.pi * i / n))
            for i in range(n)
        ]]
    elif stype == "l-shaped":
        lay = _l_stair_layout_in(
            stair.num_steps,
            stair.steps_before_landing,
            stair.tread_depth,
            stair.landing_depth,
            width,
            stair.winder_count,
        )
        rb, ra, ld = lay["run_before"], lay["run_after"], lay["landing_depth"]
        local: List[List[Tuple[float, float]]] = []
        if rb > 0:
            local.append(_rect(0.0, -hw, rb, hw))
        local.append(_rect(rb, -hw, rb + ld, hw))
        if ra > 0:
            if stair.turn_direction == "left":
                local.append(_sub(rb + ld - hw, -hw, -math.pi / 2.0, _rect(0.0, -hw, ra, hw)))
            else:
                local.append(_sub(rb + ld - hw, hw, math.pi / 2.0, _rect(0.0, -hw, ra, hw)))
        parts = [_xf(p) for p in local]
    elif stype == "u-shaped":
        ld = stair.landing_depth or width
        well = max(0.0, stair.inner_radius if stair.inner_radius != 6.0 else 0.0)
        total = stair.num_steps
        before = stair.steps_before_landing if 0 < stair.steps_before_landing < total else total // 2
        after = total - before
        rb = (before - 1) * stair.tread_depth if before > 0 else 0.0
        ra = (after - 1) * stair.tread_depth if after > 0 else 0.0
        span = 2.0 * width + well
        local = []
        if rb > 0:
            local.append(_rect(0.0, -hw, rb, hw))
        if stair.turn_direction == "left":
            local.append(_rect(rb, -hw - well - width, rb + ld, -hw - well - width + span))
            ox, oy = rb, -(width + well)
        else:
            local.append(_rect(rb, -hw, rb + ld, -hw + span))
            ox, oy = rb, width + well
        if ra > 0:
            local.append(_sub(ox, oy, math.pi, _rect(0.0, -hw, ra, hw)))
        parts = [_xf(p) for p in local]
    else:
        run = max(stair.tread_depth, stair.total_run)
        parts = [_xf(_rect(0.0, -hw, run, hw))]

    margin = max(0.0, stair.opening_clearance)
    if margin > 0.0:
        parts = [_expand_convex_poly_2d(p, margin) for p in parts]
    return parts


def _polys_overlap_2d(poly_a: List[Tuple[float, float]], poly_b: List[Tuple[float, float]]) -> bool:
    """Fast 2D overlap test (AABB + vertex/centroid containment + edge intersection)."""
    if len(poly_a) < 3 or len(poly_b) < 3:
        return False
    ax0, ax1 = min(p[0] for p in poly_a), max(p[0] for p in poly_a)
    ay0, ay1 = min(p[1] for p in poly_a), max(p[1] for p in poly_a)
    bx0, bx1 = min(p[0] for p in poly_b), max(p[0] for p in poly_b)
    by0, by1 = min(p[1] for p in poly_b), max(p[1] for p in poly_b)
    if ax1 < bx0 - 1e-3 or bx1 < ax0 - 1e-3 or ay1 < by0 - 1e-3 or by1 < ay0 - 1e-3:
        return False
    for pt in poly_a:
        if _pt_in_poly_2d(pt[0], pt[1], poly_b):
            return True
    for pt in poly_b:
        if _pt_in_poly_2d(pt[0], pt[1], poly_a):
            return True
    ca = (sum(p[0] for p in poly_a) / len(poly_a), sum(p[1] for p in poly_a) / len(poly_a))
    cb = (sum(p[0] for p in poly_b) / len(poly_b), sum(p[1] for p in poly_b) / len(poly_b))
    if _pt_in_poly_2d(ca[0], ca[1], poly_b) or _pt_in_poly_2d(cb[0], cb[1], poly_a):
        return True
    for i in range(len(poly_a)):
        a0, a1 = poly_a[i], poly_a[(i + 1) % len(poly_a)]
        for j in range(len(poly_b)):
            b0, b1 = poly_b[j], poly_b[(j + 1) % len(poly_b)]
            res = _line_intersect_2d(a0, a1, b0, b1)
            if res is not None and 0.0 <= res[2] <= 1.0 and 0.0 <= res[3] <= 1.0:
                return True
    return False


def compute_room_hole_cutouts(project: ParsedProject) -> Dict[str, List[RoomHoleCutout]]:
    """Compute floor and ceiling cutouts per room ID from stairs and manual floor openings."""
    out: Dict[str, List[RoomHoleCutout]] = {}
    rooms_by_level: Dict[str, List[ParsedRoom]] = {}
    for room in project.rooms:
        rooms_by_level.setdefault(room.level_id, []).append(room)
    sorted_levels = sorted(project.levels, key=lambda l: l.elevation)

    for stair in project.stairs:
        parts = compute_stair_footprint_parts(stair)
        src = f"stair:{stair.identifier}"
        if stair.end_level_id:
            for room in rooms_by_level.get(stair.end_level_id, []):
                for part in parts:
                    if _polys_overlap_2d(room.points, part):
                        out.setdefault(room.identifier, []).append(
                            RoomHoleCutout(points=part, cuts_floor=True, cuts_ceiling=False, source_id=src)
                        )
        should_cut_ceil = (
            bool(stair.start_level_id)
            and (stair.start_level_id != stair.end_level_id or project.cut_lower_ceiling_under_stairs)
        )
        if should_cut_ceil:
            for room in rooms_by_level.get(stair.start_level_id, []):
                for part in parts:
                    if _polys_overlap_2d(room.points, part):
                        out.setdefault(room.identifier, []).append(
                            RoomHoleCutout(points=part, cuts_floor=False, cuts_ceiling=True, source_id=src)
                        )

    for fo in project.floor_openings:
        src = f"opening:{fo.identifier}"
        for room in rooms_by_level.get(fo.level_id, []):
            if _polys_overlap_2d(room.points, fo.points):
                out.setdefault(room.identifier, []).append(
                    RoomHoleCutout(
                        points=list(fo.points),
                        cuts_floor=not fo.ceiling_only,
                        cuts_ceiling=fo.ceiling_only,
                        source_id=src,
                    )
                )
        if not fo.ceiling_only:
            cur_lvl = next((l for l in sorted_levels if l.id == fo.level_id), None)
            if cur_lvl is not None:
                below = [l for l in sorted_levels if l.elevation < cur_lvl.elevation - 1e-3]
                if below:
                    lower_lvl = below[-1]
                    for room in rooms_by_level.get(lower_lvl.id, []):
                        if _polys_overlap_2d(room.points, fo.points):
                            out.setdefault(room.identifier, []).append(
                                RoomHoleCutout(
                                    points=list(fo.points),
                                    cuts_floor=False,
                                    cuts_ceiling=True,
                                    source_id=src,
                                )
                            )
    return out


def compute_hb5_stair_transform(
    stair: ParsedStair, z_start_in: float, cx: float, cy: float
) -> Tuple[Tuple[float, float, float], float]:
    """Convert EstiSketch bottom-center stair pose to HB5 bottom-left ``(loc_m, rot_z_rad)``."""
    sx_m, sy_m = inches_to_blender_xy(stair.start_point[0], stair.start_point[1], cx, cy)
    theta_b = -stair.direction_angle
    rot_z = theta_b - math.pi / 2.0
    half_w_m = (stair.width * INCH_TO_M) / 2.0
    loc_x = sx_m - half_w_m * math.sin(theta_b)
    loc_y = sy_m + half_w_m * math.cos(theta_b)
    loc_z = z_start_in * INCH_TO_M
    return ((loc_x, loc_y, loc_z), rot_z)


def compute_stair_railing_paths_3d(
    stair: ParsedStair, z_start_in: float
) -> List[List[Tuple[float, float, float]]]:
    """Return 3D railing base polylines ``[(x_in, y_in, z_in), ...]`` in EstiSketch world inches."""
    if not stair.has_left_rail and not stair.has_right_rail:
        return []

    width = max(12.0, stair.width)
    hw = width / 2.0
    total_rise = max(6.0, stair.total_rise)
    z0 = z_start_in
    z1 = z_start_in + total_rise
    sx, sy = stair.start_point
    ang = stair.direction_angle
    ca, sa = math.cos(ang), math.sin(ang)

    def _w(u: float, v: float, z: float) -> Tuple[float, float, float]:
        return (sx + u * ca - v * sa, sy + u * sa + v * ca, z)

    left_3d: List[List[Tuple[float, float, float]]] = []
    right_3d: List[List[Tuple[float, float, float]]] = []
    stype = stair.stair_type

    if stype == "straight":
        run = max(stair.tread_depth, stair.total_run)
        left_3d.append([_w(0.0, -hw, z0), _w(run, -hw, z1)])
        right_3d.append([_w(0.0, hw, z0), _w(run, hw, z1)])

    elif stype == "l-shaped":
        lay = _l_stair_layout_in(
            stair.num_steps,
            stair.steps_before_landing,
            stair.tread_depth,
            stair.landing_depth,
            width,
            stair.winder_count,
        )
        sb = lay["steps_before"]
        sa_cnt = lay["steps_after"]
        rb = lay["run_before"]
        ra = lay["run_after"]
        ld = lay["landing_depth"]
        wc = lay["winder_count"]
        tot_steps = max(1, sb + wc + sa_cnt)
        z_land_s = z0 + total_rise * (sb / tot_steps)
        z_land_e = z0 + total_rise * ((sb + wc) / tot_steps) if wc > 0 else z_land_s

        if stair.turn_direction == "left":
            right_3d.append([
                _w(0.0, hw, z0),
                _w(rb, hw, z_land_s),
                _w(rb + ld, hw, 0.5 * (z_land_s + z_land_e)),
                _w(rb + ld, -hw, z_land_e),
                _w(rb + ld, -hw - ra, z1),
            ])
            left_3d.append([
                _w(0.0, -hw, z0),
                _w(rb, -hw, z_land_s),
                _w(rb, -hw, z_land_e),
                _w(rb, -hw - ra, z1),
            ])
        else:
            left_3d.append([
                _w(0.0, -hw, z0),
                _w(rb, -hw, z_land_s),
                _w(rb + ld, -hw, 0.5 * (z_land_s + z_land_e)),
                _w(rb + ld, hw, z_land_e),
                _w(rb + ld, hw + ra, z1),
            ])
            right_3d.append([
                _w(0.0, hw, z0),
                _w(rb, hw, z_land_s),
                _w(rb, hw, z_land_e),
                _w(rb, hw + ra, z1),
            ])

    elif stype == "u-shaped":
        ld = stair.landing_depth or width
        well = max(0.0, stair.inner_radius if stair.inner_radius != 6.0 else 0.0)
        tot = stair.num_steps
        sb = stair.steps_before_landing if 0 < stair.steps_before_landing < tot else tot // 2
        sa_cnt = tot - sb
        rb = (sb - 1) * stair.tread_depth if sb > 0 else 0.0
        ra = (sa_cnt - 1) * stair.tread_depth if sa_cnt > 0 else 0.0
        z_land = z0 + total_rise * (sb / max(1, tot))
        if stair.turn_direction == "left":
            oy = -width - well - hw
            iy = -hw - well
            right_3d.append([
                _w(0.0, hw, z0),
                _w(rb, hw, z_land),
                _w(rb + ld, hw, z_land),
                _w(rb + ld, oy, z_land),
                _w(rb, oy, z_land),
                _w(rb - ra, oy, z1),
            ])
            left_3d.append([
                _w(0.0, -hw, z0),
                _w(rb, -hw, z_land),
                _w(rb, iy, z_land),
                _w(rb - ra, iy, z1),
            ])
        else:
            oy = width + well + hw
            iy = hw + well
            left_3d.append([
                _w(0.0, -hw, z0),
                _w(rb, -hw, z_land),
                _w(rb + ld, -hw, z_land),
                _w(rb + ld, oy, z_land),
                _w(rb, oy, z_land),
                _w(rb - ra, oy, z1),
            ])
            right_3d.append([
                _w(0.0, hw, z0),
                _w(rb, hw, z_land),
                _w(rb, iy, z_land),
                _w(rb - ra, iy, z1),
            ])

    elif stype == "spiral":
        inner_r = max(2.0, stair.inner_radius)
        outer_r = inner_r + width
        rot_rad = math.radians(stair.rotation_degrees or 270.0)
        dir_mult = -1.0 if stair.turn_direction == "left" else 1.0
        steps = max(12, int((stair.rotation_degrees or 270.0) / 15.0))
        inner_pts: List[Tuple[float, float, float]] = []
        outer_pts: List[Tuple[float, float, float]] = []
        for i in range(steps + 1):
            frac = i / steps
            theta = ang + frac * rot_rad * dir_mult
            z_cur = z0 + frac * total_rise
            inner_pts.append((sx + inner_r * math.cos(theta), sy + inner_r * math.sin(theta), z_cur))
            outer_pts.append((sx + outer_r * math.cos(theta), sy + outer_r * math.sin(theta), z_cur))
        if stair.turn_direction == "left":
            if inner_r >= 4.0:
                left_3d.append(inner_pts)
            right_3d.append(outer_pts)
        else:
            left_3d.append(outer_pts)
            if inner_r >= 4.0:
                right_3d.append(inner_pts)

    paths: List[List[Tuple[float, float, float]]] = []
    if stair.has_left_rail:
        paths.extend(left_3d)
    if stair.has_right_rail:
        paths.extend(right_3d)
    return paths


def compute_hb5_fixture_transform(
    fx: ParsedFixture, level_elev_in: float, cx: float, cy: float
) -> Tuple[Tuple[float, float, float], float]:
    """Convert centered EstiSketch fixture pose to HB5 back-left ``(loc_m, rot_z_rad)``."""
    r = math.radians(fx.rotation)
    ca, sa = math.cos(r), math.sin(r)
    lx, ly = -fx.width / 2.0, -fx.depth / 2.0
    bl_x = fx.x + lx * ca - ly * sa
    bl_y = fx.y + lx * sa + ly * ca
    loc_x, loc_y = inches_to_blender_xy(bl_x, bl_y, cx, cy)
    loc_z = (level_elev_in + fx.elevation) * INCH_TO_M
    return ((loc_x, loc_y, loc_z), -r)


def compute_centered_fixture_transform(
    fx: ParsedFixture, level_elev_in: float, cx: float, cy: float
) -> Tuple[Tuple[float, float, float], float]:
    """Convert centered EstiSketch fixture pose to centered Blender ``(loc_m, rot_z_rad)``."""
    cx_m, cy_m = inches_to_blender_xy(fx.x, fx.y, cx, cy)
    loc_z = (level_elev_in + fx.elevation) * INCH_TO_M
    return ((cx_m, cy_m, loc_z), -math.radians(fx.rotation))


# ---------------------------------------------------------------------------
# Layer 2: Blender + Home Builder 5 scene builder (lazy bpy import)
# ---------------------------------------------------------------------------


def find_hb5_package() -> str:
    """Return the enabled ``home_builder_5`` addon module name in Blender."""
    import bpy

    for key in bpy.context.preferences.addons.keys():
        if key == "home_builder_5" or key.endswith(".home_builder_5"):
            return key
    raise RuntimeError(
        "Home Builder 5 extension is not enabled in Blender. "
        "Enable 'Home Builder 5' in Edit > Preferences > Get Extensions / Add-ons."
    )


def _ensure_collection(name: str, parent) -> "bpy.types.Collection":
    import bpy

    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        parent.children.link(col)
    elif col.name not in [c.name for c in parent.children]:
        parent.children.link(col)
    return col


def _move_object_to_collection(obj, target_col) -> None:
    if target_col not in obj.users_collection:
        target_col.objects.link(obj)
    for col in list(obj.users_collection):
        if col != target_col:
            col.objects.unlink(obj)


def _clear_default_scene(scene) -> None:
    import bpy

    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _ensure_sun_light(scene, target_col, north_angle: float = 0.0) -> None:
    import bpy

    light_data = bpy.data.lights.new(name="EstiSketch Sun", type="SUN")
    light_data.energy = 2.5
    light_obj = bpy.data.objects.new(name="EstiSketch Sun", object_data=light_data)
    light_obj.rotation_euler = compute_sun_rotation_euler(north_angle)
    target_col.objects.link(light_obj)


_WALL_FINISH_PRESETS: Dict[str, Tuple[str, Tuple[float, float, float], Optional[Tuple[float, float, float]], float, dict]] = {
    "drywall": ("SOLID", (0.91, 0.90, 0.87), None, 0.72, {}),
    "painted drywall": ("SOLID", (0.91, 0.90, 0.87), None, 0.65, {}),
    "plaster": ("SOLID", (0.90, 0.87, 0.82), None, 0.78, {}),
    "tile": ("TILE", (0.92, 0.92, 0.91), (0.65, 0.65, 0.64), 0.18, {"tile_w": 6 * INCH_TO_M, "tile_h": 3 * INCH_TO_M, "running_bond": True}),
    "t&g wood": ("WOOD", (0.60, 0.43, 0.27), (0.45, 0.30, 0.17), 0.45, {"tile_h": 5 * INCH_TO_M}),
    "wainscoting": ("WOOD", (0.88, 0.87, 0.84), (0.76, 0.75, 0.72), 0.42, {"tile_h": 4 * INCH_TO_M}),
    "vinyl siding": ("TILE", (0.76, 0.79, 0.81), (0.58, 0.61, 0.64), 0.52, {"tile_w": 2.4, "tile_h": 7 * INCH_TO_M, "running_bond": False, "grout_size": 0.006}),
    "hardie lap siding": ("TILE", (0.62, 0.66, 0.64), (0.44, 0.48, 0.46), 0.62, {"tile_w": 2.4, "tile_h": 7 * INCH_TO_M, "running_bond": False, "grout_size": 0.007}),
    "stucco": ("SOLID", (0.84, 0.79, 0.70), None, 0.88, {}),
    "brick": ("TILE", (0.55, 0.24, 0.17), (0.72, 0.70, 0.66), 0.82, {"tile_w": 8 * INCH_TO_M, "tile_h": 2.67 * INCH_TO_M, "running_bond": True, "grout_size": 0.010}),
    "stone veneer": ("STONE", (0.54, 0.52, 0.48), (0.36, 0.34, 0.32), 0.82, {}),
    "exposed concrete": ("SOLID", (0.56, 0.56, 0.55), None, 0.85, {}),
    "none": ("SOLID", (0.68, 0.58, 0.42), None, 0.80, {}),
}


def _resolve_wall_side_finishes(pw: ParsedWall) -> Tuple[str, str]:
    lf = pw.left_finish or "Drywall"
    rf = pw.right_finish or "Drywall"
    if (
        pw.exterior_wall
        and lf.lower() == "drywall"
        and rf.lower() == "drywall"
        and pw.exterior_finish
        and "drywall" not in pw.exterior_finish.lower()
    ):
        rf = pw.exterior_finish
    return (lf, rf)


def _get_or_create_wall_finish_material(
    finish_name: str,
    color_rgb: Optional[Tuple[float, float, float]],
    surface_materials,
    fallback_mat=None,
):
    import bpy

    key = (finish_name or "drywall").strip().lower()
    preset = _WALL_FINISH_PRESETS.get(key)
    if preset is None:
        if "siding" in key:
            preset = _WALL_FINISH_PRESETS["hardie lap siding"]
        elif "stucco" in key:
            preset = _WALL_FINISH_PRESETS["stucco"]
        elif "brick" in key:
            preset = _WALL_FINISH_PRESETS["brick"]
        elif "stone" in key:
            preset = _WALL_FINISH_PRESETS["stone veneer"]
        elif "tile" in key:
            preset = _WALL_FINISH_PRESETS["tile"]
        elif "wood" in key:
            preset = _WALL_FINISH_PRESETS["t&g wood"]
        elif "concrete" in key:
            preset = _WALL_FINISH_PRESETS["exposed concrete"]
        elif color_rgb is None and fallback_mat is not None:
            return fallback_mat
        else:
            preset = _WALL_FINISH_PRESETS["drywall"]

    style, base_srgb, accent_srgb, rough, extra = preset
    if color_rgb is not None:
        base_srgb = color_rgb
        if accent_srgb is not None:
            accent_srgb = tuple(max(0.0, c * 0.72) for c in color_rgb)
        hex_tag = "".join(f"{int(round(max(0.0, min(1.0, c)) * 255)):02x}" for c in color_rgb)
    else:
        hex_tag = "default"

    slug = "".join(ch if ch.isalnum() else "_" for ch in key).strip("_") or "drywall"
    mat_id = f"EstiSketch_Wall_{slug}_{hex_tag}"
    existing = bpy.data.materials.get(mat_id)
    if existing is not None:
        return existing

    mat = surface_materials.build_surface_material(
        mat_id, style, base_srgb, accent_srgb, rough, **extra
    )
    mat.diffuse_color = (*base_srgb, 1.0)
    return mat


def _assign_wall_materials(
    wall, scene, pw: Optional[ParsedWall] = None, surface_materials=None
) -> None:
    fallback = getattr(scene.home_builder, "wall_material", None)
    if pw is not None and surface_materials is not None:
        lf, rf = _resolve_wall_side_finishes(pw)
        left_mat = _get_or_create_wall_finish_material(
            lf, pw.left_color, surface_materials, fallback
        )
        right_mat = _get_or_create_wall_finish_material(
            rf, pw.right_color, surface_materials, fallback
        )
        edge_mat = right_mat if pw.exterior_wall else left_mat
    else:
        left_mat = right_mat = edge_mat = fallback

    if left_mat is not None and wall.has_input("Left Edge"):
        wall.set_input("Left Edge", left_mat)
    if right_mat is not None and wall.has_input("Right Edge"):
        wall.set_input("Right Edge", right_mat)

    if edge_mat is not None:
        for slot in (
            "Top Surface",
            "Bottom Surface",
            "Inside Face",
            "Outside Face",
            "Left Surface",
            "Right Surface",
            "Front Surface",
            "Back Surface",
        ):
            if wall.has_input(slot):
                wall.set_input(slot, edge_mat)


_FLOOR_PATTERN_PRESETS: Dict[str, Tuple[str, Tuple[float, float, float], Optional[Tuple[float, float, float]], float, dict]] = {
    "wood_plank": ("WOOD", (0.58, 0.42, 0.27), (0.42, 0.28, 0.16), 0.38, {"tile_h": 0.14}),
    "herringbone": ("WOOD", (0.55, 0.39, 0.24), (0.39, 0.26, 0.15), 0.36, {"tile_h": 0.10}),
    "chevron": ("WOOD", (0.60, 0.44, 0.28), (0.44, 0.30, 0.17), 0.36, {"tile_h": 0.11}),
    "vinyl_plank": ("WOOD", (0.65, 0.56, 0.44), (0.50, 0.42, 0.32), 0.35, {"tile_h": 0.18}),
    "tile_12": ("TILE", (0.84, 0.82, 0.78), (0.55, 0.54, 0.52), 0.25, {"tile_w": 12 * INCH_TO_M, "tile_h": 12 * INCH_TO_M, "running_bond": False}),
    "tile_18": ("TILE", (0.85, 0.83, 0.79), (0.55, 0.54, 0.52), 0.24, {"tile_w": 18 * INCH_TO_M, "tile_h": 18 * INCH_TO_M, "running_bond": False}),
    "tile_24": ("TILE", (0.86, 0.84, 0.81), (0.56, 0.55, 0.53), 0.22, {"tile_w": 24 * INCH_TO_M, "tile_h": 24 * INCH_TO_M, "running_bond": False}),
    "tile_offset_half": ("TILE", (0.82, 0.81, 0.79), (0.52, 0.52, 0.51), 0.25, {"tile_w": 24 * INCH_TO_M, "tile_h": 12 * INCH_TO_M, "running_bond": True}),
    "tile_offset_third": ("TILE", (0.83, 0.82, 0.79), (0.52, 0.52, 0.51), 0.25, {"tile_w": 24 * INCH_TO_M, "tile_h": 12 * INCH_TO_M, "running_bond": True}),
    "tile_hex": ("TILE", (0.86, 0.86, 0.84), (0.52, 0.52, 0.52), 0.25, {"tile_w": 8 * INCH_TO_M, "tile_h": 8 * INCH_TO_M, "running_bond": True}),
    "tile_basketweave": ("TILE", (0.85, 0.84, 0.81), (0.52, 0.52, 0.52), 0.25, {"tile_w": 8 * INCH_TO_M, "tile_h": 8 * INCH_TO_M, "running_bond": True}),
    "carpet_stipple": ("SOLID", (0.68, 0.63, 0.56), None, 0.92, {}),
    "carpet_weave": ("SOLID", (0.60, 0.56, 0.50), None, 0.92, {}),
    "concrete_stipple": ("SOLID", (0.56, 0.56, 0.55), None, 0.82, {}),
}


def _get_or_create_floor_material(pr: ParsedRoom, surface_materials):
    import bpy

    pat = (pr.floor_pattern or "none").strip().lower()
    if pat in ("none", "") or pat not in _FLOOR_PATTERN_PRESETS:
        ft = (pr.floor_type or "").lower()
        if "carpet" in ft:
            pat = "carpet_stipple"
        elif "tile" in ft or "porcelain" in ft or "ceramic" in ft:
            pat = "tile_18"
        elif "vinyl" in ft or "lvp" in ft or "laminate" in ft:
            pat = "vinyl_plank"
        elif "hardwood" in ft or "wood" in ft or "oak" in ft:
            pat = "wood_plank"
        elif "concrete" in ft or "garage" in ft or pr.is_slab:
            pat = "concrete_stipple"
        else:
            pat = "wood_plank"

    mat_id = f"EstiSketch_Floor_{pat}"
    existing = bpy.data.materials.get(mat_id)
    if existing is not None:
        return existing

    style, base_srgb, accent_srgb, rough, extra = _FLOOR_PATTERN_PRESETS[pat]
    mat = surface_materials.build_surface_material(
        mat_id, style, base_srgb, accent_srgb, rough, **extra
    )
    mat.diffuse_color = (*base_srgb, 1.0)
    return mat


def _build_floor_mesh(
    name: str,
    points_m: List[Tuple[float, float]],
    z_top: float,
    thickness_m: float,
    target_col,
    is_slab: bool,
    mat=None,
    pattern_rotation_deg: float = 0.0,
    pattern_scale: float = 1.0,
):
    import bmesh
    import bpy
    from mathutils import Vector

    cleaned: List[Tuple[float, float]] = []
    for pt in points_m:
        if not cleaned or math.hypot(pt[0] - cleaned[-1][0], pt[1] - cleaned[-1][1]) > 1e-4:
            cleaned.append(pt)
    if len(cleaned) >= 2 and math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1]) <= 1e-4:
        cleaned.pop()
    if len(cleaned) < 3:
        return None

    bm = bmesh.new()
    verts = [bm.verts.new((x, y, z_top)) for x, y in cleaned]
    bm.verts.ensure_lookup_table()
    edges = [bm.edges.new((verts[i], verts[(i + 1) % len(verts)])) for i in range(len(verts))]
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
    bm.normal_update()

    for face in bm.faces:
        if face.normal.z < 0:
            face.normal_flip()

    top_faces = list(bm.faces)
    if top_faces:
        res = bmesh.ops.extrude_face_region(bm, geom=top_faces)
        ext_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=ext_verts, vec=Vector((0.0, 0.0, -thickness_m)))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.normal_update()

    rot_rad = math.radians(pattern_rotation_deg)
    cr_rot, sr_rot = math.cos(rot_rad), math.sin(rot_rad)
    inv_scale = 1.0 / max(0.25, pattern_scale)

    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            vx, vy = loop.vert.co.x, loop.vert.co.y
            u = (vx * cr_rot - vy * sr_rot) * inv_scale
            v = (vx * sr_rot + vy * cr_rot) * inv_scale
            loop[uv_layer].uv = (u, v)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    if mat is not None:
        mesh.materials.append(mat)

    obj = bpy.data.objects.new(name, mesh)
    obj["IS_FLOOR_BP"] = True
    if is_slab:
        obj["IS_SLAB"] = True
    obj.color = mat.diffuse_color if mat is not None else (0.72, 0.72, 0.70, 1.0)
    target_col.objects.link(obj)
    return obj


def _clean_points_m(points_m: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    cleaned: List[Tuple[float, float]] = []
    for pt in points_m:
        if not cleaned or math.hypot(pt[0] - cleaned[-1][0], pt[1] - cleaned[-1][1]) > 1e-4:
            cleaned.append(pt)
    if len(cleaned) >= 2 and math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1]) <= 1e-4:
        cleaned.pop()
    return cleaned


def _build_ceiling_mesh(
    name: str,
    points_m: List[Tuple[float, float]],
    z_bottom: float,
    thickness_m: float,
    target_col,
    scene,
):
    import bmesh
    import bpy
    from mathutils import Vector

    cleaned = _clean_points_m(points_m)
    if len(cleaned) < 3:
        return None

    bm = bmesh.new()
    verts = [bm.verts.new((x, y, z_bottom)) for x, y in cleaned]
    bm.verts.ensure_lookup_table()
    edges = [bm.edges.new((verts[i], verts[(i + 1) % len(verts)])) for i in range(len(verts))]
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
    bm.normal_update()

    for face in bm.faces:
        if face.normal.z > 0:
            face.normal_flip()

    bottom_faces = list(bm.faces)
    if bottom_faces:
        res = bmesh.ops.extrude_face_region(bm, geom=bottom_faces)
        ext_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=ext_verts, vec=Vector((0.0, 0.0, thickness_m)))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.normal_update()

    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            loop[uv_layer].uv = (loop.vert.co.x, loop.vert.co.y)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    mat = getattr(scene.home_builder, "wall_material", None)
    if mat is not None:
        mesh.materials.append(mat)

    obj = bpy.data.objects.new(name, mesh)
    obj["IS_CEILING_BP"] = True
    obj.color = (0.95, 0.95, 0.94, 1.0)
    target_col.objects.link(obj)
    return obj


def _get_or_create_roof_material(material_name: str):
    import bpy

    key = (material_name or "asphalt_shingle").lower()
    mat_id = f"EstiSketch_Roof_{key}"
    existing = bpy.data.materials.get(mat_id)
    if existing is not None:
        return existing

    presets = {
        "asphalt_shingle": ((0.14, 0.15, 0.17, 1.0), 0.0, 0.85),
        "standing_seam_metal": ((0.20, 0.22, 0.24, 1.0), 0.75, 0.32),
        "metal": ((0.20, 0.22, 0.24, 1.0), 0.75, 0.32),
        "tile": ((0.52, 0.24, 0.15, 1.0), 0.0, 0.65),
        "clay_tile": ((0.52, 0.24, 0.15, 1.0), 0.0, 0.65),
        "wood_shake": ((0.36, 0.27, 0.19, 1.0), 0.0, 0.85),
    }
    base_col, metallic, roughness = presets.get(key, ((0.22, 0.23, 0.25, 1.0), 0.0, 0.75))

    mat = bpy.data.materials.new(name=mat_id)
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = base_col
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = base_col
    return mat


def _build_roof_mesh(
    name: str,
    solved: SolvedRoofGeometry,
    cx: float,
    cy: float,
    target_col,
    roof_thickness_in: float = 8.0,
):
    import bmesh
    import bpy
    from mathutils import Vector

    if not solved.facets:
        return None

    bm = bmesh.new()
    vert_cache: Dict[Tuple[int, int, int], object] = {}

    def _get_bm_vert(x_in: float, y_in: float, z_in: float):
        xm, ym = inches_to_blender_xy(x_in, y_in, cx, cy)
        zm = z_in * INCH_TO_M
        key = (int(round(xm * 10000)), int(round(ym * 10000)), int(round(zm * 10000)))
        v = vert_cache.get(key)
        if v is None:
            v = bm.verts.new((xm, ym, zm))
            vert_cache[key] = v
        return v

    for facet in solved.facets:
        f_verts = [_get_bm_vert(x, y, z) for x, y, z in facet.vertices_3d]
        dedup: List[object] = []
        for v in f_verts:
            if not dedup or dedup[-1] != v:
                dedup.append(v)
        if len(dedup) >= 2 and dedup[0] == dedup[-1]:
            dedup.pop()
        if len(dedup) < 3:
            continue

        # Check planarity for quads/ngons; fan-triangulate if non-planar > 2mm
        needs_tri = False
        if len(dedup) > 3:
            p0, p1, p2 = dedup[0].co, dedup[1].co, dedup[2].co
            n = (p1 - p0).cross(p2 - p0)
            nlen = n.length
            if nlen > 1e-6:
                n_unit = n / nlen
                if any(abs((v.co - p0).dot(n_unit)) > 0.002 for v in dedup[3:]):
                    needs_tri = True

        polys = (
            [[dedup[0], dedup[i], dedup[i + 1]] for i in range(1, len(dedup) - 1)]
            if needs_tri
            else [dedup]
        )
        for poly in polys:
            try:
                f = bm.faces.new(poly)
            except ValueError:
                continue
            f.normal_update()
            if f.normal.z < 0:
                f.normal_flip()

    bm.normal_update()
    top_faces = list(bm.faces)
    if not top_faces:
        bm.free()
        return None

    thick_m = max(0.05, roof_thickness_in * INCH_TO_M)
    res = bmesh.ops.extrude_face_region(bm, geom=top_faces)
    ext_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=ext_verts, vec=Vector((0.0, 0.0, thick_m)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()

    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        is_side = abs(face.normal.z) < 0.25
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x + co.y, co.z) if is_side else (co.x, co.y)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    mat = _get_or_create_roof_material(solved.material)
    mesh.materials.append(mat)

    obj = bpy.data.objects.new(name, mesh)
    obj["IS_ROOF_BP"] = True
    obj["ESTISKETCH_ID"] = solved.roof_id
    obj["ROOF_MATERIAL"] = solved.material
    obj.color = mat.diffuse_color
    target_col.objects.link(obj)
    return obj


def _build_gable_infill_mesh(
    name: str,
    infill: SolvedGableInfill,
    cx: float,
    cy: float,
    target_col,
    scene,
    mat=None,
):
    import bmesh
    import bpy

    ax, ay = inches_to_blender_xy(infill.p_start[0], infill.p_start[1], cx, cy)
    bx, by = inches_to_blender_xy(infill.p_end[0], infill.p_end[1], cx, cy)
    px, py = inches_to_blender_xy(infill.p_peak[0], infill.p_peak[1], cx, cy)

    dx, dy = bx - ax, by - ay
    seg_len = math.hypot(dx, dy)
    if seg_len < 1e-4:
        return None
    nx, ny = -dy / seg_len, dx / seg_len
    half_t = max(0.01, (infill.thickness * INCH_TO_M) / 2.0)
    zb = infill.z_base * INCH_TO_M
    zp = infill.z_peak * INCH_TO_M

    bm = bmesh.new()
    f0 = bm.verts.new((ax - half_t * nx, ay - half_t * ny, zb))
    f1 = bm.verts.new((bx - half_t * nx, by - half_t * ny, zb))
    f2 = bm.verts.new((px - half_t * nx, py - half_t * ny, zp))
    b0 = bm.verts.new((ax + half_t * nx, ay + half_t * ny, zb))
    b1 = bm.verts.new((bx + half_t * nx, by + half_t * ny, zb))
    b2 = bm.verts.new((px + half_t * nx, py + half_t * ny, zp))

    bm.faces.new((f0, f1, f2))
    bm.faces.new((b1, b0, b2))
    bm.faces.new((f0, b0, b1, f1))
    bm.faces.new((f1, b1, b2, f2))
    bm.faces.new((f2, b2, b0, f0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x + co.y, co.z)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    use_mat = mat if mat is not None else getattr(scene.home_builder, "wall_material", None)
    if use_mat is not None:
        mesh.materials.append(use_mat)

    obj = bpy.data.objects.new(name, mesh)
    obj["IS_GABLE_INFILL"] = True
    obj.color = use_mat.diffuse_color if use_mat is not None else (0.85, 0.85, 0.83, 1.0)
    target_col.objects.link(obj)
    return obj


def _build_wall_baseboards(
    pw: ParsedWall,
    hb_wall,
    seg_len_m: float,
    door_intervals: List[Tuple[float, float]],
    target_col,
    name: str,
):
    import bmesh
    import bpy

    if not pw.left_baseboard and not pw.right_baseboard:
        return None
    spans = compute_baseboard_spans(seg_len_m, door_intervals)
    if not spans:
        return None

    bb_h = 4.5 * INCH_TO_M
    bb_t = 0.625 * INCH_TO_M
    thick_m = max(0.02, hb_wall.get_input("Thickness"))

    bm = bmesh.new()
    for x0, x1 in spans:
        if pw.left_baseboard:
            _bm_add_box(bm, x0, -bb_t, 0.0, x1, 0.0, bb_h)
        if pw.right_baseboard:
            _bm_add_box(bm, x0, thick_m, 0.0, x1, thick_m + bb_t, bb_h)

    if not bm.faces:
        bm.free()
        return None

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x, co.z)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    trim_mat = _get_or_create_simple_material(
        "EstiSketch_Trim_Baseboard", (0.95, 0.95, 0.94, 1.0), metallic=0.0, roughness=0.35
    )
    mesh.materials.append(trim_mat)

    obj = bpy.data.objects.new(name, mesh)
    obj.parent = hb_wall.obj
    obj.location = (0.0, 0.0, 0.0)
    obj["IS_BASEBOARD"] = True
    obj["ESTISKETCH_ID"] = pw.identifier
    obj.color = trim_mat.diffuse_color
    target_col.objects.link(obj)
    return obj


def _build_footer_mesh_from_polys(
    pw: ParsedWall,
    polys_m: List[List[Tuple[float, float]]],
    lvl: ParsedLevel,
    target_col,
    surface_materials,
):
    """Build a single concrete footer object from pre-mitered 2D strip polygons."""
    import bmesh
    import bpy

    z_top = lvl.elevation * INCH_TO_M
    z_bot = z_top - max(0.05, pw.footer_depth * INCH_TO_M)
    bm = bmesh.new()
    for poly in polys_m:
        if len(poly) >= 3:
            _extrude_prism_z(bm, poly, z_bot, z_top)

    if not bm.faces:
        bm.free()
        return None

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x, co.y)

    mesh = bpy.data.meshes.new(f"Footer_{pw.identifier}")
    bm.to_mesh(mesh)
    bm.free()

    mat_id = "EstiSketch_Concrete_Footer"
    mat = bpy.data.materials.get(mat_id)
    if mat is None:
        mat = surface_materials.build_surface_material(
            mat_id, "SOLID", (0.52, 0.52, 0.51), None, 0.88
        )
        mat.diffuse_color = (0.52, 0.52, 0.51, 1.0)
    mesh.materials.append(mat)

    obj = bpy.data.objects.new(f"Footer_{pw.identifier}", mesh)
    obj["IS_FOOTER_BP"] = True
    obj["ESTISKETCH_ID"] = pw.identifier
    obj.color = mat.diffuse_color
    target_col.objects.link(obj)
    return obj


def _build_level_footers(
    project: ParsedProject,
    level_by_id: Dict[str, ParsedLevel],
    cx: float,
    cy: float,
    target_col,
    surface_materials,
) -> int:
    """Build mitered footers grouped by ``(level_id, footer_depth)``."""
    groups: Dict[Tuple[str, float], List[ParsedWall]] = {}
    for pw in project.walls:
        if pw.footer:
            groups.setdefault((pw.level_id, round(pw.footer_depth, 3)), []).append(pw)

    footer_count = 0
    for (lvl_id, _), group_walls in groups.items():
        lvl = level_by_id.get(lvl_id, project.levels[0])
        segs: List[StripSegment] = []
        seg_ranges: List[Tuple[ParsedWall, int, int]] = []
        for pw in group_walls:
            if pw.is_curved and pw.arc_center is not None and pw.arc_radius is not None:
                pts_in = tessellate_curved_wall_points(
                    pw.start, pw.end, pw.arc_center, pw.arc_radius
                )
            else:
                pts_in = [pw.start, pw.end]
            pts_m = [inches_to_blender_xy(x, y, cx, cy) for x, y in pts_in]
            thick_m = max(0.02, pw.width * INCH_TO_M)
            left_off_m = max(0.0, pw.footer_left_offset * INCH_TO_M)
            right_off_m = max(0.0, pw.footer_right_offset * INCH_TO_M)
            if pw.symbolic:
                y0 = -(thick_m / 2.0 + left_off_m)
                y1 = thick_m / 2.0 + right_off_m
            else:
                y0 = -left_off_m
                y1 = thick_m + right_off_m
            start_idx = len(segs)
            for i in range(len(pts_m) - 1):
                segs.append(StripSegment(pts_m[i], pts_m[i + 1], y0, y1))
            seg_ranges.append((pw, start_idx, len(segs)))

        polys = compute_mitered_strip_polygons(segs)
        for pw, s_idx, e_idx in seg_ranges:
            f_obj = _build_footer_mesh_from_polys(
                pw, polys[s_idx:e_idx], lvl, target_col, surface_materials
            )
            if f_obj is not None:
                footer_count += 1
    return footer_count


def _build_level_rim_bands(
    project: ParsedProject,
    level_by_id: Dict[str, ParsedLevel],
    level_cols: Dict[str, Dict[str, object]],
    cx: float,
    cy: float,
    scene,
    surface_materials,
) -> int:
    """Build exterior rim-joist band walls covering upper-level floor slab edges."""
    import bmesh
    import bpy

    fallback = getattr(scene.home_builder, "wall_material", None)
    rim_count = 0
    for lvl in project.levels:
        if lvl.elevation <= 0.1 or lvl.floor_thickness <= 0.01:
            continue
        ext_walls = [
            pw
            for pw in project.walls
            if pw.level_id == lvl.id and pw.exterior_wall and not pw.symbolic
        ]
        if not ext_walls:
            continue

        z_top = lvl.elevation * INCH_TO_M
        z_bot = (lvl.elevation - lvl.floor_thickness) * INCH_TO_M
        segs: List[StripSegment] = []
        seg_ranges: List[Tuple[ParsedWall, int, int]] = []
        for pw in ext_walls:
            if pw.is_curved and pw.arc_center is not None and pw.arc_radius is not None:
                pts_in = tessellate_curved_wall_points(
                    pw.start, pw.end, pw.arc_center, pw.arc_radius
                )
            else:
                pts_in = [pw.start, pw.end]
            pts_m = [inches_to_blender_xy(x, y, cx, cy) for x, y in pts_in]
            thick_m = max(0.02, pw.width * INCH_TO_M)
            start_idx = len(segs)
            for i in range(len(pts_m) - 1):
                segs.append(StripSegment(pts_m[i], pts_m[i + 1], 0.0, thick_m))
            seg_ranges.append((pw, start_idx, len(segs)))

        polys = compute_mitered_strip_polygons(segs)
        walls_col = level_cols[lvl.id]["walls"]
        for pw, s_idx, e_idx in seg_ranges:
            bm = bmesh.new()
            for poly in polys[s_idx:e_idx]:
                if len(poly) >= 3:
                    _extrude_prism_z(bm, poly, z_bot, z_top)
            if not bm.faces:
                bm.free()
                continue

            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            p0_m = segs[s_idx].p0 if s_idx < len(segs) else (0.0, 0.0)
            p1_m = segs[e_idx - 1].p1 if e_idx > s_idx else (1.0, 0.0)
            wdx, wdy = p1_m[0] - p0_m[0], p1_m[1] - p0_m[1]
            wlen = math.hypot(wdx, wdy) or 1.0
            ux, uy = wdx / wlen, wdy / wlen

            uv_layer = bm.loops.layers.uv.new("UVMap")
            for face in bm.faces:
                is_side = abs(face.normal.z) < 0.25
                for loop in face.loops:
                    co = loop.vert.co
                    if is_side:
                        along_m = (co.x - p0_m[0]) * ux + (co.y - p0_m[1]) * uy
                        loop[uv_layer].uv = (along_m, co.z)
                    else:
                        loop[uv_layer].uv = (co.x, co.y)

            mesh = bpy.data.meshes.new(f"RimBand_{pw.identifier}")
            bm.to_mesh(mesh)
            bm.free()

            _, rf = _resolve_wall_side_finishes(pw)
            ext_mat = _get_or_create_wall_finish_material(
                rf, pw.right_color, surface_materials, fallback
            )
            if ext_mat is not None:
                mesh.materials.append(ext_mat)

            obj = bpy.data.objects.new(f"RimBand_{pw.identifier}", mesh)
            obj["IS_RIM_BAND"] = True
            obj["ESTISKETCH_ID"] = pw.identifier
            obj["ESTISKETCH_LEVEL"] = lvl.id
            if ext_mat is not None:
                obj.color = ext_mat.diffuse_color
            walls_col.objects.link(obj)
            rim_count += 1
    return rim_count


def _build_wall_footer(
    pw: ParsedWall,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
    surface_materials,
):
    if not pw.footer:
        return None
    return _build_level_footers(
        ParsedProject(levels=[lvl], walls=[pw]),
        {lvl.id: lvl},
        cx,
        cy,
        target_col,
        surface_materials,
    )


def _build_garage_door_mesh(
    cage_obj,
    width_m: float,
    thickness_m: float,
    height_m: float,
    openings_col,
    hb_wall_obj,
):
    import bmesh
    import bpy

    # Create a dedicated boolean cutter inside the cage matching reveal depth
    cutter_bm = bmesh.new()
    reveal_pad = 0.02
    _bm_add_box(
        cutter_bm,
        0.0,
        -reveal_pad,
        -0.01,
        width_m,
        thickness_m + reveal_pad,
        height_m,
    )
    bmesh.ops.recalc_face_normals(cutter_bm, faces=cutter_bm.faces[:])
    cutter_mesh = bpy.data.meshes.new(f"{cage_obj.name}_Cutter")
    cutter_bm.to_mesh(cutter_mesh)
    cutter_bm.free()
    cutter_obj = bpy.data.objects.new(f"{cage_obj.name}_Cutter", cutter_mesh)
    cutter_obj.parent = cage_obj
    cutter_obj.display_type = "WIRE"
    cutter_obj.hide_viewport = True
    cutter_obj.hide_render = True
    openings_col.objects.link(cutter_obj)
    _add_boolean_cut(hb_wall_obj, cutter_obj)

    frame_mat = _get_or_create_simple_material(
        "EstiSketch_Garage_Frame", (0.86, 0.86, 0.85, 1.0), metallic=0.15, roughness=0.38
    )
    panel_mat = _get_or_create_simple_material(
        "EstiSketch_Garage_Panel", (0.93, 0.93, 0.91, 1.0), metallic=0.05, roughness=0.40
    )
    glass_mat = _get_or_create_simple_material(
        "EstiSketch_Garage_Glass", (0.68, 0.80, 0.88, 1.0), metallic=0.0, roughness=0.08, alpha=0.55
    )
    seal_mat = _get_or_create_simple_material(
        "EstiSketch_DarkMetal", (0.14, 0.14, 0.15, 1.0), metallic=0.5, roughness=0.45
    )

    bm = bmesh.new()
    jamb_w = 0.045
    # Perimeter jamb & header trim (mat 0)
    _bm_add_box(bm, 0.0, 0.0, 0.0, jamb_w, thickness_m, height_m, mat_index=0)
    _bm_add_box(bm, width_m - jamb_w, 0.0, 0.0, width_m, thickness_m, height_m, mat_index=0)
    _bm_add_box(bm, jamb_w, 0.0, height_m - jamb_w, width_m - jamb_w, thickness_m, height_m, mat_index=0)

    # Door leaf recessed near center-outside of wall (y in [0.03, 0.08])
    y_back = min(thickness_m * 0.45, max(0.02, thickness_m - 0.055))
    y_front = y_back + 0.045
    seal_h = 0.03
    _bm_add_box(bm, jamb_w, y_back, 0.0, width_m - jamb_w, y_front, seal_h, mat_index=3)

    inner_x0 = jamb_w
    inner_x1 = width_m - jamb_w
    inner_w = max(0.2, inner_x1 - inner_x0)
    inner_z0 = seal_h
    inner_z1 = height_m - jamb_w
    n_sections = 4
    sec_h = (inner_z1 - inner_z0) / n_sections
    gap = 0.008

    for s_idx in range(n_sections):
        sz0 = inner_z0 + s_idx * sec_h + gap * 0.5
        sz1 = inner_z0 + (s_idx + 1) * sec_h - gap * 0.5
        _bm_add_box(bm, inner_x0, y_back, sz0, inner_x1, y_front, sz1, mat_index=1)
        if s_idx < n_sections - 1:
            # Horizontal raised stiles / carriage embosses on outer face (+Y)
            n_cols = 4 if inner_w > 3.2 else 2
            col_w = inner_w / n_cols
            pad_x = 0.08
            pad_z = 0.06
            for ci in range(n_cols):
                px0 = inner_x0 + ci * col_w + pad_x
                px1 = inner_x0 + (ci + 1) * col_w - pad_x
                if px1 > px0 + 0.05 and sz1 - sz0 > 2 * pad_z + 0.04:
                    _bm_add_box(
                        bm, px0, y_front, sz0 + pad_z, px1, y_front + 0.012, sz1 - pad_z, mat_index=1
                    )
        else:
            # Top row carriage-house glass lites (mat 2)
            n_lites = 4 if inner_w > 3.2 else 2
            lite_w = inner_w / n_lites
            pad_x = 0.09
            pad_z = 0.08
            for li in range(n_lites):
                gx0 = inner_x0 + li * lite_w + pad_x
                gx1 = inner_x0 + (li + 1) * lite_w - pad_x
                if gx1 > gx0 + 0.05 and sz1 - sz0 > 2 * pad_z + 0.04:
                    _bm_add_box(
                        bm, gx0, y_front - 0.004, sz0 + pad_z, gx1, y_front + 0.008, sz1 - pad_z, mat_index=2
                    )

    door_obj = _finalize_bmesh_object(
        bm,
        f"GarageDoor_{cage_obj.name}",
        [frame_mat, panel_mat, glass_mat, seal_mat],
        (0.0, 0.0, 0.0),
        0.0,
        openings_col,
        cage_obj.get("ESTISKETCH_ID", ""),
    )
    door_obj.parent = cage_obj
    door_obj["IS_DOOR_WINDOW_GEO"] = True
    return door_obj, cutter_obj


def _get_or_create_stair_material(
    mat_id: str,
    base_col: Tuple[float, float, float, float],
    metallic: float = 0.0,
    roughness: float = 0.45,
):
    import bpy

    existing = bpy.data.materials.get(mat_id)
    if existing is not None:
        return existing
    mat = bpy.data.materials.new(name=mat_id)
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = base_col
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = base_col
    return mat


def _apply_slab_cutouts(
    slab_obj,
    cutout_polys_in: List[List[Tuple[float, float]]],
    z_min_m: float,
    z_max_m: float,
    cx: float,
    cy: float,
    scene,
) -> int:
    """Boolean-cut and bake vertical hole prisms out of a floor or ceiling slab."""
    import bmesh
    import bpy
    from mathutils import Vector

    if slab_obj is None or not cutout_polys_in:
        return 0

    cutters = []
    z_lo = z_min_m - 0.15
    z_hi = z_max_m + 0.15
    for idx, poly_in in enumerate(cutout_polys_in):
        pts_m = _clean_points_m([inches_to_blender_xy(x, y, cx, cy) for x, y in poly_in])
        if len(pts_m) < 3:
            continue
        bm = bmesh.new()
        verts = [bm.verts.new((x, y, z_lo)) for x, y in pts_m]
        bm.verts.ensure_lookup_table()
        edges = [bm.edges.new((verts[i], verts[(i + 1) % len(verts)])) for i in range(len(verts))]
        bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
        bm.normal_update()
        for f in bm.faces:
            if f.normal.z > 0:
                f.normal_flip()
        res = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
        ext_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=ext_verts, vec=Vector((0.0, 0.0, z_hi - z_lo)))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        c_mesh = bpy.data.meshes.new(f"_CutPrism_{slab_obj.name}_{idx}")
        bm.to_mesh(c_mesh)
        bm.free()

        c_obj = bpy.data.objects.new(f"_CutPrism_{slab_obj.name}_{idx}", c_mesh)
        scene.collection.objects.link(c_obj)
        mod = slab_obj.modifiers.new(name=f"HoleCut_{idx}", type="BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.object = c_obj
        mod.solver = "EXACT"
        cutters.append((c_obj, c_mesh))

    if not cutters:
        return 0

    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = slab_obj.evaluated_get(depsgraph)
    baked_mesh = bpy.data.meshes.new_from_object(eval_obj, depsgraph=depsgraph)
    old_mesh = slab_obj.data
    slab_obj.data = baked_mesh
    slab_obj.modifiers.clear()
    if old_mesh is not None and old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)

    for c_obj, c_mesh in cutters:
        bpy.data.objects.remove(c_obj, do_unlink=True)
        if c_mesh.users == 0:
            bpy.data.meshes.remove(c_mesh)
    return len(cutters)


def _extrude_prism_z(bm, pts_m: List[Tuple[float, float]], z_bot: float, z_top: float) -> None:
    from mathutils import Vector
    import bmesh

    if len(pts_m) < 3 or z_top <= z_bot + 1e-5:
        return
    verts = [bm.verts.new((x, y, z_bot)) for x, y in pts_m]
    bm.verts.ensure_lookup_table()
    edges = [bm.edges.new((verts[i], verts[(i + 1) % len(verts)])) for i in range(len(verts))]
    res_fill = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
    faces = [g for g in res_fill.get("geom", []) if isinstance(g, bmesh.types.BMFace)]
    if not faces:
        return
    for f in faces:
        f.normal_update()
        if f.normal.z > 0:
            f.normal_flip()
    res = bmesh.ops.extrude_face_region(bm, geom=faces)
    ext_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=ext_verts, vec=Vector((0.0, 0.0, z_top - z_bot)))


def _build_l_winder_stair_mesh(ps: ParsedStair, z_start_in: float, cx: float, cy: float):
    import bmesh
    import bpy

    lay = _l_stair_layout_in(
        ps.num_steps,
        ps.steps_before_landing,
        ps.tread_depth,
        ps.landing_depth,
        ps.width,
        ps.winder_count,
    )
    sb = int(lay["steps_before"])
    sa_cnt = int(lay["steps_after"])
    wc = int(lay["winder_count"])
    total_steps = max(1, sb + wc + sa_cnt)
    riser_in = ps.total_rise / total_steps
    tread_thick_in = 1.5
    width = max(12.0, ps.width)
    hw = width / 2.0
    ang = ps.direction_angle
    ca, sa = math.cos(ang), math.sin(ang)
    sx, sy = ps.start_point

    def _to_m(u: float, v: float) -> Tuple[float, float]:
        return inches_to_blender_xy(sx + u * ca - v * sa, sy + u * sa + v * ca, cx, cy)

    bm = bmesh.new()

    # Flight 1 treads + risers
    for i in range(sb):
        u0 = i * ps.tread_depth
        u1 = (i + 1) * ps.tread_depth
        z_top = (z_start_in + (i + 1) * riser_in) * INCH_TO_M
        z_bot = (z_start_in + i * riser_in) * INCH_TO_M
        pts_m = [_to_m(u0, -hw), _to_m(u1, -hw), _to_m(u1, hw), _to_m(u0, hw)]
        _extrude_prism_z(bm, pts_m, max(z_start_in * INCH_TO_M, z_bot), z_top)

    # Winder wedge treads in the width x width turn square
    rb = lay["run_before"]
    w_polys = _winder_tread_polys_local(width, wc, ps.turn_direction)
    for wi, wpoly in enumerate(w_polys):
        step_idx = sb + wi
        z_top = (z_start_in + (step_idx + 1) * riser_in) * INCH_TO_M
        z_bot = (z_start_in + step_idx * riser_in - tread_thick_in) * INCH_TO_M
        pts_m = [_to_m(rb + u, -hw + v) for (u, v) in wpoly]
        _extrude_prism_z(bm, pts_m, max(z_start_in * INCH_TO_M, z_bot), z_top)

    # Flight 2 treads + risers after turn square
    sign_v = -1.0 if ps.turn_direction == "left" else 1.0
    for i in range(sa_cnt):
        step_idx = sb + wc + i
        d0 = i * ps.tread_depth
        d1 = (i + 1) * ps.tread_depth
        v0 = sign_v * (hw + d0)
        v1 = sign_v * (hw + d1)
        z_top = (z_start_in + (step_idx + 1) * riser_in) * INCH_TO_M
        z_bot = (z_start_in + step_idx * riser_in - tread_thick_in) * INCH_TO_M
        pts_m = [_to_m(rb, v0), _to_m(rb + width, v0), _to_m(rb + width, v1), _to_m(rb, v1)]
        _extrude_prism_z(bm, pts_m, max(z_start_in * INCH_TO_M, z_bot), z_top)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(f"Stair_{ps.identifier}")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _build_spiral_stair_mesh(ps: ParsedStair, z_start_in: float, cx: float, cy: float):
    import bmesh
    import bpy
    from mathutils import Matrix

    bm = bmesh.new()
    sx_m, sy_m = inches_to_blender_xy(ps.start_point[0], ps.start_point[1], cx, cy)
    z0_m = z_start_in * INCH_TO_M
    total_rise_m = max(0.2, ps.total_rise * INCH_TO_M)
    inner_r_m = max(0.05, ps.inner_radius * INCH_TO_M)
    outer_r_m = inner_r_m + max(0.3, ps.width * INCH_TO_M)
    steps = max(4, ps.num_steps)
    riser_m = total_rise_m / steps
    tread_thick_m = 1.5 * INCH_TO_M

    # Center structural pole (extends 36" above top tread)
    pole_h = total_rise_m + 36.0 * INCH_TO_M
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=20,
        radius1=inner_r_m,
        radius2=inner_r_m,
        depth=pole_h,
        matrix=Matrix.Translation((sx_m, sy_m, z0_m + pole_h / 2.0)),
    )

    rot_rad = math.radians(ps.rotation_degrees or 270.0)
    # In Blender XY (Y-flipped), EstiSketch left-turn (-ang) corresponds to +ang_b
    dir_b = 1.0 if ps.turn_direction == "left" else -1.0
    theta0_b = -ps.direction_angle
    dtheta = (rot_rad / steps) * dir_b

    for i in range(steps):
        a0 = theta0_b + i * dtheta
        a1 = theta0_b + (i + 1) * dtheta
        pts_m = [
            (sx_m + inner_r_m * math.cos(a0), sy_m + inner_r_m * math.sin(a0)),
            (sx_m + outer_r_m * math.cos(a0), sy_m + outer_r_m * math.sin(a0)),
            (sx_m + outer_r_m * math.cos(a1), sy_m + outer_r_m * math.sin(a1)),
            (sx_m + inner_r_m * math.cos(a1), sy_m + inner_r_m * math.sin(a1)),
        ]
        z_top = z0_m + (i + 1) * riser_m
        _extrude_prism_z(bm, pts_m, max(z0_m, z_top - tread_thick_m), z_top)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(f"Stair_{ps.identifier}")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _build_stair_object(
    ps: ParsedStair,
    start_lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
    ops_stairs,
):
    import bpy

    wood_mat = _get_or_create_stair_material(
        "EstiSketch_Stair_Wood", (0.48, 0.33, 0.20, 1.0), metallic=0.0, roughness=0.45
    )

    use_hb5 = (
        ps.stair_type in ("straight", "u-shaped")
        or (ps.stair_type == "l-shaped" and ps.winder_count == 0)
    )
    if use_hb5:
        width_m = max(0.3, ps.width * INCH_TO_M)
        total_rise_m = max(0.2, ps.total_rise * INCH_TO_M)
        steps = max(1, ps.num_steps)
        riser_m = total_rise_m / steps
        if ps.stair_type == "straight" and ps.total_run > 0.0:
            tread_depth_m = (ps.total_run / steps) * INCH_TO_M
        else:
            tread_depth_m = max(0.15, ps.tread_depth * INCH_TO_M)
        tread_thick_m = 1.25 * INCH_TO_M
        landing_depth_m = max(width_m, (ps.landing_depth or ps.width) * INCH_TO_M)
        if 0 < ps.steps_before_landing < steps:
            landing_height_m = total_rise_m * (ps.steps_before_landing / steps)
        else:
            landing_height_m = total_rise_m / 2.0
        hb_type = {"straight": "STRAIGHT", "l-shaped": "L_SHAPE", "u-shaped": "U_SHAPE"}[ps.stair_type]
        hb_turn = "LEFT" if ps.turn_direction == "left" else "RIGHT"
        gap_m = max(0.0, ps.inner_radius * INCH_TO_M) if ps.stair_type == "u-shaped" and ps.inner_radius != 6.0 else 0.0

        mesh = ops_stairs.create_stair_mesh(
            width_m,
            total_rise_m,
            riser_m,
            tread_depth_m,
            tread_thick_m,
            hb_type,
            hb_turn,
            landing_depth_m,
            landing_height_m,
            gap_m,
        )
        obj = bpy.data.objects.new(f"Stair_{ps.identifier}", mesh)
        obj["IS_STAIR"] = True
        obj["MENU_ID"] = "HOME_BUILDER_MT_stair_commands"
        obj["STAIR_WIDTH"] = width_m
        obj["STAIR_TOTAL_RISE"] = total_rise_m
        obj["STAIR_RISER_HEIGHT"] = riser_m
        obj["STAIR_TREAD_DEPTH"] = tread_depth_m
        obj["STAIR_TREAD_THICKNESS"] = tread_thick_m
        obj["STAIR_TYPE"] = hb_type
        obj["STAIR_TURN_DIRECTION"] = hb_turn
        obj["STAIR_LANDING_DEPTH"] = landing_depth_m
        obj["STAIR_LANDING_HEIGHT"] = landing_height_m
        obj["STAIR_GAP"] = gap_m
        loc, rot_z = compute_hb5_stair_transform(ps, start_lvl.elevation, cx, cy)
        obj.location = loc
        obj.rotation_euler = (0.0, 0.0, rot_z)
    elif ps.stair_type == "l-shaped":
        mesh = _build_l_winder_stair_mesh(ps, start_lvl.elevation, cx, cy)
        obj = bpy.data.objects.new(f"Stair_{ps.identifier}", mesh)
        obj["IS_STAIR"] = True
    else:
        mesh = _build_spiral_stair_mesh(ps, start_lvl.elevation, cx, cy)
        obj = bpy.data.objects.new(f"Stair_{ps.identifier}", mesh)
        obj["IS_STAIR"] = True

    obj["ESTISKETCH_ID"] = ps.identifier
    obj.data.materials.append(wood_mat)
    obj.color = wood_mat.diffuse_color
    target_col.objects.link(obj)
    return obj


def _build_stair_railing_mesh(
    name: str,
    paths_3d_in: List[List[Tuple[float, float, float]]],
    rail_height_in: float,
    cx: float,
    cy: float,
    target_col,
):
    import bmesh
    import bpy

    if not paths_3d_in:
        return None

    bm = bmesh.new()
    rail_h_m = max(0.5, rail_height_in * INCH_TO_M)
    post_r = (3.5 * INCH_TO_M) / 2.0
    bal_r = (1.25 * INCH_TO_M) / 2.0
    bal_step_m = 4.5 * INCH_TO_M
    rail_hw = (2.25 * INCH_TO_M) / 2.0
    rail_ht = 1.75 * INCH_TO_M

    def _add_post(px: float, py: float, pz0: float, pz1: float, half_r: float) -> None:
        pts = [
            (px - half_r, py - half_r),
            (px + half_r, py - half_r),
            (px + half_r, py + half_r),
            (px - half_r, py + half_r),
        ]
        _extrude_prism_z(bm, pts, pz0, pz1)

    for path in paths_3d_in:
        if len(path) < 2:
            continue
        pts_m = [
            (*inches_to_blender_xy(x, y, cx, cy), z * INCH_TO_M)
            for x, y, z in path
        ]
        for vx, vy, vz in pts_m:
            _add_post(vx, vy, vz, vz + rail_h_m + 0.04, post_r)

        for i in range(len(pts_m) - 1):
            x0, y0, z0 = pts_m[i]
            x1, y1, z1 = pts_m[i + 1]
            dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
            horiz = math.hypot(dx, dy)
            if horiz < 0.02:
                continue

            # Balusters every ~4.5"
            n_bal = max(0, int(horiz / bal_step_m) - 1)
            for k in range(1, n_bal + 1):
                t = k / (n_bal + 1)
                bx = x0 + t * dx
                by = y0 + t * dy
                bz = z0 + t * dz
                _add_post(bx, by, bz, bz + rail_h_m, bal_r)

            # Sloped top handrail bar
            nx, ny = -dy / horiz, dx / horiz
            b0 = bm.verts.new((x0 + rail_hw * nx, y0 + rail_hw * ny, z0 + rail_h_m - rail_ht))
            b1 = bm.verts.new((x0 - rail_hw * nx, y0 - rail_hw * ny, z0 + rail_h_m - rail_ht))
            b2 = bm.verts.new((x1 - rail_hw * nx, y1 - rail_hw * ny, z1 + rail_h_m - rail_ht))
            b3 = bm.verts.new((x1 + rail_hw * nx, y1 + rail_hw * ny, z1 + rail_h_m - rail_ht))
            t0 = bm.verts.new((x0 + rail_hw * nx, y0 + rail_hw * ny, z0 + rail_h_m))
            t1 = bm.verts.new((x0 - rail_hw * nx, y0 - rail_hw * ny, z0 + rail_h_m))
            t2 = bm.verts.new((x1 - rail_hw * nx, y1 - rail_hw * ny, z1 + rail_h_m))
            t3 = bm.verts.new((x1 + rail_hw * nx, y1 + rail_hw * ny, z1 + rail_h_m))
            for quad in (
                (t0, t1, t2, t3),
                (b3, b2, b1, b0),
                (b0, b1, t1, t0),
                (b1, b2, t2, t1),
                (b2, b3, t3, t2),
                (b3, b0, t0, t3),
            ):
                try:
                    bm.faces.new(quad)
                except ValueError:
                    pass

    if not bm.faces:
        bm.free()
        return None

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x + co.y, co.z)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    rail_mat = _get_or_create_stair_material(
        "EstiSketch_Stair_Railing", (0.22, 0.16, 0.12, 1.0), metallic=0.1, roughness=0.4
    )
    mesh.materials.append(rail_mat)
    obj = bpy.data.objects.new(name, mesh)
    obj["IS_STAIR_RAILING"] = True
    obj.color = rail_mat.diffuse_color
    target_col.objects.link(obj)
    return obj


_HB5_CABINET_SYMBOLS = {
    "base_cabinet",
    "base_drawer_cabinet",
    "sink_base_cabinet",
    "corner_base_cabinet",
    "upper_cabinet",
    "corner_upper_cabinet",
    "tall_pantry",
    "island_cabinet",
    "vanity_single",
    "vanity_double",
}

_HB5_APPLIANCE_SYMBOLS = {
    "range_stove",
    "refrigerator",
    "dishwasher",
    "range_hood",
    "microwave",
    "cooktop",
    "wall_oven",
    "kitchen_sink_single",
    "kitchen_sink_double",
    "washer",
    "dryer",
}

_PLUMBING_MECHANICAL_SYMBOLS = {
    "toilet",
    "bathtub",
    "shower_square",
    "shower_corner",
    "pedestal_sink",
    "utility_sink",
    "water_heater",
    "furnace",
    "air_conditioner",
}

_FURNITURE_SYMBOLS = {
    "sofa",
    "loveseat",
    "armchair",
    "coffee_table",
    "end_table",
    "tv_console",
    "bed_king",
    "bed_queen",
    "bed_twin",
    "nightstand",
    "dresser",
    "dining_table",
    "dining_chair",
    "desk",
    "office_chair",
    "bookshelf",
}


def _get_or_create_simple_material(
    mat_id: str,
    base_col: Tuple[float, float, float, float],
    metallic: float = 0.0,
    roughness: float = 0.5,
    alpha: float = 1.0,
):
    import bpy

    existing = bpy.data.materials.get(mat_id)
    if existing is not None:
        return existing
    mat = bpy.data.materials.new(name=mat_id)
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = base_col
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        if alpha < 0.999 and "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
    mat.diffuse_color = (base_col[0], base_col[1], base_col[2], alpha)
    return mat


def _bm_add_box(
    bm,
    x0: float,
    y0: float,
    z0: float,
    x1: float,
    y1: float,
    z1: float,
    mat_index: int = 0,
) -> None:
    if abs(x1 - x0) < 1e-5 or abs(y1 - y0) < 1e-5 or abs(z1 - z0) < 1e-5:
        return
    xa, xb = (x0, x1) if x0 < x1 else (x1, x0)
    ya, yb = (y0, y1) if y0 < y1 else (y1, y0)
    za, zb = (z0, z1) if z0 < z1 else (z1, z0)
    v = [
        bm.verts.new((xa, ya, za)),
        bm.verts.new((xb, ya, za)),
        bm.verts.new((xb, yb, za)),
        bm.verts.new((xa, yb, za)),
        bm.verts.new((xa, ya, zb)),
        bm.verts.new((xb, ya, zb)),
        bm.verts.new((xb, yb, zb)),
        bm.verts.new((xa, yb, zb)),
    ]
    faces = [
        (v[4], v[5], v[6], v[7]),
        (v[3], v[2], v[1], v[0]),
        (v[0], v[1], v[5], v[4]),
        (v[1], v[2], v[6], v[5]),
        (v[2], v[3], v[7], v[6]),
        (v[3], v[0], v[4], v[7]),
    ]
    for fverts in faces:
        f = bm.faces.new(fverts)
        f.material_index = mat_index


def _bm_add_cylinder(
    bm,
    cx: float,
    cy: float,
    z0: float,
    z1: float,
    radius: float,
    segments: int = 20,
    mat_index: int = 0,
) -> None:
    from mathutils import Matrix
    import bmesh

    h = max(1e-4, z1 - z0)
    res = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=h,
        matrix=Matrix.Translation((cx, cy, z0 + h / 2.0)),
    )
    if mat_index != 0:
        for g in res.get("verts", []):
            for f in g.link_faces:
                f.material_index = mat_index


def _finalize_bmesh_object(
    bm,
    name: str,
    materials: List[object],
    loc: Tuple[float, float, float],
    rot_z: float,
    target_col,
    identifier: str,
):
    import bmesh
    import bpy

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        is_vert = abs(face.normal.z) < 0.25
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x + co.y, co.z) if is_vert else (co.x, co.y)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for mat in materials:
        mesh.materials.append(mat)

    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.rotation_euler = (0.0, 0.0, rot_z)
    obj["ESTISKETCH_ID"] = identifier
    if materials:
        obj.color = materials[0].diffuse_color
    target_col.objects.link(obj)
    return obj


def _move_hierarchy_to_collection(root_obj, target_col) -> None:
    _move_object_to_collection(root_obj, target_col)
    for child in list(root_obj.children_recursive):
        _move_object_to_collection(child, target_col)


def _build_hb5_cabinet(
    fx: ParsedFixture,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
    types_frameless,
    solver_frameless,
):
    sym = fx.symbol_type
    w_m = max(0.15, fx.width * INCH_TO_M)
    d_m = max(0.15, fx.depth * INCH_TO_M)
    h_m = max(0.15, fx.height * INCH_TO_M)

    if sym == "upper_cabinet":
        cab = types_frameless.UpperCabinet()
        cab.width, cab.depth, cab.height = w_m, d_m, h_m
        cab.create(f"Cabinet_{sym}_{fx.identifier}")
    elif sym == "tall_pantry":
        cab = types_frameless.TallCabinet()
        cab.width, cab.depth, cab.height = w_m, d_m, h_m
        cab.create(f"Cabinet_{sym}_{fx.identifier}")
    elif sym == "corner_base_cabinet":
        cab = types_frameless.PieCutCornerBaseCabinet()
        cab.corner_size = w_m
        cab.depth = 24.0 * INCH_TO_M
        cab.height = h_m
        cab.create(f"Cabinet_{sym}_{fx.identifier}")
        if cab.has_input("Left Depth"):
            cab.set_input("Left Depth", 24.0 * INCH_TO_M)
        if cab.has_input("Right Depth"):
            cab.set_input("Right Depth", 24.0 * INCH_TO_M)
    elif sym == "corner_upper_cabinet":
        cab = types_frameless.PieCutCornerUpperCabinet()
        cab.corner_size = w_m
        cab.depth = 12.0 * INCH_TO_M
        cab.height = h_m
        cab.create(f"Cabinet_{sym}_{fx.identifier}")
        if cab.has_input("Left Depth"):
            cab.set_input("Left Depth", 12.0 * INCH_TO_M)
        if cab.has_input("Right Depth"):
            cab.set_input("Right Depth", 12.0 * INCH_TO_M)
    else:
        cab = types_frameless.BaseCabinet()
        cab.default_exterior = "3 Drawers" if sym == "base_drawer_cabinet" else "Doors"
        cab.width, cab.depth, cab.height = w_m, d_m, h_m
        cab.create(f"Cabinet_{sym}_{fx.identifier}")
        if sym == "sink_base_cabinet":
            try:
                cab.set_property("Base Top Construction", 2)
            except Exception:
                pass

    cab.set_input("Dim X", w_m)
    cab.set_input("Dim Y", d_m if "corner" not in sym else w_m)
    cab.set_input("Dim Z", h_m)
    try:
        solver_frameless.recalculate_cabinet(cab.obj)
    except Exception as exc:
        print(f"Warning: frameless solver recalc skipped for {fx.identifier}: {exc}")

    loc, rot_z = compute_hb5_fixture_transform(fx, lvl.elevation, cx, cy)
    cab.obj.location = loc
    cab.obj.rotation_euler = (0.0, 0.0, rot_z)
    cab.obj["ESTISKETCH_ID"] = fx.identifier
    cab.obj["ESTISKETCH_SYMBOL"] = sym
    _move_hierarchy_to_collection(cab.obj, target_col)
    return cab.obj


def _build_countertop_mesh(
    fx: ParsedFixture,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
):
    import bmesh

    if not fx.has_countertop:
        return None

    w_m = max(0.1, fx.width * INCH_TO_M)
    d_m = max(0.1, fx.depth * INCH_TO_M)
    hw, hd = w_m / 2.0, d_m / 2.0
    oh_m = max(0.0, fx.countertop_overhang * INCH_TO_M)
    ct_t = max(0.015, fx.countertop_thickness * INCH_TO_M)

    ct_presets = {
        "quartz": ((0.90, 0.90, 0.88, 1.0), 0.20),
        "granite": ((0.35, 0.36, 0.38, 1.0), 0.25),
        "marble": ((0.94, 0.94, 0.95, 1.0), 0.18),
        "butcher_block": ((0.64, 0.45, 0.26, 1.0), 0.45),
        "laminate": ((0.85, 0.82, 0.76, 1.0), 0.40),
        "concrete": ((0.55, 0.56, 0.56, 1.0), 0.65),
        "solid_surface": ((0.92, 0.92, 0.90, 1.0), 0.25),
    }
    col, rough = ct_presets.get(fx.countertop_material, ((0.88, 0.88, 0.86, 1.0), 0.25))
    if fx.countertop_color is not None:
        col = (fx.countertop_color[0], fx.countertop_color[1], fx.countertop_color[2], 1.0)

    ct_mat = _get_or_create_simple_material(
        f"EstiSketch_CT_{fx.countertop_material}", col, metallic=0.0, roughness=rough
    )
    steel_mat = _get_or_create_simple_material(
        "EstiSketch_BrushedSteel", (0.72, 0.74, 0.76, 1.0), metallic=0.85, roughness=0.25
    )

    bm = bmesh.new()
    if fx.symbol_type == "corner_base_cabinet":
        arm_m = min(24.0 * INCH_TO_M + oh_m, w_m, d_m)
        # Back at +Y (+hd) and Left (-hw); open quadrant at (+X, -Y)
        pts = [
            (-hw, hd),
            (hw, hd),
            (hw, hd - arm_m),
            (-hw + arm_m, hd - arm_m),
            (-hw + arm_m, -hd),
            (-hw, -hd),
        ]
        _extrude_prism_z(bm, pts, 0.0, ct_t)
        if fx.has_backsplash:
            bs_h = 4.0 * INCH_TO_M
            bs_d = 0.75 * INCH_TO_M
            _bm_add_box(bm, -hw, hd - bs_d, ct_t, hw, hd, ct_t + bs_h, mat_index=0)
            _bm_add_box(bm, -hw, -hd, ct_t, -hw + bs_d, hd - bs_d, ct_t + bs_h, mat_index=0)
    else:
        # Back at +hd, front overhangs toward -Y (-hd - oh_m)
        _bm_add_box(bm, -hw, -hd - oh_m, 0.0, hw, hd, ct_t, mat_index=0)
        if fx.has_backsplash and fx.symbol_type != "island_cabinet":
            bs_h = 4.0 * INCH_TO_M
            bs_d = 0.75 * INCH_TO_M
            _bm_add_box(bm, -hw, hd - bs_d, ct_t, hw, hd, ct_t + bs_h, mat_index=0)

    # Add integrated sink rim & faucet for sink base and bath vanities
    if fx.symbol_type in ("sink_base_cabinet", "vanity_single", "vanity_double"):
        bowls = [-w_m * 0.24, w_m * 0.24] if fx.symbol_type == "vanity_double" else [0.0]
        bw = min(w_m * 0.36, 18.0 * INCH_TO_M) if len(bowls) > 1 else min(w_m * 0.72, 28.0 * INCH_TO_M)
        bd = min(d_m * 0.62, 15.0 * INCH_TO_M)
        rim = 1.0 * INCH_TO_M
        for bx in bowls:
            _bm_add_box(bm, bx - bw / 2.0, -bd / 2.0, ct_t, bx + bw / 2.0, bd / 2.0, ct_t + 0.008, mat_index=1)
            _bm_add_box(bm, bx - bw / 2.0 + rim, -bd / 2.0 + rim, ct_t + 0.004, bx + bw / 2.0 - rim, bd / 2.0 - rim, ct_t + 0.012, mat_index=1)
            fy = bd / 2.0 + 0.025
            _bm_add_cylinder(bm, bx, fy, ct_t, ct_t + 0.16, 0.014, segments=12, mat_index=1)
            _bm_add_box(bm, bx - 0.012, fy - 0.09, ct_t + 0.14, bx + 0.012, fy + 0.01, ct_t + 0.165, mat_index=1)

    loc, rot_z = compute_centered_fixture_transform(fx, lvl.elevation + fx.height, cx, cy)
    obj = _finalize_bmesh_object(
        bm,
        f"Countertop_{fx.symbol_type}_{fx.identifier}",
        [ct_mat, steel_mat],
        loc,
        rot_z,
        target_col,
        fx.identifier,
    )
    obj["IS_COUNTERTOP_BP"] = True
    return obj


def _build_hb5_appliance(
    fx: ParsedFixture,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
    types_appliances,
    appliance_geo,
):
    import bmesh
    import bpy

    cls_map = {
        "range_stove": ("Range", types_appliances.Range),
        "refrigerator": ("Refrigerator", types_appliances.Refrigerator),
        "dishwasher": ("Dishwasher", types_appliances.Dishwasher),
        "range_hood": ("Hood", types_appliances.Hood),
        "microwave": ("Microwave", types_appliances.Microwave),
        "cooktop": ("Cooktop", types_appliances.Cooktop),
        "wall_oven": ("Wall Oven", types_appliances.WallOven),
        "kitchen_sink_single": ("Sink", types_appliances.Sink),
        "kitchen_sink_double": ("Sink", types_appliances.Sink),
        "washer": ("Washing Machine", types_appliances.WashingMachine),
        "dryer": ("Dryer", types_appliances.Dryer),
    }
    label, app_cls = cls_map[fx.symbol_type]
    w_m = max(0.15, fx.width * INCH_TO_M)
    d_m = max(0.15, fx.depth * INCH_TO_M)
    h_m = max(0.08, fx.height * INCH_TO_M)

    app = app_cls()
    app.width = w_m
    app.depth = d_m
    app.height = h_m
    app.create(f"{label}_{fx.identifier}")
    app.set_input("Dim X", w_m)
    app.set_input("Dim Y", d_m)
    app.set_input("Dim Z", h_m)

    if fx.symbol_type == "kitchen_sink_single":
        app.obj["Sink Type"] = "Single Bowl"
    elif fx.symbol_type == "microwave" and fx.elevation >= 48.0:
        app.obj["Over Range"] = True

    if appliance_geo.supports(app.obj):
        try:
            opts = appliance_geo.defaults_for(app.obj)
            appliance_geo.set_opts(app.obj, opts)
            appliance_geo.build_geometry(app.obj)
        except Exception as exc:
            print(f"Warning: appliance_geo failed for {fx.identifier}: {exc}")
    else:
        # WashingMachine & Dryer solid cabinet + front porthole door in HB5 local coords (X: 0..W, Y: -D..0)
        white_mat = _get_or_create_simple_material(
            "EstiSketch_Appliance_White", (0.92, 0.93, 0.94, 1.0), metallic=0.1, roughness=0.35
        )
        dark_mat = _get_or_create_simple_material(
            "EstiSketch_Appliance_DarkGlass", (0.10, 0.11, 0.13, 1.0), metallic=0.4, roughness=0.18
        )
        bm = bmesh.new()
        _bm_add_box(bm, 0.0, -d_m, 0.0, w_m, 0.0, h_m, mat_index=0)
        _bm_add_box(bm, 0.02, -d_m - 0.015, h_m - 0.16, w_m - 0.02, -d_m, h_m - 0.02, mat_index=1)
        door_r = min(w_m, h_m) * 0.28
        _bm_add_box(
            bm,
            w_m / 2.0 - door_r,
            -d_m - 0.025,
            h_m * 0.46 - door_r,
            w_m / 2.0 + door_r,
            -d_m,
            h_m * 0.46 + door_r,
            mat_index=1,
        )
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        body_mesh = bpy.data.meshes.new(f"{label}_Body_{fx.identifier}")
        bm.to_mesh(body_mesh)
        bm.free()
        body_mesh.materials.append(white_mat)
        body_mesh.materials.append(dark_mat)
        body_obj = bpy.data.objects.new(f"{label}_Body_{fx.identifier}", body_mesh)
        body_obj.parent = app.obj
        target_col.objects.link(body_obj)

    loc, rot_z = compute_hb5_fixture_transform(fx, lvl.elevation, cx, cy)
    app.obj.location = loc
    app.obj.rotation_euler = (0.0, 0.0, rot_z)
    app.obj["ESTISKETCH_ID"] = fx.identifier
    app.obj["ESTISKETCH_SYMBOL"] = fx.symbol_type
    _move_hierarchy_to_collection(app.obj, target_col)
    return app.obj


def _build_plumbing_mechanical_mesh(
    fx: ParsedFixture,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
):
    import bmesh

    sym = fx.symbol_type
    w_m = max(0.15, fx.width * INCH_TO_M)
    d_m = max(0.15, fx.depth * INCH_TO_M)
    h_m = max(0.15, fx.height * INCH_TO_M)
    hw, hd = w_m / 2.0, d_m / 2.0

    porcelain = _get_or_create_simple_material(
        "EstiSketch_Porcelain", (0.96, 0.96, 0.97, 1.0), metallic=0.0, roughness=0.22
    )
    chrome = _get_or_create_simple_material(
        "EstiSketch_Chrome", (0.82, 0.84, 0.86, 1.0), metallic=0.92, roughness=0.15
    )
    glass = _get_or_create_simple_material(
        "EstiSketch_ShowerGlass", (0.78, 0.88, 0.92, 1.0), metallic=0.0, roughness=0.08, alpha=0.32
    )
    mech = _get_or_create_simple_material(
        "EstiSketch_MechanicalMetal", (0.52, 0.55, 0.58, 1.0), metallic=0.55, roughness=0.45
    )

    bm = bmesh.new()
    mats = [porcelain, chrome]

    if sym == "toilet":
        tank_d = d_m * 0.30
        _bm_add_box(bm, -hw * 0.88, hd - tank_d, h_m * 0.48, hw * 0.88, hd - 0.01, h_m, mat_index=0)
        _bm_add_box(bm, -hw * 0.92, hd - tank_d - 0.01, h_m - 0.04, hw * 0.92, hd, h_m + 0.02, mat_index=0)
        bowl_r = min(hw * 0.72, (d_m - tank_d) * 0.45)
        bowl_cy = -hd + bowl_r + 0.02
        _bm_add_cylinder(bm, 0.0, bowl_cy, 0.0, h_m * 0.52, bowl_r * 0.70, segments=18, mat_index=0)
        _bm_add_cylinder(bm, 0.0, bowl_cy, h_m * 0.46, h_m * 0.56, bowl_r, segments=20, mat_index=0)
    elif sym == "bathtub":
        wall_t = 2.5 * INCH_TO_M
        _bm_add_box(bm, -hw, -hd, 0.0, hw, hd, wall_t, mat_index=0)
        _bm_add_box(bm, -hw, hd - wall_t, wall_t, hw, hd, h_m, mat_index=0)
        _bm_add_box(bm, -hw, -hd, wall_t, hw, -hd + wall_t, h_m, mat_index=0)
        _bm_add_box(bm, -hw, -hd + wall_t, wall_t, -hw + wall_t, hd - wall_t, h_m, mat_index=0)
        _bm_add_box(bm, hw - wall_t, -hd + wall_t, wall_t, hw, hd - wall_t, h_m, mat_index=0)
        _bm_add_box(bm, -hw + 0.01, -0.02, h_m, -hw + 0.14, 0.02, h_m + 0.06, mat_index=1)
    elif sym in ("shower_square", "shower_corner"):
        mats = [porcelain, glass, chrome]
        curb_h = 4.0 * INCH_TO_M
        curb_w = 2.5 * INCH_TO_M
        gt = 0.4 * INCH_TO_M
        if sym == "shower_corner":
            chamf = min(w_m, d_m) * 0.42
            # Back at +Y (+hd) and Left (-hw), front-right chamfered corner at (+hw, -hd)
            pts = [(-hw, hd), (hw, hd), (hw, -hd + chamf), (hw - chamf, -hd), (-hw, -hd)]
            _extrude_prism_z(bm, pts, 0.0, curb_h)
            _bm_add_box(bm, hw - gt, -hd + chamf, curb_h, hw, hd, h_m, mat_index=1)
            _bm_add_box(bm, -hw, -hd, curb_h, hw - chamf, -hd + gt, h_m, mat_index=1)
            # Angled front glass panel
            x0, y0 = hw - chamf, -hd
            x1, y1 = hw, -hd + chamf
            dx, dy = x1 - x0, y1 - y0
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L * gt, dx / L * gt
            _extrude_prism_z(bm, [(x0, y0), (x1, y1), (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)], curb_h, h_m)
        else:
            _bm_add_box(bm, -hw, -hd, 0.0, hw, hd, curb_h, mat_index=0)
            _bm_add_box(bm, -hw, -hd, curb_h, hw, -hd + gt, h_m, mat_index=1)
            _bm_add_box(bm, hw - gt, -hd, curb_h, hw, hd, h_m, mat_index=1)
            _bm_add_box(bm, -hw, -hd, curb_h, -hw + gt, hd, h_m, mat_index=1)
        _bm_add_cylinder(bm, 0.0, hd - curb_w, h_m * 0.85, h_m * 0.88, 0.04, segments=12, mat_index=2)
    elif sym in ("pedestal_sink", "utility_sink"):
        basin_z0 = h_m - 0.16
        if sym == "pedestal_sink":
            _bm_add_cylinder(bm, 0.0, 0.02, 0.0, basin_z0, min(hw, hd) * 0.36, segments=16, mat_index=0)
        else:
            leg_w = 0.04
            for lx in (-hw + 0.03, hw - 0.07):
                for ly in (-hd + 0.03, hd - 0.07):
                    _bm_add_box(bm, lx, ly, 0.0, lx + leg_w, ly + leg_w, basin_z0, mat_index=1)
        _bm_add_box(bm, -hw, -hd, basin_z0, hw, hd, h_m, mat_index=0)
        _bm_add_cylinder(bm, 0.0, hd - 0.05, h_m, h_m + 0.14, 0.015, segments=10, mat_index=1)
    elif sym == "water_heater":
        mats = [mech, chrome]
        r = min(hw, hd) * 0.92
        _bm_add_cylinder(bm, 0.0, 0.0, 0.0, h_m, r, segments=24, mat_index=0)
        _bm_add_cylinder(bm, 0.0, 0.0, h_m, h_m + 0.15, r * 0.25, segments=14, mat_index=1)
    else:
        # furnace / air_conditioner
        mats = [mech, chrome]
        _bm_add_box(bm, -hw, -hd, 0.0, hw, hd, h_m, mat_index=0)
        if sym == "air_conditioner":
            _bm_add_cylinder(bm, 0.0, 0.0, h_m, h_m + 0.03, min(hw, hd) * 0.72, segments=20, mat_index=1)
        else:
            _bm_add_box(bm, -hw * 0.75, -hd - 0.01, h_m * 0.2, hw * 0.75, -hd, h_m * 0.8, mat_index=1)

    loc, rot_z = compute_centered_fixture_transform(fx, lvl.elevation, cx, cy)
    obj = _finalize_bmesh_object(
        bm,
        f"Plumbing_{sym}_{fx.identifier}",
        mats,
        loc,
        rot_z,
        target_col,
        fx.identifier,
    )
    obj["IS_PLUMBING_MECHANICAL"] = True
    return obj


def _build_furniture_mesh(
    fx: ParsedFixture,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
):
    import bmesh

    sym = fx.symbol_type
    w_m = max(0.15, fx.width * INCH_TO_M)
    d_m = max(0.15, fx.depth * INCH_TO_M)
    h_m = max(0.15, fx.height * INCH_TO_M)
    hw, hd = w_m / 2.0, d_m / 2.0

    wood_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Wood", (0.45, 0.30, 0.18, 1.0), roughness=0.45
    )
    walnut_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Walnut", (0.26, 0.17, 0.11, 1.0), roughness=0.40
    )
    fabric_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Fabric", (0.58, 0.56, 0.52, 1.0), roughness=0.85
    )
    linen_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Linen", (0.90, 0.89, 0.86, 1.0), roughness=0.80
    )
    duvet_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Duvet", (0.34, 0.44, 0.54, 1.0), roughness=0.82
    )
    screen_mat = _get_or_create_simple_material(
        "EstiSketch_TVScreen", (0.04, 0.04, 0.05, 1.0), metallic=0.2, roughness=0.12
    )
    metal_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Metal", (0.22, 0.23, 0.25, 1.0), metallic=0.8, roughness=0.35
    )

    bm = bmesh.new()
    mats = [wood_mat]

    if sym in ("bed_king", "bed_queen", "bed_twin"):
        mats = [wood_mat, linen_mat, duvet_mat]
        frame_h = 0.22
        matt_h = 0.24
        hb_h = 1.08
        hb_t = 0.09
        # Wood platform & tall headboard at +Y (+hd)
        _bm_add_box(bm, -hw, -hd, 0.06, hw, hd, frame_h, mat_index=0)
        _bm_add_box(bm, -hw, hd - hb_t, 0.0, hw, hd, hb_h, mat_index=0)
        for lx in (-hw + 0.04, hw - 0.12):
            _bm_add_box(bm, lx, -hd + 0.04, 0.0, lx + 0.08, -hd + 0.12, 0.06, mat_index=0)
        # Mattress
        pad = 0.03
        _bm_add_box(bm, -hw + pad, -hd + pad, frame_h, hw - pad, hd - hb_t, frame_h + matt_h, mat_index=1)
        # Duvet covering lower 68% of mattress
        duvet_y = hd - hb_t - (d_m - hb_t) * 0.32
        _bm_add_box(
            bm,
            -hw + pad * 0.5,
            -hd + pad * 0.5,
            frame_h + matt_h * 0.5,
            hw - pad * 0.5,
            duvet_y,
            frame_h + matt_h + 0.03,
            mat_index=2,
        )
        # Pillows near headboard
        p_cnt = 1 if sym == "bed_twin" else 2
        p_gap = 0.08
        p_w = (w_m - (p_cnt + 1) * p_gap) / p_cnt
        for pi in range(p_cnt):
            px0 = -hw + p_gap + pi * (p_w + p_gap)
            _bm_add_box(
                bm,
                px0,
                hd - hb_t - 0.36,
                frame_h + matt_h,
                px0 + p_w,
                hd - hb_t - 0.04,
                frame_h + matt_h + 0.11,
                mat_index=1,
            )

    elif sym in ("sofa", "loveseat", "armchair"):
        mats = [fabric_mat, walnut_mat]
        leg_h = 0.10
        base_h = 0.24
        seat_h = 0.44
        arm_w = 0.15
        back_d = 0.20
        # Legs
        for lx in (-hw + 0.04, hw - 0.10):
            for ly in (-hd + 0.04, hd - 0.10):
                _bm_add_box(bm, lx, ly, 0.0, lx + 0.06, ly + 0.06, leg_h, mat_index=1)
        # Frame base, backrest (+Y), left/right arms
        _bm_add_box(bm, -hw, -hd, leg_h, hw, hd, base_h, mat_index=0)
        _bm_add_box(bm, -hw, hd - back_d, base_h, hw, hd, h_m, mat_index=0)
        _bm_add_box(bm, -hw, -hd, base_h, -hw + arm_w, hd - back_d, h_m * 0.72, mat_index=0)
        _bm_add_box(bm, hw - arm_w, -hd, base_h, hw, hd - back_d, h_m * 0.72, mat_index=0)
        # Seat cushions
        c_cnt = 3 if sym == "sofa" else (2 if sym == "loveseat" else 1)
        c_span = max(0.2, w_m - 2.0 * arm_w)
        c_w = (c_span - (c_cnt - 1) * 0.015) / c_cnt
        for ci in range(c_cnt):
            cx0 = -hw + arm_w + ci * (c_w + 0.015)
            _bm_add_box(bm, cx0, -hd + 0.01, base_h, cx0 + c_w, hd - back_d - 0.01, seat_h, mat_index=0)

    elif sym in ("dining_table", "coffee_table", "end_table"):
        mats = [wood_mat]
        top_t = 0.045
        leg_w = 0.065 if sym == "dining_table" else 0.05
        inset = 0.05
        _bm_add_box(bm, -hw, -hd, h_m - top_t, hw, hd, h_m, mat_index=0)
        # Apron
        _bm_add_box(bm, -hw + inset, -hd + inset, h_m - top_t - 0.06, hw - inset, hd - inset, h_m - top_t, mat_index=0)
        for lx in (-hw + inset, hw - inset - leg_w):
            for ly in (-hd + inset, hd - inset - leg_w):
                _bm_add_box(bm, lx, ly, 0.0, lx + leg_w, ly + leg_w, h_m - top_t, mat_index=0)

    elif sym == "dining_chair":
        mats = [wood_mat, fabric_mat]
        seat_z = 0.45
        leg_w = 0.038
        for lx in (-hw + 0.02, hw - 0.02 - leg_w):
            for ly in (-hd + 0.02, hd - 0.02 - leg_w):
                _bm_add_box(bm, lx, ly, 0.0, lx + leg_w, ly + leg_w, seat_z, mat_index=0)
        _bm_add_box(bm, -hw, -hd, seat_z, hw, hd, seat_z + 0.05, mat_index=1)
        _bm_add_box(bm, -hw + 0.02, hd - 0.05, seat_z + 0.05, hw - 0.02, hd, h_m, mat_index=0)

    elif sym == "office_chair":
        mats = [metal_mat, fabric_mat]
        seat_z = 0.46
        _bm_add_cylinder(bm, 0.0, 0.0, 0.0, 0.06, 0.04, segments=12, mat_index=0)
        _bm_add_box(bm, -hw * 0.8, -0.025, 0.02, hw * 0.8, 0.025, 0.05, mat_index=0)
        _bm_add_box(bm, -0.025, -hd * 0.8, 0.02, 0.025, hd * 0.8, 0.05, mat_index=0)
        _bm_add_cylinder(bm, 0.0, 0.0, 0.05, seat_z, 0.03, segments=12, mat_index=0)
        _bm_add_box(bm, -hw * 0.85, -hd * 0.82, seat_z, hw * 0.85, hd * 0.82, seat_z + 0.07, mat_index=1)
        _bm_add_box(bm, -hw * 0.78, hd * 0.70, seat_z + 0.07, hw * 0.78, hd * 0.86, h_m, mat_index=1)
        _bm_add_box(bm, -hw * 0.92, -hd * 0.35, seat_z + 0.07, -hw * 0.80, hd * 0.65, seat_z + 0.24, mat_index=0)
        _bm_add_box(bm, hw * 0.80, -hd * 0.35, seat_z + 0.07, hw * 0.92, hd * 0.65, seat_z + 0.24, mat_index=0)

    elif sym == "desk":
        mats = [walnut_mat, metal_mat]
        top_t = 0.04
        ped_w = min(0.40, w_m * 0.28)
        _bm_add_box(bm, -hw, -hd, h_m - top_t, hw, hd, h_m, mat_index=0)
        _bm_add_box(bm, hw - ped_w - 0.02, -hd + 0.03, 0.05, hw - 0.02, hd - 0.03, h_m - top_t, mat_index=0)
        _bm_add_box(bm, -hw + 0.03, -hd + 0.04, 0.0, -hw + 0.08, hd - 0.04, h_m - top_t, mat_index=1)

    elif sym in ("nightstand", "dresser", "tv_console"):
        mats = [walnut_mat, metal_mat, screen_mat]
        _bm_add_box(bm, -hw, -hd, 0.06, hw, hd, h_m, mat_index=0)
        for lx in (-hw + 0.04, hw - 0.09):
            for ly in (-hd + 0.04, hd - 0.09):
                _bm_add_box(bm, lx, ly, 0.0, lx + 0.05, ly + 0.05, 0.06, mat_index=0)
        rows = 2 if sym == "nightstand" else (3 if sym == "dresser" else 2)
        band_h = (h_m - 0.12) / rows
        for ri in range(rows):
            bz = 0.08 + ri * band_h
            _bm_add_box(bm, -hw + 0.04, -hd - 0.015, bz + 0.015, hw - 0.04, -hd, bz + band_h - 0.015, mat_index=0)
            _bm_add_box(bm, -0.06, -hd - 0.025, bz + band_h * 0.45, 0.06, -hd - 0.015, bz + band_h * 0.55, mat_index=1)
        if sym == "tv_console":
            tv_w = min(w_m * 0.82, 1.32)
            tv_h = 0.76
            _bm_add_box(bm, -0.18, -0.06, h_m, 0.18, 0.06, h_m + 0.03, mat_index=1)
            _bm_add_box(bm, -0.04, -0.02, h_m + 0.03, 0.04, 0.02, h_m + 0.12, mat_index=1)
            _bm_add_box(bm, -tv_w / 2.0, -0.03, h_m + 0.10, tv_w / 2.0, 0.03, h_m + 0.10 + tv_h, mat_index=2)

    elif sym == "bookshelf":
        mats = [wood_mat]
        bt = 0.03
        _bm_add_box(bm, -hw, -hd, 0.0, -hw + bt, hd, h_m, mat_index=0)
        _bm_add_box(bm, hw - bt, -hd, 0.0, hw, hd, h_m, mat_index=0)
        _bm_add_box(bm, -hw + bt, hd - bt, 0.0, hw - bt, hd, h_m, mat_index=0)
        for si in range(6):
            sz = (si / 5.0) * (h_m - bt)
            _bm_add_box(bm, -hw + bt, -hd, sz, hw - bt, hd - bt, sz + bt, mat_index=0)

    loc, rot_z = compute_centered_fixture_transform(fx, lvl.elevation, cx, cy)
    obj = _finalize_bmesh_object(
        bm,
        f"Furniture_{sym}_{fx.identifier}",
        mats,
        loc,
        rot_z,
        target_col,
        fx.identifier,
    )
    obj["IS_FURNITURE"] = True
    return obj


def _add_boolean_cut(wall_obj, cutting_obj) -> None:
    mod_name = f"Boolean_{cutting_obj.name}"
    if mod_name in wall_obj.modifiers:
        return
    mod = wall_obj.modifiers.new(name=mod_name, type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutting_obj
    mod.solver = "EXACT"
    cutting_obj.hide_render = True


def _build_wall_span_cutter(
    wall_obj,
    x_start_m: float,
    x_end_m: float,
    wall_len_m: float,
    thickness_m: float,
    z_min_m: float,
    z_max_m: float,
    openings_col,
    name: str,
):
    import bmesh
    import bpy

    x0 = x_start_m - (0.005 if x_start_m <= 1e-4 else 0.0)
    x1 = x_end_m + (0.005 if x_end_m >= wall_len_m - 1e-4 else 0.0)
    bm = bmesh.new()
    _bm_add_box(bm, x0, -0.02, z_min_m - 0.01, x1, thickness_m + 0.02, z_max_m)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    cutter_obj = bpy.data.objects.new(name, mesh)
    cutter_obj.parent = wall_obj
    cutter_obj.display_type = "WIRE"
    cutter_obj.hide_viewport = True
    cutter_obj.hide_render = True
    openings_col.objects.link(cutter_obj)
    return cutter_obj


def _map_window_type(win_type: str) -> str:
    if "fixed" in win_type or "picture" in win_type:
        return "PICTURE"
    if "casement" in win_type:
        return "CASEMENT"
    if "awning" in win_type:
        return "AWNING"
    if "hung" in win_type:
        return "HUNG"
    return "SLIDER"


def _schedule_viewport_frame() -> None:
    import bpy

    def _frame_once():
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type != "VIEW_3D":
                    continue
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.color_type = "OBJECT"
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                if region is not None:
                    with bpy.context.temp_override(window=window, area=area, region=region):
                        try:
                            bpy.ops.view3d.view_all(center=False)
                        except Exception:
                            pass
        return None

    bpy.app.timers.register(_frame_once, first_interval=0.1)


def build_in_blender(xml_path: str, save_blend_path: str = "") -> Dict[str, int]:
    """Build an EstiSketch XML project inside the active Blender scene using HB5."""
    import importlib
    import bpy

    pkg_name = find_hb5_package()
    hb_types = importlib.import_module(pkg_name + ".hb_types")
    walls_op = importlib.import_module(pkg_name + ".operators.walls")
    door_window_geo = importlib.import_module(
        pkg_name + ".product_libraries.common.door_window_geo"
    )
    hb_details = importlib.import_module(pkg_name + ".hb_details")
    GeoNodeText = hb_details.GeoNodeText
    ops_stairs = importlib.import_module(pkg_name + ".operators.ops_stairs")
    types_frameless = importlib.import_module(
        pkg_name + ".product_libraries.frameless.types_frameless"
    )
    solver_frameless = importlib.import_module(
        pkg_name + ".product_libraries.frameless.solver_frameless"
    )
    types_appliances = importlib.import_module(
        pkg_name + ".product_libraries.common.types_appliances"
    )
    appliance_geo = importlib.import_module(
        pkg_name + ".product_libraries.common.appliance_geo"
    )
    surface_materials = importlib.import_module(pkg_name + ".surface_materials")

    project = parse_estisketch_xml(xml_path)
    if project.skipped_openings:
        print(
            f"Warning: skipped {len(project.skipped_openings)} orphaned opening(s): "
            + ", ".join(project.skipped_openings[:8])
        )
    orient_interior_wall_chains(project)
    cx, cy = compute_plan_center(project)

    scene = bpy.context.scene
    _clear_default_scene(scene)

    scene["IS_ROOM_SCENE"] = True
    scene.unit_settings.system = "IMPERIAL"
    scene.unit_settings.length_unit = "INCHES"

    root_col = _ensure_collection("EstiSketch Import", scene.collection)
    _ensure_sun_light(scene, root_col, north_angle=project.north_angle)
    foundations_col = _ensure_collection("Foundations", root_col)

    level_by_id = {lvl.id: lvl for lvl in project.levels}
    level_cols: Dict[str, Dict[str, object]] = {}
    for lvl in project.levels:
        lvl_col = _ensure_collection(f"EstiSketch - {lvl.name}", root_col)
        level_cols[lvl.id] = {
            "walls": _ensure_collection(f"{lvl.name} - Walls", lvl_col),
            "openings": _ensure_collection(f"{lvl.name} - Openings", lvl_col),
            "trim": _ensure_collection(f"{lvl.name} - Trim", lvl_col),
            "rooms": _ensure_collection(f"{lvl.name} - Rooms", lvl_col),
            "ceilings": _ensure_collection(f"{lvl.name} - Ceilings", lvl_col),
            "roofs": _ensure_collection(f"{lvl.name} - Roofs", lvl_col),
            "stairs": _ensure_collection(f"{lvl.name} - Stairs", lvl_col),
            "cabinets": _ensure_collection(f"{lvl.name} - Cabinets & Appliances", lvl_col),
            "plumbing": _ensure_collection(f"{lvl.name} - Plumbing & Mechanical", lvl_col),
            "furniture": _ensure_collection(f"{lvl.name} - Furniture", lvl_col),
        }

    # Build walls grouped by set_index so sequential walls in a set connect cleanly
    # without closing a cyclic COPY_LOCATION dependency loop.
    wall_segments: Dict[Tuple[int, int], List[Tuple[object, float, float, ParsedWall]]] = {}
    built_wall_records: List[Tuple[ParsedWall, object, float, ParsedLevel]] = []
    miter_records_by_level: Dict[
        str, List[Tuple[object, Tuple[float, float], Tuple[float, float], float, bool]]
    ] = {}
    walls_by_set: Dict[int, List[ParsedWall]] = {}
    for pw in project.walls:
        walls_by_set.setdefault(pw.set_index, []).append(pw)

    wall_count = 0
    for set_idx, set_walls in walls_by_set.items():
        prev_hb_wall = None
        prev_end_m: Optional[Tuple[float, float]] = None

        for pw in set_walls:
            if pw.symbolic:
                continue
            lvl = level_by_id.get(pw.level_id, project.levels[0])
            z_m = lvl.elevation * INCH_TO_M
            walls_col = level_cols[lvl.id]["walls"]

            if pw.is_curved and pw.arc_center is not None and pw.arc_radius is not None:
                pts_in = tessellate_curved_wall_points(
                    pw.start, pw.end, pw.arc_center, pw.arc_radius
                )
            else:
                pts_in = [pw.start, pw.end]

            seg_count = len(pts_in) - 1
            segs_for_wall: List[Tuple[object, float, float, ParsedWall]] = []

            for seg_i in range(seg_count):
                p0 = inches_to_blender_xy(pts_in[seg_i][0], pts_in[seg_i][1], cx, cy)
                p1 = inches_to_blender_xy(pts_in[seg_i + 1][0], pts_in[seg_i + 1][1], cx, cy)
                dx = p1[0] - p0[0]
                dy = p1[1] - p0[1]
                length_m = math.hypot(dx, dy)
                if length_m < 1e-4:
                    continue

                t0 = seg_i / seg_count
                t1 = (seg_i + 1) / seg_count
                h0_m = (pw.height + (pw.height_at_end - pw.height) * t0) * INCH_TO_M
                h1_m = (pw.height + (pw.height_at_end - pw.height) * t1) * INCH_TO_M
                thick_m = max(0.02, pw.width * INCH_TO_M)

                hb_wall = hb_types.GeoNodeWall()
                suffix = f"_{seg_i}" if seg_count > 1 else ""
                hb_wall.create(f"Wall_{set_idx}_{pw.wall_index}{suffix}")
                hb_wall.obj["WALL_TYPE"] = "Exterior" if pw.exterior_wall else "Interior"
                hb_wall.obj["ESTISKETCH_ID"] = pw.identifier
                hb_wall.obj["ESTISKETCH_LEVEL"] = lvl.id

                hb_wall.obj.location = (p0[0], p0[1], z_m)
                hb_wall.obj.rotation_euler = (0.0, 0.0, math.atan2(dy, dx))
                hb_wall.set_input("Length", length_m)
                hb_wall.set_input("Thickness", thick_m)
                hb_wall.set_input("Height", h0_m)
                if hb_wall.has_input("End Height"):
                    hb_wall.set_input("End Height", h1_m)
                _assign_wall_materials(
                    hb_wall, scene, pw=pw, surface_materials=surface_materials
                )

                _move_object_to_collection(hb_wall.obj, walls_col)
                if hb_wall.obj_x is not None:
                    _move_object_to_collection(hb_wall.obj_x, walls_col)

                # Connect sequentially if this segment starts at the previous end.
                if (
                    prev_hb_wall is not None
                    and prev_end_m is not None
                    and math.hypot(p0[0] - prev_end_m[0], p0[1] - prev_end_m[1]) < 0.01
                ):
                    hb_wall.connect_to_wall(prev_hb_wall)

                prev_hb_wall = hb_wall
                prev_end_m = p1
                wall_count += 1
                seg_min_h = min(h0_m, h1_m)
                segs_for_wall.append((hb_wall, length_m, seg_min_h, pw))
                built_wall_records.append((pw, hb_wall, length_m, lvl))
                miter_records_by_level.setdefault(lvl.id, []).append(
                    (hb_wall, p0, p1, thick_m, pw.exterior_wall)
                )

            if segs_for_wall:
                wall_segments[(pw.set_index, pw.wall_index)] = segs_for_wall

    bpy.context.view_layer.update()
    if hasattr(walls_op, "refresh_wall_junctions"):
        walls_op.refresh_wall_junctions(scene)
    elif hasattr(walls_op, "update_all_wall_miters"):
        walls_op.update_all_wall_miters()

    for lvl_records in miter_records_by_level.values():
        entries = [
            (hb_w.obj.name, p0, p1, thick_m, is_ext)
            for hb_w, p0, p1, thick_m, is_ext in lvl_records
        ]
        miters = compute_level_wall_miters(entries)
        for hb_w, _, _, _, _ in lvl_records:
            la, ra = miters.get(hb_w.obj.name, (0.0, 0.0))
            hb_w.set_input("Left Angle", la)
            hb_w.set_input("Right Angle", ra)
            hb_w.obj.update_tag()
    bpy.context.view_layer.update()

    hb_props = scene.home_builder
    hb_wm_prefs = bpy.context.window_manager.home_builder.get_user_preferences(bpy.context)

    def _resolve_opening_host(set_idx: int, wall_idx: int, ratio: float):
        segs = wall_segments.get((set_idx, wall_idx))
        if not segs:
            return None
        if len(segs) == 1:
            return (*segs[0], ratio)
        seg_idx, local_r = resolve_curved_wall_segment([s[1] for s in segs], ratio)
        return (*segs[seg_idx], local_r)

    def _apply_neighbor_opening_cuts(
        cuts: List[WallOpeningCut],
        host_pw: ParsedWall,
        host_hb_wall,
        primary_cutter,
        z_min_m: float,
        z_max_m: float,
        openings_col,
        opening_tag: str,
    ) -> None:
        host_thick_m = host_hb_wall.get_input("Thickness")
        for cut in cuts:
            if cut.wall is host_pw:
                continue
            cut_segs = wall_segments.get((cut.wall.set_index, cut.wall.wall_index))
            if not cut_segs:
                continue
            nb_hb_wall, nb_len_m, _, _ = cut_segs[0]
            nb_thick_m = nb_hb_wall.get_input("Thickness")
            same_or_thinner = cut.same_direction and nb_thick_m <= host_thick_m + 1e-4
            if same_or_thinner and primary_cutter is not None:
                _add_boolean_cut(nb_hb_wall.obj, primary_cutter)
            else:
                extra_cutter = _build_wall_span_cutter(
                    nb_hb_wall.obj,
                    cut.x_start_m,
                    cut.x_end_m,
                    nb_len_m,
                    nb_thick_m,
                    z_min_m,
                    z_max_m,
                    openings_col,
                    f"{opening_tag}_Cut_{cut.wall.identifier}",
                )
                _add_boolean_cut(nb_hb_wall.obj, extra_cutter)

    door_intervals_by_wall_obj: Dict[int, List[Tuple[float, float]]] = {}
    door_count = 0
    for pd in project.doors:
        resolved = _resolve_opening_host(pd.set_index, pd.wall_index, pd.ratio)
        if resolved is None:
            continue
        hb_wall, wall_len_m, min_h_m, host_pw, local_ratio = resolved
        lvl = level_by_id.get(pd.level_id, project.levels[0])
        openings_col = level_cols[lvl.id]["openings"]

        if not host_pw.is_curved:
            placement = resolve_opening_chain_placement(
                host_pw, local_ratio, pd.width, project.walls
            )
            width_m = placement.width_m
            x_local = placement.x_local_m
            eff_min_h_m = placement.min_height_m
            cuts = placement.cuts
            for cut in cuts:
                cut_segs = wall_segments.get((cut.wall.set_index, cut.wall.wall_index))
                if cut_segs:
                    door_intervals_by_wall_obj.setdefault(
                        id(cut_segs[0][0].obj), []
                    ).append((cut.x_start_m, cut.x_end_m))
        else:
            width_m = max(0.1, min(pd.width * INCH_TO_M, wall_len_m))
            x_local = compute_opening_local_x(local_ratio, wall_len_m, width_m)
            eff_min_h_m = min_h_m
            cuts = []
            door_intervals_by_wall_obj.setdefault(id(hb_wall.obj), []).append(
                (x_local, x_local + width_m)
            )

        height_m = max(0.2, min(pd.height * INCH_TO_M, eff_min_h_m))
        thickness_m = hb_wall.get_input("Thickness")

        cage = hb_types.GeoNodeCage()
        cage.create(f"Door_{pd.identifier}")
        cage.obj["IS_ENTRY_DOOR_BP"] = True
        cage.obj["MENU_ID"] = "HOME_BUILDER_MT_door_commands"
        cage.obj["ESTISKETCH_ID"] = pd.identifier
        cage.set_input("Dim X", width_m)
        cage.set_input("Dim Y", thickness_m)
        cage.set_input("Dim Z", height_m)
        cage.obj.color = hb_wm_prefs.door_window_color
        cage.obj.display_type = "WIRE"

        cage.obj.parent = hb_wall.obj
        cage.obj.location = (x_local, 0.0, 0.0)
        cage.obj.rotation_euler = (0.0, 0.0, 0.0)
        _move_object_to_collection(cage.obj, openings_col)

        primary_cutter = None
        if pd.door_type == "frame":
            cage.obj["IS_OPEN_DOORWAY"] = True
            _add_boolean_cut(hb_wall.obj, cage.obj)
            primary_cutter = cage.obj
        elif pd.door_type == "garage":
            cage.obj["IS_GARAGE_DOOR"] = True
            _, primary_cutter = _build_garage_door_mesh(
                cage.obj, width_m, thickness_m, height_m, openings_col, hb_wall.obj
            )
        else:
            dim_x = cage.var_input("Dim X", "dim_x")
            dim_y = cage.var_input("Dim Y", "dim_y")
            dim_z = cage.var_input("Dim Z", "dim_z")
            is_double = (
                "double" in pd.door_type
                or "bi-fold" in pd.door_type
                or pd.door_type == "sliding"
            )

            swing_obj = hb_types.GeoNodeDoorSwing()
            swing_obj.create("Door Swing Annotation")
            swing_obj.obj.parent = cage.obj
            swing_obj.driver_input("Dim X", "dim_x", [dim_x])
            swing_obj.driver_input("Dim Y", "dim_y", [dim_y])
            swing_obj.set_input("Is Double", is_double)
            swing_obj.set_input("Swing Inside", pd.orientation == "inswing")
            swing_obj.set_input("Is Left", pd.swing == "left")
            _move_object_to_collection(swing_obj.obj, openings_col)

            txt = GeoNodeText()
            txt.create("Door Text", "DOOR", hb_props.annotation_text_size)
            txt.obj.parent = cage.obj
            txt.obj.rotation_euler.x = math.radians(90)
            txt.driver_location("x", "dim_x/2", [dim_x])
            txt.driver_location("y", "dim_y/2", [dim_y])
            txt.driver_location("z", "dim_z/2", [dim_z])
            txt.set_alignment("CENTER", "CENTER")
            _move_object_to_collection(txt.obj, openings_col)

            opts = dict(door_window_geo.DOOR_DEFAULTS)
            opts["style"] = "CUSTOM"
            opts["threshold_height"] = 0.75 * INCH_TO_M if host_pw.exterior_wall else 0.0
            if pd.door_type == "sliding":
                opts["door_style"] = "LITE_FULL"
                opts["glass_grid_cols"] = 2
                opts["glass_grid_rows"] = 1
            elif "double" in pd.door_type and "bi-fold" not in pd.door_type:
                if host_pw.exterior_wall:
                    opts["door_style"] = "LITE_FULL"
                    opts["glass_grid_cols"] = 2
                    opts["glass_grid_rows"] = 3
                else:
                    opts["door_style"] = "PANEL_4"
            elif "bi-fold" in pd.door_type:
                opts["door_style"] = "PANEL_2"
            elif "pocket" in pd.door_type:
                opts["door_style"] = "FLUSH"
            else:
                opts["door_style"] = "LITE_HALF" if host_pw.exterior_wall else "PANEL_6"

            door_window_geo.set_opts(cage.obj, opts)
            cutting_obj = door_window_geo.update_reveal_cutter(cage.obj)
            _add_boolean_cut(hb_wall.obj, cutting_obj)
            primary_cutter = cutting_obj
            door_window_geo.build_geometry(cage.obj)
            for child in cage.obj.children:
                _move_object_to_collection(child, openings_col)

        _apply_neighbor_opening_cuts(
            cuts,
            host_pw,
            hb_wall,
            primary_cutter,
            0.0,
            height_m,
            openings_col,
            f"Door_{pd.identifier}",
        )
        door_count += 1

    window_count = 0
    for pw_win in project.windows:
        resolved = _resolve_opening_host(pw_win.set_index, pw_win.wall_index, pw_win.ratio)
        if resolved is None:
            continue
        hb_wall, wall_len_m, min_h_m, host_pw, local_ratio = resolved
        lvl = level_by_id.get(pw_win.level_id, project.levels[0])
        openings_col = level_cols[lvl.id]["openings"]

        if not host_pw.is_curved:
            placement = resolve_opening_chain_placement(
                host_pw, local_ratio, pw_win.width, project.walls
            )
            width_m = placement.width_m
            x_local = placement.x_local_m
            eff_min_h_m = placement.min_height_m
            cuts = placement.cuts
        else:
            width_m = max(0.1, min(pw_win.width * INCH_TO_M, wall_len_m))
            x_local = compute_opening_local_x(local_ratio, wall_len_m, width_m)
            eff_min_h_m = min_h_m
            cuts = []

        height_m = max(0.1, min(pw_win.height * INCH_TO_M, max(0.1, eff_min_h_m - 0.05)))
        thickness_m = hb_wall.get_input("Thickness")
        z_local = compute_window_sill_height_m(height_m, eff_min_h_m)

        cage = hb_types.GeoNodeCage()
        cage.create(f"Window_{pw_win.identifier}")
        cage.obj["IS_WINDOW_BP"] = True
        cage.obj["MENU_ID"] = "HOME_BUILDER_MT_window_commands"
        cage.obj["ESTISKETCH_ID"] = pw_win.identifier
        cage.set_input("Dim X", width_m)
        cage.set_input("Dim Y", thickness_m)
        cage.set_input("Dim Z", height_m)
        cage.obj.color = hb_wm_prefs.door_window_color
        cage.obj.display_type = "WIRE"

        cage.obj.parent = hb_wall.obj
        cage.obj.location = (x_local, 0.0, z_local)
        cage.obj.rotation_euler = (0.0, 0.0, 0.0)
        _move_object_to_collection(cage.obj, openings_col)

        dim_x = cage.var_input("Dim X", "dim_x")
        dim_y = cage.var_input("Dim Y", "dim_y")
        dim_z = cage.var_input("Dim Z", "dim_z")
        txt = GeoNodeText()
        txt.create("Window Text", "WINDOW", hb_props.annotation_text_size)
        txt.obj.parent = cage.obj
        txt.obj.rotation_euler.x = math.radians(90)
        txt.driver_location("x", "dim_x/2", [dim_x])
        txt.driver_location("y", "dim_y/2", [dim_y])
        txt.driver_location("z", "dim_z/2", [dim_z])
        txt.set_alignment("CENTER", "CENTER")
        _move_object_to_collection(txt.obj, openings_col)

        opts = dict(door_window_geo.WINDOW_DEFAULTS)
        opts["style"] = "CUSTOM"
        opts["window_type"] = _map_window_type(pw_win.window_type)
        door_window_geo.set_opts(cage.obj, opts)
        cutting_obj = door_window_geo.update_reveal_cutter(cage.obj)
        _add_boolean_cut(hb_wall.obj, cutting_obj)
        door_window_geo.build_geometry(cage.obj)
        for child in cage.obj.children:
            _move_object_to_collection(child, openings_col)

        _apply_neighbor_opening_cuts(
            cuts,
            host_pw,
            hb_wall,
            cutting_obj,
            z_local,
            z_local + height_m,
            openings_col,
            f"Window_{pw_win.identifier}",
        )
        window_count += 1

    door_window_geo.hide_reveal_cutters()

    baseboard_count = 0
    for b_idx, (pw, hb_wall, seg_len_m, lvl) in enumerate(built_wall_records):
        bb_obj = _build_wall_baseboards(
            pw,
            hb_wall,
            seg_len_m,
            door_intervals_by_wall_obj.get(id(hb_wall.obj), []),
            level_cols[lvl.id]["trim"],
            f"Baseboard_{pw.identifier}_{b_idx}",
        )
        if bb_obj is not None:
            baseboard_count += 1

    footer_count = _build_level_footers(
        project, level_by_id, cx, cy, foundations_col, surface_materials
    )
    _build_level_rim_bands(
        project, level_by_id, level_cols, cx, cy, scene, surface_materials
    )

    room_cutouts = compute_room_hole_cutouts(project)
    room_count = 0
    ceiling_count = 0
    cutout_count = 0
    for idx, pr in enumerate(project.rooms):
        lvl = level_by_id.get(pr.level_id, project.levels[0])
        rooms_col = level_cols[lvl.id]["rooms"]
        ceilings_col = level_cols[lvl.id]["ceilings"]
        pts_m = [inches_to_blender_xy(x, y, cx, cy) for x, y in pr.points]
        if pr.is_slab:
            thick_m = max(0.01, pr.slab_thickness * INCH_TO_M)
        elif lvl.elevation > 0.1:
            thick_m = max(0.01, lvl.floor_thickness * INCH_TO_M)
        else:
            thick_m = 0.01
        z_top_m = lvl.elevation * INCH_TO_M
        floor_mat = _get_or_create_floor_material(pr, surface_materials)
        floor_obj = _build_floor_mesh(
            f"Floor_{pr.name}_{idx}",
            pts_m,
            z_top_m,
            thick_m,
            rooms_col,
            pr.is_slab,
            mat=floor_mat,
            pattern_rotation_deg=pr.pattern_rotation,
            pattern_scale=pr.pattern_scale,
        )
        holes_for_room = room_cutouts.get(pr.identifier, [])
        if floor_obj is not None:
            floor_obj["ESTISKETCH_ID"] = pr.identifier
            floor_holes = [h.points for h in holes_for_room if h.cuts_floor]
            cutout_count += _apply_slab_cutouts(
                floor_obj, floor_holes, z_top_m - thick_m, z_top_m, cx, cy, scene
            )
            room_count += 1

        if pr.height > 0.0:
            z_ceil_m = (lvl.elevation + pr.height) * INCH_TO_M
            ceil_thick_m = 0.5 * INCH_TO_M
            ceil_obj = _build_ceiling_mesh(
                f"Ceiling_{pr.name}_{idx}",
                pts_m,
                z_ceil_m,
                ceil_thick_m,
                ceilings_col,
                scene,
            )
            if ceil_obj is not None:
                ceil_obj["ESTISKETCH_ID"] = pr.identifier
                ceil_holes = [h.points for h in holes_for_room if h.cuts_ceiling]
                cutout_count += _apply_slab_cutouts(
                    ceil_obj, ceil_holes, z_ceil_m, z_ceil_m + ceil_thick_m, cx, cy, scene
                )
                ceiling_count += 1

    stair_count = 0
    railing_count = 0
    for ps in project.stairs:
        start_lvl = level_by_id.get(ps.start_level_id, level_by_id.get(ps.level_id, project.levels[0]))
        stairs_col = level_cols[start_lvl.id]["stairs"]
        stair_obj = _build_stair_object(ps, start_lvl, cx, cy, stairs_col, ops_stairs)
        if stair_obj is not None:
            stair_count += 1
        rail_paths = compute_stair_railing_paths_3d(ps, start_lvl.elevation)
        rail_obj = _build_stair_railing_mesh(
            f"Railing_{ps.identifier}", rail_paths, ps.rail_height, cx, cy, stairs_col
        )
        if rail_obj is not None:
            rail_obj["ESTISKETCH_ID"] = ps.identifier
            railing_count += 1

    ext_mat_by_level: Dict[str, object] = {}
    for pw in project.walls:
        if pw.exterior_wall and not pw.symbolic and pw.level_id not in ext_mat_by_level:
            lf, rf = _resolve_wall_side_finishes(pw)
            use_fin = rf if rf.lower() != "drywall" else lf
            if use_fin.lower() != "drywall":
                ext_mat_by_level[pw.level_id] = _get_or_create_wall_finish_material(
                    use_fin, None, surface_materials
                )

    roof_count = 0
    infill_count = 0
    for r_idx, prf in enumerate(project.roofs):
        solved = solve_roof_3d(prf, project)
        lvl = level_by_id.get(solved.level_id, project.levels[0])
        roofs_col = level_cols[lvl.id]["roofs"]
        roof_obj = _build_roof_mesh(f"Roof_{prf.roof_type}_{r_idx}", solved, cx, cy, roofs_col)
        if roof_obj is not None:
            roof_count += 1
        for i_idx, infill in enumerate(solved.gable_infills):
            infill_lvl = level_by_id.get(infill.level_id, lvl)
            walls_col = level_cols[infill_lvl.id]["walls"]
            infill_mat = ext_mat_by_level.get(infill_lvl.id)
            infill_obj = _build_gable_infill_mesh(
                f"GableInfill_{r_idx}_{i_idx}",
                infill,
                cx,
                cy,
                walls_col,
                scene,
                mat=infill_mat,
            )
            if infill_obj is not None:
                infill_count += 1

    cabinet_count = 0
    countertop_count = 0
    appliance_count = 0
    plumbing_count = 0
    furniture_count = 0
    for fx in project.fixtures:
        lvl = level_by_id.get(fx.level_id, project.levels[0])
        sym = fx.symbol_type
        if sym in _HB5_CABINET_SYMBOLS:
            cab_obj = _build_hb5_cabinet(
                fx,
                lvl,
                cx,
                cy,
                level_cols[lvl.id]["cabinets"],
                types_frameless,
                solver_frameless,
            )
            if cab_obj is not None:
                cabinet_count += 1
        elif sym in _HB5_APPLIANCE_SYMBOLS:
            app_obj = _build_hb5_appliance(
                fx,
                lvl,
                cx,
                cy,
                level_cols[lvl.id]["cabinets"],
                types_appliances,
                appliance_geo,
            )
            if app_obj is not None:
                appliance_count += 1
        elif sym in _PLUMBING_MECHANICAL_SYMBOLS:
            pm_obj = _build_plumbing_mechanical_mesh(
                fx, lvl, cx, cy, level_cols[lvl.id]["plumbing"]
            )
            if pm_obj is not None:
                plumbing_count += 1
        else:
            furn_obj = _build_furniture_mesh(
                fx, lvl, cx, cy, level_cols[lvl.id]["furniture"]
            )
            if furn_obj is not None:
                furniture_count += 1

        if fx.has_countertop:
            ct_obj = _build_countertop_mesh(
                fx, lvl, cx, cy, level_cols[lvl.id]["cabinets"]
            )
            if ct_obj is not None:
                countertop_count += 1

    bpy.context.view_layer.update()

    if save_blend_path:
        bpy.ops.wm.save_as_mainfile(filepath=save_blend_path)

    if not bpy.app.background:
        _schedule_viewport_frame()

    return {
        "levels": len(project.levels),
        "walls": wall_count,
        "doors": door_count,
        "windows": window_count,
        "rooms": room_count,
        "ceilings": ceiling_count,
        "roofs": roof_count,
        "gable_infills": infill_count,
        "stairs": stair_count,
        "railings": railing_count,
        "floor_cutouts": cutout_count,
        "cabinets": cabinet_count,
        "countertops": countertop_count,
        "appliances": appliance_count,
        "plumbing_mechanical": plumbing_count,
        "furniture": furniture_count,
        "baseboards": baseboard_count,
        "footers": footer_count,
        "skipped_openings": len(project.skipped_openings),
    }


def _parse_cli_args(argv: List[str]) -> Tuple[str, str]:
    if "--" in argv:
        args = argv[argv.index("--") + 1 :]
    else:
        args = []
    if not args:
        raise SystemExit(
            "Usage: blender --python estisketch_to_hb5.py -- <project.xml> [--save-blend <out.blend>]"
        )
    xml_path = args[0]
    save_blend = ""
    if "--save-blend" in args:
        i = args.index("--save-blend")
        if i + 1 < len(args):
            save_blend = args[i + 1]
    return xml_path, save_blend


if __name__ == "__main__":
    xml_arg, blend_arg = _parse_cli_args(sys.argv)
    stats = build_in_blender(xml_arg, save_blend_path=blend_arg)
    print(f"EstiSketch -> HB5 import complete: {stats}")
