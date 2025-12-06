
import os
import sys
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

# Add project root to path
sys.path.append("/home/andrew/Documents/Building_App/EstiSketch")

from components import Text
from Canvas.canvas_area import CanvasArea
from project_io import save_project, open_project

def verify_text_tool():
    print("Verifying Text Tool...")
    
    # 1. Create Text object
    t = Text(10, 10, "Hello World", 100, 50, "text-1")
    assert t.content == "Hello World"
    assert t.x == 10
    assert t.y == 10
    print("Text object creation: OK")
    
    # 2. Mock Canvas
    class Config:
        PIXELS_PER_INCH = 2.0
        SNAP_ENABLED = True
        SNAP_THRESHOLD = 10.0
        DEFAULT_ZOOM_LEVEL = 1.0
        WINDOW_WIDTH = 800
        WINDOW_HEIGHT = 600
        
    class MockApp:
        config = Config()
        def queue_draw(self): pass
        
    canvas = CanvasArea(Config())
    canvas.texts.append(t)
    
    # 3. Save Project
    filepath = "test_text_project.xml"
    save_project(canvas, 800, 600, filepath)
    print("Project saved: OK")
    
    # 4. Clear and Load
    canvas.texts.clear()
    assert len(canvas.texts) == 0
    
    open_project(canvas, filepath)
    assert len(canvas.texts) == 1
    loaded_t = canvas.texts[0]
    assert loaded_t.content == "Hello World"
    assert loaded_t.x == 10.0
    assert loaded_t.y == 10.0
    assert loaded_t.width == 100.0
    assert loaded_t.identifier == "text-1"
    print("Project loaded: OK")
    
    # 5. Verify Equality/Identity (Fix check)
    t2 = Text(50, 50, "Text 2", 100, 50, "text-2")
    canvas.texts.append(t2)
    # They should NOT be equal
    assert loaded_t != t2
    print("Identity check: OK")
    
    # Clean up
    if os.path.exists(filepath):
        os.remove(filepath)
        
    print("Verification Complete: ALL PASS")

if __name__ == "__main__":
    verify_text_tool()
