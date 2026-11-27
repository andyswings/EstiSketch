"""Headless tests for the Two-Tier Blender Sync protocol and delta import."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import struct
from types import SimpleNamespace
import zipfile

import pytest

from EstiSketch.Canvas.canvas_state import CanvasStateMixin
from EstiSketch.blender_bridge import blender_sync
from EstiSketch.components import CustomAsset
from EstiSketch.scene_ir.parsed import INCH_TO_M


@dataclass
class _Level:
    id: str
    name: str
    elevation: float = 0.0
    height: float = 96.0
    floor_thickness: float = 10.0


@dataclass
class _Layer:
    id: str
    name: str = "Floor 1"
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
    level_id: str = "level_0"


@dataclass
class _Wall:
    identifier: str
    start: tuple[float, float]
    end: tuple[float, float]
    width: float = 5.5
    height: float = 96.0
    height_at_end: float = 96.0
    exterior_wall: bool = True
    layer_id: str = "layer_0"
    visible: bool = True
    locked: bool = False
    custom_3d_override: str = ""
    custom_name: str = ""
    comment: str = ""
    interior_finish: str = "drywall"
    exterior_finish: str = "siding"
    left_finish: str = ""
    right_finish: str = ""
    wall_color: str = "#ffffff"


@dataclass
class _Fixture:
    identifier: str
    symbol: str = "sofa"
    x: float = 48.0
    y: float = 48.0
    rotation: float = 0.0
    width: float = 72.0
    depth: float = 36.0
    height: float = 32.0
    layer_id: str = "layer_0"
    level_id: str = "level_0"
    visible: bool = True
    locked: bool = False
    custom_3d_override: str = ""
    custom_name: str = ""
    comment: str = ""


class _SyncCanvas(CanvasStateMixin):
    def __init__(self) -> None:
        self.levels = [_Level(id="level_0", name="First Floor")]
        self.active_level_id = "level_0"
        self.layers = [_Layer(id="layer_0")]
        self.active_layer_id = "layer_0"
        self.wall_sets: list[list[_Wall]] = [
            [_Wall(identifier="wall_1", start=(0.0, 0.0), end=(120.0, 0.0))]
        ]
        self.walls: list[_Wall] = []
        self.current_wall: _Wall | None = None
        self.drawing_wall = False
        self.rooms: list[object] = []
        self.current_room_points: list[tuple[float, float]] = []
        self.floor_openings: list[object] = []
        self.current_opening_points: list[tuple[float, float]] = []
        self.doors: list[object] = []
        self.windows: list[object] = []
        self.fixtures: list[_Fixture] = [_Fixture(identifier="fix_sofa")]
        self.roofs: list[object] = []
        self.roof_lines: list[object] = []
        self.stairs: list[object] = []
        self.custom_assets: list[CustomAsset] = []
        self.overrides_3d: dict[str, dict[str, object]] = {}
        self.views_3d: dict[str, object] = {}
        self.blender_sync_state: dict[str, object] = {}
        self.blueprints: list[object] = []
        self.texts: list[object] = []
        self.dimensions: list[object] = []
        self.dimension_chains: list[object] = []
        self.leader_callouts: list[object] = []
        self.circles: list[object] = []
        self.arcs: list[object] = []
        self.polylines: list[object] = []
        self.polyline_sets: list[list[object]] = []
        self.groups: list[object] = []
        self.selected_items: list[object] = []
        self.north_angle = 0.0
        self.cut_lower_ceiling_under_stairs = True
        self.config = SimpleNamespace(UNDO_REDO_LIMIT=50)
        self.undo_stack: list[dict[str, object]] = []
        self.redo_stack: list[dict[str, object]] = []
        self.emitted: list[str] = []

    def emit(self, name: str, *_args: object) -> None:
        self.emitted.append(name)

    def queue_draw(self) -> None:
        pass

    def get_active_layer(self) -> _Layer:
        return self.layers[0]

    def rebuild_groups_index(self) -> None:
        pass


def _valid_triangle_glb() -> bytes:
    verts = struct.pack("<9f", -0.4, -0.3, 0.0, 0.4, -0.3, 0.0, 0.0, 0.4, 0.9)
    doc = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(verts)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(verts)}],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [-0.4, -0.3, 0.0],
                "max": [0.4, 0.4, 0.9],
            }
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
    }
    json_bytes = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    while len(json_bytes) % 4 != 0:
        json_bytes += b" "
    bin_bytes = verts + (b"\x00" * ((4 - len(verts) % 4) % 4))
    total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    return b"".join(
        [
            struct.pack("<III", 0x46546C67, 2, total),
            struct.pack("<II", len(json_bytes), 0x4E4F534A),
            json_bytes,
            struct.pack("<II", len(bin_bytes), 0x004E4942),
            bin_bytes,
        ]
    )


def test_push_to_blender_exports_glb_with_entity_extras(tmp_path: Path) -> None:
    """Sync bundle exports valid `.glb` with embedded `estisketch_id` metadata."""
    canvas = _SyncCanvas()
    res = blender_sync.export_gltf_sync_bundle(canvas, tmp_path / "sync_out")
    assert res.glb_path.is_file()
    assert res.manifest_path.is_file()
    assert res.bootstrap_path.is_file()
    assert res.entity_count >= 2

    raw = res.glb_path.read_bytes()
    assert raw[:4] == b"glTF"
    json_len, chunk_type = struct.unpack("<II", raw[12:20])
    assert chunk_type == 0x4E4F534A
    doc = json.loads(raw[20:20 + json_len].decode("utf-8"))
    extras_ids = {
        node.get("extras", {}).get("estisketch_id")
        for node in doc.get("nodes", [])
    }
    assert "wall_1" in extras_ids
    assert "fix_sofa" in extras_ids


def test_classify_and_apply_blender_delta_two_tiers_and_boilerplate(tmp_path: Path) -> None:
    """Verify Tier 1, Tier 2A, Tier 2B, boilerplate filtering, single Undo, and reset."""
    canvas = _SyncCanvas()
    bundle = blender_sync.export_gltf_sync_bundle(canvas, tmp_path / "sync_out")
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    plan_center = manifest["plan_center_in"]

    glb_sculpt = _valid_triangle_glb()
    glb_island = _valid_triangle_glb()
    delta_zip = tmp_path / "changes.esk-delta.zip"
    delta_manifest = {
        "schema_version": 1,
        "plan_center_in": plan_center,
        "objects": [
            {
                "name": "EstiSketch_Camera",
                "blender_type": "CAMERA",
                "estisketch_id": "",
            },
            {
                "name": "Default_Helper_ESTISKETCH_IGNORE",
                "blender_type": "MESH",
                "estisketch_id": "",
            },
            {
                "name": "Cube",
                "blender_type": "MESH",
                "estisketch_id": "",
            },
            {
                "name": "Sofa_Parametric",
                "blender_type": "MESH",
                "estisketch_id": "fix_sofa",
                "mesh_modified": False,
                "loc_m": [1.0, -0.5, 0.0],
                "rot_z_rad": -math.pi / 4.0,
            },
            {
                "name": "Wall_Sculpted",
                "blender_type": "MESH",
                "estisketch_id": "wall_1",
                "mesh_modified": True,
                "mesh_hash": "abc1234567890001",
                "glb": "assets/wall_1_override.glb",
            },
            {
                "name": "Custom_Kitchen_Island",
                "blender_type": "MESH",
                "estisketch_id": "",
                "loc_m": [2.0, -1.0, 0.0],
                "rot_z_rad": 0.0,
                "scale": [1.0, 1.0, 1.0],
                "glb": "assets/island.glb",
            },
        ],
    }
    with zipfile.ZipFile(delta_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("delta_manifest.json", json.dumps(delta_manifest))
        zf.writestr("assets/wall_1_override.glb", glb_sculpt)
        zf.writestr("assets/island.glb", glb_island)

    canvas.save_state()
    initial_undo_depth = len(canvas.undo_stack)

    plan = blender_sync.classify_blender_delta(canvas, delta_zip)
    assert plan.ignored_count == 3
    tiers = [item.tier for item in plan.items]
    assert tiers == ["parametric", "override_3d", "custom_asset"]

    applied, warnings = blender_sync.apply_delta_import_plan(canvas, plan)
    assert applied == 3
    assert warnings == []
    # Entire multi-tier import is committed in a single atomic Undo snapshot.
    assert len(canvas.undo_stack) == initial_undo_depth + 1

    # Tier 1 updated fixture coordinates/rotation
    sofa = canvas.fixtures[0]
    assert sofa.x == pytest.approx(plan_center[0] + (1.0 / INCH_TO_M))
    assert sofa.rotation == pytest.approx(45.0)

    # Tier 2A attached visual override while keeping parametric wall intact
    wall = canvas.wall_sets[0][0]
    assert wall.custom_3d_override == "assets/override_wall_1.glb"
    assert "wall_1" in canvas.overrides_3d

    # Tier 2B added CustomAsset with projected 2D silhouette
    assert len(canvas.custom_assets) == 1
    assert canvas.custom_assets[0].name == "Custom_Kitchen_Island"
    assert len(canvas.custom_assets[0].silhouette_2d) == 3

    # Resetting Tier 2A reverts to pure parametric geometry (pushes 1 undo snapshot)
    assert blender_sync.reset_object_to_parametric(canvas, "wall_1")
    assert wall.custom_3d_override == ""
    assert "wall_1" not in canvas.overrides_3d

    # Undo 1 restores the override; Undo 2 rolls back the entire delta import atomically
    canvas.undo()
    assert canvas.wall_sets[0][0].custom_3d_override == "assets/override_wall_1.glb"
    canvas.undo()
    assert len(canvas.custom_assets) == 0


def test_locked_object_refuses_blender_delta(tmp_path: Path) -> None:
    """Locked objects must not be mutated by incoming Blender delta updates."""
    canvas = _SyncCanvas()
    canvas.fixtures[0].locked = True
    delta_zip = tmp_path / "locked.esk-delta.zip"
    with zipfile.ZipFile(delta_zip, "w") as zf:
        zf.writestr(
            "delta_manifest.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "plan_center_in": [0.0, 0.0],
                    "objects": [
                        {
                            "name": "Locked_Sofa",
                            "blender_type": "MESH",
                            "estisketch_id": "fix_sofa",
                            "mesh_modified": False,
                            "loc_m": [5.0, -5.0, 0.0],
                        }
                    ],
                }
            ),
        )

    plan = blender_sync.classify_blender_delta(canvas, delta_zip)
    applied, warnings = blender_sync.apply_delta_import_plan(canvas, plan)
    assert applied == 0
    assert len(warnings) == 1
    assert canvas.fixtures[0].x == 48.0
