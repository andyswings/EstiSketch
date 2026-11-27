"""Tests for standalone Blender integration using EstiSketch's own 3D assets."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import zipfile

import pytest

from EstiSketch import config
from EstiSketch.Canvas.canvas_area import CanvasArea
from EstiSketch.blender_bridge import estisketch_to_blender as etb
from EstiSketch.blender_bridge.launcher import (
    export_standalone_blender_bundle,
    get_standalone_bridge_script_path,
    is_hb5_installed,
)
from EstiSketch.blender_bridge.live_delta import apply_live_delta
from EstiSketch.native_3d import is_native_3d_available
from EstiSketch.project_io import open_project

REPO_ROOT = Path(__file__).resolve().parent.parent
HOUSE1 = REPO_ROOT / "examples" / "demo_houses" / "house1_gable_2bed_1_5bath_1200sqft.xml"


def test_config_default_blender_asset_source() -> None:
    cfg = config.load_config()
    assert config.DEFAULT_SETTINGS["BLENDER_ASSET_SOURCE"] == "estisketch"
    assert cfg["BLENDER_ASSET_SOURCE"] in ("estisketch", "auto", "hb5")


def test_resolve_backend_choice_and_cli_parsing() -> None:
    assert etb.normalize_asset_source(None) == "estisketch"
    assert etb.normalize_asset_source("HB5") == "hb5"
    assert etb.normalize_asset_source("invalid") == "estisketch"

    assert etb.resolve_backend_choice("estisketch", True, True, True) == "estisketch"
    assert etb.resolve_backend_choice("auto", False, True, True) == "estisketch"
    assert etb.resolve_backend_choice("auto", True, True, True) == "hb5"
    assert etb.resolve_backend_choice("hb5", False, True, True) == "estisketch"
    assert etb.resolve_backend_choice("hb5", True, True, True) == "hb5"

    parsed = etb.parse_cli_args([
        "blender",
        "--python",
        "estisketch_to_blender.py",
        "--",
        "--glb",
        "/tmp/p.glb",
        "--manifest",
        "/tmp/m.json",
        "--sync-dir",
        "/tmp/sync",
        "--asset-source",
        "auto",
    ])
    assert parsed["glb"] == "/tmp/p.glb"
    assert parsed["manifest"] == "/tmp/m.json"
    assert parsed["sync_dir"] == "/tmp/sync"
    assert parsed["asset_source"] == "auto"
    assert Path(get_standalone_bridge_script_path()).is_file()
    assert isinstance(is_hb5_installed(), bool)


@pytest.mark.skipif(not is_native_3d_available(), reason="needs compiled _native_3d extension")
def test_export_standalone_blender_bundle(tmp_path: Path) -> None:
    canvas = CanvasArea(SimpleNamespace(**config.DEFAULT_SETTINGS))
    open_project(canvas, str(HOUSE1))

    glb_path, manifest_path = export_standalone_blender_bundle(canvas, str(tmp_path))
    assert Path(glb_path).is_file()
    assert Path(glb_path).stat().st_size > 1000
    assert Path(manifest_path).is_file()

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert len(manifest["levels"]) == 1
    entities = manifest["entities"]
    assert any(v["kind"] == "wall" for v in entities.values())
    assert any(v["kind"] == "fixture" for v in entities.values())
    assert any(v["kind"] == "roof" for v in entities.values())


_STANDALONE_PROBE = r'''
import json, os, sys
sys.path.insert(0, {src!r})
import bpy
from EstiSketch.blender_bridge import estisketch_to_blender as etb

stats = etb.build_standalone_in_blender(
    glb_path={glb!r},
    manifest_path={manifest!r},
    xml_path={xml!r},
    sync_dir={sync!r},
    asset_source={asset_source!r},
)
fx_objs = [o for o in bpy.data.objects if str(o.get("ESTISKETCH_ID", "")).startswith("fixture-")]
assert fx_objs, "Expected imported fixture objects with ESTISKETCH_ID"
target_fx = fx_objs[0]
target_id = target_fx["ESTISKETCH_ID"]
orig_x = float(target_fx.location.x)
target_fx.location.x = orig_x + 0.5

bpy.ops.mesh.primitive_cube_add(size=0.35, location=(1.2, -0.8, 0.175))
bpy.context.active_object.name = "UserAddedCube"
bpy.ops.wm.save_mainfile()

delta_path = os.path.join({sync!r}, "delta.esk-delta.zip")
out = {{
    "stats": stats,
    "target_id": target_id,
    "delta_exists": os.path.isfile(delta_path),
    "fx_count": len(fx_objs),
}}
print("STANDALONE_PROBE_JSON" + json.dumps(out))
'''


@pytest.mark.skipif(
    shutil.which("blender") is None or not is_native_3d_available(),
    reason="needs Blender and compiled _native_3d extension",
)
@pytest.mark.parametrize("asset_source", ["estisketch", "hb5"])
def test_blender_factory_startup_standalone_without_hb5_and_live_sync(
    tmp_path: Path, asset_source: str
) -> None:
    """Verify Blender builds with --factory-startup (no HB5) and Ctrl+S live syncs back."""
    canvas = CanvasArea(SimpleNamespace(**config.DEFAULT_SETTINGS))
    open_project(canvas, str(HOUSE1))

    sync_dir = tmp_path / f"sync_{asset_source}"
    sync_dir.mkdir()
    glb_path, manifest_path = export_standalone_blender_bundle(canvas, str(sync_dir))

    script = tmp_path / f"probe_{asset_source}.py"
    script.write_text(
        _STANDALONE_PROBE.format(
            src=str(REPO_ROOT / "src"),
            glb=glb_path,
            manifest=manifest_path,
            xml=str(HOUSE1),
            sync=str(sync_dir),
            asset_source=asset_source,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["blender", "-b", "--factory-startup", "--python", str(script)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("STANDALONE_PROBE_JSON")]
    assert lines, proc.stdout[-2000:] + proc.stderr[-2000:]
    out = json.loads(lines[0][len("STANDALONE_PROBE_JSON"):])

    assert out["stats"]["backend"] == "estisketch"
    assert out["stats"]["hb5_fallback"] is (asset_source == "hb5")
    assert out["stats"]["entities"] >= 20
    assert out["fx_count"] >= 10
    assert out["delta_exists"] is True

    delta_zip = sync_dir / "delta.esk-delta.zip"
    with zipfile.ZipFile(delta_zip) as zf:
        manifest = json.loads(zf.read("delta_manifest.json"))
    by_name = {e["name"]: e for e in manifest["objects"]}
    assert "UserAddedCube" in by_name
    moved_entries = [e for e in manifest["objects"] if e["estisketch_id"] == out["target_id"]]
    assert len(moved_entries) == 1

    orig_fx = next(f for f in canvas.fixtures if f.identifier == out["target_id"])
    orig_x = orig_fx.x
    canvas.save_state()
    depth = len(canvas.undo_stack)
    result = apply_live_delta(canvas, delta_zip)
    assert result.applied == 2
    assert len(canvas.undo_stack) == depth + 1
    assert abs(orig_fx.x - orig_x) > 10.0
    assert len(canvas.custom_assets) == 1
