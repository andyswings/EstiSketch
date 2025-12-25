import math
from gi.repository import Gtk

class EditEventsMixin:
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
            
        # Handle wall dragging
        if getattr(self, "dragging_wall", None):
            pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
            T = self.zoom * pixels_per_inch
            
            # Calculate current position in model coordinates
            current_device_x = self.drag_start_x + offset_x
            current_device_y = self.drag_start_y + offset_y
            current_model = self.device_to_model(current_device_x, current_device_y, pixels_per_inch)
            
            # Calculate offset in model coordinates
            dx = current_model[0] - self.wall_drag_start_model[0]
            dy = current_model[1] - self.wall_drag_start_model[1]
            
            # Update wall positions
            wall = self.dragging_wall
            new_start = (self.wall_drag_original_start[0] + dx, self.wall_drag_original_start[1] + dy)
            new_end = (self.wall_drag_original_end[0] + dx, self.wall_drag_original_end[1] + dy)
            
            wall.start = new_start
            wall.end = new_end
            
            # Update connected walls at start point
            for wall_obj, endpoint_name in getattr(self, "wall_drag_connected_start", []):
                if endpoint_name == "start":
                    wall_obj.start = new_start
                else:
                    wall_obj.end = new_start
            
            # Update connected walls at end point
            for wall_obj, endpoint_name in getattr(self, "wall_drag_connected_end", []):
                if endpoint_name == "start":
                    wall_obj.start = new_end
                else:
                    wall_obj.end = new_end
            
            self.queue_draw()
            return
            
            
            
        # Handle door/window dragging  
        if getattr(self, "dragging_door_window", None):
            pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
            
            # Calculate current device position using stored start pos + offset (delta)
            current_device_x = self.drag_start_x + offset_x
            current_device_y = self.drag_start_y + offset_y
            
            # Convert to model coords using the helper function
            cursor_x, cursor_y = self.device_to_model(current_device_x, current_device_y, pixels_per_inch)
            
            # Apply the offset stored at drag start to get target position
            target_x = cursor_x + getattr(self, "drag_offset_x", 0)
            target_y = cursor_y + getattr(self, "drag_offset_y", 0)
            
            item = self.dragging_door_window
            wall, obj, ratio = item["object"]
            
            # Find nearest wall (could be current or different wall)
            best_wall = None
            best_ratio = 0.0
            best_dist = float('inf')
            snap_threshold = 24.0  # 24 inches for switching to different wall
            
            # Check all walls (iterate through wall_sets)
            for i, wall_set in enumerate(self.wall_sets):
                for j, check_wall in enumerate(wall_set):
                    dist = self.distance_point_to_segment((target_x, target_y), check_wall.start, check_wall.end)
                    
                    # Qualification check: Current wall is always valid, others must be within threshold
                    is_current_wall = (check_wall is wall)
                    is_valid_candidate = is_current_wall or (dist < snap_threshold)
                    
                    if is_valid_candidate:
                        # Optimization check: Is this strictly closer than the best we've found so far?
                        if dist < best_dist:
                            best_dist = dist
                            best_wall = check_wall
                            
                            # Calculate ratio on this wall
                            wx = check_wall.end[0] - check_wall.start[0]
                            wy = check_wall.end[1] - check_wall.start[1]
                            wall_len_sq = wx*wx + wy*wy
                            if wall_len_sq > 0:
                                dot = (target_x - check_wall.start[0]) * wx + (target_y - check_wall.start[1]) * wy
                                best_ratio = max(0.05, min(0.95, dot / wall_len_sq))  # Clamp to keep on wall
                            else:
                                best_ratio = 0.5
            
            # Update the object's wall and ratio
            if best_wall:
                # Update the tuple in the list
                if item["type"] == "door":
                    for i, door_tuple in enumerate(self.doors):
                        if door_tuple[1] is obj:
                            new_tuple = (best_wall, obj, best_ratio)
                            self.doors[i] = new_tuple
                            item["object"] = new_tuple
                            # Update selected_items to reference new tuple
                            for sel_item in self.selected_items:
                                if sel_item["type"] == "door" and sel_item["object"][1] is obj:
                                    sel_item["object"] = new_tuple
                            break
                elif item["type"] == "window":
                    for i, window_tuple in enumerate(self.windows):
                        if window_tuple[1] is obj:
                            new_tuple = (best_wall, obj, best_ratio)
                            self.windows[i] = new_tuple
                            item["object"] = new_tuple
                            # Update selected_items to reference new tuple
                            for sel_item in self.selected_items:
                                if sel_item["type"] == "window" and sel_item["object"][1] is obj:
                                    sel_item["object"] = new_tuple
                            break
            
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
            
    