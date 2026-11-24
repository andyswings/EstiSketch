"""Tests for unique Sweet Home 3D format IDs across all object types."""

import os
import re
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile
from unittest.mock import MagicMock

import pytest

from EstiSketch.Canvas.utils import UtilsMixin, generate_identifier
from EstiSketch.components import (
    Arc,
    BackgroundImage,
    Circle,
    Dimension,
    DimensionChain,
    Door,
    Hole,
    Layer,
    LeaderCallout,
    Level,
    Polyline,
    Room,
    Stair,
    Text,
    Wall,
    Window,
)
from EstiSketch.project_io import open_project, save_project
from EstiSketch.roof_components import Roof, RoofEdge, RoofLine
from EstiSketch.sh3d_importer import import_sh3d


SH3D_UUID_TAIL = (
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


def is_valid_sh3d_id(identifier: str, expected_prefix: str) -> bool:
    """Return True if identifier matches Sweet Home 3D {prefix}-{uuid}."""
    pattern = rf"^{re.escape(expected_prefix.lower())}-{SH3D_UUID_TAIL}$"
    return bool(re.match(pattern, identifier))


def test_generate_identifier_matches_sh3d_format():
    """Verify generate_identifier produces lowercase {prefix}-{uuid4}."""
    prefixes = [
        "level",
        "layer",
        "wall",
        "polyline",
        "hole",
        "room",
        "door",
        "window",
        "text",
        "dimension",
        "circle",
        "arc",
        "stair",
        "blueprint",
        "dim_chain",
        "leader",
        "roof",
        "roof_line",
    ]
    existing = []
    for prefix in prefixes:
        ident = generate_identifier(prefix, existing)
        assert is_valid_sh3d_id(ident, prefix)
        assert ident not in existing
        existing.append(ident)

    # Also test uppercase prefix normalization and UtilsMixin method
    mixin = UtilsMixin()
    upper_id = mixin.generate_identifier("WALL", existing)
    assert is_valid_sh3d_id(upper_id, "wall")


def test_generate_identifier_avoids_collisions(monkeypatch):
    """Verify generate_identifier retries when a candidate ID exists."""
    fixed_uuid_1 = uuid.UUID("0f3253ce-86f9-4286-97df-beaae4a53ece")
    fixed_uuid_2 = uuid.UUID("61026525-54bd-486e-a0a8-6bb410d7f128")
    seq = iter([fixed_uuid_1, fixed_uuid_1, fixed_uuid_2])
    monkeypatch.setattr(
        "EstiSketch.Canvas.utils.uuid.uuid4", lambda: next(seq)
    )

    existing = [f"wall-{fixed_uuid_1}"]
    new_id = generate_identifier("wall", existing)
    assert new_id == f"wall-{fixed_uuid_2}"
    assert is_valid_sh3d_id(new_id, "wall")


@pytest.mark.parametrize(
    "factory,expected_prefix",
    [
        (lambda: Level(), "level"),
        (lambda: Layer(), "layer"),
        (lambda: Wall((0, 0), (120, 0), 4.5, 96.0), "wall"),
        (lambda: Polyline((0, 0), (60, 60)), "polyline"),
        (
            lambda: Hole(
                source_id="stair:1", points=[(0, 0), (10, 0), (10, 10)]
            ),
            "hole",
        ),
        (lambda: Room([(0, 0), (120, 0), (120, 120), (0, 120)]), "room"),
        (lambda: Door("single", 36.0, 80.0, "left", "inswing"), "door"),
        (lambda: Window(36.0, 48.0, "sliding"), "window"),
        (lambda: Text(10.0, 20.0, "Hello"), "text"),
        (lambda: Dimension((0, 0), (120, 0), 12.0), "dimension"),
        (lambda: Circle((50.0, 50.0), 24.0), "circle"),
        (lambda: Arc((50.0, 50.0), 24.0, 0.0, 1.57), "arc"),
        (lambda: Stair(), "stair"),
        (lambda: BackgroundImage(), "blueprint"),
        (
            lambda: DimensionChain(points=[(0, 0), (60, 0), (120, 0)]),
            "dim_chain",
        ),
        (lambda: LeaderCallout(), "leader"),
        (lambda: Roof(), "roof"),
        (lambda: RoofLine(), "roof_line"),
    ],
)
def test_all_object_types_auto_generate_unique_sh3d_id(
    factory, expected_prefix
):
    """Every object type must have a unique SH3D-format ID on init."""
    obj1 = factory()
    obj2 = factory()

    assert hasattr(obj1, "identifier")
    assert hasattr(obj2, "identifier")
    assert is_valid_sh3d_id(obj1.identifier, expected_prefix)
    assert is_valid_sh3d_id(obj2.identifier, expected_prefix)
    assert obj1.identifier != obj2.identifier

    if isinstance(obj1, (Level, Layer)):
        assert obj1.id == obj1.identifier
        new_id = generate_identifier(expected_prefix)
        obj1.identifier = new_id
        assert obj1.id == new_id


def test_canvas_default_and_added_levels_layers_use_sh3d_ids():
    """Canvas default and newly added levels and layers must use SH3D IDs."""
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = MagicMock()
    cfg.DEFAULT_ZOOM_LEVEL = 1.0
    cfg.DEFAULT_WALL_WIDTH = 4.5
    cfg.DEFAULT_WALL_HEIGHT = 96.0
    cfg.DEFAULT_LEVEL_HEIGHT = 96.0
    cfg.PIXELS_PER_INCH = 2.0
    cfg.WINDOW_WIDTH = 800
    cfg.SNAP_ENABLED = True

    canvas = CanvasArea(cfg)

    assert len(canvas.levels) == 1
    assert len(canvas.layers) == 1
    assert is_valid_sh3d_id(canvas.levels[0].id, "level")
    assert is_valid_sh3d_id(canvas.layers[0].id, "layer")
    assert canvas.levels[0].id in canvas.existing_ids
    assert canvas.layers[0].id in canvas.existing_ids

    added_level_id = canvas.add_level("Level 2")
    added_layer_id = canvas.add_layer("Layer 1")
    assert is_valid_sh3d_id(added_level_id, "level")
    assert is_valid_sh3d_id(added_layer_id, "layer")
    assert added_level_id in canvas.existing_ids
    assert added_layer_id in canvas.existing_ids


def test_room_events_assign_unique_sh3d_ids():
    """Verify room creation paths in CanvasRoomMixin assign SH3D IDs."""
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = MagicMock()
    cfg.DEFAULT_ZOOM_LEVEL = 1.0
    cfg.DEFAULT_WALL_WIDTH = 4.5
    cfg.DEFAULT_WALL_HEIGHT = 96.0
    cfg.PIXELS_PER_INCH = 2.0
    cfg.WINDOW_WIDTH = 800
    cfg.SNAP_ENABLED = False
    cfg.SNAP_THRESHOLD = 10
    cfg.UNDO_REDO_LIMIT = 50

    canvas = CanvasArea(cfg)

    # Path 1: finalize_room()
    canvas.current_room_points = [(0.0, 0.0), (120.0, 0.0), (120.0, 120.0)]
    canvas.finalize_room()
    assert len(canvas.rooms) == 1
    assert is_valid_sh3d_id(canvas.rooms[0].identifier, "room")
    assert canvas.rooms[0].identifier in canvas.existing_ids

    # Path 2: double-click with current_room_points
    canvas.current_room_points = [(0.0, 0.0), (60.0, 0.0), (60.0, 60.0)]
    canvas._handle_room_click(2, 120.0, 120.0)
    assert len(canvas.rooms) == 2
    assert is_valid_sh3d_id(canvas.rooms[1].identifier, "room")
    assert canvas.rooms[1].identifier != canvas.rooms[0].identifier
    assert canvas.rooms[1].identifier in canvas.existing_ids

    # Path 3: double-click inside closed wall loop
    w1 = Wall((200.0, 200.0), (300.0, 200.0), 4.5, 96.0)
    w2 = Wall((300.0, 200.0), (300.0, 300.0), 4.5, 96.0)
    w3 = Wall((300.0, 300.0), (200.0, 300.0), 4.5, 96.0)
    w4 = Wall((200.0, 300.0), (200.0, 200.0), 4.5, 96.0)
    canvas.wall_sets.append([w1, w2, w3, w4])
    dev_x, dev_y = canvas.model_to_device(250.0, 250.0, 2.0)
    canvas._handle_room_click(2, dev_x, dev_y)
    assert len(canvas.rooms) == 3
    assert is_valid_sh3d_id(canvas.rooms[2].identifier, "room")
    assert canvas.rooms[2].identifier in canvas.existing_ids


def test_paste_generates_new_unique_sh3d_ids_for_all_types():
    """Verify pasting objects assigns fresh SH3D IDs and records them."""
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = MagicMock()
    cfg.DEFAULT_ZOOM_LEVEL = 1.0
    cfg.DEFAULT_WALL_WIDTH = 4.5
    cfg.DEFAULT_WALL_HEIGHT = 96.0
    cfg.PIXELS_PER_INCH = 2.0
    cfg.WINDOW_WIDTH = 800
    cfg.SNAP_ENABLED = False
    cfg.SNAP_THRESHOLD = 10
    cfg.UNDO_REDO_LIMIT = 50

    canvas = CanvasArea(cfg)

    wall = Wall((0, 0), (120, 0), 4.5, 96.0)
    canvas.wall_sets.append([wall])
    door = Door("single", 36.0, 80.0, "left", "inswing")
    win = Window(36.0, 48.0, "sliding")
    text = Text(10.0, 10.0, "Note")
    dim = Dimension((0, 0), (120, 0), 12.0)
    chain = DimensionChain(points=[(0, 0), (60, 0), (120, 0)])
    leader = LeaderCallout(tip=(0, 0), elbow=(10, 10), shoulder=(20, 10))
    poly = Polyline((0, 0), (50, 50))
    circle = Circle((40, 40), 15.0)
    arc = Arc((40, 40), 15.0, 0.0, 1.5)
    stair = Stair(start_point=(0, 0))
    room = Room([(0, 0), (100, 0), (100, 100), (0, 100)])

    orig_ids = {
        wall.identifier,
        door.identifier,
        win.identifier,
        text.identifier,
        dim.identifier,
        chain.identifier,
        leader.identifier,
        poly.identifier,
        circle.identifier,
        arc.identifier,
        stair.identifier,
        room.identifier,
    }
    canvas.existing_ids.extend(orig_ids)

    canvas.clipboard = [
        {"type": "wall", "object": wall},
        {"type": "door", "object": (wall, door, 0.3)},
        {"type": "window", "object": (wall, win, 0.6)},
        {"type": "text", "object": text},
        {"type": "dimension", "object": dim},
        {"type": "dimension_chain", "object": chain},
        {"type": "leader_callout", "object": leader},
        {"type": "polyline", "object": poly},
        {"type": "circle", "object": circle},
        {"type": "arc", "object": arc},
        {"type": "stair", "object": stair},
        {"type": "vertex", "object": (room, 0)},
    ]

    canvas.paste()

    pasted_wall = canvas.wall_sets[-1][0]
    pasted_door = canvas.doors[-1][1]
    pasted_win = canvas.windows[-1][1]
    pasted_text = canvas.texts[-1]
    pasted_dim = canvas.dimensions[-1]
    pasted_chain = canvas.dimension_chains[-1]
    pasted_leader = canvas.leader_callouts[-1]
    pasted_poly = canvas.polyline_sets[-1][0]
    pasted_circle = canvas.circles[-1]
    pasted_arc = canvas.arcs[-1]
    pasted_stair = canvas.stairs[-1]
    pasted_room = canvas.rooms[-1]

    checks = [
        (pasted_wall.identifier, "wall"),
        (pasted_door.identifier, "door"),
        (pasted_win.identifier, "window"),
        (pasted_text.identifier, "text"),
        (pasted_dim.identifier, "dimension"),
        (pasted_chain.identifier, "dim_chain"),
        (pasted_leader.identifier, "leader"),
        (pasted_poly.identifier, "polyline"),
        (pasted_circle.identifier, "circle"),
        (pasted_arc.identifier, "arc"),
        (pasted_stair.identifier, "stair"),
        (pasted_room.identifier, "room"),
    ]
    for ident, prefix in checks:
        assert is_valid_sh3d_id(ident, prefix)
        assert ident not in orig_ids
        assert ident in canvas.existing_ids


def test_roof_solver_and_manual_roof_lines_use_sh3d_ids():
    """Verify roof solver and manual roof line sketching generate SH3D IDs."""
    from EstiSketch.Canvas.roof_solver import solve_and_clean_roof
    from EstiSketch.geometry.roof_solver import solve_roof_geometry

    w1 = Wall((0, 0), (240, 0), 4.5, 96.0)
    w2 = Wall((240, 0), (240, 180), 4.5, 96.0)
    w3 = Wall((240, 180), (0, 180), 4.5, 96.0)
    w4 = Wall((0, 180), (0, 0), 4.5, 96.0)
    walls = [w1, w2, w3, w4]

    edges = [
        RoofEdge(wall_identifier=w1.identifier, edge_type="eave"),
        RoofEdge(wall_identifier=w2.identifier, edge_type="gable"),
        RoofEdge(wall_identifier=w3.identifier, edge_type="eave"),
        RoofEdge(wall_identifier=w4.identifier, edge_type="gable"),
    ]
    roof = Roof(edges=edges, roof_type="gable")
    assert is_valid_sh3d_id(roof.identifier, "roof")

    solve_and_clean_roof(roof, walls)
    assert len(roof.manual_lines) > 0
    assert len(roof.solved_lines) > 0
    for ml in roof.manual_lines:
        assert is_valid_sh3d_id(ml.identifier, "roof_line")
    for sl in roof.solved_lines:
        assert is_valid_sh3d_id(sl.identifier, "roof_line")

    # Also test 3D geometry solver RoofLine IDs
    roof2 = Roof(edges=edges, roof_type="gable")
    res = solve_roof_geometry(roof2, walls)
    for sl in res["solved_lines"]:
        assert is_valid_sh3d_id(sl.identifier, "roof_line")


def test_project_io_roundtrip_preserves_all_object_identifiers():
    """Verify save_project and open_project preserve IDs for all types."""
    canvas = MagicMock()
    lvl = Level(name="Main")
    lyr = Layer(name="Layer 0", level_id=lvl.id)
    wall = Wall((0, 0), (120, 0), 4.5, 96.0, layer_id=lyr.id)
    room = Room([(0, 0), (120, 0), (120, 120), (0, 120)], layer_id=lyr.id)
    door = Door("single", 36.0, 80.0, "left", "inswing", layer_id=lyr.id)
    win = Window(36.0, 48.0, "sliding", layer_id=lyr.id)
    txt = Text(5.0, 5.0, "Label", layer_id=lyr.id)
    dim = Dimension((0, 0), (120, 0), 10.0, layer_id=lyr.id)
    chain = DimensionChain(points=[(0, 0), (60, 0), (120, 0)], layer_id=lyr.id)
    leader = LeaderCallout(
        tip=(0, 0), elbow=(5, 5), shoulder=(15, 5), layer_id=lyr.id
    )
    poly = Polyline((0, 0), (50, 0), layer_id=lyr.id)
    circle = Circle((30, 30), 12.0, layer_id=lyr.id)
    arc = Arc((30, 30), 12.0, 0.0, 1.0, layer_id=lyr.id)
    rline = RoofLine(start=(0, 60), end=(120, 60), line_type="ridge")
    roof = Roof(layer_id=lyr.id, manual_lines=[rline], solved_lines=[rline])
    stair = Stair(
        layer_id=lyr.id,
        start_point=(10, 10),
        start_level_id=lvl.id,
    )
    bp = BackgroundImage(name="bp.png", level_id=lvl.id)

    canvas.levels = [lvl]
    canvas.active_level_id = lvl.id
    canvas.cut_lower_ceiling_under_stairs = False
    canvas.layers = [lyr]
    canvas.active_layer_id = lyr.id
    canvas.wall_sets = [[wall]]
    canvas.rooms = [room]
    canvas.doors = [(wall, door, 0.5)]
    canvas.windows = [(wall, win, 0.5)]
    canvas.texts = [txt]
    canvas.dimensions = [dim]
    canvas.dimension_chains = [chain]
    canvas.leader_callouts = [leader]
    canvas.polyline_sets = [[poly]]
    canvas.circles = [circle]
    canvas.arcs = [arc]
    canvas.roofs = [roof]
    canvas.stairs = [stair]
    canvas.blueprints = [bp]
    canvas._blueprint_surfaces = {}
    canvas.get_blueprint_surface = lambda b: None

    expected_ids = {
        "level": lvl.id,
        "layer": lyr.id,
        "wall": wall.identifier,
        "room": room.identifier,
        "door": door.identifier,
        "window": win.identifier,
        "text": txt.identifier,
        "dimension": dim.identifier,
        "dim_chain": chain.identifier,
        "leader": leader.identifier,
        "polyline": poly.identifier,
        "circle": circle.identifier,
        "arc": arc.identifier,
        "roof": roof.identifier,
        "roof_line": rline.identifier,
        "stair": stair.identifier,
        "blueprint": bp.identifier,
    }

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "project.xml")
        save_project(canvas, 1024, 768, path)

        loaded = MagicMock()
        for attr in (
            "levels",
            "layers",
            "wall_sets",
            "rooms",
            "doors",
            "windows",
            "texts",
            "dimensions",
            "dimension_chains",
            "leader_callouts",
            "polyline_sets",
            "circles",
            "arcs",
            "roofs",
            "stairs",
            "blueprints",
        ):
            setattr(loaded, attr, [])
        loaded._blueprint_surfaces = {}
        loaded.get_blueprint_surface = lambda b: None

        open_project(loaded, path)

    assert loaded.levels[0].id == expected_ids["level"]
    assert loaded.layers[0].id == expected_ids["layer"]
    assert loaded.wall_sets[0][0].identifier == expected_ids["wall"]
    assert loaded.rooms[0].identifier == expected_ids["room"]
    assert loaded.doors[0][1].identifier == expected_ids["door"]
    assert loaded.windows[0][1].identifier == expected_ids["window"]
    assert loaded.texts[0].identifier == expected_ids["text"]
    assert loaded.dimensions[0].identifier == expected_ids["dimension"]
    assert loaded.dimension_chains[0].identifier == expected_ids["dim_chain"]
    assert loaded.leader_callouts[0].identifier == expected_ids["leader"]
    assert loaded.polyline_sets[0][0].identifier == expected_ids["polyline"]
    assert loaded.circles[0].identifier == expected_ids["circle"]
    assert loaded.arcs[0].identifier == expected_ids["arc"]
    assert loaded.roofs[0].identifier == expected_ids["roof"]
    assert (
        loaded.roofs[0].manual_lines[0].identifier == expected_ids["roof_line"]
    )
    assert loaded.stairs[0].identifier == expected_ids["stair"]
    assert loaded.blueprints[0].identifier == expected_ids["blueprint"]
    for ident in expected_ids.values():
        assert ident in loaded.existing_ids


def test_open_legacy_project_without_ids_generates_sh3d_ids():
    """Legacy XML missing IDs on walls/rooms/doors/windows gets SH3D IDs."""
    root = ET.Element("Project", window_width="800", window_height="600")
    ws_parent = ET.SubElement(root, "WallSets")
    ws = ET.SubElement(ws_parent, "WallSet")
    w_elem = ET.SubElement(ws, "Wall")
    ET.SubElement(w_elem, "Start", x="0", y="0")
    ET.SubElement(w_elem, "End", x="120", y="0")

    rooms_elem = ET.SubElement(root, "Rooms")
    r_elem = ET.SubElement(rooms_elem, "Room")
    pts_elem = ET.SubElement(r_elem, "Points")
    for x, y in ((0, 0), (120, 0), (120, 120)):
        ET.SubElement(pts_elem, "Point", x=str(x), y=str(y))

    doors_elem = ET.SubElement(root, "Doors")
    ET.SubElement(doors_elem, "Door")

    windows_elem = ET.SubElement(root, "Windows")
    ET.SubElement(windows_elem, "Window")

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "legacy.xml")
        ET.ElementTree(root).write(
            path, encoding="utf-8", xml_declaration=True
        )

        canvas = MagicMock()
        for attr in (
            "levels",
            "layers",
            "wall_sets",
            "rooms",
            "doors",
            "windows",
            "texts",
            "dimensions",
            "dimension_chains",
            "leader_callouts",
            "polyline_sets",
            "circles",
            "arcs",
            "roofs",
            "stairs",
            "blueprints",
        ):
            setattr(canvas, attr, [])
        open_project(canvas, path)

    assert is_valid_sh3d_id(canvas.levels[0].id, "level")
    assert is_valid_sh3d_id(canvas.wall_sets[0][0].identifier, "wall")
    assert is_valid_sh3d_id(canvas.rooms[0].identifier, "room")
    assert is_valid_sh3d_id(canvas.doors[0][1].identifier, "door")
    assert is_valid_sh3d_id(canvas.windows[0][1].identifier, "window")


def test_sh3d_importer_extracts_and_generates_valid_ids():
    """Verify import_sh3d preserves SH3D IDs and generates missing ones."""
    wall_sh3d_id = "wall-0f3253ce-86f9-4286-97df-beaae4a53ece"
    room_sh3d_id = "room-61026525-54bd-486e-a0a8-6bb410d7f128"

    home_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<home name="test" wallHeight="243.84">\n'
        f'  <wall id="{wall_sh3d_id}" xStart="0" yStart="0"'
        ' xEnd="300" yEnd="0" thickness="11.43"/>\n'
        '  <wall xStart="300" yStart="0" xEnd="300" yEnd="300"'
        ' thickness="11.43"/>\n'
        f'  <room id="{room_sh3d_id}">\n'
        '    <point x="0" y="0"/>\n'
        '    <point x="300" y="0"/>\n'
        '    <point x="300" y="300"/>\n'
        '  </room>\n'
        '  <room>\n'
        '    <point x="0" y="0"/>\n'
        '    <point x="100" y="0"/>\n'
        '    <point x="100" y="100"/>\n'
        '  </room>\n'
        '  <doorOrWindow name="Door" x="150" y="0" width="91.44"'
        ' depth="11.43" height="203.2"/>\n'
        '  <doorOrWindow name="Slider Window" x="300" y="150"'
        ' width="91.44" depth="11.43" height="121.92"/>\n'
        '</home>\n'
    )
    with tempfile.TemporaryDirectory() as tmp:
        sh3d_path = os.path.join(tmp, "test.sh3d")
        with zipfile.ZipFile(sh3d_path, "w") as zf:
            zf.writestr("Home.xml", home_xml)

        result = import_sh3d(sh3d_path, MagicMock())

    walls = [w for ws in result["wall_sets"] for w in ws]
    rooms = result["rooms"]
    doors = [d for _, d, _ in result["doors"]]
    windows = [w for _, w, _ in result["windows"]]

    assert len(walls) == 2
    assert walls[0].identifier == wall_sh3d_id
    assert is_valid_sh3d_id(walls[1].identifier, "wall")

    assert len(rooms) == 2
    assert rooms[0].identifier == room_sh3d_id
    assert is_valid_sh3d_id(rooms[1].identifier, "room")

    assert len(doors) == 1
    assert is_valid_sh3d_id(doors[0].identifier, "door")

    assert len(windows) == 1
    assert is_valid_sh3d_id(windows[0].identifier, "window")

    # All extracted IDs should be in result["identifiers"] without duplicates
    all_ids = [w.identifier for w in walls]
    all_ids.extend(r.identifier for r in rooms)
    all_ids.extend(d.identifier for d in doors)
    all_ids.extend(w.identifier for w in windows)
    assert len(set(all_ids)) == len(all_ids)
    for ident in all_ids:
        assert ident in result["identifiers"]
