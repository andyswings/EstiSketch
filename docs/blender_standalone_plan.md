# Standalone Blender Integration Plan (Zero External Add-on Dependency)

## Goal

Ensure EstiSketch's `"Open 3D in Blender..."` workflow works out of the box with a standard installation of Blender (`4.0+` / `5.1+`) using **EstiSketch's own 3D geometry and bundled `CC0-1.0` assets**, without requiring users to install or enable the third-party **Home Builder 5** (`home_builder_5`) Blender extension. When Home Builder 5 *is* installed and enabled in Blender, users can optionally opt into using it via Settings.

---

## Architecture Overview

```
EstiSketch Canvas / Project
        │
        ├── Default ("estisketch"):
        │     SceneIR ──► native_3d (Rust mesher + assets_3d/*.glb + custom .glb)
        │                    ──► project.glb + scene_manifest.json
        │                    ──► blender --python estisketch_to_blender.py
        │                           (built-in bpy.ops.import_scene.gltf ONLY)
        │
        └── Optional ("auto" / "hb5"):
              If home_builder_5 addon is enabled in Blender:
                    ──► delegates to estisketch_to_hb5.py (native HB5 objects)
              Else:
                    ──► falls back cleanly to project.glb + EstiSketch assets
```

### 1. Asset & Scene Pipeline (`estisketch` Default Mode)

1. **Pure-Python + Native Rust Export (`launcher.py::export_standalone_blender_bundle`)**:
   - Converts the live canvas to `SceneIR` via `build_scene_ir_from_canvas(canvas)`.
   - Loads `SceneIR` into `native_3d.create_native_session()`, which registers EstiSketch's bundled `CC0-1.0` asset pack (`src/EstiSketch/assets_3d/manifest.json`: toilets, bathtubs, sofas, armchairs, beds, dining tables, refrigerators, ranges) alongside procedural Rust meshers for all walls, mitered corners, openings, baseboards, rooms/holes, pitched roofs, gable infills, footers, rim bands, stairs/railings, shaker cabinets, countertops, appliances, and user-imported `.glb`/`.gltf`/`.obj` custom assets.
   - Exports a single spec-compliant glTF 2.0 binary (`project.glb`) plus `scene_manifest.json` (levels, sun azimuth/north angle, plan center, and per-entity metadata including world center `loc_m`, `rot_z_rad`, and level `z_offset_m`).

2. **Zero-Add-on Blender Scene Assembly (`blender_bridge/estisketch_to_blender.py`)**:
   - Depends only on Blender's built-in Python (`bpy`, `mathutils`) and the standard glTF 2.0 importer (`bpy.ops.import_scene.gltf`) shipped with every Blender release.
   - Imports `project.glb`, bakes glTF world transforms into vertices, joins multi-part sub-meshes belonging to the same `estisketch_id` into single multi-material objects (preserving all PBR materials), and organizes them into clean per-level collections (`EstiSketch - <Level>` -> `Walls`, `Openings`, `Rooms`, `Roofs`, `Stairs`, `Fixtures`, `Custom Assets`).
   - Recenters movable entities (`fixture`, `custom_asset`) to their exact EstiSketch `(x, y, z)` center and Z-rotation so Blender transforms map 1:1 back to EstiSketch without corner-origin offsets.
   - Configures `EstiSketch_Sun`, imperial inch units, and `blender_live_sync.py` so pressing `Ctrl+S` in Blender writes `delta.esk-delta.zip` and syncs moves, mesh edits, and newly modeled objects straight back into EstiSketch in a single Undo step.

### 2. Optional Home Builder 5 Mode

- Controlled by `BLENDER_ASSET_SOURCE` in `config.py` and **Settings > Blender 3D Asset Source**:
  - `"estisketch"` *(default)* — Always uses EstiSketch's own procedural + `.glb` assets; works with zero add-ons.
  - `"auto"` — Uses Home Builder 5 if the `home_builder_5` add-on is installed and enabled in Blender; otherwise seamlessly falls back to EstiSketch assets.
  - `"hb5"` — Prefers Home Builder 5 when enabled, and falls back to EstiSketch assets with a status warning if HB5 is missing or disabled.

### 3. Future Asset Pack Expansion

- Standalone Blender export automatically benefits from every new `.glb` added to `src/EstiSketch/assets_3d/` (as outlined in [`docs/3d_asset_library_plan.md`](file:///home/andrew/Documents/Python_Projects/EstiSketch/docs/3d_asset_library_plan.md)) because `NativeSceneSession.export_glb` embeds those meshes directly into `project.glb`.
- If the native Rust extension is ever unavailable in a development checkout, the launcher degrades gracefully to `estisketch_to_hb5.py` when HB5 is present, or informs the user clearly.
