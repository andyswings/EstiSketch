import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio
from types import SimpleNamespace
import config
import toolbar
from Canvas import canvas_area
from Dialogs import settings_ui
from Dialogs import manage_materials
from Dialogs import estimate_materials
from Dialogs import estimate_cost
from Dialogs import help_dialog
from file_menu import create_file_menu
from sh3d_importer import import_sh3d
from project_io import save_project, open_project

class EstimatorApp(Gtk.Application):
    def __init__(self, config_constants):
        super().__init__(application_id="com.example.estimator")
        self.config = config_constants
    
    def do_startup(self):
        Gtk.Application.do_startup(self)
        
        # Add an action to clear canvas and start a new drawing
        new_action = Gio.SimpleAction.new("new")
        new_action.connect("activate", self.on_new)
        self.add_action(new_action)
        
        # Add an action for importing SH3D files.
        import_action = Gio.SimpleAction.new("import_sh3d", None)
        import_action.connect("activate", self.on_import_sh3d)
        self.add_action(import_action)
        
        # Add an action for opening opening settings dialog
        settings_action = Gio.SimpleAction.new("settings")
        settings_action.connect("activate", self.on_settings_clicked)
        self.add_action(settings_action)
        
        # Open project
        open_action = Gio.SimpleAction.new("open", None)
        open_action.connect("activate", lambda a, p: self.show_open_dialog())
        self.add_action(open_action)

        # Save project
        save_action = Gio.SimpleAction.new("save", None)
        save_action.connect("activate", lambda a, p: self.show_save_dialog())
        self.add_action(save_action)
        # (Other actions like "exit" etc. are added similarly.)

    def do_activate(self):
        self.window = Gtk.ApplicationWindow(
            application=self,
            title=self.config.WINDOW_TITLE
        )
        self.window.set_default_size(self.config.WINDOW_WIDTH, self.config.WINDOW_HEIGHT)
        self.window.maximize()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.window.set_child(vbox)
        
        # Create the file menu button and add it at the top
        file_menu_button = create_file_menu(self)
        # Pack the menu button in a horizontal box to simulate a menu bar area.
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header_box.append(file_menu_button)
        vbox.append(header_box)

        self.canvas = canvas_area.create_canvas_area(self.config)

        # Define toggle callbacks.
        def on_pointer_toggled(toggle_button):
            if toggle_button.get_active():
                self.tool_buttons["panning"].set_active(False)
                self.tool_buttons["draw_walls"].set_active(False)
                self.tool_buttons["draw_rooms"].set_active(False)
                self.tool_buttons["add_doors"].set_active(False)
                self.tool_buttons["add_windows"].set_active(False)
                self.canvas.set_tool_mode("pointer")
                print("Pointer mode activated")
            else:
                self.canvas.set_tool_mode(None)

        def on_panning_toggled(toggle_button):
            if toggle_button.get_active():
                self.tool_buttons["pointer"].set_active(False)
                self.tool_buttons["draw_walls"].set_active(False)
                self.tool_buttons["draw_rooms"].set_active(False)
                self.tool_buttons["add_doors"].set_active(False)
                self.tool_buttons["add_windows"].set_active(False)
                self.canvas.set_tool_mode("panning")
                cursor = Gdk.Cursor.new_from_name("grab", None)
                self.canvas.set_cursor(cursor)
                print("Panning mode activated")
            else:
                self.canvas.set_cursor(None)
                self.canvas.set_tool_mode(None)

        def on_draw_walls_toggled(toggle_button):
            if toggle_button.get_active():
                self.tool_buttons["pointer"].set_active(False)
                self.tool_buttons["panning"].set_active(False)
                self.tool_buttons["draw_rooms"].set_active(False)
                self.tool_buttons["add_doors"].set_active(False)
                self.tool_buttons["add_windows"].set_active(False)
                self.canvas.set_tool_mode("draw_walls")
                print("Draw walls mode activated")
            else:
                self.canvas.set_tool_mode(None)
        
        def on_add_windows_toggled(toggle_button):
            if toggle_button.get_active():
                self.tool_buttons["pointer"].set_active(False)
                self.tool_buttons["panning"].set_active(False)
                self.tool_buttons["draw_walls"].set_active(False)
                self.tool_buttons["draw_rooms"].set_active(False)
                self.tool_buttons["add_doors"].set_active(False)
                self.canvas.set_tool_mode("add_windows")
                print("Add windows mode activated")
            else:
                self.canvas.set_tool_mode(None)

        def on_draw_rooms_toggled(toggle_button):
            if toggle_button.get_active():
                self.tool_buttons["pointer"].set_active(False)
                self.tool_buttons["panning"].set_active(False)
                self.tool_buttons["draw_walls"].set_active(False)
                self.tool_buttons["add_doors"].set_active(False)
                self.tool_buttons["add_windows"].set_active(False)
                self.canvas.set_tool_mode("draw_rooms")
                print("Draw rooms mode activated")
            else:
                self.canvas.set_tool_mode(None)
        
        def on_add_doors_toggled(toggle_button):
            if toggle_button.get_active():
                # Deactivate other tools.
                self.tool_buttons["pointer"].set_active(False)
                self.tool_buttons["panning"].set_active(False)
                self.tool_buttons["draw_walls"].set_active(False)
                self.tool_buttons["draw_rooms"].set_active(False)
                self.tool_buttons["add_windows"].set_active(False)
                # Activate add_doors mode.
                self.canvas.set_tool_mode("add_doors")
                print("Add doors mode activated")
            else:
                self.canvas.set_tool_mode(None)
            

        callbacks = {
            "pointer": on_pointer_toggled,
            "panning": on_panning_toggled,
            "draw_walls": on_draw_walls_toggled,
            "draw_rooms": on_draw_rooms_toggled,
            "add_doors": on_add_doors_toggled,
            "add_windows": on_add_windows_toggled
        }
        toolbar_box, self.tool_buttons, extra_buttons = toolbar.create_toolbar(self.config, callbacks, self.canvas)
        vbox.append(toolbar_box)
        vbox.append(self.canvas)

        # Connect non-toggle button actions.
        self.tool_buttons["save"].connect("clicked", lambda btn: self.show_save_dialog())
        self.tool_buttons["open"].connect("clicked", lambda btn: self.show_open_dialog())
        self.tool_buttons["export"].connect("clicked", lambda btn: print("Export as PDF triggered"))
        self.tool_buttons["undo"].connect("clicked", lambda btn: self.canvas.undo())
        self.tool_buttons["redo"].connect("clicked", lambda btn: self.canvas.redo())
        self.tool_buttons["manage_materials"].connect("clicked", self.on_manage_materials_clicked)
        self.tool_buttons["estimate_materials"].connect("clicked", self.on_estimate_materials_clicked)
        self.tool_buttons["estimate_cost"].connect("clicked", self.on_estimate_cost_clicked)
        self.tool_buttons["zoom_in"].connect("clicked", self.on_zoom_in_clicked)
        self.tool_buttons["zoom_out"].connect("clicked", self.on_zoom_out_clicked)
        self.tool_buttons["zoom_reset"].connect("clicked", self.on_zoom_reset_clicked)

        # Connect extra buttons.
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
            elif keyname == "escape":
                if self.canvas.tool_mode == "draw_walls" and self.canvas.drawing_wall:
                    print("Esc pressed: Finalizing wall drawing")
                    self.canvas.save_state()
                    self.canvas.wall_sets.append(self.canvas.walls.copy())
                    self.canvas.walls = []
                    self.canvas.current_wall = None
                    self.canvas.drawing_wall = False
                    self.canvas.save_state()
                    self.canvas.queue_draw()
                    return True
                elif self.canvas.tool_mode == "draw_rooms" and self.canvas.current_room_points:
                    print("Esc pressed: Finalizing room drawing")
                    self.canvas.save_state()
                    self.canvas.finalize_room()
                    self.canvas.save_state()
                    self.canvas.queue_draw()
                    return True
            elif keyname == "f1":
                self.on_help_clicked(None)
                return True

        if ctrl_pressed and not shift_pressed:
            if keyname == "z":
                self.canvas.undo()
                return True
            elif keyname == "y":
                self.canvas.redo()
                return True
            elif keyname == "c":
                print("Copy action triggered")
                return True
            elif keyname == "p":
                print("Paste action triggered")
                return True
            elif keyname == "j":
                self.canvas.join_selected_walls()
                return True
            elif keyname == "s":
                self.show_save_dialog()
                return True
            elif keyname == "o":
                self.show_open_dialog()
                return True
            elif keyname == "e":
                print("Export as PDF triggered")
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

        if ctrl_pressed and shift_pressed:
            if keyname == "m":
                self.on_estimate_materials_clicked(None)
                return True
            elif keyname == "c":
                self.on_estimate_cost_clicked(None)
                return True

        return False

    def on_zoom_in_clicked(self, button):
        center_x = self.canvas.get_width() / 2
        center_y = self.canvas.get_height() / 2
        self.canvas.adjust_zoom(1.1, center_x, center_y)

    def on_zoom_out_clicked(self, button):
        center_x = self.canvas.get_width() / 2
        center_y = self.canvas.get_height() / 2
        self.canvas.adjust_zoom(0.9, center_x, center_y)

    def on_zoom_reset_clicked(self, button):
        self.canvas.reset_zoom()

    def on_settings_clicked(self, button, *args):
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
    
    def on_import_sh3d(self, action, parameter):
        # Create a standard file chooser dialog.
        dialog = Gtk.FileChooserDialog(
            title="Import SH3D File",
            transient_for=self.window,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Open", Gtk.ResponseType.OK)
        
        # Add a file filter for .sh3d files.
        sh3d_filter = Gtk.FileFilter()
        sh3d_filter.set_name("Sweet Home 3D Files")
        sh3d_filter.add_pattern("*.sh3d")
        dialog.add_filter(sh3d_filter)
        
        dialog.connect("response", self.on_import_sh3d_response)
        dialog.show()

    def on_import_sh3d_response(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            file = dialog.get_file()
            sh3d_file = file.get_path()
            try:
                imported = import_sh3d(sh3d_file)
                # Clear the current canvas content.
                self.canvas.wall_sets.clear()
                self.canvas.walls.clear()
                self.canvas.rooms.clear()
                # Populate the canvas with imported data.
                self.canvas.wall_sets.extend(imported["wall_sets"])
                self.canvas.rooms.extend(imported["rooms"])
                self.canvas.doors.extend(imported["doors"])
                self.canvas.windows.extend(imported["windows"])
                # Request redraw of canvas
                self.canvas.queue_draw()
            except Exception as e:
                print(f"Error importing SH3D file: {e}")
        dialog.destroy()
    
    def on_new(self, action, parameter):
        # Clear the current canvas content.
        self.canvas.wall_sets.clear()
        self.canvas.walls.clear()
        self.canvas.rooms.clear()
        self.canvas.doors.clear()
        self.canvas.windows.clear()
        # Request redraw of canvas
        self.canvas.queue_draw()

    def show_save_dialog(self):
        # Create GTK4 FileDialog (requires GTK >= 4.10)
        dlg = Gtk.FileDialog.new()
        dlg.set_title("Save Project")
        dlg.set_modal(True)

        # Set XML filter
        xml_filter = Gtk.FileFilter()
        xml_filter.set_name("Project Files (*.xml)")
        xml_filter.add_pattern("*.xml")
        filter_store = Gio.ListStore.new(Gtk.FileFilter)
        filter_store.append(xml_filter)
        dlg.set_filters(filter_store)
        dlg.set_default_filter(xml_filter)

        dlg.save(self.window, None, self.on_file_dialog_save_done, None)

    def on_file_dialog_save_done(self, obj, result, user_data):
        # Finish the async call and get a Gio.File
        file = obj.save_finish(result)
        if file:
            path = file.get_path()
            # Ensure .xml extension
            if not path.lower().endswith(".xml"):
                path += ".xml"
            save_project(
                self.canvas,
                self.window.get_width(),
                self.window.get_height(),
                path
            )

    def show_open_dialog(self):
        dlg = Gtk.FileDialog.new()
        dlg.set_title("Open Project")
        dlg.set_modal(True)

        # Set XML filter
        xml_filter = Gtk.FileFilter()
        xml_filter.set_name("Project Files (*.xml)")
        xml_filter.add_pattern("*.xml")
        filter_store = Gio.ListStore.new(Gtk.FileFilter)
        filter_store.append(xml_filter)
        dlg.set_filters(filter_store)
        dlg.set_default_filter(xml_filter)

        dlg.open(self.window, None, self.on_file_dialog_open_done, None)

    def on_file_dialog_open_done(self, obj, result, user_data):
        file = obj.open_finish(result)
        if file:
            path = file.get_path()
            open_project(self.canvas, path)
            self.canvas.queue_draw()


def main():
    config_dict = config.load_config()
    settings = SimpleNamespace(**config_dict)
    app = EstimatorApp(settings)
    app.run(None)

if __name__ == "__main__":
    main()
