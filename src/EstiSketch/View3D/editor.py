"""Headless interactive 3D editing controller and bidirectional canvas synchronization.

All coordinates inside Python canvas objects use **inches** (Y-down), whereas rays and
pick results from the native Rust engine use centered world **meters** (Y-up, Z-up).
This module contains no ``gi``, ``Gtk``, or ``cairo`` imports so all Phase 3 editing logic
runs directly under headless ``pytest``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import math
from typing import Literal, Protocol, cast

from ..geometry.design_checks import clamp_fixture_out_of_walls
from ..geometry.wall_chain import (
    collinear_chain,
    pocket_door_extents,
    resolve_opening_on_chain,
)
from ..measurement_utils import MeasurementConverter
from ..native_3d import PickHit
from ..scene_ir.parsed import INCH_TO_M

Tool3D = Literal["orbit", "select", "paint"]
Point2D = tuple[float, float]
Point3D = tuple[float, float, float]

ROOF_MATERIAL_OPTIONS: tuple[str, ...] = ("asphalt_shingle", "metal", "tile", "slate")
_COUNTERTOP_SUB_PARTS: frozenset[str] = frozenset({"RunCountertop", "Countertop", "Backsplash"})
_LEFT_WALL_SUB_PARTS: frozenset[str] = frozenset({"LeftFace", "BaseboardLeft"})
_RIGHT_WALL_SUB_PARTS: frozenset[str] = frozenset({"RightFace", "BaseboardRight"})


class _WallLike(Protocol):
    identifier: str
    layer_id: str
    visible: bool
    locked: bool
    start: Point2D
    end: Point2D
    width: float
    height: float
    height_at_end: float
    left_finish: str
    right_finish: str
    left_color: tuple[float, float, float] | None
    right_color: tuple[float, float, float] | None


class _OpeningLike(Protocol):
    identifier: str
    layer_id: str
    visible: bool
    locked: bool
    width: float


class _RoomLike(Protocol):
    identifier: str
    layer_id: str
    visible: bool
    locked: bool
    points: list[Point2D]
    floor_pattern: str
    name: str


class _RoofLike(Protocol):
    identifier: str
    layer_id: str
    visible: bool
    locked: bool
    pitch_rise: float
    material: str


class _FixtureLike(Protocol):
    identifier: str
    layer_id: str
    visible: bool
    locked: bool
    symbol_type: str
    x: float
    y: float
    elevation: float
    rotation: float
    fill_color: tuple[float, float, float] | None
    countertop_color: tuple[float, float, float] | None


class _LevelLike(Protocol):
    id: str
    elevation: float


@dataclass
class PaintBrushState:
    """Active 3D material brush parameters applied on click and updated by eyedropper."""

    wall_finish: str = "Painted Drywall"
    wall_color: str = "#EAE6DF"
    floor_pattern: str = "wood_plank"
    roof_material: str = "asphalt_shingle"
    fixture_color: str = "#E8E2D6"
    countertop_color: str = "#D4CFC7"


@dataclass
class EditActionResult:
    """Outcome of a 3D pointer/keyboard edit event for ``Viewport3DWidget``."""

    handled: bool = False
    mutated: bool = False
    commit_undo: bool = False
    needs_mesh_sync: bool = False
    needs_render: bool = False
    hud_message: str = ""
    selected_ids: list[str] | None = None
    preview_transform: tuple[str, Point3D, Point3D, float] | None = None
    clear_preview: bool = False
    brush_sampled: bool = False


@dataclass
class _ActiveDrag:
    kind: Literal["opening", "fixture_move", "fixture_rotate", "wall_height", "roof_pitch"]
    entity_id: str
    plane_pt_m: Point3D
    plane_normal_m: Point3D
    start_hit_m: Point3D
    changed: bool = False
    # Opening fields
    opening_kind: str = "door"
    opening_index: int = -1
    orig_host_wall: object | None = None
    opening_obj: object | None = None
    orig_ratio: float = 0.5
    grab_offset_in: float = 0.0
    # Fixture fields
    fixture_obj: _FixtureLike | None = None
    orig_fx_x: float = 0.0
    orig_fx_y: float = 0.0
    prev_fx_x: float = 0.0
    prev_fx_y: float = 0.0
    orig_fx_rot: float = 0.0
    fx_grab_dx_in: float = 0.0
    fx_grab_dy_in: float = 0.0
    fx_start_angle_deg: float = 0.0
    pivot_m: Point3D = (0.0, 0.0, 0.0)
    # Wall height fields
    wall_obj: _WallLike | None = None
    wall_end_mode: Literal["start", "end", "both"] = "both"
    orig_wall_h0: float = 96.0
    orig_wall_h1: float = 96.0
    # Roof pitch fields
    roof_obj: _RoofLike | None = None
    orig_pitch: float = 6.0


def ndc_from_widget_xy(x: float, y: float, width: float, height: float) -> tuple[float, float]:
    """Convert GTK logical widget coordinates (top-left origin) to OpenGL NDC ``[-1, 1]``."""
    w = max(1.0, float(width))
    h = max(1.0, float(height))
    ndc_x = (2.0 * float(x) / w) - 1.0
    ndc_y = 1.0 - (2.0 * float(y) / h)
    return (max(-1.0, min(1.0, ndc_x)), max(-1.0, min(1.0, ndc_y)))


def world_m_to_canvas_in(world_m: Point3D, plan_center_in: Point2D) -> Point3D:
    """Convert centered 3D world **meters** (Z-up) into canvas **inches** (Y-down)."""
    cx, cy = plan_center_in
    x_in = cx + world_m[0] / INCH_TO_M
    y_in = cy - world_m[1] / INCH_TO_M
    z_in = world_m[2] / INCH_TO_M
    return (x_in, y_in, z_in)


def canvas_in_to_world_m(pt_in: Point3D, plan_center_in: Point2D) -> Point3D:
    """Convert canvas **inches** (Y-down) into centered 3D world **meters** (Z-up)."""
    cx, cy = plan_center_in
    x_m = (pt_in[0] - cx) * INCH_TO_M
    y_m = -(pt_in[1] - cy) * INCH_TO_M
    z_m = pt_in[2] * INCH_TO_M
    return (x_m, y_m, z_m)


def ray_intersect_plane(
    ray_origin: Point3D,
    ray_dir: Point3D,
    plane_pt: Point3D,
    plane_normal: Point3D,
) -> Point3D | None:
    """Intersect a 3D ray with a plane in **meters**, returning hit point or ``None``."""
    rx, ry, rz = ray_dir
    nx, ny, nz = plane_normal
    denom = rx * nx + ry * ny + rz * nz
    if abs(denom) <= 1e-6:
        return None
    dx = plane_pt[0] - ray_origin[0]
    dy = plane_pt[1] - ray_origin[1]
    dz = plane_pt[2] - ray_origin[2]
    t = (dx * plane_normal[0] + dy * plane_normal[1] + dz * plane_normal[2]) / denom
    if t <= 1e-4:
        return None
    return (
        ray_origin[0] + ray_dir[0] * t,
        ray_origin[1] + ray_dir[1] * t,
        ray_origin[2] + ray_dir[2] * t,
    )


def _format_inches(canvas: object, inches: float) -> str:
    conv = getattr(canvas, "converter", None)
    if conv is not None and hasattr(conv, "format_measurement"):
        fmt_fn = cast(Callable[[float, bool], str], getattr(conv, "format_measurement"))
        return fmt_fn(max(0.0, float(inches)), False)
    return MeasurementConverter.format_measurement(max(0.0, float(inches)), use_fraction=False)


def _level_id_for_obj(canvas: object, obj: object) -> str:
    layer_id = str(getattr(obj, "layer_id", "") or "")
    layers = getattr(canvas, "layers", None)
    if isinstance(layers, list):
        for layer in layers:
            if getattr(layer, "id", None) == layer_id:
                return str(getattr(layer, "level_id", "level_0") or "level_0")
    return "level_0"


def _level_elevation_in(canvas: object, level_id: str) -> float:
    levels = getattr(canvas, "levels", None)
    if isinstance(levels, list):
        for lvl in cast(list[_LevelLike], levels):
            if getattr(lvl, "id", None) == level_id:
                return float(getattr(lvl, "elevation", 0.0) or 0.0)
    return 0.0


def iter_canvas_walls(canvas: object) -> list[object]:
    """Return all unique wall objects across ``canvas.walls`` and ``canvas.wall_sets``."""
    out: list[object] = []
    seen: set[int] = set()
    for w in getattr(canvas, "walls", []) or []:
        oid = id(w)
        if oid not in seen:
            seen.add(oid)
            out.append(w)
    for wset in getattr(canvas, "wall_sets", []) or []:
        for w in wset:
            oid = id(w)
            if oid not in seen:
                seen.add(oid)
                out.append(w)
    return out


def is_object_visible(canvas: object, obj: object) -> bool:
    """Return True when ``obj`` and its layer are visible."""
    if not bool(getattr(obj, "visible", True)):
        return False
    vis_fn = getattr(canvas, "is_object_on_visible_layer", None)
    if callable(vis_fn):
        return bool(vis_fn(obj))
    return True


def is_object_editable(canvas: object, obj: object) -> bool:
    """Return True when ``obj`` is visible and neither the object nor its layer is locked."""
    if not is_object_visible(canvas, obj):
        return False
    if bool(getattr(obj, "locked", False)):
        return False
    lock_fn = getattr(canvas, "is_object_on_locked_layer", None)
    if callable(lock_fn) and bool(lock_fn(obj)):
        return False
    return True


def resolve_canvas_object(
    canvas: object, entity_id: str, entity_kind: str = ""
) -> tuple[str, object, object] | None:
    """Map a Rust 3D ``entity_id`` to ``(selection_type, selection_object, primary_object)``."""
    if not entity_id:
        return None
    if entity_kind in ("", "wall"):
        for wall in iter_canvas_walls(canvas):
            if getattr(wall, "identifier", "") == entity_id:
                return ("wall", wall, wall)
    if entity_kind in ("", "opening"):
        for entry in getattr(canvas, "doors", []) or []:
            if isinstance(entry, tuple) and len(entry) >= 3:
                door_obj = entry[1]
                if getattr(door_obj, "identifier", "") == entity_id:
                    return ("door", entry, door_obj)
        for entry in getattr(canvas, "windows", []) or []:
            if isinstance(entry, tuple) and len(entry) >= 3:
                win_obj = entry[1]
                if getattr(win_obj, "identifier", "") == entity_id:
                    return ("window", entry, win_obj)
    if entity_kind in ("", "room"):
        for room in getattr(canvas, "rooms", []) or []:
            if getattr(room, "identifier", "") == entity_id:
                return ("room", room, room)
    if entity_kind in ("", "roof"):
        for roof in getattr(canvas, "roofs", []) or []:
            if getattr(roof, "identifier", "") == entity_id:
                return ("roof", roof, roof)
    if entity_kind in ("", "stair"):
        for stair in getattr(canvas, "stairs", []) or []:
            if getattr(stair, "identifier", "") == entity_id:
                return ("stair", stair, stair)
    if entity_kind in ("", "fixture"):
        for fx in getattr(canvas, "fixtures", []) or []:
            if getattr(fx, "identifier", "") == entity_id:
                return ("fixture", fx, fx)
    return None


def selected_entity_ids_from_canvas(canvas: object) -> list[str]:
    """Extract unique 3D entity IDs represented by ``canvas.selected_items``."""
    ids: list[str] = []
    seen: set[str] = set()
    for item in getattr(canvas, "selected_items", []) or []:
        if not isinstance(item, dict):
            continue
        itype = item.get("type")
        obj = item.get("object")
        ident = ""
        if itype in ("wall", "room", "roof", "stair", "fixture"):
            ident = str(getattr(obj, "identifier", "") or "")
        elif itype in ("door", "window") and isinstance(obj, tuple) and len(obj) >= 2:
            ident = str(getattr(obj[1], "identifier", "") or "")
        elif itype == "wall_handle" and isinstance(obj, tuple) and len(obj) >= 1:
            ident = str(getattr(obj[0], "identifier", "") or "")
        elif itype == "roof_line":
            roof_obj = item.get("roof")
            ident = str(getattr(roof_obj, "identifier", "") or "")
        if ident and ident not in seen:
            seen.add(ident)
            ids.append(ident)
    return ids


def _emit_selection_changed(canvas: object) -> None:
    selected = getattr(canvas, "selected_items", [])
    if hasattr(canvas, "emit"):
        emit_fn = cast(Callable[[str, object], None], getattr(canvas, "emit"))
        emit_fn("selection-changed", selected)
    if hasattr(canvas, "queue_draw"):
        getattr(canvas, "queue_draw")()


def commit_canvas_mutation(canvas: object) -> None:
    """Push a single undo snapshot, mark dirty, redraw 2D, and refresh PropertiesDock."""
    if hasattr(canvas, "save_state"):
        getattr(canvas, "save_state")()
    if hasattr(canvas, "emit"):
        emit_fn = cast(Callable[[str], None], getattr(canvas, "emit"))
        emit_fn("content-changed")
        _emit_selection_changed(canvas)
    elif hasattr(canvas, "queue_draw"):
        getattr(canvas, "queue_draw")()


def select_from_hit(canvas: object, hit: PickHit | None, extend: bool = False) -> list[str]:
    """Update ``canvas.selected_items`` from a 3D raycast hit and emit ``selection-changed``."""
    selected = list(getattr(canvas, "selected_items", []) or []) if extend else []
    if hit is not None:
        resolved = resolve_canvas_object(canvas, hit.entity_id, hit.entity_kind)
        if resolved is not None:
            sel_type, sel_obj, primary = resolved
            if is_object_visible(canvas, primary):
                already = any(
                    it.get("type") == sel_type and it.get("object") is sel_obj
                    for it in selected
                )
                if not already:
                    selected.append({"type": sel_type, "object": sel_obj})
    setattr(canvas, "selected_items", selected)
    _emit_selection_changed(canvas)
    return selected_entity_ids_from_canvas(canvas)


def _wall_side_from_hit(wall: _WallLike, hit: PickHit) -> Literal["left", "right"]:
    if hit.sub_part in _LEFT_WALL_SUB_PARTS:
        return "left"
    if hit.sub_part in _RIGHT_WALL_SUB_PARTS:
        return "right"
    # Fall back to normal comparison matching mesher.rs (d = (dx, -dy)/L, n = (-d.y, d.x),
    # so LeftFace outward normal is -n = (-dy/L, -dx/L) in 3D world XY).
    dx = float(wall.end[0]) - float(wall.start[0])
    dy = float(wall.end[1]) - float(wall.start[1])
    wlen = math.hypot(dx, dy)
    if wlen <= 1e-6:
        return "left"
    lnx_3d = -dy / wlen
    lny_3d = -dx / wlen
    dot = hit.normal[0] * lnx_3d + hit.normal[1] * lny_3d
    return "left" if dot >= 0.0 else "right"


def _point_in_poly_2d(pt: Point2D, poly: list[Point2D]) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def _room_wall_interior_side(wall: _WallLike, room: _RoomLike) -> Literal["left", "right"] | None:
    """Return which side (``left`` or ``right``) of ``wall`` faces inside ``room``, or None."""
    x1, y1 = float(wall.start[0]), float(wall.start[1])
    x2, y2 = float(wall.end[0]), float(wall.end[1])
    dx, dy = x2 - x1, y2 - y1
    wlen = math.hypot(dx, dy)
    if wlen <= 1e-4:
        return None
    mx, my = 0.5 * (x1 + x2), 0.5 * (y1 + y2)
    # 3D LeftFace (-n_3d = (-dy/L, -dx/L)) converts to 2D inches as (-dy/L, +dx/L).
    offset = max(4.0, float(getattr(wall, "width", 4.5) or 4.5) * 0.65)
    lx_in = -dy / wlen
    ly_in = dx / wlen
    left_pt = (mx + lx_in * offset, my + ly_in * offset)
    right_pt = (mx - lx_in * offset, my - ly_in * offset)
    left_in = _point_in_poly_2d(left_pt, room.points)
    right_in = _point_in_poly_2d(right_pt, room.points)
    if left_in and not right_in:
        return "left"
    if right_in and not left_in:
        return "right"
    if left_in and right_in:
        return "left"
    return None


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert ``#RGB`` or ``#RRGGBB`` hex color string to normalized ``(r, g, b)`` floats."""
    s = hex_color.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return (0.9, 0.89, 0.86)
    try:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
        return (r, g, b)
    except ValueError:
        return (0.9, 0.89, 0.86)


def _rgb_to_hex(color: object, default_hex: str) -> str:
    """Convert normalized ``(r, g, b)`` tuple or hex string into ``#RRGGBB``."""
    if isinstance(color, str) and color.strip().startswith("#"):
        return color.strip().upper()
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        vals: list[int] = []
        for comp in color[:3]:
            if isinstance(comp, (int, float)):
                vals.append(max(0, min(255, round(float(comp) * 255.0))))
        if len(vals) == 3:
            return f"#{vals[0]:02X}{vals[1]:02X}{vals[2]:02X}"
    return default_hex


def _paint_wall_side(
    wall: _WallLike, side: Literal["left", "right"], finish: str, color_hex: str
) -> None:
    rgb = _hex_to_rgb(color_hex)
    if side == "left":
        wall.left_finish = finish
        wall.left_color = rgb
    else:
        wall.right_finish = finish
        wall.right_color = rgb


def _replace_opening_in_list_and_selection(
    canvas: object,
    opening_kind: str,
    idx: int,
    new_entry: tuple[object, object, float],
    opening_obj: object,
) -> None:
    attr = "doors" if opening_kind == "door" else "windows"
    lst = getattr(canvas, attr, None)
    if isinstance(lst, list) and 0 <= idx < len(lst):
        lst[idx] = new_entry
    sel = getattr(canvas, "selected_items", None)
    if isinstance(sel, list):
        for item in sel:
            if not isinstance(item, dict) or item.get("type") != opening_kind:
                continue
            obj = item.get("object")
            if isinstance(obj, tuple) and len(obj) >= 2 and obj[1] is opening_obj:
                item["object"] = new_entry


def _editable_level_walls(canvas: object, level_id: str) -> list[object]:
    """Return unlocked, visible structural walls belonging to ``level_id``."""
    out: list[object] = []
    for w in iter_canvas_walls(canvas):
        if getattr(w, "symbolic", False):
            continue
        if _level_id_for_obj(canvas, w) != level_id:
            continue
        if is_object_editable(canvas, w):
            out.append(w)
    return out


def _compute_chain_clearances(
    host_wall: _WallLike,
    ratio: float,
    opening: _OpeningLike,
    canvas: object,
    opening_kind: str,
    prev_center_world: Point2D | None = None,
) -> tuple[float, float, float]:
    """Clamp ``ratio`` away from sibling openings on chain and return ``(clamped_ratio, left_in, right_in)``."""
    x1, y1 = float(host_wall.start[0]), float(host_wall.start[1])
    x2, y2 = float(host_wall.end[0]), float(host_wall.end[1])
    dx, dy = x2 - x1, y2 - y1
    wlen = math.hypot(dx, dy)
    if wlen <= 1e-6:
        return (0.5, 0.0, 0.0)
    ux, uy = dx / wlen, dy / wlen
    host_lvl = _level_id_for_obj(canvas, host_wall)
    candidates = [
        w
        for w in iter_canvas_walls(canvas)
        if not getattr(w, "symbolic", False) and _level_id_for_obj(canvas, w) == host_lvl
    ]
    chain = collinear_chain(host_wall, candidates)
    chain_ids = {id(m) for m in chain}

    def proj(pt: Point2D) -> float:
        return (pt[0] - x1) * ux + (pt[1] - y1) * uy

    lo = min(min(proj(m.start), proj(m.end)) for m in chain)
    hi = max(max(proj(m.start), proj(m.end)) for m in chain)

    op_width = float(getattr(opening, "width", 36.0) or 36.0)
    if opening_kind == "door" and getattr(opening, "door_type", "") == "pocket":
        ext_l, ext_r = pocket_door_extents(op_width, str(getattr(opening, "swing", "left")))
    else:
        ext_l = op_width * 0.5
        ext_r = op_width * 0.5

    centre = ratio * wlen
    ref_centre = proj(prev_center_world) if prev_center_world is not None else centre
    min_c = lo + ext_l
    max_c = hi - ext_r
    if min_c <= max_c:
        centre = max(min_c, min(max_c, centre))
    else:
        centre = 0.5 * (lo + hi)

    left_edge_bound = lo
    right_edge_bound = hi
    for lst_name in ("doors", "windows"):
        for entry in getattr(canvas, lst_name, []) or []:
            if not isinstance(entry, tuple) or len(entry) < 3:
                continue
            sib_wall, sib_op, sib_ratio = entry[0], entry[1], float(entry[2])
            if sib_op is opening or id(sib_wall) not in chain_ids:
                continue
            sib_w = float(getattr(sib_op, "width", 36.0) or 36.0)
            sx1, sy1 = float(sib_wall.start[0]), float(sib_wall.start[1])
            sx2, sy2 = float(sib_wall.end[0]), float(sib_wall.end[1])
            sc_x = sx1 + (sx2 - sx1) * sib_ratio
            sc_y = sy1 + (sy2 - sy1) * sib_ratio
            sc = (sc_x - x1) * ux + (sc_y - y1) * uy
            if lst_name == "doors" and getattr(sib_op, "door_type", "") == "pocket":
                s_ext_l, s_ext_r = pocket_door_extents(
                    sib_w, str(getattr(sib_op, "swing", "left"))
                )
            else:
                s_ext_l = sib_w * 0.5
                s_ext_r = sib_w * 0.5
            s_lo = sc - s_ext_l
            s_hi = sc + s_ext_r
            if sc <= ref_centre:
                left_edge_bound = max(left_edge_bound, s_hi)
            else:
                right_edge_bound = min(right_edge_bound, s_lo)

    gap_min_c = left_edge_bound + ext_l
    gap_max_c = right_edge_bound - ext_r
    if gap_min_c <= gap_max_c:
        centre = max(gap_min_c, min(gap_max_c, centre))

    left_clear = max(0.0, (centre - ext_l) - left_edge_bound)
    right_clear = max(0.0, right_edge_bound - (centre + ext_r))
    return (centre / wlen, left_clear, right_clear)


class Editor3DController:
    """Stateful Phase 3 3D editing controller supporting tools, drags, and paint brush."""

    def __init__(self) -> None:
        self.tool: Tool3D = "select"
        self.brush: PaintBrushState = PaintBrushState()
        self.active_drag: _ActiveDrag | None = None

    def set_tool(self, tool: Tool3D) -> None:
        """Switch active 3D tool mode (`orbit`, `select`, `paint`) and cancel active drags."""
        self.tool = tool
        self.active_drag = None

    def handle_click(
        self,
        canvas: object,
        hit: PickHit | None,
        shift: bool = False,
        alt: bool = False,
    ) -> EditActionResult:
        """Process a short click (no camera orbit/edit drag) in the 3D viewport."""
        if self.tool == "paint":
            if hit is None:
                return EditActionResult(handled=True)
            if alt:
                return self._sample_eyedropper(canvas, hit)
            return self._apply_paint(canvas, hit, room_wide=shift)

        ids = select_from_hit(canvas, hit, extend=shift)
        hud = self._describe_selection(canvas, hit)
        return EditActionResult(
            handled=True,
            needs_render=True,
            selected_ids=ids,
            hud_message=hud,
        )

    def begin_drag(
        self,
        canvas: object,
        hit: PickHit | None,
        ray_origin: Point3D,
        ray_dir: Point3D,
        plan_center_in: Point2D,
        shift: bool = False,
        alt: bool = False,
    ) -> EditActionResult:
        """Try starting a constrained 3D direct-manipulation drag; ``handled=False`` lets camera orbit."""
        self.active_drag = None
        if self.tool != "select" or hit is None:
            return EditActionResult(handled=False)

        resolved = resolve_canvas_object(canvas, hit.entity_id, hit.entity_kind)
        if resolved is None:
            return EditActionResult(handled=False)
        sel_type, _sel_obj, primary = resolved
        if not is_object_visible(canvas, primary):
            return EditActionResult(handled=False)

        if not is_object_editable(canvas, primary):
            ids = select_from_hit(canvas, hit, extend=shift)
            return EditActionResult(
                handled=False,
                needs_render=True,
                selected_ids=ids,
                hud_message="Locked: unlock object or layer to edit",
            )

        was_selected = hit.entity_id in selected_entity_ids_from_canvas(canvas)
        ids = select_from_hit(canvas, hit, extend=shift)

        if hit.entity_kind == "opening" and sel_type in ("door", "window"):
            return self._begin_opening_drag(
                canvas, sel_type, primary, hit, plan_center_in, ids
            )
        if hit.entity_kind == "fixture" and sel_type == "fixture":
            return self._begin_fixture_drag(
                canvas,
                cast(_FixtureLike, primary),
                hit,
                ray_origin,
                ray_dir,
                plan_center_in,
                alt=alt,
                ids=ids,
            )
        if hit.entity_kind == "wall" and sel_type == "wall":
            return self._begin_wall_height_drag(
                canvas,
                cast(_WallLike, primary),
                hit,
                ray_dir,
                plan_center_in,
                was_selected=was_selected,
                ids=ids,
            )
        if hit.entity_kind == "roof" and sel_type == "roof" and was_selected:
            return self._begin_roof_pitch_drag(
                cast(_RoofLike, primary), hit, ray_dir, ids
            )

        return EditActionResult(
            handled=False,
            needs_render=True,
            selected_ids=ids,
            hud_message=self._describe_selection(canvas, hit),
        )

    def update_drag(
        self,
        canvas: object,
        ray_origin: Point3D,
        ray_dir: Point3D,
        plan_center_in: Point2D,
        shift: bool = False,
    ) -> EditActionResult:
        """Advance the active 3D drag gesture and return HUD/preview updates."""
        drag = self.active_drag
        if drag is None:
            return EditActionResult(handled=False)

        if drag.kind == "opening":
            return self._update_opening_drag(canvas, drag, ray_origin, ray_dir, plan_center_in)
        if drag.kind == "fixture_move":
            return self._update_fixture_move(
                canvas, drag, ray_origin, ray_dir, plan_center_in
            )
        if drag.kind == "fixture_rotate":
            return self._update_fixture_rotate(
                drag, ray_origin, ray_dir, plan_center_in, shift=shift
            )
        if drag.kind == "wall_height":
            return self._update_wall_height_drag(
                canvas, drag, ray_origin, ray_dir, shift=shift
            )
        if drag.kind == "roof_pitch":
            return self._update_roof_pitch_drag(
                canvas, drag, ray_origin, ray_dir, shift=shift
            )
        return EditActionResult(handled=False)

    def end_drag(self, canvas: object) -> EditActionResult:
        """Finalize active 3D drag, pushing one undo snapshot if state actually changed."""
        drag = self.active_drag
        self.active_drag = None
        if drag is None:
            return EditActionResult(handled=False)
        if drag.changed:
            commit_canvas_mutation(canvas)
            return EditActionResult(
                handled=True,
                mutated=True,
                commit_undo=True,
                needs_mesh_sync=True,
                needs_render=True,
                clear_preview=True,
            )
        return EditActionResult(
            handled=True,
            mutated=False,
            commit_undo=False,
            needs_render=True,
            clear_preview=True,
        )

    def cancel_drag(self, canvas: object) -> EditActionResult:
        """Abort an in-progress drag and restore pre-drag canvas state without pushing undo."""
        drag = self.active_drag
        self.active_drag = None
        if drag is None:
            return EditActionResult(handled=False)

        if drag.changed:
            if drag.kind == "opening" and drag.orig_host_wall is not None and drag.opening_obj is not None:
                entry = (drag.orig_host_wall, drag.opening_obj, drag.orig_ratio)
                _replace_opening_in_list_and_selection(
                    canvas, drag.opening_kind, drag.opening_index, entry, drag.opening_obj
                )
            elif drag.kind in ("fixture_move", "fixture_rotate") and drag.fixture_obj is not None:
                drag.fixture_obj.x = drag.orig_fx_x
                drag.fixture_obj.y = drag.orig_fx_y
                drag.fixture_obj.rotation = drag.orig_fx_rot
            elif drag.kind == "wall_height" and drag.wall_obj is not None:
                drag.wall_obj.height = drag.orig_wall_h0
                drag.wall_obj.height_at_end = drag.orig_wall_h1
                recalc_w = getattr(canvas, "recalculate_roofs_for_wall", None)
                if callable(recalc_w):
                    recalc_w(drag.wall_obj.identifier)
            elif drag.kind == "roof_pitch" and drag.roof_obj is not None:
                drag.roof_obj.pitch_rise = drag.orig_pitch
                recalc_r = getattr(canvas, "recalculate_roof", None)
                if callable(recalc_r):
                    recalc_r(drag.roof_obj)
            _emit_selection_changed(canvas)

        return EditActionResult(
            handled=True,
            mutated=drag.changed,
            needs_mesh_sync=drag.changed,
            needs_render=True,
            clear_preview=True,
            hud_message="Cancelled",
        )

    def rotate_selected_fixture(self, canvas: object, step_deg: float) -> EditActionResult:
        """Rotate selected unlocked fixture(s) by ``step_deg`` degrees and commit one undo."""
        mutated = False
        locked_hit = False
        last_angle = 0.0
        for item in getattr(canvas, "selected_items", []) or []:
            if not isinstance(item, dict) or item.get("type") != "fixture":
                continue
            fx_obj = item.get("object")
            if fx_obj is None:
                continue
            if not is_object_editable(canvas, fx_obj):
                locked_hit = True
                continue
            fx = cast(_FixtureLike, fx_obj)
            orig_xy = (float(fx.x), float(fx.y))
            fx.rotation = (float(fx.rotation) + float(step_deg)) % 360.0
            lvl_id = _level_id_for_obj(canvas, fx)
            same_walls = [
                w
                for w in iter_canvas_walls(canvas)
                if not getattr(w, "symbolic", False) and _level_id_for_obj(canvas, w) == lvl_id
            ]
            clamp_fixture_out_of_walls(fx, same_walls, orig_pos=orig_xy)
            last_angle = float(fx.rotation)
            mutated = True

        if mutated:
            commit_canvas_mutation(canvas)
            return EditActionResult(
                handled=True,
                mutated=True,
                commit_undo=True,
                needs_mesh_sync=True,
                needs_render=True,
                hud_message=f"Rotation: {last_angle:.0f}°",
            )
        if locked_hit:
            return EditActionResult(
                handled=False,
                hud_message="Locked: unlock fixture or layer to rotate",
            )
        return EditActionResult(handled=False)

    def _describe_selection(self, canvas: object, hit: PickHit | None) -> str:
        if hit is None:
            return ""
        resolved = resolve_canvas_object(canvas, hit.entity_id, hit.entity_kind)
        if resolved is None:
            return ""
        sel_type, _, primary = resolved
        name = str(getattr(primary, "custom_name", "") or getattr(primary, "name", "") or "")
        label = name or str(getattr(primary, "symbol_type", "") or sel_type).replace("_", " ").title()
        if not is_object_editable(canvas, primary):
            return f"Selected: {label} (Locked)"
        return f"Selected: {label}"

    def _sample_eyedropper(self, canvas: object, hit: PickHit) -> EditActionResult:
        resolved = resolve_canvas_object(canvas, hit.entity_id, hit.entity_kind)
        if resolved is None:
            return EditActionResult(handled=True)
        sel_type, _, primary = resolved
        if sel_type == "wall":
            wall = cast(_WallLike, primary)
            side = _wall_side_from_hit(wall, hit)
            if side == "left":
                self.brush.wall_finish = wall.left_finish or "Drywall"
                self.brush.wall_color = _rgb_to_hex(wall.left_color, "#FFFFFF")
            else:
                self.brush.wall_finish = wall.right_finish or "Drywall"
                self.brush.wall_color = _rgb_to_hex(wall.right_color, "#FFFFFF")
            return EditActionResult(
                handled=True,
                brush_sampled=True,
                hud_message=f"Sampled {side} wall: {self.brush.wall_finish} ({self.brush.wall_color})",
            )
        if sel_type == "room":
            room = cast(_RoomLike, primary)
            self.brush.floor_pattern = room.floor_pattern or "none"
            return EditActionResult(
                handled=True,
                brush_sampled=True,
                hud_message=f"Sampled floor: {self.brush.floor_pattern}",
            )
        if sel_type == "roof":
            roof = cast(_RoofLike, primary)
            self.brush.roof_material = roof.material or "asphalt_shingle"
            return EditActionResult(
                handled=True,
                brush_sampled=True,
                hud_message=f"Sampled roof: {self.brush.roof_material}",
            )
        if sel_type == "fixture":
            fx = cast(_FixtureLike, primary)
            if hit.sub_part in _COUNTERTOP_SUB_PARTS:
                self.brush.countertop_color = _rgb_to_hex(fx.countertop_color, "#D4CFC7")
                return EditActionResult(
                    handled=True,
                    brush_sampled=True,
                    hud_message=f"Sampled countertop: {self.brush.countertop_color}",
                )
            self.brush.fixture_color = _rgb_to_hex(fx.fill_color, "#E8E2D6")
            return EditActionResult(
                handled=True,
                brush_sampled=True,
                hud_message=f"Sampled fixture color: {self.brush.fixture_color}",
            )
        return EditActionResult(handled=True)

    def _apply_paint(
        self, canvas: object, hit: PickHit, room_wide: bool = False
    ) -> EditActionResult:
        resolved = resolve_canvas_object(canvas, hit.entity_id, hit.entity_kind)
        if resolved is None:
            return EditActionResult(handled=True)
        sel_type, _, primary = resolved
        if not is_object_editable(canvas, primary):
            return EditActionResult(
                handled=True,
                hud_message="Locked: unlock object or layer to paint",
            )

        if sel_type == "wall":
            wall = cast(_WallLike, primary)
            side = _wall_side_from_hit(wall, hit)
            if room_wide:
                painted = self._paint_room_walls(canvas, wall, side)
                if painted > 0:
                    commit_canvas_mutation(canvas)
                    return EditActionResult(
                        handled=True,
                        mutated=True,
                        commit_undo=True,
                        needs_mesh_sync=True,
                        needs_render=True,
                        hud_message=(
                            f"Painted {painted} room wall face(s): {self.brush.wall_finish}"
                        ),
                    )
            _paint_wall_side(wall, side, self.brush.wall_finish, self.brush.wall_color)
            commit_canvas_mutation(canvas)
            return EditActionResult(
                handled=True,
                mutated=True,
                commit_undo=True,
                needs_mesh_sync=True,
                needs_render=True,
                hud_message=f"Painted {side} face: {self.brush.wall_finish}",
            )

        if sel_type == "room":
            room = cast(_RoomLike, primary)
            room.floor_pattern = self.brush.floor_pattern
            commit_canvas_mutation(canvas)
            return EditActionResult(
                handled=True,
                mutated=True,
                commit_undo=True,
                needs_mesh_sync=True,
                needs_render=True,
                hud_message=f"Painted floor: {self.brush.floor_pattern}",
            )

        if sel_type == "roof":
            roof = cast(_RoofLike, primary)
            roof.material = self.brush.roof_material
            commit_canvas_mutation(canvas)
            return EditActionResult(
                handled=True,
                mutated=True,
                commit_undo=True,
                needs_mesh_sync=True,
                needs_render=True,
                hud_message=f"Painted roof: {self.brush.roof_material}",
            )

        if sel_type == "fixture":
            fx = cast(_FixtureLike, primary)
            if hit.sub_part in _COUNTERTOP_SUB_PARTS:
                fx.countertop_color = _hex_to_rgb(self.brush.countertop_color)
                msg = f"Painted countertop: {self.brush.countertop_color}"
            else:
                fx.fill_color = _hex_to_rgb(self.brush.fixture_color)
                msg = f"Painted fixture: {self.brush.fixture_color}"
            commit_canvas_mutation(canvas)
            return EditActionResult(
                handled=True,
                mutated=True,
                commit_undo=True,
                needs_mesh_sync=True,
                needs_render=True,
                hud_message=msg,
            )

        return EditActionResult(handled=True)

    def _paint_room_walls(
        self,
        canvas: object,
        clicked_wall: _WallLike,
        clicked_side: Literal["left", "right"],
    ) -> int:
        rooms = getattr(canvas, "rooms", []) or []
        if not rooms:
            return 0
        wall_lvl = _level_id_for_obj(canvas, clicked_wall)
        x1, y1 = float(clicked_wall.start[0]), float(clicked_wall.start[1])
        x2, y2 = float(clicked_wall.end[0]), float(clicked_wall.end[1])
        dx, dy = x2 - x1, y2 - y1
        wlen = math.hypot(dx, dy)
        if wlen <= 1e-4:
            return 0
        sign = 1.0 if clicked_side == "left" else -1.0
        offset = max(4.0, float(getattr(clicked_wall, "width", 4.5) or 4.5) * 0.65)
        mx, my = 0.5 * (x1 + x2), 0.5 * (y1 + y2)
        # LeftFace in 2D inches sits toward (-dy/L, +dx/L)
        test_pt = (
            mx + sign * (-dy / wlen) * offset,
            my + sign * (dx / wlen) * offset,
        )
        target_room: _RoomLike | None = None
        for room_obj in rooms:
            room = cast(_RoomLike, room_obj)
            if _level_id_for_obj(canvas, room) != wall_lvl:
                continue
            if _point_in_poly_2d(test_pt, getattr(room, "points", [])):
                target_room = room
                break
        if target_room is None:
            return 0

        count = 0
        for w_obj in iter_canvas_walls(canvas):
            if getattr(w_obj, "symbolic", False):
                continue
            if _level_id_for_obj(canvas, w_obj) != wall_lvl:
                continue
            if not is_object_editable(canvas, w_obj):
                continue
            wall = cast(_WallLike, w_obj)
            side = _room_wall_interior_side(wall, target_room)
            if side is not None:
                _paint_wall_side(wall, side, self.brush.wall_finish, self.brush.wall_color)
                count += 1
        return count

    def _begin_opening_drag(
        self,
        canvas: object,
        opening_kind: str,
        opening_obj: object,
        hit: PickHit,
        plan_center_in: Point2D,
        ids: list[str],
    ) -> EditActionResult:
        lst_name = "doors" if opening_kind == "door" else "windows"
        entries = getattr(canvas, lst_name, []) or []
        match_idx = -1
        host_wall: object | None = None
        orig_ratio = 0.5
        for idx, entry in enumerate(entries):
            if isinstance(entry, tuple) and len(entry) >= 3 and entry[1] is opening_obj:
                match_idx = idx
                host_wall = entry[0]
                orig_ratio = float(entry[2])
                break
        if match_idx < 0 or host_wall is None:
            return EditActionResult(handled=False, needs_render=True, selected_ids=ids)
        if getattr(host_wall, "is_curved", False) or not is_object_editable(canvas, host_wall):
            return EditActionResult(
                handled=False,
                needs_render=True,
                selected_ids=ids,
                hud_message="Host wall is locked or curved",
            )

        hw = cast(_WallLike, host_wall)
        x1, y1 = float(hw.start[0]), float(hw.start[1])
        x2, y2 = float(hw.end[0]), float(hw.end[1])
        dx, dy = x2 - x1, y2 - y1
        wlen = math.hypot(dx, dy)
        if wlen <= 1e-4:
            return EditActionResult(handled=False)
        # Plane perpendicular to wall XY normal (wall lies along d = (dx, -dy) in 3D, so n = (dy, dx, 0))
        plane_n = (dy / wlen, dx / wlen, 0.0)
        wall_lvl = _level_id_for_obj(canvas, hw)
        wall_base_z_m = _level_elevation_in(canvas, wall_lvl) * INCH_TO_M
        plane_pt = canvas_in_to_world_m((x1, y1, wall_base_z_m / INCH_TO_M), plan_center_in)

        hit_in = world_m_to_canvas_in(hit.world_pos_m, plan_center_in)
        ux, uy = dx / wlen, dy / wlen
        hit_s = (hit_in[0] - x1) * ux + (hit_in[1] - y1) * uy
        cur_s = orig_ratio * wlen
        self.active_drag = _ActiveDrag(
            kind="opening",
            entity_id=hit.entity_id,
            plane_pt_m=plane_pt,
            plane_normal_m=plane_n,
            start_hit_m=hit.world_pos_m,
            opening_kind=opening_kind,
            opening_index=match_idx,
            orig_host_wall=host_wall,
            opening_obj=opening_obj,
            orig_ratio=orig_ratio,
            grab_offset_in=cur_s - hit_s,
        )
        return EditActionResult(
            handled=True,
            needs_render=True,
            selected_ids=ids,
            hud_message="Drag along wall to position opening",
        )

    def _update_opening_drag(
        self,
        canvas: object,
        drag: _ActiveDrag,
        ray_origin: Point3D,
        ray_dir: Point3D,
        plan_center_in: Point2D,
    ) -> EditActionResult:
        hit_m = ray_intersect_plane(ray_origin, ray_dir, drag.plane_pt_m, drag.plane_normal_m)
        if hit_m is None or drag.orig_host_wall is None or drag.opening_obj is None:
            return EditActionResult(handled=True)

        hw = cast(_WallLike, drag.orig_host_wall)
        x1, y1 = float(hw.start[0]), float(hw.start[1])
        x2, y2 = float(hw.end[0]), float(hw.end[1])
        dx, dy = x2 - x1, y2 - y1
        wlen = math.hypot(dx, dy)
        if wlen <= 1e-4:
            return EditActionResult(handled=True)
        ux, uy = dx / wlen, dy / wlen
        hit_in = world_m_to_canvas_in(hit_m, plan_center_in)
        raw_s = (hit_in[0] - x1) * ux + (hit_in[1] - y1) * uy + drag.grab_offset_in
        unclamped_ratio = raw_s / wlen

        opening = cast(_OpeningLike, drag.opening_obj)
        op_w = float(getattr(opening, "width", 36.0) or 36.0)
        host_lvl = _level_id_for_obj(canvas, hw)
        candidates = _editable_level_walls(canvas, host_lvl)

        # Preserve current position before this drag update so openings cannot tunnel past siblings
        prev_entry_wall = hw
        prev_entry_ratio = drag.orig_ratio
        lst_attr = "doors" if drag.opening_kind == "door" else "windows"
        cur_entries = getattr(canvas, lst_attr, []) or []
        if 0 <= drag.opening_index < len(cur_entries):
            cur_entry = cur_entries[drag.opening_index]
            if isinstance(cur_entry, tuple) and len(cur_entry) >= 3:
                prev_entry_wall = cast(_WallLike, cur_entry[0])
                prev_entry_ratio = float(cur_entry[2])
        pw_x1, pw_y1 = float(prev_entry_wall.start[0]), float(prev_entry_wall.start[1])
        pw_x2, pw_y2 = float(prev_entry_wall.end[0]), float(prev_entry_wall.end[1])
        prev_world_pt = (
            pw_x1 + (pw_x2 - pw_x1) * prev_entry_ratio,
            pw_y1 + (pw_y2 - pw_y1) * prev_entry_ratio,
        )

        if drag.opening_kind == "door" and getattr(opening, "door_type", "") == "pocket":
            ext_l, ext_r = pocket_door_extents(op_w, str(getattr(opening, "swing", "left")))
            next_wall, next_ratio = resolve_opening_on_chain(
                hw, unclamped_ratio, op_w, candidates, left_ext=ext_l, right_ext=ext_r
            )
        else:
            next_wall, next_ratio = resolve_opening_on_chain(hw, unclamped_ratio, op_w, candidates)

        next_hw = cast(_WallLike, next_wall)
        clamped_ratio, left_in, right_in = _compute_chain_clearances(
            next_hw,
            next_ratio,
            opening,
            canvas,
            drag.opening_kind,
            prev_center_world=prev_world_pt,
        )
        new_entry: tuple[object, object, float] = (next_wall, drag.opening_obj, clamped_ratio)
        _replace_opening_in_list_and_selection(
            canvas, drag.opening_kind, drag.opening_index, new_entry, drag.opening_obj
        )
        drag.changed = True
        left_txt = _format_inches(canvas, left_in)
        right_txt = _format_inches(canvas, right_in)
        return EditActionResult(
            handled=True,
            mutated=True,
            needs_mesh_sync=True,
            needs_render=True,
            hud_message=f"Clearance L: {left_txt}  |  R: {right_txt}",
        )

    def _begin_fixture_drag(
        self,
        canvas: object,
        fx: _FixtureLike,
        hit: PickHit,
        ray_origin: Point3D,
        ray_dir: Point3D,
        plan_center_in: Point2D,
        alt: bool,
        ids: list[str],
    ) -> EditActionResult:
        lvl_id = _level_id_for_obj(canvas, fx)
        lvl_elev_in = _level_elevation_in(canvas, lvl_id)
        fx_base_z_in = lvl_elev_in + float(getattr(fx, "elevation", 0.0) or 0.0)
        pivot_m = canvas_in_to_world_m((float(fx.x), float(fx.y), fx_base_z_in), plan_center_in)
        plane_pt = hit.world_pos_m
        plane_n = (0.0, 0.0, 1.0)
        init_plane_hit = ray_intersect_plane(ray_origin, ray_dir, plane_pt, plane_n) or hit.world_pos_m
        init_in = world_m_to_canvas_in(init_plane_hit, plan_center_in)
        start_ang = math.degrees(math.atan2(init_in[1] - float(fx.y), init_in[0] - float(fx.x)))

        self.active_drag = _ActiveDrag(
            kind="fixture_rotate" if alt else "fixture_move",
            entity_id=hit.entity_id,
            plane_pt_m=plane_pt,
            plane_normal_m=plane_n,
            start_hit_m=hit.world_pos_m,
            fixture_obj=fx,
            orig_fx_x=float(fx.x),
            orig_fx_y=float(fx.y),
            prev_fx_x=float(fx.x),
            prev_fx_y=float(fx.y),
            orig_fx_rot=float(fx.rotation),
            fx_grab_dx_in=float(fx.x) - init_in[0],
            fx_grab_dy_in=float(fx.y) - init_in[1],
            fx_start_angle_deg=start_ang,
            pivot_m=pivot_m,
        )
        msg = "Rotate fixture (Shift: 1°)" if alt else "Drag fixture (Alt+Drag/R: Rotate)"
        return EditActionResult(
            handled=True,
            needs_render=True,
            selected_ids=ids,
            hud_message=msg,
        )

    def _update_fixture_move(
        self,
        canvas: object,
        drag: _ActiveDrag,
        ray_origin: Point3D,
        ray_dir: Point3D,
        plan_center_in: Point2D,
    ) -> EditActionResult:
        hit_m = ray_intersect_plane(ray_origin, ray_dir, drag.plane_pt_m, drag.plane_normal_m)
        if hit_m is None or drag.fixture_obj is None:
            return EditActionResult(handled=True)

        fx = drag.fixture_obj
        pt_in = world_m_to_canvas_in(hit_m, plan_center_in)
        target_x = pt_in[0] + drag.fx_grab_dx_in
        target_y = pt_in[1] + drag.fx_grab_dy_in

        lvl_id = _level_id_for_obj(canvas, fx)
        same_walls = [
            w
            for w in iter_canvas_walls(canvas)
            if not getattr(w, "symbolic", False) and _level_id_for_obj(canvas, w) == lvl_id
        ]

        # Sweep from last clamped position in ~2" steps so fast drags cannot tunnel through walls.
        start_x = drag.prev_fx_x
        start_y = drag.prev_fx_y
        move_dist = math.hypot(target_x - start_x, target_y - start_y)
        steps = max(1, math.ceil(move_dist / 2.0))
        for idx in range(1, steps + 1):
            t = idx / steps
            prev_step_xy = (float(fx.x), float(fx.y))
            fx.x = start_x + (target_x - start_x) * t
            fx.y = start_y + (target_y - start_y) * t
            if clamp_fixture_out_of_walls(fx, same_walls, orig_pos=prev_step_xy):
                break
        drag.prev_fx_x = float(fx.x)
        drag.prev_fx_y = float(fx.y)
        drag.changed = True

        dx_in = float(fx.x) - drag.orig_fx_x
        dy_in = float(fx.y) - drag.orig_fx_y
        delta_m = (dx_in * INCH_TO_M, -dy_in * INCH_TO_M, 0.0)
        dist_in = math.hypot(dx_in, dy_in)
        return EditActionResult(
            handled=True,
            mutated=True,
            needs_mesh_sync=False,
            needs_render=True,
            preview_transform=(drag.entity_id, drag.pivot_m, delta_m, 0.0),
            hud_message=f"Move: {_format_inches(canvas, dist_in)}",
        )

    def _update_fixture_rotate(
        self,
        drag: _ActiveDrag,
        ray_origin: Point3D,
        ray_dir: Point3D,
        plan_center_in: Point2D,
        shift: bool = False,
    ) -> EditActionResult:
        hit_m = ray_intersect_plane(ray_origin, ray_dir, drag.plane_pt_m, drag.plane_normal_m)
        if hit_m is None or drag.fixture_obj is None:
            return EditActionResult(handled=True)

        fx = drag.fixture_obj
        pt_in = world_m_to_canvas_in(hit_m, plan_center_in)
        cur_ang = math.degrees(math.atan2(pt_in[1] - float(fx.y), pt_in[0] - float(fx.x)))
        delta_deg = cur_ang - drag.fx_start_angle_deg
        snap = 1.0 if shift else 15.0
        snapped_delta = round(delta_deg / snap) * snap
        fx.rotation = (drag.orig_fx_rot + snapped_delta) % 360.0
        drag.changed = abs(snapped_delta) > 1e-4

        return EditActionResult(
            handled=True,
            mutated=drag.changed,
            needs_mesh_sync=False,
            needs_render=True,
            preview_transform=(
                drag.entity_id,
                drag.pivot_m,
                (0.0, 0.0, 0.0),
                -math.radians(snapped_delta),
            ),
            hud_message=f"Rotation: {float(fx.rotation):.0f}°",
        )

    def _begin_wall_height_drag(
        self,
        canvas: object,
        wall: _WallLike,
        hit: PickHit,
        ray_dir: Point3D,
        plan_center_in: Point2D,
        was_selected: bool,
        ids: list[str],
    ) -> EditActionResult:
        lvl_id = _level_id_for_obj(canvas, wall)
        lvl_elev_in = _level_elevation_in(canvas, lvl_id)
        x1, y1 = float(wall.start[0]), float(wall.start[1])
        x2, y2 = float(wall.end[0]), float(wall.end[1])
        dx, dy = x2 - x1, y2 - y1
        wlen = math.hypot(dx, dy)
        if wlen <= 1e-4:
            return EditActionResult(handled=False)

        hit_in = world_m_to_canvas_in(hit.world_pos_m, plan_center_in)
        t = ((hit_in[0] - x1) * dx + (hit_in[1] - y1) * dy) / (wlen * wlen)
        t = max(0.0, min(1.0, t))
        h0 = float(getattr(wall, "height", 96.0) or 96.0)
        h1 = float(getattr(wall, "height_at_end", h0) or h0)
        top_at_hit_m = (lvl_elev_in + (h0 + (h1 - h0) * t)) * INCH_TO_M
        near_top = abs(hit.world_pos_m[2] - top_at_hit_m) <= 0.35
        if hit.sub_part != "TopEdge" and not (was_selected and near_top):
            return EditActionResult(
                handled=False,
                needs_render=True,
                selected_ids=ids,
                hud_message=self._describe_selection(canvas, hit),
            )

        end_mode: Literal["start", "end", "both"] = (
            "start" if t < 0.35 else ("end" if t > 0.65 else "both")
        )
        horiz = math.hypot(ray_dir[0], ray_dir[1])
        plane_n = (
            (-ray_dir[0] / horiz, -ray_dir[1] / horiz, 0.0)
            if horiz > 1e-4
            else (1.0, 0.0, 0.0)
        )
        self.active_drag = _ActiveDrag(
            kind="wall_height",
            entity_id=hit.entity_id,
            plane_pt_m=hit.world_pos_m,
            plane_normal_m=plane_n,
            start_hit_m=hit.world_pos_m,
            wall_obj=wall,
            wall_end_mode=end_mode,
            orig_wall_h0=h0,
            orig_wall_h1=h1,
        )
        return EditActionResult(
            handled=True,
            needs_render=True,
            selected_ids=ids,
            hud_message=f"Drag to adjust wall {end_mode} height",
        )

    def _update_wall_height_drag(
        self,
        canvas: object,
        drag: _ActiveDrag,
        ray_origin: Point3D,
        ray_dir: Point3D,
        shift: bool = False,
    ) -> EditActionResult:
        hit_m = ray_intersect_plane(ray_origin, ray_dir, drag.plane_pt_m, drag.plane_normal_m)
        if hit_m is None or drag.wall_obj is None:
            return EditActionResult(handled=True)

        delta_z_in = (hit_m[2] - drag.start_hit_m[2]) / INCH_TO_M
        snap = 0.25 if shift else 1.0
        wall = drag.wall_obj

        if drag.wall_end_mode == "start":
            new_h0 = max(12.0, min(480.0, round((drag.orig_wall_h0 + delta_z_in) / snap) * snap))
            wall.height = new_h0
            shown_h = new_h0
        elif drag.wall_end_mode == "end":
            new_h1 = max(12.0, min(480.0, round((drag.orig_wall_h1 + delta_z_in) / snap) * snap))
            wall.height_at_end = new_h1
            shown_h = new_h1
        else:
            snapped_dz = round(delta_z_in / snap) * snap
            wall.height = max(12.0, min(480.0, drag.orig_wall_h0 + snapped_dz))
            wall.height_at_end = max(12.0, min(480.0, drag.orig_wall_h1 + snapped_dz))
            shown_h = wall.height

        recalc_w = getattr(canvas, "recalculate_roofs_for_wall", None)
        if callable(recalc_w):
            recalc_w(wall.identifier)
        drag.changed = True
        return EditActionResult(
            handled=True,
            mutated=True,
            needs_mesh_sync=True,
            needs_render=True,
            hud_message=f"Wall Height ({drag.wall_end_mode}): {_format_inches(canvas, shown_h)}",
        )

    def _begin_roof_pitch_drag(
        self,
        roof: _RoofLike,
        hit: PickHit,
        ray_dir: Point3D,
        ids: list[str],
    ) -> EditActionResult:
        horiz = math.hypot(ray_dir[0], ray_dir[1])
        plane_n = (
            (-ray_dir[0] / horiz, -ray_dir[1] / horiz, 0.0)
            if horiz > 1e-4
            else (1.0, 0.0, 0.0)
        )
        orig_pitch = float(getattr(roof, "pitch_rise", 6.0) or 6.0)
        self.active_drag = _ActiveDrag(
            kind="roof_pitch",
            entity_id=hit.entity_id,
            plane_pt_m=hit.world_pos_m,
            plane_normal_m=plane_n,
            start_hit_m=hit.world_pos_m,
            roof_obj=roof,
            orig_pitch=orig_pitch,
        )
        return EditActionResult(
            handled=True,
            needs_render=True,
            selected_ids=ids,
            hud_message=f"Roof Pitch: {orig_pitch:g}/12 (Drag up/down)",
        )

    def _update_roof_pitch_drag(
        self,
        canvas: object,
        drag: _ActiveDrag,
        ray_origin: Point3D,
        ray_dir: Point3D,
        shift: bool = False,
    ) -> EditActionResult:
        hit_m = ray_intersect_plane(ray_origin, ray_dir, drag.plane_pt_m, drag.plane_normal_m)
        if hit_m is None or drag.roof_obj is None:
            return EditActionResult(handled=True)

        delta_z_in = (hit_m[2] - drag.start_hit_m[2]) / INCH_TO_M
        snap = 0.5 if shift else 1.0
        new_pitch = max(1.0, min(18.0, round((drag.orig_pitch + delta_z_in / 4.0) / snap) * snap))
        if abs(new_pitch - float(drag.roof_obj.pitch_rise)) > 1e-6:
            drag.roof_obj.pitch_rise = new_pitch
            recalc_r = getattr(canvas, "recalculate_roof", None)
            if callable(recalc_r):
                recalc_r(drag.roof_obj)
            drag.changed = True
        return EditActionResult(
            handled=True,
            mutated=drag.changed,
            needs_mesh_sync=drag.changed,
            needs_render=True,
            hud_message=f"Roof Pitch: {new_pitch:g}/12",
        )
