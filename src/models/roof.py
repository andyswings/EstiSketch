"""
models/roof.py

Data models for the 3D roof geometry engine in EstiSketch.
Defines RoofPlane, RoofEdge, RoofVertex, RoofFacet, Plane3D, and Line3D.
Preserves existing application color-coding and integrates with the unified pipeline.
"""
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Dict, Optional, Any, Union

# Application color mapping for visual rendering of roof line types
ROOF_LINE_COLORS: Dict[str, str] = {
    "ridge": "#E53935",    # Crimson Red - Horizontal / sloped roof peak
    "hip": "#FB8C00",      # Amber Orange - External sloped corner
    "valley": "#00ACC1",   # Cyan Blue - Internal drainage channel
    "rake": "#8E24AA",     # Purple - Gable end sloped edge
    "eave": "#43A047",     # Emerald Green - Horizontal lower drip edge
    "tie_in": "#D81B60",   # Magenta / Pink - Abutting wall / plane transition
    "gable": "#FB8C00",    # Amber Orange
}

# String constants for direct import
EAVE = "eave"
RIDGE = "ridge"
HIP = "hip"
VALLEY = "valley"
RAKE = "rake"
TIE_IN = "tie_in"
GABLE = "gable"


class RoofEdgeType(str, Enum):
    EAVE = "eave"
    RIDGE = "ridge"
    HIP = "hip"
    VALLEY = "valley"
    RAKE = "rake"
    TIE_IN = "tie_in"
    GABLE = "gable"


@dataclass
class RoofVertex:
    """
    Represents an exact 3D vertex coordinate (x, y, z) in inches.
    Supports tuple indexing, unpacking, and metric distance helpers.
    """
    x: float
    y: float
    z: float = 0.0

    def __iter__(self):
        yield self.x
        yield self.y
        yield self.z

    def __getitem__(self, idx: int) -> float:
        if idx == 0:
            return self.x
        elif idx == 1:
            return self.y
        elif idx == 2:
            return self.z
        raise IndexError(f"RoofVertex index out of range: {idx}")

    def __len__(self) -> int:
        return 3

    def distance_to(self, other: Union['RoofVertex', Tuple[float, float, float], Tuple[float, float]]) -> float:
        ox = other[0]
        oy = other[1]
        oz = other[2] if len(other) > 2 else 0.0
        return math.hypot(self.x - ox, self.y - oy, self.z - oz)

    def distance_2d(self, other: Union['RoofVertex', Tuple[float, float]]) -> float:
        ox = other[0]
        oy = other[1]
        return math.hypot(self.x - ox, self.y - oy)

    def is_close(self, other: Union['RoofVertex', Tuple[float, float, float]], tol: float = 1e-4) -> bool:
        return self.distance_to(other) < tol

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def to_tuple_2d(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def __repr__(self) -> str:
        return f"RoofVertex(x={self.x:.3f}, y={self.y:.3f}, z={self.z:.3f})"


class RoofEdge:
    """
    Represents an edge in 3D roof geometry connecting two RoofVertex instances,
    or links a wall to a roof in wall-binding mode.
    Preserves existing application color-coding.
    """
    def __init__(
        self,
        arg1: Any = None,
        arg2: Any = None,
        edge_type: str = "eave",
        start_vertex: Optional[RoofVertex] = None,
        end_vertex: Optional[RoofVertex] = None,
        wall_identifier: Optional[str] = None,
        pitch_rise: Optional[float] = None,
        overhang: Optional[float] = None,
        plane_id: Optional[str] = None,
    ):
        # Handle dual constructor signatures:
        # Signature A (Phase 1): RoofEdge(start_vertex, end_vertex, edge_type)
        # Signature B (Legacy wall-binding): RoofEdge(wall_identifier, edge_type, pitch_rise, overhang)
        if isinstance(arg1, str) and (isinstance(arg2, str) or arg2 is None):
            self.wall_identifier: Optional[str] = arg1
            self.edge_type: str = str(arg2) if arg2 is not None else "eave"
            self.start_vertex: Optional[RoofVertex] = start_vertex
            self.end_vertex: Optional[RoofVertex] = end_vertex
        else:
            if arg1 is not None:
                self.start_vertex = arg1 if isinstance(arg1, RoofVertex) else RoofVertex(arg1[0], arg1[1], arg1[2] if len(arg1) > 2 else 0.0)
            else:
                self.start_vertex = start_vertex

            if arg2 is not None:
                self.end_vertex = arg2 if isinstance(arg2, RoofVertex) else RoofVertex(arg2[0], arg2[1], arg2[2] if len(arg2) > 2 else 0.0)
            else:
                self.end_vertex = end_vertex

            if isinstance(edge_type, RoofEdgeType):
                self.edge_type = edge_type.value
            else:
                self.edge_type = str(edge_type).lower() if edge_type is not None else "eave"
            self.wall_identifier = wall_identifier

        self.pitch_rise: Optional[float] = pitch_rise
        self.overhang: Optional[float] = overhang
        self.plane_id: Optional[str] = plane_id

    @property
    def length_in(self) -> float:
        """3D Euclidean length in inches."""
        if self.start_vertex and self.end_vertex:
            return self.start_vertex.distance_to(self.end_vertex)
        return 0.0

    @property
    def length_ft(self) -> float:
        """Length in feet."""
        return self.length_in / 12.0

    @property
    def length_2d_in(self) -> float:
        """2D projected length in inches."""
        if self.start_vertex and self.end_vertex:
            return self.start_vertex.distance_2d(self.end_vertex)
        return 0.0

    @property
    def color(self) -> str:
        """Hex color code preserving application styling."""
        return ROOF_LINE_COLORS.get(self.edge_type.lower(), "#E53935")

    def __repr__(self) -> str:
        if self.start_vertex and self.end_vertex:
            return f"RoofEdge({self.edge_type}, start={self.start_vertex}, end={self.end_vertex})"
        return f"RoofEdge(wall={self.wall_identifier}, type={self.edge_type})"


def normalize_pitch_values(pitch: Any, pitch_run: float = 12.0) -> Tuple[float, float]:
    """
    Normalizes pitch input to (pitch_rise, pitch_slope).
    Handles fraction strings ("12/12", "6/12"), rise values (6.0, 12.0, 8.0),
    and ratio values (1.0 for 12/12, 0.5 for 6/12).
    """
    if isinstance(pitch, str):
        if "/" in pitch:
            parts = pitch.split("/")
            rise = float(parts[0])
            run = float(parts[1]) if len(parts) > 1 and float(parts[1]) > 0 else 12.0
            return rise, rise / run
        p = float(pitch)
    else:
        p = float(pitch)

    # Standard roofing ratios vs rises:
    # 12/12 = 1.0 ratio, 6/12 = 0.5 ratio
    if abs(p - 1.0) < 1e-5:
        return 12.0, 1.0
    elif abs(p - 0.5) < 1e-5:
        return 6.0, 0.5
    elif abs(p - 0.25) < 1e-5:
        return 3.0, 0.25
    elif abs(p - 0.75) < 1e-5:
        return 9.0, 0.75
    elif 0.0 < p <= 2.0:
        return p * pitch_run, p
    else:
        return p, p / pitch_run


@dataclass
class Plane3D:
    """
    Represents an analytical 3D plane: A*x + B*y + C*z + D = 0.
    In the standard formulation:
      (A, B) is parallel to the inward normal of eave line, scaled by slope s_i
      C = -1.0
      D = Z_plate - (A * x0 + B * y0)
    """
    a: float
    b: float
    c: float = -1.0
    d: float = 0.0
    plane_id: str = ""
    pitch: float = 6.0
    overhang: float = 12.0
    eave_start: Optional[Tuple[float, float]] = None
    eave_end: Optional[Tuple[float, float]] = None
    inward_normal: Tuple[float, float] = (0.0, 1.0)

    @property
    def A(self) -> float: return self.a
    @property
    def B(self) -> float: return self.b
    @property
    def C(self) -> float: return self.c
    @property
    def D(self) -> float: return self.d

    def elevation_at(self, x: float, y: float) -> float:
        """Returns elevation z at (x, y)."""
        if abs(self.c) < 1e-9:
            return 0.0
        return -(self.a * x + self.b * y + self.d) / self.c

    def normal_vector(self) -> Tuple[float, float, float]:
        return (self.a, self.b, self.c)


@dataclass
class Line3D:
    """
    Represents an analytical 3D line: P(t) = point + t * direction.
    direction is a unit vector (dx, dy, dz).
    """
    point: RoofVertex
    direction: Tuple[float, float, float]
    line_type: str = "ridge"

    def point_at(self, t: float) -> RoofVertex:
        return RoofVertex(
            self.point.x + t * self.direction[0],
            self.point.y + t * self.direction[1],
            self.point.z + t * self.direction[2]
        )


@dataclass
class RoofFacet:
    """
    Represents a closed 3D polygon facet on a roof plane.
    Provides dict-like mapping for backward compatibility with existing takeoff code.
    """
    id: str
    plane_id: str
    plane: Optional['RoofPlane'] = None
    vertices: List[RoofVertex] = field(default_factory=list)
    edges: List[RoofEdge] = field(default_factory=list)
    area_3d_sqft: float = 0.0
    area_2d_sqft: float = 0.0
    polygon_2d: List[Tuple[float, float]] = field(default_factory=list)
    pitch: float = 6.0
    name: str = ""

    def __getitem__(self, key: str) -> Any:
        if key == "area_3d_sqft":
            return self.area_3d_sqft
        elif key == "area_2d_sqft":
            return self.area_2d_sqft
        elif key == "polygon_2d":
            return self.polygon_2d
        elif key == "pitch":
            return self.pitch
        elif key == "name":
            return self.name or f"Roof Slope #{self.plane_id} (Pitch {self.pitch:.1f}/12)"
        elif hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        return key in ("area_3d_sqft", "area_2d_sqft", "polygon_2d", "pitch", "name") or hasattr(self, key)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name or f"Roof Slope #{self.plane_id} (Pitch {self.pitch:.1f}/12)",
            "pitch": self.pitch,
            "polygon_2d": self.polygon_2d,
            "area_2d_sqft": self.area_2d_sqft,
            "area_3d_sqft": self.area_3d_sqft
        }


@dataclass
class RoofPlane:
    """
    Represents a roof plane definition in the unified geometry pipeline:
    RoofPlane(id, eave_start, eave_end, pitch, overhang, plane_type).
    """
    id: str
    eave_start: Tuple[float, float] | RoofVertex
    eave_end: Tuple[float, float] | RoofVertex
    pitch: float = 6.0
    overhang: float = 12.0
    plane_type: str = "eave"
    pitch_run: float = 12.0
    wall_identifier: Optional[str] = None
    name: str = ""
    vertices: List[RoofVertex] = field(default_factory=list)
    edges: List[RoofEdge] = field(default_factory=list)
    polygon_2d: List[Tuple[float, float]] = field(default_factory=list)
    area_3d_sqft: float = 0.0
    area_2d_sqft: float = 0.0
    plane_equation: Optional[Plane3D] = None

    @property
    def pitch_rise(self) -> float:
        rise, _ = normalize_pitch_values(self.pitch, self.pitch_run)
        return rise

    @property
    def pitch_slope(self) -> float:
        _, slope = normalize_pitch_values(self.pitch, self.pitch_run)
        return slope

    def __getitem__(self, key: str) -> Any:
        if key == "area_3d_sqft":
            return self.area_3d_sqft
        elif key == "area_2d_sqft":
            return self.area_2d_sqft
        elif key == "polygon_2d":
            return self.polygon_2d
        elif key == "pitch":
            return self.pitch_rise
        elif key == "name":
            return self.name or f"Roof Slope #{self.id} (Pitch {self.pitch_rise:.1f}/12)"
        elif hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        return key in ("area_3d_sqft", "area_2d_sqft", "polygon_2d", "pitch", "name") or hasattr(self, key)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name or f"Roof Slope #{self.id} (Pitch {self.pitch_rise:.1f}/12)",
            "pitch": self.pitch_rise,
            "polygon_2d": self.polygon_2d,
            "area_2d_sqft": self.area_2d_sqft,
            "area_3d_sqft": self.area_3d_sqft
        }
