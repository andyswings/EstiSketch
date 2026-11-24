"""GTK4 Fixture Browser and Kitchen/Bath Vanity Layout Generator dialogs."""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..Canvas.render_fixtures import draw_fixture_preview_icon
from ..fixtures_catalog import (
    COUNTERTOP_MATERIALS,
    FIXTURE_CATALOG,
    FIXTURE_CATEGORIES,
    LAYOUT_PRESETS,
)


class FixtureBrowserDialog(Gtk.Window):
    """Searchable architectural symbol catalog for selecting and placing a Fixture."""

    def __init__(self, parent, canvas, on_selected=None):
        super().__init__(title="Single Cabinet, Fixture & Appliance Library", transient_for=parent)
        self.set_default_size(520, 480)
        self.canvas = canvas
        self.on_selected = on_selected
        self.selected_symbol = getattr(canvas, "active_fixture_type", "base_cabinet") or "base_cabinet"

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_top(10)
        root.set_margin_bottom(10)
        root.set_margin_start(10)
        root.set_margin_end(10)
        self.set_child(root)

        # Search + Category Filter Row
        filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search cabinets, sinks, appliances...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", lambda _e: self._populate_list())
        filter_row.append(self.search_entry)

        self.cat_combo = Gtk.ComboBoxText()
        self.cat_combo.append("all", "All Categories")
        for key, label in FIXTURE_CATEGORIES:
            self.cat_combo.append(key, label)
        self.cat_combo.set_active_id("all")
        self.cat_combo.connect("changed", lambda _c: self._populate_list())
        filter_row.append(self.cat_combo)
        root.append(filter_row)

        # Scrollable catalog list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-selected", self._on_row_selected)
        self.listbox.connect("row-activated", self._on_row_activated)
        scroll.set_child(self.listbox)
        root.append(scroll)

        # Action footer
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status_lbl = Gtk.Label(
            label="Click any symbol, then click canvas to place (R to rotate, F to show library)",
            xalign=0,
        )
        self.status_lbl.add_css_class("dim-label")
        self.status_lbl.set_hexpand(True)
        footer.append(self.status_lbl)

        self.keep_open_check = Gtk.CheckButton(label="Keep open")
        self.keep_open_check.set_active(True)
        self.keep_open_check.set_tooltip_text("Keep the Fixture Library open so you can switch symbols without reopening it")
        footer.append(self.keep_open_check)

        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda _b: self.close())
        footer.append(close_btn)

        self.place_btn = Gtk.Button(label="Select & Place")
        self.place_btn.add_css_class("suggested-action")
        self.place_btn.connect(
            "clicked",
            lambda _b: self._commit_selection(close_after=not self.keep_open_check.get_active()),
        )
        footer.append(self.place_btn)
        root.append(footer)

        self._populating = False
        self._row_symbols = {}
        self._populate_list()

    def _populate_list(self) -> None:
        self._populating = True
        try:
            while True:
                ch = self.listbox.get_first_child()
                if ch is None:
                    break
                self.listbox.remove(ch)
            self._row_symbols.clear()

            query = self.search_entry.get_text().strip().lower()
            cat_filter = self.cat_combo.get_active_id() or "all"

            for sym, spec in FIXTURE_CATALOG.items():
                if cat_filter != "all" and spec["category"] != cat_filter:
                    continue
                hay = f"{sym} {spec['label']} {spec['short_tag']}".lower()
                if query and query not in hay:
                    continue

                row = Gtk.ListBoxRow()
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                hbox.set_margin_top(4)
                hbox.set_margin_bottom(4)
                hbox.set_margin_start(6)
                hbox.set_margin_end(6)

                thumb = Gtk.DrawingArea()
                thumb.set_content_width(44)
                thumb.set_content_height(44)
                thumb.set_draw_func(lambda _da, cr, w, h, s=sym: draw_fixture_preview_icon(cr, s, w, h))
                hbox.append(thumb)

                vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                vbox.set_hexpand(True)
                title = Gtk.Label(label=spec["label"], xalign=0)
                title.add_css_class("heading")
                vbox.append(title)

                dims = f"{int(spec['width'])}\"W × {int(spec['depth'])}\"D × {spec['height']:.1f}\"H"
                if spec["elevation"] > 0:
                    dims += f"  |  Elev: {spec['elevation']:.0f}\""
                if spec["has_countertop"]:
                    dims += "  |  Countertop"
                sub = Gtk.Label(label=dims, xalign=0)
                sub.add_css_class("dim-label")
                vbox.append(sub)
                hbox.append(vbox)

                row.set_child(hbox)
                self._row_symbols[row] = sym
                self.listbox.append(row)
                if sym == self.selected_symbol:
                    self.listbox.select_row(row)
        finally:
            self._populating = False

    def _on_row_selected(self, _listbox, row) -> None:
        if row is not None and row in self._row_symbols:
            self.selected_symbol = self._row_symbols[row]
            if not getattr(self, "_populating", False) and self.canvas is not None:
                self.canvas.active_fixture_type = self.selected_symbol
                if hasattr(self.canvas, "set_tool_mode"):
                    self.canvas.set_tool_mode("add_fixture")
                if hasattr(self.canvas, "queue_draw"):
                    self.canvas.queue_draw()

    def _on_row_activated(self, _listbox, row) -> None:
        if row is not None and row in self._row_symbols:
            self.selected_symbol = self._row_symbols[row]
            self._commit_selection(close_after=not self.keep_open_check.get_active())

    def _commit_selection(self, close_after: bool = True) -> None:
        if self.canvas is not None:
            self.canvas.active_fixture_type = self.selected_symbol
            if hasattr(self.canvas, "set_tool_mode"):
                self.canvas.set_tool_mode("add_fixture")
            if hasattr(self.canvas, "queue_draw"):
                self.canvas.queue_draw()
        if callable(self.on_selected):
            self.on_selected(self.selected_symbol)
        if close_after:
            self.close()


class KitchenLayoutDialog(Gtk.Window):
    """Configuration dialog for parametric Kitchen and Bath Vanity layout presets."""

    def __init__(self, parent, canvas, on_configured=None):
        super().__init__(title="Kitchen & Vanity Layout Generator", transient_for=parent)
        self.set_default_size(400, 360)
        self.canvas = canvas
        self.on_configured = on_configured

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)
        self.set_child(root)

        def add_row(label_text, widget):
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lbl = Gtk.Label(label=label_text, xalign=0)
            lbl.set_hexpand(True)
            r.append(lbl)
            r.append(widget)
            root.append(r)

        self.preset_combo = Gtk.ComboBoxText()
        for key, label in LAYOUT_PRESETS:
            self.preset_combo.append(key, label)
        self.preset_combo.set_active_id("l_shaped")
        add_row("Layout Preset:", self.preset_combo)

        self.run_a_spin = Gtk.SpinButton.new_with_range(36, 360, 6)
        self.run_a_spin.set_value(120)
        add_row("Primary Run Width (in):", self.run_a_spin)

        self.run_b_spin = Gtk.SpinButton.new_with_range(36, 360, 6)
        self.run_b_spin.set_value(108)
        add_row("Secondary Wing / Depth (in):", self.run_b_spin)

        self.material_combo = Gtk.ComboBoxText()
        for mat in COUNTERTOP_MATERIALS:
            self.material_combo.append(mat, mat.replace("_", " ").title())
        self.material_combo.set_active_id("quartz")
        add_row("Countertop Material:", self.material_combo)

        self.rot_combo = Gtk.ComboBoxText()
        for deg in ("0", "90", "180", "270"):
            self.rot_combo.append(deg, f"{deg}°")
        self.rot_combo.set_active_id("0")
        add_row("Orientation:", self.rot_combo)

        self.uppers_switch = Gtk.Switch()
        self.uppers_switch.set_active(True)
        add_row("Include Upper Wall Cabinets:", self.uppers_switch)

        self.appliances_switch = Gtk.Switch()
        self.appliances_switch.set_active(True)
        add_row("Include Appliances (Sink/Range/Ref):", self.appliances_switch)

        note = Gtk.Label(
            label="Each placed cabinet & appliance can be selected and edited individually afterward.",
            xalign=0,
            wrap=True,
        )
        note.add_css_class("dim-label")
        root.append(note)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        single_btn = Gtk.Button(label="Single Cabinet / Appliance...")
        single_btn.set_tooltip_text("Pick an individual cabinet, sink, or appliance instead of a full layout")
        single_btn.connect("clicked", lambda _b: self._switch_to_single_browser())
        btns.append(single_btn)

        spacer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        spacer.set_hexpand(True)
        btns.append(spacer)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _b: self.close())
        btns.append(cancel_btn)

        apply_btn = Gtk.Button(label="Place Layout")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", lambda _b: self.apply_config())
        btns.append(apply_btn)
        root.append(btns)

    def _switch_to_single_browser(self) -> None:
        parent = self.get_transient_for()
        canvas = self.canvas
        self.close()
        if canvas is not None:
            canvas.active_fixture_type = "base_cabinet"
            if hasattr(canvas, "set_tool_mode"):
                canvas.set_tool_mode("add_fixture")
        dlg = FixtureBrowserDialog(parent, canvas)
        dlg.cat_combo.set_active_id("kitchen_cabinet")
        dlg.selected_symbol = "base_cabinet"
        dlg._populate_list()
        dlg.present()

    def get_config(self) -> dict:
        return {
            "layout_type": self.preset_combo.get_active_id() or "one_wall",
            "run_a": float(self.run_a_spin.get_value()),
            "run_b": float(self.run_b_spin.get_value()),
            "countertop_material": self.material_combo.get_active_id() or "quartz",
            "rotation_deg": float(self.rot_combo.get_active_id() or "0"),
            "include_uppers": bool(self.uppers_switch.get_active()),
            "include_appliances": bool(self.appliances_switch.get_active()),
        }

    def apply_config(self) -> dict:
        cfg = self.get_config()
        if self.canvas is not None:
            self.canvas.pending_layout_config = cfg
            self.canvas.active_fixture_rotation = cfg["rotation_deg"]
            if hasattr(self.canvas, "set_tool_mode"):
                self.canvas.set_tool_mode("add_kitchen_layout")
        if callable(self.on_configured):
            self.on_configured(cfg)
        self.close()
        return cfg
