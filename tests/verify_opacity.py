
import sys
import os

# Adjust path to find modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from EstiSketch.components import Layer, Wall
from EstiSketch.Canvas.canvas_area import CanvasArea

# Mock Config
class MockConfig:
    def __init__(self):
        self.DEFAULT_ZOOM_LEVEL = 1.0
        self.PIXELS_PER_INCH = 2.0
        self.SNAP_ENABLED = False
        self.SNAP_THRESHOLD = 10
        self.LAYER_FOCUS_MODE = False
        self.DEFAULT_LEVEL_HEIGHT = 96.0

def test_opacity():
    print("Testing Layer Opacity Logic...")
    config = MockConfig()
    canvas = CanvasArea(config)

    # Setup Layers
    # Canvas default creates layer-0 on level-1
    l1_id = canvas.layers[0].id
    canvas.layers[0].name = "Layer Bottom"
    
    l2_id = canvas.add_layer("Layer Top")
    
    # Verify setup
    print(f"Layers: {[l.name for l in canvas.layers]}")
    
    # Create objects
    w1 = Wall((0,0), (10,0), 6, 96, False, "w1")
    w1.layer_id = l1_id
    
    w2 = Wall((0,10), (10,10), 6, 96, False, "w2")
    w2.layer_id = l2_id
    
    # Test 1: Focus Mode OFF (Default)
    print("\nTest 1: Focus Mode OFF")
    op1 = canvas.get_object_opacity(w1)
    op2 = canvas.get_object_opacity(w2)
    print(f"Obj1 (Bottom) Opacity: {op1} (Expected 1.0)")
    print(f"Obj2 (Top) Opacity: {op2} (Expected 1.0)")
    assert op1 == 1.0
    assert op2 == 1.0
    
    # Test 2: Focus Mode ON, Bottom Active
    print("\nTest 2: Focus Mode ON, Bottom Active")
    config.LAYER_FOCUS_MODE = True
    canvas.active_layer_id = l1_id # Bottom is active
    
    op1 = canvas.get_object_opacity(w1) # on active
    op2 = canvas.get_object_opacity(w2) # on top (above)
    
    print(f"Obj1 (Active) Opacity: {op1} (Expected 1.0)")
    print(f"Obj2 (Above) Opacity: {op2} (Expected 1.0)")
    assert op1 == 1.0
    assert op2 == 1.0

    # Test 3: Focus Mode ON, Top Active
    print("\nTest 3: Focus Mode ON, Top Active")
    canvas.active_layer_id = l2_id # Top is active
    
    op1 = canvas.get_object_opacity(w1) # on bottom (below)
    op2 = canvas.get_object_opacity(w2) # on active
    
    print(f"Obj1 (Below) Opacity: {op1} (Expected 0.25)")
    print(f"Obj2 (Active) Opacity: {op2} (Expected 1.0)")
    assert op1 == 0.25
    assert op2 == 1.0
    
    print("\nPASS: All logic tests passed!")

if __name__ == "__main__":
    try:
        test_opacity()
    except Exception as e:
        print(f"\nFAIL: {e}")
        import traceback
        traceback.print_exc()
