# EstiSketch Alpha Release Notes

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
To install the package locally:
```bash
pip install dist/EstiSketch-0.2.0-alpha-py3-none-any.whl
```

## Usage
To run the application:
```bash
estisketch
```

## How to Contribute
Please report any bugs or feature requests to the issue tracker.
