import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

def create_estimate_cost_dialog(parent):
    dialog = Gtk.Dialog(
        title="Estimate Cost",
        transient_for=parent,
        modal=True
    )
    dialog.set_default_size(400, 300)  # Same size as other dialogs for consistency

    # Add a simple message
    content_area = dialog.get_content_area()
    label = Gtk.Label(label="Estimate Cost - Coming Soon")
    label.set_margin_top(20)
    label.set_margin_bottom(20)
    label.set_margin_start(20)
    label.set_margin_end(20)
    content_area.append(label)

    # Add an OK button to close the dialog
    dialog.add_button("OK", Gtk.ResponseType.OK)
    dialog.connect("response", lambda d, r: d.destroy())

    return dialog