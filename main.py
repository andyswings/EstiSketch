import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from types import SimpleNamespace
import config
import toolbar
import canvas_area
import settings_ui
import manage_materials
import estimate_materials
import estimate_cost
import help_dialog
from components import Wall

class EstimatorApp(Gtk.Application):
    def __init__(self, config_constants):
        super().__init__(application_id="com.example.estimator")
        self.config = config_constants

    def do_activate(self):
        self.window = Gtk.ApplicationWindow(
            application=self,
            title=self.config.WINDOW_TITLE
        )
        self.window.set_default_size(self.config.WINDOW_WIDTH, self.config.WINDOW_HEIGHT)
        self.window.maximize()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.window.set_child(vbox)

        self.canvas = canvas_area.create_canvas_area(self.config)

        # Define toggle callbacks
        def on_pointer_toggled(toggle_button):
            if toggle_button.get_active():
                self.tool_buttons["panning"].set_active(False)
                self.tool_buttons["draw_walls"].set_active(False)
                self.tool_buttons["draw_rooms"].set_active(False)
                self.canvas.set_tool_mode("pointer")
            else:
                self.canvas.set_tool_mode(None)

        def on_panning_toggled(toggle_button):
            if toggle_button.get_active():
                self.tool_buttons["pointer"].set_active(False)
                self.tool_buttons["draw_walls"].set_active(False)
                self.tool_buttons["draw_rooms"].set_active(False)
                self.canvas.set_tool_mode("panning")
            else:
                self.canvas.set_tool_mode(None)

        def on_draw_walls_toggled(toggle_button):
            if toggle_button.get_active():
                self.tool_buttons["pointer"].set_active(False)
                self.tool_buttons["panning"].set_active(False)
                self.tool_buttons["draw_rooms"].set_active(False)
                self.canvas.set_tool_mode("draw_walls")
            else:
                self.canvas.set_tool_mode(None)

        def on_draw_rooms_toggled(toggle_button):
            if toggle_button.get_active():
                self.tool_buttons["pointer"].set_active(False)
                self.tool_buttons["panning"].set_active(False)
                self.tool_buttons["draw_walls"].set_active(False)
                self.canvas.set_tool_mode("draw_rooms")

        callbacks = {
            "pointer": on_pointer_toggled,
            "panning": on_panning_toggled,
            "draw_walls": on_draw_walls_toggled,
            "draw_rooms": on_draw_rooms_toggled
        }
        toolbar_box, self.tool_buttons, extra_buttons = toolbar.create_toolbar(self.config, callbacks, self.canvas)
        vbox.append(toolbar_box)
        vbox.append(self.canvas)

        # Connect all non-toggle button actions
        self.tool_buttons["save"].connect("clicked", lambda btn: print("Save action triggered"))
        self.tool_buttons["open"].connect("clicked", lambda btn: print("Open action triggered"))
        self.tool_buttons["export"].connect("clicked", lambda btn: print("Export as PDF triggered"))
        self.tool_buttons["undo"].connect("clicked", lambda btn: print("Undo action triggered"))
        self.tool_buttons["redo"].connect("clicked", lambda btn: print("Redo action triggered"))
        self.tool_buttons["manage_materials"].connect("clicked", self.on_manage_materials_clicked)
        self.tool_buttons["estimate_materials"].connect("clicked", self.on_estimate_materials_clicked)
        self.tool_buttons["estimate_cost"].connect("clicked", self.on_estimate_cost_clicked)
        self.tool_buttons["zoom_in"].connect("clicked", self.on_zoom_in_clicked)
        self.tool_buttons["zoom_out"].connect("clicked", self.on_zoom_out_clicked)
        self.tool_buttons["zoom_reset"].connect("clicked", self.on_zoom_reset_clicked)

        # Connect extra buttons
        extra_buttons["settings"].connect("clicked", self.on_settings_clicked)
        extra_buttons["help"].connect("clicked", self.on_help_clicked)

        status_label = Gtk.Label(label="Status: Ready")
        vbox.append(status_label)

        self.tool_buttons["draw_walls"].set_active(True)

        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.window.add_controller(key_controller)

        self.window.present()

    def on_key_pressed(self, controller, keyval, keycode, state):
        keyname = Gdk.keyval_name(keyval).lower()
        ctrl_pressed = state & Gdk.ModifierType.CONTROL_MASK
        shift_pressed = state & Gdk.ModifierType.SHIFT_MASK

        if not ctrl_pressed and not shift_pressed:
            if keyname == "v":
                self.tool_buttons["pointer"].set_active(True)
                return True
            elif keyname == "p":
                self.tool_buttons["panning"].set_active(True)
                return True
            elif keyname == "w":
                self.tool_buttons["draw_walls"].set_active(True)
                return True
            elif keyname == "r":
                self.tool_buttons["draw_rooms"].set_active(True)
                return True
            elif keyname == "d":
                self.tool_buttons["add_doors"].set_active(True)
                return True
            elif keyname == "a":
                self.tool_buttons["add_windows"].set_active(True)
                return True
            elif keyname == "m":
                self.tool_buttons["add_dimension"].set_active(True)
                return True
            elif keyname == "t":
                self.tool_buttons["add_text"].set_active(True)
                return True
            elif keyname == "escape" and self.canvas.tool_mode == "draw_walls" and self.canvas.drawing_wall:
                print("Esc pressed: Ending wall drawing")
                self.canvas.wall_sets.append(self.canvas.walls.copy())  # Finalize the current set
                self.canvas.walls = []  # Clear for next set
                self.canvas.current_wall = None
                self.canvas.drawing_wall = False
                self.canvas.queue_draw()
                return True
            elif keyname == "f1":
                self.on_help_clicked(None)
                return True

        # Ctrl + Shift combinations
        if ctrl_pressed and shift_pressed:
            if keyname == "m":
                self.on_estimate_materials_clicked(None)
                return True
            elif keyname == "c":
                self.on_estimate_cost_clicked(None)
                return True

        # Ctrl only combinations
        if ctrl_pressed and not shift_pressed:
            if keyname == "s":
                print("Save action triggered")
                return True
            elif keyname == "o":
                print("Open action triggered")
                return True
            elif keyname == "e":
                print("Export as PDF triggered")
                return True
            elif keyname == "z":
                print("Undo action triggered")
                return True
            elif keyname == "y":
                print("Redo action triggered")
                return True
            elif keyname == "m":
                self.on_manage_materials_clicked(None)
                return True
            elif keyname == "comma":
                self.on_settings_clicked(None)
                return True
            elif keyname == "equal":
                self.on_zoom_in_clicked(None)
                return True
            elif keyname == "minus":
                self.on_zoom_out_clicked(None)
                return True
            elif keyname == "0":
                self.on_zoom_reset_clicked(None)
                return True

        return False

    def on_zoom_in_clicked(self, button):
        allocation = self.canvas.get_allocation()
        center_x = allocation.width / 2
        center_y = allocation.height / 2
        self.canvas.adjust_zoom(1.1, center_x, center_y)

    def on_zoom_out_clicked(self, button):
        allocation = self.canvas.get_allocation()
        center_x = allocation.width / 2
        center_y = allocation.height / 2
        self.canvas.adjust_zoom(0.9, center_x, center_y)

    def on_zoom_reset_clicked(self, button):
        self.canvas.reset_zoom()

    def on_settings_clicked(self, button):
        dialog = settings_ui.create_settings_dialog(self.window, self.config, self.canvas)
        dialog.connect("response", self.on_settings_response)
        dialog.present()

    def on_settings_response(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            print("Settings updated")
            config.save_config(self.config.__dict__)
        dialog.destroy()

    def on_manage_materials_clicked(self, button):
        dialog = manage_materials.create_manage_materials_dialog(self.window)
        dialog.present()

    def on_estimate_materials_clicked(self, button):
        dialog = estimate_materials.create_estimate_materials_dialog(self.window)
        dialog.present()

    def on_estimate_cost_clicked(self, button):
        dialog = estimate_cost.create_estimate_cost_dialog(self.window)
        dialog.present()

    def on_help_clicked(self, button):
        dialog = help_dialog.create_help_dialog(self.window)
        dialog.present()

def main():
    config_dict = config.load_config()
    settings = SimpleNamespace(**config_dict)
    app = EstimatorApp(settings)
    app.run(None)

if __name__ == "__main__":
    main()