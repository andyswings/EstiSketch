use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const SCENE_IR_SCHEMA_VERSION: u32 = 1;

pub type Point2D = [f64; 2];
pub type Point3D = [f64; 3];
pub type RgbColor = [f64; 3];

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct SunIR {
    #[serde(default)]
    pub north_angle_deg: f64,
    #[serde(default = "default_azimuth")]
    pub azimuth_deg: f64,
    #[serde(default = "default_elevation")]
    pub elevation_deg: f64,
}

fn default_azimuth() -> f64 {
    145.0
}

fn default_elevation() -> f64 {
    48.0
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LevelIR {
    pub id: String,
    pub name: String,
    pub elevation_m: f64,
    pub height_m: f64,
    pub floor_thickness_m: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct OpeningCutIR {
    pub opening_id: String,
    pub x0_m: f64,
    pub x1_m: f64,
    pub z0_m: f64,
    pub z1_m: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WallSegmentIR {
    pub seg_index: usize,
    pub start_m: Point2D,
    pub end_m: Point2D,
    pub thickness_m: f64,
    pub height_start_m: f64,
    pub height_end_m: f64,
    pub left_angle_rad: f64,
    pub right_angle_rad: f64,
    pub exterior: bool,
    pub left_finish: String,
    pub right_finish: String,
    #[serde(default)]
    pub left_color: Option<RgbColor>,
    #[serde(default)]
    pub right_color: Option<RgbColor>,
    #[serde(default)]
    pub left_baseboard: bool,
    #[serde(default)]
    pub right_baseboard: bool,
    #[serde(default)]
    pub opening_cuts: Vec<OpeningCutIR>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WallIR {
    pub id: String,
    pub level_id: String,
    #[serde(default)]
    pub layer_id: String,
    #[serde(default = "default_true")]
    pub visible: bool,
    #[serde(default)]
    pub locked: bool,
    #[serde(default)]
    pub segments: Vec<WallSegmentIR>,
    #[serde(default)]
    pub custom_3d_override: Option<Value>,
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct OpeningIR {
    pub id: String,
    pub kind: String,
    pub host_wall_id: String,
    pub host_seg_index: usize,
    pub x_local_m: f64,
    pub z_local_m: f64,
    pub width_m: f64,
    pub depth_m: f64,
    pub height_m: f64,
    pub style: String,
    #[serde(default)]
    pub swing: String,
    #[serde(default)]
    pub orientation: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RoomIR {
    pub id: String,
    pub level_id: String,
    pub name: String,
    pub outer_m: Vec<Point2D>,
    #[serde(default)]
    pub floor_holes_m: Vec<Vec<Point2D>>,
    #[serde(default)]
    pub ceiling_holes_m: Vec<Vec<Point2D>>,
    pub z_top_m: f64,
    pub thickness_m: f64,
    pub ceiling_z_m: f64,
    #[serde(default)]
    pub floor_pattern: String,
    #[serde(default)]
    pub pattern_rotation_deg: f64,
    #[serde(default = "default_one")]
    pub pattern_scale: f64,
}

fn default_one() -> f64 {
    1.0
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RoofFacetIR {
    pub vertices_m: Vec<Point3D>,
    pub pitch_rise: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GableInfillIR {
    pub p_start_m: Point2D,
    pub p_end_m: Point2D,
    pub p_peak_m: Point2D,
    pub z_base_m: f64,
    pub z_peak_m: f64,
    pub thickness_m: f64,
    pub finish: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RoofIR {
    pub id: String,
    pub level_id: String,
    pub material: String,
    pub thickness_m: f64,
    #[serde(default)]
    pub facets: Vec<RoofFacetIR>,
    #[serde(default)]
    pub gable_infills: Vec<GableInfillIR>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FooterIR {
    pub id: String,
    pub level_id: String,
    pub footprint_m: Vec<Point2D>,
    pub z_top_m: f64,
    pub depth_m: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RimBandIR {
    pub id: String,
    pub level_id: String,
    pub footprint_m: Vec<Point2D>,
    pub z_bottom_m: f64,
    pub height_m: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StairIR {
    pub id: String,
    pub level_id: String,
    pub stair_type: String,
    pub loc_m: Point3D,
    pub rot_z_rad: f64,
    pub width_m: f64,
    pub total_rise_m: f64,
    pub num_steps: i32,
    pub tread_depth_m: f64,
    pub total_run_m: f64,
    pub turn_direction: String,
    pub landing_depth_m: f64,
    pub steps_before_landing: i32,
    pub winder_count: i32,
    pub inner_radius_m: f64,
    pub rotation_degrees: f64,
    pub has_left_rail: bool,
    pub has_right_rail: bool,
    pub rail_height_m: f64,
    #[serde(default)]
    pub railing_paths_m: Vec<Vec<Point3D>>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FixtureIR {
    pub id: String,
    pub level_id: String,
    pub symbol_type: String,
    #[serde(default)]
    pub category: String,
    pub loc_m: Point3D,
    pub rot_z_rad: f64,
    pub width_m: f64,
    pub depth_m: f64,
    pub height_m: f64,
    pub has_countertop: bool,
    pub countertop_overhang_m: f64,
    pub countertop_thickness_m: f64,
    pub countertop_material: String,
    pub has_backsplash: bool,
    #[serde(default)]
    pub fill_color: Option<RgbColor>,
    #[serde(default)]
    pub countertop_color: Option<RgbColor>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CustomAssetIR {
    pub id: String,
    pub path: String,
    pub loc_m: Point3D,
    pub rot_z_rad: f64,
    pub scale: Point3D,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SceneIR {
    pub schema_version: u32,
    #[serde(default)]
    pub plan_center_in: Point2D,
    #[serde(default)]
    pub sun: SunIR,
    #[serde(default)]
    pub levels: Vec<LevelIR>,
    #[serde(default)]
    pub walls: Vec<WallIR>,
    #[serde(default)]
    pub openings: Vec<OpeningIR>,
    #[serde(default)]
    pub rooms: Vec<RoomIR>,
    #[serde(default)]
    pub roofs: Vec<RoofIR>,
    #[serde(default)]
    pub footers: Vec<FooterIR>,
    #[serde(default)]
    pub rim_bands: Vec<RimBandIR>,
    #[serde(default)]
    pub stairs: Vec<StairIR>,
    #[serde(default)]
    pub fixtures: Vec<FixtureIR>,
    #[serde(default)]
    pub custom_assets: Vec<CustomAssetIR>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SceneDeltaIR {
    pub schema_version: u32,
    #[serde(default)]
    pub plan_center_in: Point2D,
    #[serde(default)]
    pub sun: SunIR,
    #[serde(default)]
    pub levels: Vec<LevelIR>,
    #[serde(default)]
    pub walls: Vec<WallIR>,
    #[serde(default)]
    pub openings: Vec<OpeningIR>,
    #[serde(default)]
    pub rooms: Vec<RoomIR>,
    #[serde(default)]
    pub roofs: Vec<RoofIR>,
    #[serde(default)]
    pub footers: Vec<FooterIR>,
    #[serde(default)]
    pub rim_bands: Vec<RimBandIR>,
    #[serde(default)]
    pub stairs: Vec<StairIR>,
    #[serde(default)]
    pub fixtures: Vec<FixtureIR>,
    #[serde(default)]
    pub custom_assets: Vec<CustomAssetIR>,
    #[serde(default)]
    pub removed_ids: Vec<String>,
}
