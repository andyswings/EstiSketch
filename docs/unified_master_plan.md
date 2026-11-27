# EstiSketch Unified Master Plan & Monetization Roadmap

_Last updated: 2026-11-27_

This document consolidates EstiSketch's commercial strategy, codebase audit, technical architecture plans, and feature backlog into one canonical execution roadmap:

- [EstiSketch_Execution_Plan_&_Monetization_Roadmap.docx](EstiSketch_Execution_Plan_&_Monetization_Roadmap.docx) — commercial positioning, pricing, Free/Pro/AI tiers, and platform strategy
- [3d_asset_library_plan.md](3d_asset_library_plan.md) — Phases A1–A5 asset pipeline, `manifest.json` v2, `.glb`/`.obj` Import Wizard, and `.esk-pack` ecosystem
- [native_3d_architecture.md](native_3d_architecture.md) — Rust + OpenGL 3.3 engine, `.esk` archive, and Blender sync (Phases 0–6 complete)
- [blender_standalone_plan.md](blender_standalone_plan.md) — zero-addon Blender integration (complete)
- [sh3d_2d_parity.md](sh3d_2d_parity.md) & [sh3d_parity_plan.md](sh3d_parity_plan.md) — Sweet Home 3D 2D parity (Phases 1–7 complete)
- [../TODO.md](../TODO.md) — live release-stage backlog and completed changelog

---

## 1. Product Mission, Scope Guardrail & Market Positioning

- **Product Mission:** Lightweight, high-performance desktop drafting and estimating built with Python, GTK 4, PyCairo, and a native Rust/OpenGL 3.3 3D engine (`estisketch_3d_core`, `estisketch_3d_gl`, `estisketch_3d_py`). Serves small-to-mid residential contractors, framers, remodelers, ADU/barndominium builders, and hands-on owner-builders who need construction-grade framing and takeoff precision without enterprise CAD/BIM bloat or steep subscriptions.
- **Scope Guardrail (1–4 Unit Wood-Frame Residential):** EstiSketch strictly targets single-family homes, ADUs, barndominiums, and light multi-family builds (duplexes, triplexes, quadplexes). Commercial high-rises, large apartment complexes, heavy civil/site engineering, and full FEA structural engineering are explicitly excluded from v1.x to preserve speed and focus.
- **Platform Strategy:**
  - **Windows-First Commercial Target:** Self-contained Windows installer (`.exe` / `.msi`) via `packaging/build_windows_installer.ps1` and `.github/workflows/release.yml`.
  - **First-Class Linux:** Native `.deb` (`packaging/build_deb.py`) and AppImage (`packaging/build_pyinstaller_appimage.sh`) maintained alongside development.
  - **Deferred macOS:** Deferred until Windows Pro revenue justifies Apple Developer fees, notarization CI, and macOS GTK 4 QA.

---

## 2. Cross-Document Status Audit

### 2.1 Existing Plan Documents vs. Actual Codebase

| Plan Document | Original Scope | Current Codebase Status | Role Going Forward |
|---|---|---|---|
| **Monetization Roadmap (`.docx`)** | Free vs. Pro ($99–$149 one-time) vs. Cloud AI Credits; Windows-first + Linux; 1–4 unit guardrail; v1.0 Free → v1.0 Pro → v1.x AI → v2.0. | **Ahead on 3D & 2D drafting**, **behind on commercial Pro deliverables**: `Dialogs/estimate_cost.py` is still a `"Coming Soon"` stub; no `.sh3d` export, no DXF export, no `.xlsx` BOM, no custom wall assembly/template presets, no light multi-family, no license key gating, and no LLM bridge. | **Commercial North Star** governing tier boundaries, pricing, and release order. |
| **SH3D 2D Parity (`sh3d_2d_parity.md`, `sh3d_parity_plan.md`)** | 7-phase 2D drafting parity with Sweet Home 3D. | **~98% Complete** (all 7 phases shipped). Only `.sh3d` **export** (promised in v1.0 Free) and 3D ceiling texture patterns remain. | Fold `.sh3d` export into Stage 1; ceiling textures into Stage 5. |
| **Native 3D Architecture (`native_3d_architecture.md`)** | Rust + OpenGL 3.3 viewport, `SceneIR`, `.esk` ZIP archive, `.glb` export, interactive 3D editing, MRT SSAO. | **100% Complete** (Phases 0–6 shipped). Exceeds v1.0 Free and covers most of v2.0's originally planned 3D engine. | Foundation complete; remaining optional views/section cuts move to Stage 5/6. |
| **Blender Standalone (`blender_standalone_plan.md`)** | Zero-addon `"Open 3D in Blender..."` with `Ctrl+S` live delta sync. | **100% Complete**. Automatically picks up new `assets_3d/` assets via `NativeSceneSession.export_glb`. | Complete differentiator. |
| **3D Asset Library (`3d_asset_library_plan.md`)** | Phases A1–A5: `tools/asset_pipeline/`, `manifest.json` v2, ~150 core models (`<10 MB`), upgraded browser, 4-step `.glb`/`.obj` Import Wizard, `.esk-pack` manager. | **~15% Complete**: all 46 `FIXTURE_CATALOG` symbols have procedural Rust 3D geometry + 8 hero `.glb` files in `src/EstiSketch/assets_3d/`, but `tools/asset_pipeline/`, `manifest.json` v2, ~100 expansion models, Import Wizard, and `.esk-pack` manager are unbuilt. | Split cleanly: A1–A3 in **Stage 3 (`v1.1`)**, A4–A5 in **Stage 5 (`v1.3`)** so asset production does not block `v1.0` launch/revenue. |
| **Backlog Audit (`TODO.md`)** | 86 open backlog items audited against the codebase. | **6 already completed**, **26 partially completed**, **54 unstarted**. | Realigned to **Stages 1–6** + Guardrail-Deferred list in `TODO.md`. |

### 2.2 Six Backlog Items Verified Complete (Moved to `TODO.md > Done ✅`)

| Backlog Item | Codebase Verification |
|---|---|
| **Add automatic room area calculations** | `src/EstiSketch/geometry/room_holes.py` (`room_gross_area_sqft`, `room_floor_area_sqft`, `room_ceiling_area_sqft`, `room_slab_volume_cuft`), `src/EstiSketch/Takeoff/building_takeoff.py` (`extract_room_areas`, `generate_room_area_report`), `src/EstiSketch/Dialogs/estimate_materials.py`. |
| **Basic 3D modeling/view** | `src/EstiSketch/View3D/viewport.py`, `src/EstiSketch/View3D/editor.py`, `rust/crates/estisketch_3d_core/src/mesher.rs` (`2D \| Split \| 3D` switcher, live delta sync, interactive 3D editing). |
| **3D navigation (orbit, walk through)** | `rust/crates/estisketch_3d_gl/src/camera.rs`, `src/EstiSketch/View3D/viewport.py` (Orbit/Dollhouse, WASD Walkthrough, Jump-to-Room, Fit, 6 presets). |
| **Material textures in 3D** | `rust/crates/estisketch_3d_gl/src/shaders.rs`, `rust/crates/estisketch_3d_core/src/materials.rs` (procedural GLSL shaders + 3D Paint Brush + `.glb` PBR materials). |
| **Export to PDF** | `src/EstiSketch/Printing/print_renderer.py` (`export_pdf`), `src/EstiSketch/Printing/print_dialog.py` (scaled/tiled PDF + SVG + supplier quote PDF). |
| **Living/bedroom furniture library** | `src/EstiSketch/fixtures_catalog.py` (46 symbols including living, bedroom, dining, and office furniture), `rust/crates/estisketch_3d_core/src/fixtures.rs`. |

### 2.3 Twenty-Six Partially Completed Items (Existing Foundation vs. Remaining Gap)

- **Settings UI (`Dialogs/settings_ui.py`):** 43-row flat grid exists, including dead/unwired keys (`ENABLE_AUTO_SAVE`, `SHOW_RULERS`, `DEFAULT_FILE_FORMAT`) -> *needs categorized `Gtk.StackSidebar` rework & cleanup (Stage 1)*.
- **Auto-Save (`config.py`):** `ENABLE_AUTO_SAVE` flag exists -> *needs timer, rolling backup, and crash recovery (Stage 1)*.
- **Sample Projects (`examples/`):** 10 XML projects exist -> *needs in-app `File > Sample Projects` menu (Stage 1)*.
- **Images (PNG, JPG) Export (`View3D/viewport.py`):** Offscreen 3D `save_snapshot_png` exists -> *needs File/Export UI for 2D floor plan and 3D PNG/JPG (Stage 1)*.
- **Takeoff & Estimates (`Takeoff/building_takeoff.py`, `TakeoffEngine/`):** Lumber cut-list packing, sheathing, finishes, and room areas exist -> *needs pipeline consolidation & Free summary vs. Pro Cost/Markup engine (Stage 2)*.
- **Schedules (`TakeoffEngine/interior.py`, `Takeoff/building_takeoff.py`):** Opening counts and fixture/material reports exist -> *needs formal schedule tables + drawing tags `D1`/`W1` (Stage 2)*.
- **Templates (`floor_plan_generator/`, `examples/`):** Parametric generator and sample projects exist -> *needs reusable user project templates & custom wall assemblies (Stage 2)*.
- **Columns/Constraints & Parametric Objects:** Doors, windows, stairs, roofs, and cabinets are parametric -> *needs Columns/Posts with edge-array spacing + door-centering constraints (Stage 3) and general user constraints (Stage 5)*.
- **Ceiling Types (`config.py`, `components.py`):** `TAKEOFF_CEILING_TYPE` (`flat`/`vaulted`) and angled walls exist -> *needs per-room dropped/vaulted/cathedral 3D ceiling geometry & UI (Stage 3)*.
- **Railings/Guardrails:** Stair railings complete in 2D/3D/takeoff -> *needs standalone deck/porch/balcony guardrails (Stage 3)*.
- **HVAC (`fixtures_catalog.py`):** Major units (`water_heater`, `furnace`, `air_conditioner`) exist -> *needs supply vents, return grilles, and thermostats (Stage 3)*.
- **Wall Join Improvements (`geometry/wall_joins.py`, `snapping_manager.py`):** Miter joins and face-flush snapping exist -> *needs 3-way T-junctions, collinear cleanup, and gap auto-heal (Stage 3)*.
- **Search (`Dialogs/layers_panel.py`, `Dialogs/fixture_browser.py`):** Object & fixture search exist -> *needs global command palette `Ctrl+K` (Stage 5)*.
- **Measurement Input & Live Dimensions (`Dialogs/length_input_dialog.py`):** Length dialog, live drawing preview, and chain double-click editing exist -> *needs inline modeless typing and wall-linked associative dimensions (Stage 5)*.
- **Smart Guides & Snap Tracking (`snapping_manager.py`):** Alignment, face-flush, and tangent guides exist -> *needs equal-spacing smart guides and polar snap tracking (Stage 5)*.
- **3D Lighting:** Sun time-of-day slider, north azimuth, PCF shadows, and SSAO exist -> *needs interior artificial light sources (Stage 6)*.
- **3D Rendering (Photorealistic):** Stylized GLSL + SSAO + Blender live sync exist -> *optional in-app polish (Stage 5)*.
- **3D Camera Views (`esk_archive.py`, `View3D/viewport.py`):** Active view state saves in `views.json` + 6 presets -> *needs named multi-bookmark camera UI (Stage 5)*.
- **3D Section Cuts:** Dollhouse level slicing & Auto-Hide Roofs exist -> *needs vertical/angled clipping section planes (Stage 5)*.
- **Line Weights & Rendering Styles (`Printing/print_settings.py`, `View3D/viewport.py`):** 10-category print line weights and 4 3D styles exist -> *needs screen line weights and 2D sketch/blueprint/presentation styles (Stage 5)*.
- **Moldings:** Per-side baseboards (2D/3D/takeoff) and 3D casings exist -> *needs crown, chair rail, and selectable profiles (Stage 5)*.
- **Tile Layouts:** 2D/3D floor tile patterns exist (`Canvas/floor_patterns.py`) -> *needs backsplash and wall tile layouts (Stage 5)*.
- **Volume Calculations (`TakeoffEngine/foundation.py`, `room_holes.py`):** Slab & thickened-edge concrete exist -> *needs footer concrete and excavation/cut-fill volumes (Stage 5)*.
- **Sheet Management, Title Blocks & Drawing Numbering (`Printing/print_settings.py`, `print_renderer.py`):** Per-level/tiled sheets, `sheet_prefix` (`A-1`), `R#C#`, and editable title block exist -> *needs multi-view layouts, templates/logos, revision tracking, and custom numbering (Stage 5)*.
- **Header Autocalculation (`TakeoffEngine/wall_framing.py`):** Span-table sizing exists -> *needs structural load-driven sizing controls (Stage 6)*.
- **Code Compliance Checking (`geometry/design_checks.py`):** 11 architectural layout checks exist -> *needs expanded IRC/IBC code checks (Stage 6)*.

---

## 3. Commercial Tier & Feature Gating Architecture

EstiSketch ships as a **single codebase** with an offline-friendly Ed25519 signed license verification module (`licensing/`, paired with Lemon Squeezy or Paddle as Merchant of Record). Standard local drafting, saving, and exports never require cloud credits or always-online DRM.

| Feature Category | Free Tier (`v1.0 Free` — Free Forever, Ad-Free, No Watermarks) | Pro Tier (`v1.0 Pro` — $99–$149 One-Time Major-Version License) | Cloud AI Add-On (`v1.x` — Credit Packs) |
|---|---|---|---|
| **2D & 3D Drafting** | Full 2D drafting (curved walls, roofs, stairs, layers/levels, blueprint tracing, dimension chains), 46+ core fixtures/furniture, native 3D viewer + orbit/walkthrough + live Blender sync, unlimited `.esk`/`.xml` saves, auto-save/recovery, basic architectural layout checks. | Everything in Free + custom wall assemblies, reusable project templates, Light Multi-Family (1–4 units w/ mirrored layouts), Columns/Beams/Ceilings/Guardrails, Electrical/HVAC symbols, Wall Cleanup & Auto-Heal. | Full 2D/3D capabilities. |
| **Interoperability & Outputs** | Sweet Home 3D (`.sh3d`) import & export, 2D/3D PNG/JPG image export, `.glb` 3D export. | Scaled multi-page/tiled PDF & SVG plan sets, DXF CAD export/import, native Excel (`.xlsx`) & CSV BOM, formal Door/Window/Material schedules with plan tags (`D1`/`W1`). | Standard Pro exports supported. |
| **Estimating & Takeoffs** | Basic Room sq ft, Wall linear feet, and Perimeter summaries (+ on-canvas Room Tags). | Full automated material takeoffs with lumber-waste cut-list optimization, Cost/Labor/Markup pricing engine, and combined multi-unit takeoffs. | Standard Pro takeoffs supported. |
| **AI & Automation** | Not included. | **Local AI Mode (0 credits, 100% private):** In-app guided installer for Ollama / `llama.cpp` + multi-option AI/parametric Floor Plan Generator. | **Hosted Cloud AI (pay-as-you-go credits):** Serverless parametric/AI floor plan & workflow generation for light laptops without a local GPU. |
| **Updates & Upgrades** | Free ongoing v1.x updates. | Free v1.x minor point releases (`v1.1`, `v1.2`, `v1.3`); 30–40% loyalty discount on `v2.0` major upgrade. | Pay-as-you-go credit balance. |

---

## 4. Strategic Engineering Decisions

1. **Unify Takeoff Before Building Cost & Markup Pricing:** Consolidate legacy `src/EstiSketch/Takeoff/building_takeoff.py` (1,798 lines) and modular `src/EstiSketch/TakeoffEngine/` into one canonical takeoff output model *before* replacing the `Dialogs/estimate_cost.py` stub in Stage 2. Every line item then flows cleanly into Pro pricing, `.xlsx` BOMs, and multi-unit rollups.
2. **Stage the 3D Asset Library (`A1–A5`) Behind `v1.0`:** All 46 existing symbols already render cleanly in 2D and 3D with zero box placeholders. Ship `A1–A3` (~120–150 models + automated pipeline + grid browser) in **Stage 3 (`v1.1`)** and `A4–A5` (`.glb`/`.obj` Import Wizard + `.esk-pack` ecosystem) in **Stage 5 (`v1.3`)** so art pipeline work does not delay first Pro revenue.
3. **Incremental Codebase Cleanup:** Address oversized UI/canvas monoliths (`Dialogs/properties_dock.py`, `Canvas/events_selection.py`, `Canvas/canvas_draw.py`) and split roof wrappers incrementally alongside Stage 5 polish rather than stalling `v1.0 Free`/`Pro` shipments.
4. **Enforce the 1–4 Unit Wood-Frame Guardrail:** Keep commercial high-rises, full structural FEA, MEP pipe/duct routing, and civil terrain engineering explicitly parked outside `v1.x`.

---

## 5. Unified Release-Driven Roadmap (Stages 1–6)

### Stage 1 — `v1.0 Free` Public Launch *(Adoption & Word-of-Mouth Engine)*
- **Goal:** Ship an ad-free, watermark-free Free drafter on Windows (`.exe`) and Linux (`.deb`/AppImage) that beats SH3D for residential sketching.
- **Scope & Key Files:**
  - Rework `Dialogs/settings_ui.py` into categorized `Gtk.StackSidebar` + `Gtk.Stack` pages; wire or remove dead settings (`ENABLE_AUTO_SAVE`, `SHOW_RULERS`, `DEFAULT_FILE_FORMAT`).
  - Implement periodic **Auto-Save, Rolling Backups, and Startup Crash Recovery** in `main.py` / `config.py` / `esk_archive.py`.
  - Replace the placeholder `Dialogs/help_dialog.py` with a searchable **Help Center, Keyboard Shortcuts Cheat Sheet, and Built-In Starter Tutorials** (reusing `Resources/tool_hints.py`).
  - Add `File > Sample Projects` menu surfacing `examples/demo_houses/` and `examples/bathroom_remodel/`.
  - Add on-canvas **Room Tags & Area/Perimeter Labels** (`Canvas/wall_room_renderer.py`, `Dialogs/properties_dock.py`) plus a Free-tier **Basic Summary Panel** (room sq ft, wall linear feet, perimeter).
  - Add **2D & 3D Image Export (PNG / JPG)** (`Canvas/`, `View3D/viewport.py`, `file_menu.py`).
  - Add **Sweet Home 3D (`.sh3d`) Export** alongside `sh3d_importer.py`.
  - End-to-end packaging & smoke QA on Windows (`packaging/build_windows_installer.ps1`) and Linux (`.deb` / AppImage via `.github/workflows/release.yml`) with `_native_3d` bundled.
- **Exit Criteria:** Clean Windows & Linux installers pass headless `pytest`, `flake8`, and smoke launch tests; zero dead Settings controls or placeholder Help text; `.sh3d` round-trip and crash recovery verified.

### Stage 2 — `v1.0 Pro` Commercial Launch *(First Revenue Milestone — $99–$149 One-Time)*
- **Goal:** Deliver the contractor takeoff, pricing, and CAD export suite that justifies the one-time Pro license.
- **Scope & Key Files:**
  - Unify `Takeoff/` and `TakeoffEngine/` into one clean takeoff pipeline with lumber-waste cut-list minimization (`TakeoffEngine/lumber.py`).
  - Build the **Cost, Labor & Markup Pricing Engine** replacing `Dialogs/estimate_cost.py` (editable unit prices, labor rates, waste/tax/overhead/markup rules, contractor vs. client bid views).
  - Implement **DXF Export (and basic DXF Import)** for 2D plans.
  - Implement **Native Excel (`.xlsx`) BOM & Cost Export** (`TakeoffEngine/builder.py` / `Dialogs/takeoff_dialog.py`).
  - Add **Formal Door, Window & Material Schedules + Drawing Plan Tags (`D1`, `W1`)** across 2D canvas, PDF, DXF, and Excel exports.
  - Add **Custom Wall Assemblies & Reusable Project Templates**.
  - Implement offline-friendly **Ed25519 License Key verification & Free/Pro feature gating** (`licensing/`).
  - Launch product website, Merchant of Record checkout (Lemon Squeezy or Paddle), and initial trade YouTube walkthroughs.
- **Exit Criteria:** A contractor can draft a home, apply custom wall assemblies, generate a waste-optimized BOM + marked-up bid, and export scaled PDF plan sets, DXF, and `.xlsx` BOMs under an offline-verified Pro license key.

### Stage 3 — `v1.1 Pro` Builder Expansion *(Free Minor Update for v1.0 Pro Owners)*
- **Goal:** Deepen Pro value for framers, remodelers, and ADU/duplex builders while expanding the core 3D asset library (`A1–A3`).
- **Scope & Key Files:**
  - **Light Multi-Family Mode (1–4 Units):** Unit tagging, mirrored/linked duplex/triplex/quadplex layouts, and combined multi-unit framing, material, and cost takeoffs.
  - **Architectural Elements (2D + 3D + Takeoff + XML):**
    - `Columns/Posts` (rectangular, round, square; edge-array spacing or count; independent post editing; centering/symmetry constraints relative to doors).
    - `Beams` (load-bearing, decorative, cantilever; material & dimensions or auto-calculated sizing).
    - Per-room `Ceiling Types` (dropped, vaulted, cathedral 3D geometry & UI).
    - Standalone `Railings/Guardrails` (deck, porch, balcony).
  - **Electrical & HVAC Plan Symbols:** Outlets, switches, lights, panels, supply vents, returns, thermostats (`fixtures_catalog.py`, `Canvas/render_fixtures.py`, `estisketch_3d_core/`).
  - **Wall Cleanup & Auto-Heal:** Merge overlapping collinear walls, heal tiny near-miss endpoint gaps, and improve 3-way T-junction / mixed-thickness joins.
  - **3D Asset Library Phases A1–A3 (`docs/3d_asset_library_plan.md`):** Build `tools/asset_pipeline/` (`normalize_glb.py`, `validate_assets.py`, offscreen thumbnails, `manifest.json` v2), expand core catalog to ~120–150 stylized models (`<10 MB`), render `"polylines"` 2D symbols, and upgrade `Dialogs/fixture_browser.py` with grid/2D/3D previews, tags, Favorites, and Recents.
- **Exit Criteria:** Multi-family 1–4 unit projects produce unified takeoffs; all new architectural/MEP elements work across 2D, 3D, `.esk`/`.xml`, and takeoffs; asset CI gate passes `<10 MB` and `CC0-1.0`/`MIT` provenance rules.

### Stage 4 — `v1.2` Dual-Mode AI Home Generator & Credit Add-On *(Margin-Protected Expansion)*
- **Goal:** Turn `floor_plan_generator/` into a unified Local + Cloud AI residential design generator.
- **Scope & Key Files:**
  - Standardize `floor_plan_generator/` on an OpenAI-compatible + JSON-schema interface supporting single-family and 2–4 unit multi-family presets, validated by `geometry/design_checks.py`.
  - Build the **In-App Guided Local AI Installer** (RAM/VRAM detection, quantized model recommendation, automated zero-terminal setup for Ollama or `llama.cpp`; 0 credits for Pro users).
  - Deploy serverless **Hosted Cloud AI API**, credit metering, and MoR credit pack checkout (zero impact on offline drafting/export).
- **Exit Criteria:** Pro users can run local AI floor plan generation with zero terminal steps, and light-laptop users can purchase and spend optional cloud AI credit packs.

### Stage 5 — `v1.3` Asset Ecosystem & Presentation Polish *(Retention & Community Flywheel)*
- **Goal:** Complete SH3D-grade asset extensibility, presentation controls, documentation polish, and codebase refactoring.
- **Scope & Key Files:**
  - **3D Asset Library Phases A4–A5 (`docs/3d_asset_library_plan.md`):** Pure-Rust 4-step `.glb`/`.obj` Import Wizard (`Dialogs/asset_import_wizard.py`) with automatic `.esk` embedding, plus `.esk-pack` Pack Manager and initial downloadable release packs.
  - **Presentation & 2D/3D Controls:** Dark mode toggle & UI/canvas themes; Colors by layer; Screen line weights/types; 2D rendering styles (sketch, blueprint, presentation); 3D ceiling texture patterns; Saved named 3D camera views; Vertical/angled 3D section cuts; Optional photorealistic in-app polish / `.obj` export.
  - **Drafting, Finishes & Documentation:** Radial/diameter dimensions; Reusable text styles; Associative live dimensions; Inline modeless measurement input; Moldings (crown, chair rail, casing/baseboard profiles); Backsplash & wall tile layouts; Footer concrete & excavation volumes; Multi-view print sheets, sheet index, customizable title block templates/logos, revision tracking, custom drawing numbering, detail libraries; Global command palette (`Ctrl+K`), favorites palette, customizable UI, general parametric rules/constraints, equal-spacing smart guides, polar snap tracking.
  - **Codebase Cleanup:** Split oversized monoliths (`Dialogs/properties_dock.py`, `Canvas/events_selection.py`, `Canvas/canvas_draw.py`) and unify legacy roof solver wrappers (`Canvas/roof_solver.py` vs `geometry/roof_solver.py`).
- **Exit Criteria:** Users can import arbitrary `.glb`/`.obj` models without Blender and install `.esk-pack` libraries; all tests pass cleanly after UI/canvas modularization.

### Stage 6 — `v2.0` Paid Major Upgrade *(30–40% Loyalty Discount for v1.x Owners)*
- **Goal:** Foundational architectural & performance leap justifying a paid major version upgrade.
- **Scope:**
  - Benchmark critical paths and selectively migrate hot 2D geometry, snapping, and file I/O paths to Rust.
  - Multi-layer structural framing assemblies.
  - Structural load-driven header & beam autocalculation.
  - Expanded IRC/IBC building code compliance checking.
  - Interior artificial 3D lighting (fixtures, switches, emissive/point lights) & advanced roof join tools.
  - Optional native macOS packaging & notarization (contingent on Windows Pro revenue).

---

## 6. Deferred / Out-of-Scope Backlog (Guardrail Enforcement)

The following items are intentionally parked outside `v1.x`–`v2.0` residential wood-frame scope:
- **Heavy Engineering & MEP Design:** FEA structural stress/strain analysis, steel/concrete engineering property tables, full structural load calculations, Manual J HVAC energy loads & duct design, plumbing pipe routing, electrical circuit load calculations.
- **Site / Civil / Landscape:** Property boundary site plans, terrain contour/slope modeling, grading, landscaping, parking/driveways, fencing, pools/water features.
- **Heavy / Proprietary Formats & External:** AutoCAD binary DWG import/export, BIM IFC import/export, SketchUp `.skp` import, generic CSV data import, external community forum, and non-marketing video tutorials.
