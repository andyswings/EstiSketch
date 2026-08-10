import gi
gi.require_version('Gtk', '4.0')

from gi.repository import Gtk, Gdk, Gio  # type: ignore
import os
import sys
import html

from ..Takeoff.building_takeoff import (
    extract_walls_from_canvas,
    generate_width_summary_report,
    generate_wall_report,
    generate_framing_report,
    generate_sheathing_report,
    generate_housewrap_report,
    generate_roof_takeoff,
    get_supplier_quote_items,
    export_supplier_quote_txt,
    export_supplier_quote_csv,
    export_supplier_quote_pdf
)
from ..Takeoff.roof_takeoff import format_takeoff_report


def create_estimate_materials_dialog(parent, canvas):
    """
    Display complete Material Takeoff & Supplier Quote Management Dialog.
    
    Features:
      - Multi-tab UI: Takeoff Reports & Supplier Quote Manager
      - Interactive Line Item List: Add custom items, edit, exclude/include, and delete
      - Export functionality to .txt, .csv, and .pdf formats
    """
    dialog = Gtk.Dialog(
        title="Building Material Takeoff & Supplier Procurement Manager",
        transient_for=parent,
        modal=False
    )
    dialog.set_resizable(True)
    dialog.set_default_size(850, 620)
    dialog.add_button("Close", Gtk.ResponseType.CLOSE)
    dialog.connect("response", lambda d, r: d.destroy())

    content_area = dialog.get_content_area()
    content_area.set_margin_start(12)
    content_area.set_margin_end(12)
    content_area.set_margin_top(12)
    content_area.set_margin_bottom(12)

    config_object = getattr(canvas, "config", None)
    if not config_object and hasattr(parent, "config"):
        config_object = parent.config

    # State: list of line items (both auto and manual)
    quote_items = get_supplier_quote_items(canvas, config_object)
    custom_items = []

    notebook = Gtk.Notebook()
    notebook.set_hexpand(True)
    notebook.set_vexpand(True)
    content_area.append(notebook)

    # ─────────────────────────────────────────────────────────────
    # TAB 1: MATERIAL TAKEOFF REPORTS
    # ─────────────────────────────────────────────────────────────
    tab1_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    tab1_box.set_margin_start(10)
    tab1_box.set_margin_end(10)
    tab1_box.set_margin_top(10)
    tab1_box.set_margin_bottom(10)
    tab1_box.set_hexpand(True)
    tab1_box.set_vexpand(True)

    # Top Selector Bar
    hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    lbl_sel = Gtk.Label(label="Select Report View:")
    hdr_box.append(lbl_sel)

    report_combo = Gtk.ComboBoxText()
    report_types = [
        ("framing", "Framing Material Report (Studs & Plates)"),
        ("width_summary", "Wall Summary by Width"),
        ("detailed_walls", "Detailed Wall Listing"),
        ("sheathing", "Exterior Sheathing (OSB / Plywood)"),
        ("housewrap", "Exterior House Wrap (Weather Barrier)"),
        ("roof", "Roof Material Takeoff")
    ]
    for key, name in report_types:
        report_combo.append(key, name)
    report_combo.set_active_id("framing")

    # Disable mouse scroll wheel cycling on combobox so mouse scroll moves the report text area
    combo_scroll_ctrl = Gtk.EventControllerScroll.new(
        Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.HORIZONTAL
    )
    combo_scroll_ctrl.connect("scroll", lambda ctrl, dx, dy: True)
    report_combo.add_controller(combo_scroll_ctrl)

    hdr_box.append(report_combo)

    # Copy Button
    btn_copy = Gtk.Button(label="📋 Copy Report")
    hdr_box.append(btn_copy)
    tab1_box.append(hdr_box)

    # Text View inside Scrolled Window
    scrolled_txt = Gtk.ScrolledWindow()
    scrolled_txt.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled_txt.set_overlay_scrolling(False)
    scrolled_txt.set_focusable(True)
    scrolled_txt.set_min_content_height(400)
    scrolled_txt.set_min_content_width(650)
    scrolled_txt.set_hexpand(True)
    scrolled_txt.set_vexpand(True)

    text_view = Gtk.TextView()
    text_view.set_editable(False)
    text_view.set_focusable(True)
    text_view.set_monospace(True)
    text_view.set_left_margin(10)
    text_view.set_right_margin(10)
    text_view.set_top_margin(10)
    text_view.set_bottom_margin(10)
    text_view.set_hexpand(True)
    text_view.set_vexpand(True)
    text_buffer = text_view.get_buffer()
    scrolled_txt.set_child(text_view)
    tab1_box.append(scrolled_txt)

    def refresh_report_text(*args):
        active_id = report_combo.get_active_id()
        walls = extract_walls_from_canvas(canvas)
        stud_spacing = float(getattr(config_object, "DEFAULT_STUD_SPACING", 16.0)) if config_object else 16.0
        plate_len = float(getattr(config_object, "MAX_WALL_PLATE_INCHES", 192.0)) if config_object else 192.0

        if active_id == "framing":
            text = generate_framing_report(walls, stud_spacing, plate_len)
        elif active_id == "width_summary":
            text = generate_width_summary_report(walls)
        elif active_id == "detailed_walls":
            text = generate_wall_report(walls)
        elif active_id == "sheathing":
            s_thick = str(getattr(config_object, "SHEATHING_THICKNESS", '7/16"')) if config_object else '7/16"'
            text = generate_sheathing_report(walls, thickness=s_thick)
        elif active_id == "housewrap":
            text = generate_housewrap_report(walls)
        elif active_id == "roof":
            roof_data = generate_roof_takeoff(canvas, config_object)
            text = format_takeoff_report(roof_data) if roof_data else "No roof polyline data."
        else:
            text = "Select a report."

        text_buffer.set_text(text)

    report_combo.connect("changed", refresh_report_text)
    refresh_report_text()

    def on_copy_clicked(btn):
        start, end = text_buffer.get_bounds()
        txt = text_buffer.get_text(start, end, True)
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(txt)

    btn_copy.connect("clicked", on_copy_clicked)
    notebook.append_page(tab1_box, Gtk.Label(label="📊 Takeoff Reports"))

    # ─────────────────────────────────────────────────────────────
    # TAB 2: SUPPLIER QUOTE MANAGER
    # ─────────────────────────────────────────────────────────────
    tab2_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    tab2_box.set_margin_start(10)
    tab2_box.set_margin_end(10)
    tab2_box.set_margin_top(10)
    tab2_box.set_margin_bottom(10)
    tab2_box.set_hexpand(True)
    tab2_box.set_vexpand(True)

    # Action Toolbar
    toolbar_quote = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    
    btn_add_item = Gtk.Button(label="➕ Add Custom Item")
    btn_refresh = Gtk.Button(label="🔄 Refresh Takeoff")
    btn_export = Gtk.Button(label="💾 Export Quote...")

    toolbar_quote.append(btn_add_item)
    toolbar_quote.append(btn_refresh)
    
    spacer = Gtk.Box()
    spacer.set_hexpand(True)
    toolbar_quote.append(spacer)
    toolbar_quote.append(btn_export)
    tab2_box.append(toolbar_quote)

    # Scrolled List Box for Items
    scrolled_quote = Gtk.ScrolledWindow()
    scrolled_quote.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled_quote.set_min_content_height(400)
    scrolled_quote.set_min_content_width(650)
    scrolled_quote.set_hexpand(True)
    scrolled_quote.set_vexpand(True)


    list_box = Gtk.ListBox()
    list_box.set_selection_mode(Gtk.SelectionMode.NONE)
    scrolled_quote.set_child(list_box)
    tab2_box.append(scrolled_quote)

    def render_quote_list():
        # Clear existing rows
        while True:
            row = list_box.get_row_at_index(0)
            if not row:
                break
            list_box.remove(row)

        for item in quote_items:
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row_box.set_margin_start(8)
            row_box.set_margin_end(8)
            row_box.set_margin_top(6)
            row_box.set_margin_bottom(6)

            # Checkbox active toggle
            chk = Gtk.CheckButton()
            chk.set_active(not item.get('is_excluded', False))
            
            def _on_toggled(cb, it=item):
                it['is_excluded'] = not cb.get_active()
            chk.connect("toggled", _on_toggled)
            row_box.append(chk)

            # Type Badge
            is_auto = item.get('is_auto', True)
            badge_lbl = Gtk.Label()
            if is_auto:
                badge_lbl.set_markup("<span background='#0284C7' foreground='white'><b> AUTO </b></span>")
            else:
                badge_lbl.set_markup("<span background='#16A34A' foreground='white'><b> MANUAL </b></span>")
            row_box.append(badge_lbl)

            # Item info label
            info_lbl = Gtk.Label()
            info_lbl.set_xalign(0)
            qty_val = item.get('qty', 0)
            unit_val = html.escape(str(item.get('unit', 'Pcs')))
            desc_val = html.escape(str(item.get('description', '')))
            notes_val = html.escape(str(item.get('notes', ''))) if item.get('notes') else ""

            qty_str = f"<b>{qty_val} {unit_val}</b>"
            desc_str = f"<b>{desc_val}</b>"
            notes_str = f"<small>{notes_val}</small>" if notes_val else ""
            info_lbl.set_markup(f"{desc_str} — {qty_str}\n{notes_str}")
            info_lbl.set_hexpand(True)
            row_box.append(info_lbl)

            # Edit button
            btn_edit = Gtk.Button(label="✏️ Edit")
            def _on_edit(b, it=item):
                show_edit_item_dialog(it)
            btn_edit.connect("clicked", _on_edit)
            row_box.append(btn_edit)

            # Delete button (for manual) or Exclude toggle
            if not is_auto:
                btn_del = Gtk.Button(label="🗑️ Delete")
                def _on_del(b, it=item):
                    if it in quote_items:
                        quote_items.remove(it)
                    if it in custom_items:
                        custom_items.remove(it)
                    render_quote_list()
                btn_del.connect("clicked", _on_del)
                row_box.append(btn_del)

            list_box.append(row_box)

    render_quote_list()

    def on_refresh_clicked(btn):
        nonlocal quote_items
        quote_items = get_supplier_quote_items(canvas, config_object, custom_items=custom_items)
        render_quote_list()
        refresh_report_text()

    btn_refresh.connect("clicked", on_refresh_clicked)

    def show_edit_item_dialog(item):
        dlg_edit = Gtk.Dialog(title="Edit Line Item", transient_for=dialog, modal=True)
        dlg_edit.set_default_size(420, 260)
        dlg_edit.add_buttons("Save", Gtk.ResponseType.OK, "Cancel", Gtk.ResponseType.CANCEL)
        c_area = dlg_edit.get_content_area()

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_margin_start(16)
        grid.set_margin_end(16)
        grid.set_margin_top(16)
        grid.set_margin_bottom(16)
        c_area.append(grid)

        # Description
        grid.attach(Gtk.Label(label="Description:"), 0, 0, 1, 1)
        entry_desc = Gtk.Entry()
        entry_desc.set_text(item.get('description', ''))
        entry_desc.set_hexpand(True)
        grid.attach(entry_desc, 1, 0, 1, 1)

        # Quantity
        grid.attach(Gtk.Label(label="Quantity:"), 0, 1, 1, 1)
        spin_qty = Gtk.SpinButton.new_with_range(1, 100000, 1)
        spin_qty.set_value(float(item.get('qty', 1)))
        grid.attach(spin_qty, 1, 1, 1, 1)

        # Unit
        grid.attach(Gtk.Label(label="Unit:"), 0, 2, 1, 1)
        entry_unit = Gtk.Entry()
        entry_unit.set_text(item.get('unit', 'Pcs'))
        grid.attach(entry_unit, 1, 2, 1, 1)

        # Notes
        grid.attach(Gtk.Label(label="Notes:"), 0, 3, 1, 1)
        entry_notes = Gtk.Entry()
        entry_notes.set_text(item.get('notes', ''))
        grid.attach(entry_notes, 1, 3, 1, 1)

        def _on_save(d, res):
            if res == Gtk.ResponseType.OK:
                item['description'] = entry_desc.get_text()
                item['qty'] = int(spin_qty.get_value())
                item['unit'] = entry_unit.get_text()
                item['notes'] = entry_notes.get_text()
                render_quote_list()
            d.destroy()

        dlg_edit.connect("response", _on_save)
        dlg_edit.present()

    def on_add_custom_item_clicked(btn):
        new_item = {
            'description': 'Custom Material Item',
            'qty': 1,
            'unit': 'Pcs',
            'notes': 'Custom entry',
            'is_auto': False,
            'is_excluded': False
        }
        quote_items.append(new_item)
        custom_items.append(new_item)
        show_edit_item_dialog(new_item)

    btn_add_item.connect("clicked", on_add_custom_item_clicked)

    # ── Export Dialog Handler ──
    def on_export_clicked(btn):
        dlg_save = Gtk.FileDialog.new()
        dlg_save.set_title("Export Supplier Quote")
        dlg_save.set_modal(True)

        txt_filter = Gtk.FileFilter()
        txt_filter.set_name("Plain Text (*.txt)")
        txt_filter.add_pattern("*.txt")

        csv_filter = Gtk.FileFilter()
        csv_filter.set_name("CSV Spreadsheet (*.csv)")
        csv_filter.add_pattern("*.csv")

        pdf_filter = Gtk.FileFilter()
        pdf_filter.set_name("PDF Document (*.pdf)")
        pdf_filter.add_pattern("*.pdf")

        filter_store = Gio.ListStore.new(Gtk.FileFilter)
        filter_store.append(pdf_filter)
        filter_store.append(csv_filter)
        filter_store.append(txt_filter)

        dlg_save.set_filters(filter_store)
        dlg_save.set_default_filter(pdf_filter)

        def _on_export_done(obj, result):
            try:
                gfile = obj.save_finish(result)
            except Exception as e:
                return
            if not gfile:
                return
            path = gfile.get_path()
            proj_name = getattr(canvas, "project_name", "EstiSketch Building Project")

            if path.lower().endswith(".csv"):
                export_supplier_quote_csv(quote_items, config_object, proj_name, path)
            elif path.lower().endswith(".pdf"):
                export_supplier_quote_pdf(quote_items, config_object, proj_name, path)
            else:
                if not path.lower().endswith(".txt"):
                    path += ".txt"
                export_supplier_quote_txt(quote_items, config_object, proj_name, path)

        dlg_save.save(dialog, None, _on_export_done)

    btn_export.connect("clicked", on_export_clicked)

    notebook.append_page(tab2_box, Gtk.Label(label="📋 Supplier Quote List"))

    return dialog
