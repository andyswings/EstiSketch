import os
import zipfile
import tempfile
import xml.etree.ElementTree as ET

from components import Wall, Room

def import_sh3d(sh3d_file_path: str) -> dict:
    """
    Import a Sweet Home 3D (.sh3d) file and extract walls and rooms.

    The imported walls are returned as individual wall sets so that each wall
    uses its own imported start and end coordinates. Walls will only be mitered
    together if they share an endpoint.

    Parameters:
        sh3d_file_path (str): The path to the .sh3d file.

    Returns:
        dict: A dictionary containing two keys:
            'wall_sets' - a list of wall sets, where each wall set is a list containing a single Wall object.
            'rooms' - a list of Room objects.
    """
    if not os.path.exists(sh3d_file_path):
        raise FileNotFoundError(f"File {sh3d_file_path} does not exist.")

    # Create a temporary directory to extract the zip file.
    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(sh3d_file_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        # Assume Home.xml is located at the root of the extracted folder.
        home_xml_path = os.path.join(temp_dir, "Home.xml")
        if not os.path.exists(home_xml_path):
            raise FileNotFoundError("Home.xml not found in the extracted sh3d archive.")

        # Parse the XML file.
        tree = ET.parse(home_xml_path)
        root = tree.getroot()

        # Get the default wall height from the <home> element.
        wall_height = float(root.get('wallHeight', 96.0))

        # Extract walls from the XML.
        walls = []
        for wall_elem in root.findall('wall'):
            try:
                x_start = float(wall_elem.get('xStart', 0))
                y_start = float(wall_elem.get('yStart', 0))
                x_end = float(wall_elem.get('xEnd', 0))
                y_end = float(wall_elem.get('yEnd', 0))
                # Use the wall's own height if provided, otherwise use the default.
                wall_elem_height = float(wall_elem.get('height', wall_height))
                # The thickness attribute will be used as the wall width.
                thickness = float(wall_elem.get('thickness', 0))
            except ValueError as e:
                print(f"Error parsing wall element: {e}")
                continue

            # Create a Wall object using the extracted data.
            wall = Wall(start=(x_start, y_start), end=(x_end, y_end),
                        width=thickness, height=wall_elem_height)
            walls.append(wall)
        print(f"Extracted {len(walls)} walls from the file.")
        for wall in walls:
            print(f"Wall from {wall.start} to {wall.end}, width: {wall.width}, height: {wall.height}")

        # Extract rooms from the XML.
        rooms = []
        for room_elem in root.findall('room'):
            points = []
            for point_elem in room_elem.findall('point'):
                try:
                    x = float(point_elem.get('x', 0))
                    y = float(point_elem.get('y', 0))
                    points.append((x, y))
                except ValueError as e:
                    print(f"Error parsing room point: {e}")
            if points:
                # Create a Room object with the imported points and set its height from wallHeight.
                room = Room(points=points, height=wall_height)
                rooms.append(room)

        # Create wall sets: each wall is placed in its own set.
        # This ensures that each wall is drawn independently using its own start and end points.
        wall_sets = [[wall] for wall in walls]

        return {"wall_sets": wall_sets, "rooms": rooms}

# Example usage:
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python sh3d_importer.py <path_to_sh3d_file>")
        sys.exit(1)

    sh3d_file = sys.argv[1]
    try:
        imported = import_sh3d(sh3d_file)
        print("Imported Walls:")
        for wall_set in imported["wall_sets"]:
            for wall in wall_set:
                print(f"  Wall from {wall.start} to {wall.end}, width: {wall.width}, height: {wall.height}")
        print("\nImported Rooms:")
        for room in imported["rooms"]:
            print(f"  Room with points: {room.points}, height: {room.height}")
    except Exception as e:
        print(f"Error importing sh3d file: {e}")
