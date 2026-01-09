
import sys
import unittest
from unittest.mock import MagicMock
import math

# Mock gi before importing modules that rely on it
mock_gi = MagicMock()
sys.modules['gi'] = mock_gi
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gtk'] = MagicMock()
sys.modules['gi.repository.Gdk'] = MagicMock()

# Add src to path
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from EstiSketch.Canvas.events_selection import CanvasSelectionMixin
from EstiSketch.components import Wall, Polyline, Dimension, Room

class MockConfig:
    PIXELS_PER_INCH = 2.0
    DEFAULT_WALL_WIDTH = 6.0
    JOINT_SNAP_TOLERANCE = 0.25

class MockCanvas(CanvasSelectionMixin):
    def __init__(self):
        self.config = MockConfig()
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.wall_sets = []
        self.rooms = []
        self.doors = []
        self.windows = []
        self.texts = []
        self.polylines = []
        self.polyline_sets = []
        self.dimensions = []
        self.circles = []
        self.arcs = []
        self.selected_items = []
        self._last_mouse_pos = (0, 0)
        
    def model_to_device(self, x, y, ppi):
        return (x * self.zoom * ppi + self.offset_x, 
                y * self.zoom * ppi + self.offset_y)

    def distance_point_to_segment(self, point, start, end):
        # Simplified distance implementation
        px, py = point
        x1, y1 = start
        x2, y2 = end
        
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
            
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0, min(1, t))
        
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy
        return math.hypot(px - closest_x, py - closest_y)
    
    def _point_in_polygon(self, point, polygon):
        # Ray casting algorithm
        x, y = point
        n = len(polygon)
        inside = False
        p1x, p1y = polygon[0]
        for i in range(n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside
        
    def is_object_on_locked_layer(self, obj):
        return False
        
    def is_object_on_visible_layer(self, obj):
        return True
        
    def emit(self, signal, data):
        # print(f"Emitted {signal}: {data}")
        pass
        
    def queue_draw(self):
        pass

    # Mock same_selection from the mixin if needed, or rely on imported one
    # CanvasSelectionMixin has same_selection, so we use it.
    
    def normalize_angle(self, angle):
        return angle % (2 * math.pi)

class TestTabCycle(unittest.TestCase):
    def test_cycle_polylines(self):
        canvas = MockCanvas()
        
        # Create a polyline and a wall at the same location
        # Start at (100, 100), end at (200, 200)
        p1 = Polyline(start=(100, 100), end=(200, 200), identifier="poly1")
        canvas.polyline_sets.append([p1])
        
        w1 = Wall(start=(100, 100), end=(200, 200), width=6, height=96, identifier="wall1")
        canvas.wall_sets.append([w1])
        
        # Set mouse position to MODEL coordinates (150, 150).
        # Device coords would be 300, 300.
        canvas._last_mouse_pos = (150, 150)
        
        # Initial selection: Wall
        canvas.selected_items = [{"type": "wall", "object": w1}]
        
        print("Cycling selection...")
        canvas.cycle_selection_at_mouse()
        
        # Expectation: Should cycle to Polyline
        # Current implementation likely fails to find Polyline
        
        found_polyline = False
        for item in canvas.selected_items:
            if item["type"] == "polyline":
                found_polyline = True
                break
        
        if not found_polyline:
            print("FAILURE: Did not cycle to polyline")
        else:
            print("SUCCESS: Cycled to polyline")
            
        self.assertTrue(found_polyline, "Should have cycled to polyline")

    def test_cycle_dimensions(self):
        canvas = MockCanvas()
        
        # Create a dimension and a wall at the same location
        d1 = Dimension(start=(10, 10), end=(20, 20), offset=10, identifier="dim1")
        
        # Offset is 10 inches.
        # Vector is (10, 10). Length ~14.14.
        # Perpendicular vector (-dy, dx) = (-10, 10). Unit: (-0.707, 0.707)
        # Offset point: start + 10 * unit. 
        # But for hit testing, we just need to click on the dimension line.
        
        canvas.dimensions.append(d1)
        
        # Set mouse position. where is the dimension line?
        # Offset logic in code:
        # dx = 10, dy = 10. length = 14.14
        # ux = 0.707, uy = 0.707
        # px = -0.707, py = 0.707
        # start_dim = (10 + 10*-0.707, 10 + 10*0.707) = (2.93, 17.07)
        # end_dim = (20 + 10*-0.707, 20 + 10*0.707) = (12.93, 27.07)
        
        # Let's pick midpoint of dimension line:
        # mid_x = (2.93 + 12.93)/2 = 7.93
        # mid_y = (17.07 + 27.07)/2 = 22.07
        
        # Set mouse position to MODEL coordinates
        canvas._last_mouse_pos = (7.93, 22.07)
        
        # Select nothing initially
        canvas.selected_items = []
        
        canvas.cycle_selection_at_mouse()
        
        found_dim = False
        for item in canvas.selected_items:
            if item["type"] == "dimension":
                found_dim = True
        
        # This will fail if not implemented
        self.assertTrue(found_dim, "Should have selected dimension")

if __name__ == '__main__':
    unittest.main()
