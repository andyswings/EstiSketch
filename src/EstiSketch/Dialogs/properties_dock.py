from .layers_panel import LayersPanel
from gi.repository import Gtk, GObject
import gi
import os
import json
gi.require_version('Gtk', '4.0')

# Stub widgets—you can flesh these out with real controls



class RoofPropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.current_roofs = []
        self._block_updates = False

        # Frame
        frame = Gtk.Frame(label="Roof Properties")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        frame.set_child(box)
        self.append(frame)

        # Pitch Rise
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Pitch Rise:"))
        self.pitch_rise_spin = Gtk.SpinButton.new_with_range(0, 24, 1)
        self.pitch_rise_spin.connect("value-changed", self.on_pitch_changed)
        row.append(self.pitch_rise_spin)
        row.append(Gtk.Label(label="/"))
        
        # Pitch Run (12 or 10)
        self.pitch_run_combo = Gtk.ComboBoxText()
        self.pitch_run_combo.append_text("12")
        self.pitch_run_combo.append_text("10")
        self.pitch_run_combo.set_active(0) # Default to 12
        self.pitch_run_combo.connect("changed", self.on_pitch_changed)
        row.append(self.pitch_run_combo)
        
        box.append(row)
        
        # Overhang
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Overhang:"))
        self.overhang_spin = Gtk.SpinButton.new_with_range(0, 100, 1) # Inches
        self.overhang_spin.connect("value-changed", self.on_overhang_changed)
        row.append(self.overhang_spin)
        row.append(Gtk.Label(label="in"))
        box.append(row)
        
        # Material
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Material:"))
        self.material_combo = Gtk.ComboBoxText()
        for mat in ["asphalt_shingle", "metal", "tile", "slate"]:
            self.material_combo.append_text(mat)
        self.material_combo.connect("changed", self.on_material_changed)
        row.append(self.material_combo)
        box.append(row)

    def on_pitch_changed(self, widget):
        if self._block_updates or not self.current_roofs:
            return
            
        rise = int(self.pitch_rise_spin.get_value())
        run_text = self.pitch_run_combo.get_active_text()
        run = int(run_text) if run_text else 12
        
        for roof in self.current_roofs:
            roof.pitch_rise = rise
            roof.pitch_run = run
            
        self.emit_property_changed()

    def on_overhang_changed(self, spin):
        if self._block_updates or not self.current_roofs:
            return
            
        overhang = spin.get_value()
        for roof in self.current_roofs:
            roof.overhang = overhang
            # Trigger recalculation of outline
            if hasattr(self, "canvas"):
                self.canvas.recalculate_roof(roof)
                
        self.emit_property_changed()

    def on_material_changed(self, combo):
        if self._block_updates or not self.current_roofs:
            return
            
        material = combo.get_active_text()
        if material:
            for roof in self.current_roofs:
                roof.material = material
        self.emit_property_changed()

    def emit_property_changed(self):
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.queue_draw()

    def set_roof(self, roofs):
        self._block_updates = True
        if not isinstance(roofs, list):
            roofs = [roofs]
        self.current_roofs = roofs

        if not roofs:
            self._block_updates = False
            return

        first = roofs[0]

        # Pitch
        self.pitch_rise_spin.set_value(first.pitch_rise)
        
        run_str = str(first.pitch_run)
        found = False
        model = self.pitch_run_combo.get_model()
        for i, row in enumerate(model):
            if row[0] == run_str:
                self.pitch_run_combo.set_active(i)
                found = True
                break
        if not found:
             self.pitch_run_combo.set_active(0) # Default 12

        # Overhang
        self.overhang_spin.set_value(first.overhang)
        
        # Material
        mat = getattr(first, 'material', 'asphalt_shingle')
        # Find index
        found = False
        model = self.material_combo.get_model()
        for i, row in enumerate(model):
            if row[0] == mat:
                self.material_combo.set_active(i)
                found = True
                break
        if not found:
             self.material_combo.set_active(0)

        self._block_updates = False


class WallPropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        # ─── Initialize state fields ───
        self.current_walls = []  # Changed to list for multi-editing
        self._block_updates = False

        # ─────────── Geometry ───────────
        geo_frame = Gtk.Frame(label="Geometry")
        geo_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        geo_box.set_margin_top(6)
        geo_box.set_margin_bottom(6)
        geo_box.set_margin_start(6)
        geo_box.set_margin_end(6)
        geo_frame.set_child(geo_box)
        self.append(geo_frame)

        # Thickness dropdown
        self.available_thicknesses = [3.5, 5.5, 7.25]
        thickness_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        thickness_row.append(Gtk.Label(label="Thickness:"))
        self.thickness_combo = Gtk.ComboBoxText()
        self.thickness_handler_id = self.thickness_combo.connect(
            "changed", self.on_thickness_changed)
        for val in ['3.5" (2x4 wall)', '5.5" (2x6 wall)', '7.25" (2x8 wall)']:
            self.thickness_combo.append_text(val)
        self.thickness_combo.set_active(1)  # default 5.5"
        thickness_row.append(self.thickness_combo)
        geo_box.append(thickness_row)

        # Height dropdown
        self.available_heights = [8, 9, 10, 12]
        height_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        height_row.append(Gtk.Label(label="Height:"))
        self.height_combo = Gtk.ComboBoxText()
        self.height_handler_id = self.height_combo.connect(
            "changed", self.on_height_changed)
        for val in ["8'", "9'", "10'", "12'", "Custom (Coming later)"]:
            self.height_combo.append_text(val)
        self.height_combo.set_active(0)  # default 8'
        height_row.append(self.height_combo)
        geo_box.append(height_row)

        # ─────────── Wall Type ───────────
        type_frame = Gtk.Frame(label="Wall Type")
        type_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        type_box.set_margin_top(6)
        type_box.set_margin_bottom(6)
        type_box.set_margin_start(6)
        type_box.set_margin_end(6)

        type_frame.set_child(type_box)
        self.append(type_frame)

        type_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        type_row.append(Gtk.Label(label="Exterior Wall:"))
        self.exterior_switch = Gtk.Switch()
        type_row.append(self.exterior_switch)
        type_box.append(type_row)

        # ─────────── Footer (Foundation) ───────────
        foot_frame = Gtk.Frame(label="Footer (Foundation)")
        foot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        foot_box.set_margin_top(6)
        foot_box.set_margin_bottom(6)
        foot_box.set_margin_start(6)
        foot_box.set_margin_end(6)

        foot_frame.set_child(foot_box)
        self.append(foot_frame)

        # Enable Footer checkbox
        self.footer_check = Gtk.CheckButton(label="Enable Footer")
        foot_box.append(self.footer_check)

        # Left Offset
        left_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        left_row.append(Gtk.Label(label="Left Offset:"))
        self.footer_left_combo = Gtk.ComboBoxText()
        for val in ['1"', '2"', '3"', '4"', '5"', '6"', 'Custom']:
            self.footer_left_combo.append_text(val)
        self.footer_left_combo.set_active(5)  # default 6"
        left_row.append(self.footer_left_combo)
        foot_box.append(left_row)

        # Right Offset
        right_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        right_row.append(Gtk.Label(label="Right Offset:"))
        self.footer_right_combo = Gtk.ComboBoxText()
        for val in ['1"', '2"', '3"', '4"', '5"', '6"', 'Custom']:
            self.footer_right_combo.append_text(val)
        self.footer_right_combo.set_active(5)
        right_row.append(self.footer_right_combo)
        foot_box.append(right_row)

        # Depth
        depth_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        depth_row.append(Gtk.Label(label="Depth:"))
        self.footer_depth_combo = Gtk.ComboBoxText()
        for val in ['8"', '10"', '12"', 'Custom']:
            self.footer_depth_combo.append_text(val)
        self.footer_depth_combo.set_active(0)  # default 8"
        depth_row.append(self.footer_depth_combo)
        foot_box.append(depth_row)

        # ─────────── Materials & Finishes ───────────
        mat_frame = Gtk.Frame(label="Materials & Finishes")
        mat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        mat_box.set_margin_top(6)
        mat_box.set_margin_bottom(6)
        mat_box.set_margin_start(6)
        mat_box.set_margin_end(6)

        mat_frame.set_child(mat_box)
        self.append(mat_frame)

        # Primary Material
        mat_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        mat_row.append(Gtk.Label(label="Primary Material:"))
        self.material_combo = Gtk.ComboBoxText()
        for val in ["wood", "block", "poured concrete", "steel"]:
            self.material_combo.append_text(val)
        self.material_combo.set_active(0)
        mat_row.append(self.material_combo)
        mat_box.append(mat_row)

        # Interior Finish
        int_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        int_row.append(Gtk.Label(label="Interior Finish:"))
        self.interior_combo = Gtk.ComboBoxText()
        for val in ["Drywall", "T&G Wood"]:
            self.interior_combo.append_text(val)
        self.interior_combo.set_active(0)
        int_row.append(self.interior_combo)
        mat_box.append(int_row)

        # Exterior Finish
        ext_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ext_row.append(Gtk.Label(label="Exterior Finish:"))
        self.exterior_combo = Gtk.ComboBoxText()
        for val in ["Hardie Lap siding", "Vinyl siding", "Stucco"]:
            self.exterior_combo.append_text(val)
        self.exterior_combo.set_active(0)
        ext_row.append(self.exterior_combo)
        mat_box.append(ext_row)

        # ─────────── Structural Details ───────────
        struct_frame = Gtk.Frame(label="Structural Details")
        struct_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        struct_box.set_margin_top(6)
        struct_box.set_margin_bottom(6)
        struct_box.set_margin_start(6)
        struct_box.set_margin_end(6)

        struct_frame.set_child(struct_box)
        self.append(struct_frame)

        # Stud Spacing
        stud_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        stud_row.append(Gtk.Label(label="Stud Spacing:"))
        self.stud_combo = Gtk.ComboBoxText()
        for val in ['12"', '16"', '24"', 'Custom']:
            self.stud_combo.append_text(val)
        self.stud_combo.set_active(1)  # default 16"
        stud_row.append(self.stud_combo)
        struct_box.append(stud_row)

        # Insulation Type
        ins_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ins_row.append(Gtk.Label(label="Insulation Type:"))
        self.insulation_combo = Gtk.ComboBoxText()
        for val in ["Fiberglass", "Spray-in", "Rockwool"]:
            self.insulation_combo.append_text(val)
        self.insulation_combo.set_active(0)
        ins_row.append(self.insulation_combo)
        struct_box.append(ins_row)

        # Fire Rating
        fire_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fire_row.append(Gtk.Label(label="Fire Rating:"))
        self.fire_combo = Gtk.ComboBoxText()
        for val in ["1", "2"]:
            self.fire_combo.append_text(val)
        self.fire_combo.set_active(0)
        fire_row.append(self.fire_combo)
        struct_box.append(fire_row)

        # ─────────── Curve Properties ───────────
        curve_frame = Gtk.Frame(label="Curve Properties")
        curve_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        curve_box.set_margin_top(6)
        curve_box.set_margin_bottom(6)
        curve_box.set_margin_start(6)
        curve_box.set_margin_end(6)
        curve_frame.set_child(curve_box)
        self.append(curve_frame)
        self.curve_frame = curve_frame  # Store reference for visibility control

        # Is Curved toggle
        curved_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        curved_row.append(Gtk.Label(label="Curved Wall:"))
        self.curved_switch = Gtk.Switch()
        curved_row.append(self.curved_switch)
        curve_box.append(curved_row)

        # Radius control
        radius_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        radius_row.append(Gtk.Label(label="Radius:"))
        self.radius_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.radius_spin.set_digits(1)
        radius_row.append(self.radius_spin)
        radius_row.append(Gtk.Label(label="in"))
        curve_box.append(radius_row)

        # Arc Length display (read-only)
        arc_len_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        arc_len_row.append(Gtk.Label(label="Arc Length:"))
        self.arc_length_label = Gtk.Label(label="—")
        self.arc_length_label.set_halign(Gtk.Align.START)
        arc_len_row.append(self.arc_length_label)
        curve_box.append(arc_len_row)

        # Sagitta/Bulge control
        sagitta_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sagitta_row.append(Gtk.Label(label="Bulge:"))
        self.sagitta_spin = Gtk.SpinButton.new_with_range(-1000, 1000, 0.5)
        self.sagitta_spin.set_digits(1)
        sagitta_row.append(self.sagitta_spin)
        sagitta_row.append(Gtk.Label(label="in"))
        curve_box.append(sagitta_row)

        # ───── wire signals ─────
        self.height_combo.connect("changed", self.on_height_changed)
        self.exterior_switch.connect("state-set", self.on_exterior_toggled)
        self.footer_check.connect("toggled", self.on_footer_toggled)
        self.footer_left_combo.connect("changed", self.on_footer_left_changed)
        self.footer_right_combo.connect(
            "changed", self.on_footer_right_changed)
        self.footer_depth_combo.connect(
            "changed", self.on_footer_depth_changed)
        self.material_combo.connect("changed", self.on_material_changed)
        self.interior_combo.connect("changed", self.on_interior_changed)
        self.exterior_combo.connect("changed", self.on_ext_finish_changed)
        self.stud_combo.connect("changed", self.on_stud_spacing_changed)
        self.insulation_combo.connect("changed", self.on_insulation_changed)
        self.fire_combo.connect("changed", self.on_fire_rating_changed)
        self.curved_switch.connect("state-set", self.on_curved_toggled)
        self.radius_spin.connect("value-changed", self.on_radius_changed)
        self.sagitta_spin.connect("value-changed", self.on_sagitta_changed)

    # ───── helpers ─────

    def _find_combo_index(self, combo, value):
        """Return the index of the item in combo whose text matches value, or 0 if not found."""
        model = combo.get_model()
        for i, row in enumerate(model):
            # row[0] is the text for Gtk.ComboBoxText
            if row[0] == value:
                return i
        return 0

    # ───── handlers ─────
    def on_thickness_changed(self, combo):
        if self._block_updates or not self.current_walls:
            return

        text = combo.get_active_text()
        if not text:
            return

        token = text.split()[0]

        if token.lower().startswith("custom"):
            return

        try:
            value = float(token.split('"')[0])
        except ValueError:
            return

        # Apply to all selected walls
        for wall in self.current_walls:
            wall.width = value
        self.emit_property_changed()

    def on_height_changed(self, combo):
        if self._block_updates or not self.current_walls:
            return
        txt = combo.get_active_text()
        if txt is not None:
            txt = txt.split()[0]
        else:
            return
        if txt.lower() != "custom":
            height_feet = float(txt.split("'")[0])
            # Wall.height is stored in inches, UI shows feet, so convert
            height_inches = height_feet * 12.0
            for wall in self.current_walls:
                wall.height = height_inches
        self.emit_property_changed()

    def on_exterior_toggled(self, switch, gparam):
        if self._block_updates or not self.current_walls:
            return
        is_exterior = switch.get_active()
        for wall in self.current_walls:
            wall.exterior_wall = is_exterior
        self.emit_property_changed()

    def on_footer_toggled(self, button):
        if self._block_updates or not self.current_walls:
            return
        has_footer = button.get_active()
        for wall in self.current_walls:
            wall.footer = has_footer
        self.emit_property_changed()

    def on_footer_left_changed(self, combo):
        if self._block_updates or not self.current_walls:
            return
        text = combo.get_active_text().strip('"')
        if text.lower() != "custom":
            offset = float(text)
            for wall in self.current_walls:
                wall.footer_left_offset = offset
        self.emit_property_changed()

    def on_footer_right_changed(self, combo):
        if self._block_updates or not self.current_walls:
            return
        text = combo.get_active_text().strip('"')
        if text.lower() != "custom":
            offset = float(text)
            for wall in self.current_walls:
                wall.footer_right_offset = offset
        self.emit_property_changed()

    def on_footer_depth_changed(self, combo):
        if self._block_updates or not self.current_walls:
            return
        text = combo.get_active_text().strip('"')
        if text.lower() != "custom":
            depth = float(text)
            for wall in self.current_walls:
                wall.footer_depth = depth
        self.emit_property_changed()

    def on_material_changed(self, combo):
        if self._block_updates or not self.current_walls:
            return
        text = combo.get_active_text()
        if text:
            for wall in self.current_walls:
                wall.material = text
        self.emit_property_changed()

    def on_interior_changed(self, combo):
        if self._block_updates or not self.current_walls:
            return
        text = combo.get_active_text()
        if text:
            for wall in self.current_walls:
                wall.interior_finish = text
        self.emit_property_changed()

    def on_ext_finish_changed(self, combo):
        if self._block_updates or not self.current_walls:
            return
        text = combo.get_active_text()
        if text:
            for wall in self.current_walls:
                wall.exterior_finish = text
        self.emit_property_changed()

    def on_stud_spacing_changed(self, combo):
        if self._block_updates or not self.current_walls:
            return
        text = combo.get_active_text().strip('"')
        if text.lower() != "custom":
            spacing = float(text)
            for wall in self.current_walls:
                wall.stud_spacing = spacing
        self.emit_property_changed()

    def on_insulation_changed(self, combo):
        if self._block_updates or not self.current_walls:
            return
        text = combo.get_active_text()
        if text:
            for wall in self.current_walls:
                wall.insulation_type = text
        self.emit_property_changed()

    def on_fire_rating_changed(self, combo):
        if self._block_updates or not self.current_walls:
            return
        text = combo.get_active_text()
        if text.lower() != "custom":
            # Extract the numeric part and convert to float
            rating = float(text.split()[0])
            for wall in self.current_walls:
                wall.fire_rating = rating
        self.emit_property_changed()

    def on_curved_toggled(self, switch, gparam):
        """Handle curved wall toggle."""
        if self._block_updates or not self.current_walls:
            return
        import math
        
        is_curved = switch.get_active()
        for wall in self.current_walls:
            if is_curved and not wall.is_curved:
                # Convert straight to curved - create default bulge
                mid_x = (wall.start[0] + wall.end[0]) / 2
                mid_y = (wall.start[1] + wall.end[1]) / 2
                
                dx = wall.end[0] - wall.start[0]
                dy = wall.end[1] - wall.start[1]
                length = math.hypot(dx, dy)
                
                if length > 0:
                    # Default bulge at 1/4 wall length perpendicular
                    bulge_x = mid_x - dy / 4
                    bulge_y = mid_y + dx / 4
                    
                    # Calculate arc geometry using canvas method if available
                    if hasattr(self.canvas, 'get_circle_from_3_points'):
                        geom = self.canvas.get_circle_from_3_points(
                            wall.start, wall.end, (bulge_x, bulge_y))
                        if geom:
                            (cx, cy), radius = geom
                            wall.is_curved = True
                            wall.arc_center = (cx, cy)
                            wall.arc_radius = radius
            elif not is_curved and wall.is_curved:
                # Convert curved to straight
                wall.is_curved = False
                wall.arc_center = None
                wall.arc_radius = None
        
        self._update_curve_controls()
        self.emit_property_changed()

    def on_radius_changed(self, spin):
        """Handle radius value change - adjust arc while maintaining sagitta direction."""
        if self._block_updates or not self.current_walls:
            return
        import math
        
        new_radius = spin.get_value()
        
        for wall in self.current_walls:
            if not wall.is_curved or not wall.arc_center:
                continue
            
            # Calculate chord geometry
            start_x, start_y = wall.start
            end_x, end_y = wall.end
            chord_mid_x = (start_x + end_x) / 2
            chord_mid_y = (start_y + end_y) / 2
            half_chord = math.hypot(end_x - start_x, end_y - start_y) / 2
            
            # Can't have radius smaller than half chord
            if new_radius < half_chord:
                new_radius = half_chord + 0.1
                self._block_updates = True
                spin.set_value(new_radius)
                self._block_updates = False
            
            # Get current arc direction (which side of chord is center)
            old_cx, old_cy = wall.arc_center
            chord_dx = end_x - start_x
            chord_dy = end_y - start_y
            chord_len = math.hypot(chord_dx, chord_dy)
            
            if chord_len > 0:
                # Perpendicular direction
                perp_x = -chord_dy / chord_len
                perp_y = chord_dx / chord_len
                
                # Determine which side center is on
                to_center_x = old_cx - chord_mid_x
                to_center_y = old_cy - chord_mid_y
                center_side = perp_x * to_center_x + perp_y * to_center_y
                
                # Calculate new center position with new radius
                # Distance from chord midpoint to center = sqrt(r² - half_chord²)
                if new_radius >= half_chord:
                    center_dist = math.sqrt(new_radius**2 - half_chord**2)
                    
                    # Keep same side as before
                    if center_side >= 0:
                        new_cx = chord_mid_x + perp_x * center_dist
                        new_cy = chord_mid_y + perp_y * center_dist
                    else:
                        new_cx = chord_mid_x - perp_x * center_dist
                        new_cy = chord_mid_y - perp_y * center_dist
                    
                    wall.arc_center = (new_cx, new_cy)
                    wall.arc_radius = new_radius
        
        self._update_arc_length_display()
        self.emit_property_changed()

    def on_sagitta_changed(self, spin):
        """Handle sagitta/bulge value change."""
        if self._block_updates or not self.current_walls:
            return
        import math
        
        sagitta = spin.get_value()
        
        for wall in self.current_walls:
            if not wall.is_curved:
                continue
            
            # Calculate chord geometry
            start_x, start_y = wall.start
            end_x, end_y = wall.end
            chord_mid_x = (start_x + end_x) / 2
            chord_mid_y = (start_y + end_y) / 2
            half_chord = math.hypot(end_x - start_x, end_y - start_y) / 2
            
            chord_dx = end_x - start_x
            chord_dy = end_y - start_y
            chord_len = math.hypot(chord_dx, chord_dy)
            
            if chord_len > 0 and abs(sagitta) > 0.1:
                # Perpendicular unit vector
                perp_x = -chord_dy / chord_len
                perp_y = chord_dx / chord_len
                
                # Calculate radius from sagitta: r = (s² + c²) / (2|s|)
                new_radius = (sagitta**2 + half_chord**2) / (2 * abs(sagitta))
                
                # Distance from chord midpoint to center
                center_dist = new_radius - abs(sagitta)
                
                # Position center based on sagitta sign
                if sagitta > 0:
                    new_cx = chord_mid_x - perp_x * center_dist
                    new_cy = chord_mid_y - perp_y * center_dist
                else:
                    new_cx = chord_mid_x + perp_x * center_dist
                    new_cy = chord_mid_y + perp_y * center_dist
                
                wall.arc_center = (new_cx, new_cy)
                wall.arc_radius = new_radius
        
        self._update_radius_display()
        self._update_arc_length_display()
        self.emit_property_changed()

    def _update_curve_controls(self):
        """Update curve control values from current walls."""
        if not self.current_walls:
            return
        
        import math
        first_wall = self.current_walls[0]
        
        self._block_updates = True
        
        # Update radius and sagitta sensitivity based on curved state
        is_curved = first_wall.is_curved if first_wall else False
        self.radius_spin.set_sensitive(is_curved)
        self.sagitta_spin.set_sensitive(is_curved)
        
        if is_curved and first_wall.arc_radius:
            self.radius_spin.set_value(first_wall.arc_radius)
            
            # Calculate sagitta
            start_x, start_y = first_wall.start
            end_x, end_y = first_wall.end
            chord_mid_x = (start_x + end_x) / 2
            chord_mid_y = (start_y + end_y) / 2
            half_chord = math.hypot(end_x - start_x, end_y - start_y) / 2
            
            if first_wall.arc_center:
                cx, cy = first_wall.arc_center
                chord_dx = end_x - start_x
                chord_dy = end_y - start_y
                chord_len = math.hypot(chord_dx, chord_dy)
                
                if chord_len > 0:
                    perp_x = -chord_dy / chord_len
                    perp_y = chord_dx / chord_len
                    
                    # Sagitta = radius - center_dist (with sign based on direction)
                    to_center_x = cx - chord_mid_x
                    to_center_y = cy - chord_mid_y
                    center_dist = math.hypot(to_center_x, to_center_y)
                    
                    # Determine sign based on which side of chord
                    center_side = perp_x * to_center_x + perp_y * to_center_y
                    sagitta = first_wall.arc_radius - center_dist
                    if center_side < 0:
                        sagitta = -sagitta
                    
                    self.sagitta_spin.set_value(sagitta)
        else:
            self.radius_spin.set_value(0)
            self.sagitta_spin.set_value(0)
        
        self._update_arc_length_display()
        self._block_updates = False

    def _update_radius_display(self):
        """Update radius spin from current wall."""
        if not self.current_walls:
            return
        first_wall = self.current_walls[0]
        if first_wall.is_curved and first_wall.arc_radius:
            self._block_updates = True
            self.radius_spin.set_value(first_wall.arc_radius)
            self._block_updates = False

    def _update_arc_length_display(self):
        """Update arc length label from current wall geometry."""
        import math
        
        if not self.current_walls:
            self.arc_length_label.set_text("—")
            return
        
        first_wall = self.current_walls[0]
        if not first_wall.is_curved or not first_wall.arc_center or not first_wall.arc_radius:
            self.arc_length_label.set_text("—")
            return
        
        cx, cy = first_wall.arc_center
        radius = first_wall.arc_radius
        
        # Calculate arc angle
        start_angle = math.atan2(first_wall.start[1] - cy, first_wall.start[0] - cx)
        end_angle = math.atan2(first_wall.end[1] - cy, first_wall.end[0] - cx)
        
        angle_diff = end_angle - start_angle
        while angle_diff > math.pi:
            angle_diff -= 2 * math.pi
        while angle_diff < -math.pi:
            angle_diff += 2 * math.pi
        
        arc_length = abs(angle_diff) * radius
        
        # Format display
        if hasattr(self, 'canvas') and hasattr(self.canvas, 'converter'):
            arc_str = self.canvas.converter.format_measurement(arc_length, use_fraction=False)
        else:
            arc_str = f"{arc_length:.1f}\""
        
        self.arc_length_label.set_text(arc_str)


    def emit_property_changed(self):
        """Notify the rest of the app that the model changed."""
        # you'll want to queue a redraw of the canvas:
        self.canvas.queue_draw()

    # ───── populate UI from a Wall instance ─────
    def set_wall(self, wall_objs):
        """Set wall properties. Accepts either a single wall or a list of walls."""
        # Block change handlers while we sync the UI
        self._block_updates = True

        # Normalize to list
        if not isinstance(wall_objs, list):
            wall_objs = [wall_objs]

        self.current_walls = wall_objs

        if not wall_objs:
            self._block_updates = False
            return

        # Use first wall as reference for displaying values
        first_wall = wall_objs[0]

        #
        # Thickness (wall.width is in inches, matches self.available_thicknesses)
        #
        thickness_index = 0  # fallback if no match
        for i, val in enumerate(self.available_thicknesses):
            if abs(val - float(first_wall.width)) < 1e-6:
                thickness_index = i
                break

        self.thickness_combo.handler_block(self.thickness_handler_id)
        self.thickness_combo.set_active(thickness_index)
        self.thickness_combo.handler_unblock(self.thickness_handler_id)

        #  Height (wall.height is in feet, matches self.available_heights)
        height_feet = float(first_wall.height) / \
            12.0 if first_wall.height is not None else 8.0
        height_index = 0
        for i, ft in enumerate(self.available_heights):
            if abs(ft - height_feet) < 1e-6:
                height_index = i
                break

        self.height_combo.handler_block(self.height_handler_id)
        self.height_combo.set_active(height_index)
        self.height_combo.handler_unblock(self.height_handler_id)

        #
        # Exterior
        #
        self.exterior_switch.set_active(first_wall.exterior_wall)

        #
        # Footer fields
        #
        self.footer_check.set_active(first_wall.footer)
        self.footer_left_combo.set_active(
            self._find_combo_index(
                self.footer_left_combo, f'{
                    first_wall.footer_left_offset:.0f}"'))
        self.footer_right_combo.set_active(
            self._find_combo_index(
                self.footer_right_combo, f'{
                    first_wall.footer_right_offset:.0f}"'))
        self.footer_depth_combo.set_active(
            self._find_combo_index(
                self.footer_depth_combo, f'{
                    first_wall.footer_depth:.0f}"'))

        #
        # Materials & finishes
        #
        self.material_combo.set_active(
            self._find_combo_index(self.material_combo, first_wall.material)
        )
        self.interior_combo.set_active(
            self._find_combo_index(
                self.interior_combo,
                first_wall.interior_finish))
        self.exterior_combo.set_active(
            self._find_combo_index(
                self.exterior_combo,
                first_wall.exterior_finish))

        #
        # Structural details
        #
        self.stud_combo.set_active(self._find_combo_index(
            self.stud_combo, f'{int(first_wall.stud_spacing)}"'))
        self.insulation_combo.set_active(
            self._find_combo_index(
                self.insulation_combo,
                first_wall.insulation_type))
        self.fire_combo.set_active(self._find_combo_index(
            self.fire_combo, f"{int(first_wall.fire_rating)}"))

        #
        # Curved wall properties
        #
        is_curved = getattr(first_wall, 'is_curved', False)
        self.curved_switch.set_active(is_curved)
        self.radius_spin.set_sensitive(is_curved)
        self.sagitta_spin.set_sensitive(is_curved)
        
        if is_curved and first_wall.arc_radius:
            self.radius_spin.set_value(first_wall.arc_radius)
            
            # Calculate and display sagitta
            import math
            start_x, start_y = first_wall.start
            end_x, end_y = first_wall.end
            chord_mid_x = (start_x + end_x) / 2
            chord_mid_y = (start_y + end_y) / 2
            
            if first_wall.arc_center:
                cx, cy = first_wall.arc_center
                chord_dx = end_x - start_x
                chord_dy = end_y - start_y
                chord_len = math.hypot(chord_dx, chord_dy)
                
                if chord_len > 0:
                    perp_x = -chord_dy / chord_len
                    perp_y = chord_dx / chord_len
                    
                    to_center_x = cx - chord_mid_x
                    to_center_y = cy - chord_mid_y
                    center_dist = math.hypot(to_center_x, to_center_y)
                    
                    center_side = perp_x * to_center_x + perp_y * to_center_y
                    sagitta = first_wall.arc_radius - center_dist
                    if center_side < 0:
                        sagitta = -sagitta
                    
                    self.sagitta_spin.set_value(sagitta)
        else:
            self.radius_spin.set_value(0)
            self.sagitta_spin.set_value(0)
        
        self._update_arc_length_display()

        # Done syncing, let change handlers run again
        self._block_updates = False


class TextPropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.current_texts = []  # Changed to list to support multi-editing
        self._block_updates = False

        # Geometry
        frame = Gtk.Frame(label="Text Properties")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        frame.set_child(box)
        self.append(frame)

        # Content
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Content:"))
        self.content_entry = Gtk.Entry()
        self.content_entry.connect("changed", self.on_content_changed)
        row.append(self.content_entry)
        box.append(row)

        # Font Size
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Font Size:"))
        self.size_spin = Gtk.SpinButton.new_with_range(6, 72, 1)
        self.size_spin.connect("value-changed", self.on_size_changed)
        row.append(self.size_spin)
        box.append(row)

        # Font Family
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Font:"))
        self.font_combo = Gtk.ComboBoxText()
        for font in [
            "Sans",
            "Serif",
            "Monospace",
            "Arial",
            "Times New Roman",
                "Courier New"]:
            self.font_combo.append_text(font)
        self.font_combo.connect("changed", self.on_font_changed)
        row.append(self.font_combo)
        box.append(row)

        # Color
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Color:"))
        self.color_button = Gtk.ColorButton()
        self.color_button.connect("color-set", self.on_color_changed)
        row.append(self.color_button)
        box.append(row)

        # Rotation
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Rotation (°):"))
        self.rotation_spin = Gtk.SpinButton.new_with_range(-180, 180, 1)
        self.rotation_spin.connect("value-changed", self.on_rotation_changed)
        row.append(self.rotation_spin)
        box.append(row)

        # Styles
        style_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.bold_check = Gtk.CheckButton(label="Bold")
        self.bold_check.connect("toggled", self.on_style_toggled)
        style_box.append(self.bold_check)

        self.italic_check = Gtk.CheckButton(label="Italic")
        self.italic_check.connect("toggled", self.on_style_toggled)
        style_box.append(self.italic_check)

        self.underline_check = Gtk.CheckButton(label="Underline")
        self.underline_check.connect("toggled", self.on_style_toggled)
        style_box.append(self.underline_check)

        box.append(style_box)

    def on_content_changed(self, entry):
        if self._block_updates or not self.current_texts:
            return
        for text in self.current_texts:
            text.content = entry.get_text()
        self.emit_property_changed()

    def on_size_changed(self, spin):
        if self._block_updates or not self.current_texts:
            return
        for text in self.current_texts:
            text.font_size = spin.get_value()
        self.emit_property_changed()

    def on_font_changed(self, combo):
        if self._block_updates or not self.current_texts:
            return
        font_family = combo.get_active_text()
        for text in self.current_texts:
            text.font_family = font_family
        self.emit_property_changed()

    def on_rotation_changed(self, spin):
        if self._block_updates or not self.current_texts:
            return
        rotation = spin.get_value()
        for text in self.current_texts:
            text.rotation = rotation
        self.emit_property_changed()

    def on_color_changed(self, color_button):
        if self._block_updates or not self.current_texts:
            return
        rgba = color_button.get_rgba()
        # Convert RGBA to RGB tuple (0.0-1.0 range)
        color = (rgba.red, rgba.green, rgba.blue)
        for text in self.current_texts:
            text.color = color
        self.emit_property_changed()

    def on_style_toggled(self, check):
        if self._block_updates or not self.current_texts:
            return
        bold = self.bold_check.get_active()
        italic = self.italic_check.get_active()
        underline = self.underline_check.get_active()
        for text in self.current_texts:
            text.bold = bold
            text.italic = italic
            text.underline = underline
        self.emit_property_changed()

    def emit_property_changed(self):
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.queue_draw()

    def set_text(self, text_objs):
        """Set text properties. Accepts either a single text object or a list of text objects."""
        self._block_updates = True

        # Normalize to list
        if not isinstance(text_objs, list):
            text_objs = [text_objs]

        self.current_texts = text_objs

        if not text_objs:
            self._block_updates = False
            return

        # Use first text as reference for displaying values
        first_text = text_objs[0]

        # For multi-selection, check if all values are the same
        # If not, show placeholder or first value

        # Content - show first text's content (or could show "<Multiple>" if
        # different)
        all_same_content = all(
            t.content == first_text.content for t in text_objs)
        if all_same_content:
            self.content_entry.set_text(first_text.content)
        else:
            self.content_entry.set_text("<Multiple>")

        # Font Size
        all_same_size = all(
            t.font_size == first_text.font_size for t in text_objs)
        if all_same_size:
            self.size_spin.set_value(first_text.font_size)
        else:
            self.size_spin.set_value(first_text.font_size)  # Show first value

        # Font Family
        all_same_font = all(
            t.font_family == first_text.font_family for t in text_objs)
        idx = 0
        model = self.font_combo.get_model()
        for i, row in enumerate(model):
            if row[0] == first_text.font_family:
                idx = i
                break
        self.font_combo.set_active(idx)

        # Color
        color = getattr(first_text, 'color', (0.0, 0.0, 0.0))
        from gi.repository import Gdk
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = color[0], color[1], color[2], 1.0
        self.color_button.set_rgba(rgba)

        # Rotation
        all_same_rotation = all(
            t.rotation == first_text.rotation for t in text_objs)
        if all_same_rotation:
            self.rotation_spin.set_value(first_text.rotation)
        else:
            self.rotation_spin.set_value(
                first_text.rotation)  # Show first value

        # Styles
        all_same_bold = all(t.bold == first_text.bold for t in text_objs)
        all_same_italic = all(t.italic == first_text.italic for t in text_objs)
        all_same_underline = all(
            t.underline == first_text.underline for t in text_objs)

        self.bold_check.set_active(first_text.bold)
        self.italic_check.set_active(first_text.italic)
        self.underline_check.set_active(first_text.underline)

        # Note: For checkboxes, GTK4 doesn't have an "inconsistent" state by default
        # We show the first item's value for now

        self._block_updates = False


class DimensionPropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.current_dimension = None
        self._block_updates = False

        # Properties frame
        frame = Gtk.Frame(label="Dimension Properties")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        frame.set_child(box)
        self.append(frame)

        # Measurement display (read-only)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Measurement:"))
        self.measurement_label = Gtk.Label(label="0' 0\"")
        self.measurement_label.set_halign(Gtk.Align.START)
        row.append(self.measurement_label)
        box.append(row)

        # Text Size
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Text Size:"))
        self.text_size_spin = Gtk.SpinButton.new_with_range(6, 72, 1)
        self.text_size_spin.connect("value-changed", self.on_text_size_changed)
        row.append(self.text_size_spin)
        box.append(row)

        # Line Style
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Line Style:"))
        self.line_style_combo = Gtk.ComboBoxText()
        self.line_style_combo.append_text("solid")
        self.line_style_combo.append_text("dashed")
        self.line_style_combo.connect("changed", self.on_line_style_changed)
        row.append(self.line_style_combo)
        box.append(row)

        # Color
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Color:"))
        self.color_button = Gtk.ColorButton()
        self.color_button.connect("color-set", self.on_color_changed)
        row.append(self.color_button)
        box.append(row)

        # Show Arrows
        self.show_arrows_check = Gtk.CheckButton(label="Show Arrows")
        self.show_arrows_check.connect("toggled", self.on_show_arrows_toggled)
        box.append(self.show_arrows_check)

    def on_text_size_changed(self, spin):
        if self._block_updates or not self.current_dimension:
            return
        self.current_dimension.text_size = spin.get_value()
        self.emit_property_changed()

    def on_line_style_changed(self, combo):
        if self._block_updates or not self.current_dimension:
            return
        self.current_dimension.line_style = combo.get_active_text()
        self.emit_property_changed()

    def on_color_changed(self, color_button):
        if self._block_updates or not self.current_dimension:
            return
        rgba = color_button.get_rgba()
        color = (rgba.red, rgba.green, rgba.blue)
        self.current_dimension.color = color
        self.emit_property_changed()

    def on_show_arrows_toggled(self, check):
        if self._block_updates or not self.current_dimension:
            return
        self.current_dimension.show_arrows = check.get_active()
        self.emit_property_changed()

    def emit_property_changed(self):
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.queue_draw()

    def set_dimension(self, dimension):
        """Set dimension to edit"""
        self._block_updates = True
        self.current_dimension = dimension

        if not dimension:
            self._block_updates = False
            return

        # Calculate and display measurement
        import math
        length = math.hypot(
            dimension.end[0] - dimension.start[0],
            dimension.end[1] - dimension.start[1]
        )
        if hasattr(self, "canvas") and hasattr(self.canvas, "converter"):
            measurement_str = self.canvas.converter.format_measurement(
                length, use_fraction=False)
        else:
            measurement_str = f"{length:.2f}\""
        self.measurement_label.set_text(measurement_str)

        # Text size
        self.text_size_spin.set_value(dimension.text_size)

        # Line style
        if dimension.line_style == "solid":
            self.line_style_combo.set_active(0)
        else:
            self.line_style_combo.set_active(1)

        # Color
        color = getattr(dimension, 'color', (0.0, 0.0, 0.0))
        from gi.repository import Gdk
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = color[0], color[1], color[2], 1.0
        self.color_button.set_rgba(rgba)

        # Show arrows
        self.show_arrows_check.set_active(dimension.show_arrows)

        self._block_updates = False


class WindowPropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        # List of (wall, window, ratio) tuples for multi-editing
        self.current_windows = []
        self._block_updates = False

        # Load window sizes from config file
        # Go up one level from Dialogs to root, then into Resources
        config_path = os.path.join(
            os.path.dirname(
                os.path.dirname(__file__)),
            'Resources',
            'window_door_sizes.json')
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Properties frame
        frame = Gtk.Frame(label="Window Properties")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        frame.set_child(box)
        self.append(frame)

        # Window Type
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Type:"))
        self.type_combo = Gtk.ComboBoxText()
        for window_type in config.get(
            'window_types', [
                "double-hung", "sliding", "fixed"]):
            self.type_combo.append_text(window_type)
        self.type_combo.connect("changed", self.on_type_changed)
        row.append(self.type_combo)
        box.append(row)

        # Width
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Width:"))
        self.width_combo = Gtk.ComboBoxText()
        for width in config.get(
            'window_widths', [
                '24"', '30"', '36"', 'Custom']):
            self.width_combo.append_text(width)
        self.width_combo.connect("changed", self.on_width_changed)
        row.append(self.width_combo)
        box.append(row)

        # Height
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Height:"))
        self.height_combo = Gtk.ComboBoxText()
        for height in config.get(
            'window_heights', [
                '36"', '48"', '60"', 'Custom']):
            self.height_combo.append_text(height)
        self.height_combo.connect("changed", self.on_height_changed)
        row.append(self.height_combo)
        box.append(row)

        # Elevation (height above floor)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Elevation:"))
        self.elevation_spin = Gtk.SpinButton.new_with_range(0, 120, 1)
        self.elevation_spin.set_digits(1)
        self.elevation_spin.connect("value-changed", self.on_elevation_changed)
        row.append(self.elevation_spin)
        label = Gtk.Label(label='inches')
        row.append(label)
        box.append(row)

    def on_type_changed(self, combo):
        if self._block_updates or not self.current_windows:
            return
        window_type = combo.get_active_text()
        if window_type:
            for wall, window, ratio in self.current_windows:
                window.window_type = window_type
        self.emit_property_changed()

    def on_width_changed(self, combo):
        if self._block_updates or not self.current_windows:
            return
        text = combo.get_active_text()
        if not text or text.lower() == "custom":
            return

        try:
            width = float(text.strip('"'))
            for wall, window, ratio in self.current_windows:
                window.width = width
            self.emit_property_changed()
        except ValueError:
            pass

    def on_height_changed(self, combo):
        if self._block_updates or not self.current_windows:
            return
        text = combo.get_active_text()
        if not text or text.lower() == "custom":
            return

        try:
            height = float(text.strip('"'))
            for wall, window, ratio in self.current_windows:
                window.height = height
            self.emit_property_changed()
        except ValueError:
            pass

    def on_elevation_changed(self, spin):
        if self._block_updates or not self.current_windows:
            return
        elevation = spin.get_value()
        for wall, window, ratio in self.current_windows:
            # Store elevation on window object
            window.elevation = elevation
        self.emit_property_changed()

    def emit_property_changed(self):
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.queue_draw()
            self.canvas.save_state()

    def _find_combo_index(self, combo, value):
        """Find index of value in combo box"""
        model = combo.get_model()
        for i, row in enumerate(model):
            if row[0] == value:
                return i
        return 0

    def set_window(self, window_items):
        """Set window properties. Accepts either a single (wall, window, ratio) tuple or a list of them."""
        self._block_updates = True

        # Normalize to list
        if not isinstance(window_items, list):
            window_items = [window_items]

        self.current_windows = window_items

        if not window_items:
            self._block_updates = False
            return

        # Use first window as reference for displaying values
        wall, first_window, ratio = window_items[0]

        # Window Type
        idx = self._find_combo_index(self.type_combo, first_window.window_type)
        self.type_combo.set_active(idx)

        # Width
        width_str = f'{int(first_window.width)}"'
        idx = self._find_combo_index(self.width_combo, width_str)
        self.width_combo.set_active(idx if idx > 0 else 0)

        # Height
        height_str = f'{int(first_window.height)}"'
        idx = self._find_combo_index(self.height_combo, height_str)
        self.height_combo.set_active(idx if idx > 0 else 0)

        # Elevation
        # Calculate default elevation if not set
        elevation = getattr(first_window, 'elevation', None)
        if elevation is None:
            # Default: wall_height - header_height - window_height
            # Assuming 8' wall and 12" header for now
            wall_height = 96.0  # 8 feet in inches
            header_height = 12.0  # 12 inches
            elevation = wall_height - header_height - first_window.height
            first_window.elevation = elevation

        self.elevation_spin.set_value(elevation)

        self._block_updates = False


class DoorPropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        # List of (wall, door, ratio) tuples for multi-editing
        self.current_doors = []
        self._block_updates = False

        # Load door sizes from config file
        # Go up one level from Dialogs to root, then into Resources
        config_path = os.path.join(
            os.path.dirname(
                os.path.dirname(__file__)),
            'Resources',
            'window_door_sizes.json')
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Properties frame
        frame = Gtk.Frame(label="Door Properties")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        frame.set_child(box)
        self.append(frame)

        # Door Type
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Type:"))
        self.type_combo = Gtk.ComboBoxText()
        for door_type in config.get(
            'door_types', [
                "single", "double", "sliding"]):
            self.type_combo.append_text(door_type)
        self.type_combo.connect("changed", self.on_type_changed)
        row.append(self.type_combo)
        box.append(row)

        # Width
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Width:"))
        self.width_combo = Gtk.ComboBoxText()
        for width in config.get(
            'door_widths', [
                '30"', '32"', '36"', 'Custom']):
            self.width_combo.append_text(width)
        self.width_combo.connect("changed", self.on_width_changed)
        row.append(self.width_combo)
        box.append(row)

        # Height
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Height:"))
        self.height_combo = Gtk.ComboBoxText()
        for height in config.get(
            'door_heights', [
                '78"', '80"', '84"', 'Custom']):
            self.height_combo.append_text(height)
        self.height_combo.connect("changed", self.on_height_changed)
        row.append(self.height_combo)
        box.append(row)

        # Swing
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Swing:"))
        self.swing_combo = Gtk.ComboBoxText()
        for swing in ["left", "right"]:
            self.swing_combo.append_text(swing)
        self.swing_combo.connect("changed", self.on_swing_changed)
        row.append(self.swing_combo)
        box.append(row)

        # Orientation
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Orientation:"))
        self.orientation_combo = Gtk.ComboBoxText()
        for orientation in ["inswing", "outswing"]:
            self.orientation_combo.append_text(orientation)
        self.orientation_combo.connect("changed", self.on_orientation_changed)
        row.append(self.orientation_combo)
        box.append(row)

    def on_type_changed(self, combo):
        if self._block_updates or not self.current_doors:
            return
        door_type = combo.get_active_text()
        if door_type:
            for wall, door, ratio in self.current_doors:
                door.door_type = door_type
        self.emit_property_changed()

    def on_width_changed(self, combo):
        if self._block_updates or not self.current_doors:
            return
        text = combo.get_active_text()
        if not text or text.lower() == "custom":
            return

        try:
            width = float(text.strip('"'))
            for wall, door, ratio in self.current_doors:
                door.width = width
            self.emit_property_changed()
        except ValueError:
            pass

    def on_height_changed(self, combo):
        if self._block_updates or not self.current_doors:
            return
        text = combo.get_active_text()
        if not text or text.lower() == "custom":
            return

        try:
            height = float(text.strip('"'))
            for wall, door, ratio in self.current_doors:
                door.height = height
            self.emit_property_changed()
        except ValueError:
            pass

    def on_swing_changed(self, combo):
        if self._block_updates or not self.current_doors:
            return
        swing = combo.get_active_text()
        if swing:
            for wall, door, ratio in self.current_doors:
                door.swing = swing
        self.emit_property_changed()

    def on_orientation_changed(self, combo):
        if self._block_updates or not self.current_doors:
            return
        orientation = combo.get_active_text()
        if orientation:
            for wall, door, ratio in self.current_doors:
                door.orientation = orientation
        self.emit_property_changed()

    def emit_property_changed(self):
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.queue_draw()
            self.canvas.save_state()

    def _find_combo_index(self, combo, value):
        """Find index of value in combo box"""
        model = combo.get_model()
        for i, row in enumerate(model):
            if row[0] == value:
                return i
        return 0

    def set_door(self, door_items):
        """Set door properties. Accepts either a single (wall, door, ratio) tuple or a list of them."""
        self._block_updates = True

        # Normalize to list
        if not isinstance(door_items, list):
            door_items = [door_items]

        self.current_doors = door_items

        if not door_items:
            self._block_updates = False
            return

        # Use first door as reference for displaying values
        wall, first_door, ratio = door_items[0]

        # Door Type
        idx = self._find_combo_index(self.type_combo, first_door.door_type)
        self.type_combo.set_active(idx)

        # Width
        width_str = f'{int(first_door.width)}"'
        idx = self._find_combo_index(self.width_combo, width_str)
        self.width_combo.set_active(idx if idx > 0 else 0)

        # Height
        height_str = f'{int(first_door.height)}"'
        idx = self._find_combo_index(self.height_combo, height_str)
        self.height_combo.set_active(idx if idx > 0 else 0)

        # Swing
        idx = self._find_combo_index(self.swing_combo, first_door.swing)
        self.swing_combo.set_active(idx)

        # Orientation
        idx = self._find_combo_index(
            self.orientation_combo,
            first_door.orientation)
        self.orientation_combo.set_active(idx)

        self._block_updates = False


class CirclePropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.current_circles = []
        self._block_updates = False

        # Frame
        frame = Gtk.Frame(label="Circle Properties")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        frame.set_child(box)
        self.append(frame)

        # Radius (displayed in inches)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Radius:"))
        self.radius_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.radius_spin.set_digits(2)
        self.radius_spin.connect("value-changed", self.on_radius_changed)
        row.append(self.radius_spin)
        box.append(row)

        # Line Style
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Line Style:"))
        self.line_style_combo = Gtk.ComboBoxText()
        self.line_style_combo.append_text("solid")
        self.line_style_combo.append_text("dashed")
        self.line_style_combo.connect("changed", self.on_line_style_changed)
        row.append(self.line_style_combo)
        box.append(row)

        # Color
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Color:"))
        self.color_button = Gtk.ColorButton()
        self.color_button.connect("color-set", self.on_color_changed)
        row.append(self.color_button)
        box.append(row)

    def on_radius_changed(self, spin):
        if self._block_updates or not self.current_circles:
            return
        radius = spin.get_value()
        for circle in self.current_circles:
            circle.radius = radius
        self.emit_property_changed()

    def on_line_style_changed(self, combo):
        if self._block_updates or not self.current_circles:
            return
        style = combo.get_active_text()
        if style:
            for circle in self.current_circles:
                circle.line_style = style
        self.emit_property_changed()

    def on_color_changed(self, color_button):
        if self._block_updates or not self.current_circles:
            return
        rgba = color_button.get_rgba()
        color = (rgba.red, rgba.green, rgba.blue)
        for circle in self.current_circles:
            circle.color = color
        self.emit_property_changed()

    def emit_property_changed(self):
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.queue_draw()
            # self.canvas.save_state() # Ideally we save state on changes

    def set_circle(self, circles):
        self._block_updates = True
        if not isinstance(circles, list):
            circles = [circles]
        self.current_circles = circles

        if not circles:
            self._block_updates = False
            return

        first = circles[0]

        # Radius
        # Check if all same
        self.radius_spin.set_value(first.radius)

        # Line Style
        style = getattr(first, 'line_style', 'solid')
        if style == 'dashed':
            self.line_style_combo.set_active(1)
        else:
            self.line_style_combo.set_active(0)

        # Color
        color = getattr(first, 'color', (0.0, 0.0, 0.0))
        from gi.repository import Gdk
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = color[0], color[1], color[2], 1.0
        self.color_button.set_rgba(rgba)

        self._block_updates = False


class ArcPropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.current_arcs = []
        self._block_updates = False

        # Frame
        frame = Gtk.Frame(label="Arc Properties")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        frame.set_child(box)
        self.append(frame)

        # Radius
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Radius:"))
        self.radius_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.radius_spin.set_digits(2)
        self.radius_spin.connect("value-changed", self.on_radius_changed)
        row.append(self.radius_spin)
        box.append(row)

        # Start Angle (degrees)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Start Angle (°):"))
        self.start_angle_spin = Gtk.SpinButton.new_with_range(-360, 360, 1)
        self.start_angle_spin.connect("value-changed", self.on_angles_changed)
        row.append(self.start_angle_spin)
        box.append(row)

        # End Angle (degrees)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="End Angle (°):"))
        self.end_angle_spin = Gtk.SpinButton.new_with_range(-360, 360, 1)
        self.end_angle_spin.connect("value-changed", self.on_angles_changed)
        row.append(self.end_angle_spin)
        box.append(row)

        # Line Style
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Line Style:"))
        self.line_style_combo = Gtk.ComboBoxText()
        self.line_style_combo.append_text("solid")
        self.line_style_combo.append_text("dashed")
        self.line_style_combo.connect("changed", self.on_line_style_changed)
        row.append(self.line_style_combo)
        box.append(row)

        # Color
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Color:"))
        self.color_button = Gtk.ColorButton()
        self.color_button.connect("color-set", self.on_color_changed)
        row.append(self.color_button)
        box.append(row)

    def on_radius_changed(self, spin):
        if self._block_updates or not self.current_arcs:
            return
        radius = spin.get_value()
        for arc in self.current_arcs:
            arc.radius = radius
        self.emit_property_changed()

    def on_angles_changed(self, spin):
        if self._block_updates or not self.current_arcs:
            return
        # Convert degrees to radians
        start_deg = self.start_angle_spin.get_value()
        end_deg = self.end_angle_spin.get_value()
        
        # Ensure end > start? Not necessarily required by math, but usually arc is CCW
        
        for arc in self.current_arcs:
            arc.start_angle = math.radians(start_deg)
            arc.end_angle = math.radians(end_deg)
        self.emit_property_changed()

    def on_line_style_changed(self, combo):
        if self._block_updates or not self.current_arcs:
            return
        style = combo.get_active_text()
        if style:
            for arc in self.current_arcs:
                arc.line_style = style
        self.emit_property_changed()

    def on_color_changed(self, color_button):
        if self._block_updates or not self.current_arcs:
            return
        rgba = color_button.get_rgba()
        color = (rgba.red, rgba.green, rgba.blue)
        for arc in self.current_arcs:
            arc.color = color
        self.emit_property_changed()

    def emit_property_changed(self):
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.queue_draw()

    def set_arc(self, arcs):
        self._block_updates = True
        if not isinstance(arcs, list):
            arcs = [arcs]
        self.current_arcs = arcs

        if not arcs:
            self._block_updates = False
            return

        first = arcs[0]

        # Radius
        self.radius_spin.set_value(first.radius)

        # Angles (radians to degrees)
        import math
        self.start_angle_spin.set_value(math.degrees(first.start_angle))
        self.end_angle_spin.set_value(math.degrees(first.end_angle))

        # Line Style
        style = getattr(first, 'line_style', 'solid')
        if style == 'dashed':
            self.line_style_combo.set_active(1)
        else:
            self.line_style_combo.set_active(0)

        # Color
        color = getattr(first, 'color', (0.0, 0.0, 0.0))
        from gi.repository import Gdk
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = color[0], color[1], color[2], 1.0
        self.color_button.set_rgba(rgba)

        self._block_updates = False


class PolylinePropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.current_polylines = []
        self._block_updates = False

        # Frame
        frame = Gtk.Frame(label="Polyline Properties")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        frame.set_child(box)
        self.append(frame)

        # Line Style
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Line Style:"))
        self.line_style_combo = Gtk.ComboBoxText()
        self.line_style_combo.append_text("solid")
        self.line_style_combo.append_text("dashed")
        self.line_style_combo.connect("changed", self.on_line_style_changed)
        row.append(self.line_style_combo)
        box.append(row)

        # Color
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label="Color:"))
        self.color_button = Gtk.ColorButton()
        self.color_button.connect("color-set", self.on_color_changed)
        row.append(self.color_button)
        box.append(row)

    def on_line_style_changed(self, combo):
        if self._block_updates or not self.current_polylines:
            return
        style = combo.get_active_text()
        if style:
            for pl in self.current_polylines:
                pl.style = style
        self.emit_property_changed()

    def on_color_changed(self, color_button):
        if self._block_updates or not self.current_polylines:
            return
        rgba = color_button.get_rgba()
        color = (rgba.red, rgba.green, rgba.blue)
        for pl in self.current_polylines:
            pl.color = color
        self.emit_property_changed()

    def emit_property_changed(self):
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.queue_draw()

    def set_polyline(self, polylines):
        self._block_updates = True
        if not isinstance(polylines, list):
            polylines = [polylines]
        self.current_polylines = polylines

        if not polylines:
            self._block_updates = False
            return

        first = polylines[0]

        # Line Style
        style = getattr(first, 'style', 'solid')
        if style == 'dashed':
            self.line_style_combo.set_active(1)
        else:
            self.line_style_combo.set_active(0)

        # Color
        color = getattr(first, 'color', (0.0, 0.0, 0.0))
        from gi.repository import Gdk
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = color[0], color[1], color[2], 1.0
        self.color_button.set_rgba(rgba)

        self._block_updates = False

class PropertiesDock(Gtk.Box):

    __gsignals__ = {
        'sidebar-toggled': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self, canvas):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)

        self.canvas = canvas

        # Go up one level from Dialogs to root, then into Icons
        icon_dir = os.path.join(
            os.path.dirname(
                os.path.dirname(__file__)),
            "Icons")

        # Icon bar (fixed width, icon-only buttons)
        self.icon_bar = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.icon_bar.set_margin_top(48)
        self.icon_bar.set_size_request(40, -1)
        self.icon_bar.set_vexpand(True)
        self.append(self.icon_bar)

        # Add toggle button at the top
        self.toggle_button = Gtk.Button()
        self.toggle_open_image = Gtk.Image.new_from_file(
            os.path.join(icon_dir, "right_panel_open.png"))
        self.toggle_close_image = Gtk.Image.new_from_file(
            os.path.join(icon_dir, "right_panel_close.png"))
        self.toggle_button.set_child(
            self.toggle_close_image)  # Start with close icon (panel starts closed)
        self.toggle_button.set_tooltip_text("Toggle Sidebar")
        self.toggle_button.connect('clicked', self._on_toggle_sidebar)
        self.icon_bar.append(self.toggle_button)

        # Add a separator after the toggle button
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.icon_bar.append(separator)

        # Layers Tab (Always visible)
        self.layers_btn = self._make_tab_button("layers", icon_dir, "layers")
        self.icon_bar.append(self.layers_btn)
        self.tabs = {}  # Initialize tabs dict before adding layers
        self.tabs["layers"] = self.layers_btn

        # Content stack
        self.stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
            transition_duration=200)
        # Set width of content area (total will be 300 with icon bar)
        self.stack.set_size_request(260, -1)
        self.append(self.stack)
        self.stack.set_visible(False)  # Start hidden (sidebar collapsed)

        # Track tabs (layers already added)
        # self.tabs = {}

        # Add blank/default page for when nothing is selected
        blank_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        blank_label = Gtk.Label(label="")
        blank_page.append(blank_label)
        self.stack.add_titled(blank_page, "blank", "No Selection")

        # Layers Page
        self.layers_page = LayersPanel(canvas)
        self.stack.add_titled(self.layers_page, "layers", "Layers")
        # self.layers_page = Gtk.Label(label="Layers Panel Disabled via Debug")
        # self.stack.add_titled(self.layers_page, "layers", "Layers")

        # Pre-create all pages and tabs upfront
        self.wall_page = WallPropertiesWidget()
        self.wall_page.canvas = canvas
        self.stack.add_titled(self.wall_page, "wall", "Wall Properties")

        wall_btn = self._make_tab_button("wall", icon_dir, "wall_properties")
        self.icon_bar.append(wall_btn)
        self.tabs["wall"] = wall_btn

        self.text_page = TextPropertiesWidget()
        self.text_page.canvas = canvas
        self.stack.add_titled(self.text_page, "text", "Text Properties")

        text_btn = self._make_tab_button("text", icon_dir, "add_text")
        self.icon_bar.append(text_btn)
        self.tabs["text"] = text_btn

        self.dimension_page = DimensionPropertiesWidget()
        self.dimension_page.canvas = canvas
        self.stack.add_titled(
            self.dimension_page,
            "dimension",
            "Dimension Properties")

        dimension_btn = self._make_tab_button(
            "dimension", icon_dir, "add_dimension")
        self.icon_bar.append(dimension_btn)
        self.tabs["dimension"] = dimension_btn

        self.window_page = WindowPropertiesWidget()
        self.window_page.canvas = canvas
        self.stack.add_titled(self.window_page, "window", "Window Properties")

        window_btn = self._make_tab_button("window", icon_dir, "add_windows")
        self.icon_bar.append(window_btn)
        self.tabs["window"] = window_btn

        self.door_page = DoorPropertiesWidget()
        self.door_page.canvas = canvas
        self.stack.add_titled(self.door_page, "door", "Door Properties")

        door_btn = self._make_tab_button("door", icon_dir, "add_doors")
        self.icon_bar.append(door_btn)
        self.tabs["door"] = door_btn

        self.circle_page = CirclePropertiesWidget()
        self.circle_page.canvas = canvas
        self.stack.add_titled(self.circle_page, "circle", "Circle Properties")

        circle_btn = self._make_tab_button("circle", icon_dir, "add_circle")
        self.icon_bar.append(circle_btn)
        self.tabs["circle"] = circle_btn

        self.arc_page = ArcPropertiesWidget()
        self.arc_page.canvas = canvas
        self.stack.add_titled(self.arc_page, "arc", "Arc Properties")

        arc_btn = self._make_tab_button("arc", icon_dir, "add_arc")
        self.icon_bar.append(arc_btn)
        self.tabs["arc"] = arc_btn

        self.polyline_page = PolylinePropertiesWidget()
        self.polyline_page.canvas = canvas
        self.stack.add_titled(self.polyline_page, "polyline", "Polyline Properties")

        polyline_btn = self._make_tab_button("polyline", icon_dir, "add_polyline")
        self.icon_bar.append(polyline_btn)
        self.tabs["polyline"] = polyline_btn

        self.roof_page = RoofPropertiesWidget()
        self.roof_page.canvas = canvas
        self.stack.add_titled(self.roof_page, "roof", "Roof Properties")

        roof_btn = self._make_tab_button("roof", icon_dir, "roof")
        self.icon_bar.append(roof_btn)
        self.tabs["roof"] = roof_btn

    def _make_tab_button(self, name, icon_dir, icon_name):
        btn = Gtk.ToggleButton()
        image = Gtk.Image.new_from_file(
            os.path.join(icon_dir, f"{icon_name}.png"))

        btn.set_child(image)
        btn.set_tooltip_text(name.capitalize())
        handler_id = btn.connect(
            'toggled',
            lambda b: self._on_tab_toggled(
                b,
                name))
        # Store handler ID so we can block it when setting active
        # programmatically
        btn.handler_id = handler_id
        return btn

    def refresh_tabs(self, selected_items):
        # Detect what types are selected
        wall_items = []
        text_items = []
        dimension_items = []
        window_items = []
        door_items = []
        circle_items = []
        arc_items = []
        polyline_items = []
        roof_items = []

        for item in selected_items:
            item_type = item["type"]

            if item_type == "wall":
                wall_items.append(item)
            elif item_type == "text":
                text_items.append(item)
            elif item_type == "dimension":
                dimension_items.append(item)
            elif item_type == "door":
                # Extract door object (works for both wall-attached and
                # floating)
                wall, door, ratio = item["object"]
                door_items.append(item)  # Keep the full tuple for callbacks
            elif item_type == "window":
                # Extract window object (works for both wall-attached and
                # floating)
                wall, window, ratio = item["object"]
                window_items.append(item)  # Keep the full tuple for callbacks
            elif item_type == "circle":
                circle_items.append(item)
            elif item_type == "arc":
                arc_items.append(item)
            elif item_type == "polyline":
                polyline_items.append(item)
            elif item_type == "roof":
                roof_items.append(item)

        wants_wall = len(wall_items) > 0
        wants_text = len(text_items) > 0
        wants_dimension = len(dimension_items) > 0
        wants_window = len(window_items) > 0
        wants_door = len(door_items) > 0
        wants_circle = len(circle_items) > 0
        wants_arc = len(arc_items) > 0
        wants_polyline = len(polyline_items) > 0
        wants_roof = len(roof_items) > 0

        # Enable/disable tabs based on selection
        self.tabs["wall"].set_sensitive(wants_wall)
        self.tabs["text"].set_sensitive(wants_text)
        self.tabs["dimension"].set_sensitive(wants_dimension)
        self.tabs["window"].set_sensitive(wants_window)
        self.tabs["door"].set_sensitive(wants_door)
        self.tabs["circle"].set_sensitive(wants_circle)
        self.tabs["arc"].set_sensitive(wants_arc)
        self.tabs["polyline"].set_sensitive(wants_polyline)
        self.tabs["roof"].set_sensitive(wants_roof)
        self.tabs["layers"].set_sensitive(True)  # Layers always active

        # Update content and activate appropriate tab
        selection_count = (
             (1 if wants_wall else 0) +
             (1 if wants_text else 0) +
             (1 if wants_dimension else 0) +
             (1 if wants_window else 0) +
             (1 if wants_door else 0) +
             (1 if wants_circle else 0) +
             (1 if wants_arc else 0) +
             (1 if wants_polyline else 0) +
             (1 if wants_roof else 0)
        )

        has_selection = selection_count > 0

        # Update all active content
        if wants_wall:
             selected_walls = [item["object"] for item in wall_items]
             self.wall_page.set_wall(selected_walls)

        if wants_text:
             selected_texts = [item["object"] for item in text_items]
             self.text_page.set_text(selected_texts)

        if wants_dimension:
             selected_dimensions = [item["object"] for item in dimension_items]
             self.dimension_page.set_dimension(selected_dimensions[0])

        if wants_window:
             selected_windows = [(item["object"][1], item["object"][0]) for item in window_items] # window, wall tuple?
             # Check what window_page expects. Standard is just object list or single object
             # The existing code did: selected_window = window_items[0]["object"] (which is a tuple?)
             # Let's check window_page.set_window. It likely takes the tuple (wall, window, ratio) or just window
             # Looking at previous code line 1711: wall, window, ratio = item["object"]
             # So item["object"] is the tuple.
             # existing code: self.window_page.set_window(selected_window)
             self.window_page.set_window(window_items[0]["object"])

        if wants_door:
             self.door_page.set_door(door_items[0]["object"])

        if wants_circle:
             selected_circles = [item["object"] for item in circle_items]
             self.circle_page.set_circle(selected_circles)

        if wants_arc:
             selected_arcs = [item["object"] for item in arc_items]
             self.arc_page.set_arc(selected_arcs)

        if wants_polyline:
             selected_polylines = [item["object"] for item in polyline_items]
             self.polyline_page.set_polyline(selected_polylines)

        if wants_roof:
             selected_roofs = [item["object"] for item in roof_items]
             self.roof_page.set_roof(selected_roofs)

         # Tab Switching Logic
        # Skip tab switching if selection came from layers panel
        from_layers_panel = getattr(self.canvas, '_selection_from_layers_panel', False)
        
        if has_selection:
             # Make sure dock is visible (but don't change tabs if from layers panel)
             if not self.stack.get_visible() and not from_layers_panel:
                  self.stack.set_visible(True)
                  self.toggle_button.set_child(self.toggle_open_image)
                  self.emit('sidebar-toggled', True)
             
             # Skip the rest of tab switching if from layers panel
             if from_layers_panel:
                  return
             
             # Decide which tab to show
             current_tab = self.stack.get_visible_child_name()
             
             # If current tab is still valid, keep it
             keep_current = False
             if current_tab == "wall" and wants_wall: keep_current = True
             elif current_tab == "text" and wants_text: keep_current = True
             elif current_tab == "dimension" and wants_dimension: keep_current = True
             elif current_tab == "window" and wants_window: keep_current = True
             elif current_tab == "door" and wants_door: keep_current = True
             elif current_tab == "circle" and wants_circle: keep_current = True
             elif current_tab == "arc" and wants_arc: keep_current = True
             elif current_tab == "polyline" and wants_polyline: keep_current = True
             elif current_tab == "roof" and wants_roof: keep_current = True
             
             if not keep_current:
                  # Switch to first available
                  if wants_wall: self._set_active_tab("wall"); self.stack.set_visible_child_name("wall")
                  elif wants_text: self._set_active_tab("text"); self.stack.set_visible_child_name("text")
                  elif wants_dimension: self._set_active_tab("dimension"); self.stack.set_visible_child_name("dimension")
                  elif wants_window: self._set_active_tab("window"); self.stack.set_visible_child_name("window")
                  elif wants_door: self._set_active_tab("door"); self.stack.set_visible_child_name("door")
                  elif wants_circle: self._set_active_tab("circle"); self.stack.set_visible_child_name("circle")
                  elif wants_arc: self._set_active_tab("arc"); self.stack.set_visible_child_name("arc")
                  elif wants_polyline: self._set_active_tab("polyline"); self.stack.set_visible_child_name("polyline")
                  elif wants_roof: self._set_active_tab("roof"); self.stack.set_visible_child_name("roof")
             else:
                  # Just ensure the tab button is active visually
                  if not self.tabs[current_tab].get_active():
                       self._set_active_tab(current_tab)
        else:
             # Nothing selected
             if self.stack.get_visible():
                  self.stack.set_visible(False)
                  self.toggle_button.set_child(self.toggle_close_image)
                  self.emit('sidebar-toggled', False)
                  # Unpress all tabs
                  for btn in self.tabs.values():
                       btn.set_active(False)



    def _set_active_tab(self, active_name):
        """Set the active tab while blocking signal handlers to prevent recursion."""
        for name, tab_btn in self.tabs.items():
            tab_btn.handler_block(tab_btn.handler_id)
            tab_btn.set_active(name == active_name)
            tab_btn.handler_unblock(tab_btn.handler_id)

    def _on_tab_toggled(self, button, name):
        if button.get_active():
            self.stack.set_visible_child_name(name)
            self.stack.set_visible(True)
            # Update toggle button icon when opening sidebar
            self.toggle_button.set_child(self.toggle_open_image)
            # Untoggle others using signal blocking
            for n, b in self.tabs.items():
                if n != name:
                    b.handler_block(b.handler_id)
                    b.set_active(False)
                    b.handler_unblock(b.handler_id)
        else:
            # Clicking an active tab should re-activate it (no toggle off)
            button.handler_block(button.handler_id)
            button.set_active(True)
            button.handler_unblock(button.handler_id)

    def _on_toggle_sidebar(self, button):
        """Toggle the visibility of the sidebar content."""
        is_visible = self.stack.get_visible()
        self.stack.set_visible(not is_visible)

        # Update the icon based on the new state
        if not is_visible:
            # Sidebar is now open
            self.toggle_button.set_child(self.toggle_open_image)
        else:
            # Sidebar is now closed
            self.toggle_button.set_child(self.toggle_close_image)
            # Untoggle all tab buttons when closing
            for n, b in self.tabs.items():
                b.set_active(False)

        self.emit('sidebar-toggled', not is_visible)
