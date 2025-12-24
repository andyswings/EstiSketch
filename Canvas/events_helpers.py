import math
from typing import List

class EventsHelpersMixin:
    def distance_point_to_segment(self, P: tuple[float, float], A: tuple[float, float], B: tuple[float, float]) -> float:
        """
        Calculate the shortest distance from a point to a line segment.

        Given a point P and a segment defined by endpoints A and B, this method computes
        the minimum Euclidean distance from P to any point on the segment AB. If the segment
        is degenerate (A and B are the same), it returns the distance from P to A.

        Args:
            P (tuple[float, float]): The point as (x, y).
            A (tuple[float, float]): The start point of the segment as (x, y).
            B (tuple[float, float]): The end point of the segment as (x, y).

        Returns:
            float: The shortest distance from P to the segment AB.
        """
        px, py = P = P
        ax, ay = A
        bx, by = B
        dx = bx - ax
        dy = by - ay
        if dx == dy == 0:
            return math.hypot(px - ax, py - ay)
        t = ((px - ax) * dx + (py - ay) * dy) / (dx ** 2 + dy ** 2)
        t = max(0, min(1, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return math.hypot(px - proj_x, py - proj_y)
    
    
    def line_intersects_rect(self, A: tuple[float, float], B: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
        """
        Determine if a line segment intersects a rectangle.

        Checks whether the line segment defined by endpoints A and B crosses or touches
        the rectangle specified by rect = (rx1, ry1, rx2, ry2), where (rx1, ry1) is the
        top-left corner and (rx2, ry2) is the bottom-right corner. The function returns
        True if the segment is inside the rectangle or intersects any of its edges.

        Args:
            A (tuple[float, float]): Start point of the line segment (x, y).
            B (tuple[float, float]): End point of the line segment (x, y).
            rect (tuple[float, float, float, float]): Rectangle as (rx1, ry1, rx2, ry2).

        Returns:
            bool: True if the segment intersects or is contained in the rectangle, False otherwise.
        """
        rx1, ry1, rx2, ry2 = rect

        def point_in_rect(pt):
            x, y = pt
            return rx1 <= x <= rx2 and ry1 <= y <= ry2

        # If either endpoint is inside the rectangle, the segment intersects.
        if point_in_rect(A) or point_in_rect(B):
            return True

        # Helper: Check if two segments (p,q) and (r,s) intersect.
        def segments_intersect(p, q, r, s):
            def orientation(a, b, c):
                # Calculate the orientation of triplet (a,b,c)
                val = (b[1]-a[1])*(c[0]-b[0]) - (b[0]-a[0])*(c[1]-b[1])
                if abs(val) < 1e-6:
                    return 0  # colinear
                return 1 if val > 0 else 2  # 1: clockwise, 2: counterclockwise

            def on_segment(a, b, c):
                return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and
                        min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))

            o1 = orientation(p, q, r)
            o2 = orientation(p, q, s)
            o3 = orientation(r, s, p)
            o4 = orientation(r, s, q)

            if o1 != o2 and o3 != o4:
                return True

            if o1 == 0 and on_segment(p, q, r):
                return True
            if o2 == 0 and on_segment(p, q, s):
                return True
            if o3 == 0 and on_segment(r, s, p):
                return True
            if o4 == 0 and on_segment(r, s, q):
                return True

            return False

        # Define the rectangle's four edges:
        edges = [
            ((rx1, ry1), (rx2, ry1)),  # top edge
            ((rx2, ry1), (rx2, ry2)),  # right edge
            ((rx2, ry2), (rx1, ry2)),  # bottom edge
            ((rx1, ry2), (rx1, ry1))   # left edge
        ]

        for edge in edges:
            if segments_intersect(A, B, edge[0], edge[1]):
                return True
        return False
            

    def _get_candidate_points(self) -> List[tuple[float, float]]:
        """
        Collect all candidate points for snapping and alignment.

        This method gathers all wall endpoints from all wall sets on the canvas.
        The returned list is used for snapping logic and alignment assistance when drawing
        or editing walls, rooms, or polylines.

        Returns:
            List[Tuple[float, float]]: A list of (x, y) tuples representing wall endpoints.
        """
        return [point for wall_set in self.wall_sets for wall in wall_set for point in (wall.start, wall.end)]
    

    def _points_close(self, p1, p2, tol):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1]) < tol
