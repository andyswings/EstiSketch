import math

class SnappingManager:
    def __init__(self, snap_enabled=True, snap_threshold=75, config=None, zoom=1.0):
        self.snap_enabled = snap_enabled
        self.snap_threshold = snap_threshold  # This value is updated by canvas_area with zoom multiplication.
        self.config = config
        self.allowed_angles = [0, 22.5, 45, 67.5, 90, 112.5, 135, 157.5, 180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5]
        self.angle_tolerance = 10  # Increased from 5 to 10

    def collect_points_of_interest(self, walls, rooms, current_wall=None, in_progress_points=None):
        points = []
        for wall in walls:
            points.extend([wall.start, wall.end])
            mid_x = (wall.start[0] + wall.end[0]) / 2
            mid_y = (wall.start[1] + wall.end[1]) / 2
            points.append((mid_x, mid_y))
        for room in rooms:
            points.extend(room.points)
        if current_wall and current_wall.start != current_wall.end:
            points.append(current_wall.start)
        if in_progress_points:
            points.extend(in_progress_points)
        if self.config and self.config.ENABLE_CENTERLINE_SNAPPING:
            points.extend(self.find_intersections(walls))
        # print(f"Collected points: {points}")
        return points

    def snap_to_points(self, x, y, points, walls):
        best_candidate = (x, y)
        best_dist_sq = self.snap_threshold ** 2
        best_type = "none"
        for px, py in points:
            d_sq = (x - px) ** 2 + (y - py) ** 2
            # print(f"Checking point ({px}, {py}), distance squared: {d_sq}, threshold squared: {best_dist_sq}")
            if d_sq < best_dist_sq:
                best_candidate = (px, py)
                best_dist_sq = d_sq
                best_type = "endpoint" if (px, py) in [w.start for w in walls] + [w.end for w in walls] else "midpoint"
        # print(f"Best point snap: {best_candidate}, type: {best_type}")
        return best_candidate, best_type

    def snap_to_axis(self, x, y, base_x, base_y):
        if abs(x - base_x) < self.snap_threshold:
            # print(f"Snapped to vertical axis: ({base_x}, {y})")
            return (base_x, y), "axis"
        if abs(y - base_y) < self.snap_threshold:
            # print(f"Snapped to horizontal axis: ({x}, {base_y})")
            return (x, base_y), "axis"
        return (x, y), "none"

    def snap_to_angle(self, x, y, base_x, base_y):
        dx, dy = x - base_x, y - base_y
        if dx == 0 and dy == 0:
            return (x, y), "none"
        current_angle = math.degrees(math.atan2(dy, dx)) % 360
        for allowed_angle in self.allowed_angles:
            angle_diff = min((current_angle - allowed_angle) % 360, (allowed_angle - current_angle) % 360)
            if angle_diff <= self.angle_tolerance:
                rad = math.radians(allowed_angle)
                dist = math.sqrt(dx ** 2 + dy ** 2)
                snapped = (base_x + dist * math.cos(rad), base_y + dist * math.sin(rad))
                # print(f"Snapped to angle {allowed_angle}°: {snapped}")
                return snapped, "angle"
        return (x, y), "none"

    def snap_to_perpendicular(self, x, y, base_x, base_y, last_wall=None):
        if not (self.config and self.config.ENABLE_PERPENDICULAR_SNAPPING and last_wall):
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
        if math.sqrt((x - perp_x) ** 2 + (y - perp_y) ** 2) < self.snap_threshold:
            # print(f"Snapped to perpendicular: ({perp_x}, {perp_y})")
            return (perp_x, perp_y), "perpendicular"
        return (x, y), "none"

    def find_intersections(self, walls):
        intersections = []
        for i, wall1 in enumerate(walls):
            for wall2 in walls[i+1:]:
                intersect = self.line_intersection(wall1.start, wall1.end, wall2.start, wall2.end)
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
        if math.sqrt((x - snapped_x) ** 2 + (y - snapped_y) ** 2) < self.snap_threshold:
            # print(f"Snapped to grid: ({snapped_x}, {snapped_y})")
            return (snapped_x, snapped_y), "grid"
        return (x, y), "none"

    def snap_to_distance(self, x, y, base_x, base_y, distance_increment=1/12):
        dx = x - base_x
        dy = y - base_y
        current_dist = math.sqrt(dx ** 2 + dy ** 2)
        target_dist = round(current_dist / distance_increment) * distance_increment
        if abs(current_dist - target_dist) < self.snap_threshold:
            angle = math.atan2(dy, dx)
            snapped = (base_x + target_dist * math.cos(angle), base_y + target_dist * math.sin(angle))
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
            snapped = (curve_center[0] + radius * math.cos(angle), curve_center[1] + radius * math.sin(angle))
            # print(f"Snapped to tangent: {snapped}")
            return snapped, "tangent"
        return (x, y), "none"

    def snap_point(self, x, y, base_x, base_y, walls, rooms, current_wall=None, in_progress_points=None, last_wall=None, canvas_width=1024, zoom=1.0):
        if not self.snap_enabled:
            print("Snapping disabled")
            return (x, y), "none"
        
        # print(f"Snapping point ({x}, {y}) from base ({base_x}, {base_y}), zoom: {zoom}, canvas_width: {canvas_width}")
        points = self.collect_points_of_interest(walls, rooms, current_wall, in_progress_points)
        candidates = [
            self.snap_to_points(x, y, points, walls),  # Endpoint/midpoint
            self.snap_to_angle(x, y, base_x, base_y),    # Angle
            self.snap_to_axis(x, y, base_x, base_y),
            self.snap_to_perpendicular(x, y, base_x, base_y, last_wall),
            self.snap_to_grid(x, y, self.config.GRID_SPACING if self.config else 20, canvas_width, zoom),
            self.snap_to_distance(x, y, base_x, base_y),
            self.snap_to_tangent(x, y, (base_x, base_y), 50)
        ]
        
        # Define priority: lower number means higher priority.
        priority_map = {
            "endpoint": 1,
            "midpoint": 1,
            "angle": 2,
            "axis": 3,
            "perpendicular": 4,
            "grid": 5,
            "distance": 6,
            "tangent": 7,
            "none": 100
        }
        valid_candidates = []
        for (snap_candidate, snap_type) in candidates:
            dist = math.sqrt((x - snap_candidate[0])**2 + (y - snap_candidate[1])**2)
            # print(f"Candidate: ({snap_candidate[0]}, {snap_candidate[1]}), type: {snap_type}, distance: {dist}")
            if dist <= self.snap_threshold and snap_type != "none":
                valid_candidates.append((snap_candidate, snap_type, dist, priority_map.get(snap_type, 100)))
        
        if valid_candidates:
            valid_candidates.sort(key=lambda item: (item[3], item[2]))  # sort by priority then distance
            best_candidate, best_type, best_dist, _ = valid_candidates[0]
        else:
            best_candidate, best_type = (x, y), "none"
        
        # print(f"Final snap: {best_candidate}, type: {best_type}")
        return best_candidate, best_type
