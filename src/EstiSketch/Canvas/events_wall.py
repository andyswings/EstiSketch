import math
from gi.repository import Gtk, GLib
from typing import List
from ..components import Wall
from ..Resources.tool_hints import TOOL_HINTS

from ..Dialogs.length_input_dialog import (
    create_length_input_dialog,
    create_near_foot_confirm_dialog,
)


class CanvasWallMixin:
    def _compute_wall_draw_snap(self, canvas_x: float, canvas_y: float, apply_near_foot_auto: bool = True):
        """Compute the snapped endpoint, snap_type, alignment_candidate, and near_foot_info for wall drawing."""
        last_wall = self.walls[-1] if self.walls else None
        alloc = self.get_allocation() if hasattr(self, "get_allocation") else None
        canvas_width = (alloc.width if alloc and alloc.width else 0) or getattr(self.config, "WINDOW_WIDTH", 1024)
        base_x, base_y = (
            (canvas_x, canvas_y) if not self.drawing_wall else self.current_wall.start
        )
        candidate_points = self._get_candidate_points()
        polylines = [
            pl for poly_set in getattr(self, "polyline_sets", []) for pl in poly_set
        ]

        (snapped_x, snapped_y), snap_type = self.snap_manager.snap_point(
            canvas_x, canvas_y, base_x, base_y, self._get_snap_walls(), self.rooms,
            current_wall=self.current_wall, last_wall=last_wall,
            in_progress_points=candidate_points, canvas_width=canvas_width,
            zoom=self.zoom, polylines=polylines,
            new_wall_width=self.config.DEFAULT_WALL_WIDTH
        )

        # First click (no active wall segment yet) or curve bulge point:
        if not self.drawing_wall or not self.current_wall or getattr(self, "wall_curve_mode", False):
            candidate = None
            if self.snap_manager.snap_enabled and snap_type not in (
                "endpoint", "midpoint", "wall_centerline", "face_flush", "wall_edge"
            ):
                aligned_x, aligned_y, candidate = self._apply_alignment_snapping(
                    snapped_x, snapped_y
                )
                if candidate is not None:
                    snapped_x, snapped_y = aligned_x, aligned_y
                    if snap_type in ("none", "grid", "distance"):
                        snap_type = "alignment"
            return (snapped_x, snapped_y), snap_type, candidate, None

        # Active wall segment from (base_x, base_y) -> (canvas_x, canvas_y):
        # 1. Hard geometric feature snaps define the exact point.
        if snap_type in ("endpoint", "midpoint", "wall_centerline", "wall_edge"):
            return (snapped_x, snapped_y), snap_type, None, None

        # 2. Face-flush snap fixes perpendicular offset; quantize distance along the wall.
        if snap_type == "face_flush":
            (qx, qy), _, near_foot_info = self.snap_manager.quantize_wall_length(
                base_x, base_y, snapped_x, snapped_y, apply_near_foot_auto=apply_near_foot_auto
            )
            return (qx, qy), snap_type, None, near_foot_info

        # 3. Check horizontal/vertical alignment with current wall start and parallel alignment with other endpoints.
        if not self.snap_manager.snap_enabled:
            return (canvas_x, canvas_y), "none", None, None

        align_tol = max(
            10.0 / (self.zoom or 1.0),
            float(getattr(self.snap_manager, "snap_threshold", 4.0) or 4.0),
        )

        other_pts = [
            pt for pt in candidate_points
            if math.hypot(pt[0] - base_x, pt[1] - base_y) > 1e-4
        ]
        for room in self.rooms:
            for pt in room.points:
                if math.hypot(pt[0] - base_x, pt[1] - base_y) > 1e-4:
                    other_pts.append(pt)
        for pl in polylines:
            for pt in (pl.start, pl.end):
                if math.hypot(pt[0] - base_x, pt[1] - base_y) > 1e-4:
                    other_pts.append(pt)

        cand_x_pt = None
        min_dx = align_tol
        for pt in other_pts:
            if abs(pt[0] - base_x) <= 1e-4:
                continue
            d = abs(pt[0] - canvas_x)
            if d < min_dx:
                min_dx = d
                cand_x_pt = pt

        cand_y_pt = None
        min_dy = align_tol
        for pt in other_pts:
            if abs(pt[1] - base_y) <= 1e-4:
                continue
            d = abs(pt[1] - canvas_y)
            if d < min_dy:
                min_dy = d
                cand_y_pt = pt

        is_horiz = (
            abs(canvas_y - base_y) <= align_tol
            or (snap_type in ("angle", "axis", "perpendicular") and abs(snapped_y - base_y) < 1e-5)
        )
        is_vert = (
            abs(canvas_x - base_x) <= align_tol
            or (snap_type in ("angle", "axis", "perpendicular") and abs(snapped_x - base_x) < 1e-5)
        )

        # If both horizontal and vertical within tolerance (very close to start), pick dominant axis
        if is_horiz and is_vert:
            if abs(canvas_x - base_x) >= abs(canvas_y - base_y):
                is_vert = False
            else:
                is_horiz = False

        if is_horiz:
            if cand_x_pt is not None:
                return (cand_x_pt[0], base_y), "alignment", cand_x_pt, None
            (qx, qy), _, near_foot_info = self.snap_manager.quantize_wall_length(
                base_x, base_y, canvas_x, base_y, apply_near_foot_auto=apply_near_foot_auto
            )
            out_type = snap_type if snap_type in ("axis", "perpendicular", "angle") else "axis"
            return (qx, qy), out_type, None, near_foot_info

        if is_vert:
            if cand_y_pt is not None:
                return (base_x, cand_y_pt[1]), "alignment", cand_y_pt, None
            (qx, qy), _, near_foot_info = self.snap_manager.quantize_wall_length(
                base_x, base_y, base_x, canvas_y, apply_near_foot_auto=apply_near_foot_auto
            )
            out_type = snap_type if snap_type in ("axis", "perpendicular", "angle") else "axis"
            return (qx, qy), out_type, None, near_foot_info

        # Non-orthogonal (angled) wall: check parallel endpoint alignment first
        if cand_x_pt is not None or cand_y_pt is not None:
            if snap_type in ("angle", "perpendicular"):
                dx = snapped_x - base_x
                dy = snapped_y - base_y
                dlen = math.hypot(dx, dy)
                if dlen > 1e-6:
                    ux, uy = dx / dlen, dy / dlen
                    if cand_x_pt is not None and abs(ux) > 0.2:
                        L = (cand_x_pt[0] - base_x) / ux
                        if L > 0:
                            ix, iy = cand_x_pt[0], base_y + L * uy
                            if abs(iy - canvas_y) <= align_tol:
                                return (ix, iy), "alignment", cand_x_pt, None
                    if cand_y_pt is not None and abs(uy) > 0.2:
                        L = (cand_y_pt[1] - base_y) / uy
                        if L > 0:
                            ix, iy = base_x + L * ux, cand_y_pt[1]
                            if abs(ix - canvas_x) <= align_tol:
                                return (ix, iy), "alignment", cand_y_pt, None
            ax = cand_x_pt[0] if cand_x_pt is not None else canvas_x
            ay = cand_y_pt[1] if cand_y_pt is not None else canvas_y
            ref_pt = cand_x_pt if cand_x_pt is not None else cand_y_pt
            return (ax, ay), "alignment", ref_pt, None

        # 4. Quantize wall length (0.25" increments + near-foot auto-snap/prompt detection)
        (qx, qy), _, near_foot_info = self.snap_manager.quantize_wall_length(
            base_x, base_y, snapped_x, snapped_y, apply_near_foot_auto=apply_near_foot_auto
        )
        return (qx, qy), snap_type, None, near_foot_info

    def _handle_wall_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle click events for drawing walls on the canvas.

        This method is called when the user clicks while the wall drawing tool is active.
        On a single click, it starts or extends a wall segment, snapping and aligning the endpoint.
        Hold Ctrl after second click to create a curved wall (3-point arc).
        On a double click, it finalizes the wall chain, closes the wall set, and resets the drawing state.
        If not currently drawing, a double click inside a room will auto-create walls along the room's outline.

        Args:
            n_press (int): The number of presses (1 for single click, 2 for double click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x, canvas_y = self.device_to_model(x, y, pixels_per_inch)
        raw_point = (canvas_x, canvas_y)

        (snapped_x, snapped_y), self.snap_type, candidate, near_foot_info = (
            self._compute_wall_draw_snap(canvas_x, canvas_y, apply_near_foot_auto=True)
        )
        self.raw_current_end = raw_point
        self.alignment_candidate = candidate
        auto_snapped_msg = None

        if n_press == 1:
            self.auto_dimension_mode = False
            wall_instance = None
            
            # Check if we're in curve mode (waiting for 3rd point)
            if self.wall_curve_mode:
                # Third click: complete the curved wall
                if self.walls and len(self.walls) > 0:
                    last_wall = self.walls[-1]
                    bulge_point = (snapped_x, snapped_y)
                    
                    # Calculate arc from 3 points: start, end, bulge
                    geom = self.get_circle_from_3_points(
                        last_wall.start, last_wall.end, bulge_point
                    )
                    
                    if geom:
                        (arc_cx, arc_cy), arc_radius = geom
                        # Update the last wall to be curved
                        last_wall.is_curved = True
                        last_wall.arc_center = (arc_cx, arc_cy)
                        last_wall.arc_radius = arc_radius
                    pass
                    
                # Exit curve mode and continue normal wall drawing
                self.wall_curve_mode = False
                self.wall_curve_point = None
                # Continue from the END of the curved wall, not the bulge point
                self.current_wall.start = last_wall.end
                self.queue_draw()
                
            elif not self.drawing_wall:
                # First click: start wall
                self.drawing_wall = True
                self.current_wall = self.Wall(
                    (snapped_x, snapped_y), (snapped_x, snapped_y),
                    self.config.DEFAULT_WALL_WIDTH, self.config.DEFAULT_WALL_HEIGHT,
                    identifier=self.generate_identifier("wall", self.existing_ids),
                    layer_id=self.active_layer_id
                )
            else:
                # Second (or subsequent) click: create wall segment
                wall_instance = self.Wall(
                    self.current_wall.start,
                    (snapped_x, snapped_y),
                    self.config.DEFAULT_WALL_WIDTH,
                    self.config.DEFAULT_WALL_HEIGHT,
                    identifier=self.generate_identifier(
                        "wall",
                        self.existing_ids),
                    layer_id=self.active_layer_id)
                    
                self.existing_ids.append(wall_instance.identifier)
                self.walls.append(wall_instance)

                # Update angle
                dx = wall_instance.end[0] - wall_instance.start[0]
                dy = wall_instance.end[1] - wall_instance.start[1]
                self.last_wall_angle = math.atan2(dy, dx)

                self.current_wall.start = (snapped_x, snapped_y)
                if near_foot_info is not None:
                    target_ft = near_foot_info["nearest_foot"]
                    if near_foot_info.get("auto_applied"):
                        target_str = self.converter.format_measurement(target_ft, use_fraction=False)
                        auto_snapped_msg = f"Auto-snapped wall length to {target_str} — {TOOL_HINTS['draw_walls_active']}"
                    elif getattr(self.config, "WALL_NEAR_FOOT_BEHAVIOR", "auto") == "prompt":
                        self._prompt_near_foot_wall_fix(wall_instance, target_ft)
                self.queue_draw()

        elif n_press == 2:
            if self.drawing_wall and self.walls:
                # Removed save_state here - only save when wall set is
                # finalized
                self.current_wall.end = (snapped_x, snapped_y)
                if self.current_wall.start != self.current_wall.end:
                    duplicate = any(
                        w.start == self.current_wall.start and w.end == self.current_wall.end
                        for w in self.walls
                    )
                    if not duplicate:
                        if self.current_wall.identifier not in self.existing_ids:
                            self.existing_ids.append(
                                self.current_wall.identifier
                            )
                        self.walls.append(self.current_wall)
                        if near_foot_info is not None and not near_foot_info.get("auto_applied"):
                            if getattr(self.config, "WALL_NEAR_FOOT_BEHAVIOR", "auto") == "prompt":
                                self._prompt_near_foot_wall_fix(self.current_wall, near_foot_info["nearest_foot"])

                else:
                    self.wall_sets.append(self.walls.copy())
                    self.walls = []
                    self.current_wall = None
                    self.drawing_wall = False
                    self.snap_type = "none"
                    self.alignment_candidate = None
                    self.raw_current_end = None
                    self.save_state()  # Save after cleanup to avoid state duplication
                    self.emit('content-changed')
            else:
                # Double-click when NOT drawing walls: create walls from room
                test_point = (snapped_x, snapped_y)
                wall_created = False
                for room in self.rooms:
                    if len(room.points) < 3:
                        continue
                    if self._point_in_polygon(test_point, room.points):
                        pts = room.points if room.points[0] == room.points[-1] else room.points + [
                            room.points[0]]
                        new_wall_set = []
                        for i in range(len(pts) - 1):
                            wall_id = self.generate_identifier(
                                "wall", self.existing_ids)
                            new_wall = self.Wall(pts[i], pts[i + 1],
                                                 width=self.config.DEFAULT_WALL_WIDTH,
                                                 height=self.config.DEFAULT_WALL_HEIGHT,
                                                 identifier=wall_id,
                                                 layer_id=self.active_layer_id)
                            self.existing_ids.append(wall_id)
                            new_wall_set.append(new_wall)
                        self.wall_sets.append(new_wall_set)
                        wall_created = True
                        break

                if wall_created:
                    # Reset wall drawing state after creating walls from room
                    self.drawing_wall = False
                    self.current_wall = None
                    self.walls = []
                    self.snap_type = "none"
                    self.alignment_candidate = None
                    self.raw_current_end = None
                    self.save_state()
                    self.emit('content-changed')
                    
                    self.update_hint(TOOL_HINTS["draw_walls"])
                else:
                    self.snap_type = "none"
        
        # Update hints based on state
        if auto_snapped_msg:
             self.update_hint(auto_snapped_msg)
        elif self.drawing_wall:
             self.update_hint(TOOL_HINTS["draw_walls_active"])
        elif self.tool_mode == "draw_walls":
             self.update_hint(TOOL_HINTS["draw_walls"])

        self.queue_draw()

    def adjust_wall_to_length(self, wall: Wall, target_length: float) -> bool:
        """Adjust ``wall.end`` along the wall's current direction so its length equals ``target_length``.

        Also updates any connected wall endpoints (including ``self.current_wall.start`` if
        currently drawing a wall chain) so connected walls stay joined.
        """
        if wall is None or target_length <= 0:
            return False
        sx, sy = wall.start
        old_ex, old_ey = wall.end
        dx = old_ex - sx
        dy = old_ey - sy
        cur_len = math.hypot(dx, dy)
        if cur_len <= 1e-6:
            return False
        angle = math.atan2(dy, dx)
        new_end = (
            sx + target_length * math.cos(angle),
            sy + target_length * math.sin(angle),
        )
        tol = getattr(self.config, "JOINT_SNAP_TOLERANCE", 0.25)

        all_walls = [w for ws in self.wall_sets for w in ws] + list(self.walls)
        for w in all_walls:
            if w is wall:
                continue
            if self._points_close(w.start, (old_ex, old_ey), tol):
                w.start = new_end
            if self._points_close(w.end, (old_ex, old_ey), tol):
                w.end = new_end

        wall.end = new_end

        if getattr(self, "drawing_wall", False) and getattr(self, "current_wall", None):
            if self._points_close(self.current_wall.start, (old_ex, old_ey), tol):
                if self._points_close(self.current_wall.end, self.current_wall.start, tol):
                    self.current_wall.end = new_end
                self.current_wall.start = new_end

        self.emit("content-changed")
        self.queue_draw()
        return True

    def _prompt_near_foot_wall_fix(self, wall: Wall, nearest_foot: float) -> None:
        """Prompt the user to snap a wall whose length is very close to ``nearest_foot``."""
        if wall is None:
            return
        cur_len = math.hypot(wall.end[0] - wall.start[0], wall.end[1] - wall.start[1])
        if abs(cur_len - nearest_foot) <= 1e-4:
            return
        drawn_str = self.converter.format_measurement(cur_len, use_fraction=False)
        target_str = self.converter.format_measurement(nearest_foot, use_fraction=False)
        self.last_near_foot_prompt = (wall, nearest_foot)

        root = self.get_root() if hasattr(self, "get_root") else None
        dialog = create_near_foot_confirm_dialog(root, drawn_str=drawn_str, target_str=target_str)

        def _on_response(dlg, response_id):
            if response_id == Gtk.ResponseType.OK:
                self.adjust_wall_to_length(wall, nearest_foot)
                if not getattr(self, "drawing_wall", False):
                    self.save_state()
                self.update_hint(f"Snapped wall length to {target_str}")
            dlg.destroy()

        dialog.connect("response", _on_response)
        dialog.present()

    def snap_selected_walls_to_nearest_foot(self, popover=None) -> int:
        """Snap all currently selected walls to their nearest whole-foot length (>= 1')."""
        count = 0
        for item in getattr(self, "selected_items", []):
            if item.get("type") == "wall":
                w = item.get("object")
                if w is None or self.is_object_on_locked_layer(w):
                    continue
                cur_len = math.hypot(w.end[0] - w.start[0], w.end[1] - w.start[1])
                nearest_foot = max(12.0, round(cur_len / 12.0) * 12.0)
                if abs(cur_len - nearest_foot) > 1e-4:
                    if self.adjust_wall_to_length(w, nearest_foot):
                        count += 1
        if count > 0:
            self.save_state()
        if popover is not None:
            try:
                popover.popdown()
            except Exception:
                pass
        return count

    def toggle_wall_curve_mode(self):
        """Toggle curved wall mode on/off. Call after placing second wall point."""
        if self.tool_mode != "draw_walls" or not self.drawing_wall:
            return
        
        # Only allow entering curve mode if we just placed a wall segment
        if not self.walls or len(self.walls) == 0:
            return
            
        if not self.wall_curve_mode:
            # Enter curve mode - waiting for 3rd point (bulge)
            self.wall_curve_mode = True
            self.update_hint("Click to set arc bulge point for curved wall (Shift+C to cancel)")
        else:
            # Exit curve mode - wall stays straight
            self.wall_curve_mode = False
            self.wall_curve_point = None
            self.update_hint(TOOL_HINTS["draw_walls_active"])
        self.queue_draw()

    def enter_wall_length(self):
        """Open a dialog to enter precise wall length."""
        if self.tool_mode != "draw_walls" or not self.drawing_wall or not self.current_wall:
            return

        dialog = create_length_input_dialog(self.get_root())
        dialog.connect("response", self.on_length_input_response)
        dialog.present()
        self.update_hint("Enter exact length for wall segment")

    def on_length_input_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            text = dialog.get_length()
            try:
                length = self.converter.parse_measurement(text)
                self.apply_wall_length(length)

                self.auto_dimension_mode = True
                GLib.idle_add(self.enter_wall_length)

            except ValueError:
                print("Invalid length entered")
        else:
            self.auto_dimension_mode = False

        dialog.destroy()
        
        if self.drawing_wall:
            self.update_hint(TOOL_HINTS["draw_walls_active"])
        elif self.tool_mode == "draw_walls":
            self.update_hint(TOOL_HINTS["draw_walls"])

    def apply_wall_length(self, length):
        if not self.current_wall:
            return

        start_x, start_y = self.current_wall.start

        # Determine angle
        if self.auto_dimension_mode and self.last_wall_angle is not None:
            angle = self.last_wall_angle + (math.pi / 2)
        else:
            pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
            if hasattr(self, "mouse_x") and hasattr(self, "mouse_y"):
                mx, my = self.device_to_model(
                    self.mouse_x, self.mouse_y, pixels_per_inch)
            else:
                # Fallback if mouse hasn't moved yet? uses current end
                mx, my = self.current_wall.end

            dx = mx - start_x
            dy = my - start_y
            if dx == 0 and dy == 0:
                angle = 0
            else:
                angle = math.atan2(dy, dx)

        end_x = start_x + length * math.cos(angle)
        end_y = start_y + length * math.sin(angle)

        # Create the wall segment
        wall_instance = self.Wall(
            (start_x, start_y), (end_x, end_y),
            self.config.DEFAULT_WALL_WIDTH, self.config.DEFAULT_WALL_HEIGHT,
            identifier=self.generate_identifier("wall", self.existing_ids),
            layer_id=self.active_layer_id
        )

        self.existing_ids.append(wall_instance.identifier)
        self.walls.append(wall_instance)

        # Update state for next segment
        self.current_wall.start = (end_x, end_y)
        self.current_wall.end = (end_x, end_y)
        self.last_wall_angle = angle
        self.emit('content-changed')
        self.queue_draw()

    def _group_walls_into_sets(self, walls: List[Wall]) -> List[List[Wall]]:
        """
        Group a list of walls into connected sets (chains).
        """
        sets = []
        remaining = walls.copy()

        while remaining:
            # Start a new component
            component_walls = [remaining.pop(0)]

            changed = True
            while changed:
                changed = False
                tol = (
                    getattr(
                        self.config,
                        "WALL_JOIN_TOLERANCE",
                        5.0)) / self.zoom

                # Check neighbors for head
                head_pt = component_walls[0].start
                for w in remaining:
                    if self._points_close(w.start, head_pt, tol):
                        w.start, w.end = w.end, w.start
                        w.end = head_pt  # Snap to exact point
                        component_walls.insert(0, w)
                        remaining.remove(w)
                        changed = True
                        break
                    elif self._points_close(w.end, head_pt, tol):
                        w.end = head_pt  # Snap to exact point
                        component_walls.insert(0, w)
                        remaining.remove(w)
                        changed = True
                        break

                if changed:
                    continue

                # Check neighbors for tail
                tail_pt = component_walls[-1].end
                for w in remaining:
                    if self._points_close(w.start, tail_pt, tol):
                        w.start = tail_pt  # Snap to exact point
                        component_walls.append(w)
                        remaining.remove(w)
                        changed = True
                        break
                    elif self._points_close(w.end, tail_pt, tol):
                        w.start, w.end = w.end, w.start
                        w.start = tail_pt  # Snap to exact point
                        component_walls.append(w)
                        remaining.remove(w)
                        changed = True
                        break


            # Check if the component forms a loop and snap the closure
            head_pt = component_walls[0].start
            tail_pt = component_walls[-1].end
            tol = (getattr(self.config, "WALL_JOIN_TOLERANCE", 5.0)) / self.zoom
            
            if len(component_walls) > 1 and self._points_close(head_pt, tail_pt, tol):
                 # Snap tail to head
                 component_walls[-1].end = head_pt

            sets.append(component_walls)
        return sets

    def _order_walls_into_chain(self, walls: List[Wall]) -> List[Wall]:
        """
        Helper to greedily order a list of walls into a contiguous chain.
        """
        if not walls:
            return []

        tol = (getattr(self.config, "WALL_JOIN_TOLERANCE", 5.0)) / self.zoom
        remaining = walls.copy()
        joined = [remaining.pop(0)]

        extended = True
        while extended and remaining:
            extended = False
            last_point = joined[-1].end
            for wall in remaining:
                if self._points_close(wall.start, last_point, tol):
                    wall.start = last_point  # Snap
                    joined.append(wall)
                    remaining.remove(wall)
                    extended = True
                    break
                elif self._points_close(wall.end, last_point, tol):
                    wall.start, wall.end = wall.end, wall.start
                    wall.start = last_point  # Snap
                    joined.append(wall)
                    remaining.remove(wall)
                    extended = True
                    break

        extended = True
        while extended and remaining:
            extended = False
            first_point = joined[0].start
            for wall in remaining:
                if self._points_close(wall.end, first_point, tol):
                    wall.end = first_point  # Snap
                    joined.insert(0, wall)
                    remaining.remove(wall)
                    extended = True
                    break
                elif self._points_close(wall.start, first_point, tol):
                    wall.start, wall.end = wall.end, wall.start
                    wall.end = first_point  # Snap
                    joined.insert(0, wall)
                    remaining.remove(wall)
                    extended = True
                    break
                    
        # Check for loop closure
        if len(joined) > 1:
            head_pt = joined[0].start
            tail_pt = joined[-1].end
            if self._points_close(head_pt, tail_pt, tol):
                joined[-1].end = head_pt

        # Any remaining walls are disjoint from the main chain we found.
        # We'll just append them (butt joins likely) to avoid losing data.
        if remaining:
            print(f"Warning: {len(remaining)} walls could not be linked to the main chain.")
            joined.extend(remaining)

        return joined
