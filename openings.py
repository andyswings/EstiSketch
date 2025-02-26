from dataclasses import dataclass
from typing import Tuple, Optional

@dataclass
class Door:
    def __init__(self, location: Tuple[float, float], width: int, height: int):
        # Basic geometry
        self.location = location  # (x, y) coordinates
        self.width = width       # inches
        self.height = height     # inches
        self.thickness = 1.75    # inches
        self.wall_reference = None  # reference to parent wall
        
        # Material and finish
        self.material = "wood"   # wood, metal, fiberglass
        self.finish = "paint"    # paint, stain, veneer
        self.color = "#FFFFFF"   # hex color
        self.brand = ""
        self.model = ""
        
        # Hardware
        self.handle_type = "lever"    # lever, knob, panic
        self.hinge_type = "standard"  # standard, spring, pivot
        self.closer_type = None       # surface, concealed
        self.lock_type = "standard"   # standard, deadbolt, electronic
        
        # Properties
        self.fire_rating = None    # 20min, 45min, 90min
        self.sound_rating = None   # STC rating
        self.swing_direction = "left"  # left, right
        self.swing_angle = 90     # degrees
        self.is_open = False
        
        # Cost
        self.cost = 0.0
        self.installation_cost = 0.0

@dataclass
class Window:
    def __init__(self, location: Tuple[float, float], width: int, height: int):
        # Basic geometry
        self.location = location  # (x, y) coordinates
        self.width = width       # inches
        self.height = height     # inches
        self.wall_reference = None  # reference to parent wall
        
        # Material and finish
        self.frame_material = "vinyl"  # vinyl, aluminum, wood
        self.frame_color = "#FFFFFF"   # hex color
        self.brand = ""
        self.model = ""
        
        # Glass properties
        self.glass_type = "double"     # single, double, triple
        self.glazing = "clear"         # clear, low-e, tinted
        self.gas_fill = "argon"        # air, argon, krypton
        
        # Operation
        self.operation_type = "single-hung"  # single-hung, casement, sliding
        self.screen_type = "standard"        # none, standard, security
        self.is_open = False
        
        # Performance
        self.u_value = 0.30            # thermal performance
        self.shgc = 0.40              # solar heat gain coefficient
        self.vt = 0.55                # visible transmittance
        self.energy_star = True
        
        # Cost
        self.cost = 0.0
        self.installation_cost = 0.0