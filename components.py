from dataclasses import dataclass
from typing import List, Tuple
import math
from gi.repository import Pango

@dataclass
class Wall:
    def __init__(self, start, end, width, height):
        # Basic geometry
        self.start = start  # tuple of (x, y)
        self.end = end    # tuple of (x, y)
        self.width = width  # integer (inches)
        self.height = height  # integer (inches)
        
        # Material properties
        self.material = "wood"  # wood, metal, concrete
        self.interior_finish = "drywall"  # drywall, plaster, wood
        self.exterior_finish = "stucco"  # stucco, brick, hardie, LP_lap
        self.color = "#FFFFFF"  # hex color
        self.cost_per_sqft = 0.0
        
        # Construction details
        self.stud_spacing = 16  # inches
        self.insulation_type = "fiberglass"
        self.fire_rating = "1hr"
        self.sound_rating = "STC 35"
        
    def length(self) -> float:
        """Calculate wall length in inches"""
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return (dx * dx + dy * dy) ** 0.5
        
    def area(self) -> float:
        """Calculate wall area in square feet"""
        return (self.length() * self.height) / 144  # Convert to sq ft
        
    def volume(self) -> float:
        """Calculate wall volume in cubic feet"""
        return (self.length() * self.height * self.width) / 1728  # Convert to cu ft
        
    def total_cost(self) -> float:
        """Calculate total wall cost"""
        return self.area() * self.cost_per_sqft

@dataclass
class Room:
    def __init__(self, points: List[Tuple[float, float]], height: float = 96.0):
        self.points = points  # List of (x, y) tuples defining the room vertices
        self.height = height  # Room height in inches
        self.floor_type = "default"
        self.wall_finish = "default"
        self.room_type = "undefined"
        self.name = ""
        
    def area(self) -> float:
        """Calculate room area using shoelace formula"""
        n = len(self.points)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += self.points[i][0] * self.points[j][1]
            area -= self.points[j][0] * self.points[i][1]
        return abs(area) / 2.0
    
    def perimeter(self) -> float:
        """Calculate room perimeter"""
        n = len(self.points)
        perim = 0.0
        for i in range(n):
            j = (i + 1) % n
            dx = self.points[j][0] - self.points[i][0]
            dy = self.points[j][1] - self.points[i][1]
            perim += (dx * dx + dy * dy) ** 0.5
        return perim


@dataclass
class DimensionLine:
    def __init__(self, start: Tuple[float, float], end: Tuple[float, float], text: str):
        self.start = start  # (x, y) coordinates
        self.end = end      # (x, y) coordinates
        self.text = text
        self.color = "#000000"  # black
        self.font = "Sans 10"
        self.arrow = True
        self.extension = 0.0
        self.text_offset = 0.0
        self.text_angle = 0.0
        self.text_align = "center"
        self.text_justify = "center"
        self.text_color = "#000000"
        self.text_background = None
        self.text_border = None
        self.text_padding = 2
        self.text_wrap = False
    
    def length(self) -> float:
        """Calculate dimension line length"""
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return (dx * dx + dy * dy) ** 0.5
    
    def angle(self) -> float:
        """Calculate dimension line angle"""
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return math.degrees(math.atan2(dy, dx))
    
    def midpoint(self) -> Tuple[float, float]:
        """Calculate midpoint of dimension line"""
        return ((self.start[0] + self.end[0]) / 2, (self.start[1] + self.end[1]) / 2)
    
    def text_position(self) -> Tuple[float, float]: # (x, y)
        """Calculate text position"""
        angle = self.angle()
        dx = math.cos(math.radians(angle))
        dy = math.sin(math.radians(angle))
        x = self.midpoint()[0] + dx * self.text_offset
        y = self.midpoint()[1] + dy * self.text_offset
        return x, y
    
    def text_bounds(self) -> Tuple[float, float, float, float]: # (x1, y1, x2, y2)
        """Calculate text bounding box"""
        x, y = self.text_position()
        width, height = self.text_size()
        x1 = x - width / 2
        y1 = y - height / 2
        x2 = x + width / 2
        y2 = y + height / 2
        return x1, y1, x2, y2
    
    def text_size(self) -> Tuple[float, float]: # (width, height)
        """Calculate text size"""
        layout = Pango.Layout.new_empty()
        layout.set_text(self.text)
        layout.set_font_description(Pango.FontDescription.from_string(self.font))
        width, height = layout.get_pixel_size()
        return width, height
    
    def draw(self, cr):
        """Draw dimension line"""
        cr.set_line_width(self.width)
        cr.set_source_rgb(*hex_to_rgb(self.color))
        cr.move_to(*self.start)
        cr.line_to(*self.end)
        cr.stroke()
        self.draw_arrowhead(cr)
        self.draw_text(cr)
        
    def draw_arrowhead(self, cr):
        """Draw arrowhead"""
        if self.arrow:
            cr.move_to(*self.end)
            cr.rel_line_to(-self.arrow_size, -self.arrow_size)
            cr.move_to(*self.end)
            cr.rel_line_to(-self.arrow_size, self.arrow_size)
            cr.stroke()
            
    def draw_text(self, cr):
        """Draw dimension text"""
        cr.set_source_rgb(*hex_to_rgb(self.text_color))
        cr.select_font_face(*self.font.split())
        cr.set_font_size(int(self.font.split()[-1]))
        cr.move_to(*self.text_position())
        cr.show_text(self.text)
        cr.stroke()
        if self.text_background:
            self.draw_text_background(cr)
    
    def draw_text_background(self, cr):
        """Draw text background"""
        cr.set_source_rgb(*hex_to_rgb(self.text_background))
        x1, y1, x2, y2 = self.text_bounds()
        cr.rectangle(x1, y1, x2 - x1, y2 - y1)
        cr.fill()
        if self.text_border:
            self.draw_text_border(cr)
        
    def draw_text_border(self, cr):
        """Draw text border"""
        cr.set_source_rgb(*hex_to_rgb(self.text_border))
        x1, y1, x2, y2 = self.text_bounds()
        cr.rectangle(x1, y1, x2 - x1, y2 - y1)
        cr.stroke()
    
    def draw_text_wrap(self, cr):
        """Draw wrapped text"""
        if self.text_wrap:
            layout = Pango.Layout.new_empty()
            layout.set_text(self.text)
            layout.set_font_description(Pango.FontDescription.from_string(self.font))
            width, height = layout.get_pixel_size()
            cr.set_source_rgb(*hex_to_rgb(self.text_color))
            cr.move_to(*self.text_position())
            cr.show_layout(layout)
            cr.stroke()
    
    def draw_text_rotate(self, cr):
        """Draw rotated text"""
        cr.save()
        cr.translate(*self.text_position())
        cr.rotate(math.radians(self.text_angle))
        cr.translate(-self.text_position()[0], -self.text_position()[1])
        cr.set_source_rgb(*hex_to_rgb(self.text_color))
        cr.select_font_face(*self.font.split())
        cr.set_font_size(int(self.font.split()[-1]))
        cr.move_to(*self.text_position())
        cr.show_text(self.text)
        cr.stroke()
        cr.restore()
    
    @property
    def arrow_size(self):
        return 10
    
    @property
    def width(self):
        return 1
    

@dataclass
class Text:
    def __init__(self, location: Tuple[float, float], text: str):
        self.location = location
        self.text = text
        self.font = "Sans 10"
        self.color = "#000000"
        self.angle = 0.0
        self.align = "center"
        self.justify = "center"
        self.background = None
        self.border = None
        self.padding = 2
        self.wrap = False
        
    def draw(self, cr):
        """Draw text"""
        cr.set_source_rgb(*hex_to_rgb(self.color))
        cr.select_font_face(*self.font.split())
        cr.set_font_size(int(self.font.split()[-1]))
        cr.move_to(*self.location)
        cr.show_text(self.text)
        cr.stroke()
        if self.background:
            self.draw_background(cr)
        if self.wrap:
            self.draw_wrap(cr)
        if self.angle:
            self.draw_rotate(cr)

    def draw_background(self, cr):
        """Draw text background"""
        cr.set_source_rgb(*hex_to_rgb(self.background))
        x, y = self.location
        width, height = self.size(cr)
        x1 = x - width / 2
        y1 = y - height / 2
        cr.rectangle(x1, y1, width, height)
        cr.fill()
        if self.border:
            self.draw_border(cr)
        if self.padding:
            self.draw_padding(cr)
    
    def draw_border(self, cr):
        """Draw text border"""
        cr.set_source_rgb(*hex_to_rgb(self.border))
        x, y = self.location
        width, height = self.size(cr)
        x1 = x - width / 2
        y1 = y - height / 2
        cr.rectangle(x1, y1, width, height)
        cr.stroke()
        
    def draw_padding(self, cr):
        """Draw text padding"""
        cr.set_source_rgb(*hex_to_rgb(self.background))
        x, y = self.location
        width, height = self.size(cr)
        x1 = x - width / 2 + self.padding
        y1 = y - height / 2 + self.padding
        cr.rectangle(x1, y1, width - 2 * self.padding, height - 2 * self.padding)
        cr.fill()
        
    def draw_wrap(self, cr):
        """Draw wrapped text"""
        layout = Pango.Layout.new_empty()
        layout.set_text(self.text)
        layout.set_font_description(Pango.FontDescription.from_string(self.font))
        width, height = layout.get_pixel_size()
        cr.set_source_rgb(*hex_to_rgb(self.color))
        cr.move_to(*self.location)
        cr.show_layout(layout)
        cr.stroke()
    
    
    
def hex_to_rgb(hex_color):
    """Convert hex color to RGB"""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4))

def rgb_to_hex(rgb_color):
    """Convert RGB color to hex"""
    return "#{:02x}{:02x}{:02x}".format(*tuple(int(x * 255) for x in rgb_color))