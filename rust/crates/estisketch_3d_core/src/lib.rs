//! Pure-Rust architectural 3D data structures, procedural meshers, and glTF 2.0 export.
//!
//! All world coordinates use **meters** in a right-handed **Z-up** coordinate
//! system matching `SceneIR` schema version 1.

pub mod assets;
pub mod cabinets;
pub mod engine;
pub mod fixtures;
pub mod glb_export;
pub mod materials;
pub mod mesh;
pub mod mesher;
pub mod openings;
pub mod picking;
pub mod scene_ir;
pub mod sinks;

pub use assets::{
    compute_asset_mesh_hash, compute_asset_silhouette_2d, convert_3d_asset_to_glb,
    inspect_3d_asset_file, inspect_loaded_asset, load_3d_asset, load_glb_asset, load_gltf_file,
    load_obj_bytes, parse_glb_bytes, AssetInspection, AssetLibrary, LoadedGlbAsset,
};
pub use engine::{SceneState, SceneSummary};
pub use glb_export::{export_loaded_asset_to_glb, export_scene_mesh_to_glb, write_glb_file};
pub use mesh::{
    BuiltSceneMesh, LevelBounds, MaterialDef, MaterialKey, MaterialStyle, MeshBuilder, MeshPart,
    MeshStats, PartFlags, Vertex,
};
pub use mesher::{build_scene_mesh, build_scene_mesh_with_assets};
pub use picking::{is_part_visible, PickFilter, PickHit, ScenePicker};
pub use scene_ir::{
    CustomAssetIR, FixtureIR, FooterIR, GableInfillIR, LevelIR, OpeningCutIR, OpeningIR, RimBandIR,
    RoofFacetIR, RoofIR, RoomIR, SceneDeltaIR, SceneIR, StairIR, SunIR, WallIR, WallSegmentIR,
    SCENE_IR_SCHEMA_VERSION,
};
