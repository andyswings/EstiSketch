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
        
        # --- Stair Type Frame ---
        type_frame = Gtk.Frame(label="Stair Type")
        type_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        type_box.set_margin_start(6)
        type_box.set_margin_end(6)
        type_box.set_margin_top(6)
        type_box.set_margin_bottom(6)
        type_frame.set_child(type_box)
        self.append(type_frame)
        
        # Stair Type Dropdown
        row_type = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_type = Gtk.Label(label="Type:")
        lbl_type.set_xalign(0)
        self.dropdown_type = Gtk.DropDown.new_from_strings(["Straight", "L-shaped", "U-shaped", "Spiral"])
        self.dropdown_type.connect("notify::selected", self.on_type_changed)
        row_type.append(lbl_type)
        row_type.append(self.dropdown_type)
        type_box.append(row_type)
        
        # Turn Direction (for L-shaped only)
        row_turn = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_turn = Gtk.Label(label="Turn Direction:")
        lbl_turn.set_xalign(0)
        self.dropdown_turn = Gtk.DropDown.new_from_strings(["Left", "Right"])
        self.dropdown_turn.connect("notify::selected", self.on_turn_changed)
        row_turn.append(lbl_turn)
        row_turn.append(self.dropdown_turn)
        type_box.append(row_turn)
        self.row_turn = row_turn  # Save reference for show/hide
        
        # Landing Depth (for L-shaped only)
        row_landing = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_landing = Gtk.Label(label="Landing Depth (in):")
        lbl_landing.set_xalign(0)
        self.spin_landing = Gtk.SpinButton.new_with_range(30.0, 72.0, 6.0)
        self.spin_landing.connect("value-changed", self.on_landing_changed)
        row_landing.append(lbl_landing)
        row_landing.append(self.spin_landing)
        type_box.append(row_landing)
        self.row_landing = row_landing  # Save reference for show/hide
        
        # Steps Before Landing (for L-shaped only)
        row_steps_before = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_steps_before = Gtk.Label(label="Steps (1st flight):")
        lbl_steps_before.set_xalign(0)
        self.spin_steps_before = Gtk.SpinButton.new_with_range(1, 50, 1)
        self.spin_steps_before.connect("value-changed", self.on_steps_before_changed)
        row_steps_before.append(lbl_steps_before)
        row_steps_before.append(self.spin_steps_before)
        type_box.append(row_steps_before)
        self.row_steps_before = row_steps_before  # Save reference
        
        # Well Width / Gap (for U-shaped only)
        row_well = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_well = Gtk.Label(label="Well Width (in):")
        lbl_well.set_xalign(0)
        self.spin_well = Gtk.SpinButton.new_with_range(0.0, 48.0, 1.0)
        self.spin_well.connect("value-changed", self.on_well_changed)
        row_well.append(lbl_well)
        row_well.append(self.spin_well)
        type_box.append(row_well)
        self.row_well = row_well
        self.lbl_well = lbl_well # Save ref to change label
        
        # Rotation (Spiral only)
        row_rotation = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_rotation = Gtk.Label(label="Rotation (deg):")
        lbl_rotation.set_xalign(0)
        self.spin_rotation = Gtk.SpinButton.new_with_range(90.0, 720.0, 15.0)
        self.spin_rotation.connect("value-changed", self.on_rotation_changed)
        row_rotation.append(lbl_rotation)
        row_rotation.append(self.spin_rotation)
        type_box.append(row_rotation)
        self.row_rotation = row_rotation
        
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
        
        # Set stair type
        stair_type = getattr(stair, 'stair_type', 'straight')
        if stair_type == 'straight':
            type_idx = 0
        elif stair_type == 'L-shaped':
            type_idx = 1
        elif stair_type == 'U-shaped':
            type_idx = 2
        else: # Spiral
            type_idx = 3
        self.dropdown_type.set_selected(type_idx)
        
        # Set L/U/Spiral specific controls
        is_multi_segment = (stair_type in ['L-shaped', 'U-shaped'])
        is_u_shaped = (stair_type == 'U-shaped')
        is_spiral = (stair_type == 'spiral')
        
        self.row_turn.set_visible(is_multi_segment or is_spiral)
        self.row_landing.set_visible(is_multi_segment)
        self.row_steps_before.set_visible(is_multi_segment)
        
        self.row_well.set_visible(is_u_shaped or is_spiral)
        if is_spiral:
            self.lbl_well.set_label("Inner Radius (in):")
        else:
            self.lbl_well.set_label("Well Width (in):")
            
        self.row_rotation.set_visible(is_spiral)
        
        if is_multi_segment or is_spiral:
            turn_dir = getattr(stair, 'turn_direction', 'left')
            self.dropdown_turn.set_selected(0 if turn_dir == 'left' else 1)
            
        if is_multi_segment:
            landing_depth = getattr(stair, 'landing_depth', 36.0)
            self.spin_landing.set_value(landing_depth)
            
            # Steps before landing
            stored_steps = getattr(stair, 'steps_before_landing', 0)
            if stored_steps > 0:
                steps_before = stored_steps
            else:
                steps_before = stair.num_steps // 2
            self.spin_steps_before.set_value(steps_before)
            
        if is_u_shaped or is_spiral:
            # We reuse inner_radius for U-shape gap and Spiral inner radius
            val = getattr(stair, 'inner_radius', 0.0)
            self.spin_well.set_value(val)
            
        if is_spiral:
            rot = getattr(stair, 'rotation_degrees', 270.0)
            self.spin_rotation.set_value(rot)
        
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
        if hasattr(self, 'canvas'):
            self.canvas.queue_draw()
        
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
    
    def on_type_changed(self, dropdown, _param):
        """Handle stair type change."""
        if self._block_updates or not self.current_stairs:
            return
        
        selected = dropdown.get_selected()
        if selected == 0:
            stair_type = "straight"
        elif selected == 1:
            stair_type = "L-shaped"
        elif selected == 2:
            stair_type = "U-shaped"
        else:
            stair_type = "spiral"
        
        for stair in self.current_stairs:
            stair.stair_type = stair_type
        
        # Show/hide specific controls
        is_multi_segment = (stair_type in ["L-shaped", "U-shaped"])
        is_u_shaped = (stair_type == "U-shaped")
        is_spiral = (stair_type == "spiral")
        
        # If switching to multi-segment and steps_before_landing is 0 (default/unset),
        # set it to a sensible default (3) instead of leaving it at 0 (which renders as half).
        # This matches the spinner minimum and provides a better user experience.
        if is_multi_segment:
            for stair in self.current_stairs:
                current_val = getattr(stair, 'steps_before_landing', 0)
                if current_val == 0:
                     stair.steps_before_landing = 3
                     # Also update the spinner to match this new reality
                     self.spin_steps_before.set_value(3)

        self.row_turn.set_visible(is_multi_segment or is_spiral)
        self.row_landing.set_visible(is_multi_segment)
        self.row_steps_before.set_visible(is_multi_segment)
        
        # Well/Gap row is reused for Inner Radius in Spiral
        self.row_well.set_visible(is_u_shaped or is_spiral)
        if is_spiral:
            self.lbl_well.set_label("Inner Radius (in):")
        else:
            self.lbl_well.set_label("Well Width (in):")
            
        self.row_rotation.set_visible(is_spiral)
        
        self.emit_property_changed()
    
    def on_turn_changed(self, dropdown, _param):
        """Handle turn direction change."""
        if self._block_updates or not self.current_stairs:
            return
        
        selected = dropdown.get_selected()
        turn_direction = "left" if selected == 0 else "right"
        
        for stair in self.current_stairs:
            stair.turn_direction = turn_direction
        
        self.emit_property_changed()
    
    def on_landing_changed(self, spin):
        """Handle landing depth change."""
        if self._block_updates or not self.current_stairs:
            return
        
        val = spin.get_value()
        for stair in self.current_stairs:
            stair.landing_depth = val
        
        self.emit_property_changed()
    
    def on_steps_before_changed(self, spin):
        """Handle steps before landing change."""
        if self._block_updates or not self.current_stairs:
            return
        
        val = int(spin.get_value())
        for stair in self.current_stairs:
             stair.steps_before_landing = val
             
        self.emit_property_changed()
        
    def on_well_changed(self, spin):
        """Handle well width (gap) change."""
        if self._block_updates or not self.current_stairs:
            return
            
        val = spin.get_value()
        for stair in self.current_stairs:
            # We use inner_radius to store the well/gap width
            stair.inner_radius = val
            
        self.emit_property_changed()

    def on_rotation_changed(self, spin):
        """Handle rotation angle change."""
        if self._block_updates or not self.current_stairs:
            return
            
        val = spin.get_value()
        for stair in self.current_stairs:
            stair.rotation_degrees = val
            
        self.emit_property_changed()


