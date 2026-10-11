"""
stair_rail_geometry.py

Pure mathematical geometry module for stair railings in EstiSketch.
Calculates:
- 2D railing paths in stair-local and world coordinates
- Rail paths for all stair types: straight, L-shaped, U-shaped (switchback), winders, spiral
- Respects has_left_rail, has_right_rail, rail_height, and turn_direction
- Exact 3D sloped linear footage for material takeoff and supplier quoting
"""

import math
from typing import Dict, List, Tuple, Any
from ..components import Stair
from .winder_geometry import l_stair_layout


def stair_rail_paths(stair: Stair) -> Dict[str, List[List[Tuple[float, float]]]]:
    """
    Compute stair railing polylines in stair-local coordinates.
    Returns:
      {
        "left": [ [(x1, y1), (x2, y2), ...], ... ],
        "right": [ [(x1, y1), (x2, y2), ...], ... ]
      }
    """
    stair_type = getattr(stair, 'stair_type', 'straight')
    width = float(getattr(stair, 'width', 36.0) or 36.0)
    half_width = width / 2.0

    left_paths: List[List[Tuple[float, float]]] = []
    right_paths: List[List[Tuple[float, float]]] = []

    # 1. Straight Stair
    if stair_type == 'straight':
        run = float(getattr(stair, 'total_run', 143.0) or 143.0)
        # Person walking up from x=0 to x=run:
        # Screen Y points down: left hand is -half_width, right hand is +half_width
        left_paths.append([(0.0, -half_width), (run, -half_width)])
        right_paths.append([(0.0, half_width), (run, half_width)])

    # 2. L-Shaped Stair (with landing or winders)
    elif stair_type == 'L-shaped':
        total_steps = int(getattr(stair, 'num_steps', 14) or 14)
        tread_depth = float(getattr(stair, 'tread_depth', 11.0) or 11.0)
        landing_depth = float(getattr(stair, 'landing_depth', 36.0) or 36.0)
        winder_count = int(getattr(stair, 'winder_count', 0) or 0)
        turn_dir = getattr(stair, 'turn_direction', 'left')

        layout = l_stair_layout(
            total_steps,
            getattr(stair, 'steps_before_landing', 0),
            tread_depth,
            landing_depth,
            width,
            winder_count
        )
        run_before = layout["run_before"]
        run_after = layout["run_after"]
        actual_landing = layout["landing_depth"]

        if turn_dir == 'left':
            # Turn in -Y direction:
            # Right hand is on the outer wall / outside corner
            # Left hand is on the inner pivot
            outer_rail = [
                (0.0, half_width),
                (run_before + actual_landing, half_width),
                (run_before + actual_landing, -half_width - run_after)
            ]
            inner_rail = [
                (0.0, -half_width),
                (run_before, -half_width),
                (run_before, -half_width - run_after)
            ]
            right_paths.append(outer_rail)
            left_paths.append(inner_rail)
        else:
            # Turn in +Y direction:
            # Left hand is on the outer wall / outside corner
            # Right hand is on the inner pivot
            outer_rail = [
                (0.0, -half_width),
                (run_before + actual_landing, -half_width),
                (run_before + actual_landing, half_width + run_after)
            ]
            inner_rail = [
                (0.0, half_width),
                (run_before, half_width),
                (run_before, half_width + run_after)
            ]
            left_paths.append(outer_rail)
            right_paths.append(inner_rail)

    # 3. U-Shaped Stair (Switchback)
    elif stair_type == 'U-shaped':
        landing_depth = float(getattr(stair, 'landing_depth', 36.0) or 36.0)
        turn_dir = getattr(stair, 'turn_direction', 'left')
        well_width = float(getattr(stair, 'inner_radius', 0.0) or 0.0)
        total_steps = int(getattr(stair, 'num_steps', 14) or 14)
        tread_depth = float(getattr(stair, 'tread_depth', 11.0) or 11.0)

        steps_before = getattr(stair, 'steps_before_landing', 0)
        if not (0 < steps_before < total_steps):
            steps_before = total_steps // 2
        steps_after = total_steps - steps_before

        run_before = (steps_before - 1) * tread_depth if steps_before > 0 else 0.0
        run_after = (steps_after - 1) * tread_depth if steps_after > 0 else 0.0

        if turn_dir == 'left':
            outer_y2 = -width - well_width - half_width
            inner_y2 = -half_width - well_width
            outer_rail = [
                (0.0, half_width),
                (run_before + landing_depth, half_width),
                (run_before + landing_depth, outer_y2),
                (run_before - run_after, outer_y2)
            ]
            inner_rail = [
                (0.0, -half_width),
                (run_before, -half_width),
                (run_before, inner_y2),
                (run_before - run_after, inner_y2)
            ]
            right_paths.append(outer_rail)
            left_paths.append(inner_rail)
        else:
            outer_y2 = width + well_width + half_width
            inner_y2 = half_width + well_width
            outer_rail = [
                (0.0, -half_width),
                (run_before + landing_depth, -half_width),
                (run_before + landing_depth, outer_y2),
                (run_before - run_after, outer_y2)
            ]
            inner_rail = [
                (0.0, half_width),
                (run_before, half_width),
                (run_before, inner_y2),
                (run_before - run_after, inner_y2)
            ]
            left_paths.append(outer_rail)
            right_paths.append(inner_rail)

    # 4. Spiral Stair
    elif stair_type == 'spiral':
        inner_r = float(getattr(stair, 'inner_radius', 6.0) or 6.0)
        outer_r = inner_r + width
        rot_deg = float(getattr(stair, 'rotation_degrees', 270.0) or 270.0)
        rot_rad = math.radians(rot_deg)
        turn_dir = getattr(stair, 'turn_direction', 'left')
        dir_mult = -1.0 if turn_dir == 'left' else 1.0
        start_angle = float(getattr(stair, 'direction_angle', 0.0) or 0.0)

        num_pts = max(16, int(rot_deg / 10.0))
        inner_arc: List[Tuple[float, float]] = []
        outer_arc: List[Tuple[float, float]] = []

        for i in range(num_pts + 1):
            theta = start_angle + (i / num_pts) * rot_rad * dir_mult
            inner_arc.append((inner_r * math.cos(theta), inner_r * math.sin(theta)))
            outer_arc.append((outer_r * math.cos(theta), outer_r * math.sin(theta)))

        if turn_dir == 'left':
            left_paths.append(inner_arc)
            right_paths.append(outer_arc)
        else:
            left_paths.append(outer_arc)
            right_paths.append(inner_arc)

    return {
        "left": left_paths,
        "right": right_paths
    }


def stair_rail_world_paths(stair: Stair) -> Dict[str, List[List[Tuple[float, float]]]]:
    """
    Get stair railing polylines transformed into canvas world coordinates.
    """
    local = stair_rail_paths(stair)
    start_x, start_y = stair.start_point
    stair_type = getattr(stair, 'stair_type', 'straight')

    if stair_type == 'spiral':
        # Local paths for spiral already include start_angle relative to center
        def transform_spiral(pt: Tuple[float, float]) -> Tuple[float, float]:
            return (start_x + pt[0], start_y + pt[1])

        return {
            "left": [[transform_spiral(p) for p in poly] for poly in local["left"]],
            "right": [[transform_spiral(p) for p in poly] for poly in local["right"]]
        }

    angle = float(getattr(stair, 'direction_angle', 0.0) or 0.0)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)

    def transform_pt(pt: Tuple[float, float]) -> Tuple[float, float]:
        lx, ly = pt
        return (
            start_x + lx * cos_a - ly * sin_a,
            start_y + lx * sin_a + ly * cos_a
        )

    return {
        "left": [[transform_pt(p) for p in poly] for poly in local["left"]],
        "right": [[transform_pt(p) for p in poly] for poly in local["right"]]
    }


def stair_rail_length_3d(stair: Stair) -> Dict[str, float]:
    """
    Calculate 3D slope length of each railing side in inches.
    Returns:
      {"left": inches, "right": inches, "total": inches}
    """
    stair_type = getattr(stair, 'stair_type', 'straight')
    width = float(getattr(stair, 'width', 36.0) or 36.0)
    total_rise = float(getattr(stair, 'total_rise', 106.0) or 106.0)
    total_steps = int(getattr(stair, 'num_steps', 14) or 14)
    tread_depth = float(getattr(stair, 'tread_depth', 11.0) or 11.0)

    has_left = bool(getattr(stair, 'has_left_rail', True))
    has_right = bool(getattr(stair, 'has_right_rail', True))

    l_in = 0.0
    r_in = 0.0

    if stair_type == 'straight':
        run = float(getattr(stair, 'total_run', 143.0) or 143.0)
        slope_len = math.hypot(run, total_rise)
        if has_left:
            l_in = slope_len
        if has_right:
            r_in = slope_len

    elif stair_type == 'L-shaped':
        landing_depth = float(getattr(stair, 'landing_depth', 36.0) or 36.0)
        winder_count = int(getattr(stair, 'winder_count', 0) or 0)
        turn_dir = getattr(stair, 'turn_direction', 'left')

        layout = l_stair_layout(
            total_steps,
            getattr(stair, 'steps_before_landing', 0),
            tread_depth,
            landing_depth,
            width,
            winder_count
        )
        steps_before = layout["steps_before"]
        steps_after = layout["steps_after"]
        run_before = layout["run_before"]
        run_after = layout["run_after"]
        actual_landing = layout["landing_depth"]

        rise1 = total_rise * (steps_before / total_steps) if total_steps else 0.0
        rise2 = total_rise - rise1
        slope1 = math.hypot(run_before, rise1)
        slope2 = math.hypot(run_after, rise2)

        outer_len = slope1 + actual_landing + slope2
        inner_len = slope1 + slope2

        if turn_dir == 'left':
            if has_left:
                l_in = inner_len
            if has_right:
                r_in = outer_len
        else:
            if has_left:
                l_in = outer_len
            if has_right:
                r_in = inner_len

    elif stair_type == 'U-shaped':
        landing_depth = float(getattr(stair, 'landing_depth', 36.0) or 36.0)
        well_width = float(getattr(stair, 'inner_radius', 0.0) or 0.0)
        turn_dir = getattr(stair, 'turn_direction', 'left')

        steps_before = getattr(stair, 'steps_before_landing', 0)
        if not (0 < steps_before < total_steps):
            steps_before = total_steps // 2
        steps_after = total_steps - steps_before

        run_before = (steps_before - 1) * tread_depth if steps_before > 0 else 0.0
        run_after = (steps_after - 1) * tread_depth if steps_after > 0 else 0.0
        landing_span = 2 * width + well_width

        rise1 = total_rise * (steps_before / total_steps) if total_steps else 0.0
        rise2 = total_rise - rise1
        slope1 = math.hypot(run_before, rise1)
        slope2 = math.hypot(run_after, rise2)

        outer_len = slope1 + landing_span + slope2
        inner_len = slope1 + well_width + slope2

        if turn_dir == 'left':
            if has_left:
                l_in = inner_len
            if has_right:
                r_in = outer_len
        else:
            if has_left:
                l_in = outer_len
            if has_right:
                r_in = inner_len

    elif stair_type == 'spiral':
        inner_r = float(getattr(stair, 'inner_radius', 6.0) or 6.0)
        outer_r = inner_r + width
        rot_deg = float(getattr(stair, 'rotation_degrees', 270.0) or 270.0)
        rot_rad = math.radians(rot_deg)
        turn_dir = getattr(stair, 'turn_direction', 'left')

        outer_arc = outer_r * rot_rad
        inner_arc = inner_r * rot_rad

        outer_slope = math.hypot(outer_arc, total_rise)
        inner_slope = math.hypot(inner_arc, total_rise)

        if turn_dir == 'left':
            if has_left:
                l_in = inner_slope
            if has_right:
                r_in = outer_slope
        else:
            if has_left:
                l_in = outer_slope
            if has_right:
                r_in = inner_slope

    return {
        "left": l_in,
        "right": r_in,
        "total": l_in + r_in
    }


def stair_railing_linear_ft(stair: Stair) -> float:
    """
    Calculate total railing linear feet for a staircase.
    """
    lengths = stair_rail_length_3d(stair)
    return lengths["total"] / 12.0
