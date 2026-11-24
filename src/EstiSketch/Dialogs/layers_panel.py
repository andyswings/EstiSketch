"""
Layers Panel Widget for managing project layers.

Provides UI for:
- Viewing all layers
- Toggling layer visibility (eye icon)
- Toggling layer lock status
- Setting the active layer
- Adding and removing layers
"""

from gi.repository import Gtk, GObject, Pango, GLib


class LayersPanel(Gtk.Box):
    """A panel widget for managing layers."""

    __gsignals__ = {
        'layer-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, canvas):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.canvas = canvas
        self._updating_ui = False
        self.canvas.connect("config-changed", lambda w: self.refresh_layers())
        self.canvas.connect("content-changed", lambda w: self.refresh_layer_contents())
        self.canvas.connect("selection-changed", self._on_canvas_selection_changed)
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)

        # View switcher: Layers | Objects
        switcher_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        switcher_row.set_homogeneous(True)
        self.layers_tab_btn = Gtk.ToggleButton(label="Layers")
        self.layers_tab_btn.set_active(True)
        self.objects_tab_btn = Gtk.ToggleButton(label="Objects")
        self.objects_tab_btn.set_group(self.layers_tab_btn)
        switcher_row.append(self.layers_tab_btn)
        switcher_row.append(self.objects_tab_btn)
        self.append(switcher_row)

        self.view_stack = Gtk.Stack()
        self.view_stack.set_vexpand(True)
        self.append(self.view_stack)

        # ── Page 1: Layers view ──
        self.layers_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.view_stack.add_named(self.layers_view, "layers")

        # Level Controls (inside Layers view)
        self.setup_level_controls(parent_box=self.layers_view)

        # Scrolled container for layer list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(100)

        # Layer list container
        self.layer_list = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scrolled.set_child(self.layer_list)
        self.layers_view.append(scrolled)

        # Button row
        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        add_btn = Gtk.Button(label="+")
        add_btn.set_tooltip_text("Add new layer")
        add_btn.connect("clicked", self.on_add_layer)
        button_row.append(add_btn)

        remove_btn = Gtk.Button(label="-")
        remove_btn.set_tooltip_text("Remove selected layer")
        remove_btn.connect("clicked", self.on_remove_layer)
        button_row.append(remove_btn)

        self.layers_view.append(button_row)

        # Blueprint underlays section
        bp_header = Gtk.Label(label="Blueprints", xalign=0)
        bp_header.add_css_class("heading")
        self.layers_view.append(bp_header)
        self.blueprint_list = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.layers_view.append(self.blueprint_list)
        self.canvas.connect(
            "content-changed", lambda w: self.refresh_blueprints())

        # ── Page 2: All Objects & Groups view ──
        self._build_objects_view()

        self.layers_tab_btn.connect(
            "toggled",
            lambda b: self.view_stack.set_visible_child_name("layers") if b.get_active() else None,
        )
        self.objects_tab_btn.connect(
            "toggled",
            lambda b: (
                self.view_stack.set_visible_child_name("objects"),
                self.refresh_objects_list(),
            ) if b.get_active() else None,
        )

        # Store per-layer object count badges
        self.layer_count_buttons = {}

        # Initial population
        self.refresh_level_ui()
        self.refresh_layers()
        self.refresh_objects_list()

    def _on_canvas_selection_changed(self, canvas, selected):
        """Keep checkboxes in Layers & Objects views synced with canvas selection."""
        if self._updating_ui:
            return
        self.refresh_layer_contents()

    def _build_objects_view(self):
        """Build the unified All Objects & Groups explorer page."""
        self.objects_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.view_stack.add_named(self.objects_view, "objects")

        # Search entry
        self.obj_search_entry = Gtk.SearchEntry()
        self.obj_search_entry.set_placeholder_text("Search name, comment, layer...")
        self.obj_search_entry.connect("search-changed", lambda e: self.refresh_objects_list())
        self.objects_view.append(self.obj_search_entry)

        # Filter row: Type dropdown + All Levels toggle
        filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._type_filter_options = [
            ("All Types", "all"),
            ("Walls", "wall"),
            ("Rooms", "room"),
            ("Floor Openings", "floor_opening"),
            ("Fixtures & Cabinets", "fixture"),
            ("Doors", "door"),
            ("Windows", "window"),
            ("Stairs", "stair"),
            ("Roofs", "roof"),
            ("Text", "text"),
            ("Dimensions", "dimension"),
            ("Polylines", "polyline"),
            ("Circles & Arcs", "circle_arc"),
            ("Groups", "group"),
        ]
        self.obj_type_dropdown = Gtk.DropDown.new_from_strings(
            [label for label, _ in self._type_filter_options]
        )
        self.obj_type_dropdown.set_hexpand(True)
        self.obj_type_dropdown.connect(
            "notify::selected", lambda d, p: self.refresh_objects_list()
        )
        filter_row.append(self.obj_type_dropdown)

        self.obj_all_levels_btn = Gtk.ToggleButton(label="All Lvls")
        self.obj_all_levels_btn.set_active(True)
        self.obj_all_levels_btn.set_tooltip_text("Show objects from all levels (uncheck for current level only)")
        self.obj_all_levels_btn.connect("toggled", lambda b: self.refresh_objects_list())
        filter_row.append(self.obj_all_levels_btn)
        self.objects_view.append(filter_row)

        # Layer filter row
        layer_filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        layer_filter_row.append(Gtk.Label(label="Layer:"))
        self._updating_layer_filter = False
        self._layer_filter_options = [("All Layers", "all")]
        self.obj_layer_dropdown = Gtk.DropDown()
        self.obj_layer_dropdown.set_hexpand(True)
        self.obj_layer_dropdown.set_tooltip_text("Filter objects by layer")
        self.obj_layer_dropdown.connect("notify::selected", self._on_obj_layer_filter_changed)
        layer_filter_row.append(self.obj_layer_dropdown)
        self.objects_view.append(layer_filter_row)
        self._refresh_obj_layer_filter()

        # Quick bulk action bar for current selection
        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        action_row.set_homogeneous(True)

        group_btn = Gtk.Button(label="Group")
        group_btn.set_tooltip_text("Group selected objects (Ctrl+G)")
        group_btn.connect("clicked", lambda b: self.canvas.group_selected())
        action_row.append(group_btn)

        ungroup_btn = Gtk.Button(label="Ungroup")
        ungroup_btn.set_tooltip_text("Ungroup selected group (Ctrl+Shift+G)")
        ungroup_btn.connect("clicked", lambda b: self.canvas.ungroup_selected())
        action_row.append(ungroup_btn)

        del_sel_btn = Gtk.Button(label="Delete")
        del_sel_btn.set_tooltip_text("Delete selected objects")
        del_sel_btn.connect("clicked", self._on_delete_selected_clicked)
        action_row.append(del_sel_btn)
        self.objects_view.append(action_row)

        # Scrolled list of groups + all objects
        obj_scroll = Gtk.ScrolledWindow()
        obj_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        obj_scroll.set_vexpand(True)
        obj_scroll.set_min_content_height(120)

        self.all_objects_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        obj_scroll.set_child(self.all_objects_box)
        self.objects_view.append(obj_scroll)

    def _on_delete_selected_clicked(self, button):
        if self.canvas.selected_items:
            self.canvas.delete_selected()
            self.canvas.save_state()

    def setup_level_controls(self, parent_box=None):
        """Create the UI for level selection and management."""
        level_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        level_box.set_margin_bottom(8)
        target = parent_box if parent_box is not None else self
        target.append(level_box)

        # Row 1: Active Level Display + Toggle
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        level_box.append(row1)

        # Level Selector Button (MenuButton)
        self.level_btn = Gtk.MenuButton()
        self.level_btn.set_hexpand(True)
        self.level_btn.set_halign(Gtk.Align.FILL)

        # Label inside button
        self.level_label = Gtk.Label(label="Level 1")
        self.level_btn.set_child(self.level_label)

        # Popover for level list
        self.level_popover = Gtk.Popover()
        self.level_btn.set_popover(self.level_popover)

        row1.append(self.level_btn)

        # Show All Toggle
        self.show_all_btn = Gtk.ToggleButton()
        self.show_all_btn.set_icon_name(
            "view-reveal-symbolic")  # standard icon? or text
        self.show_all_btn.set_label("All")
        self.show_all_btn.set_tooltip_text("Show layers from all levels")
        self.show_all_btn.connect("toggled", self.on_show_all_toggled)
        row1.append(self.show_all_btn)

        # Build the popover content dynamically
        self.level_list_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.level_list_box.set_margin_top(4)
        self.level_list_box.set_margin_bottom(4)
        self.level_list_box.set_margin_start(4)
        self.level_list_box.set_margin_end(4)
        self.level_popover.set_child(self.level_list_box)

        # Row 2: Onion-skinning Ghost Level + Opacity
        ghost_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        ghost_lbl = Gtk.Label(label="Ghost:")
        ghost_lbl.set_xalign(0)
        ghost_row.append(ghost_lbl)

        self._updating_ghost_ui = False
        self._ghost_options = []
        self.ghost_level_dropdown = Gtk.DropDown()
        self.ghost_level_dropdown.set_hexpand(True)
        self.ghost_level_dropdown.set_tooltip_text(
            "Show another level as a muted background trace"
        )
        self.ghost_level_dropdown.connect(
            "notify::selected", self.on_ghost_level_changed
        )
        ghost_row.append(self.ghost_level_dropdown)

        self.ghost_opacity_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.05, 0.80, 0.05
        )
        self.ghost_opacity_scale.set_draw_value(False)
        self.ghost_opacity_scale.set_size_request(65, -1)
        self.ghost_opacity_scale.set_tooltip_text("Ghost trace opacity")
        self.ghost_opacity_scale.connect(
            "value-changed", self.on_ghost_opacity_changed
        )
        ghost_row.append(self.ghost_opacity_scale)
        level_box.append(ghost_row)

    def refresh_level_ui(self):
        """Update level selector UI."""
        # Update current level label
        active_level_id = self.canvas.active_level_id
        active_level_name = "Unknown"
        for level in self.canvas.levels:
            if level.id == active_level_id:
                active_level_name = level.name
                break
        self.level_label.set_label(active_level_name)

        # Rebuild popover list
        while True:
            child = self.level_list_box.get_first_child()
            if not child:
                break
            self.level_list_box.remove(child)

        # Add levels
        for level in self.canvas.levels:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            btn = Gtk.Button(label=level.name)
            btn.set_has_frame(False)
            btn.set_hexpand(True)
            btn.set_halign(Gtk.Align.START)
            if level.id == active_level_id:
                btn.add_css_class("suggested-action")
            btn.connect("clicked", self.on_level_selected, level.id)
            row.append(btn)
            self.level_list_box.append(row)

        # Divider
        self.level_list_box.append(Gtk.Separator(
            orientation=Gtk.Orientation.HORIZONTAL))

        # Manage Levels button
        manage_btn = Gtk.Button(label="Manage Levels...")
        manage_btn.set_has_frame(False)
        manage_btn.connect("clicked", self.on_manage_levels)
        self.level_list_box.append(manage_btn)

        # Refresh Ghost Level dropdown & opacity slider
        self._ghost_options = [
            ("Off", None),
            ("Below (N-1)", "below"),
            ("Above (N+1)", "above"),
        ] + [(lv.name, lv.id) for lv in self.canvas.levels]

        self._updating_ghost_ui = True
        try:
            self.ghost_level_dropdown.set_model(
                Gtk.StringList.new([lbl for lbl, _ in self._ghost_options])
            )
            current_ghost = getattr(self.canvas, "ghost_level_id", None)
            sel_idx = 0
            for idx, (_, val) in enumerate(self._ghost_options):
                if val == current_ghost:
                    sel_idx = idx
                    break
            self.ghost_level_dropdown.set_selected(sel_idx)
            self.ghost_opacity_scale.set_value(
                float(getattr(self.canvas, "ghost_opacity", 0.25))
            )
            ghost_enabled = not getattr(self.canvas, "show_all_levels", False)
            self.ghost_level_dropdown.set_sensitive(ghost_enabled)
            self.ghost_opacity_scale.set_sensitive(
                ghost_enabled and bool(current_ghost)
            )
        finally:
            self._updating_ghost_ui = False

    def on_ghost_level_changed(self, dropdown, pspec):
        if getattr(self, "_updating_ghost_ui", False):
            return
        idx = dropdown.get_selected()
        if 0 <= idx < len(self._ghost_options):
            _, val = self._ghost_options[idx]
        else:
            val = None
        if hasattr(self.canvas, "set_ghost_level"):
            self.canvas.set_ghost_level(val)
        else:
            self.canvas.ghost_level_id = val
            self.canvas.queue_draw()
        ghost_enabled = not getattr(self.canvas, "show_all_levels", False)
        self.ghost_opacity_scale.set_sensitive(ghost_enabled and bool(val))

    def on_ghost_opacity_changed(self, scale):
        if getattr(self, "_updating_ghost_ui", False):
            return
        val = scale.get_value()
        if hasattr(self.canvas, "set_ghost_opacity"):
            self.canvas.set_ghost_opacity(val)
        else:
            self.canvas.ghost_opacity = val
            self.canvas.queue_draw()

    def on_level_selected(self, btn, level_id):
        self.canvas.set_active_level(level_id)
        self.level_popover.popdown()
        self.refresh_level_ui()
        self.refresh_layers()

    def on_show_all_toggled(self, btn):
        self.canvas.show_all_levels = btn.get_active()
        self.canvas._ensure_valid_active_layer()
        self.canvas.deselect_non_visible_items()
        self.canvas.queue_draw()
        self.refresh_level_ui()
        self.refresh_layers()

    def on_manage_levels(self, btn):
        self.level_popover.popdown()
        self.show_level_manager_dialog()

    def show_level_manager_dialog(self):
        """Show simple dialog to add/remove levels."""
        dialog = Gtk.Window(title="Manage Levels")
        # Use get_root() to find the parent window
        root = self.get_root()
        if root:
            dialog.set_transient_for(root)

        dialog.set_modal(True)
        dialog.set_default_size(300, 400)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        dialog.set_child(vbox)

        # Scrolled list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        vbox.append(scrolled)

        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scrolled.set_child(list_box)

        def refresh_manager_list():
            while True:
                c = list_box.get_first_child()
                if not c:
                    break
                list_box.remove(c)
            
            # Header Row
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            h1 = Gtk.Label(label="Name")
            h1.set_hexpand(True)
            h1.set_halign(Gtk.Align.START)
            header.append(h1)
            h2 = Gtk.Label(label="Elevation")
            h2.set_size_request(80, -1)
            header.append(h2)
            h3 = Gtk.Label(label="Del")
            header.append(h3)
            list_box.append(header)

            for level in self.canvas.levels:
                row = Gtk.Box(
                    orientation=Gtk.Orientation.HORIZONTAL,
                    spacing=4)

                name_entry = Gtk.Entry()
                name_entry.set_text(level.name)
                name_entry.set_hexpand(True)
                name_entry.connect(
                    "activate", lambda e, l=level: rename_level(
                        l, e.get_text()))
                name_entry.connect(
                    "changed", lambda e, l=level: rename_level(
                        l, e.get_text()))  # rename live?
                row.append(name_entry)
                
                elev_entry = Gtk.Entry()
                elev_txt = self.canvas.converter.format_measurement(level.elevation)
                elev_entry.set_text(elev_txt)
                elev_entry.set_size_request(80, -1)
                
                # Handle Enter key
                elev_entry.connect(
                    "activate", lambda e, l=level: update_elevation(l, e.get_text()))
                
                # Handle focus lost (GTK4 style)
                focus_controller = Gtk.EventControllerFocus()
                focus_controller.connect(
                    "leave", lambda c, l=level, e=elev_entry: update_elevation(l, e.get_text()))
                elev_entry.add_controller(focus_controller)
                
                row.append(elev_entry)

                # Delete btn (unless only 1 level)
                if len(self.canvas.levels) > 1:
                    del_btn = Gtk.Button(label="X")
                    del_btn.connect(
                        "clicked", lambda b, lid=level.id: delete_level(lid))
                    row.append(del_btn)

                list_box.append(row)

        def rename_level(level, new_name):
            if new_name:
                level.name = new_name
                self.refresh_level_ui()  # update main panel
        
        def update_elevation(level, new_value):
            try:
                val = self.canvas.converter.parse_measurement(new_value)
                if val is not None:
                    level.elevation = val
                    if hasattr(self.canvas, 'update_stairs_for_level_change'):
                        self.canvas.update_stairs_for_level_change(level.id)
            except Exception as e:
                print(f"Error parsing elevation: {e}")

        def delete_level(level_id):
            if self.canvas.remove_level(level_id):
                refresh_manager_list()
                self.refresh_level_ui()
                self.refresh_layers()

        refresh_manager_list()

        # Add Header
        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_entry = Gtk.Entry()
        add_entry.set_placeholder_text("New Level Name")
        add_entry.set_hexpand(True)
        add_btn = Gtk.Button(label="Add")

        def do_add(btn=None):
            name = add_entry.get_text()
            if name:
                self.canvas.add_level(name)
                add_entry.set_text("")
                refresh_manager_list()
                self.refresh_level_ui()

        add_entry.connect("activate", lambda e: do_add())
        add_btn.connect("clicked", do_add)

        add_box.append(add_entry)
        add_box.append(add_btn)
        vbox.append(add_box)

        dialog.present()

    def refresh_layers(self):
        """Rebuild the layer list UI from canvas.layers."""
        # Clear existing
        while True:
            child = self.layer_list.get_first_child()
            if child is None:
                break
            self.layer_list.remove(child)

        self.layer_count_buttons = {}

        # Build layer rows (in reverse order so top layer is at top of list)
        for layer in reversed(self.canvas.layers):
            # Filtering
            is_global = not layer.level_id
            is_active_level = (layer.level_id == self.canvas.active_level_id)

            if self.canvas.show_all_levels or is_global or is_active_level:
                row_box = self._create_layer_row(layer)
                self.layer_list.append(row_box)

        self._refresh_obj_layer_filter()
        self.refresh_blueprints()
        self.refresh_objects_list()

    # ------------------------------------------------------------------
    # Blueprint underlays
    # ------------------------------------------------------------------
    def refresh_blueprints(self):
        """Rebuild the blueprint rows from canvas.blueprints."""
        while True:
            child = self.blueprint_list.get_first_child()
            if child is None:
                break
            self.blueprint_list.remove(child)

        blueprints = getattr(self.canvas, "blueprints", [])
        if not blueprints:
            empty = Gtk.Label(label="None (File > Import Blueprint...)", xalign=0)
            empty.add_css_class("dim-label")
            self.blueprint_list.append(empty)
            return
        for bp in blueprints:
            self.blueprint_list.append(self._create_blueprint_row(bp))

    def _create_blueprint_row(self, bp):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        vis_btn = Gtk.ToggleButton()
        vis_btn.set_has_frame(False)
        vis_btn.set_active(bp.visible)
        vis_btn.set_label("👁" if bp.visible else "○")
        vis_btn.set_tooltip_text("Toggle blueprint visibility")
        vis_btn.add_css_class("layer-control")
        vis_btn.connect("toggled", self.on_blueprint_visibility_toggled, bp)
        top.append(vis_btn)

        lock_btn = Gtk.ToggleButton()
        lock_btn.set_has_frame(False)
        lock_btn.set_active(bp.locked)
        lock_btn.set_label("🔒" if bp.locked else "🔓")
        lock_btn.set_tooltip_text("Lock blueprint (prevents accidental moves)")
        lock_btn.add_css_class("layer-control")
        lock_btn.connect("toggled", self.on_blueprint_lock_toggled, bp)
        top.append(lock_btn)

        name_lbl = Gtk.Label(label=bp.name or "Blueprint", xalign=0)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        name_lbl.set_hexpand(True)
        top.append(name_lbl)

        opacity_adj = Gtk.Adjustment(
            value=bp.opacity, lower=0.05, upper=1.0, step_increment=0.05)
        scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL, adjustment=opacity_adj)
        scale.set_draw_value(False)
        scale.set_size_request(70, -1)
        scale.set_tooltip_text("Blueprint opacity")
        scale.connect("value-changed", self.on_blueprint_opacity_changed, bp)
        top.append(scale)
        box.append(top)

        is_straightening = (
            getattr(self.canvas, "tool_mode", None) == "straighten_blueprint" and
            getattr(self.canvas, "straighten_bp", None) is bp
        )

        if is_straightening:
            str_ctrls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            str_ctrls.set_margin_start(4)
            apply_btn = Gtk.Button(label="✓ Apply")
            apply_btn.add_css_class("suggested-action")
            apply_btn.set_hexpand(True)
            apply_btn.set_tooltip_text("Apply straightening transform")
            apply_btn.connect("clicked", lambda b: self.canvas.apply_straighten())
            str_ctrls.append(apply_btn)

            cancel_btn = Gtk.Button(label="Cancel")
            cancel_btn.set_hexpand(True)
            cancel_btn.set_tooltip_text("Cancel without applying")
            cancel_btn.connect("clicked", lambda b: self.canvas.cancel_blueprint_tool())
            str_ctrls.append(cancel_btn)
            box.append(str_ctrls)
        else:
            row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            row1.set_margin_start(4)
            cal_btn = Gtk.Button(label="Calibrate")
            cal_btn.set_tooltip_text("Click two points and enter their real distance")
            cal_btn.set_hexpand(True)
            cal_btn.connect("clicked", lambda b: self.canvas.start_calibration(bp))
            row1.append(cal_btn)

            str_btn = Gtk.Button(label="Straighten")
            str_btn.set_tooltip_text("Perspective and curved paper correction")
            str_btn.set_hexpand(True)
            str_btn.connect("clicked", lambda b: self.canvas.start_straighten(bp))
            row1.append(str_btn)
            box.append(row1)

            row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            row2.set_margin_start(4)
            move_btn = Gtk.Button(label="Move")
            move_btn.set_tooltip_text("Drag the blueprint (must be unlocked)")
            move_btn.set_hexpand(True)
            move_btn.connect("clicked", lambda b: self.canvas.start_blueprint_move(bp))
            row2.append(move_btn)

            rot_lbl = Gtk.Label(label="Rot°", xalign=0)
            row2.append(rot_lbl)
            rot_adj = Gtk.Adjustment(
                value=bp.rotation, lower=-360.0, upper=360.0, step_increment=0.5)
            rot_spin = Gtk.SpinButton(adjustment=rot_adj, digits=1)
            rot_spin.set_width_chars(5)
            rot_spin.set_tooltip_text("Rotation (degrees)")
            rot_spin.connect("value-changed", self.on_blueprint_rotation_changed, bp)
            row2.append(rot_spin)

            rm_btn = Gtk.Button(label="✕")
            rm_btn.set_tooltip_text("Remove blueprint")
            rm_btn.connect("clicked", lambda b: self.canvas.remove_blueprint(bp))
            row2.append(rm_btn)
            box.append(row2)

        return box


    def on_blueprint_visibility_toggled(self, button, bp):
        button.set_label("👁" if button.get_active() else "○")
        self.canvas.update_blueprint(bp, visible=button.get_active())

    def on_blueprint_lock_toggled(self, button, bp):
        button.set_label("🔒" if button.get_active() else "🔓")
        self.canvas.update_blueprint(bp, locked=button.get_active())
        if button.get_active() and self.canvas.active_blueprint is bp:
            self.canvas.cancel_blueprint_tool()

    def on_blueprint_opacity_changed(self, scale, bp):
        bp.opacity = scale.get_value()
        self.canvas.queue_draw()
        # Record a single undo snapshot once the slider settles.
        pending = getattr(self, "_bp_opacity_timer", None)
        if pending:
            GLib.source_remove(pending)

        def commit():
            self._bp_opacity_timer = None
            self.canvas.save_state()
            return False
        self._bp_opacity_timer = GLib.timeout_add(400, commit)

    def on_blueprint_rotation_changed(self, spin, bp):
        self.canvas.update_blueprint(bp, rotation=spin.get_value())
                
    def refresh_layer_contents(self):
        """Update per-layer object count badges and refresh the Objects view."""
        if self._updating_ui:
            return
        self._updating_ui = True
        try:
            for layer_id, btn in self.layer_count_buttons.items():
                count = len(self.canvas.get_objects_by_layer_id(layer_id))
                btn.set_label(f"({count})")
            if hasattr(self, "all_objects_box"):
                self._populate_all_objects_view()
        finally:
            self._updating_ui = False

    def _refresh_obj_layer_filter(self):
        """Rebuild the Objects tab Layer dropdown while preserving selection if possible."""
        if not hasattr(self, "obj_layer_dropdown"):
            return
        prev_key = "all"
        prev_idx = self.obj_layer_dropdown.get_selected()
        if 0 <= prev_idx < len(getattr(self, "_layer_filter_options", [])):
            prev_key = self._layer_filter_options[prev_idx][1]

        multi_level = len(getattr(self.canvas, "levels", [])) > 1
        level_names = {lv.id: lv.name for lv in getattr(self.canvas, "levels", [])}
        options = [("All Layers", "all")]
        for layer in getattr(self.canvas, "layers", []):
            if multi_level:
                lvl = level_names.get(getattr(layer, "level_id", ""), "Global")
                label = f"{layer.name} ({lvl})"
            else:
                label = layer.name
            options.append((label, layer.id))
        options.append(("Unassigned", "__unassigned__"))
        self._layer_filter_options = options

        self._updating_layer_filter = True
        try:
            self.obj_layer_dropdown.set_model(
                Gtk.StringList.new([lbl for lbl, _ in options])
            )
            sel_idx = 0
            for idx, (_, key) in enumerate(options):
                if key == prev_key:
                    sel_idx = idx
                    break
            self.obj_layer_dropdown.set_selected(sel_idx)
        finally:
            self._updating_layer_filter = False

    def _on_obj_layer_filter_changed(self, dropdown, pspec):
        if getattr(self, "_updating_layer_filter", False):
            return
        self.refresh_objects_list()

    def show_objects_for_layer(self, layer_id: str) -> None:
        """Switch to the Objects tab filtered to ``layer_id``."""
        self._refresh_obj_layer_filter()
        sel_idx = 0
        for idx, (_, key) in enumerate(getattr(self, "_layer_filter_options", [])):
            if key == layer_id:
                sel_idx = idx
                break
        self._updating_layer_filter = True
        try:
            if hasattr(self, "obj_layer_dropdown"):
                self.obj_layer_dropdown.set_selected(sel_idx)
        finally:
            self._updating_layer_filter = False

        self.objects_tab_btn.set_active(True)
        self.view_stack.set_visible_child_name("objects")
        self.refresh_objects_list()

    def refresh_objects_list(self):
        """Refresh the All Objects & Groups explorer view."""
        if self._updating_ui or not hasattr(self, "all_objects_box"):
            return
        self._updating_ui = True
        try:
            self._populate_all_objects_view()
        finally:
            self._updating_ui = False

    def _get_location_label(self, layer_id: str) -> str:
        """Return a short human-readable 'Layer · Level' label for ``layer_id``."""
        layer = self.canvas.get_layer_by_id(layer_id) if layer_id else None
        if not layer:
            return "Unassigned"
        if not getattr(layer, "level_id", ""):
            return f"{layer.name} · Global"
        level_name = ""
        for lvl in getattr(self.canvas, "levels", []):
            if lvl.id == layer.level_id:
                level_name = lvl.name
                break
        return f"{layer.name} · {level_name}" if level_name else layer.name

    def _matches_type_filter(self, type_name: str, filter_key: str) -> bool:
        if filter_key == "all":
            return True
        if filter_key == "dimension":
            return type_name in ("dimension", "dimension_chain")
        if filter_key == "text":
            return type_name in ("text", "leader_callout")
        if filter_key == "circle_arc":
            return type_name in ("circle", "arc")
        return type_name == filter_key

    def _populate_all_objects_view(self):
        """Populate ``self.all_objects_box`` with groups and all matching drawing objects."""
        while True:
            child = self.all_objects_box.get_first_child()
            if not child:
                break
            self.all_objects_box.remove(child)

        query = self.obj_search_entry.get_text().strip().lower() if hasattr(self, "obj_search_entry") else ""
        sel_idx = self.obj_type_dropdown.get_selected() if hasattr(self, "obj_type_dropdown") else 0
        if 0 <= sel_idx < len(getattr(self, "_type_filter_options", [])):
            filter_key = self._type_filter_options[sel_idx][1]
        else:
            filter_key = "all"
        show_all_levels = self.obj_all_levels_btn.get_active() if hasattr(self, "obj_all_levels_btn") else True
        layer_filter_key = "all"
        if hasattr(self, "obj_layer_dropdown"):
            l_idx = self.obj_layer_dropdown.get_selected()
            if 0 <= l_idx < len(getattr(self, "_layer_filter_options", [])):
                layer_filter_key = self._layer_filter_options[l_idx][1]

        # ── Groups Section ──
        groups = getattr(self.canvas, "groups", [])
        matching_groups = []
        if filter_key in ("all", "group"):
            for grp in groups:
                grp_layer_id = getattr(grp, "layer_id", "")
                if layer_filter_key == "__unassigned__":
                    if grp_layer_id:
                        continue
                elif layer_filter_key != "all":
                    if grp_layer_id != layer_filter_key:
                        continue
                elif not show_all_levels:
                    layer = self.canvas.get_layer_by_id(grp_layer_id)
                    if layer and layer.level_id and layer.level_id != self.canvas.active_level_id:
                        continue
                loc = self._get_location_label(grp_layer_id)
                g_name = getattr(grp, "custom_name", "") or getattr(grp, "name", "") or "Group"
                g_comment = getattr(grp, "comment", "") or ""
                if query:
                    haystack = f"{g_name} {g_comment} {loc} group".lower()
                    if query not in haystack:
                        continue
                matching_groups.append(grp)

        if matching_groups:
            grp_hdr = Gtk.Label(label=f"Groups ({len(matching_groups)})", xalign=0)
            grp_hdr.add_css_class("heading")
            self.all_objects_box.append(grp_hdr)
            for grp in matching_groups:
                self.all_objects_box.append(self._create_group_row(grp))
            if filter_key != "group":
                self.all_objects_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        if filter_key == "group":
            if not matching_groups:
                empty = Gtk.Label(label="No groups found", xalign=0)
                empty.add_css_class("dim-label")
                self.all_objects_box.append(empty)
            return

        # ── All Objects Section ──
        all_objs = self.canvas.get_all_objects() if hasattr(self.canvas, "get_all_objects") else []
        matching_objs = []
        room_counter = 1
        for type_name, obj in all_objs:
            current_room_idx = room_counter
            if type_name == "room":
                room_counter += 1

            if not self._matches_type_filter(type_name, filter_key):
                continue

            layer_id = getattr(obj, "layer_id", "")
            if layer_filter_key == "__unassigned__":
                if layer_id:
                    continue
            elif layer_filter_key != "all":
                if layer_id != layer_filter_key:
                    continue
            elif not show_all_levels and layer_id:
                layer = self.canvas.get_layer_by_id(layer_id)
                if layer and layer.level_id and layer.level_id != self.canvas.active_level_id:
                    continue

            display_name = self._get_object_display_name(type_name, obj, current_room_idx)
            comment = getattr(obj, "comment", "") or ""
            loc = self._get_location_label(layer_id)
            if query:
                haystack = f"{display_name} {type_name} {comment} {loc}".lower()
                if query not in haystack:
                    continue
            matching_objs.append((type_name, obj, current_room_idx))

        obj_hdr = Gtk.Label(label=f"Objects ({len(matching_objs)})", xalign=0)
        obj_hdr.add_css_class("heading")
        self.all_objects_box.append(obj_hdr)

        if not matching_objs:
            empty = Gtk.Label(label="No matching objects", xalign=0)
            empty.add_css_class("dim-label")
            self.all_objects_box.append(empty)
            return

        for type_name, obj, r_idx in matching_objs:
            row = self._create_object_row(type_name, obj, r_idx, show_location=True)
            self.all_objects_box.append(row)

    def _create_layer_row(self, layer):
        """Create a compact row widget for a layer with a clickable object count badge."""
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header_row.set_margin_top(2)
        header_row.set_margin_bottom(2)

        # Visibility toggle (eye icon)
        visibility_btn = Gtk.ToggleButton()
        visibility_btn.set_has_frame(False)
        visibility_btn.set_active(layer.visible)
        visibility_btn.set_label("👁" if layer.visible else "○")
        visibility_btn.set_tooltip_text("Toggle layer visibility")
        visibility_btn.add_css_class("layer-control")
        visibility_btn.connect("toggled", self.on_visibility_toggled, layer)
        header_row.append(visibility_btn)

        # Lock toggle
        lock_btn = Gtk.ToggleButton()
        lock_btn.set_has_frame(False)
        lock_btn.set_active(layer.locked)
        lock_btn.set_label("🔒" if layer.locked else "🔓")
        lock_btn.set_tooltip_text("Toggle layer lock")
        lock_btn.add_css_class("layer-control")
        lock_btn.connect("toggled", self.on_lock_toggled, layer)
        header_row.append(lock_btn)

        # Layer name (as button to select active layer)
        name_btn = Gtk.Button()
        name_lbl = Gtk.Label(label=layer.name)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        name_lbl.set_xalign(0)
        name_btn.set_child(name_lbl)
        name_btn.set_hexpand(True)
        name_btn.connect("clicked", self.on_layer_selected, layer)

        # Add right-click controller for renaming
        right_click = Gtk.GestureClick()
        right_click.set_button(3)
        right_click.connect("pressed", self.on_layer_right_click, layer, name_btn)
        name_btn.add_controller(right_click)

        # Highlight active layer
        if layer.id == self.canvas.active_layer_id:
            name_btn.add_css_class("suggested-action")

        header_row.append(name_btn)

        # Opacity scale (small)
        opacity_adj = Gtk.Adjustment(value=layer.opacity, lower=0.0, upper=1.0, step_increment=0.1)
        opacity_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=opacity_adj)
        opacity_scale.set_draw_value(False)
        opacity_scale.set_size_request(60, -1)
        opacity_scale.set_tooltip_text(f"Opacity: {int(layer.opacity * 100)}%")
        opacity_scale.connect("value-changed", self.on_opacity_changed, layer)
        
        if not getattr(self.canvas.config, "LAYER_FOCUS_MODE", False):
            header_row.append(opacity_scale)

        # Clickable object count badge -> jumps to Objects tab filtered to this layer
        count = len(self.canvas.get_objects_by_layer_id(layer.id))
        count_btn = Gtk.Button(label=f"({count})")
        count_btn.set_has_frame(False)
        count_btn.add_css_class("layer-control")
        count_btn.set_tooltip_text("View objects on this layer in the Objects tab")
        count_btn.connect("clicked", lambda b, lid=layer.id: self.show_objects_for_layer(lid))
        header_row.append(count_btn)
        self.layer_count_buttons[layer.id] = count_btn

        # Select All button (small)
        select_all_btn = Gtk.Button()
        select_all_btn.set_label("☑")
        select_all_btn.set_has_frame(False)
        select_all_btn.set_tooltip_text("Select all objects in this layer")
        select_all_btn.connect("clicked", self.on_select_all_layer, layer)
        header_row.append(select_all_btn)
        
        # Deselect All button (small)  
        deselect_all_btn = Gtk.Button()
        deselect_all_btn.set_label("☐")
        deselect_all_btn.set_has_frame(False)
        deselect_all_btn.set_tooltip_text("Deselect all objects in this layer")
        deselect_all_btn.connect("clicked", self.on_deselect_all_layer, layer)
        header_row.append(deselect_all_btn)

        return header_row
    
    def on_select_all_layer(self, button, layer):
        """Select all objects on this layer."""
        objects = self.canvas.get_objects_by_layer_id(layer.id)
        if not objects:
            return
            
        # Use special flag to prevent tab switching
        self.canvas._selection_from_layers_panel = True
        
        for type_name, obj in objects:
            # Skip locked or hidden objects
            if getattr(obj, 'locked', False) or not getattr(obj, 'visible', True):
                continue
            self._add_to_selection(type_name, obj)
        
        self.canvas.emit('selection-changed', self.canvas.selected_items)
        self.canvas.queue_draw()
        self.refresh_layer_contents()
        # Reset flag AFTER signal is processed
        self.canvas._selection_from_layers_panel = False
    
    def on_deselect_all_layer(self, button, layer):
        """Deselect all objects on this layer."""
        objects = self.canvas.get_objects_by_layer_id(layer.id)
        if not objects:
            return
        
        for type_name, obj in objects:
            self._remove_from_selection(obj)
        
        self.canvas.emit('selection-changed', self.canvas.selected_items)
        self.canvas.queue_draw()
        self.refresh_layer_contents()
    
    def _add_to_selection(self, type_name, obj):
        """Add an object to the canvas selection if not already selected."""
        # Check if already selected
        for item in self.canvas.selected_items:
            item_obj = item.get("object")
            # Handle tuples (door/window)
            if isinstance(item_obj, tuple) and len(item_obj) >= 2:
                if item_obj[1] == obj:
                    return  # Already selected
            elif item_obj == obj:
                return  # Already selected
        
        # Create selection item based on type
        if type_name == "door":
            # Find the door tuple
            for wall, door, ratio in self.canvas.doors:
                if door == obj:
                    self.canvas.selected_items.append({
                        "type": "door",
                        "object": (wall, door, ratio)
                    })
                    return
        elif type_name == "window":
            # Find the window tuple
            for wall, window, ratio in self.canvas.windows:
                if window == obj:
                    self.canvas.selected_items.append({
                        "type": "window", 
                        "object": (wall, window, ratio)
                    })
                    return
        else:
            self.canvas.selected_items.append({
                "type": type_name,
                "object": obj
            })
    
    def _remove_from_selection(self, obj):
        """Remove an object from the canvas selection."""
        new_selection = []
        for item in self.canvas.selected_items:
            item_obj = item.get("object")
            # Handle tuples (door/window)
            if isinstance(item_obj, tuple) and len(item_obj) >= 2:
                if item_obj[1] != obj:
                    new_selection.append(item)
            elif item_obj != obj:
                new_selection.append(item)
        self.canvas.selected_items = new_selection
    
    def _is_object_selected(self, obj):
        """Check if an object is currently selected."""
        for item in self.canvas.selected_items:
            item_obj = item.get("object")
            # Handle tuples (door/window)
            if isinstance(item_obj, tuple) and len(item_obj) >= 2:
                if item_obj[1] == obj:
                    return True
            elif item_obj == obj:
                return True
        return False

    def _create_object_row(self, type_name, obj, room_counter=1, show_location=False):
        """Build a compact interactive row for a single drawing object."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
        row.set_margin_top(0)
        row.set_margin_bottom(0)
        row.add_css_class("object-row")

        # Selection Checkbox
        select_check = Gtk.CheckButton()
        select_check.set_active(self._is_object_selected(obj))
        select_check.set_tooltip_text("Toggle selection")
        select_check.add_css_class("object-control")
        select_check.connect("toggled", self.on_obj_selection_toggled, obj, type_name)
        row.append(select_check)

        # Visibility Toggle
        vis_btn = Gtk.ToggleButton()
        vis_btn.set_has_frame(False)
        is_vis = getattr(obj, 'visible', True)
        vis_btn.set_active(is_vis)
        vis_lbl = Gtk.Label(label="👁" if is_vis else "○")
        vis_lbl.add_css_class("object-control")
        vis_btn.set_child(vis_lbl)
        vis_btn.add_css_class("object-control")
        vis_btn.set_tooltip_text("Hide / Show object")
        vis_btn.connect("toggled", self.on_obj_visibility_toggled, obj, vis_lbl)
        row.append(vis_btn)

        # Lock Toggle
        lock_btn = Gtk.ToggleButton()
        lock_btn.set_has_frame(False)
        is_locked = getattr(obj, 'locked', False)
        lock_btn.set_active(is_locked)
        lock_lbl = Gtk.Label(label="🔒" if is_locked else "🔓")
        lock_lbl.add_css_class("object-control")
        lock_btn.set_child(lock_lbl)
        lock_btn.add_css_class("object-control")
        lock_btn.set_tooltip_text("Lock / Unlock object")
        lock_btn.connect("toggled", self.on_obj_lock_toggled, obj, lock_lbl)
        row.append(lock_btn)

        # Display Name + Comment / Group indicators
        display_name = self._get_object_display_name(type_name, obj, room_counter)
        comment = getattr(obj, 'comment', '') or ''
        grp = self.canvas.get_group_for_object(obj) if hasattr(self.canvas, 'get_group_for_object') else None

        label_text = display_name
        if grp is not None:
            label_text = f"🔗 {label_text}"
        if comment:
            label_text = f"{label_text} 💬"

        tooltip_parts = [display_name]
        if show_location:
            tooltip_parts.append(self._get_location_label(getattr(obj, "layer_id", "")))
        if grp is not None:
            grp_name = getattr(grp, "custom_name", "") or getattr(grp, "name", "") or "Group"
            tooltip_parts.append(f"Group: {grp_name}")
        if comment:
            tooltip_parts.append(f"Comment: {comment}")
        tooltip_text = "\n".join(tooltip_parts)

        name_btn = Gtk.Button()
        name_lbl = Gtk.Label(label=label_text)
        name_lbl.set_xalign(0)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        name_lbl.add_css_class("object-label")
        name_btn.set_child(name_lbl)
        name_btn.set_has_frame(False)
        name_btn.set_hexpand(True)
        name_btn.set_tooltip_text(tooltip_text)

        name_btn.connect("clicked", self.on_obj_name_clicked, obj, type_name, select_check)

        right_click = Gtk.GestureClick()
        right_click.set_button(3)
        right_click.connect("pressed", self.on_object_right_click, obj, type_name, name_btn)
        name_btn.add_controller(right_click)
        row.append(name_btn)

        # Details / Actions button (⋯)
        more_btn = Gtk.Button(label="⋯")
        more_btn.set_has_frame(False)
        more_btn.add_css_class("object-control")
        more_btn.set_tooltip_text("Rename, comment, move layer/level, or delete")
        more_btn.connect("clicked", lambda b, o=obj, t=type_name: self.show_object_popover(o, t, b))
        row.append(more_btn)

        # Quick Delete button (✕)
        del_btn = Gtk.Button(label="✕")
        del_btn.set_has_frame(False)
        del_btn.add_css_class("object-control")
        del_btn.set_tooltip_text("Delete object")
        del_btn.connect("clicked", lambda b, o=obj, t=type_name: self._delete_single_object(t, o))
        row.append(del_btn)

        outer.append(row)

        if show_location:
            loc_str = self._get_location_label(getattr(obj, "layer_id", ""))
            sub_lbl = Gtk.Label(label=loc_str, xalign=0)
            sub_lbl.set_margin_start(28)
            sub_lbl.add_css_class("dim-label")
            sub_lbl.add_css_class("object-label")
            sub_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            outer.append(sub_lbl)

        return outer

    def _create_group_row(self, group):
        """Build a compact interactive row for an ObjectGroup."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
        row.add_css_class("object-row")

        members = self.canvas.get_group_members(group) if hasattr(self.canvas, "get_group_members") else []
        is_selected = bool(members) and all(self._is_object_selected(m_obj) for _, m_obj in members)

        select_check = Gtk.CheckButton()
        select_check.set_active(is_selected)
        select_check.set_tooltip_text("Select / deselect entire group")
        select_check.add_css_class("object-control")
        select_check.connect("toggled", self.on_group_selection_toggled, group)
        row.append(select_check)

        vis_btn = Gtk.ToggleButton()
        vis_btn.set_has_frame(False)
        vis_btn.set_active(group.visible)
        vis_lbl = Gtk.Label(label="👁" if group.visible else "○")
        vis_lbl.add_css_class("object-control")
        vis_btn.set_child(vis_lbl)
        vis_btn.add_css_class("object-control")
        vis_btn.set_tooltip_text("Hide / Show group")
        vis_btn.connect("toggled", self.on_group_visibility_toggled, group, vis_lbl)
        row.append(vis_btn)

        lock_btn = Gtk.ToggleButton()
        lock_btn.set_has_frame(False)
        lock_btn.set_active(group.locked)
        lock_lbl = Gtk.Label(label="🔒" if group.locked else "🔓")
        lock_lbl.add_css_class("object-control")
        lock_btn.set_child(lock_lbl)
        lock_btn.add_css_class("object-control")
        lock_btn.set_tooltip_text("Lock / Unlock group")
        lock_btn.connect("toggled", self.on_group_lock_toggled, group, lock_lbl)
        row.append(lock_btn)

        g_name = getattr(group, "custom_name", "") or getattr(group, "name", "") or "Group"
        g_comment = getattr(group, "comment", "") or ""
        label_text = f"🔗 {g_name} ({len(members)})"
        if g_comment:
            label_text = f"{label_text} 💬"

        tooltip = label_text if not g_comment else f"{label_text}\nComment: {g_comment}"
        name_btn = Gtk.Button()
        name_lbl = Gtk.Label(label=label_text)
        name_lbl.set_xalign(0)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        name_lbl.add_css_class("object-label")
        name_btn.set_child(name_lbl)
        name_btn.set_has_frame(False)
        name_btn.set_hexpand(True)
        name_btn.set_tooltip_text(tooltip)
        name_btn.connect("clicked", lambda b, chk=select_check: chk.set_active(not chk.get_active()))

        right_click = Gtk.GestureClick()
        right_click.set_button(3)
        right_click.connect("pressed", lambda g, n, x, y, grp=group, btn=name_btn: self.show_group_popover(grp, btn))
        name_btn.add_controller(right_click)
        row.append(name_btn)

        more_btn = Gtk.Button(label="⋯")
        more_btn.set_has_frame(False)
        more_btn.add_css_class("object-control")
        more_btn.set_tooltip_text("Group options: rename, comment, rotate, move, ungroup, delete")
        more_btn.connect("clicked", lambda b, grp=group: self.show_group_popover(grp, b))
        row.append(more_btn)

        del_btn = Gtk.Button(label="✕")
        del_btn.set_has_frame(False)
        del_btn.add_css_class("object-control")
        del_btn.set_tooltip_text("Delete group and all its objects")
        del_btn.connect("clicked", lambda b, grp=group: self.canvas.delete_group(grp))
        row.append(del_btn)

        return row

    def on_group_selection_toggled(self, check_button, group):
        if self._updating_ui:
            return
        self.canvas._selection_from_layers_panel = True
        try:
            if check_button.get_active():
                self.canvas.select_group(group, extend=True)
            else:
                self.canvas.deselect_group(group)
        finally:
            self.canvas._selection_from_layers_panel = False

    def on_group_visibility_toggled(self, btn, group, lbl):
        if self._updating_ui:
            return
        visible = btn.get_active()
        lbl.set_label("👁" if visible else "○")
        self.canvas.set_group_visible(group, visible)

    def on_group_lock_toggled(self, btn, group, lbl):
        if self._updating_ui:
            return
        locked = btn.get_active()
        lbl.set_label("🔒" if locked else "🔓")
        self.canvas.set_group_locked(group, locked)

    def _delete_single_object(self, type_name, obj):
        if hasattr(self.canvas, "delete_object"):
            self.canvas.delete_object(type_name, obj)

    def _get_object_display_name(self, type_name, obj, room_counter=1):
        """Generate a smart display name for an object based on its type and properties."""
        import math

        custom_name = getattr(obj, 'custom_name', None)
        if custom_name:
            return custom_name

        if type_name == "wall":
            start = getattr(obj, 'start', (0, 0))
            end = getattr(obj, 'end', (0, 0))
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            length_str = self.canvas.converter.format_measurement(length, use_fraction=False)
            return f"Wall - {length_str}"

        elif type_name == "room":
            rname = getattr(obj, 'name', '')
            if rname and rname != "Room":
                return f"Room - {rname}"
            return f"Room - #{room_counter}"

        elif type_name == "floor_opening":
            from ..geometry.room_holes import polygon_area
            lbl = getattr(obj, 'display_label', '') or 'Floor Opening'
            area_sqft = polygon_area(getattr(obj, 'points', []) or []) / 144.0
            return f"Opening - {lbl} ({area_sqft:.1f} sq ft)"

        elif type_name == "fixture":
            from ..fixtures_catalog import get_fixture_spec
            spec = get_fixture_spec(getattr(obj, 'symbol_type', 'base_cabinet'))
            w = int(round(getattr(obj, 'width', 0)))
            d = int(round(getattr(obj, 'depth', 0)))
            return f"{spec['label']} - {w}\"×{d}\""

        elif type_name == "door":
            width = getattr(obj, 'width', 36)
            height = getattr(obj, 'height', 80)
            return f"Door - {int(width)}\"×{int(height)}\""

        elif type_name == "window":
            width = getattr(obj, 'width', 36)
            height = getattr(obj, 'height', 48)
            return f"Window - {int(width)}\"×{int(height)}\""

        elif type_name == "circle":
            radius = getattr(obj, 'radius', 0)
            radius_str = self.canvas.converter.format_measurement(radius, use_fraction=False)
            return f"Circle - R:{radius_str}"

        elif type_name == "arc":
            radius = getattr(obj, 'radius', 0)
            radius_str = self.canvas.converter.format_measurement(radius, use_fraction=False)
            return f"Arc - R:{radius_str}"

        elif type_name == "polyline":
            start = getattr(obj, 'start', (0, 0))
            end = getattr(obj, 'end', (0, 0))
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            length_str = self.canvas.converter.format_measurement(length, use_fraction=False)
            return f"Line - {length_str}"

        elif type_name == "text":
            content = getattr(obj, 'content', 'Text')
            preview = content[:15] + "..." if len(content) > 15 else content
            return f"Text - \"{preview}\""

        elif type_name == "dimension":
            start = getattr(obj, 'start', (0, 0))
            end = getattr(obj, 'end', (0, 0))
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            length_str = self.canvas.converter.format_measurement(length, use_fraction=False)
            return f"Dim - {length_str}"

        elif type_name == "dimension_chain":
            total = obj.get_total_length() if hasattr(obj, "get_total_length") else 0.0
            length_str = self.canvas.converter.format_measurement(total, use_fraction=False)
            return f"Dim Chain - {length_str}"

        elif type_name == "leader_callout":
            txt = getattr(obj, 'text', 'Note')
            preview = txt[:15] + "..." if len(txt) > 15 else txt
            return f"Callout - \"{preview}\""

        elif type_name == "roof":
            rtype = getattr(obj, 'roof_type', 'custom')
            return f"Roof ({rtype})"

        elif type_name == "stair":
            stair_type = getattr(obj, 'stair_type', 'straight')
            rise = getattr(obj, 'total_rise', 0)
            rise_str = self.canvas.converter.format_measurement(rise, use_fraction=False)
            return f"Stair ({stair_type}) - Rise: {rise_str}"

        else:
            ident = getattr(obj, 'identifier', '')
            if ident:
                return f"{type_name.capitalize()} - {ident}"
            return type_name.capitalize()

    def on_object_right_click(self, gesture, n_press, x, y, obj, type_name, button):
        """Show full object details/actions popover on right-click."""
        self.show_object_popover(obj, type_name, button)

    def show_object_popover(self, obj, type_name, anchor_widget):
        """Show popover to rename, edit comments, move layer/level, manage group, or delete."""
        popover = Gtk.Popover()
        popover.set_parent(anchor_widget)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for setter in (vbox.set_margin_start, vbox.set_margin_end, vbox.set_margin_top, vbox.set_margin_bottom):
            setter(8)
        vbox.set_size_request(240, -1)
        popover.set_child(vbox)

        # ── Name Section ──
        name_hdr = Gtk.Label(label="Object Name", xalign=0)
        name_hdr.add_css_class("heading")
        vbox.append(name_hdr)

        current_name = getattr(obj, 'custom_name', '') or ''
        entry = Gtk.Entry()
        entry.set_placeholder_text(self._get_object_display_name(type_name, obj))
        entry.set_text(current_name)
        vbox.append(entry)

        # ── Comment Section ──
        cmt_hdr = Gtk.Label(label="Comment / Notes", xalign=0)
        cmt_hdr.add_css_class("heading")
        vbox.append(cmt_hdr)

        cmt_frame = Gtk.Frame()
        cmt_scroll = Gtk.ScrolledWindow()
        cmt_scroll.set_min_content_height(56)
        cmt_scroll.set_max_content_height(100)
        cmt_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        cmt_view = Gtk.TextView()
        cmt_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        cmt_buf = cmt_view.get_buffer()
        cmt_buf.set_text(getattr(obj, 'comment', '') or '')
        cmt_scroll.set_child(cmt_view)
        cmt_frame.set_child(cmt_scroll)
        vbox.append(cmt_frame)

        def save_meta(*_args):
            obj.custom_name = entry.get_text().strip()
            start_it, end_it = cmt_buf.get_bounds()
            obj.comment = cmt_buf.get_text(start_it, end_it, True).strip()
            if hasattr(self.canvas, "save_state"):
                self.canvas.save_state()
            popover.popdown()
            self.refresh_layer_contents()
            self.canvas.emit("content-changed")

        entry.connect("activate", save_meta)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.set_hexpand(True)
        save_btn.connect("clicked", save_meta)
        btn_box.append(save_btn)

        reset_btn = Gtk.Button(label="Reset Name")
        reset_btn.set_tooltip_text("Clear custom name")
        reset_btn.connect("clicked", lambda b: self._reset_object_name(obj, popover))
        btn_box.append(reset_btn)
        vbox.append(btn_box)

        vbox.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # ── Move to Layer Section ──
        layer_hdr = Gtk.Label(label="Move to Layer", xalign=0)
        layer_hdr.add_css_class("heading")
        vbox.append(layer_hdr)

        current_layer_id = getattr(obj, "layer_id", "")
        layer_options = []
        active_layer_idx = 0
        for idx, lyr in enumerate(self.canvas.layers):
            loc = self._get_location_label(lyr.id)
            layer_options.append((lyr.id, loc))
            if lyr.id == current_layer_id:
                active_layer_idx = idx

        if layer_options:
            layer_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            layer_dd = Gtk.DropDown.new_from_strings([lbl for _, lbl in layer_options])
            layer_dd.set_selected(active_layer_idx)
            layer_dd.set_hexpand(True)
            layer_row.append(layer_dd)

            move_lyr_btn = Gtk.Button(label="Move")
            move_lyr_btn.connect(
                "clicked",
                lambda b: (
                    self.canvas.move_object_to_layer(
                        obj, layer_options[layer_dd.get_selected()][0]
                    ),
                    popover.popdown(),
                ),
            )
            layer_row.append(move_lyr_btn)
            vbox.append(layer_row)

        # ── Move to Level Section ──
        level_hdr = Gtk.Label(label="Move to Level", xalign=0)
        level_hdr.add_css_class("heading")
        vbox.append(level_hdr)

        lvl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        g_btn = Gtk.Button(label="Global")
        g_btn.set_has_frame(False)
        g_btn.connect(
            "clicked",
            lambda b: (self.canvas.move_object_to_level(obj, ""), popover.popdown()),
        )
        lvl_box.append(g_btn)
        for lvl in getattr(self.canvas, "levels", []):
            l_btn = Gtk.Button(label=lvl.name)
            l_btn.set_has_frame(False)
            l_btn.connect(
                "clicked",
                lambda b, lid=lvl.id: (self.canvas.move_object_to_level(obj, lid), popover.popdown()),
            )
            lvl_box.append(l_btn)
        vbox.append(lvl_box)

        # ── Group Section (if member of a group) ──
        grp = self.canvas.get_group_for_object(obj) if hasattr(self.canvas, "get_group_for_object") else None
        if grp is not None:
            vbox.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
            g_name = getattr(grp, "custom_name", "") or getattr(grp, "name", "") or "Group"
            grp_lbl = Gtk.Label(label=f"Group: {g_name}", xalign=0)
            grp_lbl.add_css_class("heading")
            vbox.append(grp_lbl)
            grp_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            sel_grp_btn = Gtk.Button(label="Select Group")
            sel_grp_btn.set_hexpand(True)
            sel_grp_btn.connect("clicked", lambda b: (self.canvas.select_group(grp), popover.popdown()))
            grp_row.append(sel_grp_btn)
            ungrp_btn = Gtk.Button(label="Ungroup")
            ungrp_btn.set_hexpand(True)
            ungrp_btn.connect("clicked", lambda b: (self.canvas.ungroup(grp), popover.popdown()))
            grp_row.append(ungrp_btn)
            vbox.append(grp_row)

        vbox.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # ── Delete Button ──
        del_btn = Gtk.Button(label="Delete Object")
        del_btn.add_css_class("destructive-action")
        del_btn.connect(
            "clicked",
            lambda b: (popover.popdown(), self._delete_single_object(type_name, obj)),
        )
        vbox.append(del_btn)

        popover.popup()

    def show_group_popover(self, group, anchor_widget):
        """Show popover for ObjectGroup rename, comment, rotate, move, ungroup, and delete."""
        popover = Gtk.Popover()
        popover.set_parent(anchor_widget)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for setter in (vbox.set_margin_start, vbox.set_margin_end, vbox.set_margin_top, vbox.set_margin_bottom):
            setter(8)
        vbox.set_size_request(240, -1)
        popover.set_child(vbox)

        hdr = Gtk.Label(label="Group Name", xalign=0)
        hdr.add_css_class("heading")
        vbox.append(hdr)

        entry = Gtk.Entry()
        entry.set_text(getattr(group, "custom_name", "") or getattr(group, "name", "") or "")
        vbox.append(entry)

        cmt_hdr = Gtk.Label(label="Comment / Notes", xalign=0)
        cmt_hdr.add_css_class("heading")
        vbox.append(cmt_hdr)

        cmt_frame = Gtk.Frame()
        cmt_scroll = Gtk.ScrolledWindow()
        cmt_scroll.set_min_content_height(50)
        cmt_scroll.set_max_content_height(90)
        cmt_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        cmt_view = Gtk.TextView()
        cmt_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        cmt_buf = cmt_view.get_buffer()
        cmt_buf.set_text(getattr(group, "comment", "") or "")
        cmt_scroll.set_child(cmt_view)
        cmt_frame.set_child(cmt_scroll)
        vbox.append(cmt_frame)

        def save_grp_meta(*_args):
            new_n = entry.get_text().strip()
            if new_n:
                group.custom_name = new_n
                group.name = new_n
            start_it, end_it = cmt_buf.get_bounds()
            group.comment = cmt_buf.get_text(start_it, end_it, True).strip()
            if hasattr(self.canvas, "save_state"):
                self.canvas.save_state()
            popover.popdown()
            self.refresh_layer_contents()
            self.canvas.emit("content-changed")

        entry.connect("activate", save_grp_meta)
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", save_grp_meta)
        vbox.append(save_btn)

        vbox.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Rotate Group
        rot_hdr = Gtk.Label(label="Rotate Group", xalign=0)
        rot_hdr.add_css_class("heading")
        vbox.append(rot_hdr)

        rot_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for lbl, deg in [("↺ 90°", -90.0), ("↻ 90°", 90.0), ("180°", 180.0)]:
            rb = Gtk.Button(label=lbl)
            rb.set_hexpand(True)
            rb.connect("clicked", lambda b, d=deg: (self.canvas.rotate_group(group, d), popover.popdown()))
            rot_row.append(rb)
        custom_rb = Gtk.Button(label="Angle...")
        custom_rb.connect(
            "clicked",
            lambda b: (popover.popdown(), self.canvas.show_rotate_group_dialog(group)),
        )
        rot_row.append(custom_rb)
        vbox.append(rot_row)

        vbox.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Move Group to Layer
        layer_hdr = Gtk.Label(label="Move Group to Layer", xalign=0)
        layer_hdr.add_css_class("heading")
        vbox.append(layer_hdr)

        layer_options = [(lyr.id, self._get_location_label(lyr.id)) for lyr in self.canvas.layers]
        active_idx = next(
            (i for i, (lid, _) in enumerate(layer_options) if lid == getattr(group, "layer_id", "")),
            0,
        )
        if layer_options:
            lrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            ldd = Gtk.DropDown.new_from_strings([lbl for _, lbl in layer_options])
            ldd.set_selected(active_idx)
            ldd.set_hexpand(True)
            lrow.append(ldd)
            mbtn = Gtk.Button(label="Move")
            mbtn.connect(
                "clicked",
                lambda b: (
                    self.canvas.move_group_to_layer(group, layer_options[ldd.get_selected()][0]),
                    popover.popdown(),
                ),
            )
            lrow.append(mbtn)
            vbox.append(lrow)

        # Move Group to Level
        level_hdr = Gtk.Label(label="Move Group to Level", xalign=0)
        level_hdr.add_css_class("heading")
        vbox.append(level_hdr)

        lvl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        g_btn = Gtk.Button(label="Global")
        g_btn.set_has_frame(False)
        g_btn.connect("clicked", lambda b: (self.canvas.move_group_to_level(group, ""), popover.popdown()))
        lvl_box.append(g_btn)
        for lvl in getattr(self.canvas, "levels", []):
            l_btn = Gtk.Button(label=lvl.name)
            l_btn.set_has_frame(False)
            l_btn.connect(
                "clicked",
                lambda b, lid=lvl.id: (self.canvas.move_group_to_level(group, lid), popover.popdown()),
            )
            lvl_box.append(l_btn)
        vbox.append(lvl_box)

        vbox.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        ungrp_btn = Gtk.Button(label="Ungroup")
        ungrp_btn.set_hexpand(True)
        ungrp_btn.connect("clicked", lambda b: (self.canvas.ungroup(group), popover.popdown()))
        action_row.append(ungrp_btn)

        del_btn = Gtk.Button(label="Delete Group")
        del_btn.add_css_class("destructive-action")
        del_btn.set_hexpand(True)
        del_btn.connect("clicked", lambda b: (popover.popdown(), self.canvas.delete_group(group)))
        action_row.append(del_btn)
        vbox.append(action_row)

        popover.popup()

    def _perform_object_rename(self, obj, new_name, popover):
        """Rename an object with a custom name."""
        if new_name.strip():
            obj.custom_name = new_name.strip()
            if hasattr(self.canvas, "save_state"):
                self.canvas.save_state()
            popover.popdown()
            self.refresh_layer_contents()

    def _reset_object_name(self, obj, popover):
        """Reset object to default name by clearing custom_name."""
        if hasattr(obj, 'custom_name'):
            obj.custom_name = ""
        if hasattr(self.canvas, "save_state"):
            self.canvas.save_state()
        popover.popdown()
        self.refresh_layer_contents()

    def on_obj_selection_toggled(self, check_button, obj, type_name):
        """Handle selection checkbox toggle."""
        if self._updating_ui:
            return
        self.canvas._selection_from_layers_panel = True
        try:
            if check_button.get_active():
                self._add_to_selection(type_name, obj)
            else:
                self._remove_from_selection(obj)
            self.canvas.emit('selection-changed', self.canvas.selected_items)
            self.canvas.queue_draw()
        finally:
            self.canvas._selection_from_layers_panel = False

    def on_obj_name_clicked(self, button, obj, type_name, check_button):
        """Handle clicking on object name to toggle selection."""
        check_button.set_active(not check_button.get_active())

    def on_obj_visibility_toggled(self, btn, obj, lbl):
        if self._updating_ui:
            return
        if hasattr(obj, 'visible'):
            obj.visible = btn.get_active()
            lbl.set_label("👁" if obj.visible else "○")
            if not obj.visible:
                self._remove_from_selection(obj)
                self.canvas.emit('selection-changed', self.canvas.selected_items)
            if hasattr(self.canvas, "save_state"):
                self.canvas.save_state()
            self.canvas.queue_draw()

    def on_obj_lock_toggled(self, btn, obj, lbl):
        if self._updating_ui:
            return
        if hasattr(obj, 'locked'):
            obj.locked = btn.get_active()
            lbl.set_label("🔒" if obj.locked else "🔓")
            if obj.locked:
                self._remove_from_selection(obj)
                self.canvas.emit('selection-changed', self.canvas.selected_items)
            if hasattr(self.canvas, "save_state"):
                self.canvas.save_state()
            self.canvas.queue_draw()

    def on_visibility_toggled(self, button, layer):
        """Handle visibility toggle."""
        layer.visible = button.get_active()
        button.set_label("👁" if layer.visible else "○")
        if not layer.visible:
            self.canvas.deselect_items_on_layer(layer.id)
        self.canvas.queue_draw()
        self.emit('layer-changed')

    def on_lock_toggled(self, button, layer):
        """Handle lock toggle."""
        layer.locked = button.get_active()
        button.set_label("🔒" if layer.locked else "🔓")
        if layer.locked:
            self.canvas.deselect_items_on_layer(layer.id)
        self.emit('layer-changed')

    def on_layer_selected(self, button, layer):
        """Set the clicked layer as active."""
        self.canvas.set_active_layer(layer.id)
        self.refresh_layers()
        self.emit('layer-changed')

    def on_opacity_changed(self, scale, layer):
        """Handle opacity change."""
        layer.opacity = scale.get_value()
        scale.set_tooltip_text(f"Opacity: {int(layer.opacity * 100)}%")
        self.canvas.queue_draw()

    def on_add_layer(self, button):
        """Add a new layer."""
        new_id = self.canvas.add_layer()
        if new_id:
            self.canvas.set_active_layer(new_id)
            self.refresh_layers()
            self.emit('layer-changed')

    def on_remove_layer(self, button):
        """Remove the active layer."""
        if self.canvas.remove_layer(self.canvas.active_layer_id):
            self.refresh_layers()
            self.canvas.queue_draw()
            self.emit('layer-changed')

    def on_layer_right_click(self, gesture, n_press, x, y, layer, button):
        """Show context menu for layer operations."""
        # Use simple Gtk.Popover
        popover = Gtk.Popover()
        popover.set_parent(button)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        popover.set_child(vbox)

        # Rename Section
        lbl = Gtk.Label(label="Rename Layer")
        vbox.append(lbl)

        entry = Gtk.Entry()
        entry.set_text(layer.name)
        entry.connect(
            "activate",
            lambda e: self.perform_rename(
                layer,
                entry.get_text(),
                popover))
        vbox.append(entry)

        btn = Gtk.Button(label="Rename")
        btn.connect(
            "clicked",
            lambda b: self.perform_rename(
                layer,
                entry.get_text(),
                popover))
        vbox.append(btn)

        vbox.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Move to Level Section
        # Since Popovers don't easily do submenus in this ad-hoc way, let's just list a few buttons
        # or use a dropdown if many levels. For now, simple buttons.

        move_lbl = Gtk.Label(label="Move to Level:")
        vbox.append(move_lbl)

        # Global option
        if layer.level_id:
            g_btn = Gtk.Button(label="Global (All Levels)")
            g_btn.set_has_frame(False)
            g_btn.connect(
                "clicked", lambda b: self.move_layer_to_level(
                    layer, "", popover))
            vbox.append(g_btn)

        for level in self.canvas.levels:
            if layer.level_id != level.id:
                l_btn = Gtk.Button(label=level.name)
                l_btn.set_has_frame(False)
                l_btn.connect(
                    "clicked",
                    lambda b,
                    lid=level.id: self.move_layer_to_level(
                        layer,
                        lid,
                        popover))
                vbox.append(l_btn)

        popover.popup()

    def perform_rename(self, layer, new_name, popover):
        """Execute rename and refresh."""
        if new_name and new_name != layer.name:
            layer.name = new_name
            self.refresh_layers()
            self.emit('layer-changed')
        popover.popdown()

    def move_layer_to_level(self, layer, level_id, popover):
        """Move layer to a different level."""
        layer.level_id = level_id
        self.canvas._ensure_valid_active_layer()
        self.canvas.deselect_non_visible_items()

        self.refresh_layers()
        self.canvas.queue_draw()  # queue draw to update object visibility
        self.emit('layer-changed')
        popover.popdown()
