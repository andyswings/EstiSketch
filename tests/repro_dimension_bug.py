import unittest
from unittest.mock import MagicMock
from EstiSketch.Canvas.canvas_area import CanvasArea
from EstiSketch.components import Dimension

class TestDimensionResetBug(unittest.TestCase):
    def setUp(self):
        # Mock config
        self.config = MagicMock()
        self.config.PIXELS_PER_INCH = 10.0
        self.config.SNAP_ENABLED = False
        
        # Initialize Canvas
        self.canvas = CanvasArea(self.config)
        
        # Add a dimension
        self.dim = Dimension(start=(0, 0), end=(100, 0), offset=10)
        self.canvas.dimensions.append(self.dim)
        
        # Select it
        self.canvas.selected_items = [{"type": "dimension", "object": self.dim}]

    def test_edit_then_move(self):
        # 1. Edit the dimension endpoint (simulate dragging handle)
        print(f"Initial State: {self.dim.start} to {self.dim.end}")
        
        # Simulate selecting handle
        self.canvas.editing_dimension = self.dim
        self.canvas.editing_dimension_handle = "end"
        
        # Move end point from (100, 0) to (100, 100)
        # In real app, on_drag_update modifies the object directly
        new_end = (100, 100)
        self.dim.end = new_end
        
        # End edit (simulate on_drag_end)
        self.canvas.editing_dimension = None
        self.canvas.editing_dimension_handle = None
        
        print(f"Post-Edit State: {self.dim.start} to {self.dim.end}")
        self.assertEqual(self.dim.end, (100, 100))
        
        # 2. Deselect everything
        self.canvas.selected_items = []
        
        # 3. Select via click (simulate clicking the dimension to move it)
        # We need to simulate a click that would hit the dimension.
        # Dimension is at (0,0) -> (100,100). Offset 10.
        # Perpendicular vector to (100, 100) is (-0.707, 0.707) roughly.
        # Midpoint is (50, 50).
        # We need to calculate where the dimension line is.
        import math
        dx = 100
        dy = 100
        length = math.hypot(dx, dy)
        ux = dx/length
        uy = dy/length
        px = -uy
        py = ux
        # Offset point
        mid_x = 50 + 10 * px
        mid_y = 50 + 10 * py
        
        # Click near there.
        # Since we mock pixels per inch = 10.
        # Widget coords = model * 10.
        click_x = mid_x * 10
        click_y = mid_y * 10
        
        # Manually invoke selection logic or mimic it
        # EventsSelectionMixin._handle_pointer_click is complex to mock fully.
        # But we can verify if the element in self.dimensions IS the modified one.
        
        print("Verifying object in canvas.dimensions list...")
        stored_dim = self.canvas.dimensions[0]
        self.assertEqual(stored_dim.end, (100, 100), "Stored dimension should retain edits")
        
        # Re-select manually for drag simulation as before
        self.canvas.selected_items = [{"type": "dimension", "object": stored_dim}]
        
        # 4. Now Move the dimension (simulate drag)
        # Simulate on_drag_begin
        # This logic mimics events_selection.py on_drag_begin for dimensions
        selected_dims = [i for i in self.canvas.selected_items if i["type"] == "dimension"]
        self.canvas.dragging_dimensions = []
        for dim_item in selected_dims:
            dim = dim_item["object"]
            self.canvas.dragging_dimensions.append({
                "dimension": dim,
                "original_start": dim.start,
                "original_end": dim.end
            })
            
        self.canvas.drag_start_x = 0
        self.canvas.drag_start_y = 0
        self.canvas.dimension_drag_start_model = (0, 0) # Simplification
        
        # Verify captured state
        captured_end = self.canvas.dragging_dimensions[0]["original_end"]
        print(f"Captured during drag_begin: {captured_end}")
        self.assertEqual(captured_end, (100, 100), "Should capture the EDITED position")
        
        # Simulate on_drag_update
        # Move by (10, 10)
        dx, dy = 10, 10
        
        # Logic from events_edit.py on_drag_update
        for dim_info in self.canvas.dragging_dimensions:
            dim = dim_info["dimension"]
            orig_start = dim_info["original_start"]
            orig_end = dim_info["original_end"]

            dim.start = (orig_start[0] + dx, orig_start[1] + dy)
            dim.end = (orig_end[0] + dx, orig_end[1] + dy)
            
        print(f"Final State: {self.dim.start} to {self.dim.end}")
        
        self.assertEqual(self.dim.end, (110, 110))

if __name__ == "__main__":
    unittest.main()
