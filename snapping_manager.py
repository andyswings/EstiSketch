import math
import re
from components import Wall

class SnappingManager:
    def __init__(self, snap_enabled=True, snap_threshold=10):
        self.snap_enabled = snap_enabled
        self.snap_threshold = snap_threshold
        self.allowed_angles = [0, 45, 90, 135, 180, 225, 270, 315]

    def collect_endpoints(self, walls, rooms, in_progress_points=None):
        endpoints = []
        for wall in walls:
            endpoints.extend([wall.start, wall.end])
        for room in rooms:
            endpoints.extend(room)
        if in_progress_points:
            endpoints.extend(in_progress_points)
        return endpoints

    def snap_to_endpoints(self, x, y, endpoints):
        best_candidate = (x, y)
        best_dist_sq = self.snap_threshold ** 2
        for ex, ey in endpoints:
            d_sq = (x - ex) ** 2 + (y - ey) ** 2
            if d_sq < best_dist_sq:
                best_candidate = (ex, ey)
                best_dist_sq = d_sq
        return best_candidate

    def snap_to_axis(self, x, y, base_x, base_y):
        if abs(x - base_x) < self.snap_threshold:
            x = base_x
        if abs(y - base_y) < self.snap_threshold:
            y = base_y
        return x, y

    def snap_to_angle(self, x, y, base_x, base_y):
        dx, dy = x - base_x, y - base_y
        if dx == 0 and dy == 0:
            return x, y
        current_angle = math.degrees(math.atan2(dy, dx))
        closest_angle = min(self.allowed_angles, key=lambda angle: abs(current_angle - angle))
        rad = math.radians(closest_angle)
        dist = math.sqrt(dx ** 2 + dy ** 2)
        return base_x + dist * math.cos(rad), base_y + dist * math.sin(rad)

    def snap_point(self, x, y, base_x, base_y, walls, rooms, in_progress_points=None):
        if not self.snap_enabled:
            return x, y
        endpoints = self.collect_endpoints(walls, rooms, in_progress_points)
        x, y = self.snap_to_endpoints(x, y, endpoints)
        x, y = self.snap_to_axis(x, y, base_x, base_y)
        x, y = self.snap_to_angle(x, y, base_x, base_y)
        return x, y


