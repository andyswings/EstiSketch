from gi.repository import Gtk
import gi

gi.require_version('Gtk', '4.0')


def create_manage_materials_dialog(parent, config_object, canvas=None):
    """
    Display comprehensive Material Management & Procurement Configuration dialog.
    Allows editing framing, sheathing, weather barrier, roof structure, and foundation specs.
    """
    dialog = Gtk.Dialog(
        title="Manage Materials & Construction Specs",
        transient_for=parent,
        modal=False
    )
    dialog.set_resizable(True)
    dialog.set_default_size(680, 540)
    dialog.add_buttons(
        getattr(config_object, "OK_LABEL", "OK"), Gtk.ResponseType.OK,
        getattr(config_object, "CANCEL_LABEL", "Cancel"), Gtk.ResponseType.CANCEL
    )

    content_area = dialog.get_content_area()
    content_area.set_margin_start(12)
    content_area.set_margin_end(12)
    content_area.set_margin_top(12)
    content_area.set_margin_bottom(12)

    # Use a GTK Notebook for clean categorical tabs
    notebook = Gtk.Notebook()
    notebook.set_tab_pos(Gtk.PositionType.TOP)
    notebook.set_hexpand(True)
    notebook.set_vexpand(True)
    content_area.append(notebook)

    # Helper function to create scrolled grid for tab content
    def create_tab_grid():
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(380)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        grid = Gtk.Grid(column_spacing=16, row_spacing=12)
        grid.set_margin_start(16)
        grid.set_margin_end(16)
        grid.set_margin_top(16)
        grid.set_margin_bottom(16)
        grid.set_hexpand(True)
        grid.set_vexpand(True)
        scrolled.set_child(grid)
        return scrolled, grid

    fields = {}

    # ─── TAB 1: Wall Framing Specs ───
    tab1_scroll, grid1 = create_tab_grid()
    row = 0

    # Section Header
    lbl_hdr = Gtk.Label()
    lbl_hdr.set_markup("<b>Wall Framing &amp; Lumber Parameters</b>")
    lbl_hdr.set_halign(Gtk.Align.START)
    grid1.attach(lbl_hdr, 0, row, 2, 1)
    row += 1

    # Stud Spacing Dropdown
    lbl = Gtk.Label(label="Stud Spacing (On Center):")
    lbl.set_xalign(0)
    grid1.attach(lbl, 0, row, 1, 1)
    combo_stud = Gtk.ComboBoxText()
    combo_stud.append("16.0", '16.0" OC (Standard)')
    combo_stud.append("24.0", '24.0" OC (Advanced Framing)')
    cur_stud = str(getattr(config_object, "DEFAULT_STUD_SPACING", "16.0"))
    combo_stud.set_active_id(cur_stud if cur_stud in ["16.0", "24.0"] else "16.0")
    fields["DEFAULT_STUD_SPACING"] = ("combo_float", combo_stud)
    grid1.attach(combo_stud, 1, row, 1, 1)
    row += 1

    # Max Wall Plate Length Dropdown
    lbl = Gtk.Label(label="Max Stock Wall Plate Length:")
    lbl.set_xalign(0)
    grid1.attach(lbl, 0, row, 1, 1)
    combo_plate = Gtk.ComboBoxText()
    for val, title in [("96", "8 Feet (96\")"), ("120", "10 Feet (120\")"), ("144", "12 Feet (144\")"),
                       ("168", "14 Feet (168\")"), ("192", "16 Feet (192\" - Default)"), ("240", "20 Feet (240\")")]:
        combo_plate.append(val, title)
    cur_plate = str(int(getattr(config_object, "MAX_WALL_PLATE_INCHES", 192)))
    combo_plate.set_active_id(cur_plate if combo_plate.set_active_id(cur_plate) else "192")
    fields["MAX_WALL_PLATE_INCHES"] = ("combo_int", combo_plate)
    grid1.attach(combo_plate, 1, row, 1, 1)
    row += 1

    # Default Wall Height
    lbl = Gtk.Label(label="Default Wall Height (Inches):")
    lbl.set_xalign(0)
    grid1.attach(lbl, 0, row, 1, 1)
    spin_height = Gtk.SpinButton.new_with_range(72.0, 240.0, 1.0)
    spin_height.set_value(float(getattr(config_object, "DEFAULT_WALL_HEIGHT", 96.0)))
    fields["DEFAULT_WALL_HEIGHT"] = ("spin_float", spin_height)
    grid1.attach(spin_height, 1, row, 1, 1)
    row += 1

    notebook.append_page(tab1_scroll, Gtk.Label(label="🏗️ Wall Framing"))

    # ─── TAB 2: Sheathing & House Wrap ───
    tab2_scroll, grid2 = create_tab_grid()
    row = 0

    lbl_hdr = Gtk.Label()
    lbl_hdr.set_markup("<b>Exterior Sheathing &amp; Weather Barrier</b>")
    lbl_hdr.set_halign(Gtk.Align.START)
    grid2.attach(lbl_hdr, 0, row, 2, 1)
    row += 1

    # Sheathing Thickness Dropdown
    lbl = Gtk.Label(label="Sheathing Panel Thickness:")
    lbl.set_xalign(0)
    grid2.attach(lbl, 0, row, 1, 1)
    combo_sthick = Gtk.ComboBoxText()
    for t in ['7/16"', '1/2"', '5/8"', '3/4"']:
        combo_sthick.append(t, t)
    cur_sthick = str(getattr(config_object, "SHEATHING_THICKNESS", '7/16"'))
    combo_sthick.set_active_id(cur_sthick if cur_sthick in ['7/16"', '1/2"', '5/8"', '3/4"'] else '7/16"')
    fields["SHEATHING_THICKNESS"] = ("combo_str", combo_sthick)
    grid2.attach(combo_sthick, 1, row, 1, 1)
    row += 1

    # Sheathing Material Type Dropdown
    lbl = Gtk.Label(label="Sheathing Material:")
    lbl.set_xalign(0)
    grid2.attach(lbl, 0, row, 1, 1)
    combo_smat = Gtk.ComboBoxText()
    combo_smat.append("OSB", "OSB (Oriented Strand Board)")
    combo_smat.append("Plywood", "CDX Exterior Plywood")
    cur_smat = str(getattr(config_object, "SHEATHING_MATERIAL_TYPE", "OSB"))
    combo_smat.set_active_id(cur_smat if cur_smat in ["OSB", "Plywood"] else "OSB")
    fields["SHEATHING_MATERIAL_TYPE"] = ("combo_str", combo_smat)
    grid2.attach(combo_smat, 1, row, 1, 1)
    row += 1

    # House Wrap Roll Width
    lbl = Gtk.Label(label="House Wrap Roll Width (Feet):")
    lbl.set_xalign(0)
    grid2.attach(lbl, 0, row, 1, 1)
    spin_wrap_w = Gtk.SpinButton.new_with_range(3.0, 12.0, 1.0)
    spin_wrap_w.set_value(float(getattr(config_object, "HOUSEWRAP_ROLL_WIDTH_FT", 9.0)))
    fields["HOUSEWRAP_ROLL_WIDTH_FT"] = ("spin_float", spin_wrap_w)
    grid2.attach(spin_wrap_w, 1, row, 1, 1)
    row += 1

    # House Wrap Roll Length
    lbl = Gtk.Label(label="House Wrap Roll Length (Feet):")
    lbl.set_xalign(0)
    grid2.attach(lbl, 0, row, 1, 1)
    spin_wrap_l = Gtk.SpinButton.new_with_range(50.0, 300.0, 10.0)
    spin_wrap_l.set_value(float(getattr(config_object, "HOUSEWRAP_ROLL_LENGTH_FT", 150.0)))
    fields["HOUSEWRAP_ROLL_LENGTH_FT"] = ("spin_float", spin_wrap_l)
    grid2.attach(spin_wrap_l, 1, row, 1, 1)
    row += 1

    # House Wrap Overlap %
    lbl = Gtk.Label(label="Wrap Overlap & Waste Allowance (%):")
    lbl.set_xalign(0)
    grid2.attach(lbl, 0, row, 1, 1)
    spin_wrap_pct = Gtk.SpinButton.new_with_range(0.0, 30.0, 1.0)
    spin_wrap_pct.set_value(float(getattr(config_object, "HOUSEWRAP_OVERLAP_PCT", 10.0)))
    fields["HOUSEWRAP_OVERLAP_PCT"] = ("spin_float", spin_wrap_pct)
    grid2.attach(spin_wrap_pct, 1, row, 1, 1)
    row += 1

    notebook.append_page(tab2_scroll, Gtk.Label(label="🪵 Sheathing & Wrap"))

    # ─── TAB 3: Roof Construction Specs ───
    tab3_scroll, grid3 = create_tab_grid()
    row = 0

    lbl_hdr = Gtk.Label()
    lbl_hdr.set_markup("<b>Roof Construction &amp; Framing System</b>")
    lbl_hdr.set_halign(Gtk.Align.START)
    grid3.attach(lbl_hdr, 0, row, 2, 1)
    row += 1

    # Roof Framing Type Dropdown
    lbl = Gtk.Label(label="Roof Framing Method:")
    lbl.set_xalign(0)
    grid3.attach(lbl, 0, row, 1, 1)
    combo_rframing = Gtk.ComboBoxText()
    combo_rframing.append("truss", "Pre-Engineered Roof Trusses")
    combo_rframing.append("stick", "Stick Framed (Site-Built Rafters)")
    cur_rframing = str(getattr(config_object, "ROOF_FRAMING_TYPE", "truss"))
    combo_rframing.set_active_id(cur_rframing if cur_rframing in ["truss", "stick"] else "truss")
    fields["ROOF_FRAMING_TYPE"] = ("combo_str", combo_rframing)
    grid3.attach(combo_rframing, 1, row, 1, 1)
    row += 1

    # Rafter Spacing Dropdown
    lbl = Gtk.Label(label="Stick Rafter Spacing (On Center):")
    lbl.set_xalign(0)
    grid3.attach(lbl, 0, row, 1, 1)
    combo_rspace = Gtk.ComboBoxText()
    combo_rspace.append("16.0", '16.0" OC')
    combo_rspace.append("24.0", '24.0" OC')
    cur_rspace = str(getattr(config_object, "ROOF_RAFTER_SPACING_IN", "16.0"))
    combo_rspace.set_active_id(cur_rspace if cur_rspace in ["16.0", "24.0"] else "16.0")
    fields["ROOF_RAFTER_SPACING_IN"] = ("combo_float", combo_rspace)
    grid3.attach(combo_rspace, 1, row, 1, 1)
    row += 1

    # LVL Ridge Switch
    lbl = Gtk.Label(label="Use LVL Engineered Ridge Beam:")
    lbl.set_xalign(0)
    grid3.attach(lbl, 0, row, 1, 1)
    sw_lvl = Gtk.Switch()
    sw_lvl.set_active(bool(getattr(config_object, "ROOF_USE_LVL_RIDGE", False)))
    sw_lvl.set_halign(Gtk.Align.END)
    fields["ROOF_USE_LVL_RIDGE"] = ("switch", sw_lvl)
    grid3.attach(sw_lvl, 1, row, 1, 1)
    row += 1

    # Roof Sheathing Thickness
    lbl = Gtk.Label(label="Roof Sheathing Thickness:")
    lbl.set_xalign(0)
    grid3.attach(lbl, 0, row, 1, 1)
    combo_rthick = Gtk.ComboBoxText()
    for t in ['7/16"', '1/2"', '5/8"', '3/4"']:
        combo_rthick.append(t, t)
    cur_rthick = str(getattr(config_object, "ROOF_SHEATHING_THICKNESS", '5/8"'))
    combo_rthick.set_active_id(cur_rthick if cur_rthick in ['7/16"', '1/2"', '5/8"', '3/4"'] else '5/8"')
    fields["ROOF_SHEATHING_THICKNESS"] = ("combo_str", combo_rthick)
    grid3.attach(combo_rthick, 1, row, 1, 1)
    row += 1

    # Roof Waste %
    lbl = Gtk.Label(label="Roof Shingle & Decking Waste (%):")
    lbl.set_xalign(0)
    grid3.attach(lbl, 0, row, 1, 1)
    spin_rwaste = Gtk.SpinButton.new_with_range(0.0, 30.0, 1.0)
    spin_rwaste.set_value(float(getattr(config_object, "ROOF_WASTE_PCT", 10.0)))
    fields["ROOF_WASTE_PCT"] = ("spin_float", spin_rwaste)
    grid3.attach(spin_rwaste, 1, row, 1, 1)
    row += 1

    notebook.append_page(tab3_scroll, Gtk.Label(label="🏠 Roof Specs"))

    # ─── TAB 4: Foundation & Hardware ───
    tab4_scroll, grid4 = create_tab_grid()
    row = 0

    lbl_hdr = Gtk.Label()
    lbl_hdr.set_markup("<b>Concrete Slab Foundation &amp; Anchors</b>")
    lbl_hdr.set_halign(Gtk.Align.START)
    grid4.attach(lbl_hdr, 0, row, 2, 1)
    row += 1

    lbl_desc = Gtk.Label(
        label="Sill Seal foam gaskets are automatically computed per wall width.\n"
              "Foundation Anchor J-Bolts (1/2\" x 10\") are computed for exterior walls\n"
              "using 12\" end spacing and 48\" OC intermediate spacing."
    )
    lbl_desc.set_xalign(0)
    grid4.attach(lbl_desc, 0, row, 2, 1)
    row += 1

    notebook.append_page(tab4_scroll, Gtk.Label(label="🔩 Foundation"))

    # Apply configuration on OK response
    def apply_changes():
        for key, (ftype, widget) in fields.items():
            if ftype == "combo_float":
                setattr(config_object, key, float(widget.get_active_id() or 16.0))
            elif ftype == "combo_int":
                setattr(config_object, key, int(widget.get_active_id() or 192))
            elif ftype == "combo_str":
                setattr(config_object, key, widget.get_active_id())
            elif ftype == "spin_float":
                setattr(config_object, key, float(widget.get_value()))
            elif ftype == "switch":
                setattr(config_object, key, bool(widget.get_active()))

        if canvas and hasattr(canvas, "queue_draw"):
            canvas.queue_draw()

    dialog.connect("response", lambda d, r: apply_changes() if r == Gtk.ResponseType.OK else None)

    return dialog
