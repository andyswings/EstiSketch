import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

def create_manage_materials_dialog(parent, config_constants, canvas):
    dialog = Gtk.Dialog(title=config_constants.MANAGE_MATERIALS_TITLE,
                        transient_for=parent,
                        modal=True)
    dialog.set_default_size(420, 180)  # Set a reasonable default size
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
        # ("Default Wall Height (inches)", "DEFAULT_WALL_HEIGHT")
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
        ("Max wall plate length (inches)", "MAX_WALL_PLATE_INCHES", ["96", "120", "144", "168", "192", "240"]),
    ]
    
    dropdown_widgets = {}
    for label, key, options in dropdowns:
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0)
        grid.attach(lbl, 0, row, 1, 1)
        combo = Gtk.ComboBoxText()
        for option in options:
            combo.append(option, option.replace("_", " ").title())
        current_value = str(getattr(config_constants, key, options[0]))
        combo.set_active_id(str(current_value))
        dropdown_widgets[key] = combo
        grid.attach(combo, 1, row, 1, 1)
        row += 1
    
    # Group 3: Toggle switches
    toggles = [
        # ("Enable Snapping", "SNAP_ENABLED")
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
            try:
                setattr(config_constants, key, int(combo.get_active_id()))
            except Exception:
                setattr(config_constants, key, combo.get_active_id())
        
        for key, switch in switches.items():
            setattr(config_constants, key, switch.get_active())
        canvas.queue_draw()
    
    dialog.connect("response", lambda d, response: update_config() if response == Gtk.ResponseType.OK else None)
    
    return dialog
