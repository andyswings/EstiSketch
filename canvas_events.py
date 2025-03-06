import math
from gi.repository import Gtk, Gdk

class CanvasEventsMixin:
    def on_click(self, gesture, n_press, x, y):
        if self.tool_mode == "draw_walls":
            self._handle_wall_click(n_press, x, y)
        elif self.tool_mode == "draw_rooms":
            self._handle_room_click(n_press, x, y)
        elif self.tool_mode == "pointer":
            self._handle_pointer_click(gesture, n_press, x, y)
    
    def _handle_pointer_click(self, gesture, n_press, x, y):
        # Get modifier state (shift pressed or not)
        event = gesture.get_current_event()
        state = event.get_modifier_state() if event is not None else 0
        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)

        
        # Convert click from screen to world coordinates:
        world_x = (x - self.offset_x) / self.zoom
        world_y = (y - self.offset_y) / self.zoom

        # Set a threshold in world coordinates (e.g., 10 pixels on screen)
        threshold = 10 / self.zoom

        best_distance = float('inf')
        candidate_type = None
        candidate_object = None

        # Helper function: distance from point P to segment AB.
        def distance_point_to_segment(P, A, B):
            (px, py) = P
            (ax, ay) = A
            (bx, by) = B
            dx = bx - ax
            dy = by - ay
            if dx == 0 and dy == 0:
                return math.hypot(px - ax, py - ay)
            t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
            if t < 0:
                return math.hypot(px - ax, py - ay)
            elif t > 1:
                return math.hypot(px - bx, py - by)
            proj_x = ax + t * dx
            proj_y = ay + t * dy
            return math.hypot(px - proj_x, py - proj_y)

        # Check each wall segment in all finalized wall sets.
        for wall_set in self.wall_sets:
            for wall in wall_set:
                d = distance_point_to_segment((world_x, world_y), wall.start, wall.end)
                if d < threshold and d < best_distance:
                    best_distance = d
                    candidate_type = "wall"
                    candidate_object = wall

        # Also check room vertices.
        for room in self.rooms:
            for idx, pt in enumerate(room.points):
                d = math.hypot(world_x - pt[0], world_y - pt[1])
                if d < threshold and d < best_distance:
                    best_distance = d
                    candidate_type = "vertex"
                    candidate_object = (room, idx)

        # Update the selection based on shift key:
        if candidate_object is not None:
            if shift_pressed:
                # If already selected, toggle it off; else add to selection.
                if not any(item["type"] == candidate_type and item["object"] == candidate_object for item in self.selected_items):
                    self.selected_items.append({"type": candidate_type, "object": candidate_object})
                else:
                    self.selected_items = [item for item in self.selected_items
                                           if not (item["type"] == candidate_type and item["object"] == candidate_object)]
            else:
                # Clear any previous selection and select the candidate.
                self.selected_items = [{"type": candidate_type, "object": candidate_object}]
        else:
            if not shift_pressed:
                # Clear selection if nothing is hit and shift is not pressed.
                self.selected_items = []
        
        self.queue_draw()

    def on_drag_begin(self, gesture, start_x, start_y):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.drag_start_x = start_x
        self.drag_start_y = start_y
        self.last_offset_x = self.offset_x
        self.last_offset_y = self.offset_y

    def on_drag_update(self, gesture, offset_x, offset_y):
        if self.tool_mode == "panning":
            self.offset_x = self.last_offset_x + offset_x
            self.offset_y = self.last_offset_y + offset_y
        self.queue_draw()

    def on_motion(self, controller, x, y):
        self.mouse_x = x
        self.mouse_y = y
        if self.tool_mode == "draw_walls" and self.drawing_wall and self.current_wall:
            canvas_x = (x - self.offset_x) / self.zoom
            canvas_y = (y - self.offset_y) / self.zoom
            raw_point = (canvas_x, canvas_y)
            last_wall = self.walls[-1] if self.walls else None
            canvas_width = self.get_allocation().width or self.config.WINDOW_WIDTH
            finalized_points = []
            for wall_set in self.wall_sets:
                for wall in wall_set:
                    finalized_points.append(wall.start)
                    finalized_points.append(wall.end)
            (snapped_x, snapped_y), self.snap_type = self.snap_manager.snap_point(
                canvas_x, canvas_y, self.current_wall.start[0], self.current_wall.start[1],
                self.walls, self.rooms, current_wall=self.current_wall, last_wall=last_wall,
                in_progress_points=finalized_points, canvas_width=canvas_width, zoom=self.zoom
            )
            self.raw_current_end = raw_point
            raw_x, raw_y = raw_point
            aligned_x, aligned_y, candidate = self._apply_alignment_snapping(raw_x, raw_y)
            snapped_x, snapped_y = aligned_x, aligned_y
            self.alignment_candidate = candidate
            self.current_wall.end = (snapped_x, snapped_y)
            self.queue_draw()
        elif self.tool_mode == "draw_rooms":
            canvas_x = (x - self.offset_x) / self.zoom
            canvas_y = (y - self.offset_y) / self.zoom
            raw_point = (canvas_x, canvas_y)
            base_x = self.current_room_points[-1][0] if self.current_room_points else canvas_x
            base_y = self.current_room_points[-1][1] if self.current_room_points else canvas_y
            candidate_points = []
            for wall_set in self.wall_sets:
                for wall in wall_set:
                    candidate_points.append(wall.start)
                    candidate_points.append(wall.end)
            candidate_points.extend(self.current_room_points)
            (snapped_x, snapped_y), _ = self.snap_manager.snap_point(
                canvas_x, canvas_y, base_x, base_y,
                self.walls, self.rooms,
                current_wall=None, last_wall=None,
                in_progress_points=candidate_points,
                canvas_width=self.get_allocation().width or self.config.WINDOW_WIDTH,
                zoom=self.zoom
            )
            raw_x, raw_y = raw_point
            aligned_x, aligned_y, _ = self._apply_alignment_snapping(raw_x, raw_y)
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
        allocation = self.get_allocation()
        pointer_x, pointer_y = self.get_pointer()
        center_x = pointer_x
        center_y = pointer_y
        zoom_factor = 1.0 + (-dy * 0.1)
        self.adjust_zoom(zoom_factor, center_x, center_y)
        return True

    def _handle_room_click(self, n_press, x, y):
        canvas_x = (x - self.offset_x) / self.zoom
        canvas_y = (y - self.offset_y) / self.zoom
        raw_point = (canvas_x, canvas_y)
        base_x = self.current_room_points[-1][0] if self.current_room_points else canvas_x
        base_y = self.current_room_points[-1][1] if self.current_room_points else canvas_y
        candidate_points = []
        for wall_set in self.wall_sets:
            for wall in wall_set:
                candidate_points.append(wall.start)
                candidate_points.append(wall.end)
        candidate_points.extend(self.current_room_points)
        (snapped_x, snapped_y), _ = self.snap_manager.snap_point(
            canvas_x, canvas_y, base_x, base_y,
            self.walls, self.rooms,
            current_wall=None, last_wall=None,
            in_progress_points=candidate_points,
            canvas_width=self.get_allocation().width or self.config.WINDOW_WIDTH,
            zoom=self.zoom
        )
        raw_x, raw_y = raw_point
        aligned_x, aligned_y, _ = self._apply_alignment_snapping(raw_x, raw_y)
        snapped_x, snapped_y = aligned_x, aligned_y

        if n_press == 1:
            self.save_state()
            self.current_room_points.append((snapped_x, snapped_y))
            print(f"Added point to room: {snapped_x}, {snapped_y}")
            self.queue_draw()
        elif n_press == 2:
            self.save_state()
            print(f"Double-click at ({snapped_x}, {snapped_y}), current_room_points: {len(self.current_room_points)}")
            if self.current_room_points:
                if len(self.current_room_points) > 2:
                    if self.current_room_points[0] != self.current_room_points[-1]:
                        self.current_room_points.append(self.current_room_points[0])
                    new_room = self.Room(self.current_room_points)
                    self.rooms.append(new_room)
                    print(f"Finalized manual room with points: {self.current_room_points}")
                self.current_room_points = []
                self.current_room_preview = None
            print(f"Checking {len(self.wall_sets)} wall sets")
            for wall_set in self.wall_sets:
                if len(wall_set) > 2:
                    poly = [w.start for w in wall_set]
                    closed = self._is_closed_polygon(wall_set)
                    if closed and self._point_in_polygon((snapped_x, snapped_y), poly):
                        new_room = self.Room(poly)
                        self.rooms.append(new_room)
                        print(f"Created room from wall set: {poly}")
                        break
            self.queue_draw()

    def _handle_wall_click(self, n_press, x, y):
        canvas_x = (x - self.offset_x) / self.zoom
        canvas_y = (y - self.offset_y) / self.zoom
        raw_point = (canvas_x, canvas_y)
        last_wall = self.walls[-1] if self.walls else None
        canvas_width = self.get_allocation().width or self.config.WINDOW_WIDTH
        base_x = canvas_x if not self.drawing_wall else self.current_wall.start[0]
        base_y = canvas_y if not self.drawing_wall else self.current_wall.start[1]
        finalized_points = []
        for wall_set in self.wall_sets:
            for wall in wall_set:
                finalized_points.append(wall.start)
                finalized_points.append(wall.end)
        (snapped_x, snapped_y), self.snap_type = self.snap_manager.snap_point(
            canvas_x, canvas_y, base_x, base_y, self.walls, self.rooms,
            current_wall=self.current_wall, last_wall=last_wall,
            in_progress_points=finalized_points, canvas_width=canvas_width, zoom=self.zoom
        )
        self.raw_current_end = raw_point
        raw_x, raw_y = raw_point
        aligned_x, aligned_y, candidate = self._apply_alignment_snapping(raw_x, raw_y)
        snapped_x, snapped_y = aligned_x, aligned_y
        self.alignment_candidate = candidate

        if n_press == 1:
            if not self.drawing_wall:
                self.save_state()
                self.current_wall = self.Wall((snapped_x, snapped_y), (snapped_x, snapped_y),
                                            width=self.config.DEFAULT_WALL_WIDTH,
                                            height=self.config.DEFAULT_WALL_HEIGHT)
                self.walls = []
                self.drawing_wall = True
            else:
                self.save_state()
                self.current_wall.end = (snapped_x, snapped_y)
                self.walls.append(self.current_wall)
                self.current_wall = self.Wall((snapped_x, snapped_y), (snapped_x, snapped_y),
                                            width=self.config.DEFAULT_WALL_WIDTH,
                                            height=self.config.DEFAULT_WALL_HEIGHT)
        elif n_press == 2:
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
                print(f"Auto-wall creation: raw_point = {raw_point}, rooms count = {len(self.rooms)}")
                found = False
                for room in self.rooms:
                    if len(room.points) < 3:
                        print(f"Skipping room with insufficient points: {room.points}")
                        continue
                    print(f"Checking room with points: {room.points} for raw_point: {raw_point}")
                    if self._point_in_polygon(raw_point, room.points):
                        pts = room.points if room.points[0] == room.points[-1] else room.points + [room.points[0]]
                        new_wall_set = []
                        for i in range(len(pts) - 1):
                            new_wall = self.Wall(pts[i], pts[i+1],
                                                width=self.config.DEFAULT_WALL_WIDTH,
                                                height=self.config.DEFAULT_WALL_HEIGHT)
                            new_wall_set.append(new_wall)
                        self.wall_sets.append(new_wall_set)
                        print(f"Auto-created walls for room with points: {room.points}")
                        found = True
                        break
                if not found:
                    print("No room found for auto-wall creation.")
        self.queue_draw()


