import gi, copy, math
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, cairo
from typing import List

from measurement_utils import MeasurementConverter
from components import Wall, Room
from snapping_manager import SnappingManager

from canvas_draw import CanvasDrawMixin
from canvas_events import CanvasEventsMixin
from canvas_state import CanvasStateMixin
from canvas_geometry import CanvasGeometryMixin
from canvas_tool import CanvasToolMixin

class CanvasArea(Gtk.DrawingArea, 
                 CanvasDrawMixin, 
                 CanvasEventsMixin, 
                 CanvasStateMixin, 
                 CanvasGeometryMixin,
                 CanvasToolMixin):
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
        print(f"Zoom level: {self.zoom}")
        self.ruler_offset = 80
        self.offset_x = self.ruler_offset
        self.offset_y = self.ruler_offset
        

        # Wall drawing state
        self.walls = []
        self.current_wall = None
        self.drawing_wall = False
        self.wall_sets = []

        # Room drawing state
        self.rooms = []                # Finalized Room objects
        self.current_room_points = []  # Manual room drawing points
        self.current_room_preview = None  # Live preview point (snapped)
        
        self.doors = []  # List of door placements; each item is a tuple: (wall, door, position_ratio)
        self.windows = []  # List of window placements; each item is a tuple: (wall, window, position_ratio)

        # For alignment snapping (used for walls and rooms)
        self.alignment_candidate = None
        self.raw_current_end = None

        self.snap_type = "none"
        self.tool_mode = None  # "draw_walls" or "draw_rooms"

        # Undo/Redo stacks
        self.undo_stack = []
        self.redo_stack = []
        
        # Selection variables
        self.selected_items = []
        self.box_selecting = False
        self.box_select_start = (0, 0)
        self.box_select_end = (0, 0)


        # Expose Wall and Room for mixins
        self.Wall = Wall
        self.Room = Room

        # Initialize snapping manager
        self.snap_manager = SnappingManager(
            snap_enabled=self.config.SNAP_ENABLED,
            snap_threshold=self.config.SNAP_THRESHOLD,
            config=self.config,
            zoom=self.zoom
        )

        # Set up input controllers (delegated to the events mixin)
        scroll_controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.NONE)
        scroll_controller.connect("scroll", self.on_scroll)
        self.add_controller(scroll_controller)

        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("pressed", self.on_click_pressed)
        click_gesture.connect("released", self.on_click)
        self.add_controller(click_gesture)

        drag_gesture = Gtk.GestureDrag.new()
        drag_gesture.connect("drag-begin", self.on_drag_begin)
        drag_gesture.connect("drag-update", self.on_drag_update)
        drag_gesture.connect("drag-end", self.on_drag_end)
        self.add_controller(drag_gesture)

        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("motion", self.on_motion)
        self.add_controller(motion_controller)

        pinch_gesture = Gtk.GestureZoom.new()
        pinch_gesture.connect("scale-changed", self.on_zoom_changed)
        self.add_controller(pinch_gesture)
        
        # Create a gesture click dedicated to right-click (secondary button)
        right_click_gesture = Gtk.GestureClick.new()
        right_click_gesture.set_button(Gdk.BUTTON_SECONDARY)  # Listen for right-click events.
        right_click_gesture.connect("pressed", self.on_right_click)
        self.add_controller(right_click_gesture)

    
    def adjust_zoom(self, factor, center_x, center_y):
        # Calculate the new zoom level.
        new_zoom = self.zoom * factor
        # Adjust offsets so that the point at (center_x, center_y) stays fixed.
        self.offset_x = center_x - factor * (center_x - self.offset_x)
        self.offset_y = center_y - factor * (center_y - self.offset_y)
        self.zoom = new_zoom
        self.queue_draw()
    
    def reset_zoom(self):
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.queue_draw()

    def finalize_room(self):
        # Only finalize if there are enough points to form a room
        if self.current_room_points and len(self.current_room_points) >= 3:
            # Ensure the room is closed by appending the first point if necessary
            if self.current_room_points[0] != self.current_room_points[-1]:
                self.current_room_points.append(self.current_room_points[0])
            new_room = self.Room(self.current_room_points)
            self.rooms.append(new_room)
            print(f"Finalized room with points: {self.current_room_points}")
        # Clear the temporary room points and preview
        self.current_room_points = []
        self.current_room_preview = None
        self.queue_draw()

def create_canvas_area(config_constants):
    return CanvasArea(config_constants)
