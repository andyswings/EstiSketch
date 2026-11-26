"""Print / PDF / SVG export dialog with live preview, line weights, and tiling."""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import gtk_printer  # noqa: E402
from . import print_renderer as pr  # noqa: E402
from .print_settings import (  # noqa: E402
    FIT_SCALE,
    LINE_WEIGHT_CATEGORIES,
    LINE_WEIGHT_PRESETS,
    PAPER_SIZES,
    PrintSettings,
    SCALES,
)

_PAPER_NAMES = list(PAPER_SIZES.keys())
_SCALE_NAMES = list(SCALES.keys())
_LW_PRESET_NAMES = list(LINE_WEIGHT_PRESETS.keys()) + ["Custom"]
_TB_FIELDS = [
    ("company", "Company"), ("project_name", "Project name"),
    ("address", "Address"), ("client", "Client"),
    ("job_number", "Job number"), ("drawn_by", "Drawn by"),
    ("checked_by", "Checked by"), ("date", "Date (blank = today)"),
    ("revision", "Revision"), ("drawing_title", "Drawing title"),
    ("sheet_prefix", "Sheet number prefix"),
]


class PrintDialog(Gtk.Window):
    def __init__(self, parent, canvas, default_name: str = "", on_settings_changed=None):
        super().__init__(title="Print / Export PDF & SVG", transient_for=parent, modal=True)
        self.set_default_size(1140, 740)
        self.canvas = canvas
        self.default_name = default_name or "drawing"
        self.on_settings_changed = on_settings_changed
        self.settings: PrintSettings = PrintSettings.from_dict(
            getattr(canvas, "print_settings", None))
        if not self.settings.title_block.project_name:
            self.settings.title_block.project_name = default_name
        self.page_index = 0
        self._sheets: List[pr.PrintSheet] = []
        self._bounds_cache: Dict[Tuple[str, Tuple[str, ...]], Optional[pr.Bounds]] = {}
        self._overview_tile_rects: List[Tuple[pr.TileSpec, pr.Rect]] = []
        self._gtk_print_settings: Optional[Gtk.PrintSettings] = None
        self._drag_start = (0.0, 0.0)
        self._preview_scale = 1.0
        self._building = True

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_child(root)
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        body.set_vexpand(True)
        root.append(body)

        notebook = Gtk.Notebook()
        notebook.set_size_request(360, -1)
        notebook.append_page(self._build_page_tab(), Gtk.Label(label="Page"))
        notebook.append_page(self._build_line_weights_tab(), Gtk.Label(label="Line Weights"))
        notebook.append_page(self._build_content_tab(), Gtk.Label(label="Levels & Layers"))
        notebook.append_page(self._build_title_tab(), Gtk.Label(label="Title Block"))
        body.append(notebook)
        body.append(self._build_preview())

        # Bottom bar
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(bar, f"set_margin_{side}")(8)
        self.status = Gtk.Label(label="", xalign=0, hexpand=True)
        bar.append(self.status)
        cancel = Gtk.Button(label="Close")
        cancel.connect("clicked", lambda b: self.close())
        print_btn = Gtk.Button(label="Print...")
        print_btn.connect("clicked", self._on_print)
        self.print_btn = print_btn
        export_svg = Gtk.Button(label="Export SVG...")
        export_svg.connect("clicked", self._on_export_svg)
        self.export_svg_btn = export_svg
        export = Gtk.Button(label="Export PDF...")
        export.add_css_class("suggested-action")
        export.connect("clicked", self._on_export)
        bar.append(cancel)
        bar.append(print_btn)
        bar.append(export_svg)
        bar.append(export)
        root.append(bar)

        self.connect("close-request", self._on_close)
        self._pull_settings()
        self._initial_settings_dict = self.settings.to_dict()
        self._building = False
        self._refresh_pages()

    # ------------------------------------------------------------------ UI
    @staticmethod
    def _tab_box() -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(10)
        return box

    @staticmethod
    def _row(label: str, widget: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lab = Gtk.Label(label=label, xalign=0)
        lab.set_size_request(130, -1)
        widget.set_hexpand(True)
        row.append(lab)
        row.append(widget)
        return row

    def _build_page_tab(self) -> Gtk.Widget:
        s = self.settings
        box = self._tab_box()

        self.paper_dd = Gtk.DropDown.new_from_strings(_PAPER_NAMES)
        self.paper_dd.set_selected(_PAPER_NAMES.index(s.paper))
        self.paper_dd.connect("notify::selected", self._on_changed)
        box.append(self._row("Paper size", self.paper_dd))

        self.orient_dd = Gtk.DropDown.new_from_strings(["Portrait", "Landscape"])
        self.orient_dd.set_selected(1 if s.landscape else 0)
        self.orient_dd.connect("notify::selected", self._on_changed)
        box.append(self._row("Orientation", self.orient_dd))

        self.margin_spin = Gtk.SpinButton.new_with_range(0.0, 3.0, 0.05)
        self.margin_spin.set_digits(2)
        self.margin_spin.set_value(s.margin_in)
        self.margin_spin.connect("value-changed", self._on_changed)
        box.append(self._row("Margins (in)", self.margin_spin))

        self.scale_dd = Gtk.DropDown.new_from_strings(_SCALE_NAMES)
        self.scale_dd.set_selected(_SCALE_NAMES.index(s.scale_name))
        self.scale_dd.connect("notify::selected", self._on_changed)
        box.append(self._row("Scale", self.scale_dd))

        self.border_chk = Gtk.CheckButton(label="Draw border")
        self.border_chk.set_active(s.draw_border)
        self.border_chk.connect("toggled", self._on_changed)
        box.append(self.border_chk)

        center = Gtk.Button(label="Re-center drawing")
        center.connect("clicked", self._on_recenter)
        box.append(center)
        hint = Gtk.Label(
            label="Tip: drag the drawing in the preview to nudge its position on the sheet.",
            xalign=0,
            wrap=True,
        )
        hint.add_css_class("dim-label")
        box.append(hint)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        tile_hdr = Gtk.Label(label="Multi-Page Tiling", xalign=0)
        tile_hdr.add_css_class("heading")
        box.append(tile_hdr)

        self.tile_chk = Gtk.CheckButton(label="Tile oversized drawing across pages")
        self.tile_chk.set_active(s.tile_enabled)
        self.tile_chk.connect("toggled", self._on_changed)
        box.append(self.tile_chk)

        self.tile_overlap_spin = Gtk.SpinButton.new_with_range(0.0, 2.0, 0.125)
        self.tile_overlap_spin.set_digits(2)
        self.tile_overlap_spin.set_value(s.tile_overlap_in)
        self.tile_overlap_spin.connect("value-changed", self._on_changed)
        box.append(self._row("Overlap (in)", self.tile_overlap_spin))

        self.tile_marks_chk = Gtk.CheckButton(label="Overlap trim & registration marks")
        self.tile_marks_chk.set_active(s.tile_registration_marks)
        self.tile_marks_chk.connect("toggled", self._on_changed)
        box.append(self.tile_marks_chk)

        self.tile_labels_chk = Gtk.CheckButton(label="Tile coordinates on sheets (R1C1)")
        self.tile_labels_chk.set_active(s.tile_page_numbers)
        self.tile_labels_chk.connect("toggled", self._on_changed)
        box.append(self.tile_labels_chk)

        self.tile_hint = Gtk.Label(
            label="Select a fixed architectural or metric scale to enable tiling.",
            xalign=0,
            wrap=True,
        )
        self.tile_hint.add_css_class("dim-label")
        box.append(self.tile_hint)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(box)
        return scroll

    def _build_line_weights_tab(self) -> Gtk.Widget:
        lw = self.settings.line_weights
        box = self._tab_box()

        preset_idx = (
            _LW_PRESET_NAMES.index(lw.preset)
            if lw.preset in _LW_PRESET_NAMES
            else 0
        )
        self.lw_preset_dd = Gtk.DropDown.new_from_strings(_LW_PRESET_NAMES)
        self.lw_preset_dd.set_selected(preset_idx)
        self.lw_preset_dd.connect("notify::selected", self._on_lw_preset_changed)
        box.append(self._row("Preset", self.lw_preset_dd))

        self.lw_mult_spin = Gtk.SpinButton.new_with_range(0.10, 5.00, 0.05)
        self.lw_mult_spin.set_digits(2)
        self.lw_mult_spin.set_value(lw.global_multiplier)
        self.lw_mult_spin.connect("value-changed", self._on_lw_custom_changed)
        box.append(self._row("Global multiplier", self.lw_mult_spin))

        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        pen_hdr = Gtk.Label(label="Pen Weights (PostScript pt)", xalign=0)
        pen_hdr.add_css_class("heading")
        box.append(pen_hdr)

        self.lw_spins: Dict[str, Gtk.SpinButton] = {}
        for key, label, default_pt in LINE_WEIGHT_CATEGORIES:
            spin = Gtk.SpinButton.new_with_range(0.05, 5.00, 0.05)
            spin.set_digits(2)
            spin.set_value(float(getattr(lw, key, default_pt)))
            spin.connect("value-changed", self._on_lw_custom_changed)
            self.lw_spins[key] = spin
            box.append(self._row(label, spin))

        note = Gtk.Label(
            label="Line weights apply to plotted output (PDF, SVG, printer) at true physical "
                  "points regardless of drawing scale; structural wall thicknesses stay true to scale.",
            xalign=0,
            wrap=True,
        )
        note.add_css_class("dim-label")
        box.append(note)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(box)
        return scroll

    def _build_content_tab(self) -> Gtk.Widget:
        s = self.settings
        box = self._tab_box()
        self.all_chk = Gtk.CheckButton(label="Print all levels (one page per level)")
        self.all_chk.set_active(s.print_all_levels)
        self.all_chk.connect("toggled", self._on_all_toggled)
        box.append(self.all_chk)

        box.append(Gtk.Label(label="Levels", xalign=0))
        self.level_checks: Dict[str, Gtk.CheckButton] = {}
        selected = set(s.level_ids) or {lv.id for lv in self.canvas.levels}
        for lv in self.canvas.levels:
            chk = Gtk.CheckButton(label=lv.name)
            chk.set_active(lv.id in selected)
            chk.set_sensitive(not s.print_all_levels)
            chk.connect("toggled", self._on_changed)
            self.level_checks[lv.id] = chk
            box.append(chk)

        box.append(Gtk.Label(label="Layers (unchecked layers are not printed)", xalign=0))
        self.layer_checks: Dict[str, Gtk.CheckButton] = {}
        names = {lv.id: lv.name for lv in self.canvas.levels}
        hidden = set(s.hidden_layer_ids)
        for layer in self.canvas.layers:
            where = names.get(layer.level_id, "Global")
            chk = Gtk.CheckButton(label=f"{layer.name}  ({where})")
            chk.set_active(layer.id not in hidden)
            chk.connect("toggled", self._on_changed)
            self.layer_checks[layer.id] = chk
            box.append(chk)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(box)
        return scroll

    def _build_title_tab(self) -> Gtk.Widget:
        box = self._tab_box()
        tb = self.settings.title_block
        self.tb_enable = Gtk.CheckButton(label="Include title block")
        self.tb_enable.set_active(tb.enabled)
        self.tb_enable.connect("toggled", self._on_changed)
        box.append(self.tb_enable)
        self.tb_entries: Dict[str, Gtk.Entry] = {}
        for key, label in _TB_FIELDS:
            entry = Gtk.Entry()
            entry.set_text(str(getattr(tb, key)))
            entry.connect("changed", self._on_changed)
            self.tb_entries[key] = entry
            box.append(self._row(label, entry))
        note = Gtk.Label(
            label="Sheet title and scale are filled in automatically.",
            xalign=0,
            wrap=True,
        )
        note.add_css_class("dim-label")
        box.append(note)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(box)
        return scroll

    def _build_preview(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_hexpand(True)
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nav.set_halign(Gtk.Align.CENTER)
        self.prev_btn = Gtk.Button(label="◀")
        self.next_btn = Gtk.Button(label="▶")
        self.page_label = Gtk.Label(label="")
        self.tile_overview_btn = Gtk.ToggleButton(label="Tile Grid")
        self.tile_overview_btn.set_sensitive(False)
        self.prev_btn.connect("clicked", lambda b: self._goto(self.page_index - 1))
        self.next_btn.connect("clicked", lambda b: self._goto(self.page_index + 1))
        self.tile_overview_btn.connect("toggled", lambda b: self.preview.queue_draw())
        nav.append(self.prev_btn)
        nav.append(self.page_label)
        nav.append(self.next_btn)
        nav.append(self.tile_overview_btn)
        box.append(nav)

        self.preview = Gtk.DrawingArea()
        self.preview.set_hexpand(True)
        self.preview.set_vexpand(True)
        self.preview.set_draw_func(self._draw_preview)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        self.preview.add_controller(drag)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_preview_click)
        self.preview.add_controller(click)

        box.append(self.preview)
        return box

    # ------------------------------------------------------------ settings
    def _sync_tiling_sensitivity(self) -> None:
        is_fixed_scale = self.settings.scale_name != FIT_SCALE
        self.tile_chk.set_sensitive(is_fixed_scale)
        tiling_active = is_fixed_scale and self.tile_chk.get_active()
        self.tile_overlap_spin.set_sensitive(tiling_active)
        self.tile_marks_chk.set_sensitive(tiling_active)
        self.tile_labels_chk.set_sensitive(tiling_active)
        self.tile_hint.set_visible(not is_fixed_scale)

    def _pull_settings(self) -> None:
        s = self.settings
        s.paper = _PAPER_NAMES[self.paper_dd.get_selected()]
        s.landscape = self.orient_dd.get_selected() == 1
        s.margin_in = self.margin_spin.get_value()
        s.scale_name = _SCALE_NAMES[self.scale_dd.get_selected()]
        s.draw_border = self.border_chk.get_active()
        s.tile_enabled = self.tile_chk.get_active()
        s.tile_overlap_in = self.tile_overlap_spin.get_value()
        s.tile_registration_marks = self.tile_marks_chk.get_active()
        s.tile_page_numbers = self.tile_labels_chk.get_active()
        s.print_all_levels = self.all_chk.get_active()
        s.level_ids = [i for i, c in self.level_checks.items() if c.get_active()]
        s.hidden_layer_ids = [i for i, c in self.layer_checks.items() if not c.get_active()]
        s.title_block.enabled = self.tb_enable.get_active()
        for key, entry in self.tb_entries.items():
            setattr(s.title_block, key, entry.get_text())
        s.line_weights.preset = _LW_PRESET_NAMES[self.lw_preset_dd.get_selected()]
        s.line_weights.global_multiplier = self.lw_mult_spin.get_value()
        for key, spin in self.lw_spins.items():
            setattr(s.line_weights, key, spin.get_value())

    def _on_changed(self, *args) -> None:
        if self._building:
            return
        self._pull_settings()
        self._sync_tiling_sensitivity()
        self._refresh_pages()

    def _on_lw_preset_changed(self, *args) -> None:
        if self._building:
            return
        preset = _LW_PRESET_NAMES[self.lw_preset_dd.get_selected()]
        if preset in LINE_WEIGHT_PRESETS:
            self._building = True
            try:
                self.settings.line_weights.apply_preset(preset)
                self.lw_mult_spin.set_value(self.settings.line_weights.global_multiplier)
                for key, spin in self.lw_spins.items():
                    spin.set_value(float(getattr(self.settings.line_weights, key)))
            finally:
                self._building = False
        self._bounds_cache.clear()
        self._pull_settings()
        self._refresh_pages()

    def _on_lw_custom_changed(self, *args) -> None:
        if self._building:
            return
        self._building = True
        try:
            custom_idx = _LW_PRESET_NAMES.index("Custom")
            if self.lw_preset_dd.get_selected() != custom_idx:
                self.lw_preset_dd.set_selected(custom_idx)
        finally:
            self._building = False
        self._bounds_cache.clear()
        self._pull_settings()
        self._refresh_pages()

    def _on_all_toggled(self, chk) -> None:
        for c in self.level_checks.values():
            c.set_sensitive(not chk.get_active())
        self._on_changed()

    def _on_recenter(self, *args) -> None:
        self.settings.offset_x = self.settings.offset_y = 0.0
        self._refresh_pages()

    def _levels(self):
        return pr.resolve_levels(self.canvas, self.settings)

    def _refresh_pages(self) -> None:
        self._sync_tiling_sensitivity()
        levels = self._levels()
        self._sheets = pr.resolve_sheets(
            self.canvas,
            self.settings,
            levels=levels,
            bounds_cache=self._bounds_cache,
        )
        if not self._sheets:
            self.page_index = 0
            self.page_label.set_text("No levels selected")
            self.prev_btn.set_sensitive(False)
            self.next_btn.set_sensitive(False)
            self.tile_overview_btn.set_sensitive(False)
            self.tile_overview_btn.set_active(False)
            self.preview.queue_draw()
            return

        self.page_index = max(0, min(self.page_index, len(self._sheets) - 1))
        sheet = self._sheets[self.page_index]
        level_name = getattr(sheet.level, "name", "")
        if sheet.tile is not None:
            tile_str = f"R{sheet.tile.row + 1}C{sheet.tile.col + 1}"
            self.page_label.set_text(
                f"Page {self.page_index + 1} of {len(self._sheets)} — {level_name} ({tile_str})"
            )
            self.tile_overview_btn.set_sensitive(True)
        else:
            self.page_label.set_text(
                f"Page {self.page_index + 1} of {len(self._sheets)} — {level_name}"
            )
            self.tile_overview_btn.set_sensitive(False)
            if self.tile_overview_btn.get_active():
                self.tile_overview_btn.set_active(False)

        self.prev_btn.set_sensitive(self.page_index > 0)
        self.next_btn.set_sensitive(self.page_index < len(self._sheets) - 1)
        self.preview.queue_draw()

    def _goto(self, idx: int) -> None:
        self.page_index = idx
        self._refresh_pages()

    # ------------------------------------------------------------- preview
    def _bounds(self, level) -> Optional[pr.Bounds]:
        return pr._get_cached_bounds(
            self.canvas, level.id, self.settings, self._bounds_cache
        )

    def _draw_preview(self, area, cr, width, height) -> None:
        cr.set_source_rgb(0.55, 0.55, 0.58)
        cr.paint()
        if not self._sheets:
            return
        sheet = self._sheets[self.page_index]
        level = sheet.level
        bounds = self._bounds(level)

        if self.tile_overview_btn.get_active() and sheet.tile is not None:
            self._overview_tile_rects = pr.render_tile_overview(
                cr,
                self.canvas,
                self.settings,
                level,
                bounds,
                sheet.tile,
                float(width),
                float(height),
            )
            return

        self._overview_tile_rects = []
        pw, ph = self.settings.page_size()
        k = min((width - 40) / pw, (height - 40) / ph)
        if k <= 0:
            return
        self._preview_scale = k
        ox, oy = (width - pw * k) / 2, (height - ph * k) / 2
        # Shadow + paper
        cr.set_source_rgba(0, 0, 0, 0.3)
        cr.rectangle(ox + 4, oy + 4, pw * k, ph * k)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.rectangle(ox, oy, pw * k, ph * k)
        cr.fill()
        cr.save()
        try:
            cr.translate(ox, oy)
            cr.scale(k, k)
            layout = pr.render_page(
                cr,
                self.canvas,
                self.settings,
                level,
                sheet.sheet_index,
                sheet.sheet_count,
                bounds=bounds,
                measure=False,
                tile=sheet.tile,
            )
            # Printable-margin guide (preview only)
            fx, fy, fw, fh = layout.frame
            cr.set_source_rgba(0.2, 0.5, 1.0, 0.6)
            cr.set_line_width(1.0 / k)
            cr.set_dash([4 / k, 4 / k])
            cr.rectangle(fx, fy, fw, fh)
            cr.stroke()
        finally:
            cr.restore()

    def _on_preview_click(self, _gesture, n_press: int, x: float, y: float) -> None:
        if not self.tile_overview_btn.get_active() or not self._overview_tile_rects:
            return
        if not self._sheets:
            return
        cur_level_id = getattr(self._sheets[self.page_index].level, "id", None)
        for tile, (rx, ry, rw, rh) in self._overview_tile_rects:
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                for idx, sheet in enumerate(self._sheets):
                    same_level = getattr(sheet.level, "id", None) == cur_level_id
                    if same_level and sheet.tile is not None:
                        if sheet.tile.row == tile.row and sheet.tile.col == tile.col:
                            self.page_index = idx
                            if n_press >= 2:
                                self.tile_overview_btn.set_active(False)
                            self._refresh_pages()
                            return

    def _on_drag_begin(self, gesture, x, y) -> None:
        self._drag_start = (self.settings.offset_x, self.settings.offset_y)

    def _on_drag_update(self, gesture, dx, dy) -> None:
        if self.tile_overview_btn.get_active():
            return
        k = self._preview_scale or 1.0
        self.settings.offset_x = self._drag_start[0] + dx / k
        self.settings.offset_y = self._drag_start[1] + dy / k
        self._refresh_pages()

    # -------------------------------------------------------------- export & print
    def _on_print(self, *args) -> None:
        self._pull_settings()
        levels = self._levels()
        if not levels:
            self.status.set_text("Select at least one level to print.")
            return
        base = os.path.splitext(os.path.basename(self.default_name))[0] or "EstiSketch Drawing"
        msg, _count, new_ps = gtk_printer.run_print_dialog(
            parent=self,
            canvas=self.canvas,
            settings=self.settings,
            levels=levels,
            bounds_cache=self._bounds_cache,
            job_name=base,
            gtk_print_settings=self._gtk_print_settings,
        )
        if new_ps is not None:
            self._gtk_print_settings = new_ps
        self.status.set_text(msg)

    def _on_export(self, *args) -> None:
        self._pull_settings()
        if not self._levels():
            self.status.set_text("Select at least one level to print.")
            return
        dlg = Gtk.FileDialog()
        dlg.set_title("Export PDF")
        base = os.path.splitext(os.path.basename(self.default_name))[0] or "drawing"
        dlg.set_initial_name(f"{base}.pdf")
        flt = Gtk.FileFilter()
        flt.set_name("PDF files")
        flt.add_pattern("*.pdf")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(flt)
        dlg.set_filters(store)
        dlg.save(self, None, self._on_export_done)

    def _on_export_done(self, dlg, result) -> None:
        try:
            gfile = dlg.save_finish(result)
        except GLib.Error:
            return
        if gfile is None:
            return
        path = gfile.get_path()
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            n = pr.export_pdf(
                self.canvas,
                self.settings,
                path,
                self._levels(),
                bounds_cache=self._bounds_cache,
            )
            self.status.set_text(f"Saved {n} page(s) to {path}")
        except Exception as exc:  # report, don't crash the app
            self.status.set_text(f"Export failed: {exc}")

    def _on_export_svg(self, *args) -> None:
        self._pull_settings()
        if not self._levels():
            self.status.set_text("Select at least one level to export.")
            return
        dlg = Gtk.FileDialog()
        dlg.set_title("Export SVG")
        base = os.path.splitext(os.path.basename(self.default_name))[0] or "drawing"
        dlg.set_initial_name(f"{base}.svg")
        flt = Gtk.FileFilter()
        flt.set_name("SVG vector files")
        flt.add_pattern("*.svg")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(flt)
        dlg.set_filters(store)
        dlg.save(self, None, self._on_export_svg_done)

    def _on_export_svg_done(self, dlg, result) -> None:
        try:
            gfile = dlg.save_finish(result)
        except GLib.Error:
            return
        if gfile is None:
            return
        path = gfile.get_path()
        if not path.lower().endswith(".svg"):
            path += ".svg"
        try:
            paths = pr.export_svg(
                self.canvas,
                self.settings,
                path,
                self._levels(),
                bounds_cache=self._bounds_cache,
            )
            if len(paths) == 1:
                self.status.set_text(f"Saved SVG to {paths[0]}")
            else:
                self.status.set_text(
                    f"Saved {len(paths)} SVG files (starting with {os.path.basename(paths[0])})"
                )
        except Exception as exc:  # report, don't crash the app
            self.status.set_text(f"SVG export failed: {exc}")

    def _on_close(self, *args) -> bool:
        self._pull_settings()
        new_dict = self.settings.to_dict()
        if new_dict != self._initial_settings_dict:
            self.canvas.print_settings = new_dict
            if self.on_settings_changed:
                self.on_settings_changed()
        return False


def show_print_dialog(parent, canvas, default_name: str = "", on_settings_changed=None) -> PrintDialog:
    dlg = PrintDialog(parent, canvas, default_name, on_settings_changed)
    dlg.present()
    return dlg
