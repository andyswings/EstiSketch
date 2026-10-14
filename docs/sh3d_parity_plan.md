# SweetHome3D (SH3D) 2D Feature Parity Execution Plan

This document details the engineering specifications, data models, rendering engines, and phased implementation roadmap to achieve complete 2D plan parity with **SweetHome3D (SH3D)**, directly operationalizing the gap analysis in [`docs/sh3d_2d_parity.md`](file:///home/andrew/Documents/Python_Projects/EstiSketch/docs/sh3d_2d_parity.md).

---

## 1. Architectural Strategy & Phasing

```mermaid
graph TD
    subgraph Phase 1: Precision Geometry & Snapping
        A1[Edge-to-Edge Wall Snapping] --> A2[Arc Wall Snapping & Tangent Cuts]
        A2 --> A3[Multi-Thickness Miter Joins]
    end

    subgraph Phase 2: Blueprint Tracing & Underlays
        B1[Background Image Underlay Engine] --> B2[Two-Click Distance Calibration Wizard]
        B2 --> B3[Per-Level Blueprint Controls & Opacity]
    end

    subgraph Phase 3: Advanced Dimensions & Callouts
        C1[Continuous Dimension Chains] --> C2[Leader Lines & Callout Arrows]
        C1 --> C3[Angular & Cumulative Summary Dimensions]
    end

    subgraph Phase 4: Room Cutouts & Surface Finishes
        D1[Room Holes / Stairwell Cutouts] --> D2[Hatch & Pattern Texture Engine]
        D1 --> D3[Per-Side Wall Finishes & Baseboards]
    end

    subgraph Phase 5: Architectural 2D Fixtures Catalog
        E1[Parametric Fixture Data Model] --> E2[Kitchen Cabinetry & Appliance Generator]
        E2 --> E3[Bathroom Fixtures & AIA Symbols]
        E3 --> E4[Interior Design Toolset & Library Dock]
    end

    subgraph Phase 6: Multi-Story Ghosting & Compass
        F1[Level Onion-Skinning Ghosting] --> F2[Compass Rose & North Azimuth]
    end

    subgraph Phase 7: Scaled Architectural Output
        G1[Cairo Vector SVG Export] --> G2[Scaled PDF Sheet Plotting & Title Blocks]
    end

    Phase 1 --> Phase 4
    Phase 2 --> Phase 1
    Phase 3 --> Phase 7
    Phase 4 --> Phase 5
    Phase 5 --> Phase 7
    Phase 6 --> Phase 7
```

---

## 2. Technical Specifications & Implementation Plan

### Phase 1: Edge-to-Edge Wall Snapping & Multi-Thickness Miters (Roadmap Item #2)

#### 1.1 Requirements
When joining walls of differing thicknesses (e.g., an 8" exterior concrete wall and a 4.5" interior stud wall), users must be able to choose whether to align:
1. **Exterior Face Flush** (outer faces aligned).
2. **Interior Face Flush** (inner faces aligned).
3. **Centerline Aligned** (standard centerline intersection).

#### 1.2 Target Files
- [`src/EstiSketch/snapping_manager.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/snapping_manager.py)
- [`src/EstiSketch/Canvas/events_wall.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/events_wall.py)
- [`src/EstiSketch/Canvas/wall_room_renderer.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/wall_room_renderer.py)

#### 1.3 Implementation Details
1. **Face Snapping Geometry**:
   - For an existing wall $W_1$ with normal $\vec{n}$:
     $$\text{Face}_{\text{left}} = \text{Centerline} + \vec{n} \cdot \frac{w_1}{2}$$
     $$\text{Face}_{\text{right}} = \text{Centerline} - \vec{n} \cdot \frac{w_1}{2}$$
   - When drawing or dragging wall $W_2$ with width $w_2$, evaluate offsets to match $W_2$'s left or right face flush with $W_1$'s faces.
   - Add dynamic visual snap guidelines (cyan dashed lines for outer edge alignment, orange dashed lines for inner edge alignment).
2. **Miter Join Polygon Calculation**:
   - Update `draw_wall_joint` in [`wall_room_renderer.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/wall_room_renderer.py) so corner miters cleanly meet at exterior/interior edge intersections rather than producing stepped artifacts.

---

### Phase 2: Blueprint Tracing & Calibration Wizard (Roadmap Item #1)

#### 2.1 Requirements
Allow users to import raster images (PNG, JPG) or vector blueprints as drawing underlays and calibrate their true scale using a 2-click reference measurement.

#### 2.2 Target Files
- [`src/EstiSketch/components.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/components.py)
- [`src/EstiSketch/Dialogs/blueprint_wizard.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Dialogs/blueprint_wizard.py) (new)
- [`src/EstiSketch/Canvas/canvas_draw.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/canvas_draw.py)
- [`src/EstiSketch/Canvas/events_tools.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/events_tools.py)
- [`src/EstiSketch/project_io.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/project_io.py)

#### 2.3 Implementation Details
1. **Data Model**:
   ```python
   @dataclass
   class BackgroundImage:
       identifier: str = ""
       image_path: str = ""
       x: float = 0.0          # Origin in model inches
       y: float = 0.0
       scale_x: float = 1.0    # Inches per pixel
       scale_y: float = 1.0
       rotation: float = 0.0
       opacity: float = 0.5    # 0.0 to 1.0
       visible: bool = True
       locked: bool = True     # Locked from accidental drag
       level_id: str = ""      # Associated building level
   ```
2. **Two-Click Calibration Wizard**:
   - User initiates **File > Import Blueprint...** or clicks toolbar icon.
   - Canvas enters `"calibrate_blueprint"` mode:
     - User clicks Point 1 (e.g., start of a dimension line).
     - User clicks Point 2 (end of the dimension line).
   - Dialog opens asking for real dimension (e.g., `24' 0"` or `7500 mm`).
   - Calculate scale factor:
     $$\text{scale} = \frac{\sqrt{(x_2 - x_1)^2 + (y_2 - y_1)^2}}{\text{real\_inches}}$$
   - Store scale and align image origin.
3. **Rendering & Controls**:
   - Render in [`canvas_draw.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/canvas_draw.py) using Cairo `paint_with_alpha` before drawing grid and structural elements.
   - Provide opacity slider and lock/unlock toggle in Layers Panel.

---

### Phase 3: Continuous Dimension Chains & Annotation Leaders (Roadmap Item #3)

#### 3.1 Requirements
Provide rapid architectural dimensioning via unbroken dimension strings along exterior walls and leader callouts for construction annotations.

#### 3.2 Target Files
- [`src/EstiSketch/components.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/components.py)
- [`src/EstiSketch/Canvas/canvas_draw.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/canvas_draw.py)
- [`src/EstiSketch/Canvas/events_tools.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/events_tools.py)
- [`src/EstiSketch/Dialogs/properties_dock.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Dialogs/properties_dock.py)

#### 3.3 Implementation Details
1. **Data Models**:
   - `DimensionChain`: Ordered list of points along a shared baseline, perpendicular offset, optional cumulative summary dimension, and witness line rendering.
   - `LeaderCallout`: Arrowhead tip point, elbow point, shoulder point, and multiline text with optional border box.
2. **Interaction & Snapping**:
   - Consecutive clicks drop dimension points automatically projected along the baseline defined by the initial segment.
   - Dragging the dimension offset shifts the entire chain together while preserving individual segment measurements.
   - Leader arrows snap to wall faces, windows, doors, or stairs.

---

### Phase 4: Room Cutouts & Surface Finishes (Roadmap Item #5)

#### 4.1 Requirements
Support multi-point room polygons with interior hole cutouts (stairwells, double-height atriums, courtyards), along with directional floor/ceiling pattern hatches and per-side wall finishes.

#### 4.2 Target Files
- [`src/EstiSketch/components.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/components.py)
- [`src/EstiSketch/Canvas/wall_room_renderer.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/wall_room_renderer.py)
- [`src/EstiSketch/Takeoff/building_takeoff.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Takeoff/building_takeoff.py)
- [`src/EstiSketch/project_io.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/project_io.py)

#### 4.3 Implementation Details
1. **Room Holes**:
   - Add `holes: List[List[Tuple[float, float]]]` to [`Room`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/components.py).
   - Render using `cairo.FILL_RULE_EVEN_ODD` across outer boundary and hole paths.
   - Deduct hole area from room square footage, floor slab takeoff, and ceiling finishes.
2. **Floor & Ceiling Texture Patterns**:
   - Procedural Cairo pattern fills: wood plank (offset parallel lines), tile grid (custom pitch 12", 18", 24"), herringbone, and concrete stipple.
   - Support pattern rotation angle and pattern scaling factor.
3. **Per-Side Wall Finishes**:
   - Extend `Wall` with `left_finish`, `right_finish`, `left_color`, `right_color`, `left_baseboard`, `right_baseboard`.
   - Update takeoff engine to compute distinct interior vs exterior wall surface areas and linear baseboard footage.

---

### Phase 5: Architectural Fixtures & 2D Symbol Catalog (Roadmap Item #4)

#### 5.1 Requirements
Provide standard 2D top-down architectural plan symbols conforming to AIA drafting conventions for kitchen cabinetry, major appliances, and bathroom fixtures.

#### 5.2 Target Files
- [`src/EstiSketch/components.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/components.py)
- [`src/EstiSketch/Canvas/render_fixtures.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/render_fixtures.py) (new)
- [`src/EstiSketch/toolbar.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/toolbar.py)
- [`src/EstiSketch/Dialogs/fixture_browser.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Dialogs/fixture_browser.py) (new)

#### 5.3 Symbol Catalog
- **Kitchen**:
  - Base Cabinets (12"–48", depth 24"): perimeter rectangle, door/drawer split line, handle notch.
  - Upper Cabinets (12"–48", depth 12"): dashed perimeter rectangle with diagonal cross.
  - Corner Cabinets & Tall Pantries.
  - Sinks (single/double undermount basin), Cooktops (burners), Refrigerators, Dishwashers.
- **Bathroom**:
  - Toilets: rectangular tank (8"x18") with oval elongated bowl (14"x20") and standard clearance boundary.
  - Bathtubs (60"x30", 60"x32"): apron rectangle, rounded inner tub, drain.
  - Shower Enclosures: square/corner curb with diagonal floor drain lines.
  - Vanity Sinks: countertop with oval/rectangular basin.
- **Placement & Snapping**:
  - Wall-hosted alignment: fixtures auto-orient against the nearest wall face when dragged near a wall.

---

### Phase 6: Multi-Story Ghosting & Compass Rose (Parity Matrix Items)

#### 6.1 Requirements
- Level onion-skinning: View adjacent floor plans (Level N-1 or N+1) as a muted background trace.
- Compass Rose: Interactive North orientation needle with azimuth angle.

#### 6.2 Target Files
- [`src/EstiSketch/Canvas/canvas_area.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/canvas_area.py)
- [`src/EstiSketch/Canvas/canvas_draw.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Canvas/canvas_draw.py)
- [`src/EstiSketch/Dialogs/layers_panel.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Dialogs/layers_panel.py)

#### 6.3 Implementation Details
1. **Onion-Skinning**:
   - Add `ghost_level_id` and `ghost_opacity` (default 25%) to `CanvasArea`.
   - Render adjacent level geometry in muted grayscale/cyan before active level rendering.
2. **Compass Rose**:
   - Add `canvas.north_angle` (degrees).
   - Draw an interactive North arrow widget in the top-right corner; dragging rotates the project azimuth.

---

### Phase 7: Scaled Architectural PDF Sheet Plotting & Vector Export (Roadmap Item #6)

#### 7.1 Requirements
Generate publication-ready, scaled architectural PDF sheets with title blocks and clean layered SVG vector files.

#### 7.2 Target Files
- [`src/EstiSketch/export_engine.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/export_engine.py) (new)
- [`src/EstiSketch/Dialogs/export_dialog.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/Dialogs/export_dialog.py) (new)
- [`src/EstiSketch/toolbar.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/toolbar.py) (uncomment export button)

#### 7.3 Implementation Details
1. **Vector SVG Export**:
   - Use `cairo.SVGSurface` to export vector layers (`walls`, `doors`, `rooms`, `dimensions`, `fixtures`) with true scale and vector fidelity.
2. **Scaled Architectural PDF Plotting**:
   - Sheet sizes: Letter (8.5x11), Tabloid (11x17), Arch C (18x24), Arch D (24x36).
   - Standard architectural scales: 1/8" = 1'-0", 1/4" = 1'-0", 1/2" = 1'-0", 1" = 1'-0", 1:50, 1:100.
   - Title Block: Project name, sheet title, sheet number, scale bar, date, author, revision block, and north arrow.

---

## 3. Project File Serialization & Migration Schema

All additions integrate cleanly into [`src/EstiSketch/project_io.py`](file:///home/andrew/Documents/Python_Projects/EstiSketch/src/EstiSketch/project_io.py) XML format:

```xml
<Project window_width="1920" window_height="1080" active_level_id="lvl-1" north_angle="0.0">
  <Levels>...</Levels>
  <Layers>...</Layers>

  <!-- Background Blueprints -->
  <BackgroundImages>
    <BackgroundImage id="bg-1" path="/path/to/blueprint.png" x="0.0" y="0.0"
                     scale_x="0.125" scale_y="0.125" rotation="0.0" opacity="0.4"
                     locked="True" level_id="lvl-1" />
  </BackgroundImages>

  <!-- Rooms with Holes and Patterns -->
  <Rooms>
    <Room id="rm-1" floor_type="hardwood" pattern="wood_plank" pattern_rotation="45">
      <Points>...</Points>
      <Holes>
        <Hole>
          <Point x="120.0" y="80.0" />
          <Point x="180.0" y="80.0" />
          <Point x="180.0" y="140.0" />
          <Point x="120.0" y="140.0" />
        </Hole>
      </Holes>
    </Room>
  </Rooms>

  <!-- Dimension Chains -->
  <DimensionChains>
    <DimensionChain id="dimc-1" offset="24.0" show_overall="True" overall_offset="36.0">
      <Point x="0.0" y="0.0" />
      <Point x="144.0" y="0.0" />
      <Point x="288.0" y="0.0" />
    </DimensionChain>
  </DimensionChains>

  <!-- Leader Callouts -->
  <LeaderCallouts>
    <LeaderCallout id="ld-1" target_x="100" target_y="50" knee_x="140" knee_y="70"
                   text_x="180" text_y="70" text="2x6 Bearing Wall" arrow_style="filled" />
  </LeaderCallouts>

  <!-- Fixtures & Cabinetry -->
  <Fixtures>
    <Fixture id="fix-1" category="kitchen" symbol_type="base_cabinet"
             x="48.0" y="0.0" width="36.0" depth="24.0" height="34.5" rotation="0.0" />
  </Fixtures>
</Project>
```

---

## 4. Execution Roadmap & Milestones

| Phase | Milestone | Priority in TODO | Scope & Deliverables | Est. Complexity |
|---|---|---|---|---|
| **Phase 1** | **Edge-to-Edge Wall Snapping** | High (#2) | Face-to-face snapping in `snapping_manager.py`, visual snap guidelines, multi-thickness miter corner fixes in renderer | Moderate-High |
| **Phase 2** | **Blueprint Calibration Wizard** | High (#1) | Background image component, 2-click calibration tool, scale calculator dialog, opacity/lock controls in layer panel | Moderate |
| **Phase 3** | **Continuous Dimension Chains & Leaders** | High (#3) | `DimensionChain` and `LeaderCallout` data models, multi-click continuous tool, baseline witness rendering, callout arrows | Moderate |
| **Phase 4** | **Room Cutouts & Surface Finishes** | High (#5) | Nested hole polygons in `Room`, even-odd Cairo fill, area deduction in takeoff, floor hatch rotation, per-side wall finishes | Moderate |
| **Phase 5** | **Fixtures & Architectural Symbols** | High (#4) | `Fixture` model, procedural Cairo renderers for kitchen/bath/appliances, library dock in sidebar, interior design toolset | High |
| **Phase 6** | **Level Ghosting & Compass Rose** | Medium | Onion-skinning render pass of adjacent floor, north arrow canvas widget, sun angle orientation | Low-Moderate |
| **Phase 7** | **Scaled Vector & PDF Plotting** | High (#6) | Vector SVG export, scaled PDF sheet generation with standard title blocks, paper size / scale dialog | High |
