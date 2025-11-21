from Resources.framing import roughOpeningExtraStuds

class FramingEstimator:
    """
    Estimates framing materials (studs, etc.) for wood-framed walls.
    """

    @staticmethod
    def calculate_stud_count(wall, doors: list = None, windows: list = None, connected_walls: int = 0) -> int:
        """
        Calculate the number of studs required for a wall.

        The calculation is based on:
        1. Base studs: (wall_length / stud_spacing) + 1
        2. Extra studs for openings (doors/windows) from roughOpeningExtraStuds lookup
        3. One extra stud per connected wall (drywall nailer)

        Args:
            wall (Wall): The wall object with start, end, and stud_spacing attributes.
            doors (list, optional): List of doors on this wall, each with a width attribute.
            windows (list, optional): List of windows on this wall, each with a width attribute.
            connected_walls (int, optional): Number of walls that connect to this wall (for nailers).

        Returns:
            int: The total number of studs required.
        """
        if wall.material != "wood":
            return 0

        # Calculate wall length in inches
        dx = wall.end[0] - wall.start[0]
        dy = wall.end[1] - wall.start[1]
        wall_length_inches = ((dx ** 2 + dy ** 2) ** 0.5)
        print(f"Wall length (inches): {wall_length_inches}")
        print(f"Wall length (feet): {wall_length_inches / 12}")

        # Get stud spacing (default to 16 if not specified)
        stud_spacing = getattr(wall, "stud_spacing", 16)

        # Base stud count: (length / spacing) + 1
        base_studs = int(wall_length_inches / stud_spacing) + 1

        # Add extra studs for openings
        opening_studs = 0
        if doors:
            for door in doors:
                door_width = int(getattr(door, "width", 36))
                opening_studs += roughOpeningExtraStuds.get(door_width, 0)

        if windows:
            for window in windows:
                window_width = int(getattr(window, "width", 36))
                opening_studs += roughOpeningExtraStuds.get(window_width, 0)

        # Add one stud per connected wall (drywall nailer)
        nailer_studs = connected_walls

        total_studs = base_studs + opening_studs + nailer_studs

        return max(total_studs, 1)  # Ensure at least 1 stud

    @staticmethod
    def estimate_wall_materials(wall, doors: list = None, windows: list = None, connected_walls: int = 0) -> dict:
        """
        Estimate all framing materials for a single wall.

        Args:
            wall (Wall): The wall object.
            doors (list, optional): List of doors on this wall.
            windows (list, optional): List of windows on this wall.
            connected_walls (int, optional): Number of connecting walls.

        Returns:
            dict: Dictionary containing material counts (studs, top_plates, bottom_plates, etc.).
        """
        if wall.material != "wood":
            return {}

        stud_count = FramingEstimator.calculate_stud_count(wall, doors, windows, connected_walls)

        # Wall length in inches for plate calculations
        dx = wall.end[0] - wall.start[0]
        dy = wall.end[1] - wall.start[1]
        wall_length_inches = ((dx ** 2 + dy ** 2) ** 0.5) * 12

        return {
            "studs": stud_count,
            "top_plates": 2,  # Typically 2 top plates (single or doubled)
            "bottom_plates": 1,
            "wall_length_inches": wall_length_inches,
            "stud_spacing": getattr(wall, "stud_spacing", 16)
        }

    @staticmethod
    def estimate_all_walls(wall_sets: list, walls_with_openings: dict = None) -> dict:
        """
        Estimate framing materials for all walls in the project.

        Args:
            wall_sets (list): List of wall sets (each set is a list of connected walls).
            walls_with_openings (dict, optional): Dict mapping wall identifier to {"doors": [...], "windows": [...]}

        Returns:
            dict: Aggregated material counts.
        """
        if walls_with_openings is None:
            walls_with_openings = {}

        total_studs = 0
        total_top_plates = 0
        total_bottom_plates = 0
        wall_details = []

        for wall_set in wall_sets:
            for wall in wall_set:
                if wall.material != "wood":
                    continue

                # Get connected walls count (walls in same set + 1 for each connection)
                connected_count = len(wall_set) - 1

                # Get doors and windows for this wall
                openings = walls_with_openings.get(wall.identifier, {})
                doors = openings.get("doors", [])
                windows = openings.get("windows", [])

                materials = FramingEstimator.estimate_wall_materials(
                    wall, doors, windows, connected_count
                )

                if materials:
                    total_studs += materials["studs"]
                    total_top_plates += materials["top_plates"]
                    total_bottom_plates += materials["bottom_plates"]
                    wall_details.append({
                        "wall_id": wall.identifier,
                        "materials": materials
                    })

        return {
            "total_studs": total_studs,
            "total_top_plates": total_top_plates,
            "total_bottom_plates": total_bottom_plates,
            "wall_details": wall_details
        }