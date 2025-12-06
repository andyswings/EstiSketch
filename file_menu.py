import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gio', '2.0')
from gi.repository import Gtk, Gio

def create_file_menu(app):
    # Create a Gio.Menu to serve as the model for the popover menu.
    menu_model = Gio.Menu()
    menu_model.append("New", "app.new")
    menu_model.append("Open", "app.open")
    menu_model.append("Open Recent Project", "app.open_recent")
    #TODO: Add a button at the bottom of the recent files list to clear the list.
    #TODO: Automatically remove files from the recent files list that no longer exist.
    menu_model.append("Import SH3D", "app.import_sh3d")
    # Separator
    menu_model.append_section("", Gio.Menu())
    menu_model.append("Save", "app.save")
    menu_model.append("Save As", "app.save_as")
    menu_model.append("Export", "app.export")
    # Separator
    menu_model.append_section("", Gio.Menu())
    menu_model.append("Settings", "app.settings")
    # Separator
    menu_model.append_section("", Gio.Menu())
    menu_model.append("Exit", "app.exit")

    # Create a MenuButton that shows the popover menu when clicked.
    menu_button = Gtk.MenuButton()
    menu_button.set_icon_name("open-menu-symbolic")
    popover = Gtk.PopoverMenu.new_from_model(menu_model)
    menu_button.set_popover(popover)
    
    return menu_button
