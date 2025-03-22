import math
from gi.repository import Gtk, Gdk
from typing import List
from components import Wall, Door, Window


class CanvasEventsMixin:
    def on_click(self, gesture, n_press, x, y):
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
        """
        Handle a click event in 'add_doors' mode by adding a door on the wall nearest
        to the click point.

        The method converts the click position from widget to world coordinates, then
        iterates over existing wall sets to find a wall whose segment is within a small
        tolerance of the click. It computes the projection ratio along the wall (from 0.0 at
        the wall's start to 1.0 at the wall's end) where the door should be placed. A new
        Door object is created (using default attributes) and stored along with the target
        wall and position ratio in self.doors. Subsequent redraws will use the current state
        of each Door object to render the door on the wall.

        Parameters:
            n_press (int): The number of clicks (typically 1 for a single click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
        # Convert the widget (screen) coordinates to world coordinates.
        canvas_x = (x - self.offset_x) / self.zoom
        canvas_y = (y - self.offset_y) / self.zoom
        click_pt = (canvas_x, canvas_y)
        
        # Define a tolerance in world coordinates for detecting a click near a wall.
        tolerance = 10 / self.zoom  # Adjust as needed.
        best_dist = float('inf')
        selected_wall = None
        selected_ratio = None
        
        # Iterate through all finished walls in wall sets.
        for wall_set in self.wall_sets:
            for wall in wall_set:
                dist = self.distance_point_to_segment(click_pt, wall.start, wall.end)
                if dist < tolerance and dist < best_dist:
                    best_dist = dist
                    selected_wall = wall
                    # Compute projection ratio along the wall:
                    dx = wall.end[0] - wall.start[0]
                    dy = wall.end[1] - wall.start[1]
                    wall_length = math.hypot(dx, dy)
                    if wall_length > 0:
                        t = ((canvas_x - wall.start[0]) * dx + (canvas_y - wall.start[1]) * dy) / (wall_length ** 2)
                        # Clamp ratio to [0, 1]
                        selected_ratio = max(0.0, min(1.0, t))
                    else:
                        selected_ratio = 0.5  # default if degenerate wall.
        
        if selected_wall is None:
            print("No wall was found near the click for door addition.")
            return
        
        # Create a new Door object with default attributes.
        # (You can later expand this to allow the user to choose door types, etc.)
        new_door = Door("single", 36.0, 80.0, "left", "inward")
        
        # Add the door placement to the canvas.
        # Assume self.doors is a list initialized in CanvasArea.__init__.
        self.doors.append((selected_wall, new_door, selected_ratio))
        self.queue_draw()
    
    def _handle_window_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle a click event in 'add_windows' mode by adding a window on the wall nearest
        to the click point.

        The method converts the click position from widget to world coordinates, then
        iterates over existing wall sets to find a wall whose segment is within a small
        tolerance of the click. It computes the projection ratio along the wall (from 0.0 at
        the wall's start to 1.0 at the wall's end) where the window should be placed. A new
        Window object is created (using default attributes) and stored along with the target
        wall and position ratio in self.windows. Subsequent redraws will use the current state
        of each Window object to render the window on the wall.

        Parameters:
            n_press (int): The number of clicks (typically 1 for a single click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
        # Convert the widget (screen) coordinates to world coordinates.
        canvas_x = (x - self.offset_x) / self.zoom
        canvas_y = (y - self.offset_y) / self.zoom
        click_pt = (canvas_x, canvas_y)
        
        # Define a tolerance in world coordinates for detecting a click near a wall.
        tolerance = 10 / self.zoom  # Adjust as needed.
        best_dist = float('inf')
        selected_wall = None
        selected_ratio = None
        
        # Iterate through all finished walls in wall sets.
        for wall_set in self.wall_sets:
            for wall in wall_set:
                dist = self.distance_point_to_segment(click_pt, wall.start, wall.end)
                if dist < tolerance and dist < best_dist:
                    best_dist = dist
                    selected_wall = wall
                    # Compute projection ratio along the wall:
                    dx = wall.end[0] - wall.start[0]
                    dy = wall.end[1] - wall.start[1]
                    wall_length = math.hypot(dx, dy)
                    if wall_length > 0:
                        t = ((canvas_x - wall.start[0]) * dx + (canvas_y - wall.start[1]) * dy) / (wall_length ** 2)
                        # Clamp ratio to [0, 1]
                        selected_ratio = max(0.0, min(1.0, t))
                    else:
                        selected_ratio = 0.5  # default if degenerate wall.
        
        if selected_wall is None:
            print("No wall was found near the click for window addition.")
            return
        
        # Create a new Window object with default attributes.
        # (You can later expand this to allow the user to choose window types, etc.)
        new_window = Window(48.0, 36.0, "sliding")
        
        # Add the window placement to the canvas.
        # Assume self.windows is a list initialized in CanvasArea.__init__.
        self.windows.append((selected_wall, new_window, selected_ratio))
        self.queue_draw()

    
    def _handle_pointer_right_click(self, gesture, n_press, x, y):
        """
        Handle right-click events in pointer mode by displaying a context menu
        (using a Gtk.Popover) when two or more wall segments are selected.
        
        This context menu currently has a single entry ("Join Walls") that calls
        join_selected_walls() when activated.
        
        Parameters:
            gesture (Gtk.GestureClick): The gesture that triggered the right-click.
            n_press (int): The number of clicks.
            x (float): The x-coordinate of the click (in widget coordinates).
            y (float): The y-coordinate of the click (in widget coordinates).
        
        Returns:
            None
        """
        # Filter selected items to get only wall segments.
        selected_walls = [item for item in self.selected_items if item.get("type") == "wall"]

        # Create a popover to serve as the context menu.
        popover = Gtk.Popover()
        
        # Create a vertical box to hold the menu item(s).
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        popover.set_child(box)
        
        # Decide whether or not to create "Set as Exterior" or "Set as Interior" buttons
        use_ext_button = False
        use_int_button = False
        for wall in selected_walls:
            if wall["object"].exterior_wall == False and use_ext_button == False:
                use_ext_button = True
            elif wall["object"].exterior_wall == True and use_int_button == False:
                use_int_button = True
        
        def set_ext_int(selected_walls, state):
            for wall in selected_walls:
                wall["object"].exterior_wall = state
        
        if use_ext_button:
            ext_button = Gtk.Button(label="Set as Exterior")
            ext_button.connect("clicked", lambda btn: set_ext_int(selected_walls, True))
            box.append(ext_button)
        
        if use_int_button:
            int_button = Gtk.Button(label="Set as Interior")
            int_button.connect("clicked", lambda btn: set_ext_int(selected_walls, False))
            box.append(int_button)
            
        # Create a button labeled "Join Walls".
        join_button = Gtk.Button(label="Join Walls")
        join_button.connect("clicked", lambda btn: self.join_selected_walls())
        box.append(join_button)
        
        # Position the popover at the click location.
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        
        # Set the popover's parent to the canvas (self).
        popover.set_parent(self)
        
        # Show the popover.
        popover.show()
    
    def join_selected_walls(self) -> None:
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
            
    def on_click_pressed(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        self.click_start = (x, y)
    
    def _handle_pointer_click(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        """
        Handle a pointer click event when the pointer tool is active.

        This method processes a click by first checking if the click is actually part of a drag 
        (i.e. if the pointer has moved more than a small threshold from the initial click position).
        It then performs hit testing against the walls rendered on the canvas by converting the 
        click's widget (screen) coordinates into world coordinates and comparing the distances to each 
        wall's endpoints and segments. The wall that is closest to the click (within a fixed threshold) 
        is considered selected.

        If the SHIFT key is held down during the click, the selected item is added to the current 
        selection. Otherwise, the selection is replaced with the new item. Finally, the method requests 
        a redraw of the canvas so that any visual indicators of selection are updated.

        Parameters:
            gesture (Gtk.GestureClick): The gesture object representing the pointer click event.
            n_press (int): The number of clicks (e.g., 1 for single-click, 2 for double-click).
            x (float): The x-coordinate of the click in widget (screen) coordinates.
            y (float): The y-coordinate of the click in widget (screen) coordinates.

        Returns:
            None
        """
        # Check if this click is part of a drag by comparing current position to the initial click position.
        if hasattr(self, "click_start"):
            dx = x - self.click_start[0]  # Difference in x from where the click started.
            dy = y - self.click_start[1]  # Difference in y from where the click started.
            # If the movement is more than 5 pixels, consider it part of a drag; do not treat it as a simple click.
            if math.hypot(dx, dy) > 5:
                return

        # Store the click point in widget (screen) coordinates.
        click_pt = (x, y)
        fixed_threshold = 10  # Tolerance threshold in pixels for considering a click "close" to an item.
        best_dist = float('inf')  # Initialize best (smallest) distance found to infinity.
        selected_item = None  # This will hold the item (wall) that is the best candidate for selection.

        # Loop through each set of walls (each wall_set may represent connected segments).
        for wall_set in self.wall_sets:
            for wall in wall_set:
                # Convert the wall's start point from world coordinates to widget coordinates.
                start_widget = (
                    wall.start[0] * self.zoom + self.offset_x,
                    wall.start[1] * self.zoom + self.offset_y
                )
                # Convert the wall's end point from world coordinates to widget coordinates.
                end_widget = (
                    wall.end[0] * self.zoom + self.offset_x,
                    wall.end[1] * self.zoom + self.offset_y
                )

                # Compute the distance from the click to the start point of the wall.
                dist_start = math.hypot(click_pt[0] - start_widget[0],
                                        click_pt[1] - start_widget[1])
                # Compute the distance from the click to the end point of the wall.
                dist_end = math.hypot(click_pt[0] - end_widget[0],
                                    click_pt[1] - end_widget[1])
                # If the click is within threshold of the start point and closer than any previous candidate...
                if dist_start < fixed_threshold and dist_start < best_dist:
                    best_dist = dist_start  # Update best distance.
                    selected_item = {"type": "wall", "object": wall}  # Select this wall.
                # If the click is within threshold of the end point and closer than any previous candidate...
                if dist_end < fixed_threshold and dist_end < best_dist:
                    best_dist = dist_end  # Update best distance.
                    selected_item = {"type": "wall", "object": wall}  # Select this wall.

                # Also check the distance from the click to the wall segment (the line between start and end).
                dist_seg = self.distance_point_to_segment(click_pt, start_widget, end_widget)
                if dist_seg < fixed_threshold and dist_seg < best_dist:
                    best_dist = dist_seg  # Update best distance.
                    selected_item = {"type": "wall", "object": wall}  # Select this wall.

        # Retrieve the current event from the gesture to check for modifier keys.
        event = gesture.get_current_event()
        # Use get_modifier_state if available; otherwise, use event.state.
        state = event.get_modifier_state() if hasattr(event, "get_modifier_state") else event.state
        # Determine if the SHIFT key is pressed (used to extend the current selection).
        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)

        # Update the selection based on the hit test and whether SHIFT is held.
        if selected_item:
            if shift_pressed:
                # If SHIFT is pressed, add the new item to the current selection if it's not already selected.
                if not any(existing["object"] == selected_item["object"] for existing in self.selected_items):
                    self.selected_items.append(selected_item)
            else:
                # If SHIFT is not pressed, replace any existing selection with this new item.
                self.selected_items = [selected_item]
        else:
            # If no item was selected and SHIFT is not pressed, clear the current selection.
            if not shift_pressed:
                self.selected_items = []
        # Request a redraw of the canvas to update any visual selection indicators.
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
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        if self.tool_mode == "panning":
            self.drag_start_x = start_x
            self.drag_start_y = start_y
            self.last_offset_x = self.offset_x
            self.last_offset_y = self.offset_y
        elif self.tool_mode == "pointer":
            self.box_selecting = True
            self.box_select_start = ((start_x - self.offset_x) / self.zoom,
                                    (start_y - self.offset_y) / self.zoom)
            self.box_select_end = self.box_select_start
            event = gesture.get_current_event()
            state = event.get_modifier_state() if hasattr(event, "get_modifier_state") else event.state
            self.box_select_extend = bool(state & Gdk.ModifierType.SHIFT_MASK)



    def on_drag_update(self, gesture, offset_x, offset_y):
        if self.tool_mode == "panning":
            self.offset_x = self.last_offset_x + offset_x
            self.offset_y = self.last_offset_y + offset_y
            self.queue_draw()
        elif self.tool_mode == "pointer" and self.box_selecting:
            # Calculate current world position from offset:
            current_x = self.box_select_start[0] + (offset_x / self.zoom)
            current_y = self.box_select_start[1] + (offset_y / self.zoom)
            self.box_select_end = (current_x, current_y)
            self.queue_draw()
    
    def on_drag_end(self, gesture, offset_x, offset_y):
        if self.tool_mode == "pointer" and self.box_selecting:
            # Determine selection rectangle in world coordinates:
            x1 = min(self.box_select_start[0], self.box_select_end[0])
            y1 = min(self.box_select_start[1], self.box_select_end[1])
            x2 = max(self.box_select_start[0], self.box_select_end[0])
            y2 = max(self.box_select_start[1], self.box_select_end[1])
            rect = (x1, y1, x2, y2)
            
            # Helper function: Check if line segment (A,B) intersects the rectangle.
            def line_intersects_rect(A, B, rect):
                rx1, ry1, rx2, ry2 = rect
                
                def point_in_rect(pt):
                    x, y = pt
                    return rx1 <= x <= rx2 and ry1 <= y <= ry2
                
                if point_in_rect(A) or point_in_rect(B):
                    return True
                
                def segments_intersect(p, q, r, s):
                    def orientation(a, b, c):
                        val = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
                        if abs(val) < 1e-6:
                            return 0
                        return 1 if val > 0 else 2
                    
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
                
                # Define rectangle edges:
                edges = [
                    ((rx1, ry1), (rx2, ry1)),
                    ((rx2, ry1), (rx2, ry2)),
                    ((rx2, ry2), (rx1, ry2)),
                    ((rx1, ry2), (rx1, ry1))
                ]
                for edge in edges:
                    if segments_intersect(A, B, edge[0], edge[1]):
                        return True
                return False
            
            new_selection = []
            
            # Check wall segments: use intersection test
            for wall_set in self.wall_sets:
                for wall in wall_set:
                    if line_intersects_rect(wall.start, wall.end, rect):
                        new_selection.append({"type": "wall", "object": wall})
            
            # Check room vertices
            for room in self.rooms:
                for idx, pt in enumerate(room.points):
                    if (x1 <= pt[0] <= x2) and (y1 <= pt[1] <= y2):
                        new_selection.append({"type": "vertex", "object": (room, idx)})
            
            # If extending selection, add to the existing selection without duplicates
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

    def on_motion(self, controller: Gtk.EventControllerMotion, x: float, y: float) -> None: # This function is called when the mouse moves over the canvas.
        """
        Handle mouse movement events on the canvas and update the drawing preview.

        This method is invoked whenever the mouse moves over the canvas. It updates the current
        mouse position (in widget coordinates) and converts these coordinates into world coordinates.
        Based on the active tool mode, it then updates either the wall or room preview by applying
        snapping and alignment rules.

        In "draw_walls" mode:
        - Converts the pointer's widget coordinates (x, y) to world coordinates.
        - Stores the raw pointer world coordinate for potential reference.
        - Uses the snapping manager to adjust the pointer's position relative to the starting
            point of the current wall and candidate snapping points (from finalized walls and rooms).
        - Applies additional alignment snapping to further refine the pointer position.
        - Updates the end point of the current wall with the final snapped (and aligned) coordinates.
        - Requests a canvas redraw to update the wall preview.

        In "draw_rooms" mode:
        - Converts the pointer's widget coordinates (x, y) to world coordinates.
        - Determines a base point for snapping (using the last point of the current room, if available).
        - Collects candidate snapping points from finalized walls and current room points.
        - Uses the snapping manager to adjust the room point.
        - Applies alignment snapping to the raw pointer coordinate.
        - Updates the current room preview with the final snapped (and aligned) coordinates.
        - Requests a canvas redraw to update the room preview.

        Parameters:
            controller (Gtk.EventControllerMotion): The motion event controller that triggered this event.
            x (float): The x-coordinate of the mouse pointer in widget (screen) coordinates.
            y (float): The y-coordinate of the mouse pointer in widget (screen) coordinates.

        Returns:
            None
        """
        self.mouse_x = x
        self.mouse_y = y
        
        # Convert widget coordinates to model coordinates
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
        """Handle clicks in draw_rooms mode."""
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
                if len(wall_set) > 2 and self._is_closed_polygon(wall_set):
                    poly = [w.start for w in wall_set]
                    if self._point_in_polygon((snapped_x, snapped_y), poly):
                        new_room = self.Room(poly)
                        self.rooms.append(new_room)
                        print(f"Created room from wall set: {poly}")
                        break
            self.queue_draw()

    def _handle_wall_click(self, n_press, x, y):
        """Handle clicks in draw_walls mode."""
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