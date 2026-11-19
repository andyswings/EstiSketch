"""Object management and ObjectGroup operations mixin for CanvasArea."""

import math
from typing import Any, Dict, List, Optional, Set, Tuple

from ..components import ObjectGroup


def _rotate_point(
    pt: Tuple[float, float],
    cx: float,
    cy: float,
    cos_a: float,
    sin_a: float,
) -> Tuple[float, float]:
    """Rotate point ``pt`` around ``(cx, cy)`` by angle with precomputed cos/sin."""
    dx = pt[0] - cx
    dy = pt[1] - cy
    return (
        cx + dx * cos_a - dy * sin_a,
        cy + dx * sin_a + dy * cos_a,
    )


class CanvasGroupMixin:
    """Provides unified object enumeration/management and ObjectGroup operations."""

    # ─────────────────────────────────────────────────────────────────────────
    # Unified Object Enumeration & Lookup
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_objects(self) -> List[Tuple[str, Any]]:
        """Return ``(type_name, obj)`` for every drawable object across all layers."""
        objects: List[Tuple[str, Any]] = []

        for wall_set in getattr(self, "wall_sets", []):
            for wall in wall_set:
                objects.append(("wall", wall))

        for room in getattr(self, "rooms", []):
            objects.append(("room", room))

        for item in getattr(self, "doors", []):
            objects.append(("door", item[1]))

        for item in getattr(self, "windows", []):
            objects.append(("window", item[1]))

        for text in getattr(self, "texts", []):
            objects.append(("text", text))

        for dim in getattr(self, "dimensions", []):
            objects.append(("dimension", dim))

        for chain in getattr(self, "dimension_chains", []):
            objects.append(("dimension_chain", chain))

        for callout in getattr(self, "leader_callouts", []):
            objects.append(("leader_callout", callout))

        for poly_set in getattr(self, "polyline_sets", []):
            for poly in poly_set:
                objects.append(("polyline", poly))

        for circle in getattr(self, "circles", []):
            objects.append(("circle", circle))

        for arc in getattr(self, "arcs", []):
            objects.append(("arc", arc))

        for roof in getattr(self, "roofs", []):
            objects.append(("roof", roof))

        for stair in getattr(self, "stairs", []):
            objects.append(("stair", stair))

        return objects

    def find_object_by_id(self, identifier: str) -> Optional[Tuple[str, Any]]:
        """Find a drawable ``(type_name, obj)`` by its unique ``identifier``."""
        if not identifier:
            return None
        for type_name, obj in self.get_all_objects():
            if getattr(obj, "identifier", "") == identifier:
                return (type_name, obj)
        return None

    def extract_selection_object(self, item: Dict[str, Any]) -> Optional[Tuple[str, Any]]:
        """Normalize a ``selected_items`` entry into ``(type_name, obj)``."""
        if not isinstance(item, dict):
            return None
        otype = item.get("type")
        obj = item.get("object")
        if obj is None or not otype:
            return None

        if otype in ("door", "window"):
            if isinstance(obj, tuple) and len(obj) >= 2:
                return (otype, obj[1])
            return (otype, obj)
        if otype == "vertex":
            if isinstance(obj, tuple) and len(obj) >= 1:
                return ("room", obj[0])
            return None
        if otype in ("wall_handle", "curved_wall_handle"):
            if isinstance(obj, tuple) and len(obj) >= 1:
                return ("wall", obj[0])
            return None
        if otype == "polyline_handle":
            if isinstance(obj, tuple) and len(obj) >= 1:
                return ("polyline", obj[0])
            return None
        if otype == "dimension_handle":
            if isinstance(obj, tuple) and len(obj) >= 1:
                return ("dimension", obj[0])
            return None
        if otype == "dimension_chain_handle":
            if isinstance(obj, tuple) and len(obj) >= 1:
                return ("dimension_chain", obj[0])
            return None
        if otype == "leader_handle":
            if isinstance(obj, tuple) and len(obj) >= 1:
                return ("leader_callout", obj[0])
            return None
        if otype == "arc_handle":
            if isinstance(obj, tuple) and len(obj) >= 1:
                return ("arc", obj[0])
            return None
        if otype in ("roof_line", "roof_line_handle"):
            roof = item.get("roof")
            if roof is not None:
                return ("roof", roof)
            return None
        return (otype, obj)

    def make_selection_item(self, type_name: str, obj: Any) -> Optional[Dict[str, Any]]:
        """Construct the canonical ``selected_items`` dict for ``(type_name, obj)``."""
        if type_name == "door":
            for door_tuple in getattr(self, "doors", []):
                if door_tuple[1] is obj or (
                    getattr(door_tuple[1], "identifier", "")
                    and getattr(door_tuple[1], "identifier", "") == getattr(obj, "identifier", "")
                ):
                    return {"type": "door", "object": door_tuple}
            return None
        if type_name == "window":
            for win_tuple in getattr(self, "windows", []):
                if win_tuple[1] is obj or (
                    getattr(win_tuple[1], "identifier", "")
                    and getattr(win_tuple[1], "identifier", "") == getattr(obj, "identifier", "")
                ):
                    return {"type": "window", "object": win_tuple}
            return None
        if type_name == "polyline":
            return {
                "type": "polyline",
                "object": obj,
                "identifier": getattr(obj, "identifier", ""),
            }
        return {"type": type_name, "object": obj}

    def _is_in_selected_items(self, obj: Any) -> bool:
        """Return True if ``obj`` is currently represented in ``self.selected_items``."""
        target_id = getattr(obj, "identifier", "")
        for item in getattr(self, "selected_items", []):
            extracted = self.extract_selection_object(item)
            if not extracted:
                continue
            _, sel_obj = extracted
            if sel_obj is obj:
                return True
            if target_id and getattr(sel_obj, "identifier", "") == target_id:
                return True
        return False

    def _remove_object_from_selection(self, obj: Any) -> bool:
        """Remove any selection entries referencing ``obj``. Returns True if changed."""
        target_id = getattr(obj, "identifier", "")
        new_sel = []
        changed = False
        for item in getattr(self, "selected_items", []):
            extracted = self.extract_selection_object(item)
            if extracted:
                _, sel_obj = extracted
                if sel_obj is obj or (target_id and getattr(sel_obj, "identifier", "") == target_id):
                    changed = True
                    continue
            new_sel.append(item)
        if changed:
            self.selected_items = new_sel
        return changed

    # ─────────────────────────────────────────────────────────────────────────
    # Single-Object Management (Delete, Move Layer / Level)
    # ─────────────────────────────────────────────────────────────────────────

    def _remove_single_object_from_storage(self, type_name: str, obj: Any) -> bool:
        """Remove ``obj`` from its underlying canvas collection without side effects."""
        obj_id = getattr(obj, "identifier", "")
        removed = False

        if type_name == "wall":
            for ws in list(self.wall_sets):
                for w in list(ws):
                    if w is obj or (obj_id and getattr(w, "identifier", "") == obj_id):
                        ws.remove(w)
                        removed = True
                if len(ws) == 0 and ws in self.wall_sets:
                    self.wall_sets.remove(ws)
            # Also remove doors/windows attached to this wall? Keep consistent with delete_selected
        elif type_name == "room":
            if obj in self.rooms:
                self.rooms.remove(obj)
                removed = True
        elif type_name == "door":
            for dt in list(self.doors):
                if dt[1] is obj or (obj_id and getattr(dt[1], "identifier", "") == obj_id):
                    self.doors.remove(dt)
                    removed = True
        elif type_name == "window":
            for wt in list(self.windows):
                if wt[1] is obj or (obj_id and getattr(wt[1], "identifier", "") == obj_id):
                    self.windows.remove(wt)
                    removed = True
        elif type_name == "text":
            if obj in self.texts:
                self.texts.remove(obj)
                removed = True
        elif type_name == "dimension":
            if obj in self.dimensions:
                self.dimensions.remove(obj)
                removed = True
        elif type_name == "dimension_chain":
            chains = getattr(self, "dimension_chains", [])
            if obj in chains:
                chains.remove(obj)
                removed = True
        elif type_name == "leader_callout":
            callouts = getattr(self, "leader_callouts", [])
            if obj in callouts:
                callouts.remove(obj)
                removed = True
        elif type_name == "polyline":
            for ps in list(self.polyline_sets):
                for pl in list(ps):
                    if pl is obj or (obj_id and getattr(pl, "identifier", "") == obj_id):
                        ps.remove(pl)
                        removed = True
                if len(ps) == 0 and ps in self.polyline_sets:
                    self.polyline_sets.remove(ps)
        elif type_name == "circle":
            if obj in self.circles:
                self.circles.remove(obj)
                removed = True
        elif type_name == "arc":
            if obj in self.arcs:
                self.arcs.remove(obj)
                removed = True
        elif type_name == "roof":
            if hasattr(self, "delete_roof") and obj in getattr(self, "roofs", []):
                self.delete_roof(obj)
                removed = True
            elif obj in getattr(self, "roofs", []):
                self.roofs.remove(obj)
                removed = True
        elif type_name == "stair":
            stairs = getattr(self, "stairs", [])
            if obj in stairs:
                stairs.remove(obj)
                removed = True

        return removed

    def delete_object(self, type_name: str, obj: Any, save_undo: bool = True) -> bool:
        """Delete a single object from the canvas, updating selection and groups."""
        if not self._remove_single_object_from_storage(type_name, obj):
            return False

        self._remove_object_from_selection(obj)
        self.prune_groups()

        if save_undo and hasattr(self, "save_state"):
            self.save_state()
        self.queue_draw()
        if hasattr(self, "emit"):
            self.emit("selection-changed", self.selected_items)
            self.emit("content-changed")
        return True

    def move_object_to_layer(
        self,
        obj: Any,
        layer_id: str,
        save_undo: bool = True,
    ) -> bool:
        """Move a single object to ``layer_id``."""
        target_layer = self.get_layer_by_id(layer_id)
        if target_layer is None:
            return False
        if not hasattr(obj, "layer_id"):
            return False

        obj.layer_id = layer_id

        # If moving to a layer that is not currently visible or is locked, deselect
        if hasattr(self, "deselect_non_visible_items"):
            self.deselect_non_visible_items()

        if save_undo and hasattr(self, "save_state"):
            self.save_state()
        self.queue_draw()
        if hasattr(self, "emit"):
            self.emit("content-changed")
        return True

    def _get_or_create_layer_for_level(self, level_id: str) -> Optional[str]:
        """Return the ID of the first layer on ``level_id`` (or global if ``level_id == ''``).

        Creates a new layer for ``level_id`` if none exists yet.
        """
        for layer in getattr(self, "layers", []):
            if getattr(layer, "level_id", "") == level_id:
                return layer.id

        # Find level name for a clear layer name
        level_name = "Global"
        if level_id:
            for lvl in getattr(self, "levels", []):
                if lvl.id == level_id:
                    level_name = lvl.name
                    break
        return self.add_layer(name=f"{level_name} - Layer", level_id=level_id)

    def move_object_to_level(
        self,
        obj: Any,
        level_id: str,
        save_undo: bool = True,
    ) -> bool:
        """Move an object to a layer belonging to ``level_id`` (or global if ``''``)."""
        if level_id and not any(lvl.id == level_id for lvl in getattr(self, "levels", [])):
            return False

        target_layer_id = self._get_or_create_layer_for_level(level_id)
        if not target_layer_id:
            return False

        # If it's a Stair, keep start_level_id in sync when moving to a concrete level
        if level_id and hasattr(obj, "start_level_id"):
            obj.start_level_id = level_id

        return self.move_object_to_layer(obj, target_layer_id, save_undo=save_undo)

    def get_level_for_layer_id(self, layer_id: str):
        """Return the Level object for a layer_id, or None if global/unknown."""
        layer = self.get_layer_by_id(layer_id)
        if not layer or not getattr(layer, "level_id", ""):
            return None
        for lvl in getattr(self, "levels", []):
            if lvl.id == layer.level_id:
                return lvl
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # ObjectGroup CRUD & Lookup
    # ─────────────────────────────────────────────────────────────────────────

    def get_group_by_id(self, group_id: str) -> Optional[ObjectGroup]:
        """Return the ``ObjectGroup`` with ``group_id``, or None."""
        for g in getattr(self, "groups", []):
            if g.identifier == group_id:
                return g
        return None

    def get_group_for_object(self, obj_or_id: Any) -> Optional[ObjectGroup]:
        """Return the ``ObjectGroup`` containing ``obj_or_id``, or None."""
        ident = obj_or_id if isinstance(obj_or_id, str) else getattr(obj_or_id, "identifier", "")
        if not ident:
            return None
        for group in getattr(self, "groups", []):
            if ident in group.member_ids:
                return group
        return None

    def get_group_for_selection_item(self, item: Dict[str, Any]) -> Optional[ObjectGroup]:
        """Return the ``ObjectGroup`` for a ``selected_items`` entry, or None."""
        extracted = self.extract_selection_object(item)
        if not extracted:
            return None
        return self.get_group_for_object(extracted[1])

    def get_selected_groups(self) -> List[ObjectGroup]:
        """Return all distinct ``ObjectGroup`` instances represented in ``selected_items``."""
        seen: Set[str] = set()
        result: List[ObjectGroup] = []
        for item in getattr(self, "selected_items", []):
            g = self.get_group_for_selection_item(item)
            if g and g.identifier not in seen:
                seen.add(g.identifier)
                result.append(g)
        return result

    def get_group_members(self, group: ObjectGroup) -> List[Tuple[str, Any]]:
        """Resolve ``group.member_ids`` into live ``(type_name, obj)`` pairs."""
        id_set = set(group.member_ids)
        if not id_set:
            return []
        found: Dict[str, Tuple[str, Any]] = {}
        for type_name, obj in self.get_all_objects():
            ident = getattr(obj, "identifier", "")
            if ident in id_set:
                found[ident] = (type_name, obj)
        # Preserve member_ids order
        return [found[mid] for mid in group.member_ids if mid in found]

    def prune_groups(self) -> None:
        """Remove missing member IDs from groups and drop empty groups."""
        live_ids = {
            getattr(obj, "identifier", "")
            for _, obj in self.get_all_objects()
            if getattr(obj, "identifier", "")
        }
        kept: List[ObjectGroup] = []
        for g in getattr(self, "groups", []):
            g.member_ids = [mid for mid in g.member_ids if mid in live_ids]
            if len(g.member_ids) > 0:
                kept.append(g)
        self.groups = kept

    def group_selected(self, name: str = "") -> Optional[ObjectGroup]:
        """Group the currently selected objects into a new ``ObjectGroup``.

        Requires at least 2 distinct objects. Returns the created group or None.
        """
        member_ids: List[str] = []
        member_objs: List[Tuple[str, Any]] = []
        seen: Set[str] = set()

        for item in getattr(self, "selected_items", []):
            extracted = self.extract_selection_object(item)
            if not extracted:
                continue
            otype, obj = extracted
            ident = getattr(obj, "identifier", "")
            if not ident or ident in seen:
                continue
            seen.add(ident)
            member_ids.append(ident)
            member_objs.append((otype, obj))

        if len(member_ids) < 2:
            return None

        # Remove these IDs from any existing groups (flat grouping)
        for existing in list(getattr(self, "groups", [])):
            existing.member_ids = [mid for mid in existing.member_ids if mid not in seen]
        self.groups = [g for g in getattr(self, "groups", []) if len(g.member_ids) > 0]

        existing_ids = list(getattr(self, "existing_ids", [])) + [
            g.identifier for g in getattr(self, "groups", [])
        ]
        group_id = self.generate_identifier("group", existing_ids)
        if hasattr(self, "existing_ids"):
            self.existing_ids.append(group_id)

        group_num = len(getattr(self, "groups", [])) + 1
        group_name = name.strip() if name else f"Group {group_num}"
        first_layer = getattr(member_objs[0][1], "layer_id", getattr(self, "active_layer_id", ""))

        group = ObjectGroup(
            identifier=group_id,
            name=group_name,
            member_ids=member_ids,
            layer_id=first_layer,
            visible=True,
            locked=False,
        )
        self.groups.append(group)

        # Normalize selection to all members of the new group
        self.select_group(group, extend=False, emit_signal=False)

        if hasattr(self, "save_state"):
            self.save_state()
        self.queue_draw()
        if hasattr(self, "emit"):
            self.emit("selection-changed", self.selected_items)
            self.emit("content-changed")
        return group

    def ungroup(self, group: ObjectGroup, save_undo: bool = True) -> bool:
        """Dissolve ``group``, leaving its member objects on the canvas."""
        if group not in getattr(self, "groups", []):
            return False
        self.groups.remove(group)
        if save_undo and hasattr(self, "save_state"):
            self.save_state()
        self.queue_draw()
        if hasattr(self, "emit"):
            self.emit("selection-changed", self.selected_items)
            self.emit("content-changed")
        return True

    def ungroup_selected(self) -> bool:
        """Dissolve all groups represented in ``self.selected_items``."""
        selected_groups = self.get_selected_groups()
        if not selected_groups:
            return False
        for g in selected_groups:
            if g in self.groups:
                self.groups.remove(g)
        if hasattr(self, "save_state"):
            self.save_state()
        self.queue_draw()
        if hasattr(self, "emit"):
            self.emit("selection-changed", self.selected_items)
            self.emit("content-changed")
        return True

    def select_group(
        self,
        group: ObjectGroup,
        extend: bool = False,
        emit_signal: bool = True,
    ) -> None:
        """Select all visible, unlocked members of ``group``."""
        if not extend:
            self.selected_items = []
        if group.locked or not group.visible:
            if emit_signal and hasattr(self, "emit"):
                self.emit("selection-changed", self.selected_items)
            self.queue_draw()
            return

        for type_name, obj in self.get_group_members(group):
            if self.is_object_on_locked_layer(obj) or not self.is_object_on_visible_layer(obj):
                continue
            if self._is_in_selected_items(obj):
                continue
            sel_item = self.make_selection_item(type_name, obj)
            if sel_item is not None:
                self.selected_items.append(sel_item)

        if emit_signal and hasattr(self, "emit"):
            self.emit("selection-changed", self.selected_items)
        self.queue_draw()

    def deselect_group(self, group: ObjectGroup, emit_signal: bool = True) -> None:
        """Remove all members of ``group`` from ``self.selected_items``."""
        changed = False
        for _, obj in self.get_group_members(group):
            if self._remove_object_from_selection(obj):
                changed = True
        if changed and emit_signal and hasattr(self, "emit"):
            self.emit("selection-changed", self.selected_items)
        if changed:
            self.queue_draw()

    def set_group_locked(
        self,
        group: ObjectGroup,
        locked: bool,
        save_undo: bool = True,
    ) -> None:
        """Lock or unlock ``group`` and all of its member objects."""
        group.locked = bool(locked)
        for _, obj in self.get_group_members(group):
            if hasattr(obj, "locked"):
                obj.locked = bool(locked)
        if locked:
            self.deselect_group(group, emit_signal=True)
        if save_undo and hasattr(self, "save_state"):
            self.save_state()
        self.queue_draw()
        if hasattr(self, "emit"):
            self.emit("content-changed")

    def set_group_visible(
        self,
        group: ObjectGroup,
        visible: bool,
        save_undo: bool = True,
    ) -> None:
        """Show or hide ``group`` and all of its member objects."""
        group.visible = bool(visible)
        for _, obj in self.get_group_members(group):
            if hasattr(obj, "visible"):
                obj.visible = bool(visible)
        if not visible:
            self.deselect_group(group, emit_signal=True)
        if save_undo and hasattr(self, "save_state"):
            self.save_state()
        self.queue_draw()
        if hasattr(self, "emit"):
            self.emit("content-changed")

    def delete_group(self, group: ObjectGroup, save_undo: bool = True) -> bool:
        """Delete all member objects of ``group`` and remove the group itself."""
        if group.locked:
            return False
        members = self.get_group_members(group)
        for type_name, obj in members:
            if getattr(obj, "locked", False):
                continue
            self._remove_single_object_from_storage(type_name, obj)
            self._remove_object_from_selection(obj)
        if group in self.groups:
            self.groups.remove(group)
        self.prune_groups()

        if save_undo and hasattr(self, "save_state"):
            self.save_state()
        self.queue_draw()
        if hasattr(self, "emit"):
            self.emit("selection-changed", self.selected_items)
            self.emit("content-changed")
        return True

    def move_group_to_layer(
        self,
        group: ObjectGroup,
        layer_id: str,
        save_undo: bool = True,
    ) -> bool:
        """Move ``group`` and all of its members to ``layer_id``."""
        if self.get_layer_by_id(layer_id) is None:
            return False
        group.layer_id = layer_id
        for _, obj in self.get_group_members(group):
            if hasattr(obj, "layer_id"):
                obj.layer_id = layer_id
        if hasattr(self, "deselect_non_visible_items"):
            self.deselect_non_visible_items()
        if save_undo and hasattr(self, "save_state"):
            self.save_state()
        self.queue_draw()
        if hasattr(self, "emit"):
            self.emit("content-changed")
        return True

    def move_group_to_level(
        self,
        group: ObjectGroup,
        level_id: str,
        save_undo: bool = True,
    ) -> bool:
        """Move ``group`` and all of its members to a layer on ``level_id``."""
        if level_id and not any(lvl.id == level_id for lvl in getattr(self, "levels", [])):
            return False
        target_layer_id = self._get_or_create_layer_for_level(level_id)
        if not target_layer_id:
            return False
        for _, obj in self.get_group_members(group):
            if level_id and hasattr(obj, "start_level_id"):
                obj.start_level_id = level_id
        return self.move_group_to_layer(group, target_layer_id, save_undo=save_undo)

    # ─────────────────────────────────────────────────────────────────────────
    # Bounds & Unit Transformations (Move & Rotate)
    # ─────────────────────────────────────────────────────────────────────────

    def get_object_bounds(
        self,
        type_name: str,
        obj: Any,
    ) -> Optional[Tuple[float, float, float, float]]:
        """Return ``(min_x, min_y, max_x, max_y)`` in model inches for an object."""
        pts: List[Tuple[float, float]] = []

        if type_name == "wall":
            pts.extend([obj.start, obj.end])
            if getattr(obj, "is_curved", False) and getattr(obj, "arc_center", None) and getattr(obj, "arc_radius", None):
                cx, cy = obj.arc_center
                r = obj.arc_radius
                sa = math.atan2(obj.start[1] - cy, obj.start[0] - cx)
                ea = math.atan2(obj.end[1] - cy, obj.end[0] - cx)
                diff = ea - sa
                while diff > math.pi:
                    diff -= 2 * math.pi
                while diff < -math.pi:
                    diff += 2 * math.pi
                mid_a = sa + diff / 2.0
                pts.append((cx + r * math.cos(mid_a), cy + r * math.sin(mid_a)))
        elif type_name == "room":
            pts.extend(getattr(obj, "points", []))
        elif type_name == "polyline":
            pts.extend([obj.start, obj.end])
        elif type_name in ("door", "window"):
            collection = self.doors if type_name == "door" else self.windows
            for wall, o, ratio in collection:
                if o is obj:
                    if wall is not None:
                        px = wall.start[0] + ratio * (wall.end[0] - wall.start[0])
                        py = wall.start[1] + ratio * (wall.end[1] - wall.start[1])
                        half = getattr(obj, "width", 36.0) / 2.0
                        return (px - half, py - half, px + half, py + half)
                    elif getattr(obj, "floating_pos", None):
                        px, py = obj.floating_pos
                        half = getattr(obj, "width", 36.0) / 2.0
                        return (px - half, py - half, px + half, py + half)
                    break
        elif type_name == "text":
            x, y = obj.x, obj.y
            w = getattr(obj, "width", 50.0)
            h = getattr(obj, "height", 20.0)
            pts.extend([(x, y), (x + w, y + h)])
        elif type_name == "dimension":
            pts.extend([obj.start, obj.end])
        elif type_name == "dimension_chain":
            pts.extend(getattr(obj, "points", []))
        elif type_name == "leader_callout":
            pts.extend([obj.tip, obj.elbow, obj.shoulder])
        elif type_name == "circle":
            cx, cy = obj.center
            r = obj.radius
            return (cx - r, cy - r, cx + r, cy + r)
        elif type_name == "arc":
            cx, cy = obj.center
            r = obj.radius
            return (cx - r, cy - r, cx + r, cy + r)
        elif type_name == "stair":
            sx, sy = obj.start_point
            run = getattr(obj, "total_run", 120.0)
            w = getattr(obj, "width", 36.0)
            ang = getattr(obj, "direction_angle", 0.0)
            ca, sa = math.cos(ang), math.sin(ang)
            nx, ny = -sa, ca
            hw = w / 2.0
            pts.extend([
                (sx + nx * hw, sy + ny * hw),
                (sx - nx * hw, sy - ny * hw),
                (sx + ca * run + nx * hw, sy + sa * run + ny * hw),
                (sx + ca * run - nx * hw, sy + sa * run - ny * hw),
            ])
        elif type_name == "roof":
            pts.extend(getattr(obj, "outline_points", []))
            for attr in ("manual_lines", "solved_lines"):
                for rl in getattr(obj, attr, []):
                    pts.extend([rl.start, rl.end])
            for attr in ("ridge_lines", "hip_lines", "valley_lines", "rake_lines", "eave_lines", "tie_in_lines"):
                for s, e in getattr(obj, attr, []):
                    pts.extend([s, e])

        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def get_group_bounds(self, group: ObjectGroup) -> Optional[Tuple[float, float, float, float]]:
        """Return ``(min_x, min_y, max_x, max_y)`` enclosing all members of ``group``."""
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")
        found = False
        for type_name, obj in self.get_group_members(group):
            b = self.get_object_bounds(type_name, obj)
            if b is None:
                continue
            found = True
            min_x = min(min_x, b[0])
            min_y = min(min_y, b[1])
            max_x = max(max_x, b[2])
            max_y = max(max_y, b[3])
        if not found:
            return None
        return (min_x, min_y, max_x, max_y)

    def get_group_center(self, group: ObjectGroup) -> Optional[Tuple[float, float]]:
        """Return the center ``(cx, cy)`` of ``group``'s bounding box."""
        b = self.get_group_bounds(group)
        if b is None:
            return None
        return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)

    def get_group_rotation_handle_device(
        self,
        group: ObjectGroup,
    ) -> Optional[Tuple[float, float]]:
        """Return the device-space ``(x, y)`` of the rotation handle for ``group``."""
        b = self.get_group_bounds(group)
        if b is None:
            return None
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        T = self.zoom * pixels_per_inch
        cx_dev = ((b[0] + b[2]) / 2.0) * T + self.offset_x
        top_dev = b[1] * T + self.offset_y
        # 24 device pixels above the top edge of the group bounding box
        return (cx_dev, top_dev - 24.0)

    def translate_object(
        self,
        type_name: str,
        obj: Any,
        dx: float,
        dy: float,
        moving_wall_ids: Optional[Set[str]] = None,
    ) -> None:
        """Translate a single object in model inches by ``(dx, dy)``."""
        if type_name == "wall":
            obj.start = (obj.start[0] + dx, obj.start[1] + dy)
            obj.end = (obj.end[0] + dx, obj.end[1] + dy)
            if getattr(obj, "is_curved", False) and getattr(obj, "arc_center", None):
                obj.arc_center = (obj.arc_center[0] + dx, obj.arc_center[1] + dy)
        elif type_name == "room":
            obj.points = [(p[0] + dx, p[1] + dy) for p in obj.points]
        elif type_name == "polyline":
            obj.start = (obj.start[0] + dx, obj.start[1] + dy)
            obj.end = (obj.end[0] + dx, obj.end[1] + dy)
        elif type_name in ("door", "window"):
            # Doors/windows attached to a wall follow the wall automatically.
            if getattr(obj, "floating_pos", None) is not None:
                fx, fy = obj.floating_pos
                obj.floating_pos = (fx + dx, fy + dy)
        elif type_name == "text":
            obj.x += dx
            obj.y += dy
        elif type_name == "dimension":
            obj.start = (obj.start[0] + dx, obj.start[1] + dy)
            obj.end = (obj.end[0] + dx, obj.end[1] + dy)
        elif type_name == "dimension_chain":
            obj.points = [(p[0] + dx, p[1] + dy) for p in obj.points]
        elif type_name == "leader_callout":
            obj.tip = (obj.tip[0] + dx, obj.tip[1] + dy)
            obj.elbow = (obj.elbow[0] + dx, obj.elbow[1] + dy)
            obj.shoulder = (obj.shoulder[0] + dx, obj.shoulder[1] + dy)
        elif type_name == "circle":
            obj.center = (obj.center[0] + dx, obj.center[1] + dy)
        elif type_name == "arc":
            obj.center = (obj.center[0] + dx, obj.center[1] + dy)
        elif type_name == "stair":
            obj.start_point = (obj.start_point[0] + dx, obj.start_point[1] + dy)
        elif type_name == "roof":
            obj.outline_points = [(p[0] + dx, p[1] + dy) for p in getattr(obj, "outline_points", [])]
            for attr in ("ridge_lines", "hip_lines", "valley_lines", "rake_lines", "eave_lines", "tie_in_lines"):
                segs = getattr(obj, attr, [])
                setattr(
                    obj,
                    attr,
                    [((s[0] + dx, s[1] + dy), (e[0] + dx, e[1] + dy)) for s, e in segs],
                )
            for attr in ("manual_lines", "solved_lines"):
                for rl in getattr(obj, attr, []):
                    rl.start = (rl.start[0] + dx, rl.start[1] + dy)
                    rl.end = (rl.end[0] + dx, rl.end[1] + dy)

    def translate_group(
        self,
        group: ObjectGroup,
        dx: float,
        dy: float,
        save_undo: bool = False,
    ) -> bool:
        """Translate all members of ``group`` as a unit by ``(dx, dy)``."""
        if group.locked:
            return False
        members = self.get_group_members(group)
        if not members:
            return False
        # Do not move if any member is individually locked or on a locked layer
        for _, obj in members:
            if self.is_object_on_locked_layer(obj):
                return False

        moving_wall_ids = {
            getattr(obj, "identifier", "")
            for t, obj in members
            if t == "wall"
        }
        for type_name, obj in members:
            self.translate_object(type_name, obj, dx, dy, moving_wall_ids=moving_wall_ids)

        if save_undo and hasattr(self, "save_state"):
            self.save_state()
        self.queue_draw()
        return True

    def rotate_object(
        self,
        type_name: str,
        obj: Any,
        angle_deg: float,
        cx: float,
        cy: float,
        rotating_wall_ids: Optional[Set[str]] = None,
    ) -> None:
        """Rotate a single object around ``(cx, cy)`` by ``angle_deg`` degrees."""
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        if type_name == "wall":
            obj.start = _rotate_point(obj.start, cx, cy, cos_a, sin_a)
            obj.end = _rotate_point(obj.end, cx, cy, cos_a, sin_a)
            if getattr(obj, "is_curved", False) and getattr(obj, "arc_center", None):
                obj.arc_center = _rotate_point(obj.arc_center, cx, cy, cos_a, sin_a)
        elif type_name == "room":
            obj.points = [_rotate_point(p, cx, cy, cos_a, sin_a) for p in obj.points]
        elif type_name == "polyline":
            obj.start = _rotate_point(obj.start, cx, cy, cos_a, sin_a)
            obj.end = _rotate_point(obj.end, cx, cy, cos_a, sin_a)
        elif type_name in ("door", "window"):
            if getattr(obj, "floating_pos", None) is not None:
                obj.floating_pos = _rotate_point(obj.floating_pos, cx, cy, cos_a, sin_a)
        elif type_name == "text":
            rx, ry = _rotate_point((obj.x, obj.y), cx, cy, cos_a, sin_a)
            obj.x = rx
            obj.y = ry
            obj.rotation = (getattr(obj, "rotation", 0.0) + angle_deg) % 360.0
        elif type_name == "dimension":
            obj.start = _rotate_point(obj.start, cx, cy, cos_a, sin_a)
            obj.end = _rotate_point(obj.end, cx, cy, cos_a, sin_a)
        elif type_name == "dimension_chain":
            obj.points = [_rotate_point(p, cx, cy, cos_a, sin_a) for p in obj.points]
        elif type_name == "leader_callout":
            obj.tip = _rotate_point(obj.tip, cx, cy, cos_a, sin_a)
            obj.elbow = _rotate_point(obj.elbow, cx, cy, cos_a, sin_a)
            obj.shoulder = _rotate_point(obj.shoulder, cx, cy, cos_a, sin_a)
        elif type_name == "circle":
            obj.center = _rotate_point(obj.center, cx, cy, cos_a, sin_a)
        elif type_name == "arc":
            obj.center = _rotate_point(obj.center, cx, cy, cos_a, sin_a)
            obj.start_angle += angle_rad
            obj.end_angle += angle_rad
        elif type_name == "stair":
            obj.start_point = _rotate_point(obj.start_point, cx, cy, cos_a, sin_a)
            obj.direction_angle = getattr(obj, "direction_angle", 0.0) + angle_rad
        elif type_name == "roof":
            obj.outline_points = [
                _rotate_point(p, cx, cy, cos_a, sin_a)
                for p in getattr(obj, "outline_points", [])
            ]
            for attr in ("ridge_lines", "hip_lines", "valley_lines", "rake_lines", "eave_lines", "tie_in_lines"):
                segs = getattr(obj, attr, [])
                setattr(
                    obj,
                    attr,
                    [
                        (
                            _rotate_point(s, cx, cy, cos_a, sin_a),
                            _rotate_point(e, cx, cy, cos_a, sin_a),
                        )
                        for s, e in segs
                    ],
                )
            for attr in ("manual_lines", "solved_lines"):
                for rl in getattr(obj, attr, []):
                    rl.start = _rotate_point(rl.start, cx, cy, cos_a, sin_a)
                    rl.end = _rotate_point(rl.end, cx, cy, cos_a, sin_a)

    def rotate_group(
        self,
        group: ObjectGroup,
        angle_deg: float,
        pivot: Optional[Tuple[float, float]] = None,
        save_undo: bool = True,
    ) -> bool:
        """Rotate all members of ``group`` as a unit by ``angle_deg`` degrees."""
        if group.locked:
            return False
        members = self.get_group_members(group)
        if not members:
            return False
        for _, obj in members:
            if self.is_object_on_locked_layer(obj):
                return False

        if pivot is None:
            pivot = self.get_group_center(group)
        if pivot is None:
            return False

        cx, cy = pivot
        rotating_wall_ids = {
            getattr(obj, "identifier", "")
            for t, obj in members
            if t == "wall"
        }
        for type_name, obj in members:
            self.rotate_object(
                type_name, obj, angle_deg, cx, cy, rotating_wall_ids=rotating_wall_ids
            )

        if save_undo and hasattr(self, "save_state"):
            self.save_state()
        self.queue_draw()
        if save_undo and hasattr(self, "emit"):
            self.emit("content-changed")
        return True
