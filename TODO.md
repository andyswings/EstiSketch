# TODO / Backlog

## 🚀 High Priority (do next)
- [ ] Add Stairs tool (straight, L-shaped, U-shaped)
- [ ] Add Circles/Arcs drawing tool
- [ ] Create Furniture & Fixture library
- [ ] Add automatic room area calculations

## ✨ Core Features (essential functionality)

### Drawing Tools (more of a parametric cad tool set) (long term)
- [ ] Rectangle/Square tool
- [ ] Polygon tool  
- [ ] Offset tool (parallel lines at distance)
- [ ] Trim/Extend tool
- [ ] Fillet/Chamfer (rounded/beveled corners)
- [ ] Mirror tool
- [ ] Array/Pattern tools (grid/circular)
- [ ] Scale tool
- [ ] Align/Distribute tools
- [ ] Hatching/Fill patterns

### Architectural Elements
- [ ] Roof design (gable, hip, flat, custom pitches)
- [ ] Roof components (trusses, rafters, ridges, valleys)
- [ ] Columns/Posts
- [ ] Beams
- [ ] Foundations (slab, crawlspace, basement)
- [ ] Ceiling types (dropped, vaulted, cathedral)
- [ ] Railings/Guardrails (deck, stair, balcony)
- [ ] Add Cabinet Tool
- [ ] Countertops (custom shapes)
- [ ] Appliances library
- [ ] Moldings (crown, base, chair rail, casing)

### Dimensions & Annotations
- [ ] Dimension chains (continuous dimensions)
- [ ] Radial/diameter dimensions
- [ ] Angular dimensions
- [ ] Leaders/Callouts
- [ ] Text styles (save and reuse formatting)
- [ ] Area/Perimeter labels
- [ ] Schedules (door/window/material)
- [ ] Tags/Labels (room names, numbers)

### 3D Visualization (long term)
- [ ] Basic 3D modeling/view
- [ ] 3D navigation (orbit, walk through)
- [ ] Material textures in 3D
- [ ] Lighting (sun position, artificial lights)
- [ ] Rendering (photorealistic)
- [ ] Camera views (save perspectives)
- [ ] Section cuts (slice through building)

## 📊 Analysis & Documentation

### Calculations
- [ ] Header sizes and controls autocalculation based on loads (for window/door header calculations)
- [ ] Volume calculations (concrete, excavation)
- [ ] Live dimension updates
- [ ] Energy analysis (heating/cooling loads)
- [ ] Code compliance checking

### Documentation
- [ ] Sheet management
- [ ] Title blocks (customizable templates)
- [ ] Revision tracking
- [ ] Drawing numbering
- [ ] Detail libraries
- [ ] Print layouts with multiple views

## 🔄 Import/Export

### Import
- [ ] DWG/DXF import (AutoCAD files)
- [ ] IFC import (BIM standard)
- [ ] SketchUp (.skp)
- [ ] PDF/images as underlay
- [ ] CSV data import

### Export  
- [ ] Export to SweetHome3d
- [ ] Export to PDF
- [ ] Export to DXF
- [ ] DWG export
- [ ] IFC export (BIM)
- [ ] Images (PNG, JPG) export
- [ ] 3DS/OBJ export (3D models)
- [ ] CSV/Excel export (schedules, takeoffs)

## ⚡ Productivity & Workflow

### Productivity Features
- [ ] Templates (start from prebuilt designs)
- [ ] Favorites/palette (quick access)
- [ ] Search (find objects, commands)
- [ ] Measurement input (type exact dimensions) (rudimentary implementation complete)
- [ ] Auto-save
- [ ] Backup system
- [ ] Recovery (unsaved work)
- [ ] Customizable UI

### Smart Features
- [ ] Parametric objects (objects with rules)
- [ ] Constraints (enforce relationships)
- [ ] Automatic wall join improvements
- [ ] Wall cleanup (overlapping walls)
- [ ] Auto-heal (fix gaps)
- [ ] Smart guides (alignment suggestions)
- [ ] Object snap tracking

## 🏗️ Specialized Tools

### Engineering
- [ ] Structural analysis (loads, stresses)
- [ ] Material properties (steel, concrete, wood)
- [ ] Load calculations
- [ ] Stress/strain analysis

### Electrical/Plumbing/HVAC
- [ ] Electrical symbols (outlets, switches, lights, panels)
- [ ] Plumbing fixtures (sinks, toilets, showers, tubs)
- [ ] HVAC (vents, returns, units)
- [ ] Circuit calculations
- [ ] Pipe routing
- [ ] Duct design

### Site/Landscape
- [ ] Site plans (property boundaries)
- [ ] Terrain modeling (contours, slopes)
- [ ] Landscaping (trees, plants, hardscape)
- [ ] Parking/driveways
- [ ] Fencing
- [ ] Pools/water features
- [ ] Grading (elevation changes)

### Kitchen/Bath Specialized
- [ ] Cabinet designer (custom cabinets)
- [ ] Countertop templates
- [ ] Backsplash patterns
- [ ] Tile layouts

## 🎓 Help & Learning
- [ ] Keyboard shortcuts cheat sheet
- [ ] Built-in tutorials
- [ ] Tooltips (hover help)
- [ ] Video tutorials
- [ ] Sample projects
- [ ] Help documentation
- [ ] Community forum

## 🎨 Presentation & Visualization
- [ ] Line weights/types control
- [ ] Colors by layer
- [ ] Transparency
- [ ] 2D shadows
- [ ] Rendering styles (sketch, blueprint, presentation)
- [ ] Dark mode toggle
- [ ] Themes

## 🛠️ Tech Debt / Refactoring

## 🐛 Known Bugs / FIXMEs
- [ ] When drawing a loop of walls, the last wall is not closed (not mitered with the first wall)
- [ ] Creating a text object does not seem to make the canvas dirty (no prompt to save when closing)

## 💡 Currently Working On
- [ ] Finish Material Estimator
- [ ] Build Cost Estimator
- [ ] Implement Footer rendering

## Done ✅ (latest first)
- [x] Fixed issue where side panel was too needy (pops out when anything is selected event when we've clicked on the toggle to hide it) (2025-12-25)
- [x] Added support for multiple story/floor levels (2025-12-25)
- [x] Implemented a basic Layers system (2025-12-25)
- [x] Add right click menu option to mirror offset of dimension to other side of dimension line (2025-12-25)
- [x] Allow adding points to an existing room - double-click on edge to insert (2025-12-25)
- [x] Allow moving an entire room (dragging from inside the room) (2025-12-25)
- [x] Fixed snapping to work in multiple directions at the same time (e.g. horizontal and vertical) also, end points should snap to other end points of lines and when directly above/below or left or right of any other point (2025-12-25)
- [x] Polylines are now editable (segments moved, endpoints repositioned) (2025-12-25)
- [x] Rooms no longer closed with duplicate point - only unique vertices stored (2025-12-25)
- [x] Add Ctrl+A to select all objects (2025-12-25)
- [x] Dimensions can now be moved and edited - implemented dimension dragging and editing (2025-12-25)
- [x] Room points can now be moved (dragged) - implemented vertex dragging (2025-12-25)
- [x] Improved snapping is too course (the snapping "band" is too large) (2025-12-25)
- [x] Fixed Walls etc. use snapping even when it is disabled in the settings (2025-12-25)
- [x] Right click menu should not show anything when no object is selected unless the clipboard is not empty (and then it should show "Paste" option for now) (2025-12-25)
- [x] Fixed text object rendering bug caused by Cairo context corruption (2025-12-24)
- [x] Fixed "Separate Walls" - now separates selected walls into individual sets (2025-12-24)
- [x] Fixed box selection interference when moving text objects (2025-12-24)
- [x] Walls are now draggable with connected walls moving together (2025-12-24)
- [x] Refactor the Canvas to a more modular structure (2025-12-24)
- [x] Add Copy / Cut / Paste to the right click menu (2025-12-18)
- [x] Added Cut, Copy, Paste functionality (2025-12-18)
- [x] Fixed changing wall height from properties dock is not persistent (2025-12-11)
- [x] Implement multi-door object editing (with properties dock) (2025-12-11)
- [x] Implement multi-window object editing (with properties dock) (2025-12-11)
- [x] Implement multi-wall object editing (with properties dock) (2025-12-11)
- [x] Implement Dimension Tool (with auto-dimensioning) (2025-12-07)
- [x] Implement Multi-Text object editing (with properties dock) (2025-12-07)
- [x] Enable changing text color (2025-12-07)


_Last updated: 2025-12-25_