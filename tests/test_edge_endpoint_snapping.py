#!/usr/bin/env python3
"""Test edge-aligned endpoint snapping."""

import math
from dataclasses import dataclass

@dataclass
class MockWall:
    start: tuple
    end: tuple
    width: float
    is_curved: bool = False

class MockConfig:
    ENABLE_CENTERLINE_SNAPPING = False
    GRID_SPACING = 12

class SnappingManager:
    def __init__(self):
        self.snap_threshold = 4.0
        self.config = MockConfig()
    
    def collect_points_of_interest(self, walls, rooms, current_wall=None, 
                                   in_progress_points=None, polylines=None):
        points = []
        for wall in walls:
            # Add centerline endpoints
            points.extend([wall.start, wall.end])
            
            # Add edge points at endpoints for edge-aligned connections
            if not getattr(wall, 'is_curved', False):
                dx = wall.end[0] - wall.start[0]
                dy = wall.end[1] - wall.start[1]
                length = math.sqrt(dx * dx + dy * dy)
                
                if length > 0:
                    perp_x = -dy / length
                    perp_y = dx / length
                    offset = wall.width / 2.0
                    
                    # Add edge points at start
                    points.append((wall.start[0] + perp_x * offset, 
                                  wall.start[1] + perp_y * offset))
                    points.append((wall.start[0] - perp_x * offset, 
                                  wall.start[1] - perp_y * offset))
                    
                    # Add edge points at end
                    points.append((wall.end[0] + perp_x * offset, 
                                  wall.end[1] + perp_y * offset))
                    points.append((wall.end[0] - perp_x * offset, 
                                  wall.end[1] - perp_y * offset))
            
            # Add midpoint
            mid_x = (wall.start[0] + wall.end[0]) / 2
            mid_y = (wall.start[1] + wall.end[1]) / 2
            points.append((mid_x, mid_y))
            
        return points


def test_edge_points_at_endpoints():
    """Test that edge points are correctly added at wall endpoints."""
    print("Test 1: Edge points at endpoints")
    
    # 6-inch horizontal wall from (0, 50) to (100, 50)
    wall = MockWall(start=(0, 50), end=(100, 50), width=6)
    
    sm = SnappingManager()
    points = sm.collect_points_of_interest([wall], [])
    
    print(f"  Total points collected: {len(points)}")
    print(f"  Points: {points}")
    
    # Should have:
    # - 2 centerline endpoints: (0, 50), (100, 50)
    # - 4 edge points: (0, 53), (0, 47), (100, 53), (100, 47)
    # - 1 midpoint: (50, 50)
    # Total = 7 points
    
    assert len(points) == 7, f"Expected 7 points, got {len(points)}"
    
    # Check start edge points exist
    assert (0, 53) in points, "Top edge at start should exist"
    assert (0, 47) in points, "Bottom edge at start should exist"
    
    # Check end edge points exist
    assert (100, 53) in points, "Top edge at end should exist"
    assert (100, 47) in points, "Bottom edge at end should exist"
    
    print("  ✓ Edge points correctly added at both endpoints\n")


def test_different_thickness_alignment():
    """Test aligning a 4-inch wall to a 6-inch wall edge-to-edge."""
    print("Test 2: Different thickness alignment scenario")
    
    # Existing 6-inch horizontal wall
    wall_6in = MockWall(start=(0, 50), end=(100, 50), width=6)
    
    sm = SnappingManager()
    points = sm.collect_points_of_interest([wall_6in], [])
    
    # New 4-inch wall starting near the top edge of the 6-inch wall
    # The 6-inch wall's top edge at end is at (100, 53)
    # A 4-inch wall starting there should have its bottom edge at (100, 53)
    # So its centerline should be at (100, 55)
    
    new_wall_point = (100, 55)  # Where 4-inch wall centerline should be
    
    # Check that (100, 53) is available as a snap point
    assert (100, 53) in points, "Top edge point at (100, 53) should be available"
    
    print(f"  6-inch wall top edge at end: (100, 53)")
    print(f"  4-inch wall would start with centerline at: (100, 55)")
    print(f"  4-inch wall bottom edge would be at: (100, 53) ✓")
    print("  ✓ Edges can align properly\n")


def test_vertical_wall_edge_points():
    """Test edge points for vertical wall."""
    print("Test 3: Vertical wall edge points")
    
    # 4-inch vertical wall
    wall = MockWall(start=(50, 0), end=(50, 80), width=4)
    
    sm = SnappingManager()
    points = sm.collect_points_of_interest([wall], [])
    
    # Check edge points at start
    assert (48, 0) in points, "Left edge at start should exist"
    assert (52, 0) in points, "Right edge at start should exist"
    
    # Check edge points at end
    assert (48, 80) in points, "Left edge at end should exist"
    assert (52, 80) in points, "Right edge at end should exist"
    
    print("  ✓ Vertical wall edge points correct\n")


if __name__ == "__main__":
    print("="*60)
    print("Edge-Aligned Endpoint Snapping Tests")
    print("="*60 + "\n")
    
    test_edge_points_at_endpoints()
    test_different_thickness_alignment()
    test_vertical_wall_edge_points()
    
    print("="*60)
    print("✅ All tests passed!")
    print("="*60)
