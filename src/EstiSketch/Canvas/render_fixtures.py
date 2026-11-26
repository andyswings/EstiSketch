"""3-pass layered 2D AIA Cairo renderer for architectural fixtures, cabinetry, countertops, and appliances."""
import math
from typing import Optional, Tuple

import cairo

from ..fixtures_catalog import get_fixture_spec, pack_cabinet_run
from ..Printing.print_settings import resolve_stroke_width

COUNTERTOP_RGB = {
    "quartz": (0.94, 0.94, 0.93),
    "granite": (0.84, 0.85, 0.87),
    "laminate": (0.95, 0.93, 0.88),
    "butcher_block": (0.88, 0.75, 0.58),
    "marble": (0.96, 0.96, 0.97),
    "concrete": (0.79, 0.80, 0.81),
    "solid_surface": (0.96, 0.96, 0.94),
}


def _ellipse(cr: cairo.Context, cx: float, cy: float, rx: float, ry: float) -> None:
    if rx <= 1e-4 or ry <= 1e-4:
        return
    cr.save()
    cr.translate(cx, cy)
    cr.scale(rx, ry)
    cr.arc(0.0, 0.0, 1.0, 0.0, 2.0 * math.pi)
    cr.restore()


def _rounded_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    r = max(0.0, min(r, abs(w) / 2.0, abs(h) / 2.0))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2.0, 0.0)
    cr.arc(x + w - r, y + h - r, r, 0.0, math.pi / 2.0)
    cr.arc(x + r, y + h - r, r, math.pi / 2.0, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3.0 * math.pi / 2.0)
    cr.close_path()


def _corner_poly(w: float, d: float, arm: float):
    hw, hd = w / 2.0, d / 2.0
    arm = min(arm, w - 2.0, d - 2.0)
    return [
        (-hw, -hd),
        (hw, -hd),
        (hw, -hd + arm),
        (-hw + arm, -hd + arm),
        (-hw + arm, hd),
        (-hw, hd),
    ]


def _poly_path(cr: cairo.Context, pts) -> None:
    cr.move_to(pts[0][0], pts[0][1])
    for pt in pts[1:]:
        cr.line_to(pt[0], pt[1])
    cr.close_path()


def _draw_tag(cr: cairo.Context, text: str, max_w: float, cy: float = 0.0, size: float = 5.0, opacity: float = 1.0, rotation_deg: float = 0.0) -> None:
    if not text:
        return
    cr.save()
    cr.set_dash([])
    rot_norm = float(rotation_deg) % 360.0
    if 90.0 < rot_norm <= 270.0:
        cr.translate(0.0, cy)
        cr.rotate(math.pi)
        draw_cy = 0.0
    else:
        draw_cy = cy
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(size)
    ext = cr.text_extents(text)
    if ext.width > max_w * 0.85 and ext.width > 1e-6:
        size = max(2.2, size * (max_w * 0.85) / ext.width)
        cr.set_font_size(size)
        ext = cr.text_extents(text)
    cr.set_source_rgba(0.18, 0.20, 0.24, opacity * 0.9)
    cr.move_to(-(ext.width / 2.0 + ext.x_bearing), draw_cy - (ext.height / 2.0 + ext.y_bearing))
    cr.show_text(text)
    cr.restore()


def _draw_basin_and_faucet(cr: cairo.Context, cx: float, cy: float, bw: float, bd: float, lw: float, opacity: float, double_bowl: bool = False) -> None:
    cr.save()
    cr.set_line_width(lw)
    cr.set_source_rgba(0.99, 0.99, 1.0, opacity)
    if double_bowl:
        gap = max(1.5, bw * 0.06)
        each_w = (bw - gap) / 2.0
        for sign in (-1.0, 1.0):
            bx = cx + sign * (each_w / 2.0 + gap / 2.0)
            _rounded_rect(cr, bx - each_w / 2.0, cy - bd / 2.0, each_w, bd, min(2.0, bd * 0.15))
            cr.set_source_rgba(0.99, 0.99, 1.0, opacity)
            cr.fill_preserve()
            cr.set_source_rgba(0.18, 0.20, 0.24, opacity)
            cr.stroke()
            cr.arc(bx, cy, max(0.8, min(1.3, bd * 0.08)), 0.0, 2.0 * math.pi)
            cr.stroke()
    else:
        _rounded_rect(cr, cx - bw / 2.0, cy - bd / 2.0, bw, bd, min(2.2, bd * 0.18))
        cr.fill_preserve()
        cr.set_source_rgba(0.18, 0.20, 0.24, opacity)
        cr.stroke()
        cr.arc(cx, cy, max(0.9, min(1.4, bd * 0.08)), 0.0, 2.0 * math.pi)
        cr.stroke()
    # Faucet stem at back edge
    fy_back = cy - bd / 2.0 - 1.5
    cr.set_source_rgba(0.2, 0.22, 0.26, opacity)
    cr.arc(cx, fy_back, 1.1, 0.0, 2.0 * math.pi)
    cr.fill()
    cr.set_line_width(lw * 1.4)
    cr.move_to(cx, fy_back)
    cr.line_to(cx, fy_back + 3.2)
    cr.stroke()
    cr.restore()


def _base_fill_color(fixture) -> Tuple[float, float, float]:
    if getattr(fixture, "fill_color", None):
        c = fixture.fill_color
        return (float(c[0]), float(c[1]), float(c[2]))
    cat = getattr(fixture, "category", "kitchen_cabinet")
    if cat in ("kitchen_cabinet", "bathroom_vanity"):
        return (0.97, 0.95, 0.91)
    if cat == "bathroom_fixture":
        return (0.99, 0.99, 1.0)
    if cat in ("living_furniture", "bedroom_furniture"):
        return (0.95, 0.93, 0.89)
    if cat in ("dining_furniture", "office_furniture"):
        return (0.92, 0.88, 0.82)
    return (0.94, 0.95, 0.97)


def _countertop_fill_color(fixture) -> Tuple[float, float, float]:
    if getattr(fixture, "countertop_color", None):
        c = fixture.countertop_color
        return (float(c[0]), float(c[1]), float(c[2]))
    mat = getattr(fixture, "countertop_material", "quartz") or "quartz"
    return COUNTERTOP_RGB.get(mat, (0.94, 0.94, 0.93))


def _draw_pass_base(
    cr: cairo.Context,
    fixture,
    zoom_transform: float,
    opacity: float,
    base_lw: Optional[float] = None,
) -> None:
    sym = fixture.symbol_type
    if fixture.is_upper or getattr(fixture, "mount_surface", "auto") == "countertop":
        return
    if sym in ("kitchen_sink_single", "kitchen_sink_double", "cooktop"):
        return

    w, d = float(fixture.width), float(fixture.depth)
    hw, hd = w / 2.0, d / 2.0
    lw = base_lw if base_lw is not None else 1.2 / zoom_transform
    thin_lw = (base_lw * (0.8 / 1.2)) if base_lw is not None else 0.8 / zoom_transform
    r, g, b = _base_fill_color(fixture)

    cr.save()
    cr.translate(fixture.x, fixture.y)
    cr.rotate(math.radians(fixture.rotation))
    cr.set_line_width(lw)

    if sym == "corner_base_cabinet":
        pts = _corner_poly(w, d, 24.0)
        _poly_path(cr, pts)
        cr.set_source_rgba(r, g, b, opacity)
        cr.fill_preserve()
        cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
        cr.stroke()
    elif sym == "toilet":
        # Tank at back (-Y), elongated bowl toward front (+Y)
        tank_w = w * 0.92
        tank_d = d * 0.30
        _rounded_rect(cr, -tank_w / 2.0, -hd + 0.5, tank_w, tank_d, 1.5)
        cr.set_source_rgba(r, g, b, opacity)
        cr.fill_preserve()
        cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
        cr.stroke()
        bowl_ry = (d - tank_d - 2.0) / 2.0
        bowl_cy = -hd + tank_d + 1.0 + bowl_ry
        _ellipse(cr, 0.0, bowl_cy, w * 0.38, bowl_ry)
        cr.set_source_rgba(r, g, b, opacity)
        cr.fill_preserve()
        cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
        cr.stroke()
        cr.set_line_width(thin_lw)
        _ellipse(cr, 0.0, bowl_cy + bowl_ry * 0.1, w * 0.24, bowl_ry * 0.65)
        cr.stroke()
    elif sym == "bathtub":
        cr.set_source_rgba(r, g, b, opacity)
        cr.rectangle(-hw, -hd, w, d)
        cr.fill_preserve()
        cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
        cr.stroke()
        pad = 3.0
        cr.set_line_width(thin_lw)
        _rounded_rect(cr, -hw + pad, -hd + pad, max(4.0, w - 2 * pad), max(4.0, d - 2 * pad), min(8.0, d * 0.28))
        cr.stroke()
        cr.arc(-hw + pad + 5.0, 0.0, 1.4, 0.0, 2.0 * math.pi)
        cr.stroke()
    elif sym == "shower_square":
        cr.set_source_rgba(r, g, b, opacity)
        cr.rectangle(-hw, -hd, w, d)
        cr.fill_preserve()
        cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
        cr.stroke()
        inset = 2.0
        cr.set_line_width(thin_lw)
        cr.rectangle(-hw + inset, -hd + inset, w - 2 * inset, d - 2 * inset)
        cr.stroke()
        cr.move_to(-hw + inset, -hd + inset); cr.line_to(hw - inset, hd - inset)
        cr.move_to(hw - inset, -hd + inset); cr.line_to(-hw + inset, hd - inset)
        cr.stroke()
        cr.set_source_rgba(r, g, b, opacity)
        cr.arc(0.0, 0.0, 2.2, 0.0, 2.0 * math.pi)
        cr.fill_preserve()
        cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
        cr.stroke()
    elif sym == "shower_corner":
        chamfer = min(w, d) * 0.42
        pts = [(-hw, -hd), (hw, -hd), (hw, hd - chamfer), (hw - chamfer, hd), (-hw, hd)]
        _poly_path(cr, pts)
        cr.set_source_rgba(r, g, b, opacity)
        cr.fill_preserve()
        cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
        cr.stroke()
        cr.set_line_width(thin_lw)
        cr.move_to(-hw + 2.0, -hd + 2.0); cr.line_to(hw - chamfer * 0.6, hd - chamfer * 0.6)
        cr.move_to(hw - 2.0, -hd + 2.0); cr.line_to(-hw + 2.0, hd - 2.0)
        cr.stroke()
        cr.arc(-2.0, -2.0, 2.0, 0.0, 2.0 * math.pi)
        cr.stroke()
    elif sym in ("pedestal_sink", "utility_sink"):
        cr.set_source_rgba(r, g, b, opacity)
        _rounded_rect(cr, -hw, -hd, w, d, 3.0 if sym == "pedestal_sink" else 1.0)
        cr.fill_preserve()
        cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
        cr.stroke()
        _draw_basin_and_faucet(cr, 0.0, 1.0, w * 0.72, d * 0.64, thin_lw, opacity)
    else:
        # Rectangular cabinet / appliance / mechanical footprint (opaque mask over floor textures)
        cr.set_source_rgba(r, g, b, opacity)
        cr.rectangle(-hw, -hd, w, d)
        cr.fill_preserve()
        cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
        cr.stroke()

        cr.set_line_width(thin_lw)
        if sym == "range_stove":
            # Back control strip + 4 burners
            cr.move_to(-hw, -hd + 3.0); cr.line_to(hw, -hd + 3.0); cr.stroke()
            for bx in (-w * 0.24, w * 0.24):
                for by in (-d * 0.12 + 1.5, d * 0.24 + 1.5):
                    cr.arc(bx, by, min(w, d) * 0.14, 0.0, 2.0 * math.pi)
                    cr.stroke()
        elif sym == "refrigerator":
            # Front door line + handles
            cr.move_to(-hw, hd - 3.0); cr.line_to(hw, hd - 3.0); cr.stroke()
            if w >= 30.0:
                cr.move_to(0.0, hd - 3.0); cr.line_to(0.0, hd); cr.stroke()
            _draw_tag(cr, "REF", w, cy=-2.0, size=5.5, opacity=opacity, rotation_deg=fixture.rotation)
        elif sym == "dishwasher":
            _draw_tag(cr, "DW", w, cy=0.0, size=5.0, opacity=opacity, rotation_deg=fixture.rotation)
        elif sym == "tall_pantry":
            cr.move_to(-hw, -hd); cr.line_to(hw, hd)
            cr.move_to(hw, -hd); cr.line_to(-hw, hd)
            cr.stroke()
            _draw_tag(cr, "PANTRY", w, cy=0.0, size=4.2, opacity=opacity, rotation_deg=fixture.rotation)
        elif sym in ("washer", "dryer"):
            cr.arc(0.0, 1.0, min(w, d) * 0.28, 0.0, 2.0 * math.pi)
            cr.stroke()
            _draw_tag(cr, "W" if sym == "washer" else "D", w, cy=1.0, size=5.5, opacity=opacity, rotation_deg=fixture.rotation)
        elif sym == "water_heater":
            cr.arc(0.0, 0.0, min(hw, hd) - 1.5, 0.0, 2.0 * math.pi)
            cr.stroke()
            _draw_tag(cr, "WH", w, cy=0.0, size=5.0, opacity=opacity, rotation_deg=fixture.rotation)
        elif sym in ("furnace", "air_conditioner", "wall_oven"):
            cr.move_to(-hw, -hd); cr.line_to(hw, hd)
            cr.move_to(hw, -hd); cr.line_to(-hw, hd)
            cr.stroke()
            _draw_tag(cr, get_fixture_spec(sym)["short_tag"], w, cy=0.0, size=4.5, opacity=opacity, rotation_deg=fixture.rotation)
        elif sym == "base_drawer_cabinet":
            # Front pull bar
            cr.move_to(-w * 0.25, hd - 1.5); cr.line_to(w * 0.25, hd - 1.5); cr.stroke()
        elif sym in ("bed_king", "bed_queen", "bed_twin"):
            # Headboard along -Y, pillows, and folded duvet line
            hb_h = min(4.0, d * 0.06)
            cr.set_source_rgba(0.84, 0.79, 0.72, opacity)
            cr.rectangle(-hw, -hd, w, hb_h)
            cr.fill_preserve()
            cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
            cr.stroke()
            pillow_count = 1 if sym == "bed_twin" else 2
            pil_gap = 4.0
            pil_w = (w - (pillow_count + 1) * pil_gap) / pillow_count
            pil_d = min(14.0, d * 0.20)
            for pi in range(pillow_count):
                px = -hw + pil_gap + pi * (pil_w + pil_gap)
                _rounded_rect(cr, px, -hd + hb_h + 2.0, pil_w, pil_d, 2.0)
                cr.set_source_rgba(0.99, 0.99, 1.0, opacity)
                cr.fill_preserve()
                cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
                cr.stroke()
            duvet_y = -hd + min(d * 0.34, 24.0)
            cr.move_to(-hw, duvet_y); cr.line_to(hw, duvet_y); cr.stroke()
        elif sym in ("sofa", "loveseat", "armchair"):
            back_d = min(7.0, d * 0.22)
            arm_w = min(5.5, w * 0.16)
            cr.move_to(-hw + arm_w, -hd + back_d); cr.line_to(hw - arm_w, -hd + back_d)
            cr.move_to(-hw + arm_w, -hd); cr.line_to(-hw + arm_w, hd)
            cr.move_to(hw - arm_w, -hd); cr.line_to(hw - arm_w, hd)
            seats = 3 if sym == "sofa" else (2 if sym == "loveseat" else 1)
            seat_span = max(4.0, w - 2.0 * arm_w)
            for si in range(1, seats):
                sx = -hw + arm_w + seat_span * (si / seats)
                cr.move_to(sx, -hd + back_d); cr.line_to(sx, hd)
            cr.stroke()
        elif sym in ("dining_table", "coffee_table", "end_table"):
            inset = min(2.5, w * 0.08, d * 0.08)
            _rounded_rect(cr, -hw + inset, -hd + inset, w - 2.0 * inset, d - 2.0 * inset, 2.0)
            cr.stroke()
            if sym == "dining_table":
                _draw_tag(cr, "DINING", w, cy=0.0, size=4.8, opacity=opacity, rotation_deg=fixture.rotation)
        elif sym == "dining_chair":
            back_d = min(3.0, d * 0.20)
            cr.rectangle(-hw + 1.0, -hd, w - 2.0, back_d)
            cr.stroke()
        elif sym == "office_chair":
            back_d = min(3.5, d * 0.18)
            _rounded_rect(cr, -hw + 2.0, -hd + back_d + 1.0, w - 4.0, d - back_d - 3.0, 3.0)
            cr.stroke()
            cr.arc(0.0, -hd + back_d + 1.0, min(hw, hd) * 0.65, math.pi * 1.15, math.pi * 1.85)
            cr.stroke()
        elif sym == "desk":
            ped_w = min(15.0, w * 0.28)
            cr.save()
            cr.set_dash([2.5 / zoom_transform, 2.0 / zoom_transform])
            cr.rectangle(hw - ped_w, -hd + 1.5, ped_w - 1.5, d - 3.0)
            cr.stroke()
            cr.restore()
            _draw_tag(cr, "DESK", w - ped_w, cy=0.0, size=4.5, opacity=opacity, rotation_deg=fixture.rotation)
        elif sym in ("nightstand", "dresser"):
            cr.move_to(-w * 0.30, hd - 1.5); cr.line_to(w * 0.30, hd - 1.5); cr.stroke()
        elif sym == "tv_console":
            # Thin TV bar near back edge (-Y)
            tv_w = min(w * 0.85, 52.0)
            cr.set_source_rgba(0.18, 0.20, 0.24, opacity)
            cr.rectangle(-tv_w / 2.0, -hd + 2.5, tv_w, 2.5)
            cr.fill()
        elif sym == "bookshelf":
            for frac in (0.25, 0.5, 0.75):
                bx = -hw + w * frac
                cr.move_to(bx, -hd + 1.5); cr.line_to(bx, hd - 1.5)
            cr.stroke()

    cr.restore()


def _draw_pass_countertop(
    cr: cairo.Context,
    fixture,
    zoom_transform: float,
    opacity: float,
    base_lw: Optional[float] = None,
) -> None:
    sym = fixture.symbol_type
    w, d = float(fixture.width), float(fixture.depth)
    hw, hd = w / 2.0, d / 2.0
    lw = base_lw if base_lw is not None else 1.2 / zoom_transform
    thin_lw = (base_lw * (0.85 / 1.2)) if base_lw is not None else 0.85 / zoom_transform

    # Standalone countertop-mounted fixtures (sink / cooktop)
    if sym in ("kitchen_sink_single", "kitchen_sink_double", "cooktop"):
        cr.save()
        cr.translate(fixture.x, fixture.y)
        cr.rotate(math.radians(fixture.rotation))
        if sym == "cooktop":
            cr.set_source_rgba(0.95, 0.95, 0.96, opacity)
            _rounded_rect(cr, -hw, -hd, w, d, 1.5)
            cr.fill_preserve()
            cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
            cr.set_line_width(lw)
            cr.stroke()
            cr.set_line_width(thin_lw)
            for bx in (-w * 0.26, w * 0.26):
                for by in (-d * 0.22, d * 0.22):
                    cr.arc(bx, by, min(w, d) * 0.16, 0.0, 2.0 * math.pi)
                    cr.stroke()
        else:
            cr.set_source_rgba(0.98, 0.99, 1.0, opacity)
            _rounded_rect(cr, -hw, -hd, w, d, 2.0)
            cr.fill_preserve()
            cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
            cr.set_line_width(lw)
            cr.stroke()
            _draw_basin_and_faucet(
                cr, 0.0, 1.0, w * 0.84, d * 0.72, thin_lw, opacity,
                double_bowl=(sym == "kitchen_sink_double"),
            )
        cr.restore()
        return

    if not getattr(fixture, "has_countertop", False) or fixture.is_upper:
        return

    overhang = max(0.0, float(getattr(fixture, "countertop_overhang", 0.0) or 0.0))
    cr_r, cr_g, cr_b = _countertop_fill_color(fixture)

    cr.save()
    cr.translate(fixture.x, fixture.y)
    cr.rotate(math.radians(fixture.rotation))
    cr.set_line_width(lw)

    if sym == "corner_base_cabinet":
        pts = _corner_poly(w, d, 24.0 + overhang)
        _poly_path(cr, pts)
        cr.set_source_rgba(cr_r, cr_g, cr_b, opacity)
        cr.fill_preserve()
        cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
        cr.stroke()
        if getattr(fixture, "has_backsplash", True):
            cr.set_line_width(thin_lw)
            cr.move_to(-hw + 1.5, hd)
            cr.line_to(-hw + 1.5, -hd + 1.5)
            cr.line_to(hw, -hd + 1.5)
            cr.stroke()
    else:
        ct_d = d + overhang
        cr.set_source_rgba(cr_r, cr_g, cr_b, opacity)
        cr.rectangle(-hw, -hd, w, ct_d)
        cr.fill_preserve()
        cr.set_source_rgba(0.16, 0.18, 0.22, opacity)
        cr.stroke()
        # Subtle dashed cabinet-box front line under overhang when overhang > 0.25"
        if overhang > 0.25:
            cr.save()
            cr.set_line_width(thin_lw)
            cr.set_source_rgba(0.35, 0.37, 0.42, opacity * 0.65)
            cr.set_dash([3.0 / zoom_transform, 2.5 / zoom_transform])
            cr.move_to(-hw, hd)
            cr.line_to(hw, hd)
            cr.stroke()
            cr.restore()
        if getattr(fixture, "has_backsplash", True) and sym != "island_cabinet":
            cr.set_line_width(thin_lw)
            cr.move_to(-hw, -hd + 1.2)
            cr.line_to(hw, -hd + 1.2)
            cr.stroke()
        if sym == "sink_base_cabinet":
            _draw_basin_and_faucet(
                cr, 0.0, 0.5, min(w * 0.78, 30.0), min(d * 0.68, 17.0), thin_lw, opacity,
                double_bowl=(w >= 33.0),
            )
        elif sym == "vanity_single":
            _draw_basin_and_faucet(cr, 0.0, 0.5, min(w * 0.52, 19.0), min(d * 0.66, 14.0), thin_lw, opacity)
        elif sym == "vanity_double":
            for sx in (-w * 0.25, w * 0.25):
                _draw_basin_and_faucet(cr, sx, 0.5, min(w * 0.28, 18.0), min(d * 0.66, 14.0), thin_lw, opacity)

    cr.restore()


def _draw_pass_upper(
    cr: cairo.Context,
    fixture,
    zoom_transform: float,
    opacity: float,
    base_lw: Optional[float] = None,
) -> None:
    if not getattr(fixture, "is_upper", False):
        return
    sym = fixture.symbol_type
    w, d = float(fixture.width), float(fixture.depth)
    hw, hd = w / 2.0, d / 2.0
    lw = (base_lw * (1.1 / 1.2)) if base_lw is not None else 1.1 / zoom_transform

    cr.save()
    cr.translate(fixture.x, fixture.y)
    cr.rotate(math.radians(fixture.rotation))
    cr.set_line_width(lw)
    cr.set_source_rgba(0.18, 0.24, 0.34, opacity * 0.9)
    cr.set_dash([5.0 / zoom_transform, 3.0 / zoom_transform])

    if sym == "corner_upper_cabinet":
        pts = _corner_poly(w, d, 12.0)
        _poly_path(cr, pts)
        cr.stroke()
    else:
        cr.rectangle(-hw, -hd, w, d)
        cr.stroke()
        if sym == "range_hood":
            cr.set_dash([])
            cr.set_line_width(lw * (0.8 / 1.1))
            cr.arc(0.0, -hd + d * 0.35, min(w, d) * 0.16, 0.0, 2.0 * math.pi)
            cr.stroke()
            _draw_tag(cr, "HOOD", w, cy=2.5, size=3.8, opacity=opacity, rotation_deg=fixture.rotation)
        elif sym == "microwave":
            _draw_tag(cr, "MW", w, cy=0.0, size=3.8, opacity=opacity, rotation_deg=fixture.rotation)

    cr.restore()


def draw_fixture_list(
    cr: cairo.Context,
    fixtures,
    zoom_transform: float,
    opacity_fn=None,
    base_lw: Optional[float] = None,
) -> None:
    """Render a sequence of Fixture instances in 3 passes: base -> countertop -> upper."""
    if not fixtures:
        return
    # 1. Base cabinetry / appliances / bath fixtures (masks floor pattern)
    for fix in fixtures:
        op = opacity_fn(fix) if opacity_fn else 1.0
        _draw_pass_base(cr, fix, zoom_transform, op, base_lw=base_lw)
    # 2. Countertops & drop-in sinks/cooktops
    for fix in fixtures:
        op = opacity_fn(fix) if opacity_fn else 1.0
        if getattr(fix, "mount_surface", "") != "countertop":
            _draw_pass_countertop(cr, fix, zoom_transform, op, base_lw=base_lw)
    for fix in fixtures:
        op = opacity_fn(fix) if opacity_fn else 1.0
        if getattr(fix, "mount_surface", "") == "countertop":
            _draw_pass_countertop(cr, fix, zoom_transform, op, base_lw=base_lw)
    # 3. Upper wall cabinets & hoods (dashed overlays)
    for fix in fixtures:
        op = opacity_fn(fix) if opacity_fn else 1.0
        _draw_pass_upper(cr, fix, zoom_transform, op, base_lw=base_lw)


def draw_fixtures(canvas, cr: cairo.Context, zoom_transform: float, printing: bool = False) -> None:
    """Render committed fixtures and active placement previews on ``canvas``."""
    def is_visible(obj):
        if hasattr(canvas, "is_object_on_visible_layer"):
            return canvas.is_object_on_visible_layer(obj)
        return True

    def get_opacity(obj):
        if hasattr(canvas, "get_object_opacity"):
            return canvas.get_object_opacity(obj)
        return 1.0

    visible = [f for f in getattr(canvas, "fixtures", []) if is_visible(f)]
    base_lw = (
        resolve_stroke_width(canvas, "fixtures", 1.2, zoom_transform)
        if getattr(canvas, "_print_line_weights", None) is not None
        else None
    )
    draw_fixture_list(cr, visible, zoom_transform, opacity_fn=get_opacity, base_lw=base_lw)

    if printing:
        return

    tool_mode = getattr(canvas, "tool_mode", None)
    if tool_mode == "add_fixture" and getattr(canvas, "fixture_ghost", None) is not None:
        draw_fixture_list(cr, [canvas.fixture_ghost], zoom_transform, opacity_fn=lambda _f: 0.55)
    elif tool_mode == "add_kitchen_layout" and getattr(canvas, "layout_ghost_fixtures", None):
        draw_fixture_list(cr, canvas.layout_ghost_fixtures, zoom_transform, opacity_fn=lambda _f: 0.55)
    elif tool_mode == "draw_cabinet_run":
        start = getattr(canvas, "cabinet_run_start", None)
        end = getattr(canvas, "cabinet_run_preview", None)
        if start and end and math.hypot(end[0] - start[0], end[1] - start[1]) >= 6.0:
            preview_items = pack_cabinet_run(
                start,
                end,
                include_uppers=bool(getattr(canvas, "cabinet_run_include_uppers", True)),
                countertop_material=getattr(canvas, "cabinet_run_material", "quartz") or "quartz",
                side=float(getattr(canvas, "cabinet_run_side", 1.0) or 1.0),
            )
            draw_fixture_list(cr, preview_items, zoom_transform, opacity_fn=lambda _f: 0.55)
            cr.save()
            cr.set_source_rgba(0.10, 0.50, 0.82, 0.9)
            cr.set_line_width(2.0 / zoom_transform)
            cr.set_dash([5.0 / zoom_transform, 3.0 / zoom_transform])
            cr.move_to(start[0], start[1])
            cr.line_to(end[0], end[1])
            cr.stroke()
            cr.restore()


def draw_fixture_preview_icon(cr: cairo.Context, symbol_type: str, width: float, height: float) -> None:
    """Draw a scaled-to-fit AIA thumbnail of ``symbol_type`` for the Fixture Browser dialog."""
    from ..components import Fixture

    spec = get_fixture_spec(symbol_type)
    fix = Fixture(symbol_type=symbol_type, x=0.0, y=0.0)
    fw = max(1.0, float(spec["width"]))
    fd = max(1.0, float(spec["depth"]) + (float(spec["countertop_overhang"]) if spec["has_countertop"] else 0.0))
    scale = min((width - 8.0) / fw, (height - 8.0) / fd)
    cr.save()
    cr.translate(width / 2.0, height / 2.0)
    cr.scale(scale, scale)
    draw_fixture_list(cr, [fix], max(scale, 0.5))
    cr.restore()
