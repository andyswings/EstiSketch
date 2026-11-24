# SweetHome3D 2D Feature Parity Gap Analysis for EstiSketch

## Executive Summary
This document provides a systematic architectural and functional comparison between **SweetHome3D (SH3D)**'s 2D plan editor and **EstiSketch**.
SweetHome3D is a mature open-source interior design and floor-planning application written in Java. While EstiSketch specializes in rapid architectural sketching, structural framing, takeoff calculations, and contractor procurement, reaching functional parity with SweetHome3D's 2D plan capabilities is essential for providing a complete drafting and architectural design workflow.

---

## 1. Feature Comparison Matrix

| Feature Domain | SweetHome3D (2D Plan) | EstiSketch (Current State) | Parity Status | Priority / Gap Impact |
|---|---|---|---|---|
| **Walls: Curved / Arc Walls** | Full support via arc bulge (`arcExtent`), circular segment rendering, thickness offset, door/window cuts along arcs | Basic curved wall data structure and rendering exists; snapping and door/window host cuts along curved walls need refinement | **Partial** | High |
| **Walls: Wall Finishes / Patterns** | Per-side colors, textures, patterns, and baseboards (left side vs right side) | Uniform line width & hatch styling; no distinct left/right side finish or baseboard definitions | **Missing** | Medium |
| **Walls: Miter & Join Styles** | Automatic miter intersections, corner beveling, T-junction cleanup across multiple wall thicknesses | Centerline intersection snapping and standard miter rendering; alignment of walls with different thicknesses needs edge-to-edge snapping | **Partial** | High |
| **Rooms: Polygons & Holes** | Multi-point custom rooms, automatic room generation from walls, interior hole cutouts (stairwells, lightwells, courtyards) | Automatic room loop detection from walls, manual room drawing; hole cutouts inside rooms not yet supported | **Partial** | High |
| **Rooms: Floor & Ceiling Textures** | Floor patterns, tile grids, hardwood planks, ceiling grid textures with rotation and scale | Solid color room fills; no texture mapping or hatch rotations | **Missing** | Medium |
| **Doors & Windows** | Parametric width, height, elevation, depth, wall cutouts, swing orientation (inward/outward/left/right), sash opening angle | Parametric width/height, wall placement, 2D plan swing arcs, exterior/interior orientation | **Close to Parity** | Low |
| **Furniture & Symbols Library** | 1,000+ catalog items with 2D plan SVG/bitmap top-down representations, resizing, elevation, rotation | Library of basic architectural items; needs comprehensive 2D furniture/fixture symbols (kitchen cabinets, bath fixtures, appliances, plumbing) | **Partial** | High |
| **Stairs & Railings** | Pre-packaged 3D stair objects placed in 2D with tread counts; basic top-down representations | Full parametric 2D generator for Straight, L-shaped, U-shaped, Winders, Spiral, left/right railings, 3D linear footage takeoff | **Feature Superiority** (EstiSketch exceeds SH3D) | Complete |
| **Roofs & Overhangs** | Separate roof box objects or community plug-ins; lacks native parametric complex roof solving | Parametric hip, gable, L-shape, T-shape, multisided straight skeleton, exterior-face overhangs, multi-level & sloped wall plate heights | **Feature Superiority** (EstiSketch exceeds SH3D) | Complete |
| **Dimensions & Measurement Chains** | Continuous dimension chains, offset extension lines, witness lines, prefix/suffix text, imperial/metric | Linear dimensions with extension lines; continuous chained dimensions and angular dimensions needed | **Partial** | High |
| **Text Labels & Annotations** | Free-floating text labels with font size, style, color, rotation, leader lines with arrows | Text annotation tool with basic formatting; leader lines / callout arrows needed | **Partial** | Medium |
| **Compass Rose & Sun Orientation** | Interactive compass rose with North direction angle, geographic latitude/longitude for shadow analysis | No compass or orientation element | **Missing** | Low |
| **Background Blueprint Tracing** | Background image wizard with scale calibration line, origin offset, image transparency, level assignment | Background image import exists; interactive 2-point scale calibration wizard needed | **Partial** | High |
| **Multi-Level / Stories** | Explicit level hierarchy with elevations, floor thickness, ceiling height, and previous-level ghosting ("onion skinning") | Multi-level and multi-layer engine with elevations, active layer visibility; needs configurable ghosting / tracing overlay of adjacent levels | **Close to Parity** | Medium |
| **Printing & Export** | Vector SVG export, scaled PDF printing with customizable margins, title block, and plan scale (e.g. 1/4" = 1') | PDF supplier quotes, basic canvas raster export; vector SVG export and scaled architectural PDF sheet layouts needed | **Partial** | High |

---

## 2. Deep-Dive Gap Details & Recommendations

### Gap 1: Continuous Dimension Chains & Annotation Leaders
- **SH3D Capability:** Users can click a series of wall corners sequentially to drop an aligned string of dimensions (dimension chain). Extension lines automatically align, and overall summary dimensions can be placed alongside detail dimensions. Leader callouts point arrows to specific details.
- **Recommendation for EstiSketch:** Implement a continuous dimension chain tool where successive clicks add consecutive dimension links, and add leader arrow annotations.

### Gap 2: Background Blueprint Tracing Calibration Wizard
- **SH3D Capability:** When importing a blueprint PDF/PNG, SH3D presents a 2-step wizard:
  1. The user draws a reference line over a known dimension on the image (e.g. a 20' 0" dimension line).
  2. The user inputs the real length ("20 ft"), and the image is automatically rescaled to pixel-perfect architectural scale.
- **Recommendation for EstiSketch:** Implement this two-click calibration line tool for imported background images.

### Gap 3: Edge-to-Edge Wall Snapping for Different Wall Thicknesses
- **SH3D Capability:** When joining an 8" exterior concrete wall to a 4.5" interior partition wall, users can choose to align exterior faces flush, interior faces flush, or centerlines flush.
- **Recommendation for EstiSketch:** Extend `snapping_manager.py` to snap not just centerline-to-centerline, but exterior-face to exterior-face and interior-face to interior-face.

### Gap 4: Architectural 2D Fixtures & Cabinetry Library
- **SH3D Capability:** Built-in standard library of kitchen base/wall cabinets, sinks, ranges, refrigerators, bathtubs, showers, toilets, beds, and tables with clean 2D architectural plan symbols.
- **Recommendation for EstiSketch:** Add parameterized 2D symbols for kitchen cabinets (base & upper), bathroom fixtures (toilet, tub, vanity, shower), and major appliances.

### Gap 5: Scaled Architectural PDF Print / SVG Export
- **SH3D Capability:** Prints plans to scale (1/4" = 1'-0", 1:50, etc.) on standard paper sizes (Arch D, Tabloid, Letter) with optional title block, project metadata, and vector SVG output.
- **Recommendation for EstiSketch:** Add Cairo-based vector SVG export and scaled PDF sheet plotting.

---

## 3. Ranked SweetHome3D Parity Roadmap Items (Added to TODO.md)
1. **Background Image Blueprint Calibration Wizard** (Two-click reference distance calibration).
2. **Edge-to-Edge Wall Snapping** (Aligning outer/inner wall faces for differing wall thicknesses).
3. **Continuous Dimension Chains & Leader Callout Arrows**.
4. **Architectural Fixtures & Cabinetry 2D Symbols** (Kitchen base/upper cabinets, bath fixtures, appliances).
5. **Room Cutouts / Holes** (Support for stairwell openings and lightwells in room polygons).
6. **Scaled Vector Export** (Architectural scaled PDF plotting with title block and vector SVG).
