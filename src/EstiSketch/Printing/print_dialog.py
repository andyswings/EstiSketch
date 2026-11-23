"""Print / PDF export dialog with live page preview and fit adjustment."""
from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib  # noqa: E402

from .print_settings import PAPER_SIZES, SCALES, PrintSettings  # noqa: E402
from . import print_renderer as pr  # noqa: E402

_PAPER_NAMES = list(PAPER_SIZES.keys())
_SCALE_NAMES = list(SCALES.keys())
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
        super().__init__(title="Print / Export PDF", transient_for=parent, modal=True)
        self.set_default_size(1100, 720)
        self.canvas = canvas
        self.default_name = default_name or "drawing"
        self.on_settings_changed = on_settings_changed
        self.settings: PrintSettings = PrintSettings.from_dict(
            getattr(canvas, "print_settings", None))
        if not self.settings.title_block.project_name:
            self.settings.title_block.project_name = default_name
        self.page_index = 0
        self._bounds_cache: Dict[Tuple, Optional[tuple]] = {}
        self._drag_start = (0.0, 0.0)
        self._preview_scale = 1.0
        self._building = True

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_child(root)
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        body.set_vexpand(True)
        root.append(body)

        notebook = Gtk.Notebook()
        notebook.set_size_request(340, -1)
        notebook.append_page(self._build_page_tab(), Gtk.Label(label="Page"))
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
        export = Gtk.Button(label="Export PDF...")
        export.add_css_class("suggested-action")
        export.connect("clicked", self._on_export)
        bar.append(cancel)
        bar.append(export)
        root.append(bar)

        self.connect("close-request", self._on_close)
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
        lab.set_size_request(110, -1)
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
        hint = Gtk.Label(label="Tip: drag the drawing in the preview to nudge its position on the sheet.",
                         xalign=0, wrap=True)
        hint.add_css_class("dim-label")
        box.append(hint)
        return box

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
        note = Gtk.Label(label="Sheet title and scale are filled in automatically.",
                         xalign=0, wrap=True)
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
        self.prev_btn.connect("clicked", lambda b: self._goto(self.page_index - 1))
        self.next_btn.connect("clicked", lambda b: self._goto(self.page_index + 1))
        nav.append(self.prev_btn)
        nav.append(self.page_label)
        nav.append(self.next_btn)
        box.append(nav)

        self.preview = Gtk.DrawingArea()
        self.preview.set_hexpand(True)
        self.preview.set_vexpand(True)
        self.preview.set_draw_func(self._draw_preview)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        self.preview.add_controller(drag)
        box.append(self.preview)
        return box

    # ------------------------------------------------------------ settings
    def _pull_settings(self) -> None:
        s = self.settings
        s.paper = _PAPER_NAMES[self.paper_dd.get_selected()]
        s.landscape = self.orient_dd.get_selected() == 1
        s.margin_in = self.margin_spin.get_value()
        s.scale_name = _SCALE_NAMES[self.scale_dd.get_selected()]
        s.draw_border = self.border_chk.get_active()
        s.print_all_levels = self.all_chk.get_active()
        s.level_ids = [i for i, c in self.level_checks.items() if c.get_active()]
        s.hidden_layer_ids = [i for i, c in self.layer_checks.items() if not c.get_active()]
        s.title_block.enabled = self.tb_enable.get_active()
        for key, entry in self.tb_entries.items():
            setattr(s.title_block, key, entry.get_text())

    def _on_changed(self, *args) -> None:
        if self._building:
            return
        self._pull_settings()
        self._refresh_pages()

    def _on_all_toggled(self, chk) -> None:
        for c in self.level_checks.values():
            c.set_sensitive(not chk.get_active())
        self._on_changed()

    def _on_recenter(self, *args) -> None:
        self.settings.offset_x = self.settings.offset_y = 0.0
        self.preview.queue_draw()

    def _levels(self):
        return pr.resolve_levels(self.canvas, self.settings)

    def _refresh_pages(self) -> None:
        levels = self._levels()
        self.page_index = max(0, min(self.page_index, len(levels) - 1))
        self.page_label.set_text(
            f"Page {self.page_index + 1} of {len(levels)}" if levels else "No levels selected")
        self.prev_btn.set_sensitive(self.page_index > 0)
        self.next_btn.set_sensitive(self.page_index < len(levels) - 1)
        self.preview.queue_draw()

    def _goto(self, idx: int) -> None:
        self.page_index = idx
        self._refresh_pages()

    # ------------------------------------------------------------- preview
    def _bounds(self, level):
        key = (level.id, tuple(sorted(self.settings.hidden_layer_ids)))
        if key not in self._bounds_cache:
            self._bounds_cache[key] = pr.content_bounds(
                self.canvas, level.id, self.settings.hidden_layer_ids)
        return self._bounds_cache[key]

    def _draw_preview(self, area, cr, width, height) -> None:
        cr.set_source_rgb(0.55, 0.55, 0.58)
        cr.paint()
        levels = self._levels()
        if not levels:
            return
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
        cr.translate(ox, oy)
        cr.scale(k, k)
        level = levels[self.page_index]
        layout = pr.render_page(cr, self.canvas, self.settings, level, self.page_index,
                                len(levels), bounds=self._bounds(level), measure=False)
        # Printable-margin guide (preview only)
        fx, fy, fw, fh = layout.frame
        cr.set_source_rgba(0.2, 0.5, 1.0, 0.6)
        cr.set_line_width(1.0 / k)
        cr.set_dash([4 / k, 4 / k])
        cr.rectangle(fx, fy, fw, fh)
        cr.stroke()
        cr.restore()

    def _on_drag_begin(self, gesture, x, y) -> None:
        self._drag_start = (self.settings.offset_x, self.settings.offset_y)

    def _on_drag_update(self, gesture, dx, dy) -> None:
        k = self._preview_scale or 1.0
        self.settings.offset_x = self._drag_start[0] + dx / k
        self.settings.offset_y = self._drag_start[1] + dy / k
        self.preview.queue_draw()

    # -------------------------------------------------------------- export
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
            n = pr.export_pdf(self.canvas, self.settings, path, self._levels(),
                              bounds_cache=self._bounds_cache)
            self.status.set_text(f"Saved {n} page(s) to {path}")
        except Exception as exc:  # report, don't crash the app
            self.status.set_text(f"Export failed: {exc}")

    def _on_close(self, *args) -> bool:
        self._pull_settings()
        self.canvas.print_settings = self.settings.to_dict()
        if self.on_settings_changed:
            self.on_settings_changed()
        return False


def show_print_dialog(parent, canvas, default_name: str = "", on_settings_changed=None) -> PrintDialog:
    dlg = PrintDialog(parent, canvas, default_name, on_settings_changed)
    dlg.present()
    return dlg
