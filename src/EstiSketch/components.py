import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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


WALL_FINISH_OPTIONS = [
    "Drywall",
    "Painted Drywall",
    "Plaster",
    "Tile",
    "T&G Wood",
    "Wainscoting",
    "Vinyl Siding",
    "Hardie Lap Siding",
    "Stucco",
    "Brick",
    "Stone Veneer",
    "Exposed Concrete",
    "None",
]

EXTERIOR_WALL_FINISHES = {
    "Vinyl Siding",
    "Hardie Lap Siding",
    "Stucco",
    "Brick",
    "Stone Veneer",
}


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
            height_at_end=None,
            custom_name: str = "",
            comment: str = ""):
        self.identifier = (
            identifier if identifier else generate_identifier("wall")
        )  # unique string identifier
        self.layer_id = layer_id  # layer this wall belongs to
        self.visible = visible
        self.locked = locked
        self.custom_name = custom_name
        self.comment = comment
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
        self.left_finish = "Drywall"
        self.right_finish = "Drywall"
        self.left_color = None
        self.right_color = None
        self.left_baseboard = False
        self.right_baseboard = False

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
            locked=False,
            custom_name: str = "",
            comment: str = ""):
        self.identifier = (
            identifier if identifier else generate_identifier("polyline")
        )  # unique string identifier
        self.layer_id = layer_id  # layer this polyline belongs to
        self.visible = visible
        self.locked = locked
        self.custom_name = custom_name
        self.comment = comment
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


FLOOR_OPENING_TYPES = [
    ("opening", "Floor Opening"),
    ("atrium", "Atrium"),
    ("lightwell", "Lightwell"),
    ("courtyard", "Courtyard"),
    ("elevator", "Elevator Shaft"),
    ("shaft", "Mechanical / Utility Shaft"),
    ("double_height", "Double-Height / Open to Below"),
]

FLOOR_OPENING_DEFAULT_LABELS = {
    "opening": "OPEN TO BELOW",
    "atrium": "ATRIUM",
    "lightwell": "LIGHTWELL",
    "courtyard": "COURTYARD",
    "elevator": "ELEVATOR",
    "shaft": "SHAFT",
    "double_height": "OPEN TO BELOW",
}


@dataclass(eq=False)
class FloorOpening:
    """Manual polygon floor/ceiling opening (atrium, shaft, elevator, stairwell, etc.)."""

    def __init__(
        self,
        points: List[Tuple[float, float]],
        opening_type: str = "opening",
        label: str = "",
        ceiling_only: bool = False,
        show_cross: bool = True,
        show_label: bool = True,
        identifier: str = "",
        layer_id: str = "",
        visible: bool = True,
        locked: bool = False,
        custom_name: str = "",
        comment: str = "",
    ):
        self.identifier = identifier if identifier else generate_identifier("opening")
        self.layer_id = layer_id
        self.visible = visible
        self.locked = locked
        self.custom_name = custom_name
        self.comment = comment
        self.points = [tuple(pt) for pt in points]
        self.opening_type = opening_type
        self.label = label
        self.ceiling_only = ceiling_only
        self.show_cross = show_cross
        self.show_label = show_label

    @property
    def display_label(self) -> str:
        """Return explicit custom label or default architectural label for ``opening_type``."""
        text = (self.label or "").strip()
        if text:
            return text
        if self.ceiling_only and self.opening_type == "opening":
            return "CEILING OPENING"
        return FLOOR_OPENING_DEFAULT_LABELS.get(self.opening_type, "OPEN TO BELOW")


@dataclass(eq=False)
class Fixture:
    """Parametric architectural cabinet, vanity, plumbing fixture, appliance, or HVAC unit."""

    def __init__(
        self,
        symbol_type: str = "base_cabinet",
        x: float = 0.0,
        y: float = 0.0,
        width: Optional[float] = None,
        depth: Optional[float] = None,
        height: Optional[float] = None,
        rotation: float = 0.0,
        elevation: Optional[float] = None,
        mount_surface: Optional[str] = None,
        base_elevation: float = 0.0,
        has_countertop: Optional[bool] = None,
        countertop_overhang: Optional[float] = None,
        countertop_thickness: float = 1.5,
        countertop_material: str = "quartz",
        has_backsplash: bool = True,
        door_swing: str = "left",
        fill_color: Optional[Tuple[float, float, float]] = None,
        countertop_color: Optional[Tuple[float, float, float]] = None,
        category: str = "",
        identifier: str = "",
        layer_id: str = "",
        visible: bool = True,
        locked: bool = False,
        custom_name: str = "",
        comment: str = "",
    ):
        from .fixtures_catalog import get_fixture_spec

        spec = get_fixture_spec(symbol_type)
        self.identifier = identifier if identifier else generate_identifier("fixture")
        self.layer_id = layer_id
        self.visible = visible
        self.locked = locked
        self.custom_name = custom_name
        self.comment = comment

        self.symbol_type = symbol_type
        self.category = category if category else spec["category"]
        self.x = float(x)
        self.y = float(y)
        self.width = float(width if width is not None else spec["width"])
        self.depth = float(depth if depth is not None else spec["depth"])
        self.height = float(height if height is not None else spec["height"])
        self.rotation = float(rotation) % 360.0
        self.elevation = float(elevation if elevation is not None else spec["elevation"])
        self.mount_surface = mount_surface if mount_surface else spec["mount_surface"]
        self.base_elevation = float(base_elevation)

        ct_default = bool(spec["has_countertop"])
        self.has_countertop = ct_default if has_countertop is None else has_countertop
        oh_default = float(spec["countertop_overhang"]) if self.has_countertop else 0.0
        self.countertop_overhang = float(
            countertop_overhang if countertop_overhang is not None else oh_default
        )
        self.countertop_thickness = float(countertop_thickness)
        self.countertop_material = countertop_material or "quartz"
        self.has_backsplash = has_backsplash
        self.door_swing = door_swing or "left"
        self.fill_color = fill_color
        self.countertop_color = countertop_color

    @property
    def is_upper(self) -> bool:
        """Return True if this fixture is wall-hung above counter height (drawn dashed)."""
        from .fixtures_catalog import get_fixture_spec

        if bool(get_fixture_spec(self.symbol_type).get("is_upper", False)):
            return True
        return self.elevation >= 42.0 and self.mount_surface == "wall"

    @property
    def total_top_elevation(self) -> float:
        """Return top elevation in inches above datum (floor/slab + elevation + height + countertop)."""
        ct = self.countertop_thickness if self.has_countertop else 0.0
        return self.base_elevation + self.elevation + self.height + ct

    def world_corners(self, include_overhang: bool = False) -> List[Tuple[float, float]]:
        """Return 4 world-coordinate bounding corners in inches."""
        import math

        hw = self.width / 2.0
        hd = self.depth / 2.0
        extra = (
            float(self.countertop_overhang)
            if (include_overhang and self.has_countertop and self.countertop_overhang > 0)
            else 0.0
        )
        local_pts = [(-hw, -hd), (hw, -hd), (hw, hd + extra), (-hw, hd + extra)]
        rad = math.radians(self.rotation)
        ca, sa = math.cos(rad), math.sin(rad)
        return [
            (self.x + lx * ca - ly * sa, self.y + lx * sa + ly * ca)
            for lx, ly in local_pts
        ]

    def point_inside(self, px: float, py: float, tolerance: float = 0.0) -> bool:
        """Return True if model point ``(px, py)`` falls inside this fixture's 2D footprint."""
        import math

        dx = px - self.x
        dy = py - self.y
        rad = math.radians(-self.rotation)
        ca, sa = math.cos(rad), math.sin(rad)
        lx = dx * ca - dy * sa
        ly = dx * sa + dy * ca

        hw = self.width / 2.0 + tolerance
        hd = self.depth / 2.0 + tolerance
        extra = float(self.countertop_overhang) if (self.has_countertop and self.countertop_overhang > 0) else 0.0
        if not (-hw <= lx <= hw and -hd <= ly <= hd + extra):
            return False
        if self.symbol_type in ("corner_base_cabinet", "corner_upper_cabinet"):
            arm = (12.0 if self.symbol_type == "corner_upper_cabinet" else 24.0) + tolerance
            return (lx <= -self.width / 2.0 + arm) or (ly <= -self.depth / 2.0 + arm)
        return True


@dataclass
class Room:
    def __init__(self,
                 points: List[Tuple[float,
                                    float]],
                 height: float = 96.0,
                 identifier="",
                 layer_id: str = "",
                 visible=True,
                 locked=False,
                 custom_name: str = "",
                 comment: str = ""):
        self.identifier = (
            identifier if identifier else generate_identifier("room")
        )  # unique string identifier
        self.layer_id = layer_id  # layer this room belongs to
        self.visible = visible
        self.locked = locked
        self.custom_name = custom_name
        self.comment = comment
        # List of (x, y) tuples defining the room vertices
        self.points = points
        self.height = height  # Room height in inches
        self.floor_type = "default"
        self.floor_pattern = "none"
        self.pattern_rotation = 0.0
        self.pattern_scale = 1.0
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
            locked=False,
            custom_name: str = "",
            comment: str = ""):
        self.identifier = (
            identifier if identifier else generate_identifier("door")
        )  # unique string identifier
        self.layer_id = layer_id  # layer this door belongs to
        self.visible = visible
        self.locked = locked
        self.custom_name = custom_name
        self.comment = comment
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
            locked=False,
            custom_name: str = "",
            comment: str = ""):
        self.identifier = (
            identifier if identifier else generate_identifier("window")
        )  # unique string identifier
        self.layer_id = layer_id  # layer this window belongs to
        self.visible = visible
        self.locked = locked
        self.custom_name = custom_name
        self.comment = comment
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
    custom_name: str = ""
    comment: str = ""

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
    custom_name: str = ""
    comment: str = ""

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
    custom_name: str = ""
    comment: str = ""

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
    custom_name: str = ""
    comment: str = ""

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
    custom_name: str = ""
    comment: str = ""

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
    custom_name: str = ""
    comment: str = ""

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
    custom_name: str = ""
    comment: str = ""

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("leader")


@dataclass(eq=False)
class ObjectGroup:
    """Represents a logical group of drawing objects manipulated as a unit."""
    identifier: str = ""
    name: str = ""
    custom_name: str = ""
    comment: str = ""
    member_ids: List[str] = field(default_factory=list)
    layer_id: str = ""
    visible: bool = True
    locked: bool = False

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("group")


@dataclass(eq=False)
class CustomAsset:
    """Custom imported or Blender-sculpted 3D asset (`.glb`) with projected 2D silhouette.

    All coordinates and silhouette vertices are stored in **inches** (2D Y-down model
    space); Z is height in **inches** above level floor elevation, and ``rotation`` is in
    **degrees**.
    """

    name: str = "Custom 3D Asset"
    glb_rel_path: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    rotation: float = 0.0
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    silhouette_2d: List[Tuple[float, float]] = field(default_factory=list)
    glb_bytes: Optional[bytes] = None
    level_id: str = ""
    identifier: str = ""
    layer_id: str = ""
    visible: bool = True
    locked: bool = False
    custom_name: str = ""
    comment: str = ""

    def __post_init__(self) -> None:
        if not self.identifier:
            self.identifier = generate_identifier("custom_asset")

    def world_silhouette(self) -> List[Tuple[float, float]]:
        """Return 2D footprint polygon transformed into world **inches**."""
        import math

        pts = self.silhouette_2d if len(self.silhouette_2d) >= 3 else [
            (-18.0, -18.0),
            (18.0, -18.0),
            (18.0, 18.0),
            (-18.0, 18.0),
        ]
        sx, sy = float(self.scale[0]), float(self.scale[1])
        rad = math.radians(float(self.rotation))
        ca, sa = math.cos(rad), math.sin(rad)
        out: List[Tuple[float, float]] = []
        for lx, ly in pts:
            px = float(lx) * sx
            py = float(ly) * sy
            out.append((self.x + px * ca - py * sa, self.y + px * sa + py * ca))
        return out


