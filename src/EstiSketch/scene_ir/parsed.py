"""Pure-Python dataclasses and XML/canvas parsers for EstiSketch 3D geometry.

This module implements Layer 1 project extraction without importing GTK, Cairo,
or Blender (``bpy``), enabling headless unit testing and direct conversion to
``SceneIR`` for both the native 3D engine and the Blender HB5 bridge. All
dimensional coordinates are in **inches** unless explicitly noted.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field

INCH_TO_M: float = 0.0254

Point2D = tuple[float, float]
Point3D = tuple[float, float, float]
Line2D = tuple[Point2D, Point2D]
RgbColor = tuple[float, float, float]


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
    start: Point2D  # inches
    end: Point2D  # inches
    width: float  # inches
    height: float  # inches
    height_at_end: float  # inches
    exterior_wall: bool
    level_id: str
    layer_id: str
    is_curved: bool = False
    arc_center: Point2D | None = None
    arc_radius: float | None = None
    symbolic: bool = False
    interior_finish: str = "Drywall"
    exterior_finish: str = ""
    left_finish: str = "Drywall"
    right_finish: str = "Drywall"
    left_color: RgbColor | None = None
    right_color: RgbColor | None = None
    left_baseboard: bool = False
    right_baseboard: bool = False
    footer: bool = False
    footer_left_offset: float = 6.0  # inches
    footer_right_offset: float = 6.0  # inches
    footer_depth: float = 8.0  # inches


@dataclass
class ParsedRoom:
    """Room or concrete slab parsed from an EstiSketch project."""

    identifier: str
    name: str
    points: list[Point2D]  # inches
    height: float  # inches
    level_id: str
    floor_type: str = "default"
    is_slab: bool = False
    slab_thickness: float = 4.0  # inches
    floor_pattern: str = "none"
    pattern_rotation: float = 0.0  # degrees
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
    pitch_rise: float | None = None
    overhang: float | None = None  # inches


@dataclass
class ParsedRoof:
    """Roof parsed from an EstiSketch project."""

    identifier: str
    level_id: str
    layer_id: str
    roof_type: str
    pitch_rise: float
    pitch_run: float
    overhang: float  # inches
    material: str
    edges: list[ParsedRoofEdge] = field(default_factory=list)
    ridge_lines: list[Line2D] = field(default_factory=list)
    hip_lines: list[Line2D] = field(default_factory=list)
    valley_lines: list[Line2D] = field(default_factory=list)
    rake_lines: list[Line2D] = field(default_factory=list)
    eave_lines: list[Line2D] = field(default_factory=list)
    outline_points: list[Point2D] = field(default_factory=list)


@dataclass
class SolvedRoofFacet:
    """Closed 3D planar/faceted roof slope in EstiSketch inches."""

    vertices_3d: list[Point3D]
    pitch_rise: float


@dataclass
class SolvedGableInfill:
    """Triangular gable-end wall infill above a flat-topped gable wall (inches)."""

    p_start: Point2D
    p_end: Point2D
    p_peak: Point2D
    z_base: float  # inches
    z_peak: float  # inches
    thickness: float  # inches
    level_id: str


@dataclass
class SolvedRoofGeometry:
    """Solved 3D facets and gable infills for a roof."""

    roof_id: str
    level_id: str
    material: str
    facets: list[SolvedRoofFacet] = field(default_factory=list)
    gable_infills: list[SolvedGableInfill] = field(default_factory=list)


@dataclass
class ParsedStair:
    """Staircase parsed from an EstiSketch project."""

    identifier: str
    layer_id: str
    level_id: str
    start_point: Point2D  # inches
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
    points: list[Point2D] = field(default_factory=list)


@dataclass
class RoomHoleCutout:
    """Derived floor or ceiling cutout polygon (in EstiSketch inches) for a room."""

    points: list[Point2D]
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
    fill_color: RgbColor | None = None
    countertop_color: RgbColor | None = None


@dataclass
class ParsedCustomAsset:
    """Pure-Python representation of a custom `.glb` asset placed in inches."""

    identifier: str
    layer_id: str
    name: str
    glb_path: str
    x: float
    y: float
    z: float
    rotation: float  # degrees
    scale: tuple[float, float, float]


@dataclass
class ParsedProject:
    """Container for all parsed EstiSketch elements needed for 3D conversion."""

    levels: list[ParsedLevel] = field(default_factory=list)
    walls: list[ParsedWall] = field(default_factory=list)
    rooms: list[ParsedRoom] = field(default_factory=list)
    doors: list[ParsedDoor] = field(default_factory=list)
    windows: list[ParsedWindow] = field(default_factory=list)
    roofs: list[ParsedRoof] = field(default_factory=list)
    stairs: list[ParsedStair] = field(default_factory=list)
    floor_openings: list[ParsedFloorOpening] = field(default_factory=list)
    fixtures: list[ParsedFixture] = field(default_factory=list)
    custom_assets: list[ParsedCustomAsset] = field(default_factory=list)
    cut_lower_ceiling_under_stairs: bool = False
    north_angle: float = 0.0  # degrees
    skipped_openings: list[str] = field(default_factory=list)


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
    layer_to_level: dict[str, str],
    default_level_id: str,
) -> str:
    if layer_id and layer_id in layer_to_level and layer_to_level[layer_id]:
        return layer_to_level[layer_id]
    return default_level_id


def _parse_hex_rgb(text: str) -> RgbColor | None:
    s = (text or "").strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16) / 255.0, int(s[2:4], 16) / 255.0, int(s[4:6], 16) / 255.0)
    except ValueError:
        return None


def _coerce_float(val: object, default: float) -> float:
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return default
    return default


def _coerce_int(val: object, default: int) -> int:
    if val is None:
        return default
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            return default
    return default


def _coerce_str(val: object, default: str = "") -> str:
    if val is None:
        return default
    return str(val).strip()


def _coerce_bool(val: object, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        s = val.strip().lower()
        if not s:
            return default
        return s in ("true", "1", "yes")
    return bool(val)


def _coerce_point2d(val: object, default: Point2D = (0.0, 0.0)) -> Point2D:
    if isinstance(val, (tuple, list)) and len(val) >= 2:
        return (_coerce_float(val[0], default[0]), _coerce_float(val[1], default[1]))
    return default


def _coerce_rgb(val: object) -> RgbColor | None:
    if val is None:
        return None
    if isinstance(val, str):
        return _parse_hex_rgb(val)
    if isinstance(val, (tuple, list)) and len(val) >= 3:
        return (
            _coerce_float(val[0], 0.0),
            _coerce_float(val[1], 0.0),
            _coerce_float(val[2], 0.0),
        )
    return None


def _iter_seq(val: object) -> list[object]:
    if val is None or isinstance(val, (str, bytes)):
        return []
    if isinstance(val, Iterable):
        return list(val)
    return []


def _coerce_lines(raw_lines: object) -> list[Line2D]:
    out: list[Line2D] = []
    for item in _iter_seq(raw_lines):
        if not isinstance(item, (tuple, list)) or len(item) < 2:
            continue
        p1 = _coerce_point2d(item[0])
        p2 = _coerce_point2d(item[1])
        if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) > 1e-4:
            out.append((p1, p2))
    return out


def parse_estisketch_xml(xml_path: str) -> ParsedProject:
    """Parse an EstiSketch ``.xml`` project file into pure-Python dataclasses.

    Args:
        xml_path: Path to an EstiSketch project XML file.

    Returns:
        A ``ParsedProject`` whose dimensions are stored in EstiSketch inches.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    levels: list[ParsedLevel] = []
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

    layer_to_level: dict[str, str] = {}
    layers_elem = root.find("Layers")
    if layers_elem is not None:
        for layer_el in layers_elem.findall("Layer"):
            lid = layer_el.get("id", "")
            if lid:
                layer_to_level[lid] = layer_el.get("level_id", "") or default_level_id

    walls: list[ParsedWall] = []
    valid_wall_refs: set[tuple[int, int]] = set()
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
                arc_center: Point2D | None = None
                arc_radius: float | None = None
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
                        interior_finish=(
                            _elem_text(wall_el, "InteriorFinish", "Drywall") or "Drywall"
                        ),
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

    rooms: list[ParsedRoom] = []
    rooms_elem = root.find("Rooms")
    if rooms_elem is not None:
        for room_idx, room_el in enumerate(rooms_elem.findall("Room")):
            if not _is_visible(room_el):
                continue
            pts_el = room_el.find("Points")
            points: list[Point2D] = []
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
                    pattern_scale=max(
                        0.25, min(4.0, _elem_float(room_el, "PatternScale", 1.0))
                    ),
                    room_type=_elem_text(room_el, "RoomType", ""),
                    wall_finish=_elem_text(room_el, "WallFinish", "Paint") or "Paint",
                )
            )

    skipped_openings: list[str] = []
    doors: list[ParsedDoor] = []
    doors_elem = root.find("Doors")
    if doors_elem is not None:
        for door_idx, door_el in enumerate(doors_elem.findall("Door")):
            if not _is_visible(door_el):
                continue
            raw_door_id = door_el.get("identifier") or _elem_text(door_el, "Identifier", "")
            door_id = raw_door_id or f"door_{door_idx}"
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

    windows: list[ParsedWindow] = []
    windows_elem = root.find("Windows")
    if windows_elem is not None:
        for win_idx, win_el in enumerate(windows_elem.findall("Window")):
            if not _is_visible(win_el):
                continue
            raw_win_id = win_el.get("identifier") or _elem_text(win_el, "Identifier", "")
            win_id = raw_win_id or f"window_{win_idx}"
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
    roofs: list[ParsedRoof] = []
    roofs_elem = root.find("Roofs")
    if roofs_elem is not None:
        def _parse_lines(parent: ET.Element, tag: str) -> list[Line2D]:
            out: list[Line2D] = []
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
            edges: list[ParsedRoofEdge] = []
            edges_el = r_el.find("Edges")
            if edges_el is not None:
                for e_el in edges_el.findall("Edge"):
                    e_pitch = (
                        _attr_float(e_el, "pitch_rise", 0.0)
                        if "pitch_rise" in e_el.attrib
                        else None
                    )
                    e_oh = (
                        _attr_float(e_el, "overhang", 0.0)
                        if "overhang" in e_el.attrib
                        else None
                    )
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

            outline_pts: list[Point2D] = []
            out_el = r_el.find("Outline")
            if out_el is not None:
                for pt_el in out_el.findall("Point"):
                    outline_pts.append(
                        (_attr_float(pt_el, "x", 0.0), _attr_float(pt_el, "y", 0.0))
                    )

            roof_mat = (r_el.get("material", "asphalt_shingle") or "asphalt_shingle").lower()
            roofs.append(
                ParsedRoof(
                    identifier=r_el.get("identifier", "") or f"roof_{roof_idx}",
                    level_id=level_id,
                    layer_id=layer_id,
                    roof_type=(r_el.get("roof_type", "gable") or "gable").lower(),
                    pitch_rise=_attr_float(r_el, "pitch_rise", 6.0),
                    pitch_run=_attr_float(r_el, "pitch_run", 12.0) or 12.0,
                    overhang=_attr_float(r_el, "overhang", 12.0),
                    material=roof_mat,
                    edges=edges,
                    ridge_lines=_parse_lines(r_el, "RidgeLines"),
                    hip_lines=_parse_lines(r_el, "HipLines"),
                    valley_lines=_parse_lines(r_el, "ValleyLines"),
                    rake_lines=_parse_lines(r_el, "RakeLines"),
                    eave_lines=_parse_lines(r_el, "EaveLines"),
                    outline_points=outline_pts,
                )
            )

    stairs: list[ParsedStair] = []
    stairs_elem = root.find("Stairs")
    if stairs_elem is not None:
        for s_idx, s_el in enumerate(stairs_elem.findall("Stair")):
            if not _is_visible(s_el):
                continue
            layer_id = s_el.get("layer_id", "") or ""
            start_level_id = s_el.get("start_level_id", "") or ""
            end_level_id = s_el.get("end_level_id", "") or ""
            level_id = layer_to_level.get(layer_id, "") or start_level_id or default_level_id
            stairs.append(
                ParsedStair(
                    identifier=s_el.get("identifier", "") or f"stair_{s_idx}",
                    layer_id=layer_id,
                    level_id=level_id,
                    start_point=(
                        _attr_float(s_el, "start_x", 0.0),
                        _attr_float(s_el, "start_y", 0.0),
                    ),
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

    floor_openings: list[ParsedFloorOpening] = []
    fo_elem = root.find("FloorOpenings")
    if fo_elem is not None:
        for fo_idx, f_el in enumerate(fo_elem.findall("FloorOpening")):
            if not _is_visible(f_el):
                continue
            pts_el = f_el.find("Points")
            pts: list[Point2D] = []
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

    fixtures: list[ParsedFixture] = []
    fx_elem = root.find("Fixtures")
    if fx_elem is not None:
        for fx_idx, f_el in enumerate(fx_elem.findall("Fixture")):
            if not _is_visible(f_el):
                continue
            layer_id = f_el.get("layer_id", "") or ""
            ct_mat = (f_el.get("countertop_material", "quartz") or "quartz").lower()
            sym_type = (f_el.get("symbol_type", "base_cabinet") or "base_cabinet").lower()
            fixtures.append(
                ParsedFixture(
                    identifier=f_el.get("identifier", "") or f"fixture_{fx_idx}",
                    symbol_type=sym_type,
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
                    has_countertop=(
                        f_el.get("has_countertop", "False").strip().lower() == "true"
                    ),
                    countertop_overhang=_attr_float(f_el, "countertop_overhang", 0.0),
                    countertop_thickness=_attr_float(f_el, "countertop_thickness", 1.5),
                    countertop_material=ct_mat,
                    has_backsplash=(
                        f_el.get("has_backsplash", "True").strip().lower() == "true"
                    ),
                    door_swing=(f_el.get("door_swing", "left") or "left").lower(),
                    fill_color=_parse_hex_rgb(f_el.get("fill_color", "")),
                    countertop_color=_parse_hex_rgb(f_el.get("countertop_color", "")),
                )
            )

    custom_assets_el = root.find("CustomAssets")
    custom_assets: list[ParsedCustomAsset] = []
    if custom_assets_el is not None:
        for idx, ca_el in enumerate(custom_assets_el.findall("CustomAsset")):
            layer_id = (ca_el.get("layer_id") or "").strip()
            if not _is_visible(ca_el):
                continue
            ca_id = (ca_el.get("identifier") or "").strip() or f"custom_asset_{idx}"
            custom_assets.append(
                ParsedCustomAsset(
                    identifier=ca_id,
                    layer_id=layer_id,
                    name=ca_el.get("name", "Custom 3D Asset"),
                    glb_path=(ca_el.get("glb") or "").strip(),
                    x=_attr_float(ca_el, "x", 0.0),
                    y=_attr_float(ca_el, "y", 0.0),
                    z=_attr_float(ca_el, "z", 0.0),
                    rotation=_attr_float(ca_el, "rotation", 0.0),
                    scale=(
                        _attr_float(ca_el, "scale_x", 1.0),
                        _attr_float(ca_el, "scale_y", 1.0),
                        _attr_float(ca_el, "scale_z", 1.0),
                    ),
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
        custom_assets=custom_assets,
        cut_lower_ceiling_under_stairs=cut_lower,
        north_angle=north_angle,
        skipped_openings=skipped_openings,
    )


def parse_estisketch_canvas(canvas: object) -> ParsedProject:
    """Extract pure-Python ``ParsedProject`` dataclasses directly from a live canvas.

    Mirrors :func:`parse_estisketch_xml` visibility, fallback, and coordinate rules
    without serializing XML or mutating ``canvas``.

    Args:
        canvas: A ``CanvasArea`` instance (or duck-typed project container).

    Returns:
        A ``ParsedProject`` whose dimensions are stored in EstiSketch inches.
    """
    levels: list[ParsedLevel] = []
    for lvl in _iter_seq(getattr(canvas, "levels", [])):
        lvl_idx = len(levels)
        levels.append(
            ParsedLevel(
                id=_coerce_str(getattr(lvl, "id", "")) or f"level_{lvl_idx}",
                name=_coerce_str(getattr(lvl, "name", "")) or f"Level {lvl_idx + 1}",
                elevation=_coerce_float(getattr(lvl, "elevation", 0.0), 0.0),
                height=_coerce_float(getattr(lvl, "height", 96.0), 96.0),
                floor_thickness=_coerce_float(getattr(lvl, "floor_thickness", 10.0), 10.0),
            )
        )
    if not levels:
        levels.append(ParsedLevel(id="level_0", name="Level 1", elevation=0.0, height=96.0))
    default_level_id = levels[0].id

    layer_to_level: dict[str, str] = {}
    for layer in _iter_seq(getattr(canvas, "layers", [])):
        lid = _coerce_str(getattr(layer, "id", ""))
        if lid:
            layer_to_level[lid] = _coerce_str(getattr(layer, "level_id", "")) or default_level_id

    walls: list[ParsedWall] = []
    valid_wall_refs: set[tuple[int, int]] = set()
    wall_index_map: dict[int, tuple[int, int]] = {}

    for set_idx, ws in enumerate(_iter_seq(getattr(canvas, "wall_sets", []))):
        for wall_idx, wall in enumerate(_iter_seq(ws)):
            wall_index_map[id(wall)] = (set_idx, wall_idx)
            is_symbolic = _coerce_bool(getattr(wall, "symbolic", False), False)
            has_footer = _coerce_bool(getattr(wall, "footer", False), False)
            visible = _coerce_bool(getattr(wall, "visible", True), True)
            if not visible or (is_symbolic and not has_footer):
                continue

            start_raw = getattr(wall, "start", None)
            end_raw = getattr(wall, "end", None)
            if start_raw is None or end_raw is None:
                continue
            start = _coerce_point2d(start_raw)
            end = _coerce_point2d(end_raw)

            height = _coerce_float(getattr(wall, "height", 96.0), 96.0)
            height_at_end = _coerce_float(getattr(wall, "height_at_end", height), height)
            layer_id = _coerce_str(getattr(wall, "layer_id", ""))
            level_id = _resolve_level_id(layer_id, layer_to_level, default_level_id)

            is_curved = _coerce_bool(getattr(wall, "is_curved", False), False)
            arc_center: Point2D | None = None
            arc_radius: float | None = None
            if is_curved:
                raw_ac = getattr(wall, "arc_center", None)
                if raw_ac is not None:
                    arc_center = _coerce_point2d(raw_ac)
                raw_ar = _coerce_float(getattr(wall, "arc_radius", 0.0), 0.0)
                arc_radius = raw_ar or None

            wall_id = _coerce_str(getattr(wall, "identifier", ""))
            int_finish = _coerce_str(getattr(wall, "interior_finish", "Drywall")) or "Drywall"
            left_finish = _coerce_str(getattr(wall, "left_finish", "Drywall")) or "Drywall"
            right_finish = _coerce_str(getattr(wall, "right_finish", "Drywall")) or "Drywall"
            walls.append(
                ParsedWall(
                    identifier=wall_id or f"wall_{set_idx}_{wall_idx}",
                    set_index=set_idx,
                    wall_index=wall_idx,
                    start=start,
                    end=end,
                    width=_coerce_float(getattr(wall, "width", 5.5), 5.5),
                    height=height,
                    height_at_end=height_at_end,
                    exterior_wall=_coerce_bool(getattr(wall, "exterior_wall", False), False),
                    level_id=level_id,
                    layer_id=layer_id,
                    is_curved=is_curved,
                    arc_center=arc_center,
                    arc_radius=arc_radius,
                    symbolic=is_symbolic,
                    interior_finish=int_finish,
                    exterior_finish=_coerce_str(getattr(wall, "exterior_finish", "")),
                    left_finish=left_finish,
                    right_finish=right_finish,
                    left_color=_coerce_rgb(getattr(wall, "left_color", None)),
                    right_color=_coerce_rgb(getattr(wall, "right_color", None)),
                    left_baseboard=_coerce_bool(getattr(wall, "left_baseboard", False), False),
                    right_baseboard=_coerce_bool(getattr(wall, "right_baseboard", False), False),
                    footer=has_footer,
                    footer_left_offset=_coerce_float(
                        getattr(wall, "footer_left_offset", 6.0), 6.0
                    ),
                    footer_right_offset=_coerce_float(
                        getattr(wall, "footer_right_offset", 6.0), 6.0
                    ),
                    footer_depth=_coerce_float(getattr(wall, "footer_depth", 8.0), 8.0),
                )
            )
            if not is_symbolic:
                valid_wall_refs.add((set_idx, wall_idx))

    rooms: list[ParsedRoom] = []
    for room_idx, room in enumerate(_iter_seq(getattr(canvas, "rooms", []))):
        if not _coerce_bool(getattr(room, "visible", True), True):
            continue
        points = [_coerce_point2d(pt) for pt in _iter_seq(getattr(room, "points", []))]
        if len(points) < 3:
            continue
        layer_id = _coerce_str(getattr(room, "layer_id", ""))
        room_id = _coerce_str(getattr(room, "identifier", "")) or f"room_{room_idx}"
        floor_pattern = _coerce_str(getattr(room, "floor_pattern", "none")) or "none"
        pat_scale = max(
            0.25, min(4.0, _coerce_float(getattr(room, "pattern_scale", 1.0), 1.0))
        )
        rooms.append(
            ParsedRoom(
                identifier=room_id,
                name=_coerce_str(getattr(room, "name", "")) or f"Room {room_idx + 1}",
                points=points,
                height=_coerce_float(getattr(room, "height", 96.0), 96.0),
                level_id=_resolve_level_id(layer_id, layer_to_level, default_level_id),
                floor_type=_coerce_str(getattr(room, "floor_type", "default"), "default"),
                is_slab=_coerce_bool(getattr(room, "is_slab", False), False),
                slab_thickness=_coerce_float(getattr(room, "slab_thickness", 4.0), 4.0),
                floor_pattern=floor_pattern,
                pattern_rotation=_coerce_float(getattr(room, "pattern_rotation", 0.0), 0.0),
                pattern_scale=pat_scale,
                room_type=_coerce_str(getattr(room, "room_type", "")),
                wall_finish=_coerce_str(getattr(room, "wall_finish", "Paint")) or "Paint",
            )
        )

    skipped_openings: list[str] = []
    doors: list[ParsedDoor] = []
    for door_idx, entry in enumerate(_iter_seq(getattr(canvas, "doors", []))):
        if not isinstance(entry, (tuple, list)) or len(entry) < 3:
            continue
        attached_wall, door, raw_ratio = entry[0], entry[1], entry[2]
        if not _coerce_bool(getattr(door, "visible", True), True):
            continue
        door_id = _coerce_str(getattr(door, "identifier", "")) or f"door_{door_idx}"
        if attached_wall is None:
            skipped_openings.append(f"door:{door_id} (no WallReference)")
            continue
        ref = wall_index_map.get(id(attached_wall))
        if ref is None or ref not in valid_wall_refs:
            set_idx = ref[0] if ref is not None else -1
            wall_idx = ref[1] if ref is not None else -1
            skipped_openings.append(f"door:{door_id} (set={set_idx}, wall={wall_idx})")
            continue
        layer_id = _coerce_str(getattr(door, "layer_id", ""))
        doors.append(
            ParsedDoor(
                identifier=door_id,
                set_index=ref[0],
                wall_index=ref[1],
                ratio=_coerce_float(raw_ratio, 0.5),
                door_type=(_coerce_str(getattr(door, "door_type", "single")) or "single").lower(),
                width=_coerce_float(getattr(door, "width", 36.0), 36.0),
                height=_coerce_float(getattr(door, "height", 80.0), 80.0),
                swing=(_coerce_str(getattr(door, "swing", "left")) or "left").lower(),
                orientation=(
                    _coerce_str(getattr(door, "orientation", "inswing")) or "inswing"
                ).lower(),
                level_id=_resolve_level_id(layer_id, layer_to_level, default_level_id),
            )
        )

    windows: list[ParsedWindow] = []
    for win_idx, entry in enumerate(_iter_seq(getattr(canvas, "windows", []))):
        if not isinstance(entry, (tuple, list)) or len(entry) < 3:
            continue
        attached_wall, win_obj, raw_ratio = entry[0], entry[1], entry[2]
        if not _coerce_bool(getattr(win_obj, "visible", True), True):
            continue
        win_id = _coerce_str(getattr(win_obj, "identifier", "")) or f"window_{win_idx}"
        if attached_wall is None:
            skipped_openings.append(f"window:{win_id} (no WallReference)")
            continue
        ref = wall_index_map.get(id(attached_wall))
        if ref is None or ref not in valid_wall_refs:
            set_idx = ref[0] if ref is not None else -1
            wall_idx = ref[1] if ref is not None else -1
            skipped_openings.append(f"window:{win_id} (set={set_idx}, wall={wall_idx})")
            continue
        layer_id = _coerce_str(getattr(win_obj, "layer_id", ""))
        win_type = (_coerce_str(getattr(win_obj, "window_type", "sliding")) or "sliding").lower()
        windows.append(
            ParsedWindow(
                identifier=win_id,
                set_index=ref[0],
                wall_index=ref[1],
                ratio=_coerce_float(raw_ratio, 0.5),
                window_type=win_type,
                width=_coerce_float(getattr(win_obj, "width", 36.0), 36.0),
                height=_coerce_float(getattr(win_obj, "height", 36.0), 36.0),
                level_id=_resolve_level_id(layer_id, layer_to_level, default_level_id),
            )
        )

    wall_level_by_id = {w.identifier: w.level_id for w in walls}
    roofs: list[ParsedRoof] = []
    for roof_idx, roof in enumerate(_iter_seq(getattr(canvas, "roofs", []))):
        if not _coerce_bool(getattr(roof, "visible", True), True):
            continue
        edges: list[ParsedRoofEdge] = []
        for edge in _iter_seq(getattr(roof, "edges", [])):
            raw_ep = getattr(edge, "pitch_rise", None)
            raw_eo = getattr(edge, "overhang", None)
            e_pitch = _coerce_float(raw_ep, 0.0) if raw_ep is not None else None
            e_oh = _coerce_float(raw_eo, 0.0) if raw_eo is not None else None
            edges.append(
                ParsedRoofEdge(
                    wall_identifier=_coerce_str(getattr(edge, "wall_identifier", "")),
                    edge_type=(
                        _coerce_str(getattr(edge, "edge_type", "eave")) or "eave"
                    ).lower(),
                    pitch_rise=e_pitch,
                    overhang=e_oh,
                )
            )

        layer_id = _coerce_str(getattr(roof, "layer_id", ""))
        if layer_id and layer_id in layer_to_level and layer_to_level[layer_id]:
            level_id = layer_to_level[layer_id]
        else:
            inferred_lvl = ""
            for edge in edges:
                if edge.wall_identifier in wall_level_by_id:
                    inferred_lvl = wall_level_by_id[edge.wall_identifier]
                    break
            level_id = inferred_lvl or default_level_id

        outline_pts = [
            _coerce_point2d(pt) for pt in _iter_seq(getattr(roof, "outline_points", []))
        ]
        roof_mat = (
            _coerce_str(getattr(roof, "material", "asphalt_shingle")) or "asphalt_shingle"
        ).lower()
        roofs.append(
            ParsedRoof(
                identifier=_coerce_str(getattr(roof, "identifier", "")) or f"roof_{roof_idx}",
                level_id=level_id,
                layer_id=layer_id,
                roof_type=(_coerce_str(getattr(roof, "roof_type", "gable")) or "gable").lower(),
                pitch_rise=_coerce_float(getattr(roof, "pitch_rise", 6.0), 6.0),
                pitch_run=_coerce_float(getattr(roof, "pitch_run", 12.0), 12.0) or 12.0,
                overhang=_coerce_float(getattr(roof, "overhang", 12.0), 12.0),
                material=roof_mat,
                edges=edges,
                ridge_lines=_coerce_lines(getattr(roof, "ridge_lines", [])),
                hip_lines=_coerce_lines(getattr(roof, "hip_lines", [])),
                valley_lines=_coerce_lines(getattr(roof, "valley_lines", [])),
                rake_lines=_coerce_lines(getattr(roof, "rake_lines", [])),
                eave_lines=_coerce_lines(getattr(roof, "eave_lines", [])),
                outline_points=outline_pts,
            )
        )

    stairs: list[ParsedStair] = []
    for s_idx, stair in enumerate(_iter_seq(getattr(canvas, "stairs", []))):
        if not _coerce_bool(getattr(stair, "visible", True), True):
            continue
        layer_id = _coerce_str(getattr(stair, "layer_id", ""))
        start_level_id = _coerce_str(getattr(stair, "start_level_id", ""))
        end_level_id = _coerce_str(getattr(stair, "end_level_id", ""))
        level_id = layer_to_level.get(layer_id, "") or start_level_id or default_level_id
        stairs.append(
            ParsedStair(
                identifier=_coerce_str(getattr(stair, "identifier", "")) or f"stair_{s_idx}",
                layer_id=layer_id,
                level_id=level_id,
                start_point=_coerce_point2d(getattr(stair, "start_point", (0.0, 0.0))),
                direction_angle=_coerce_float(getattr(stair, "direction_angle", 0.0), 0.0),
                start_level_id=start_level_id or level_id,
                end_level_id=end_level_id,
                stair_type=(
                    _coerce_str(getattr(stair, "stair_type", "straight")) or "straight"
                ).lower(),
                width=_coerce_float(getattr(stair, "width", 36.0), 36.0),
                total_rise=_coerce_float(getattr(stair, "total_rise", 106.0), 106.0),
                riser_height=_coerce_float(getattr(stair, "riser_height", 7.57), 7.57),
                num_steps=max(1, _coerce_int(getattr(stair, "num_steps", 14), 14)),
                tread_depth=_coerce_float(getattr(stair, "tread_depth", 11.0), 11.0),
                total_run=_coerce_float(getattr(stair, "total_run", 143.0), 143.0),
                nosing=_coerce_float(getattr(stair, "nosing", 1.0), 1.0),
                has_left_rail=_coerce_bool(getattr(stair, "has_left_rail", True), True),
                has_right_rail=_coerce_bool(getattr(stair, "has_right_rail", True), True),
                rail_height=_coerce_float(getattr(stair, "rail_height", 36.0), 36.0),
                turn_direction=(
                    _coerce_str(getattr(stair, "turn_direction", "left")) or "left"
                ).lower(),
                landing_depth=_coerce_float(getattr(stair, "landing_depth", 36.0), 36.0),
                steps_before_landing=_coerce_int(
                    getattr(stair, "steps_before_landing", 0), 0
                ),
                winder_count=_coerce_int(getattr(stair, "winder_count", 0), 0),
                opening_clearance=_coerce_float(getattr(stair, "opening_clearance", 0.0), 0.0),
                inner_radius=_coerce_float(getattr(stair, "inner_radius", 6.0), 6.0),
                rotation_degrees=_coerce_float(getattr(stair, "rotation_degrees", 270.0), 270.0),
            )
        )

    floor_openings: list[ParsedFloorOpening] = []
    for fo_idx, fo in enumerate(_iter_seq(getattr(canvas, "floor_openings", []))):
        if not _coerce_bool(getattr(fo, "visible", True), True):
            continue
        pts = [_coerce_point2d(pt) for pt in _iter_seq(getattr(fo, "points", []))]
        if len(pts) < 3:
            continue
        layer_id = _coerce_str(getattr(fo, "layer_id", ""))
        fo_type = (_coerce_str(getattr(fo, "opening_type", "opening")) or "opening").lower()
        floor_openings.append(
            ParsedFloorOpening(
                identifier=_coerce_str(getattr(fo, "identifier", "")) or f"opening_{fo_idx}",
                level_id=_resolve_level_id(layer_id, layer_to_level, default_level_id),
                opening_type=fo_type,
                label=_coerce_str(getattr(fo, "label", "")),
                ceiling_only=_coerce_bool(getattr(fo, "ceiling_only", False), False),
                points=pts,
            )
        )

    fixtures: list[ParsedFixture] = []
    for fx_idx, fx in enumerate(_iter_seq(getattr(canvas, "fixtures", []))):
        if not _coerce_bool(getattr(fx, "visible", True), True):
            continue
        layer_id = _coerce_str(getattr(fx, "layer_id", ""))
        sym_type = (
            _coerce_str(getattr(fx, "symbol_type", "base_cabinet")) or "base_cabinet"
        ).lower()
        ct_mat = (_coerce_str(getattr(fx, "countertop_material", "quartz")) or "quartz").lower()
        fixtures.append(
            ParsedFixture(
                identifier=_coerce_str(getattr(fx, "identifier", "")) or f"fixture_{fx_idx}",
                symbol_type=sym_type,
                category=_coerce_str(getattr(fx, "category", "")).lower(),
                level_id=_resolve_level_id(layer_id, layer_to_level, default_level_id),
                layer_id=layer_id,
                x=_coerce_float(getattr(fx, "x", 0.0), 0.0),
                y=_coerce_float(getattr(fx, "y", 0.0), 0.0),
                width=_coerce_float(getattr(fx, "width", 24.0), 24.0),
                depth=_coerce_float(getattr(fx, "depth", 24.0), 24.0),
                height=_coerce_float(getattr(fx, "height", 34.5), 34.5),
                rotation=_coerce_float(getattr(fx, "rotation", 0.0), 0.0),
                elevation=_coerce_float(getattr(fx, "elevation", 0.0), 0.0),
                mount_surface=(
                    _coerce_str(getattr(fx, "mount_surface", "auto")) or "auto"
                ).lower(),
                has_countertop=_coerce_bool(getattr(fx, "has_countertop", False), False),
                countertop_overhang=_coerce_float(
                    getattr(fx, "countertop_overhang", 0.0), 0.0
                ),
                countertop_thickness=_coerce_float(
                    getattr(fx, "countertop_thickness", 1.5), 1.5
                ),
                countertop_material=ct_mat,
                has_backsplash=_coerce_bool(getattr(fx, "has_backsplash", True), True),
                door_swing=(_coerce_str(getattr(fx, "door_swing", "left")) or "left").lower(),
                fill_color=_coerce_rgb(getattr(fx, "fill_color", None)),
                countertop_color=_coerce_rgb(getattr(fx, "countertop_color", None)),
            )
        )

    raw_custom = _iter_seq(getattr(canvas, "custom_assets", []))
    custom_assets: list[ParsedCustomAsset] = []
    if raw_custom:
        from ..esk_archive import materialize_project_assets

        materialize_project_assets(canvas)
    for idx, ca in enumerate(raw_custom):
        layer_id = _coerce_str(getattr(ca, "layer_id", ""))
        if not _coerce_bool(getattr(ca, "visible", True), True):
            continue
        ca_id = _coerce_str(getattr(ca, "identifier", "")) or f"custom_asset_{idx}"
        res_path = _coerce_str(
            getattr(ca, "resolved_glb_path", "") or getattr(ca, "glb_rel_path", "")
        )
        raw_scale = getattr(ca, "scale", (1.0, 1.0, 1.0))
        if isinstance(raw_scale, (tuple, list)) and len(raw_scale) >= 3:
            scale = (
                _coerce_float(raw_scale[0], 1.0),
                _coerce_float(raw_scale[1], 1.0),
                _coerce_float(raw_scale[2], 1.0),
            )
        else:
            scale = (1.0, 1.0, 1.0)
        custom_assets.append(
            ParsedCustomAsset(
                identifier=ca_id,
                layer_id=layer_id,
                name=_coerce_str(getattr(ca, "name", "Custom 3D Asset")) or "Custom 3D Asset",
                glb_path=res_path,
                x=_coerce_float(getattr(ca, "x", 0.0), 0.0),
                y=_coerce_float(getattr(ca, "y", 0.0), 0.0),
                z=_coerce_float(getattr(ca, "z", 0.0), 0.0),
                rotation=_coerce_float(getattr(ca, "rotation", 0.0), 0.0),
                scale=scale,
            )
        )

    cut_lower = _coerce_bool(getattr(canvas, "cut_lower_ceiling_under_stairs", False), False)
    north_angle = _coerce_float(getattr(canvas, "north_angle", 0.0), 0.0)

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
        custom_assets=custom_assets,
        cut_lower_ceiling_under_stairs=cut_lower,
        north_angle=north_angle,
        skipped_openings=skipped_openings,
    )
