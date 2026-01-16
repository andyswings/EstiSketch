"""
Roof components for EstiSketch.

This module contains dataclasses for roof-related objects, kept separate
from the main components.py to isolate complexity and support future
expansion to complex roof types.
"""
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class RoofEdge:
    """Links a wall to a roof with edge-type info."""
    wall_identifier: str  # Reference to the wall's identifier
    edge_type: str  # "eave" or "gable"


@dataclass
class Roof:
    """
    Represents a roof bound to a set of walls.
    
    The roof geometry (ridge_lines, hip_lines, valley_lines) is calculated
    automatically based on the edge types and pitch settings.
    """
    identifier: str = ""
    layer_id: str = ""
    
    # Wall bindings - list of RoofEdge linking walls to this roof
    edges: List[RoofEdge] = field(default_factory=list)
    
    # Roof properties
    roof_type: str = "gable"  # "gable", "hip", "shed", "flat"
    pitch_rise: int = 6  # Rise (e.g., 6 in 6/12)
    pitch_run: int = 12  # Run (always 12 for standard notation)
    overhang: float = 12.0  # Eave overhang in inches
    
    # Calculated geometry (auto-generated, stored for rendering)
    # Each line is ((x1, y1), (x2, y2))
    ridge_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = field(default_factory=list)
    hip_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = field(default_factory=list)
    valley_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = field(default_factory=list)
    
    # Roof outline with overhang (for rendering the roof boundary)
    outline_points: List[Tuple[float, float]] = field(default_factory=list)
    
    # Materials
    material: str = "asphalt_shingle"
