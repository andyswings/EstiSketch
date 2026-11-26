"""Headless snapshot/delta helpers for dragging multi-object canvas selections.

Captures original model coordinates (in inches) for heterogeneous unlocked items in
``selected_items``—deduplicating shared objects and avoiding double-moves on hosted
openings or vertices belonging to selected rooms/openings—so every drag update computes
``orig + (dx, dy)`` cleanly with zero cumulative drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Sequence

Point = tuple[float, float]


@dataclass
class MultiDragSnapshot:
    """Original positions of every unlocked item participating in a multi-object drag."""

    walls: list[tuple[Any, Point, Point, Point | None]] = field(default_factory=list)
    connected_wall_endpoints: list[tuple[Any, str, Point]] = field(default_factory=list)
    rooms: list[tuple[Any, list[Point]]] = field(default_factory=list)
    room_vertices: list[tuple[Any, int, Point]] = field(default_factory=list)
    floor_openings: list[tuple[Any, list[Point]]] = field(default_factory=list)
    opening_vertices: list[tuple[Any, int, Point]] = field(default_factory=list)
    fixtures: list[tuple[Any, float, float]] = field(default_factory=list)
    polylines: list[tuple[Any, Point, Point]] = field(default_factory=list)
    dimensions: list[tuple[Any, Point, Point]] = field(default_factory=list)
    dimension_chains: list[tuple[Any, list[Point]]] = field(default_factory=list)
    leader_callouts: list[tuple[Any, Point, Point, Point]] = field(default_factory=list)
    circles: list[tuple[Any, Point]] = field(default_factory=list)
    arcs: list[tuple[Any, Point]] = field(default_factory=list)
    stairs: list[tuple[Any, Point]] = field(default_factory=list)
    texts: list[tuple[Any, float, float]] = field(default_factory=list)
    floating_openings: list[tuple[Any, Point]] = field(default_factory=list)
    roofs: list[tuple[Any, dict[str, Any]]] = field(default_factory=list)
    roof_lines: list[tuple[Any, Point, Point, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Return True when no unlocked movable items were captured."""
        return not any((
            self.walls,
            self.rooms,
            self.room_vertices,
            self.floor_openings,
            self.opening_vertices,
            self.fixtures,
            self.polylines,
            self.dimensions,
            self.dimension_chains,
            self.leader_callouts,
            self.circles,
            self.arcs,
            self.stairs,
            self.texts,
            self.floating_openings,
            self.roofs,
            self.roof_lines,
        ))


def _pt_close(a: Point, b: Point, tol: float) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol


def _is_locked(canvas: Any, obj: Any) -> bool:
    checker = getattr(canvas, "is_object_on_locked_layer", None)
    if callable(checker):
        return bool(checker(obj))
    return bool(getattr(obj, "locked", False))


def _capture_roof_state(roof: Any) -> dict[str, Any]:
    return {
        "outline_points": [
            (float(p[0]), float(p[1])) for p in getattr(roof, "outline_points", [])
        ],
        "lists": {
            attr: [
                ((float(s[0]), float(s[1])), (float(e[0]), float(e[1])))
                for s, e in getattr(roof, attr, [])
            ]
            for attr in (
                "ridge_lines",
                "hip_lines",
                "valley_lines",
                "rake_lines",
                "eave_lines",
                "tie_in_lines",
            )
        },
        "lines": [
            (
                rl,
                (float(rl.start[0]), float(rl.start[1])),
                (float(rl.end[0]), float(rl.end[1])),
            )
            for attr in ("manual_lines", "solved_lines")
            for rl in getattr(roof, attr, [])
        ],
    }


def capture_multi_drag_snapshot(
    canvas: Any,
    selected_items: Sequence[dict[str, Any]],
    joint_tol: float = 0.25,
) -> MultiDragSnapshot:
    """Capture a deduplicated snapshot of all unlocked items in ``selected_items``."""
    snap = MultiDragSnapshot()
    seen_ids: set[int] = set()

    # Pass 1: identify whole rooms, floor openings, and roofs first so nested vertices
    # or roof lines belonging to them are never double-translated.
    whole_room_ids: set[int] = set()
    whole_opening_ids: set[int] = set()
    whole_roof_ids: set[int] = set()
    selected_wall_ids: set[int] = set()

    for it in selected_items:
        itype = it.get("type")
        obj = it.get("object")
        if obj is None:
            continue
        if itype == "room" and not _is_locked(canvas, obj):
            whole_room_ids.add(id(obj))
        elif itype == "floor_opening" and not _is_locked(canvas, obj):
            whole_opening_ids.add(id(obj))
        elif itype == "roof" and not _is_locked(canvas, obj):
            whole_roof_ids.add(id(obj))
        elif itype == "wall" and not _is_locked(canvas, obj):
            selected_wall_ids.add(id(obj))

    seen_room_verts: set[tuple[int, int]] = set()
    seen_op_verts: set[tuple[int, int]] = set()

    for it in selected_items:
        itype = it.get("type")
        obj = it.get("object")
        if obj is None:
            continue

        if itype == "vertex":
            room, idx = obj
            if _is_locked(canvas, room) or id(room) in whole_room_ids:
                continue
            key = (id(room), int(idx))
            if key not in seen_room_verts and 0 <= idx < len(room.points):
                seen_room_verts.add(key)
                px, py = room.points[idx]
                snap.room_vertices.append((room, int(idx), (float(px), float(py))))
            continue

        if itype == "opening_vertex":
            opening, idx = obj
            if _is_locked(canvas, opening) or id(opening) in whole_opening_ids:
                continue
            key = (id(opening), int(idx))
            if key not in seen_op_verts and 0 <= idx < len(opening.points):
                seen_op_verts.add(key)
                px, py = opening.points[idx]
                snap.opening_vertices.append((opening, int(idx), (float(px), float(py))))
            continue

        if itype in ("door", "window"):
            wall, op_obj, _ratio = obj
            # Wall-hosted doors/windows follow their host wall automatically via ratio.
            if wall is not None or _is_locked(canvas, op_obj):
                continue
            fpos = getattr(op_obj, "floating_pos", None)
            if fpos is not None and id(op_obj) not in seen_ids:
                seen_ids.add(id(op_obj))
                snap.floating_openings.append((op_obj, (float(fpos[0]), float(fpos[1]))))
            continue

        if id(obj) in seen_ids or _is_locked(canvas, obj):
            continue

        if itype == "roof_line":
            parent_roof = it.get("roof")
            if parent_roof is not None and id(parent_roof) in whole_roof_ids:
                continue
            seen_ids.add(id(obj))
            snap.roof_lines.append((
                obj,
                (float(obj.start[0]), float(obj.start[1])),
                (float(obj.end[0]), float(obj.end[1])),
                parent_roof,
            ))
            continue

        seen_ids.add(id(obj))
        if itype == "wall":
            ac = getattr(obj, "arc_center", None)
            orig_ac = (float(ac[0]), float(ac[1])) if ac is not None else None
            snap.walls.append((
                obj,
                (float(obj.start[0]), float(obj.start[1])),
                (float(obj.end[0]), float(obj.end[1])),
                orig_ac,
            ))
        elif itype == "room":
            snap.rooms.append((
                obj,
                [(float(p[0]), float(p[1])) for p in obj.points],
            ))
        elif itype == "floor_opening":
            snap.floor_openings.append((
                obj,
                [(float(p[0]), float(p[1])) for p in obj.points],
            ))
        elif itype == "fixture":
            snap.fixtures.append((obj, float(obj.x), float(obj.y)))
        elif itype == "polyline":
            snap.polylines.append((
                obj,
                (float(obj.start[0]), float(obj.start[1])),
                (float(obj.end[0]), float(obj.end[1])),
            ))
        elif itype == "dimension":
            snap.dimensions.append((
                obj,
                (float(obj.start[0]), float(obj.start[1])),
                (float(obj.end[0]), float(obj.end[1])),
            ))
        elif itype == "dimension_chain":
            snap.dimension_chains.append((
                obj,
                [(float(p[0]), float(p[1])) for p in obj.points],
            ))
        elif itype == "leader_callout":
            snap.leader_callouts.append((
                obj,
                (float(obj.tip[0]), float(obj.tip[1])),
                (float(obj.elbow[0]), float(obj.elbow[1])),
                (float(obj.shoulder[0]), float(obj.shoulder[1])),
            ))
        elif itype == "circle":
            snap.circles.append((obj, (float(obj.center[0]), float(obj.center[1]))))
        elif itype == "arc":
            snap.arcs.append((obj, (float(obj.center[0]), float(obj.center[1]))))
        elif itype == "stair":
            snap.stairs.append((obj, (float(obj.start_point[0]), float(obj.start_point[1]))))
        elif itype == "text":
            snap.texts.append((obj, float(obj.x), float(obj.y)))
        elif itype == "roof":
            snap.roofs.append((obj, _capture_roof_state(obj)))

    # Collect unselected unlocked wall endpoints touching any moved wall's endpoints so
    # adjoining walls rubber-band smoothly rather than tearing open wall corners.
    if snap.walls:
        moving_pts: list[Point] = []
        for _w, orig_s, orig_e, _orig_ac in snap.walls:
            moving_pts.append(orig_s)
            moving_pts.append(orig_e)

        seen_conn: set[tuple[int, str]] = set()
        all_wall_groups = list(getattr(canvas, "wall_sets", []))
        if getattr(canvas, "walls", None):
            all_wall_groups.append(canvas.walls)
        for wall_set in all_wall_groups:
            for other in wall_set:
                if id(other) in selected_wall_ids or _is_locked(canvas, other):
                    continue
                for ep_name in ("start", "end"):
                    pt = getattr(other, ep_name)
                    if any(_pt_close(pt, mp, joint_tol) for mp in moving_pts):
                        key = (id(other), ep_name)
                        if key not in seen_conn:
                            seen_conn.add(key)
                            snap.connected_wall_endpoints.append(
                                (other, ep_name, (float(pt[0]), float(pt[1])))
                            )

    return snap


def _needs_hole_sync(snapshot: MultiDragSnapshot) -> bool:
    """Return True if any stair, floor opening, or room geometry moved."""
    return any((
        snapshot.stairs,
        snapshot.floor_openings,
        snapshot.opening_vertices,
        snapshot.rooms,
        snapshot.room_vertices,
    ))


def apply_multi_drag_delta(
    canvas: Any,
    snapshot: MultiDragSnapshot,
    dx: float,
    dy: float,
) -> None:
    """Apply total offset ``(dx, dy)`` (inches) relative to ``snapshot``."""
    for wall, orig_s, orig_e, orig_ac in snapshot.walls:
        wall.start = (orig_s[0] + dx, orig_s[1] + dy)
        wall.end = (orig_e[0] + dx, orig_e[1] + dy)
        if orig_ac is not None and getattr(wall, "is_curved", False):
            wall.arc_center = (orig_ac[0] + dx, orig_ac[1] + dy)

    for wall, ep_name, orig_pt in snapshot.connected_wall_endpoints:
        setattr(wall, ep_name, (orig_pt[0] + dx, orig_pt[1] + dy))

    for room, orig_pts in snapshot.rooms:
        room.points = [(p[0] + dx, p[1] + dy) for p in orig_pts]

    for room, idx, orig_pt in snapshot.room_vertices:
        if 0 <= idx < len(room.points):
            room.points[idx] = (orig_pt[0] + dx, orig_pt[1] + dy)

    for opening, orig_pts in snapshot.floor_openings:
        opening.points = [(p[0] + dx, p[1] + dy) for p in orig_pts]

    for opening, idx, orig_pt in snapshot.opening_vertices:
        if 0 <= idx < len(opening.points):
            opening.points[idx] = (orig_pt[0] + dx, orig_pt[1] + dy)

    for poly, orig_s, orig_e in snapshot.polylines:
        poly.start = (orig_s[0] + dx, orig_s[1] + dy)
        poly.end = (orig_e[0] + dx, orig_e[1] + dy)

    for dim, orig_s, orig_e in snapshot.dimensions:
        dim.start = (orig_s[0] + dx, orig_s[1] + dy)
        dim.end = (orig_e[0] + dx, orig_e[1] + dy)

    for chain, orig_pts in snapshot.dimension_chains:
        chain.points = [(p[0] + dx, p[1] + dy) for p in orig_pts]

    for leader, orig_tip, orig_elbow, orig_shoulder in snapshot.leader_callouts:
        leader.tip = (orig_tip[0] + dx, orig_tip[1] + dy)
        leader.elbow = (orig_elbow[0] + dx, orig_elbow[1] + dy)
        leader.shoulder = (orig_shoulder[0] + dx, orig_shoulder[1] + dy)

    for circle, orig_center in snapshot.circles:
        circle.center = (orig_center[0] + dx, orig_center[1] + dy)

    for arc, orig_center in snapshot.arcs:
        arc.center = (orig_center[0] + dx, orig_center[1] + dy)

    for stair, orig_start in snapshot.stairs:
        stair.start_point = (orig_start[0] + dx, orig_start[1] + dy)

    for text, orig_x, orig_y in snapshot.texts:
        text.x = orig_x + dx
        text.y = orig_y + dy

    for op_obj, orig_pos in snapshot.floating_openings:
        op_obj.floating_pos = (orig_pos[0] + dx, orig_pos[1] + dy)

    for roof, state in snapshot.roofs:
        roof.outline_points = [
            (p[0] + dx, p[1] + dy) for p in state["outline_points"]
        ]
        for attr, orig_segs in state["lists"].items():
            setattr(
                roof,
                attr,
                [((s[0] + dx, s[1] + dy), (e[0] + dx, e[1] + dy)) for s, e in orig_segs],
            )
        for rl, orig_s, orig_e in state["lines"]:
            rl.start = (orig_s[0] + dx, orig_s[1] + dy)
            rl.end = (orig_e[0] + dx, orig_e[1] + dy)

    for rl, orig_s, orig_e, _parent_roof in snapshot.roof_lines:
        rl.start = (orig_s[0] + dx, orig_s[1] + dy)
        rl.end = (orig_e[0] + dx, orig_e[1] + dy)

    if snapshot.fixtures:
        moving_wall_ids = {id(w) for w, _, _, _ in snapshot.walls}
        get_walls = getattr(canvas, "_get_structural_visible_walls", None)
        stationary_walls: list[Any] = []
        if callable(get_walls):
            stationary_walls = [w for w in get_walls() if id(w) not in moving_wall_ids]
        rooms = getattr(canvas, "rooms", [])
        from ..fixtures_catalog import resolve_fixture_surface
        from ..geometry.design_checks import clamp_fixture_out_of_walls

        for fix, orig_x, orig_y in snapshot.fixtures:
            fix.x = orig_x + dx
            fix.y = orig_y + dy
            if stationary_walls and not getattr(fix, "is_upper", False):
                clamp_fixture_out_of_walls(fix, stationary_walls)
            resolve_fixture_surface(fix, rooms)

    if _needs_hole_sync(snapshot) and hasattr(canvas, "rooms") and hasattr(canvas, "stairs"):
        from ..geometry.room_holes import sync_stair_holes
        sync_stair_holes(canvas)


def finalize_multi_drag(canvas: Any, snapshot: MultiDragSnapshot) -> None:
    """Sync derived roof topology and room holes once after a multi-object drag."""
    moved_roof_ids = {id(r) for r, _ in snapshot.roofs}
    moved_wall_str_ids = {
        getattr(w, "identifier", "")
        for w, _, _, _ in snapshot.walls
        if getattr(w, "identifier", "")
    }
    moved_wall_str_ids.update(
        getattr(w, "identifier", "")
        for w, _, _ in snapshot.connected_wall_endpoints
        if getattr(w, "identifier", "")
    )
    if moved_wall_str_ids and hasattr(canvas, "recalculate_roof"):
        for roof in getattr(canvas, "roofs", []):
            edge_wids = {e.wall_identifier for e in getattr(roof, "edges", [])}
            if id(roof) in moved_roof_ids and edge_wids and edge_wids.issubset(moved_wall_str_ids):
                continue
            if edge_wids & moved_wall_str_ids:
                canvas.recalculate_roof(roof)

    if _needs_hole_sync(snapshot) and hasattr(canvas, "rooms") and hasattr(canvas, "stairs"):
        from ..geometry.room_holes import sync_stair_holes
        sync_stair_holes(canvas)
