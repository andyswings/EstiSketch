import math
from gi.repository import Gtk
from components import Door, Window, Polyline

class CanvasToolsMixin:
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
        # Convert device (widget) coordinates to model coordinates using zoom and pixels-per-inch.
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x = (x - self.offset_x) / (self.zoom * pixels_per_inch)
        canvas_y = (y - self.offset_y) / (self.zoom * pixels_per_inch)
        click_pt = (canvas_x, canvas_y)
        
        tolerance = 10 / (self.zoom * pixels_per_inch)
        best_dist = float('inf')
        selected_wall = None
        selected_ratio = None
        
        for wall_set in self.wall_sets:
            for wall in wall_set:
                dist = self.distance_point_to_segment(click_pt, wall.start, wall.end)
                if dist < tolerance and dist < best_dist:
                    best_dist = dist
                    selected_wall = wall
                    dx = wall.end[0] - wall.start[0]
                    dy = wall.end[1] - wall.start[1]
                    wall_length = math.hypot(dx, dy)
                    if wall_length > 0:
                        t = ((canvas_x - wall.start[0]) * dx + (canvas_y - wall.start[1]) * dy) / (wall_length ** 2)
                        selected_ratio = max(0.0, min(1.0, t))
                    else:
                        selected_ratio = 0.5
        
        if selected_wall is None:
            print("No wall was found near the click for door addition.")
            return
        door_type = getattr(self.config, "DEFAULT_DOOR_TYPE", "single")
        door_identifier = self.generate_identifier("door", self.existing_ids)
        if door_type == "garage":
            new_door = Door(door_type, 96.0, 80.0, "left", "inswing", identifier=door_identifier, layer_id=self.active_layer_id)
        elif door_type == "double" or door_type == "sliding":
            new_door = Door(door_type, 72.0, 80.0, "left", "inswing", identifier=door_identifier, layer_id=self.active_layer_id)
        else:
            new_door = Door(door_type, 36.0, 80.0, "left", "inswing", identifier=door_identifier, layer_id=self.active_layer_id)
        self.existing_ids.append(door_identifier)
        self.doors.append((selected_wall, new_door, selected_ratio))
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
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x = (x - self.offset_x) / (self.zoom * pixels_per_inch)
        canvas_y = (y - self.offset_y) / (self.zoom * pixels_per_inch)
        click_pt = (canvas_x, canvas_y)
        
        tolerance = 10 / (self.zoom * pixels_per_inch)
        best_dist = float('inf')
        selected_wall = None
        selected_ratio = None
        
        for wall_set in self.wall_sets:
            for wall in wall_set:
                dist = self.distance_point_to_segment(click_pt, wall.start, wall.end)
                if dist < tolerance and dist < best_dist:
                    best_dist = dist
                    selected_wall = wall
                    dx = wall.end[0] - wall.start[0]
                    dy = wall.end[1] - wall.start[1]
                    wall_length = math.hypot(dx, dy)
                    if wall_length > 0:
                        t = ((canvas_x - wall.start[0]) * dx + (canvas_y - wall.start[1]) * dy) / (wall_length ** 2)
                        selected_ratio = max(0.0, min(1.0, t))
                    else:
                        selected_ratio = 0.5
        
        if selected_wall is None:
            print("No wall was found near the click for window addition.")
            return
        
        window_type = getattr(self.config, "DEFAULT_WINDOW_TYPE", "sliding")
        window_identifier = self.generate_identifier("window", self.existing_ids)
        new_window = Window(48.0, 36.0, window_type, identifier=window_identifier, layer_id=self.active_layer_id)
        self.existing_ids.append(window_identifier)
        self.windows.append((selected_wall, new_window, selected_ratio))
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
                polyline_identifier = self.generate_identifier("polyline", self.existing_ids)
                seg = Polyline(self.current_polyline_start, snapped, identifier=polyline_identifier, layer_id=self.active_layer_id)
                self.existing_ids.append(polyline_identifier)
                default_style = getattr(self.config, "POLYLINE_TYPE", "solid")
                seg_style = default_style if default_style in ("solid", "dashed") else "solid"
                if seg_style == "dashed":
                    seg.style = "dashed"
                else:
                    seg.style = "solid" 
                self.polylines.append(seg)
                self.current_polyline_start = snapped
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
            self.queue_draw()
            self.current_polyline_preview = None
    

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
        new_text = self.Text(canvas_x, canvas_y, content="Text", width=48.0, height=24.0, identifier=text_id, layer_id=self.active_layer_id)
        self.texts.append(new_text)
        self.existing_ids.append(text_id)
        
        # Select it
        self.selected_items = [{"type": "text", "object": new_text}]
        self.emit('selection-changed', self.selected_items)
        self.queue_draw()
        

    def _handle_dimension_click(self, n_press: int, x: float, y: float) -> None:
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
            self.queue_draw()
    
    def _handle_auto_dimension(self, canvas_x: float, canvas_y: float, pixels_per_inch: float) -> None:
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
                dist = self.distance_point_to_segment(click_pt, wall.start, wall.end)
                if dist < tolerance and dist < best_dist:
                    best_dist = dist
                    selected_wall = wall
        
        if selected_wall is None:
            print("No wall found near double-click for auto-dimensioning")
            return
        
        # Calculate automatic offset (perpendicular distance from wall)
        # Use 12 inches as default offset
        default_offset = 12.0 # TODO: Make this configurable
        
        # Create dimension object
        dim_id = self.generate_identifier("dimension", self.existing_ids)
        new_dimension = self.Dimension(
            start=selected_wall.start,
            end=selected_wall.end,
            offset=default_offset,
            identifier=dim_id,
            layer_id=self.active_layer_id
        )
        self.dimensions.append(new_dimension)
        self.existing_ids.append(dim_id)
        
        print(f"Auto-dimension created for wall from {selected_wall.start} to {selected_wall.end}")
        self.save_state()
        self.queue_draw()
    
    def _calculate_dimension_offset(self, start: tuple, end: tuple, mouse_pos: tuple) -> float:
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
                        if item.get("type") == "text" and item.get("object") == text_obj:
                            # Re-emit selection-changed to update sidebar
                            self.emit('selection-changed', self.selected_items)
                            break
            d.destroy()
            
        dialog.connect("response", on_response)
    

