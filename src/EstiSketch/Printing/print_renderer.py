"""Page layout, title block and PDF rendering for printing.

All page geometry is in PostScript points. The model is in inches, so a
scale is expressed as "points per model inch".
"""
from __future__ import annotations

import datetime
import math
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import cairo

from .print_settings import FIT_SCALE, LineWeights, PrintSettings, SCALES
from ..Canvas.compass import draw_north_arrow

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
def _print_state(
    canvas,
    level_id: str,
    hidden_layer_ids: Iterable[str],
    pts_per_in: float,
    line_weights: Optional[LineWeights] = None,
):
    """Temporarily show only `level_id` (minus hidden layers) at print scale."""
    saved_layers = [(layer, layer.visible) for layer in canvas.layers]
    saved = (canvas.active_level_id, canvas.show_all_levels, canvas.zoom)
    saved_lw = getattr(canvas, "_print_line_weights", None)
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
        canvas._print_line_weights = line_weights
        yield ppi
    finally:
        canvas.active_level_id, canvas.show_all_levels, canvas.zoom = saved
        canvas._print_line_weights = saved_lw
        for layer, vis in saved_layers:
            layer.visible = vis


def _draw_model(canvas, cr, pts_per_in: float, ppi: float) -> None:
    canvas.draw_scene(cr, pts_per_in, ppi, printing=True)


def content_bounds(
    canvas,
    level_id: str,
    hidden_layer_ids: Iterable[str] = (),
    line_weights: Optional[LineWeights] = None,
) -> Optional[Bounds]:
    """Extent of everything drawn for a level, in model inches (or None)."""
    surf = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)  # pyrefly: ignore[bad-argument-type]  # Pycairo stub omits Optional for unbounded RecordingSurface
    cr = cairo.Context(surf)
    with _print_state(
        canvas, level_id, hidden_layer_ids, _BOUNDS_PTS_PER_IN, line_weights=line_weights
    ) as ppi:
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


def compute_layout(
    settings: PrintSettings,
    page_size_override: Optional[Tuple[float, float]] = None,
) -> PageLayout:
    pw, ph = page_size_override if page_size_override is not None else settings.page_size()
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


@dataclass
class TileSpec:
    """Geometry and adjacency flags for one sheet in a tiled grid."""

    row: int
    col: int
    rows: int
    cols: int
    origin_model_x: float
    origin_model_y: float
    overlap_pt: float
    has_left: bool
    has_right: bool
    has_top: bool
    has_bottom: bool
    grid_x0_model: float
    grid_y0_model: float
    step_x_pt: float
    step_y_pt: float


@dataclass
class PrintSheet:
    """Resolved output sheet representing either a full level or one tile."""

    level: object
    level_index: int
    sheet_index: int
    sheet_count: int
    tile: Optional[TileSpec] = None


def compute_tile_grid(
    bounds: Optional[Bounds],
    scale: float,
    draw_rect: Rect,
    overlap_pt: float,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> List[TileSpec]:
    """Split ``bounds`` at fixed ``scale`` across a ``rows x cols`` grid of ``draw_rect`` sheets."""
    _dx, _dy, dw, dh = draw_rect
    clamped_overlap = max(0.0, min(float(overlap_pt), min(dw, dh) * 0.4))
    step_x = max(1.0, dw - clamped_overlap)
    step_y = max(1.0, dh - clamped_overlap)
    if bounds is None or scale <= 0.0:
        return [
            TileSpec(
                0, 0, 1, 1, 0.0, 0.0, clamped_overlap,
                False, False, False, False, 0.0, 0.0, step_x, step_y,
            )
        ]

    x0, y0, x1, y1 = bounds
    content_w_pt = max(0.0, (x1 - x0) * scale)
    content_h_pt = max(0.0, (y1 - y0) * scale)
    cols = 1 if content_w_pt <= dw + 1e-3 else max(
        1, math.ceil((content_w_pt - clamped_overlap - 1e-6) / step_x)
    )
    rows = 1 if content_h_pt <= dh + 1e-3 else max(
        1, math.ceil((content_h_pt - clamped_overlap - 1e-6) / step_y)
    )
    total_w_pt = dw + (cols - 1) * step_x
    total_h_pt = dh + (rows - 1) * step_y

    cx_in = (x0 + x1) / 2.0
    cy_in = (y0 + y1) / 2.0
    grid_x0_in = cx_in - (total_w_pt / 2.0 + offset_x) / scale
    grid_y0_in = cy_in - (total_h_pt / 2.0 + offset_y) / scale

    tiles: List[TileSpec] = []
    for r in range(rows):
        for c in range(cols):
            tiles.append(
                TileSpec(
                    row=r,
                    col=c,
                    rows=rows,
                    cols=cols,
                    origin_model_x=grid_x0_in + (c * step_x) / scale,
                    origin_model_y=grid_y0_in + (r * step_y) / scale,
                    overlap_pt=clamped_overlap,
                    has_left=(c > 0),
                    has_right=(c < cols - 1),
                    has_top=(r > 0),
                    has_bottom=(r < rows - 1),
                    grid_x0_model=grid_x0_in,
                    grid_y0_model=grid_y0_in,
                    step_x_pt=step_x,
                    step_y_pt=step_y,
                )
            )
    return tiles


def _get_cached_bounds(
    canvas,
    level_id: str,
    settings: PrintSettings,
    bounds_cache: Optional[Dict[Tuple[str, Tuple[str, ...]], Optional[Bounds]]] = None,
) -> Optional[Bounds]:
    key = (level_id, tuple(sorted(settings.hidden_layer_ids)))
    if bounds_cache is not None and key in bounds_cache:
        return bounds_cache[key]
    bounds = content_bounds(
        canvas, level_id, settings.hidden_layer_ids, line_weights=settings.line_weights
    )
    if bounds_cache is not None:
        bounds_cache[key] = bounds
    return bounds


def resolve_sheets(
    canvas,
    settings: PrintSettings,
    levels: Optional[List] = None,
    bounds_cache: Optional[Dict[Tuple[str, Tuple[str, ...]], Optional[Bounds]]] = None,
    page_size_override: Optional[Tuple[float, float]] = None,
) -> List[PrintSheet]:
    """Expand selected levels into ordered ``PrintSheet``s (tiled when enabled at fixed scale)."""
    levels_list = list(levels) if levels is not None else resolve_levels(canvas, settings)
    layout = compute_layout(settings, page_size_override=page_size_override)
    use_tiling = settings.tile_enabled and settings.scale_name != FIT_SCALE
    overlap_pt = max(0.0, float(settings.tile_overlap_in)) * 72.0

    sheets: List[PrintSheet] = []
    for lv_idx, level in enumerate(levels_list):
        if use_tiling:
            bounds = _get_cached_bounds(canvas, level.id, settings, bounds_cache)
            scale = compute_scale(settings, bounds, layout.draw_rect)
            tiles = compute_tile_grid(
                bounds,
                scale,
                layout.draw_rect,
                overlap_pt,
                offset_x=settings.offset_x,
                offset_y=settings.offset_y,
            )
            for tile in tiles:
                sheets.append(
                    PrintSheet(
                        level=level,
                        level_index=lv_idx,
                        sheet_index=0,
                        sheet_count=0,
                        tile=tile if (tile.rows > 1 or tile.cols > 1) else None,
                    )
                )
        else:
            sheets.append(
                PrintSheet(
                    level=level,
                    level_index=lv_idx,
                    sheet_index=0,
                    sheet_count=0,
                    tile=None,
                )
            )

    total = len(sheets)
    for idx, sheet in enumerate(sheets):
        sheet.sheet_index = idx
        sheet.sheet_count = total
    return sheets


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
                     sheet_number: str, scale_text: str,
                     north_angle: float = 0.0) -> None:
    tb = settings.title_block
    x, y, w, h = rect
    date = tb.date.strip() or datetime.date.today().strftime("%b %d, %Y")
    c_north = min(h, w * 0.10)
    rem = w - c_north
    c1, c2 = rem * 0.45, rem * 0.30
    c3 = rem - c1 - c2
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

    # Column 4: North arrow cell
    nx, ny = x + rem, y
    _cell(cr, (nx, ny, c_north, h), "North", "", h * 0.14)
    label_h = max(4.0, min(7.0, h * 0.18)) + 3.0
    avail_h = max(8.0, h - label_h - 3.0)
    arrow_r = min(c_north - 8.0, avail_h) * 0.46
    draw_north_arrow(
        cr,
        nx + c_north / 2.0,
        ny + label_h + avail_h / 2.0,
        arrow_r,
        north_angle,
        monochrome=True,
    )

    # Heavier outer outline
    cr.set_source_rgb(0, 0, 0)
    cr.set_line_width(1.5)
    cr.rectangle(x, y, w, h)
    cr.stroke()


# ---------------------------------------------------------------------------
# Page rendering
# ---------------------------------------------------------------------------
def _draw_reg_target(cr: cairo.Context, x: float, y: float) -> None:
    cr.arc(x, y, 4.5, 0.0, 2.0 * math.pi)
    cr.move_to(x - 8.0, y)
    cr.line_to(x + 8.0, y)
    cr.move_to(x, y - 8.0)
    cr.line_to(x, y + 8.0)
    cr.stroke()


def _draw_tile_registration_marks(cr: cairo.Context, draw_rect: Rect, tile: TileSpec) -> None:
    """Draw dashed overlap trim guides and crosshair registration marks on shared edges."""
    dx, dy, dw, dh = draw_rect
    half_ov = tile.overlap_pt / 2.0
    cr.save()
    try:
        cr.set_source_rgba(0.25, 0.25, 0.28, 0.75)
        cr.set_line_width(0.6)
        cr.set_dash([4.0, 4.0])
        if tile.has_left:
            lx = dx + half_ov
            cr.move_to(lx, dy)
            cr.line_to(lx, dy + dh)
            cr.stroke()
        if tile.has_right:
            rx = dx + dw - half_ov
            cr.move_to(rx, dy)
            cr.line_to(rx, dy + dh)
            cr.stroke()
        if tile.has_top:
            ty = dy + half_ov
            cr.move_to(dx, ty)
            cr.line_to(dx + dw, ty)
            cr.stroke()
        if tile.has_bottom:
            by = dy + dh - half_ov
            cr.move_to(dx, by)
            cr.line_to(dx + dw, by)
            cr.stroke()

        cr.set_dash([])
        cr.set_line_width(0.75)
        xs: List[float] = []
        ys: List[float] = []
        if tile.has_left:
            xs.append(dx + half_ov)
        if tile.has_right:
            xs.append(dx + dw - half_ov)
        if tile.has_top:
            ys.append(dy + half_ov)
        if tile.has_bottom:
            ys.append(dy + dh - half_ov)
        for mx in xs:
            _draw_reg_target(cr, mx, dy + 14.0)
            _draw_reg_target(cr, mx, dy + dh - 14.0)
        for my in ys:
            _draw_reg_target(cr, dx + 14.0, my)
            _draw_reg_target(cr, dx + dw - 14.0, my)
        for mx in xs:
            for my in ys:
                _draw_reg_target(cr, mx, my)
    finally:
        cr.restore()


def _draw_tile_badge(cr: cairo.Context, frame: Rect, label: str) -> None:
    fx, fy, fw, fh = frame
    cr.save()
    try:
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(8.5)
        ext = cr.text_extents(label)
        bw = ext.width + 12.0
        bh = ext.height + 8.0
        bx = fx + fw - bw - 6.0
        by = fy + fh - bh - 6.0
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.9)
        cr.rectangle(bx, by, bw, bh)
        cr.fill_preserve()
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.set_line_width(0.6)
        cr.stroke()
        cr.move_to(bx + 6.0 - ext.x_bearing, by + bh - 4.0)
        cr.show_text(label)
    finally:
        cr.restore()


def render_page(
    cr,
    canvas,
    settings: PrintSettings,
    level,
    page_index: int,
    page_count: int,
    bounds: Optional[Bounds] = None,
    measure: bool = True,
    tile: Optional[TileSpec] = None,
    page_size_override: Optional[Tuple[float, float]] = None,
) -> PageLayout:
    """Draw one sheet (paper is assumed white) onto `cr` at 1 unit = 1 point."""
    layout = compute_layout(settings, page_size_override=page_size_override)
    if bounds is None and measure:
        bounds = content_bounds(
            canvas, level.id, settings.hidden_layer_ids, line_weights=settings.line_weights
        )
    scale = compute_scale(settings, bounds, layout.draw_rect)

    # Drawing content, clipped to the drawing area
    dx, dy, dw, dh = layout.draw_rect
    cr.save()
    try:
        cr.rectangle(dx, dy, dw, dh)
        cr.clip()
        if bounds is not None:
            if tile is not None:
                cr.translate(
                    dx - tile.origin_model_x * scale,
                    dy - tile.origin_model_y * scale,
                )
            else:
                cx = (bounds[0] + bounds[2]) / 2
                cy = (bounds[1] + bounds[3]) / 2
                cr.translate(
                    dx + dw / 2 + settings.offset_x - cx * scale,
                    dy + dh / 2 + settings.offset_y - cy * scale,
                )
            cr.scale(scale, scale)
            cr.set_source_rgb(0, 0, 0)
            with _print_state(
                canvas,
                level.id,
                settings.hidden_layer_ids,
                scale,
                line_weights=settings.line_weights,
            ) as ppi:
                _draw_model(canvas, cr, scale, ppi)
    finally:
        cr.restore()

    is_tiled = tile is not None and (tile.rows > 1 or tile.cols > 1)
    if is_tiled and tile is not None and settings.tile_registration_marks:
        _draw_tile_registration_marks(cr, layout.draw_rect, tile)

    # Border and title block
    fx, fy, fw, fh = layout.frame
    if settings.draw_border or settings.title_block.enabled:
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(1.5)
        cr.rectangle(fx, fy, fw, fh)
        cr.stroke()
    tile_tag = f"R{tile.row + 1}C{tile.col + 1}" if (is_tiled and tile is not None) else ""
    if layout.title_rect is not None:
        tb = settings.title_block
        title = level.name
        if tb.drawing_title.strip():
            title = f"{tb.drawing_title.strip()} - {level.name}"
        number = f"{tb.sheet_prefix}-{page_index + 1}" if tb.sheet_prefix else str(page_index + 1)
        if tile_tag and settings.tile_page_numbers:
            number = f"{number} ({tile_tag})"
        draw_title_block(
            cr,
            layout.title_rect,
            settings,
            title,
            number,
            scale_label(settings, scale),
            north_angle=float(getattr(canvas, "north_angle", 0.0)),
        )
    elif tile_tag and settings.tile_page_numbers:
        _draw_tile_badge(cr, layout.frame, f"{tile_tag} ({page_index + 1}/{page_count})")
    return layout


def render_tile_overview(
    cr: cairo.Context,
    canvas,
    settings: PrintSettings,
    level,
    bounds: Optional[Bounds],
    active_tile: Optional[TileSpec],
    view_w: float,
    view_h: float,
) -> List[Tuple[TileSpec, Rect]]:
    """Render full-plan tile grid overview in widget pixels and return hit rects per tile."""
    layout = compute_layout(settings)
    scale = compute_scale(settings, bounds, layout.draw_rect)
    overlap_pt = max(0.0, float(settings.tile_overlap_in)) * 72.0
    tiles = compute_tile_grid(
        bounds,
        scale,
        layout.draw_rect,
        overlap_pt,
        offset_x=settings.offset_x,
        offset_y=settings.offset_y,
    )
    if not tiles:
        return []

    first = tiles[0]
    _dx, _dy, dw, dh = layout.draw_rect
    total_w_pt = dw + (first.cols - 1) * first.step_x_pt
    total_h_pt = dh + (first.rows - 1) * first.step_y_pt
    pad = 24.0
    k = min((view_w - 2 * pad) / max(total_w_pt, 1.0), (view_h - 2 * pad) / max(total_h_pt, 1.0))
    if k <= 0.0:
        return []

    ox = (view_w - total_w_pt * k) / 2.0
    oy = (view_h - total_h_pt * k) / 2.0

    # Paper backdrop for the stitched sheet mosaic
    cr.set_source_rgb(1.0, 1.0, 1.0)
    cr.rectangle(ox, oy, total_w_pt * k, total_h_pt * k)
    cr.fill()

    if bounds is not None:
        cr.save()
        try:
            cr.rectangle(ox, oy, total_w_pt * k, total_h_pt * k)
            cr.clip()
            cr.translate(
                ox - first.grid_x0_model * scale * k,
                oy - first.grid_y0_model * scale * k,
            )
            cr.scale(scale * k, scale * k)
            cr.set_source_rgb(0.0, 0.0, 0.0)
            with _print_state(
                canvas,
                level.id,
                settings.hidden_layer_ids,
                scale * k,
                line_weights=settings.line_weights,
            ) as ppi:
                _draw_model(canvas, cr, scale * k, ppi)
        finally:
            cr.restore()

    hit_rects: List[Tuple[TileSpec, Rect]] = []
    cr.save()
    try:
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        for tile in tiles:
            tx = ox + tile.col * tile.step_x_pt * k
            ty = oy + tile.row * tile.step_y_pt * k
            tw = dw * k
            th = dh * k
            hit_rects.append((tile, (tx, ty, tw, th)))

            is_active = active_tile is not None and (active_tile.row, active_tile.col) == (tile.row, tile.col)
            if is_active:
                cr.set_source_rgba(0.15, 0.50, 0.95, 0.14)
                cr.rectangle(tx, ty, tw, th)
                cr.fill()

            cr.set_source_rgba(0.10, 0.45, 0.88, 0.95 if is_active else 0.55)
            cr.set_line_width(2.2 if is_active else 1.0)
            cr.set_dash([] if is_active else [5.0, 3.0])
            cr.rectangle(tx, ty, tw, th)
            cr.stroke()

            label = f"R{tile.row + 1}C{tile.col + 1}"
            cr.set_font_size(max(9.0, min(14.0, min(tw, th) * 0.14)))
            ext = cr.text_extents(label)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.85)
            cr.rectangle(tx + 4.0, ty + 4.0, ext.width + 8.0, ext.height + 6.0)
            cr.fill()
            cr.set_source_rgba(0.08, 0.32, 0.72, 1.0)
            cr.move_to(tx + 8.0 - ext.x_bearing, ty + 7.0 + ext.height)
            cr.show_text(label)
    finally:
        cr.restore()
    return hit_rects


def export_pdf(
    canvas,
    settings: PrintSettings,
    path: str,
    levels: Optional[List] = None,
    bounds_cache: Optional[Dict[Tuple[str, Tuple[str, ...]], Optional[Bounds]]] = None,
) -> int:
    """Write the selected levels (and tiles when enabled) to a multi-page PDF. Returns sheet count."""
    sheets = resolve_sheets(canvas, settings, levels=levels, bounds_cache=bounds_cache)
    if not sheets:
        raise ValueError("No levels selected to print.")
    pw, ph = settings.page_size()
    surface = cairo.PDFSurface(path, pw, ph)
    try:
        cr = cairo.Context(surface)
        for sheet in sheets:
            surface.set_size(pw, ph)
            cr.save()
            cr.set_source_rgb(1, 1, 1)
            cr.paint()
            cr.restore()
            bounds = _get_cached_bounds(
                canvas, getattr(sheet.level, "id"), settings, bounds_cache
            )
            render_page(
                cr,
                canvas,
                settings,
                sheet.level,
                sheet.sheet_index,
                sheet.sheet_count,
                bounds=bounds,
                measure=False,
                tile=sheet.tile,
            )
            cr.show_page()
    finally:
        surface.finish()
    return len(sheets)


def _svg_level_slug(name: str, index: int) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip()).strip("_")
    return slug or f"level_{index + 1}"


def export_svg(
    canvas,
    settings: PrintSettings,
    path: str,
    levels: Optional[List] = None,
    bounds_cache: Optional[Dict[Tuple[str, Tuple[str, ...]], Optional[Bounds]]] = None,
) -> List[str]:
    """Write the selected levels (and tiles when enabled) to scaled vector SVG file(s)."""
    sheets = resolve_sheets(canvas, settings, levels=levels, bounds_cache=bounds_cache)
    if not sheets:
        raise ValueError("No levels selected to export.")
    pw, ph = settings.page_size()

    if len(sheets) == 1:
        out_paths = [path]
    else:
        root, ext = os.path.splitext(path)
        ext = ext or ".svg"
        seen = set()
        out_paths = []
        for sheet in sheets:
            slug = _svg_level_slug(getattr(sheet.level, "name", ""), sheet.level_index)
            if sheet.tile is not None:
                slug = f"{slug}_R{sheet.tile.row + 1}C{sheet.tile.col + 1}"
            if slug in seen:
                slug = f"{slug}_{sheet.sheet_index + 1}"
            seen.add(slug)
            out_paths.append(f"{root}_{slug}{ext}")

    for sheet, out_path in zip(sheets, out_paths):
        surface = cairo.SVGSurface(out_path, pw, ph)
        if hasattr(surface, "set_document_unit") and hasattr(cairo, "SVGUnit"):
            surface.set_document_unit(cairo.SVGUnit.PT)
        try:
            cr = cairo.Context(surface)
            cr.save()
            cr.set_source_rgb(1, 1, 1)
            cr.paint()
            cr.restore()
            bounds = _get_cached_bounds(
                canvas, getattr(sheet.level, "id"), settings, bounds_cache
            )
            render_page(
                cr,
                canvas,
                settings,
                sheet.level,
                sheet.sheet_index,
                sheet.sheet_count,
                bounds=bounds,
                measure=False,
                tile=sheet.tile,
            )
        finally:
            surface.finish()
    return out_paths
