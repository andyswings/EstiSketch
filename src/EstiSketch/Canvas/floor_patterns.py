"""Pure-Cairo procedural vector floor pattern renderer (no GTK dependency)."""
from __future__ import annotations

import math
from typing import Iterable, List, Optional, Tuple

import cairo

FLOOR_PATTERNS: List[Tuple[str, str]] = [
    ("none", "None (Solid)"),
    ("wood_plank", "Wood Plank"),
    ("vinyl_plank", "LVP / Laminate Plank"),
    ("herringbone", "Herringbone"),
    ("chevron", "Chevron Wood"),
    ("tile_12", 'Tile Grid (12")'),
    ("tile_18", 'Tile Grid (18")'),
    ("tile_24", 'Tile Grid (24")'),
    ("tile_offset_half", 'Tile 1/2 Offset (12"x24")'),
    ("tile_offset_third", 'Tile 1/3 Offset (12"x24")'),
    ("tile_hex", "Hexagon Tile"),
    ("tile_basketweave", "Basketweave Tile"),
    ("carpet_stipple", "Carpet (Plush)"),
    ("carpet_weave", "Carpet (Berber Weave)"),
    ("concrete_stipple", "Concrete Stipple"),
]

_VALID_PATTERNS = {pid for pid, _ in FLOOR_PATTERNS}

_BASE_COLORS = {
    "wood_plank": (0.95, 0.90, 0.82),
    "vinyl_plank": (0.92, 0.90, 0.87),
    "herringbone": (0.94, 0.89, 0.80),
    "chevron": (0.94, 0.89, 0.80),
    "tile_12": (0.95, 0.95, 0.93),
    "tile_18": (0.95, 0.95, 0.93),
    "tile_24": (0.95, 0.95, 0.93),
    "tile_offset_half": (0.95, 0.95, 0.93),
    "tile_offset_third": (0.95, 0.95, 0.93),
    "tile_hex": (0.95, 0.95, 0.93),
    "tile_basketweave": (0.95, 0.95, 0.93),
    "carpet_stipple": (0.94, 0.92, 0.88),
    "carpet_weave": (0.93, 0.91, 0.86),
    "concrete_stipple": (0.86, 0.86, 0.85),
}

_MAX_STEPS = 400


def pattern_base_color(pattern: str, is_slab: bool) -> Tuple[float, float, float]:
    """Return the background fill RGB color for a room given its pattern and slab flag."""
    if pattern and pattern != "none" and pattern in _BASE_COLORS:
        return _BASE_COLORS[pattern]
    return (0.85, 0.85, 0.85) if is_slab else (0.9, 0.9, 1.0)


def _safe_step(span: float, step: float, max_steps: int = _MAX_STEPS) -> float:
    """Keep iteration count bounded for giant polygons."""
    if step <= 0:
        return span
    if span / step > max_steps:
        return span / max_steps
    return step


def _draw_offset_tile(
    cr: cairo.Context,
    r: float,
    tile_w: float,
    tile_l: float,
    offset_denom: int,
    zoom_transform: float,
    stroke_rgba: Tuple[float, float, float, float],
    line_width_override: Optional[float] = None,
) -> None:
    """Draw running-bond / offset rectangular courses with staggered cross joints."""
    course_h = _safe_step(2.0 * r, tile_w)
    course_l = _safe_step(2.0 * r, max(course_h * 1.5, tile_l))
    cr.set_source_rgba(*stroke_rgba)
    lw = line_width_override if line_width_override is not None else 0.6 / max(zoom_transform, 1e-3)
    cr.set_line_width(lw)

    y_start = math.floor(-r / course_h) * course_h
    y = y_start
    row_idx = round(y_start / course_h)
    while y <= r + 1e-6:
        cr.move_to(-r, y)
        cr.line_to(r, y)
        offset = (row_idx % offset_denom) * (course_l / offset_denom)
        x = math.floor((-r - offset) / course_l) * course_l + offset
        y_next = y + course_h
        while x <= r + 1e-6:
            if -r <= x <= r:
                cr.move_to(x, y)
                cr.line_to(x, y_next)
            x += course_l
        y += course_h
        row_idx += 1
    cr.stroke()


def _draw_tile_grid(
    cr: cairo.Context,
    r: float,
    pitch: float,
    zoom_transform: float,
    opacity: float,
    line_width_override: Optional[float] = None,
) -> None:
    step = _safe_step(2.0 * r, pitch)
    cr.set_source_rgba(0.45, 0.45, 0.48, opacity * 0.45)
    lw = line_width_override if line_width_override is not None else 0.6 / max(zoom_transform, 1e-3)
    cr.set_line_width(lw)

    v = math.floor(-r / step) * step
    while v <= r + 1e-6:
        cr.move_to(v, -r)
        cr.line_to(v, r)
        cr.move_to(-r, v)
        cr.line_to(r, v)
        v += step
    cr.stroke()


def _draw_herringbone(
    cr: cairo.Context,
    r: float,
    s: float,
    zoom_transform: float,
    opacity: float,
    line_width_override: Optional[float] = None,
) -> None:
    k = 4
    w = _safe_step(2.0 * r, 4.0 * s)
    # Extra -45 deg rotation gives classic vertical chevron columns
    cr.rotate(-math.pi / 4.0)
    cr.set_source_rgba(0.55, 0.42, 0.28, opacity * 0.45)
    lw = line_width_override if line_width_override is not None else 0.6 / max(zoom_transform, 1e-3)
    cr.set_line_width(lw)

    limit_t = math.ceil(r / w) + k + 2
    limit_m = math.ceil(r / (k * w)) + 2
    if (2 * limit_t + 1) * (2 * limit_m + 1) > 16000:
        scale_up = math.sqrt(((2 * limit_t + 1) * (2 * limit_m + 1)) / 16000.0)
        w *= scale_up
        limit_t = math.ceil(r / w) + k + 2
        limit_m = math.ceil(r / (k * w)) + 2

    reach = r + k * w
    for t in range(-limit_t, limit_t + 1):
        for m in range(-limit_m, limit_m + 1):
            hx = (t + m * k) * w
            hy = (t - m * k) * w
            if -reach <= hx <= reach and -reach <= hy <= reach:
                cr.rectangle(hx, hy, k * w, w)
            vx = hx
            vy = (t - m * k + 1) * w
            if -reach <= vx <= reach and -reach <= vy <= reach:
                cr.rectangle(vx, vy, w, k * w)
    cr.stroke()


def _draw_chevron(
    cr: cairo.Context,
    r: float,
    s: float,
    zoom_transform: float,
    opacity: float,
    line_width_override: Optional[float] = None,
) -> None:
    col_w = _safe_step(2.0 * r, 12.0 * s, max_steps=160)
    dy = _safe_step(2.0 * r, 4.0 * s, max_steps=200)
    cr.set_source_rgba(0.55, 0.42, 0.28, opacity * 0.45)
    lw = line_width_override if line_width_override is not None else 0.6 / max(zoom_transform, 1e-3)
    cr.set_line_width(lw)

    c_min = math.floor(-r / col_w)
    c_max = math.ceil(r / col_w)
    y_min = math.floor((-r - col_w) / dy) * dy
    y_max = r + col_w

    for col in range(c_min, c_max + 1):
        x0 = col * col_w
        x1 = x0 + col_w
        cr.move_to(x0, -r)
        cr.line_to(x0, r)
        even = (col % 2 == 0)
        y = y_min
        while y <= y_max + 1e-6:
            if even:
                cr.move_to(x0, y)
                cr.line_to(x1, y + col_w)
            else:
                cr.move_to(x0, y + col_w)
                cr.line_to(x1, y)
            y += dy
    cr.stroke()


def _draw_hex_tile(
    cr: cairo.Context,
    r: float,
    s: float,
    zoom_transform: float,
    opacity: float,
    line_width_override: Optional[float] = None,
) -> None:
    a = _safe_step(2.0 * r, 3.5 * s, max_steps=140)
    dx = 1.5 * a
    dy = math.sqrt(3.0) * a
    half_dy = dy * 0.5
    if (2.0 * r / dx) * (2.0 * r / dy) > 12000:
        scale_up = math.sqrt(((2.0 * r / dx) * (2.0 * r / dy)) / 12000.0)
        a *= scale_up
        dx = 1.5 * a
        dy = math.sqrt(3.0) * a
        half_dy = dy * 0.5

    cr.set_source_rgba(0.45, 0.45, 0.48, opacity * 0.45)
    lw = line_width_override if line_width_override is not None else 0.6 / max(zoom_transform, 1e-3)
    cr.set_line_width(lw)

    c_min = math.floor((-r - 2.0 * a) / dx)
    c_max = math.ceil((r + 2.0 * a) / dx)
    r_min = math.floor((-r - 2.0 * a) / dy)
    r_max = math.ceil((r + 2.0 * a) / dy)

    for col in range(c_min, c_max + 1):
        cx = col * dx
        y_off = half_dy if (col & 1) else 0.0
        for row in range(r_min, r_max + 1):
            cy = row * dy + y_off
            cr.move_to(cx + a, cy)
            cr.line_to(cx + 0.5 * a, cy + half_dy)
            cr.line_to(cx - 0.5 * a, cy + half_dy)
            cr.line_to(cx - a, cy)
    cr.stroke()


def _draw_basketweave(
    cr: cairo.Context,
    r: float,
    s: float,
    zoom_transform: float,
    opacity: float,
    line_width_override: Optional[float] = None,
) -> None:
    block = _safe_step(2.0 * r, 12.0 * s, max_steps=140)
    cr.set_source_rgba(0.45, 0.45, 0.48, opacity * 0.45)
    lw = line_width_override if line_width_override is not None else 0.6 / max(zoom_transform, 1e-3)
    cr.set_line_width(lw)

    v = math.floor(-r / block) * block
    while v <= r + 1e-6:
        cr.move_to(v, -r)
        cr.line_to(v, r)
        cr.move_to(-r, v)
        cr.line_to(r, v)
        v += block

    i_min = math.floor(-r / block)
    i_max = math.ceil(r / block)
    for ix in range(i_min, i_max + 1):
        x0 = ix * block
        for iy in range(i_min, i_max + 1):
            y0 = iy * block
            if (ix + iy) % 2 == 0:
                cr.move_to(x0, y0 + 0.5 * block)
                cr.line_to(x0 + block, y0 + 0.5 * block)
            else:
                cr.move_to(x0 + 0.5 * block, y0)
                cr.line_to(x0 + 0.5 * block, y0 + block)
    cr.stroke()


def _draw_stipple_cells(
    cr: cairo.Context,
    r: float,
    cell_base: float,
    dot_radius: float,
    dots_per_cell: int,
    rgba: Tuple[float, float, float, float],
) -> None:
    cell = _safe_step(2.0 * r, cell_base, max_steps=140)
    cr.set_source_rgba(*rgba)
    ix_min = math.floor(-r / cell)
    ix_max = math.ceil(r / cell)
    seeds = (
        (73856093, 19349663),
        (83492791, 2971215073),
        (49979687, 67867967),
    )
    for ix in range(ix_min, ix_max + 1):
        for iy in range(ix_min, ix_max + 1):
            for k in range(dots_per_cell):
                sx, sy = seeds[k]
                h = ((ix * sx) ^ (iy * sy)) & 0xFFFFFFFF
                fx = ((h & 0xFF) / 255.0) * 0.8 + 0.1
                fy = (((h >> 8) & 0xFF) / 255.0) * 0.8 + 0.1
                cr.new_sub_path()
                cr.arc((ix + fx) * cell, (iy + fy) * cell, dot_radius, 0, 2 * math.pi)
    cr.fill()


def _draw_carpet_weave(
    cr: cairo.Context,
    r: float,
    s: float,
    zoom_transform: float,
    opacity: float,
    line_width_override: Optional[float] = None,
) -> None:
    row_step = _safe_step(2.0 * r, 3.0 * s, max_steps=200)
    dash_pitch = _safe_step(2.0 * r, max(row_step * 1.5, 4.5 * s), max_steps=200)
    dash_len = 0.62 * dash_pitch

    cr.set_source_rgba(0.60, 0.54, 0.46, opacity * 0.42)
    lw = line_width_override if line_width_override is not None else 0.55 / max(zoom_transform, 1e-3)
    cr.set_line_width(lw)

    y_start = math.floor(-r / row_step) * row_step
    y = y_start
    row_idx = round(y_start / row_step)
    while y <= r + 1e-6:
        offset = 0.5 * dash_pitch if (row_idx & 1) else 0.0
        x = math.floor((-r - offset) / dash_pitch) * dash_pitch + offset
        while x <= r + 1e-6:
            cr.move_to(x, y)
            cr.line_to(x + dash_len, y)
            x += dash_pitch
        y += row_step
        row_idx += 1
    cr.stroke()


def draw_floor_pattern(
    cr: cairo.Context,
    points: Iterable[Tuple[float, float]],
    pattern: str,
    rotation_deg: float = 0.0,
    scale: float = 1.0,
    zoom_transform: float = 1.0,
    opacity: float = 1.0,
    line_width_override: Optional[float] = None,
) -> None:
    """Draw a vector floor pattern over the current clipped region."""
    pts = list(points)
    if not pattern or pattern == "none" or pattern not in _VALID_PATTERNS or len(pts) < 3:
        return

    s = max(0.25, min(4.0, float(scale or 1.0)))
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    r = max(math.hypot(x - cx, y - cy) for x, y in pts)
    if r <= 1e-6:
        return

    cr.save()
    cr.translate(cx, cy)
    cr.rotate(math.radians(float(rotation_deg or 0.0)))

    if pattern == "wood_plank":
        _draw_offset_tile(cr, r, 4.0 * s, 36.0 * s, 3, zoom_transform,
                          (0.55, 0.42, 0.28, opacity * 0.45), line_width_override)
    elif pattern == "vinyl_plank":
        _draw_offset_tile(cr, r, 7.0 * s, 48.0 * s, 4, zoom_transform,
                          (0.52, 0.46, 0.40, opacity * 0.42), line_width_override)
    elif pattern == "herringbone":
        _draw_herringbone(cr, r, s, zoom_transform, opacity, line_width_override)
    elif pattern == "chevron":
        _draw_chevron(cr, r, s, zoom_transform, opacity, line_width_override)
    elif pattern == "tile_12":
        _draw_tile_grid(cr, r, 12.0 * s, zoom_transform, opacity, line_width_override)
    elif pattern == "tile_18":
        _draw_tile_grid(cr, r, 18.0 * s, zoom_transform, opacity, line_width_override)
    elif pattern == "tile_24":
        _draw_tile_grid(cr, r, 24.0 * s, zoom_transform, opacity, line_width_override)
    elif pattern == "tile_offset_half":
        _draw_offset_tile(cr, r, 12.0 * s, 24.0 * s, 2, zoom_transform,
                          (0.45, 0.45, 0.48, opacity * 0.45), line_width_override)
    elif pattern == "tile_offset_third":
        _draw_offset_tile(cr, r, 12.0 * s, 24.0 * s, 3, zoom_transform,
                          (0.45, 0.45, 0.48, opacity * 0.45), line_width_override)
    elif pattern == "tile_hex":
        _draw_hex_tile(cr, r, s, zoom_transform, opacity, line_width_override)
    elif pattern == "tile_basketweave":
        _draw_basketweave(cr, r, s, zoom_transform, opacity, line_width_override)
    elif pattern == "carpet_stipple":
        _draw_stipple_cells(cr, r, 5.0 * s, max(0.2, 0.30 * s), 3,
                            (0.62, 0.56, 0.48, opacity * 0.45))
    elif pattern == "carpet_weave":
        _draw_carpet_weave(cr, r, s, zoom_transform, opacity, line_width_override)
    elif pattern == "concrete_stipple":
        _draw_stipple_cells(cr, r, 6.0 * s, max(0.2, 0.35 * s), 2,
                            (0.38, 0.38, 0.40, opacity * 0.55))

    cr.restore()
