"""Main application file menu popover builder."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, Gtk  # noqa: E402


def create_file_menu(app: Gtk.Application) -> Gtk.MenuButton:
    """Create the top-left application file menu button bound to Gio actions."""
    menu_model = Gio.Menu()
    menu_model.append("New", "app.new")
    menu_model.append("Open", "app.open")
    menu_model.append("Open Recent Project", "app.open_recent")
    menu_model.append("Import SH3D", "app.import_sh3d")
    menu_model.append("Import Blueprint...", "app.import_blueprint")

    menu_model.append_section("", Gio.Menu())
    menu_model.append("Save", "app.save")
    menu_model.append("Save As", "app.save_as")
    menu_model.append("Print / Export (PDF / SVG)...", "app.print")
    menu_model.append("Export 3D Model (.glb)...", "app.export_glb")
    menu_model.append("Open 3D in Blender...", "app.open_in_blender")

    menu_model.append_section("", Gio.Menu())
    menu_model.append("Settings", "app.settings")

    menu_model.append_section("", Gio.Menu())
    menu_model.append("Exit", "app.exit")

    menu_button = Gtk.MenuButton()
    menu_button.set_icon_name("open-menu-symbolic")
    popover = Gtk.PopoverMenu.new_from_model(menu_model)
    menu_button.set_popover(popover)

    return menu_button
