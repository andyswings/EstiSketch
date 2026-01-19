"""
Layers Panel Widget for managing project layers.

Provides UI for:
- Viewing all layers
- Toggling layer visibility (eye icon)
- Toggling layer lock status
- Setting the active layer
- Adding and removing layers
"""

from gi.repository import Gtk, GObject, Pango


class LayersPanel(Gtk.Box):
    """A panel widget for managing layers."""

    __gsignals__ = {
        'layer-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, canvas):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.canvas = canvas
        self.canvas.connect("config-changed", lambda w: self.refresh_layers())
        self.canvas.connect("content-changed", lambda w: self.refresh_layer_contents())
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)

        # Header
        header = Gtk.Label(label="Layers")
        header.add_css_class("heading")
        self.append(header)

        # Level Controls
        self.setup_level_controls()

        # Scrolled container for layer list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(100)

        # Layer list container
        self.layer_list = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scrolled.set_child(self.layer_list)
        self.append(scrolled)

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

        self.append(button_row)
        
        # Store expanders to preserve state
        self.layer_expanders = {} 

        # Initial population
        self.refresh_level_ui()
        self.refresh_layers()

    def setup_level_controls(self):
        """Create the UI for level selection and management."""
        level_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        level_box.set_margin_bottom(8)
        self.append(level_box)  # Insert before list

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

    def on_level_selected(self, btn, level_id):
        self.canvas.set_active_level(level_id)
        self.level_popover.popdown()
        self.refresh_level_ui()
        self.refresh_layers()

    def on_show_all_toggled(self, btn):
        self.canvas.show_all_levels = btn.get_active()
        self.canvas.queue_draw()
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
                    print(f"Updated Level {level.name} elevation to {val}")
                    # If this is active level, maybe queue draw?
                    # Generally drawing doesn't depend on elevation yet unless 3D
                    pass
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
            
        # Clear stored expanders references for removed/recreated rows
        # Actually we might want to preserve expansion state by ID
        old_expanded_states = {lid: exp.get_expanded() for lid, exp in self.layer_expanders.items()}
        self.layer_expanders = {}

        # Build layer rows (in reverse order so top layer is at top of list)
        for layer in reversed(self.canvas.layers):
            # Filtering
            is_global = not layer.level_id
            is_active_level = (layer.level_id == self.canvas.active_level_id)

            if self.canvas.show_all_levels or is_global or is_active_level:
                row_expander = self._create_layer_row(layer)
                
                # Restore expansion state
                if layer.id in old_expanded_states:
                    row_expander.set_expanded(old_expanded_states[layer.id])
                    
                self.layer_list.append(row_expander)
                self.layer_expanders[layer.id] = row_expander
                
    def refresh_layer_contents(self):
        """Refresh only the object lists within existing layer expanders."""
        # This is more efficient than full rebuild.
        # However, if layers changed order or count, we need full rebuild.
        # Assuming content-changed doesn't change layer list itself usually.
        # But for simplicity, let's just trigger update of the listboxes.
        
        for layer in self.canvas.layers:
            if layer.id in self.layer_expanders:
                expander = self.layer_expanders[layer.id]
                # The child of expander is the object list box
                object_list_box = expander.get_child()
                if object_list_box:
                    self._populate_object_list(object_list_box, layer)

    def _create_layer_row(self, layer):
        """Create a row widget for a layer (Expander with header)."""
        
        # Main Container (Expander)
        expander = Gtk.Expander()
        
        # Header Box (Layer Controls)
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header_row.set_margin_top(2)
        header_row.set_margin_bottom(2)
        
        # We need to set the label widget of the expander to be our custom header_row
        expander.set_label_widget(header_row)

        # Visibility toggle (eye icon)
        visibility_btn = Gtk.ToggleButton()
        visibility_btn.set_has_frame(False)
        visibility_btn.set_active(layer.visible)
        visibility_btn.set_label("👁" if layer.visible else "○")
        visibility_btn.set_tooltip_text("Toggle layer visibility")
        visibility_btn.connect("toggled", self.on_visibility_toggled, layer)
        header_row.append(visibility_btn)

        # Lock toggle
        lock_btn = Gtk.ToggleButton()
        lock_btn.set_has_frame(False)
        lock_btn.set_active(layer.locked)
        lock_btn.set_label("🔒" if layer.locked else "🔓")
        lock_btn.set_tooltip_text("Toggle layer lock")
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
            
        # Object List (Expander Child)
        object_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        object_list_box.set_margin_start(20) # Indent
        
        self._populate_object_list(object_list_box, layer)
        
        expander.set_child(object_list_box)

        return expander
    
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

    def _populate_object_list(self, list_box, layer):
        """Populate the list box with objects for the given layer."""
        # Clear existing
        while True:
            child = list_box.get_first_child()
            if not child:
                break
            list_box.remove(child)
            
        objects = self.canvas.get_objects_by_layer_id(layer.id)
        if not objects:
            return

        # Track room count for numbering
        room_counter = 1
        
        for type_name, obj in objects:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
            row.set_margin_top(1)
            row.set_margin_bottom(1)
            
            # Selection Checkbox
            select_check = Gtk.CheckButton()
            select_check.set_active(self._is_object_selected(obj))
            select_check.set_tooltip_text("Toggle selection")
            select_check.connect("toggled", self.on_obj_selection_toggled, obj, type_name)
            row.append(select_check)
            
            # Object Visibility (smaller)
            vis_btn = Gtk.ToggleButton()
            vis_btn.set_has_frame(False)
            is_vis = getattr(obj, 'visible', True)
            vis_btn.set_active(is_vis)
            vis_btn.set_label("👁" if is_vis else "○")
            vis_btn.set_tooltip_text("Toggle object visibility")
            vis_btn.connect("toggled", self.on_obj_visibility_toggled, obj)
            row.append(vis_btn)
            
            # Object Lock (smaller)
            lock_btn = Gtk.ToggleButton()
            lock_btn.set_has_frame(False)
            is_locked = getattr(obj, 'locked', False)
            lock_btn.set_active(is_locked)
            lock_btn.set_label("🔒" if is_locked else "🔓")
            lock_btn.set_tooltip_text("Toggle object lock")
            lock_btn.connect("toggled", self.on_obj_lock_toggled, obj)
            row.append(lock_btn)
            
            # Generate smart display name
            display_name = self._get_object_display_name(type_name, obj, room_counter)
            if type_name == "room":
                room_counter += 1
            
            # Object Label Button (clickable for selection, right-clickable for rename)
            name_btn = Gtk.Button()
            name_lbl = Gtk.Label(label=display_name)
            name_lbl.set_xalign(0)
            name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            # Smaller font using CSS
            name_lbl.add_css_class("caption")
            name_btn.set_child(name_lbl)
            name_btn.set_has_frame(False)
            name_btn.set_hexpand(True)
            name_btn.set_tooltip_text(display_name)
            
            # Left-click to toggle selection
            name_btn.connect("clicked", self.on_obj_name_clicked, obj, type_name, select_check)
            
            # Right-click for rename
            right_click = Gtk.GestureClick()
            right_click.set_button(3)
            right_click.connect("pressed", self.on_object_right_click, obj, type_name, name_btn)
            name_btn.add_controller(right_click)
            
            row.append(name_btn)
            
            list_box.append(row)

    def _get_object_display_name(self, type_name, obj, room_counter=1):
        """Generate a smart display name for an object based on its type and properties."""
        import math
        
        # Check for custom name first
        custom_name = getattr(obj, 'custom_name', None)
        if custom_name:
            return custom_name
            
        if type_name == "wall":
            # Wall - length
            start = getattr(obj, 'start', (0, 0))
            end = getattr(obj, 'end', (0, 0))
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            length_str = self.canvas.converter.format_measurement(length, use_fraction=False)
            return f"Wall - {length_str}"
            
        elif type_name == "room":
            # Room - numbered order
            return f"Room - #{room_counter}"
            
        elif type_name == "door":
            # Door - size (width x height)
            width = getattr(obj, 'width', 36)
            height = getattr(obj, 'height', 80)
            return f"Door - {int(width)}\"×{int(height)}\""
            
        elif type_name == "window":
            # Window - size (width x height)
            width = getattr(obj, 'width', 36)
            height = getattr(obj, 'height', 48)
            return f"Window - {int(width)}\"×{int(height)}\""
            
        elif type_name == "circle":
            # Circle - radius
            radius = getattr(obj, 'radius', 0)
            radius_str = self.canvas.converter.format_measurement(radius, use_fraction=False)
            return f"Circle - R:{radius_str}"
            
        elif type_name == "arc":
            # Arc - radius
            radius = getattr(obj, 'radius', 0)
            radius_str = self.canvas.converter.format_measurement(radius, use_fraction=False)
            return f"Arc - R:{radius_str}"
            
        elif type_name == "polyline":
            # Polyline - length
            start = getattr(obj, 'start', (0, 0))
            end = getattr(obj, 'end', (0, 0))
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            length_str = self.canvas.converter.format_measurement(length, use_fraction=False)
            return f"Line - {length_str}"
            
        elif type_name == "text":
            # Text - first few chars of content
            content = getattr(obj, 'content', 'Text')
            preview = content[:15] + "..." if len(content) > 15 else content
            return f"Text - \"{preview}\""
            
        elif type_name == "dimension":
            # Dimension - measurement value
            start = getattr(obj, 'start', (0, 0))
            end = getattr(obj, 'end', (0, 0))
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            length_str = self.canvas.converter.format_measurement(length, use_fraction=False)
            return f"Dim - {length_str}"
            
        elif type_name == "roof":
            # Roof - identifier or simple name
            ident = getattr(obj, 'identifier', '')
            return f"Roof - {ident}" if ident else "Roof"
            
        else:
            # Fallback
            ident = getattr(obj, 'identifier', '')
            if ident:
                return f"{type_name.capitalize()} - {ident}"
            return type_name.capitalize()

    def on_object_right_click(self, gesture, n_press, x, y, obj, type_name, button):
        """Show context menu for object rename."""
        popover = Gtk.Popover()
        popover.set_parent(button)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_margin_start(8)
        vbox.set_margin_end(8)
        vbox.set_margin_top(8)
        vbox.set_margin_bottom(8)
        popover.set_child(vbox)

        # Rename Section
        lbl = Gtk.Label(label="Rename Object")
        lbl.add_css_class("heading")
        vbox.append(lbl)

        # Get current custom name or generate default
        current_name = getattr(obj, 'custom_name', None)
        if not current_name:
            current_name = self._get_object_display_name(type_name, obj)

        entry = Gtk.Entry()
        entry.set_text(current_name)
        entry.connect(
            "activate",
            lambda e: self._perform_object_rename(obj, entry.get_text(), popover))
        vbox.append(entry)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        
        rename_btn = Gtk.Button(label="Rename")
        rename_btn.connect(
            "clicked",
            lambda b: self._perform_object_rename(obj, entry.get_text(), popover))
        btn_box.append(rename_btn)
        
        reset_btn = Gtk.Button(label="Reset")
        reset_btn.set_tooltip_text("Reset to default name")
        reset_btn.connect(
            "clicked",
            lambda b: self._reset_object_name(obj, popover))
        btn_box.append(reset_btn)
        
        vbox.append(btn_box)

        popover.popup()

    def _perform_object_rename(self, obj, new_name, popover):
        """Rename an object with a custom name."""
        if new_name.strip():
            obj.custom_name = new_name.strip()
            popover.popdown()
            self.refresh_layer_contents()

    def _reset_object_name(self, obj, popover):
        """Reset object to default name by clearing custom_name."""
        if hasattr(obj, 'custom_name'):
            delattr(obj, 'custom_name')
        popover.popdown()
        self.refresh_layer_contents()

    def on_obj_selection_toggled(self, check_button, obj, type_name):
        """Handle selection checkbox toggle."""
        # Set flag to prevent tab switching
        self.canvas._selection_from_layers_panel = True
        
        if check_button.get_active():
            # Add to selection
            self._add_to_selection(type_name, obj)
        else:
            # Remove from selection
            self._remove_from_selection(obj)
        
        self.canvas.emit('selection-changed', self.canvas.selected_items)
        self.canvas.queue_draw()
        # Reset flag AFTER signal is processed
        self.canvas._selection_from_layers_panel = False

    def on_obj_name_clicked(self, button, obj, type_name, check_button):
        """Handle clicking on object name to toggle selection."""
        # Toggle the checkbox state
        check_button.set_active(not check_button.get_active())

    def on_obj_visibility_toggled(self, btn, obj):
        if hasattr(obj, 'visible'):
            obj.visible = btn.get_active()
            btn.set_label("👁" if obj.visible else "○")
            self.canvas.queue_draw()
            # self.emit('content-changed') # This might cause loop if we listen to it?
            # actually we listen to content-changed to refresh list.
            # changing visibility doesn't add/remove objects so maybe we don't need full refresh.
            
    def on_obj_lock_toggled(self, btn, obj):
        if hasattr(obj, 'locked'):
            obj.locked = btn.get_active()
            btn.set_label("🔒" if obj.locked else "🔓")
            # If we lock it, maybe deselect it?
            if obj.locked and hasattr(self.canvas, 'selected_items'):
                # Check if selected
                # simple check
                for item in self.canvas.selected_items:
                     if item.get('object') == obj:
                         self.canvas.deselect_items_on_layer("") # hack or just clear selection
                         self.canvas.selected_items = [i for i in self.canvas.selected_items if i.get('object') != obj]
                         self.canvas.emit('selection-changed', self.canvas.selected_items)
                         self.canvas.queue_draw()
                         break

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
        # if the layer is no longer visible on current level, it will disappear from list
        # ensure active layer isn't this one if it disappears?
        # Actually canvas filters selection visibility, so it's fine.

        self.refresh_layers()
        self.canvas.queue_draw()  # queue draw to update object visibility
        self.emit('layer-changed')
        popover.popdown()
