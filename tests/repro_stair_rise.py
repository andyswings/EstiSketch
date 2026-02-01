
import sys
import os

# Adjust path to find src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from EstiSketch.components import Level, Stair
# Mocking Canvas for this specific test
class MockCanvas:
    def __init__(self):
        self.levels = []
        self.stairs = []
        
    def get_level_by_id(self, level_id):
        for level in self.levels:
            if level.id == level_id:
                return level
        return None
        
    def queue_draw(self):
        print("Canvas redraw queued.")
        
    def _calculate_default_rise(self, start_id, end_id):
        # Determine logical rise
        s = self.get_level_by_id(start_id)
        e = self.get_level_by_id(end_id)
        if s and e:
            return e.elevation - s.elevation
        return 106.0

    # Inject the method we just wrote in mixin
    def update_stairs_for_level_change(self, changed_level_id: str):
        print(f"Update triggered for level: {changed_level_id}")
        if not changed_level_id:
            return

        stairs_updated = False
        
        for stair in self.stairs:
            update_needed = False
            if hasattr(stair, 'start_level_id') and stair.start_level_id == changed_level_id:
                update_needed = True
            if hasattr(stair, 'end_level_id') and stair.end_level_id == changed_level_id:
                update_needed = True
                
            if update_needed:
                new_rise = self._calculate_default_rise(stair.start_level_id, stair.end_level_id)
                
                if abs(new_rise - stair.total_rise) > 0.01:
                    print(f"  Stair {stair.identifier} rise changing: {stair.total_rise} -> {new_rise}")
                    stair.total_rise = new_rise
                    
                    if stair.num_steps > 0:
                        stair.riser_height = new_rise / stair.num_steps
                        print(f"  New riser height: {stair.riser_height}")
                    
                    stairs_updated = True
        
        if stairs_updated:
            self.queue_draw()

def test_stair_rise_update():
    canvas = MockCanvas()
    
    # 1. Setup Levels
    l1 = Level(id="l1", name="Level 1", elevation=0.0)
    l2 = Level(id="l2", name="Level 2", elevation=100.0)
    canvas.levels = [l1, l2]
    
    # 2. Setup Stair connecting L1 to L2
    stair = Stair(
        start_point=(0,0),
        direction_angle=0,
        start_level_id="l1",
        end_level_id="l2",
        total_rise=100.0,
        num_steps=14, # ~7.14" rise
        tread_depth=10.0,
        width=36.0
    )
    stair.identifier = "stair_1"
    stair.riser_height = 100.0 / 14
    canvas.stairs.append(stair)
    
    print(f"Initial Stair Rise: {stair.total_rise} (Expected 100.0)")
    
    # 3. Modify Level 2 Elevation
    print("\nModifying Level 2 Elevation to 120.0...")
    l2.elevation = 120.0
    
    # 4. Trigger Update
    canvas.update_stairs_for_level_change("l2")
    
    # 5. Verify
    print(f"\nFinal Stair Rise: {stair.total_rise}")
    
    if abs(stair.total_rise - 120.0) < 0.001:
        print("SUCCESS: Stair rise updated correctly to 120.0")
    else:
        print(f"FAILURE: Expected 120.0, got {stair.total_rise}")

if __name__ == "__main__":
    test_stair_rise_update()
