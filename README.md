# EstiSketch ![Status](https://img.shields.io/badge/Status-Beta-blue)

> **Beta Release (v0.4.0-beta)**: EstiSketch is now in beta! Core 2D drafting, roof modeling, architectural fixtures, material takeoffs, and PDF/SVG printing are functional. Please report any bugs or rough edges on our issue tracker.

EstiSketch is a lightweight, GTK4-based 2D architectural drafting and building estimation tool designed for contractors and designers to quickly sketch floor plans, generate material takeoffs, and produce scaled construction prints.

## Current Features

### Essential Drawing Tools
- **Pointer (V)**: Select walls, corners, rooms, roofs, stairs, fixtures, or groups. Supports box select, shift-extend, Tab-to-cycle through overlapping objects, and a rich right-click context menu.
- **Pan (P) & Zoom**: Smooth canvas navigation with Zoom In (`Ctrl+=`), Out (`Ctrl+-`), Reset (`Ctrl+0`), mouse wheel, and pinch gestures.
- **Undo/Redo**: Undo/redo history (`Ctrl+Z` / `Ctrl+Y`).
- **Toolset Selector**: Switch between **Main**, **Annotation**, **Roof**, and **Interior Design** tool categories.

### Wall, Room & Foundation System
- **Draw Walls (W)**: Mitered corners, live grid/endpoint/face-flush snapping, 0.25" and near-foot length snapping, and sloped-top wall heights.
- **Curved Walls**: Press **Shift+C** after placing the 2nd wall point to create 3-point arc walls with tangent opening cuts and arc snapping.
- **Draw Rooms (R) & Floor Openings (O)**: Click points or double-click inside a closed wall loop to generate a room along interior wall faces; add procedural floor texture patterns and manual floor openings.
- **Foundations**: Toggle wall footers with adjustable width/depth, symbolic footer-only walls, and concrete slabs with hatching and reinforcement settings.
- **Per-Side Wall Finishes & Baseboards**: Configure left/right wall finish types, colors, and baseboard trim.

### Openings, Stairs & Architectural Fixtures
- **Doors (D) & Windows (A)**: Placement ghosts along straight and curved walls with configurable default sizes and swing/orientation controls.
- **Stairs**: Straight, L-shaped, U-shaped, winder, and spiral stairs with 2D/3D railings, automatic floor-to-floor rise updates, and room hole cutouts.
- **Fixtures, Cabinetry & Appliances**: 30-symbol procedural catalog (kitchen/bath cabinetry, countertops, plumbing fixtures, appliances, HVAC) with searchable browser, 9-preset Kitchen Layout Wizard, and `draw_cabinet_run` tool.

### Roof Design
- **Roof Solver & Complex Roofs**: Gable, hip, asymmetric dual-pitch, L/T-shaped, and multisided roof generation with variable eave overhangs, angled/multi-level wall plate support, and manual roof line sketching (`Shift+L`).

### Annotations & Levels
- **Dimension Tools**: Single dimensions (`M`), continuous aligned dimension chains with exact segment editing, and leader callout arrows.
- **Shapes & Text**: Polylines (`L`), Circles (`C`), Arcs (`Shift+A`), and rotatable Text labels (`T`).
- **Multi-Level & Layers**: Multi-story levels, level onion-skinning ghosting, layer visibility/locking, object grouping (`Ctrl+G` / `Ctrl+Shift+G`), and searchable **All Objects** explorer.
- **Compass Rose**: Interactive north azimuth overlay synced with print title blocks.

### File Operations, Printing & Estimation
- **Save/Open**: Custom XML project format preserving geometry, layers, levels, groups, blueprints, and print settings.
- **Import**: Sweet Home 3D (`.sh3d`) layout import and **Blueprint Underlay** (`PNG`/`JPG`) with two-click scale calibration and perspective/curvature straightening.
- **Print / Export (`Ctrl+P` / `Ctrl+E`)**: Live print preview, architectural/metric scales, multi-level pagination, customizable title block, PDF export, and scaled vector SVG export.
- **Material Management & Takeoffs**: Manage material pricing (`Ctrl+M`), estimate framing/sheathing/finishes/roof/fixture materials (`Ctrl+Shift+M`), calculate costs (`Ctrl+Shift+C`), and export TXT/CSV/PDF supplier quotes.

## Installation and Usage

### Prebuilt Packages (`.deb`, `AppImage`, Windows `.exe`)
- **Debian / Ubuntu (`.deb`):**
  ```bash
  sudo apt install ./dist/estisketch_0.4.0~beta_all.deb
  estisketch
  ```
- **Linux Portable (`AppImage`):**
  ```bash
  chmod +x dist/EstiSketch-0.4.0-beta-x86_64.AppImage
  ./dist/EstiSketch-0.4.0-beta-x86_64.AppImage
  ```
- **Windows (`.exe`):** Run the Conda `constructor` installer (`EstiSketch-0.4.0-beta-Windows-x86_64.exe`).

### Run or Build from Source

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/andyswings/EstiSketch.git
   cd EstiSketch
   ```

2. **Install System Dependencies (Debian/Ubuntu):**
   ```bash
   sudo apt install libgirepository-2.0-dev gcc libcairo2-dev pkg-config python3-dev gir1.2-gtk-4.0 python3-pip
   ```

3. **Create a Virtual Environment and Install Python Dependencies:**
   ```bash
   pip install uv
   uv venv .venv
   source .venv/bin/activate
   uv pip install pycairo PyGObject numpy reportlab
   ```

4. **Run the Application:**
   ```bash
   python run_dev.py
   ```

### Building Release Packages Locally
- **Debian `.deb`:** `python3 packaging/build_deb.py` -> `dist/estisketch_0.4.0~beta_all.deb`
- **Linux AppImage:** `bash packaging/build_pyinstaller_appimage.sh` -> `dist/EstiSketch-0.4.0-beta-x86_64.AppImage`
- **Windows `.exe` (on Windows with Conda + `conda-build` + `constructor`):** `powershell -ExecutionPolicy Bypass -File packaging/build_windows_installer.ps1`

## Contributing
Contributions are welcome!

Fork the repository, make your changes, and submit a pull request.
For major changes, please open an issue first to discuss your ideas.

## License
This project is licensed under the MIT License.
