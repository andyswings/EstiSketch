import math
from gi.repository import Gtk, Gdk
from typing import List
from components import Wall, Door, Window, Polyline


class CanvasEventsMixin:
    def on_click(self, gesture, n_press, x, y):
        # print(f"Current tool_mode: {self.tool_mode}")
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
            print("Dimension tool is not implemented yet.")
            # TODO: Implement dimension tool
        #     self._handle_dimension_click(n_press, x, y)
        elif self.tool_mode == "add_text":
            print("Text tool is not implemented yet.")
            # TODO: Implement text tool
        #     self._handle_text_click(n_press, x, y)
    
    def on_right_click(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        """
        Handle right-click events by invoking the pointer tool's right-click handler.
        
        Parameters:
            gesture (Gtk.GestureClick): The gesture object for the right-click.
            n_press (int): The click count.
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.
        
        Returns:
            None
        """
        # Invoke the existing right-click handler.
        self._handle_pointer_right_click(gesture, n_press, x, y)
    
    def _handle_door_click(self, n_press: int, x: float, y: float) -> None:
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
        if door_type == "garage":
            new_door = Door(door_type, 96.0, 80.0, "left", "inswing")
        elif door_type == "double" or door_type == "sliding":
            new_door = Door(door_type, 72.0, 80.0, "left", "inswing")
        else:
            new_door = Door(door_type, 36.0, 80.0, "left", "inswing")
        self.doors.append((selected_wall, new_door, selected_ratio))
        self.queue_draw()
    
    def _handle_window_click(self, n_press: int, x: float, y: float) -> None:
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
        new_window = Window(48.0, 36.0, window_type)
        self.windows.append((selected_wall, new_window, selected_ratio))
        self.queue_draw()

    
    def _handle_pointer_right_click(self, gesture, n_press, x, y):
        # Filter selected items
        selected_walls = [item for item in self.selected_items if item.get("type") == "wall"]
        selected_doors = [item for item in self.selected_items if item.get("type") == "door"]
        selected_windows = [item for item in self.selected_items if item.get("type") == "window"]

        # Create a popover to serve as the context menu
        parent_popover = Gtk.Popover()  # Renamed for clarity
        
        # Create a vertical box to hold the menu item(s)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        parent_popover.set_child(box)
        
        # Decide whether or not to create "Set as Exterior" or "Set as Interior" buttons
        use_ext_button = False
        use_int_button = False
        for wall in selected_walls:
            if wall["object"].exterior_wall == False and use_ext_button == False:
                use_ext_button = True
            elif wall["object"].exterior_wall == True and use_int_button == False:
                use_int_button = True
        
        if use_ext_button:
            ext_button = Gtk.Button(label="Set as Exterior")
            ext_button.connect("clicked", lambda btn: self.set_ext_int(selected_walls, True, parent_popover))
            box.append(ext_button)
        
        if use_int_button:
            int_button = Gtk.Button(label="Set as Interior")
            int_button.connect("clicked", lambda btn: self.set_ext_int(selected_walls, False, parent_popover))
            box.append(int_button)
        
        # Create a button labeled "Join Walls"
        if len(selected_walls) >= 2:
            join_button = Gtk.Button(label="Join Walls")
            join_button.connect("clicked", lambda btn: self.join_selected_walls(parent_popover))
            box.append(join_button)
        
        # Door-specific options
        if selected_doors:
            door_button = Gtk.Button(label="Change Door Type")
            door_button.connect("clicked", lambda btn: self.show_change_door_type_submenu(btn, selected_doors, parent_popover))
            box.append(door_button)
            
            
            if selected_doors[0]["object"][1].orientation == "inswing":
                orientation_button = Gtk.Button(label="Change to Outswing")
                orientation_button.connect("clicked", lambda btn: self.toggle_door_orientation(selected_doors, parent_popover, outswing=True))
                box.append(orientation_button)
                
            elif selected_doors[0]["object"][1].orientation == "outswing":
                orientation_button = Gtk.Button(label="Change to Inswing")
                orientation_button.connect("clicked", lambda btn: self.toggle_door_orientation(selected_doors, parent_popover, inswing=True))
                box.append(orientation_button)
            
            toggle_swing_button = Gtk.Button(label="Toggle Swing Direction")
            toggle_swing_button.connect("clicked", lambda btn: self.toggle_door_swing(selected_doors, parent_popover))
            box.append(toggle_swing_button)
        
        # Window-specific option
        if selected_windows:
            window_button = Gtk.Button(label="Change Window Type")
            window_button.connect("clicked", lambda btn: self.show_change_window_type_submenu(btn, selected_windows, parent_popover))
            box.append(window_button)
        
        # Position the popover at the click location
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        parent_popover.set_pointing_to(rect)
        
        # Set the popover's parent to the canvas (self)
        parent_popover.set_parent(self)
        
        # Show the popover
        parent_popover.popup()
    
    def join_selected_walls(self, popover) -> None:
        """
        Join selected wall segments or wall sets into a single continuous wall set.

        This method searches the current selection (stored in self.selected_items) for wall segments.
        It then determines which wall sets contain any of these selected walls, removes those wall sets
        from self.wall_sets, and merges their walls into a single chain. Walls are considered connected
        if the distance between an endpoint of one wall and the start point of the next wall is within a
        specified tolerance (typically based on a configuration value divided by the current zoom level).

        If some selected walls are not contiguous with the main chain, they will not be merged and a warning
        is printed. The resulting joined wall set preserves each wall segment’s original start and end coordinates.
        Finally, the method clears the current selection and requests a redraw of the canvas.

        Returns:
            None
        """
        # Gather all wall sets that contain at least one selected wall.
        selected_sets: List[List[Wall]] = []
        for item in self.selected_items:
            if item.get("type") == "wall":
                # For each selected wall, find which wall set it belongs to.
                for ws in self.wall_sets:
                    if item["object"] in ws and ws not in selected_sets:
                        selected_sets.append(ws)
                        break
                    
        # Check if there are at least two selected wall sets to join.
        if len(selected_sets) < 2:
            print("Right-click: Need at least 2 selected walls to join.")
            return

        if not selected_sets:
            print("No wall segments selected for joining.")
            return

        # Remove the selected wall sets from the overall list.
        for ws in selected_sets:
            if ws in self.wall_sets:
                self.wall_sets.remove(ws)

        # Flatten all selected walls into a single list.
        all_walls: List[Wall] = []
        for ws in selected_sets:
            all_walls.extend(ws)

        # Define a helper function to compute Euclidean distance.
        def distance(p, q):
            return math.hypot(p[0] - q[0], p[1] - q[1])

        # Use a tolerance for determining connectivity.
        # Use the config's WALL_JOIN_TOLERANCE (if defined) divided by zoom, or default to 5.
        tol = (getattr(self.config, "WALL_JOIN_TOLERANCE", 5.0)) / self.zoom

        # Greedily order the walls into a continuous chain.
        remaining: List[Wall] = all_walls.copy()
        joined: List[Wall] = []
        if not remaining:
            return

        # Start with an arbitrary wall.
        current = remaining.pop(0)
        joined.append(current)

        # Extend forward from the end of the chain.
        extended = True
        while extended and remaining:
            extended = False
            last_point = joined[-1].end
            for wall in remaining:
                if distance(wall.start, last_point) < tol:
                    joined.append(wall)
                    remaining.remove(wall)
                    extended = True
                    break
                elif distance(wall.end, last_point) < tol:
                    # Reverse the wall so its start becomes the connecting endpoint.
                    wall.start, wall.end = wall.end, wall.start
                    joined.append(wall)
                    remaining.remove(wall)
                    extended = True
                    break

        # Extend backward from the beginning of the chain.
        extended = True
        while extended and remaining:
            extended = False
            first_point = joined[0].start
            for wall in remaining:
                if distance(wall.end, first_point) < tol:
                    joined.insert(0, wall)
                    remaining.remove(wall)
                    extended = True
                    break
                elif distance(wall.start, first_point) < tol:
                    wall.start, wall.end = wall.end, wall.start
                    joined.insert(0, wall)
                    remaining.remove(wall)
                    extended = True
                    break

        if remaining:
            print("Warning: Not all selected walls are contiguous; only contiguous segments have been joined.")

        # Append the new, joined wall set to the canvas.
        self.wall_sets.append(joined)
        # Clear selection and request a redraw.
        self.selected_items = []
        self.queue_draw()
        popover.popdown()
            
    def on_click_pressed(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        self.click_start = (x, y)
    
    def _handle_pointer_click(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        # print(f"Pointer click: {n_press} press(es) at ({x}, {y})")
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        if hasattr(self, "click_start"):
            dx = x - self.click_start[0]
            dy = y - self.click_start[1]
            if math.hypot(dx, dy) > 5:
                return

        click_pt = (x, y)
        fixed_threshold = 10      # device pixels for walls
        vertex_threshold = 15     # device pixels for vertices
        best_dist = float('inf')
        selected_item = None

        T = self.zoom * pixels_per_inch
        for wall_set in self.wall_sets:
            for wall in wall_set:
                start_widget = (
                    (wall.start[0] * T) + self.offset_x,
                    (wall.start[1] * T) + self.offset_y
                )
                end_widget = (
                    (wall.end[0] * T) + self.offset_x,
                    (wall.end[1] * T) + self.offset_y
                )
                dist_start = math.hypot(click_pt[0] - start_widget[0],
                                        click_pt[1] - start_widget[1])
                dist_end = math.hypot(click_pt[0] - end_widget[0],
                                    click_pt[1] - end_widget[1])
                if dist_start < fixed_threshold and dist_start < best_dist:
                    best_dist = dist_start
                    selected_item = {"type": "wall", "object": wall}
                if dist_end < fixed_threshold and dist_end < best_dist:
                    best_dist = dist_end
                    selected_item = {"type": "wall", "object": wall}
                dist_seg = self.distance_point_to_segment(click_pt, start_widget, end_widget)
                if dist_seg < fixed_threshold and dist_seg < best_dist:
                    best_dist = dist_seg
                    # print("Wall selected")
                    selected_item = {"type": "wall", "object": wall}
        
        for room in self.rooms:
            for idx, pt in enumerate(room.points):
                pt_widget = (
                    (pt[0] * T) + self.offset_x,
                    (pt[1] * T) + self.offset_y
                )
                dist_pt = math.hypot(click_pt[0] - pt_widget[0],
                                    click_pt[1] - pt_widget[1])
                if dist_pt < vertex_threshold and dist_pt < best_dist:
                    best_dist = dist_pt
                    # print("Vertex selected")
                    selected_item = {"type": "vertex", "object": (room, idx)}

        for door_item in self.doors:
            wall, door, ratio = door_item
            A = wall.start
            B = wall.end
            H = (A[0] + ratio * (B[0] - A[0]), A[1] + ratio * (B[1] - A[1]))
            dx = B[0] - A[0]
            dy = B[1] - A[1]
            length = math.hypot(dx, dy)
            if length == 0:
                continue
            d = (dx / length, dy / length)
            p = (-d[1], d[0])
            n = (-p[0], -p[1]) if door.swing == "left" else (p[0], p[1])
            w = door.width
            t = self.config.DEFAULT_WALL_WIDTH
            H_start = (H[0] - (w / 2) * d[0], H[1] - (w / 2) * d[1])
            H_end = (H[0] + (w / 2) * d[0], H[1] + (w / 2) * d[1])
            P1 = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1])
            P2 = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1])
            P3 = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1])
            P4 = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1])
            P1_dev = self.model_to_device(P1[0], P1[1], pixels_per_inch)
            P2_dev = self.model_to_device(P2[0], P2[1], pixels_per_inch)
            P3_dev = self.model_to_device(P3[0], P3[1], pixels_per_inch)
            P4_dev = self.model_to_device(P4[0], P4[1], pixels_per_inch)
            door_poly = [P1_dev, P2_dev, P3_dev, P4_dev]
            if self._point_in_polygon(click_pt, door_poly):
                # print("Door selected")
                selected_item = {"type": "door", "object": door_item}
                break  # Exit loop if door is selected

        for window_item in self.windows:
            wall, window, ratio = window_item
            A = wall.start
            B = wall.end
            H = (A[0] + ratio * (B[0] - A[0]), A[1] + ratio * (B[1] - A[1]))
            dx = B[0] - A[0]
            dy = B[1] - A[1]
            length = math.hypot(dx, dy)
            if length == 0:
                continue
            d = (dx / length, dy / length)
            p = (-d[1], d[0])
            w = window.width
            t = self.config.DEFAULT_WALL_WIDTH
            H_start = (H[0] - (w / 2) * d[0], H[1] - (w / 2) * d[1])
            H_end = (H[0] + (w / 2) * d[0], H[1] + (w / 2) * d[1])
            P1 = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1])
            P2 = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1])
            P3 = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1])
            P4 = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1])
            P1_dev = self.model_to_device(P1[0], P1[1], pixels_per_inch)
            P2_dev = self.model_to_device(P2[0], P2[1], pixels_per_inch)
            P3_dev = self.model_to_device(P3[0], P3[1], pixels_per_inch)
            P4_dev = self.model_to_device(P4[0], P4[1], pixels_per_inch)
            window_poly = [P1_dev, P2_dev, P3_dev, P4_dev]
            if self._point_in_polygon(click_pt, window_poly):
                # print("Window selected")
                selected_item = {"type": "window", "object": window_item}
                break


        event = gesture.get_current_event()
        state = event.get_modifier_state() if hasattr(event, "get_modifier_state") else event.state
        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if selected_item:
            # print("Selected item:", selected_item)
            if shift_pressed:
                if not any(existing["object"] == selected_item["object"] for existing in self.selected_items):
                    self.selected_items.append(selected_item)
            else:
                self.selected_items = [selected_item]
        else:
            if not shift_pressed:
                self.selected_items = []
        self.queue_draw()


    def distance_point_to_segment(self, P, A, B):
        px, py = P = P
        ax, ay = A
        bx, by = B
        dx = bx - ax
        dy = by - ay
        if dx == dy == 0:
            return math.hypot(px - ax, py - ay)
        t = ((px - ax) * dx + (py - ay) * dy) / (dx ** 2 + dy ** 2)
        t = max(0, min(1, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return math.hypot(px - proj_x, py - proj_y)
    
    def line_intersects_rect(self, A, B, rect):
        """Return True if line segment AB intersects the rectangle defined by rect = (rx1, ry1, rx2, ry2) 
        (with rx1 < rx2 and ry1 < ry2)."""
        rx1, ry1, rx2, ry2 = rect

        def point_in_rect(pt):
            x, y = pt
            return rx1 <= x <= rx2 and ry1 <= y <= ry2

        # If either endpoint is inside the rectangle, the segment intersects.
        if point_in_rect(A) or point_in_rect(B):
            return True

        # Helper: Check if two segments (p,q) and (r,s) intersect.
        def segments_intersect(p, q, r, s):
            def orientation(a, b, c):
                # Calculate the orientation of triplet (a,b,c)
                val = (b[1]-a[1])*(c[0]-b[0]) - (b[0]-a[0])*(c[1]-b[1])
                if abs(val) < 1e-6:
                    return 0  # colinear
                return 1 if val > 0 else 2  # 1: clockwise, 2: counterclockwise

            def on_segment(a, b, c):
                return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and
                        min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))

            o1 = orientation(p, q, r)
            o2 = orientation(p, q, s)
            o3 = orientation(r, s, p)
            o4 = orientation(r, s, q)

            if o1 != o2 and o3 != o4:
                return True

            if o1 == 0 and on_segment(p, q, r):
                return True
            if o2 == 0 and on_segment(p, q, s):
                return True
            if o3 == 0 and on_segment(r, s, p):
                return True
            if o4 == 0 and on_segment(r, s, q):
                return True

            return False

        # Define the rectangle's four edges:
        edges = [
            ((rx1, ry1), (rx2, ry1)),  # top edge
            ((rx2, ry1), (rx2, ry2)),  # right edge
            ((rx2, ry2), (rx1, ry2)),  # bottom edge
            ((rx1, ry2), (rx1, ry1))   # left edge
        ]

        for edge in edges:
            if segments_intersect(A, B, edge[0], edge[1]):
                return True
        return False


    def on_drag_begin(self, gesture, start_x, start_y):
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        if self.tool_mode == "panning":
            self.drag_start_x = start_x
            self.drag_start_y = start_y
            self.last_offset_x = self.offset_x
            self.last_offset_y = self.offset_y
        elif self.tool_mode == "pointer":
            self.box_selecting = True
            self.box_select_start = ((start_x - self.offset_x) / (self.zoom * pixels_per_inch),
                                    (start_y - self.offset_y) / (self.zoom * pixels_per_inch))
            self.box_select_end = self.box_select_start
            event = gesture.get_current_event()
            state = event.get_modifier_state() if hasattr(event, "get_modifier_state") else event.state
            self.box_select_extend = bool(state & Gdk.ModifierType.SHIFT_MASK)

    def on_drag_update(self, gesture, offset_x, offset_y):
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        if self.tool_mode == "panning":
            self.offset_x = self.last_offset_x + offset_x
            self.offset_y = self.last_offset_y + offset_y
            self.queue_draw()
        elif self.tool_mode == "pointer" and self.box_selecting:
            current_x = self.box_select_start[0] + (offset_x / (self.zoom * pixels_per_inch))
            current_y = self.box_select_start[1] + (offset_y / (self.zoom * pixels_per_inch))
            self.box_select_end = (current_x, current_y)
            self.queue_draw()

    def on_drag_end(self, gesture, offset_x, offset_y):
        if self.tool_mode == "pointer" and self.box_selecting:
            x1 = min(self.box_select_start[0], self.box_select_end[0])
            y1 = min(self.box_select_start[1], self.box_select_end[1])
            x2 = max(self.box_select_start[0], self.box_select_end[0])
            y2 = max(self.box_select_start[1], self.box_select_end[1])
            rect = (x1, y1, x2, y2)
            
            new_selection = []
            
            for wall_set in self.wall_sets:
                for wall in wall_set:
                    if self.line_intersects_rect(wall.start, wall.end, rect):
                        new_selection.append({"type": "wall", "object": wall})
            
            for room in self.rooms:
                for idx, pt in enumerate(room.points):
                    if (x1 <= pt[0] <= x2) and (y1 <= pt[1] <= y2):
                        new_selection.append({"type": "vertex", "object": (room, idx)})
            
            for door_item in self.doors:
                wall, door, ratio = door_item
                A = wall.start
                B = wall.end
                H = (A[0] + ratio * (B[0] - A[0]), A[1] + ratio * (B[1] - A[1]))
                dx = B[0] - A[0]
                dy = B[1] - A[1]
                length = math.hypot(dx, dy)
                if length == 0:
                    continue
                d = (dx / length, dy / length)
                p = (-d[1], d[0])
                n = (-p[0], -p[1]) if door.swing == "left" else (p[0], p[1])
                w = door.width
                t = self.config.DEFAULT_WALL_WIDTH
                H_start = (H[0] - (w / 2) * d[0], H[1] - (w / 2) * d[1])
                H_end = (H[0] + (w / 2) * d[0], H[1] + (w / 2) * d[1])
                P1 = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1])
                P2 = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1])
                P3 = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1])
                P4 = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1])
                # Compute bounding box for the door polygon.
                door_min_x = min(P1[0], P2[0], P3[0], P4[0])
                door_max_x = max(P1[0], P2[0], P3[0], P4[0])
                door_min_y = min(P1[1], P2[1], P3[1], P4[1])
                door_max_y = max(P1[1], P2[1], P3[1], P4[1])
                # If the door bounding box overlaps with the selection rectangle, add it.
                if door_max_x >= x1 and door_min_x <= x2 and door_max_y >= y1 and door_min_y <= y2:
                    new_selection.append({"type": "door", "object": door_item})

            for window_item in self.windows:
                wall, window, ratio = window_item
                A = wall.start
                B = wall.end
                H = (A[0] + ratio * (B[0] - A[0]), A[1] + ratio * (B[1] - A[1]))
                dx = B[0] - A[0]
                dy = B[1] - A[1]
                length = math.hypot(dx, dy)
                if length == 0:
                    continue
                d = (dx / length, dy / length)
                p = (-d[1], d[0])
                w = window.width
                t = self.config.DEFAULT_WALL_WIDTH
                H_start = (H[0] - (w / 2) * d[0], H[1] - (w / 2) * d[1])
                H_end = (H[0] + (w / 2) * d[0], H[1] + (w / 2) * d[1])
                P1 = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1])
                P2 = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1])
                P3 = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1])
                P4 = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1])
                window_min_x = min(P1[0], P2[0], P3[0], P4[0])
                window_max_x = max(P1[0], P2[0], P3[0], P4[0])
                window_min_y = min(P1[1], P2[1], P3[1], P4[1])
                window_max_y = max(P1[1], P2[1], P3[1], P4[1])
                if window_max_x >= x1 and window_min_x <= x2 and window_max_y >= y1 and window_min_y <= y2:
                    new_selection.append({"type": "window", "object": window_item})
            
            if hasattr(self, "box_select_extend") and self.box_select_extend:
                for item in new_selection:
                    if not any(existing["type"] == item["type"] and existing["object"] == item["object"]
                            for existing in self.selected_items):
                        self.selected_items.append(item)
            else:
                self.selected_items = new_selection
            
            self.box_selecting = False
            self.queue_draw()
    
    def _get_candidate_points(self): # Helper function to get all candidate points from wall sets.
            return [point for wall_set in self.wall_sets for wall in wall_set for point in (wall.start, wall.end)]

    def on_motion(self, controller: Gtk.EventControllerMotion, x: float, y: float) -> None:
        self.mouse_x = x
        self.mouse_y = y
        
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x, canvas_y = self.device_to_model(x, y, pixels_per_inch)
        raw_point = (canvas_x, canvas_y)

        if self.tool_mode == "draw_walls" and self.drawing_wall and self.current_wall:
            last_wall = self.walls[-1] if self.walls else None
            canvas_width = self.get_allocation().width or self.config.WINDOW_WIDTH
            candidate_points = self._get_candidate_points()
            
            (snapped_x, snapped_y), self.snap_type = self.snap_manager.snap_point(
                canvas_x, canvas_y,
                self.current_wall.start[0], self.current_wall.start[1],
                self.walls, self.rooms,
                current_wall=self.current_wall, last_wall=last_wall,
                in_progress_points=candidate_points,
                canvas_width=canvas_width, zoom=self.zoom
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
            (sx, sy), _ = self.snap_manager.snap_point(
                canvas_x, canvas_y,
                base_x, base_y,
                self.walls, self.rooms,
                current_wall=None, last_wall=None,
                in_progress_points=candidates,
                canvas_width=self.get_allocation().width or self.config.WINDOW_WIDTH,
                zoom=self.zoom
            )
            ax, ay, _ = self._apply_alignment_snapping(sx, sy)
            self.current_polyline_preview = (ax, ay)
            self.queue_draw()

        elif self.tool_mode == "draw_rooms":
            base_x = self.current_room_points[-1][0] if self.current_room_points else canvas_x
            base_y = self.current_room_points[-1][1] if self.current_room_points else canvas_y
            candidate_points = self._get_candidate_points()
            candidate_points.extend(self.current_room_points)
            
            (snapped_x, snapped_y), _ = self.snap_manager.snap_point(
                canvas_x, canvas_y, base_x, base_y,
                self.walls, self.rooms,
                current_wall=None, last_wall=None,
                in_progress_points=candidate_points,
                canvas_width=self.get_allocation().width or self.config.WINDOW_WIDTH,
                zoom=self.zoom
            )
            aligned_x, aligned_y, _ = self._apply_alignment_snapping(canvas_x, canvas_y)
            snapped_x, snapped_y = aligned_x, aligned_y
            
            self.current_room_preview = (snapped_x, snapped_y)
            self.queue_draw()

    def on_zoom_changed(self, controller, scale):
        sensitivity = 0.2
        factor = 1 + (scale - 1) * sensitivity
        allocation = self.get_allocation()
        center_x = allocation.width / 2
        center_y = allocation.height / 2
        self.adjust_zoom(factor, center_x, center_y)

    def on_scroll(self, controller, dx, dy):
        pointer_x, pointer_y = self.get_pointer()
        center_x = pointer_x
        center_y = pointer_y
        zoom_factor = 1.0 + (-dy * 0.1)
        self.adjust_zoom(zoom_factor, center_x, center_y)
        return True

    def _handle_room_click(self, n_press, x, y):
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x, canvas_y = self.device_to_model(x, y, pixels_per_inch)
        raw_point = (canvas_x, canvas_y)
        base_x = self.current_room_points[-1][0] if self.current_room_points else canvas_x
        base_y = self.current_room_points[-1][1] if self.current_room_points else canvas_y
        candidate_points = self._get_candidate_points()
        candidate_points.extend(self.current_room_points)
        
        (snapped_x, snapped_y), _ = self.snap_manager.snap_point(
            canvas_x, canvas_y, base_x, base_y,
            self.walls, self.rooms,
            current_wall=None, last_wall=None,
            in_progress_points=candidate_points,
            canvas_width=self.get_allocation().width or self.config.WINDOW_WIDTH,
            zoom=self.zoom
        )
        aligned_x, aligned_y, _ = self._apply_alignment_snapping(canvas_x, canvas_y)
        snapped_x, snapped_y = aligned_x, aligned_y

        if n_press == 1:
            self.save_state()
            self.current_room_points.append((snapped_x, snapped_y))
            print(f"Added point to room: {snapped_x}, {snapped_y}")
            self.queue_draw()
        elif n_press == 2:
            self.save_state()
            if self.current_room_points and len(self.current_room_points) > 2:
                if self.current_room_points[0] != self.current_room_points[-1]:
                    self.current_room_points.append(self.current_room_points[0])
                new_room = self.Room(self.current_room_points)
                self.rooms.append(new_room)
                print(f"Finalized manual room with points: {self.current_room_points}")
                self.current_room_points = []
                self.current_room_preview = None
            for wall_set in self.wall_sets:
                if len(wall_set) < 3:
                    continue
                if self._is_closed_polygon(wall_set):
                    poly = [w.start for w in wall_set]
                    if self._point_in_polygon((snapped_x, snapped_y), poly):
                        new_room = self.Room(poly)
                        self.rooms.append(new_room)
                        print(f"Created room from wall set: {poly}")
                        break
            self.queue_draw()

    def _handle_wall_click(self, n_press, x, y):
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x, canvas_y = self.device_to_model(x, y, pixels_per_inch)
        raw_point = (canvas_x, canvas_y)

        last_wall = self.walls[-1] if self.walls else None
        canvas_width = self.get_allocation().width or self.config.WINDOW_WIDTH
        base_x, base_y = (canvas_x, canvas_y) if not self.drawing_wall else self.current_wall.start
        candidate_points = self._get_candidate_points()

        (snapped_x, snapped_y), self.snap_type = self.snap_manager.snap_point(
            canvas_x, canvas_y, base_x, base_y, self.walls, self.rooms,
            current_wall=self.current_wall, last_wall=last_wall,
            in_progress_points=candidate_points, canvas_width=canvas_width,
            zoom=self.zoom
        )
        self.raw_current_end = raw_point
        aligned_x, aligned_y, candidate = self._apply_alignment_snapping(canvas_x, canvas_y)
        snapped_x, snapped_y = aligned_x, aligned_y
        self.alignment_candidate = candidate

        if n_press == 1:
            if not self.drawing_wall:
                self.drawing_wall = True
                self.current_wall = self.Wall(
                    (snapped_x, snapped_y), (snapped_x, snapped_y),
                    self.config.DEFAULT_WALL_WIDTH, self.config.DEFAULT_WALL_HEIGHT
                )
                print(f"Drawing current wall of width: {self.config.DEFAULT_WALL_WIDTH}")
            else:
                self.walls.append(self.Wall(self.current_wall.start, (snapped_x, snapped_y),
                                            self.config.DEFAULT_WALL_WIDTH, self.config.DEFAULT_WALL_HEIGHT))
                self.current_wall.start = (snapped_x, snapped_y)
            self.queue_draw()

        elif n_press == 2:
            print(f"Double-click at ({snapped_x}, {snapped_y}), drawing_wall = {self.drawing_wall}")
            if self.drawing_wall and self.walls:
                self.save_state()
                self.current_wall.end = (snapped_x, snapped_y)
                self.walls.append(self.current_wall)
                self.wall_sets.append(self.walls.copy())
                self.save_state()
                self.walls = []
                self.current_wall = None
                self.drawing_wall = False
                self.snap_type = "none"
                self.alignment_candidate = None
                self.raw_current_end = None
            else:
                test_point = (snapped_x, snapped_y)
                for room in self.rooms:
                    if len(room.points) < 3:
                        continue
                    if self._point_in_polygon(test_point, room.points):
                        pts = room.points if room.points[0] == room.points[-1] else room.points + [room.points[0]]
                        new_wall_set = []
                        for i in range(len(pts) - 1):
                            new_wall = self.Wall(pts[i], pts[i+1],
                                                width=self.config.DEFAULT_WALL_WIDTH,
                                                height=self.config.DEFAULT_WALL_HEIGHT)
                            new_wall_set.append(new_wall)
                        self.wall_sets.append(new_wall_set)
                        print(f"Auto-created walls for room with points: {room.points}")
                        break
                self.snap_type = "none"
            self.queue_draw()
    
    def _handle_polyline_click(self, n_press: int, x: float, y: float) -> None:
        # 1. Convert to model coords
        ppi = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        mx, my = self.device_to_model(x, y, ppi)

        # 2. Snap & align
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
            # start or extend
            self.save_state()
            if not self.drawing_polyline:
                self.drawing_polyline = True
                self.current_polyline_start = snapped
                self.polylines = []
            else:
                seg = Polyline(self.current_polyline_start, snapped)
                self.polylines.append(seg)
                self.current_polyline_start = snapped
            self.queue_draw()
            self.current_polyline_preview = None

        elif n_press == 2 and self.drawing_polyline:
            # finalize
            self.save_state()
            if self.polylines:
                self.polyline_sets.append(self.polylines.copy())
            self.drawing_polyline = False
            self.current_polyline_start = None
            self.polylines = []
            self.queue_draw()
            self.current_polyline_preview = None

    def show_change_door_type_submenu(self, widget, selected_doors, parent_popover):
        # Create a popover to serve as the sub-menu
        popover = Gtk.Popover()
        
        # Create a vertical box to hold the menu items
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        popover.set_child(box)
        
        # Add a button for each door type
        door_types = ["single", "double", "sliding", "frame", "pocket", "bi-fold", "double bi-fold", "garage"]
        for dt in door_types:
            btn = Gtk.Button(label=dt)
            btn.connect("clicked", lambda btn, dt=dt: self.on_change_door_type_selected(dt, selected_doors, popover, parent_popover))
            box.append(btn)
        
        # Set the popover's parent to the "Change Door Type" button (widget)
        popover.set_parent(widget)
        
        # Position the popover relative to the button
        allocation = widget.get_allocation()
        rect = Gdk.Rectangle()
        rect.x = allocation.width  # Relative to the button’s left edge
        rect.y = allocation.height  # Below the button
        rect.width = 1
        rect.height = 1
        
        popover.set_pointing_to(rect)
        
        # Show the popover
        popover.popup()

    def on_change_door_type_selected(self, new_type, selected_doors, popover, parent_popover):
        for door_item in selected_doors:
            wall, door, ratio = door_item["object"]
            door.door_type = new_type
        self.queue_draw()
        popover.popdown()  # Hide the sub-menu popover
        parent_popover.popdown()  # Hide the parent right-click popover
        
    def show_change_window_type_submenu(self, widget, selected_windows, parent_popover):
        # Create a popover to serve as the sub-menu
        popover = Gtk.Popover()
        
        # Create a vertical box to hold the menu items
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        popover.set_child(box)
        
        # Add a button for each door type
        window_types = ["sliding", "fixed", "double-hung"]
        for dt in window_types:
            btn = Gtk.Button(label=dt)
            btn.connect("clicked", lambda btn, dt=dt: self.on_change_window_type_selected(dt, selected_windows, popover, parent_popover))
            box.append(btn)
        
        # Set the popover's parent to the "Change Door Type" button (widget)
        popover.set_parent(widget)
        
        # Position the popover relative to the button
        allocation = widget.get_allocation()
        rect = Gdk.Rectangle()
        rect.x = allocation.width  # Relative to the button’s left edge
        rect.y = allocation.height  # Below the button
        rect.width = 1
        rect.height = 1
        
        popover.set_pointing_to(rect)
        
        # Show the popover
        popover.popup()
    
    def on_change_window_type_selected(self, new_type, selected_windows, popover, parent_popover):
        for window_item in selected_windows:
            wall, window, ratio = window_item["object"]
            window.window_type = new_type
        self.queue_draw()
        popover.popdown()  # Hide the sub-menu popover
        parent_popover.popdown()  # Hide the parent right-click popover

    def set_ext_int(self, selected_walls, state, popover):
            for wall in selected_walls:
                wall["object"].exterior_wall = state
            self.queue_draw()
            popover.popdown()
    
    def toggle_door_orientation(self, selected_doors, popover, inswing=False, outswing=False):
        for door_item in selected_doors:
            wall, door, ratio = door_item["object"]
            if inswing == True:
                door.orientation = "inswing"
            elif outswing == True:
                door.orientation = "outswing"
            else:
                door.orientation = "inswing" if door.orientation == "outswing" else "outswing"
        self.queue_draw()
        popover.popdown()
    
    def toggle_door_swing(self, selected_doors, popover):
        for door_item in selected_doors:
            wall, door, ratio = door_item["object"]
            door.swing = "left" if door.swing == "right" else "right"
        self.queue_draw()
        popover.popdown()