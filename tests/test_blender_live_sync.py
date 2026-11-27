"""Tests for the one-click Open-in-Blender round trip (save in Blender -> applied in EstiSketch)."""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from EstiSketch.blender_bridge import blender_live_sync as bls
from EstiSketch.blender_bridge.live_delta import DeltaWatcher, apply_live_delta
from EstiSketch.scene_ir import (
    compute_centered_fixture_transform,
    compute_hb5_fixture_transform,
    parse_estisketch_xml,
)
from test_blender_sync import _Fixture, _SyncCanvas
from test_esk_archive import _minimal_glb

REPO_ROOT = Path(__file__).resolve().parent.parent
HOUSE2 = REPO_ROOT / "examples" / "demo_houses"
HOUSE2 /= "house2_two_story_3bed_2bath_garage_1800sqft.xml"


class _FakeObj:
    """Duck-typed stand-in for ``bpy.types.Object`` (custom props via ``get``)."""

    def __init__(self, name: str, props: dict[str, object] | None = None, **kw: object) -> None:
        self.name = name
        self.type = kw.get("type", "MESH")
        self.parent = kw.get("parent")
        self.location = kw.get("location", (0.0, 0.0, 0.0))
        self.rotation_euler = kw.get("rotation_euler", (0.0, 0.0, 0.0))
        self.scale = (1.0, 1.0, 1.0)
        self._props = props or {}

    def get(self, key: str, default: object = None) -> object:
        return self._props.get(key, default)


def test_center_from_origin_matches_hb5_and_centered_fixture_transforms() -> None:
    """The HB5 back-left origin plus the recorded offset reproduces the centered fixture pose."""
    project = parse_estisketch_xml(str(HOUSE2))
    cx, cy = 0.0, 0.0
    checked = 0
    for fx in project.fixtures:
        for rot in (0.0, 90.0, 33.0, 270.0):
            fx.rotation = rot
            loc_hb5, rot_hb5 = compute_hb5_fixture_transform(fx, 0.0, cx, cy)
            loc_ctr, _ = compute_centered_fixture_transform(fx, 0.0, cx, cy)
            offset = (fx.width * 0.0254 / 2.0, -fx.depth * 0.0254 / 2.0)
            got = bls.center_from_origin(loc_hb5, rot_hb5, offset)
            assert got[0] == pytest.approx(loc_ctr[0], abs=1e-6)
            assert got[1] == pytest.approx(loc_ctr[1], abs=1e-6)
            checked += 1
    assert checked > 50


def test_classify_object_rules() -> None:
    gen = {"ESTISKETCH_GEN": True}
    base = [0.0, 0.0, 0.0, 0.0]
    assert bls.classify_object(_FakeObj("Cabinet", {**gen, "ESTISKETCH_ID": "a",
                                                    "ESTISKETCH_BASE": base})) == "unchanged"
    assert bls.classify_object(
        _FakeObj("Cabinet", {**gen, "ESTISKETCH_ID": "a", "ESTISKETCH_BASE": base},
                 location=(0.5, 0.0, 0.0))
    ) == "moved"
    assert bls.classify_object(_FakeObj("Bay", gen)) == "skip"
    assert bls.classify_object(_FakeObj("MyShelf")) == "new"
    assert bls.classify_object(_FakeObj("Lamp", type="LIGHT")) == "skip"
    assert bls.classify_object(_FakeObj("Child", parent=object())) == "skip"
    assert bls.classify_object(_FakeObj("EstiSketch_Sun")) == "skip"
    assert bls.classify_object(_FakeObj("Helper_ESTISKETCH_IGNORE")) == "skip"


def test_build_entry_applies_center_offset_and_z_offset() -> None:
    obj = _FakeObj(
        "Cab",
        {"ESTISKETCH_CENTER_OFFSET": [0.5, -0.25], "ESTISKETCH_Z_OFFSET_M": 1.0},
        location=(1.0, 2.0, 1.0),
        rotation_euler=(0.0, 0.0, 1.5707963267948966),
    )
    entry = bls.build_entry(obj, "fx")
    # Local (0.5, -0.25) rotated +90 deg -> (0.25, 0.5)
    assert entry["loc_m"] == pytest.approx([1.25, 2.5, 0.0])
    assert entry["rot_z_rad"] == pytest.approx(1.5707963267948966)


def test_delta_watcher_reports_each_new_delta_once(tmp_path: Path) -> None:
    watcher = DeltaWatcher(tmp_path)
    assert watcher.poll() is None
    delta = tmp_path / "delta.esk-delta.zip"
    delta.write_bytes(b"one")
    assert watcher.poll() == delta
    assert watcher.poll() is None
    delta.write_bytes(b"second-version")
    assert watcher.poll() == delta


def _hb5_installed() -> bool:
    patterns = [
        os.path.expanduser("~/.config/blender/*/extensions/*/home_builder_5"),
        os.path.expanduser("~/.config/blender/*/scripts/addons/home_builder_5"),
    ]
    return any(glob.glob(p) for p in patterns)


_PROBE = r'''
import json, sys
sys.path.insert(0, {src!r})
import bpy
from EstiSketch.blender_bridge import estisketch_to_hb5 as m

stats = m.build_in_blender({xml!r}, sync_dir={sync!r}, custom_assets_json={assets!r})
out = {{"stats": stats}}
cab = next(o for o in bpy.data.objects if o.get("ESTISKETCH_CENTER_OFFSET") and o.get("ESTISKETCH_ID"))
out["cab_id"] = cab["ESTISKETCH_ID"]
out["cab_loc_before"] = list(cab.location)
out["custom_ids"] = [o["ESTISKETCH_ID"] for o in bpy.data.objects
                     if str(o.get("ESTISKETCH_ID", "")).startswith("custom_asset-seed")]
cab.location.x += 0.5
bpy.ops.mesh.primitive_cube_add(size=0.4, location=(1.0, 1.0, 0.2))
bpy.context.active_object.name = "MyShelf"
bpy.ops.wm.save_mainfile()
import os
delta = os.path.join({sync!r}, "delta.esk-delta.zip")
out["delta_exists"] = os.path.isfile(delta)
mtime = os.path.getmtime(delta) if out["delta_exists"] else 0
bpy.ops.wm.save_mainfile()
out["second_save_rewrote"] = os.path.getmtime(delta) != mtime
print("PROBE_JSON" + json.dumps(out))
'''


@pytest.mark.skipif(
    shutil.which("blender") is None or not _hb5_installed(),
    reason="needs Blender and the Home Builder 5 extension",
)
def test_blender_save_sends_delta_back_and_applies(tmp_path: Path) -> None:
    sync = tmp_path / "session"
    sync.mkdir()
    xml = sync / "house.xml"
    shutil.copyfile(HOUSE2, xml)
    assets = sync / "custom_assets.json"
    glb = sync / "seed.glb"
    glb.write_bytes(_minimal_glb())
    assets.write_text(
        json.dumps(
            [
                {
                    "identifier": "custom_asset-seed1",
                    "name": "Seed",
                    "glb": str(glb),
                    "x": 100.0,
                    "y": 100.0,
                    "z": 0.0,
                    "rotation": 0.0,
                    "scale": [1.0, 1.0, 1.0],
                    "level_elevation_in": 0.0,
                }
            ]
        )
    )
    script = tmp_path / "probe.py"
    script.write_text(
        _PROBE.format(src=str(REPO_ROOT / "src"), xml=str(xml), sync=str(sync), assets=str(assets))
    )
    proc = subprocess.run(
        ["blender", "-b", "--python", str(script)],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("PROBE_JSON")]
    assert lines, proc.stdout[-2000:] + proc.stderr[-2000:]
    out = json.loads(lines[0][len("PROBE_JSON"):])  # noqa: E203

    assert out["stats"]["custom_assets"] == 1
    assert out["custom_ids"] == ["custom_asset-seed1"]
    assert out["delta_exists"] is True
    assert out["second_save_rewrote"] is False

    delta = sync / "delta.esk-delta.zip"
    with zipfile.ZipFile(delta) as zf:
        manifest = json.loads(zf.read("delta_manifest.json"))
        names = set(zf.namelist())
    by_name = {e["name"]: e for e in manifest["objects"]}
    assert "MyShelf" in by_name and by_name["MyShelf"]["glb"] in names
    moved = next(e for e in manifest["objects"] if e["estisketch_id"] == out["cab_id"])
    assert len(manifest["objects"]) == 2, [e["name"] for e in manifest["objects"]]
    assert moved["blender_type"] == "MESH" or moved["blender_type"] == "EMPTY"

    canvas = _SyncCanvas()
    canvas.fixtures = [_Fixture(identifier=out["cab_id"], x=0.0, y=0.0)]
    canvas.save_state()
    depth = len(canvas.undo_stack)
    result = apply_live_delta(canvas, delta)
    assert result.applied == 2, result
    assert len(canvas.undo_stack) == depth + 1
    assert len(canvas.custom_assets) == 1
    assert canvas.custom_assets[0].identifier == by_name["MyShelf"]["new_estisketch_id"]
    assert canvas.fixtures[0].x != 0.0
    assert sys.version_info >= (3, 10)
