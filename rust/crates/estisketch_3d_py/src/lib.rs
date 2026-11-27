use estisketch_3d_core::{SceneDeltaIR, SceneIR, SceneState, SCENE_IR_SCHEMA_VERSION};
use estisketch_3d_gl::GlRenderer;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

fn to_py_value_error(err: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(err.to_string())
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

#[pyclass]
pub struct NativeSceneSession {
    state: SceneState,
    renderer: GlRenderer,
}

#[pymethods]
impl NativeSceneSession {
    #[new]
    fn new() -> Self {
        Self {
            state: SceneState::new(),
            renderer: GlRenderer::default(),
        }
    }

    fn load_scene(&mut self, scene_json: &str) -> PyResult<String> {
        let scene: SceneIR = serde_json::from_str(scene_json).map_err(to_py_value_error)?;
        let summary = self.state.load_scene(scene).map_err(to_py_value_error)?;
        self.renderer.sync_summary(&summary);
        serde_json::to_string(&summary).map_err(to_py_value_error)
    }

    fn upsert_entities(&mut self, delta_json: &str) -> PyResult<String> {
        let delta: SceneDeltaIR = serde_json::from_str(delta_json).map_err(to_py_value_error)?;
        let summary = self.state.apply_delta(delta).map_err(to_py_value_error)?;
        self.renderer.sync_summary(&summary);
        serde_json::to_string(&summary).map_err(to_py_value_error)
    }

    fn remove_entities(&mut self, ids: Vec<String>) -> PyResult<String> {
        let summary = self.state.remove_ids(&ids);
        self.renderer.sync_summary(&summary);
        serde_json::to_string(&summary).map_err(to_py_value_error)
    }

    fn summary_json(&self) -> PyResult<String> {
        serde_json::to_string(&self.state.summary()).map_err(to_py_value_error)
    }

    fn entity_count(&self) -> usize {
        self.state.entity_count()
    }
}

#[pymodule]
fn _native_3d(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("NATIVE_3D_VERSION", env!("CARGO_PKG_VERSION"))?;
    m.add("SCHEMA_VERSION", SCENE_IR_SCHEMA_VERSION)?;
    m.add_function(wrap_pyfunction!(echo_scene_ir, m)?)?;
    m.add_function(wrap_pyfunction!(summarize_scene_ir, m)?)?;
    m.add_class::<NativeSceneSession>()?;
    Ok(())
}
