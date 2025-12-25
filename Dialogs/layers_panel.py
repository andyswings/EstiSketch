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
        self.refresh_layers()
    
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
        """Show rename popover."""
        # Use simple Gtk.Popover for renaming
        popover = Gtk.Popover()
        popover.set_parent(button)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        popover.set_child(vbox)
        
        lbl = Gtk.Label(label="Rename Layer")
        vbox.append(lbl)
        
        entry = Gtk.Entry()
        entry.set_text(layer.name)
        entry.connect("activate", lambda e: self.perform_rename(layer, entry.get_text(), popover))
        vbox.append(entry)
        
        btn = Gtk.Button(label="Rename")
        btn.connect("clicked", lambda b: self.perform_rename(layer, entry.get_text(), popover))
        vbox.append(btn)
        
        popover.popup()
        
    def perform_rename(self, layer, new_name, popover):
        """Execute rename and refresh."""
        if new_name and new_name != layer.name:
            layer.name = new_name
            self.refresh_layers()
            self.emit('layer-changed')
        popover.popdown()

