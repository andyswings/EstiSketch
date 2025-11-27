import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from Takeoff.framing_takeoff import FramingEstimator


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
    
    label_string = """<b>Framing Material Estimate</b>"""
    
    for key, value in estimates.items():
        if not value:
            continue
        if key in ["wall_details", "wall_plates_length"]:
            continue
        if "studs" in key:
            label_string = f"{key}: {value}\n"
        elif "top_plates" in key or "bottom_plates" in key:
            if "2x4" in key:
                nominal_width = 4
            elif "2x6" in key:
                nominal_width = 6
            elif "2x8" in key:
                nominal_width = 8
            else:
                nominal_width = 4  # Default to 2x4 if unknown
            
            pieces = int(value // estimates['wall_plates_length']) + 1
            plate_length_feet = int(estimates['wall_plates_length'] / 12)
            
            label_string += (
            f"\n{key}: {pieces} --- 2 x {nominal_width}"
            f" x {plate_length_feet}"
        )

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