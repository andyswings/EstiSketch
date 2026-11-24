"""Dialog used by the blueprint calibration wizard.

After the user clicks two reference points on an imported blueprint this
dialog asks for the real-world distance between them.
"""
from gi.repository import Gtk
import gi
gi.require_version('Gtk', '4.0')

from ..measurement_utils import parse_distance


class BlueprintCalibrationDialog(Gtk.Dialog):
    """Ask for the true distance between two calibration points."""

    def __init__(self, parent, measured_inches: float):
        super().__init__(title="Calibrate Blueprint", transient_for=parent)
        self.set_modal(True)
        self.set_default_size(340, 150)
        self.ok_response = Gtk.ResponseType.OK

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for setter in (box.set_margin_top, box.set_margin_bottom,
                       box.set_margin_start, box.set_margin_end):
            setter(16)
        self.get_content_area().append(box)

        box.append(Gtk.Label(
            label="Real distance between the two points\n"
                  "(e.g. 24' 0\", 288, 7500 mm, 7.5 m):",
            xalign=0))

        self.entry = Gtk.Entry()
        self.entry.set_activates_default(True)
        self.entry.connect("activate", lambda e: self.response(Gtk.ResponseType.OK))
        box.append(self.entry)

        self.error_label = Gtk.Label(label="", xalign=0)
        self.error_label.add_css_class("error")
        box.append(self.error_label)

        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Calibrate", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.entry.grab_focus()

    def get_real_inches(self):
        """Return the entered distance in inches, or None if invalid."""
        try:
            return parse_distance(self.entry.get_text())
        except ValueError as exc:
            self.error_label.set_label(str(exc))
            return None
