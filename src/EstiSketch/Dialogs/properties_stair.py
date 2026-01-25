"""
Stair properties widget for EstiSketch.
"""
from gi.repository import Gtk, GObject
import gi
gi.require_version('Gtk', '4.0')


class StairPropertiesWidget(Gtk.Box):
    """Widget for editing properties of selected stairs."""
    
    __gsignals__ = {
        'property-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        
        self.current_stairs = []
        self._block_updates = False
        
        # --- Dimensions Frame ---
        dim_frame = Gtk.Frame(label="Dimensions")
        dim_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        dim_box.set_margin_start(6)
        dim_box.set_margin_end(6)
        dim_box.set_margin_top(6)
        dim_box.set_margin_bottom(6)
        dim_frame.set_child(dim_box)
        self.append(dim_frame)
        
        # Width Row
        row_width = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_width = Gtk.Label(label="Width (in):")
        lbl_width.set_xalign(0)
        self.spin_width = Gtk.SpinButton.new_with_range(24.0, 120.0, 1.0)
        self.spin_width.connect("value-changed", self.on_width_changed)
        row_width.append(lbl_width)
        row_width.append(self.spin_width)
        dim_box.append(row_width)
        
        # Total Rise (Display Only mostly, or trigger recalc)
        row_rise = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_rise = Gtk.Label(label="Total Rise (in):")
        lbl_rise.set_xalign(0)
        self.lbl_rise_val = Gtk.Label(label="106.0")
        row_rise.append(lbl_rise)
        row_rise.append(self.lbl_rise_val)
        dim_box.append(row_rise)
        
        # Number of Steps
        row_steps = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_steps = Gtk.Label(label="Steps:")
        lbl_steps.set_xalign(0)
        self.spin_steps = Gtk.SpinButton.new_with_range(1, 100, 1)
        self.spin_steps.connect("value-changed", self.on_steps_changed)
        row_steps.append(lbl_steps)
        row_steps.append(self.spin_steps)
        dim_box.append(row_steps)
        
        # Tread Depth
        row_tread = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_tread = Gtk.Label(label="Tread Depth (in):")
        lbl_tread.set_xalign(0)
        self.spin_tread = Gtk.SpinButton.new_with_range(8.0, 24.0, 0.25)
        self.spin_tread.connect("value-changed", self.on_tread_changed)
        row_tread.append(lbl_tread)
        row_tread.append(self.spin_tread)
        dim_box.append(row_tread)
        
        # --- Railings Frame ---
        rail_frame = Gtk.Frame(label="Railings")
        rail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        rail_box.set_margin_start(6)
        rail_box.set_margin_end(6)
        rail_box.set_margin_top(6)
        rail_box.set_margin_bottom(6)
        rail_frame.set_child(rail_box)
        self.append(rail_frame)
        
        self.check_left_rail = Gtk.CheckButton(label="Left Rail")
        self.check_left_rail.connect("toggled", self.on_rail_toggled)
        rail_box.append(self.check_left_rail)
        
        self.check_right_rail = Gtk.CheckButton(label="Right Rail")
        self.check_right_rail.connect("toggled", self.on_rail_toggled)
        rail_box.append(self.check_right_rail)
        
        # --- Code Compliance Frame ---
        code_frame = Gtk.Frame(label="Code Compliance")
        code_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        code_box.set_margin_start(6)
        code_box.set_margin_end(6)
        code_box.set_margin_top(6)
        code_box.set_margin_bottom(6)
        code_frame.set_child(code_box)
        self.append(code_frame)
        
        self.lbl_compliance = Gtk.Label(label="✓ Compiant")
        self.lbl_compliance.set_wrap(True)
        self.lbl_compliance.set_xalign(0)
        code_box.append(self.lbl_compliance)
        
    def set_stairs(self, stairs):
        """Set the stair objects to edit."""
        self._block_updates = True
        self.current_stairs = stairs
        
        if not stairs:
            self._block_updates = False
            return
            
        # Use first stair for values (multi-edit could be complex)
        stair = stairs[0]
        
        self.spin_width.set_value(stair.width)
        self.lbl_rise_val.set_label(f"{stair.total_rise:.2f}")
        self.spin_steps.set_value(stair.num_steps)
        self.spin_tread.set_value(stair.tread_depth)
        
        self.check_left_rail.set_active(stair.has_left_rail)
        self.check_right_rail.set_active(stair.has_right_rail)
        
        self._update_compliance_display(stair)
        
        self._block_updates = False
        
    def on_width_changed(self, spin):
        if self._block_updates or not self.current_stairs:
            return
        
        val = spin.get_value()
        for stair in self.current_stairs:
            stair.width = val
            
        self.emit_property_changed()
        
    def on_steps_changed(self, spin):
        if self._block_updates or not self.current_stairs:
            return
            
        val = int(spin.get_value())
        for stair in self.current_stairs:
            stair.num_steps = val
            # Recalculate riser height
            stair.riser_height = stair.total_rise / val
            # Recalculate total run
            stair.total_run = (val - 1) * stair.tread_depth
            
        self._update_compliance_display(self.current_stairs[0])
        self.emit_property_changed()
        
    def on_tread_changed(self, spin):
        if self._block_updates or not self.current_stairs:
            return
            
        val = spin.get_value()
        for stair in self.current_stairs:
            stair.tread_depth = val
            # Recalculate total run
            stair.total_run = (stair.num_steps - 1) * val
            
        self._update_compliance_display(self.current_stairs[0])
        self.emit_property_changed()
        
    def on_rail_toggled(self, button):
        if self._block_updates or not self.current_stairs:
            return
            
        left = self.check_left_rail.get_active()
        right = self.check_right_rail.get_active()
        
        for stair in self.current_stairs:
            stair.has_left_rail = left
            stair.has_right_rail = right
            
        self.emit_property_changed()
        
    def emit_property_changed(self):
        self.emit("property-changed")
        
    def _update_compliance_display(self, stair):
        """Update the compliance label based on current stair values."""
        # Simple check - this logic should ideally match CanvasStairEventsMixin logic
        warnings = []
        if stair.riser_height > 7.75:
            warnings.append(f"• Riser height {stair.riser_height:.2f}\" > 7.75\"")
        if stair.tread_depth < 10.0:
            warnings.append(f"• Tread depth {stair.tread_depth:.2f}\" < 10\"")
        if stair.width < 36.0:
            warnings.append(f"• Width {stair.width:.2f}\" < 36\"")
            
        if not warnings:
            self.lbl_compliance.set_markup("<span foreground=\"green\">✓ Compliant (IRC)</span>")
        else:
            # Use plain text instead of markup for multi-line warnings (bullets + newlines cause parsing issues)
            text = "⚠️ Compliance Warnings:\n" + "\n".join(warnings)
            self.lbl_compliance.set_text(text)

