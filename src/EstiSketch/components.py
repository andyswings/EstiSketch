import math
from dataclasses import dataclass, field
from typing import List, Tuple

from .Canvas.utils import generate_identifier


@dataclass
class Level:
    """Represents a vertical building level (story)."""
    id: str = ""  # Unique identifier
    name: str = "Level 1"
    elevation: float = 0.0
    height: float = 96.0  # Default 8ft
    floor_thickness: float = 10.0  # Thickness of floor structure

    def __post_init__(self) -> None:
        if not self.id:
            self.id = generate_identifier("level")

    @property
    def identifier(self) -> str:
        """Alias for id so all objects expose .identifier consistently."""
        return self.id

    @identifier.setter
    def identifier(self, value: str) -> None:
        self.id = value


@dataclass
class Layer:
    """Represents a layer that objects can be assigned to."""
    id: str = ""  # Unique identifier (e.g., "layer-abc123...")
    name: str = "Layer 0"  # Display name
    visible: bool = True  # Whether objects on this layer are drawn
    locked: bool = False  # Whether objects on this layer can be selected/edited
    opacity: float = 1.0  # Layer opacity (0.0 to 1.0)
    # ID of the level this layer belongs to. Empty = Global.
    level_id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = generate_identifier("layer")

    @property
    def identifier(self) -> str:
        """Alias for id so all objects expose .identifier consistently."""
        return self.id

    @identifier.setter
    def identifier(self, value: str) -> None:
        self.id = value


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
        self.identifier = (
            identifier if identifier else generate_identifier("wall")
        )  # unique string identifier
        self.layer_id = layer_id  # layer this wall belongs to
        self.visible = visible
        self.locked = locked
        self.start = start  # tuple of (x, y)
        self.end = end      # tuple of (x, y)
        self.width = width  # integer (inches)
        self.height = height  # integer (inches) - start height
        self.height_at_end = (
            height_at_end if height_at_end is not None else height
        )  # integer (inches) - end height
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
    def __init__(
            self,
            start,
            end,
            identifier="",
            layer_id: str = "",
            color: tuple = (0.0, 0.0, 0.0),
            visible=True,
            locked=False):
        self.identifier = (
            identifier if identifier else generate_identifier("polyline")
        )  # unique string identifier
        self.layer_id = layer_id  # layer this polyline belongs to
        self.visible = visible
        self.locked = locked
        self.start = start  # tuple of (x, y)
        self.end = end      # tuple of (x, y)
        self.style = "solid"  # or "dashed"
        self.color = color


@dataclass
class Hole:
    """A floor opening in a Room, derived from the object that created it.

    ``source_id`` links back to that object (e.g. ``"stair:<identifier>"``);
    ``points`` are regenerated from it and are not the source of truth.
    ``ceiling_only`` holes (lower-level ceiling under a stair) don't open the
    floor and only affect ceiling takeoff.
    """
    source_id: str = ""
    points: List[Tuple[float, float]] = field(default_factory=list)
    ceiling_only: bool = False
    identifier: str = ""

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("hole")


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
        self.identifier = (
            identifier if identifier else generate_identifier("room")
        )  # unique string identifier
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
        # Derived floor openings (see Hole); regenerated from their sources
        self.holes: List[Hole] = []

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
        self.identifier = (
            identifier if identifier else generate_identifier("door")
        )  # unique string identifier
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
        self.identifier = (
            identifier if identifier else generate_identifier("window")
        )  # unique string identifier
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

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("text")


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

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("dimension")


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

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("circle")


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

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("arc")


@dataclass(eq=False)
class Stair:
    """Represents a staircase spanning between levels or within a level."""

    # Standard object properties
    identifier: str = ""
    layer_id: str = ""
    visible: bool = True
    locked: bool = False

    # Placement
    start_point: Tuple[float, float] = (0.0, 0.0)  # (x, y) where stairs begin (bottom)
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

    # Extra clearance (inches) added around the floor opening this stair cuts
    opening_clearance: float = 0.0

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
    winder_count: int = 0  # L-shaped: 0 = flat landing, 2-5 = pie-shaped winder treads

    # Spiral Specifics (for future use)
    inner_radius: float = 6.0
    rotation_degrees: float = 270.0

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("stair")


@dataclass(eq=False)
class BackgroundImage:
    """A raster blueprint/underlay image placed behind the drawing.

    The image is positioned by its top-left corner (``x``, ``y``) in model
    inches and scaled by ``scale_x``/``scale_y`` (inches per source pixel).
    The raw encoded file bytes are kept in ``image_data`` so projects stay
    portable; ``image_path`` is only informational.
    """
    identifier: str = ""
    image_path: str = ""
    x: float = 0.0          # Origin (top-left) in model inches
    y: float = 0.0
    scale_x: float = 1.0    # Inches per pixel
    scale_y: float = 1.0
    rotation: float = 0.0   # Degrees, rotated about the origin
    opacity: float = 0.5    # 0.0 to 1.0
    visible: bool = True
    locked: bool = True     # Locked from accidental drag
    level_id: str = ""      # Associated building level ("" = every level)
    name: str = ""
    image_data: bytes = b""  # Encoded image file contents (PNG/JPG/...)
    pixel_width: int = 0
    pixel_height: int = 0

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("blueprint")


@dataclass(eq=False)
class DimensionChain:
    """Represents a continuous string of aligned dimensions sharing a common baseline.

    Attributes:
        points: Ordered list of (x, y) coordinates defining measurement points.
        offset: Perpendicular offset distance (inches) from baseline.
        summary_dimension: Whether to render an overall cumulative summary dimension.
        summary_offset: Extra perpendicular distance (inches) for the summary line.
        identifier: Unique string ID.
        layer_id: Layer ID this chain belongs to.
        visible: Whether chain is rendered.
        locked: Whether chain is locked from editing.
        text_size: Font size in points.
        show_arrows: Whether to render arrows or architectural tick marks.
        arrow_style: "architectural_tick" or "arrow".
        line_style: "solid" or "dashed".
        color: RGB tuple (0.0 to 1.0).
        witness_gap: Distance (inches) from measured point to witness line start.
        witness_overhang: Distance (inches) witness line extends past dimension line.
    """
    points: List[Tuple[float, float]] = field(default_factory=list)
    offset: float = 18.0
    summary_dimension: bool = True
    summary_offset: float = 16.0
    identifier: str = ""
    layer_id: str = ""
    visible: bool = True
    locked: bool = False
    text_size: float = 12.0
    show_arrows: bool = True
    arrow_style: str = "architectural_tick"
    line_style: str = "solid"
    color: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    witness_gap: float = 4.0
    witness_overhang: float = 6.0

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("dim_chain")

    @property
    def total_length(self) -> float:
        """Returns the total measured baseline length of the chain."""
        if len(self.points) < 2:
            return 0.0
        p0 = self.points[0]
        p1 = self.points[1]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length == 0:
            return 0.0
        ux, uy = dx / length, dy / length
        projections = [
            (p[0] - p0[0]) * ux + (p[1] - p0[1]) * uy for p in self.points
        ]
        return max(projections) - min(projections)

    def get_sorted_points(self) -> List[Tuple[float, float]]:
        """Returns the points sorted by their projection along the baseline."""
        if len(self.points) < 2:
            return list(self.points)
        p0 = self.points[0]
        p1 = self.points[1]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length == 0:
            return list(self.points)
        ux, uy = dx / length, dy / length
        indexed = []
        for p in self.points:
            t = (p[0] - p0[0]) * ux + (p[1] - p0[1]) * uy
            indexed.append((t, p))
        indexed.sort(key=lambda item: item[0])
        return [item[1] for item in indexed]

    def get_total_length(self) -> float:
        """Returns total length of the chain."""
        return self.total_length


@dataclass(eq=False)
class LeaderCallout:
    """Represents an architectural annotation leader with arrowhead, elbow, landing, and text.

    Attributes:
        tip: (x, y) coordinate of the arrowhead tip (pointing to feature).
        elbow: (x, y) coordinate of the first bend.
        shoulder: (x, y) coordinate of the landing end (text attachment point).
        text: Multiline string annotation.
        identifier: Unique string ID.
        layer_id: Layer ID this callout belongs to.
        visible: Whether callout is visible.
        locked: Whether callout is locked.
        text_size: Font size in points.
        color: RGB tuple (0.0 to 1.0).
        box_border: Whether to draw a rectangular border around the text.
        arrow_type: "arrow", "dot", "slash", or "open_arrow".
        line_style: "solid" or "dashed".
    """
    tip: Tuple[float, float] = (0.0, 0.0)
    elbow: Tuple[float, float] = (0.0, 0.0)
    shoulder: Tuple[float, float] = (0.0, 0.0)
    text: str = "Note"
    identifier: str = ""
    layer_id: str = ""
    visible: bool = True
    locked: bool = False
    text_size: float = 12.0
    color: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    box_border: bool = False
    arrow_type: str = "arrow"
    line_style: str = "solid"

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("leader")


