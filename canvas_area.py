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

        # Use the default zoom level from settings
        self.zoom = self.config.DEFAULT_ZOOM_LEVEL
        self.offset_x = 0
        self.offset_y = 0
        self.ruler_offset = 30
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.last_offset_x = 0
        self.last_offset_y = 0
        self.mouse_x = 0
        self.mouse_y = 0
        self.snap_type = "none"

        self.tool_mode = None
        self.walls = []
        self.rooms = []
        self.current_wall = None
        self.drawing_wall = False
        self.wall_sets = []
        # Undo/Redo stacks
        self.undo_stack = []
        self.redo_stack = []

        # Initialize snapping manager; snap_threshold is multiplied by zoom
        self.snap_manager = SnappingManager(
            snap_enabled=self.config.SNAP_ENABLED, 
            snap_threshold=self.config.SNAP_THRESHOLD, 
            config=self.config,
            zoom=self.zoom
        )

        # Set up controllers
        scroll_controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.NONE)
        scroll_controller.connect("scroll", self.on_scroll)
        self.add_controller(scroll_controller)

        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("pressed", self.on_wall_click)
        self.add_controller(click_gesture)

        drag_gesture = Gtk.GestureDrag.new()
        drag_gesture.connect("drag-begin", self.on_drag_begin)
        drag_gesture.connect("drag-update", self.on_drag_update)
        self.add_controller(drag_gesture)

        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("motion", self.on_motion)
        self.add_controller(motion_controller)

        # Pinch-to-zoom gesture (for trackpads)
        pinch_gesture = Gtk.GestureZoom.new()
        pinch_gesture.connect("scale-changed", self.on_zoom_changed)
        self.add_controller(pinch_gesture)

    def on_zoom_changed(self, controller, scale):
        sensitivity = 0.2
        factor = 1 + (scale - 1) * sensitivity
        allocation = self.get_allocation()
        center_x = allocation.width / 2
        center_y = allocation.height / 2
        self.adjust_zoom(factor, center_x, center_y)

    def on_draw(self, widget, cr, width, height):
        # Clear the canvas
        cr.set_source_rgb(1, 1, 1)
        cr.paint()

        cr.save()
        cr.translate(self.offset_x, self.offset_y)
        cr.scale(self.zoom, self.zoom)

        self.draw_grid(cr, width, height)

        base_feet_per_pixel = 60.0 / width
        wall_thickness_feet = self.config.DEFAULT_WALL_WIDTH / 12
        wall_pixel_width = wall_thickness_feet / base_feet_per_pixel
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(max(wall_pixel_width * self.zoom, 1.0))
        cr.set_line_join(0)
        cr.set_line_cap(0)
        cr.set_miter_limit(10.0)

        # Draw finalized wall sets
        for wall_set in self.wall_sets:
            if not wall_set:
                continue
            cr.move_to(wall_set[0].start[0], wall_set[0].start[1])
            for wall in wall_set:
                cr.line_to(wall.end[0], wall.end[1])
            if len(wall_set) > 2 and wall_set[-1].end == wall_set[0].start:
                cr.close_path()
            cr.stroke()

        # Draw current in-progress wall(s)
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

        # Draw live measurement labels for the current wall
        if self.drawing_wall and self.current_wall:
            dx = self.current_wall.end[0] - self.current_wall.start[0]
            dy = self.current_wall.end[1] - self.current_wall.start[1]
            length_pixels = math.sqrt(dx**2 + dy**2)
            length_inches = length_pixels * (60.0 / width) * 12
            length_str = self.converter.format_measurement(self, length_inches, use_fraction=True)
            wall_angle = math.atan2(dy, dx)
            angle_deg = math.degrees(wall_angle) % 360
            angle_str = f"{round(angle_deg, 2)}°"
            
            mid_x = (self.current_wall.start[0] + self.current_wall.end[0]) / 2
            mid_y = (self.current_wall.start[1] + self.current_wall.end[1]) / 2

            # Compute wall normal
            n_x = -dy
            n_y = dx
            norm = math.sqrt(n_x*n_x + n_y*n_y)
            if norm != 0:
                n_x /= norm
                n_y /= norm
            if abs(n_y) < 1e-6:
                n_x, n_y = 0, -1
            elif n_y > 0:
                n_x = -n_x
                n_y = -n_y
            offset = 20 / self.zoom
            label_pos_x = mid_x + n_x * offset
            label_pos_y = mid_y + n_y * offset

            if 90 < angle_deg < 270:
                text_rotation = wall_angle + math.pi
            else:
                text_rotation = wall_angle

            cr.save()
            cr.translate(label_pos_x, label_pos_y)
            cr.rotate(text_rotation)
            cr.set_font_size(12 / self.zoom)
            cr.select_font_face("Sans", cairo.FontSlant.NORMAL, cairo.FontWeight.NORMAL)
            ext_length = cr.text_extents(length_str)
            ext_angle = cr.text_extents(angle_str)
            margin = 5 / self.zoom
            text_offset = max(20 / self.zoom, ext_length.height + margin)
            cr.move_to(-ext_length.width / 2, -text_offset)
            cr.show_text(length_str)
            cr.move_to(-ext_angle.width / 2, -text_offset - ext_length.height - margin)
            cr.show_text(angle_str)
            cr.restore()

        self.draw_snap_indicator(cr)

        cr.restore()

        if self.config.SHOW_RULERS:
            self.draw_rulers(cr, width, height)

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

    def set_tool_mode(self, mode):
        self.tool_mode = mode
        self.current_wall = None
        self.drawing_wall = False
        self.snap_type = "none"
        self.queue_draw()

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

    def on_wall_click(self, gesture, n_press, x, y):
        if self.tool_mode != "draw_walls":
            return
        canvas_x = (x - self.offset_x) / self.zoom
        canvas_y = (y - self.offset_y) / self.zoom
        last_wall = self.walls[-1] if self.walls else None
        canvas_width = self.get_allocation().width or self.config.WINDOW_WIDTH
        base_x = canvas_x if not self.drawing_wall else self.current_wall.start[0]
        base_y = canvas_y if not self.drawing_wall else self.current_wall.start[1]
        print(f"Click at screen ({x}, {y}), canvas ({canvas_x}, {canvas_y})")
        (snapped_x, snapped_y), self.snap_type = self.snap_manager.snap_point(
            canvas_x, canvas_y, base_x, base_y, self.walls, self.rooms,
            current_wall=self.current_wall, last_wall=last_wall, canvas_width=canvas_width, zoom=self.zoom
        )
        print(f"Snapped to ({snapped_x}, {snapped_y}), type: {self.snap_type}")
        if n_press == 1:
            if not self.drawing_wall:
                self.save_state()  # Save state before starting a new wall
                self.current_wall = Wall(
                    (snapped_x, snapped_y),
                    (snapped_x, snapped_y),
                    width=self.config.DEFAULT_WALL_WIDTH,
                    height=self.config.DEFAULT_WALL_HEIGHT
                )
                self.walls = []
                self.drawing_wall = True
            else:
                self.save_state()  # Save state before adding a segment
                self.current_wall.end = (snapped_x, snapped_y)
                self.walls.append(self.current_wall)
                self.current_wall = Wall(
                    (snapped_x, snapped_y),
                    (snapped_x, snapped_y),
                    width=self.config.DEFAULT_WALL_WIDTH,
                    height=self.config.DEFAULT_WALL_HEIGHT
                )
        elif n_press == 2:
            if self.drawing_wall:
                self.save_state()  # Save state before finalizing
                self.current_wall.end = (snapped_x, snapped_y)
                self.walls.append(self.current_wall)
                self.wall_sets.append(self.walls.copy())
                self.save_state()  # Save state after finalizing
                self.walls = []
                self.current_wall = None
                self.drawing_wall = False
                self.snap_type = "none"
        self.queue_draw()

    def on_drag_begin(self, gesture, start_x, start_y):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.drag_start_x = start_x
        self.drag_start_y = start_y
        self.last_offset_x = self.offset_x
        self.last_offset_y = self.offset_y

    def on_drag_update(self, gesture, offset_x, offset_y):
        if self.tool_mode == "panning":
            delta_x = offset_x
            delta_y = offset_y
            self.offset_x = self.last_offset_x + delta_x
            self.offset_y = self.last_offset_y + delta_y
        self.queue_draw()

    def on_motion(self, controller, x, y):
        self.mouse_x = x
        self.mouse_y = y
        if self.tool_mode == "draw_walls" and self.drawing_wall and self.current_wall:
            canvas_x = (x - self.offset_x) / self.zoom
            canvas_y = (y - self.offset_y) / self.zoom
            last_wall = self.walls[-1] if self.walls else None
            canvas_width = self.get_allocation().width or self.config.WINDOW_WIDTH
            print(f"Mouse at screen ({x}, {y}), canvas ({canvas_x}, {canvas_y})")
            (snapped_x, snapped_y), self.snap_type = self.snap_manager.snap_point(
                canvas_x, canvas_y, self.current_wall.start[0], self.current_wall.start[1],
                self.walls, self.rooms, current_wall=self.current_wall, last_wall=last_wall,
                canvas_width=canvas_width, zoom=self.zoom
            )
            print(f"Snapped to ({snapped_x}, {snapped_y}), type: {self.snap_type}")
            self.current_wall.end = (snapped_x, snapped_y)
            self.queue_draw()

    def save_state(self):
        state = {
            "wall_sets": copy.deepcopy(self.wall_sets),
            "walls": copy.deepcopy(self.walls),
            "current_wall": copy.deepcopy(self.current_wall) if self.current_wall else None,
            "drawing_wall": self.drawing_wall
        }
        self.undo_stack.append(state)
        if len(self.undo_stack) > self.config.UNDO_REDO_LIMIT:
            self.undo_stack.pop(0)
        print(f"Saved state: wall_sets={len(state['wall_sets'])}, walls={len(state['walls'])}, drawing_wall={state['drawing_wall']}")

    def restore_state(self, state):
        self.wall_sets = copy.deepcopy(state["wall_sets"])
        self.walls = copy.deepcopy(state["walls"])
        self.current_wall = copy.deepcopy(state["current_wall"]) if state["current_wall"] else None
        self.drawing_wall = state["drawing_wall"]
        self.snap_type = "none"  # Reset snapping to avoid visual artifacts
        self.queue_draw()
        print(f"Restored state: wall_sets={len(self.wall_sets)}, walls={len(self.walls)}, drawing_wall={self.drawing_wall}")

    def undo(self):
        if not self.undo_stack:
            print("Nothing to undo.")
            return
        current_state = {
            "wall_sets": copy.deepcopy(self.wall_sets),
            "walls": copy.deepcopy(self.walls),
            "current_wall": copy.deepcopy(self.current_wall) if self.current_wall else None,
            "drawing_wall": self.drawing_wall
        }
        self.redo_stack.append(current_state)
        state = self.undo_stack.pop()
        self.restore_state(state)
        print(f"Undo performed: redo_stack size={len(self.redo_stack)}, undo_stack size={len(self.undo_stack)}")

    def redo(self):
        if not self.redo_stack:
            print("Nothing to redo.")
            return
        current_state = {
            "wall_sets": copy.deepcopy(self.wall_sets),
            "walls": copy.deepcopy(self.walls),
            "current_wall": copy.deepcopy(self.current_wall) if self.current_wall else None,
            "drawing_wall": self.drawing_wall
        }
        self.undo_stack.append(current_state)
        state = self.redo_stack.pop()
        self.restore_state(state)
        print(f"Redo performed: redo_stack size={len(self.redo_stack)}, undo_stack size={len(self.undo_stack)}")

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