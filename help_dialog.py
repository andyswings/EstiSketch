import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

def create_help_dialog(parent):
    dialog = Gtk.Dialog(
        title="Help",
        transient_for=parent,
        modal=True
    )
    dialog.set_default_size(400, 300)  # Same size as other dialogs for consistency

    # Add a simple message
    content_area = dialog.get_content_area()
    label = Gtk.Label(label="""    Thought you were getting help, didn't you? Laugh's on you! 😂 
    Who would help you anyway? Certainly not anyone here, we haven't got time. 
    You'd better just figure it out on your own.""")
    label.set_margin_top(20)
    label.set_margin_bottom(20)
    label.set_margin_start(20)
    label.set_margin_end(20)
    content_area.append(label)

    # Add an OK button to close the dialog
    dialog.add_button("OK", Gtk.ResponseType.OK)
    dialog.connect("response", lambda d, r: d.destroy())

    return dialog