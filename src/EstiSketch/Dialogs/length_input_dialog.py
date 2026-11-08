from gi.repository import Gtk
import gi
gi.require_version('Gtk', '4.0')


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


class NearFootConfirmDialog(Gtk.Dialog):
    """Confirmation dialog asking whether to snap a near-whole-foot wall length to the nearest foot."""

    def __init__(self, parent=None, drawn_str: str = "", target_str: str = ""):
        super().__init__(title="Snap Wall to Nearest Foot?", transient_for=parent)
        self.set_modal(True)
        self.set_default_size(360, 120)

        content_area = self.get_content_area()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        content_area.append(box)

        msg = (
            f"Wall length is {drawn_str}, which is very close to {target_str}.\n\n"
            f"Would you like to snap it to {target_str}?"
        )
        label = Gtk.Label(label=msg)
        label.set_wrap(True)
        box.append(label)

        self.add_button(f"Keep {drawn_str}", Gtk.ResponseType.CANCEL)
        ok_btn = self.add_button(f"Snap to {target_str}", Gtk.ResponseType.OK)
        if ok_btn is not None:
            ok_btn.add_css_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.OK)


def create_near_foot_confirm_dialog(parent, drawn_str: str, target_str: str):
    return NearFootConfirmDialog(parent, drawn_str=drawn_str, target_str=target_str)
