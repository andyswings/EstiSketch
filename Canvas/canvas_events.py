import math
from gi.repository import Gtk

class CanvasEventsMixin:
    def on_click(self, gesture: Gtk.Gesture, n_press: int, x: float, y:float) -> None:
        """
        Handle click events on the canvas and dispatch to the appropriate tool handler.

        This method is called when the user clicks on the canvas. It checks the current tool mode
        and calls the corresponding handler for wall drawing, room drawing, door/window addition,
        pointer selection, polyline drawing, or other tools. For unimplemented tools, it prints a message.

        Args:
            gesture: The gesture object for the click event (may be None for some tools).
            n_press (int): The number of presses (usually 1 for a single click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
        if self.tool_mode == "draw_walls":
            self._handle_wall_click(n_press, x, y)
        elif self.tool_mode == "draw_rooms":
            self._handle_room_click(n_press, x, y)
        elif self.tool_mode == "add_doors":
            self._handle_door_click(n_press, x, y)
        elif self.tool_mode == "add_windows":
            self._handle_window_click(n_press, x, y)
        elif self.tool_mode == "pointer":
            self._handle_pointer_click(gesture, n_press, x, y)
        elif self.tool_mode == "add_polyline":
            self._handle_polyline_click(n_press, x, y)
        elif self.tool_mode == "add_dimension":
            self._handle_dimension_click(n_press, x, y)
        elif self.tool_mode == "add_text":
            self._handle_text_click(n_press, x, y)


    def on_click_pressed(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        """
        Store the starting coordinates of a mouse click gesture.

        This method is called when the user presses a mouse button on the canvas.
        It records the initial click position, which can be used for subsequent
        drag or selection operations.

        Args:
            gesture (Gtk.GestureClick): The gesture object for the click event.
            n_press (int): The number of presses (usually 1 for a single click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
        self.grab_focus()
        self.click_start = (x, y)
        
        # Reset drag active state on new press
        self.drag_active = False
        
        # --- Detect wall-handle press so drag can edit endpoints ---
        # If a selected wall handle was pressed, set editing state and record
        # the model-space start point for the drag logic (box_select_start).
        
        if self.tool_mode != "pointer":
            return
        
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        T = self.zoom * pixels_per_inch
        # Ensure attributes exist
        if not hasattr(self, "handle_radius"):
            self.handle_radius = 10

        for item in self.selected_items:
            if item.get("type") == "wall":
                wall = item.get("object")
                for handle_name, pt in [("start", wall.start), ("end", wall.end)]:
                    pt_widget = ((pt[0] * T) + self.offset_x, (pt[1] * T) + self.offset_y)
                    dx = x - pt_widget[0]
                    dy = y - pt_widget[1]
                    if math.hypot(dx, dy) < self.handle_radius:
                        # Begin editing this wall endpoint.
                        self.editing_wall = wall
                        self.editing_handle = handle_name

                        # Original joint position in model space
                        self.joint_drag_origin = pt

                        # Find ALL endpoints that share this joint (within tolerance)
                        connected = []
                        tol = getattr(self.config, "JOINT_SNAP_TOLERANCE", 0.25)
                        for wall_set in self.wall_sets:
                            for w in wall_set:
                                if self._points_close(w.start, pt, tol):
                                    connected.append((w, "start"))
                                if self._points_close(w.end, pt, tol):
                                    connected.append((w, "end"))
                        self.connected_endpoints = connected

                        # You can still keep this for box-select if you like, but it's
                        # no longer used for endpoint movement math:
                        self.box_select_start = pt

                        # Snapshot state for undo.
                        try:
                            self.save_state()
                        except Exception:
                            pass
                        return
        
        # If no handle was pressed, proceed with normal click selection
        self._handle_pointer_click(gesture, n_press, x, y)

        # Check if we clicked on a text object's rotation handle or for potential dragging
        # (Since _handle_pointer_click should have selected it)
        if hasattr(self, "selected_items"):
             for item in self.selected_items:
                 if item["type"] == "text":
                     text = item["object"]
                     # Check if click was on rotation handle (small circle at top-right)
                     # First calculate handle position in device coordinates
                     from gi.repository import Pango, PangoCairo
                     import cairo
                     
                     # Create temporary surface to measure text
                     temp_surface = cairo.ImageSurface(cairo.Format.ARGB32, 1, 1)
                     temp_cr = cairo.Context(temp_surface)
                     layout = PangoCairo.create_layout(temp_cr)
                     layout.set_text(text.content, -1)
                     desc = Pango.FontDescription(f"{text.font_family} {text.font_size}")
                     if text.bold:
                         desc.set_weight(Pango.Weight.BOLD)
                     if text.italic:
                         desc.set_style(Pango.Style.ITALIC)
                     layout.set_font_description(desc)
                     ink_rect, logical_rect = layout.get_extents()
                     text_width = (logical_rect.width / Pango.SCALE) * self.zoom
                     
                     # Get text position in device coords
                     text_x_dev, text_y_dev = self.model_to_device(text.x, text.y, pixels_per_inch)
                     
                     # Rotation handle is at top-right of text, rotated with text
                     rotation_radians = math.radians(text.rotation)
                     # Handle position relative to text origin
                     handle_rel_x = text_width * math.cos(rotation_radians)
                     handle_rel_y = text_width * math.sin(rotation_radians)
                     handle_x = text_x_dev + handle_rel_x
                     handle_y = text_y_dev + handle_rel_y
                     
                     handle_radius = 8.0  # Slightly larger hit area than visual radius
                     dx = x - handle_x
                     dy = y - handle_y
                     
                     if math.hypot(dx, dy) < handle_radius:
                         # User clicked on rotation handle, start rotation
                         self.rotating_text = text
                         self.rotation_start_angle = text.rotation
                         self.rotation_center = (text_x_dev, text_y_dev)
                         # Calculate initial angle from center to mouse
                         self.rotation_start_mouse_angle = math.degrees(math.atan2(y - text_y_dev, x - text_x_dev))
                         return
                     
                     # Otherwise, start moving the text
                     self.moving_text = text
                     self.moving_text_start_pos = (self.moving_text.x, self.moving_text.y)
                     return


    def on_motion(self, controller: Gtk.EventControllerMotion, x: float, y: float) -> None:
        """
        Handle pointer motion events on the canvas.

        This method is called when the pointer moves over the canvas. It updates the mouse coordinates,
        converts them to model space, and provides live previews for wall, polyline, and room drawing
        with snapping and alignment assistance.

        Args:
            controller (Gtk.EventControllerMotion): The motion event controller.
            x (float): The x-coordinate of the pointer in widget coordinates.
            y (float): The y-coordinate of the pointer in widget coordinates.

        Returns:
            None
        """
        self.mouse_x = x
        self.mouse_y = y
        
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x, canvas_y = self.device_to_model(x, y, pixels_per_inch)
        raw_point = (canvas_x, canvas_y)
        
        # Store last mouse position for dimension preview
        self._last_mouse_pos = (canvas_x, canvas_y)
        
        # Update dimension preview if in dimension drawing mode
        if self.tool_mode == "add_dimension" and self.drawing_dimension:
            if self.dimension_end:
                # After second click - update offset preview
                self.dimension_offset_preview = (canvas_x, canvas_y)
                self.queue_draw()
            # After first click, preview line is drawn using _last_mouse_pos
            elif self.dimension_start:
                self.queue_draw()

        if self.tool_mode == "draw_walls" and self.drawing_wall and self.current_wall:
            last_wall = self.walls[-1] if self.walls else None
            canvas_width = self.get_allocation().width or self.config.WINDOW_WIDTH
            candidate_points = self._get_candidate_points()
            
            polylines = [pl for poly_set in self.polyline_sets for pl in poly_set]
            (snapped_x, snapped_y), self.snap_type = self.snap_manager.snap_point(
                canvas_x, canvas_y,
                self.current_wall.start[0], self.current_wall.start[1],
                self.walls, self.rooms,
                current_wall=self.current_wall, last_wall=last_wall,
                in_progress_points=candidate_points,
                canvas_width=canvas_width, zoom=self.zoom,
                polylines=polylines
            )
            self.raw_current_end = raw_point
            aligned_x, aligned_y, candidate = self._apply_alignment_snapping(canvas_x, canvas_y)
            snapped_x, snapped_y = aligned_x, aligned_y
            self.alignment_candidate = candidate
            
            self.current_wall.end = (snapped_x, snapped_y)
            self.queue_draw()
        
        # Live preview for polylines
        if self.tool_mode == "add_polyline" and self.drawing_polyline:
            base_x, base_y = self.current_polyline_start
            # reuse snapping against walls/rooms
            candidates = self._get_candidate_points() + [(base_x, base_y)]
            polylines = [pl for poly_set in self.polyline_sets for pl in poly_set]
            (sx, sy), _ = self.snap_manager.snap_point(
                canvas_x, canvas_y,
                base_x, base_y,
                self.walls, self.rooms,
                current_wall=None, last_wall=None,
                in_progress_points=candidates,
                canvas_width=self.get_allocation().width or self.config.WINDOW_WIDTH,
                zoom=self.zoom,
                polylines=polylines
            )
            ax, ay, _ = self._apply_alignment_snapping(sx, sy)
            self.current_polyline_preview = (ax, ay)
            self.queue_draw()

        elif self.tool_mode == "draw_rooms":
            base_x = self.current_room_points[-1][0] if self.current_room_points else canvas_x
            base_y = self.current_room_points[-1][1] if self.current_room_points else canvas_y
            candidate_points = self._get_candidate_points()
            candidate_points.extend(self.current_room_points)
            
            polylines = [pl for poly_set in self.polyline_sets for pl in poly_set]
            (snapped_x, snapped_y), _ = self.snap_manager.snap_point(
                canvas_x, canvas_y, base_x, base_y,
                self.walls, self.rooms,
                current_wall=None, last_wall=None,
                in_progress_points=candidate_points,
                canvas_width=self.get_allocation().width or self.config.WINDOW_WIDTH,
                zoom=self.zoom,
                polylines=polylines
            )
            aligned_x, aligned_y, _ = self._apply_alignment_snapping(canvas_x, canvas_y)
            snapped_x, snapped_y = aligned_x, aligned_y
            
            self.current_room_preview = (snapped_x, snapped_y)
            self.queue_draw()
            

    def on_zoom_changed(self, controller: Gtk.GestureZoom, scale: float) -> None:
        """
        Handle zoom level changes on the canvas.

        This method is called when the user adjusts the zoom (e.g., via pinch gesture or zoom control).
        It calculates a new zoom factor based on the input scale and a sensitivity setting, then
        updates the canvas zoom centered on the current view.

        Args:
            controller: The event controller for the zoom gesture.
            scale (float): The zoom scale factor from the gesture.

        Returns:
            None
        """
        sensitivity = 0.2
        factor = 1 + (scale - 1) * sensitivity
        allocation = self.get_allocation()
        center_x = allocation.width / 2
        center_y = allocation.height / 2
        self.adjust_zoom(factor, center_x, center_y)
        

    def on_scroll(self, controller: Gtk.EventControllerScroll, dx: float, dy: float) -> bool:
        """
        Handle scroll events to zoom the canvas view.

        This method is called when the user scrolls with the mouse wheel or touchpad.
        It calculates a zoom factor based on the scroll delta and adjusts the canvas zoom,
        centering the zoom on the current pointer position.

        Args:
            controller (Gtk.EventControllerScroll): The scroll event controller.
            dx (float): The horizontal scroll delta.
            dy (float): The vertical scroll delta.

        Returns:
            bool: True if the event was handled.
        """
        pointer_x, pointer_y = self.get_pointer()
        center_x = pointer_x
        center_y = pointer_y
        zoom_factor = 1.0 + (-dy * 0.1)
        self.adjust_zoom(zoom_factor, center_x, center_y)
        return True
        