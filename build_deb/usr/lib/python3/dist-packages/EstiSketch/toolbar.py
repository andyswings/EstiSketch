import os
from gi.repository import Gtk
import gi
gi.require_version('Gtk', '4.0')


def create_toolbar(config_constants, callbacks=None, canvas=None):
    if callbacks is None:
        callbacks = {}
    tb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    tool_buttons = {}

    icon_dir = os.path.join(os.path.dirname(__file__), "Icons")

    def create_icon_button(icon_name, tooltip):
        button = Gtk.Button()
        image = Gtk.Image.new_from_file(
            os.path.join(icon_dir, f"{icon_name}.png"))
        image.set_pixel_size(24)
        button.set_child(image)
        button.set_tooltip_text(tooltip)
        return button

    def create_icon_toggle_button(icon_name, tooltip):
        button = Gtk.ToggleButton()
        image = Gtk.Image.new_from_file(
            os.path.join(icon_dir, f"{icon_name}.png"))
        image.set_pixel_size(24)
        button.set_child(image)
        button.set_tooltip_text(tooltip)
        return button

    tool_buttons["save"] = create_icon_button(
        "save", f"{config_constants.SAVE_LABEL} (Ctrl+S)")
    tool_buttons["open"] = create_icon_button(
        "open", f"{config_constants.OPEN_LABEL} (Ctrl+O)")
    # Export button hidden until functionality is implemented
    tool_buttons["export"] = create_icon_button(
        "export", f"{config_constants.EXPORT_LABEL} (Ctrl+E)")
    tb.append(tool_buttons["save"])
    tb.append(tool_buttons["open"])
    # tb.append(tool_buttons["export"])  # Hidden - not yet implemented

    # Undo and Redo (after Export)
    tool_buttons["undo"] = create_icon_button("undo", "Undo (Ctrl+Z)")
    tool_buttons["redo"] = create_icon_button("redo", "Redo (Ctrl+Y)")
    tb.append(tool_buttons["undo"])
    tb.append(tool_buttons["redo"])

    tb.append(Gtk.Separator.new(Gtk.Orientation.VERTICAL))

    # ─── Toolset Definitions ───
    TOOLSETS = {
        "Main": ["pointer", "panning", "draw_walls", "draw_rooms", "add_doors", "add_windows", "add_dimension", "add_text"],
        "Annotation": ["pointer", "panning", "add_polyline", "add_dimension", "add_text", "add_circle", "add_arc"],
        "Roof": ["design_roof", "panning", "add_dimension"],
        "Interior Design": ["pointer", "panning", "add_doors", "add_windows", "add_dimension", "add_text"],  # Placeholder
    }
    
    # ─── Toolset Dropdown ───
    toolset_names = list(TOOLSETS.keys())
    toolset_model = Gtk.StringList.new(toolset_names)
    toolset_dropdown = Gtk.DropDown(model=toolset_model)
    toolset_dropdown.set_tooltip_text("Select Toolset")
    tb.append(toolset_dropdown)

    # Spacer to push tools to center
    left_spacer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    left_spacer.set_hexpand(True)
    tb.append(left_spacer)

    # Group 2: Tool buttons (centered)
    tool_buttons["pointer"] = create_icon_toggle_button(
        "pointer", "Select (V)")
    tool_buttons["panning"] = create_icon_toggle_button("panning", "Pan (P)")
    tool_buttons["draw_walls"] = create_icon_toggle_button(
        "draw_walls", f"{config_constants.DRAW_WALLS_LABEL} (W)")
    tool_buttons["draw_rooms"] = create_icon_toggle_button(
        "draw_rooms", f"{config_constants.DRAW_ROOMS_LABEL} (R)")
    tool_buttons["add_doors"] = create_icon_toggle_button(
        "add_doors", f"{config_constants.ADD_DOORS_LABEL} (D)")
    tool_buttons["add_windows"] = create_icon_toggle_button(
        "add_windows", f"{config_constants.ADD_WINDOWS_LABEL} (A)")
    tool_buttons["add_polyline"] = create_icon_toggle_button(
        "add_polyline", f"Add Polyline (L)")
    tool_buttons["add_dimension"] = create_icon_toggle_button(
        "add_dimension", f"{config_constants.ADD_DIMENSION_LABEL} (M)")
    tool_buttons["add_text"] = create_icon_toggle_button(
        "add_text", f"{config_constants.ADD_TEXT_LABEL} (T)")
    tool_buttons["add_circle"] = create_icon_toggle_button(
        "add_circle", "Add Circle (C)")
    tool_buttons["add_arc"] = create_icon_toggle_button(
        "add_arc", "Add Arc (Shift+A)")
    tool_buttons["design_roof"] = create_icon_toggle_button(
        "roof", "Design Roof (Shift+R)")

    # Set up toggle button group
    tool_buttons["panning"].set_group(tool_buttons["pointer"])  # Add to group
    tool_buttons["draw_walls"].set_group(tool_buttons["pointer"])
    tool_buttons["draw_rooms"].set_group(tool_buttons["pointer"])
    tool_buttons["add_doors"].set_group(tool_buttons["pointer"])
    tool_buttons["add_windows"].set_group(tool_buttons["pointer"])
    tool_buttons["add_polyline"].set_group(tool_buttons["pointer"])
    tool_buttons["add_dimension"].set_group(tool_buttons["pointer"])
    tool_buttons["add_text"].set_group(tool_buttons["pointer"])
    tool_buttons["add_circle"].set_group(tool_buttons["pointer"])
    tool_buttons["add_arc"].set_group(tool_buttons["pointer"])
    tool_buttons["design_roof"].set_group(tool_buttons["pointer"])

    # Add tool buttons to toolbar
    tb.append(tool_buttons["pointer"])
    tb.append(tool_buttons["panning"])
    tb.append(tool_buttons["draw_walls"])
    tb.append(tool_buttons["draw_rooms"])
    tb.append(tool_buttons["add_doors"])
    tb.append(tool_buttons["add_windows"])
    tb.append(tool_buttons["add_polyline"])
    tb.append(tool_buttons["add_dimension"])
    tb.append(tool_buttons["add_text"])
    tb.append(tool_buttons["add_circle"])
    tb.append(tool_buttons["add_arc"])
    tb.append(tool_buttons["design_roof"])

    # Separator between tools and zoom controls
    tb.append(Gtk.Separator.new(Gtk.Orientation.VERTICAL))

    # Zoom buttons (after tools)
    tool_buttons["zoom_in"] = create_icon_button("zoom_in", "Zoom In (Ctrl+=)")
    tool_buttons["zoom_out"] = create_icon_button(
        "zoom_out", "Zoom Out (Ctrl+-)")
    tool_buttons["zoom_reset"] = create_icon_button(
        "zoom_reset", "Reset Zoom (Ctrl+0)")
    tb.append(tool_buttons["zoom_in"])
    tb.append(tool_buttons["zoom_out"])
    tb.append(tool_buttons["zoom_reset"])

    # Spacer to push right-side buttons
    right_spacer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    right_spacer.set_hexpand(True)
    tb.append(right_spacer)

    tb.append(Gtk.Separator.new(Gtk.Orientation.VERTICAL))

    # Group 3: Right-side buttons
    tool_buttons["manage_materials"] = create_icon_button(
        "manage_materials", f"{config_constants.MANAGE_MATERIALS_LABEL} (Ctrl+M)")
    tool_buttons["estimate_materials"] = create_icon_button(
        "estimate_materials", f"{
            config_constants.ESTIMATE_MATERIALS_LABEL} (Ctrl+Shift+M)")
    tool_buttons["estimate_cost"] = create_icon_button(
        "estimate_cost", f"{config_constants.ESTIMATE_COST_LABEL} (Ctrl+Shift+C)")
    settings_button = create_icon_button(
        "settings", f"{config_constants.SETTINGS_LABEL} (Ctrl+,)")
    help_button = create_icon_button(
        "help", f"{config_constants.HELP_LABEL} (F1)")

    tb.append(tool_buttons["manage_materials"])
    tb.append(tool_buttons["estimate_materials"])
    tb.append(tool_buttons["estimate_cost"])
    tb.append(settings_button)
    tb.append(help_button)

    extra_buttons = {"settings": settings_button, "help": help_button}

    # Connect toggle button callbacks
    for key, callback in callbacks.items():
        if key in tool_buttons and isinstance(
                tool_buttons[key], Gtk.ToggleButton):
            tool_buttons[key].connect("toggled", callback)

    # Function to set tool visibility based on toolset
    def set_toolset_visibility(toolset_name):
        """Show/hide tool buttons based on selected toolset."""
        if toolset_name not in TOOLSETS:
            return
        
        visible_tools = TOOLSETS[toolset_name]
        
        # List of all toggle tool buttons that can be shown/hidden
        all_tools = ["pointer", "panning", "draw_walls", "draw_rooms", 
                     "add_doors", "add_windows", "add_polyline", 
                     "add_dimension", "add_text", "add_circle", "add_arc", "design_roof"]
        
        for tool_name in all_tools:
            if tool_name in tool_buttons:
                tool_buttons[tool_name].set_visible(tool_name in visible_tools)
    
    # Set initial visibility to Main
    set_toolset_visibility("Main")
    
    # Package toolset info
    toolset_info = {
        "dropdown": toolset_dropdown,
        "definitions": TOOLSETS,
        "set_visibility": set_toolset_visibility
    }

    return tb, tool_buttons, extra_buttons, toolset_info
