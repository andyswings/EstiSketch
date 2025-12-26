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
        self.layer_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
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
        
        # Initial population
        self.refresh_level_ui()
        self.refresh_layers()
    
    def setup_level_controls(self):
        """Create the UI for level selection and management."""
        level_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        level_box.set_margin_bottom(8)
        self.append(level_box) # Insert before list
        
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
        self.show_all_btn.set_icon_name("view-reveal-symbolic") # standard icon? or text
        self.show_all_btn.set_label("All")
        self.show_all_btn.set_tooltip_text("Show layers from all levels")
        self.show_all_btn.connect("toggled", self.on_show_all_toggled)
        row1.append(self.show_all_btn)
        
        # Build the popover content dynamically
        self.level_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
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
            if not child: break
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
        self.level_list_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        
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
                if not c: break
                list_box.remove(c)
            for level in self.canvas.levels:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                
                name_entry = Gtk.Entry()
                name_entry.set_text(level.name)
                name_entry.set_hexpand(True)
                name_entry.connect("activate", lambda e, l=level: rename_level(l, e.get_text()))
                name_entry.connect("changed", lambda e, l=level: rename_level(l, e.get_text())) # rename live?
                row.append(name_entry)
                
                # Delete btn (unless only 1 level)
                if len(self.canvas.levels) > 1:
                    del_btn = Gtk.Button(label="X")
                    del_btn.connect("clicked", lambda b, lid=level.id: delete_level(lid))
                    row.append(del_btn)
                    
                list_box.append(row)

        def rename_level(level, new_name):
            if new_name:
                level.name = new_name
                self.refresh_level_ui() # update main panel
                
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
        
        # Build layer rows (in reverse order so top layer is at top of list)
        for layer in reversed(self.canvas.layers):
            # Filtering
            is_global = not layer.level_id
            is_active_level = (layer.level_id == self.canvas.active_level_id)
            
            if self.canvas.show_all_levels or is_global or is_active_level:
                row = self._create_layer_row(layer)
                self.layer_list.append(row)
    
    def _create_layer_row(self, layer):
        """Create a row widget for a layer."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row.set_margin_top(2)
        row.set_margin_bottom(2)
        
        # Visibility toggle (eye icon)
        visibility_btn = Gtk.ToggleButton()
        visibility_btn.set_has_frame(False)  # Make it look like an icon
        visibility_btn.set_active(layer.visible)
        visibility_btn.set_label("👁" if layer.visible else "○")
        visibility_btn.set_tooltip_text("Toggle visibility")
        visibility_btn.connect("toggled", self.on_visibility_toggled, layer)
        row.append(visibility_btn)
        
        # Lock toggle
        lock_btn = Gtk.ToggleButton()
        lock_btn.set_has_frame(False)  # Make it look like an icon
        lock_btn.set_active(layer.locked)
        lock_btn.set_label("🔒" if layer.locked else "🔓")
        lock_btn.set_tooltip_text("Toggle lock")
        lock_btn.connect("toggled", self.on_lock_toggled, layer)
        row.append(lock_btn)
        
        # Layer name (as button to select active layer)
        name_btn = Gtk.Button()
        name_lbl = Gtk.Label(label=layer.name)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        name_lbl.set_xalign(0) # Left align text
        name_btn.set_child(name_lbl)
        
        name_btn.set_hexpand(True)
        # name_btn.set_halign(Gtk.Align.FILL) 
        name_btn.connect("clicked", self.on_layer_selected, layer)
        
        # Add right-click controller for renaming
        right_click = Gtk.GestureClick()
        right_click.set_button(3)
        right_click.connect("pressed", self.on_layer_right_click, layer, name_btn)
        name_btn.add_controller(right_click)
        
        # Highlight active layer
        if layer.id == self.canvas.active_layer_id:
            name_btn.add_css_class("suggested-action")
        
        row.append(name_btn)
        
        # Opacity scale (small)
        opacity_adj = Gtk.Adjustment(value=layer.opacity, lower=0.0, upper=1.0, step_increment=0.1)
        opacity_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=opacity_adj)
        opacity_scale.set_draw_value(False)
        opacity_scale.set_size_request(60, -1)
        opacity_scale.set_tooltip_text(f"Opacity: {int(layer.opacity * 100)}%")
        opacity_scale.connect("value-changed", self.on_opacity_changed, layer)
        row.append(opacity_scale)
        
        return row
    
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
        entry.connect("activate", lambda e: self.perform_rename(layer, entry.get_text(), popover))
        vbox.append(entry)
        
        btn = Gtk.Button(label="Rename")
        btn.connect("clicked", lambda b: self.perform_rename(layer, entry.get_text(), popover))
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
            g_btn.connect("clicked", lambda b: self.move_layer_to_level(layer, "", popover))
            vbox.append(g_btn)
            
        for level in self.canvas.levels:
            if layer.level_id != level.id:
                l_btn = Gtk.Button(label=level.name)
                l_btn.set_has_frame(False)
                l_btn.connect("clicked", lambda b, lid=level.id: self.move_layer_to_level(layer, lid, popover))
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
        self.canvas.queue_draw() # queue draw to update object visibility
        self.emit('layer-changed')
        popover.popdown()

