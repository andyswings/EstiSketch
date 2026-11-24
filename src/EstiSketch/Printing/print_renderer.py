"""Page layout, title block and PDF rendering for printing.

All page geometry is in PostScript points. The model is in inches, so a
scale is expressed as "points per model inch".
"""
from __future__ import annotations

import datetime
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cairo

from .print_settings import PrintSettings, SCALES, FIT_SCALE

Rect = Tuple[float, float, float, float]  # x, y, w, h
Bounds = Tuple[float, float, float, float]  # x0, y0, x1, y1 (model inches)

_BOUNDS_PTS_PER_IN = 20.0  # scale used while measuring content extents
_FALLBACK_PTS_PER_IN = _FALLBACK = 1.5  # 1/4" = 1'-0"


# ---------------------------------------------------------------------------
# Page resolution
# ---------------------------------------------------------------------------
def resolve_levels(canvas, settings: PrintSettings) -> list:
    """Levels to print (one page each), in project order."""
    levels = list(canvas.levels)
    if settings.print_all_levels:
        return levels
    wanted = set(settings.level_ids)
    return [lv for lv in levels if lv.id in wanted]


# ---------------------------------------------------------------------------
# Canvas state juggling
# ---------------------------------------------------------------------------
@contextmanager
def _print_state(canvas, level_id: str, hidden_layer_ids, pts_per_in: float):
    """Temporarily show only `level_id` (minus hidden layers) at print scale."""
    saved_layers = [(layer, layer.visible) for layer in canvas.layers]
    saved = (canvas.active_level_id, canvas.show_all_levels, canvas.zoom)
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    try:
        canvas.active_level_id = level_id
        canvas.show_all_levels = False
        hidden = set(hidden_layer_ids)
        for layer in canvas.layers:
            if layer.id in hidden:
                layer.visible = False
        # draw_scene sizes strokes as 1/zoom, so zoom must match the print
        # scale: zoom * PIXELS_PER_INCH == points per model inch.
        canvas.zoom = pts_per_in / ppi
        yield ppi
    finally:
        canvas.active_level_id, canvas.show_all_levels, canvas.zoom = saved
        for layer, vis in saved_layers:
            layer.visible = vis


def _draw_model(canvas, cr, pts_per_in: float, ppi: float) -> None:
    canvas.draw_scene(cr, pts_per_in, ppi, printing=True)


def content_bounds(canvas, level_id: str, hidden_layer_ids=()) -> Optional[Bounds]:
    """Extent of everything drawn for a level, in model inches (or None)."""
    surf = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
    cr = cairo.Context(surf)
    with _print_state(canvas, level_id, hidden_layer_ids, _BOUNDS_PTS_PER_IN) as ppi:
        cr.scale(_BOUNDS_PTS_PER_IN, _BOUNDS_PTS_PER_IN)
        _draw_model(canvas, cr, _BOUNDS_PTS_PER_IN, ppi)
    x, y, w, h = surf.ink_extents()
    if w <= 0 or h <= 0:
        return None
    k = _BOUNDS_PTS_PER_IN
    return (x / k, y / k, (x + w) / k, (y + h) / k)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
@dataclass
class PageLayout:
    page_w: float
    page_h: float
    frame: Rect  # inside the margins (border is drawn here)
    title_rect: Optional[Rect]
    draw_rect: Rect  # area available to the drawing


def compute_layout(settings: PrintSettings) -> PageLayout:
    pw, ph = settings.page_size()
    m = max(0.0, settings.margin_in) * 72.0
    m = min(m, min(pw, ph) / 4)
    frame = (m, m, pw - 2 * m, ph - 2 * m)
    fx, fy, fw, fh = frame
    pad = 6.0 if settings.draw_border or settings.title_block.enabled else 0.0
    title_rect = None
    bottom = fy + fh
    if settings.title_block.enabled:
        tb_h = min(max(fh * 0.10, 72.0), 144.0)
        tb_h = min(tb_h, fh * 0.4)
        title_rect = (fx, fy + fh - tb_h, fw, tb_h)
        bottom = fy + fh - tb_h
    draw_rect = (fx + pad, fy + pad, fw - 2 * pad, max(10.0, bottom - fy - 2 * pad))
    return PageLayout(pw, ph, frame, title_rect, draw_rect)


def compute_scale(settings: PrintSettings, bounds: Optional[Bounds], draw_rect: Rect) -> float:
    """Points per model inch for this page."""
    fixed = SCALES.get(settings.scale_name)
    if fixed is not None:
        return fixed
    if bounds is None:
        return _FALLBACK_PTS_PER_IN
    bw = max(bounds[2] - bounds[0], 1e-6)
    bh = max(bounds[3] - bounds[1], 1e-6)
    return min(draw_rect[2] / bw, draw_rect[3] / bh)


def scale_label(settings: PrintSettings, pts_per_in: float) -> str:
    if settings.scale_name != FIT_SCALE:
        return settings.scale_name
    # Report the effective ratio for a fit-to-page sheet.
    ratio = 72.0 / pts_per_in if pts_per_in > 0 else 0
    return f"Fit (approx 1:{ratio:.0f})"


# ---------------------------------------------------------------------------
# Title block
# ---------------------------------------------------------------------------
def _fit_text(cr, text: str, max_w: float, max_size: float, min_size: float = 4.0,
              bold: bool = False) -> float:
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    size = max_size
    while size > min_size:
        cr.set_font_size(size)
        if cr.text_extents(text).x_advance <= max_w:
            break
        size -= 0.5
    cr.set_font_size(max(size, min_size))
    return max(size, min_size)


def _cell(cr, rect: Rect, label: str, value: str, value_size: float, bold: bool = False) -> None:
    x, y, w, h = rect
    cr.set_line_width(0.5)
    cr.set_source_rgb(0, 0, 0)
    cr.rectangle(x, y, w, h)
    cr.stroke()
    label_size = max(4.0, min(7.0, h * 0.18))
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(label_size)
    cr.set_source_rgb(0.4, 0.4, 0.4)
    cr.move_to(x + 3, y + label_size + 1)
    cr.show_text(label.upper())
    if value:
        cr.set_source_rgb(0, 0, 0)
        avail_h = h - label_size - 4
        size = _fit_text(cr, value, w - 8, min(value_size, avail_h * 0.8), bold=bold)
        cr.move_to(x + 4, y + h - max(3.0, (avail_h - size) / 2) - 1)
        cr.show_text(value)


def draw_title_block(cr, rect: Rect, settings: PrintSettings, sheet_title: str,
                     sheet_number: str, scale_text: str) -> None:
    tb = settings.title_block
    x, y, w, h = rect
    date = tb.date.strip() or datetime.date.today().strftime("%b %d, %Y")
    c1, c2 = w * 0.45, w * 0.30
    c3 = w - c1 - c2
    big = h * 0.34

    # Column 1: company / project / address
    r1, r2, r3 = h * 0.25, h * 0.45, h * 0.30
    _cell(cr, (x, y, c1, r1), "Company", tb.company, h * 0.16)
    _cell(cr, (x, y + r1, c1, r2), "Project", tb.project_name, big, bold=True)
    _cell(cr, (x, y + r1 + r2, c1, r3), "Address", tb.address, h * 0.16)

    # Column 2: 3 rows x 2 columns
    rh = h / 3
    cw = c2 / 2
    pairs = [("Client", tb.client), ("Job No.", tb.job_number),
             ("Drawn by", tb.drawn_by), ("Checked by", tb.checked_by),
             ("Date", date), ("Revision", tb.revision)]
    for i, (label, value) in enumerate(pairs):
        _cell(cr, (x + c1 + (i % 2) * cw, y + (i // 2) * rh, cw, rh),
              label, value, h * 0.16)

    # Column 3: sheet title / number / scale
    x3 = x + c1 + c2
    t_h = h * 0.5
    _cell(cr, (x3, y, c3, t_h), "Sheet", sheet_title, h * 0.24, bold=True)
    _cell(cr, (x3, y + t_h, c3 / 2, h - t_h), "Sheet No.", sheet_number, h * 0.24, bold=True)
    _cell(cr, (x3 + c3 / 2, y + t_h, c3 / 2, h - t_h), "Scale", scale_text, h * 0.14)

    # Heavier outer outline
    cr.set_source_rgb(0, 0, 0)
    cr.set_line_width(1.5)
    cr.rectangle(x, y, w, h)
    cr.stroke()


# ---------------------------------------------------------------------------
# Page rendering
# ---------------------------------------------------------------------------
def render_page(cr, canvas, settings: PrintSettings, level, page_index: int,
                page_count: int, bounds: Optional[Bounds] = None,
                measure: bool = True) -> PageLayout:
    """Draw one sheet (paper is assumed white) onto `cr` at 1 unit = 1 point."""
    layout = compute_layout(settings)
    if bounds is None and measure:
        bounds = content_bounds(canvas, level.id, settings.hidden_layer_ids)
    scale = compute_scale(settings, bounds, layout.draw_rect)

    # Drawing content, clipped to the drawing area
    dx, dy, dw, dh = layout.draw_rect
    cr.save()
    cr.rectangle(dx, dy, dw, dh)
    cr.clip()
    if bounds is not None:
        cx = (bounds[0] + bounds[2]) / 2
        cy = (bounds[1] + bounds[3]) / 2
        cr.translate(dx + dw / 2 + settings.offset_x - cx * scale,
                     dy + dh / 2 + settings.offset_y - cy * scale)
        cr.scale(scale, scale)
        cr.set_source_rgb(0, 0, 0)
        with _print_state(canvas, level.id, settings.hidden_layer_ids, scale) as ppi:
            _draw_model(canvas, cr, scale, ppi)
    cr.restore()

    # Border and title block
    fx, fy, fw, fh = layout.frame
    if settings.draw_border or settings.title_block.enabled:
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(1.5)
        cr.rectangle(fx, fy, fw, fh)
        cr.stroke()
    if layout.title_rect is not None:
        tb = settings.title_block
        title = level.name
        if tb.drawing_title.strip():
            title = f"{tb.drawing_title.strip()} - {level.name}"
        number = f"{tb.sheet_prefix}-{page_index + 1}" if tb.sheet_prefix else str(page_index + 1)
        draw_title_block(cr, layout.title_rect, settings, title, number,
                         scale_label(settings, scale))
    return layout


def export_pdf(canvas, settings: PrintSettings, path: str, levels: Optional[List] = None,
               bounds_cache: Optional[dict] = None) -> int:
    """Write the selected levels to a multi-page PDF. Returns page count."""
    levels = levels if levels is not None else resolve_levels(canvas, settings)
    if not levels:
        raise ValueError("No levels selected to print.")
    pw, ph = settings.page_size()
    surface = cairo.PDFSurface(path, pw, ph)
    try:
        cr = cairo.Context(surface)
        for i, level in enumerate(levels):
            surface.set_size(pw, ph)
            cr.save()
            cr.set_source_rgb(1, 1, 1)
            cr.paint()
            cr.restore()
            bounds = None
            if bounds_cache is not None:
                bounds = bounds_cache.get((level.id, tuple(sorted(settings.hidden_layer_ids))))
            render_page(cr, canvas, settings, level, i, len(levels), bounds=bounds)
            cr.show_page()
    finally:
        surface.finish()
    return len(levels)


def _svg_level_slug(name: str, index: int) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip()).strip("_")
    return slug or f"level_{index + 1}"


def export_svg(canvas, settings: PrintSettings, path: str, levels: Optional[List] = None,
               bounds_cache: Optional[dict] = None) -> List[str]:
    """Write the selected levels to scaled vector SVG file(s). Returns output paths."""
    levels = levels if levels is not None else resolve_levels(canvas, settings)
    if not levels:
        raise ValueError("No levels selected to export.")
    pw, ph = settings.page_size()

    if len(levels) == 1:
        out_paths = [path]
    else:
        root, ext = os.path.splitext(path)
        ext = ext or ".svg"
        seen = set()
        out_paths = []
        for i, level in enumerate(levels):
            slug = _svg_level_slug(getattr(level, "name", ""), i)
            if slug in seen:
                slug = f"{slug}_{i + 1}"
            seen.add(slug)
            out_paths.append(f"{root}_{slug}{ext}")

    for i, (level, out_path) in enumerate(zip(levels, out_paths)):
        surface = cairo.SVGSurface(out_path, pw, ph)
        if hasattr(surface, "set_document_unit") and hasattr(cairo, "SVGUnit"):
            surface.set_document_unit(cairo.SVGUnit.PT)
        try:
            cr = cairo.Context(surface)
            cr.save()
            cr.set_source_rgb(1, 1, 1)
            cr.paint()
            cr.restore()
            bounds = None
            if bounds_cache is not None:
                bounds = bounds_cache.get((level.id, tuple(sorted(settings.hidden_layer_ids))))
            render_page(cr, canvas, settings, level, i, len(levels), bounds=bounds)
        finally:
            surface.finish()
    return out_paths
