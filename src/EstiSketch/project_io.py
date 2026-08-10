import xml.etree.ElementTree as ET
from .components import Wall, Room, Door, Window, Text, Dimension, Layer, Level, Polyline, Circle, Arc, Stair
from .roof_components import Roof, RoofEdge


def save_project(canvas, window_width, window_height, filepath):
    """ Save the entire project state to an XML file.

    Parameters:
    canvas: The CanvasArea instance holding project elements.
    window_width: The current width of the project window.
    window_height: The current height of the project window.
    filepath: The destination filepath to write the XML.

    The XML structure will include wall sets, rooms, doors, windows,
    and the window size. Additionally, each Door and Window saves a reference
    to the wall (set index and wall index) it is attached to.
    """
    # Create the XML root with window dimensions.
    root = ET.Element(
        "Project",
        window_width=str(window_width),
        window_height=str(window_height))

    # Save Levels
    levels_elem = ET.SubElement(root, "Levels")
    for level in getattr(canvas, 'levels', []):
        level_elem = ET.SubElement(levels_elem, "Level")
        level_elem.set("id", level.id)
        level_elem.set("name", level.name)
        level_elem.set("elevation", str(level.elevation))
        level_elem.set("height", str(level.height))

    # Save active level ID
    active_level_id = getattr(canvas, 'active_level_id', '')
    root.set("active_level_id", active_level_id)

    # Save layers
    layers_elem = ET.SubElement(root, "Layers")
    for layer in getattr(canvas, 'layers', []):
        layer_elem = ET.SubElement(layers_elem, "Layer")
        layer_elem.set("id", layer.id)
        layer_elem.set("name", layer.name)
        layer_elem.set("visible", str(layer.visible))
        layer_elem.set("locked", str(layer.locked))
        layer_elem.set("opacity", str(layer.opacity))
        layer_elem.set("level_id", getattr(layer, "level_id", ""))

    # Save active layer ID
    active_layer_id = getattr(canvas, 'active_layer_id', '')
    root.set("active_layer_id", active_layer_id)

    # Save wall sets (each wall in a wall set includes all construction
    # details)
    walls_elem = ET.SubElement(root, "WallSets")
    # Build a mapping of wall objects to their wall set index and index within
    # that set.
    wall_mapping = {}
    for set_index, wall_set in enumerate(canvas.wall_sets):
        ws_elem = ET.SubElement(walls_elem, "WallSet")
        for wall_index, wall in enumerate(wall_set):
            wall_mapping[id(wall)] = (set_index, wall_index)
            wall_elem = ET.SubElement(ws_elem, "Wall")
            # Save coordinates and dimensions.
            ET.SubElement(
                wall_elem, "Start", x=str(
                    wall.start[0]), y=str(
                    wall.start[1]))
            ET.SubElement(
                wall_elem, "End", x=str(
                    wall.end[0]), y=str(
                    wall.end[1]))
            ET.SubElement(wall_elem, "Width").text = str(wall.width)
            ET.SubElement(wall_elem, "Height").text = str(wall.height)
            ET.SubElement(wall_elem, "HeightAtEnd").text = str(getattr(wall, 'height_at_end', wall.height))
            ET.SubElement(
                wall_elem,
                "ExteriorWall").text = str(
                wall.exterior_wall)
            ET.SubElement(
                wall_elem,
                "LayerId").text = getattr(
                wall,
                'layer_id',
                '')
            # Save additional construction properties.
            ET.SubElement(wall_elem, "Material").text = wall.material
            ET.SubElement(
                wall_elem,
                "InteriorFinish").text = wall.interior_finish
            ET.SubElement(
                wall_elem,
                "ExteriorFinish").text = wall.exterior_finish
            ET.SubElement(
                wall_elem,
                "StudSpacing").text = str(
                wall.stud_spacing)
            ET.SubElement(
                wall_elem,
                "InsulationType").text = wall.insulation_type
            ET.SubElement(wall_elem, "FireRating").text = wall.fire_rating

            # Save footer properties
            ET.SubElement(wall_elem, "Footer").text = str(wall.footer)
            ET.SubElement(wall_elem, "FooterLeftOffset").text = str(wall.footer_left_offset)
            ET.SubElement(wall_elem, "FooterRightOffset").text = str(wall.footer_right_offset)
            ET.SubElement(wall_elem, "FooterDepth").text = str(wall.footer_depth)
            ET.SubElement(wall_elem, "Symbolic").text = str(getattr(wall, 'symbolic', False))

    # Save rooms along with their vertex points and other properties.
    rooms_elem = ET.SubElement(root, "Rooms")
    for room in canvas.rooms:
        room_elem = ET.SubElement(rooms_elem, "Room")
        points_elem = ET.SubElement(room_elem, "Points")
        for pt in room.points:
            ET.SubElement(points_elem, "Point", x=str(pt[0]), y=str(pt[1]))
        ET.SubElement(room_elem, "Height").text = str(room.height)
        ET.SubElement(room_elem, "FloorType").text = room.floor_type
        ET.SubElement(room_elem, "WallFinish").text = room.wall_finish
        ET.SubElement(room_elem, "RoomType").text = room.room_type
        ET.SubElement(room_elem, "Name").text = room.name
        ET.SubElement(
            room_elem,
            "LayerId").text = getattr(
            room,
            'layer_id',
            '')

        # Save slab properties
        ET.SubElement(room_elem, "IsSlab").text = str(getattr(room, 'is_slab', False))
        ET.SubElement(room_elem, "SlabThickness").text = str(getattr(room, 'slab_thickness', 4.0))
        ET.SubElement(room_elem, "SlabReinforcement").text = getattr(room, 'slab_reinforcement', 'wire_mesh')
        ET.SubElement(room_elem, "SlabEdgeType").text = getattr(room, 'slab_edge_type', 'thickened')

    # Save doors. In addition to their properties and attachment ratio, also
    # save a wall reference.
    doors_elem = ET.SubElement(root, "Doors")
    for attached_wall, door, ratio in canvas.doors:
        door_elem = ET.SubElement(doors_elem, "Door")
        ET.SubElement(door_elem, "DoorType").text = door.door_type
        ET.SubElement(door_elem, "Width").text = str(door.width)
        ET.SubElement(door_elem, "Height").text = str(door.height)
        ET.SubElement(door_elem, "Swing").text = door.swing
        ET.SubElement(door_elem, "Orientation").text = door.orientation
        ET.SubElement(door_elem, "AttachedToWallRatio").text = str(ratio)
        ET.SubElement(
            door_elem,
            "LayerId").text = getattr(
            door,
            'layer_id',
            '')
        # Save the wall reference.
        wall_ref_elem = ET.SubElement(door_elem, "WallReference")
        if attached_wall is not None:
            ref = wall_mapping.get(id(attached_wall))
            if ref:
                wall_ref_elem.set("set_index", str(ref[0]))
                wall_ref_elem.set("wall_index", str(ref[1]))
            else:
                wall_ref_elem.set("set_index", "-1")
                wall_ref_elem.set("wall_index", "-1")
        else:
            wall_ref_elem.set("set_index", "-1")
            wall_ref_elem.set("wall_index", "-1")

    # Save windows in a similar fashion.
    windows_elem = ET.SubElement(root, "Windows")
    for attached_wall, window_obj, ratio in canvas.windows:
        win_elem = ET.SubElement(windows_elem, "Window")
        ET.SubElement(win_elem, "Width").text = str(window_obj.width)
        ET.SubElement(win_elem, "Height").text = str(window_obj.height)
        ET.SubElement(win_elem, "WindowType").text = window_obj.window_type
        ET.SubElement(win_elem, "AttachedToWallRatio").text = str(ratio)
        ET.SubElement(
            win_elem,
            "LayerId").text = getattr(
            window_obj,
            'layer_id',
            '')
        # Save the wall reference.
        wall_ref_elem = ET.SubElement(win_elem, "WallReference")
        if attached_wall is not None:
            ref = wall_mapping.get(id(attached_wall))
            if ref:
                wall_ref_elem.set("set_index", str(ref[0]))
                wall_ref_elem.set("wall_index", str(ref[1]))
            else:
                wall_ref_elem.set("set_index", "-1")
                wall_ref_elem.set("wall_index", "-1")
        else:
            wall_ref_elem.set("set_index", "-1")
            wall_ref_elem.set("wall_index", "-1")

    # Save texts
    texts_elem = ET.SubElement(root, "Texts")
    for text in canvas.texts:
        t_elem = ET.SubElement(texts_elem, "Text")
        t_elem.set("x", str(text.x))
        t_elem.set("y", str(text.y))
        t_elem.set("width", str(text.width))
        t_elem.set("height", str(text.height))
        t_elem.set("content", text.content)
        t_elem.set("font_size", str(text.font_size))
        t_elem.set("font_family", text.font_family)
        t_elem.set("bold", str(text.bold))
        t_elem.set("italic", str(text.italic))
        t_elem.set("underline", str(text.underline))
        t_elem.set("identifier", text.identifier)
        t_elem.set("layer_id", getattr(text, 'layer_id', ''))

    # Save dimensions
    dimensions_elem = ET.SubElement(root, "Dimensions")
    for dimension in canvas.dimensions:
        d_elem = ET.SubElement(dimensions_elem, "Dimension")
        d_elem.set("start_x", str(dimension.start[0]))
        d_elem.set("start_y", str(dimension.start[1]))
        d_elem.set("end_x", str(dimension.end[0]))
        d_elem.set("end_y", str(dimension.end[1]))
        d_elem.set("offset", str(dimension.offset))
        d_elem.set("identifier", dimension.identifier)
        d_elem.set("layer_id", getattr(dimension, 'layer_id', ''))
        d_elem.set("text_size", str(dimension.text_size))
        d_elem.set("show_arrows", str(dimension.show_arrows))
        d_elem.set("line_style", dimension.line_style)
        color = getattr(dimension, 'color', (0.0, 0.0, 0.0))
        d_elem.set("color_r", str(color[0]))
        d_elem.set("color_g", str(color[1]))
        d_elem.set("color_b", str(color[2]))


    # Save Polylines
    # Canvas stores polylines as list-of-lists (sets of connected segments)
    # We will flatten this for XML or keep structure? Keeping structure is better
    # Structure: <PolylineSets><PolylineSet><Polyline .../><Polyline .../></PolylineSet></PolylineSets>
    polyline_sets_elem = ET.SubElement(root, "PolylineSets")
    for poly_set in canvas.polyline_sets:
        set_elem = ET.SubElement(polyline_sets_elem, "PolylineSet")
        for pl in poly_set:
            pl_elem = ET.SubElement(set_elem, "Polyline")
            pl_elem.set("start_x", str(pl.start[0]))
            pl_elem.set("start_y", str(pl.start[1]))
            pl_elem.set("end_x", str(pl.end[0]))
            pl_elem.set("end_y", str(pl.end[1]))
            pl_elem.set("identifier", pl.identifier)
            pl_elem.set("layer_id", getattr(pl, 'layer_id', ''))
            pl_elem.set("style", pl.style)
            color = getattr(pl, 'color', (0.0, 0.0, 0.0))
            pl_elem.set("color_r", str(color[0]))
            pl_elem.set("color_g", str(color[1]))
            pl_elem.set("color_b", str(color[2]))

    # Save Circles
    circles_elem = ET.SubElement(root, "Circles")
    for circle in getattr(canvas, 'circles', []):
        c_elem = ET.SubElement(circles_elem, "Circle")
        c_elem.set("center_x", str(circle.center[0]))
        c_elem.set("center_y", str(circle.center[1]))
        c_elem.set("radius", str(circle.radius))
        c_elem.set("identifier", circle.identifier)
        c_elem.set("layer_id", getattr(circle, 'layer_id', ''))
        c_elem.set("line_style", getattr(circle, 'line_style', 'solid'))
        color = getattr(circle, 'color', (0.0, 0.0, 0.0))
        c_elem.set("color_r", str(color[0]))
        c_elem.set("color_g", str(color[1]))
        c_elem.set("color_b", str(color[2]))

    # Save Arcs
    arcs_elem = ET.SubElement(root, "Arcs")
    for arc in getattr(canvas, 'arcs', []):
        a_elem = ET.SubElement(arcs_elem, "Arc")
        a_elem.set("center_x", str(arc.center[0]))
        a_elem.set("center_y", str(arc.center[1]))
        a_elem.set("radius", str(arc.radius))
        a_elem.set("start_angle", str(arc.start_angle))
        a_elem.set("end_angle", str(arc.end_angle))
        a_elem.set("identifier", arc.identifier)
        a_elem.set("layer_id", getattr(arc, 'layer_id', ''))
        a_elem.set("line_style", getattr(arc, 'line_style', 'solid'))
        color = getattr(arc, 'color', (0.0, 0.0, 0.0))
        a_elem.set("color_r", str(color[0]))
        a_elem.set("color_g", str(color[1]))
        a_elem.set("color_b", str(color[2]))

    # Save Roofs
    roofs_elem = ET.SubElement(root, "Roofs")
    for roof in getattr(canvas, 'roofs', []):
        r_elem = ET.SubElement(roofs_elem, "Roof")
        r_elem.set("identifier", roof.identifier)
        r_elem.set("layer_id", getattr(roof, 'layer_id', ''))
        r_elem.set("roof_type", roof.roof_type)
        r_elem.set("pitch_rise", str(roof.pitch_rise))
        r_elem.set("pitch_run", str(roof.pitch_run))
        r_elem.set("overhang", str(roof.overhang))
        r_elem.set("material", roof.material)
        
        # Save edges
        edges_elem = ET.SubElement(r_elem, "Edges")
        for edge in roof.edges:
            e_elem = ET.SubElement(edges_elem, "Edge")
            e_elem.set("wall_identifier", edge.wall_identifier)
            e_elem.set("edge_type", edge.edge_type)
        
        # Save calculated geometry (for faster loading, can be recalculated)
        ridge_elem = ET.SubElement(r_elem, "RidgeLines")
        for (p1, p2) in roof.ridge_lines:
            line_elem = ET.SubElement(ridge_elem, "Line")
            line_elem.set("x1", str(p1[0]))
            line_elem.set("y1", str(p1[1]))
            line_elem.set("x2", str(p2[0]))
            line_elem.set("y2", str(p2[1]))
        
        hip_elem = ET.SubElement(r_elem, "HipLines")
        for (p1, p2) in roof.hip_lines:
            line_elem = ET.SubElement(hip_elem, "Line")
            line_elem.set("x1", str(p1[0]))
            line_elem.set("y1", str(p1[1]))
            line_elem.set("x2", str(p2[0]))
            line_elem.set("y2", str(p2[1]))
        
        valley_elem = ET.SubElement(r_elem, "ValleyLines")
        for (p1, p2) in roof.valley_lines:
            line_elem = ET.SubElement(valley_elem, "Line")
            line_elem.set("x1", str(p1[0]))
            line_elem.set("y1", str(p1[1]))
            line_elem.set("x2", str(p2[0]))
            line_elem.set("y2", str(p2[1]))
        
        outline_elem = ET.SubElement(r_elem, "Outline")
        for pt in roof.outline_points:
            pt_elem = ET.SubElement(outline_elem, "Point")
            pt_elem = ET.SubElement(outline_elem, "Point")
            pt_elem.set("x", str(pt[0]))
            pt_elem.set("y", str(pt[1]))

    # Save Stairs
    stairs_elem = ET.SubElement(root, "Stairs")
    for stair in getattr(canvas, 'stairs', []):
        s_elem = ET.SubElement(stairs_elem, "Stair")
        s_elem.set("identifier", stair.identifier)
        s_elem.set("layer_id", getattr(stair, 'layer_id', ''))
        
        # Placement
        s_elem.set("start_x", str(stair.start_point[0]))
        s_elem.set("start_y", str(stair.start_point[1]))
        s_elem.set("direction_angle", str(stair.direction_angle))
        
        # Level IDs
        s_elem.set("start_level_id", str(stair.start_level_id))
        s_elem.set("end_level_id", str(stair.end_level_id))
        
        # Type & Dimensions
        s_elem.set("stair_type", stair.stair_type)
        s_elem.set("width", str(stair.width))
        s_elem.set("total_rise", str(stair.total_rise))
        s_elem.set("riser_height", str(stair.riser_height))
        s_elem.set("num_steps", str(stair.num_steps))
        s_elem.set("tread_depth", str(stair.tread_depth))
        s_elem.set("total_run", str(stair.total_run))
        s_elem.set("nosing", str(stair.nosing))
        
        # Railings
        s_elem.set("has_left_rail", str(stair.has_left_rail))
        s_elem.set("has_right_rail", str(stair.has_right_rail))
        s_elem.set("rail_height", str(stair.rail_height))
        
        # Visual
        s_elem.set("show_up_arrow", str(stair.show_up_arrow))
        s_elem.set("show_step_count", str(stair.show_step_count))

    # Write out the XML to the given file (with declaration and proper
    # encoding).
    tree = ET.ElementTree(root)
    tree.write(filepath, encoding="utf-8", xml_declaration=True)


def _get_elem_text(parent, tag, default=""):
    elem = parent.find(tag)
    if elem is not None and elem.text is not None:
        return elem.text
    return default


def _get_elem_float(parent, tag, default=0.0):
    val = _get_elem_text(parent, tag, None)
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    return default


def _get_elem_int(parent, tag, default=0):
    val = _get_elem_text(parent, tag, None)
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return default


def _get_elem_bool(parent, tag, default=False):
    val = _get_elem_text(parent, tag, None)
    if val is not None:
        return val.lower() == "true"
    return default


def _get_attr_text(elem, attr, default=""):
    val = elem.get(attr)
    return val if val is not None else default


def _get_attr_int(elem, attr, default=0):
    val = elem.get(attr)
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return default


def _get_attr_float(elem, attr, default=0.0):
    val = elem.get(attr)
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    return default


def open_project(canvas, filepath):
    """ Load a project from an XML file and update the canvas state.

    Parameters:
    canvas: The CanvasArea instance where project elements will be restored.
    filepath: The file path of the XML project file.

    Returns:
    A tuple (window_width, window_height) as specified in the file.

    This function reverses the save_project process by restoring wall sets, rooms,
    doors, and windows. When restoring doors and windows, the attached wall is reattached
    using the saved wall reference (set_index and wall_index).
    """
    # Parse the XML file.
    tree = ET.parse(filepath)
    root = tree.getroot()

    # Retrieve window dimensions (with fallback defaults if missing or invalid).
    window_width = _get_attr_int(root, "window_width", 800)
    window_height = _get_attr_int(root, "window_height", 600)

    # Clear the current canvas state.
    canvas.wall_sets.clear()
    canvas.rooms.clear()
    canvas.doors.clear()
    canvas.windows.clear()
    canvas.texts.clear()
    canvas.dimensions.clear()
    if hasattr(canvas, 'layers'):
        canvas.layers.clear()
    if hasattr(canvas, 'levels'):
        canvas.levels.clear()

    # --- Restore Levels ---
    levels_elem = root.find("Levels")
    if levels_elem is not None:
        for level_elem in levels_elem.findall("Level"):
            level = Level(
                id=_get_attr_text(level_elem, "id", ""),
                name=_get_attr_text(level_elem, "name", "Level"),
                elevation=_get_attr_float(level_elem, "elevation", 0.0),
                height=_get_attr_float(level_elem, "height", 96.0)
            )
            if hasattr(canvas, 'levels'):
                canvas.levels.append(level)

    # Default level if none found
    if hasattr(canvas, 'levels') and not canvas.levels:
        canvas.levels.append(Level(id="level-1", name="Level 1"))

    # Restore active level ID
    active_level_id = _get_attr_text(root, "active_level_id", "")
    if hasattr(canvas, 'active_level_id'):
        if active_level_id:
            canvas.active_level_id = active_level_id
        elif canvas.levels:
            canvas.active_level_id = canvas.levels[0].id

    # --- Restore Layers ---
    layers_elem = root.find("Layers")
    if layers_elem is not None:
        for layer_elem in layers_elem.findall("Layer"):
            # Handle legacy files: assign to active level (first one) if level_id missing
            legacy_level_id = canvas.levels[0].id if (hasattr(canvas, 'levels') and canvas.levels) else ""

            layer = Layer(
                id=_get_attr_text(layer_elem, "id", ""),
                name=_get_attr_text(layer_elem, "name", "Layer"),
                visible=_get_attr_text(layer_elem, "visible", "True") == "True",
                locked=_get_attr_text(layer_elem, "locked", "False") == "True",
                opacity=_get_attr_float(layer_elem, "opacity", 1.0),
                level_id=_get_attr_text(layer_elem, "level_id", legacy_level_id)
            )
            if hasattr(canvas, 'layers'):
                canvas.layers.append(layer)

    # Restore active layer ID
    active_layer_id = _get_attr_text(root, "active_layer_id", "")
    if hasattr(canvas, 'active_layer_id'):
        canvas.active_layer_id = active_layer_id

    # --- Restore Wall Sets ---
    walls_elem = root.find("WallSets")
    if walls_elem is not None:
        for ws_elem in walls_elem.findall("WallSet"):
            wall_set = []
            for wall_elem in ws_elem.findall("Wall"):
                # Get start and end coordinates.
                start_elem = wall_elem.find("Start")
                end_elem = wall_elem.find("End")
                if start_elem is None or end_elem is None:
                    continue
                start = (
                    _get_attr_float(start_elem, "x", 0.0),
                    _get_attr_float(start_elem, "y", 0.0)
                )
                end = (
                    _get_attr_float(end_elem, "x", 0.0),
                    _get_attr_float(end_elem, "y", 0.0)
                )
                width = _get_elem_float(wall_elem, "Width", 4.5)
                height = _get_elem_float(wall_elem, "Height", 96.0)
                height_at_end = _get_elem_float(wall_elem, "HeightAtEnd", height)
                exterior_wall = _get_elem_bool(wall_elem, "ExteriorWall", False)

                # Create a new Wall instance.
                wall = Wall(start, end, width, height, exterior_wall, height_at_end=height_at_end)
                wall.layer_id = _get_elem_text(wall_elem, "LayerId", "")
                wall.material = _get_elem_text(wall_elem, "Material", "2x4 Wood Stud")
                wall.interior_finish = _get_elem_text(wall_elem, "InteriorFinish", "1/2\" Drywall")
                wall.exterior_finish = _get_elem_text(wall_elem, "ExteriorFinish", "Vinyl Siding")
                wall.stud_spacing = _get_elem_int(wall_elem, "StudSpacing", 16)
                wall.insulation_type = _get_elem_text(wall_elem, "InsulationType", "Fiberglass Batt")
                wall.fire_rating = _get_elem_text(wall_elem, "FireRating", "None")

                # Restore footer properties (with defaults for legacy files)
                wall.footer = _get_elem_bool(wall_elem, "Footer", False)
                wall.footer_left_offset = _get_elem_float(wall_elem, "FooterLeftOffset", 6.0)
                wall.footer_right_offset = _get_elem_float(wall_elem, "FooterRightOffset", 6.0)
                wall.footer_depth = _get_elem_float(wall_elem, "FooterDepth", 8.0)
                wall.symbolic = _get_elem_bool(wall_elem, "Symbolic", False)

                wall_set.append(wall)
            canvas.wall_sets.append(wall_set)

    # --- Restore Rooms ---
    rooms_elem = root.find("Rooms")
    if rooms_elem is not None:
        for room_elem in rooms_elem.findall("Room"):
            points = []
            points_elem = room_elem.find("Points")
            if points_elem is not None:
                for pt_elem in points_elem.findall("Point"):
                    x = _get_attr_float(pt_elem, "x", 0.0)
                    y = _get_attr_float(pt_elem, "y", 0.0)
                    points.append((x, y))
            height = _get_elem_float(room_elem, "Height", 96.0)
            room = Room(points, height)
            room.floor_type = _get_elem_text(room_elem, "FloorType", "Hardwood")
            room.wall_finish = _get_elem_text(room_elem, "WallFinish", "Paint")
            room.room_type = _get_elem_text(room_elem, "RoomType", "Living Room")
            room.name = _get_elem_text(room_elem, "Name", "Room")
            room.layer_id = _get_elem_text(room_elem, "LayerId", "")

            # Restore slab properties (with defaults for legacy files)
            room.is_slab = _get_elem_bool(room_elem, "IsSlab", False)
            room.slab_thickness = _get_elem_float(room_elem, "SlabThickness", 4.0)
            room.slab_reinforcement = _get_elem_text(room_elem, "SlabReinforcement", "wire_mesh")
            room.slab_edge_type = _get_elem_text(room_elem, "SlabEdgeType", "thickened")

            canvas.rooms.append(room)

    # --- Restore Doors ---
    doors_elem = root.find("Doors")
    if doors_elem is not None:
        for door_elem in doors_elem.findall("Door"):
            door_type = _get_elem_text(door_elem, "DoorType", "single")
            width = _get_elem_float(door_elem, "Width", 36.0)
            height = _get_elem_float(door_elem, "Height", 80.0)
            swing = _get_elem_text(door_elem, "Swing", "left")
            orientation = _get_elem_text(door_elem, "Orientation", "inswing")
            ratio = _get_elem_float(door_elem, "AttachedToWallRatio", 0.5)

            door = Door(door_type, width, height, swing, orientation)
            door.layer_id = _get_elem_text(door_elem, "LayerId", "")
            attached_wall = None
            wall_ref_elem = door_elem.find("WallReference")
            if wall_ref_elem is not None:
                set_index = _get_attr_int(wall_ref_elem, "set_index", -1)
                wall_index = _get_attr_int(wall_ref_elem, "wall_index", -1)
                if set_index >= 0 and wall_index >= 0 and set_index < len(
                        canvas.wall_sets):
                    wall_set = canvas.wall_sets[set_index]
                    if wall_index < len(wall_set):
                        attached_wall = wall_set[wall_index]
            canvas.doors.append((attached_wall, door, ratio))

    # --- Restore Windows ---
    windows_elem = root.find("Windows")
    if windows_elem is not None:
        for win_elem in windows_elem.findall("Window"):
            win_width = _get_elem_float(win_elem, "Width", 36.0)
            win_height = _get_elem_float(win_elem, "Height", 48.0)
            window_type = _get_elem_text(win_elem, "WindowType", "sliding")
            ratio = _get_elem_float(win_elem, "AttachedToWallRatio", 0.5)

            window_obj = Window(win_width, win_height, window_type)
            window_obj.layer_id = _get_elem_text(win_elem, "LayerId", "")
            attached_wall = None
            wall_ref_elem = win_elem.find("WallReference")
            if wall_ref_elem is not None:
                set_index = _get_attr_int(wall_ref_elem, "set_index", -1)
                wall_index = _get_attr_int(wall_ref_elem, "wall_index", -1)
                if set_index >= 0 and wall_index >= 0 and set_index < len(
                        canvas.wall_sets):
                    wall_set = canvas.wall_sets[set_index]
                    if wall_index < len(wall_set):
                        attached_wall = wall_set[wall_index]
            canvas.windows.append((attached_wall, window_obj, ratio))

    # --- Restore Texts ---
    texts_elem = root.find("Texts")
    if texts_elem is not None:
        for t_elem in texts_elem.findall("Text"):
            x = _get_attr_float(t_elem, "x", 0.0)
            y = _get_attr_float(t_elem, "y", 0.0)
            width = _get_attr_float(t_elem, "width", 100.0)
            height = _get_attr_float(t_elem, "height", 30.0)
            content = _get_attr_text(t_elem, "content", "Text")
            identifier = _get_attr_text(t_elem, "identifier", "")

            text_obj = Text(x, y, content, width, height, identifier)
            text_obj.font_size = _get_attr_float(t_elem, "font_size", 12.0)
            text_obj.font_family = _get_attr_text(t_elem, "font_family", "Sans")
            text_obj.bold = _get_attr_text(t_elem, "bold", "False") == "True"
            text_obj.italic = _get_attr_text(t_elem, "italic", "False") == "True"
            text_obj.underline = _get_attr_text(t_elem, "underline", "False") == "True"
            text_obj.layer_id = _get_attr_text(t_elem, "layer_id", "")

            canvas.texts.append(text_obj)

    # --- Restore Dimensions ---
    dimensions_elem = root.find("Dimensions")
    if dimensions_elem is not None:
        for d_elem in dimensions_elem.findall("Dimension"):
            start_x = _get_attr_float(d_elem, "start_x", 0.0)
            start_y = _get_attr_float(d_elem, "start_y", 0.0)
            end_x = _get_attr_float(d_elem, "end_x", 0.0)
            end_y = _get_attr_float(d_elem, "end_y", 0.0)
            offset = _get_attr_float(d_elem, "offset", 0.0)
            identifier = _get_attr_text(d_elem, "identifier", "")

            dimension_obj = Dimension(
                start=(start_x, start_y),
                end=(end_x, end_y),
                offset=offset,
                identifier=identifier
            )
            dimension_obj.text_size = _get_attr_float(d_elem, "text_size", 12.0)
            dimension_obj.show_arrows = _get_attr_text(d_elem, "show_arrows", "True") == "True"
            dimension_obj.line_style = _get_attr_text(d_elem, "line_style", "solid")
            color_r = _get_attr_float(d_elem, "color_r", 0.0)
            color_g = _get_attr_float(d_elem, "color_g", 0.0)
            color_b = _get_attr_float(d_elem, "color_b", 0.0)
            dimension_obj.color = (color_r, color_g, color_b)
            dimension_obj.layer_id = _get_attr_text(d_elem, "layer_id", "")

            canvas.dimensions.append(dimension_obj)

    # --- Restore Polylines ---
    if hasattr(canvas, 'polyline_sets'):
        canvas.polyline_sets.clear()
        polyline_sets_elem = root.find("PolylineSets")
        if polyline_sets_elem is not None:
            for set_elem in polyline_sets_elem.findall("PolylineSet"):
                poly_set = []
                for pl_elem in set_elem.findall("Polyline"):
                    start = (_get_attr_float(pl_elem, "start_x", 0.0), _get_attr_float(pl_elem, "start_y", 0.0))
                    end = (_get_attr_float(pl_elem, "end_x", 0.0), _get_attr_float(pl_elem, "end_y", 0.0))
                    identifier = _get_attr_text(pl_elem, "identifier", "")

                    pl = Polyline(start, end, identifier)
                    pl.layer_id = _get_attr_text(pl_elem, "layer_id", "")
                    pl.style = _get_attr_text(pl_elem, "style", "solid")

                    color_r = _get_attr_float(pl_elem, "color_r", 0.0)
                    color_g = _get_attr_float(pl_elem, "color_g", 0.0)
                    color_b = _get_attr_float(pl_elem, "color_b", 0.0)
                    pl.color = (color_r, color_g, color_b)

                    poly_set.append(pl)
                canvas.polyline_sets.append(poly_set)

    # --- Restore Circles ---
    if hasattr(canvas, 'circles'):
        canvas.circles.clear()
        circles_elem = root.find("Circles")
        if circles_elem is not None:
            for c_elem in circles_elem.findall("Circle"):
                center = (_get_attr_float(c_elem, "center_x", 0.0), _get_attr_float(c_elem, "center_y", 0.0))
                radius = _get_attr_float(c_elem, "radius", 0.0)
                identifier = _get_attr_text(c_elem, "identifier", "")

                c = Circle(center, radius, identifier)
                c.layer_id = _get_attr_text(c_elem, "layer_id", "")
                c.line_style = _get_attr_text(c_elem, "line_style", "solid")

                color_r = _get_attr_float(c_elem, "color_r", 0.0)
                color_g = _get_attr_float(c_elem, "color_g", 0.0)
                color_b = _get_attr_float(c_elem, "color_b", 0.0)
                c.color = (color_r, color_g, color_b)

                canvas.circles.append(c)

    # --- Restore Arcs ---
    if hasattr(canvas, 'arcs'):
        canvas.arcs.clear()
        arcs_elem = root.find("Arcs")
        if arcs_elem is not None:
            for a_elem in arcs_elem.findall("Arc"):
                center = (_get_attr_float(a_elem, "center_x", 0.0), _get_attr_float(a_elem, "center_y", 0.0))
                radius = _get_attr_float(a_elem, "radius", 0.0)
                start_angle = _get_attr_float(a_elem, "start_angle", 0.0)
                end_angle = _get_attr_float(a_elem, "end_angle", 0.0)
                identifier = _get_attr_text(a_elem, "identifier", "")

                a = Arc(center, radius, start_angle, end_angle, identifier)
                a.layer_id = _get_attr_text(a_elem, "layer_id", "")
                a.line_style = _get_attr_text(a_elem, "line_style", "solid")

                color_r = _get_attr_float(a_elem, "color_r", 0.0)
                color_g = _get_attr_float(a_elem, "color_g", 0.0)
                color_b = _get_attr_float(a_elem, "color_b", 0.0)
                a.color = (color_r, color_g, color_b)

                canvas.arcs.append(a)

    # --- Restore Roofs ---
    if hasattr(canvas, 'roofs'):
        canvas.roofs.clear()

    if hasattr(canvas, 'stairs'):
        canvas.stairs.clear()

    roofs_elem = root.find("Roofs")
    if roofs_elem is not None and hasattr(canvas, 'roofs'):
        for r_elem in roofs_elem.findall("Roof"):
            identifier = _get_attr_text(r_elem, "identifier", "")
            layer_id = _get_attr_text(r_elem, "layer_id", "")
            roof_type = _get_attr_text(r_elem, "roof_type", "gable")
            pitch_rise = _get_attr_int(r_elem, "pitch_rise", 6)
            pitch_run = _get_attr_int(r_elem, "pitch_run", 12)
            overhang = _get_attr_float(r_elem, "overhang", 12.0)
            material = _get_attr_text(r_elem, "material", "asphalt_shingle")

            # Load edges
            edges = []
            edges_elem = r_elem.find("Edges")
            if edges_elem is not None:
                for e_elem in edges_elem.findall("Edge"):
                    edges.append(RoofEdge(
                        wall_identifier=_get_attr_text(e_elem, "wall_identifier", ""),
                        edge_type=_get_attr_text(e_elem, "edge_type", "eave")
                    ))

            # Load geometry
            ridge_lines = []
            ridge_elem = r_elem.find("RidgeLines")
            if ridge_elem is not None:
                for line_elem in ridge_elem.findall("Line"):
                    p1 = (_get_attr_float(line_elem, "x1", 0.0), _get_attr_float(line_elem, "y1", 0.0))
                    p2 = (_get_attr_float(line_elem, "x2", 0.0), _get_attr_float(line_elem, "y2", 0.0))
                    ridge_lines.append((p1, p2))

            hip_lines = []
            hip_elem = r_elem.find("HipLines")
            if hip_elem is not None:
                for line_elem in hip_elem.findall("Line"):
                    p1 = (_get_attr_float(line_elem, "x1", 0.0), _get_attr_float(line_elem, "y1", 0.0))
                    p2 = (_get_attr_float(line_elem, "x2", 0.0), _get_attr_float(line_elem, "y2", 0.0))
                    hip_lines.append((p1, p2))

            valley_lines = []
            valley_elem = r_elem.find("ValleyLines")
            if valley_elem is not None:
                for line_elem in valley_elem.findall("Line"):
                    p1 = (_get_attr_float(line_elem, "x1", 0.0), _get_attr_float(line_elem, "y1", 0.0))
                    p2 = (_get_attr_float(line_elem, "x2", 0.0), _get_attr_float(line_elem, "y2", 0.0))
                    valley_lines.append((p1, p2))

            outline_points = []
            outline_elem = r_elem.find("Outline")
            if outline_elem is not None:
                for pt_elem in outline_elem.findall("Point"):
                    outline_points.append((_get_attr_float(pt_elem, "x", 0.0), _get_attr_float(pt_elem, "y", 0.0)))

            roof = Roof(
                identifier=identifier,
                layer_id=layer_id,
                edges=edges,
                roof_type=roof_type,
                pitch_rise=pitch_rise,
                pitch_run=pitch_run,
                overhang=overhang,
                ridge_lines=ridge_lines,
                hip_lines=hip_lines,
                valley_lines=valley_lines,
                outline_points=outline_points,
                material=material
            )
            canvas.roofs.append(roof)

    # --- Restore Stairs ---
    stairs_elem = root.find("Stairs")
    if stairs_elem is not None and hasattr(canvas, 'stairs'):
        for s_elem in stairs_elem.findall("Stair"):
            identifier = _get_attr_text(s_elem, "identifier", "")
            layer_id = _get_attr_text(s_elem, "layer_id", "")

            start_x = _get_attr_float(s_elem, "start_x", 0.0)
            start_y = _get_attr_float(s_elem, "start_y", 0.0)
            direction_angle = _get_attr_float(s_elem, "direction_angle", 0.0)

            stair = Stair(
                identifier=identifier,
                layer_id=layer_id,
                start_point=(start_x, start_y),
                direction_angle=direction_angle
            )

            stair.start_level_id = _get_attr_text(s_elem, "start_level_id", "")
            stair.end_level_id = _get_attr_text(s_elem, "end_level_id", "")

            stair.stair_type = _get_attr_text(s_elem, "stair_type", "straight")
            stair.width = _get_attr_float(s_elem, "width", 36.0)
            stair.total_rise = _get_attr_float(s_elem, "total_rise", 106.0)
            stair.riser_height = _get_attr_float(s_elem, "riser_height", 7.57)
            stair.num_steps = _get_attr_int(s_elem, "num_steps", 14)
            stair.tread_depth = _get_attr_float(s_elem, "tread_depth", 11.0)
            stair.total_run = _get_attr_float(s_elem, "total_run", 143.0)
            stair.nosing = _get_attr_float(s_elem, "nosing", 1.0)

            stair.has_left_rail = _get_attr_text(s_elem, "has_left_rail", "True") == "True"
            stair.has_right_rail = _get_attr_text(s_elem, "has_right_rail", "True") == "True"
            stair.rail_height = _get_attr_float(s_elem, "rail_height", 36.0)

            stair.show_up_arrow = _get_attr_text(s_elem, "show_up_arrow", "True") == "True"
            stair.show_step_count = _get_attr_text(s_elem, "show_step_count", "True") == "True"

            canvas.stairs.append(stair)

    # Return the saved window size.
    return window_width, window_height

