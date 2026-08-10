from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class Level:
    """Represents a vertical building level (story)."""
    id: str  # Unique identifier
    name: str = "Level 1"
    elevation: float = 0.0
    height: float = 96.0  # Default 8ft
    floor_thickness: float = 10.0  # Thickness of floor structure


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
            arc_radius=None,
            visible=True,
            locked=False,
            height_at_end=None):
        self.identifier = identifier  # unique string identifier
        self.layer_id = layer_id  # layer this wall belongs to
        self.visible = visible
        self.locked = locked
        self.start = start  # tuple of (x, y)
        self.end = end      # tuple of (x, y)
        self.width = width  # integer (inches)
        self.height = height  # integer (inches) - start height
        self.height_at_end = height_at_end if height_at_end is not None else height  # integer (inches) - end height
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

        # Symbolic wall - only renders footer, wall itself not shown
        self.symbolic = False

        # Material properties
        self.material = "wood"
        self.interior_finish = "drywall"
        self.exterior_finish = "stucco"

        # Construction details
        self.stud_spacing = 16
        self.insulation_type = "fiberglass"
        self.fire_rating = "1"

    @property
    def is_sloped(self) -> bool:
        """Returns True if the wall start and end heights differ."""
        return abs(self.height - self.height_at_end) > 0.01

    @property
    def min_height(self) -> float:
        """Returns the lower height of the wall ends."""
        return min(self.height, self.height_at_end)

    @property
    def max_height(self) -> float:
        """Returns the higher height of the wall ends."""
        return max(self.height, self.height_at_end)

    @property
    def avg_height(self) -> float:
        """Returns average height of the wall."""
        return (self.height + self.height_at_end) / 2.0



@dataclass
class Polyline:
    def __init__(self, start, end, identifier="", layer_id: str = "", color: tuple = (0.0, 0.0, 0.0), visible=True, locked=False):
        self.identifier = identifier  # unique string identifier
        self.layer_id = layer_id  # layer this polyline belongs to
        self.visible = visible
        self.locked = locked
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
                 layer_id: str = "",
                 visible=True,
                 locked=False):
        self.identifier = identifier  # unique string identifier
        self.layer_id = layer_id  # layer this room belongs to
        self.visible = visible
        self.locked = locked
        # List of (x, y) tuples defining the room vertices
        self.points = points
        self.height = height  # Room height in inches
        self.floor_type = "default"
        self.wall_finish = "default"
        self.room_type = "undefined"
        self.name = ""

        # Foundation slab properties
        self.is_slab = False  # True if this room represents a foundation slab
        self.slab_thickness = 4.0  # inches (typical 4" slab)
        self.slab_reinforcement = "wire_mesh"  # wire_mesh, rebar_grid, fiber
        self.slab_edge_type = "thickened"  # thickened, monolithic, floating


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
            layer_id: str = "",
            visible=True,
            locked=False):
        self.identifier = identifier  # unique string identifier
        self.layer_id = layer_id  # layer this door belongs to
        self.visible = visible
        self.locked = locked
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
            layer_id: str = "",
            visible=True,
            locked=False):
        self.identifier = identifier  # unique string identifier
        self.layer_id = layer_id  # layer this window belongs to
        self.visible = visible
        self.locked = locked
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
    visible: bool = True
    locked: bool = False
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
    visible: bool = True
    locked: bool = False
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
    visible: bool = True
    locked: bool = False
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
    visible: bool = True
    locked: bool = False
    line_style: str = "solid"
    color: tuple = (0.0, 0.0, 0.0)


@dataclass(eq=False)
class Stair:
    """Represents a staircase spanning between levels or within a level."""
    
    # Standard object properties
    identifier: str = ""
    layer_id: str = ""
    visible: bool = True
    locked: bool = False
    
    # Placement
    start_point: Tuple[float, float] = (0.0, 0.0) # (x, y) where stairs begin (bottom)
    direction_angle: float = 0.0  # radians, direction of ascent
    
    # Level spanning
    start_level_id: str = ""  # Level where stairs start (bottom)
    end_level_id: str = ""    # Level where stairs end (top)
    
    # Type
    stair_type: str = "straight"  # "straight", "L-shaped", "U-shaped", "spiral"
    width: float = 36.0  # inches
    
    # Vertical dimensions
    total_rise: float = 106.0  # inches (default for 8ft wall + 10in floor)
    riser_height: float = 7.57  # inches per step
    num_steps: int = 14
    
    # Horizontal dimensions
    tread_depth: float = 11.0  # inches
    total_run: float = 143.0  # inches (calculated: (num_steps-1) * tread_depth)
    nosing: float = 1.0  # inches
    
    # Railings
    has_left_rail: bool = True
    has_right_rail: bool = True
    rail_height: float = 36.0  # inches
    
    # Visual
    show_up_arrow: bool = True
    show_step_count: bool = True
    
    # L-Shaped / U-Shaped Specifics (for future use)
    landing_depth: float = 36.0
    turn_direction: str = "left"  # "left", "right"
    steps_before_landing: int = 0  # 0 = auto-calculate (half)
    
    # Spiral Specifics (for future use)
    inner_radius: float = 6.0
    rotation_degrees: float = 270.0
