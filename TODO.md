# TODO / Backlog

## 🚀 High Priority (do next)
- [ ] Foundation design tools
- [ ] Foundation - Footers
- [ ] Foundation - Slabs
- [ ] When a layer is selected, the layers under it should be set to 25% opacity
- [ ] Don't allow objects to be placed or edited on a locked layer.

## ✨ Core Features (essential functionality)

### Architectural Elements
- [ ] Asymetrical roof pitches
- [ ] Roof design - Complex roof shapes
- [ ] Roof components (trusses, rafters, ridges, valleys)
- [ ] Columns/Posts
- [ ] Beams
- [ ] Foundations (slab, crawlspace, basement)
- [ ] Ceiling types (dropped, vaulted, cathedral)
- [ ] Add Stairs tool (straight, L-shaped, U-shaped, spiral)
- [ ] Railings/Guardrails (deck, stair, balcony)
- [ ] Add Cabinet Tool
- [ ] Countertops (custom shapes)
- [ ] Appliances library
- [ ] Moldings (crown, base, chair rail, casing)

### Dimensions & Annotations
- [ ] Add automatic room area calculations
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
- [ ] Create Furniture & Fixture library
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

## 💡 Takeoffs
- [ ] Material Estimator
- [ ] Cost Estimator

## Done ✅ (latest first)
- [x] Fixed wall loops are not always mitered correctly between the last and first wall and the issue is not fixed by joining the walls or joining connected walls. (2026-01-18)
- [x] Implemented custom roof pitches (editable pitch, overhang, material) (2026-01-18)
- [x] Added tool hint for the roof design tool (2026-01-15)
- [x] Added shift + R as shortcut for roof design tool (2026-01-15)
- [x] Added smart inference for roof design only requires 2 walls to be marked to create a gable roof (2026-01-15)
- [x] Added visual separator between dynamic tool buttons and static zoom controls (2026-01-15)
- [x] Properties panel now automatically hides when selection is cleared (2026-01-15)
- [x] Toolset switching now clears selection, closes properties panel, and resets to first tool in set (2026-01-15)
- [x] Properties panel now starts minimized on application launch (2026-01-15)
- [x] Implemented roof design - Gable roofs (basic implementation complete) (2026-01-15)
- [x] Added **Toolset Selector** - dropdown in toolbar to switch between tool categories: Basic, Annotation, Foundation, Roof, Interior Design (2026-01-14)
- [x] Added ability to edit curved walls via click and drag or by using the properties panel (radius, arc length, etc.) (2026-01-14)
- [x] Added right-click context menu options to convert between curved and straight walls (2026-01-14)
- [x] Fixed windows and doors are now drawn tangent to the curve on curved walls. (2026-01-13)
- [x] Added **Curved Walls** feature - integrated into wall tool, press Shift+C after 2nd point to create 3-point arc walls with live preview and radius display (2026-01-13)
- [x] Fixed rendering artifact where circles/arcs displayed unwanted lines to dimensions (2026-01-13)
- [x] Fixed when multiple objects of different types are selected, the properties panel now enables all applicable tabs. (2026-01-12)
- [x] Added polyline tab to properties panel (2026-01-12)
- [x] Added context-aware tool usage hints to the status bar (2026-01-09)
- [x] Added "dirty" indicator to the left side of the status bar (green circle when clean, red circle when dirty) (2026-01-09)
- [x] Fixed dimension moving - when you try to move the dimension it no longer resets the dimension to the original angle and length (2026-01-09)
- [x] Added Tab-to-cycle selection for overlapping objects - press Tab to cycle through objects at mouse position (2026-01-08)
- [x] Editing an arc endpoint, the radius now changes only as required to maintain the same distance between the arc peak and a straight line between the endpoints. (2026-01-08)
- [x] Fixed arc mid handle editing - endpoints now stay fixed while radius changes (2026-01-08)
- [x] Fixed circle/arc dragging - objects can now be moved by dragging (2026-01-08)
- [x] Fixed arc endpoint editing to adjust radius instead of rotating along arc (2026-01-08)
- [x] Added live dimensions for arc span creation (first step) (2026-01-08)
- [x] Corrected arc dimension orientation (2026-01-05)
- [x] Fixed missing live dimensions during circle/arc editing (2026-01-05)
- [x] Fixed selection state visual loss during handle dragging (2026-01-05)
- [x] Added support for editing circle and arc dimensions (change radius) (2026-01-05)
- [x] Added circle and arc tab to properties panel (2026-01-05)
- [x] Added live dimensions for circle and arc objects while drawing (2026-01-05)
- [x] Fixed NameError when drawing circle and arc objects (2026-01-05)
- [x] Added Circles/Arcs drawing tools (2026-01-03)
- [x] Added "Default Level Height" setting to Settings Dialog and Config (2026-01-03)
- [x] Added support for changing the elevation of a level (Level Manager UI update) (2026-01-03)
- [x] Fixed wall loop closure to correctly miter join the end with the start (2026-01-03)
- [x] Fixed wall line thickness scaling when zooming (2026-01-03)
- [x] Fixed manual dimension adjustment to snap to wall face corners (refined) (2026-01-03)
- [x] Fixed mirrored dimension not updating to opposite wall face (2026-01-03)
- [x] Fixed auto-dimension alignment to snap to wall edges instead of centerlines (2026-01-03)
- [x] Creating a text object now makes the canvas dirty (2026-01-03)
- [x] Application window now correctly maximizes on startup if configured (2026-01-03)
- [x] Sidebar now correctly collapses by default on startup (2026-01-03)
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


_Last updated: 2026-01-18_