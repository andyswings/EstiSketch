# EstiSketch Coding Guidelines

Mandatory standards for all LLM-generated and edited code in the EstiSketch repository (`Python >= 3.10`, GTK4 / PyGObject, PyCairo, NumPy, optional ReportLab, the Blender `bpy` bridge, and the `rust/` 3D engine workspace built with PyO3 `abi3-py310`, `glow`, and Serde). Apply these rules to all new files and modified code without performing unrelated refactors on untouched legacy code.

---

## 1. PEP 8 & Code Style

- **Naming conventions**:
  - `snake_case` for functions, methods, local/instance variables, and new module filenames.
  - `PascalCase` for classes and type aliases (e.g., `Point`, `WallSegment`).
  - `UPPER_SNAKE_CASE` for module-level constants and configuration keys.
  - Leading underscore (`_helper`) for internal/private functions, methods, and attributes.
- **Formatting**:
  - 4 spaces per indentation level (never tabs), UTF-8 encoding, LF (`\n`) line endings, and a single trailing newline.
  - Target **100 characters** max line length for all new and edited lines. (`.flake8` allows up to `200` for legacy compatibility; do not reformat untouched legacy lines solely for wrapping.)
- **Imports**:
  - Group imports in strict PEP 8 order separated by a single blank line:
    1. `from __future__ import annotations` (recommended in all new modules)
    2. Standard library imports
    3. Third-party imports (`gi`, `cairo`, `numpy`, `reportlab`, `pytest`)
    4. Local package/relative imports (`from .geometry...`, `from EstiSketch...`)
  - Remove unused imports and avoid wildcard imports (`from x import *`).
  - For GTK4 modules, always call `gi.require_version("Gtk", "4.0")` immediately after `import gi` and before `from gi.repository import ...`.
- **Error handling**:
  - Never use bare `except:` or silently swallow exceptions.
  - Catch specific exception types (`ValueError`, `KeyError`, `OSError`, `ET.ParseError`) and surface failures clearly by raising, reporting in the UI/result object, or emitting `warnings.warn(..., UserWarning)`.
  - Never invent hardcoded fallback geometry or silent numeric defaults when required project geometry or input data is missing.

---

## 2. Type Hinting

- **Complete annotations**: Add type hints to all new and modified functions, methods, and dataclass fields, including explicit return types (`-> None` for procedures).
- **Syntax**:
  - Include `from __future__ import annotations` in new modules and use modern Python 3.10+ syntax (`X | None`, `list[...]`, `dict[...]`, `tuple[...]`).
  - When making small, localized edits to legacy files that use `typing` (`Optional`, `List`, `Dict`, `Tuple`), match the surrounding file's style or modernize cleanly if updating the function.
- **Dataclasses & defaults**:
  - Prefer `@dataclass` with typed fields and `field(default_factory=...)` for collections.
  - Never use mutable default arguments (`[]`, `{}`) in function signatures or class attributes.
- **Strictness**: Avoid `Any` unless there is no other single correct type hint; prefer concrete types, `Protocol`, `TypedDict`, `Union`, or `object` with runtime narrowing (including at GTK/PyGObject, Cairo, or Blender `bpy` boundaries whenever a narrower type is practical). Define clear type aliases (e.g., `Point = tuple[float, float]`) or `Protocol`s for structured data.

---

## 3. Docstrings & Comments

- **Docstrings**: Every new module, class, and public function/method must include a concise PEP 257 / Google-style docstring describing:
  - Purpose and behavior.
  - Physical units (`inches`, `feet`, `radians`, `degrees`, `meters`) for dimensional arguments and return values.
  - Arguments, return values, and key invariants or preconditions.
- **Comments**: Explain *why*—geometry sign conventions, CCW vs. CW arc direction, coordinate frame transforms, or non-obvious edge cases—never narrate *what* obvious statements do. Preserve existing unrelated comments and docstrings.

---

## 4. Architecture, Modularity & Anti-Duplication

- **Headless core separation**:
  - Keep pure geometry (`src/EstiSketch/geometry/`), data models (`components.py`, `models/`, `roof_components.py`), takeoff math (`TakeoffEngine/`), and Layer 1 XML/geometry parsing in `blender_bridge/` (`estisketch_to_hb5.py`) completely free of `gi`, `Gtk`, `cairo`, and `bpy` imports so they can be unit-tested headlessly under standard `pytest`.
- **Reuse over duplication**:
  - Before writing new geometry, snapping, label-orientation, ID-generation, or serialization code, check existing shared helpers and reuse or extend them rather than duplicating logic across 2D canvas, printing, takeoff, and Blender export:
    - `generate_identifier` in `src/EstiSketch/Canvas/utils.py`
    - Curved/straight wall math in `src/EstiSketch/geometry/arc_wall.py`
    - Room hole clipping & triangulation in `src/EstiSketch/geometry/room_holes.py`
    - Upright label angles in `src/EstiSketch/Canvas/label_utils.py`
    - Unit conversion & formatting in `src/EstiSketch/measurement_utils.py`
- **Small, cohesive units**: Keep functions focused on a single responsibility with shallow nesting and early returns. Prefer extracting focused helpers or dedicated modules over appending large blocks to already-large files (`Canvas/canvas_area.py`, `project_io.py`, `blender_bridge/estisketch_to_hb5.py`).
- **Internal units**: All 2D/3D model coordinates and dimensions in EstiSketch are in **inches** (`float`) unless explicitly documented otherwise (e.g., `blender_bridge` converts inches to meters via `INCH_TO_M = 0.0254`).

---

## 5. EstiSketch-Specific Invariants

- **Object identifiers & metadata**:
  - Every project/canvas object must expose a unique string `.identifier` generated via `generate_identifier("<type>")` and preserve standard metadata (`layer_id`, `visible`, `locked`, `custom_name`, `comment`).
- **Canvas state safety**:
  - User-facing canvas mutations must respect locked layers and locked objects, push an undo snapshot, emit `content-changed` (marking the project dirty), and keep `LayersPanel` and `PropertiesDock` synchronized.
- **XML persistence (`src/EstiSketch/project_io.py`)**:
  - Any new persistent model or canvas attribute must be serialized and deserialized with backwards-compatible defaults when loading older `.xml` project files.
- **User configuration (`src/EstiSketch/config.py`)**:
  - Never write settings into the installed package directory (`src/EstiSketch/settings.json`). Always read/write via `get_config_dir()` / `CONFIG_FILE` and merge loaded values with `DEFAULT_SETTINGS`.
- **Cairo context hygiene**:
  - Always balance `cr.save()` and `cr.restore()` (use `try`/`finally` when early returns are possible).
  - Ensure scene rendering honors `printing=True` by omitting editor-only overlays (grid, selection handles, snap guides, ghost previews).
- **Cross-platform paths**:
  - Use `pathlib.Path` or `os.path` for all filesystem paths—EstiSketch targets both Linux (`.deb`, AppImage) and Windows (`conda` `.exe`).

---

## 6. Testing, Linting & Change Hygiene

- **Tests**: Add or update headless `pytest` unit tests under `tests/test_<area>.py` for every bug fix and new feature. Keep test fixtures deterministic and free of display-server requirements whenever testing core logic.
- **Verification before completion**:
  - Run targeted `pytest` suites (and full `pytest` for shared/core changes) after your final edit.
  - Run `flake8` on all created or modified Python files.
  - Whenever any file under `rust/` is created or modified, complete the full Rust build, lint, test, and native extension staging workflow in **Section 7** so everything necessary is compiled and ready to test immediately.
- **TODO / Done tracking**: Every completed fix or feature must be recorded in `TODO.md` under `## Done ✅ (latest first)` (and checked off or removed from the backlog section if it was tracked there).
- **Scoped changes**:
  - Keep diffs strictly scoped to the request. Do not leave debug `print` statements, scratch files, or commented-out dead code in the repository.
  - Never commit or track generated build/packaging artifacts (`dist/`, `build/`, `build_deb/`, `build_pyinstaller/`, `.venv/`, `__pycache__/`, `rust/target/`, `src/EstiSketch/_native_3d*.{so,pyd,dylib}`).

---

## 7. Rust Coding Guidelines (`rust/`)

- **Formatting & Naming**:
  - Follow `rustfmt` defaults (4 spaces per indentation level, LF line endings, max width 100 chars).
  - Use `snake_case` for modules, crates, functions, methods, and local variables; `PascalCase` for structs, enums, traits, and type aliases; and `UPPER_SNAKE_CASE` for constants and statics.
  - Document public structs, fields with physical meanings, traits, functions, and error conditions with `///` (or `//!` at module level), explicitly specifying physical units (`meters`, `radians`, `degrees`) and coordinate conventions (3D world space is centered **meters**, **Z-up**).
- **Crate Architecture & Separation**:
  - `estisketch_3d_core`: Pure-Rust data models (`SceneIR`, `SceneDeltaIR`), procedural meshers, BVH/spatial indexing, and scene state. Keep it strictly free of `glow`, GTK, and `pyo3` dependencies so core logic builds and runs headlessly with `cargo test`.
  - `estisketch_3d_gl`: OpenGL 3.3 Core (`glow`) rendering pipeline and GPU resource management. Keep it strictly free of `pyo3` dependencies, and ensure every allocated GL buffer, texture, VAO, framebuffer, and shader program has an explicit teardown/cleanup path.
  - `estisketch_3d_py`: Thin PyO3 (`abi3-py310`) binding layer exporting `EstiSketch._native_3d`. Keep business logic out of `estisketch_3d_py`; translate Rust errors cleanly into `PyValueError` / `PyRuntimeError` and never panic across FFI.
- **Error Handling, Safety & Schema Invariants**:
  - Prefer safe Rust everywhere. Use `unsafe` only at unavoidable FFI/GL boundaries (e.g., OpenGL loader function pointers or `glow` calls), keeping blocks minimal with a `// SAFETY: ...` comment explaining why the invariants hold.
  - Never use `.unwrap()` or `.expect()` in non-test library code; return `Result<T, E>` (or explicit contextual errors) and propagate with `?`. `.unwrap()` / `.expect()` is permitted inside `#[cfg(test)]` unit tests.
  - Keep `SceneIR` and `SceneDeltaIR` structs strictly synchronized with `src/EstiSketch/scene_ir/schema.py`, preserve `schema_version` validation, and ensure changes stay non-destructive with respect to caller state.
- **Mandatory Compile & Verification for Testing**:
  - **Every time anything in `rust/` changes, compile everything necessary for immediate user testing before finishing:** run `python3 packaging/build_native_3d.py` to compile `estisketch_3d_py` in `--release` and stage the updated `src/EstiSketch/_native_3d.abi3.so` (or `_native_3d.pyd` on Windows) into `src/EstiSketch/` so `run_dev.py` and `pytest` never run against stale native binaries.
  - Always verify formatting, lints, Rust tests, and Python FFI integration after final Rust edits:
    - `cargo fmt --manifest-path rust/Cargo.toml --check`
    - `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
    - `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 cargo test --manifest-path rust/Cargo.toml`
    - `python3 packaging/build_native_3d.py && python3 -m pytest tests/test_scene_ir.py -q` (plus any other relevant test suites).
