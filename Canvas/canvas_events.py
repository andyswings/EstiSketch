import math
from gi.repository import Gtk, Gdk, GLib
from typing import List
from components import Wall, Door, Window, Polyline
import config
import random
import string
from Dialogs.length_input_dialog import create_length_input_dialog

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
            print("Dimension tool is not implemented yet.")
        elif self.tool_mode == "add_text":
            self._handle_text_click(n_press, x, y)
    
    def _handle_text_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle simple click to create a default text box if no drag occurred.
        """
        # If we dragged, on_drag_end would have handled it. 
        # But commonly on_click (released) fires even after drag? 
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
        new_text = self.Text(canvas_x, canvas_y, content="Text", width=48.0, height=24.0, identifier=text_id)
        self.texts.append(new_text)
        self.existing_ids.append(text_id)
        
        # Select it
        self.selected_items = [{"type": "text", "object": new_text}]
        self.emit('selection-changed', self.selected_items)
        self.queue_draw()
        
        # Switch to pointer mode? Or stay in text mode?
        # Usually standard behavior is to stay, or switch. Let's stay.


    def generate_identifier(self, component_type: str, existing_ids: List[str]) -> str:
        ''' Generate a unique identifier for a component.
    
         The identifier format is: {component_type}-{8 chars}-{4 chars}-{4 chars}-{4 chars}-{12 chars}
         
         Example: wall-A1B2C3D4-E5F6-G7H8-I9J0-K1L2M3N4O5P6
         
         Parameters:
             component_type (str): The type of component (e.g., "wall", "door").
             existing_ids (List[str]): List of existing identifiers to ensure uniqueness.'''
        characters = string.ascii_letters + string.digits
        while True:
            pt1 = ''.join(random.choices(characters, k=8))
            pt2 = ''.join(random.choices(characters, k=4))
            pt3 = ''.join(random.choices(characters, k=4))
            pt4 = ''.join(random.choices(characters, k=4))
            pt5 = ''.join(random.choices(characters, k=12))
            identifier = f"{component_type}-{pt1}-{pt2}-{pt3}-{pt4}-{pt5}".lower()
            if identifier not in existing_ids:
                return identifier
            
    
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
            new_door = Door(door_type, 96.0, 80.0, "left", "inswing", identifier=door_identifier)
        elif door_type == "double" or door_type == "sliding":
            new_door = Door(door_type, 72.0, 80.0, "left", "inswing", identifier=door_identifier)
        else:
            new_door = Door(door_type, 36.0, 80.0, "left", "inswing", identifier=door_identifier)
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
        new_window = Window(48.0, 36.0, window_type, identifier=window_identifier)
        self.existing_ids.append(window_identifier)
        self.windows.append((selected_wall, new_window, selected_ratio))
        self.queue_draw()

    
    def _handle_pointer_right_click(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        """
        Display a context menu (popover) at the pointer location for selected canvas items.

        This method is called when the user right-clicks on the canvas while using the pointer tool.
        It analyzes the current selection (walls, doors, windows, polylines) and dynamically builds
        a popover menu with relevant actions, such as setting wall exterior/interior, adding/removing
        footers, joining walls, changing door/window types, toggling door orientation/swing, and
        changing polyline styles.

        The popover is positioned at the click location and attached to the canvas. Selecting an action
        from the menu will apply the change to the selected items and update the canvas display.

        Args:
            gesture (Gtk.GestureClick): The gesture object for the right-click event.
            n_press (int): The number of presses (usually 1 for right-click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
        if len(self.selected_items) == 0 and not self.wall_sets:
            # If no items are selected AND no walls exist, do nothing.
            return
        
        # Filter selected items
        selected_walls = [item for item in self.selected_items if item.get("type") == "wall"]
        selected_doors = [item for item in self.selected_items if item.get("type") == "door"]
        selected_windows = [item for item in self.selected_items if item.get("type") == "window"]
        selected_polylines = [item for item in self.selected_items if item.get("type") == "polyline"]
        selected_texts = [item for item in self.selected_items if item.get("type") == "text"]

        # Create a popover to serve as the context menu
        parent_popover = Gtk.Popover()
        
        # Create a vertical box to hold the menu item(s)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        parent_popover.set_child(box)
        
        # Text options
        if selected_texts:
            # For brevity, let's just allow changing font size or something basic or just "Properties" (which opens dock)
            # Actually we can add "Edit Text" to open a dialog.
            edit_text_btn = Gtk.Button(label="Edit Text Content")
            edit_text_btn.connect("clicked", lambda btn: self.show_edit_text_dialog(selected_texts[0]["object"], parent_popover))
            box.append(edit_text_btn)
            
            # Additional text options can go here
        
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
        
        
        use_add_footer_button = False
        use_remove_footer_button = False
        for wall in selected_walls:
            print(f"Wall {wall['object'].start} to {wall['object'].end} has footer: {wall['object'].footer} and footer depth: {wall['object'].footer_depth} and footer offsets: {wall['object'].footer_left_offset}, {wall['object'].footer_right_offset}")
            print(f"Width: {wall['object'].width}, Height: {wall['object'].height}")
            if wall["object"].footer == False and use_add_footer_button == False:
                use_add_footer_button = True
            elif wall["object"].footer == True and use_remove_footer_button == False:
                use_remove_footer_button = True
        
        if use_add_footer_button:
            add_foot_btn = Gtk.Button(label="Add Footer")
            add_foot_btn.connect("clicked", lambda btn: self.add_remove_footer(selected_walls, parent_popover, state=True))
            box.append(add_foot_btn)
        
        if use_remove_footer_button:
            remove_foot_btn = Gtk.Button(label="Remove Footer")
            remove_foot_btn.connect("clicked", lambda btn: self.add_remove_footer(selected_walls, parent_popover, state=False))
            box.append(remove_foot_btn)
            
        
        # Create a button labeled "Join Walls"
        if len(selected_walls) >= 2:
            join_button = Gtk.Button(label="Join Walls")
            join_button.connect("clicked", lambda btn: self.join_selected_walls(parent_popover))
            box.append(join_button)

        # "Join Connected Walls" applies globally or to touched sets, so show it if any walls exist.
        if self.wall_sets:
            join_all_button = Gtk.Button(label="Join Connected Walls")
            join_all_button.connect("clicked", lambda btn: self.join_all_connected_walls(parent_popover))
            box.append(join_all_button)

        # Separate Walls button
        if len(selected_walls) > 0:
            sep_button = Gtk.Button(label="Separate Walls")
            sep_button.connect("clicked", lambda btn: self.separate_walls(parent_popover))
            box.append(sep_button)
            
        # Split Wall button (only if exactly one wall selected)
        if len(selected_walls) == 1:
            split_button = Gtk.Button(label="Split Wall")
            split_button.connect("clicked", lambda btn: self.split_wall(parent_popover))
            box.append(split_button)
        
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
        
        # Polyline-specific option
        if selected_polylines:
            polyline_button = Gtk.Button(label="Change Polyline Style")
            polyline_button.connect("clicked", lambda btn: self.toggle_polyline_style(selected_polylines, parent_popover, style="toggle"))
            box.append(polyline_button)
            
            if selected_polylines[0]["object"].style == "dashed":
                polyline_solid_button = Gtk.Button(label="Change Polyline(s) to Solid")
                polyline_solid_button.connect("clicked", lambda btn: self.toggle_polyline_style(selected_polylines, parent_popover, style="dashed"))
                box.append(polyline_solid_button)
            
            if selected_polylines[0]["object"].style == "solid":
                polyline_dashed_button = Gtk.Button(label="Change Polyline(s) to Dashed")
                polyline_dashed_button.connect("clicked", lambda btn: self.toggle_polyline_style(selected_polylines, parent_popover, style="solid"))
                box.append(polyline_dashed_button)
        
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
        
    
    def join_selected_walls(self, popover: Gtk.Popover) -> None:
        """
        Join the wall sets that contain the selected walls.
        This merges the entire chains that the selected walls belong to.
        """
        # 1. Gather distinct wall sets containing selected walls
        sets_to_merge = []
        for item in self.selected_items:
            if item.get("type") == "wall":
                wall = item["object"]
                for ws in self.wall_sets:
                    if wall in ws and ws not in sets_to_merge:
                        sets_to_merge.append(ws)
                        break
        
        if len(sets_to_merge) < 2:
            print("Need at least 2 distinct wall sets selected to join.")
            return

        # 2. Remove old sets from self.wall_sets
        for ws in sets_to_merge:
            if ws in self.wall_sets:
                self.wall_sets.remove(ws)
        
        # 3. Flatten walls
        walls_to_join = []
        for ws in sets_to_merge:
            walls_to_join.extend(ws)
            
        # 4. Merge into a new ordered set using greedy logic
        new_set = self._order_walls_into_chain(walls_to_join)
        
        # 5. Add back
        self.wall_sets.append(new_set)
        
        # Cleanup
        self.selected_items = []
        self.queue_draw()
        popover.popdown()

    def join_all_connected_walls(self, popover: Gtk.Popover) -> None:
        """
        Globally scan all wall sets and merge any that are connected.
        This effectively reconstructs the wall_sets based on geometric connectivity.
        """
        # 1. Flatten ALL walls
        all_walls = []
        for ws in self.wall_sets:
            all_walls.extend(ws)
        
        # 2. Rebuild sets based on connectivity
        self.wall_sets = self._group_walls_into_sets(all_walls)
        
        self.selected_items = []
        self.queue_draw()
        try:
            popover.popdown()
        except:
            pass

    def separate_walls(self, popover: Gtk.Popover) -> None:
        """
        Extract selected walls from their current sets.
        - Selected walls are grouped into new sets based on their connectivity.
        - Remaining unselected walls in affected sets are also regrouped.
        - Other unaffected sets remain unchanged.
        """
        selected_walls = [item["object"] for item in self.selected_items if item["type"] == "wall"]
        if not selected_walls:
            return

        affected_sets_indices = set()
        walls_to_keep_as_is = [] # Lists of walls (whole sets) that are not affected
        
        # Identify which sets are affected
        for i, wall_set in enumerate(self.wall_sets):
            is_affected = any(w in selected_walls for w in wall_set)
            if is_affected:
                affected_sets_indices.add(i)
            else:
                walls_to_keep_as_is.append(wall_set)

        # Gather 'remaining' walls from affected sets (those NOT selected)
        remaining_walls = []
        for i in affected_sets_indices:
            for w in self.wall_sets[i]:
                if w not in selected_walls:
                    remaining_walls.append(w)

        # Regroup the selected walls themselves
        new_selected_sets = self._group_walls_into_sets(selected_walls)
        
        # Regroup the remaining walls from affected sets
        new_remaining_sets = self._group_walls_into_sets(remaining_walls)
        
        # Combine everything
        self.wall_sets = walls_to_keep_as_is + new_selected_sets + new_remaining_sets
        
        # Clear selection and redraw
        self.selected_items = []
        self.queue_draw()
        try:
            popover.popdown()
        except:
            pass

    def split_wall(self, popover: Gtk.Popover) -> None:
        """
        Split a single selected wall into two connected walls at its midpoint.
        """
        selected_walls = [item["object"] for item in self.selected_items if item["type"] == "wall"]
        if len(selected_walls) != 1:
            return
            
        wall = selected_walls[0]
        
        # Calculate midpoint
        mid_x = (wall.start[0] + wall.end[0]) / 2
        mid_y = (wall.start[1] + wall.end[1]) / 2
        midpoint = (mid_x, mid_y)
        
        # Create two new walls
        # Wall 1: start -> midpoint
        w1 = self.Wall(wall.start, midpoint, wall.width, wall.height, 
                       getattr(wall, "exterior_wall", True), 
                       identifier=self.generate_identifier("wall", self.existing_ids))
        # Wall 2: midpoint -> end
        w2 = self.Wall(midpoint, wall.end, wall.width, wall.height, 
                       getattr(wall, "exterior_wall", True), 
                       identifier=self.generate_identifier("wall", self.existing_ids))
                       
        # Copy properties if needed (e.g., footer settings, materials)
        # Assuming Wall class has methods/attributes for these, or we rely on defaults/manual copy.
        # Ideally we should copy specific attributes.
        for attr in ["has_footer", "footer_depth", "footer_offset", "stud_spacing", "insulation_type", "fire_rating", "exterior_finish", "interior_finish"]:
             if hasattr(wall, attr):
                 val = getattr(wall, attr)
                 setattr(w1, attr, val)
                 setattr(w2, attr, val)

        self.existing_ids.extend([w1.identifier, w2.identifier])

        # Replace in wall_sets
        found = False
        for i, wall_set in enumerate(self.wall_sets):
            if wall in wall_set:
                idx = wall_set.index(wall)
                # Remove old wall
                wall_set.pop(idx)
                # Insert new walls. Order should be maintained if part of a chain.
                # Since w1 ends at midpoint and w2 starts at midpoint, inserting w1, w2 works if wall was Start->End.
                # If the wall was reversed in the chain logic, we might need care, but wall objects store absolute Start/End.
                # Inserting them in place usually works for the loop logic.
                wall_set.insert(idx, w2)
                wall_set.insert(idx, w1) 
                
                # Update any doors/windows on this wall?
                # This is complex. For now, drop openings on the split wall or try to reassign.
                # Moving forward without complex opening logic for now.
                found = True
                break
        
        if found:
            self.selected_items = []
            self.queue_draw()
            
        try:
            popover.popdown()
        except:
            pass

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
                tol = (getattr(self.config, "WALL_JOIN_TOLERANCE", 5.0)) / self.zoom
                
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
                        w.end = head_pt # Snap to exact point
                        component_walls.insert(0, w)
                        remaining.remove(w)
                        changed = True
                        break
                
                if changed: continue
                
                # Check neighbors for tail
                tail_pt = component_walls[-1].end
                for w in remaining:
                    if self._points_close(w.start, tail_pt, tol):
                        w.start = tail_pt # Snap to exact point
                        component_walls.append(w)
                        remaining.remove(w)
                        changed = True
                        break
                    elif self._points_close(w.end, tail_pt, tol):
                        w.start, w.end = w.end, w.start
                        w.start = tail_pt # Snap to exact point
                        component_walls.append(w)
                        remaining.remove(w)
                        changed = True
                        break
            
            sets.append(component_walls)
        return sets
        
    def _points_close(self, p1, p2, tol):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1]) < tol

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
                    joined.append(wall)
                    remaining.remove(wall)
                    extended = True
                    break
                elif self._points_close(wall.end, last_point, tol):
                    wall.start, wall.end = wall.end, wall.start
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
                    joined.insert(0, wall)
                    remaining.remove(wall)
                    extended = True
                    break
                elif self._points_close(wall.start, first_point, tol):
                    wall.start, wall.end = wall.end, wall.start
                    joined.insert(0, wall)
                    remaining.remove(wall)
                    extended = True
                    break
                    
        # Any remaining walls are disjoint from the main chain we found.
        # We'll just append them (butt joins likely) to avoid losing data.
        if remaining:
            print(f"Warning: {len(remaining)} walls could not be linked to the main chain.")
            joined.extend(remaining)
            
        return joined





        
            
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
                # Also update properties dock if open?
                # The dock listens to selection change, but maybe not content change on same object?
                # It's fine for now.
            d.destroy()
            
        dialog.connect("response", on_response)

    def _handle_pointer_click(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        """
        Handle pointer-tool clicks to select canvas items or begin wall-handle editing.

        Summary:
        - If the click is on a handle of an already-selected wall endpoint, start endpoint editing:
          sets self.editing_wall and self.editing_handle ("start" or "end"). The selection entry for
          this is {"type": "wall_handle", "object": (wall, handle_name)}.
        - Otherwise detect and select the nearest canvas object (wall segment or endpoint, room vertex,
          door, window, or polyline segment) using device-space thresholds and snapping-aware transforms.
        - Polyline selection entries include "identifier" and "_obj_id" when available to allow robust
          deletion/matching.
        - Small pointer movement between press and click is ignored to avoid accidental drags.
        - Supports multi-selection when Shift is held; without Shift selection is replaced.

        Args:
            gesture (Gtk.GestureClick): The gesture object for the click event.
            n_press (int): The number of presses (usually 1 for a single click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
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
        
        # Check for wall handle clicks (for editing)
        T = self.zoom * pixels_per_inch
        for item in self.selected_items:
            if item["type"] == "wall":
                wall = item["object"]
                for handle_name, pt in [("start", wall.start), ("end", wall.end)]:
                    pt_widget = (
                        (pt[0] * T) + self.offset_x,
                        (pt[1] * T) + self.offset_y
                    )
                    dist = math.hypot(click_pt[0] - pt_widget[0], click_pt[1] - pt_widget[1])
                    if dist < self.handle_radius:
                        # Start editing this wall's handle
                        self.editing_wall = wall
                        self.editing_handle = handle_name
                        selected_item = {"type": "wall_handle", "object": (wall, handle_name)}
                        break
            if selected_item:
                break

        # T = self.zoom * pixels_per_inch
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
        
        for poly_list in self.polyline_sets:
            for pl in poly_list:
                # transform endpoints from model to widget coords
                p1 = self.model_to_device(pl.start[0], pl.start[1], pixels_per_inch)
                p2 = self.model_to_device(pl.end[0],   pl.end[1],   pixels_per_inch)
                # distance from click to segment
                if self.distance_point_to_segment(click_pt, p1, p2) < fixed_threshold:
                    selected_item = {
                        "type": "polyline", 
                        "object": pl, 
                        "identifier": getattr(pl, "identifier", None), 
                        "_obj_id": id(pl)
                    }
                    break
                    break
            if selected_item: break
            
        # Check Texts
        if selected_item is None:
            for text in self.texts:
                # Text hit test: check if click is within bounding box
                # text.x, text.y is top-left in model space
                # text.width, text.height are dimensions in model space (inches)
                
                x_dev, y_dev = self.model_to_device(text.x, text.y, pixels_per_inch)
                w_dev = text.width * T
                h_dev = text.height * T
                
                # Simple AABB check
                if (x_dev <= click_pt[0] <= x_dev + w_dev) and (y_dev <= click_pt[1] <= y_dev + h_dev):
                    selected_item = {"type": "text", "object": text}
                    break


        event = gesture.get_current_event()
        state = event.get_modifier_state() if hasattr(event, "get_modifier_state") else event.state
        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if selected_item:
            if shift_pressed:
                if not any(self.same_selection(existing["object"], selected_item["object"]) for existing in self.selected_items):
                    self.selected_items.append(selected_item)
            else:
                self.selected_items = [selected_item]
        else:
            if not shift_pressed:
                self.selected_items = []
        self.emit('selection-changed', self.selected_items)
        self.queue_draw()


    def distance_point_to_segment(self, P: tuple[float, float], A: tuple[float, float], B: tuple[float, float]) -> float:
        """
        Calculate the shortest distance from a point to a line segment.

        Given a point P and a segment defined by endpoints A and B, this method computes
        the minimum Euclidean distance from P to any point on the segment AB. If the segment
        is degenerate (A and B are the same), it returns the distance from P to A.

        Args:
            P (tuple[float, float]): The point as (x, y).
            A (tuple[float, float]): The start point of the segment as (x, y).
            B (tuple[float, float]): The end point of the segment as (x, y).

        Returns:
            float: The shortest distance from P to the segment AB.
        """
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
    
    
    def line_intersects_rect(self, A: tuple[float, float], B: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
        """
        Determine if a line segment intersects a rectangle.

        Checks whether the line segment defined by endpoints A and B crosses or touches
        the rectangle specified by rect = (rx1, ry1, rx2, ry2), where (rx1, ry1) is the
        top-left corner and (rx2, ry2) is the bottom-right corner. The function returns
        True if the segment is inside the rectangle or intersects any of its edges.

        Args:
            A (tuple[float, float]): Start point of the line segment (x, y).
            B (tuple[float, float]): End point of the line segment (x, y).
            rect (tuple[float, float, float, float]): Rectangle as (rx1, ry1, rx2, ry2).

        Returns:
            bool: True if the segment intersects or is contained in the rectangle, False otherwise.
        """
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


    def on_drag_begin(self, gesture: Gtk.Gesture, start_x: float, start_y: float) -> None:
        """
        Handle the beginning of a drag gesture on the canvas.

        This method is called when the user starts dragging with the mouse or pointer.
        It initializes state for either panning (moving the canvas view) or box selection
        (selecting multiple items with a rectangular area), depending on the current tool mode.
        For box selection, it also checks if the Shift key is held to extend the selection.

        Args:
            gesture (Gtk.Gesture): The gesture object for the drag event.
            start_x (float): The x-coordinate where the drag started.
            start_y (float): The y-coordinate where the drag started.

        Returns:
            None
        """
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        
        # If we already entered handle-editing on press, don't overwrite box_select_start.
        if getattr(self, "editing_wall", None) and getattr(self, "editing_handle", None):
            # Keep box_select_start set by on_click_pressed (model coords of endpoint).
            # No further initialization required for editing; on_drag_update will handle motion.
            return
        
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
            self.box_select_end = self.box_select_start
            event = gesture.get_current_event()
            state = event.get_modifier_state() if hasattr(event, "get_modifier_state") else event.state
            self.box_select_extend = bool(state & Gdk.ModifierType.SHIFT_MASK)
            
            # If we are moving or rotating text, cancel box selection
            if getattr(self, "moving_text", None) or getattr(self, "rotating_text", None):
                self.box_selecting = False
        elif self.tool_mode == "add_text":
            self.drag_start_x = start_x
            self.drag_start_y = start_y
            # self.drag_active = True # Don't set here, set in update to distinguish click from drag
            

    def on_drag_update(self, gesture: Gtk.Gesture, offset_x: float, offset_y: float) -> None:
        """
        Handle updates during a drag gesture on the canvas.

        This method is invoked repeatedly while the user drags. It supports three behaviors:
        - Wall endpoint editing: if a wall handle is active (self.editing_wall and self.editing_handle),
          compute the new endpoint in model coordinates from the drag offsets, update the edited wall,
          propagate the motion to any connected walls via _update_connected_walls(), and request a redraw.
        - Panning: when the current tool is "panning", update canvas offsets to move the view.
        - Box selection: when using the pointer tool and box selection is active, update the selection
          rectangle end coordinates for live feedback and redraw.

        The method converts drag offsets into model-space movement using the current zoom and
        PIXELS_PER_INCH config, updates relevant state, and queues a redraw as needed.

        Args:
            gesture (Gtk.Gesture): The gesture object for the drag event.
            offset_x (float): The horizontal offset from the drag start position.
            offset_y (float): The vertical offset from the drag start position.

        Returns:
            None
        """
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        
        # Handle wall endpoint editing
        if getattr(self, "editing_wall", None) and getattr(self, "editing_handle", None):
            # Use the ORIGINAL joint position and the TOTAL drag offset
            T = self.zoom * pixels_per_inch
            origin = getattr(self, "joint_drag_origin", self.editing_wall.start)

            new_x = origin[0] + (offset_x / T)
            new_y = origin[1] + (offset_y / T)
            
            # --- Angle Snapping Logic ---
            best_snap = (new_x, new_y)
            
            # Check against anchors of all connected walls
            for wall_obj, endpoint_name in getattr(self, "connected_endpoints", []):
                # The anchor is the OTHER end of the wall
                anchor = wall_obj.end if endpoint_name == "start" else wall_obj.start
                
                # Try snapping to angle relative to this anchor
                snap_pt, snap_type = self.snap_manager.snap_to_angle(new_x, new_y, anchor[0], anchor[1])
                
                if snap_type != "none":
                    best_snap = snap_pt
                    break # Snap to the first valid alignment we find
            
            new_point = best_snap

            # Move all connected endpoints to this joint position
            for wall_obj, endpoint_name in getattr(self, "connected_endpoints", []):
                if endpoint_name == "start":
                    wall_obj.start = new_point
                else:
                    wall_obj.end = new_point

            self.queue_draw()
            return
        
        # Handle text rotation
        if getattr(self, "rotating_text", None):
            pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
            
            # Current mouse position in device coords
            # Use click_start which was set in on_click_pressed
            if not hasattr(self, "click_start"):
                return
            
            start_x, start_y = self.click_start
            current_x = start_x + offset_x
            current_y = start_y + offset_y
            
            # Calculate current angle from center to mouse
            center_x, center_y = self.rotation_center
            current_mouse_angle = math.degrees(math.atan2(current_y - center_y, current_x - center_x))
            
            # Calculate rotation delta
            angle_delta = current_mouse_angle - self.rotation_start_mouse_angle
            
            # Update text rotation
            new_rotation = self.rotation_start_angle + angle_delta
            
            # Normalize to -180 to 180 range
            while new_rotation > 180:
                new_rotation -= 360
            while new_rotation < -180:
                new_rotation += 360
            
            self.rotating_text.rotation = new_rotation
            
            # Update sidebar rotation spinner if properties dock is available
            if hasattr(self, "properties_dock") and self.properties_dock:
                text_page = self.properties_dock.text_page
                if text_page.current_text == self.rotating_text:
                    # Block the handler to prevent feedback loop
                    text_page._block_updates = True
                    text_page.rotation_spin.set_value(new_rotation)
                    text_page._block_updates = False
            
            self.queue_draw()
            return
        
        if getattr(self, "moving_text", None):
            pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
            T = self.zoom * pixels_per_inch
            
            # offset in model units
            dx = offset_x / T
            dy = offset_y / T
            
            start_x, start_y = self.moving_text_start_pos
            self.moving_text.x = start_x + dx
            self.moving_text.y = start_y + dy
            
            self.queue_draw()
            return
            
        if self.tool_mode == "panning":
            self.offset_x = self.last_offset_x + offset_x
            self.offset_y = self.last_offset_y + offset_y
            self.queue_draw()
        elif self.tool_mode == "pointer" and self.box_selecting:
            current_x = self.box_select_start[0] + (offset_x / (self.zoom * pixels_per_inch))
            current_y = self.box_select_start[1] + (offset_y / (self.zoom * pixels_per_inch))
            self.box_select_end = (current_x, current_y)
            self.queue_draw()
        elif self.tool_mode == "add_text" and hasattr(self, "drag_start_x"):
            self.drag_active = True # user is dragging
            # Calculate rect
            current_x = self.drag_start_x + offset_x
            current_y = self.drag_start_y + offset_y
            
            # Convert to model
            pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
            start_m_x, start_m_y = self.device_to_model(self.drag_start_x, self.drag_start_y, pixels_per_inch)
            curr_m_x, curr_m_y = self.device_to_model(current_x, current_y, pixels_per_inch)
            
            w = abs(curr_m_x - start_m_x)
            h = abs(curr_m_y - start_m_y)
            x = min(start_m_x, curr_m_x)
            y = min(start_m_y, curr_m_y)
            
            self.current_text_preview = (x, y, w, h)
            self.queue_draw()
            

    def on_drag_end(self, gesture: Gtk.Gesture, offset_x: float, offset_y: float) -> None:
        """
        Handle the end of a drag gesture on the canvas.

        This method is called when the user releases the mouse or pointer after dragging.
        If the pointer tool and box selection are active, it finalizes the selection rectangle,
        determines which canvas items (walls, vertices, doors, windows, polylines) are within or intersect
        the selection area, and updates the selection. Supports extending the selection with Shift.

        Args:
            gesture (Gtk.Gesture): The gesture object for the drag event.
            offset_x (float): The horizontal offset from the drag start position.
            offset_y (float): The vertical offset from the drag start position.

        Returns:
            None
        """
        
        # If we were editing a wall endpoint, just clear that state and stop.
        if getattr(self, "editing_wall", None) and getattr(self, "editing_handle", None):
            self.editing_wall = None
            self.editing_handle = None
            self.connected_endpoints = []
            self.connected_endpoints = []
            self.joint_drag_origin = None
            return

        if getattr(self, "rotating_text", None):
            self.rotating_text = None
            self.rotation_start_angle = None
            self.rotation_center = None
            self.rotation_start_mouse_angle = None
            return

        if getattr(self, "moving_text", None):
            self.moving_text = None
            return
        
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
            
            for poly_list in self.polyline_sets:
                for pl in poly_list:
                    if self.line_intersects_rect(pl.start, pl.end, rect):
                        new_selection.append({"type": "polyline", "object": pl, "identifier": pl.identifier})
            
            for poly_list in self.polyline_sets:
                for pl in poly_list:
                    if self.line_intersects_rect(pl.start, pl.end, rect):
                        new_selection.append({"type": "polyline", "object": pl, "identifier": pl.identifier})
            
            for text in self.texts:
                tx1 = text.x
                ty1 = text.y
                tx2 = text.x + text.width
                ty2 = text.y + text.height
                
                # Check intersection (if NOT disjoint)
                if not (tx2 < x1 or tx1 > x2 or ty2 < y1 or ty1 > y2):
                    new_selection.append({"type": "text", "object": text})

            if hasattr(self, "box_select_extend") and self.box_select_extend:
                for item in new_selection:
                    if not any(existing["type"] == item["type"] and self.same_selection(existing["object"], item["object"])
                            for existing in self.selected_items):
                        self.selected_items.append(item)
            else:
                self.selected_items = new_selection
            self.emit('selection-changed', self.selected_items)
            
            self.box_selecting = False
            self.editing_wall = None
            self.editing_handle = None
            self.queue_draw()
        elif self.tool_mode == "add_text" and hasattr(self, "drag_start_x"):
            if hasattr(self, "current_text_preview"):
                x, y, w, h = self.current_text_preview
                # Ensure minimum size
                if w > 1 and h > 1:
                    text_id = self.generate_identifier("text", self.existing_ids)
                    new_text = self.Text(x, y, content="Text", width=w, height=h, identifier=text_id)
                    self.texts.append(new_text)
                    self.existing_ids.append(text_id)
                    self.selected_items = [{"type": "text", "object": new_text}]
                    self.emit('selection-changed', self.selected_items)
                
                del self.current_text_preview
            if hasattr(self, "drag_start_x"):
                del self.drag_start_x
            # self.drag_active = False # REMOVED: Do not reset here, wait for click release to check it
            self.queue_draw()
            self.box_selecting = False
            self.editing_wall = None
            self.editing_handle = None
            self.queue_draw()
            
    
    def _get_candidate_points(self) -> List[tuple[float, float]]:
        """
        Collect all candidate points for snapping and alignment.

        This method gathers all wall endpoints from all wall sets on the canvas.
        The returned list is used for snapping logic and alignment assistance when drawing
        or editing walls, rooms, or polylines.

        Returns:
            List[Tuple[float, float]]: A list of (x, y) tuples representing wall endpoints.
        """
        return [point for wall_set in self.wall_sets for wall in wall_set for point in (wall.start, wall.end)]
    

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
            self.queue_draw()
        elif n_press == 2:
            self.save_state()
            if self.current_room_points and len(self.current_room_points) > 2:
                if self.current_room_points[0] != self.current_room_points[-1]:
                    self.current_room_points.append(self.current_room_points[0])
                new_room = self.Room(self.current_room_points)
                self.rooms.append(new_room)
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
                        break
            self.queue_draw()
            

    def enter_wall_length(self):
        """Open a dialog to enter precise wall length."""
        if self.tool_mode != "draw_walls" or not self.drawing_wall or not self.current_wall:
            return

        dialog = create_length_input_dialog(self.get_root())
        dialog.connect("response", self.on_length_input_response)
        dialog.present()

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

    def apply_wall_length(self, length):
        if not self.current_wall: return

        start_x, start_y = self.current_wall.start
        
        # Determine angle
        if self.auto_dimension_mode and self.last_wall_angle is not None:
             angle = self.last_wall_angle + (math.pi / 2)
        else:
             pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
             if hasattr(self, "mouse_x") and hasattr(self, "mouse_y"):
                 mx, my = self.device_to_model(self.mouse_x, self.mouse_y, pixels_per_inch)
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
            identifier=self.generate_identifier("wall", self.existing_ids)
        )
        
        self.existing_ids.append(wall_instance.identifier)
        self.walls.append(wall_instance)
        
        # Update state for next segment
        self.current_wall.start = (end_x, end_y)
        self.current_wall.end = (end_x, end_y)
        self.last_wall_angle = angle
        
        self.queue_draw()

    def _handle_wall_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle click events for drawing walls on the canvas.

        This method is called when the user clicks while the wall drawing tool is active.
        On a single click, it starts or extends a wall segment, snapping and aligning the endpoint.
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
            self.auto_dimension_mode = False
            wall_instance = None
            if not self.drawing_wall:
                self.drawing_wall = True
                self.current_wall = self.Wall(
                    (snapped_x, snapped_y), (snapped_x, snapped_y),
                    self.config.DEFAULT_WALL_WIDTH, self.config.DEFAULT_WALL_HEIGHT,
                    identifier=self.generate_identifier("wall", self.existing_ids)
                )
            else:
                wall_instance = self.Wall(
                    self.current_wall.start, (snapped_x, snapped_y),
                    self.config.DEFAULT_WALL_WIDTH, self.config.DEFAULT_WALL_HEIGHT,
                    identifier=self.generate_identifier("wall", self.existing_ids)
                )
            if wall_instance:
                self.existing_ids.append(wall_instance.identifier)
                self.walls.append(wall_instance)
                
                # Update angle
                dx = wall_instance.end[0] - wall_instance.start[0]
                dy = wall_instance.end[1] - wall_instance.start[1]
                self.last_wall_angle = math.atan2(dy, dx)
                
                self.current_wall.start = (snapped_x, snapped_y)
                self.queue_draw()

        elif n_press == 2:
                if self.drawing_wall and self.walls:
                    self.save_state()
                    self.current_wall.end = (snapped_x, snapped_y)
                    if self.current_wall.start != self.current_wall.end:
                        duplicate = any(
                            w.start == self.current_wall.start and w.end == self.current_wall.end
                            for w in self.walls
                        )
                        if not duplicate:
                            self.walls.append(self.current_wall)
                        
                    else:
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
                    break
            self.snap_type = "none"
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
            # start or extend
            self.save_state()
            if not self.drawing_polyline:
                self.drawing_polyline = True
                self.current_polyline_start = snapped
                self.polylines = []
            else:
                polyline_identifier = self.generate_identifier("polyline", self.existing_ids)
                seg = Polyline(self.current_polyline_start, snapped, identifier=polyline_identifier)
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
            # finalize
            self.save_state()
            if self.polylines:
                self.polyline_sets.append(self.polylines.copy())
            self.drawing_polyline = False
            self.current_polyline_start = None
            self.polylines = []
            self.queue_draw()
            self.current_polyline_preview = None
            

    def show_change_door_type_submenu(self, widget: Gtk.Widget, selected_doors: list, parent_popover: Gtk.Popover) -> None:
        """
        Display a submenu popover for changing the type of selected doors.

        This method creates a popover menu anchored to the provided widget, listing all available door types.
        When a door type button is clicked, the selected doors are updated to the new type and both the submenu
        and parent popover are closed.

        Args:
            widget: The Gtk widget to anchor the submenu popover to.
            selected_doors: List of selected door items to update.
            parent_popover: The parent popover to close after selection.

        Returns:
            None
        """
        popover = Gtk.Popover()
        
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
        

    def on_change_door_type_selected(self, new_type: str, selected_doors: list, popover: Gtk.Popover, parent_popover: Gtk.Popover) -> None:
        """
        Handle selection of a new door type from the submenu.

        Updates the door type for all selected doors, redraws the canvas, and closes both the submenu and parent popover.

        Args:
            new_type (str): The new door type to apply.
            selected_doors (list): List of selected door items to update.
            popover (Gtk.Popover): The submenu popover to close.
            parent_popover (Gtk.Popover): The parent popover to close.

        Returns:
            None
        """
        for door_item in selected_doors:
            wall, door, ratio = door_item["object"]
            door.door_type = new_type
        self.queue_draw()
        popover.popdown()  # Hide the sub-menu popover
        parent_popover.popdown()  # Hide the parent right-click popover
        
        
    def show_change_window_type_submenu(self, widget: Gtk.Widget, selected_windows: list, parent_popover: Gtk.Popover) -> None:
        """
        Display a submenu popover for changing the type of selected windows.

        This method creates a popover menu anchored to the provided widget, listing all available window types.
        When a window type button is clicked, the selected windows are updated to the new type and both the submenu
        and parent popover are closed.

        Args:
            widget (Gtk.Widget): The widget to anchor the submenu popover to.
            selected_windows (list): List of selected window items to update.
            parent_popover (Gtk.Popover): The parent popover to close after selection.

        Returns:
            None
        """
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
        
    
    def on_change_window_type_selected(self, new_type: str, selected_windows: list, popover: Gtk.Popover, parent_popover: Gtk.Popover) -> None:
        """
        Handle selection of a new window type from the submenu.

        Updates the window type for all selected windows, redraws the canvas, and closes both the submenu and parent popover.

        Args:
            new_type (str): The new window type to apply.
            selected_windows (list): List of selected window items to update.
            popover (Gtk.Popover): The submenu popover to close.
            parent_popover (Gtk.Popover): The parent popover to close.

        Returns:
            None
        """
        for window_item in selected_windows:
            wall, window, ratio = window_item["object"]
            window.window_type = new_type
        self.queue_draw()
        popover.popdown()  # Hide the sub-menu popover
        parent_popover.popdown()  # Hide the parent right-click popover
        
    
    def toggle_polyline_style(self, selected_polylines: list, popover: Gtk.Popover, style: str) -> None:
        """
        Toggle or set the style of selected polylines.

        This method updates the style ("solid" or "dashed") of all selected polylines based on the given style argument.
        If style is "toggle", it switches each polyline's style between "solid" and "dashed".
        After updating, it redraws the canvas and closes the popover.

        Args:
            selected_polylines (list): List of selected polyline items to update.
            popover (Gtk.Popover): The popover to close after the action.
            style (str): The style to apply ("solid", "dashed", or "toggle").

        Returns:
            None
        """
        if style == "dashed":
            for polyline in selected_polylines:
                polyline["object"].style = "solid"
            self.queue_draw()
            popover.popdown()
        elif style == "solid":
            for polyline in selected_polylines:
                polyline["object"].style = "dashed"
            self.queue_draw()
            popover.popdown()
        elif style == "toggle":
            for polyline in selected_polylines:
                polyline["object"].style = "dashed" if polyline["object"].style == "solid" else "solid"
            self.queue_draw()
            popover.popdown()
            

    def set_ext_int(self, selected_walls: list, state: str, popover: Gtk.Popover) -> None:
        """
        Set the exterior or interior state of selected walls.

        This method updates the 'exterior_wall' property of each selected wall to the given state (True for exterior, False for interior).
        After updating, it redraws the canvas and closes the popover.

        Args:
            selected_walls (list): List of selected wall items to update.
            state (str): The state to set ("True" for exterior, "False" for interior).
            popover (Gtk.Popover): The popover to close after the action.

        Returns:
            None
        """
        for wall in selected_walls:
            wall["object"].exterior_wall = state
        self.queue_draw()
        popover.popdown()
        
    
    def add_remove_footer(self, selected_walls: list, popover: Gtk.Popover, state: bool) -> None:
        """
        Add or remove a footer for selected walls.

        This method sets the 'footer' property of each selected wall to the given state (True to add, False to remove).
        After updating, it redraws the canvas and closes the popover.

        Args:
            selected_walls (list): List of selected wall items to update.
            popover (Gtk.Popover): The popover to close after the action.
            state (bool): The footer state to set (True for add, False for remove).

        Returns:
            None
        """
        for wall in selected_walls:
            wall["object"].footer = state
        print(f"Footer state set to {state} for selected walls.")
        # TODO : Implement footer rendering logic
        self.queue_draw()
        popover.popdown()
        
    
    def toggle_door_orientation(self, selected_doors: list, popover: Gtk.Popover, inswing: bool = False, outswing: bool = False) -> None:
        """
        Toggle or set the orientation of selected doors.

        This method updates the 'orientation' property of each selected door to "inswing" or "outswing"
        based on the provided arguments. If neither argument is True, it toggles the orientation.
        After updating, it redraws the canvas and closes the popover.

        Args:
            selected_doors (list): List of selected door items to update.
            popover (Gtk.Popover): The popover to close after the action.
            inswing (bool, optional): If True, set orientation to "inswing".
            outswing (bool, optional): If True, set orientation to "outswing".

        Returns:
            None
        """
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
        
    
    def toggle_door_swing(self, selected_doors: list, popover: Gtk.Popover) -> None:
        """
        Toggle the swing direction of selected doors.

        This method switches the 'swing' property of each selected door between "left" and "right".
        After updating, it redraws the canvas and closes the popover.

        Args:
            selected_doors (list): List of selected door items to update.
            popover (Gtk.Popover): The popover to close after the action.

        Returns:
            None
        """
        for door_item in selected_doors:
            wall, door, ratio = door_item["object"]
            door.swing = "left" if door.swing == "right" else "right"
        self.queue_draw()
        popover.popdown()
    
    
    def same_selection(self, a, b):
                    # compare by identity first
                    if a is b:
                        return True
                    # if either is a tuple (room, idx) compare by exact tuple equality
                    if isinstance(a, tuple) and isinstance(b, tuple):
                        return a == b
                    # fall back to identifier match if available
                    ida = getattr(a, "identifier", None)
                    idb = getattr(b, "identifier", None)
                    if ida and idb:
                        return ida == idb
                    return False
    
    
    def _points_close(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        tol: float | None = None,
    ) -> bool:
        """
        Return True if two model-space points are within a small tolerance.

        Args:
            p1, p2: Points in model space (inches).
            tol: Optional override tolerance in inches. If None, uses
                 config.JOINT_SNAP_TOLERANCE if present, otherwise 0.25".
        """
        if tol is None:
            tol = getattr(self.config, "JOINT_SNAP_TOLERANCE", 0.25)
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        return dx * dx + dy * dy <= tol * tol
