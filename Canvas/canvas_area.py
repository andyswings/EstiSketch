import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject

from measurement_utils import MeasurementConverter
from components import Wall, Room, Text, Dimension
from snapping_manager import SnappingManager

from Canvas.canvas_draw import CanvasDrawMixin
from Canvas.canvas_events import CanvasEventsMixin
from Canvas.canvas_state import CanvasStateMixin
from Canvas.canvas_geometry import CanvasGeometryMixin
from Canvas.canvas_tool import CanvasToolMixin
from Canvas.events_selection import CanvasSelectionMixin
from Canvas.events_wall import CanvasWallMixin
from Canvas.events_room import CanvasRoomMixin
from Canvas.events_tools import CanvasToolsMixin
from Canvas.events_edit import EditEventsMixin
from Canvas.utils import UtilsMixin
from Canvas.events_helpers import EventsHelpersMixin


class CanvasArea(Gtk.DrawingArea, 
                 CanvasDrawMixin, 
                 CanvasEventsMixin, 
                 CanvasStateMixin, 
                 CanvasGeometryMixin,
                 CanvasToolMixin,
                 CanvasSelectionMixin,
                 CanvasWallMixin,
                 CanvasRoomMixin,
                 CanvasToolsMixin,
                 EditEventsMixin,
                 UtilsMixin,
                 EventsHelpersMixin):
    
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
        
        # Layers system - max 24 layers
        self.MAX_LAYERS = 24
        # Create default layer using generate_identifier
        default_layer_id = self.generate_identifier("layer", [])
        from components import Layer
        self.layers = [Layer(
            id=default_layer_id,
            name="Layer 0",
            visible=True,
            locked=False,
            opacity=1.0
        )]
        self.active_layer_id = default_layer_id
        

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
        self.handle_radius = 15      # device pixels for hit detection
        
        
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
        
        # Dimension drawing state
        self.dimensions = []  # List of finalized Dimension objects
        self.drawing_dimension = False  # Flag for dimension mode
        self.dimension_start = None  # First click point (x, y)
        self.dimension_end = None  # Second click point (x, y)
        self.dimension_offset_preview = None  # Mouse position for offset preview

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
        
        # Clipboard for copy/paste operations
        self.clipboard = []


        # Expose Wall and Room for mixins
        self.Wall = Wall
        self.Room = Room
        self.Text = Text
        self.Dimension = Dimension
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
    
    # ─────────────────────────────────────────────────────────────────────────
    # Layer Management Methods
    # ─────────────────────────────────────────────────────────────────────────
    
    def add_layer(self, name: str = None) -> str:
        """Add a new layer and return its ID. Returns None if max layers reached."""
        if len(self.layers) >= self.MAX_LAYERS:
            print(f"Cannot add more than {self.MAX_LAYERS} layers")
            return None
        
        from components import Layer
        existing_ids = [layer.id for layer in self.layers]
        new_layer_id = self.generate_identifier("layer", existing_ids)
        layer_num = len(self.layers)
        layer_name = name if name else f"Layer {layer_num}"
        
        new_layer = Layer(
            id=new_layer_id,
            name=layer_name,
            visible=True,
            locked=False,
            opacity=1.0
        )
        self.layers.append(new_layer)
        return new_layer_id
    
    def remove_layer(self, layer_id: str) -> bool:
        """Remove a layer by ID. Cannot remove last layer. Returns True if removed."""
        if len(self.layers) <= 1:
            print("Cannot remove the last layer")
            return False
        
        for i, layer in enumerate(self.layers):
            if layer.id == layer_id:
                self.layers.pop(i)
                # If active layer was removed, switch to first layer
                if self.active_layer_id == layer_id:
                    self.active_layer_id = self.layers[0].id
                return True
        return False
    
    def get_layer_by_id(self, layer_id: str):
        """Get a Layer object by its ID."""
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        return None
    
    def set_active_layer(self, layer_id: str) -> bool:
        """Set the active layer by ID. Returns True if successful."""
        layer = self.get_layer_by_id(layer_id)
        if layer:
            self.active_layer_id = layer_id
            return True
        return False
    
    def get_visible_layer_ids(self) -> set:
        """Get set of IDs for all visible layers."""
        return {layer.id for layer in self.layers if layer.visible}
    
    def get_locked_layer_ids(self) -> set:
        """Get set of IDs for all locked layers."""
        return {layer.id for layer in self.layers if layer.locked}
    
    def is_object_on_visible_layer(self, obj) -> bool:
        """Check if an object is on a visible layer. Objects with no layer_id are always visible."""
        layer_id = getattr(obj, 'layer_id', '')
        if not layer_id:  # Empty layer_id means visible on all layers (legacy compatibility)
            return True
        return layer_id in self.get_visible_layer_ids()
    
    def is_object_on_locked_layer(self, obj) -> bool:
        """Check if an object is on a locked layer. Objects with no layer_id are never locked."""
        layer_id = getattr(obj, 'layer_id', '')
        if not layer_id:  # Empty layer_id means not locked
            return False
        return layer_id in self.get_locked_layer_ids()

    def get_object_opacity(self, obj) -> float:
        """Get the opacity of an object based on its layer."""
        layer_id = getattr(obj, 'layer_id', '')
        if not layer_id:
            return 1.0
        layer = self.get_layer_by_id(layer_id)
        if layer:
            return layer.opacity
        return 1.0
    
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
                # item["object"] is (wall, door, ratio) tuple
                door_tuple = item["object"]
                if door_tuple in self.doors:
                    self.doors.remove(door_tuple)
            # Windows
            if item["type"] == "window":
                # item["object"] is (wall, window, ratio) tuple
                window_tuple = item["object"]
                if window_tuple in self.windows:
                    self.windows.remove(window_tuple)

            # Text
            if item["type"] == "text":
                text_obj = item["object"]
                if text_obj in self.texts:
                    self.texts.remove(text_obj)
            
            # Dimension
            if item["type"] == "dimension":
                dim_obj = item["object"]
                if dim_obj in self.dimensions:
                    self.dimensions.remove(dim_obj)


        # Process room vertex deletions
        for room_id, indices in room_vertices_to_delete.items():
            # Find the actual room object in self.rooms
            target_room = next((r for r in self.rooms if r.identifier == room_id), None)
            if not target_room:
                continue

            # Sort indices in descending order so earlier indices remain valid
            indices.sort(reverse=True)
            
            # Delete all requested vertices
            for idx in indices:
                if 0 <= idx < len(target_room.points):
                    del target_room.points[idx]
            
            # After all deletions, check if room still has enough points
            # Rooms now store only unique vertices (no closing point)
            # Need at least 3 points for a valid polygon
            if len(target_room.points) < 3:
                if target_room in self.rooms:
                    self.rooms.remove(target_room)

        self.selected_items.clear()
        self.queue_draw()
        self.emit('selection-changed', self.selected_items)
    
    def select_all(self):
        """Select all objects on the canvas"""
        self.selected_items.clear()
        
        # Select all walls
        for wall_set in self.wall_sets:
            for wall in wall_set:
                if not self.is_object_on_locked_layer(wall) and self.is_object_on_visible_layer(wall):
                    self.selected_items.append({"type": "wall", "object": wall})
        
        # Select all room vertices
        for room in self.rooms:
            if not self.is_object_on_locked_layer(room) and self.is_object_on_visible_layer(room):
                for idx in range(len(room.points)):
                    self.selected_items.append({"type": "vertex", "object": (room, idx)})
        
        # Select all doors
        for door_item in self.doors:
            # door_item is (wall, door, ratio)
            # check the door object (index 1)
            if not self.is_object_on_locked_layer(door_item[1]) and self.is_object_on_visible_layer(door_item[1]):
                self.selected_items.append({"type": "door", "object": door_item})
        
        # Select all windows
        for window_item in self.windows:
            if not self.is_object_on_locked_layer(window_item[1]) and self.is_object_on_visible_layer(window_item[1]):
                self.selected_items.append({"type": "window", "object": window_item})
        
        # Select all text objects
        for text in self.texts:
            if not self.is_object_on_locked_layer(text) and self.is_object_on_visible_layer(text):
                self.selected_items.append({"type": "text", "object": text})
        
        # Select all dimensions
        for dim in self.dimensions:
            if not self.is_object_on_locked_layer(dim) and self.is_object_on_visible_layer(dim):
                self.selected_items.append({"type": "dimension", "object": dim})
        
        # Select all polylines
        for polyline_set in self.polyline_sets:
            for polyline in polyline_set:
                if not self.is_object_on_locked_layer(polyline) and self.is_object_on_visible_layer(polyline):
                    self.selected_items.append({"type": "polyline", "object": polyline})
        
        self.queue_draw()
        self.emit('selection-changed', self.selected_items)
        print(f"Selected {len(self.selected_items)} objects")

    def deselect_items_on_layer(self, layer_id):
        """Deselect all items belonging to the specified layer_id."""
        if not layer_id or not self.selected_items:
            return
            
        new_selection = []
        changed = False
        
        for item in self.selected_items:
            obj = item["object"]
            
            # Extract real object to check layer_id
            real_obj = obj
            otype = item.get("type")
            
            if otype in ("door", "window"):
                if isinstance(obj, tuple) and len(obj) >= 2:
                    real_obj = obj[1]
            elif otype == "vertex":
                if isinstance(obj, tuple) and len(obj) >= 1:
                    real_obj = obj[0] # The room
            elif otype in ("wall_handle", "polyline_handle", "dimension_handle"):
                if isinstance(obj, tuple) and len(obj) >= 1:
                     real_obj = obj[0]
            
            # Check layer
            obj_layer = getattr(real_obj, 'layer_id', '')
            if obj_layer == layer_id:
                changed = True
            else:
                new_selection.append(item)
        
        if changed:
            self.selected_items = new_selection
            self.queue_draw()
            self.emit('selection-changed', self.selected_items)
    
    def copy_selected(self):
        """Copy selected items to clipboard"""
        import copy as copy_module
        self.clipboard.clear()
        
        for item in self.selected_items:
            # Store a deep copy of the item dictionary
            self.clipboard.append(copy_module.deepcopy(item))
    
    def cut_selected(self):
        """Cut selected items (copy + delete)"""
        self.copy_selected()
        self.delete_selected()
        self.save_state()
    
    def paste(self):
        """Paste clipboard items with offset"""
        if not self.clipboard:
            return
        
        import copy as copy_module
        import string
        import random
        
        # Offset for pasted items (12 inches down and right)
        offset = (12, 12)
        
        # Clear current selection
        self.selected_items.clear()
        
        # Paste each item
        for item in self.clipboard:
            item_type = item.get("type")
            
            if item_type == "wall":
                wall = item["object"]
                # Create new wall with offset
                new_wall = self.Wall(
                    start=(wall.start[0] + offset[0], wall.start[1] + offset[1]),
                    end=(wall.end[0] + offset[0], wall.end[1] + offset[1]),
                    width=wall.width,
                    height=wall.height,
                    exterior_wall=wall.exterior_wall,
                    identifier=self.generate_identifier("wall", self.existing_ids)
                )
                # Copy all other properties
                new_wall.footer = wall.footer
                new_wall.footer_left_offset = wall.footer_left_offset
                new_wall.footer_right_offset = wall.footer_right_offset
                new_wall.footer_depth = wall.footer_depth
                new_wall.material = wall.material
                new_wall.interior_finish = wall.interior_finish
                new_wall.exterior_finish = wall.exterior_finish
                new_wall.stud_spacing = wall.stud_spacing
                new_wall.insulation_type = wall.insulation_type
                new_wall.fire_rating = wall.fire_rating
                
                # Add to a new wall set
                self.wall_sets.append([new_wall])
                self.selected_items.append({"type": "wall", "object": new_wall})
            
            elif item_type == "door":
                # Doors are (wall, door, ratio) tuples
                old_wall, door, ratio = item["object"]
                # Create new door object
                new_door = copy_module.deepcopy(door)
                new_door.identifier = self.generate_identifier("door", self.existing_ids)
                
                # Paste on same wall with offset ratio
                new_ratio = ratio + 0.1  # 10% offset along the wall
                if new_ratio > 1.0:
                    new_ratio = min(0.9, ratio - 0.1)  # Try going backward or clamp to 0.9
                
                # Store door on same wall
                new_door_tuple = (old_wall, new_door, new_ratio)
                self.doors.append(new_door_tuple)
                self.selected_items.append({"type": "door", "object": new_door_tuple})
            
            elif item_type == "window":
                # Windows are (wall, window, ratio) tuples
                old_wall, window, ratio = item["object"]
                # Create new window object
                new_window = copy_module.deepcopy(window)
                new_window.identifier = self.generate_identifier("window", self.existing_ids)
                
                # Paste on same wall with offset ratio
                new_ratio = ratio + 0.1  # 10% offset along the wall
                if new_ratio > 1.0:
                    new_ratio = min(0.9, ratio - 0.1)  # Try going backward or clamp to 0.9
                
                # Store window on same wall
                new_window_tuple = (old_wall, new_window, new_ratio)
                self.windows.append(new_window_tuple)
                self.selected_items.append({"type": "window", "object": new_window_tuple})
            
            elif item_type == "text":
                text = item["object"]
                # Create new text with offset
                new_text = copy_module.deepcopy(text)               
                new_text.x = text.x + offset[0]
                new_text.y = text.y + offset[1]
                new_text.identifier = self.generate_identifier("text", self.existing_ids)
                
                self.texts.append(new_text)
                self.selected_items.append({"type": "text", "object": new_text})
            
            elif item_type == "dimension":
                dim = item["object"]
                # Create new dimension with offset
                new_dim = self.Dimension(
                    start=(dim.start[0] + offset[0], dim.start[1] + offset[1]),
                    end=(dim.end[0] + offset[0], dim.end[1] + offset[1]),
                    offset=dim.offset,
                    identifier=self.generate_identifier("dimension", self.existing_ids),
                    text_size=dim.text_size,
                    show_arrows=dim.show_arrows,
                    line_style=dim.line_style,
                    color=dim.color
                )
                
                self.dimensions.append(new_dim)
                self.selected_items.append({"type": "dimension", "object": new_dim})
            
            elif item_type == "polyline":
                poly = item["object"]
                # Create new polyline with offset
                new_poly = copy_module.deepcopy(poly)
                new_poly.start = (poly.start[0] + offset[0], poly.start[1] + offset[1])
                new_poly.end = (poly.end[0] + offset[0], poly.end[1] + offset[1])
                new_poly.identifier = self.generate_identifier("polyline", self.existing_ids)
                
                # Add as a new polyline set
                self.polyline_sets.append([new_poly])
                self.selected_items.append({"type": "polyline", "object": new_poly, "identifier": new_poly.identifier})
            
            elif item_type == "vertex":
                # Room vertices - we'll handle this by pasting the whole room
                # Skip individual vertices
                pass
        
        # Handle rooms (check for room objects in clipboard)
        rooms_to_paste = set()
        for item in self.clipboard:
            if item["type"] == "vertex":
                room, idx = item["object"]
                rooms_to_paste.add(id(room))  # Use object id to track unique rooms
        
        # Paste unique rooms
        for item in self.clipboard:
            if item["type"] == "vertex":
                room, idx = item["object"]
                if id(room) in rooms_to_paste:
                    # Create new room with offset
                    new_points = [(pt[0] + offset[0], pt[1] + offset[1]) for pt in room.points]
                    new_room = self.Room(
                        points=new_points,
                        height=room.height,
                        identifier=self.generate_identifier("room", self.existing_ids),
                        layer_id=self.active_layer_id
                    )
                    new_room.floor_type = room.floor_type
                    new_room.wall_finish = room.wall_finish
                    new_room.room_type = room.room_type
                    new_room.name = room.name
                    
                    self.rooms.append(new_room)
                    # Add all vertices to selection
                    for i in range(len(new_room.points)):
                        self.selected_items.append({"type": "vertex", "object": (new_room, i)})
                    
                    rooms_to_paste.remove(id(room))  # Don't paste again
        
        self.save_state()
        self.queue_draw()
        self.emit('selection-changed', self.selected_items)


def create_canvas_area(config_constants):
    return CanvasArea(config_constants)
