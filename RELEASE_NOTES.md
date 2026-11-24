# EstiSketch Release Notes

## Version 0.4.0-beta
**Date:** 2026-11-23

### Highlights
- **Alpha to Beta Milestone:** EstiSketch graduates from Alpha to Beta (`0.4.0-beta`) with complete 2D architectural drafting, 3D roof geometry, interactive material takeoffs, scaled PDF/SVG output, and cross-platform packaging preparation.
- **Cross-Platform Release Packaging:** Updated `.deb` (Debian/Ubuntu), AppImage (Linux portable bundle), and Windows Conda `constructor` `.exe` installer configurations, backed by automated GitHub Actions release builds.
- **Writable Per-User Settings:** Fixed settings persistence so installed packages store layout and configuration in the user's writable config directory (`~/.config/estisketch` on Linux, `%APPDATA%\EstiSketch` on Windows) instead of the application install directory.

### New Features
- **Architectural Fixtures, Cabinetry, Countertops & Appliances:** Added a 30-symbol procedural `Fixture` catalog with 3-pass AIA Cairo rendering, surface mounting/elevation, straight & arc wall snapping, searchable `FixtureBrowserDialog`, 9-preset `KitchenLayoutDialog`, `draw_cabinet_run` tool, and material takeoff / supplier quote integration.
- **3D Roof Geometry Engine & Complex Roofs:** Unified 3D roof solver supporting gable, hip, asymmetric dual-pitch, L/T-shaped, and multisided roofs, manual roof-line sketching, variable eave overhangs, sloped-top walls, and multi-level plate elevations.
- **Stairs, Winders & Railings:** Straight, L-shaped, U-shaped switchback, winder, and spiral stairs with configurable 2D/3D railings, automatic floor-to-floor rise updates, and room hole cutouts.
- **Interactive Material Takeoff & Cost Estimation:** Comprehensive framing, foundation, exterior sheathing/housewrap, interior finish, flooring, ceiling, roof, stair, and fixture takeoff engine with material management and TXT/CSV/PDF supplier quote exports.
- **Blueprint Tracing, Calibration & Straightening:** Import PNG/JPG blueprint underlays, calibrate scale with two clicks, and apply perspective homography / curvature straightening transforms.
- **Floor Texture Patterns, Wall Finishes & Floor Openings:** Pure-Cairo procedural flooring patterns, per-side wall finishes and baseboards, stair-derived room holes, and first-class `FloorOpening` polygons.
- **Continuous Dimension Chains & Leader Callouts:** Aligned dimension strings with exact segment length editing, baseline snapping, and leader callout arrows.
- **Level Ghosting & Compass Rose:** Onion-skinning ghost view of adjacent levels (`Off`, `Below`, `Above`, or explicit level) and an interactive north-azimuth compass overlay synced with print title blocks.
- **Scaled PDF Printing & Vector SVG Export:** Live print preview with drag-to-reposition, architectural/metric scales, multi-level pagination, customizable title block, and scaled vector SVG export.
- **Object Grouping & All Objects Explorer:** Group/ungroup (`Ctrl+G` / `Ctrl+Shift+G`), unit move/rotate/lock/hide, custom names/comments, and unified searchable object management.
- **Precision Snapping:** Edge-to-edge face-flush snapping, curved/arc wall midpoint & tangent snapping, and 0.25" / near-foot wall length snapping.

### Packaging & Infrastructure
- Consolidated Python package metadata into `pyproject.toml` (`EstiSketch.version.__version__` as single source of truth).
- Updated `packaging/build_deb.py` (`0.4.0~beta` Debian versioning, `python3-numpy` dependency, `python3-reportlab` recommendation).
- Updated `packaging/estisketch.spec` and `packaging/build_pyinstaller_appimage.sh` with full `EstiSketch` submodule collection and `settings.json` data bundling.
- Fixed Windows Conda `constructor` pipeline (`conda-recipe/meta.yaml`, `conda-recipe/bld.bat`, `construct.yaml`, `menu/estisketch-menu.json`, `packaging/make_ico.py`, `packaging/build_windows_installer.ps1`, `pixi.toml`).
- Added `.github/workflows/release.yml` to run tests and build `.deb`, `.AppImage`, and Windows `.exe` installers on release tags.

---

## Version 0.3.0-alpha
**Date:** 2026-01-25

### Highlights
- **Foundation Design**: comprehensive tools for designing footers and concrete slabs.
- **Improved Workflow**: Refactored toolsets with "Main" category streamlining access to core tools.
- **Rendering Upgrades**: Seamless footer connections and concrete material hatching.

### New Features
- **Foundation Footers**: Configure footers on walls with adjustable width and depth.
- **Symbolic Walls**: Option to render only the footer (hides wall body) for foundation plans.
- **Concrete Slabs**: "Draw Rooms" tool now supports Slab mode with hatching, thickness, and reinforcement settings.
- **Interactive Foundations**: Footers and slabs are selectable and editable via the properties panel.
- **Refactored Toolsets**: Renamed "Basic" to "Main" and integrated Foundation tools for a unified workflow.

### Bug Fixes
- Fixed footer rendering position (removed double transformation offset).
- Removed internal miter lines for seamless footer corner connections.
- Corrected footer extension logic for free-standing wall ends.

---


## Version 0.2.0-alpha
**Date:** 2026-01-14

### Highlights
- **Curved Walls**: Draw curved/arc walls with Shift+C during wall creation, edit curvature via drag handle or properties panel
- **Toolset Selector**: Dropdown to switch between tool categories (Basic, Annotation, Foundation, Roof, Interior Design)
- **Enhanced Properties Panel**: Edit curved wall radius, bulge, and arc length directly

### New Features
- **Curved Walls** - Integrated into wall tool, press Shift+C after 2nd point to create 3-point arc walls with live preview and radius display
- **Curved Wall Editing** - Edit via arc midpoint drag handle or properties panel (radius, bulge, arc length)
- **Convert Walls** - Right-click context menu to convert between curved and straight walls
- **Toolset Selector** - Dropdown in toolbar to switch between tool categories
- **Tab-to-Cycle Selection** - Press Tab to cycle through overlapping objects at mouse position
- **Status Bar Hints** - Context-aware tool usage hints in status bar
- **Dirty Indicator** - Green/red circle showing save state

### Bug Fixes
- Fixed windows and doors now drawn tangent to curve on curved walls
- Fixed rendering artifact where circles/arcs displayed unwanted lines to dimensions
- Fixed multi-type selection now enables all applicable property tabs
- Fixed dimension moving no longer resets angle and length
- Fixed arc endpoint editing maintains sagitta when endpoints moved
- Fixed circle/arc dragging - objects can now be moved by dragging

### Known Limitations
- Some placeholder toolsets (Foundation, Roof) have limited tools until full implementation
- Undo/Redo may have edge cases in complex scenarios

---

## Version 0.1.0-alpha
**Date:** 2025-12-30

### Highlights
- **First Alpha Release:** The core functionality for sketching walls, rooms, doors, and windows is available.
- **Improved Code Quality:** Resolved major static analysis issues and critical import errors to ensure stability.
- **New Features:**
  - **Wall Length Input:** Precise wall length entry via dialog.
  - **Packaging:** Project is now structured as a proper Python package.
  - **Testing:** Basic test suite established.

### Known Limitations
- Sidebar width behavior on resize may need further tuning.
- Some minor lint warnings (whitespace/comments) remain but do not affect functionality.
- Undo/Redo is implemented but may have edge cases in complex scenarios.

---

## Installation
- **Debian / Ubuntu (`.deb`):**
  ```bash
  sudo apt install ./dist/estisketch_0.4.0~beta_all.deb
  ```
- **Linux Portable (`AppImage`):**
  ```bash
  chmod +x EstiSketch-0.4.0-beta-x86_64.AppImage
  ./EstiSketch-0.4.0-beta-x86_64.AppImage
  ```
- **Windows (`.exe` Installer):** Download and run `EstiSketch-0.4.0-beta-Windows-x86_64.exe` from the Releases page.
- **From Source (pip):**
  ```bash
  pip install .
  estisketch
  ```

## How to Contribute
Please report any bugs or feature requests to the issue tracker.
