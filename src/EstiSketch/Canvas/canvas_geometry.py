import math

from ..geometry.room_loop import find_enclosed_room_inner_polygon, inset_polygon, polygon_signed_area


class CanvasGeometryMixin:
    def _apply_alignment_snapping(self, x, y, exclude_points=None):
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
        if exclude_points:
            candidates = [pt for pt in candidates if pt not in exclude_points]
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
        if not wall_set or len(wall_set) < 2:
            return False
        if len(wall_set) == 2 and not any(getattr(w, 'is_curved', False) for w in wall_set):
            return False
        first = wall_set[0].start
        last = wall_set[-1].end
        zoom = getattr(self, 'zoom', 1.0) or 1.0
        tolerance = 5.0 / zoom
        return abs(first[0] - last[0]) < tolerance and abs(first[1] - last[1]) < tolerance

    def _get_wall_set_polygon(self, wall_set):
        """
        Extract the centerline polygon boundary for a wall set.
        For curved walls, intermediate points along the arc are sampled
        so that auto-generated rooms follow wall curves accurately.
        """
        return self._get_wall_set_polygon_with_widths(wall_set)[0]

    def _get_wall_set_inner_polygon(self, wall_set):
        """Polygon of the room enclosed by a closed wall set, drawn to the
        inside faces of the walls instead of the centerlines."""
        poly, widths = self._get_wall_set_polygon_with_widths(wall_set)
        return self._inset_polygon(poly, [w / 2.0 for w in widths])

    @staticmethod
    def _inset_polygon(poly, offsets):
        """Offset each edge i (poly[i] -> poly[i+1]) inward by offsets[i] and
        intersect consecutive offset edges. Orientation independent."""
        return inset_polygon(poly, offsets)

    def _find_closed_wall_room_inner_polygon(
        self,
        click_pt: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        """Return the smallest closed-wall-loop inside-face polygon around ``click_pt``."""
        is_visible = getattr(self, "is_object_on_visible_layer", lambda _obj: True)
        candidates: list[tuple[float, list[tuple[float, float]]]] = []

        visible_straight_walls = []
        for wall_set in getattr(self, "wall_sets", []):
            visible_in_set = [w for w in wall_set if is_visible(w)]
            for w in visible_in_set:
                if not getattr(w, "is_curved", False):
                    visible_straight_walls.append(w)

            has_curved = any(getattr(w, "is_curved", False) for w in wall_set)
            if has_curved and len(visible_in_set) == len(wall_set) and len(wall_set) >= 2:
                if self._is_closed_polygon(wall_set):
                    center_poly = self._get_wall_set_polygon(wall_set)
                    if self._point_in_polygon(click_pt, center_poly):
                        inner = self._get_wall_set_inner_polygon(wall_set)
                        area = abs(polygon_signed_area(inner))
                        if len(inner) >= 3 and area > 1.0:
                            candidates.append((area, inner))

        for wall in getattr(self, "walls", []):
            if is_visible(wall) and not getattr(wall, "is_curved", False):
                visible_straight_walls.append(wall)

        planar_inner = find_enclosed_room_inner_polygon(visible_straight_walls, click_pt)
        if planar_inner:
            planar_area = abs(polygon_signed_area(planar_inner))
            if planar_area > 1.0:
                candidates.append((planar_area, planar_inner))

        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])[1]

    def _get_wall_set_polygon_with_widths(self, wall_set):
        """Returns (points, widths) where widths[i] is the thickness of the
        wall whose edge starts at points[i]."""
        if not wall_set:
            return [], []

        poly = []
        widths = []
        n = len(wall_set)

        for i, wall in enumerate(wall_set):
            next_wall = wall_set[(i + 1) % n]
            d_end_to_next = min(
                math.hypot(wall.end[0] - next_wall.start[0], wall.end[1] - next_wall.start[1]),
                math.hypot(wall.end[0] - next_wall.end[0], wall.end[1] - next_wall.end[1])
            )
            d_start_to_next = min(
                math.hypot(wall.start[0] - next_wall.start[0], wall.start[1] - next_wall.start[1]),
                math.hypot(wall.start[0] - next_wall.end[0], wall.start[1] - next_wall.end[1])
            )
            is_reversed = (d_start_to_next < d_end_to_next) and (n > 1)
            p_start = wall.end if is_reversed else wall.start
            p_end = wall.start if is_reversed else wall.end

            if getattr(wall, 'is_curved', False) and getattr(wall, 'arc_center', None) and getattr(wall, 'arc_radius', None):
                cx, cy = wall.arc_center
                radius = wall.arc_radius

                start_angle = math.atan2(p_start[1] - cy, p_start[0] - cx)
                end_angle = math.atan2(p_end[1] - cy, p_end[0] - cx)

                angle_diff = end_angle - start_angle
                while angle_diff > math.pi:
                    angle_diff -= 2 * math.pi
                while angle_diff < -math.pi:
                    angle_diff += 2 * math.pi

                span_deg = math.degrees(abs(angle_diff))
                num_segs = max(8, min(32, math.ceil(span_deg / 5.0)))

                for seg in range(num_segs):
                    t = seg / float(num_segs)
                    ang = start_angle + t * angle_diff
                    poly.append((cx + radius * math.cos(ang), cy + radius * math.sin(ang)))
                    widths.append(wall.width)
            else:
                poly.append(p_start)
                widths.append(wall.width)

        return poly, widths

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

    def get_circle_from_3_points(self, p1, p2, p3):
        """
        Calculate center and radius of a circle defined by 3 points.
        Returns:
            ((center_x, center_y), radius) or None if collinear.
        """
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3

        D = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        
        if abs(D) < 1e-6:
            return None  # Points are collinear

        center_x = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / D
        center_y = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / D
        
        radius = math.hypot(center_x - x1, center_y - y1)
        
        return ((center_x, center_y), radius)

    def get_angle_at_point(self, center, point):
        """Calculate angle (radians) of 'point' around 'center', normalized to 0-2PI."""
        return math.atan2(point[1] - center[1], point[0] - center[0])

    def normalize_angle(self, angle):
        """Normalize angle to 0-2PI range."""
        return angle % (2 * math.pi)
