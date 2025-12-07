import gi
import os
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

# Stub widgets—you can flesh these out with real controls
class WallPropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        
        # ─── Initialize state fields ───
        self.current_wall = None
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
        thickness_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        thickness_row.append(Gtk.Label(label="Thickness:"))
        self.thickness_combo = Gtk.ComboBoxText()
        self.thickness_handler_id = self.thickness_combo.connect("changed", self.on_thickness_changed)
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
        self.height_handler_id    = self.height_combo.connect("changed", self.on_height_changed)
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
        
        # ───── wire signals ─────
        self.height_combo.connect("changed",    self.on_height_changed)
        self.exterior_switch.connect("state-set", self.on_exterior_toggled)
        self.footer_check.connect("toggled",    self.on_footer_toggled)
        self.footer_left_combo.connect("changed",  self.on_footer_left_changed)
        self.footer_right_combo.connect("changed", self.on_footer_right_changed)
        self.footer_depth_combo.connect("changed", self.on_footer_depth_changed)
        self.material_combo.connect("changed",      self.on_material_changed)
        self.interior_combo.connect("changed",     self.on_interior_changed)
        self.exterior_combo.connect("changed",     self.on_ext_finish_changed)
        self.stud_combo.connect("changed",         self.on_stud_spacing_changed)
        self.insulation_combo.connect("changed",   self.on_insulation_changed)
        self.fire_combo.connect("changed",         self.on_fire_rating_changed)
    
    
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
        if self._block_updates or not self.current_wall:
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

        self.current_wall.width = value
        self.emit_property_changed()

    def on_height_changed(self, combo):
        if self._block_updates or not self.current_wall: return
        txt = combo.get_active_text()
        if txt is not None:
            txt = txt.split()[0]
        else:
            return
        if txt.lower() != "custom":
            self.current_wall.height = float(txt.split("'")[0])
        self.emit_property_changed()

    def on_exterior_toggled(self, switch, gparam):
        if self._block_updates or not self.current_wall: return
        self.current_wall.exterior_wall = switch.get_active()
        self.emit_property_changed()

    def on_footer_toggled(self, button):
        if self._block_updates or not self.current_wall: return
        self.current_wall.footer = button.get_active()
        self.emit_property_changed()
    
    def on_footer_left_changed(self, combo):
        if self._block_updates or not self.current_wall: return
        text = combo.get_active_text().strip('"')
        if text.lower() != "custom":
            self.current_wall.footer_left_offset = float(text)
        self.emit_property_changed()
    
    def on_footer_right_changed(self, combo):
        if self._block_updates or not self.current_wall: return
        text = combo.get_active_text().strip('"')
        if text.lower() != "custom":
            self.current_wall.footer_right_offset = float(text)
        self.emit_property_changed()
    
    def on_footer_depth_changed(self, combo):
        if self._block_updates or not self.current_wall: return
        text = combo.get_active_text().strip('"')
        if text.lower() != "custom":
            self.current_wall.footer_depth = float(text)
        self.emit_property_changed()
    
    def on_material_changed(self, combo):
        if self._block_updates or not self.current_wall: return
        text = combo.get_active_text()
        if text:
            self.current_wall.material = text
        self.emit_property_changed()
    
    def on_interior_changed(self, combo):
        if self._block_updates or not self.current_wall: return
        text = combo.get_active_text()
        if text:
            self.current_wall.interior_finish = text
        self.emit_property_changed()
    
    def on_ext_finish_changed(self, combo):
        if self._block_updates or not self.current_wall: return
        text = combo.get_active_text()
        if text:
            self.current_wall.exterior_finish = text
        self.emit_property_changed()
    
    def on_stud_spacing_changed(self, combo):
        if self._block_updates or not self.current_wall: return
        text = combo.get_active_text().strip('"')
        if text.lower() != "custom":
            self.current_wall.stud_spacing = float(text)
        self.emit_property_changed()
    
    def on_insulation_changed(self, combo):
        if self._block_updates or not self.current_wall: return
        text = combo.get_active_text()
        if text:
            self.current_wall.insulation_type = text
        self.emit_property_changed()
    
    def on_fire_rating_changed(self, combo):
        if self._block_updates or not self.current_wall: return
        text = combo.get_active_text()
        if text.lower() != "custom":
            # Extract the numeric part and convert to float
            rating = float(text.split()[0])
            self.current_wall.fire_rating = rating
        self.emit_property_changed()

    def emit_property_changed(self):
        """Notify the rest of the app that the model changed."""
        # you'll want to queue a redraw of the canvas:
        self.canvas.queue_draw()

    # ───── populate UI from a Wall instance ─────
    def set_wall(self, wall):
        # Block change handlers while we sync the UI to this wall
        self._block_updates = True
        self.current_wall = wall

        #
        # Thickness (wall.width is in inches, matches self.available_thicknesses)
        #
        thickness_index = 0  # fallback if no match
        for i, val in enumerate(self.available_thicknesses):
            if abs(val - float(wall.width)) < 1e-6:
                thickness_index = i
                break

        self.thickness_combo.handler_block(self.thickness_handler_id)
        self.thickness_combo.set_active(thickness_index)
        self.thickness_combo.handler_unblock(self.thickness_handler_id)

        #  Height (wall.height is in feet, matches self.available_heights)
        height_feet = float(wall.height) / 12.0 if wall.height is not None else 8.0
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
        self.exterior_switch.set_active(wall.exterior_wall)

        #
        # Footer fields
        #
        self.footer_check.set_active(wall.footer)
        self.footer_left_combo.set_active(
            self._find_combo_index(self.footer_left_combo, f'{wall.footer_left_offset:.0f}"')
        )
        self.footer_right_combo.set_active(
            self._find_combo_index(self.footer_right_combo, f'{wall.footer_right_offset:.0f}"')
        )
        self.footer_depth_combo.set_active(
            self._find_combo_index(self.footer_depth_combo, f'{wall.footer_depth:.0f}"')
        )

        #
        # Materials & finishes
        #
        self.material_combo.set_active(
            self._find_combo_index(self.material_combo, wall.material)
        )
        self.interior_combo.set_active(
            self._find_combo_index(self.interior_combo, wall.interior_finish)
        )
        self.exterior_combo.set_active(
            self._find_combo_index(self.exterior_combo, wall.exterior_finish)
        )

        #
        # Structural details
        #
        self.stud_combo.set_active(
            self._find_combo_index(self.stud_combo, f'{int(wall.stud_spacing)}"')
        )
        self.insulation_combo.set_active(
            self._find_combo_index(self.insulation_combo, wall.insulation_type)
        )
        self.fire_combo.set_active(
            self._find_combo_index(self.fire_combo, f"{int(wall.fire_rating)}")
        )

        # Done syncing, let change handlers run again
        self._block_updates = False


        


class TextPropertiesWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.current_text = None
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
        for font in ["Sans", "Serif", "Monospace", "Arial", "Times New Roman", "Courier New"]:
            self.font_combo.append_text(font)
        self.font_combo.connect("changed", self.on_font_changed)
        row.append(self.font_combo)
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
        if self._block_updates or not self.current_text: return
        self.current_text.content = entry.get_text()
        self.emit_property_changed()
        
    def on_size_changed(self, spin):
        if self._block_updates or not self.current_text: return
        self.current_text.font_size = spin.get_value()
        self.emit_property_changed()

    def on_font_changed(self, combo):
        if self._block_updates or not self.current_text: return
        self.current_text.font_family = combo.get_active_text()
        self.emit_property_changed()
    
    def on_rotation_changed(self, spin):
        if self._block_updates or not self.current_text: return
        self.current_text.rotation = spin.get_value()
        self.emit_property_changed()

    def on_style_toggled(self, check):
        if self._block_updates or not self.current_text: return
        self.current_text.bold = self.bold_check.get_active()
        self.current_text.italic = self.italic_check.get_active()
        self.current_text.underline = self.underline_check.get_active()
        self.emit_property_changed()
    
    def emit_property_changed(self):
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.queue_draw()
        
    def set_text(self, text_obj):
        self._block_updates = True
        self.current_text = text_obj
        self.content_entry.set_text(text_obj.content)
        self.size_spin.set_value(text_obj.font_size)
        
        # Font
        # Find font in combo or default to 0
        idx = 0
        model = self.font_combo.get_model()
        for i, row in enumerate(model):
            if row[0] == text_obj.font_family:
                idx = i
                break
        self.font_combo.set_active(idx)
        
        # Rotation
        self.rotation_spin.set_value(text_obj.rotation)
        
        # Styles
        self.bold_check.set_active(text_obj.bold)
        self.italic_check.set_active(text_obj.italic)
        self.underline_check.set_active(text_obj.underline)
        
        self._block_updates = False

class PropertiesDock(Gtk.Box):

    def __init__(self, canvas):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        
        self.canvas = canvas

        icon_dir = os.path.join(os.path.dirname(__file__), "Icons")
        
        # Icon bar (fixed width, icon-only buttons)
        self.icon_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.icon_bar.set_margin_top(48)
        self.icon_bar.set_size_request(40, -1)
        self.icon_bar.set_vexpand(True)
        self.append(self.icon_bar)
        
        # Add toggle button at the top
        self.toggle_button = Gtk.Button()
        self.toggle_open_image = Gtk.Image.new_from_file(os.path.join(icon_dir, "right_panel_open.png"))
        self.toggle_close_image = Gtk.Image.new_from_file(os.path.join(icon_dir, "right_panel_close.png"))
        self.toggle_button.set_child(self.toggle_close_image)  # Start with close icon
        self.toggle_button.set_tooltip_text("Toggle Sidebar")
        self.toggle_button.connect('clicked', self._on_toggle_sidebar)
        self.icon_bar.append(self.toggle_button)
        
        # Add a separator after the toggle button
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.icon_bar.append(separator)

        # Content stack
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
                               transition_duration=200)
        self.append(self.stack)
        self.stack.set_visible(False)

        # Track tabs
        self.tabs = {}

        # Add blank/default page for when nothing is selected
        blank_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        blank_label = Gtk.Label(label="")
        blank_page.append(blank_label)
        self.stack.add_titled(blank_page, "blank", "No Selection")

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

    def _make_tab_button(self, name, icon_dir, icon_name):
        btn = Gtk.ToggleButton()
        image = Gtk.Image.new_from_file(os.path.join(icon_dir, f"{icon_name}.png"))
        
        btn.set_child(image)
        btn.set_tooltip_text(name.capitalize())
        handler_id = btn.connect('toggled', lambda b: self._on_tab_toggled(b, name))
        # Store handler ID so we can block it when setting active programmatically
        btn.handler_id = handler_id
        return btn


    
    def refresh_tabs(self, selected_items):
        # Check what types of items are selected
        wall_items = [item for item in selected_items if item.get("type") == "wall"]
        text_items = [item for item in selected_items if item.get("type") == "text"]
        
        wants_wall = bool(wall_items)
        wants_text = bool(text_items)
        
        # Enable/disable tabs based on selection
        self.tabs["wall"].set_sensitive(wants_wall)
        self.tabs["text"].set_sensitive(wants_text)
        
        # Update content and activate appropriate tab
        if wants_wall:
            # Check if we're already showing the wall tab (to avoid animation)
            already_on_wall = self.stack.get_visible_child_name() == "wall"
            
            # Populate wall properties with first selected wall
            selected_wall = wall_items[0]["object"]
            self.wall_page.set_wall(selected_wall)
            
            # If not already on wall tab, switch to it with animation
            if not already_on_wall:
                self.stack.set_visible_child_name("wall")
            
            # Only set visible if not already visible (to avoid double animation)
            if not self.stack.get_visible():
                self.stack.set_visible(True)
                self.toggle_button.set_child(self.toggle_open_image)
            # Only set active tab if it's not already active
            if not self.tabs["wall"].get_active():
                self._set_active_tab("wall")
        elif wants_text:
            # Check if we're already showing the text tab (to avoid animation)
            already_on_text = self.stack.get_visible_child_name() == "text"
            
            # Populate text properties with first selected text
            selected_text = text_items[0]["object"]
            self.text_page.set_text(selected_text)
            
            # If not already on text tab, switch to it with animation
            if not already_on_text:
                self.stack.set_visible_child_name("text")
            
            # Only set visible if not already visible (to avoid double animation)
            if not self.stack.get_visible():
                self.stack.set_visible(True)
                self.toggle_button.set_child(self.toggle_open_image)
            # Only set active tab if it's not already active
            if not self.tabs["text"].get_active():
                self._set_active_tab("text")
        else:
            # Nothing selected - but don't immediately switch to blank if we're on a content tab
            # This prevents animation flicker during selection changes
            current_child = self.stack.get_visible_child_name()
            if current_child not in ["wall", "text"]:
                # Only switch to blank if we're not currently showing a content tab
                # (avoids flicker when selection is briefly cleared during click)
                self.stack.set_visible_child_name("blank")
            # Deactivate all tabs
            for name, tab_btn in self.tabs.items():
                tab_btn.handler_block(tab_btn.handler_id)
                tab_btn.set_active(False)
                tab_btn.handler_unblock(tab_btn.handler_id)

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
