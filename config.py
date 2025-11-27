import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "settings.json")

DEFAULT_SETTINGS = {
    "WINDOW_TITLE": "Estimator App",
    "WINDOW_WIDTH": 1024,
    "WINDOW_HEIGHT": 900,
    "SAVE_LABEL": "Save",
    "OPEN_LABEL": "Open File",
    "EXPORT_LABEL": "Export as PDF",
    "POINTER_LABEL": "Pointer Tool",
    "DRAW_WALLS_LABEL": "Draw Walls",
    "DRAW_ROOMS_LABEL": "Draw Rooms",
    "ADD_DOORS_LABEL": "Add Doors",
    "ADD_WINDOWS_LABEL": "Add Windows",
    "ADD_DIMENSION_LABEL": "Add Dimension Lines",
    "ADD_TEXT_LABEL": "Add Text",
    "MANAGE_MATERIALS_LABEL": "Manage Materials",
    "ESTIMATE_MATERIALS_LABEL": "Estimate Materials",
    "ESTIMATE_COST_LABEL": "Estimate Cost",
    "SETTINGS_LABEL": "Settings",
    "HELP_LABEL": "Help",
    "SETTINGS_TITLE": "Settings",
    "OK_LABEL": "OK",
    "CANCEL_LABEL": "Cancel",
    "DEFAULT_WALL_HEIGHT": 96.0,
    "DEFAULT_WALL_WIDTH": 5.5,
    "UNITS": "feet_inches",
    "SNAP_ENABLED": True,
    "SNAP_THRESHOLD": 10,
    "SHOW_GRID": True,
    "FONT": "Sans 10",
    "SHOW_RULERS": True,
    "WALL_DISPLAY_PATTERN": "solid",
    "CONSTRUCTION_TYPE": "stick",
    "DEFAULT_ZOOM_LEVEL": 1.0,
    "ENABLE_AUTO_SAVE": True,
    "AUTO_SAVE_INTERVAL": 5,
    "GRID_SPACING": 20,
    "SHOW_GRID_LABELS": True,
    "PRECISION_LEVEL": 2,
    "SHOW_MEASUREMENT_HINTS": True,
    "DEFAULT_ROOM_HEIGHT": 96.0,
    "WALL_JOIN_TOLERANCE": 5,
    "SNAP_TO_ANGLE_INCREMENT": 22.5,
    "ENABLE_PERPENDICULAR_SNAPPING": True,
    "ENABLE_CENTERLINE_SNAPPING": True,
    "ENABLE_UNDO_REDO_LIMIT": True,
    "UNDO_REDO_LIMIT": 50,
    "ENABLE_OBJECT_LOCKING": True,
    "DEFAULT_DIMENSION_STYLE": "inline",
    "ENABLE_DIMENSION_AUTO_UPDATE": True,
    "FONT_SIZE_DIMENSIONS": 12,
    "DEFAULT_FILE_FORMAT": "json",
    "ENABLE_PDF_EXPORT_OPTIONS": True,
    "INCLUDE_COST_ESTIMATE_IN_EXPORT": True,
    "DEFAULT_MATERIAL_COST_UNIT": "per sq ft",
    "LABOR_COST_PER_HOUR": 50.0,
    "TAX_RATE_PERCENTAGE": 8.0,
    "ALLOW_CURVED_WALLS": False,
    "DEFAULT_INTERIOR_WALL_MATERIAL": "Drywall",
    "DEFAULT_EXTERIOR_WALL_MATERIAL": "Brick",
    "PIXELS_PER_INCH": 2.0,
    "RECENT_FILES": [],
    "MAX_RECENT_FILES": 6,
    "POLYLINE_TYPE": "solid",
    "SHOW_PROPERTIES_PANEL": False,
    "JOINT_SNAP_TOLERANCE": 1,
    "MAX_WALL_PLATE_INCHES": 192
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                contents = f.read().strip()
                if not contents:
                    return DEFAULT_SETTINGS.copy()
                settings = json.loads(contents)
        except (json.JSONDecodeError, IOError):
            settings = DEFAULT_SETTINGS.copy()
    else:
        settings = DEFAULT_SETTINGS.copy()
    return settings

def save_config(settings):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(settings, f, indent=4)
