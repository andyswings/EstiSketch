import gi, os
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

# Import your domain classes
from components import Wall

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
        for val in ["8'", "9'", "10'", "12'", "Custom (Coming in a future release)"]:
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
        self.thickness_combo.connect("changed", self.on_thickness_changed)
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
        if self._block_updates or not self.current_wall: return
        current_thickness = self.current_wall.width
        for i in self.available_thicknesses:
            if str(i) == current_thickness:
                text = self.available_thicknesses.index(i)
                combo.set_active(text)
                print(f"Setting thickness to {i} inches")
                break
        # Get the active text from the combo box
        text = combo.get_active_text()
        if text is not None:
            text = text.split()[0]
        else:
            return
        if text.lower() != "custom":
            self.current_wall.width = float(text.split('"')[0])
        self.current_wall.width = float(text.split('"')[0])
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
        self.current_wall = wall
        
        # Combo Strings
        width_str = f"{wall.width:g}"
        height_str = f"{wall.height:g}"
        print(f"Setting wall properties for {wall} with width {width_str} and height {height_str}")
        
        
        self.thickness_combo.handler_block(self.thickness_handler_id)
        
        # SELECT the right one by ID:
        self.thickness_combo.set_active_id(width_str)

        # unblock signals if you were blocking them
        self.thickness_combo.handler_unblock(self.thickness_handler_id)

        # Height
        self.height_combo.handler_block(self.height_handler_id)
        self.height_combo.set_active_id(height_str)
        self.height_combo.handler_unblock(self.height_handler_id)

        # Exterior
        self.exterior_switch.set_active(wall.exterior_wall)

        # Footer
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

        # Materials & finishes
        self.material_combo.set_active(
            self._find_combo_index(self.material_combo, wall.material)
        )
        self.interior_combo.set_active(
            self._find_combo_index(self.interior_combo, wall.interior_finish)
        )
        self.exterior_combo.set_active(
            self._find_combo_index(self.exterior_combo, wall.exterior_finish)
        )

        # Structural details
        self.stud_combo.set_active(
            self._find_combo_index(self.stud_combo, f'{int(wall.stud_spacing)}"')
        )
        self.insulation_combo.set_active(
            self._find_combo_index(self.insulation_combo, wall.insulation_type)
        )
        self.fire_combo.set_active(
            self._find_combo_index(self.fire_combo, f"{int(wall.fire_rating)}")
        )

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

        # Content stack
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
                               transition_duration=200)
        self.append(self.stack)
        self.stack.set_visible(False)

        # Track added tabs
        self.tabs = {}

        # Pre-create pages
        self.wall_page = WallPropertiesWidget()
        self.wall_page.canvas = canvas
        self.stack.add_titled(self.wall_page, "wall", "Wall Properties")
        
        wall_btn = self._make_tab_button("wall", icon_dir, "wall_properties") 
        self.icon_bar.append(wall_btn)  
        self.tabs["wall"] = wall_btn  

    def _make_tab_button(self, name, icon_dir, icon_name):
        btn = Gtk.ToggleButton()
        print(icon_name)
        image = Gtk.Image.new_from_file(os.path.join(icon_dir, f"{icon_name}.png"))
        
        btn.set_child(image)
        btn.set_tooltip_text(name.capitalize())
        btn.connect('toggled', lambda b: self._on_tab_toggled(b, name))
        return btn

    def _ensure_tab(self, name, should_show, icon_name, icon_dir=os.path.join(os.path.dirname(__file__), "Icons")):
        if should_show and name not in self.tabs:
            btn = self._make_tab_button(name, icon_dir, icon_name)
            self.icon_bar.append(btn)
            self.tabs[name] = btn
        elif not should_show and name in self.tabs:
            btn = self.tabs.pop(name)
            self.icon_bar.remove(btn)
    
    def refresh_tabs(self, selected_items):
        # 1) Do we have at least one wall selected?
        wall_items = [item for item in selected_items if item.get("type") == "wall"]
        wants_wall = bool(wall_items)

        # 2) Show or hide the wall tab icon
        self._ensure_tab("wall", wants_wall, "wall_properties")

        if wants_wall:
            # Take the first selected wall and populate the UI
            selected_wall = wall_items[0]["object"]
            print(f"{selected_wall} Should be shown in properties dock")
            self.wall_page.set_wall(selected_wall)
            # # Also auto-open the tab (so the user sees it immediately)
            # self.tabs["wall"].set_active(True)
        else:
            # Optionally, hide the stack if there’s nothing to show
            self.stack.set_visible(False)

        # 3) (rest of your foundation-tab logic …)
        wants_foundation = any(
            item.get("type") == "wall" and getattr(item["object"], "footer", False)
            for item in selected_items
        )

        # 4) If the currently visible child is no longer valid, hide the stack
        current = self.stack.get_visible_child_name()
        valid   = {"wall": wants_wall, "foundation": wants_foundation}
        if current and not valid.get(current, False):
            self.stack.set_visible(False)

    def _on_tab_toggled(self, button, name):
        if button.get_active():
            self.stack.set_visible_child_name(name)
            self.stack.set_visible(True)
            # untoggle others
            for n, b in self.tabs.items():
                if n != name:
                    b.set_active(False)
        else:
            # clicking active icon hides panel
            self.stack.set_visible(False)
