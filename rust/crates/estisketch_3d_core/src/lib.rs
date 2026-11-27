//! Pure-Rust architectural 3D data structures, procedural meshers, and glTF 2.0 export.
//!
//! All world coordinates use **meters** in a right-handed **Z-up** coordinate
//! system matching `SceneIR` schema version 1.

pub mod engine;
pub mod glb_export;
pub mod materials;
pub mod mesh;
pub mod mesher;
pub mod scene_ir;

pub use engine::{SceneState, SceneSummary};
pub use glb_export::{export_scene_mesh_to_glb, write_glb_file};
pub use mesh::{
    BuiltSceneMesh, LevelBounds, MaterialDef, MaterialKey, MaterialStyle, MeshBuilder, MeshPart,
    MeshStats, PartFlags, Vertex,
};
pub use mesher::build_scene_mesh;
pub use scene_ir::{
    CustomAssetIR, FixtureIR, FooterIR, GableInfillIR, LevelIR, OpeningCutIR, OpeningIR, RimBandIR,
    RoofFacetIR, RoofIR, RoomIR, SceneDeltaIR, SceneIR, StairIR, SunIR, WallIR, WallSegmentIR,
    SCENE_IR_SCHEMA_VERSION,
};
