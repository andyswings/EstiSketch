
import sys
import os
from dataclasses import dataclass

# Mock Stair class
@dataclass
class MockStair:
    stair_type: str = "straight"
    steps_before_landing: int = 0
    num_steps: int = 14

# Simulate the Logic in properties_stair.py
class MockStairPropertiesWidget:
    def __init__(self):
        self.current_stairs = []
        self.block_updates = False
    
    def set_stairs(self, stairs):
        self.current_stairs = stairs
        # In the real code, basic population happens here
    
    def on_type_changed(self, new_type):
        if self.block_updates or not self.current_stairs:
            return
            
        print(f"DEBUG: Changing type to {new_type}")
        
        for stair in self.current_stairs:
            stair.stair_type = new_type
        
        # --- Logic to be tested/implemented ---
        is_multi_segment = (new_type in ["L-shaped", "U-shaped"])
        
        if is_multi_segment:
             for stair in self.current_stairs:
                 # Check if steps_before_landing is 0 (default)
                 current_val = getattr(stair, 'steps_before_landing', 0)
                 if current_val == 0:
                     print(f"DEBUG: Detected default steps_before_landing (0). Setting to 3.")
                     stair.steps_before_landing = 3
                 else:
                     print(f"DEBUG: steps_before_landing is already {current_val}. Keeping it.")
        # ---------------------------------------

def test_stair_init_logic():
    print("--- Testing Stair Init Logic ---")
    
    # Scene 1: New stair (straight) -> Change to L-shaped
    print("\nScene 1: Straight -> L-shaped")
    stair1 = MockStair()
    widget = MockStairPropertiesWidget()
    widget.set_stairs([stair1])
    
    print(f"Before: type={stair1.stair_type}, steps_before={stair1.steps_before_landing}")
    widget.on_type_changed("L-shaped")
    print(f"After:  type={stair1.stair_type}, steps_before={stair1.steps_before_landing}")
    
    if stair1.steps_before_landing == 3:
        print("PASS: Defaulted to 3 steps")
    else:
        print(f"FAIL: Expected 3, got {stair1.steps_before_landing}")

    # Scene 2: Existing L-stair with set values -> Change to U-shaped
    print("\nScene 2: L-shaped (custom 5) -> U-shaped")
    stair2 = MockStair(stair_type="L-shaped", steps_before_landing=5)
    widget.set_stairs([stair2])
    
    print(f"Before: type={stair2.stair_type}, steps_before={stair2.steps_before_landing}")
    widget.on_type_changed("U-shaped")
    print(f"After:  type={stair2.stair_type}, steps_before={stair2.steps_before_landing}")

    if stair2.steps_before_landing == 5:
        print("PASS: Preserved custom value 5")
    else:
        print(f"FAIL: Expected 5, got {stair2.steps_before_landing}")

if __name__ == "__main__":
    test_stair_init_logic()
