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
class ParsedProject:
    """Container for all parsed EstiSketch elements needed for 3D conversion."""

    levels: List[ParsedLevel] = field(default_factory=list)
    walls: List[ParsedWall] = field(default_factory=list)
    rooms: List[ParsedRoom] = field(default_factory=list)
    doors: List[ParsedDoor] = field(default_factory=list)
    windows: List[ParsedWindow] = field(default_factory=list)


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

    return ParsedProject(
        levels=levels,
        walls=walls,
        rooms=rooms,
        doors=doors,
        windows=windows,
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
    for idx, pr in enumerate(project.rooms):
        lvl = level_by_id.get(pr.level_id, project.levels[0])
        rooms_col = level_cols[lvl.id]["rooms"]
        pts_m = [inches_to_blender_xy(x, y, cx, cy) for x, y in pr.points]
        thick_m = max(0.01, pr.slab_thickness * INCH_TO_M) if pr.is_slab else 0.01
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
