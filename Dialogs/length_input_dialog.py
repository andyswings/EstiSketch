import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

class LengthInputDialog(Gtk.Dialog):
    def __init__(self, parent=None, title="Enter Wall Length"):
        super().__init__(title=title, transient_for=parent)
        self.set_modal(True)
        self.set_default_size(300, 100)

        # Content area
        content_area = self.get_content_area()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        content_area.append(box)

        label = Gtk.Label(label="Length (e.g. 10' or 120):")
        box.append(label)

        self.entry = Gtk.Entry()
        self.entry.connect("activate", self.on_enter_pressed)
        box.append(self.entry)

        # Action area buttons
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("OK", Gtk.ResponseType.OK)
    
    def on_enter_pressed(self, entry):
        self.response(Gtk.ResponseType.OK)

    def get_length(self):
        return self.entry.get_text()

def create_length_input_dialog(parent):
    return LengthInputDialog(parent)
