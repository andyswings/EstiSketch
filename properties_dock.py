import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

# Import your domain classes
from components import Wall

# Stub widgets—you can flesh these out with real controls
class WallPropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        lbl = Gtk.Label(label="Wall Properties")
        self.append(lbl)
        # TODO: add controls, e.g. width, material, footer checkbox etc.

class FoundationPropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        lbl = Gtk.Label(label="Foundation Settings")
        self.append(lbl)
        # TODO: add controls for footer offsets, depth, material etc.

class PropertiesDock(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)

        # Icon bar (fixed width, icon-only buttons)
        self.icon_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.icon_bar.set_size_request(40, -1)
        self.append(self.icon_bar)

        # Content stack (hidden until needed)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
                               transition_duration=200)
        self.append(self.stack)
        self.stack.set_visible(False)

        # Track added tabs
        self.tabs = {}

        # Pre-create pages
        self.wall_page = WallPropertiesWidget()
        self.stack.add_titled(self.wall_page, "wall", "Wall")
        self.foundation_page = FoundationPropertiesWidget()
        self.stack.add_titled(self.foundation_page, "foundation", "Foundation")

    def _make_tab_button(self, name, icon_name):
        btn = Gtk.ToggleButton()
        image = Gtk.Image.new_from_icon_name(icon_name)
        btn.set_child(image)
        btn.set_tooltip_text(name.capitalize())
        btn.connect('toggled', lambda b: self._on_tab_toggled(b, name))
        return btn

    def _ensure_tab(self, name, should_show, icon_name):
        if should_show and name not in self.tabs:
            btn = self._make_tab_button(name, icon_name)
            self.icon_bar.append(btn)
            self.tabs[name] = btn
        elif not should_show and name in self.tabs:
            btn = self.tabs.pop(name)
            self.icon_bar.remove(btn)

    def refresh_tabs(self, selected_items):
        wants_wall = any(isinstance(i, Wall) for i in selected_items)
        wants_foundation = wants_wall and any(getattr(i, 'footer', False) for i in selected_items)

        # Show/hide icons
        self._ensure_tab('wall', wants_wall, 'application-inspector')
        self._ensure_tab('foundation', wants_foundation, 'view-filter')

        # Hide stack if current page no longer valid
        current = self.stack.get_visible_child_name()
        valid = {'wall': wants_wall, 'foundation': wants_foundation}
        if current and not valid.get(current, False):
            self.stack.set_visible(False)

    def _on_tab_toggled(self, button, name):
        if button.get_active():
            self.stack.set_visible_child_name(name)
            self.stack.set_visible(True)
            # untoggle others
            for n, b in self.tabs.items():
                if n != name:
                    b.set_active(False)
        else:
            # clicking active icon hides panel
            self.stack.set_visible(False)
