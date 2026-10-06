#!/usr/bin/env python3
"""Test wall edge snapping functionality."""

import sys
import math
from dataclasses import dataclass

# Mock Wall class
@dataclass
class MockWall:
    start: tuple
    end: tuple
    width: float
    is_curved: bool = False

# Mock SnappingManager with just the wall edge methods
class SnappingManager:
    def __init__(self):
        self.snap_threshold = 4.0
    
    def get_wall_edge_lines(self, wall):
        """Calculate the two parallel edge lines for a wall."""
        if getattr(wall, 'is_curved', False):
            return []
        
        dx = wall.end[0] - wall.start[0]
        dy = wall.end[1] - wall.start[1]
        length = math.sqrt(dx * dx + dy * dy)
        
        if length == 0:
            return []
        
        perp_x = -dy / length
        perp_y = dx / length
        offset = wall.width / 2.0
        
        edge1_start = (wall.start[0] + perp_x * offset, 
                      wall.start[1] + perp_y * offset)
        edge1_end = (wall.end[0] + perp_x * offset, 
                    wall.end[1] + perp_y * offset)
        
        edge2_start = (wall.start[0] - perp_x * offset, 
                      wall.start[1] - perp_y * offset)
        edge2_end = (wall.end[0] - perp_x * offset, 
                    wall.end[1] - perp_y * offset)
        
        return [(edge1_start, edge1_end), (edge2_start, edge2_end)]

    def closest_point_on_line(self, px, py, line_start, line_end):
        """Find the closest point on a line segment to a given point."""
        x1, y1 = line_start
        x2, y2 = line_end
        
        dx = x2 - x1
        dy = y2 - y1
        
        if dx == 0 and dy == 0:
            return line_start
        
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0, min(1, t))
        
        return (x1 + t * dx, y1 + t * dy)

    def snap_to_wall_edge(self, x, y, walls):
        """Snap to nearby wall edges (faces)."""
        best_point = (x, y)
        best_dist_sq = self.snap_threshold ** 2
        
        for wall in walls:
            edges = self.get_wall_edge_lines(wall)
            for edge_start, edge_end in edges:
                closest = self.closest_point_on_line(x, y, edge_start, edge_end)
                dist_sq = (x - closest[0]) ** 2 + (y - closest[1]) ** 2
                
                if dist_sq < best_dist_sq:
                    best_point = closest
                    best_dist_sq = dist_sq
        
        if best_dist_sq < self.snap_threshold ** 2:
            return best_point, "wall_edge"
        return (x, y), "none"


def test_horizontal_wall_edges():
    """Test edge calculation for a horizontal wall."""
    print("Test 1: Horizontal wall (100 inches long, 6 inches wide)")
    wall = MockWall(start=(0, 50), end=(100, 50), width=6)
    
    sm = SnappingManager()
    edges = sm.get_wall_edge_lines(wall)
    
    print(f"  Edge 1: {edges[0]}")
    print(f"  Edge 2: {edges[1]}")
    
    # For horizontal wall, edges should be offset 3 inches up/down
    assert abs(edges[0][0][1] - 53) < 0.01, "Edge 1 start should be at y=53"
    assert abs(edges[1][0][1] - 47) < 0.01, "Edge 2 start should be at y=47"
    print("  ✓ Edges correctly offset by ±3 inches\n")


def test_vertical_wall_edges():
    """Test edge calculation for a vertical wall."""
    print("Test 2: Vertical wall (80 inches tall, 4 inches wide)")
    wall = MockWall(start=(50, 0), end=(50, 80), width=4)
    
    sm = SnappingManager()
    edges = sm.get_wall_edge_lines(wall)
    
    print(f"  Edge 1: {edges[0]}")
    print(f"  Edge 2: {edges[1]}")
    
    # For vertical wall, edges should be offset 2 inches left/right
    # Edge 1 is offset to the left (negative perpendicular)
    # Edge 2 is offset to the right (positive perpendicular)
    assert abs(edges[0][0][0] - 48) < 0.01, "Edge 1 start should be at x=48"
    assert abs(edges[1][0][0] - 52) < 0.01, "Edge 2 start should be at x=52"
    print("  ✓ Edges correctly offset by ±2 inches\n")


def test_snap_to_edge():
    """Test snapping to a wall edge."""
    print("Test 3: Snap point near wall edge")
    wall = MockWall(start=(0, 50), end=(100, 50), width=6)
    
    sm = SnappingManager()
    
    # Point near top edge (should snap)
    point = (50, 54)
    snapped, snap_type = sm.snap_to_wall_edge(point[0], point[1], [wall])
    
    print(f"  Original point: {point}")
    print(f"  Snapped to: {snapped}")
    print(f"  Snap type: {snap_type}")
    
    assert snap_type == "wall_edge", "Should detect wall edge"
    assert abs(snapped[1] - 53) < 0.01, "Should snap to y=53"
    print("  ✓ Correctly snapped to wall edge\n")


def test_different_thickness_alignment():
    """Test aligning walls of different thicknesses."""
    print("Test 4: Aligning 4-inch wall to 6-inch wall edge")
    
    # Existing 6-inch wall
    wall_6in = MockWall(start=(0, 50), end=(100, 50), width=6)
    
    # New 4-inch wall endpoint near the edge
    new_point = (50, 55)  # Near top edge of 6-inch wall
    
    sm = SnappingManager()
    snapped, snap_type = sm.snap_to_wall_edge(new_point[0], new_point[1], [wall_6in])
    
    print(f"  6-inch wall top edge at y=53")
    print(f"  New 4-inch wall point: {new_point}")
    print(f"  Snapped to: {snapped}")
    
    assert snap_type == "wall_edge"
    assert abs(snapped[1] - 53) < 0.01
    print("  ✓ Successfully aligned different thickness walls\n")


if __name__ == "__main__":
    print("="*50)
    print("Wall Edge Snapping Tests")
    print("="*50 + "\n")
    
    test_horizontal_wall_edges()
    test_vertical_wall_edges()
    test_snap_to_edge()
    test_different_thickness_alignment()
    
    print("="*50)
    print("✅ All tests passed!")
    print("="*50)
