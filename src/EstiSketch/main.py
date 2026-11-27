import gi
import os
import sys
import json
from typing import Optional, Callable
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GdkPixbuf, GObject
from .version import __version__
from .project_io import save_project, open_project
from .sh3d_importer import import_sh3d
from .file_menu import create_file_menu
from .Dialogs.properties_dock import PropertiesDock
from .Dialogs import help_dialog
from .Dialogs import estimate_cost
from .Dialogs import estimate_materials
from .Dialogs import takeoff_dialog
from .Dialogs import manage_materials
from .Dialogs import settings_ui
from .Printing import print_dialog
from .Canvas import canvas_area
from .Canvas.project_reset import reset_canvas_content
from . import toolbar
from . import config
from . import blender_bridge
from .View3D import Viewport3DWidget
from types import SimpleNamespace

class EstimatorApp(Gtk.Application):
    """
    Main application class.

    This class extends Gtk.Application and implements the application logic,
    including startup, activation, and shutdown phases. It handles file
    operations, UI construction, and application state management.
    """
    def __init__(self, config_constants: SimpleNamespace) -> None:
        """
        Initialize the application.

        Args:
            config_constants: Configuration constants loaded from the config file.
        """
        super().__init__(application_id="com.example.estimator")
        self.config = config_constants
        # Remember where the current project is saved
        self.current_filepath = None
        # Track if the canvas is dirty (modified)
        self.is_dirty = False
        # This is a list of recently opened files.
        self.recent_files = getattr(self.config, 'RECENT_FILES', [])

    def do_startup(self) -> None:
        """
        Perform application startup initialization.

        This method overrides Gtk.Application.do_startup() to register
        application-wide actions (new, open, save, export, settings, etc.)
        and to load global CSS styles used by the UI.

        Actions registered here are available to menus, shortcuts, and
        other widgets for the lifetime of the application.
        """
        Gtk.Application.do_startup(self)

        # Add an action to clear canvas and start a new drawing
        new_action = Gio.SimpleAction.new("new")
        new_action.connect("activate", self.on_new)
        self.add_action(new_action)

        # Print / export PDF
        print_action = Gio.SimpleAction.new("print", None)
        print_action.connect("activate", lambda a, p: self.on_print())
        self.add_action(print_action)

        # Open 3D in Blender / Home Builder 5
        open_blender_action = Gio.SimpleAction.new("open_in_blender", None)
        open_blender_action.connect("activate", self.on_open_in_blender)
        self.add_action(open_blender_action)

        # Export 3D .glb
        export_glb_action = Gio.SimpleAction.new("export_glb", None)
        export_glb_action.connect("activate", self.on_export_glb)
        self.add_action(export_glb_action)

        # Open project
        open_action = Gio.SimpleAction.new("open", None)
        open_action.connect("activate", lambda a, p: self.show_open_dialog())
        self.add_action(open_action)

        # Add an action for opening settings dialog
        settings_action = Gio.SimpleAction.new("settings")
        settings_action.connect("activate", self.on_settings_clicked)
        self.add_action(settings_action)

        # Open recent project
        recent_action = Gio.SimpleAction.new("open_recent", None)
        recent_action.connect("activate", self.on_open_recent)
        self.add_action(recent_action)

        # Clear recent files
        clear_recent_action = Gio.SimpleAction.new("clear_recent", None)
        clear_recent_action.connect("activate", self.on_clear_recent)
        self.add_action(clear_recent_action)

        # Add an action for importing SH3D files.
        import_action = Gio.SimpleAction.new("import_sh3d", None)
        import_action.connect("activate", self.on_import_sh3d)
        self.add_action(import_action)

        # Import a blueprint image as a drawing underlay.
        import_bp_action = Gio.SimpleAction.new("import_blueprint", None)
        import_bp_action.connect("activate", self.on_import_blueprint)
        self.add_action(import_bp_action)

        # Save project
        save_action = Gio.SimpleAction.new("save", None)
        save_action.connect("activate", lambda a, p: self.show_save_dialog())
        self.add_action(save_action)

        # Save project as
        save_as = Gio.SimpleAction.new("save_as", None)
        save_as.connect("activate", lambda a, p: self.show_save_as_dialog())
        self.add_action(save_as)

        # Exit action
        exit_action = Gio.SimpleAction.new("exit", None)
        exit_action.connect("activate", self.on_exit)
        self.add_action(exit_action)

        # Load CSS for status indicator and layers panel
        css_provider = Gtk.CssProvider()
        css = b"""
        .success { color: #33d17a; }
        .error { color: #e01b24; }
        
        /* Layer controls (slightly smaller than default) */
        .layer-control {
            font-size: 13px;
            min-height: 22px;
            min-width: 22px;
            padding: 1px;
        }
        
        /* Object controls (smaller than layers) */
        .object-control {
            font-size: 12px;
            min-height: 18px;
            min-width: 18px;
            padding: 0px;
            margin: 0px;
        }
        .object-row {
            padding: 0px;
            margin: 0px;
        }
        .object-label {
            font-size: 11px;
        }
        """
        css_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self) -> None:
        """
        Create and present the main application window.

        This method overrides Gtk.Application.do_activate() to build the primary UI:
        - Create/configure the main Gtk.ApplicationWindow (size, optional maximize, app icon)
        - Construct the layout containers and top-level widgets (file menu, toolbar, canvas)
        - Wire tool toggle callbacks to switch the canvas tool mode
        - Optionally attach the properties sidebar (Gtk.Paned) when enabled in config
        - Connect UI signals (keyboard shortcuts, selection/status updates, dirty-state tracking)
        - Present the window to the user
        """
        self.window = Gtk.ApplicationWindow(
            application=self,
            title=self.config.WINDOW_TITLE
        )
        self.window.set_default_size(
            self.config.WINDOW_WIDTH,
            self.config.WINDOW_HEIGHT)
            
        if getattr(self.config, 'WINDOW_MAXIMIZED', False):
            self.window.maximize()

        # Set application icon
        icon_path = os.path.join(os.path.dirname(__file__), 'Icons', 'estisketch.png')
        if os.path.exists(icon_path):
            self.window.set_icon_name(None)  # Clear any theme icon
            # Load the icon as a paintable and set it
            icon_file = Gio.File.new_for_path(icon_path)
            icon_texture = Gdk.Texture.new_from_file(icon_file)
            # GTK4 uses the icon theme; we need to add our icon to the search path
            icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            icon_theme.add_search_path(os.path.join(os.path.dirname(__file__), 'Icons'))
            self.window.set_icon_name('estisketch')

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.window.set_child(vbox)

        # Create the file menu button and add it at the top
        file_menu_button = create_file_menu(self)
        # save a reference so we can anchor the recent‑files popover
        self.file_menu_button = file_menu_button
        # Top header bar with file menu on the left and 2D | Split | 3D switcher centered.
        header_box = Gtk.CenterBox()
        header_box.set_start_widget(file_menu_button)

        view_switcher = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        view_switcher.add_css_class("linked")
        self._view_mode_buttons: dict[str, Gtk.ToggleButton] = {}
        first_view_btn: Optional[Gtk.ToggleButton] = None
        for mode_key, mode_label in (("2d", "2D"), ("split", "Split"), ("3d", "3D")):
            vbtn = Gtk.ToggleButton(label=mode_label)
            if first_view_btn is None:
                first_view_btn = vbtn
                vbtn.set_active(True)
            else:
                vbtn.set_group(first_view_btn)
            vbtn.connect(
                "toggled",
                lambda b, m=mode_key: self.set_view_mode(m) if b.get_active() else None,
            )
            view_switcher.append(vbtn)
            self._view_mode_buttons[mode_key] = vbtn
        header_box.set_center_widget(view_switcher)
        vbox.append(header_box)

        self.canvas = canvas_area.create_canvas_area(self.config)
        self.viewport_3d = Viewport3DWidget(
            self.canvas, on_export_glb=self.show_export_glb_dialog
        )
        self.view_mode: str = "2d"
        self.canvas.connect("content-changed", lambda _c: self.viewport_3d.mark_dirty())

        self.canvas.connect("selection-changed", self._on_canvas_selection_changed)

        # Define toggle callbacks.

        TOGGLE_BTNS = ["pointer", "draw_walls", "draw_rooms", "add_floor_opening", "add_doors", "add_windows", 
        "add_polyline", "add_dimension", "add_text", "add_stair", "add_fixture", "add_kitchen_layout", "draw_cabinet_run", "panning", "add_dimension_chain", 
        "add_leader", "design_roof", "add_roof_line", "add_arc", "add_circle"]


        def on_btn_toggled(btn_to_toggle: str, toggle_button: Gtk.Button, toggle_btn_list: list):
            """
            Handle toolbar button toggling.

            This method is called when a toolbar button is clicked, selecting the clicked button 
            and deselecting all the others. Sets tool mode which tells the canvas which tool to draw or select with.

            Args:
                btn_to_toggle (str): name of button we want to select.
                toggle_button (Gtk.button): Gtk button
                toggle_btn_list (list): List of all the names of the toggle buttons available.
            
            Returns:
                None
            """
            if toggle_button.get_active():
                for btn in toggle_btn_list:
                    if btn == btn_to_toggle:
                        self.tool_buttons[btn].set_active(True)
                        self.canvas.set_tool_mode(btn)
                    else:
                        self.tool_buttons[btn].set_active(False)
                    if btn == "panning":
                        cursor = Gdk.Cursor.new_from_name("grab", None)
                        self.canvas.set_cursor(cursor)
                    else:
                        self.canvas.set_cursor(None)
                    if self.config.DEBUG:
                        print(f"{btn} mode activated")
            else:
                self.canvas.set_tool_mode(None)
        

        def on_pointer_toggled(toggle_button):
            on_btn_toggled("pointer", toggle_button, TOGGLE_BTNS)

        def on_panning_toggled(toggle_button):
            on_btn_toggled("panning", toggle_button, TOGGLE_BTNS)

        def on_draw_walls_toggled(toggle_button):
            on_btn_toggled("draw_walls", toggle_button, TOGGLE_BTNS)

        def on_add_windows_toggled(toggle_button):
            on_btn_toggled("add_windows", toggle_button, TOGGLE_BTNS)

        def on_draw_rooms_toggled(toggle_button):
            on_btn_toggled("draw_rooms", toggle_button, TOGGLE_BTNS)

        def on_add_floor_opening_toggled(toggle_button):
            on_btn_toggled("add_floor_opening", toggle_button, TOGGLE_BTNS)

        def on_add_doors_toggled(toggle_button):
            on_btn_toggled("add_doors", toggle_button, TOGGLE_BTNS)

        def on_add_polyline_toggled(toggle_button):
            on_btn_toggled("add_polyline", toggle_button, TOGGLE_BTNS)

        def on_add_dimension_toggled(toggle_button):
            on_btn_toggled("add_dimension", toggle_button, TOGGLE_BTNS)

        def on_add_text_toggled(toggle_button):
            on_btn_toggled("add_text", toggle_button, TOGGLE_BTNS)

        def on_add_circle_toggled(toggle_button):
            on_btn_toggled("add_circle", toggle_button, TOGGLE_BTNS)

        def on_add_arc_toggled(toggle_button):
            on_btn_toggled("add_arc", toggle_button, TOGGLE_BTNS)

        def on_design_roof_toggled(toggle_button):
            on_btn_toggled("design_roof", toggle_button, TOGGLE_BTNS)

        def on_add_stair_toggled(toggle_button):
            on_btn_toggled("add_stair", toggle_button, TOGGLE_BTNS)

        def open_fixture_browser():
            from EstiSketch.Dialogs.fixture_browser import FixtureBrowserDialog
            if not getattr(self, "_fixture_browser_win", None):
                self._fixture_browser_win = FixtureBrowserDialog(self.window, self.canvas)
                self._fixture_browser_win.connect(
                    "close-request",
                    lambda _w: (setattr(self, "_fixture_browser_win", None), False)[1],
                )
            self._fixture_browser_win.present()

        def open_kitchen_layout_dialog():
            from EstiSketch.Dialogs.fixture_browser import KitchenLayoutDialog
            if not getattr(self, "_kitchen_layout_win", None):
                self._kitchen_layout_win = KitchenLayoutDialog(self.window, self.canvas)
                self._kitchen_layout_win.connect(
                    "close-request",
                    lambda _w: (setattr(self, "_kitchen_layout_win", None), False)[1],
                )
            self._kitchen_layout_win.present()

        def on_add_fixture_toggled(toggle_button):
            on_btn_toggled("add_fixture", toggle_button, TOGGLE_BTNS)
            if toggle_button.get_active():
                open_fixture_browser()

        def on_add_kitchen_layout_toggled(toggle_button):
            on_btn_toggled("add_kitchen_layout", toggle_button, TOGGLE_BTNS)
            if toggle_button.get_active():
                open_kitchen_layout_dialog()

        def on_draw_cabinet_run_toggled(toggle_button):
            on_btn_toggled("draw_cabinet_run", toggle_button, TOGGLE_BTNS)

        def on_add_roof_line_toggled(toggle_button):
            on_btn_toggled("add_roof_line", toggle_button, TOGGLE_BTNS)

        def on_add_dimension_chain_toggled(toggle_button):
            on_btn_toggled("add_dimension_chain", toggle_button, TOGGLE_BTNS)

        def on_add_leader_toggled(toggle_button):
            on_btn_toggled("add_leader", toggle_button, TOGGLE_BTNS)

        callbacks = {
            "pointer": on_pointer_toggled,
            "panning": on_panning_toggled,
            "draw_walls": on_draw_walls_toggled,
            "draw_rooms": on_draw_rooms_toggled,
            "add_floor_opening": on_add_floor_opening_toggled,
            "add_doors": on_add_doors_toggled,
            "add_windows": on_add_windows_toggled,
            "add_polyline": on_add_polyline_toggled,
            "add_dimension": on_add_dimension_toggled,
            "add_dimension_chain": on_add_dimension_chain_toggled,
            "add_leader": on_add_leader_toggled,
            "add_text": on_add_text_toggled,
            "add_circle": on_add_circle_toggled,
            "add_arc": on_add_arc_toggled,
            "design_roof": on_design_roof_toggled,
            "add_stair": on_add_stair_toggled,
            "add_fixture": on_add_fixture_toggled,
            "add_kitchen_layout": on_add_kitchen_layout_toggled,
            "draw_cabinet_run": on_draw_cabinet_run_toggled,
            "add_roof_line": on_add_roof_line_toggled
        }

        toolbar_box, self.tool_buttons, extra_buttons, self.toolset_info = toolbar.create_toolbar(
            self.config, callbacks, self.canvas)
        vbox.append(toolbar_box)

        # Clicking an already-active fixture or layout button re-presents its palette/dialog
        for btn_key, opener in (
            ("add_fixture", open_fixture_browser),
            ("add_kitchen_layout", open_kitchen_layout_dialog),
        ):
            btn = self.tool_buttons.get(btn_key)
            if btn is not None:
                reopen_click = Gtk.GestureClick()
                reopen_click.connect(
                    "pressed",
                    lambda _g, _n, _x, _y, b=btn, fn=opener: fn() if b.get_active() else None,
                )
                btn.add_controller(reopen_click)

        self._open_fixture_browser = open_fixture_browser
        self._open_kitchen_layout_dialog = open_kitchen_layout_dialog

        # Connect toolset dropdown to switch handler
        self.toolset_info["dropdown"].connect(
            "notify::selected", self.on_toolset_changed)

        self.workspace_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.workspace_paned.set_hexpand(True)
        self.workspace_paned.set_vexpand(True)
        self.workspace_paned.set_resize_start_child(True)
        self.workspace_paned.set_resize_end_child(True)
        self.workspace_paned.set_shrink_start_child(True)
        self.workspace_paned.set_shrink_end_child(True)
        self.workspace_paned.set_start_child(self.canvas)
        self.viewport_3d.set_visible(False)

        main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main_paned.set_start_child(self.workspace_paned)
        self.main_paned = main_paned

        # Only show properties panel if enabled in config
        if getattr(self.config, 'SHOW_PROPERTIES_PANEL', False):
            # Add Properties Dock
            self.properties_dock = PropertiesDock(self.canvas, self.config)
            # Give canvas a reference to properties dock so it can update
            # sidebar values
            self.canvas.properties_dock = self.properties_dock

            # Use Paned for resizing
            main_paned.set_end_child(self.properties_dock)
            main_paned.set_resize_end_child(False)
            main_paned.set_shrink_end_child(False)
            main_paned.set_shrink_start_child(True)

            # Set initial position based on config

            # Defer position setting until window is mapped (realized)
            # This ensures we get the correct window dimensions
            def set_initial_position(*args):
                width = self.window.get_width()
                if width > 0:
                    main_paned.set_position(width - 320)
                return False  # Disconnect the handler
            
            self.window.connect('map', set_initial_position)

            # Update toggle behavior to use paned
            self.properties_dock.connect(
                'sidebar-toggled', self.on_sidebar_toggled)

        vbox.append(main_paned)

        # Connect non-toggle button actions.
        self.tool_buttons["save"].connect(
            "clicked", lambda btn: self.show_save_dialog())
        self.tool_buttons["open"].connect(
            "clicked", lambda btn: self.show_open_dialog())
        self.tool_buttons["export"].connect(
            "clicked", lambda btn: self.on_print())
        self.tool_buttons["undo"].connect(
            "clicked", lambda btn: self.canvas.undo())
        self.tool_buttons["redo"].connect(
            "clicked", lambda btn: self.canvas.redo())
        self.tool_buttons["manage_materials"].connect(
            "clicked", self.on_manage_materials_clicked)
        self.tool_buttons["estimate_materials"].connect(
            "clicked", self.on_estimate_materials_clicked)
        self.tool_buttons["estimate_cost"].connect(
            "clicked", self.on_estimate_cost_clicked)
        self.tool_buttons["zoom_in"].connect(
            "clicked", self.on_zoom_in_clicked)
        self.tool_buttons["zoom_out"].connect(
            "clicked", self.on_zoom_out_clicked)
        self.tool_buttons["zoom_reset"].connect(
            "clicked", self.on_zoom_reset_clicked)

        # Connect extra buttons.
        extra_buttons["settings"].connect("clicked", self.on_settings_clicked)
        extra_buttons["help"].connect("clicked", self.on_help_clicked)

        # Status Bar Area
        # Status Bar Area (CenterBox to center the hint)
        status_box = Gtk.CenterBox()
        status_box.set_margin_start(10)
        status_box.set_margin_end(10)
        status_box.set_margin_bottom(4)
        vbox.append(status_box)

        # Dirty Indicator (Circle icon) - Left widget
        self.dirty_indicator = Gtk.Image.new_from_icon_name("media-record-symbolic")
        self.dirty_indicator.set_pixel_size(16)
        status_box.set_start_widget(self.dirty_indicator)
        
        # Tool Hints Label - Center widget
        self.status_label = Gtk.Label(label="Ready")
        # Ensure label doesn't expand to push others if text is long, use ellipsization if needed?
        # Actually Gtk.CenterBox handles it well.
        status_box.set_center_widget(self.status_label)
        
        # Connect to canvas status updates
        self.canvas.connect('status-update', self.on_status_update)

        self.tool_buttons["pointer"].set_active(True)

        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.window.add_controller(key_controller)

        self.properties_dock.refresh_tabs(self.canvas.selected_items)

        self.window.present()

        # ---- Dirty State Handling ----
        # Connect the "changed" signal of the canvas to set the dirty state.
        orig_save_state = self.canvas.save_state

        def save_state_mark_dirty(*args, **kwargs):
            orig_save_state(*args, **kwargs)
            self.update_dirty_state(True)
        self.canvas.save_state = save_state_mark_dirty

        # Initialize as clean
        self.update_dirty_state(False)

        # Connect the "destroy" signal to check for unsaved changes.
        self.window.connect("close-request", self.on_close_request)

    def on_status_update(self, canvas: canvas_area.CanvasArea, message: str) -> None:
        """Update the status bar text."""
        self.status_label.set_label(message)

    def on_toolset_changed(self, dropdown: Gtk.DropDown, pspec: GObject.ParamSpec) -> None:
        """
        Handle changes to the active toolset.

        Updates which tools are visible based on the selected toolset, clears any
        current canvas selection, and activates the default (first) tool in the
        newly selected toolset.
        """
        selected_index = dropdown.get_selected()
        toolset_names = list(self.toolset_info["definitions"].keys())
        
        if selected_index < len(toolset_names):
            toolset_name = toolset_names[selected_index]
            visible_tools = self.toolset_info["definitions"][toolset_name]
            
            # Clear selection when switching toolsets
            self.canvas.selected_items = []
            self.canvas.queue_draw()
            
            # Always reset to first tool in the new toolset
            first_tool = visible_tools[0] if visible_tools else "pointer"
            if first_tool in self.tool_buttons:
                self.tool_buttons[first_tool].set_active(True)
            
            # Update visibility
            self.toolset_info["set_visibility"](toolset_name)
            print(f"Switched to toolset: {toolset_name}")
    
    def update_dirty_state(self, is_dirty: bool) -> None:
        """
        Update the application's dirty state and visual indicator.

        Sets the internal dirty flag and updates the status indicator color and
        tooltip to reflect whether there are unsaved changes. A dirty state is
        shown in red, while a clean state is shown in green.
        """
        self.is_dirty = is_dirty
        
        context = self.dirty_indicator.get_style_context()
        if context.has_class("success"):
            context.remove_class("success")
        if context.has_class("error"):
            context.remove_class("error")

        if self.is_dirty:
            context.add_class("error")
            self.dirty_indicator.set_tooltip_text("Unsaved changes")
        else:
            context.add_class("success")
            self.dirty_indicator.set_tooltip_text("All changes saved")

    def _on_canvas_selection_changed(self, _canvas: object, selected: object) -> None:
        if hasattr(self, "properties_dock") and self.properties_dock:
            self.properties_dock.refresh_tabs(selected)
        self.viewport_3d.sync_selection_from_canvas()

    def on_key_pressed(self, controller: Gtk.EventControllerKey, keyval: int, keycode: int, state: Gdk.ModifierType) -> bool:
        """
        Handle global keyboard shortcuts and tool commands.

        Interprets key presses with and without modifier keys (Ctrl, Shift) to:
        - Switch active drawing tools
        - Control canvas editing actions (undo/redo, copy/paste, delete)
        - Finalize or cancel in-progress drawing operations
        - Trigger application commands (open, save, export, help, zoom)

        Returns True if the key event was handled and should not propagate further,
        otherwise returns False.
        """
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
                if self.canvas.tool_mode in ("add_fixture", "add_kitchen_layout"):
                    self.canvas.rotate_active_fixture_preview(90.0)
                    return True
                elif self.canvas.tool_mode == "draw_cabinet_run":
                    self.canvas.cabinet_run_side = -1.0 if getattr(self.canvas, "cabinet_run_side", 1.0) >= 0.0 else 1.0
                    self.canvas._cabinet_run_manual_side = True
                    self.canvas.queue_draw()
                    return True
                self.tool_buttons["draw_rooms"].set_active(True)
                return True
            elif keyname == "f":
                if self.tool_buttons["add_fixture"].get_active():
                    self._open_fixture_browser()
                else:
                    self.tool_buttons["add_fixture"].set_active(True)
                return True
            elif keyname == "k":
                if self.tool_buttons["add_kitchen_layout"].get_active():
                    self._open_kitchen_layout_dialog()
                else:
                    self.tool_buttons["add_kitchen_layout"].set_active(True)
                return True
            elif keyname == "o":
                self.tool_buttons["add_floor_opening"].set_active(True)
                return True
            elif keyname == "d":
                self.tool_buttons["add_doors"].set_active(True)
                return True
            elif keyname == "a":
                self.tool_buttons["add_windows"].set_active(True)
                return True
            elif keyname == "l":
                self.tool_buttons["add_polyline"].set_active(True)
                return True
            elif keyname == "t":
                self.tool_buttons["add_text"].set_active(True)
                return True
            elif keyname == "m":
                self.tool_buttons["add_dimension"].set_active(True)
                return True
            elif keyname == "s":
                self.tool_buttons["add_stair"].set_active(True)
                return True
            elif keyname == "escape":
                if self.canvas.tool_mode in ("calibrate_blueprint", "move_blueprint", "straighten_blueprint"):
                    self.canvas.cancel_blueprint_tool()
                    return True
                if self.canvas.tool_mode == "draw_walls" and self.canvas.drawing_wall:
                    self.canvas.wall_sets.append(self.canvas.walls.copy())
                    self.canvas.walls = []
                    self.canvas.current_wall = None
                    self.canvas.drawing_wall = False
                    self.canvas.wall_curve_mode = False
                    self.canvas.wall_curve_point = None
                    from EstiSketch.Resources.tool_hints import TOOL_HINTS
                    self.canvas.update_hint(TOOL_HINTS["draw_walls"])
                    self.canvas.save_state()
                    self.canvas.queue_draw()
                    return True
                if self.canvas.tool_mode == "add_polyline" and self.canvas.drawing_polyline:
                    self.canvas.save_state()
                    if self.canvas.polylines:
                        self.canvas.polyline_sets.append(
                            self.canvas.polylines.copy())
                    self.canvas.drawing_polyline = False
                    self.canvas.current_polyline_start = None
                    self.canvas.current_polyline_preview = None
                    self.canvas.polylines = []
                    from EstiSketch.Resources.tool_hints import TOOL_HINTS
                    self.canvas.update_hint(TOOL_HINTS["add_polyline"])
                    self.canvas.save_state()
                    self.canvas.queue_draw()
                    return True
                elif self.canvas.tool_mode == "draw_rooms" and self.canvas.current_room_points:
                    self.canvas.save_state()
                    self.canvas.finalize_room()
                    self.canvas.save_state()
                    self.canvas.queue_draw()
                    return True
                elif self.canvas.tool_mode == "add_floor_opening" and getattr(self.canvas, "current_opening_points", None):
                    self.canvas.finalize_floor_opening()
                    return True
                elif self.canvas.tool_mode in ("add_fixture", "add_kitchen_layout", "draw_cabinet_run"):
                    if hasattr(self.canvas, "_reset_fixture_interaction_state"):
                        self.canvas._reset_fixture_interaction_state()
                    from EstiSketch.Resources.tool_hints import TOOL_HINTS
                    self.canvas.update_hint(TOOL_HINTS.get(self.canvas.tool_mode, ""))
                    self.canvas.queue_draw()
                    return True
                elif self.canvas.tool_mode == "add_stair" and getattr(self.canvas, "action_state", "idle") != "idle":
                    self.canvas.temp_object = None
                    self.canvas.temp_start_point = None
                    self.canvas.action_state = "idle"
                    from EstiSketch.Resources.tool_hints import TOOL_HINTS
                    self.canvas.update_hint(TOOL_HINTS["add_stair"])
                    self.canvas.queue_draw()
                    return True
                elif self.canvas.tool_mode == "add_dimension" and getattr(self.canvas, "drawing_dimension", False):
                    self.canvas.drawing_dimension = False
                    self.canvas.dimension_start = None
                    self.canvas.dimension_end = None
                    self.canvas.dimension_offset_preview = None
                    from EstiSketch.Resources.tool_hints import TOOL_HINTS
                    self.canvas.update_hint(TOOL_HINTS["add_dimension"])
                    self.canvas.queue_draw()
                    return True
                elif self.canvas.tool_mode == "add_circle" and getattr(self.canvas, "drawing_circle", False):
                    self.canvas.drawing_circle = False
                    self.canvas.circle_center = None
                    self.canvas.circle_radius_preview = None
                    from EstiSketch.Resources.tool_hints import TOOL_HINTS
                    self.canvas.update_hint(TOOL_HINTS["add_circle"])
                    self.canvas.queue_draw()
                    return True
                elif self.canvas.tool_mode == "add_arc" and getattr(self.canvas, "drawing_arc", False):
                    self.canvas.drawing_arc = False
                    self.canvas.arc_start = None
                    self.canvas.arc_end = None
                    self.canvas.arc_preview_point = None
                    from EstiSketch.Resources.tool_hints import TOOL_HINTS
                    self.canvas.update_hint(TOOL_HINTS["add_arc"])
                    self.canvas.queue_draw()
                    return True
                elif self.canvas.tool_mode == "add_roof_line" and getattr(self.canvas, 'drawing_roof_line', False):
                    self.canvas.drawing_roof_line = False
                    self.canvas.roof_line_start = None
                    self.canvas.roof_line_preview = None
                    from EstiSketch.Resources.tool_hints import TOOL_HINTS
                    self.canvas.update_hint(TOOL_HINTS.get("add_roof_line", "Click to start drawing roof line (ridge/hip/valley/eave)"))
                    self.canvas.queue_draw()
                    return True
                elif self.canvas.tool_mode == "add_dimension_chain" and getattr(self.canvas, 'drawing_dimension_chain', False):
                    self.canvas.drawing_dimension_chain = False
                    self.canvas.dimension_chain_points = []
                    self.canvas.dimension_chain_offset = None
                    from EstiSketch.Resources.tool_hints import TOOL_HINTS
                    self.canvas.update_hint(TOOL_HINTS.get("add_dimension_chain", ""))
                    self.canvas.queue_draw()
                    return True
                elif self.canvas.tool_mode == "add_leader" and getattr(self.canvas, 'drawing_leader', False):
                    self.canvas.drawing_leader = False
                    self.canvas.leader_tip = None
                    self.canvas.leader_elbow = None
                    from EstiSketch.Resources.tool_hints import TOOL_HINTS
                    self.canvas.update_hint(TOOL_HINTS.get("add_leader", ""))
                    self.canvas.queue_draw()
                    return True
            elif keyname == "f1":
                self.on_help_clicked(None)
                return True
            elif keyname in ("delete", "backspace"):
                if self.canvas.selected_items:
                    self.canvas.delete_selected()
                    self.canvas.save_state()
                    self.canvas.queue_draw()
                    return True
            elif keyname == "return":
                if self.canvas.tool_mode == "straighten_blueprint":
                    self.canvas.apply_straighten()
                    return True
                elif self.canvas.tool_mode == "add_dimension_chain" and getattr(self.canvas, 'drawing_dimension_chain', False):
                    self.canvas.finalize_dimension_chain()
                    return True
                elif self.canvas.tool_mode == "add_leader" and getattr(self.canvas, 'drawing_leader', False):
                    self.canvas.finalize_leader()
                    return True
                self.canvas.enter_wall_length()
                return True
            elif keyname == "c":
                self.tool_buttons["add_circle"].set_active(True)
                return True
            elif keyname == "tab":
                if hasattr(self.canvas, 'cycle_selection_at_mouse'):
                    self.canvas.cycle_selection_at_mouse()
                return True

        elif shift_pressed and not ctrl_pressed:
            if keyname == "a":
                 self.tool_buttons["add_arc"].set_active(True)
                 return True
            elif keyname == "r":
                 self.tool_buttons["design_roof"].set_active(True)
                 return True
            elif keyname == "k":
                 self.tool_buttons["draw_cabinet_run"].set_active(True)
                 return True
            elif keyname == "l":
                 self.tool_buttons["add_roof_line"].set_active(True)
                 return True
            elif keyname == "m":
                 self.tool_buttons["add_dimension_chain"].set_active(True)
                 return True
            elif keyname == "t":
                 self.tool_buttons["add_leader"].set_active(True)
                 return True
            elif keyname == "c":
                if self.canvas.tool_mode == "draw_walls" and self.canvas.drawing_wall and self.canvas.walls:
                    self.canvas.toggle_wall_curve_mode()
                    return True


        if ctrl_pressed and not shift_pressed:
            if keyname in ("p", "e"):
                self.on_print()
                return True
            if keyname == "z":
                self.canvas.undo()
                return True
            elif keyname == "y":
                self.canvas.redo()
                return True
            elif keyname == "c":
                self.canvas.copy_selected()
                return True
            elif keyname == "x":
                self.canvas.cut_selected()
                return True
            elif keyname == "v":
                self.canvas.paste()
                return True
            elif keyname == "o":
                self.show_open_dialog()
                return True
            elif keyname == "n":
                self.on_new(None, None)
                return True
            elif keyname == "j":
                self.canvas.join_selected_walls(None)
                return True
            elif keyname == "s":
                 self.show_save_dialog()
                 return True
            elif keyname == "o":
                self.show_open_dialog()
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
            elif keyname == "a":
                self.canvas.select_all()
                return True
            elif keyname == "g":
                if hasattr(self.canvas, "group_selected"):
                    self.canvas.group_selected()
                return True

        if ctrl_pressed and shift_pressed:
            if keyname == "m":
                self.on_estimate_materials_clicked(None)
                return True
            elif keyname == "g":
                if hasattr(self.canvas, "ungroup_selected"):
                    self.canvas.ungroup_selected()
                return True
            elif keyname == "c":
                self.on_estimate_cost_clicked(None)
                return True
            elif keyname == "s":
                self.show_save_as_dialog()
                return True

        return False

    def on_zoom_in_clicked(self, button: Gtk.Button) -> None:
        """
        Zoom the canvas in, centered on the current view.

        Increases the canvas zoom level by a fixed increment, using the center
        of the visible canvas as the zoom focal point.
        """
        center_x = self.canvas.get_width() / 2
        center_y = self.canvas.get_height() / 2
        self.canvas.adjust_zoom(1.1, center_x, center_y)

    def on_zoom_out_clicked(self, button: Gtk.Button) -> None:
        """
        Zoom the canvas out, centered on the current view.

        Decreases the canvas zoom level by a fixed increment, using the center
        of the visible canvas as the zoom focal point.
        """
        center_x = self.canvas.get_width() / 2
        center_y = self.canvas.get_height() / 2
        self.canvas.adjust_zoom(0.9, center_x, center_y)

    def on_zoom_reset_clicked(self, button: Gtk.Button) -> None:
        """
        Reset the canvas zoom to its default level.

        Sets the canvas zoom level to 1.0 (100%), centered on the current view.
        """
        self.canvas.reset_zoom()

    def on_print(self) -> None:
        """Open the print / PDF export dialog with live preview."""
        name = ""
        if self.current_filepath:
            name = os.path.splitext(os.path.basename(self.current_filepath))[0]
        print_dialog.show_print_dialog(
            self.window,
            self.canvas,
            name,
            on_settings_changed=lambda: self.update_dirty_state(True),
        )

    def set_view_mode(self, mode: str) -> None:
        """Switch central workspace between ``'2d'``, ``'split'``, and ``'3d'``."""
        norm = mode.lower()
        if norm not in ("2d", "split", "3d"):
            return
        self.view_mode = norm
        self.workspace_paned.set_start_child(None)
        self.workspace_paned.set_end_child(None)
        if norm == "2d":
            self.canvas.set_visible(True)
            self.viewport_3d.set_visible(False)
            self.workspace_paned.set_start_child(self.canvas)
        elif norm == "3d":
            self.canvas.set_visible(False)
            self.viewport_3d.set_visible(True)
            self.workspace_paned.set_end_child(self.viewport_3d)
            self.viewport_3d.mark_dirty()
        else:
            self.canvas.set_visible(True)
            self.viewport_3d.set_visible(True)
            self.workspace_paned.set_start_child(self.canvas)
            self.workspace_paned.set_end_child(self.viewport_3d)
            alloc_w = self.workspace_paned.get_allocated_width()
            if alloc_w > 100:
                self.workspace_paned.set_position(alloc_w // 2)
            self.viewport_3d.mark_dirty()

    def on_export_glb(self, action: Gio.SimpleAction, parameter: object) -> None:
        """Handle File -> Export 3D Model (.glb) action."""
        self.show_export_glb_dialog()

    def show_export_glb_dialog(self) -> None:
        """Prompt user for a destination path and export the 3D scene as a `.glb` file."""
        dlg = Gtk.FileDialog.new()
        dlg.set_title("Export 3D Model (.glb)")
        dlg.set_modal(True)
        if self.current_filepath:
            stem = os.path.splitext(os.path.basename(self.current_filepath))[0]
            dlg.set_initial_name(f"{stem}.glb")
        else:
            dlg.set_initial_name("house.glb")

        glb_filter = Gtk.FileFilter()
        glb_filter.set_name("glTF 2.0 Binary (*.glb)")
        glb_filter.add_pattern("*.glb")
        filter_store = Gio.ListStore.new(Gtk.FileFilter)
        filter_store.append(glb_filter)
        dlg.set_filters(filter_store)
        dlg.set_default_filter(glb_filter)

        dlg.save(self.window, None, self._on_export_glb_done, None)

    def _on_export_glb_done(
        self, obj: Gtk.FileDialog, result: Gio.AsyncResult, _user_data: object
    ) -> None:
        try:
            file = obj.save_finish(result)
        except Exception:
            return
        if not file:
            return
        path = file.get_path()
        if not path:
            return
        if not path.lower().endswith(".glb"):
            path += ".glb"
        try:
            nbytes = self.viewport_3d.export_glb_to_path(path)
            if hasattr(self.canvas, "update_hint"):
                self.canvas.update_hint(f"Exported 3D model ({nbytes} bytes): {path}")
        except (OSError, RuntimeError, ValueError) as exc:
            err_dlg = Gtk.MessageDialog(
                transient_for=self.window,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Unable to Export .glb",
                secondary_text=str(exc),
            )
            err_dlg.connect("response", lambda d, _r: d.destroy())
            err_dlg.present()

    def on_open_in_blender(self, action: Gio.SimpleAction, parameter) -> None:
        """Export the current project and launch Blender with Home Builder 5."""
        ok, msg = blender_bridge.open_in_blender(
            self.canvas,
            self.window.get_width() if self.window else 1024,
            self.window.get_height() if self.window else 900,
            blender_path=getattr(self.config, "BLENDER_EXECUTABLE", ""),
            project_filepath=self.current_filepath or "",
        )
        if ok:
            if hasattr(self.canvas, "update_hint"):
                self.canvas.update_hint(msg)
            return

        dlg = Gtk.MessageDialog(
            transient_for=self.window,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Unable to Launch Blender",
            secondary_text=msg,
        )
        dlg.connect("response", lambda d, _r: d.destroy())
        dlg.present()

    def on_settings_clicked(self, button: Gtk.Button, *args) -> None:
        """
        Open the application settings dialog.

        Creates and presents the settings dialog, allowing the user to modify
        application and canvas preferences. Changes are applied when the dialog
        is accepted.
        """
        dialog = settings_ui.create_settings_dialog(
            self.window, self.config, self.canvas)
        dialog.connect("response", self.on_settings_response)
        dialog.present()

    def on_settings_response(self, dialog: Gtk.Dialog, response: Gtk.ResponseType) -> None:
        """
        Handle the response from the settings dialog.

        Saves updated configuration values when the dialog is accepted and
        closes the dialog in all cases.
        """
        if response == Gtk.ResponseType.OK:
            config.save_config(self.config.__dict__)
        dialog.destroy()

    def on_manage_materials_clicked(self, button: Gtk.Button, *args) -> None:
        """
        Open the material management dialog.

        Presents a dialog for creating, editing, or removing material definitions
        used by the application.
        """
        dialog = manage_materials.create_manage_materials_dialog(
            self.window, self.config, self.canvas)
        dialog.connect("response", self.on_manage_materials_response)
        dialog.present()

    def on_manage_materials_response(self, dialog: Gtk.Dialog, response: Gtk.ResponseType) -> None:
        """
        Handle the response from the material management dialog.

        Saves updated configuration values when the dialog is accepted and
        closes the dialog in all cases.
        """
        if response == Gtk.ResponseType.OK:
            config.save_config(self.config.__dict__)
        dialog.destroy()

    def on_estimate_materials_clicked(self, button: Gtk.Button, *args) -> None:
        """
        Open the material estimation dialog backed by TakeoffEngine.

        Presents an interactive window displaying computed quantities,
        editable overrides, project assumptions, sanity checks, and exports.
        """
        dialog = takeoff_dialog.create_takeoff_dialog(
            self.window, self.canvas)
        dialog.present()

    def on_estimate_cost_clicked(self, button: Gtk.Button) -> None:
        """
        Open the cost estimation dialog.

        Presents a dialog that calculates and displays estimated costs based
        on the current canvas contents.
        """
        dialog = estimate_cost.create_estimate_cost_dialog(self.window)
        dialog.present()

    def on_help_clicked(self, button: Gtk.Button, *args) -> None:
        """
        Open the help dialog.

        Presents a dialog containing information about the application.
        """
        dialog = help_dialog.create_help_dialog(self.window)
        dialog.present()

    def on_import_sh3d(self, action: Gio.SimpleAction, parameter) -> None:
        """
        Open a dialog to import a Sweet Home 3D (.sh3d) file.

        Presents a file chooser restricted to SH3D files and delegates the
        import handling to the response callback.
        """
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

    def on_import_sh3d_response(self, dialog: Gtk.FileChooserDialog, response: Gtk.ResponseType) -> None:
        """
        Handle the response from the SH3D import dialog.

        When accepted, imports the selected SH3D file, replaces the current
        canvas contents with the imported data, marks the project as dirty,
        and redraws the canvas.
        """
        if response == Gtk.ResponseType.OK:
            file = dialog.get_file()
            sh3d_file = file.get_path()
            try:
                imported = import_sh3d(sh3d_file, self.canvas)
                # Clear the current canvas content.
                self.canvas.wall_sets.clear()
                self.canvas.walls.clear()
                self.canvas.rooms.clear()
                # Populate the canvas with imported data.
                self.canvas.wall_sets.extend(imported["wall_sets"])
                self.canvas.rooms.extend(imported["rooms"])
                self.canvas.doors.extend(imported["doors"])
                self.canvas.windows.extend(imported["windows"])
                self.canvas.existing_ids.extend(imported["identifiers"])
                # Mark the canvas as dirty since it has new content.
                self.update_dirty_state(True)
                self._refresh_sidebar_layers()
                # Request redraw of canvas
                self.canvas.queue_draw()
            except Exception as e:
                print(f"Error importing SH3D file: {e}")
        dialog.destroy()

    def on_import_blueprint(self, action: Gio.SimpleAction, parameter) -> None:
        """Choose an image to use as a blueprint underlay, then calibrate it."""
        dialog = Gtk.FileChooserDialog(
            title="Import Blueprint Image",
            transient_for=self.window,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Open", Gtk.ResponseType.OK)

        image_filter = Gtk.FileFilter()
        image_filter.set_name("Images (PNG, JPG, BMP, GIF, TIFF)")
        for mime in ("image/png", "image/jpeg", "image/bmp", "image/gif", "image/tiff"):
            image_filter.add_mime_type(mime)
        dialog.add_filter(image_filter)

        dialog.connect("response", self.on_import_blueprint_response)
        dialog.show()

    def on_import_blueprint_response(self, dialog: Gtk.FileChooserDialog, response: Gtk.ResponseType) -> None:
        """Import the chosen image and start the two-click calibration."""
        if response == Gtk.ResponseType.OK:
            path = dialog.get_file().get_path()
            try:
                self.canvas.import_blueprint(path)
            except Exception as e:
                print(f"Error importing blueprint: {e}")
                self.canvas.update_hint(f"Could not import blueprint: {e}")
        dialog.destroy()

    def on_new(self, action: Gio.SimpleAction, parameter) -> None:
        """
        Start a new project.

        If there are unsaved changes, prompts the user to save, discard, or cancel.
        Otherwise, immediately clears the canvas and resets project state.
        """
        if self.is_dirty:
            # Prompt user to save changes
            dlg = Gtk.MessageDialog(
                transient_for=self.window,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.NONE,
                text="You have unsaved changes. Do you want to save before starting a new drawing?"
            )
            dlg.add_buttons(
                "Cancel", Gtk.ResponseType.CANCEL,
                "Save & New", Gtk.ResponseType.YES,
                "Discard", Gtk.ResponseType.NO
            )
            dlg.connect("response", self.on_new_response)
            dlg.present()
        else:
            # If not dirty, clear the canvas immediately
            self.clear_canvas_and_reset()

    def on_new_response(self, dialog: Gtk.MessageDialog, response: Gtk.ResponseType) -> None:
        """
        Handle the save/discard/cancel choice for starting a new project.

        - YES: Save the current project, then reset.
        - NO:  Discard changes and reset.
        - CANCEL: Do nothing.
        """
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            # User chose to save before starting anew
            self.show_save_dialog(callback=self.clear_canvas_and_reset)
        elif response == Gtk.ResponseType.NO:
            # User chose to discard changes
            self.clear_canvas_and_reset()

    def clear_canvas_and_reset(self) -> None:
        """
        Clear the canvas and reset the project state.

        Removes all drawing content, resets the current file path, marks the
        project as clean, and redraws the canvas.
        """
        reset_canvas_content(self.canvas)
        # Seed the fresh undo history with the empty state
        self.canvas.save_state()
        # Reset the current file path
        self.current_filepath = None
        # Reset the dirty state
        self.update_dirty_state(False)
        self._refresh_sidebar_layers()
        # Redraw the canvas
        self.canvas.queue_draw()

    def add_to_recent(self, path: str) -> None:
        """
        Add a file path to the recent files list.

        Moves the path to the front of the list if it already exists and
        trims the list to the maximum allowed number of entries.
        """
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        if len(self.recent_files) > 6:
            self.recent_files.pop()

    def show_save_dialog(self, callback: Optional[Callable[[], None]] = None) -> None:
        """
        Save the current project or prompt for a save location.

        If a file path already exists, saves immediately. Otherwise, presents
        a file save dialog restricted to project (.xml) files. An optional
        callback is invoked after a successful save.
        """
        if self.current_filepath:
            # Save directly if a file path is already set
            save_project(
                self.canvas,
                self.window.get_width(),
                self.window.get_height(),
                self.current_filepath
            )
            self.update_dirty_state(False)
            if callback:
                callback()
            return
        # Otherwise, show a file save dialog
        dlg = Gtk.FileDialog.new()
        dlg.set_title("Save Project")
        dlg.set_modal(True)
        xml_filter = Gtk.FileFilter()
        xml_filter.set_name("Project Files (*.xml)")
        xml_filter.add_pattern("*.xml")
        filter_store = Gio.ListStore.new(Gtk.FileFilter)
        filter_store.append(xml_filter)
        dlg.set_filters(filter_store)
        dlg.set_default_filter(xml_filter)
        dlg.save(
            self.window,
            None,
            lambda obj,
            result,
            user_data: self.on_file_dialog_save_done(
                obj,
                result,
                user_data,
                callback),
            None)

    def on_file_dialog_save_done(self, obj: Gtk.FileDialog, result: Gio.AsyncResult, user_data: Optional[Callable[[], None]], callback: Optional[Callable[[], None]] = None) -> None:
        """
        Handle completion of the save file dialog.

        Finalizes the selected file path, ensures a .xml extension, saves the
        project, updates recent files and dirty state, and invokes the optional
        callback on success.
        """
        try:
            file = obj.save_finish(result)
        except Exception:
            return
        if not file:
            return
        path = file.get_path()
        if not path.lower().endswith(".xml"):
            path += ".xml"
        self.current_filepath = path
        save_project(
            self.canvas,
            self.window.get_width(),
            self.window.get_height(),
            path
        )
        self.add_to_recent(path)
        self.update_dirty_state(False)
        if callback:
            callback()

    def show_save_as_dialog(self) -> None:
        """
        Show a save dialog to save the project as a new file.

        Presents a file save dialog restricted to project (.xml) files. The
        dialog is modal and ensures a .xml extension. On successful save,
        updates recent files and marks the project as clean.
        """
        dlg = Gtk.FileDialog.new()
        dlg.set_title("Save Project As")
        dlg.set_modal(True)

        # Set XML filter
        xml_filter = Gtk.FileFilter()
        xml_filter.set_name("Project Files (*.xml)")
        xml_filter.add_pattern("*.xml")
        filter_store = Gio.ListStore.new(Gtk.FileFilter)
        filter_store.append(xml_filter)
        dlg.set_filters(filter_store)
        dlg.set_default_filter(xml_filter)

        dlg.save(self.window, None, self.on_file_dialog_save_as_done, None)

    def on_file_dialog_save_as_done(self, obj: Gtk.FileDialog, result: Gio.AsyncResult, user_data: Optional[Callable[[], None]]) -> None:
        """
        Handle completion of the save file dialog.

        Finalizes the selected file path, ensures a .xml extension, saves the
        project, updates recent files and dirty state, and invokes the optional
        callback on success.
        """
        try:
            file = obj.save_finish(result)
        except Exception:
            return
        if not file:
            return
        path = file.get_path()
        # Ensure .xml extension
        if not path.lower().endswith(".xml"):
            path += ".xml"
        self.current_filepath = path
        save_project(
            self.canvas,
            self.window.get_width(),
            self.window.get_height(),
            path
        )
        self.update_dirty_state(False)
        self.add_to_recent(path)

    def show_open_dialog(self) -> None:
        """
        Prompt the user to open an existing project file.

        Presents a file chooser dialog restricted to project (.xml) files and
        delegates loading to the open dialog completion handler.
        """
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

    def on_file_dialog_open_done(self, obj: Gtk.FileDialog, result: Gio.AsyncResult, user_data: Optional[Callable[[], None]]) -> None:
        """
        Handle completion of the open file dialog.

        Finalizes the selected file path, ensures a .xml extension, loads the
        project, updates recent files and dirty state, and invokes the optional
        callback on success.
        """
        try:
            file = obj.open_finish(result)
        except Exception:
            return
        if not file:
            return
        path = file.get_path()
        self.add_to_recent(path)
        self.current_filepath = path
        open_project(self.canvas, path)
        self._refresh_sidebar_layers()
        self.canvas.queue_draw()
        self.update_dirty_state(False)

    def _refresh_sidebar_layers(self) -> None:
        """Refresh level, ghost, and layer controls in the sidebar after project load/reset."""
        if hasattr(self, "properties_dock") and self.properties_dock:
            lp = getattr(self.properties_dock, "layers_page", None)
            if lp is not None:
                lp.refresh_level_ui()
                lp.refresh_layers()

    def on_open_recent(self, action: Gio.SimpleAction, parameter) -> None:
        """
        Show a popover menu for opening recently used project files.

        Filters out missing paths, displays a list of recent project files anchored
        to the file menu button, and opens the selected project when clicked.
        Includes an option to clear the recent files list.
        """
        self.recent_files = [
            path for path in self.recent_files if os.path.exists(path)]

        popover = Gtk.Popover()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        popover.set_child(box)

        if not self.recent_files:
            lbl = Gtk.Label(label="No recent files")
            box.append(lbl)
        else:
            for path in self.recent_files:
                btn = Gtk.Button(
                    label=Gio.File.new_for_path(path).get_basename())

                def _on_click(button, p=path):
                    self.current_filepath = p
                    open_project(self.canvas, p)
                    self._refresh_sidebar_layers()
                    self.canvas.queue_draw()
                    self.update_dirty_state(False)
                    popover.popdown()
                btn.connect("clicked", _on_click)
                box.append(btn)

            separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            box.append(separator)

            clear_btn = Gtk.Button(label="Clear Recent Files")

            def _on_clear_click(button):
                self.on_clear_recent(None, None)
                popover.popdown()
            clear_btn.connect("clicked", _on_clear_click)
            box.append(clear_btn)

        popover.set_parent(self.file_menu_button)
        popover.set_position(Gtk.PositionType.BOTTOM)

        popover.popup()

    def on_clear_recent(self, action: Gio.SimpleAction, parameter) -> None:
        """
        Clear the recent files list.
        """
        self.recent_files = []
        self.config.RECENT_FILES = self.recent_files
        config.save_config(self.config.__dict__)

    def on_exit(self, action: Gio.SimpleAction, parameter) -> None:
        """Handle exit action."""
        self.window.emit("close-request")

    def on_close_request(self, window: Gtk.Window) -> bool:
        """
        Handle a request to close the main application window.

        If the project has unsaved changes, presents a confirmation dialog
        allowing the user to save, discard, or cancel the close action.
        Returns True to block the default close behavior while awaiting
        user input, or False to allow the window to close immediately.
        """
        try:
            self.on_window_destroy(self)
        except Exception as e:
            print(f"Error saving settings: {e}")

        if not self.is_dirty:
            return False

        # Prompt user to save changes
        dlg = Gtk.MessageDialog(
            transient_for=self.window,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Unsaved Changes",
            secondary_text="You have unsaved changes. Do you want to save before exiting?"
        )
        dlg.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Discard", Gtk.ResponseType.CLOSE,
            "Save", Gtk.ResponseType.ACCEPT
        )

        dlg.connect("response", self.on_close_response)
        dlg.present()

        return True

    def on_sidebar_toggled(self, dock: Gtk.Box, visible: bool) -> None:
        """
        Handle visibility changes for the properties sidebar.

        Restores the sidebar to its previous configured width when shown and
        collapses it to the minimal icon-bar width when hidden by adjusting
        the Gtk.Paned divider position.
        """
        if visible:
            # Restore previous width if known, else default
            width = getattr(self.config, 'SIDEBAR_WIDTH', 300)
            target_pos = self.window.get_allocated_width() - width
            self.main_paned.set_position(target_pos)
        else:
            # When hiding, we want it to be minimum size (icon bar only)
            target_pos = self.window.get_allocated_width() - 40
            self.main_paned.set_position(target_pos)

    def on_window_destroy(self, widget: Gtk.Window) -> bool:
        """
        Handle window destroy event.

        Saves application settings including window size, sidebar width,
        and internal split positions before closing the application.
        Returns True to block the default destroy behavior, or False to allow
        the window to close immediately.
        """
        if hasattr(self, 'config'):
            # Save settings
            # Update width if sidebar is open
            if hasattr(
                    self,
                    'properties_dock') and self.properties_dock.stack.get_visible():
                width = self.window.get_allocated_width() - self.main_paned.get_position()
                if width > 50:  # Sanity check
                    self.config.SIDEBAR_WIDTH = width
            
            # Save the internal Layers/Properties split position
            if hasattr(self, 'properties_dock') and hasattr(self.properties_dock, 'content_paned'):
                split_pos = self.properties_dock.content_paned.get_position()
                if split_pos > 0:
                    paned_h = self.properties_dock.content_paned.get_height()
                    if paned_h > 0:
                        split_pos = max(120, min(split_pos, max(120, paned_h - 220)))
                    else:
                        split_pos = max(120, min(split_pos, 450))
                    self.config.LAYERS_PROPERTIES_SPLIT = split_pos

            # Save window state
            w, h = self.window.get_default_size()
            self.config.WINDOW_WIDTH = w
            self.config.WINDOW_HEIGHT = h
            self.config.WINDOW_MAXIMIZED = self.window.is_maximized()

            self._save_settings()
        return False

    def _save_settings(self) -> None:
        """
        Save application settings to the user's writable configuration file.

        Merges window and sidebar layout state into the loaded user settings
        and persists them via ``config.save_config``.
        """
        # Collect values to save
        layout_data = {
            "WINDOW_WIDTH": self.config.WINDOW_WIDTH,
            "WINDOW_HEIGHT": self.config.WINDOW_HEIGHT,
            "WINDOW_MAXIMIZED": getattr(
                self.config,
                "WINDOW_MAXIMIZED",
                False),
            "SIDEBAR_WIDTH": getattr(
                self.config,
                "SIDEBAR_WIDTH",
                300),
            "LAYERS_PROPERTIES_SPLIT": getattr(
                self.config,
                "LAYERS_PROPERTIES_SPLIT",
                200),
            "SHOW_PROPERTIES_PANEL": getattr(
                self.config,
                "SHOW_PROPERTIES_PANEL",
                True)}

        try:
            data = config.load_config()
            data.update(layout_data)
            config.save_config(data)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def on_window_close_request(self, *args) -> bool:
        """
        Handle window close request.

        Saves application settings and prompts the user to save changes if
        the canvas is dirty. Returns True to block the default close behavior,
        or False to allow the window to close immediately.
        """
        try:
            self.on_window_destroy(self)
        except Exception as e:
            print(f"Error saving settings: {e}")

        if not self.is_dirty:
            self.window.destroy()
            return True
        # Prompt user to save changes
        dlg = Gtk.MessageDialog(
            transient_for=self.window,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="You have unsaved changes. Do you want to save before exiting?")
        dlg.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Save & Close", Gtk.ResponseType.YES,
            "Discard", Gtk.ResponseType.NO
        )
        dlg.connect("response", self.on_quit_response, self)
        dlg.present()
        return True

    def on_close_response(self, dialog: Gtk.MessageDialog, response: Gtk.ResponseType) -> None:
        """
        Handle response from close dialog.

        Closes the application window based on user response: Save & Close
        saves the current project and closes the window, Cancel keeps the
        window open, and Discard closes the window without saving.
        """
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT:  # Save
            if self.current_filepath:
                save_project(
                    self.canvas,
                    self.window.get_width(),
                    self.window.get_height(),
                    self.current_filepath,
                )
                self.window.destroy()
            else:
                def after_save(*args):
                    self.window.destroy()
                self.show_save_dialog(callback=lambda: after_save())
        elif response == Gtk.ResponseType.CLOSE:  # Discard
            self.window.destroy()
        else:
            # Cancel or closed dialog
            pass

    def do_shutdown(self) -> None:
        """
        Perform application shutdown cleanup.

        This method overrides Gtk.Application.do_shutdown() to save recent
        files to the configuration before shutting down the application.
        """
        self.config.RECENT_FILES = self.recent_files
        config.save_config(self.config.__dict__)
        Gtk.Application.do_shutdown(self)


def main(argv: Optional[list[str]] = None) -> None:
    """
    Entry point for the application.

    Handles CLI flags like ``--version`` and otherwise loads configuration,
    creates the application instance, and runs it.
    """
    args = sys.argv[1:] if argv is None else argv
    if "--version" in args or "-V" in args:
        print(f"EstiSketch {__version__}")
        return

    config_dict = config.load_config()
    settings = SimpleNamespace(**config_dict)
    app = EstimatorApp(settings)
    app.run(None)


if __name__ == "__main__":
    main()
