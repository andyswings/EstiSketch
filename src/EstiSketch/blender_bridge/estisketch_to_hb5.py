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
class ParsedProject:
    """Container for all parsed EstiSketch elements needed for 3D conversion."""

    levels: List[ParsedLevel] = field(default_factory=list)
    walls: List[ParsedWall] = field(default_factory=list)
    rooms: List[ParsedRoom] = field(default_factory=list)
    doors: List[ParsedDoor] = field(default_factory=list)
    windows: List[ParsedWindow] = field(default_factory=list)
    roofs: List[ParsedRoof] = field(default_factory=list)


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
                if not _is_visible(wall_el) or _elem_bool(wall_el, "Symbolic", False):
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
                    )
                )
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
                )
            )

    doors: List[ParsedDoor] = []
    doors_elem = root.find("Doors")
    if doors_elem is not None:
        for door_idx, door_el in enumerate(doors_elem.findall("Door")):
            if not _is_visible(door_el):
                continue
            wref = door_el.find("WallReference")
            if wref is None:
                continue
            set_idx = _attr_int(wref, "set_index", -1)
            wall_idx = _attr_int(wref, "wall_index", -1)
            if (set_idx, wall_idx) not in valid_wall_refs:
                continue
            layer_id = _elem_text(door_el, "LayerId", "")
            door_id = door_el.get("identifier") or _elem_text(door_el, "Identifier", "")
            doors.append(
                ParsedDoor(
                    identifier=door_id or f"door_{door_idx}",
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
            wref = win_el.find("WallReference")
            if wref is None:
                continue
            set_idx = _attr_int(wref, "set_index", -1)
            wall_idx = _attr_int(wref, "wall_index", -1)
            if (set_idx, wall_idx) not in valid_wall_refs:
                continue
            layer_id = _elem_text(win_el, "LayerId", "")
            win_id = win_el.get("identifier") or _elem_text(win_el, "Identifier", "")
            windows.append(
                ParsedWindow(
                    identifier=win_id or f"window_{win_idx}",
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

    return ParsedProject(
        levels=levels,
        walls=walls,
        rooms=rooms,
        doors=doors,
        windows=windows,
        roofs=roofs,
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
    wall_by_id = {w.identifier: w for w in project.walls}

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
            if ow.identifier == pw.identifier:
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


def _ensure_sun_light(scene, target_col) -> None:
    import bpy

    light_data = bpy.data.lights.new(name="EstiSketch Sun", type="SUN")
    light_data.energy = 2.5
    light_obj = bpy.data.objects.new(name="EstiSketch Sun", object_data=light_data)
    light_obj.rotation_euler = (math.radians(48.0), math.radians(15.0), math.radians(-35.0))
    target_col.objects.link(light_obj)


def _assign_wall_materials(wall, scene) -> None:
    mat = getattr(scene.home_builder, "wall_material", None)
    if mat is None:
        return
    for slot in (
        "Top Surface",
        "Bottom Surface",
        "Inside Face",
        "Outside Face",
        "Left Edge",
        "Right Edge",
        "Left Surface",
        "Right Surface",
        "Front Surface",
        "Back Surface",
    ):
        if wall.has_input(slot):
            wall.set_input(slot, mat)


def _build_floor_mesh(
    name: str,
    points_m: List[Tuple[float, float]],
    z_top: float,
    thickness_m: float,
    target_col,
    is_slab: bool,
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

    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            loop[uv_layer].uv = (loop.vert.co.x, loop.vert.co.y)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    obj["IS_FLOOR_BP"] = True
    if is_slab:
        obj["IS_SLAB"] = True
    obj.color = (0.72, 0.72, 0.70, 1.0)
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

    mat = getattr(scene.home_builder, "wall_material", None)
    if mat is not None:
        mesh.materials.append(mat)

    obj = bpy.data.objects.new(name, mesh)
    obj["IS_GABLE_INFILL"] = True
    obj.color = (0.85, 0.85, 0.83, 1.0)
    target_col.objects.link(obj)
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

    project = parse_estisketch_xml(xml_path)
    cx, cy = compute_plan_center(project)

    scene = bpy.context.scene
    _clear_default_scene(scene)

    scene["IS_ROOM_SCENE"] = True
    scene.unit_settings.system = "IMPERIAL"
    scene.unit_settings.length_unit = "INCHES"

    root_col = _ensure_collection("EstiSketch Import", scene.collection)
    _ensure_sun_light(scene, root_col)

    level_by_id = {lvl.id: lvl for lvl in project.levels}
    level_cols: Dict[str, Dict[str, object]] = {}
    for lvl in project.levels:
        lvl_col = _ensure_collection(f"EstiSketch - {lvl.name}", root_col)
        level_cols[lvl.id] = {
            "walls": _ensure_collection(f"{lvl.name} - Walls", lvl_col),
            "openings": _ensure_collection(f"{lvl.name} - Openings", lvl_col),
            "rooms": _ensure_collection(f"{lvl.name} - Rooms", lvl_col),
            "ceilings": _ensure_collection(f"{lvl.name} - Ceilings", lvl_col),
            "roofs": _ensure_collection(f"{lvl.name} - Roofs", lvl_col),
        }

    # Build walls grouped by set_index so sequential walls in a set connect cleanly
    # without closing a cyclic COPY_LOCATION dependency loop.
    wall_map: Dict[Tuple[int, int], Tuple[object, float, float]] = {}
    walls_by_set: Dict[int, List[ParsedWall]] = {}
    for pw in project.walls:
        walls_by_set.setdefault(pw.set_index, []).append(pw)

    wall_count = 0
    for set_idx, set_walls in walls_by_set.items():
        prev_hb_wall = None
        prev_end_m: Optional[Tuple[float, float]] = None

        for pw in set_walls:
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
            first_seg_wall = None
            first_seg_len = 0.0

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
                _assign_wall_materials(hb_wall, scene)

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
                if first_seg_wall is None:
                    first_seg_wall = hb_wall
                    first_seg_len = length_m

            if first_seg_wall is not None and not pw.is_curved:
                min_h_m = min(pw.height, pw.height_at_end) * INCH_TO_M
                wall_map[(pw.set_index, pw.wall_index)] = (
                    first_seg_wall,
                    first_seg_len,
                    min_h_m,
                )

    bpy.context.view_layer.update()
    if hasattr(walls_op, "refresh_wall_junctions"):
        walls_op.refresh_wall_junctions(scene)
    elif hasattr(walls_op, "update_all_wall_miters"):
        walls_op.update_all_wall_miters()

    hb_props = scene.home_builder
    hb_wm_prefs = bpy.context.window_manager.home_builder.get_user_preferences(bpy.context)

    door_count = 0
    for pd in project.doors:
        host = wall_map.get((pd.set_index, pd.wall_index))
        if host is None:
            continue
        hb_wall, wall_len_m, min_h_m = host
        lvl = level_by_id.get(pd.level_id, project.levels[0])
        openings_col = level_cols[lvl.id]["openings"]

        width_m = max(0.1, min(pd.width * INCH_TO_M, wall_len_m))
        height_m = max(0.2, min(pd.height * INCH_TO_M, min_h_m))
        thickness_m = hb_wall.get_input("Thickness")
        x_local = compute_opening_local_x(pd.ratio, wall_len_m, width_m)

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

        is_frame = pd.door_type == "frame"
        if is_frame:
            cage.obj["IS_OPEN_DOORWAY"] = True
            _add_boolean_cut(hb_wall.obj, cage.obj)
        else:
            dim_x = cage.var_input("Dim X", "dim_x")
            dim_y = cage.var_input("Dim Y", "dim_y")
            dim_z = cage.var_input("Dim Z", "dim_z")

            swing_obj = hb_types.GeoNodeDoorSwing()
            swing_obj.create("Door Swing Annotation")
            swing_obj.obj.parent = cage.obj
            swing_obj.driver_input("Dim X", "dim_x", [dim_x])
            swing_obj.driver_input("Dim Y", "dim_y", [dim_y])
            swing_obj.set_input("Is Double", "double" in pd.door_type)
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
            if "double" in pd.door_type:
                opts["door_style"] = "FLUSH"
            door_window_geo.set_opts(cage.obj, opts)
            cutting_obj = door_window_geo.update_reveal_cutter(cage.obj)
            _add_boolean_cut(hb_wall.obj, cutting_obj)
            door_window_geo.build_geometry(cage.obj)
            for child in cage.obj.children:
                _move_object_to_collection(child, openings_col)

        door_count += 1

    window_count = 0
    default_sill_m = getattr(hb_props, "window_height_from_floor", 36.0 * INCH_TO_M)
    for pw in project.windows:
        host = wall_map.get((pw.set_index, pw.wall_index))
        if host is None:
            continue
        hb_wall, wall_len_m, min_h_m = host
        lvl = level_by_id.get(pw.level_id, project.levels[0])
        openings_col = level_cols[lvl.id]["openings"]

        width_m = max(0.1, min(pw.width * INCH_TO_M, wall_len_m))
        height_m = max(0.1, min(pw.height * INCH_TO_M, max(0.1, min_h_m - 0.05)))
        thickness_m = hb_wall.get_input("Thickness")
        z_local = max(0.0, min(default_sill_m, max(0.0, min_h_m - height_m - 0.05)))
        x_local = compute_opening_local_x(pw.ratio, wall_len_m, width_m)

        cage = hb_types.GeoNodeCage()
        cage.create(f"Window_{pw.identifier}")
        cage.obj["IS_WINDOW_BP"] = True
        cage.obj["MENU_ID"] = "HOME_BUILDER_MT_window_commands"
        cage.obj["ESTISKETCH_ID"] = pw.identifier
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
        opts["window_type"] = _map_window_type(pw.window_type)
        door_window_geo.set_opts(cage.obj, opts)
        cutting_obj = door_window_geo.update_reveal_cutter(cage.obj)
        _add_boolean_cut(hb_wall.obj, cutting_obj)
        door_window_geo.build_geometry(cage.obj)
        for child in cage.obj.children:
            _move_object_to_collection(child, openings_col)

        window_count += 1

    door_window_geo.hide_reveal_cutters()

    room_count = 0
    ceiling_count = 0
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
        floor_obj = _build_floor_mesh(
            f"Floor_{pr.name}_{idx}",
            pts_m,
            lvl.elevation * INCH_TO_M,
            thick_m,
            rooms_col,
            pr.is_slab,
        )
        if floor_obj is not None:
            floor_obj["ESTISKETCH_ID"] = pr.identifier
            room_count += 1

        if pr.height > 0.0:
            ceil_obj = _build_ceiling_mesh(
                f"Ceiling_{pr.name}_{idx}",
                pts_m,
                (lvl.elevation + pr.height) * INCH_TO_M,
                0.5 * INCH_TO_M,
                ceilings_col,
                scene,
            )
            if ceil_obj is not None:
                ceil_obj["ESTISKETCH_ID"] = pr.identifier
                ceiling_count += 1

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
            infill_obj = _build_gable_infill_mesh(
                f"GableInfill_{r_idx}_{i_idx}", infill, cx, cy, walls_col, scene
            )
            if infill_obj is not None:
                infill_count += 1

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
