use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::scene_ir::{
    CustomAssetIR, FixtureIR, FooterIR, LevelIR, OpeningIR, Point2D, RimBandIR, RoofIR, RoomIR,
    SceneDeltaIR, SceneIR, StairIR, SunIR, WallIR, SCENE_IR_SCHEMA_VERSION,
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SceneSummary {
    pub schema_version: u32,
    pub level_count: usize,
    pub wall_count: usize,
    pub wall_segment_count: usize,
    pub opening_count: usize,
    pub room_count: usize,
    pub roof_count: usize,
    pub footer_count: usize,
    pub rim_band_count: usize,
    pub stair_count: usize,
    pub fixture_count: usize,
    pub custom_asset_count: usize,
    pub total_entities: usize,
}

#[derive(Debug, Clone)]
pub struct SceneState {
    pub schema_version: u32,
    pub plan_center_in: Point2D,
    pub sun: SunIR,
    pub levels: BTreeMap<String, LevelIR>,
    pub walls: BTreeMap<String, WallIR>,
    pub openings: BTreeMap<String, OpeningIR>,
    pub rooms: BTreeMap<String, RoomIR>,
    pub roofs: BTreeMap<String, RoofIR>,
    pub footers: BTreeMap<String, FooterIR>,
    pub rim_bands: BTreeMap<String, RimBandIR>,
    pub stairs: BTreeMap<String, StairIR>,
    pub fixtures: BTreeMap<String, FixtureIR>,
    pub custom_assets: BTreeMap<String, CustomAssetIR>,
}

impl Default for SceneState {
    fn default() -> Self {
        Self {
            schema_version: SCENE_IR_SCHEMA_VERSION,
            plan_center_in: [0.0, 0.0],
            sun: SunIR::default(),
            levels: BTreeMap::new(),
            walls: BTreeMap::new(),
            openings: BTreeMap::new(),
            rooms: BTreeMap::new(),
            roofs: BTreeMap::new(),
            footers: BTreeMap::new(),
            rim_bands: BTreeMap::new(),
            stairs: BTreeMap::new(),
            fixtures: BTreeMap::new(),
            custom_assets: BTreeMap::new(),
        }
    }
}

fn validate_schema_version(version: u32) -> Result<(), String> {
    if version != SCENE_IR_SCHEMA_VERSION {
        return Err(format!(
            "Unsupported SceneIR schema_version {version} (expected {SCENE_IR_SCHEMA_VERSION})"
        ));
    }
    Ok(())
}

impl SceneState {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn load_scene(&mut self, scene: SceneIR) -> Result<SceneSummary, String> {
        validate_schema_version(scene.schema_version)?;
        self.clear();
        self.schema_version = scene.schema_version;
        self.plan_center_in = scene.plan_center_in;
        self.sun = scene.sun;
        for item in scene.levels {
            self.levels.insert(item.id.clone(), item);
        }
        for item in scene.walls {
            self.walls.insert(item.id.clone(), item);
        }
        for item in scene.openings {
            self.openings.insert(item.id.clone(), item);
        }
        for item in scene.rooms {
            self.rooms.insert(item.id.clone(), item);
        }
        for item in scene.roofs {
            self.roofs.insert(item.id.clone(), item);
        }
        for item in scene.footers {
            self.footers.insert(item.id.clone(), item);
        }
        for item in scene.rim_bands {
            self.rim_bands.insert(item.id.clone(), item);
        }
        for item in scene.stairs {
            self.stairs.insert(item.id.clone(), item);
        }
        for item in scene.fixtures {
            self.fixtures.insert(item.id.clone(), item);
        }
        for item in scene.custom_assets {
            self.custom_assets.insert(item.id.clone(), item);
        }
        Ok(self.summary())
    }

    pub fn apply_delta(&mut self, delta: SceneDeltaIR) -> Result<SceneSummary, String> {
        validate_schema_version(delta.schema_version)?;
        self.schema_version = delta.schema_version;
        self.plan_center_in = delta.plan_center_in;
        self.sun = delta.sun;

        self.remove_ids_internal(&delta.removed_ids);

        for item in delta.levels {
            self.levels.insert(item.id.clone(), item);
        }
        for item in delta.walls {
            self.walls.insert(item.id.clone(), item);
        }
        for item in delta.openings {
            self.openings.insert(item.id.clone(), item);
        }
        for item in delta.rooms {
            self.rooms.insert(item.id.clone(), item);
        }
        for item in delta.roofs {
            self.roofs.insert(item.id.clone(), item);
        }
        for item in delta.footers {
            self.footers.insert(item.id.clone(), item);
        }
        for item in delta.rim_bands {
            self.rim_bands.insert(item.id.clone(), item);
        }
        for item in delta.stairs {
            self.stairs.insert(item.id.clone(), item);
        }
        for item in delta.fixtures {
            self.fixtures.insert(item.id.clone(), item);
        }
        for item in delta.custom_assets {
            self.custom_assets.insert(item.id.clone(), item);
        }
        Ok(self.summary())
    }

    pub fn remove_ids(&mut self, ids: &[String]) -> SceneSummary {
        self.remove_ids_internal(ids);
        self.summary()
    }

    fn remove_ids_internal(&mut self, ids: &[String]) {
        for id in ids {
            self.levels.remove(id);
            self.walls.remove(id);
            self.openings.remove(id);
            self.rooms.remove(id);
            self.roofs.remove(id);
            self.footers.remove(id);
            self.rim_bands.remove(id);
            self.stairs.remove(id);
            self.fixtures.remove(id);
            self.custom_assets.remove(id);
        }
    }

    fn clear(&mut self) {
        self.levels.clear();
        self.walls.clear();
        self.openings.clear();
        self.rooms.clear();
        self.roofs.clear();
        self.footers.clear();
        self.rim_bands.clear();
        self.stairs.clear();
        self.fixtures.clear();
        self.custom_assets.clear();
    }

    pub fn entity_count(&self) -> usize {
        self.walls.len()
            + self.openings.len()
            + self.rooms.len()
            + self.roofs.len()
            + self.footers.len()
            + self.rim_bands.len()
            + self.stairs.len()
            + self.fixtures.len()
            + self.custom_assets.len()
    }

    pub fn summary(&self) -> SceneSummary {
        let wall_segment_count: usize = self.walls.values().map(|w| w.segments.len()).sum();
        SceneSummary {
            schema_version: self.schema_version,
            level_count: self.levels.len(),
            wall_count: self.walls.len(),
            wall_segment_count,
            opening_count: self.openings.len(),
            room_count: self.rooms.len(),
            roof_count: self.roofs.len(),
            footer_count: self.footers.len(),
            rim_band_count: self.rim_bands.len(),
            stair_count: self.stairs.len(),
            fixture_count: self.fixtures.len(),
            custom_asset_count: self.custom_assets.len(),
            total_entities: self.entity_count(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scene_ir::WallSegmentIR;

    fn sample_scene() -> SceneIR {
        SceneIR {
            schema_version: SCENE_IR_SCHEMA_VERSION,
            plan_center_in: [120.0, 60.0],
            sun: SunIR::default(),
            levels: vec![LevelIR {
                id: "lvl_0".into(),
                name: "Level 1".into(),
                elevation_m: 0.0,
                height_m: 2.4384,
                floor_thickness_m: 0.254,
            }],
            walls: vec![WallIR {
                id: "wall_1".into(),
                level_id: "lvl_0".into(),
                layer_id: "layer_0".into(),
                visible: true,
                locked: false,
                segments: vec![WallSegmentIR {
                    seg_index: 0,
                    start_m: [-2.0, 0.0],
                    end_m: [2.0, 0.0],
                    thickness_m: 0.15,
                    height_start_m: 2.4384,
                    height_end_m: 2.4384,
                    left_angle_rad: 0.0,
                    right_angle_rad: 0.0,
                    exterior: true,
                    left_finish: "Drywall".into(),
                    right_finish: "Siding".into(),
                    left_color: None,
                    right_color: None,
                    left_baseboard: false,
                    right_baseboard: false,
                    opening_cuts: Vec::new(),
                }],
                custom_3d_override: None,
            }],
            openings: Vec::new(),
            rooms: Vec::new(),
            roofs: Vec::new(),
            footers: Vec::new(),
            rim_bands: Vec::new(),
            stairs: Vec::new(),
            fixtures: Vec::new(),
            custom_assets: Vec::new(),
        }
    }

    #[test]
    fn round_trip_scene_ir_json() {
        let scene = sample_scene();
        let raw = serde_json::to_string(&scene).expect("serialize");
        let parsed: SceneIR = serde_json::from_str(&raw).expect("deserialize");
        assert_eq!(parsed, scene);
    }

    #[test]
    fn apply_delta_upsert_and_remove() {
        let mut state = SceneState::new();
        let sum = state.load_scene(sample_scene()).expect("load");
        assert_eq!(sum.wall_count, 1);
        assert_eq!(sum.total_entities, 1);

        let delta = SceneDeltaIR {
            schema_version: SCENE_IR_SCHEMA_VERSION,
            plan_center_in: [120.0, 60.0],
            sun: SunIR::default(),
            levels: Vec::new(),
            walls: Vec::new(),
            openings: Vec::new(),
            rooms: vec![RoomIR {
                id: "room_1".into(),
                level_id: "lvl_0".into(),
                name: "Living".into(),
                outer_m: vec![[-2.0, -2.0], [2.0, -2.0], [2.0, 2.0], [-2.0, 2.0]],
                floor_holes_m: Vec::new(),
                ceiling_holes_m: Vec::new(),
                z_top_m: 0.0,
                thickness_m: 0.254,
                ceiling_z_m: 2.4384,
                floor_pattern: "none".into(),
                pattern_rotation_deg: 0.0,
                pattern_scale: 1.0,
            }],
            roofs: Vec::new(),
            footers: Vec::new(),
            rim_bands: Vec::new(),
            stairs: Vec::new(),
            fixtures: Vec::new(),
            custom_assets: Vec::new(),
            removed_ids: vec!["wall_1".into()],
        };
        let sum2 = state.apply_delta(delta).expect("delta");
        assert_eq!(sum2.wall_count, 0);
        assert_eq!(sum2.room_count, 1);
        assert_eq!(sum2.total_entities, 1);
    }

    #[test]
    fn rejects_unsupported_schema_version() {
        let mut scene = sample_scene();
        scene.schema_version = 99;
        let mut state = SceneState::new();
        let err = state.load_scene(scene).expect_err("must fail");
        assert!(err.contains("99"));
    }
}
