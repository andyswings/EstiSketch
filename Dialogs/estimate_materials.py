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

    # Display results
    label = Gtk.Label()
    label.set_markup(
        f"<b>Framing Material Estimate</b>\n\n"
        f"Total Studs: {estimates['total_studs']}\n"
        f"Top Plates: {estimates['total_top_plates']}\n"
        f"Bottom Plates: {estimates['total_bottom_plates']}\n"
    )
    label.set_halign(Gtk.Align.START)
    content_area.append(label)

    # Add OK button
    dialog.add_button("OK", Gtk.ResponseType.OK)
    dialog.connect("response", lambda d, r: d.destroy())

    return dialog