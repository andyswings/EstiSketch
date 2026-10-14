import math

from .geometry.wall_joins import face_flush_offsets


class SnappingManager:
    # Lower number means higher priority.
    SNAP_PRIORITY = {
        "endpoint": 1,
        "midpoint": 2,
        "wall_centerline": 2.5,  # Snap to wall centerline
        "face_flush": 3,        # Parallel wall face/center alignment
        "wall_edge": 3.5,       # Wall outer/inner face edge
        "alignment_cross": 4,   # Snapped to both H and V alignment with points
        "alignment_vertical": 5,
        "alignment_horizontal": 5,
        "angle": 6,
        "axis": 7,
        "perpendicular": 8,
        "grid": 9,
        "distance": 10,
        "tangent": 11,
        "none": 100,
    }

    def __init__(
            self,
            snap_enabled=True,
            snap_threshold=4,
            config=None,
            zoom=1.0):
        self.snap_enabled = snap_enabled
        # Distance in model units (inches) for snap detection
        self.snap_threshold = snap_threshold
        self.config = config
        self.allowed_angles = [
            0,
            22.5,
            45,
            67.5,
            90,
            112.5,
            135,
            157.5,
            180,
            202.5,
            225,
            247.5,
            270,
            292.5,
            315,
            337.5]
        self.angle_tolerance = 10  # Increased from 5 to 10
        # Guide for the face-flush snap chosen by the last snap_point call:
        # (line_start, line_end, kind) or None.
        self.face_flush_guide = None
        self._face_guides = {}

    def collect_points_of_interest(
            self,
            walls,
            rooms,
            current_wall=None,
            in_progress_points=None,
            polylines=None):
        points = []
        for wall in walls:
            # Add centerline endpoints
            points.extend([wall.start, wall.end])
            
            # Add edge points at endpoints for edge-aligned connections
            # This allows walls of different thicknesses to snap edge-to-edge
            if not getattr(wall, 'is_curved', False):  # Skip curved walls
                dx = wall.end[0] - wall.start[0]
                dy = wall.end[1] - wall.start[1]
                length = math.sqrt(dx * dx + dy * dy)
                
                if length > 0:
                    # Unit perpendicular vector
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
            
        for room in rooms:
            points.extend(room.points)
        if current_wall and current_wall.start != current_wall.end:
            points.append(current_wall.start)
        if in_progress_points:
            points.extend(in_progress_points)
        # Add polyline endpoints
        if polylines:
            for poly in polylines:
                points.extend([poly.start, poly.end])
        if self.config and self.config.ENABLE_CENTERLINE_SNAPPING:
            points.extend(self.find_intersections(walls))
        # print(f"Collected points: {points}")
        return points

    def snap_to_points(self, x, y, points, walls):
        best_candidate = (x, y)
        best_dist_sq = self.snap_threshold ** 2
        best_type = "none"

        wall_endpoints = {w.start for w in walls} | {w.end for w in walls}
        wall_midpoints = {
            ((w.start[0] + w.end[0]) / 2.0, (w.start[1] + w.end[1]) / 2.0)
            for w in walls if not getattr(w, 'is_curved', False)
        }
        edge_points = set()
        for w in walls:
            if not getattr(w, 'is_curved', False):
                dx = w.end[0] - w.start[0]
                dy = w.end[1] - w.start[1]
                length = math.hypot(dx, dy)
                if length > 0:
                    perp_x = -dy / length
                    perp_y = dx / length
                    offset = w.width / 2.0
                    edge_points.add((w.start[0] + perp_x * offset, w.start[1] + perp_y * offset))
                    edge_points.add((w.start[0] - perp_x * offset, w.start[1] - perp_y * offset))
                    edge_points.add((w.end[0] + perp_x * offset, w.end[1] + perp_y * offset))
                    edge_points.add((w.end[0] - perp_x * offset, w.end[1] - perp_y * offset))

        for px, py in points:
            d_sq = (x - px) ** 2 + (y - py) ** 2
            if d_sq < best_dist_sq:
                best_candidate = (px, py)
                best_dist_sq = d_sq
                if (px, py) in wall_endpoints:
                    best_type = "endpoint"
                elif (px, py) in wall_midpoints:
                    best_type = "midpoint"
                elif (px, py) in edge_points:
                    best_type = "wall_edge"
                else:
                    best_type = "endpoint"
        return best_candidate, best_type

    def get_wall_edge_lines(self, wall):
        """Calculate the two parallel edge lines for a wall.
        
        Returns a list of tuples: [(edge1_start, edge1_end), (edge2_start, edge2_end)]
        Each edge is a line segment parallel to the wall centerline, offset by half width.
        """
        # Skip curved walls for now
        if getattr(wall, 'is_curved', False):
            return []
        
        dx = wall.end[0] - wall.start[0]
        dy = wall.end[1] - wall.start[1]
        length = math.sqrt(dx * dx + dy * dy)
        
        if length == 0:
            return []
        
        # Unit perpendicular vector (rotated 90 degrees)
        perp_x = -dy / length
        perp_y = dx / length
        
        # Offset by half width for each edge
        offset = wall.width / 2.0
        
        # Edge 1 (left side)
        edge1_start = (wall.start[0] + perp_x * offset, 
                      wall.start[1] + perp_y * offset)
        edge1_end = (wall.end[0] + perp_x * offset, 
                    wall.end[1] + perp_y * offset)
        
        # Edge 2 (right side)
        edge2_start = (wall.start[0] - perp_x * offset, 
                      wall.start[1] - perp_y * offset)
        edge2_end = (wall.end[0] - perp_x * offset, 
                    wall.end[1] - perp_y * offset)
        
        return [(edge1_start, edge1_end), (edge2_start, edge2_end)]

    def closest_point_on_line(self, px, py, line_start, line_end):
        """Find the closest point on a line segment to a given point.
        
        Projects the point onto the line and clamps to the segment bounds.
        """
        x1, y1 = line_start
        x2, y2 = line_end
        
        dx = x2 - x1
        dy = y2 - y1
        
        if dx == 0 and dy == 0:
            return line_start
        
        # Calculate parameter t for the projection
        # t=0 means at line_start, t=1 means at line_end
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        
        # Clamp t to [0, 1] to stay within the line segment
        t = max(0, min(1, t))
        
        return (x1 + t * dx, y1 + t * dy)

    def snap_to_wall_edge(self, x, y, walls):
        """Snap to nearby wall edges (faces).
        
        Finds the closest point on any wall edge line and snaps if within threshold.
        """
        best_point = (x, y)
        best_dist_sq = self.snap_threshold ** 2
        
        for wall in walls:
            edges = self.get_wall_edge_lines(wall)
            for edge_start, edge_end in edges:
                # Find closest point on this edge line
                closest = self.closest_point_on_line(x, y, edge_start, edge_end)
                dist_sq = (x - closest[0]) ** 2 + (y - closest[1]) ** 2
                
                if dist_sq < best_dist_sq:
                    best_point = closest
                    best_dist_sq = dist_sq
        
        if best_dist_sq < self.snap_threshold ** 2:
            return best_point, "wall_edge"
        return (x, y), "none"

    def snap_to_wall_centerline(self, x, y, walls):
        """Snap to nearby wall centerlines.

        Finds the closest point on any wall centerline segment (or arc centerline for curved walls)
        and snaps if within threshold.
        """
        best_point = (x, y)
        best_dist_sq = self.snap_threshold ** 2

        for wall in walls:
            if getattr(wall, 'is_curved', False) and getattr(wall, 'arc_center', None) and getattr(wall, 'arc_radius', None):
                cx, cy = wall.arc_center
                radius = wall.arc_radius
                dx, dy = x - cx, y - cy
                dist = math.hypot(dx, dy)
                if dist > 1e-9:
                    pt_circle = (cx + radius * dx / dist, cy + radius * dy / dist)
                    start_angle = math.atan2(wall.start[1] - cy, wall.start[0] - cx)
                    end_angle = math.atan2(wall.end[1] - cy, wall.end[0] - cx)
                    pt_angle = math.atan2(pt_circle[1] - cy, pt_circle[0] - cx)
                    diff = (end_angle - start_angle)
                    while diff > math.pi:
                        diff -= 2 * math.pi
                    while diff < -math.pi:
                        diff += 2 * math.pi
                    p_diff = (pt_angle - start_angle)
                    while p_diff > math.pi:
                        p_diff -= 2 * math.pi
                    while p_diff < -math.pi:
                        p_diff += 2 * math.pi
                    if (diff >= 0 and 0 <= p_diff <= diff) or (diff < 0 and diff <= p_diff <= 0):
                        dist_sq = (x - pt_circle[0]) ** 2 + (y - pt_circle[1]) ** 2
                        if dist_sq < best_dist_sq:
                            best_point = pt_circle
                            best_dist_sq = dist_sq
            else:
                closest = self.closest_point_on_line(x, y, wall.start, wall.end)
                dist_sq = (x - closest[0]) ** 2 + (y - closest[1]) ** 2
                if dist_sq < best_dist_sq:
                    best_point = closest
                    best_dist_sq = dist_sq

        if best_dist_sq < self.snap_threshold ** 2:
            return best_point, "wall_centerline"
        return (x, y), "none"

    def snap_to_face_flush(self, x, y, base_x, base_y, walls, new_width,
                           max_extension=240.0, direction=None):
        """Snap so a new wall of ``new_width`` sits face-flush with an existing wall.

        For each straight wall parallel to the new wall's direction (or any
        wall when no direction is known yet), the new centerline is offset so
        one of its faces is coplanar with a face of the existing wall, either
        overlapping on the same side ("flush") or touching alongside ("abut").

        ``direction`` (unit vector) overrides the base->cursor direction; use it
        when the wall's orientation is already known (e.g. moving a wall).
        """
        self._face_guides = {}
        best = None
        best_d = self.snap_threshold

        if direction is None:
            bdx, bdy = x - base_x, y - base_y
            blen = math.hypot(bdx, bdy)
            if blen > self.snap_threshold * 2:
                direction = (bdx / blen, bdy / blen)

        for wall in walls:
            if getattr(wall, 'is_curved', False):
                continue
            dx = wall.end[0] - wall.start[0]
            dy = wall.end[1] - wall.start[1]
            length = math.hypot(dx, dy)
            if length < 1e-9:
                continue
            ux, uy = dx / length, dy / length
            if direction is not None:
                # Require the new wall to run (nearly) parallel to this wall.
                if abs(ux * direction[1] - uy * direction[0]) > 0.0872:
                    continue
            nx, ny = -uy, ux

            # Position of the cursor relative to this wall's frame.
            rx, ry = x - wall.start[0], y - wall.start[1]
            along = rx * ux + ry * uy
            if along < -max_extension or along > length + max_extension:
                continue
            across = rx * nx + ry * ny

            for offset, side, kind in face_flush_offsets(wall.width, new_width):
                d = abs(across - offset)
                if d < best_d:
                    best_d = d
                    px = x - (across - offset) * nx
                    py = y - (across - offset) * ny
                    face = side * wall.width / 2.0
                    g0 = (wall.start[0] + nx * face - ux * max_extension,
                          wall.start[1] + ny * face - uy * max_extension)
                    g1 = (wall.end[0] + nx * face + ux * max_extension,
                          wall.end[1] + ny * face + uy * max_extension)
                    best = ((px, py), (g0, g1, kind))

        if best is None:
            return (x, y), "none"
        point, guide = best
        self._face_guides[point] = guide
        return point, "face_flush"

    def snap_face_flush_for_edit(self, x, y, base_x, base_y, walls, width,
                                 direction=None):
        """snap_to_face_flush for editing existing walls; also publishes the
        guide in ``face_flush_guide`` (None when nothing snapped)."""
        pt, kind = self.snap_to_face_flush(
            x, y, base_x, base_y, walls, width, direction=direction)
        self.face_flush_guide = (
            self._face_guides.get(pt) if kind == "face_flush" else None)
        return pt, kind

    def snap_to_axis(self, x, y, base_x, base_y):
        if abs(x - base_x) < self.snap_threshold:
            # print(f"Snapped to vertical axis: ({base_x}, {y})")
            return (base_x, y), "axis"
        if abs(y - base_y) < self.snap_threshold:
            # print(f"Snapped to horizontal axis: ({x}, {base_y})")
            return (x, base_y), "axis"
        return (x, y), "none"

    def snap_to_alignment(self, x, y, points):
        """
        Snap to alignment with any point of interest.
        Returns the point snapped to vertical and/or horizontal alignment.
        If aligned with multiple points, prioritizes the closest alignment.
        Can snap to both axes simultaneously if aligned with 2+ different points.
        """
        vertical_snap_x = None
        vertical_dist = float('inf')
        horizontal_snap_y = None
        horizontal_dist = float('inf')

        for px, py in points:
            # Check vertical alignment (same X - point directly above/below)
            x_diff = abs(x - px)
            if x_diff < self.snap_threshold and x_diff < vertical_dist:
                vertical_snap_x = px
                vertical_dist = x_diff

            # Check horizontal alignment (same Y - point directly left/right)
            y_diff = abs(y - py)
            if y_diff < self.snap_threshold and y_diff < horizontal_dist:
                horizontal_snap_y = py
                horizontal_dist = y_diff

        # Apply both snaps if both found (intersection snap)
        if vertical_snap_x is not None and horizontal_snap_y is not None:
            return (vertical_snap_x, horizontal_snap_y), "alignment_cross"
        elif vertical_snap_x is not None:
            return (vertical_snap_x, y), "alignment_vertical"
        elif horizontal_snap_y is not None:
            return (x, horizontal_snap_y), "alignment_horizontal"

        return (x, y), "none"

    def snap_to_angle(self, x, y, base_x, base_y):
        dx, dy = x - base_x, y - base_y
        if dx == 0 and dy == 0:
            return (x, y), "none"
        current_angle = math.degrees(math.atan2(dy, dx)) % 360
        for allowed_angle in self.allowed_angles:
            angle_diff = min(
                (current_angle - allowed_angle) %
                360, (allowed_angle - current_angle) %
                360)
            if angle_diff <= self.angle_tolerance:
                rad = math.radians(allowed_angle)
                dist = math.sqrt(dx ** 2 + dy ** 2)
                snapped = (
                    base_x + dist * math.cos(rad),
                    base_y + dist * math.sin(rad))
                # print(f"Snapped to angle {allowed_angle}°: {snapped}")
                return snapped, "angle"
        return (x, y), "none"

    def snap_to_perpendicular(self, x, y, base_x, base_y, last_wall=None):
        if not (
                self.config and self.config.ENABLE_PERPENDICULAR_SNAPPING and last_wall):
            return (x, y), "none"
        dx = last_wall.end[0] - last_wall.start[0]
        dy = last_wall.end[1] - last_wall.start[1]
        if dx == 0 and dy == 0:
            return (x, y), "none"
        angle = math.degrees(math.atan2(dy, dx)) % 360
        perp_angle = (angle + 90) % 360
        rad = math.radians(perp_angle)
        dist = math.sqrt((x - base_x) ** 2 + (y - base_y) ** 2)
        perp_x = base_x + dist * math.cos(rad)
        perp_y = base_y + dist * math.sin(rad)
        if math.sqrt((x - perp_x) ** 2 + (y - perp_y)
                     ** 2) < self.snap_threshold:
            # print(f"Snapped to perpendicular: ({perp_x}, {perp_y})")
            return (perp_x, perp_y), "perpendicular"
        return (x, y), "none"

    def find_intersections(self, walls):
        intersections = []
        for i, wall1 in enumerate(walls):
            for wall2 in walls[i + 1:]:
                intersect = self.line_intersection(
                    wall1.start, wall1.end, wall2.start, wall2.end)
                if intersect:
                    intersections.append(intersect)
        # print(f"Intersections found: {intersections}")
        return intersections

    def line_intersection(self, p1, p2, p3, p4):
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        x4, y4 = p4
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if denom == 0:
            return None
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
        if 0 <= t <= 1 and 0 <= u <= 1:
            x = x1 + t * (x2 - x1)
            y = y1 + t * (y2 - y1)
            return (x, y)
        return None

    def snap_to_grid(self, x, y, grid_spacing, canvas_width, zoom):
        if canvas_width <= 0 or zoom <= 0:
            return (x, y), "none"
        grid_spacing_pixels = grid_spacing / (60.0 / canvas_width) * zoom
        if grid_spacing_pixels == 0:
            return (x, y), "none"
        snapped_x = round(x / grid_spacing_pixels) * grid_spacing_pixels
        snapped_y = round(y / grid_spacing_pixels) * grid_spacing_pixels
        if math.sqrt((x - snapped_x) ** 2 + (y - snapped_y)
                     ** 2) < self.snap_threshold:
            # print(f"Snapped to grid: ({snapped_x}, {snapped_y})")
            return (snapped_x, snapped_y), "grid"
        return (x, y), "none"

    def snap_to_distance(self, x, y, base_x, base_y,
                         distance_increment=1 / 12):
        dx = x - base_x
        dy = y - base_y
        current_dist = math.sqrt(dx ** 2 + dy ** 2)
        target_dist = round(
            current_dist / distance_increment) * distance_increment
        if abs(current_dist - target_dist) < self.snap_threshold:
            angle = math.atan2(dy, dx)
            snapped = (
                base_x +
                target_dist *
                math.cos(angle),
                base_y +
                target_dist *
                math.sin(angle))
            # print(f"Snapped to distance {target_dist}: {snapped}")
            return snapped, "distance"
        return (x, y), "none"

    def snap_to_tangent(self, x, y, curve_center, radius):
        if not (self.config and self.config.ALLOW_CURVED_WALLS):
            return (x, y), "none"
        dx = x - curve_center[0]
        dy = y - curve_center[1]
        dist = math.sqrt(dx ** 2 + dy ** 2)
        if abs(dist - radius) < self.snap_threshold:
            angle = math.atan2(dy, dx)
            snapped = (
                curve_center[0] +
                radius *
                math.cos(angle),
                curve_center[1] +
                radius *
                math.sin(angle))
            # print(f"Snapped to tangent: {snapped}")
            return snapped, "tangent"
        return (x, y), "none"

    def snap_point(
            self,
            x,
            y,
            base_x,
            base_y,
            walls,
            rooms,
            current_wall=None,
            in_progress_points=None,
            last_wall=None,
            canvas_width=1024,
            zoom=1.0,
            polylines=None,
            new_wall_width=None,
            wall_direction=None):
        self.face_flush_guide = None
        if not self.snap_enabled:
            print("Snapping disabled")
            return (x, y), "none"

        # print(f"Snapping point ({x}, {y}) from base ({base_x}, {base_y}), zoom: {zoom}, canvas_width: {canvas_width}")
        points = self.collect_points_of_interest(
            walls, rooms, current_wall, in_progress_points, polylines)
        candidates = [
            self.snap_to_points(x, y, points, walls),  # Endpoint/midpoint
            self.snap_to_wall_centerline(x, y, walls),  # Snap to wall centerline
            (self.snap_to_face_flush(x, y, base_x, base_y, walls, new_wall_width,
                                     direction=wall_direction)
             if new_wall_width else self.snap_to_wall_edge(x, y, walls)),
            self.snap_to_wall_edge(x, y, walls),  # Wall outer/inner face edge
            # Multi-direction alignment with any point
            self.snap_to_alignment(x, y, points),
            self.snap_to_angle(x, y, base_x, base_y),    # Angle
            self.snap_to_axis(x, y, base_x, base_y),
            self.snap_to_perpendicular(x, y, base_x, base_y, last_wall),
            self.snap_to_grid(
                x,
                y,
                self.config.GRID_SPACING if self.config else 20,
                canvas_width,
                zoom),
            self.snap_to_distance(x, y, base_x, base_y),
            self.snap_to_tangent(x, y, (base_x, base_y), 50)
        ]

        # Define priority: lower number means higher priority.
        priority_map = self.SNAP_PRIORITY
        valid_candidates = []
        for (snap_candidate, snap_type) in candidates:
            dist = math.sqrt(
                (x - snap_candidate[0])**2 + (y - snap_candidate[1])**2)
            # print(f"Candidate: ({snap_candidate[0]}, {snap_candidate[1]}), type: {snap_type}, distance: {dist}")
            if dist <= self.snap_threshold and snap_type != "none":
                valid_candidates.append(
                    (snap_candidate,
                     snap_type,
                     dist,
                     priority_map.get(
                         snap_type,
                         100)))

        if valid_candidates:
            # sort by priority then distance
            valid_candidates.sort(key=lambda item: (item[3], item[2]))
            best_candidate, best_type, best_dist, _ = valid_candidates[0]
        else:
            best_candidate, best_type = (x, y), "none"

        if best_type == "face_flush":
            self.face_flush_guide = self._face_guides.get(best_candidate)

        # print(f"Final snap: {best_candidate}, type: {best_type}")
        return best_candidate, best_type
