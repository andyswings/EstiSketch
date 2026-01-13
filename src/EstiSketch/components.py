from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class Level:
    """Represents a vertical building level (story)."""
    id: str  # Unique identifier
    name: str = "Level 1"
    elevation: float = 0.0
    height: float = 96.0  # Default 8ft


@dataclass
class Layer:
    """Represents a layer that objects can be assigned to."""
    id: str  # Unique identifier (e.g., "layer-abc123...")
    name: str = "Layer 0"  # Display name
    visible: bool = True  # Whether objects on this layer are drawn
    locked: bool = False  # Whether objects on this layer can be selected/edited
    opacity: float = 1.0  # Layer opacity (0.0 to 1.0)
    # ID of the level this layer belongs to. Empty = Global.
    level_id: str = ""


@dataclass(eq=False)
class Wall:
    def __init__(
            self,
            start,
            end,
            width,
            height,
            exterior_wall=False,
            identifier="",
            layer_id: str = "",
            is_curved=False,
            arc_center=None,
            arc_radius=None):
        self.identifier = identifier  # unique string identifier
        self.layer_id = layer_id  # layer this wall belongs to
        self.start = start  # tuple of (x, y)
        self.end = end      # tuple of (x, y)
        self.width = width  # integer (inches)
        self.height = height  # integer (inches)
        self.exterior_wall = exterior_wall  # boolean

        # Curved wall properties
        self.is_curved = is_curved  # True if this is a curved/arc wall
        self.arc_center = arc_center if is_curved else None  # (x, y) center of arc
        self.arc_radius = arc_radius if is_curved else None  # radius of arc in inches

        # Footer properties
        self.footer = False
        self.footer_left_offset = 6.0
        self.footer_right_offset = 6.0
        self.footer_depth = 8.0

        # Material properties
        self.material = "wood"
        self.interior_finish = "drywall"
        self.exterior_finish = "stucco"

        # Construction details
        self.stud_spacing = 16
        self.insulation_type = "fiberglass"
        self.fire_rating = "1"


@dataclass
class Polyline:
    def __init__(self, start, end, identifier="", layer_id: str = "", color: tuple = (0.0, 0.0, 0.0)):
        self.identifier = identifier  # unique string identifier
        self.layer_id = layer_id  # layer this polyline belongs to
        self.start = start  # tuple of (x, y)
        self.end = end      # tuple of (x, y)
        self.style = "solid"  # or "dashed"
        self.color = color


@dataclass
class Room:
    def __init__(self,
                 points: List[Tuple[float,
                                    float]],
                 height: float = 96.0,
                 identifier="",
                 layer_id: str = ""):
        self.identifier = identifier  # unique string identifier
        self.layer_id = layer_id  # layer this room belongs to
        # List of (x, y) tuples defining the room vertices
        self.points = points
        self.height = height  # Room height in inches
        self.floor_type = "default"
        self.wall_finish = "default"
        self.room_type = "undefined"
        self.name = ""


@dataclass
class Door:
    def __init__(
            self,
            door_type: str,
            width: float,
            height: float,
            swing: str,
            orientation: str,
            identifier="",
            layer_id: str = ""):
        self.identifier = identifier  # unique string identifier
        self.layer_id = layer_id  # layer this door belongs to
        self.door_type = door_type  # Type of door
        self.width = width  # Door width in inches
        self.height = height    # Door height in inches
        self.swing = swing  # Door swing direction (e.g., "left", "right")
        # Orientation of the door (e.g., "inswing", "outswing")
        self.orientation = orientation
        # (x, y) tuple for independent doors (not on a wall)
        self.floating_pos = None


@dataclass
class Window:
    def __init__(
            self,
            width: float,
            height: float,
            window_type: str,
            identifier="",
            layer_id: str = ""):
        self.identifier = identifier  # unique string identifier
        self.layer_id = layer_id  # layer this window belongs to
        self.width = width  # Window width in inches
        self.height = height  # Window height in inches
        self.window_type = window_type  # Type of window
        # (x, y) tuple for independent windows (not on a wall)
        self.floating_pos = None


@dataclass(eq=False)
class Text:
    x: float
    y: float
    content: str = "Text"
    width: float = 100.0
    height: float = 50.0
    identifier: str = ""
    layer_id: str = ""  # layer this text belongs to
    font_size: float = 12.0
    font_family: str = "Sans"
    bold: bool = False
    italic: bool = False
    underline: bool = False
    rotation: float = 0.0  # Rotation angle in degrees
    color: tuple = (0.0, 0.0, 0.0)  # RGB color


@dataclass(eq=False)
class Dimension:
    start: tuple  # (x, y) start point in inches
    end: tuple  # (x, y) end point in inches
    offset: float  # Perpendicular distance from measured line (in inches)
    identifier: str = ""
    layer_id: str = ""  # layer this dimension belongs to
    text_size: float = 12.0  # Font size for dimension text
    show_arrows: bool = True  # Whether to show extension arrows
    line_style: str = "solid"  # "solid" or "dashed"
    color: tuple = (0.0, 0.0, 0.0)  # RGB color


@dataclass(eq=False)
class Circle:
    center: tuple  # (x, y) in inches
    radius: float  # in inches
    identifier: str = ""
    layer_id: str = ""
    line_style: str = "solid"
    color: tuple = (0.0, 0.0, 0.0)


@dataclass(eq=False)
class Arc:
    center: tuple  # (x, y) in inches
    radius: float  # in inches
    start_angle: float  # radians
    end_angle: float  # radians
    identifier: str = ""
    layer_id: str = ""
    line_style: str = "solid"
    color: tuple = (0.0, 0.0, 0.0)
