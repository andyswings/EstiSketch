import os
import zipfile
import tempfile
import xml.etree.ElementTree as ET
import math

from components import Wall, Room, Door, Window

def import_sh3d(sh3d_file_path: str) -> dict:
    """
    Import a Sweet Home 3D (.sh3d) file and extract walls, rooms, doors, and windows.
    All measurements (in centimeters) are converted to inches.
    Doors and windows are attached to the nearest wall based on a projection ratio.
    """
    if not os.path.exists(sh3d_file_path):
        raise FileNotFoundError(f"File {sh3d_file_path} does not exist.")

    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(sh3d_file_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        home_xml_path = os.path.join(temp_dir, "Home.xml")
        if not os.path.exists(home_xml_path):
            raise FileNotFoundError("Home.xml not found in the extracted sh3d archive.")

        tree = ET.parse(home_xml_path)
        root = tree.getroot()

        # Conversion factor: 1 cm ≈ 0.3937 inches
        cm_to_in = 0.393700787

        wall_height = float(root.get('wallHeight', 96.0)) * cm_to_in

        # Extract walls
        walls = []
        for wall_elem in root.findall('wall'):
            try:
                x_start = float(wall_elem.get('xStart', 0)) * cm_to_in
                y_start = float(wall_elem.get('yStart', 0)) * cm_to_in
                x_end = float(wall_elem.get('xEnd', 0)) * cm_to_in
                y_end = float(wall_elem.get('yEnd', 0)) * cm_to_in
                wall_elem_height = float(wall_elem.get('height', wall_height/cm_to_in)) * cm_to_in
                thickness = float(wall_elem.get('thickness', 0)) * cm_to_in
            except ValueError as e:
                print(f"Error parsing wall element: {e}")
                continue

            wall = Wall(start=(x_start, y_start), end=(x_end, y_end),
                        width=thickness, height=wall_elem_height)
            # Optionally, mark walls with a specific pattern as exterior
            if wall_elem.get('pattern', '').lower() == 'hatchup':
                wall.exterior_wall = True
            walls.append(wall)
        print(f"Extracted {len(walls)} walls.")

        # Extract rooms
        rooms = []
        for room_elem in root.findall('room'):
            points = []
            for point_elem in room_elem.findall('point'):
                try:
                    x = float(point_elem.get('x', 0)) * cm_to_in
                    y = float(point_elem.get('y', 0)) * cm_to_in
                    points.append((x, y))
                except ValueError as e:
                    print(f"Error parsing room point: {e}")
            if points:
                room = Room(points=points, height=wall_height)
                rooms.append(room)

        wall_sets = [[wall] for wall in walls]

        # Helper: Project point P onto segment AB.
        def project_point(P, A, B):
            (px, py), (ax, ay), (bx, by) = P, A, B
            dx = bx - ax
            dy = by - ay
            if dx == 0 and dy == 0:
                return math.hypot(px - ax, py - ay), 0
            t = ((px - ax) * dx + (py - ay) * dy) / (dx*dx + dy*dy)
            t = max(0, min(1, t))
            proj_x = ax + t * dx
            proj_y = ay + t * dy
            dist = math.hypot(px - proj_x, py - proj_y)
            return dist, t

        # Extract doors and windows
        doors = []
        windows = []
        for dw_elem in root.findall('doorOrWindow'):
            try:
                x = float(dw_elem.get('x', 0)) * cm_to_in
                y = float(dw_elem.get('y', 0)) * cm_to_in
                width = float(dw_elem.get('width', 0)) * cm_to_in
                depth = float(dw_elem.get('depth', 0)) * cm_to_in
                height = float(dw_elem.get('height', 0)) * cm_to_in
            except ValueError as e:
                print(f"Error parsing doorOrWindow element: {e}")
                continue

            name_attr = dw_elem.get('name', '').lower()
            if "window" in name_attr:
                element_type = "window"
            elif "door" in name_attr:
                element_type = "door"
            else:
                continue

            center = (x, y)
            best_dist = float('inf')
            best_ratio = 0
            associated_wall = None
            for wall in walls:
                dist, t = project_point(center, wall.start, wall.end)
                if dist < best_dist:
                    best_dist = dist
                    best_ratio = t
                    associated_wall = wall

            # Use a tolerance (e.g., 10 inches) to decide if the door/window is close enough to a wall.
            if best_dist > 10:
                print(f"{element_type.title()} at {center} is too far from any wall (distance {best_dist:.2f} in). Skipping.")
                continue

            if element_type == "door":
                new_door = Door("single", width, height, "left", "inward")
                doors.append((associated_wall, new_door, best_ratio))
            else:  # window
                new_window = Window(width, height, "sliding")
                windows.append((associated_wall, new_window, best_ratio))

        return {"wall_sets": wall_sets, "rooms": rooms, "doors": doors, "windows": windows}
