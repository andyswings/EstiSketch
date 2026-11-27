use std::path::Path;

use estisketch_3d_core::{
    build_scene_mesh_with_assets, write_glb_file, AssetLibrary, BuiltSceneMesh, SceneDeltaIR,
    SceneIR, SceneState, SCENE_IR_SCHEMA_VERSION,
};
use estisketch_3d_gl::{CameraMode, CameraPreset, GlRenderer, RenderStyle};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;

fn to_py_value_error(err: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(err.to_string())
}

fn to_py_runtime_error(err: impl std::fmt::Display) -> PyErr {
    PyRuntimeError::new_err(err.to_string())
}

#[pyfunction]
fn echo_scene_ir(scene_json: &str) -> PyResult<String> {
    let scene: SceneIR = serde_json::from_str(scene_json).map_err(to_py_value_error)?;
    if scene.schema_version != SCENE_IR_SCHEMA_VERSION {
        return Err(PyValueError::new_err(format!(
            "Unsupported SceneIR schema_version {} (expected {})",
            scene.schema_version, SCENE_IR_SCHEMA_VERSION
        )));
    }
    serde_json::to_string(&scene).map_err(to_py_value_error)
}

#[pyfunction]
fn summarize_scene_ir(scene_json: &str) -> PyResult<String> {
    let scene: SceneIR = serde_json::from_str(scene_json).map_err(to_py_value_error)?;
    let mut state = SceneState::new();
    let summary = state.load_scene(scene).map_err(to_py_value_error)?;
    serde_json::to_string(&summary).map_err(to_py_value_error)
}

#[pyfunction]
fn scene_mesh_stats(scene_json: &str) -> PyResult<String> {
    let scene: SceneIR = serde_json::from_str(scene_json).map_err(to_py_value_error)?;
    let mut state = SceneState::new();
    state.load_scene(scene).map_err(to_py_value_error)?;
    let built = build_scene_mesh_with_assets(&state, None);
    serde_json::to_string(&built.stats()).map_err(to_py_runtime_error)
}

#[pyfunction]
fn export_scene_glb(scene_json: &str, output_path: &str) -> PyResult<usize> {
    let scene: SceneIR = serde_json::from_str(scene_json).map_err(to_py_value_error)?;
    let mut state = SceneState::new();
    state.load_scene(scene).map_err(to_py_value_error)?;
    let built = build_scene_mesh_with_assets(&state, None);
    write_glb_file(Path::new(output_path), &built, &state.sun).map_err(to_py_runtime_error)
}

#[pyclass]
pub struct NativeSceneSession {
    state: SceneState,
    renderer: GlRenderer,
    assets: Option<AssetLibrary>,
    cached_mesh: Option<BuiltSceneMesh>,
    has_loaded_once: bool,
}

impl NativeSceneSession {
    fn rebuild_mesh(&mut self) -> BuiltSceneMesh {
        build_scene_mesh_with_assets(&self.state, self.assets.as_mut())
    }

    fn ensure_mesh(&mut self, auto_fit: bool) -> &BuiltSceneMesh {
        if self.cached_mesh.is_none() {
            let built = self.rebuild_mesh();
            self.renderer
                .set_scene_mesh(built.clone(), self.state.sun.clone(), auto_fit);
            self.cached_mesh = Some(built);
        }
        self.cached_mesh
            .get_or_insert_with(|| build_scene_mesh_with_assets(&self.state, None))
    }

    fn mark_mesh_dirty(&mut self, fit_camera: bool) {
        let built = self.rebuild_mesh();
        self.renderer
            .set_scene_mesh(built.clone(), self.state.sun.clone(), fit_camera);
        self.cached_mesh = Some(built);
    }
}

#[pymethods]
impl NativeSceneSession {
    #[new]
    fn new() -> Self {
        Self {
            state: SceneState::new(),
            renderer: GlRenderer::default(),
            assets: None,
            cached_mesh: None,
            has_loaded_once: false,
        }
    }

    fn set_asset_root(&mut self, asset_root: &str) -> PyResult<usize> {
        let lib =
            AssetLibrary::load_from_dir(Path::new(asset_root)).map_err(to_py_runtime_error)?;
        let count = lib.manifest_len();
        self.assets = Some(lib);
        if self.has_loaded_once {
            self.mark_mesh_dirty(false);
        }
        Ok(count)
    }

    fn load_scene(&mut self, scene_json: &str) -> PyResult<String> {
        let scene: SceneIR = serde_json::from_str(scene_json).map_err(to_py_value_error)?;
        let summary = self.state.load_scene(scene).map_err(to_py_value_error)?;
        self.renderer.sync_summary(&summary);
        let auto_fit = !self.has_loaded_once;
        self.has_loaded_once = true;
        self.mark_mesh_dirty(auto_fit);
        serde_json::to_string(&summary).map_err(to_py_value_error)
    }

    fn upsert_entities(&mut self, delta_json: &str) -> PyResult<String> {
        let delta: SceneDeltaIR = serde_json::from_str(delta_json).map_err(to_py_value_error)?;
        let summary = self.state.apply_delta(delta).map_err(to_py_value_error)?;
        self.renderer.sync_summary(&summary);
        self.mark_mesh_dirty(false);
        serde_json::to_string(&summary).map_err(to_py_value_error)
    }

    fn remove_entities(&mut self, ids: Vec<String>) -> PyResult<String> {
        let summary = self.state.remove_ids(&ids);
        self.renderer.sync_summary(&summary);
        self.mark_mesh_dirty(false);
        serde_json::to_string(&summary).map_err(to_py_value_error)
    }

    fn summary_json(&self) -> PyResult<String> {
        serde_json::to_string(&self.state.summary()).map_err(to_py_value_error)
    }

    fn entity_count(&self) -> usize {
        self.state.entity_count()
    }

    fn mesh_stats_json(&mut self) -> PyResult<String> {
        let stats = self.ensure_mesh(false).stats();
        serde_json::to_string(&stats).map_err(to_py_runtime_error)
    }

    fn export_glb(&mut self, output_path: &str) -> PyResult<usize> {
        let sun = self.state.sun.clone();
        let built = self.ensure_mesh(false).clone();
        write_glb_file(Path::new(output_path), &built, &sun).map_err(to_py_runtime_error)
    }

    fn init_gl(&mut self) -> PyResult<()> {
        self.ensure_mesh(!self.has_loaded_once);
        self.renderer.init_gl().map_err(to_py_runtime_error)
    }

    fn destroy_gl(&mut self) {
        self.renderer.destroy_gl();
    }

    fn resize_gl(&mut self, width: u32, height: u32) {
        self.renderer.resize(width, height);
    }

    fn render_gl(&mut self) -> PyResult<()> {
        self.renderer.render_gl().map_err(to_py_runtime_error)
    }

    fn set_camera_mode(&mut self, mode: &str) -> PyResult<()> {
        let parsed = match mode.trim().to_lowercase().as_str() {
            "orbit" => CameraMode::Orbit,
            "walk" | "walkthrough" => CameraMode::Walkthrough,
            other => {
                return Err(PyValueError::new_err(format!(
                    "Unknown camera mode '{other}'"
                )))
            }
        };
        self.renderer.camera.set_mode(parsed);
        Ok(())
    }

    fn orbit_drag(&mut self, dx: f32, dy: f32) {
        self.renderer.camera.orbit_drag(dx, dy);
    }

    fn pan_drag(&mut self, dx: f32, dy: f32) {
        self.renderer.camera.pan_drag(dx, dy);
    }

    fn zoom_scroll(&mut self, delta: f32) {
        self.renderer.camera.zoom_scroll(delta);
    }

    fn walk_move(&mut self, forward: f32, right: f32, up: f32) {
        self.renderer.camera.walk_move(forward, right, up);
    }

    fn set_camera_preset(&mut self, preset: &str) -> PyResult<()> {
        let parsed = CameraPreset::parse(preset).map_err(to_py_value_error)?;
        self.renderer.set_camera_preset(parsed);
        Ok(())
    }

    fn fit_scene(&mut self) {
        self.renderer.fit_scene();
    }

    fn jump_to_room(&mut self, x_m: f32, y_m: f32, floor_z_m: f32) {
        self.renderer.camera.jump_to_point(x_m, y_m, floor_z_m);
    }

    fn set_render_style(&mut self, style: &str) -> PyResult<()> {
        let parsed = RenderStyle::parse(style).map_err(to_py_value_error)?;
        self.renderer.render_style = parsed;
        Ok(())
    }

    fn set_time_of_day(&mut self, hour: f32) {
        self.renderer.time_of_day_hour = hour.clamp(6.0, 20.0);
    }

    fn set_dollhouse_level(&mut self, level_id: Option<String>) {
        self.renderer.dollhouse_level_id = level_id.filter(|s| !s.is_empty());
    }

    fn set_auto_hide_roofs(&mut self, enabled: bool) {
        self.renderer.auto_hide_roofs = enabled;
    }
}

#[pymodule]
fn _native_3d(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("NATIVE_3D_VERSION", env!("CARGO_PKG_VERSION"))?;
    m.add("SCHEMA_VERSION", SCENE_IR_SCHEMA_VERSION)?;
    m.add_function(wrap_pyfunction!(echo_scene_ir, m)?)?;
    m.add_function(wrap_pyfunction!(summarize_scene_ir, m)?)?;
    m.add_function(wrap_pyfunction!(scene_mesh_stats, m)?)?;
    m.add_function(wrap_pyfunction!(export_scene_glb, m)?)?;
    m.add_class::<NativeSceneSession>()?;
    Ok(())
}
