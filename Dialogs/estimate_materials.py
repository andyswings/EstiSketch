import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from Takeoff.framing_takeoff import FramingEstimator

# import config

# # Read runtime config (falls back to DEFAULT_SETTINGS if settings file missing)
# _cfg = config.load_config() if hasattr(config, "load_config") else getattr(config, "DEFAULT_SETTINGS", {})
# MAX_WALL_PLATE_INCHES = _cfg.get("MAX_WALL_PLATE_INCHES", getattr(config, "DEFAULT_SETTINGS", {}).get("MAX_WALL_PLATE_INCHES", 192))


def create_estimate_materials_dialog(parent, canvas):
    """
    Display material estimates for the project.
    
    Args:
        parent: Parent window.
        canvas: Reference to CanvasArea to access wall_sets and doors/windows.
    """
    dialog = Gtk.Dialog(
        title="Estimate Materials",
        transient_for=parent,
        modal=True
    )
    dialog.set_default_size(600, 400)

    content_area = dialog.get_content_area()
    content_area.set_margin_top(20)
    content_area.set_margin_bottom(20)
    content_area.set_margin_start(20)
    content_area.set_margin_end(20)

    # Build walls_with_openings map from canvas doors/windows
    walls_with_openings = {}
    for door_item in canvas.doors:
        wall, door, ratio = door_item
        wall_id = wall.identifier
        if wall_id not in walls_with_openings:
            walls_with_openings[wall_id] = {"doors": [], "windows": []}
        walls_with_openings[wall_id]["doors"].append(door)

    for window_item in canvas.windows:
        wall, window, ratio = window_item
        wall_id = wall.identifier
        if wall_id not in walls_with_openings:
            walls_with_openings[wall_id] = {"doors": [], "windows": []}
        walls_with_openings[wall_id]["windows"].append(window)

    # Calculate estimates
    estimates = FramingEstimator.estimate_all_walls(canvas.wall_sets, walls_with_openings)
    width = estimates['wall_details'][0]['materials']['wall_width']
    if width == 3.5:
        width = 4
    elif width == 5.5:
        width = 6
    elif width == 7.25:
        width = 8
    label_string = """<b>Framing Material Estimate</b>"""
    for i in estimates:
        if estimates[i] != 0:
            if "studs" in i:
                label_string += f"\n{i}: {estimates[i]}"
            elif "top_plates" in i or "bottom_plates" in i:
                label_string += f"\n{i}: {int(estimates[i] // estimates['wall_plates_length']) + 1} --- 2 x {width}" + f" x {int(estimates['wall_plates_length'] / 12)}"

    # Display results
    label = Gtk.Label()
    label.set_markup(
        label_string
    )
    label.set_halign(Gtk.Align.START)
    content_area.append(label)

    # Add OK button
    dialog.add_button("OK", Gtk.ResponseType.OK)
    dialog.connect("response", lambda d, r: d.destroy())

    return dialog