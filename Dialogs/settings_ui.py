import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

def create_settings_dialog(parent, config_constants, canvas):
    dialog = Gtk.Dialog(title=config_constants.SETTINGS_TITLE,
                        transient_for=parent,
                        modal=True)
    dialog.set_default_size(600, 500)  # Set a reasonable default size
    dialog.add_buttons(config_constants.OK_LABEL, Gtk.ResponseType.OK,
                       config_constants.CANCEL_LABEL, Gtk.ResponseType.CANCEL)
    
    content_area = dialog.get_content_area()
    
    # Add scrolling capability with a larger viewport
    scrolled_window = Gtk.ScrolledWindow()
    scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled_window.set_min_content_height(400)  # Make sure the viewport is large
    scrolled_window.set_min_content_width(580)
    content_area.append(scrolled_window)
    
    grid = Gtk.Grid(column_spacing=10, row_spacing=10)
    grid.set_margin_start(10)
    grid.set_margin_end(10)
    grid.set_margin_top(10)
    grid.set_margin_bottom(10)
    scrolled_window.set_child(grid)
    
    row = 0
    
    # Group 1: Numeric Entry Fields
    numeric_fields = [
        ("Default Wall Height (inches)", "DEFAULT_WALL_HEIGHT"),
        ("Default Wall Width (inches)", "DEFAULT_WALL_WIDTH"),
        ("Default Room Height (inches)", "DEFAULT_ROOM_HEIGHT"),
        ("Grid Spacing (pixels)", "GRID_SPACING"),
        ("Wall Join Tolerance", "WALL_JOIN_TOLERANCE"),
        ("Snap to Angle Increment", "SNAP_TO_ANGLE_INCREMENT"),
        ("Undo/Redo Limit", "UNDO_REDO_LIMIT"),
        ("Labor Cost per Hour ($)", "LABOR_COST_PER_HOUR"),
        ("Snap Threshold", "SNAP_THRESHOLD"),
        ("Default Zoom Level", "DEFAULT_ZOOM_LEVEL"),
        ("Pixels per inch", "PIXELS_PER_INCH")
    ]
    
    numeric_entries = {}
    for label, key in numeric_fields:
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0)
        grid.attach(lbl, 0, row, 1, 1)
        entry = Gtk.Entry()
        entry.set_text(str(getattr(config_constants, key, 0)))
        entry.set_width_chars(6)
        numeric_entries[key] = entry
        grid.attach(entry, 1, row, 1, 1)
        row += 1
    
    # Group 2: Dropdown Menus
    dropdowns = [
        ("Units", "UNITS", ["feet_inches", "metric"]),
        ("Wall Display Pattern", "WALL_DISPLAY_PATTERN", ["solid", "patterned", "filled_rectangle"]),
        ("Construction Type", "CONSTRUCTION_TYPE", ["stick", "metal", "cinder", "pole"]),
        ("Default Door Type", "DEFAULT_DOOR_TYPE", ["single", "double", "sliding", "pocket", "bi-fold", "double bi-fold", "frame", "garage"]),
        ("Default Window Type", "DEFAULT_WINDOW_TYPE", ["sliding", "fixed", "double-hung"]),
        ("Default Interior Wall Material", "DEFAULT_INTERIOR_WALL_MATERIAL", ["Drywall", "T&G"]),
        ("Default Exterior Wall Material", "DEFAULT_EXTERIOR_WALL_MATERIAL", ["Brick", "LP Lap Siding", "Hardie", "Stucco", "Wood", "Stone"]),
        ("Default Polyline Type", "POLYLINE_TYPE", ["solid", "dashed"]),
        ("Default File Format", "DEFAULT_FILE_FORMAT", ["json", "xml", "csv"])
    ]
    
    dropdown_widgets = {}
    for label, key, options in dropdowns:
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0)
        grid.attach(lbl, 0, row, 1, 1)
        combo = Gtk.ComboBoxText()
        for option in options:
            combo.append(option, option.replace("_", " ").title())
        combo.set_active_id(getattr(config_constants, key, options[0]))
        dropdown_widgets[key] = combo
        grid.attach(combo, 1, row, 1, 1)
        row += 1
    
    # Group 3: Toggle switches
    toggles = [
        ("Enable Snapping", "SNAP_ENABLED"),
        ("Show Grid", "SHOW_GRID"),
        ("Show Rulers", "SHOW_RULERS"),
        ("Enable Auto Save", "ENABLE_AUTO_SAVE"),
        ("Show Measurement Hints", "SHOW_MEASUREMENT_HINTS"),
        ("Enable Centerline Snapping", "ENABLE_CENTERLINE_SNAPPING"),
        ("Enable Undo/Redo Limit", "ENABLE_UNDO_REDO_LIMIT"),
        ("Include Cost Estimate in Export", "INCLUDE_COST_ESTIMATE_IN_EXPORT"),
    ]
    
    switches = {}
    for label, key in toggles:
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0)
        grid.attach(lbl, 0, row, 1, 1)
        switch = Gtk.Switch()
        switch.set_active(getattr(config_constants, key, False))
        switch.set_halign(Gtk.Align.END)
        switches[key] = switch
        grid.attach(switch, 1, row, 1, 1)
        row += 1
    
    # Apply changes: update the config and also force a redraw of the canvas
    def update_config():
        for key, entry in numeric_entries.items():
            try:
                setattr(config_constants, key, float(entry.get_text()))
            except ValueError:
                pass
        
        for key, combo in dropdown_widgets.items():
            setattr(config_constants, key, combo.get_active_id())
        
        for key, switch in switches.items():
            setattr(config_constants, key, switch.get_active())
        canvas.queue_draw()
    
    dialog.connect("response", lambda d, response: update_config() if response == Gtk.ResponseType.OK else None)
    
    return dialog
