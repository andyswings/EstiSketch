"""GTK4 physical printer bridge reusing ``print_renderer`` sheet layout."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from . import print_renderer as pr  # noqa: E402
from .print_settings import DEFAULT_PAPER, PAPER_SIZES, PrintSettings  # noqa: E402

GTK_STANDARD_PAPER_NAMES: Dict[str, str] = {
    "Letter (8.5 x 11 in)": Gtk.PAPER_NAME_LETTER,
    "Legal (8.5 x 14 in)": Gtk.PAPER_NAME_LEGAL,
    "Tabloid / ANSI B (11 x 17 in)": "na_ledger",
    "A4 (210 x 297 mm)": Gtk.PAPER_NAME_A4,
    "A3 (297 x 420 mm)": Gtk.PAPER_NAME_A3,
    "A2 (420 x 594 mm)": "iso_a2",
    "A1 (594 x 841 mm)": "iso_a1",
    "A0 (841 x 1189 mm)": "iso_a0",
}


def _custom_paper_id(paper_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", paper_name.lower()).strip("_")
    return f"estisketch_{slug or 'custom'}"


def paper_size_for_name(paper_name: str) -> Gtk.PaperSize:
    """Map an EstiSketch ``PAPER_SIZES`` key to a ``Gtk.PaperSize`` (standard or custom)."""
    std_name = GTK_STANDARD_PAPER_NAMES.get(paper_name)
    if std_name:
        return Gtk.PaperSize.new(std_name)
    w_pt, h_pt = PAPER_SIZES.get(paper_name, PAPER_SIZES[DEFAULT_PAPER])
    return Gtk.PaperSize.new_custom(
        _custom_paper_id(paper_name),
        paper_name,
        float(w_pt),
        float(h_pt),
        Gtk.Unit.POINTS,
    )


def build_page_setup(settings: PrintSettings) -> Gtk.PageSetup:
    """Create a ``Gtk.PageSetup`` in points with orientation and zero hardware margins."""
    setup = Gtk.PageSetup.new()
    setup.set_paper_size(paper_size_for_name(settings.paper))
    setup.set_orientation(
        Gtk.PageOrientation.LANDSCAPE
        if settings.landscape
        else Gtk.PageOrientation.PORTRAIT
    )
    # render_page manages settings.margin_in internally on full-page point coordinates.
    setup.set_top_margin(0.0, Gtk.Unit.POINTS)
    setup.set_bottom_margin(0.0, Gtk.Unit.POINTS)
    setup.set_left_margin(0.0, Gtk.Unit.POINTS)
    setup.set_right_margin(0.0, Gtk.Unit.POINTS)
    return setup


def page_size_from_setup(page_setup: Gtk.PageSetup) -> Tuple[float, float]:
    """Return orientation-aware ``(width_pt, height_pt)`` from a ``Gtk.PageSetup``."""
    return (
        float(page_setup.get_paper_width(Gtk.Unit.POINTS)),
        float(page_setup.get_paper_height(Gtk.Unit.POINTS)),
    )


@dataclass
class PrintJobState:
    """Resolved print job state shared between ``begin-print`` and ``draw-page``."""

    canvas: object
    settings: PrintSettings
    levels: List[object]
    bounds_cache: Dict[Tuple[str, Tuple[str, ...]], Optional[pr.Bounds]] = field(
        default_factory=dict
    )
    sheets: List[pr.PrintSheet] = field(default_factory=list)
    actual_page_size: Optional[Tuple[float, float]] = None


def prepare_print_operation(
    canvas: object,
    settings: PrintSettings,
    levels: Optional[List[object]] = None,
    bounds_cache: Optional[Dict[Tuple[str, Tuple[str, ...]], Optional[pr.Bounds]]] = None,
    job_name: str = "EstiSketch Drawing",
    gtk_print_settings: Optional[Gtk.PrintSettings] = None,
) -> Tuple[Gtk.PrintOperation, PrintJobState]:
    """Build and connect a ``Gtk.PrintOperation`` configured for full-page point rendering."""
    resolved_levels = list(levels) if levels is not None else pr.resolve_levels(canvas, settings)
    state = PrintJobState(
        canvas=canvas,
        settings=settings,
        levels=resolved_levels,
        bounds_cache=bounds_cache if bounds_cache is not None else {},
    )

    op = Gtk.PrintOperation.new()
    op.set_unit(Gtk.Unit.POINTS)
    op.set_use_full_page(True)
    op.set_embed_page_setup(True)
    op.set_default_page_setup(build_page_setup(settings))
    op.set_job_name(job_name or "EstiSketch Drawing")
    if gtk_print_settings is not None:
        op.set_print_settings(gtk_print_settings)

    def _on_begin_print(operation: Gtk.PrintOperation, context: Gtk.PrintContext) -> None:
        setup = context.get_page_setup()
        actual_size = page_size_from_setup(setup)
        state.actual_page_size = actual_size
        state.sheets = pr.resolve_sheets(
            state.canvas,
            state.settings,
            levels=state.levels,
            bounds_cache=state.bounds_cache,
            page_size_override=actual_size,
        )
        operation.set_n_pages(max(1, len(state.sheets)))

    def _on_draw_page(
        _operation: Gtk.PrintOperation,
        context: Gtk.PrintContext,
        page_nr: int,
    ) -> None:
        if page_nr < 0 or page_nr >= len(state.sheets):
            return
        sheet = state.sheets[page_nr]
        cr = context.get_cairo_context()
        actual_size = state.actual_page_size or page_size_from_setup(context.get_page_setup())
        bounds = pr._get_cached_bounds(
            state.canvas,
            getattr(sheet.level, "id"),
            state.settings,
            state.bounds_cache,
        )
        pr.render_page(
            cr,
            state.canvas,
            state.settings,
            sheet.level,
            sheet.sheet_index,
            sheet.sheet_count,
            bounds=bounds,
            measure=False,
            tile=sheet.tile,
            page_size_override=actual_size,
        )

    op.connect("begin-print", _on_begin_print)
    op.connect("draw-page", _on_draw_page)
    return op, state


def run_print_dialog(
    parent: Optional[Gtk.Window],
    canvas: object,
    settings: PrintSettings,
    levels: Optional[List[object]] = None,
    bounds_cache: Optional[Dict[Tuple[str, Tuple[str, ...]], Optional[pr.Bounds]]] = None,
    job_name: str = "EstiSketch Drawing",
    gtk_print_settings: Optional[Gtk.PrintSettings] = None,
) -> Tuple[str, int, Optional[Gtk.PrintSettings]]:
    """Show the system print dialog and render pages via ``Gtk.PrintOperation``."""
    op, state = prepare_print_operation(
        canvas=canvas,
        settings=settings,
        levels=levels,
        bounds_cache=bounds_cache,
        job_name=job_name,
        gtk_print_settings=gtk_print_settings,
    )
    try:
        result = op.run(Gtk.PrintOperationAction.PRINT_DIALOG, parent)
    except Exception as exc:
        return (f"Print failed: {exc}", 0, gtk_print_settings)

    if result == Gtk.PrintOperationResult.APPLY:
        count = len(state.sheets)
        return (f"Sent {count} sheet(s) to printer.", count, op.get_print_settings())
    if result == Gtk.PrintOperationResult.IN_PROGRESS:
        count = len(state.sheets)
        return (f"Printing {count} sheet(s)...", count, op.get_print_settings())
    if result == Gtk.PrintOperationResult.CANCEL:
        return ("Print cancelled.", 0, gtk_print_settings)
    return ("Print failed.", 0, gtk_print_settings)
