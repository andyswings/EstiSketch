"""Pure-Cairo architectural north arrow / compass rose renderer."""
from __future__ import annotations

import math

import cairo


def draw_north_arrow(
    cr: cairo.Context,
    cx: float,
    cy: float,
    radius: float,
    angle_deg: float,
    show_degree_label: bool = False,
    highlight: bool = False,
    monochrome: bool = False,
) -> None:
    """Draw a north arrow / compass rose centered at ``(cx, cy)``.

    ``angle_deg`` is the azimuth in degrees clockwise from straight up
    (0 = up, 90 = right, 180 = down, 270 = left).
    """
    if radius <= 0:
        return

    norm_deg = float(angle_deg) % 360.0
    rad = math.radians(norm_deg)

    cr.save()

    if monochrome:
        stroke_rgb = (0.0, 0.0, 0.0)
        fill_dark = (0.0, 0.0, 0.0)
        tick_rgb = (0.3, 0.3, 0.3)
    elif highlight:
        stroke_rgb = (0.2, 0.5, 0.9)
        fill_dark = (0.12, 0.35, 0.72)
        tick_rgb = (0.2, 0.5, 0.9)
    else:
        stroke_rgb = (0.22, 0.27, 0.34)
        fill_dark = (0.15, 0.19, 0.25)
        tick_rgb = (0.45, 0.50, 0.58)

    # Backdrop disk for legibility over canvas grid/lines
    if not monochrome:
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.88)
        cr.fill()

    # Outer ring
    cr.arc(cx, cy, radius, 0, 2 * math.pi)
    cr.set_source_rgb(*stroke_rgb)
    cr.set_line_width(max(0.75, radius * (0.055 if highlight else 0.04)))
    cr.stroke()

    # Cardinal ticks rotated with azimuth
    cr.save()
    cr.translate(cx, cy)
    cr.rotate(rad)

    cr.set_source_rgb(*tick_rgb)
    cr.set_line_width(max(0.5, radius * 0.035))
    for i in range(4):
        cr.save()
        cr.rotate(i * math.pi / 2.0)
        cr.move_to(0.0, -radius * 0.96)
        cr.line_to(0.0, -radius * 0.82)
        cr.stroke()
        cr.restore()

    # Split architectural compass needle (pointing along -Y in rotated frame)
    tip_y = -radius * 0.50
    wing_x = radius * 0.25
    wing_y = radius * 0.42
    notch_y = radius * 0.20

    # Right half (dark filled)
    cr.move_to(0.0, tip_y)
    cr.line_to(wing_x, wing_y)
    cr.line_to(0.0, notch_y)
    cr.close_path()
    cr.set_source_rgb(*fill_dark)
    cr.fill_preserve()
    cr.set_source_rgb(*stroke_rgb)
    cr.set_line_width(max(0.6, radius * 0.035))
    cr.stroke()

    # Left half (white filled with dark outline)
    cr.move_to(0.0, tip_y)
    cr.line_to(0.0, notch_y)
    cr.line_to(-wing_x, wing_y)
    cr.close_path()
    cr.set_source_rgb(1.0, 1.0, 1.0)
    cr.fill_preserve()
    cr.set_source_rgb(*stroke_rgb)
    cr.set_line_width(max(0.6, radius * 0.035))
    cr.stroke()

    cr.restore()

    # Upright "N" placed inside the ring along the North direction
    nx = cx + math.sin(rad) * radius * 0.74
    ny = cy - math.cos(rad) * radius * 0.74
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(max(5.5, radius * 0.34))
    ext = cr.text_extents("N")
    cr.set_source_rgb(*fill_dark)
    cr.move_to(nx - (ext.x_bearing + ext.width / 2.0), ny - (ext.y_bearing + ext.height / 2.0))
    cr.show_text("N")

    if show_degree_label:
        deg_text = f"{int(round(norm_deg)) % 360}°"
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(max(8.0, radius * 0.36))
        dext = cr.text_extents(deg_text)
        lx = cx - (dext.x_bearing + dext.width / 2.0)
        ly = cy + radius + 12.0
        # Subtle pill background for readability
        pad_x, pad_y = 4.0, 2.0
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.85)
        cr.rectangle(
            cx - dext.width / 2.0 - pad_x,
            ly + dext.y_bearing - pad_y,
            dext.width + 2 * pad_x,
            dext.height + 2 * pad_y,
        )
        cr.fill()
        cr.set_source_rgb(*stroke_rgb)
        cr.move_to(lx, ly)
        cr.show_text(deg_text)

    cr.restore()
