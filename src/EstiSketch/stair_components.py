"""
Stair components for EstiSketch.

This module contains the dataclass for stair objects.
"""
from dataclasses import dataclass, field
from typing import Tuple, Optional


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
    
    # Spiral Specifics (for future use)
    inner_radius: float = 6.0
    rotation_degrees: float = 270.0

