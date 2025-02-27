import gi, math, copy
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, cairo
from measurement_utils import MeasurementConverter
from components import Wall, Room

class CanvasArea(Gtk.DrawingArea):
    def __init__(self, config_constants):
        super().__init__()
        self.config = config_constants

        self.set_focusable(True)
        self.grab_focus()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_draw_func(self.on_draw)

        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.ruler_offset = 30
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.last_offset_x = 0
        self.last_offset_y = 0

        self.tool_mode = None
        self.walls = []
        self.rooms = []

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

    def on_draw(self, widget, cr, width, height):
        cr.set_source_rgb(1, 1, 1)
        cr.paint()

        cr.save()
        cr.translate(self.offset_x, self.offset_y)
        cr.scale(self.zoom, self.zoom)
        self.draw_grid(cr, width, height)
        cr.restore()

        if self.config.SHOW_RULERS:
            self.draw_rulers(cr, width, height)

    def set_tool_mode(self, mode):
        self.tool_mode = mode
        self.queue_draw()

    def adjust_zoom(self, factor, center_x=None, center_y=None):
        old_zoom = self.zoom
        new_zoom = self.zoom * factor
        self.zoom = max(0.1, min(new_zoom, 10.0))

        if center_x is not None and center_y is not None:
            self.offset_x = center_x - (center_x - self.offset_x) * (self.zoom / old_zoom)
            self.offset_y = center_y - (center_y - self.offset_y) * (self.zoom / old_zoom)

        self.queue_draw()

    def reset_zoom(self):
        self.zoom = 1.0
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

    def on_click(self, gesture, n_press, x, y):
        self.grab_focus()
        self.queue_draw()

    def on_drag_begin(self, gesture, start_x, start_y):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.drag_start_x = start_x
        self.drag_start_y = start_y
        self.last_offset_x = self.offset_x
        self.last_offset_y = self.offset_y
        print(f"Drag begin at x={start_x}, y={start_y}")

    def on_drag_update(self, gesture, offset_x, offset_y):
        if self.tool_mode == "panning":
            delta_x = (self.drag_start_x + offset_x - self.drag_start_x) / self.zoom
            delta_y = (self.drag_start_y + offset_y - self.drag_start_y) / self.zoom
            self.offset_x = self.last_offset_x + delta_x
            self.offset_y = self.last_offset_y + delta_y
            print(f"Drag offset_x: {offset_x}, offset_y: {offset_y}, zoom: {self.zoom}")
            print(f"Delta_x: {delta_x}, Delta_y: {delta_y}")
            print(f"New self.offset_x: {self.offset_x}, self.offset_y: {self.offset_y}")
        self.queue_draw()

    def draw_rulers(self, cr, width, height):
        """Draw rulers synced with grid, incrementing by 8 ft, following panning."""
        ruler_size = 20
        base_feet_per_pixel = 60.0 / width  # 60 ft across width at zoom 1.0
        major_spacing = 8 / base_feet_per_pixel * self.zoom  # Unzoomed pixel spacing
        minor_spacing = 1 / base_feet_per_pixel * self.zoom

        # Grid's visible left/top edge in zoomed space
        grid_left_pixel = -self.offset_x / self.zoom
        grid_top_pixel = -self.offset_y / self.zoom

        # Convert to feet and find the first grid line before the edge
        left_feet = grid_left_pixel * base_feet_per_pixel
        top_feet = grid_top_pixel * base_feet_per_pixel
        first_grid_x_feet = math.floor(left_feet / 8) * 8
        first_grid_y_feet = math.floor(top_feet / 8) * 8

        # Map to unzoomed ruler pixels, syncing with grid translation
        first_major_x_pixel = (first_grid_x_feet / base_feet_per_pixel * self.zoom + self.offset_x)
        first_major_y_pixel = (first_grid_y_feet / base_feet_per_pixel * self.zoom + self.offset_y)

        # Adjust to ensure ticks start before the visible area
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

        # Background
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.rectangle(self.ruler_offset, 0, width, ruler_size)
        cr.rectangle(0, self.ruler_offset, ruler_size, height)
        cr.fill()

        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(1)

        # Debug prints
        print(f"Major spacing: {major_spacing}, Minor spacing: {minor_spacing}")
        print(f"First X pixel: {first_major_x_pixel}, First Y pixel: {first_major_y_pixel}")
        print(f"First grid X feet: {first_grid_x_feet}, First grid Y feet: {first_grid_y_feet}")

        # Horizontal ruler (top)
        for x in range(int(first_major_x_pixel), width + int(major_spacing), int(major_spacing)):
            if x >= self.ruler_offset and x <= width:
                cr.move_to(x, ruler_size - 10)
                cr.line_to(x, ruler_size)
                cr.stroke()
                feet = int(first_grid_x_feet + ((x - first_major_x_pixel) / major_spacing) * 8)
                cr.move_to(x + 2, ruler_size - 7)
                cr.show_text(f"{feet} ft")
                print(f"Horizontal tick at x={x}, feet={feet}")

            for i in range(1, 8):
                minor_x = x + i * minor_spacing
                if minor_x >= self.ruler_offset and minor_x <= width:
                    cr.move_to(minor_x, ruler_size - 5)
                    cr.line_to(minor_x, ruler_size)
                    cr.stroke()

        # Vertical ruler (left)
        for y in range(int(first_major_y_pixel), height + int(major_spacing), int(major_spacing)):
            if y >= self.ruler_offset and y <= height:
                cr.move_to(ruler_size - 10, y)
                cr.line_to(ruler_size, y)
                cr.stroke()
                feet = int(first_grid_y_feet + ((y - first_major_y_pixel) / major_spacing) * 8)
                cr.move_to(2, y + 10)
                cr.show_text(f"{feet} ft")
                print(f"Vertical tick at y={y}, feet={feet}")

            for i in range(1, 8):
                minor_y = y + i * minor_spacing
                if minor_y >= self.ruler_offset and minor_y <= height:
                    cr.move_to(ruler_size - 5, minor_y)
                    cr.line_to(ruler_size, minor_y)
                    cr.stroke()

    def draw_grid(self, cr, width, height):
        """Draw grid for the viewable area with proper scaling."""
        if not self.config.SHOW_GRID:
            return

        base_feet_per_pixel = 60.0 / width  # Base scale at zoom 1.0
        major_grid_spacing = 8  # In feet
        minor_grid_spacing = 1

        # Visible bounds in grid (zoomed) space
        left_pixel = -self.offset_x / self.zoom
        right_pixel = (width - self.offset_x) / self.zoom
        top_pixel = -self.offset_y / self.zoom
        bottom_pixel = (height - self.offset_y) / self.zoom

        # Convert to feet
        left_feet = left_pixel * base_feet_per_pixel
        right_feet = right_pixel * base_feet_per_pixel
        top_feet = top_pixel * base_feet_per_pixel
        bottom_feet = bottom_pixel * base_feet_per_pixel

        # Add buffer
        buffer_feet = 8
        left_feet -= buffer_feet
        right_feet += buffer_feet
        top_feet -= buffer_feet
        bottom_feet += buffer_feet

        cr.set_line_width(1 / self.zoom)

        # Major grid lines
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

        # Minor grid lines
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