import math
from gi.repository import Gtk
from ..components import Door, Window, Polyline
from ..Resources.tool_hints import TOOL_HINTS


class CanvasToolsMixin:
    def _locate_on_wall(self, x, y, opening_width=None):
        """Find the wall nearest to widget point (x, y) and the position ratio on it.

        Shared by door/window placement clicks and the placement ghost so the
        preview always matches what a click would create.

        Args:
            x, y: Pointer position in widget coordinates.
            opening_width: Optional opening width (inches). For straight walls
                the ratio is clamped so the opening stays within the wall.

        Returns:
            (wall, ratio) or None if no wall is within tolerance.
        """
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x = (x - self.offset_x) / (self.zoom * pixels_per_inch)
        canvas_y = (y - self.offset_y) / (self.zoom * pixels_per_inch)
        click_pt = (canvas_x, canvas_y)

        tolerance = 10 / (self.zoom * pixels_per_inch)
        best_dist = float('inf')
        selected_wall = None
        selected_ratio = None

        def normalize(a):
            return a % (2 * math.pi)

        for wall_set in self.wall_sets:
            for wall in wall_set:
                curved = bool(wall.is_curved and wall.arc_center and wall.arc_radius)
                if curved:
                    dist = self.distance_point_to_arc(
                        click_pt, wall.arc_center, wall.arc_radius,
                        math.atan2(wall.start[1] - wall.arc_center[1], wall.start[0] - wall.arc_center[0]),
                        math.atan2(wall.end[1] - wall.arc_center[1], wall.end[0] - wall.arc_center[0])
                    )
                else:
                    dist = self.distance_point_to_segment(
                        click_pt, wall.start, wall.end)

                if not (dist < tolerance and dist < best_dist):
                    continue
                best_dist = dist
                selected_wall = wall

                if curved:
                    cx, cy = wall.arc_center
                    angle = normalize(math.atan2(canvas_y - cy, canvas_x - cx))
                    start_angle = normalize(math.atan2(wall.start[1] - cy, wall.start[0] - cx))
                    end_angle = normalize(math.atan2(wall.end[1] - cy, wall.end[0] - cx))
                    if start_angle < end_angle:
                        arc_span = end_angle - start_angle
                        if start_angle <= angle <= end_angle:
                            selected_ratio = (angle - start_angle) / arc_span
                        else:
                            selected_ratio = 0.0 if abs(angle - start_angle) < abs(angle - end_angle) else 1.0
                    else:  # Arc crosses 0
                        arc_span = (2 * math.pi - start_angle) + end_angle
                        if angle >= start_angle:
                            selected_ratio = (angle - start_angle) / arc_span
                        elif angle <= end_angle:
                            selected_ratio = (2 * math.pi - start_angle + angle) / arc_span
                        else:
                            selected_ratio = 0.5
                    selected_ratio = max(0.0, min(1.0, selected_ratio))
                else:
                    dx = wall.end[0] - wall.start[0]
                    dy = wall.end[1] - wall.start[1]
                    wall_length = math.hypot(dx, dy)
                    if wall_length > 0:
                        t = ((canvas_x - wall.start[0]) * dx + (canvas_y - wall.start[1]) * dy) / (wall_length ** 2)
                        lo, hi = 0.0, 1.0
                        if opening_width and opening_width < wall_length:
                            half = (opening_width / 2.0) / wall_length
                            lo, hi = half, 1.0 - half
                        selected_ratio = max(lo, min(hi, t))
                    else:
                        selected_ratio = 0.5

        if selected_wall is None:
            return None
        return selected_wall, selected_ratio

    def _default_door_dims(self):
        """Return (width, height) of the door the tool would currently place."""
        door_type = getattr(self.config, "DEFAULT_DOOR_TYPE", "single")
        if door_type == "garage":
            return 96.0, 80.0
        if door_type in ("double", "sliding"):
            return 72.0, 80.0
        return 36.0, 80.0

    def _build_default_door(self, identifier=""):
        """Build the door the door tool would place (used for click and ghost)."""
        door_type = getattr(self.config, "DEFAULT_DOOR_TYPE", "single")
        width, height = self._default_door_dims()
        return Door(
            door_type, width, height, "left", "inswing",
            identifier=identifier, layer_id=self.active_layer_id)

    def _build_default_window(self, identifier=""):
        """Build the window the window tool would place (used for click and ghost)."""
        window_type = getattr(self.config, "DEFAULT_WINDOW_TYPE", "sliding")
        return Window(
            48.0, 36.0, window_type,
            identifier=identifier, layer_id=self.active_layer_id)

    def _handle_door_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle the addition of a door to the nearest wall based on a click event.

        This method is called when the user clicks on the canvas while the door tool is active.
        It converts the click coordinates to model space, finds the nearest wall segment within a
        tolerance, and attaches a new door object to that wall at the appropriate position ratio.
        The door type and identifier are determined from configuration and generated uniquely.
        The new door is added to the canvas and the display is updated.

        Args:
            n_press (int): The number of presses (usually 1 for a single click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
        hit = self._locate_on_wall(x, y, opening_width=self._default_door_dims()[0])
        if hit is None:
            print("No wall was found near the click for door addition.")
            return
        selected_wall, selected_ratio = hit
        door_identifier = self.generate_identifier("door", self.existing_ids)
        new_door = self._build_default_door(identifier=door_identifier)
        self.existing_ids.append(door_identifier)
        self.doors.append((selected_wall, new_door, selected_ratio))
        self.save_state()
        self.emit('content-changed')
        self.queue_draw()

    def _handle_window_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle the addition of a window to the nearest wall based on a click event.

        This method is called when the user clicks on the canvas while the window tool is active.
        It converts the click coordinates to model space, finds the nearest wall segment within a
        tolerance, and attaches a new window object to that wall at the appropriate position ratio.
        The window type and identifier are determined from configuration and generated uniquely.
        The new window is added to the canvas and the display is updated.

        Args:
            n_press (int): The number of presses (usually 1 for a single click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
        hit = self._locate_on_wall(x, y, opening_width=48.0)
        if hit is None:
            print("No wall was found near the click for window addition.")
            return

        selected_wall, selected_ratio = hit
        window_identifier = self.generate_identifier(
            "window", self.existing_ids)
        new_window = self._build_default_window(identifier=window_identifier)
        self.existing_ids.append(window_identifier)
        self.windows.append((selected_wall, new_window, selected_ratio))
        self.save_state()
        self.emit('content-changed')
        self.queue_draw()

    def _handle_polyline_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle click events for drawing polylines on the canvas.

        This method is called when the user clicks while the polyline drawing tool is active.
        On a single click, it starts or extends a polyline segment, snapping and aligning the endpoint.
        On a double click, it finalizes the polyline chain, closes the polyline set, and resets the drawing state.

        Args:
            n_press (int): The number of presses (1 for single click, 2 for double click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
        # Convert to model coords
        ppi = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        mx, my = self.device_to_model(x, y, ppi)

        # Snap & align
        last = self.current_polyline_start or (mx, my)
        candidates = self._get_candidate_points() + [last]
        (sx, sy), self.snap_type = self.snap_manager.snap_point(
            mx, my,
            last[0], last[1],
            self.walls, self.rooms,
            current_wall=None, last_wall=None,
            in_progress_points=candidates,
            canvas_width=self.get_allocation().width or self.config.WINDOW_WIDTH,
            zoom=self.zoom
        )
        ax, ay, _ = self._apply_alignment_snapping(sx, sy)
        snapped = (ax, ay)

        if n_press == 1:
            # start or extend - removed save_state here
            if not self.drawing_polyline:
                self.drawing_polyline = True
                self.current_polyline_start = snapped
                self.polylines = []
            else:
                polyline_identifier = self.generate_identifier(
                    "polyline", self.existing_ids)
                seg = Polyline(
                    self.current_polyline_start,
                    snapped,
                    identifier=polyline_identifier,
                    layer_id=self.active_layer_id)
                self.existing_ids.append(polyline_identifier)
                default_style = getattr(self.config, "POLYLINE_TYPE", "solid")
                seg_style = default_style if default_style in (
                    "solid", "dashed") else "solid"
                if seg_style == "dashed":
                    seg.style = "dashed"
                else:
                    seg.style = "solid"
                self.polylines.append(seg)
                self.current_polyline_start = snapped
                self.update_hint(TOOL_HINTS["add_polyline_active"])
                self.emit('content-changed')
            self.queue_draw()
            self.current_polyline_preview = None

        elif n_press == 2 and self.drawing_polyline:
            # finalize - only save here when complete
            self.save_state()
            if self.polylines:
                self.polyline_sets.append(self.polylines.copy())
            self.drawing_polyline = False
            self.current_polyline_start = None
            self.polylines = []
            self.polylines = []
            self.emit('content-changed')
            self.queue_draw()
            self.current_polyline_preview = None

            # Reset hint
            self.update_hint(TOOL_HINTS["add_polyline"])

    def _handle_text_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle simple click to create a default text box if no drag occurred.
        """
        # Check if we have a significant drag.
        if hasattr(self, "drag_active") and self.drag_active:
            self.drag_active = False
            return

        # Guard against duplicate if drag_start_x still exists (dirty state)
        if hasattr(self, "drag_start_x"):
            del self.drag_start_x
            return

        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x = (x - self.offset_x) / (self.zoom * pixels_per_inch)
        canvas_y = (y - self.offset_y) / (self.zoom * pixels_per_inch)

        # Create default text
        text_id = self.generate_identifier("text", self.existing_ids)
        new_text = self.Text(
            canvas_x,
            canvas_y,
            content="Text",
            width=48.0,
            height=24.0,
            identifier=text_id,
            layer_id=self.active_layer_id)
        self.texts.append(new_text)
        self.existing_ids.append(text_id)

        # Select it
        self.selected_items = [{"type": "text", "object": new_text}]
        self.emit('selection-changed', self.selected_items)
        self.save_state()
        self.emit('content-changed')
        self.queue_draw()

    def _handle_dimension_click(
            self,
            n_press: int,
            x: float,
            y: float) -> None:
        """
        Handle dimension tool clicks with three-click workflow or auto-dimension on double-click.

        Workflow:
        1. Single click: Set start point
        2. Single click: Set end point
        3. Single click: Set offset and finalize

        Auto-dimension:
        - Double-click on wall: Auto-create dimension for that wall
        """
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x = (x - self.offset_x) / (self.zoom * pixels_per_inch)
        canvas_y = (y - self.offset_y) / (self.zoom * pixels_per_inch)

        # Check for double-click (n_press == 2)
        if n_press == 2:
            self._handle_auto_dimension(canvas_x, canvas_y, pixels_per_inch)
            return

        # Three-click workflow for manual dimensioning
        if not self.drawing_dimension:
            # First click - set start point
            self.dimension_start = (canvas_x, canvas_y)
            self.drawing_dimension = True
            self.dimension_end = None
            self.dimension_offset_preview = None
            print(f"Dimension start set at {self.dimension_start}")
            self.queue_draw()
        elif self.dimension_end is None:
            # Second click - set end point
            self.dimension_end = (canvas_x, canvas_y)
            print(f"Dimension end set at {self.dimension_end}")
            self.queue_draw()
            self.update_hint(TOOL_HINTS["add_dimension_active"])
        else:
            # Third click - finalize with offset
            offset = self._calculate_dimension_offset(
                self.dimension_start,
                self.dimension_end,
                (canvas_x, canvas_y)
            )

            # Create dimension object
            dim_id = self.generate_identifier("dimension", self.existing_ids)
            new_dimension = self.Dimension(
                start=self.dimension_start,
                end=self.dimension_end,
                offset=offset,
                identifier=dim_id,
                layer_id=self.active_layer_id
            )
            self.dimensions.append(new_dimension)
            self.existing_ids.append(dim_id)

            # Reset state
            self.drawing_dimension = False
            self.dimension_start = None
            self.dimension_end = None
            self.dimension_offset_preview = None

            print(f"Dimension created with offset {offset}")
            self.save_state()
            self.save_state()
            self.emit('content-changed')
            self.queue_draw()

            self.update_hint(TOOL_HINTS["add_dimension"])

    def _handle_auto_dimension(
            self,
            canvas_x: float,
            canvas_y: float,
            pixels_per_inch: float) -> None:
        """
        Auto-create a dimension for a wall near the double-click point.
        """
        # Immediately reset any manual dimension state from the first click
        # (GTK fires single-click before double-click)
        self.drawing_dimension = False
        self.dimension_start = None
        self.dimension_end = None
        self.dimension_offset_preview = None

        click_pt = (canvas_x, canvas_y)
        tolerance = 10 / (self.zoom * pixels_per_inch)

        # Find nearest wall
        best_dist = float('inf')
        selected_wall = None

        for wall_set in self.wall_sets:
            for wall in wall_set:
                dist = self.distance_point_to_segment(
                    click_pt, wall.start, wall.end)
                if dist < tolerance and dist < best_dist:
                    best_dist = dist
                    selected_wall = wall

        if selected_wall is None:
            print("No wall found near double-click for auto-dimensioning")
            return

        # Calculate wall geometry for edge alignment
        start = selected_wall.start
        end = selected_wall.end
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.hypot(dx, dy)

        if length == 0:
            return

        # Unit vector along wall
        ux = dx / length
        uy = dy / length

        # Perpendicular vector (rotate 90 degrees counter-clockwise)
        # Using consistent normal definition
        px = -uy
        py = ux

        # Vector from start to click point
        mx = canvas_x - start[0]
        my = canvas_y - start[1]

        # Cross product to determine side (signed distance)
        # vals > 0 means "left" side (positive normal), < 0 means "right" side
        cross = ux * my - uy * mx
        direction = 1.0 if cross >= 0 else -1.0

        # Offset to wall edge
        # Wall width is in inches
        half_width = selected_wall.width / 2.0
        
        # Calculate new start/end points at the wall edge
        edge_offset_x = px * half_width * direction
        edge_offset_y = py * half_width * direction

        edge_offset_vector = (edge_offset_x, edge_offset_y)
        edge_start_simple = (start[0] + edge_offset_x, start[1] + edge_offset_y)
        edge_end_simple = (end[0] + edge_offset_x, end[1] + edge_offset_y)

        # Calculate true corner points (handling miter joins)
        edge_start = self._get_corner_point_for_dimension(
            selected_wall, start, edge_start_simple, edge_offset_vector)
        edge_end = self._get_corner_point_for_dimension(
            selected_wall, end, edge_end_simple, edge_offset_vector)

        # Calculate automatic offset for dimension line
        # Use 12 inches as default offset from the edge
        default_offset = 12.0  # TODO: Make this configurable
        
        # Apply direction to offset so dimension extends outward from the edge
        final_offset = default_offset * direction

        # Create dimension object
        dim_id = self.generate_identifier("dimension", self.existing_ids)
        new_dimension = self.Dimension(
            start=edge_start,
            end=edge_end,
            offset=final_offset,
            identifier=dim_id,
            layer_id=self.active_layer_id)
        self.dimensions.append(new_dimension)
        self.existing_ids.append(dim_id)
        self.save_state()
        self.emit('content-changed')
        self.queue_draw()



    def _calculate_dimension_offset(
            self,
            start: tuple,
            end: tuple,
            mouse_pos: tuple) -> float:
        """
        Calculate the perpendicular distance from the line (start to end) to mouse_pos.
        Returns a signed offset (positive on one side, negative on the other).
        """
        # Vector from start to end
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.hypot(dx, dy)

        if length == 0:
            return 0.0

        # Unit vector along the line
        ux = dx / length
        uy = dy / length

        # Vector from start to mouse
        mx = mouse_pos[0] - start[0]
        my = mouse_pos[1] - start[1]

        # Perpendicular distance (cross product gives signed area, divide by length)
        # Using 2D cross product: ux * my - uy * mx
        offset = ux * my - uy * mx

        return offset

    def show_edit_text_dialog(self, text_obj, popover: Gtk.Popover):
        # Create a simple dialog to edit text
        popover.popdown()

        # Use Gtk.Window or simple Dialog? Gtk4 Dialog is different.
        # Let's create a temporary window.

        dialog = Gtk.Dialog(title="Edit Text")
        dialog.set_transient_for(self.get_native())
        dialog.set_modal(True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK", Gtk.ResponseType.OK)

        content_area = dialog.get_content_area()
        entry = Gtk.Entry()
        entry.set_text(text_obj.content)
        entry.set_hexpand(True)
        content_area.append(entry)

        # We need to present it
        dialog.show()

        def on_response(d, response):
            if response == Gtk.ResponseType.OK:
                text_obj.content = entry.get_text()
                self.queue_draw()
                # Update properties dock by emitting selection-changed
                # Find this text in selected_items and re-emit the signal
                if hasattr(self, 'selected_items'):
                    for item in self.selected_items:
                        if item.get("type") == "text" and item.get(
                                "object") == text_obj:
                            # Re-emit selection-changed to update sidebar
                            self.emit('selection-changed', self.selected_items)
                            break
            d.destroy()

        dialog.connect("response", on_response)

    def _handle_circle_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle click events for drawing circles.
        Workflow: Click Center -> Move (Radius preview) -> Click Radius.
        """
        ppi = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        mx, my = self.device_to_model(x, y, ppi)
        
        # Snap logic (reuse snap manager from other tools)
        (sx, sy), self.snap_type = self.snap_manager.snap_point(
            mx, my,
            mx, my, # No previous point logic used for circle center unless we track it
            self.walls, self.rooms, # etc
            zoom=self.zoom
        )
        
        if not self.drawing_circle:
             # First click: Set Center
             self.circle_center = (sx, sy)
             self.drawing_circle = True
             self.circle_radius_preview = 0.0
             self.circle_radius_preview = 0.0
             print(f"Circle center set at {self.circle_center}")
             self.update_hint(TOOL_HINTS["add_circle_active"])
        else:
             # Second click: Set Radius and Finalize
             radius = math.hypot(sx - self.circle_center[0], sy - self.circle_center[1])
             if radius > 0:
                 circle_id = self.generate_identifier("circle", self.existing_ids)
                 new_circle = self.Circle(
                     center=self.circle_center,
                     radius=radius,
                     identifier=circle_id,
                     layer_id=self.active_layer_id
                 )
                 self.circles.append(new_circle)
                 self.existing_ids.append(circle_id)
                 print(f"Circle created with radius {radius}")
                 self.save_state()
             
             # Reset
             self.drawing_circle = False
             self.circle_center = None
             self.circle_radius_preview = None
             self.update_hint(TOOL_HINTS["add_circle"])
        
        
        if not self.drawing_circle:
             self.emit('content-changed')
        self.queue_draw()

    def _handle_arc_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle click events for drawing arcs (3-point).
        Workflow: Click Start -> Click End -> Click Point-on-Curve.
        """
        ppi = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        mx, my = self.device_to_model(x, y, ppi)
        
        # Snap logic (simple point snap)
        (sx, sy), self.snap_type = self.snap_manager.snap_point(
            mx, my, mx, my, self.walls, self.rooms, zoom=self.zoom
        )
        
        if not self.drawing_arc:
            # First click: Set Start
            self.arc_start = (sx, sy)
            self.drawing_arc = True
            self.arc_end = None
            self.arc_preview_point = None
            print(f"Arc start set at {self.arc_start}")
            
            self.update_hint(TOOL_HINTS["add_arc_active_end"])
        
        elif self.arc_end is None:
            # Second click: Set End
            if (sx, sy) != self.arc_start:
                self.arc_end = (sx, sy)
                print(f"Arc end set at {self.arc_end}")
                
                self.update_hint(TOOL_HINTS["add_arc_active_mid"])
            else:
                print("Arc end cannot be same as start")
        
        else:
            # Third click: Set Point-on-Curve and Finalize
            self.arc_preview_point = (sx, sy)
            
            # Calculate geometry
            geom = self.get_circle_from_3_points(self.arc_start, self.arc_end, (sx, sy))
            if geom:
                (cx, cy), radius = geom
                
                # Determine angles
                angle_start = self.get_angle_at_point((cx, cy), self.arc_start)
                angle_mid = self.get_angle_at_point((cx, cy), (sx, sy))
                angle_end = self.get_angle_at_point((cx, cy), self.arc_end)
                
                # Determine orientation for storage
                # Cairo assumes CW drawing from start to end by default OR we explicitly store CW/CCW?
                # Arc dataclass stores start/end angles. We need to know if we traverse CW or CCW.
                # Standard convention (like DXF): Arcs are CCW.
                # If our 3 points imply a CW arc from start to end, we should swap start/end logic?
                # Actually, standard math returns angles in CCW from X-axis.
                # If we draw from Angle Start to Angle End CCW, does it hit Mid?
                
                a_start_n = self.normalize_angle(angle_start)
                a_mid_n = self.normalize_angle(angle_mid)
                a_end_n = self.normalize_angle(angle_end)
                
                # Check if Mid is between Start and End in CCW direction
                # (Start < Mid < End) circular logic
                
                is_ccw = False
                if a_start_n < a_end_n:
                    if a_start_n < a_mid_n < a_end_n:
                         is_ccw = True
                else: # start > end (crosses 0)
                    if a_mid_n > a_start_n or a_mid_n < a_end_n:
                         is_ccw = True
                
                final_start = angle_start
                final_end = angle_end

                if not is_ccw:
                    # If the user defined points imply a CW arc (Start -> Mid -> End is CW),
                    # we should store it as an arc from End to Start (CCW) so standard renderers work?
                    # OR we just store it as is and renderer handles it. 
                    # My renderer currently handles CW/CCW check.
                    # Let's align with the renderer's logic in on_draw. Is uses arc/arc_negative.
                    # But simpler to just normalize to always be valid CCW arc? 
                    # If 3 points determine circle, arc is unique.
                    
                    # Let's perform the swap so stored arc is always CCW traversal?
                    # This makes rendering cleaner (always cr.arc, never cr.arc_negative).
                    final_start = angle_end
                    final_end = angle_start
                
                arc_id = self.generate_identifier("arc", self.existing_ids)
                new_arc = self.Arc(
                    center=(cx, cy),
                    radius=radius,
                    start_angle=final_start,
                    end_angle=final_end,
                    identifier=arc_id,
                    layer_id=self.active_layer_id
                )
                self.arcs.append(new_arc)
                self.existing_ids.append(arc_id)
                print(f"Arc created with radius {radius}")
                self.save_state()
            
            else:
                print("Points are collinear, cannot create arc.")

            # Reset
            self.drawing_arc = False
            self.arc_start = None
            self.arc_end = None
            self.arc_preview_point = None
            
            self.update_hint(TOOL_HINTS["add_arc"])
            
        # Emit change if we just finished an arc
        if not self.drawing_arc:
            self.emit('content-changed')
        self.queue_draw()

    def _handle_dimension_chain_click(self, n_press: int, x: float, y: float) -> None:
        """Handle multi-click continuous dimension chain creation."""
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x = (x - self.offset_x) / (self.zoom * pixels_per_inch)
        canvas_y = (y - self.offset_y) / (self.zoom * pixels_per_inch)

        # Snap point
        last = self.dimension_chain_points[-1] if getattr(self, "dimension_chain_points", None) else (canvas_x, canvas_y)
        candidates = self._get_candidate_points() + [last]
        (sx, sy), self.snap_type = self.snap_manager.snap_point(
            canvas_x, canvas_y,
            last[0], last[1],
            self.walls, self.rooms,
            current_wall=None, last_wall=None,
            in_progress_points=candidates,
            canvas_width=self.get_allocation().width or self.config.WINDOW_WIDTH,
            zoom=self.zoom
        )
        ax, ay, _ = self._apply_alignment_snapping(sx, sy)
        click_pt = (ax, ay)

        # If double-click: finalize immediately (do not append duplicate point!)
        if n_press == 2:
            if getattr(self, "drawing_dimension_chain", False) and len(getattr(self, "dimension_chain_points", [])) >= 2:
                if self.dimension_chain_offset is None:
                    p0 = self.dimension_chain_points[0]
                    p1 = self.dimension_chain_points[1]
                    off = self._calculate_dimension_offset(p0, p1, (canvas_x, canvas_y))
                    self.dimension_chain_offset = off if abs(off) > 1.0 else 18.0
                self.finalize_dimension_chain()
            return

        if not getattr(self, "drawing_dimension_chain", False):
            # First click: start of chain
            self.selected_items = []
            self.dimension_chain_points = [click_pt]
            self.drawing_dimension_chain = True
            self.dimension_chain_offset = None
            self.update_hint(TOOL_HINTS["add_dimension_chain_baseline"])
            self.queue_draw()
            return

        if len(self.dimension_chain_points) == 1:
            # Second click: establishes baseline axis
            p0 = self.dimension_chain_points[0]
            if math.hypot(click_pt[0] - p0[0], click_pt[1] - p0[1]) < 0.5:
                return
            self.dimension_chain_points.append(click_pt)
            self.update_hint(TOOL_HINTS["add_dimension_chain_offset"])
            self.queue_draw()
            return

        # We have at least 2 points (p0 and p1) establishing the baseline
        p0 = self.dimension_chain_points[0]
        p1 = self.dimension_chain_points[1]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        blen = math.hypot(dx, dy)
        if blen < 1e-4:
            return
        ux = dx / blen
        uy = dy / blen
        px = -uy
        py = ux

        # Calculate perpendicular distance of click to baseline
        d_perp = (canvas_x - p0[0]) * px + (canvas_y - p0[1]) * py

        # If user clicked away from the baseline (d_perp >= 6.0),
        # they are setting the offset and dropping the chain!
        is_offset_click = (abs(d_perp) >= 6.0)

        if is_offset_click:
            self.dimension_chain_offset = d_perp
            self.finalize_dimension_chain()
            return

        # Otherwise, user is clicking an additional point along the chain (e.g. wall feature)
        last_pt = self.dimension_chain_points[-1]
        if math.hypot(click_pt[0] - last_pt[0], click_pt[1] - last_pt[1]) >= 0.5:
            self.dimension_chain_points.append(click_pt)
            self.update_hint(TOOL_HINTS["add_dimension_chain_points"])
            self.queue_draw()

    def finalize_dimension_chain(self) -> None:
        """Finalize the in-progress dimension chain and save state."""
        pts = getattr(self, "dimension_chain_points", [])
        if len(pts) >= 2:
            chain_id = self.generate_identifier("dim_chain", self.existing_ids)
            offset = self.dimension_chain_offset if self.dimension_chain_offset is not None else 18.0
            if abs(offset) < 1.0:
                offset = 18.0
            new_chain = self.DimensionChain(
                points=list(pts),
                offset=offset,
                identifier=chain_id,
                layer_id=self.active_layer_id,
                summary_dimension=True,
                summary_offset=16.0,
                arrow_style="architectural_tick",
                line_style="solid",
                text_size=12.0
            )
            self.dimension_chains.append(new_chain)
            self.existing_ids.append(chain_id)
            self.selected_items = [{"type": "dimension_chain", "object": new_chain}]
            self.save_state()
            self.emit('content-changed')
            self.emit('selection-changed', self.selected_items)

        self.drawing_dimension_chain = False
        self.dimension_chain_points = []
        self.dimension_chain_offset = None
        self.update_hint(TOOL_HINTS["add_dimension_chain"])
        self.queue_draw()

    def _snap_leader_target(self, x: float, y: float, snap_threshold: float = 15.0) -> tuple:
        """Snap leader arrowhead tip to wall faces, windows, doors, or stairs."""
        best_pt = (x, y)
        best_dist = snap_threshold

        # 1. Snap to discrete object features: doors, windows, stairs
        for door_item in getattr(self, "doors", []):
            if isinstance(door_item, (tuple, list)) and len(door_item) >= 3 and door_item[0]:
                wall, door, ratio = door_item[0], door_item[1], door_item[2]
                dx = wall.end[0] - wall.start[0]
                dy = wall.end[1] - wall.start[1]
                center_x = wall.start[0] + ratio * dx
                center_y = wall.start[1] + ratio * dy
                dist = math.hypot(x - center_x, y - center_y)
                if dist < best_dist:
                    best_dist = dist
                    best_pt = (center_x, center_y)
            elif hasattr(door_item, "floating_pos") and door_item.floating_pos:
                dist = math.hypot(x - door_item.floating_pos[0], y - door_item.floating_pos[1])
                if dist < best_dist:
                    best_dist = dist
                    best_pt = door_item.floating_pos

        for win_item in getattr(self, "windows", []):
            if isinstance(win_item, (tuple, list)) and len(win_item) >= 3 and win_item[0]:
                wall, win, ratio = win_item[0], win_item[1], win_item[2]
                dx = wall.end[0] - wall.start[0]
                dy = wall.end[1] - wall.start[1]
                center_x = wall.start[0] + ratio * dx
                center_y = wall.start[1] + ratio * dy
                dist = math.hypot(x - center_x, y - center_y)
                if dist < best_dist:
                    best_dist = dist
                    best_pt = (center_x, center_y)
            elif hasattr(win_item, "floating_pos") and win_item.floating_pos:
                dist = math.hypot(x - win_item.floating_pos[0], y - win_item.floating_pos[1])
                if dist < best_dist:
                    best_dist = dist
                    best_pt = win_item.floating_pos

        for stair in getattr(self, "stairs", []):
            s_start = getattr(stair, "start_point", None)
            if s_start:
                dist = math.hypot(x - s_start[0], y - s_start[1])
                if dist < best_dist:
                    best_dist = dist
                    best_pt = (s_start[0], s_start[1])

        # If a discrete feature point was snapped, prioritize it over continuous wall surfaces
        if best_pt != (x, y):
            return best_pt

        # 2. Snap to wall faces (centerline, outer face, inner face)
        walls_to_check = list(getattr(self, "walls", []))
        for wall_set in getattr(self, "wall_sets", []):
            walls_to_check.extend(wall_set)

        for wall in walls_to_check:
            w_start = wall.start
            w_end = wall.end
            dx = w_end[0] - w_start[0]
            dy = w_end[1] - w_start[1]
            w_len = math.hypot(dx, dy)
            if w_len == 0:
                continue
            ux = dx / w_len
            uy = dy / w_len
            px = -uy
            py = ux
            half_w = wall.width / 2.0

            # Project point onto segment
            t = max(0.0, min(w_len, (x - w_start[0]) * ux + (y - w_start[1]) * uy))
            base_x = w_start[0] + t * ux
            base_y = w_start[1] + t * uy

            # Candidates: outer edge (+normal), inner edge (-normal), and centerline
            for d_norm in (half_w, -half_w, 0.0):
                cand_x = base_x + d_norm * px
                cand_y = base_y + d_norm * py
                dist = math.hypot(x - cand_x, y - cand_y)
                if dist < best_dist:
                    best_dist = dist
                    best_pt = (cand_x, cand_y)

        return best_pt

    def _handle_leader_click(self, n_press: int, x: float, y: float) -> None:
        """Handle 3-click architectural leader callout placement."""
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x = (x - self.offset_x) / (self.zoom * pixels_per_inch)
        canvas_y = (y - self.offset_y) / (self.zoom * pixels_per_inch)

        if not getattr(self, "drawing_leader", False):
            # Click 1: Arrowhead tip
            snap_dist = 16.0 / (self.zoom * pixels_per_inch)
            snapped_tip = self._snap_leader_target(canvas_x, canvas_y, snap_dist)
            self.leader_tip = snapped_tip
            self.drawing_leader = True
            self.leader_elbow = None
            self.update_hint(TOOL_HINTS["add_leader_elbow"])
            self.queue_draw()
            return

        if self.leader_elbow is None:
            # Click 2: Elbow bend
            self.leader_elbow = (canvas_x, canvas_y)
            if n_press == 2:
                # Double-click: auto horizontal shoulder landing
                landing_dir = 16.0 if canvas_x >= self.leader_tip[0] else -16.0
                shoulder = (canvas_x + landing_dir, canvas_y)
                self.finalize_leader(self.leader_tip, self.leader_elbow, shoulder)
            else:
                self.update_hint(TOOL_HINTS["add_leader_shoulder"])
                self.queue_draw()
            return

        # Click 3: Shoulder landing point
        shoulder = (canvas_x, canvas_y)
        self.finalize_leader(self.leader_tip, self.leader_elbow, shoulder)

    def finalize_leader(self, tip: tuple = None, elbow: tuple = None, shoulder: tuple = None) -> None:
        """Finalize the leader callout and select it for editing."""
        if tip is None:
            tip = getattr(self, "leader_tip", None)
        if elbow is None:
            elbow = getattr(self, "leader_elbow", None)
        if tip is None or elbow is None:
            self.drawing_leader = False
            self.leader_tip = None
            self.leader_elbow = None
            self.queue_draw()
            return
        if shoulder is None:
            shoulder = (elbow[0] + 30.0, elbow[1])
        lead_id = self.generate_identifier("leader", self.existing_ids)
        new_leader = self.LeaderCallout(
            tip=tip,
            elbow=elbow,
            shoulder=shoulder,
            text="Note",
            identifier=lead_id,
            layer_id=self.active_layer_id,
            text_size=12.0,
            box_border=False,
            arrow_type="arrow",
            line_style="solid"
        )
        self.leader_callouts.append(new_leader)
        self.existing_ids.append(lead_id)
        self.selected_items = [{"type": "leader_callout", "object": new_leader}]
        self.emit('selection-changed', self.selected_items)
        self.save_state()
        self.emit('content-changed')

        self.drawing_leader = False
        self.leader_tip = None
        self.leader_elbow = None
        self.update_hint(TOOL_HINTS["add_leader"])
        self.queue_draw()

