//! GPU-agnostic mesh containers and procedural polygon extrusion builders.
//!
//! Coordinates are in **meters** using Z-up right-handed space.

use bytemuck::{Pod, Zeroable};
use glam::{Vec2, Vec3};
use serde::{Deserialize, Serialize};

/// Interleaved mesh vertex in meters (Z-up world coordinates).
#[repr(C)]
#[derive(Copy, Clone, Debug, PartialEq, Pod, Zeroable)]
pub struct Vertex {
    /// 3D world position `[x, y, z]` in meters.
    pub pos: [f32; 3],
    /// Unit surface normal `[nx, ny, nz]`.
    pub normal: [f32; 3],
    /// Planar texture coordinates `[u, v]` in meters/pattern units.
    pub uv: [f32; 2],
}

/// Procedural surface pattern selector shared with GLSL fragment shaders.
#[repr(u32)]
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MaterialStyle {
    Solid = 0,
    Wood = 1,
    Tile = 2,
    Brick = 3,
    Siding = 4,
    Stone = 5,
    Shingle = 6,
    Glass = 7,
}

/// Architectural PBR surface definition.
#[derive(Clone, Debug, PartialEq)]
pub struct MaterialDef {
    /// Human-readable material identifier.
    pub name: String,
    /// Linear-friendly RGBA base color (`[r, g, b, a]` in `0.0..=1.0`).
    pub base_color: [f32; 4],
    /// PBR roughness in `0.0..=1.0`.
    pub roughness: f32,
    /// PBR metallic factor in `0.0..=1.0`.
    pub metallic: f32,
    /// Procedural fragment shader pattern family.
    pub style: MaterialStyle,
    /// Pattern scale multiplier (`1.0` default).
    pub pattern_scale: f32,
    /// Pattern rotation in **degrees**.
    pub pattern_rotation_deg: f32,
    /// True when rendered in the alpha-blended transparent pass.
    pub transparent: bool,
}

/// Quantized key used when deduplicating materials for `.glb` export.
pub type MaterialKey = (String, [u16; 4], u16, u16, u32, bool);

/// Flags classifying mesh part visibility in Dollhouse and X-Ray modes.
#[derive(Copy, Clone, Debug, Default)]
pub struct PartFlags {
    /// True for roofs and ceiling plates hidden by Auto-Hide Roofs.
    pub is_roof_or_ceiling: bool,
    /// True for structural wall faces rendered translucent in X-Ray mode.
    pub is_wall: bool,
}

impl MaterialDef {
    /// Quantized key used when deduplicating materials for `.glb` export.
    pub fn quant_key(&self) -> MaterialKey {
        let q = |v: f32| (v.clamp(0.0, 1.0) * 1000.0).round() as u16;
        (
            self.name.clone(),
            [
                q(self.base_color[0]),
                q(self.base_color[1]),
                q(self.base_color[2]),
                q(self.base_color[3]),
            ],
            q(self.roughness),
            q(self.metallic),
            self.style as u32,
            self.transparent,
        )
    }
}

/// Single renderable and pickable sub-mesh belonging to a `SceneIR` entity.
#[derive(Clone, Debug)]
pub struct MeshPart {
    /// Source `SceneIR` entity identifier.
    pub entity_id: String,
    /// Entity category (`"wall"`, `"opening"`, `"room"`, `"roof"`, etc.).
    pub entity_kind: String,
    /// Level identifier for Dollhouse level filtering.
    pub level_id: String,
    /// Sub-part label (`"LeftFace"`, `"RightFace"`, `"Reveal"`, `"Glass"`, etc.).
    pub sub_part: String,
    /// True for roofs and ceiling plates hidden by Auto-Hide Roofs.
    pub is_roof_or_ceiling: bool,
    /// True for structural wall faces rendered translucent in X-Ray mode.
    pub is_wall: bool,
    /// Minimum Z coordinate in meters.
    pub z_min_m: f32,
    /// Maximum Z coordinate in meters.
    pub z_max_m: f32,
    /// Assigned PBR/stylized material definition.
    pub material: MaterialDef,
    /// Vertex buffer in meters (Z-up).
    pub vertices: Vec<Vertex>,
    /// Triangle index buffer (`len % 3 == 0`).
    pub indices: Vec<u32>,
}

/// Vertical elevation bounds for a single floor level in meters.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct LevelBounds {
    /// Level identifier.
    pub id: String,
    /// Display name.
    pub name: String,
    /// Floor top elevation in meters.
    pub elevation_m: f32,
    /// Ceiling/plate elevation (`elevation_m + height_m`) in meters.
    pub top_z_m: f32,
}

/// Serializable statistics for a compiled 3D scene mesh.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct MeshStats {
    /// Total generated mesh parts.
    pub part_count: usize,
    /// Total vertices across all parts.
    pub vertex_count: usize,
    /// Total triangles across all parts.
    pub triangle_count: usize,
    /// World axis-aligned bounding box minimum `[x, y, z]` in meters.
    pub bounds_min: [f32; 3],
    /// World axis-aligned bounding box maximum `[x, y, z]` in meters.
    pub bounds_max: [f32; 3],
}

/// Complete triangulated scene output from [`crate::build_scene_mesh`].
#[derive(Clone, Debug, Default)]
pub struct BuiltSceneMesh {
    /// All generated mesh parts.
    pub parts: Vec<MeshPart>,
    /// World bounding box minimum `[x, y, z]` in meters.
    pub bounds_min: [f32; 3],
    /// World bounding box maximum `[x, y, z]` in meters.
    pub bounds_max: [f32; 3],
    /// Level elevation spans sorted by ascending `elevation_m`.
    pub levels: Vec<LevelBounds>,
}

impl BuiltSceneMesh {
    /// Compute aggregate vertex, triangle, and bounding-box statistics.
    pub fn stats(&self) -> MeshStats {
        let vertex_count: usize = self.parts.iter().map(|p| p.vertices.len()).sum();
        let triangle_count: usize = self.parts.iter().map(|p| p.indices.len() / 3).sum();
        MeshStats {
            part_count: self.parts.len(),
            vertex_count,
            triangle_count,
            bounds_min: self.bounds_min,
            bounds_max: self.bounds_max,
        }
    }

    /// Recompute `bounds_min` and `bounds_max` in meters from current parts.
    pub fn recompute_bounds(&mut self) {
        let mut min_v = Vec3::splat(f32::INFINITY);
        let mut max_v = Vec3::splat(f32::NEG_INFINITY);
        let mut any = false;
        for part in &self.parts {
            for v in &part.vertices {
                let p = Vec3::from_array(v.pos);
                min_v = min_v.min(p);
                max_v = max_v.max(p);
                any = true;
            }
        }
        if any {
            self.bounds_min = min_v.to_array();
            self.bounds_max = max_v.to_array();
        } else {
            self.bounds_min = [-2.0, -2.0, 0.0];
            self.bounds_max = [2.0, 2.0, 3.0];
        }
    }
}

/// Stateful triangle mesh accumulator producing [`MeshPart`] instances.
#[derive(Default)]
pub struct MeshBuilder {
    vertices: Vec<Vertex>,
    indices: Vec<u32>,
    z_min: f32,
    z_max: f32,
    has_verts: bool,
}

impl MeshBuilder {
    /// Create an empty mesh builder.
    pub fn new() -> Self {
        Self {
            vertices: Vec::new(),
            indices: Vec::new(),
            z_min: f32::INFINITY,
            z_max: f32::NEG_INFINITY,
            has_verts: false,
        }
    }

    /// Return true when no triangles have been emitted yet.
    pub fn is_empty(&self) -> bool {
        self.indices.is_empty()
    }

    fn record_z(&mut self, z: f32) {
        if !self.has_verts {
            self.z_min = z;
            self.z_max = z;
            self.has_verts = true;
        } else {
            self.z_min = self.z_min.min(z);
            self.z_max = self.z_max.max(z);
        }
    }

    fn push_vertex(&mut self, pos: Vec3, normal: Vec3, uv: [f32; 2]) -> u32 {
        self.record_z(pos.z);
        let idx = self.vertices.len() as u32;
        self.vertices.push(Vertex {
            pos: pos.to_array(),
            normal: normal.normalize_or_zero().to_array(),
            uv,
        });
        idx
    }

    /// Emit one CCW triangle `(a, b, c)` with auto-computed outward face normal.
    pub fn push_tri(&mut self, a: Vec3, b: Vec3, c: Vec3, uvs: [[f32; 2]; 3]) {
        let normal = (b - a).cross(c - a);
        if normal.length_squared() <= 1e-12 {
            return;
        }
        let n = normal.normalize();
        let ia = self.push_vertex(a, n, uvs[0]);
        let ib = self.push_vertex(b, n, uvs[1]);
        let ic = self.push_vertex(c, n, uvs[2]);
        self.indices.extend_from_slice(&[ia, ib, ic]);
    }

    /// Emit a planar CCW quad `(a, b, c, d)` with automatic outward normal & box UVs.
    pub fn push_quad(&mut self, a: Vec3, b: Vec3, c: Vec3, d: Vec3) {
        let e1 = b - a;
        let e2 = d - a;
        let normal = e1.cross(c - a);
        if normal.length_squared() <= 1e-12 {
            return;
        }
        let n = normal.normalize();
        let u_len = e1.length();
        let v_len = e2.length();
        let ia = self.push_vertex(a, n, [0.0, 0.0]);
        let ib = self.push_vertex(b, n, [u_len, 0.0]);
        let ic = self.push_vertex(c, n, [u_len, v_len]);
        let id = self.push_vertex(d, n, [0.0, v_len]);
        self.indices.extend_from_slice(&[ia, ib, ic, ia, ic, id]);
    }

    /// Emit a quad with explicit per-corner texture coordinates `(u, v)`.
    pub fn push_quad_uv(&mut self, pts: [Vec3; 4], uvs: [[f32; 2]; 4]) {
        let normal = (pts[1] - pts[0]).cross(pts[2] - pts[0]);
        if normal.length_squared() <= 1e-12 {
            return;
        }
        let n = normal.normalize();
        let ia = self.push_vertex(pts[0], n, uvs[0]);
        let ib = self.push_vertex(pts[1], n, uvs[1]);
        let ic = self.push_vertex(pts[2], n, uvs[2]);
        let id = self.push_vertex(pts[3], n, uvs[3]);
        self.indices.extend_from_slice(&[ia, ib, ic, ia, ic, id]);
    }

    /// Emit a solid axis-aligned box rotated around Z at `origin` (`size = [w, d, h]` in meters).
    ///
    /// Local extents cover `[-w/2..w/2] x [-d/2..d/2] x [z_off..z_off+h]`.
    pub fn push_oriented_box(
        &mut self,
        origin: Vec3,
        rot_z_rad: f32,
        center_offset: Vec3,
        size: Vec3,
    ) {
        let hw = size.x * 0.5;
        let hd = size.y * 0.5;
        let hz = size.z * 0.5;
        if hw <= 1e-5 || hd <= 1e-5 || hz <= 1e-5 {
            return;
        }
        let (sr, cr) = rot_z_rad.sin_cos();
        let xf = |lx: f32, ly: f32, lz: f32| -> Vec3 {
            let p = center_offset + Vec3::new(lx, ly, lz);
            origin + Vec3::new(p.x * cr - p.y * sr, p.x * sr + p.y * cr, p.z)
        };

        let c000 = xf(-hw, -hd, -hz);
        let c100 = xf(hw, -hd, -hz);
        let c110 = xf(hw, hd, -hz);
        let c010 = xf(-hw, hd, -hz);
        let c001 = xf(-hw, -hd, hz);
        let c101 = xf(hw, -hd, hz);
        let c111 = xf(hw, hd, hz);
        let c011 = xf(-hw, hd, hz);

        self.push_quad(c001, c101, c111, c011); // +Z top
        self.push_quad(c010, c110, c100, c000); // -Z bottom
        self.push_quad(c000, c100, c101, c001); // -Y front
        self.push_quad(c110, c010, c011, c111); // +Y back
        self.push_quad(c100, c110, c111, c101); // +X right
        self.push_quad(c010, c000, c001, c011); // -X left
    }

    /// Extrude a 2D polygon (`outer`) with optional interior holes from `z_bot` to `z_top` (meters).
    pub fn push_extruded_polygon(
        &mut self,
        outer_in: &[[f64; 2]],
        holes_in: &[Vec<[f64; 2]>],
        z_bot: f32,
        z_top: f32,
    ) {
        if (z_top - z_bot).abs() <= 1e-5 {
            return;
        }
        let z0 = z_bot.min(z_top);
        let z1 = z_bot.max(z_top);

        let mut outer = clean_ring_2d(outer_in, 1e-4);
        if outer.len() < 3 {
            return;
        }
        if signed_area_2d(&outer) < 0.0 {
            outer.reverse();
        }

        // Clean and orient valid interior holes clockwise for consistent side normals.
        let mut valid_holes: Vec<Vec<Vec2>> = Vec::new();
        for raw_hole in holes_in {
            let mut hole = clean_ring_2d(raw_hole, 1e-4);
            if hole.len() < 3 {
                continue;
            }
            if signed_area_2d(&hole) > 0.0 {
                hole.reverse();
            }
            // Keep holes whose centroid and at least 3 vertices sit inside outer.
            let centroid = hole.iter().copied().sum::<Vec2>() / (hole.len() as f32);
            let inside_cnt = hole.iter().filter(|&&p| pt_in_ring_2d(p, &outer)).count();
            if pt_in_ring_2d(centroid, &outer) && inside_cnt >= 3 {
                valid_holes.push(hole);
            }
        }

        // Try triangulating with holes first; if invalid overlap causes empty earcut, retry outer only.
        let mut used_holes = !valid_holes.is_empty();
        let mut tri_data = flatten_for_earcut(&outer, &valid_holes);
        let mut tris =
            earcutr::earcut(&tri_data.coords, &tri_data.hole_indices, 2).unwrap_or_default();
        if tris.is_empty() && used_holes {
            used_holes = false;
            tri_data = flatten_for_earcut(&outer, &[]);
            tris = earcutr::earcut(&tri_data.coords, &[], 2).unwrap_or_default();
        }
        if tris.is_empty() {
            return;
        }

        // Top cap (+Z normal) and bottom cap (-Z normal)
        for &[i0, i1, i2] in tris.as_chunks::<3>().0 {
            let p0 = tri_data.points[i0];
            let p1 = tri_data.points[i1];
            let p2 = tri_data.points[i2];

            self.push_tri(
                Vec3::new(p0.x, p0.y, z1),
                Vec3::new(p1.x, p1.y, z1),
                Vec3::new(p2.x, p2.y, z1),
                [[p0.x, p0.y], [p1.x, p1.y], [p2.x, p2.y]],
            );
            self.push_tri(
                Vec3::new(p0.x, p0.y, z0),
                Vec3::new(p2.x, p2.y, z0),
                Vec3::new(p1.x, p1.y, z0),
                [[p0.x, p0.y], [p2.x, p2.y], [p1.x, p1.y]],
            );
        }

        // Outer perimeter walls (CCW loop -> outward normals)
        emit_ring_walls(self, &outer, z0, z1);

        // Hole walls (CW loop -> normals pointing into the hole cavity)
        if used_holes {
            for hole in &valid_holes {
                emit_ring_walls(self, hole, z0, z1);
            }
        }
    }

    /// Finalize into a [`MeshPart`] if non-empty.
    pub fn into_part(
        self,
        entity_id: impl Into<String>,
        entity_kind: impl Into<String>,
        level_id: impl Into<String>,
        sub_part: impl Into<String>,
        flags: PartFlags,
        material: MaterialDef,
    ) -> Option<MeshPart> {
        if self.indices.is_empty() {
            return None;
        }
        Some(MeshPart {
            entity_id: entity_id.into(),
            entity_kind: entity_kind.into(),
            level_id: level_id.into(),
            sub_part: sub_part.into(),
            is_roof_or_ceiling: flags.is_roof_or_ceiling,
            is_wall: flags.is_wall,
            z_min_m: self.z_min,
            z_max_m: self.z_max,
            material,
            vertices: self.vertices,
            indices: self.indices,
        })
    }
}

struct EarcutInput {
    coords: Vec<f64>,
    hole_indices: Vec<usize>,
    points: Vec<Vec2>,
}

fn flatten_for_earcut(outer: &[Vec2], holes: &[Vec<Vec2>]) -> EarcutInput {
    let mut coords =
        Vec::with_capacity((outer.len() + holes.iter().map(|h| h.len()).sum::<usize>()) * 2);
    let mut points = Vec::new();
    let mut hole_indices = Vec::with_capacity(holes.len());

    for &p in outer {
        coords.push(p.x as f64);
        coords.push(p.y as f64);
        points.push(p);
    }
    for hole in holes {
        if hole.len() < 3 {
            continue;
        }
        hole_indices.push(points.len());
        for &p in hole {
            coords.push(p.x as f64);
            coords.push(p.y as f64);
            points.push(p);
        }
    }
    EarcutInput {
        coords,
        hole_indices,
        points,
    }
}

fn emit_ring_walls(builder: &mut MeshBuilder, ring: &[Vec2], z0: f32, z1: f32) {
    let n = ring.len();
    for i in 0..n {
        let a = ring[i];
        let b = ring[(i + 1) % n];
        if a.distance(b) <= 1e-5 {
            continue;
        }
        builder.push_quad(
            Vec3::new(a.x, a.y, z0),
            Vec3::new(b.x, b.y, z0),
            Vec3::new(b.x, b.y, z1),
            Vec3::new(a.x, a.y, z1),
        );
    }
}

pub(crate) fn clean_ring_2d(pts: &[[f64; 2]], tol: f32) -> Vec<Vec2> {
    let mut out: Vec<Vec2> = Vec::with_capacity(pts.len());
    for pt in pts {
        let v = Vec2::new(pt[0] as f32, pt[1] as f32);
        if out.last().is_none_or(|prev| prev.distance(v) > tol) {
            out.push(v);
        }
    }
    if out.len() >= 2 && out[0].distance(*out.last().unwrap_or(&out[0])) <= tol {
        out.pop();
    }
    out
}

pub(crate) fn signed_area_2d(pts: &[Vec2]) -> f32 {
    let n = pts.len();
    if n < 3 {
        return 0.0;
    }
    let mut s = 0.0f32;
    for i in 0..n {
        let p0 = pts[i];
        let p1 = pts[(i + 1) % n];
        s += p0.x * p1.y - p1.x * p0.y;
    }
    0.5 * s
}

pub(crate) fn pt_in_ring_2d(p: Vec2, ring: &[Vec2]) -> bool {
    let n = ring.len();
    if n < 3 {
        return false;
    }
    let mut inside = false;
    for i in 0..n {
        let a = ring[i];
        let b = ring[(i + 1) % n];
        if ((a.y > p.y) != (b.y > p.y))
            && (p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y + 1e-12) + a.x)
        {
            inside = !inside;
        }
    }
    inside
}
