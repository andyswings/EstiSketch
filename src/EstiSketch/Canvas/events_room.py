

from ..Resources.tool_hints import TOOL_HINTS


class CanvasRoomMixin:
    def _compute_room_snap(self, canvas_x: float, canvas_y: float):
        """Snap a room point like the wall tool does.

        Considers committed wall sets (edges, faces, centerlines, endpoints),
        rooms, polylines and in-progress room points. Alignment snapping is
        only a fallback when no hard geometric feature was hit.
        Returns ((x, y), snap_type, alignment_candidate)."""
        base_x, base_y = (self.current_room_points[-1]
                          if self.current_room_points else (canvas_x, canvas_y))
        candidate_points = self._get_candidate_points()
        candidate_points.extend(self.current_room_points)
        polylines = [pl for poly_set in getattr(self, "polyline_sets", [])
                     for pl in poly_set]
        alloc = self.get_allocation() if hasattr(self, "get_allocation") else None
        canvas_width = (alloc.width if alloc and alloc.width else 0) or self.config.WINDOW_WIDTH
        (sx, sy), snap_type = self.snap_manager.snap_point(
            canvas_x, canvas_y, base_x, base_y,
            self._get_snap_walls(), self.rooms,
            current_wall=None, last_wall=None,
            in_progress_points=candidate_points,
            canvas_width=canvas_width, zoom=self.zoom, polylines=polylines)
        candidate = None
        if self.snap_manager.snap_enabled and snap_type not in (
                "endpoint", "midpoint", "wall_centerline", "face_flush", "wall_edge"):
            ax, ay, candidate = self._apply_alignment_snapping(sx, sy)
            if candidate is not None:
                sx, sy = ax, ay
                if snap_type in ("none", "grid", "distance"):
                    snap_type = "alignment"
        return (sx, sy), snap_type, candidate

    def _handle_room_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle click events for drawing rooms on the canvas.

        This method is called when the user clicks while the room drawing tool is active.
        On a single click, it adds a snapped and aligned point to the current room outline.
        On a double click, it finalizes the room by closing the polygon and creating a new room object,
        or attempts to create a room from a closed wall set if the click is inside one.

        Args:
            n_press (int): The number of presses (1 for single click, 2 for double click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x, canvas_y = self.device_to_model(x, y, pixels_per_inch)
        # raw_point = (canvas_x, canvas_y)
        base_x = self.current_room_points[-1][0] if self.current_room_points else canvas_x
        base_y = self.current_room_points[-1][1] if self.current_room_points else canvas_y
        (snapped_x, snapped_y), _, _ = self._compute_room_snap(canvas_x, canvas_y)

        if n_press == 1:
            # Removed save_state here - only save when room is complete
            self.current_room_points.append((snapped_x, snapped_y))
            self.update_hint(TOOL_HINTS["draw_rooms_active"])
            self.queue_draw()
        elif n_press == 2:
            # Only save when finalizing the room
            room_created = False
            if self.current_room_points and len(self.current_room_points) >= 3:
                # Room stores only unique vertices - rendering uses
                # close_path() to close polygon
                room_id = self.generate_identifier("room", self.existing_ids)
                new_room = self.Room(
                    self.current_room_points,
                    identifier=room_id,
                    layer_id=self.active_layer_id)
                self.existing_ids.append(room_id)
                self.rooms.append(new_room)
                self.current_room_points = []
                self.current_room_preview = None
                room_created = True
                
                self.update_hint(TOOL_HINTS["draw_rooms"])
            for wall_set in self.wall_sets:
                if len(wall_set) < 2:
                    continue
                if self._is_closed_polygon(wall_set):
                    poly = self._get_wall_set_polygon(wall_set)
                    if self._point_in_polygon((snapped_x, snapped_y), poly):
                        # Draw the room to the inside faces of the walls
                        poly = self._get_wall_set_inner_polygon(wall_set)
                        room_id = self.generate_identifier(
                            "room", self.existing_ids
                        )
                        new_room = self.Room(
                            poly,
                            identifier=room_id,
                            layer_id=self.active_layer_id)
                        self.existing_ids.append(room_id)
                        self.rooms.append(new_room)
                        # Reset room drawing state after creating room from
                        # closed loop
                        self.current_room_points = []
                        self.current_room_preview = None
                        room_created = True
                        
                        self.update_hint(TOOL_HINTS["draw_rooms"])
                        break
            if room_created:
                self.save_state()
                self.emit('content-changed')
            self.queue_draw()

    def finalize_room(self):
        # Only finalize if there are enough points to form a room
        if self.current_room_points and len(self.current_room_points) >= 3:
            # Room stores only unique vertices - rendering uses close_path() to
            # close polygon
            room_id = self.generate_identifier("room", self.existing_ids)
            new_room = self.Room(
                self.current_room_points,
                identifier=room_id,
                layer_id=self.active_layer_id)
            self.existing_ids.append(room_id)
            self.rooms.append(new_room)
            print(f"Finalized room with points: {self.current_room_points}")
        # Clear the temporary room points and preview
        self.current_room_points = []
        self.current_room_preview = None
        
        self.update_hint(TOOL_HINTS["draw_rooms"])
        self.emit('content-changed')
        self.queue_draw()

    # ─────────────────────────────────────────────────────────────────────────
    # Manual Floor Opening Drawing
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_opening_snap(self, canvas_x: float, canvas_y: float):
        """Snap a floor opening vertex using wall/room/opening geometry and alignment."""
        import math

        cur_pts = getattr(self, "current_opening_points", [])
        base_x, base_y = cur_pts[-1] if cur_pts else (canvas_x, canvas_y)
        candidate_points = self._get_candidate_points()
        for opening in getattr(self, "floor_openings", []):
            candidate_points.extend(getattr(opening, "points", []))
        candidate_points.extend(cur_pts)
        polylines = [pl for poly_set in getattr(self, "polyline_sets", []) for pl in poly_set]
        alloc = self.get_allocation() if hasattr(self, "get_allocation") else None
        canvas_width = (alloc.width if alloc and alloc.width else 0) or self.config.WINDOW_WIDTH
        (sx, sy), snap_type = self.snap_manager.snap_point(
            canvas_x, canvas_y, base_x, base_y,
            self._get_snap_walls(), self.rooms,
            current_wall=None, last_wall=None,
            in_progress_points=candidate_points,
            canvas_width=canvas_width, zoom=self.zoom, polylines=polylines,
        )
        candidate = None
        if self.snap_manager.snap_enabled and snap_type not in (
                "endpoint", "midpoint", "wall_centerline", "face_flush", "wall_edge"):
            ax, ay, candidate = self._apply_alignment_snapping(sx, sy)
            if candidate is not None:
                sx, sy = ax, ay
                if snap_type in ("none", "grid", "distance"):
                    snap_type = "alignment"
        # Also allow snapping directly back to first corner when closing loop
        if len(cur_pts) >= 3:
            p0 = cur_pts[0]
            if math.hypot(canvas_x - p0[0], canvas_y - p0[1]) < 8.0 / max(self.zoom, 0.25):
                return p0, "endpoint", candidate
        return (sx, sy), snap_type, candidate

    def _handle_floor_opening_click(self, n_press: int, x: float, y: float) -> None:
        """Handle clicks for the manual Floor Opening polygon tool."""
        import math

        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x, canvas_y = self.device_to_model(x, y, pixels_per_inch)
        (snapped_x, snapped_y), _, _ = self._compute_opening_snap(canvas_x, canvas_y)

        if not hasattr(self, "current_opening_points"):
            self.current_opening_points = []

        if n_press == 1:
            if len(self.current_opening_points) >= 3:
                p0 = self.current_opening_points[0]
                if math.hypot(snapped_x - p0[0], snapped_y - p0[1]) < 6.0 / max(self.zoom, 0.25):
                    self.finalize_floor_opening()
                    return
            if (not self.current_opening_points or
                    math.hypot(snapped_x - self.current_opening_points[-1][0],
                               snapped_y - self.current_opening_points[-1][1]) > 1e-4):
                self.current_opening_points.append((snapped_x, snapped_y))
            self.update_hint(TOOL_HINTS["add_floor_opening_active"])
            self.queue_draw()
        elif n_press == 2:
            self.finalize_floor_opening()

    def finalize_floor_opening(self):
        """Close the current opening polygon, create a FloorOpening, and sync room holes."""
        import math
        from ..geometry.room_holes import MIN_HOLE_AREA_SQIN, polygon_area, sync_stair_holes

        raw_pts = list(getattr(self, "current_opening_points", []) or [])
        pts = []
        for pt in raw_pts:
            if not pts or math.hypot(pt[0] - pts[-1][0], pt[1] - pts[-1][1]) > 1e-4:
                pts.append(tuple(pt))
        if len(pts) > 1 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= 1e-4:
            pts.pop()

        self.current_opening_points = []
        self.current_opening_preview = None

        created = None
        if len(pts) >= 3 and polygon_area(pts) >= MIN_HOLE_AREA_SQIN:
            opening_id = self.generate_identifier("opening", self.existing_ids)
            created = self.FloorOpening(
                pts,
                identifier=opening_id,
                layer_id=self.active_layer_id,
            )
            self.existing_ids.append(opening_id)
            if not hasattr(self, "floor_openings"):
                self.floor_openings = []
            self.floor_openings.append(created)
            sync_stair_holes(self)
            self.save_state()
            self.emit('content-changed')

        self.update_hint(TOOL_HINTS["add_floor_opening"])
        self.queue_draw()
        return created
