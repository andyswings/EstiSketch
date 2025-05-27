from dataclasses import dataclass
from typing import List, Tuple
import math
from gi.repository import Pango

@dataclass(eq=False)
class Wall:
    def __init__(self, start, end, width, height, exterior_wall=False):
        self.start = start  # tuple of (x, y)
        self.end = end      # tuple of (x, y)
        self.width = width  # integer (inches)
        self.height = height  # integer (inches)
        self.exterior_wall = exterior_wall  # boolean
        
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
        self.fire_rating = "1hr"

    def __eq__(self, other):
        if not isinstance(other, Wall):
            return False
        return (self.start == other.start and
                self.end == other.end and
                self.width == other.width and
                self.height == other.height)


@dataclass
class Polyline:
    def __init__(self, start, end):
        self.start = start  # tuple of (x, y)
        self.end = end      # tuple of (x, y) 
        self.style = "solid"  # or "dashed"  
                 

@dataclass
class Room:
    def __init__(self, points: List[Tuple[float, float]], height: float = 96.0):
        self.points = points  # List of (x, y) tuples defining the room vertices
        self.height = height  # Room height in inches
        self.floor_type = "default"
        self.wall_finish = "default"
        self.room_type = "undefined"
        self.name = ""


@dataclass
class Door:
    def __init__(self, door_type: str, width: float, height: float, swing: str, orientation: str):
        self.door_type = door_type  # Type of door (e.g., "single", "double", "sliding", "pocket", "bi-fold", "double_bi-fold", "door_frame", "garage")
        self.width = width  # Door width in inches
        self.height = height    # Door height in inches
        self.swing = swing  # Door swing direction (e.g., "left", "right")
        self.orientation = orientation  # Orientation of the door (e.g., "inswing", "outswing")


@dataclass
class Window:
    def __init__(self, width: float, height: float, window_type: str):
        self.width = width  # Window width in inches
        self.height = height  # Window height in inches
        self.window_type = window_type # Type of window (e.g.,"double-hung", "sliding", "fixed")