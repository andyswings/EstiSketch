
import sys
import unittest
from unittest.mock import MagicMock
from dataclasses import dataclass

# Mock dependencies
class MockConverter:
    def parse_measurement(self, val):
        return float(val) if val else 0.0

@dataclass
class MockStair:
    identifier: str = "stair1"
    start_level_id: str = "L1"
    end_level_id: str = "L2"
    total_rise: float = 100.0
    riser_height: float = 7.0
    num_steps: int = 14
    width: float = 36.0
    tread_depth: float = 10.0

@dataclass
class MockLevel:
    id: str
    name: str
    elevation: float
    height: float = 108.0

# Mixin Simulation
class CanvasStairEventsMixin:
    def __init__(self):
        self.stairs = []
        self.levels = []
        self.converter = MockConverter()
        self.selected_items = []
        self.properties_dock = MagicMock()
        
    def queue_draw(self):
        print("Canvas redraw queued")

    def _calculate_default_rise(self, start_id, end_id):
        # Simplified simulation of the real calculation
        start_level = next((l for l in self.levels if l.id == start_id), None)
        end_level = next((l for l in self.levels if l.id == end_id), None)
        if start_level and end_level:
            return end_level.elevation - start_level.elevation
        return 0.0

    # Paste the updated method here for testing
    def update_stairs_for_level_change(self, changed_level_id: str):
        if not changed_level_id:
            return

        stairs_updated = False
        
        for stair in self.stairs:
            update_needed = False
            start = getattr(stair, 'start_level_id', None)
            end = getattr(stair, 'end_level_id', None)
            
            if start == changed_level_id:
                update_needed = True
            if end == changed_level_id:
                update_needed = True
                
            if update_needed:
                new_rise = self._calculate_default_rise(stair.start_level_id, stair.end_level_id)
                
                if abs(new_rise - stair.total_rise) > 0.01:
                    print(f"Updating stair {stair.identifier} rise from {stair.total_rise} to {new_rise}")
                    stair.total_rise = new_rise
                    if stair.num_steps > 0:
                        stair.riser_height = new_rise / stair.num_steps
                    stairs_updated = True
        
        if stairs_updated:
            self.queue_draw()
            
            if getattr(self, "selected_items", None) and hasattr(self, "properties_dock"):
                 has_selected_stair = any(item.get("type") == "stair" for item in self.selected_items)
                 if has_selected_stair:
                     print("Properties dock refresh triggered")
                     self.properties_dock.refresh_tabs(self.selected_items)

class TestStairUpdate(unittest.TestCase):
    def test_update_triggers_properties_refresh(self):
        canvas = CanvasStairEventsMixin()
        
        # Setup Levels
        l1 = MockLevel("L1", "Level 1", 0.0)
        l2 = MockLevel("L2", "Level 2", 100.0)
        canvas.levels = [l1, l2]
        
        # Setup Stair connected to L1 -> L2
        stair = MockStair()
        canvas.stairs = [stair]
        
        # Select the stair
        canvas.selected_items = [{"type": "stair", "object": stair}]
        
        # Change Level 2 Elevation
        l2.elevation = 120.0
        
        # Trigger Update
        canvas.update_stairs_for_level_change("L2")
        
        # Verify Stair Updated
        self.assertEqual(stair.total_rise, 120.0)
        
        # Verify Properties Dock Refreshed
        canvas.properties_dock.refresh_tabs.assert_called_once()
        print("Success: Properties dock was refreshed!")

if __name__ == '__main__':
    unittest.main()
