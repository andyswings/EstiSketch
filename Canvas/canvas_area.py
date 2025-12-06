import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject

from measurement_utils import MeasurementConverter
from components import Wall, Room, Text
from snapping_manager import SnappingManager

from Canvas.canvas_draw import CanvasDrawMixin
from Canvas.canvas_events import CanvasEventsMixin
from Canvas.canvas_state import CanvasStateMixin
from Canvas.canvas_geometry import CanvasGeometryMixin
from Canvas.canvas_tool import CanvasToolMixin

class CanvasArea(Gtk.DrawingArea, 
                 CanvasDrawMixin, 
                 CanvasEventsMixin, 
                 CanvasStateMixin, 
                 CanvasGeometryMixin,
                 CanvasToolMixin):
    
    __gtype_name__ = 'CanvasArea'
    __gsignals__ = {
        # when selection changes, send the new list of selected items
        'selection-changed': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }
    
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
        self.ruler_offset = 80
        self.offset_x = self.ruler_offset
        self.offset_y = self.ruler_offset
        

        # Wall drawing state
        self.walls = []
        self.current_wall = None
        self.drawing_wall = False
        self.wall_sets = []
        
        self.auto_dimension_mode = False
        self.last_wall_angle = None
        
        
        # Wall editing state
        self.editing_wall = None     # The wall being edited
        self.editing_handle = None   # "start" or "end"
        self.handle_radius = 10      # device pixels for hit detection
        
        
        # Polyline drawing state
        self.polylines = []                # current segments (list of Polyline)
        self.current_polyline_start = None # last click point
        self.current_polyline_preview = None   # live endpoint while moving
        self.drawing_polyline = False      # are we in the middle of drawing?
        self.polyline_sets = []            # list of finished polyline lists


        # Room drawing state
        self.rooms = []                # Finalized Room objects
        self.current_room_points = []  # Manual room drawing points
        self.current_room_preview = None  # Live preview point (snapped)
        
        
        self.doors = []  # List of door placements; each item is a tuple: (wall, door, position_ratio)
        self.windows = []  # List of window placements; each item is a tuple: (wall, window, position_ratio)
        self.texts = [] # List of Text objects

        # Alignment snapping (used for walls and rooms)
        self.alignment_candidate = None
        self.raw_current_end = None

        self.snap_type = "none"
        self.tool_mode = None  # "draw_walls" or "draw_rooms"
        
        # ID stack 
        self.existing_ids = []

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
        self.Text = Text
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
    
    def delete_selected(self):
        """
        Delete the currently selected object(s) from the canvas.
        Supports walls, rooms, polylines, doors, and windows.
        """
        if not self.selected_items:
            return

        room_vertices_to_delete = {}  # room_identifier -> list of indices

        for item in list(self.selected_items):            
            # Walls
            if item["type"] == "wall":
                selected_id = item["object"].identifier
                for wall_set in self.wall_sets:
                    for wall in wall_set:
                        if wall.identifier == selected_id:
                            wall_set.remove(wall)
                    
                    # If wall set is empty remove it
                    if len(wall_set) == 0:
                        self.wall_sets.remove(wall_set)
            
            # Rooms
            if item["type"] == "vertex":
                # item["object"] is (room, index)
                room = item["object"][0]
                index = item["object"][1]
                if room.identifier not in room_vertices_to_delete:
                    room_vertices_to_delete[room.identifier] = []
                room_vertices_to_delete[room.identifier].append(index)
                    
            # Polylines: search and remove from polyline_sets (list of lists)
            if item["type"] == "polyline":
                # selection entries may come from click (object only) or box-select (object + identifier)
                selected_obj = item.get("object")
                selected_id = item.get("identifier") or getattr(selected_obj, "identifier", None)
                # iterate over a copy so removals are safe
                for poly_list in list(self.polyline_sets):
                    found_index = None
                    # find the exact segment by identity or by identifier
                    for idx, segment in enumerate(poly_list):
                        if segment is selected_obj or (selected_id is not None and getattr(segment, "identifier", None) == selected_id):
                            found_index = idx
                            break
                    if found_index is not None:
                        del poly_list[found_index]
                    if len(poly_list) == 0:
                        self.polyline_sets.remove(poly_list)
            # Doors
            if item["type"] == "door":
                ...
            # Windows
            if item["type"] == "window":
                ...

            # Text
            if item["type"] == "text":
                text_obj = item["object"]
                if text_obj in self.texts:
                    self.texts.remove(text_obj)

        # Process room vertex deletions
        for room_id, indices in room_vertices_to_delete.items():
            # Find the actual room object in self.rooms
            target_room = next((r for r in self.rooms if r.identifier == room_id), None)
            if not target_room:
                continue

            # Sort indices in descending order so earlier indices remain valid
            indices.sort(reverse=True)
            
            for idx in indices:
                # If room has enough points to stay a polygon (needs > 3 to remove one and still have >=3)
                # Wait, if it has 3 points, removing one makes it 2 (line), effectively destroying the room?
                # The logic says: if len > 3, remove point. Else remove room.
                if len(target_room.points) > 3:
                    if 0 <= idx < len(target_room.points):
                        del target_room.points[idx]
                else:
                    # Not enough points to sustain a room
                    if target_room in self.rooms:
                        self.rooms.remove(target_room)
                    # Once room is removed, stop processing its vertices
                    break

        self.selected_items.clear()
        self.queue_draw()
        self.emit('selection-changed', self.selected_items)


def create_canvas_area(config_constants):
    return CanvasArea(config_constants)
