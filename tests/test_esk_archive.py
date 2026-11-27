"""Headless tests for `.esk` ZIP project archives and `.obj`/`.glb` asset import."""

from __future__ import annotations

import json
from pathlib import Path
import struct
from types import SimpleNamespace
import zipfile

import pytest

from EstiSketch import esk_archive, native_3d
from EstiSketch.Canvas.canvas_state import CanvasStateMixin
from EstiSketch.components import BackgroundImage, CustomAsset, Layer, Level, Wall
from EstiSketch.project_io import open_project, save_project
from EstiSketch.scene_ir import build_scene_ir_from_canvas

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakeCanvas(CanvasStateMixin):
    def __init__(self) -> None:
        self.levels = [Level(id="level_0", name="First Floor")]
        self.active_level_id = "level_0"
        self.layers = [Layer(id="layer_0", name="Floor 1", level_id="level_0")]
        self.active_layer_id = "layer_0"
        self.wall_sets: list[list[Wall]] = []
        self.walls: list[Wall] = []
        self.current_wall: Wall | None = None
        self.drawing_wall = False
        self.rooms: list[object] = []
        self.current_room_points: list[tuple[float, float]] = []
        self.floor_openings: list[object] = []
        self.current_opening_points: list[tuple[float, float]] = []
        self.doors: list[object] = []
        self.windows: list[object] = []
        self.fixtures: list[object] = []
        self.roofs: list[object] = []
        self.roof_lines: list[object] = []
        self.stairs: list[object] = []
        self.custom_assets: list[CustomAsset] = []
        self.overrides_3d: dict[str, dict[str, object]] = {}
        self.views_3d: dict[str, object] = {}
        self.blender_sync_state: dict[str, object] = {}
        self.blueprints: list[BackgroundImage] = []
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
        self.pixels_per_inch = 2.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.zoom = 1.0
        self.default_wall_type = "framed"
        self.default_wall_width = 5.5
        self.default_wall_height = 96.0
        self.roof_overhang = 12.0
        self.cut_lower_ceiling_under_stairs = True
        self.north_angle = 0.0
        self.ghost_level_id = ""
        self.ghost_opacity = 0.25
        self.config = SimpleNamespace(
            UNDO_REDO_LIMIT=50,
            PIXELS_PER_INCH=2.0,
            SHOW_DESIGN=True,
            SHOW_GRID=True,
            SNAP_ENABLED=True,
        )
        self.undo_stack: list[dict[str, object]] = []
        self.redo_stack: list[dict[str, object]] = []
        self.emitted_signals: list[str] = []
        self.queue_draw_calls = 0

    def emit(self, signal_name: str, *_args: object) -> None:
        self.emitted_signals.append(signal_name)

    def queue_draw(self) -> None:
        self.queue_draw_calls += 1

    def get_active_layer(self) -> Layer:
        return self.layers[0]

    def rebuild_groups_index(self) -> None:
        pass


def _minimal_glb() -> bytes:
    """Construct a valid minimal 1-triangle binary glTF 2.0 payload."""
    verts = struct.pack(
        "<9f",
        -0.5, -0.25, 0.0,
        0.5, -0.25, 0.0,
        0.0, 0.5, 1.0,
    )
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
                "min": [-0.5, -0.25, 0.0],
                "max": [0.5, 0.5, 1.0],
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
    header = struct.pack("<III", 0x46546C67, 2, total)
    j_chunk = struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes
    b_chunk = struct.pack("<II", len(bin_bytes), 0x004E4942) + bin_bytes
    return header + j_chunk + b_chunk


def _write_sample_obj(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "o TestCrate",
                "v -0.5 -0.4 0.0",
                "v 0.5 -0.4 0.0",
                "v 0.5 0.4 0.0",
                "v -0.5 0.4 0.0",
                "v -0.5 -0.4 0.8",
                "v 0.5 -0.4 0.8",
                "v 0.5 0.4 0.8",
                "v -0.5 0.4 0.8",
                "f 1 2 3 4",
                "f 5 6 7 8",
                "f 1 2 6 5",
                "f 2 3 7 6",
                "f 3 4 8 7",
                "f 4 1 5 8",
            ]
        ),
        encoding="utf-8",
    )


def test_esk_archive_layout_blueprints_and_legacy_xml_roundtrip(tmp_path: Path) -> None:
    """`.esk` archives store normalized ZIP entries while `.xml` remains untouched."""
    canvas = _FakeCanvas()
    wall = Wall(
        start=(0.0, 0.0),
        end=(120.0, 0.0),
        width=5.5,
        height=96.0,
        exterior_wall=True,
        identifier="wall_ext_1",
        layer_id="layer_0",
    )
    wall.custom_3d_override = "assets/override_wall_ext_1.glb"
    canvas.wall_sets.append([wall])
    canvas.views_3d = {
        "view_preset": "top",
        "dollhouse_level": "level_0",
        "auto_hide_roofs": False,
        "render_style": "clay",
        "ssao_enabled": False,
        "time_of_day": 15.25,
    }
    glb_payload = _minimal_glb()
    asset = CustomAsset(
        identifier="custom_asset_chair",
        name="Accent Chair",
        glb_rel_path="assets/chair.glb",
        x=48.0,
        y=36.0,
        z=0.0,
        rotation=45.0,
        silhouette_2d=[(-12.0, -12.0), (12.0, -12.0), (12.0, 12.0), (-12.0, 12.0)],
        glb_bytes=glb_payload,
        level_id="level_0",
        layer_id="layer_0",
    )
    canvas.custom_assets.append(asset)
    canvas.overrides_3d["wall_ext_1"] = {
        "glb_rel_path": "assets/override_wall_ext_1.glb",
        "mesh_hash": "deadbeef12345678",
        "glb_bytes": glb_payload,
    }
    canvas.blender_sync_state = {
        "schema_version": 1,
        "mesh_hashes": {"wall_ext_1": "deadbeef12345678"},
    }
    bp = BackgroundImage(
        identifier="bp_1",
        image_path="plan.png",
        image_data=_TINY_PNG,
        level_id="level_0",
    )
    canvas.blueprints.append(bp)

    esk_path = tmp_path / "house.esk"
    save_project(canvas, 1280, 800, str(esk_path), preview_png=_TINY_PNG)
    assert esk_archive.is_esk_archive(esk_path)

    with zipfile.ZipFile(esk_path, "r") as zf:
        names = set(zf.namelist())
        assert {
            "manifest.json",
            "project.xml",
            "views.json",
            "overrides_3d.json",
            "sync/blender_state.json",
            "preview.png",
            "assets/chair.glb",
            "assets/override_wall_ext_1.glb",
        }.issubset(names)
        assert any(n.startswith("blueprints/") for n in names)
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["format"] == "esk"
        assert manifest["version"] == 1
        xml_text = zf.read("project.xml").decode("utf-8")
        assert 'archive_path="blueprints/' in xml_text
        assert "iVBOR" not in xml_text

    loaded = _FakeCanvas()
    w, h = open_project(loaded, str(esk_path))
    assert (w, h) == (1280, 800)
    assert loaded.views_3d["render_style"] == "clay"
    assert loaded.views_3d["time_of_day"] == pytest.approx(15.25)
    assert loaded.wall_sets[0][0].custom_3d_override == "assets/override_wall_ext_1.glb"
    assert len(loaded.custom_assets) == 1
    assert loaded.custom_assets[0].name == "Accent Chair"
    assert loaded.custom_assets[0].glb_bytes == glb_payload
    assert len(loaded.blueprints) == 1
    assert loaded.blueprints[0].image_data == _TINY_PNG
    assert loaded.blender_sync_state["mesh_hashes"] == {"wall_ext_1": "deadbeef12345678"}

    xml_path = tmp_path / "legacy.xml"
    save_project(loaded, 1024, 768, str(xml_path))
    assert not esk_archive.is_esk_archive(xml_path)
    xml_loaded = _FakeCanvas()
    w2, h2 = open_project(xml_loaded, str(xml_path))
    assert (w2, h2) == (1024, 768)
    assert len(xml_loaded.wall_sets) == 1


def test_import_obj_and_glb_asset_produces_hull_and_scene_ir(tmp_path: Path) -> None:
    """Importing an `.obj` converts to `.glb`, computes a convex silhouette, and emits SceneIR."""
    obj_path = tmp_path / "crate.obj"
    _write_sample_obj(obj_path)
    out_glb = tmp_path / "crate.glb"

    info = native_3d.import_3d_asset_to_glb(obj_path, out_glb)
    assert out_glb.is_file()
    assert out_glb.read_bytes()[:4] == b"glTF"
    assert info.triangle_count == 12
    assert len(info.silhouette_2d_m) == 4
    assert len(info.mesh_hash) == 16

    reinspected = native_3d.inspect_3d_asset(out_glb)
    assert reinspected.triangle_count == 12
    assert reinspected.mesh_hash == info.mesh_hash

    canvas = _FakeCanvas()
    canvas.save_state()
    in_per_m = 1.0 / 0.0254
    asset = CustomAsset(
        name="Crate",
        glb_rel_path="assets/crate.glb",
        x=60.0,
        y=24.0,
        rotation=90.0,
        silhouette_2d=[(x * in_per_m, y * in_per_m) for x, y in info.silhouette_2d_m],
        glb_bytes=out_glb.read_bytes(),
        level_id="level_0",
        layer_id="layer_0",
    )
    canvas.custom_assets.append(asset)
    canvas.save_state()

    world_poly = asset.world_silhouette()
    assert len(world_poly) == 4
    cache_dir = esk_archive.materialize_project_assets(canvas)
    assert (cache_dir / "assets" / "crate.glb").is_file()

    scene_ir = build_scene_ir_from_canvas(canvas)
    assert len(scene_ir.custom_assets) == 1
    assert scene_ir.custom_assets[0].path.endswith("assets/crate.glb")

    canvas.undo()
    assert canvas.custom_assets == []
    canvas.redo()
    assert len(canvas.custom_assets) == 1
