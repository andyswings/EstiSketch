"""Headless unit tests for EstiSketch SceneIR extraction, diffing, and Rust FFI."""

from __future__ import annotations

import copy
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from EstiSketch import native_3d
from EstiSketch.scene_ir import (
    SCENE_IR_SCHEMA_VERSION,
    RoomIR,
    SceneIR,
    build_scene_ir,
    build_scene_ir_from_canvas,
    build_scene_ir_from_xml,
    diff_scene_ir,
    parse_estisketch_canvas,
    parse_estisketch_xml,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SIMPLE_HOUSE_XML = REPO_ROOT / "simple_house.xml"
DEMO_HOUSES_DIR = REPO_ROOT / "examples" / "demo_houses"


@dataclass
class _StubLevel:
    id: str
    name: str
    elevation: float
    height: float
    floor_thickness: float = 10.0


@dataclass
class _StubLayer:
    id: str
    name: str = "Layer"
    visible: bool = True
    locked: bool = False
    level_id: str = ""


@dataclass
class _StubWall:
    identifier: str
    start: tuple[float, float]
    end: tuple[float, float]
    width: float = 5.5
    height: float = 96.0
    height_at_end: float = 96.0
    exterior_wall: bool = True
    layer_id: str = "layer_0"
    visible: bool = True
    symbolic: bool = False
    is_curved: bool = False
    arc_center: tuple[float, float] | None = None
    arc_radius: float | None = None
    interior_finish: str = "Drywall"
    exterior_finish: str = "Siding"
    left_finish: str = "Drywall"
    right_finish: str = "Siding"
    left_color: tuple[float, float, float] | None = (0.9, 0.9, 0.9)
    right_color: tuple[float, float, float] | None = None
    left_baseboard: bool = True
    right_baseboard: bool = False
    footer: bool = True
    footer_left_offset: float = 6.0
    footer_right_offset: float = 6.0
    footer_depth: float = 8.0


@dataclass
class _StubRoom:
    identifier: str
    name: str
    points: list[tuple[float, float]]
    height: float = 96.0
    layer_id: str = "layer_0"
    visible: bool = True
    floor_type: str = "default"
    is_slab: bool = False
    slab_thickness: float = 4.0
    floor_pattern: str = "wood_plank"
    pattern_rotation: float = 0.0
    pattern_scale: float = 1.0
    room_type: str = "living"
    wall_finish: str = "Paint"


@dataclass
class _StubDoor:
    identifier: str
    door_type: str = "single"
    width: float = 36.0
    height: float = 80.0
    swing: str = "left"
    orientation: str = "inswing"
    layer_id: str = "layer_0"
    visible: bool = True


@dataclass
class _StubWindow:
    identifier: str
    window_type: str = "sliding"
    width: float = 48.0
    height: float = 36.0
    layer_id: str = "layer_0"
    visible: bool = True


@dataclass
class _StubCanvas:
    levels: list[_StubLevel] = field(default_factory=list)
    layers: list[_StubLayer] = field(default_factory=list)
    wall_sets: list[list[_StubWall]] = field(default_factory=list)
    rooms: list[_StubRoom] = field(default_factory=list)
    doors: list[tuple[object, object, float]] = field(default_factory=list)
    windows: list[tuple[object, object, float]] = field(default_factory=list)
    roofs: list[object] = field(default_factory=list)
    stairs: list[object] = field(default_factory=list)
    floor_openings: list[object] = field(default_factory=list)
    fixtures: list[object] = field(default_factory=list)
    cut_lower_ceiling_under_stairs: bool = False
    north_angle: float = 25.0


def _sample_xml_paths() -> list[Path]:
    paths: list[Path] = [SIMPLE_HOUSE_XML]
    if DEMO_HOUSES_DIR.is_dir():
        paths.extend(sorted(DEMO_HOUSES_DIR.glob("*.xml")))
    return paths


def test_build_scene_ir_does_not_mutate_parsed_project() -> None:
    parsed = parse_estisketch_xml(str(SIMPLE_HOUSE_XML))
    snapshot = copy.deepcopy(parsed)
    ir = build_scene_ir(parsed)
    assert ir.schema_version == SCENE_IR_SCHEMA_VERSION
    assert parsed == snapshot


@pytest.mark.parametrize("xml_path", _sample_xml_paths(), ids=lambda p: p.name)
def test_build_scene_ir_all_sample_projects(xml_path: Path) -> None:
    ir = build_scene_ir_from_xml(str(xml_path))
    assert ir.schema_version == SCENE_IR_SCHEMA_VERSION
    assert len(ir.levels) >= 1
    assert len(ir.walls) >= 1
    payload = ir.to_json()
    assert '"schema_version": 1' in payload
    for w in ir.walls:
        assert w.segments, f"Wall {w.id} has no segments"


def test_parse_estisketch_canvas_and_build_scene_ir() -> None:
    w0 = _StubWall(identifier="w_south", start=(0.0, 0.0), end=(240.0, 0.0))
    w1 = _StubWall(identifier="w_east", start=(240.0, 0.0), end=(240.0, 180.0))
    w2 = _StubWall(identifier="w_north", start=(240.0, 180.0), end=(0.0, 180.0))
    w3 = _StubWall(identifier="w_west", start=(0.0, 180.0), end=(0.0, 0.0))
    room = _StubRoom(
        identifier="r_main",
        name="Main Room",
        points=[(0.0, 0.0), (240.0, 0.0), (240.0, 180.0), (0.0, 180.0)],
    )
    door = _StubDoor(identifier="d_entry")
    win = _StubWindow(identifier="win_east")
    canvas = _StubCanvas(
        levels=[_StubLevel(id="lvl_1", name="First Floor", elevation=0.0, height=96.0)],
        layers=[_StubLayer(id="layer_0", level_id="lvl_1")],
        wall_sets=[[w0, w1, w2, w3]],
        rooms=[room],
        doors=[(w0, door, 0.5)],
        windows=[(w1, win, 0.5)],
    )

    parsed = parse_estisketch_canvas(canvas)
    assert parsed.north_angle == pytest.approx(25.0)
    assert len(parsed.walls) == 4
    assert len(parsed.doors) == 1
    assert len(parsed.windows) == 1

    ir = build_scene_ir_from_canvas(canvas)
    assert ir.plan_center_in == pytest.approx((120.0, 90.0))
    assert len(ir.walls) == 4
    assert len(ir.openings) == 2
    assert len(ir.footers) == 4
    assert len(ir.rooms) == 1
    # Hosted cuts should be recorded on the host wall segments.
    cuts_w0 = ir.walls[0].segments[0].opening_cuts
    assert len(cuts_w0) == 1
    assert cuts_w0[0].opening_id == "d_entry"


def test_diff_scene_ir_detects_adds_updates_and_removals() -> None:
    prev = build_scene_ir_from_xml(str(SIMPLE_HOUSE_XML))
    curr = copy.deepcopy(prev)
    removed_id = curr.walls.pop().id
    curr.rooms.append(
        RoomIR(
            id="room_extra",
            level_id=curr.levels[0].id,
            name="Loft",
            outer_m=[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]],
        )
    )
    delta = diff_scene_ir(prev, curr)
    assert removed_id in delta.removed_ids
    assert [r.id for r in delta.rooms] == ["room_extra"]
    assert delta.walls == []


def test_native_3d_round_trip_and_session() -> None:
    if not native_3d.is_native_3d_available():
        pytest.skip(f"_native_3d not built: {native_3d.native_3d_load_error()}")

    assert native_3d.native_schema_version() == SCENE_IR_SCHEMA_VERSION
    ir = build_scene_ir_from_xml(str(SIMPLE_HOUSE_XML))

    echoed = native_3d.echo_scene_ir(ir)
    assert echoed["schema_version"] == SCENE_IR_SCHEMA_VERSION
    echoed_walls = echoed["walls"]
    assert isinstance(echoed_walls, list)
    assert len(echoed_walls) == len(ir.walls)

    summary = native_3d.summarize_scene_ir(ir)
    assert summary["wall_count"] == len(ir.walls)
    assert summary["room_count"] == len(ir.rooms)

    session = native_3d.create_native_session()
    loaded = session.load_scene(ir.to_json())
    assert '"wall_count"' in loaded
    assert session.entity_count() > 0

    curr = copy.deepcopy(ir)
    removed_wall_id = curr.walls.pop().id
    delta = diff_scene_ir(ir, curr)
    session.upsert_entities(delta.to_json())
    assert session.entity_count() == ir_count(curr)

    with pytest.raises(ValueError):
        native_3d.echo_scene_ir(SceneIR(schema_version=99).to_json())
    assert removed_wall_id in delta.removed_ids


@pytest.mark.parametrize("xml_path", _sample_xml_paths(), ids=lambda p: p.name)
def test_native_3d_meshing_and_glb_export(xml_path: Path, tmp_path: Path) -> None:
    if not native_3d.is_native_3d_available():
        pytest.skip(f"_native_3d not built: {native_3d.native_3d_load_error()}")

    ir = build_scene_ir_from_xml(str(xml_path))
    stats = native_3d.scene_mesh_stats(ir)
    part_count = stats["part_count"]
    tri_count = stats["triangle_count"]
    assert isinstance(part_count, int) and part_count > 0
    assert isinstance(tri_count, int) and tri_count > 10

    glb_path = tmp_path / f"{xml_path.stem}.glb"
    written = native_3d.export_scene_glb(ir, glb_path)
    assert written == glb_path.stat().st_size
    raw = glb_path.read_bytes()
    magic, version, total_len = struct.unpack("<III", raw[:12])
    assert magic == 0x46546C67
    assert version == 2
    assert total_len == len(raw)

    json_len, json_type = struct.unpack("<II", raw[12:20])
    assert json_type == 0x4E4F534A
    json_slice = raw[20 : 20 + json_len]  # noqa: E203
    doc = json.loads(json_slice.decode("utf-8"))
    assert doc["asset"]["version"] == "2.0"
    assert len(doc["nodes"]) == part_count
    assert doc["nodes"][0]["extras"]["estisketch_id"]


def ir_count(ir: SceneIR) -> int:
    collections: tuple[list[object], ...] = (
        list(ir.walls),
        list(ir.openings),
        list(ir.rooms),
        list(ir.roofs),
        list(ir.footers),
        list(ir.rim_bands),
        list(ir.stairs),
        list(ir.fixtures),
        list(ir.custom_assets),
    )
    return sum(len(items) for items in collections)
