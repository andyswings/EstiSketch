import math
from gi.repository import Gtk, Gdk

class CanvasSelectionMixin:
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
            
            # Skip invalid entries
            if wall is None:
                continue

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
                break  # Exit loop
        # Check windows
        for window_item in self.windows:
            wall, window, ratio = window_item
            
            # Skip invalid entries
            if wall is None:
                continue
            
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
        
        # Check Dimensions
        if selected_item is None:
            for dimension in self.dimensions:
                # Check if click is near the dimension line
                # Calculate dimension line position
                start = dimension.start
                end = dimension.end
                offset = dimension.offset
                
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                length = math.hypot(dx, dy)
                
                if length == 0:
                    continue
                
                # Perpendicular unit vector
                ux = dx / length
                uy = dy / length
                px = -uy
                py = ux
                
                # Dimension line endpoints
                dim_start = (start[0] + offset * px, start[1] + offset * py)
                dim_end = (end[0] + offset * px, end[1] + offset * py)
                
                # Convert to device coordinates
                dim_start_dev = self.model_to_device(dim_start[0], dim_start[1], pixels_per_inch)
                dim_end_dev = self.model_to_device(dim_end[0], dim_end[1], pixels_per_inch)
                
                # Check distance to dimension line
                dist = self.distance_point_to_segment(click_pt, dim_start_dev, dim_end_dev)
                if dist < fixed_threshold:
                    selected_item = {"type": "dimension", "object": dimension}
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
                
            # Check for door/window dragging
            if len(self.selected_items) > 0:
                # Handle single selection drag for doors/windows
                item = self.selected_items[0]
                if item["type"] in ["door", "window"]:
                    wall, obj, ratio = item["object"]
                    if wall is not None:  # Only drag if on a wall
                        self.dragging_door_window = item
                        self.dragging_door_window_start_ratio = ratio
                        
                        # Store drag start coordinates (device space) explicitly
                        self.drag_start_x = start_x
                        self.drag_start_y = start_y
                        
                        # Calculate the cursor position in model coords at drag start
                        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
                        start_model_x, start_model_y = self.device_to_model(start_x, start_y, pixels_per_inch)
                        
                        # Calculate current window center position
                        A = wall.start
                        B = wall.end
                        window_center_x = A[0] + ratio * (B[0] - A[0])
                        window_center_y = A[1] + ratio * (B[1] - A[1])
                        
                        # Store offset from click to window center
                        self.drag_offset_x = window_center_x - start_model_x
                        self.drag_offset_y = window_center_y - start_model_y
                        
                        self.box_selecting = False
                
                # Check for wall dragging (only if not already dragging door/window)
                elif item["type"] == "wall" and not getattr(self, "dragging_door_window", None):
                    wall = item["object"]
                    self.dragging_wall = wall
                    
                    # Store original wall positions
                    self.wall_drag_original_start = wall.start
                    self.wall_drag_original_end = wall.end
                    
                    # Store drag start coordinates (device space)
                    self.drag_start_x = start_x
                    self.drag_start_y = start_y
                    
                    # Convert drag start to model coordinates
                    pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
                    self.wall_drag_start_model = self.device_to_model(start_x, start_y, pixels_per_inch)
                    
                    # Find all walls connected to this wall's endpoints
                    connected_start = []
                    connected_end = []
                    tol = getattr(self.config, "JOINT_SNAP_TOLERANCE", 0.25)
                    
                    for wall_set in self.wall_sets:
                        for w in wall_set:
                            if w is not wall:  # Don't include the dragged wall itself
                                # Check if other wall's start connects to dragged wall's start
                                if self._points_close(w.start, wall.start, tol):
                                    connected_start.append((w, "start"))
                                # Check if other wall's end connects to dragged wall's start
                                if self._points_close(w.end, wall.start, tol):
                                    connected_start.append((w, "end"))
                                # Check if other wall's start connects to dragged wall's end
                                if self._points_close(w.start, wall.end, tol):
                                    connected_end.append((w, "start"))
                                # Check if other wall's end connects to dragged wall's end
                                if self._points_close(w.end, wall.end, tol):
                                    connected_end.append((w, "end"))
                    
                    self.wall_drag_connected_start = connected_start
                    self.wall_drag_connected_end = connected_end
                    
                    self.box_selecting = False

        elif self.tool_mode == "add_text":
            self.drag_start_x = start_x
            self.drag_start_y = start_y
    
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
            self.save_state()
            return

        if getattr(self, "moving_text", None):
            self.moving_text = None
            self.moving_text_start_pos = None
            self.save_state()
            return
        if getattr(self, "dragging_door_window", None):
            # Finalize door/window drag and clear selection
            self.selected_items = []
            self.dragging_door_window = None
            self.dragging_door_window_start_ratio = None
            self.drag_offset_x = 0
            self.drag_offset_y = 0
            self.save_state()
            self.queue_draw()
            return
        
        if getattr(self, "dragging_wall", None):
            # Finalize wall drag and clear dragging state
            self.dragging_wall = None
            self.wall_drag_original_start = None
            self.wall_drag_original_end = None
            self.wall_drag_start_model = None
            self.wall_drag_connected_start = []
            self.wall_drag_connected_end = []
            self.save_state()
            self.queue_draw()
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
            
            # Check doors
            for door_item in self.doors:
                wall, door, ratio = door_item
                
                # Skip doors without a wall
                if wall is None:
                    continue
                
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
                
                # Skip windows without a wall
                if wall is None:
                    continue
                
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
            
            for dimension in self.dimensions:
                # Calculate dimension line position
                start = dimension.start
                end = dimension.end
                offset = dimension.offset
                
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                length = math.hypot(dx, dy)
                
                if length == 0:
                    continue
                
                # Perpendicular unit vector
                ux = dx / length
                uy = dy / length
                px = -uy
                py = ux
                
                # Dimension line endpoints
                dim_start = (start[0] + offset * px, start[1] + offset * py)
                dim_end = (end[0] + offset * px, end[1] + offset * py)
                
                if self.line_intersects_rect(dim_start, dim_end, rect):
                    new_selection.append({"type": "dimension", "object": dimension})

            
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

        # Standard Edit Operations (Copy/Cut/Paste)
        # Paste - Available if clipboard has content
        if self.clipboard:
            paste_btn = Gtk.Button(label="Paste")
            paste_btn.connect("clicked", lambda btn: (self.paste(), parent_popover.popdown()))
            box.append(paste_btn)
            
        # Copy/Cut - Available if items are selected
        if self.selected_items:
            copy_btn = Gtk.Button(label="Copy")
            copy_btn.connect("clicked", lambda btn: (self.copy_selected(), parent_popover.popdown()))
            box.append(copy_btn)
            
            cut_btn = Gtk.Button(label="Cut")
            cut_btn.connect("clicked", lambda btn: (self.cut_selected(), parent_popover.popdown()))
            box.append(cut_btn)
            
            # Add a separator if we have other options coming up
            separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            box.append(separator)
        
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
