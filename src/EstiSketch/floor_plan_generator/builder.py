"""Headless parametric multi-style, multi-option floor plan generator."""

from __future__ import annotations

import copy
import math
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple

from ..Canvas.events_roof import CanvasRoofEventsMixin
from ..Canvas.project_reset import reset_canvas_content
from ..Canvas.utils import generate_identifier
from ..components import (
    Door,
    Fixture,
    Layer,
    Level,
    Room,
    Stair,
    Text,
    Wall,
    Window,
)
from ..roof_components import Roof
from ..config import DEFAULT_SETTINGS
from ..fixtures_catalog import resolve_fixture_surface
from ..geometry.design_checks import validate_project_layout
from ..geometry.room_holes import polygon_area, sync_stair_holes
from .specs import (
    MAX_OPTIONS_PER_STYLE,
    MAX_STYLES,
    MAX_TOTAL_PLANS,
    FloorPlanRequest,
    GeneratedFloorPlan,
    HomeStyleSpec,
)
from .styles import get_style

Point = Tuple[float, float]
Rect = Tuple[float, float, float, float]  # (x0, y0, x1, y1) in inches

_EXT_WALL_W = 6.0
_INT_WALL_W = 4.5

_VARIANT_NAMES: tuple[str, ...] = (
    "Classic Wing",
    "Split-Suite",
    "L-Shaped Courtyard",
    "Front-Kitchen Open",
)


class PlanCanvas(CanvasRoofEventsMixin):
    """Minimal headless canvas supporting roof solving, stair holes, and project I/O."""

    def __init__(self, north_angle: float = 0.0) -> None:
        self.config = SimpleNamespace(**DEFAULT_SETTINGS)
        self.levels: List[Level] = []
        self.layers: List[Layer] = []
        self.active_level_id: str = ""
        self.active_layer_id: str = ""
        self.wall_sets: List[List[Wall]] = []
        self.walls: List[Wall] = []
        self.rooms: List[Room] = []
        self.doors: List[Tuple[Wall, Door, float]] = []
        self.windows: List[Tuple[Wall, Window, float]] = []
        self.texts: List[Text] = []
        self.dimensions: list[object] = []
        self.dimension_chains: list[object] = []
        self.leader_callouts: list[object] = []
        self.polyline_sets: list[object] = []
        self.circles: list[object] = []
        self.arcs: list[object] = []
        self.roofs: List[Roof] = []
        self.stairs: List[Stair] = []
        self.floor_openings: list[object] = []
        self.fixtures: List[Fixture] = []
        self.blueprints: list[object] = []
        self.groups: list[object] = []
        self.custom_assets: list[object] = []
        self.overrides_3d: dict[str, object] = {}
        self.selected_items: list[object] = []
        self.existing_ids: List[str] = []
        self.cut_lower_ceiling_under_stairs: bool = False
        self.north_angle: float = float(north_angle)
        self.ghost_level_id: Optional[str] = None
        self.ghost_opacity: float = 0.25
        self._roof_edge_markings: Dict[str, str] = {}
        self.views_3d: dict[str, object] = {}

    def generate_identifier(self, prefix: str, existing: Optional[List[str]] = None) -> str:
        """Generate a unique SH3D-style identifier for ``prefix``."""
        pool = existing if existing is not None else self.existing_ids
        return generate_identifier(prefix, pool)

    def new_id(self, prefix: str) -> str:
        """Create and register a new identifier on this plan canvas."""
        ident = self.generate_identifier(prefix, self.existing_ids)
        self.existing_ids.append(ident)
        return ident

    def get_layer_by_id(self, layer_id: str) -> Optional[Layer]:
        """Return matching :class:`Layer` or ``None``."""
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        return None

    def _points_close(self, p1: Point, p2: Point, tol: float = 0.5) -> bool:
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1]) <= tol

    def queue_draw(self) -> None:
        """No-op headless redraw hook."""

    def save_state(self) -> None:
        """No-op headless undo hook."""

    def update_hint(self, _msg: str) -> None:
        """No-op headless status hint hook."""


def _snap12(val: float) -> float:
    return round(val / 12.0) * 12.0


def _make_wall(
    canvas: PlanCanvas,
    start: Point,
    end: Point,
    width: float,
    height: float,
    layer_id: str,
    exterior: bool = False,
    footer: bool = False,
    ext_finish: str = "Hardie Lap Siding",
) -> Wall:
    w = Wall(
        start=start,
        end=end,
        width=width,
        height=height,
        exterior_wall=exterior,
        identifier=canvas.new_id("wall"),
        layer_id=layer_id,
    )
    w.footer = footer
    w.left_finish = "Drywall"
    w.right_finish = ext_finish if exterior else "Drywall"
    w.left_baseboard = True
    w.right_baseboard = not exterior
    if exterior:
        w.exterior_finish = ext_finish
    return w


def _add_room(
    canvas: PlanCanvas,
    name: str,
    points: List[Point],
    height: float,
    layer_id: str,
    floor_type: str,
    floor_pattern: str,
    room_type: str,
    is_slab: bool = True,
    slab_thickness: float = 4.0,
    label_pos: Optional[Point] = None,
) -> Room:
    r = Room(
        points=points,
        height=height,
        identifier=canvas.new_id("room"),
        layer_id=layer_id,
    )
    r.name = name
    r.floor_type = floor_type
    r.floor_pattern = floor_pattern
    r.room_type = room_type
    r.is_slab = is_slab
    r.slab_thickness = slab_thickness
    canvas.rooms.append(r)

    if label_pos is None:
        lx = sum(p[0] for p in points) / len(points)
        ly = sum(p[1] for p in points) / len(points)
    else:
        lx, ly = label_pos
    txt = Text(
        x=lx - 34.0,
        y=ly - 10.0,
        content=name,
        width=68.0,
        height=20.0,
        identifier=canvas.new_id("text"),
        layer_id=layer_id,
        font_size=10.5,
        bold=True,
    )
    canvas.texts.append(txt)
    return r


def _ratio_along(wall: Wall, coord: float, axis: str) -> float:
    idx = 0 if axis == "x" else 1
    s = float(wall.start[idx])
    e = float(wall.end[idx])
    if abs(e - s) < 1e-6:
        return 0.5
    return max(0.05, min(0.95, (coord - s) / (e - s)))


def _add_door(
    canvas: PlanCanvas,
    wall: Wall,
    ratio: float,
    door_type: str,
    width: float,
    height: float,
    layer_id: str,
    swing: str = "left",
    orientation: str = "inswing",
) -> Door:
    d = Door(
        door_type=door_type,
        width=width,
        height=height,
        swing=swing,
        orientation=orientation,
        identifier=canvas.new_id("door"),
        layer_id=layer_id,
    )
    canvas.doors.append((wall, d, ratio))
    return d


def _add_window(
    canvas: PlanCanvas,
    wall: Wall,
    ratio: float,
    window_type: str,
    width: float,
    height: float,
    layer_id: str,
) -> Window:
    win = Window(
        width=width,
        height=height,
        window_type=window_type,
        identifier=canvas.new_id("window"),
        layer_id=layer_id,
    )
    canvas.windows.append((wall, win, ratio))
    return win


def _add_fx(
    canvas: PlanCanvas,
    symbol_type: str,
    x: float,
    y: float,
    rotation: float,
    layer_id: str,
    width: Optional[float] = None,
    depth: Optional[float] = None,
) -> Fixture:
    fx = Fixture(
        symbol_type=symbol_type,
        x=x,
        y=y,
        width=width,
        depth=depth,
        rotation=rotation,
        countertop_material="quartz",
        identifier=canvas.new_id("fixture"),
        layer_id=layer_id,
    )
    canvas.fixtures.append(fx)
    return fx


def _wall_has_span(wall: Wall, x_or_y: float, axis: str, min_margin: float = 22.0) -> bool:
    idx = 0 if axis == "x" else 1
    lo = min(float(wall.start[idx]), float(wall.end[idx]))
    hi = max(float(wall.start[idx]), float(wall.end[idx]))
    return lo + min_margin <= x_or_y <= hi - min_margin


def _add_door_to_room(
    canvas: PlanCanvas,
    wall: Wall,
    coord: float,
    axis: str,
    target_room_pt: Point,
    door_type: str,
    width: float,
    layer_id: str,
    swing: str = "left",
) -> Door:
    """Place a hinged/opening door on ``wall`` swinging toward ``target_room_pt``."""
    ratio = _ratio_along(wall, coord, axis)
    dx = float(wall.end[0]) - float(wall.start[0])
    dy = float(wall.end[1]) - float(wall.start[1])
    wlen = math.hypot(dx, dy) or 1.0
    px, py = -dy / wlen, dx / wlen
    cx = float(wall.start[0]) + ratio * dx
    cy = float(wall.start[1]) + ratio * dy
    dot = (target_room_pt[0] - cx) * px + (target_room_pt[1] - cy) * py
    orientation = "inswing" if dot >= 0.0 else "outswing"
    return _add_door(
        canvas, wall, ratio, door_type, width, 80.0, layer_id,
        swing=swing, orientation=orientation,
    )


def _rect_overlaps(a: Rect, b: Rect, pad: float = 1.0) -> bool:
    return a[0] < b[2] + pad and a[2] > b[0] - pad and a[1] < b[3] + pad and a[3] > b[1] - pad


def _door_blocked_rect(
    wall: Wall, ratio: float, door_w: float, door_type: str, depth_in: float = 42.0
) -> Rect:
    """Return conservative axis-aligned clearance zone around a wall opening."""
    dx = float(wall.end[0]) - float(wall.start[0])
    dy = float(wall.end[1]) - float(wall.start[1])
    wlen = math.hypot(dx, dy) or 1.0
    ux, uy = dx / wlen, dy / wlen
    nx, ny = -uy, ux
    cx = float(wall.start[0]) + ratio * dx
    cy = float(wall.start[1]) + ratio * dy
    hw = max(door_w / 2.0 + 4.0, 22.0)
    d = depth_in if door_type not in ("pocket", "sliding") else 30.0
    pts = [
        (cx - hw * ux - d * nx, cy - hw * uy - d * ny),
        (cx + hw * ux - d * nx, cy + hw * uy - d * ny),
        (cx + hw * ux + d * nx, cy + hw * uy + d * ny),
        (cx - hw * ux + d * nx, cy - hw * uy + d * ny),
    ]
    return (
        min(p[0] for p in pts),
        min(p[1] for p in pts),
        max(p[0] for p in pts),
        max(p[1] for p in pts),
    )


def _room_door_zones(canvas: PlanCanvas, level_id: str) -> list[Rect]:
    layer_to_lvl = {l.id: l.level_id for l in canvas.layers}
    zones: list[Rect] = []
    for wall, door, ratio in canvas.doors:
        if layer_to_lvl.get(door.layer_id, "") != level_id:
            continue
        zones.append(_door_blocked_rect(wall, ratio, door.width, door.door_type))
    return zones


def _furnish_kitchen(
    canvas: PlanCanvas,
    lid: str,
    rect: Rect,
    north_ext_wall: Optional[Wall],
    style: HomeStyleSpec,
    blocked_zones: list[Rect],
    sink_on_west: bool = False,
    west_ext_wall: Optional[Wall] = None,
) -> None:
    """Place kitchen cabinets, sink + centered exterior window, appliances, and optional island."""
    x0, y0, x1, y1 = rect
    kw = x1 - x0
    kd = y1 - y0
    if kw < 108.0 or kd < 96.0:
        return

    if not sink_on_west and north_ext_wall is not None:
        # North exterior run (y0 + 3 inner face)
        sink_x = min(x1 - 54.0, max(x0 + 57.0, x0 + kw * 0.42))
        _add_fx(canvas, "corner_base_cabinet", x0 + 21.0, y0 + 21.0, 0.0, lid)
        _add_fx(canvas, "corner_upper_cabinet", x0 + 15.0, y0 + 15.0, 0.0, lid)
        _add_fx(canvas, "sink_base_cabinet", sink_x, y0 + 15.0, 0.0, lid, width=36.0)
        win_w = min(48.0, style.window_width_in, max(30.0, kw - 72.0))
        _add_window(
            canvas,
            north_ext_wall,
            _ratio_along(north_ext_wall, sink_x, "x"),
            style.secondary_window_type,
            win_w,
            min(36.0, style.window_height_in),
            lid,
        )
        if sink_x + 30.0 + 15.0 <= x1 - 6.0:
            _add_fx(canvas, "dishwasher", sink_x + 30.0, y0 + 15.0, 0.0, lid)
        if sink_x + 54.0 + 15.0 <= x1 - 6.0:
            _add_fx(canvas, "base_drawer_cabinet", sink_x + 54.0, y0 + 15.0, 0.0, lid, width=24.0)
            _add_fx(canvas, "upper_cabinet", sink_x + 54.0, y0 + 9.0, 0.0, lid, width=24.0)

        # West run (x0 + 3 inner face, facing East rot=270)
        if kd >= 132.0:
            _add_fx(canvas, "base_cabinet", x0 + 15.0, y0 + 51.0, 270.0, lid, width=24.0)
            _add_fx(canvas, "upper_cabinet", x0 + 9.0, y0 + 51.0, 270.0, lid, width=24.0)
            _add_fx(canvas, "range_stove", x0 + 16.0, y0 + 78.0, 270.0, lid)
            _add_fx(canvas, "range_hood", x0 + 13.0, y0 + 78.0, 270.0, lid)
            _add_fx(canvas, "refrigerator", x0 + 18.0, y0 + 111.0, 270.0, lid)

        # Island only when 40"+ clear on all 4 sides & clear of door zones
        if kw >= 168.0 and kd >= 156.0:
            isl_w = min(60.0, kw - 114.0)
            isl_d = 28.0
            ix = x0 + 33.0 + 40.0 + isl_w / 2.0
            iy = y0 + 27.0 + 40.0 + isl_d / 2.0
            isl_rect: Rect = (
                ix - isl_w / 2.0 - 40.0,
                iy - isl_d / 2.0 - 40.0,
                ix + isl_w / 2.0 + 40.0,
                iy + isl_d / 2.0 + 12.0 + 40.0,
            )
            island_clear = (
                isl_w >= 42.0,
                ix + isl_w / 2.0 <= x1 - 40.0,
                iy + isl_d / 2.0 + 12.0 <= y1 - 40.0,
                not any(_rect_overlaps(isl_rect, bz, pad=0.0) for bz in blocked_zones),
            )
            if all(island_clear):
                _add_fx(canvas, "island_cabinet", ix, iy, 0.0, lid, width=isl_w, depth=isl_d)
    elif west_ext_wall is not None:
        # West exterior sink wall
        sink_y = min(y1 - 54.0, max(y0 + 57.0, y0 + kd * 0.45))
        _add_fx(canvas, "sink_base_cabinet", x0 + 15.0, sink_y, 270.0, lid, width=36.0)
        _add_window(
            canvas,
            west_ext_wall,
            _ratio_along(west_ext_wall, sink_y, "y"),
            style.secondary_window_type,
            min(48.0, style.window_width_in),
            min(36.0, style.window_height_in),
            lid,
        )
        if sink_y + 30.0 <= y1 - 24.0:
            _add_fx(canvas, "dishwasher", x0 + 15.0, sink_y + 30.0, 270.0, lid)
        if kw >= 132.0:
            _add_fx(canvas, "base_cabinet", x0 + 51.0, y0 + 15.0, 0.0, lid, width=24.0)
            _add_fx(canvas, "range_stove", x0 + 78.0, y0 + 16.0, 0.0, lid)
            _add_fx(canvas, "range_hood", x0 + 78.0, y0 + 13.0, 0.0, lid)
            _add_fx(canvas, "refrigerator", x0 + 111.0, y0 + 18.0, 0.0, lid)


def _furnish_full_bath(
    canvas: PlanCanvas,
    lid: str,
    rect: Rect,
    blocked_zones: list[Rect],
    door_on_south: bool = True,
    door_on_west: bool = False,
) -> None:
    """Place bathtub (drain flush on plumbing wall), toilet, and vanity with 24\"+ clearance."""
    x0, y0, x1, y1 = rect
    bw = x1 - x0
    bd = y1 - y0
    if bw < 66.0 or bd < 66.0:
        return

    # Orient wet fixtures away from the hallway door edge (y1 if door_on_south else y0)
    if bw >= 94.0 and bd >= 108.0:
        tub_x = (x1 - 17.5) if door_on_west else (x0 + 17.5)
        fix_x_van = (x0 + 13.0) if door_on_west else (x1 - 13.0)
        fix_x_wc = (x0 + 16.5) if door_on_west else (x1 - 16.5)
        fix_rot = 270.0 if door_on_west else 90.0
        if door_on_south:
            _add_fx(canvas, "bathtub", tub_x, y0 + 32.5, 90.0, lid)
            _add_fx(canvas, "vanity_single", fix_x_van, y0 + 22.0, fix_rot, lid, width=30.0)
            _add_fx(canvas, "toilet", fix_x_wc, y0 + 58.0, fix_rot, lid)
        else:
            _add_fx(canvas, "bathtub", tub_x, y1 - 32.5, 270.0, lid)
            _add_fx(canvas, "vanity_single", fix_x_van, y1 - 22.0, fix_rot, lid, width=30.0)
            _add_fx(canvas, "toilet", fix_x_wc, y1 - 58.0, fix_rot, lid)
        return

    # Wide & shallow (>=94" wide x 72..107" deep): tub horizontal along North/South away from door
    if bw >= 94.0:
        tub_x = (x1 - 32.5) if door_on_west else (x0 + 32.5)
        tub_rot = 180.0 if door_on_west else 0.0
        fix_x_wc = (x0 + 16.5) if door_on_west else (x1 - 16.5)
        fix_x_sink = (x0 + 12.0) if door_on_west else (x1 - 12.0)
        fix_rot = 270.0 if door_on_west else 90.0
        if door_on_south:
            _add_fx(canvas, "bathtub", tub_x, y0 + 17.5, tub_rot, lid)
            _add_fx(canvas, "toilet", fix_x_wc, y0 + 22.0, fix_rot, lid)
            _add_fx(canvas, "pedestal_sink", fix_x_sink, y0 + 52.0, fix_rot, lid)
        else:
            _add_fx(canvas, "bathtub", tub_x, y1 - 17.5, tub_rot, lid)
            _add_fx(canvas, "toilet", fix_x_wc, y1 - 22.0, fix_rot, lid)
            _add_fx(canvas, "pedestal_sink", fix_x_sink, y1 - 52.0, fix_rot, lid)
        return

    # Compact fallback when bw < 94"
    sh_x = (x1 - 20.5) if door_on_west else (x0 + 20.5)
    sink_x = (x1 - 12.0) if door_on_west else (x0 + 12.0)
    sink_rot = 90.0 if door_on_west else 270.0
    wc_x = (x0 + 15.0) if door_on_west else (x1 - 15.0)
    if door_on_south:
        _add_fx(canvas, "shower_square", sh_x, y0 + 20.5, 0.0, lid)
        _add_fx(canvas, "pedestal_sink", sink_x, y0 + 58.0, sink_rot, lid)
        _add_fx(canvas, "toilet", wc_x, y0 + 16.5, 0.0, lid)
    else:
        _add_fx(canvas, "shower_square", sh_x, y1 - 20.5, 0.0, lid)
        _add_fx(canvas, "pedestal_sink", sink_x, y1 - 58.0, sink_rot, lid)
        _add_fx(canvas, "toilet", wc_x, y1 - 16.5, 180.0, lid)


def _furnish_half_bath(
    canvas: PlanCanvas,
    lid: str,
    rect: Rect,
    blocked_zones: list[Rect],
    door_on_south: bool = True,
) -> None:
    """Place toilet and pedestal sink in a compact half bath clear of door landings."""
    x0, y0, x1, y1 = rect
    ty = (y0 + 20.0) if door_on_south else (y1 - 20.0)
    sy = (y0 + 48.0) if door_on_south else (y1 - 48.0)
    west_ok = not any(
        _rect_overlaps((x0 + 2.5, min(ty, sy) - 12.0, x0 + 54.0, max(ty, sy) + 12.0), bz, pad=1.0)
        for bz in blocked_zones
    )
    if west_ok:
        _add_fx(canvas, "toilet", x0 + 16.5, ty, 270.0, lid)
        _add_fx(canvas, "pedestal_sink", x0 + 12.0, sy, 270.0, lid)
    else:
        _add_fx(canvas, "toilet", x1 - 16.5, ty, 90.0, lid)
        _add_fx(canvas, "pedestal_sink", x1 - 12.0, sy, 90.0, lid)


def _furnish_bedroom(
    canvas: PlanCanvas,
    lid: str,
    rect: Rect,
    is_primary: bool,
    blocked_zones: list[Rect],
) -> None:
    """Place bed, nightstands, and dresser inside ``rect`` clear of walls and doors."""
    x0, y0, x1, y1 = rect
    rw = x1 - x0
    rd = y1 - y0
    if rw < 108.0 or rd < 108.0:
        return

    if is_primary and rw >= 136.0 and rd >= 136.0:
        sym, bw, bd = "bed_queen", 60.0, 80.0
    elif rw >= 120.0 and rd >= 120.0:
        sym, bw, bd = "bed_queen", 60.0, 80.0
    else:
        sym, bw, bd = "bed_twin", 39.0, 75.0

    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    # Candidate placements: (x, y, rot_deg, aabb_with_margin)
    candidates: list[tuple[float, float, float, Rect]] = [
        # Headboard North (rot=0)
        (cx, y0 + 3.0 + bd / 2.0, 0.0,
         (cx - bw / 2.0 - 4.0, y0 + 2.5, cx + bw / 2.0 + 4.0, y0 + 3.0 + bd + 18.0)),
        # Headboard South (rot=180)
        (cx, y1 - 3.0 - bd / 2.0, 180.0,
         (cx - bw / 2.0 - 4.0, y1 - 3.0 - bd - 18.0, cx + bw / 2.0 + 4.0, y1 - 2.5)),
        # Headboard East (rot=90)
        (x1 - 3.0 - bd / 2.0, cy, 90.0,
         (x1 - 3.0 - bd - 18.0, cy - bw / 2.0 - 4.0, x1 - 2.5, cy + bw / 2.0 + 4.0)),
        # Headboard West (rot=270)
        (x0 + 3.0 + bd / 2.0, cy, 270.0,
         (x0 + 2.5, cy - bw / 2.0 - 4.0, x0 + 3.0 + bd + 18.0, cy + bw / 2.0 + 4.0)),
    ]

    placed_rect: Optional[Rect] = None
    for bx, by, brot, brect in candidates:
        if brect[0] < x0 + 6.0 or brect[2] > x1 - 6.0 or brect[1] < y0 + 6.0 or brect[3] > y1 - 6.0:
            continue
        if any(_rect_overlaps(brect, bz, pad=2.0) for bz in blocked_zones):
            continue
        _add_fx(canvas, sym, bx, by, brot, lid)
        placed_rect = brect
        if brot in (0.0, 180.0):
            ny = y0 + 12.0 if brot == 0.0 else y1 - 12.0
            for nx_pos in (bx - bw / 2.0 - 14.0, bx + bw / 2.0 + 14.0):
                nrect: Rect = (nx_pos - 11.0, ny - 9.0, nx_pos + 11.0, ny + 9.0)
                if nrect[0] >= x0 + 4.0 and nrect[2] <= x1 - 4.0:
                    if not any(_rect_overlaps(nrect, bz, pad=2.0) for bz in blocked_zones):
                        _add_fx(canvas, "nightstand", nx_pos, ny, brot, lid)
        else:
            nx_pos = x1 - 12.0 if brot == 90.0 else x0 + 12.0
            for ny in (by - bw / 2.0 - 14.0, by + bw / 2.0 + 14.0):
                nrect = (nx_pos - 9.0, ny - 11.0, nx_pos + 9.0, ny + 11.0)
                if nrect[1] >= y0 + 4.0 and nrect[3] <= y1 - 4.0:
                    if not any(_rect_overlaps(nrect, bz, pad=2.0) for bz in blocked_zones):
                        _add_fx(canvas, "nightstand", nx_pos, ny, brot, lid)
        break

    # Add dresser if clear of bed and door zones
    if placed_rect is not None and rw >= 132.0:
        drect: Rect = (cx - 27.0, y1 - 24.0, cx + 27.0, y1 - 3.0)
        if not _rect_overlaps(drect, placed_rect, pad=18.0):
            if not any(_rect_overlaps(drect, bz, pad=4.0) for bz in blocked_zones):
                _add_fx(canvas, "dresser", cx, y1 - 13.0, 180.0, lid)


def _furnish_living(
    canvas: PlanCanvas,
    lid: str,
    rect: Rect,
    blocked_zones: list[Rect],
) -> None:
    """Place sofa, coffee table, and TV console inside ``rect`` clear of door landings."""
    x0, y0, x1, y1 = rect
    lw = x1 - x0
    ld = y1 - y0
    if lw < 132.0 or ld < 120.0:
        return
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0

    sofa_rect: Rect = (cx - 42.0, cy - 36.0, cx + 42.0, cy)
    ct_rect: Rect = (cx - 24.0, cy + 12.0, cx + 24.0, cy + 36.0)
    tv_rect: Rect = (cx - 30.0, y1 - 22.0, cx + 30.0, y1 - 3.0)

    if sofa_rect[0] >= x0 + 18.0 and sofa_rect[2] <= x1 - 18.0:
        if not any(_rect_overlaps(sofa_rect, bz, pad=4.0) for bz in blocked_zones):
            _add_fx(canvas, "sofa", cx, cy - 18.0, 0.0, lid)
            if not any(_rect_overlaps(ct_rect, bz, pad=4.0) for bz in blocked_zones):
                _add_fx(canvas, "coffee_table", cx, cy + 24.0, 0.0, lid)
    if tv_rect[0] >= x0 + 12.0 and tv_rect[2] <= x1 - 12.0:
        if not _rect_overlaps(tv_rect, ct_rect, pad=12.0):
            if not any(_rect_overlaps(tv_rect, bz, pad=4.0) for bz in blocked_zones):
                _add_fx(canvas, "tv_console", cx, y1 - 12.5, 180.0, lid)


def _furnish_dining(
    canvas: PlanCanvas,
    lid: str,
    rect: Rect,
    blocked_zones: list[Rect],
) -> None:
    """Place dining table + chairs inside ``rect`` when clearances allow."""
    x0, y0, x1, y1 = rect
    dw = x1 - x0
    dd = y1 - y0
    if dw < 108.0 or dd < 96.0:
        return
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    table_rect: Rect = (cx - 48.0, cy - 32.0, cx + 48.0, cy + 32.0)
    inside_room = (
        table_rect[0] >= x0 + 12.0 and table_rect[2] <= x1 - 12.0,
        table_rect[1] >= y0 + 12.0 and table_rect[3] <= y1 - 12.0,
        not any(_rect_overlaps(table_rect, bz, pad=4.0) for bz in blocked_zones),
    )
    if all(inside_room):
        _add_fx(canvas, "dining_table", cx, cy, 0.0, lid)
        for dx in (-20.0, 20.0):
            _add_fx(canvas, "dining_chair", cx + dx, cy - 26.0, 0.0, lid)
            _add_fx(canvas, "dining_chair", cx + dx, cy + 26.0, 180.0, lid)


def _furnish_office(
    canvas: PlanCanvas,
    lid: str,
    rect: Rect,
    blocked_zones: list[Rect],
    door_on_south: bool = True,
) -> None:
    """Place desk and office chair inside ``rect`` clear of door swings."""
    x0, y0, x1, y1 = rect
    if x1 - x0 < 96.0 or y1 - y0 < 96.0:
        return
    cx = (x0 + x1) / 2.0
    if door_on_south:
        desk_rect: Rect = (cx - 32.0, y0 + 4.0, cx + 32.0, y0 + 64.0)
        if not any(_rect_overlaps(desk_rect, bz, pad=4.0) for bz in blocked_zones):
            _add_fx(canvas, "desk", cx, y0 + 20.0, 0.0, lid)
            _add_fx(canvas, "office_chair", cx, y0 + 48.0, 180.0, lid)
    else:
        desk_rect = (cx - 32.0, y1 - 64.0, cx + 32.0, y1 - 4.0)
        if not any(_rect_overlaps(desk_rect, bz, pad=4.0) for bz in blocked_zones):
            _add_fx(canvas, "desk", cx, y1 - 20.0, 180.0, lid)
            _add_fx(canvas, "office_chair", cx, y1 - 48.0, 0.0, lid)


def _furnish_laundry(
    canvas: PlanCanvas,
    lid: str,
    rect: Rect,
    door_on_south: bool = True,
) -> None:
    """Place washer and dryer with >= 30\" unobstructed front clearance."""
    x0, y0, x1, y1 = rect
    if x1 - x0 < 66.0 or y1 - y0 < 66.0:
        return
    cx = (x0 + x1) / 2.0
    if door_on_south:
        _add_fx(canvas, "washer", cx - 15.0, y0 + 18.0, 0.0, lid)
        _add_fx(canvas, "dryer", cx + 15.0, y0 + 18.0, 0.0, lid)
    else:
        _add_fx(canvas, "washer", cx - 15.0, y1 - 18.0, 180.0, lid)
        _add_fx(canvas, "dryer", cx + 15.0, y1 - 18.0, 180.0, lid)


def _apply_style_roof(
    canvas: PlanCanvas,
    eave_walls: List[Wall],
    gable_walls: List[Wall],
    style: HomeStyleSpec,
    layer_id: str,
) -> None:
    canvas.active_layer_id = layer_id
    canvas.clear_roof_markings()
    if style.roof_type == "hip" or not gable_walls:
        canvas.mark_walls_as_eave(eave_walls + gable_walls)
    else:
        canvas.mark_walls_as_eave(eave_walls)
        canvas.mark_walls_as_gable(gable_walls)
    canvas.generate_roof_from_marked_walls(
        pitch_rise=style.roof_pitch_rise,
        pitch_run=12,
        overhang=style.roof_overhang_in,
        material=style.roof_material,
    )


def _garage_width_in(garage_cars: int) -> float:
    if garage_cars <= 0:
        return 0.0
    return {1: 144.0, 2: 264.0, 3: 384.0}[garage_cars]


def _build_attached_garage(
    canvas: PlanCanvas,
    lid: str,
    x_attach: float,
    y_top: float,
    y_bot: float,
    gw: float,
    h: float,
    style: HomeStyleSpec,
    shared_wall: Wall,
    shared_door_y: float,
    garage_cars: int,
    is_2story: bool,
    attach_on_west: bool = False,
) -> None:
    """Attach a 1-story garage on the East (or West) flank of ``shared_wall``."""
    x_e = (x_attach - gw) if attach_on_west else (x_attach + gw)
    if attach_on_west:
        wg_n = _make_wall(canvas, (x_e, y_top), (x_attach, y_top), _EXT_WALL_W, h, lid,
                          exterior=True, footer=True, ext_finish=style.exterior_finish)
        wg_w = _make_wall(canvas, (x_e, y_bot), (x_e, y_top), _EXT_WALL_W, h, lid,
                          exterior=True, footer=True, ext_finish=style.exterior_finish)
        wg_s = _make_wall(canvas, (x_attach, y_bot), (x_e, y_bot), _EXT_WALL_W, h, lid,
                          exterior=True, footer=True, ext_finish=style.exterior_finish)
        canvas.wall_sets.append([wg_n, shared_wall, wg_s, wg_w])
        poly = [(x_e, y_top), (x_attach, y_top), (x_attach, y_bot), (x_e, y_bot)]
        side_win_wall = wg_w
        gable_walls = [wg_w, shared_wall]
        room_in_pt = (x_attach + 24.0, shared_door_y)
    else:
        wg_n = _make_wall(canvas, (x_attach, y_top), (x_e, y_top), _EXT_WALL_W, h, lid,
                          exterior=True, footer=True, ext_finish=style.exterior_finish)
        wg_e = _make_wall(canvas, (x_e, y_top), (x_e, y_bot), _EXT_WALL_W, h, lid,
                          exterior=True, footer=True, ext_finish=style.exterior_finish)
        wg_s = _make_wall(canvas, (x_e, y_bot), (x_attach, y_bot), _EXT_WALL_W, h, lid,
                          exterior=True, footer=True, ext_finish=style.exterior_finish)
        canvas.wall_sets.append([wg_n, wg_e, wg_s, shared_wall])
        poly = [(x_attach, y_top), (x_e, y_top), (x_e, y_bot), (x_attach, y_bot)]
        side_win_wall = wg_e
        gable_walls = [wg_e, shared_wall]
        room_in_pt = (x_attach - 24.0, shared_door_y)

    _add_room(
        canvas,
        f"{garage_cars}-Car Garage",
        poly,
        h,
        lid,
        "concrete",
        "concrete_stipple",
        "garage",
        is_slab=True,
        slab_thickness=6.0,
    )

    door_w = 108.0 if garage_cars == 1 else (192.0 if garage_cars == 2 else 216.0)
    _add_door(canvas, wg_s, 0.5, "garage", door_w, 84.0, lid)
    _add_door_to_room(
        canvas, shared_wall, shared_door_y, "y",
        room_in_pt, "single", 34.0, lid, swing="left",
    )
    _add_window(canvas, side_win_wall, 0.5, style.secondary_window_type, 48.0, 36.0, lid)

    if is_2story:
        _apply_style_roof(canvas, [wg_n, wg_s], gable_walls, style, lid)


def _split_bath_counts(bathrooms: float, levels: int) -> tuple[int, int, int, int]:
    """Return ``(l1_full, l1_half, l2_full, l2_half)`` matching ``bathrooms``."""
    full_total = int(math.floor(bathrooms + 1e-6))
    has_half = abs((bathrooms - full_total) - 0.5) < 0.1
    half_total = 1 if has_half else 0
    if levels == 1:
        return (full_total, half_total, 0, 0)
    # 2-story: reserve half bath for Level 1 when available; if >= 3 full baths put 1 on L1
    if full_total >= 3:
        l1_full = 1
        l2_full = full_total - 1
        return (l1_full, half_total, l2_full, 0)
    return (0, half_total, full_total, 0)


def _balance_wing_rows(
    items: list[tuple[str, str, bool]],
    min_widths: dict[str, float],
) -> tuple[list[tuple[str, str, bool]], list[tuple[str, str, bool]]]:
    """Greedily balance wing rooms across North and South rows by minimum width."""
    north_items: list[tuple[str, str, bool]] = []
    south_items: list[tuple[str, str, bool]] = []
    north_w = 0.0
    south_w = 0.0
    for item in items:
        item_w = min_widths[item[0]]
        if north_w <= south_w:
            north_items.append(item)
            north_w += item_w
        else:
            south_items.append(item)
            south_w += item_w
    if not south_items and len(north_items) > 1:
        south_items.append(north_items.pop())
    return (north_items, south_items)


def _layout_bedroom_wing(
    canvas: PlanCanvas,
    lid: str,
    wx0: float,
    wy0: float,
    wx1: float,
    wy1: float,
    h: float,
    bed_specs: list[tuple[str, bool]],
    full_baths: int,
    half_baths: int,
    include_laundry: bool,
    hall_entry_wall: Wall,
    style: HomeStyleSpec,
    is_slab: bool,
    ext_walls_lookup: dict[str, Wall],
    add_entry_opening: bool = True,
    row_variation: int = 0,
    compact_baths: bool = False,
    minimal_hall: bool = False,
    entry_side: str = "west",
    require_full_hall: bool = False,
    east_alcove: Optional[tuple[float, float]] = None,
    include_office: bool = False,
) -> float:
    """Divide wing ``[wx0..wx1] x [wy0..wy1]`` into a corridor + bedrooms/baths/laundry.

    In open-concept ``minimal_hall`` mode, uses a compact ``42\"`` corridor, eliminates
    dead-end hallway segments when ``not require_full_hall``, and omits the hallway
    altogether for a single-bedroom/single-bath open suite. Returns the hallway
    centerline Y coordinate ``(hy0 + hy1) / 2.0``.
    """
    wing_w = wx1 - wx0
    wing_d = wy1 - wy0
    if all((
        minimal_hall,
        not require_full_hall,
        len(bed_specs) == 1,
        full_baths == 1,
        half_baths == 0,
        not include_laundry,
        not include_office,
    )):
        bed_label, is_prim = bed_specs[0]
        pb_y = wy0 + 96.0
        mid_x = 0.5 * (wx0 + wx1)
        w_pb_s = _make_wall(canvas, (wx0, pb_y), (wx1, pb_y), _INT_WALL_W, h, lid)
        canvas.wall_sets.append([w_pb_s])
        bath_label = "Primary Bath" if is_prim else "Full Bath 1"
        _add_room(
            canvas, bath_label, [(wx0, wy0), (wx1, wy0), (wx1, pb_y), (wx0, pb_y)],
            h, lid, "tile", style.bath_floor_pattern, "bathroom", is_slab=is_slab,
        )
        _add_room(
            canvas, bed_label, [(wx0, pb_y), (wx1, pb_y), (wx1, wy1), (wx0, wy1)],
            h, lid, "carpet", style.bedroom_floor_pattern, "bedroom", is_slab=is_slab,
        )
        _add_door_to_room(
            canvas, w_pb_s, mid_x, "x", (mid_x, 0.5 * (wy0 + pb_y)),
            "single", 30.0, lid, swing="left",
        )
        if _wall_has_span(ext_walls_lookup["north"], mid_x, "x", min_margin=20.0):
            _add_window(
                canvas, ext_walls_lookup["north"],
                _ratio_along(ext_walls_lookup["north"], mid_x, "x"),
                "awning", 24.0, 24.0, lid,
            )
        door_y = 0.5 * (pb_y + wy1)
        _add_door_to_room(
            canvas, hall_entry_wall, door_y, "y", (mid_x, door_y),
            "single", 32.0, lid, swing="left",
        )
        if _wall_has_span(ext_walls_lookup["south"], mid_x, "x", min_margin=28.0):
            _add_window(
                canvas, ext_walls_lookup["south"],
                _ratio_along(ext_walls_lookup["south"], mid_x, "x"),
                style.primary_window_type, min(style.window_width_in, wing_w - 36.0),
                style.window_height_in, lid,
            )
        lvl_id = canvas.get_layer_by_id(lid).level_id  # type: ignore[union-attr]
        bz = _room_door_zones(canvas, lvl_id)
        _furnish_full_bath(canvas, lid, (wx0, wy0, wx1, pb_y), bz, door_on_south=True)
        _furnish_bedroom(canvas, lid, (wx0, pb_y, wx1, wy1), is_prim, bz)
        return door_y

    hall_h = 42.0 if minimal_hall else 48.0
    hy0 = _snap12(wy0 + (wing_d - hall_h) / 2.0)
    hy0 = max(wy0 + 108.0, min(wy1 - 108.0 - hall_h, hy0))
    hy1 = hy0 + hall_h

    min_widths = {
        "bedroom": 108.0,
        "bathroom": 72.0 if compact_baths else 96.0,
        "half_bath": 72.0,
        "laundry": 72.0,
        "office": 96.0,
    }
    weights = {
        "bedroom": 1.65,
        "bathroom": 1.10,
        "half_bath": 0.78,
        "laundry": 0.78,
        "office": 1.20,
    }

    # North row and South row cells
    all_cells: list[tuple[str, str, bool]] = []

    for bname, is_p in bed_specs:
        all_cells.append(("bedroom", bname, is_p))
    for i in range(full_baths):
        bname = "Primary Bath" if i == 0 and any(p for _, p in bed_specs) else f"Full Bath {i + 1}"
        all_cells.append(("bathroom", bname, False))
    for i in range(half_baths):
        all_cells.append(("half_bath", "Half Bath" if i == 0 else f"Half Bath {i + 1}", False))
    if include_laundry:
        all_cells.append(("laundry", "Laundry", False))
    if include_office:
        all_cells.append(("office", "Home Office", False))

    north_items, south_items = _balance_wing_rows(all_cells, min_widths)

    if (row_variation & 1) and north_items and south_items:
        north_items, south_items = south_items, north_items
    if (row_variation >> 1) & 1:
        north_items = list(reversed(north_items))
        south_items = list(reversed(south_items))

    def _compute_row_xs(items: list[tuple[str, str, bool]]) -> list[float]:
        if not items:
            return []
        mins = [min_widths[k] for k, _, _ in items]
        extra = max(0.0, wing_w - sum(mins))
        tot_w = sum(weights[k] for k, _, _ in items) or 1.0
        xs: list[float] = [wx0]
        for idx, (kind, _, _) in enumerate(items):
            if idx == len(items) - 1:
                xs.append(wx1)
            else:
                share = mins[idx] + extra * (weights[kind] / tot_w)
                rem_min = sum(mins[idx + 1:])
                nx = _snap12(xs[-1] + share)
                nx = max(xs[-1] + mins[idx], min(wx1 - rem_min, nx))
                xs.append(nx)
        return xs

    north_xs = _compute_row_xs(north_items)
    south_xs = _compute_row_xs(south_items)

    # Trim dead-end hallway span in minimal_hall mode when outer end is not a garage entry
    hall_x0, hall_x1 = wx0, wx1
    if minimal_hall and not require_full_hall and len(north_items) >= 2 and len(south_items) >= 2:
        if entry_side == "west":
            raw_end = max(north_xs[-2], south_xs[-2]) + 48.0
            cand_end = math.ceil(raw_end / 12.0) * 12.0
            if wx1 - cand_end >= 36.0 and cand_end < wx1:
                hall_x1 = cand_end
        else:
            raw_start = min(north_xs[1], south_xs[1]) - 48.0
            cand_start = math.floor(raw_start / 12.0) * 12.0
            if cand_start - wx0 >= 36.0 and cand_start > wx0:
                hall_x0 = cand_start

    # Hallway walls
    w_hn = _make_wall(canvas, (hall_x0, hy0), (hall_x1, hy0), _INT_WALL_W, h, lid)
    w_hs = _make_wall(canvas, (hall_x0, hy1), (hall_x1, hy1), _INT_WALL_W, h, lid)
    hall_walls = [w_hn, w_hs]
    hy_mid = 0.5 * (hy0 + hy1)
    if hall_x1 < wx1:
        hall_walls.append(_make_wall(canvas, (hall_x1, hy0), (hall_x1, hy_mid), _INT_WALL_W, h, lid))
        hall_walls.append(_make_wall(canvas, (hall_x1, hy_mid), (hall_x1, hy1), _INT_WALL_W, h, lid))
        hall_walls.append(_make_wall(canvas, (hall_x1, hy_mid), (wx1, hy_mid), _INT_WALL_W, h, lid))
    if hall_x0 > wx0:
        hall_walls.append(_make_wall(canvas, (hall_x0, hy0), (hall_x0, hy_mid), _INT_WALL_W, h, lid))
        hall_walls.append(_make_wall(canvas, (hall_x0, hy_mid), (hall_x0, hy1), _INT_WALL_W, h, lid))
        hall_walls.append(_make_wall(canvas, (wx0, hy_mid), (hall_x0, hy_mid), _INT_WALL_W, h, lid))
    canvas.wall_sets.append(hall_walls)

    _add_room(
        canvas,
        "Bedroom Hall",
        [(hall_x0, hy0), (hall_x1, hy0), (hall_x1, hy1), (hall_x0, hy1)],
        h,
        lid,
        style.public_floor_type,
        style.public_floor_pattern,
        "hallway",
        is_slab=is_slab,
    )
    if add_entry_opening:
        _add_door(
            canvas,
            hall_entry_wall,
            _ratio_along(hall_entry_wall, hy_mid, "y"),
            "frame",
            44.0,
            80.0,
            lid,
        )

    def _partition_row(
        items: list[tuple[str, str, bool]],
        xs: list[float],
        ry0: float,
        ry1: float,
        hall_wall: Wall,
        is_north_row: bool,
    ) -> None:
        if not items:
            return

        part_walls: list[Wall] = []
        for idx in range(len(items) - 1):
            px = xs[idx + 1]
            pw = _make_wall(canvas, (px, ry0), (px, ry1), _INT_WALL_W, h, lid)
            part_walls.append(pw)
        if part_walls:
            canvas.wall_sets.append(part_walls)

        west_bath_flags: dict[int, bool] = {}
        for idx, (kind, label, _is_primary) in enumerate(items):
            cx0, cx1 = xs[idx], xs[idx + 1]
            rcenter = ((cx0 + cx1) / 2.0, (ry0 + ry1) / 2.0)
            pts: list[Point] = [(cx0, ry0), (cx1, ry0), (cx1, ry1), (cx0, ry1)]
            trimmed_west_end = hall_x1 < wx1 and idx == len(items) - 1
            trimmed_east_end = hall_x0 > wx0 and idx == 0

            if is_north_row and idx == len(items) - 1 and east_alcove is not None:
                alc_x1, alc_y1 = east_alcove
                if abs(alc_y1 - hy0) < 1e-3:
                    pts = [(cx0, ry0), (alc_x1, ry0), (alc_x1, hy0), (cx0, hy0)]
                else:
                    pts = [
                        (cx0, ry0), (alc_x1, ry0), (alc_x1, alc_y1),
                        (wx1, alc_y1), (wx1, hy0), (cx0, hy0),
                    ]
            elif trimmed_west_end:
                if is_north_row:
                    pts = [
                        (cx0, ry0), (wx1, ry0), (wx1, hy_mid),
                        (hall_x1, hy_mid), (hall_x1, hy0), (cx0, hy0),
                    ]
                else:
                    pts = [
                        (cx0, hy1), (hall_x1, hy1), (hall_x1, hy_mid),
                        (wx1, hy_mid), (wx1, ry1), (cx0, ry1),
                    ]
            elif trimmed_east_end:
                if is_north_row:
                    pts = [
                        (wx0, ry0), (cx1, ry0), (cx1, hy0),
                        (hall_x0, hy0), (hall_x0, hy_mid), (wx0, hy_mid),
                    ]
                else:
                    pts = [
                        (wx0, hy_mid), (hall_x0, hy_mid), (hall_x0, hy1),
                        (cx1, hy1), (cx1, ry1), (wx0, ry1),
                    ]

            def _cell_door_x(default_x: float) -> float:
                if trimmed_west_end:
                    return cx0 + 24.0
                if trimmed_east_end:
                    return cx1 - 24.0
                return default_x

            if kind == "bedroom":
                _add_room(
                    canvas, label, pts, h, lid,
                    "carpet", style.bedroom_floor_pattern, "bedroom", is_slab=is_slab,
                )
                dx = _cell_door_x((cx0 + cx1) / 2.0)
                _add_door_to_room(
                    canvas, hall_wall, dx, "x", (dx, rcenter[1]),
                    "single", 32.0, lid, swing="left",
                )
                ext_w = ext_walls_lookup["north" if is_north_row else "south"]
                if _wall_has_span(ext_w, (cx0 + cx1) / 2.0, "x", min_margin=28.0):
                    _add_window(
                        canvas, ext_w, _ratio_along(ext_w, (cx0 + cx1) / 2.0, "x"),
                        style.primary_window_type,
                        min(style.window_width_in, (cx1 - cx0) - 36.0),
                        style.window_height_in,
                        lid,
                    )
            elif kind == "office":
                _add_room(
                    canvas, label, pts, h, lid,
                    style.public_floor_type, style.public_floor_pattern, "office", is_slab=is_slab,
                )
                dx = _cell_door_x((cx0 + cx1) / 2.0)
                _add_door_to_room(
                    canvas, hall_wall, dx, "x", (dx, rcenter[1]),
                    "single", 32.0, lid, swing="left",
                )
                ext_w = ext_walls_lookup["north" if is_north_row else "south"]
                if _wall_has_span(ext_w, (cx0 + cx1) / 2.0, "x", min_margin=24.0):
                    _add_window(
                        canvas, ext_w, _ratio_along(ext_w, (cx0 + cx1) / 2.0, "x"),
                        style.secondary_window_type, 36.0, 42.0, lid,
                    )
            elif kind == "bathroom":
                _add_room(
                    canvas, label, pts, h, lid,
                    "tile", style.bath_floor_pattern, "bathroom", is_slab=is_slab,
                )
                door_x = _cell_door_x(max(cx0 + 24.0, cx1 - 30.0))
                west_bath_flags[idx] = trimmed_west_end
                _add_door_to_room(
                    canvas, hall_wall, door_x, "x", (door_x, rcenter[1]),
                    "single", 30.0, lid, swing="left",
                )
                ext_w = ext_walls_lookup["north" if is_north_row else "south"]
                if _wall_has_span(ext_w, (cx0 + cx1) / 2.0, "x", min_margin=20.0):
                    _add_window(
                        canvas, ext_w, _ratio_along(ext_w, (cx0 + cx1) / 2.0, "x"),
                        "awning", 24.0, 24.0, lid,
                    )
            elif kind == "half_bath":
                _add_room(
                    canvas, label, pts, h, lid,
                    "tile", style.bath_floor_pattern, "bathroom", is_slab=is_slab,
                )
                hx = _cell_door_x((cx0 + cx1) / 2.0)
                use_pocket = all((
                    not trimmed_west_end,
                    not trimmed_east_end,
                    (cx1 - cx0) >= 64.0,
                    (hx - hall_x0) >= 48.0,
                    (hall_x1 - hx) >= 48.0,
                    len(items) <= 2,
                ))
                if use_pocket:
                    _add_door(
                        canvas, hall_wall, _ratio_along(hall_wall, hx, "x"),
                        "pocket", 28.0, 80.0, lid, swing="left",
                        orientation="inswing" if not is_north_row else "outswing",
                    )
                else:
                    _add_door_to_room(
                        canvas, hall_wall, hx, "x", (hx, rcenter[1]),
                        "single", 28.0, lid, swing="left",
                    )
            else:
                _add_room(
                    canvas, label, pts, h, lid,
                    "tile", style.bath_floor_pattern, "utility", is_slab=is_slab,
                )
                lx = _cell_door_x((cx0 + cx1) / 2.0)
                _add_door(
                    canvas, hall_wall, _ratio_along(hall_wall, lx, "x"),
                    "bi-fold", 36.0, 80.0, lid, swing="left",
                    orientation="inswing" if not is_north_row else "outswing",
                )

        # Furnish rooms after all doors on this level are placed
        bz = _room_door_zones(canvas, canvas.get_layer_by_id(lid).level_id)  # type: ignore[union-attr]
        for idx, (kind, _label, is_primary) in enumerate(items):
            cell_rect: Rect = (xs[idx], ry0, xs[idx + 1], ry1)
            if kind == "bedroom":
                _furnish_bedroom(canvas, lid, cell_rect, is_primary, bz)
            elif kind == "office":
                _furnish_office(canvas, lid, cell_rect, bz, door_on_south=is_north_row)
            elif kind == "bathroom":
                _furnish_full_bath(
                    canvas,
                    lid,
                    cell_rect,
                    bz,
                    door_on_south=is_north_row,
                    door_on_west=west_bath_flags.get(idx, False),
                )
            elif kind == "half_bath":
                _furnish_half_bath(canvas, lid, cell_rect, bz, door_on_south=is_north_row)
            else:
                _furnish_laundry(canvas, lid, cell_rect, door_on_south=is_north_row)

    _partition_row(north_items, north_xs, wy0, hy0, w_hn, True)
    _partition_row(south_items, south_xs, hy1, wy1, w_hs, False)
    return hy_mid


def _min_wing_width(
    n_beds: int,
    n_full: int,
    n_half: int,
    has_laundry: bool,
    compact_baths: bool = False,
    minimal_hall: bool = False,
    include_office: bool = False,
) -> float:
    """Compute minimum wing width so every row cell meets architectural minimums."""
    if all((
        minimal_hall,
        n_beds == 1,
        n_full <= 1,
        n_half == 0,
        not has_laundry,
        not include_office,
    )):
        return 144.0
    min_widths = {
        "bedroom": 108.0,
        "bathroom": 72.0 if compact_baths else 96.0,
        "half_bath": 72.0,
        "laundry": 72.0,
        "office": 96.0,
    }
    items: list[tuple[str, str, bool]] = [("bedroom", "", False) for _ in range(n_beds)]
    items.extend(("bathroom", "", False) for _ in range(n_full))
    items.extend(("half_bath", "", False) for _ in range(n_half))
    if has_laundry:
        items.append(("laundry", "", False))
    if include_office:
        items.append(("office", "", False))
    north_items, south_items = _balance_wing_rows(items, min_widths)
    north_w = sum(min_widths[k] for k, _, _ in north_items)
    south_w = sum(min_widths[k] for k, _, _ in south_items)
    return max(180.0, north_w, south_w)


def _is_open_concept(req: FloorPlanRequest, style: HomeStyleSpec) -> bool:
    """Return True when the public zone uses an open-concept layout."""
    if req.open_floor_plan == "open":
        return True
    if req.open_floor_plan == "traditional":
        return False
    return style.open_concept


def _solve_rect_footprint(
    target_area_sqft: float,
    min_area_sqft: float,
    max_area_sqft: float,
    min_w_in: float,
    min_d_in: float,
    preferred_ratio: float = 1.5,
) -> tuple[float, float]:
    """Solve ``(width_in, depth_in)`` in inches fitting inside ``[min_area_sqft, max_area_sqft]``."""
    clamped_target = max(min_area_sqft, min(max_area_sqft, target_area_sqft))
    min_w_12 = math.ceil(min_w_in / 12.0) * 12.0
    min_d_12 = math.ceil(min_d_in / 12.0) * 12.0
    if (min_w_12 * min_d_12) / 144.0 > max_area_sqft:
        min_w_6 = math.ceil(min_w_in / 6.0) * 6.0
        min_d_6 = math.ceil(min_d_in / 6.0) * 6.0
        return (min_w_6, min_d_6)

    for step in (12.0, 6.0):
        w_lo = math.ceil(min_w_in / step) * step
        d_lo = math.ceil(min_d_in / step) * step
        max_w = max(w_lo, math.ceil(math.sqrt(max_area_sqft * 144.0 * 2.4) / step) * step)
        best_in: Optional[tuple[float, float, float]] = None
        w = w_lo
        while w <= max_w + 1e-6:
            ideal_d = (clamped_target * 144.0) / w
            d_cands = (
                math.floor(ideal_d / step) * step,
                round(ideal_d / step) * step,
                math.ceil(ideal_d / step) * step,
                math.ceil((min_area_sqft * 144.0) / w / step) * step,
                math.floor((max_area_sqft * 144.0) / w / step) * step,
            )
            for dc in d_cands:
                d = max(d_lo, dc)
                area = (w * d) / 144.0
                if min_area_sqft - 1e-6 <= area <= max_area_sqft + 1e-6:
                    score = abs(area - clamped_target) / max(1.0, clamped_target)
                    score += 0.15 * abs((w / max(1.0, d)) - preferred_ratio)
                    if best_in is None or score < best_in[0]:
                        best_in = (score, w, d)
            w += step
        if best_in is not None:
            return (best_in[1], best_in[2])

    best_out: Optional[tuple[float, float, float, float]] = None
    step = 6.0
    w_lo = math.ceil(min_w_in / step) * step
    d_lo = math.ceil(min_d_in / step) * step
    max_w = max(w_lo, math.ceil(math.sqrt(max_area_sqft * 144.0 * 2.4) / step) * step)
    w = w_lo
    while w <= max_w + 1e-6:
        ideal_d = (clamped_target * 144.0) / w
        for mul in (-1, 0, 1):
            d = max(d_lo, round(ideal_d / step) * step + mul * step)
            area = (w * d) / 144.0
            range_dist = 0.0
            if area < min_area_sqft:
                range_dist = min_area_sqft - area
            elif area > max_area_sqft:
                range_dist = area - max_area_sqft
            key = (range_dist, abs(area - clamped_target), w, d)
            if best_out is None or key < best_out:
                best_out = key
        w += step
    if best_out is not None:
        return (best_out[2], best_out[3])
    return (min_w_12, min_d_12)


def _solve_l_footprint(
    target_area_sqft: float,
    min_area_sqft: float,
    max_area_sqft: float,
    min_pub_w: float,
    min_wing_w: float,
    min_east_d: float,
    min_west_d: float,
    preferred_ratio: float = 1.65,
) -> Optional[tuple[float, float, float, float]]:
    """Solve L-shaped ``(pub_w, wing_w, d_east, d_west)`` inside ``[min_area_sqft, max_area_sqft]``."""
    clamped_target = max(min_area_sqft, min(max_area_sqft, target_area_sqft))
    for step in (12.0, 6.0):
        pw_lo = math.ceil(min_pub_w / step) * step
        ww_lo = math.ceil(min_wing_w / step) * step
        de_lo = math.ceil(min_east_d / step) * step
        best: Optional[tuple[float, float, float, float, float]] = None
        de = de_lo
        max_de = max(de_lo, math.ceil(math.sqrt(max_area_sqft * 144.0) / step) * step)
        while de <= max_de + 1e-6:
            dw_lo = max(math.ceil(min_west_d / step) * step, de + 96.0)
            if (pw_lo * dw_lo + ww_lo * de) / 144.0 > max_area_sqft + 1e-6:
                break
            tot_w = pw_lo + ww_lo
            max_w = max(tot_w, math.ceil((max_area_sqft * 144.0) / max(1.0, de) / step) * step)
            while tot_w <= max_w + 1e-6:
                extra_w = tot_w - (pw_lo + ww_lo)
                pw = pw_lo + math.floor((extra_w * 0.42) / step) * step
                ww = tot_w - pw
                ideal_dw = (clamped_target * 144.0 - ww * de) / max(1.0, pw)
                dw_cands = (
                    math.floor(ideal_dw / step) * step,
                    round(ideal_dw / step) * step,
                    math.ceil(ideal_dw / step) * step,
                    math.ceil((min_area_sqft * 144.0 - ww * de) / max(1.0, pw) / step) * step,
                    math.floor((max_area_sqft * 144.0 - ww * de) / max(1.0, pw) / step) * step,
                )
                for dwc in dw_cands:
                    dw = max(dw_lo, dwc)
                    area = (pw * dw + ww * de) / 144.0
                    if min_area_sqft - 1e-6 <= area <= max_area_sqft + 1e-6:
                        score = abs(area - clamped_target) / max(1.0, clamped_target)
                        score += 0.15 * abs((tot_w / max(1.0, dw)) - preferred_ratio)
                        if best is None or score < best[0]:
                            best = (score, pw, ww, de, dw)
                tot_w += step
            de += step
        if best is not None:
            return (best[1], best[2], best[3], best[4])
    return None


def _compute_single_story_dims(
    req: FloorPlanRequest,
    aspect_step: int = 0,
    target_sqft: Optional[float] = None,
    open_concept: bool = False,
) -> tuple[float, float, float, bool]:
    """Return ``(pub_w, wing_w, depth, compact_baths)`` in inches for a 1-story plan."""
    if target_sqft is None:
        target_sqft = 0.5 * (req.min_sqft + req.max_sqft)
    l1_full, l1_half, _, _ = _split_bath_counts(req.bathrooms, 1)
    pub_has_office = req.include_office and not open_concept
    wing_has_office = req.include_office and open_concept
    std_pub_w = 216.0 if (req.include_dining or pub_has_office) else 192.0
    std_wing_w = _min_wing_width(
        req.bedrooms, l1_full, l1_half, req.include_laundry,
        compact_baths=False, minimal_hall=open_concept, include_office=wing_has_office,
    )
    std_min_d = 384.0 if pub_has_office else (336.0 if req.include_dining else 300.0)
    use_compact = ((std_pub_w + std_wing_w) * std_min_d / 144.0) > req.max_sqft

    if use_compact:
        min_pub_w = 180.0 if (req.include_dining or pub_has_office) else 168.0
        min_wing_w = _min_wing_width(
            req.bedrooms, l1_full, l1_half, req.include_laundry,
            compact_baths=True, minimal_hall=open_concept, include_office=wing_has_office,
        )
        if req.include_dining and pub_has_office:
            min_d = 408.0
        elif pub_has_office:
            min_d = 336.0
        elif req.include_dining:
            min_d = 312.0
        else:
            min_d = 288.0
    else:
        min_pub_w = std_pub_w
        min_wing_w = std_wing_w
        min_d = std_min_d

    pref_ratio = 1.65 + 0.18 * aspect_step
    total_w, depth = _solve_rect_footprint(
        target_sqft,
        float(req.min_sqft),
        float(req.max_sqft),
        min_pub_w + min_wing_w,
        min_d,
        preferred_ratio=pref_ratio,
    )
    extra_w = max(0.0, total_w - (min_pub_w + min_wing_w))
    pub_add = round((extra_w * 0.42) / 6.0) * 6.0
    pub_w = min_pub_w + pub_add
    wing_w = total_w - pub_w
    return (pub_w, wing_w, depth, use_compact)


def _build_1story_plan(
    req: FloorPlanRequest,
    style: HomeStyleSpec,
    variant_idx: int,
    row_variation: int = 0,
    aspect_step: int = 0,
    target_sqft: Optional[float] = None,
) -> PlanCanvas:
    """Build one complete 1-story floor plan for ``variant_idx`` (0..3)."""
    canvas = PlanCanvas(north_angle=float((15 * (variant_idx + req.seed)) % 360))
    h = style.main_wall_height_in
    lvl1 = Level(
        id=canvas.new_id("level"), name="Level 1", elevation=0.0, height=h, floor_thickness=10.0
    )
    canvas.levels.append(lvl1)
    canvas.active_level_id = lvl1.id
    l1 = Layer(id=canvas.new_id("layer"), name="Level 1 - Main Floor", level_id=lvl1.id)
    canvas.layers.append(l1)
    canvas.active_layer_id = l1.id
    lid = l1.id

    if target_sqft is None:
        target_sqft = 0.5 * (req.min_sqft + req.max_sqft)
    open_concept = _is_open_concept(req, style)
    pub_has_office = req.include_office and not open_concept
    wing_has_office = req.include_office and open_concept
    pub_w, wing_w, depth, compact_baths = _compute_single_story_dims(
        req, aspect_step=aspect_step, target_sqft=target_sqft, open_concept=open_concept
    )
    l1_full, l1_half, _, _ = _split_bath_counts(req.bathrooms, 1)
    bed_specs = [("Primary Bedroom", True)] + [
        (f"Bedroom {i}", False) for i in range(2, req.bedrooms + 1)
    ]

    gw = _garage_width_in(req.garage_cars)
    total_w = pub_w + wing_w

    l_dims: Optional[tuple[float, float, float, float]] = None
    if variant_idx == 2:
        l_pub_min = 180.0 if (compact_baths and (req.include_dining or pub_has_office)) else (
            168.0 if compact_baths else (216.0 if (req.include_dining or pub_has_office) else 192.0)
        )
        l_wing_min = _min_wing_width(
            req.bedrooms, l1_full, l1_half, req.include_laundry,
            compact_baths=compact_baths, minimal_hall=open_concept, include_office=wing_has_office,
        )
        l_west_min = 408.0 if (req.include_dining and pub_has_office) else 384.0
        l_dims = _solve_l_footprint(
            target_sqft,
            float(req.min_sqft),
            float(req.max_sqft),
            l_pub_min,
            l_wing_min,
            288.0,
            l_west_min,
            preferred_ratio=1.65 + 0.18 * aspect_step,
        )

    if variant_idx == 2 and l_dims is not None:
        # Variant 2: L-Shaped Courtyard Wing (6 exterior walls)
        # Public wing extends South deeper than East bedroom wing
        pub_w, wing_w, d_east, d_west = l_dims
        total_w = pub_w + wing_w
        pub_side_garage = open_concept and gw > 0.0
        gy0_l = max(0.0, d_west - 240.0)
        w_n = _make_wall(canvas, (0.0, 0.0), (total_w, 0.0), _EXT_WALL_W, h, lid,
                         exterior=True, footer=True, ext_finish=style.exterior_finish)
        w_e = _make_wall(canvas, (total_w, 0.0), (total_w, d_east), _EXT_WALL_W, h, lid,
                         exterior=True, footer=True, ext_finish=style.exterior_finish)
        w_in_s = _make_wall(canvas, (total_w, d_east), (pub_w, d_east), _EXT_WALL_W, h, lid,
                            exterior=True, footer=True, ext_finish=style.exterior_finish)
        w_in_e = _make_wall(canvas, (pub_w, d_east), (pub_w, d_west), _EXT_WALL_W, h, lid,
                            exterior=True, footer=True, ext_finish=style.exterior_finish)
        w_s = _make_wall(canvas, (pub_w, d_west), (0.0, d_west), _EXT_WALL_W, h, lid,
                         exterior=True, footer=True, ext_finish=style.exterior_finish)
        if pub_side_garage and gy0_l > 0.5:
            w_w_gar = _make_wall(canvas, (0.0, d_west), (0.0, gy0_l), _EXT_WALL_W, h, lid,
                                 exterior=True, footer=True, ext_finish=style.exterior_finish)
            w_w_top = _make_wall(canvas, (0.0, gy0_l), (0.0, 0.0), _EXT_WALL_W, h, lid,
                                 exterior=True, footer=True, ext_finish=style.exterior_finish)
            west_walls = [w_w_gar, w_w_top]
            w_w = w_w_top
        else:
            w_w_gar = _make_wall(canvas, (0.0, d_west), (0.0, 0.0), _EXT_WALL_W, h, lid,
                                 exterior=True, footer=True, ext_finish=style.exterior_finish)
            west_walls = [w_w_gar]
            w_w = w_w_gar
        canvas.wall_sets.append([w_n, w_e, w_in_s, w_in_e, w_s] + west_walls)

        w_div = _make_wall(canvas, (pub_w, 0.0), (pub_w, d_east), _INT_WALL_W, h, lid)
        canvas.wall_sets.append([w_div])
        kit_d = 168.0 if d_west >= 420.0 else 132.0
        din_d = (120.0 if d_west >= 432.0 else 96.0) if req.include_dining else 0.0
        off_d = (120.0 if d_west >= 432.0 else 96.0) if pub_has_office else 0.0
        if d_west - kit_d - din_d - off_d < 96.0:
            kit_d = max(120.0, kit_d - 24.0)
        y_cur = kit_d + din_d
        if not open_concept:
            w_kd = _make_wall(canvas, (0.0, kit_d), (pub_w, kit_d), _INT_WALL_W, h, lid)
            canvas.wall_sets.append([w_kd])
            _add_door(canvas, w_kd, 0.5, "frame", 60.0, 80.0, lid)
            if req.include_dining:
                w_dl = _make_wall(canvas, (0.0, y_cur), (pub_w, y_cur), _INT_WALL_W, h, lid)
                canvas.wall_sets.append([w_dl])
                _add_door(canvas, w_dl, 0.5, "frame", 60.0, 80.0, lid)

        _add_room(
            canvas, "Kitchen", [(0.0, 0.0), (pub_w, 0.0), (pub_w, kit_d), (0.0, kit_d)],
            h, lid, "tile", style.kitchen_floor_pattern, "kitchen", is_slab=True,
        )
        if req.include_dining:
            _add_room(
                canvas, "Dining Room",
                [(0.0, kit_d), (pub_w, kit_d), (pub_w, y_cur), (0.0, y_cur)],
                h, lid, style.public_floor_type, style.public_floor_pattern, "dining", is_slab=True,
            )
        liv_end = d_west - off_d
        living_label = "Great Room" if open_concept else "Living Room"
        _add_room(
            canvas, living_label,
            [(0.0, y_cur), (pub_w, y_cur), (pub_w, liv_end), (0.0, liv_end)],
            h, lid, style.public_floor_type, style.public_floor_pattern, "living", is_slab=True,
        )
        if pub_has_office:
            w_off = _make_wall(canvas, (0.0, liv_end), (pub_w, liv_end), _INT_WALL_W, h, lid)
            canvas.wall_sets.append([w_off])
            _add_room(
                canvas, "Home Office",
                [(0.0, liv_end), (pub_w, liv_end), (pub_w, d_west), (0.0, d_west)],
                h, lid, style.public_floor_type, style.public_floor_pattern, "office", is_slab=True,
            )
            _add_door_to_room(
                canvas, w_off, pub_w * 0.3, "x", (pub_w * 0.5, d_west - 24.0),
                "double", 48.0, lid, swing="left",
            )

        # Front entry door on South wing wall or West wall, patio slider on East inner wall
        _add_door_to_room(
            canvas, w_s, pub_w * 0.65, "x", (pub_w * 0.65, d_west - 24.0),
            "single", style.front_entry_door_width_in, lid, swing="left",
        )
        patio_w = min(72.0, max(48.0, d_west - d_east - 24.0))
        _add_door(
            canvas, w_in_e, _ratio_along(w_in_e, 0.5 * (d_east + d_west), "y"),
            "sliding", patio_w, 80.0, lid,
        )
        if not pub_side_garage or gy0_l >= y_cur + 72.0:
            win_y = min(gy0_l - 36.0, 0.5 * (y_cur + liv_end)) if pub_side_garage else 0.5 * (
                y_cur + liv_end
            )
            _add_window(
                canvas, w_w, _ratio_along(w_w, win_y, "y"),
                style.primary_window_type, style.window_width_in, style.window_height_in, lid,
            )

        hall_y = _layout_bedroom_wing(
            canvas, lid, pub_w, 0.0, total_w, d_east, h, bed_specs, l1_full, l1_half,
            req.include_laundry, w_div, style, True, {"north": w_n, "south": w_in_s},
            row_variation=row_variation, compact_baths=compact_baths,
            minimal_hall=open_concept, entry_side="west",
            require_full_hall=(gw > 0.0 and not pub_side_garage),
            include_office=wing_has_office,
        )
        bz = _room_door_zones(canvas, lvl1.id)
        _furnish_kitchen(canvas, lid, (0.0, 0.0, pub_w, kit_d), w_n, style, bz)
        if req.include_dining:
            _furnish_dining(canvas, lid, (0.0, kit_d, pub_w, kit_d + din_d), bz)
        _furnish_living(canvas, lid, (0.0, y_cur, pub_w, liv_end), bz)
        if pub_has_office:
            _furnish_office(canvas, lid, (0.0, liv_end, pub_w, d_west), bz)

        if gw > 0.0:
            if pub_side_garage:
                _build_attached_garage(
                    canvas, lid, 0.0, gy0_l, d_west, gw, h, style,
                    w_w_gar, d_west - 48.0, req.garage_cars, is_2story=False, attach_on_west=True,
                )
            else:
                _build_attached_garage(
                    canvas, lid, total_w, max(0.0, d_east - 240.0), d_east, gw, h, style,
                    w_e, hall_y, req.garage_cars, is_2story=False,
                )

        _apply_style_roof(canvas, [w_n, w_in_s, w_in_e] + west_walls, [w_e, w_s], style, lid)
        sync_stair_holes(canvas)
        for fx in canvas.fixtures:
            resolve_fixture_surface(fx, canvas.rooms)
        return canvas

    # Rectangular variants (0: Classic Wing, 1: Split-Suite, 3: Front-Kitchen Open)
    pub_side_garage = open_concept and gw > 0.0
    gy0_rect = max(0.0, depth - 264.0)
    w_n = _make_wall(canvas, (0.0, 0.0), (total_w, 0.0), _EXT_WALL_W, h, lid,
                     exterior=True, footer=True, ext_finish=style.exterior_finish)
    w_s = _make_wall(canvas, (total_w, depth), (0.0, depth), _EXT_WALL_W, h, lid,
                     exterior=True, footer=True, ext_finish=style.exterior_finish)
    if pub_side_garage and variant_idx == 1 and gy0_rect > 0.5:
        w_e_top = _make_wall(canvas, (total_w, 0.0), (total_w, gy0_rect), _EXT_WALL_W, h, lid,
                             exterior=True, footer=True, ext_finish=style.exterior_finish)
        w_e_gar = _make_wall(canvas, (total_w, gy0_rect), (total_w, depth), _EXT_WALL_W, h, lid,
                             exterior=True, footer=True, ext_finish=style.exterior_finish)
        east_walls = [w_e_top, w_e_gar]
        w_e = w_e_top
    else:
        w_e_gar = _make_wall(canvas, (total_w, 0.0), (total_w, depth), _EXT_WALL_W, h, lid,
                             exterior=True, footer=True, ext_finish=style.exterior_finish)
        east_walls = [w_e_gar]
        w_e = w_e_gar
    if pub_side_garage and variant_idx != 1 and gy0_rect > 0.5:
        w_w_gar = _make_wall(canvas, (0.0, depth), (0.0, gy0_rect), _EXT_WALL_W, h, lid,
                             exterior=True, footer=True, ext_finish=style.exterior_finish)
        w_w_top = _make_wall(canvas, (0.0, gy0_rect), (0.0, 0.0), _EXT_WALL_W, h, lid,
                             exterior=True, footer=True, ext_finish=style.exterior_finish)
        west_walls = [w_w_gar, w_w_top]
        w_w = w_w_top
    else:
        w_w_gar = _make_wall(canvas, (0.0, depth), (0.0, 0.0), _EXT_WALL_W, h, lid,
                             exterior=True, footer=True, ext_finish=style.exterior_finish)
        west_walls = [w_w_gar]
        w_w = w_w_gar
    canvas.wall_sets.append([w_n] + east_walls + [w_s] + west_walls)

    # Public zone spans [0..pub_w] (for variants 0, 3) or [wing_w..total_w] (mirrored variant 1)
    if variant_idx == 1:
        # Mirrored: Private bedroom wing on West [0..wing_w], Public on East [wing_w..total_w]
        px0, px1 = wing_w, total_w
        bx0, bx1 = 0.0, wing_w
        w_div = _make_wall(canvas, (wing_w, 0.0), (wing_w, depth), _INT_WALL_W, h, lid)
        ext_pub = w_e
        gar_shared_wall = w_e_gar
    else:
        px0, px1 = 0.0, pub_w
        bx0, bx1 = pub_w, total_w
        w_div = _make_wall(canvas, (pub_w, 0.0), (pub_w, depth), _INT_WALL_W, h, lid)
        ext_pub = w_w
        gar_shared_wall = w_w_gar
    canvas.wall_sets.append([w_div])

    kit_d = 168.0 if depth >= 396.0 else (144.0 if depth >= 336.0 else 132.0)
    din_d = (108.0 if depth >= 360.0 else 96.0) if req.include_dining else 0.0
    off_d = (120.0 if depth >= 408.0 else 96.0) if pub_has_office else 0.0
    eff_din_d = din_d if variant_idx != 3 else 0.0
    if depth - kit_d - eff_din_d - off_d < 96.0:
        kit_d = max(120.0, kit_d - 24.0)
    if variant_idx == 3:
        # Front-Kitchen Open: Kitchen + Dining across North, full-depth Living along South
        liv_y0 = kit_d
        if not open_concept:
            w_kd = _make_wall(canvas, (px0, kit_d), (px1, kit_d), _INT_WALL_W, h, lid)
            canvas.wall_sets.append([w_kd])
            _add_door(canvas, w_kd, 0.5, "frame", 60.0, 80.0, lid)
    else:
        liv_y0 = kit_d + din_d
        if not open_concept:
            w_kd = _make_wall(canvas, (px0, kit_d), (px1, kit_d), _INT_WALL_W, h, lid)
            canvas.wall_sets.append([w_kd])
            _add_door(canvas, w_kd, 0.5, "frame", 60.0, 80.0, lid)
            if req.include_dining:
                w_dl = _make_wall(canvas, (px0, liv_y0), (px1, liv_y0), _INT_WALL_W, h, lid)
                canvas.wall_sets.append([w_dl])
                _add_door(canvas, w_dl, 0.5, "frame", 60.0, 80.0, lid)

    _add_room(
        canvas, "Kitchen", [(px0, 0.0), (px1, 0.0), (px1, kit_d), (px0, kit_d)],
        h, lid, "tile", style.kitchen_floor_pattern, "kitchen", is_slab=True,
    )
    if req.include_dining and variant_idx != 3:
        _add_room(
            canvas, "Dining Room",
            [(px0, kit_d), (px1, kit_d), (px1, liv_y0), (px0, liv_y0)],
            h, lid, style.public_floor_type, style.public_floor_pattern, "dining", is_slab=True,
        )
    liv_y1 = depth - off_d
    living_label = "Great Room" if open_concept else "Living Room"
    _add_room(
        canvas, living_label,
        [(px0, liv_y0), (px1, liv_y0), (px1, liv_y1), (px0, liv_y1)],
        h, lid, style.public_floor_type, style.public_floor_pattern, "living", is_slab=True,
    )
    if pub_has_office:
        w_off = _make_wall(canvas, (px0, liv_y1), (px1, liv_y1), _INT_WALL_W, h, lid)
        canvas.wall_sets.append([w_off])
        _add_room(
            canvas, "Home Office",
            [(px0, liv_y1), (px1, liv_y1), (px1, depth), (px0, depth)],
            h, lid, style.public_floor_type, style.public_floor_pattern, "office", is_slab=True,
        )
        _add_door_to_room(
            canvas, w_off, (px0 + px1) / 2.0, "x", ((px0 + px1) / 2.0, depth - 24.0),
            "double", 48.0, lid, swing="left",
        )

    entry_x = px0 + (px1 - px0) * 0.25 if pub_has_office else (px0 + px1) / 2.0
    if not pub_has_office:
        _add_door_to_room(
            canvas, w_s, entry_x, "x", (entry_x, depth - 24.0),
            "single", style.front_entry_door_width_in, lid, swing="left",
        )
    else:
        _add_door_to_room(
            canvas, ext_pub, (liv_y0 + liv_y1) / 2.0, "y",
            ((px0 + px1) / 2.0, (liv_y0 + liv_y1) / 2.0),
            "single", style.front_entry_door_width_in, lid, swing="left",
        )

    if not pub_side_garage or gy0_rect >= liv_y0 + 72.0:
        win_y = min(gy0_rect - 36.0, liv_y0 + (liv_y1 - liv_y0) * 0.35) if pub_side_garage else (
            liv_y0 + (liv_y1 - liv_y0) * 0.35
        )
        _add_window(
            canvas, ext_pub, _ratio_along(ext_pub, win_y, "y"),
            style.primary_window_type, style.window_width_in, style.window_height_in, lid,
        )
    if pub_has_office or (px1 - px0) >= 216.0:
        win_s_x = (px0 + px1) * 0.5 if pub_has_office else px0 + (px1 - px0) * 0.78
        _add_window(
            canvas, w_s, _ratio_along(w_s, win_s_x, "x"),
            style.primary_window_type, style.window_width_in, style.window_height_in, lid,
        )

    hall_y = _layout_bedroom_wing(
        canvas, lid, bx0, 0.0, bx1, depth, h, bed_specs, l1_full, l1_half,
        req.include_laundry, w_div, style, True, {"north": w_n, "south": w_s},
        row_variation=row_variation, compact_baths=compact_baths,
        minimal_hall=open_concept,
        entry_side="east" if variant_idx == 1 else "west",
        require_full_hall=(gw > 0.0 and not pub_side_garage),
        include_office=wing_has_office,
    )

    bz = _room_door_zones(canvas, lvl1.id)
    _furnish_kitchen(canvas, lid, (px0, 0.0, px1, kit_d), w_n, style, bz)
    if req.include_dining and variant_idx != 3:
        _furnish_dining(canvas, lid, (px0, kit_d, px1, liv_y0), bz)
    _furnish_living(canvas, lid, (px0, liv_y0, px1, liv_y1), bz)
    if pub_has_office:
        _furnish_office(canvas, lid, (px0, liv_y1, px1, depth), bz)

    if gw > 0.0:
        if pub_side_garage:
            _build_attached_garage(
                canvas, lid, total_w if variant_idx == 1 else 0.0, gy0_rect, depth, gw, h, style,
                gar_shared_wall, depth - 48.0, req.garage_cars, is_2story=False,
                attach_on_west=(variant_idx != 1),
            )
        elif variant_idx == 1:
            _build_attached_garage(
                canvas, lid, 0.0, gy0_rect, depth, gw, h, style,
                w_w, hall_y, req.garage_cars, is_2story=False, attach_on_west=True,
            )
        else:
            _build_attached_garage(
                canvas, lid, total_w, gy0_rect, depth, gw, h, style,
                w_e, hall_y, req.garage_cars, is_2story=False,
            )

    _apply_style_roof(canvas, [w_n, w_s], east_walls + west_walls, style, lid)
    sync_stair_holes(canvas)
    for fx in canvas.fixtures:
        resolve_fixture_surface(fx, canvas.rooms)
    return canvas


def _build_2story_plan(
    req: FloorPlanRequest,
    style: HomeStyleSpec,
    variant_idx: int,
    row_variation: int = 0,
    aspect_step: int = 0,
    target_sqft: Optional[float] = None,
) -> PlanCanvas:
    """Build one complete 2-story floor plan with flush stairs, upper hall, and garage roof."""
    canvas = PlanCanvas(north_angle=float((20 * (variant_idx + req.seed)) % 360))
    h1 = style.main_wall_height_in
    h2 = style.upper_wall_height_in
    floor_t = 10.0

    lvl1 = Level(
        id=canvas.new_id("level"), name="Level 1", elevation=0.0, height=h1,
        floor_thickness=floor_t,
    )
    lvl2 = Level(
        id=canvas.new_id("level"), name="Level 2", elevation=h1 + floor_t, height=h2,
        floor_thickness=floor_t,
    )
    canvas.levels.extend([lvl1, lvl2])
    canvas.active_level_id = lvl1.id

    l1 = Layer(id=canvas.new_id("layer"), name="Level 1 - Main Floor", level_id=lvl1.id)
    l2 = Layer(id=canvas.new_id("layer"), name="Level 2 - Upper Floor", level_id=lvl2.id)
    canvas.layers.extend([l1, l2])
    canvas.active_layer_id = l1.id

    l1_full, l1_half, l2_full, l2_half = _split_bath_counts(req.bathrooms, 2)
    if target_sqft is None:
        target_sqft = 0.5 * (req.min_sqft + req.max_sqft)
    per_floor_sqft = target_sqft / 2.0

    up_full = max(1, l2_full)
    std_wing_all = max(
        _min_wing_width(req.bedrooms, up_full, l2_half, req.include_laundry, compact_baths=False),
        240.0 if req.include_dining else 216.0,
    )
    std_min_2story_sqft = 2.0 * (std_wing_all + 132.0) * 312.0 / 144.0
    compact_baths = std_min_2story_sqft > req.max_sqft
    stair_w = 108.0 if compact_baths else (120.0 if variant_idx == 1 else 132.0)
    min_main_d = (300.0 if req.include_office else 288.0) if compact_baths else 312.0
    min_pub_w = (204.0 if req.include_dining else 180.0) if compact_baths else (
        240.0 if req.include_dining else 216.0
    )

    prim_cand_w = 156.0 if compact_baths else 180.0
    prim_up_beds = max(1, req.bedrooms - 1)
    prim_wing_min = max(
        _min_wing_width(prim_up_beds, up_full, l2_half, req.include_laundry, compact_baths=compact_baths),
        min_pub_w,
    )
    min_prim_2story_sqft = 2.0 * (prim_wing_min + stair_w + prim_cand_w) * min_main_d / 144.0
    has_l1_primary = variant_idx == 1 and req.bedrooms >= 2 and min_prim_2story_sqft <= req.max_sqft

    if has_l1_primary:
        prim_w = prim_cand_w
        min_wing_w = prim_wing_min
        pref_ratio = 1.55 + 0.15 * aspect_step
    else:
        prim_w = 0.0
        min_wing_w = max(
            _min_wing_width(req.bedrooms, up_full, l2_half, req.include_laundry, compact_baths=compact_baths),
            min_pub_w,
        )
        pref_ratio = 1.35 + 0.15 * aspect_step

    main_w, main_d = _solve_rect_footprint(
        per_floor_sqft,
        req.min_sqft / 2.0,
        req.max_sqft / 2.0,
        min_wing_w + stair_w + prim_w,
        min_main_d,
        preferred_ratio=pref_ratio,
    )
    wing_w = main_w - stair_w - prim_w

    gw = _garage_width_in(req.garage_cars)
    gy0 = max(0.0, main_d - 264.0)

    # --- LEVEL 1 ---
    w1_n = _make_wall(canvas, (0.0, 0.0), (main_w, 0.0), _EXT_WALL_W, h1, l1.id,
                      exterior=True, footer=True, ext_finish=style.exterior_finish)
    if gw > 0.0 and not has_l1_primary and gy0 > 0.5:
        w1_e_top = _make_wall(canvas, (main_w, 0.0), (main_w, gy0), _EXT_WALL_W, h1, l1.id,
                              exterior=True, footer=True, ext_finish=style.exterior_finish)
        w1_e = _make_wall(canvas, (main_w, gy0), (main_w, main_d), _EXT_WALL_W, h1, l1.id,
                          exterior=True, footer=True, ext_finish=style.exterior_finish)
        east_l1_walls = [w1_e_top, w1_e]
    else:
        w1_e = _make_wall(canvas, (main_w, 0.0), (main_w, main_d), _EXT_WALL_W, h1, l1.id,
                          exterior=True, footer=True, ext_finish=style.exterior_finish)
        east_l1_walls = [w1_e]
    w1_s = _make_wall(canvas, (main_w, main_d), (0.0, main_d), _EXT_WALL_W, h1, l1.id,
                      exterior=True, footer=True, ext_finish=style.exterior_finish)
    if gw > 0.0 and has_l1_primary and gy0 > 0.5:
        w1_w_gar = _make_wall(canvas, (0.0, main_d), (0.0, gy0), _EXT_WALL_W, h1, l1.id,
                              exterior=True, footer=True, ext_finish=style.exterior_finish)
        w1_w_top = _make_wall(canvas, (0.0, gy0), (0.0, 0.0), _EXT_WALL_W, h1, l1.id,
                              exterior=True, footer=True, ext_finish=style.exterior_finish)
        west_l1_walls = [w1_w_gar, w1_w_top]
        w1_w = w1_w_top
    else:
        w1_w_gar = _make_wall(canvas, (0.0, main_d), (0.0, 0.0), _EXT_WALL_W, h1, l1.id,
                              exterior=True, footer=True, ext_finish=style.exterior_finish)
        west_l1_walls = [w1_w_gar]
        w1_w = w1_w_gar
    canvas.wall_sets.append([w1_n] + east_l1_walls + [w1_s] + west_l1_walls)

    # Level 1 split: Public West [0..stair_x0], Stair/Foyer [stair_x0..stair_x1], Primary [stair_x1..main_w]
    stair_x0 = wing_w
    stair_x1 = wing_w + stair_w

    open_concept = _is_open_concept(req, style)
    kit_d = min(168.0, max(132.0, _snap12(main_d * 0.45)))
    din_w = _snap12(stair_x0 * 0.45) if req.include_dining else 0.0
    if din_w > 0.0:
        # Kitchen West [0..kx1], Dining East [kx1..stair_x0] so West cabinet leg sits on solid w1_w
        kx0, kx1 = 0.0, stair_x0 - din_w
        if kx1 < 132.0:
            kx1 = 132.0
        dx0, dx1 = kx1, stair_x0
        _add_room(
            canvas, "Dining Room", [(dx0, 0.0), (dx1, 0.0), (dx1, kit_d), (dx0, kit_d)],
            h1, l1.id, style.public_floor_type, style.public_floor_pattern, "dining", is_slab=True,
        )
        if not open_concept:
            w1_kd = _make_wall(canvas, (kx1, 0.0), (kx1, kit_d), _INT_WALL_W, h1, l1.id)
            canvas.wall_sets.append([w1_kd])
            _add_door(canvas, w1_kd, 0.5, "frame", 54.0, 80.0, l1.id)
    else:
        kx0, kx1 = 0.0, stair_x0
        dx0, dx1 = 0.0, 0.0

    if not open_concept:
        w1_kl = _make_wall(canvas, (0.0, kit_d), (stair_x0, kit_d), _INT_WALL_W, h1, l1.id)
        canvas.wall_sets.append([w1_kl])
        kl_open_x = kx1 * 0.5 if din_w > 0.0 else stair_x0 * 0.5
        _add_door(canvas, w1_kl, _ratio_along(w1_kl, kl_open_x, "x"), "frame", 60.0, 80.0, l1.id)

    _add_room(
        canvas, "Kitchen", [(kx0, 0.0), (kx1, 0.0), (kx1, kit_d), (kx0, kit_d)],
        h1, l1.id, "tile", style.kitchen_floor_pattern, "kitchen", is_slab=True,
    )

    # Stair column top enclosure (Half Bath / Office) when present
    extra_top_h = 0.0
    if l1_half > 0 or req.include_office:
        extra_top_h = 96.0 if req.include_office else 72.0

    if open_concept:
        # Minimal-hallway Open Concept: eliminate Foyer & Stair Hall wall/room so Great Room
        # flows openly into the front entry and staircase.
        if extra_top_h > 0.0:
            w1_pub_e = _make_wall(
                canvas, (stair_x0, 0.0), (stair_x0, extra_top_h), _INT_WALL_W, h1, l1.id
            )
            w1_hall_n = _make_wall(
                canvas, (stair_x0, extra_top_h), (stair_x1, extra_top_h), _INT_WALL_W, h1, l1.id
            )
            canvas.wall_sets.append([w1_pub_e, w1_hall_n])
        else:
            w1_hall_n = None
        if abs(extra_top_h - kit_d) < 1e-3:
            great_pts: List[Point] = [
                (0.0, kit_d), (stair_x1, kit_d), (stair_x1, main_d), (0.0, main_d)
            ]
        else:
            great_pts = [
                (0.0, kit_d), (stair_x0, kit_d), (stair_x0, extra_top_h),
                (stair_x1, extra_top_h), (stair_x1, main_d), (0.0, main_d),
            ]
        _add_room(
            canvas, "Great Room", great_pts, h1, l1.id,
            style.public_floor_type, style.public_floor_pattern, "living", is_slab=True,
        )
    else:
        w1_pub_e = _make_wall(canvas, (stair_x0, 0.0), (stair_x0, main_d), _INT_WALL_W, h1, l1.id)
        canvas.wall_sets.append([w1_pub_e])
        _add_room(
            canvas, "Living Room",
            [(0.0, kit_d), (stair_x0, kit_d), (stair_x0, main_d), (0.0, main_d)],
            h1, l1.id, style.public_floor_type, style.public_floor_pattern, "living", is_slab=True,
        )
        if extra_top_h > 0.0:
            w1_hall_n = _make_wall(
                canvas, (stair_x0, extra_top_h), (stair_x1, extra_top_h), _INT_WALL_W, h1, l1.id
            )
            canvas.wall_sets.append([w1_hall_n])
        else:
            w1_hall_n = None

    if extra_top_h > 0.0 and w1_hall_n is not None:
        top_label = "Home Office" if req.include_office else "Half Bath"
        top_type = "office" if req.include_office else "bathroom"
        top_pat = style.public_floor_pattern if req.include_office else style.bath_floor_pattern
        _add_room(
            canvas, top_label,
            [(stair_x0, 0.0), (stair_x1, 0.0), (stair_x1, extra_top_h), (stair_x0, extra_top_h)],
            h1, l1.id, style.public_floor_type, top_pat, top_type, is_slab=True,
        )
        if req.include_office:
            _add_door_to_room(
                canvas, w1_hall_n, (stair_x0 + stair_x1) / 2.0, "x",
                ((stair_x0 + stair_x1) / 2.0, 48.0), "single", 32.0, l1.id,
            )
            _add_window(
                canvas, w1_n, _ratio_along(w1_n, (stair_x0 + stair_x1) / 2.0, "x"),
                style.secondary_window_type, 36.0, 42.0, l1.id,
            )
        else:
            _add_door(
                canvas, w1_hall_n, 0.5, "pocket", 28.0, 80.0, l1.id, swing="left",
            )

    if not open_concept:
        _add_room(
            canvas,
            "Foyer & Stair Hall",
            [(stair_x0, extra_top_h), (stair_x1, extra_top_h), (stair_x1, main_d), (stair_x0, main_d)],
            h1, l1.id, style.public_floor_type, style.public_floor_pattern, "hallway", is_slab=True,
        )
        # Door linking Living -> Stair Hall
        _add_door(
            canvas, w1_pub_e, _ratio_along(w1_pub_e, main_d - 54.0, "y"),
            "frame", 60.0, 80.0, l1.id,
        )
    _add_door_to_room(
        canvas, w1_s, (stair_x0 + stair_x1) / 2.0, "x",
        ((stair_x0 + stair_x1) / 2.0, main_d - 24.0),
        "single", style.front_entry_door_width_in, l1.id, swing="left",
    )
    win_top_limit = gy0 if (gw > 0.0 and has_l1_primary) else main_d
    if win_top_limit - kit_d >= 72.0:
        win_y = min(win_top_limit - 36.0, kit_d + 72.0)
        _add_window(
            canvas, w1_w, _ratio_along(w1_w, win_y, "y"),
            style.primary_window_type, style.window_width_in, style.window_height_in, l1.id,
        )
    _add_window(
        canvas, w1_s, _ratio_along(w1_s, stair_x0 * 0.5, "x"),
        style.primary_window_type, style.window_width_in, style.window_height_in, l1.id,
    )

    # Main-level Primary Suite for Variant 1 when footprint allows
    if has_l1_primary:
        w1_prim_w = _make_wall(canvas, (stair_x1, 0.0), (stair_x1, main_d), _INT_WALL_W, h1, l1.id)
        pb_h = 96.0
        w1_pb_s = _make_wall(canvas, (stair_x1, pb_h), (main_w, pb_h), _INT_WALL_W, h1, l1.id)
        canvas.wall_sets.append([w1_prim_w, w1_pb_s])
        _add_room(
            canvas, "Primary Bath",
            [(stair_x1, 0.0), (main_w, 0.0), (main_w, pb_h), (stair_x1, pb_h)],
            h1, l1.id, "tile", style.bath_floor_pattern, "bathroom", is_slab=True,
        )
        _add_room(
            canvas, "Primary Bedroom",
            [(stair_x1, pb_h), (main_w, pb_h), (main_w, main_d), (stair_x1, main_d)],
            h1, l1.id, "carpet", style.bedroom_floor_pattern, "bedroom", is_slab=True,
        )
        _add_door_to_room(
            canvas, w1_prim_w, pb_h + 60.0, "y", (main_w - 40.0, pb_h + 60.0),
            "single", 32.0, l1.id, swing="left",
        )
        pb_door_x = stair_x1 + prim_w * 0.5
        _add_door_to_room(
            canvas, w1_pb_s, pb_door_x, "x", (pb_door_x, 48.0),
            "single", 30.0, l1.id, swing="left",
        )
        _add_window(
            canvas, w1_s, _ratio_along(w1_s, (stair_x1 + main_w) / 2.0, "x"),
            style.primary_window_type, style.window_width_in, style.window_height_in, l1.id,
        )

    # Staircase (U-shaped switchback inside [stair_x0..stair_x1, extra_top_h..main_d])
    total_rise = h1 + floor_t
    num_steps = max(14, math.ceil(total_rise / 7.75))
    sbl = num_steps // 2
    st_x = stair_x0 + 30.0
    st_y = main_d - 78.0
    stair = Stair(
        identifier=canvas.new_id("stair"),
        layer_id=l1.id,
        start_point=(st_x, st_y),
        direction_angle=-math.pi / 2.0,  # Ascend North (-Y), turn right (+X)
        start_level_id=lvl1.id,
        end_level_id=lvl2.id,
        stair_type="U-shaped",
        width=36.0,
        total_rise=total_rise,
        riser_height=total_rise / num_steps,
        num_steps=num_steps,
        steps_before_landing=sbl,
        tread_depth=10.0,
        total_run=(num_steps - 1) * 10.0,
        landing_depth=36.0,
        inner_radius=2.0,
        turn_direction="right",
        nosing=1.0,
        opening_clearance=2.0,
        has_left_rail=True,
        has_right_rail=True,
        rail_height=36.0,
    )
    canvas.stairs.append(stair)

    # Furnish Level 1
    bz1 = _room_door_zones(canvas, lvl1.id)
    _furnish_kitchen(canvas, l1.id, (kx0, 0.0, kx1, kit_d), w1_n, style, bz1)
    if din_w > 0.0:
        _furnish_dining(canvas, l1.id, (dx0, 0.0, dx1, kit_d), bz1)
    _furnish_living(canvas, l1.id, (0.0, kit_d, stair_x0, main_d), bz1)
    if extra_top_h > 0.0:
        if req.include_office:
            _furnish_office(canvas, l1.id, (stair_x0, 0.0, stair_x1, extra_top_h), bz1)
        else:
            _furnish_half_bath(canvas, l1.id, (stair_x0, 0.0, stair_x1, extra_top_h), bz1)
    if has_l1_primary:
        _furnish_full_bath(canvas, l1.id, (stair_x1, 0.0, main_w, 96.0), bz1)
        _furnish_bedroom(canvas, l1.id, (stair_x1, 96.0, main_w, main_d), True, bz1)

    if gw > 0.0:
        if has_l1_primary:
            _build_attached_garage(
                canvas, l1.id, 0.0, gy0, main_d, gw, h1, style,
                w1_w_gar, main_d - 42.0, req.garage_cars, is_2story=True, attach_on_west=True,
            )
        else:
            _build_attached_garage(
                canvas, l1.id, main_w, gy0, main_d, gw, h1, style,
                w1_e, main_d - 42.0, req.garage_cars, is_2story=True,
            )

    # --- LEVEL 2 ---
    w2_n = _make_wall(canvas, (0.0, 0.0), (main_w, 0.0), _EXT_WALL_W, h2, l2.id,
                      exterior=True, ext_finish=style.exterior_finish)
    w2_e = _make_wall(canvas, (main_w, 0.0), (main_w, main_d), _EXT_WALL_W, h2, l2.id,
                      exterior=True, ext_finish=style.exterior_finish)
    w2_s = _make_wall(canvas, (main_w, main_d), (0.0, main_d), _EXT_WALL_W, h2, l2.id,
                      exterior=True, ext_finish=style.exterior_finish)
    w2_w = _make_wall(canvas, (0.0, main_d), (0.0, 0.0), _EXT_WALL_W, h2, l2.id,
                      exterior=True, ext_finish=style.exterior_finish)
    canvas.wall_sets.append([w2_n, w2_e, w2_s, w2_w])

    # Upper Hall occupies [stair_x0..stair_x1], minimized in open-concept mode
    st_y_north = st_y - max(0, sbl - 1) * 10.0 - 36.0
    l2_hall_h = 42.0 if open_concept else 48.0
    hy0_l2 = max(108.0, min(main_d - 108.0 - l2_hall_h, _snap12((main_d - l2_hall_h) / 2.0)))
    n_cut = min(hy0_l2, math.floor((st_y_north - 14.0) / 12.0) * 12.0)

    east_alcove: Optional[tuple[float, float]] = None
    if has_l1_primary and open_concept:
        w2_hall_w = _make_wall(canvas, (stair_x0, 0.0), (stair_x0, main_d), _INT_WALL_W, h2, l2.id)
        canvas.wall_sets.append([w2_hall_w])
        _add_room(
            canvas, "Upper Loft",
            [(stair_x0, 0.0), (main_w, 0.0), (main_w, main_d), (stair_x0, main_d)],
            h2, l2.id, style.public_floor_type, style.public_floor_pattern, "living", is_slab=False,
        )
        _add_window(
            canvas, w2_e, 0.5, style.primary_window_type, style.window_width_in,
            style.window_height_in, l2.id,
        )
        _add_window(
            canvas, w2_s, _ratio_along(w2_s, (stair_x0 + stair_x1) / 2.0, "x"),
            style.secondary_window_type, 36.0, 42.0, l2.id,
        )
    elif open_concept and not has_l1_primary and n_cut >= 72.0:
        w2_hall_w = _make_wall(
            canvas, (stair_x0, n_cut), (stair_x0, main_d), _INT_WALL_W, h2, l2.id
        )
        w2_alc_s = _make_wall(
            canvas, (stair_x0, n_cut), (stair_x1, n_cut), _INT_WALL_W, h2, l2.id
        )
        canvas.wall_sets.append([w2_hall_w, w2_alc_s])
        _add_room(
            canvas, "Upper Hall",
            [(stair_x0, n_cut), (stair_x1, n_cut), (stair_x1, main_d), (stair_x0, main_d)],
            h2, l2.id, style.public_floor_type, style.public_floor_pattern, "hallway", is_slab=False,
        )
        _add_window(
            canvas, w2_s, _ratio_along(w2_s, (stair_x0 + stair_x1) / 2.0, "x"),
            style.secondary_window_type, 36.0, 42.0, l2.id,
        )
        east_alcove = (stair_x1, n_cut)
    else:
        w2_hall_w = _make_wall(canvas, (stair_x0, 0.0), (stair_x0, main_d), _INT_WALL_W, h2, l2.id)
        canvas.wall_sets.append([w2_hall_w])
        upper_pts: List[Point] = [
            (stair_x0, 0.0), (stair_x1, 0.0), (stair_x1, main_d), (stair_x0, main_d)
        ]
        if has_l1_primary:
            w2_hall_e = _make_wall(canvas, (stair_x1, 0.0), (stair_x1, main_d), _INT_WALL_W, h2, l2.id)
            canvas.wall_sets.append([w2_hall_e])
            _add_room(
                canvas, "Upper Loft",
                [(stair_x1, 0.0), (main_w, 0.0), (main_w, main_d), (stair_x1, main_d)],
                h2, l2.id, style.public_floor_type, style.public_floor_pattern, "living",
                is_slab=False,
            )
            _add_door(canvas, w2_hall_e, 0.5, "frame", 60.0, 80.0, l2.id)
            _add_window(
                canvas, w2_e, 0.5, style.primary_window_type, style.window_width_in,
                style.window_height_in, l2.id,
            )

        _add_room(
            canvas, "Upper Hall", upper_pts, h2, l2.id,
            style.public_floor_type, style.public_floor_pattern, "hallway", is_slab=False,
        )
        _add_window(
            canvas, w2_s, _ratio_along(w2_s, (stair_x0 + stair_x1) / 2.0, "x"),
            style.secondary_window_type, 36.0, 42.0, l2.id,
        )

    if has_l1_primary:
        up_beds = [(f"Bedroom {i}", False) for i in range(2, req.bedrooms + 1)]
        up_full = max(1, l2_full)
    else:
        up_beds = [("Primary Bedroom", True)] + [
            (f"Bedroom {i}", False) for i in range(2, req.bedrooms + 1)
        ]
        up_full = max(1, l2_full)

    _layout_bedroom_wing(
        canvas, l2.id, 0.0, 0.0, stair_x0, main_d, h2, up_beds, up_full, l2_half,
        req.include_laundry, w2_hall_w, style, False, {"north": w2_n, "south": w2_s},
        row_variation=row_variation, compact_baths=compact_baths,
        minimal_hall=open_concept, entry_side="east", require_full_hall=False,
        east_alcove=east_alcove,
    )

    sync_stair_holes(canvas)
    _apply_style_roof(canvas, [w2_n, w2_s], [w2_e, w2_w], style, l2.id)
    for fx in canvas.fixtures:
        resolve_fixture_surface(fx, canvas.rooms)
    return canvas


def _summarize_plan(
    plan_id: str,
    style: HomeStyleSpec,
    option_idx: int,
    req: FloorPlanRequest,
    canvas: PlanCanvas,
) -> GeneratedFloorPlan:
    living_sqft = sum(
        polygon_area(r.points) / 144.0
        for r in canvas.rooms
        if getattr(r, "room_type", "") != "garage"
    )
    garage_sqft = sum(
        polygon_area(r.points) / 144.0
        for r in canvas.rooms
        if getattr(r, "room_type", "") == "garage"
    )
    violations = validate_project_layout(canvas)
    variant_name = _VARIANT_NAMES[option_idx % len(_VARIANT_NAMES)]
    concept_label = "Open Concept" if _is_open_concept(req, style) else "Traditional"
    roof_summary = (
        f"{style.roof_pitch_rise}/12 {style.roof_type.title()} "
        f"({style.roof_material.replace('_', ' ').title()})"
    )
    summary = (
        f"{living_sqft:,.0f} sq ft • {concept_label} • {req.bedrooms} Bed • "
        f"{req.bathrooms:g} Bath • {req.levels}-Story • {req.garage_cars}-Car Garage"
    )
    return GeneratedFloorPlan(
        plan_id=plan_id,
        style_key=style.key,
        style_name=style.name,
        option_index=option_idx,
        variant_name=variant_name,
        summary=summary,
        living_sqft=living_sqft,
        garage_sqft=garage_sqft,
        bedrooms=req.bedrooms,
        bathrooms=req.bathrooms,
        levels=req.levels,
        garage_cars=req.garage_cars,
        roof_summary=roof_summary,
        layout_violations=violations,
        canvas=canvas,
    )


def generate_floor_plans(request: FloorPlanRequest) -> list[GeneratedFloorPlan]:
    """Generate capped multi-style, multi-option floor plans matching ``request``."""
    req = request.normalized()
    selected_styles = [get_style(k) for k in req.styles[:MAX_STYLES]]
    opts_per_style = min(req.options_per_style, MAX_OPTIONS_PER_STYLE)

    # Respect MAX_TOTAL_PLANS while keeping all selected styles represented
    total_requested = len(selected_styles) * opts_per_style
    if total_requested > MAX_TOTAL_PLANS:
        opts_per_style = max(1, MAX_TOTAL_PLANS // len(selected_styles))

    plans: list[GeneratedFloorPlan] = []
    for style in selected_styles:
        for o_idx in range(opts_per_style):
            if len(plans) >= MAX_TOTAL_PLANS:
                break
            variant_idx = (o_idx + (req.seed % len(_VARIANT_NAMES))) % len(_VARIANT_NAMES)
            row_var = (req.seed // 2 + o_idx) % 4
            aspect_step = ((req.seed + o_idx) % 3) - 1
            if opts_per_style > 1 and req.max_sqft > req.min_sqft:
                slot = (o_idx + (req.seed % opts_per_style)) % opts_per_style
                frac = 0.20 + 0.60 * (slot / (opts_per_style - 1))
                target_sqft = req.min_sqft + frac * (req.max_sqft - req.min_sqft)
            else:
                target_sqft = 0.5 * (req.min_sqft + req.max_sqft)
            if req.levels == 1:
                canvas = _build_1story_plan(
                    req,
                    style,
                    variant_idx,
                    row_variation=row_var,
                    aspect_step=aspect_step,
                    target_sqft=target_sqft,
                )
            else:
                canvas = _build_2story_plan(
                    req,
                    style,
                    variant_idx,
                    row_variation=row_var,
                    aspect_step=aspect_step,
                    target_sqft=target_sqft,
                )
            plan_id = f"{style.key}_opt{o_idx + 1}_s{req.seed}"
            plans.append(_summarize_plan(plan_id, style, variant_idx, req, canvas))
    return plans


def populate_canvas_from_plan(plan: GeneratedFloorPlan, target_canvas: object) -> None:
    """Copy a generated floor plan cleanly into an editable EstiSketch ``CanvasArea``."""
    src = plan.canvas
    if src is None:
        raise ValueError("GeneratedFloorPlan has no canvas data")

    reset_canvas_content(target_canvas)

    target_canvas.levels = copy.deepcopy(getattr(src, "levels", []))  # type: ignore[attr-defined]
    target_canvas.layers = copy.deepcopy(getattr(src, "layers", []))  # type: ignore[attr-defined]
    target_canvas.active_level_id = str(getattr(src, "active_level_id", ""))  # type: ignore[attr-defined]
    target_canvas.active_layer_id = str(getattr(src, "active_layer_id", ""))  # type: ignore[attr-defined]

    wall_map: dict[int, Wall] = {}
    new_wall_sets: list[list[Wall]] = []
    for ws in getattr(src, "wall_sets", []):
        copied_ws: list[Wall] = []
        for w in ws:
            cw = copy.deepcopy(w)
            wall_map[id(w)] = cw
            copied_ws.append(cw)
        new_wall_sets.append(copied_ws)
    target_canvas.wall_sets = new_wall_sets  # type: ignore[attr-defined]
    target_canvas.walls = [wall_map.get(id(w), copy.deepcopy(w)) for w in getattr(src, "walls", [])]  # type: ignore[attr-defined]

    target_canvas.rooms = copy.deepcopy(getattr(src, "rooms", []))  # type: ignore[attr-defined]
    target_canvas.doors = [
        (wall_map.get(id(w), copy.deepcopy(w)), copy.deepcopy(d), float(r))
        for w, d, r in getattr(src, "doors", [])
    ]  # type: ignore[attr-defined]
    target_canvas.windows = [
        (wall_map.get(id(w), copy.deepcopy(w)), copy.deepcopy(win), float(r))
        for w, win, r in getattr(src, "windows", [])
    ]  # type: ignore[attr-defined]
    target_canvas.texts = copy.deepcopy(getattr(src, "texts", []))  # type: ignore[attr-defined]
    target_canvas.stairs = copy.deepcopy(getattr(src, "stairs", []))  # type: ignore[attr-defined]
    target_canvas.fixtures = copy.deepcopy(getattr(src, "fixtures", []))  # type: ignore[attr-defined]
    target_canvas.roofs = copy.deepcopy(getattr(src, "roofs", []))  # type: ignore[attr-defined]
    target_canvas.north_angle = float(getattr(src, "north_angle", 0.0))  # type: ignore[attr-defined]
    target_canvas.existing_ids = list(getattr(src, "existing_ids", []))  # type: ignore[attr-defined]
    target_canvas.cut_lower_ceiling_under_stairs = bool(
        getattr(src, "cut_lower_ceiling_under_stairs", False)
    )  # type: ignore[attr-defined]
    if hasattr(target_canvas, "emit"):
        target_canvas.emit("content-changed")  # type: ignore[attr-defined]
