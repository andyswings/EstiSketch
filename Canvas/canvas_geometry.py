import math

class CanvasGeometryMixin:
    def _apply_alignment_snapping(self, x, y):
        candidates = []
        for wall_set in self.wall_sets:
            for wall in wall_set:
                candidates.append(wall.start)
                candidates.append(wall.end)
        for wall in self.walls:
            candidates.append(wall.start)
            candidates.append(wall.end)
        if self.current_wall:
            candidates.append(self.current_wall.start)
        if self.tool_mode == "draw_rooms":
            candidates.extend(self.current_room_points)
        tolerance = 10 / self.zoom
        aligned_x = x
        aligned_y = y
        candidate_x = None
        candidate_y = None
        min_diff_x = tolerance
        for (cx, cy) in candidates:
            diff = abs(cx - x)
            if diff < min_diff_x:
                min_diff_x = diff
                candidate_x = cx
        if candidate_x is not None:
            aligned_x = candidate_x
        min_diff_y = tolerance
        for (cx, cy) in candidates:
            diff = abs(cy - y)
            if diff < min_diff_y:
                min_diff_y = diff
                candidate_y = cy
        if candidate_y is not None:
            aligned_y = candidate_y
        candidate = None
        if candidate_x is not None or candidate_y is not None:
            candidate = (aligned_x, aligned_y)
        return aligned_x, aligned_y, candidate

    def _point_in_polygon(self, point, poly):
        x, y = point
        inside = False
        n = len(poly)
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
                inside = not inside
            j = i
        return inside

    def _is_closed_polygon(self, wall_set):
        if not wall_set or len(wall_set) < 3:
            return False
        first = wall_set[0].start
        last = wall_set[-1].end
        tolerance = 5 / self.zoom
        return abs(first[0] - last[0]) < tolerance and abs(first[1] - last[1]) < tolerance
