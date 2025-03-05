import gi, math, copy
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, cairo
from measurement_utils import MeasurementConverter
from components import Wall, Room
from snapping_manager import SnappingManager

class CanvasArea(Gtk.DrawingArea):
    def __init__(self, config_constants):
        super().__init__()
        self.config = config_constants
        self.converter = MeasurementConverter()

        self.set_focusable(True)
        self.grab_focus()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_draw_func(self.on_draw)

        # Zoom and pan
        self.zoom = self.config.DEFAULT_ZOOM_LEVEL
        self.offset_x = 0
        self.offset_y = 0
        self.ruler_offset = 30

        # Wall drawing state
        self.walls = []
        self.current_wall = None
        self.drawing_wall = False
        self.wall_sets = []

        # Room drawing state
        self.rooms = []                # Finalized Room objects
        self.current_room_points = []  # Manual room drawing points
        self.current_room_preview = None  # Live preview point (snapped)

        # For alignment snapping (used for walls and rooms)
        self.alignment_candidate = None
        self.raw_current_end = None

        self.snap_type = "none"
        self.tool_mode = None  # "draw_walls" or "draw_rooms"

        # Undo/Redo stacks
        self.undo_stack = []
        self.redo_stack = []

        # Initialize snapping manager
        self.snap_manager = SnappingManager(
            snap_enabled=self.config.SNAP_ENABLED,
            snap_threshold=self.config.SNAP_THRESHOLD,
            config=self.config,
            zoom=self.zoom
        )

        # Set up input controllers
        scroll_controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.NONE)
        scroll_controller.connect("scroll", self.on_scroll)
        self.add_controller(scroll_controller)

        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("pressed", self.on_click)
        self.add_controller(click_gesture)

        drag_gesture = Gtk.GestureDrag.new()
        drag_gesture.connect("drag-begin", self.on_drag_begin)
        drag_gesture.connect("drag-update", self.on_drag_update)
        self.add_controller(drag_gesture)

        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("motion", self.on_motion)
        self.add_controller(motion_controller)

        pinch_gesture = Gtk.GestureZoom.new()
        pinch_gesture.connect("scale-changed", self.on_zoom_changed)
        self.add_controller(pinch_gesture)

    def set_tool_mode(self, mode):
        self.tool_mode = mode
        self.current_wall = None
        self.drawing_wall = False
        self.snap_type = "none"
        self.alignment_candidate = None
        self.raw_current_end = None
        self.current_room_points = []
        self.current_room_preview = None
        self.queue_draw()

    def on_zoom_changed(self, controller, scale):
        sensitivity = 0.2
        factor = 1 + (scale - 1) * sensitivity
        allocation = self.get_allocation()
        center_x = allocation.width / 2
        center_y = allocation.height / 2
        self.adjust_zoom(factor, center_x, center_y)

    def adjust_zoom(self, factor, center_x=None, center_y=None):
        old_zoom = self.zoom
        new_zoom = self.zoom * factor
        self.zoom = max(0.1, min(new_zoom, 10.0))
        self.snap_manager.snap_threshold = self.config.SNAP_THRESHOLD * self.zoom
        if center_x is not None and center_y is not None:
            self.offset_x = center_x - (center_x - self.offset_x) * (self.zoom / old_zoom)
            self.offset_y = center_y - (center_y - self.offset_y) * (self.zoom / old_zoom)
        self.queue_draw()

    def reset_zoom(self):
        self.zoom = self.config.DEFAULT_ZOOM_LEVEL
        self.snap_manager.snap_threshold = self.config.SNAP_THRESHOLD * self.zoom
        self.offset_x = 0
        self.offset_y = 0
        self.queue_draw()

    def on_scroll(self, controller, dx, dy):
        allocation = self.get_allocation()
        pointer_x, pointer_y = self.get_pointer()
        center_x = pointer_x
        center_y = pointer_y
        zoom_factor = 1.0 + (-dy * 0.1)
        self.adjust_zoom(zoom_factor, center_x, center_y)
        return True

    def _apply_alignment_snapping(self, x, y):
        candidates = []
        for wall_set in self.wall_sets:
            for wall in wall_set:
                candidates.append(wall.start)
                candidates.append(wall.end)
        for wall in self.walls:
            candidates.append(wall.start)
            candidates.append(wall.end)
        if self.current_wall:
            candidates.append(self.current_wall.start)
        if self.tool_mode == "draw_rooms":
            candidates.extend(self.current_room_points)
        tolerance = 10 / self.zoom
        aligned_x = x
        aligned_y = y
        candidate_x = None
        candidate_y = None
        min_diff_x = tolerance
        for (cx, cy) in candidates:
            diff = abs(cx - x)
            if diff < min_diff_x:
                min_diff_x = diff
                candidate_x = cx
        if candidate_x is not None:
            aligned_x = candidate_x
        min_diff_y = tolerance
        for (cx, cy) in candidates:
            diff = abs(cy - y)
            if diff < min_diff_y:
                min_diff_y = diff
                candidate_y = cy
        if candidate_y is not None:
            aligned_y = candidate_y
        candidate = None
        if candidate_x is not None or candidate_y is not None:
            candidate = (aligned_x, aligned_y)
        return aligned_x, aligned_y, candidate

    def on_draw(self, widget, cr, width, height):
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        cr.save()
        cr.translate(self.offset_x, self.offset_y)
        cr.scale(self.zoom, self.zoom)
        self.draw_grid(cr, width, height)

        # Draw walls
        base_feet_per_pixel = 60.0 / width
        wall_thickness_feet = self.config.DEFAULT_WALL_WIDTH / 12
        wall_pixel_width = wall_thickness_feet / base_feet_per_pixel
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(max(wall_pixel_width * self.zoom, 1.0))
        cr.set_line_join(0)
        cr.set_line_cap(0)
        cr.set_miter_limit(10.0)
        for wall_set in self.wall_sets:
            if not wall_set: continue
            cr.move_to(wall_set[0].start[0], wall_set[0].start[1])
            for wall in wall_set:
                cr.line_to(wall.end[0], wall.end[1])
            if len(wall_set) > 2 and wall_set[-1].end == wall_set[0].start:
                cr.close_path()
            cr.stroke()
        if self.walls:
            cr.move_to(self.walls[0].start[0], self.walls[0].start[1])
            for wall in self.walls:
                cr.line_to(wall.end[0], wall.end[1])
            if self.current_wall:
                cr.line_to(self.current_wall.end[0], self.current_wall.end[1])
            if not self.drawing_wall and len(self.walls) > 2 and self.walls[-1].end == self.walls[0].start:
                cr.close_path()
            cr.stroke()
        elif self.current_wall:
            cr.move_to(self.current_wall.start[0], self.current_wall.start[1])
            cr.line_to(self.current_wall.end[0], self.current_wall.end[1])
            cr.stroke()

        # Draw finalized rooms
        cr.set_source_rgb(0.9, 0.9, 1)  # Light blue fill for rooms
        cr.set_line_width(1.0 / self.zoom)  # Thinner line for room outlines
        for room in self.rooms:
            if room.points:
                cr.save()
                cr.move_to(room.points[0][0], room.points[0][1])
                for pt in room.points[1:]:
                    cr.line_to(pt[0], pt[1])
                cr.close_path()
                cr.fill_preserve()
                cr.set_source_rgb(0, 0, 0)  # Black outline
                cr.stroke()
                cr.restore()

        # Draw room in-progress (manual)
        if self.tool_mode == "draw_rooms" and self.current_room_points:
            cr.save()
            cr.set_source_rgb(0, 0, 1)  # Blue for in-progress room
            cr.set_line_width(2.0 / self.zoom)
            cr.move_to(self.current_room_points[0][0], self.current_room_points[0][1])
            for pt in self.current_room_points[1:]:
                cr.line_to(pt[0], pt[1])
            if self.current_room_preview:
                cr.line_to(self.current_room_preview[0], self.current_room_preview[1])
            cr.stroke()
            cr.restore()

        self.draw_alignment_guide(cr)
        self.draw_snap_indicator(cr)

        cr.restore()
        if self.config.SHOW_RULERS:
            self.draw_rulers(cr, width, height)

    def draw_alignment_guide(self, cr):
        if not (self.drawing_wall and self.current_wall and self.alignment_candidate and self.raw_current_end):
            return
        dx = self.raw_current_end[0] - self.alignment_candidate[0]
        dy = self.raw_current_end[1] - self.alignment_candidate[1]
        if math.sqrt(dx**2 + dy**2) < 1:
            return
        cr.save()
        cr.set_line_width(1.0 / self.zoom)
        cr.set_dash([2.0 / self.zoom, 2.0 / self.zoom])
        cr.set_source_rgb(0.7, 0.7, 0.7)
        cr.move_to(self.raw_current_end[0], self.raw_current_end[1])
        cr.line_to(self.alignment_candidate[0], self.alignment_candidate[1])
        cr.stroke()
        cr.restore()

    def draw_snap_indicator(self, cr):
        if self.snap_type == "none" or not self.drawing_wall or not self.current_wall:
            return
        cr.save()
        snap_x, snap_y = self.current_wall.end
        cr.set_line_width(2.0 / self.zoom)
        cr.set_font_size(12 / self.zoom)
        cr.select_font_face("Sans")
        if self.snap_type == "endpoint":
            cr.set_source_rgb(1, 0, 0)
            cr.arc(snap_x, snap_y, 10 / self.zoom, 0, 2 * math.pi)
            cr.fill()
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Endpoint")
        elif self.snap_type == "midpoint":
            cr.set_source_rgb(0, 0, 1)
            cr.arc(snap_x, snap_y, 10 / self.zoom, 0, 2 * math.pi)
            cr.stroke()
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Midpoint")
        elif self.snap_type == "axis":
            cr.set_source_rgb(0, 1, 0)
            cr.move_to(snap_x - 20 / self.zoom, snap_y)
            cr.line_to(snap_x + 20 / self.zoom, snap_y)
            cr.move_to(snap_x, snap_y - 20 / self.zoom)
            cr.line_to(snap_x, snap_y + 20 / self.zoom)
            cr.stroke()
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Axis")
        elif self.snap_type in ["angle", "perpendicular"]:
            cr.set_source_rgb(1, 0, 1)
            cr.move_to(self.current_wall.start[0], self.current_wall.start[1])
            cr.line_to(snap_x, snap_y)
            cr.stroke()
            if self.snap_type == "perpendicular":
                cr.move_to(snap_x + 15 / self.zoom, snap_y)
                cr.show_text("Perpendicular")
        elif self.snap_type == "grid":
            cr.set_source_rgb(0.5, 0.5, 0.5)
            cr.rectangle(snap_x - 10 / self.zoom, snap_y - 10 / self.zoom, 20 / self.zoom, 20 / self.zoom)
            cr.stroke()
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Grid")
        elif self.snap_type == "distance":
            cr.set_source_rgb(1, 0.5, 0)
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Distance")
        elif self.snap_type == "tangent":
            cr.set_source_rgb(0, 1, 1)
            cr.arc(snap_x, snap_y, 10 / self.zoom, 0, 2 * math.pi)
            cr.fill()
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Tangent")
        cr.restore()

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

        if n_press == 1:  # Single-click: Add point to manual room
            self.save_state()
            self.current_room_points.append((snapped_x, snapped_y))
            print(f"Added point to room: {snapped_x}, {snapped_y}")
            self.queue_draw()

        elif n_press == 2:  # Double-click
            self.save_state()
            print(f"Double-click at ({snapped_x}, {snapped_y}), current_room_points: {len(self.current_room_points)}")
            if self.current_room_points:  # Finalize manual room drawing
                if len(self.current_room_points) > 2:
                    if self.current_room_points[0] != self.current_room_points[-1]:
                        self.current_room_points.append(self.current_room_points[0])
                    new_room = Room(self.current_room_points)
                    self.rooms.append(new_room)
                    print(f"Finalized manual room with points: {self.current_room_points}")
                self.current_room_points = []
                self.current_room_preview = None
            # Check for wall loop regardless of current_room_points
            print(f"Checking {len(self.wall_sets)} wall sets")
            for wall_set in self.wall_sets:
                if len(wall_set) > 2:
                    poly = [w.start for w in wall_set]
                    closed = self._is_closed_polygon(wall_set)
                    if closed and self._point_in_polygon((snapped_x, snapped_y), poly):
                        new_room = Room(poly)
                        self.rooms.append(new_room)
                        print(f"Created room from wall set: {poly}")
                        break
            self.queue_draw()

    def finalize_room(self):
        if self.current_room_points and len(self.current_room_points) > 2:
            self.save_state()
            if self.current_room_points[0] != self.current_room_points[-1]:
                self.current_room_points.append(self.current_room_points[0])
            new_room = Room(self.current_room_points)
            self.rooms.append(new_room)
            print(f"Finalized room with points: {self.current_room_points}")
            self.current_room_points = []
            self.current_room_preview = None
            self.queue_draw()

    def _is_closed_polygon(self, wall_set):
        if not wall_set or len(wall_set) < 3:
            print(f"Wall set too small: {len(wall_set)} walls")
            return False
        first = wall_set[0].start
        last = wall_set[-1].end
        tolerance = 5 / self.zoom
        closed = abs(first[0] - last[0]) < tolerance and abs(first[1] - last[1]) < tolerance
        print(f"Checking closure: first={first}, last={last}, tolerance={tolerance}, closed={closed}")
        return closed

    def _point_in_polygon(self, point, poly):
        x, y = point
        inside = False
        n = len(poly)
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
                inside = not inside
            j = i
        print(f"Point {point} in polygon {poly}: {inside}")
        return inside

    def on_click(self, gesture, n_press, x, y):
        if self.tool_mode == "draw_walls":
            self._handle_wall_click(n_press, x, y)
        elif self.tool_mode == "draw_rooms":
            self._handle_room_click(n_press, x, y)

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
                self.current_wall = Wall((snapped_x, snapped_y), (snapped_x, snapped_y),
                                        width=self.config.DEFAULT_WALL_WIDTH,
                                        height=self.config.DEFAULT_WALL_HEIGHT)
                self.walls = []
                self.drawing_wall = True
            else:
                self.save_state()
                self.current_wall.end = (snapped_x, snapped_y)
                self.walls.append(self.current_wall)
                self.current_wall = Wall((snapped_x, snapped_y), (snapped_x, snapped_y),
                                        width=self.config.DEFAULT_WALL_WIDTH,
                                        height=self.config.DEFAULT_WALL_HEIGHT)
        elif n_press == 2:
            # If drawing is in progress and at least one wall segment exists, finalize normally.
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
                # Otherwise, treat the double-click as a command to auto-create walls.
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
                            new_wall = Wall(pts[i], pts[i+1],
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

    def save_state(self):
        state = {
            "wall_sets": copy.deepcopy(self.wall_sets),
            "walls": copy.deepcopy(self.walls),
            "current_wall": copy.deepcopy(self.current_wall) if self.current_wall else None,
            "drawing_wall": self.drawing_wall,
            "rooms": copy.deepcopy(self.rooms),
            "current_room_points": copy.deepcopy(self.current_room_points)
        }
        self.undo_stack.append(state)
        if len(self.undo_stack) > self.config.UNDO_REDO_LIMIT:
            self.undo_stack.pop(0)
        print(f"save_state: {len(state['wall_sets'])} wall sets, {len(state['walls'])} walls, {len(state['rooms'])} rooms")

    def restore_state(self, state):
        self.wall_sets = copy.deepcopy(state["wall_sets"])
        self.walls = copy.deepcopy(state["walls"])
        self.current_wall = copy.deepcopy(state["current_wall"]) if state["current_wall"] else None
        self.drawing_wall = state["drawing_wall"]
        self.rooms = copy.deepcopy(state["rooms"])
        self.current_room_points = copy.deepcopy(state["current_room_points"])
        self.snap_type = "none"
        self.queue_draw()
        print(f"restore_state: {len(self.wall_sets)} wall sets, {len(self.walls)} walls, {len(self.rooms)} rooms")

    def undo(self):
        if not self.undo_stack:
            print("Nothing to undo.")
            return
        current_state = {
            "wall_sets": copy.deepcopy(self.wall_sets),
            "walls": copy.deepcopy(self.walls),
            "current_wall": copy.deepcopy(self.current_wall) if self.current_wall else None,
            "drawing_wall": self.drawing_wall,
            "rooms": copy.deepcopy(self.rooms),
            "current_room_points": copy.deepcopy(self.current_room_points)
        }
        self.redo_stack.append(current_state)
        state = self.undo_stack.pop()
        self.restore_state(state)

    def redo(self):
        if not self.redo_stack:
            print("Nothing to redo.")
            return
        current_state = {
            "wall_sets": copy.deepcopy(self.wall_sets),
            "walls": copy.deepcopy(self.walls),
            "current_wall": copy.deepcopy(self.current_wall) if self.current_wall else None,
            "drawing_wall": self.drawing_wall,
            "rooms": copy.deepcopy(self.rooms),
            "current_room_points": copy.deepcopy(self.current_room_points)
        }
        self.undo_stack.append(current_state)
        state = self.redo_stack.pop()
        self.restore_state(state)

    def draw_rulers(self, cr, width, height):
        ruler_size = 20
        base_feet_per_pixel = 60.0 / width
        major_spacing = 8 / base_feet_per_pixel * self.zoom
        minor_spacing = major_spacing / 8
        grid_left_pixel = -self.offset_x / self.zoom
        grid_top_pixel = -self.offset_y / self.zoom
        left_feet = grid_left_pixel * base_feet_per_pixel
        top_feet = grid_top_pixel * base_feet_per_pixel
        first_grid_x_feet = math.floor(left_feet / 8) * 8
        first_grid_y_feet = math.floor(top_feet / 8) * 8
        first_major_x_pixel = (first_grid_x_feet / base_feet_per_pixel * self.zoom + self.offset_x)
        first_major_y_pixel = (first_grid_y_feet / base_feet_per_pixel * self.zoom + self.offset_y)
        while first_major_x_pixel > self.ruler_offset:
            first_major_x_pixel -= major_spacing
            first_grid_x_feet -= 8
        while first_major_x_pixel < self.ruler_offset - major_spacing:
            first_major_x_pixel += major_spacing
            first_grid_x_feet += 8
        while first_major_y_pixel > self.ruler_offset:
            first_major_y_pixel -= major_spacing
            first_grid_y_feet -= 8
        while first_major_y_pixel < self.ruler_offset - major_spacing:
            first_major_y_pixel += major_spacing
            first_grid_y_feet += 8
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.rectangle(self.ruler_offset, 0, width, ruler_size)
        cr.rectangle(0, self.ruler_offset, ruler_size, height)
        cr.fill()
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(1)
        for x in range(int(first_major_x_pixel), width + int(major_spacing), int(major_spacing)):
            if x >= self.ruler_offset and x <= width:
                cr.move_to(x, ruler_size - 10)
                cr.line_to(x, ruler_size)
                cr.stroke()
                feet = round((x - first_major_x_pixel) / major_spacing) * 8 + first_grid_x_feet
                cr.move_to(x + 2, ruler_size - 7)
                cr.show_text(f"{feet} ft")
            for i in range(1, 8):
                minor_x = x + i * minor_spacing
                if minor_x >= self.ruler_offset and minor_x <= width:
                    cr.move_to(minor_x, ruler_size - 5)
                    cr.line_to(minor_x, ruler_size)
                    cr.stroke()
        for y in range(int(first_major_y_pixel), height + int(major_spacing), int(major_spacing)):
            if y >= self.ruler_offset and y <= height:
                cr.move_to(ruler_size - 10, y)
                cr.line_to(ruler_size, y)
                cr.stroke()
                feet = round((y - first_major_y_pixel) / major_spacing) * 8 + first_grid_y_feet
                cr.move_to(2, y + 10)
                cr.show_text(f"{feet} ft")
            for i in range(1, 8):
                minor_y = y + i * minor_spacing
                if minor_y >= self.ruler_offset and minor_y <= height:
                    cr.move_to(ruler_size - 5, minor_y)
                    cr.line_to(ruler_size, minor_y)
                    cr.stroke()

    def draw_grid(self, cr, width, height):
        if not self.config.SHOW_GRID:
            return
        base_feet_per_pixel = 60.0 / width
        major_grid_spacing = 8
        minor_grid_spacing = 1
        left_pixel = -self.offset_x / self.zoom
        right_pixel = (width - self.offset_x) / self.zoom
        top_pixel = -self.offset_y / self.zoom
        bottom_pixel = (height - self.offset_y) / self.zoom
        left_feet = left_pixel * base_feet_per_pixel
        right_feet = right_pixel * base_feet_per_pixel
        top_feet = top_pixel * base_feet_per_pixel
        bottom_feet = bottom_pixel * base_feet_per_pixel
        buffer_feet = 8
        left_feet -= buffer_feet
        right_feet += buffer_feet
        top_feet -= buffer_feet
        bottom_feet += buffer_feet
        cr.set_line_width(1 / self.zoom)
        cr.set_source_rgb(0.8, 0.8, 0.8)
        first_major_x = math.floor(left_feet / 8) * 8
        for feet in range(int(first_major_x), int(right_feet) + 1, 8):
            x = feet / base_feet_per_pixel
            cr.move_to(x, top_pixel)
            cr.line_to(x, bottom_pixel)
        first_major_y = math.floor(top_feet / 8) * 8
        for feet in range(int(first_major_y), int(bottom_feet) + 1, 8):
            y = feet / base_feet_per_pixel
            cr.move_to(left_pixel, y)
            cr.line_to(right_pixel, y)
        cr.stroke()
        cr.set_source_rgb(0.9, 0.9, 0.9)
        first_minor_x = math.floor(left_feet)
        for feet in range(int(first_minor_x), int(right_feet) + 1):
            if feet % 8 != 0:
                x = feet / base_feet_per_pixel
                cr.move_to(x, top_pixel)
                cr.line_to(x, bottom_pixel)
        first_minor_y = math.floor(top_feet)
        for feet in range(int(first_minor_y), int(bottom_feet) + 1):
            if feet % 8 != 0:
                y = feet / base_feet_per_pixel
                cr.move_to(left_pixel, y)
                cr.line_to(right_pixel, y)
        cr.stroke()

def create_canvas_area(config_constants):
    return CanvasArea(config_constants)
