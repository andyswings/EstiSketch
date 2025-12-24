import math
from gi.repository import Gtk
from typing import List
from components import Wall

class CanvasWallMixin:
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
                # Removed save_state here - only save when wall set is finalized
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
                    self.walls = []
                    self.current_wall = None
                    self.drawing_wall = False
                    self.snap_type = "none"
                    self.alignment_candidate = None
                    self.raw_current_end = None
                    self.save_state()  # Save after cleanup to avoid state duplication
            else:
                # Double-click when NOT drawing walls: create walls from room
                test_point = (snapped_x, snapped_y)
                wall_created = False
                for room in self.rooms:
                    if len(room.points) < 3:
                        continue
                    if self._point_in_polygon(test_point, room.points):
                        pts = room.points if room.points[0] == room.points[-1] else room.points + [room.points[0]]
                        new_wall_set = []
                        for i in range(len(pts) - 1):
                            wall_id = self.generate_identifier("wall", self.existing_ids)
                            new_wall = self.Wall(pts[i], pts[i+1],
                                                width=self.config.DEFAULT_WALL_WIDTH,
                                                height=self.config.DEFAULT_WALL_HEIGHT,
                                                identifier=wall_id)
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
                else:
                    self.snap_type = "none"
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
    