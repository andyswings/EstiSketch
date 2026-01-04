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
            if ((yi > y) != (yj > y)) and (
                    x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
                inside = not inside
            j = i
        return inside

    def _is_closed_polygon(self, wall_set):
        if not wall_set or len(wall_set) < 3:
            return False
        first = wall_set[0].start
        last = wall_set[-1].end
        tolerance = 5 / self.zoom
        return abs(
            first[0] -
            last[0]) < tolerance and abs(
            first[1] -
            last[1]) < tolerance

    def _get_corner_point_for_dimension(self, wall, nominal_point, simple_offset_point, offset_vec):
        """
        Calculate the true edge corner point, considering miter joins with connected walls.
        
        Args:
            wall: The current wall being dimensioned.
            nominal_point: The centerline endpoint (start or end) of the wall.
            simple_offset_point: The point shifted laterally by width/2.
            offset_vec: The lateral shift vector used.
            
        Returns:
            tuple: (x, y) coordinates of the wall corner.
        """
        # 1. Find connected wall at nominal_point
        connected_wall = None
        for w_set in self.wall_sets:
            for w in w_set:
                if w is wall:
                    continue
                # Check soft equality for connection
                if (abs(w.start[0] - nominal_point[0]) < 1e-4 and abs(w.start[1] - nominal_point[1]) < 1e-4) or \
                   (abs(w.end[0] - nominal_point[0]) < 1e-4 and abs(w.end[1] - nominal_point[1]) < 1e-4):
                    connected_wall = w
                    break
            if connected_wall:
                break
        
        # If no connected wall, return simple offset (butt end)
        if not connected_wall:
            return simple_offset_point

        # 2. Get vectors for both walls pointing AWAY from the connection vertex
        
        # Vector 1 (Current Wall)
        if (abs(wall.start[0] - nominal_point[0]) < 1e-4 and abs(wall.start[1] - nominal_point[1]) < 1e-4):
            dx1, dy1 = wall.end[0] - wall.start[0], wall.end[1] - wall.start[1]
        else:
            dx1, dy1 = wall.start[0] - wall.end[0], wall.start[1] - wall.end[1]
            
        len1 = math.hypot(dx1, dy1)
        if len1 == 0: return simple_offset_point
        ux1, uy1 = dx1 / len1, dy1 / len1

        # Vector 2 (Connected Wall)
        if (abs(connected_wall.start[0] - nominal_point[0]) < 1e-4 and abs(connected_wall.start[1] - nominal_point[1]) < 1e-4):
            dx2, dy2 = connected_wall.end[0] - connected_wall.start[0], connected_wall.end[1] - connected_wall.start[1]
        else:
            dx2, dy2 = connected_wall.start[0] - connected_wall.end[0], connected_wall.start[1] - connected_wall.end[1]

        len2 = math.hypot(dx2, dy2)
        if len2 == 0: return simple_offset_point
        ux2, uy2 = dx2 / len2, dy2 / len2

        # 3. Calculate Miter Direction (Bisector)
        # The join line goes along V1 + V2
        bx, by = ux1 + ux2, uy1 + uy2
        
        # Check for collinearity (parallel or anti-parallel)
        # If magnitude is near 0, they are 180 deg apart (straight line) -> continuous edge
        if math.hypot(bx, by) < 1e-3:
            return simple_offset_point
            
        # 4. Intersect Edge Line with Miter Line
        # Line 1 (Edge): P = simple_offset_point + t * U1
        # Line 2 (Miter): Q = nominal_point + s * (V1 + V2)
        
        # We solve for intersection:
        # Px + t*ux1 = Qx + s*bx
        # Py + t*uy1 = Qy + s*by
        
        # Rearrange:
        # t*ux1 - s*bx = Qx - Px
        # t*uy1 - s*by = Qy - Py
        
        # Cramer's rule or direct substitution
        det = ux1 * (-by) - (-bx) * uy1
        # det = -ux1*by + bx*uy1
        
        if abs(det) < 1e-5:
            return simple_offset_point
            
        dx_qp = nominal_point[0] - simple_offset_point[0]
        dy_qp = nominal_point[1] - simple_offset_point[1]
        
        # Solve for t
        t = (dx_qp * (-by) - (-bx) * dy_qp) / det
        
        # Intersection point
        ix = simple_offset_point[0] + t * ux1
        iy = simple_offset_point[1] + t * uy1
        
        return (ix, iy)
