//! Pure-Rust BVH acceleration and ray-triangle picking for compiled architectural meshes.
//!
//! Coordinates and distances are expressed in **meters** (Z-up right-handed world space).

use glam::Vec3;
use serde::{Deserialize, Serialize};

use crate::mesh::{BuiltSceneMesh, MeshPart};

const LEAF_MAX_TRIANGLES: usize = 8;
const MAX_BVH_DEPTH: usize = 20;
const RAY_EPSILON: f32 = 1e-6;
const MIN_HIT_DIST_M: f32 = 1e-4;

/// Closest raycast intersection against a compiled 3D scene mesh.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct PickHit {
    /// Source `SceneIR` entity identifier (e.g., wall ID, opening ID, fixture ID).
    pub entity_id: String,
    /// Entity category (`"wall"`, `"opening"`, `"room"`, `"roof"`, `"stair"`, `"fixture"`, etc.).
    pub entity_kind: String,
    /// Mesh sub-part identifier (`"LeftFace"`, `"RightFace"`, `"RoofDeck"`, `"Floor"`, etc.).
    pub sub_part: String,
    /// Intersection point `[x, y, z]` in **meters** (Z-up world space).
    pub world_pos_m: [f32; 3],
    /// Unit surface normal `[nx, ny, nz]` facing back toward the ray origin.
    pub normal: [f32; 3],
    /// Distance from the ray origin along normalized ray direction in **meters**.
    pub distance_m: f32,
}

/// Shared visibility filter ensuring raycast picking matches OpenGL Dollhouse & Auto-Hide Roofs.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct PickFilter {
    /// When true, roofs and room ceilings are ignored by both rendering and picking.
    pub hide_roofs: bool,
    /// Optional active Dollhouse level identifier.
    pub dollhouse_level_id: Option<String>,
    /// Ceiling Z cutoff (`elevation_m + height_m` in **meters**) for the active Dollhouse level.
    pub level_cutoff_z_m: Option<f32>,
}

/// Return true if a mesh part should be both rendered and pickable under `filter`.
pub fn is_part_visible(
    level_id: &str,
    is_roof_or_ceiling: bool,
    z_min_m: f32,
    z_max_m: f32,
    filter: &PickFilter,
) -> bool {
    if filter.hide_roofs && is_roof_or_ceiling {
        return false;
    }
    if let Some(cutoff) = filter.level_cutoff_z_m {
        if let Some(ref active_id) = filter.dollhouse_level_id {
            if level_id != *active_id && z_min_m > cutoff - 0.05 {
                return false;
            }
        }
        if z_max_m > cutoff + 0.15 && is_roof_or_ceiling {
            return false;
        }
    }
    true
}

#[derive(Copy, Clone, Debug)]
struct Aabb {
    min: Vec3,
    max: Vec3,
}

impl Aabb {
    fn empty() -> Self {
        Self {
            min: Vec3::splat(f32::INFINITY),
            max: Vec3::splat(f32::NEG_INFINITY),
        }
    }

    fn expand_point(&mut self, p: Vec3) {
        self.min = self.min.min(p);
        self.max = self.max.max(p);
    }

    fn expand_aabb(&mut self, other: &Self) {
        self.min = self.min.min(other.min);
        self.max = self.max.max(other.max);
    }
}

#[derive(Copy, Clone, Debug)]
struct Triangle {
    v0: Vec3,
    v1: Vec3,
    v2: Vec3,
    centroid: Vec3,
    bounds: Aabb,
}

impl Triangle {
    fn new(v0: Vec3, v1: Vec3, v2: Vec3) -> Self {
        let mut bounds = Aabb::empty();
        bounds.expand_point(v0);
        bounds.expand_point(v1);
        bounds.expand_point(v2);
        Self {
            v0,
            v1,
            v2,
            centroid: (v0 + v1 + v2) * (1.0 / 3.0),
            bounds,
        }
    }
}

#[derive(Clone, Debug)]
struct BvhNode {
    bounds: Aabb,
    left_or_start: usize,
    right_or_count: usize,
    is_leaf: bool,
}

struct PartBvh {
    entity_id: String,
    entity_kind: String,
    level_id: String,
    sub_part: String,
    is_roof_or_ceiling: bool,
    z_min_m: f32,
    z_max_m: f32,
    bounds: Aabb,
    triangles: Vec<Triangle>,
    tri_indices: Vec<usize>,
    nodes: Vec<BvhNode>,
}

impl PartBvh {
    fn from_part(part: &MeshPart) -> Option<Self> {
        if part.vertices.is_empty() || part.indices.len() < 3 {
            return None;
        }
        let mut triangles = Vec::with_capacity(part.indices.len() / 3);
        let mut part_bounds = Aabb::empty();

        for &[i0, i1, i2] in part.indices.as_chunks::<3>().0 {
            let (Some(a), Some(b), Some(c)) = (
                part.vertices.get(i0 as usize),
                part.vertices.get(i1 as usize),
                part.vertices.get(i2 as usize),
            ) else {
                continue;
            };
            let v0 = Vec3::from_array(a.pos);
            let v1 = Vec3::from_array(b.pos);
            let v2 = Vec3::from_array(c.pos);
            if (v1 - v0).cross(v2 - v0).length_squared() <= 1e-12 {
                continue;
            }
            let tri = Triangle::new(v0, v1, v2);
            part_bounds.expand_aabb(&tri.bounds);
            triangles.push(tri);
        }

        if triangles.is_empty() {
            return None;
        }

        let mut tri_indices: Vec<usize> = (0..triangles.len()).collect();
        let mut nodes = Vec::with_capacity((triangles.len() / 2).max(1));
        build_bvh_node(
            &triangles,
            &mut tri_indices,
            0,
            triangles.len(),
            0,
            &mut nodes,
        );

        Some(Self {
            entity_id: part.entity_id.clone(),
            entity_kind: part.entity_kind.clone(),
            level_id: part.level_id.clone(),
            sub_part: part.sub_part.clone(),
            is_roof_or_ceiling: part.is_roof_or_ceiling,
            z_min_m: part.z_min_m,
            z_max_m: part.z_max_m,
            bounds: part_bounds,
            triangles,
            tri_indices,
            nodes,
        })
    }

    fn intersect_ray(
        &self,
        origin: Vec3,
        dir: Vec3,
        inv_dir: Vec3,
        max_t: f32,
    ) -> Option<(f32, Vec3)> {
        if self.nodes.is_empty() || intersect_aabb(&self.bounds, origin, inv_dir, max_t).is_none() {
            return None;
        }

        let mut best_t = max_t;
        let mut best_normal = Vec3::Z;
        let mut hit_any = false;
        let mut stack = [0usize; 64];
        let mut sp = 1usize;
        stack[0] = 0;

        while sp > 0 {
            sp -= 1;
            let node = &self.nodes[stack[sp]];
            if intersect_aabb(&node.bounds, origin, inv_dir, best_t).is_none() {
                continue;
            }
            if node.is_leaf {
                let start = node.left_or_start;
                let end = start + node.right_or_count;
                for &tri_idx in &self.tri_indices[start..end] {
                    let tri = &self.triangles[tri_idx];
                    if let Some((t, normal)) = intersect_triangle_two_sided(origin, dir, tri) {
                        if t > MIN_HIT_DIST_M && t < best_t {
                            best_t = t;
                            best_normal = normal;
                            hit_any = true;
                        }
                    }
                }
            } else {
                let left_idx = node.left_or_start;
                let right_idx = node.right_or_count;
                let left_t = intersect_aabb(&self.nodes[left_idx].bounds, origin, inv_dir, best_t);
                let right_t =
                    intersect_aabb(&self.nodes[right_idx].bounds, origin, inv_dir, best_t);
                match (left_t, right_t) {
                    (Some(lt), Some(rt)) => {
                        if lt < rt {
                            if sp + 2 <= stack.len() {
                                stack[sp] = right_idx;
                                stack[sp + 1] = left_idx;
                                sp += 2;
                            }
                        } else if sp + 2 <= stack.len() {
                            stack[sp] = left_idx;
                            stack[sp + 1] = right_idx;
                            sp += 2;
                        }
                    }
                    (Some(_), None) => {
                        if sp < stack.len() {
                            stack[sp] = left_idx;
                            sp += 1;
                        }
                    }
                    (None, Some(_)) => {
                        if sp < stack.len() {
                            stack[sp] = right_idx;
                            sp += 1;
                        }
                    }
                    (None, None) => {}
                }
            }
        }

        if hit_any {
            Some((best_t, best_normal))
        } else {
            None
        }
    }
}

fn build_bvh_node(
    triangles: &[Triangle],
    tri_indices: &mut [usize],
    start: usize,
    end: usize,
    depth: usize,
    nodes: &mut Vec<BvhNode>,
) -> usize {
    let mut bounds = Aabb::empty();
    let mut centroid_bounds = Aabb::empty();
    for &idx in &tri_indices[start..end] {
        bounds.expand_aabb(&triangles[idx].bounds);
        centroid_bounds.expand_point(triangles[idx].centroid);
    }

    let count = end - start;
    let node_idx = nodes.len();
    nodes.push(BvhNode {
        bounds,
        left_or_start: start,
        right_or_count: count,
        is_leaf: true,
    });

    if count <= LEAF_MAX_TRIANGLES || depth >= MAX_BVH_DEPTH {
        return node_idx;
    }

    let extent = centroid_bounds.max - centroid_bounds.min;
    let axis = if extent.x >= extent.y && extent.x >= extent.z {
        0
    } else if extent.y >= extent.z {
        1
    } else {
        2
    };

    if extent[axis] <= 1e-6 {
        return node_idx;
    }

    let mid_coord = 0.5 * (centroid_bounds.min[axis] + centroid_bounds.max[axis]);
    let slice = &mut tri_indices[start..end];
    let mut split_local = 0usize;
    for i in 0..slice.len() {
        if triangles[slice[i]].centroid[axis] < mid_coord {
            slice.swap(i, split_local);
            split_local += 1;
        }
    }

    if split_local == 0 || split_local == count {
        split_local = count / 2;
    }

    let mid = start + split_local;
    let left_child = build_bvh_node(triangles, tri_indices, start, mid, depth + 1, nodes);
    let right_child = build_bvh_node(triangles, tri_indices, mid, end, depth + 1, nodes);

    nodes[node_idx].left_or_start = left_child;
    nodes[node_idx].right_or_count = right_child;
    nodes[node_idx].is_leaf = false;
    node_idx
}

fn safe_inv_dir(dir: Vec3) -> Vec3 {
    let inv = |v: f32| {
        if v.abs() < 1e-8 {
            if v.is_sign_negative() {
                -1e8
            } else {
                1e8
            }
        } else {
            1.0 / v
        }
    };
    Vec3::new(inv(dir.x), inv(dir.y), inv(dir.z))
}

fn intersect_aabb(bounds: &Aabb, origin: Vec3, inv_dir: Vec3, max_t: f32) -> Option<f32> {
    let t0 = (bounds.min - origin) * inv_dir;
    let t1 = (bounds.max - origin) * inv_dir;
    let tmin_v = t0.min(t1);
    let tmax_v = t0.max(t1);
    let tmin = tmin_v.x.max(tmin_v.y).max(tmin_v.z).max(0.0);
    let tmax = tmax_v.x.min(tmax_v.y).min(tmax_v.z).min(max_t);
    if tmax >= tmin {
        Some(tmin)
    } else {
        None
    }
}

fn intersect_triangle_two_sided(origin: Vec3, dir: Vec3, tri: &Triangle) -> Option<(f32, Vec3)> {
    let e1 = tri.v1 - tri.v0;
    let e2 = tri.v2 - tri.v0;
    let h = dir.cross(e2);
    let a = e1.dot(h);
    if a.abs() <= RAY_EPSILON {
        return None;
    }
    let f = 1.0 / a;
    let s = origin - tri.v0;
    let u = f * s.dot(h);
    if !(0.0..=1.0).contains(&u) {
        return None;
    }
    let q = s.cross(e1);
    let v = f * dir.dot(q);
    if v < 0.0 || u + v > 1.0 {
        return None;
    }
    let t = f * e2.dot(q);
    if t <= MIN_HIT_DIST_M {
        return None;
    }
    let mut normal = e1.cross(e2).normalize_or_zero();
    if normal.dot(dir) > 0.0 {
        normal = -normal;
    }
    Some((t, normal))
}

/// Spatial BVH raycast accelerator built from a compiled [`BuiltSceneMesh`].
#[derive(Default)]
pub struct ScenePicker {
    parts: Vec<PartBvh>,
}

impl ScenePicker {
    /// Construct an interactive raycast picker for all sub-parts in `mesh`.
    pub fn from_mesh(mesh: &BuiltSceneMesh) -> Self {
        let parts = mesh.parts.iter().filter_map(PartBvh::from_part).collect();
        Self { parts }
    }

    /// Return number of pickable mesh parts indexed by this picker.
    pub fn part_count(&self) -> usize {
        self.parts.len()
    }

    /// Cast a ray in world **meters** (`origin_m`, `dir_m`) and return the closest visible hit.
    pub fn pick_ray(&self, origin_m: Vec3, dir_m: Vec3, filter: &PickFilter) -> Option<PickHit> {
        let dir = dir_m.normalize_or_zero();
        if dir.length_squared() <= 1e-8 {
            return None;
        }
        let inv_dir = safe_inv_dir(dir);
        let mut best_t = f32::INFINITY;
        let mut best_hit: Option<PickHit> = None;

        for part in &self.parts {
            if !is_part_visible(
                &part.level_id,
                part.is_roof_or_ceiling,
                part.z_min_m,
                part.z_max_m,
                filter,
            ) {
                continue;
            }
            if let Some((t, normal)) = part.intersect_ray(origin_m, dir, inv_dir, best_t) {
                best_t = t;
                let world_pos = origin_m + dir * t;
                best_hit = Some(PickHit {
                    entity_id: part.entity_id.clone(),
                    entity_kind: part.entity_kind.clone(),
                    sub_part: part.sub_part.clone(),
                    world_pos_m: world_pos.to_array(),
                    normal: normal.to_array(),
                    distance_m: t,
                });
            }
        }

        best_hit
    }

    /// Convenience wrapper accepting raw `[f32; 3]` arrays in world **meters** for FFI callers.
    pub fn pick_ray_coords(
        &self,
        origin_m: [f32; 3],
        dir_m: [f32; 3],
        filter: &PickFilter,
    ) -> Option<PickHit> {
        self.pick_ray(Vec3::from_array(origin_m), Vec3::from_array(dir_m), filter)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::SceneState;
    use crate::mesher::build_scene_mesh_with_assets;
    use crate::scene_ir::SceneIR;

    fn sample_scene() -> BuiltSceneMesh {
        let json_payload = r#"{
            "schema_version": 1,
            "plan_center_in": [0.0, 0.0],
            "levels": [
                {"id": "lvl_0", "name": "Floor 1", "elevation_m": 0.0, "height_m": 2.7, "floor_thickness_m": 0.25},
                {"id": "lvl_1", "name": "Floor 2", "elevation_m": 2.95, "height_m": 2.5, "floor_thickness_m": 0.25}
            ],
            "walls": [
                {
                    "id": "wall_1",
                    "level_id": "lvl_0",
                    "segments": [{
                        "seg_index": 0,
                        "start_m": [-3.0, 0.0],
                        "end_m": [3.0, 0.0],
                        "thickness_m": 0.15,
                        "height_start_m": 2.7,
                        "height_end_m": 2.7,
                        "left_angle_rad": 0.0,
                        "right_angle_rad": 0.0,
                        "exterior": true,
                        "left_finish": "Drywall",
                        "right_finish": "Vinyl Siding",
                        "opening_cuts": [{
                            "opening_id": "door_1",
                            "x0_m": 2.5,
                            "x1_m": 3.4,
                            "z0_m": 0.0,
                            "z1_m": 2.1
                        }]
                    }]
                },
                {
                    "id": "wall_upper",
                    "level_id": "lvl_1",
                    "segments": [{
                        "seg_index": 0,
                        "start_m": [-2.0, 0.0],
                        "end_m": [2.0, 0.0],
                        "thickness_m": 0.15,
                        "height_start_m": 2.5,
                        "height_end_m": 2.5,
                        "left_angle_rad": 0.0,
                        "right_angle_rad": 0.0,
                        "exterior": true,
                        "left_finish": "Drywall",
                        "right_finish": "Vinyl Siding"
                    }]
                }
            ],
            "openings": [{
                "id": "door_1",
                "kind": "door",
                "host_wall_id": "wall_1",
                "host_seg_index": 0,
                "x_local_m": 2.5,
                "z_local_m": 0.0,
                "width_m": 0.9,
                "depth_m": 0.15,
                "height_m": 2.1,
                "style": "single",
                "swing": "left",
                "orientation": "inswing"
            }],
            "rooms": [{
                "id": "room_1",
                "level_id": "lvl_0",
                "name": "Living",
                "outer_m": [[-3.0, -3.0], [3.0, -3.0], [3.0, 3.0], [-3.0, 3.0]],
                "z_top_m": 0.0,
                "thickness_m": 0.25,
                "ceiling_z_m": 2.7
            }],
            "roofs": [{
                "id": "roof_1",
                "level_id": "lvl_0",
                "material": "asphalt_shingle",
                "thickness_m": 0.2,
                "facets": [{
                    "vertices_m": [[-3.5, -3.5, 3.0], [3.5, -3.5, 3.0], [3.5, 3.5, 3.0], [-3.5, 3.5, 3.0]],
                    "pitch_rise": 6.0
                }]
            }],
            "fixtures": [{
                "id": "fix_1",
                "level_id": "lvl_0",
                "symbol_type": "refrigerator",
                "category": "appliance",
                "loc_m": [0.0, -1.8, 0.0],
                "rot_z_rad": 0.0,
                "width_m": 0.9,
                "depth_m": 0.8,
                "height_m": 1.8,
                "has_countertop": false,
                "countertop_overhang_m": 0.0,
                "countertop_thickness_m": 0.0,
                "countertop_material": "",
                "has_backsplash": false
            }]
        }"#;
        let scene: SceneIR = serde_json::from_str(json_payload).unwrap();
        let mut state = SceneState::new();
        state.load_scene(scene).unwrap();
        build_scene_mesh_with_assets(&state, None)
    }

    #[test]
    fn pick_wall_left_and_right_faces() {
        let mesh = sample_scene();
        let picker = ScenePicker::from_mesh(&mesh);
        let filter = PickFilter::default();

        // Wall goes from (-3, 0) to (+3, 0): d=(1,0), n=(0,1). RightFace faces +n (+Y), LeftFace faces -n (-Y).
        let hit_right = picker
            .pick_ray(
                Vec3::new(-1.5, 2.0, 1.4),
                Vec3::new(0.0, -1.0, 0.0),
                &filter,
            )
            .expect("should hit wall RightFace");
        assert_eq!(hit_right.entity_id, "wall_1");
        assert_eq!(hit_right.entity_kind, "wall");
        assert_eq!(hit_right.sub_part, "RightFace");
        assert!(hit_right.normal[1] > 0.9);

        let hit_left = picker
            .pick_ray(
                Vec3::new(-1.5, -2.0, 1.4),
                Vec3::new(0.0, 1.0, 0.0),
                &filter,
            )
            .expect("should hit wall LeftFace");
        assert_eq!(hit_left.entity_id, "wall_1");
        assert_eq!(hit_left.entity_kind, "wall");
        assert_eq!(hit_left.sub_part, "LeftFace");
        assert!(hit_left.normal[1] < -0.9);
    }

    #[test]
    fn pick_opening_and_fixture_and_visibility_filter() {
        let mesh = sample_scene();
        let picker = ScenePicker::from_mesh(&mesh);
        let filter = PickFilter::default();

        // Door sits around x in [-0.5, +0.4], y = 0.0
        let hit_door = picker
            .pick_ray(Vec3::new(0.0, 2.0, 1.0), Vec3::new(0.0, -1.0, 0.0), &filter)
            .expect("should hit door leaf/frame");
        assert_eq!(hit_door.entity_id, "door_1");
        assert_eq!(hit_door.entity_kind, "opening");

        // Refrigerator sits at (0.0, -1.8, 0..1.8)
        let hit_fx = picker
            .pick_ray(Vec3::new(0.0, -4.0, 0.9), Vec3::new(0.0, 1.0, 0.0), &filter)
            .expect("should hit fixture");
        assert_eq!(hit_fx.entity_id, "fix_1");
        assert_eq!(hit_fx.entity_kind, "fixture");

        // Looking straight down from above hits roof when hide_roofs=false, and floor when hide_roofs=true.
        let hit_roof = picker
            .pick_ray(Vec3::new(1.5, 1.5, 8.0), Vec3::new(0.0, 0.0, -1.0), &filter)
            .expect("should hit roof");
        assert_eq!(hit_roof.entity_id, "roof_1");
        assert_eq!(hit_roof.entity_kind, "roof");

        let hide_filter = PickFilter {
            hide_roofs: true,
            dollhouse_level_id: Some("lvl_0".to_string()),
            level_cutoff_z_m: Some(2.7),
        };
        let hit_floor = picker
            .pick_ray(
                Vec3::new(1.5, 1.5, 8.0),
                Vec3::new(0.0, 0.0, -1.0),
                &hide_filter,
            )
            .expect("should bypass roof and hit room floor");
        assert_eq!(hit_floor.entity_id, "room_1");
        assert_eq!(hit_floor.entity_kind, "room");
        assert_eq!(hit_floor.sub_part, "Floor");
    }
}
