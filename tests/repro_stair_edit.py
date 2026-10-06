
import math
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from EstiSketch.components import Stair

def test_stair_rotate():
    print("Testing Stair Rotation...")
    # Stair at (100, 100) facing RIGHT (0 angle)
    stair = Stair(
        start_point=(100, 100),
        direction_angle=0.0,
        num_steps=10,
        riser_height=7.0,
        tread_depth=10.0,
        width=36.0
    )
    
    # Mocking logic from events_edit.py
    # Rotate Handle logic:
    # new_angle = math.atan2(new_y - start_y, new_x - start_x)
    # stair.direction_angle = new_angle - math.pi
    
    start_x, start_y = stair.start_point
    
    # 1. Simulate mouse drag to (100, 88) -> directly ABOVE start (y-axis negative/positive?)
    # Graphics coords: Y down is positive.
    # So (100, 112) is BELOW. (100, 88) is ABOVE.
    # dx = 0, dy = -12. atan2(-12, 0) = -90 deg (-pi/2).
    # stair.angle = -pi/2 - pi = -3pi/2 = pi/2 (90 deg).
    # Wait.
    # If handle is at (-12, 0) relative to start (backwards).
    # Using atan2 of mouse pos relative to start gives angle of mouse vector.
    # If mouse is at angle A from start, and handle is "behind" start, then stair forward is A - 180.
    
    # Case A: Mouse at (112, 100) -> dx=12, dy=0 -> angle 0.
    # stair.angle = 0 - 180 = -180.
    # This means stair is pointing LEFT. Correct because mouse (handle) is at RIGHT (112), so "behind" (handle) is at RIGHT, so "front" is LEFT.
    
    # Let's run the code
    new_x, new_y = (112, 100)
    dx = new_x - start_x
    dy = new_y - start_y
    new_angle = math.atan2(dy, dx)
    
    # Snap logic (simple round to 15 deg)
    def snap(rad):
        deg = math.degrees(rad)
        interval = 15.0
        snapped = round(deg / interval) * interval
        return math.radians(snapped)
        
    new_angle = snap(new_angle)
    stair.direction_angle = new_angle - math.pi
    
    print(f"  Mouse at ({new_x}, {new_y}): Dir Angle = {math.degrees(stair.direction_angle)} (Expected ~180)")
    
    # Case B: Mouse at (100, 112) -> dx=0, dy=12 (DOWN). Angle 90.
    # stair.angle = 90 - 180 = -90 (UP).
    new_x, new_y = (100, 112)
    dx = new_x - start_x
    dy = new_y - start_y
    new_angle = snap(math.atan2(dy, dx))
    stair.direction_angle = new_angle - math.pi
    
    print(f"  Mouse at ({new_x}, {new_y}): Dir Angle = {math.degrees(stair.direction_angle)} (Expected -90)")
    



if __name__ == "__main__":
    test_stair_rotate()
