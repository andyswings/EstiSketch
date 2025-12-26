import xml.etree.ElementTree as ET
from components import Wall, Room, Door, Window, Text, Dimension, Layer, Level

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
    root = ET.Element("Project", window_width=str(window_width), window_height=str(window_height))

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

    # Save wall sets (each wall in a wall set includes all construction details)
    walls_elem = ET.SubElement(root, "WallSets")
    # Build a mapping of wall objects to their wall set index and index within that set.
    wall_mapping = {}
    for set_index, wall_set in enumerate(canvas.wall_sets):
        ws_elem = ET.SubElement(walls_elem, "WallSet")
        for wall_index, wall in enumerate(wall_set):
            wall_mapping[id(wall)] = (set_index, wall_index)
            wall_elem = ET.SubElement(ws_elem, "Wall")
            # Save coordinates and dimensions.
            ET.SubElement(wall_elem, "Start", x=str(wall.start[0]), y=str(wall.start[1]))
            ET.SubElement(wall_elem, "End", x=str(wall.end[0]), y=str(wall.end[1]))
            ET.SubElement(wall_elem, "Width").text = str(wall.width)
            ET.SubElement(wall_elem, "Height").text = str(wall.height)
            ET.SubElement(wall_elem, "ExteriorWall").text = str(wall.exterior_wall)
            ET.SubElement(wall_elem, "LayerId").text = getattr(wall, 'layer_id', '')
            # Save additional construction properties.
            ET.SubElement(wall_elem, "Material").text = wall.material
            ET.SubElement(wall_elem, "InteriorFinish").text = wall.interior_finish
            ET.SubElement(wall_elem, "ExteriorFinish").text = wall.exterior_finish
            ET.SubElement(wall_elem, "StudSpacing").text = str(wall.stud_spacing)
            ET.SubElement(wall_elem, "InsulationType").text = wall.insulation_type
            ET.SubElement(wall_elem, "FireRating").text = wall.fire_rating

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
        ET.SubElement(room_elem, "LayerId").text = getattr(room, 'layer_id', '')

    # Save doors. In addition to their properties and attachment ratio, also save a wall reference.
    doors_elem = ET.SubElement(root, "Doors")
    for attached_wall, door, ratio in canvas.doors:
        door_elem = ET.SubElement(doors_elem, "Door")
        ET.SubElement(door_elem, "DoorType").text = door.door_type
        ET.SubElement(door_elem, "Width").text = str(door.width)
        ET.SubElement(door_elem, "Height").text = str(door.height)
        ET.SubElement(door_elem, "Swing").text = door.swing
        ET.SubElement(door_elem, "Orientation").text = door.orientation
        ET.SubElement(door_elem, "AttachedToWallRatio").text = str(ratio)
        ET.SubElement(door_elem, "LayerId").text = getattr(door, 'layer_id', '')
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
        ET.SubElement(win_elem, "LayerId").text = getattr(window_obj, 'layer_id', '')
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

    # Write out the XML to the given file (with declaration and proper encoding).
    tree = ET.ElementTree(root)
    tree.write(filepath, encoding="utf-8", xml_declaration=True)



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

    # Retrieve window dimensions.
    window_width = int(root.get("window_width"))
    window_height = int(root.get("window_height"))

    # Clear the current canvas state.
    canvas.wall_sets.clear()
    canvas.rooms.clear()
    canvas.doors.clear()
    canvas.windows.clear()
    canvas.texts.clear()
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
                id=level_elem.get("id"),
                name=level_elem.get("name", "Level"),
                elevation=float(level_elem.get("elevation", "0.0")),
                height=float(level_elem.get("height", "96.0"))
            )
            if hasattr(canvas, 'levels'):
                canvas.levels.append(level)
    
    # Default level if none found
    if hasattr(canvas, 'levels') and not canvas.levels:
        canvas.levels.append(Level(id="level-1", name="Level 1"))
        
    # Restore active level ID
    active_level_id = root.get("active_level_id", "")
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
            legacy_level_id = canvas.levels[0].id if canvas.levels else ""
            
            layer = Layer(
                id=layer_elem.get("id", ""),
                name=layer_elem.get("name", "Layer"),
                visible=layer_elem.get("visible", "True") == "True",
                locked=layer_elem.get("locked", "False") == "True",
                opacity=float(layer_elem.get("opacity", "1.0")),
                level_id=layer_elem.get("level_id", legacy_level_id)
            )
            if hasattr(canvas, 'layers'):
                canvas.layers.append(layer)
    
    # Restore active layer ID
    active_layer_id = root.get("active_layer_id", "")
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
                start = (float(start_elem.get("x")), float(start_elem.get("y")))
                end = (float(end_elem.get("x")), float(end_elem.get("y")))
                width = float(wall_elem.find("Width").text)
                height = float(wall_elem.find("Height").text)
                exterior_text = wall_elem.find("ExteriorWall").text
                exterior_wall = exterior_text.lower() == "true"
                
                # Create a new Wall instance.
                wall = Wall(start, end, width, height, exterior_wall)
                wall.layer_id = wall_elem.find("LayerId").text if wall_elem.find("LayerId") is not None else ""
                wall.material = wall_elem.find("Material").text
                wall.interior_finish = wall_elem.find("InteriorFinish").text
                wall.exterior_finish = wall_elem.find("ExteriorFinish").text
                wall.stud_spacing = int(wall_elem.find("StudSpacing").text)
                wall.insulation_type = wall_elem.find("InsulationType").text
                wall.fire_rating = wall_elem.find("FireRating").text
                
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
                    x = float(pt_elem.get("x"))
                    y = float(pt_elem.get("y"))
                    points.append((x, y))
            height = float(room_elem.find("Height").text)
            room = Room(points, height)
            room.floor_type = room_elem.find("FloorType").text
            room.wall_finish = room_elem.find("WallFinish").text
            room.room_type = room_elem.find("RoomType").text
            room.name = room_elem.find("Name").text
            room.layer_id = room_elem.find("LayerId").text if room_elem.find("LayerId") is not None else ""
            canvas.rooms.append(room)

    # --- Restore Doors ---
    doors_elem = root.find("Doors")
    if doors_elem is not None:
        for door_elem in doors_elem.findall("Door"):
            door_type = door_elem.find("DoorType").text
            width = float(door_elem.find("Width").text)
            height = float(door_elem.find("Height").text)
            swing = door_elem.find("Swing").text
            orientation = door_elem.find("Orientation").text
            ratio = float(door_elem.find("AttachedToWallRatio").text)
            
            door = Door(door_type, width, height, swing, orientation)
            door.layer_id = door_elem.find("LayerId").text if door_elem.find("LayerId") is not None else ""
            attached_wall = None
            wall_ref_elem = door_elem.find("WallReference")
            if wall_ref_elem is not None:
                set_index = int(wall_ref_elem.get("set_index", "-1"))
                wall_index = int(wall_ref_elem.get("wall_index", "-1"))
                if set_index >= 0 and wall_index >= 0 and set_index < len(canvas.wall_sets):
                    wall_set = canvas.wall_sets[set_index]
                    if wall_index < len(wall_set):
                        attached_wall = wall_set[wall_index]
            canvas.doors.append((attached_wall, door, ratio))

    # --- Restore Windows ---
    windows_elem = root.find("Windows")
    if windows_elem is not None:
        for win_elem in windows_elem.findall("Window"):
            win_width = float(win_elem.find("Width").text)
            win_height = float(win_elem.find("Height").text)
            window_type = win_elem.find("WindowType").text
            ratio = float(win_elem.find("AttachedToWallRatio").text)
            
            window_obj = Window(win_width, win_height, window_type)
            window_obj.layer_id = win_elem.find("LayerId").text if win_elem.find("LayerId") is not None else ""
            attached_wall = None
            wall_ref_elem = win_elem.find("WallReference")
            if wall_ref_elem is not None:
                set_index = int(wall_ref_elem.get("set_index", "-1"))
                wall_index = int(wall_ref_elem.get("wall_index", "-1"))
                if set_index >= 0 and wall_index >= 0 and set_index < len(canvas.wall_sets):
                    wall_set = canvas.wall_sets[set_index]
                    if wall_index < len(wall_set):
                        attached_wall = wall_set[wall_index]
            canvas.windows.append((attached_wall, window_obj, ratio))

    # --- Restore Texts ---
    texts_elem = root.find("Texts")
    if texts_elem is not None:
        for t_elem in texts_elem.findall("Text"):
            x = float(t_elem.get("x"))
            y = float(t_elem.get("y"))
            width = float(t_elem.get("width"))
            height = float(t_elem.get("height"))
            content = t_elem.get("content", "Text")
            identifier = t_elem.get("identifier", "")
            
            text_obj = Text(x, y, content, width, height, identifier)
            text_obj.font_size = float(t_elem.get("font_size", "12.0"))
            text_obj.font_family = t_elem.get("font_family", "Sans")
            text_obj.bold = t_elem.get("bold", "False") == "True"
            text_obj.italic = t_elem.get("italic", "False") == "True"
            text_obj.underline = t_elem.get("underline", "False") == "True"
            text_obj.layer_id = t_elem.get("layer_id", "")
            
            canvas.texts.append(text_obj)
    
    # --- Restore Dimensions ---
    dimensions_elem = root.find("Dimensions")
    if dimensions_elem is not None:
        for d_elem in dimensions_elem.findall("Dimension"):
            start_x = float(d_elem.get("start_x"))
            start_y = float(d_elem.get("start_y"))
            end_x = float(d_elem.get("end_x"))
            end_y = float(d_elem.get("end_y"))
            offset = float(d_elem.get("offset"))
            identifier = d_elem.get("identifier", "")
            
            dimension_obj = Dimension(
                start=(start_x, start_y),
                end=(end_x, end_y),
                offset=offset,
                identifier=identifier
            )
            dimension_obj.text_size = float(d_elem.get("text_size", "12.0"))
            dimension_obj.show_arrows = d_elem.get("show_arrows", "True") == "True"
            dimension_obj.line_style = d_elem.get("line_style", "solid")
            color_r = float(d_elem.get("color_r", "0.0"))
            color_g = float(d_elem.get("color_g", "0.0"))
            color_b = float(d_elem.get("color_b", "0.0"))
            dimension_obj.color = (color_r, color_g, color_b)
            dimension_obj.layer_id = d_elem.get("layer_id", "")
            
            canvas.dimensions.append(dimension_obj)

    # Return the saved window size.
    return window_width, window_height
