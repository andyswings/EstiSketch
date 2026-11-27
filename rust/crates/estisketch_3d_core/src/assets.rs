//! Pure-Rust binary glTF 2.0 (`.glb`) asset loader and cached [`AssetLibrary`].
//!
//! Parses bundled `CC0-1.0` architectural asset packs defined in `manifest.json`
//! and converts glTF Y-up meters `(x, y, z)` back to EstiSketch Z-up meters
//! `(x, -z, y)`, scaling cleanly to the placed fixture's `(width, depth, height)`.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use glam::{Vec2, Vec3};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::glb_export::export_loaded_asset_to_glb;
use crate::mesh::{MaterialDef, MaterialStyle, MeshPart, Vertex};
use crate::scene_ir::{CustomAssetIR, FixtureIR};

const GLB_MAGIC: u32 = 0x4654_6C67;
const CHUNK_JSON: u32 = 0x4E4F_534A;
const CHUNK_BIN: u32 = 0x004E_4942;

/// Entry in `src/EstiSketch/assets_3d/manifest.json`.
#[derive(Clone, Debug, Deserialize)]
pub struct AssetManifestEntry {
    /// Relative path to `.glb` file under asset root.
    pub glb: String,
    /// SPDX license identifier (e.g. `"CC0-1.0"`).
    pub license: String,
    /// Attribution/origin note.
    pub source: String,
    /// Native model bounding box `[w, d, h]` in meters.
    pub native_size_m: [f32; 3],
    /// Origin convention (`"bottom_center"`).
    pub anchor: String,
    /// Material names allowed to receive user `fill_color` tint.
    #[serde(default)]
    pub recolor_slots: Vec<String>,
}

/// Decoded mesh primitive stored in normalized local Z-up meters (centered around origin XY, z>=0).
#[derive(Clone, Debug)]
pub struct LoadedGlbPrimitive {
    pub material: MaterialDef,
    pub vertices: Vec<Vertex>,
    pub indices: Vec<u32>,
}

/// Decoded `.glb` template with native bounding box in Z-up meters.
#[derive(Clone, Debug)]
pub struct LoadedGlbAsset {
    pub primitives: Vec<LoadedGlbPrimitive>,
    pub size_m: [f32; 3],
}

/// Cached `manifest.json` and parsed `.glb` asset registry.
#[derive(Clone, Debug, Default)]
pub struct AssetLibrary {
    root_dir: Option<PathBuf>,
    manifest: HashMap<String, AssetManifestEntry>,
    cache: HashMap<String, Option<LoadedGlbAsset>>,
}

impl AssetLibrary {
    /// Load `manifest.json` from `root_dir` if present (non-fatal on missing directory).
    pub fn load_from_dir(root_dir: impl AsRef<Path>) -> Result<Self, String> {
        let root = root_dir.as_ref().to_path_buf();
        let manifest_path = root.join("manifest.json");
        if !manifest_path.is_file() {
            return Ok(Self {
                root_dir: Some(root),
                manifest: HashMap::new(),
                cache: HashMap::new(),
            });
        }
        let raw = std::fs::read_to_string(&manifest_path)
            .map_err(|e| format!("Failed reading {}: {e}", manifest_path.display()))?;
        let manifest: HashMap<String, AssetManifestEntry> = serde_json::from_str(&raw)
            .map_err(|e| format!("Invalid {}: {e}", manifest_path.display()))?;
        Ok(Self {
            root_dir: Some(root),
            manifest,
            cache: HashMap::new(),
        })
    }

    /// Number of fixture symbols registered in `manifest.json`.
    pub fn manifest_len(&self) -> usize {
        self.manifest.len()
    }

    /// Try instantiating `MeshPart`s from the bundled `.glb` for `fx`, or return `None` to fall back.
    pub fn instantiate_fixture_parts(&mut self, fx: &FixtureIR) -> Option<Vec<MeshPart>> {
        let root = self.root_dir.as_ref()?;
        let sym = fx.symbol_type.to_lowercase();
        let entry = self.manifest.get(&sym)?.clone();

        if !self.cache.contains_key(&sym) {
            let glb_path = root.join(&entry.glb);
            let loaded = load_glb_asset(&glb_path).ok();
            self.cache.insert(sym.clone(), loaded);
        }
        let asset = self.cache.get(&sym)?.as_ref()?;

        let sx = (fx.width_m as f32).max(0.05) / asset.size_m[0].max(0.05);
        let sy = (fx.depth_m as f32).max(0.05) / asset.size_m[1].max(0.05);
        let sz = (fx.height_m as f32).max(0.05) / asset.size_m[2].max(0.05);
        let scale = Vec3::new(sx, sy, sz);
        let origin = Vec3::new(fx.loc_m[0] as f32, fx.loc_m[1] as f32, fx.loc_m[2] as f32);
        let (sr, cr) = (fx.rot_z_rad as f32).sin_cos();

        let mut out: Vec<MeshPart> = Vec::with_capacity(asset.primitives.len());
        for (p_idx, prim) in asset.primitives.iter().enumerate() {
            let mut mat = prim.material.clone();
            if let Some([r, g, b]) = fx.fill_color {
                if entry
                    .recolor_slots
                    .iter()
                    .any(|slot| slot.eq_ignore_ascii_case(&mat.name))
                {
                    mat.base_color = [
                        (r as f32).clamp(0.0, 1.0),
                        (g as f32).clamp(0.0, 1.0),
                        (b as f32).clamp(0.0, 1.0),
                        mat.base_color[3],
                    ];
                }
            }
            let mut z_min = f32::INFINITY;
            let mut z_max = f32::NEG_INFINITY;
            let mut verts: Vec<Vertex> = Vec::with_capacity(prim.vertices.len());
            for v in &prim.vertices {
                let p = Vec3::from_array(v.pos) * scale;
                let wp = origin + Vec3::new(p.x * cr - p.y * sr, p.x * sr + p.y * cr, p.z);
                let n_raw = Vec3::new(v.normal[0] / sx, v.normal[1] / sy, v.normal[2] / sz);
                let wn = Vec3::new(
                    n_raw.x * cr - n_raw.y * sr,
                    n_raw.x * sr + n_raw.y * cr,
                    n_raw.z,
                )
                .normalize_or_zero();
                z_min = z_min.min(wp.z);
                z_max = z_max.max(wp.z);
                verts.push(Vertex {
                    pos: wp.to_array(),
                    normal: wn.to_array(),
                    uv: v.uv,
                });
            }
            out.push(MeshPart {
                entity_id: fx.id.clone(),
                entity_kind: "fixture".to_string(),
                level_id: fx.level_id.clone(),
                sub_part: format!("Asset_{p_idx}"),
                is_roof_or_ceiling: false,
                is_wall: false,
                z_min_m: z_min,
                z_max_m: z_max,
                material: mat,
                vertices: verts,
                indices: prim.indices.clone(),
            });
        }
        if out.is_empty() {
            None
        } else {
            Some(out)
        }
    }

    /// Instantiate a [`CustomAssetIR`] from disk relative to `root_dir` or absolute path.
    pub fn instantiate_custom_asset(&self, item: &CustomAssetIR) -> Result<Vec<MeshPart>, String> {
        let p = Path::new(&item.path);
        let full = if p.is_absolute() {
            p.to_path_buf()
        } else if let Some(ref root) = self.root_dir {
            root.join(p)
        } else {
            p.to_path_buf()
        };
        let asset = load_glb_asset(&full)?;
        let origin = Vec3::new(
            item.loc_m[0] as f32,
            item.loc_m[1] as f32,
            item.loc_m[2] as f32,
        );
        let scale = Vec3::new(
            item.scale[0] as f32,
            item.scale[1] as f32,
            item.scale[2] as f32,
        );
        let (sr, cr) = (item.rot_z_rad as f32).sin_cos();

        let mut parts = Vec::with_capacity(asset.primitives.len());
        for (idx, prim) in asset.primitives.iter().enumerate() {
            let mut z_min = f32::INFINITY;
            let mut z_max = f32::NEG_INFINITY;
            let mut verts = Vec::with_capacity(prim.vertices.len());
            for v in &prim.vertices {
                let p = Vec3::from_array(v.pos) * scale;
                let wp = origin + Vec3::new(p.x * cr - p.y * sr, p.x * sr + p.y * cr, p.z);
                let wn = Vec3::new(
                    v.normal[0] * cr - v.normal[1] * sr,
                    v.normal[0] * sr + v.normal[1] * cr,
                    v.normal[2],
                )
                .normalize_or_zero();
                z_min = z_min.min(wp.z);
                z_max = z_max.max(wp.z);
                verts.push(Vertex {
                    pos: wp.to_array(),
                    normal: wn.to_array(),
                    uv: v.uv,
                });
            }
            parts.push(MeshPart {
                entity_id: item.id.clone(),
                entity_kind: "custom_asset".to_string(),
                level_id: String::new(),
                sub_part: format!("Custom_{idx}"),
                is_roof_or_ceiling: false,
                is_wall: false,
                z_min_m: z_min,
                z_max_m: z_max,
                material: prim.material.clone(),
                vertices: verts,
                indices: prim.indices.clone(),
            });
        }
        Ok(parts)
    }
}

fn gltf_to_zup(v: [f32; 3]) -> [f32; 3] {
    [v[0], -v[2], v[1]]
}

fn read_u32_le(bytes: &[u8], off: usize) -> Option<u32> {
    let slice: [u8; 4] = bytes.get(off..off + 4)?.try_into().ok()?;
    Some(u32::from_le_bytes(slice))
}

fn read_f32_le(bytes: &[u8], off: usize) -> Option<f32> {
    let slice: [u8; 4] = bytes.get(off..off + 4)?.try_into().ok()?;
    Some(f32::from_le_bytes(slice))
}

fn accessor_slice<'a>(
    doc: &Value,
    bin: &'a [u8],
    acc_idx: usize,
) -> Option<(&'a [u8], usize, usize, u32)> {
    let acc = doc.get("accessors")?.get(acc_idx)?;
    let bv_idx = acc.get("bufferView")?.as_u64()? as usize;
    let bv = doc.get("bufferViews")?.get(bv_idx)?;
    let bv_off = bv.get("byteOffset").and_then(Value::as_u64).unwrap_or(0) as usize;
    let acc_off = acc.get("byteOffset").and_then(Value::as_u64).unwrap_or(0) as usize;
    let count = acc.get("count")?.as_u64()? as usize;
    let comp_type = acc.get("componentType")?.as_u64()? as u32;
    let type_str = acc.get("type")?.as_str()?;

    let comps = match type_str {
        "SCALAR" => 1usize,
        "VEC2" => 2usize,
        "VEC3" => 3usize,
        "VEC4" => 4usize,
        _ => return None,
    };
    let elem_size = match comp_type {
        5121 | 5120 => 1usize,
        5123 | 5122 => 2usize,
        5125 | 5126 => 4usize,
        _ => return None,
    };
    let default_stride = comps * elem_size;
    let stride = bv
        .get("byteStride")
        .and_then(Value::as_u64)
        .map_or(default_stride, |s| s as usize);
    let start = bv_off + acc_off;
    let needed = if count == 0 {
        0
    } else {
        (count - 1) * stride + default_stride
    };
    let end = start + needed;
    if end > bin.len() {
        return None;
    }
    Some((&bin[start..end], count, stride, comp_type))
}

/// Decode a binary `.glb` file into normalized Z-up meters (bottom-center `[0, 0, 0]`).
pub fn load_glb_asset(path: &Path) -> Result<LoadedGlbAsset, String> {
    let raw = std::fs::read(path).map_err(|e| format!("Read {}: {e}", path.display()))?;
    parse_glb_bytes(&raw)
}

/// Summary metrics computed for an imported `.glb`, `.gltf`, or `.obj` 3D asset.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AssetInspection {
    /// Bounding box dimensions `[width, depth, height]` in **meters** (Z-up).
    pub size_m: [f32; 3],
    /// Counter-clockwise 2D convex hull footprint points `[x, y]` in **meters** centered on origin.
    pub silhouette_2d_m: Vec<[f32; 2]>,
    /// Deterministic 64-bit FNV-1a geometry hash hex string for Blender sync delta detection.
    pub mesh_hash: String,
    /// Total triangle count across all decoded mesh primitives.
    pub triangle_count: usize,
}

/// Parse standalone JSON `.gltf` file with data-URI or relative `.bin` buffer into Z-up meters.
pub fn load_gltf_file(path: &Path) -> Result<LoadedGlbAsset, String> {
    let raw = std::fs::read_to_string(path).map_err(|e| format!("Read {}: {e}", path.display()))?;
    let doc: Value = serde_json::from_str(&raw).map_err(|e| format!("Invalid glTF JSON: {e}"))?;
    let base_dir = path.parent().unwrap_or_else(|| Path::new("."));
    let bin = load_first_gltf_buffer(&doc, base_dir)?;
    decode_gltf_doc(&doc, &bin)
}

/// Load a `.glb`, `.gltf`, or Wavefront `.obj` 3D model into normalized Z-up meters.
pub fn load_3d_asset(path: &Path) -> Result<LoadedGlbAsset, String> {
    let ext = path
        .extension()
        .and_then(|s| s.to_str())
        .map(str::to_lowercase)
        .unwrap_or_default();
    match ext.as_str() {
        "glb" => load_glb_asset(path),
        "gltf" => load_gltf_file(path),
        "obj" => {
            let raw = std::fs::read(path).map_err(|e| format!("Read {}: {e}", path.display()))?;
            load_obj_bytes(&raw)
        }
        other => Err(format!(
            "Unsupported 3D asset format '.{other}' (expected .glb, .gltf, or .obj)"
        )),
    }
}

/// Parse Wavefront `.obj` bytes (Y-up meters) into normalized bottom-centered Z-up meters.
pub fn load_obj_bytes(raw: &[u8]) -> Result<LoadedGlbAsset, String> {
    let text = String::from_utf8_lossy(raw);
    let mut positions: Vec<[f32; 3]> = Vec::new();
    let mut normals: Vec<[f32; 3]> = Vec::new();
    let mut uvs: Vec<[f32; 2]> = Vec::new();
    let mut verts: Vec<Vertex> = Vec::new();
    let mut indices: Vec<u32> = Vec::new();

    for line in text.lines() {
        let trimmed = line.split('#').next().unwrap_or("").trim();
        if trimmed.is_empty() {
            continue;
        }
        let mut parts = trimmed.split_whitespace();
        let Some(tag) = parts.next() else {
            continue;
        };
        match tag {
            "v" => {
                let coords: Vec<f32> = parts.filter_map(|p| p.parse::<f32>().ok()).collect();
                if coords.len() >= 3 {
                    positions.push(gltf_to_zup([coords[0], coords[1], coords[2]]));
                }
            }
            "vn" => {
                let coords: Vec<f32> = parts.filter_map(|p| p.parse::<f32>().ok()).collect();
                if coords.len() >= 3 {
                    normals.push(gltf_to_zup([coords[0], coords[1], coords[2]]));
                }
            }
            "vt" => {
                let coords: Vec<f32> = parts.filter_map(|p| p.parse::<f32>().ok()).collect();
                if coords.len() >= 2 {
                    uvs.push([coords[0], coords[1]]);
                }
            }
            "f" => {
                let corners: Vec<(Option<usize>, Option<usize>, Option<usize>)> = parts
                    .map(|tok| {
                        parse_obj_face_vertex(tok, positions.len(), uvs.len(), normals.len())
                    })
                    .collect();
                if corners.len() < 3 {
                    continue;
                }
                for i in 1..(corners.len() - 1) {
                    let tri_refs = [corners[0], corners[i], corners[i + 1]];
                    let mut tri_pos = [[0.0f32; 3]; 3];
                    let mut valid = true;
                    for (k, (pi, _, _)) in tri_refs.iter().enumerate() {
                        if let Some(p_idx) = pi.and_then(|idx| positions.get(idx)) {
                            tri_pos[k] = *p_idx;
                        } else {
                            valid = false;
                            break;
                        }
                    }
                    if !valid {
                        continue;
                    }
                    let face_n = (Vec3::from_array(tri_pos[1]) - Vec3::from_array(tri_pos[0]))
                        .cross(Vec3::from_array(tri_pos[2]) - Vec3::from_array(tri_pos[0]))
                        .normalize_or_zero()
                        .to_array();
                    for (k, &(_, ti, ni)) in tri_refs.iter().enumerate() {
                        let p = tri_pos[k];
                        let n = ni
                            .and_then(|idx| normals.get(idx))
                            .copied()
                            .unwrap_or(face_n);
                        let uv = ti
                            .and_then(|idx| uvs.get(idx))
                            .copied()
                            .unwrap_or([p[0], p[1]]);
                        let idx = verts.len() as u32;
                        verts.push(Vertex {
                            pos: p,
                            normal: n,
                            uv,
                        });
                        indices.push(idx);
                    }
                }
            }
            _ => {}
        }
    }

    if verts.is_empty() || indices.is_empty() {
        return Err("OBJ contained no valid triangle faces".to_string());
    }

    let primitives = vec![LoadedGlbPrimitive {
        material: MaterialDef {
            name: "ImportedObj".to_string(),
            base_color: [0.85, 0.84, 0.82, 1.0],
            roughness: 0.6,
            metallic: 0.0,
            style: MaterialStyle::Solid,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        },
        vertices: verts,
        indices,
    }];
    Ok(normalize_asset_primitives(primitives))
}

/// Compute a counter-clockwise 2D convex hull footprint `[x, y]` in **meters** for `asset`.
pub fn compute_asset_silhouette_2d(asset: &LoadedGlbAsset) -> Vec<[f32; 2]> {
    let mut pts: Vec<Vec2> = Vec::new();
    for prim in &asset.primitives {
        for v in &prim.vertices {
            // Snap to mm grid to deduplicate dense organic meshes rapidly
            let x = (v.pos[0] * 1000.0).round() * 0.001;
            let y = (v.pos[1] * 1000.0).round() * 0.001;
            pts.push(Vec2::new(x, y));
        }
    }
    if pts.len() < 3 {
        let hw = 0.5 * asset.size_m[0].max(0.1);
        let hd = 0.5 * asset.size_m[1].max(0.1);
        return vec![[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]];
    }
    pts.sort_by(|a, b| a.x.total_cmp(&b.x).then_with(|| a.y.total_cmp(&b.y)));
    pts.dedup_by(|a, b| (*a - *b).length_squared() <= 1e-6);
    if pts.len() < 3 {
        let hw = 0.5 * asset.size_m[0].max(0.1);
        let hd = 0.5 * asset.size_m[1].max(0.1);
        return vec![[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]];
    }

    let cross2 = |o: Vec2, a: Vec2, b: Vec2| -> f32 {
        (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)
    };
    let mut lower: Vec<Vec2> = Vec::new();
    for &p in &pts {
        while lower.len() >= 2 && cross2(lower[lower.len() - 2], lower[lower.len() - 1], p) <= 0.0 {
            lower.pop();
        }
        lower.push(p);
    }
    let mut upper: Vec<Vec2> = Vec::new();
    for &p in pts.iter().rev() {
        while upper.len() >= 2 && cross2(upper[upper.len() - 2], upper[upper.len() - 1], p) <= 0.0 {
            upper.pop();
        }
        upper.push(p);
    }
    lower.pop();
    upper.pop();
    lower.extend(upper);
    if lower.len() < 3 {
        let hw = 0.5 * asset.size_m[0].max(0.1);
        let hd = 0.5 * asset.size_m[1].max(0.1);
        return vec![[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]];
    }
    lower.into_iter().map(|p| [p.x, p.y]).collect()
}

/// Compute a deterministic 64-bit FNV-1a hash over `asset` vertex geometry and index count.
pub fn compute_asset_mesh_hash(asset: &LoadedGlbAsset) -> String {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    let prime: u64 = 0x0100_0000_01b3;
    let feed = |h: &mut u64, bytes: &[u8]| {
        for &b in bytes {
            *h ^= u64::from(b);
            *h = h.wrapping_mul(prime);
        }
    };
    let tri_count: usize = asset.primitives.iter().map(|p| p.indices.len() / 3).sum();
    feed(&mut hash, &(tri_count as u64).to_le_bytes());
    for prim in &asset.primitives {
        feed(&mut hash, &(prim.vertices.len() as u64).to_le_bytes());
        for v in &prim.vertices {
            for c in v.pos {
                let q = (c * 1000.0).round() as i32;
                feed(&mut hash, &q.to_le_bytes());
            }
        }
    }
    format!("{hash:016x}")
}

/// Summarize bounds, 2D hull silhouette, geometry hash, and triangle count for [`LoadedGlbAsset`].
pub fn inspect_loaded_asset(asset: &LoadedGlbAsset) -> AssetInspection {
    let triangle_count = asset.primitives.iter().map(|p| p.indices.len() / 3).sum();
    AssetInspection {
        size_m: asset.size_m,
        silhouette_2d_m: compute_asset_silhouette_2d(asset),
        mesh_hash: compute_asset_mesh_hash(asset),
        triangle_count,
    }
}

/// Inspect a `.glb`, `.gltf`, or `.obj` file on disk without modifying files.
pub fn inspect_3d_asset_file(path: &Path) -> Result<AssetInspection, String> {
    let asset = load_3d_asset(path)?;
    Ok(inspect_loaded_asset(&asset))
}

/// Load `.glb`/`.gltf`/`.obj` from `input_path`, write normalized `.glb` to `output_glb`, and return summary.
pub fn convert_3d_asset_to_glb(
    input_path: &Path,
    output_glb: &Path,
) -> Result<AssetInspection, String> {
    let asset = load_3d_asset(input_path)?;
    let name = input_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("custom_asset");
    let glb_bytes = export_loaded_asset_to_glb(&asset, name)?;
    if let Some(parent) = output_glb.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("Create dir {}: {e}", parent.display()))?;
    }
    std::fs::write(output_glb, glb_bytes)
        .map_err(|e| format!("Write {}: {e}", output_glb.display()))?;
    Ok(inspect_loaded_asset(&asset))
}

fn parse_obj_index(raw: &str, len: usize) -> Option<usize> {
    if raw.is_empty() {
        return None;
    }
    let idx: isize = raw.parse().ok()?;
    if idx > 0 {
        let z = (idx - 1) as usize;
        (z < len).then_some(z)
    } else if idx < 0 {
        let abs_i = idx.unsigned_abs();
        (abs_i <= len).then(|| len - abs_i)
    } else {
        None
    }
}

fn parse_obj_face_vertex(
    token: &str,
    pos_len: usize,
    uv_len: usize,
    norm_len: usize,
) -> (Option<usize>, Option<usize>, Option<usize>) {
    let mut parts = token.split('/');
    let pi = parts.next().and_then(|s| parse_obj_index(s, pos_len));
    let ti = parts.next().and_then(|s| parse_obj_index(s, uv_len));
    let ni = parts.next().and_then(|s| parse_obj_index(s, norm_len));
    (pi, ti, ni)
}

fn load_first_gltf_buffer(doc: &Value, base_dir: &Path) -> Result<Vec<u8>, String> {
    let Some(buffers) = doc.get("buffers").and_then(Value::as_array) else {
        return Ok(Vec::new());
    };
    let Some(first) = buffers.first() else {
        return Ok(Vec::new());
    };
    let Some(uri) = first.get("uri").and_then(Value::as_str) else {
        return Ok(Vec::new());
    };
    if let Some((_, b64_part)) = uri.split_once(";base64,") {
        if uri.starts_with("data:") {
            return decode_base64_bytes(b64_part);
        }
    }
    let rel = Path::new(uri);
    if rel.is_absolute()
        || rel
            .components()
            .any(|c| matches!(c, std::path::Component::ParentDir))
    {
        return Err(format!("Unsafe external glTF buffer URI '{uri}'"));
    }
    let buf_path = base_dir.join(rel);
    std::fs::read(&buf_path).map_err(|e| format!("Read buffer {}: {e}", buf_path.display()))
}

fn decode_base64_bytes(input: &str) -> Result<Vec<u8>, String> {
    let val_for = |b: u8| -> Option<u8> {
        match b {
            b'A'..=b'Z' => Some(b - b'A'),
            b'a'..=b'z' => Some(b - b'a' + 26),
            b'0'..=b'9' => Some(b - b'0' + 52),
            b'+' => Some(62),
            b'/' => Some(63),
            _ => None,
        }
    };
    let mut out: Vec<u8> = Vec::with_capacity((input.len() * 3) / 4);
    let mut buf: u32 = 0;
    let mut bits: u8 = 0;
    for b in input.bytes() {
        if b.is_ascii_whitespace() || b == b'=' {
            continue;
        }
        let v = val_for(b).ok_or_else(|| "Invalid base64 byte in glTF URI".to_string())?;
        buf = (buf << 6) | u32::from(v);
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push(((buf >> bits) & 0xFF) as u8);
        }
    }
    Ok(out)
}

fn normalize_asset_primitives(mut primitives: Vec<LoadedGlbPrimitive>) -> LoadedGlbAsset {
    let mut min_v = Vec3::splat(f32::INFINITY);
    let mut max_v = Vec3::splat(f32::NEG_INFINITY);
    for prim in &primitives {
        for v in &prim.vertices {
            let vp = Vec3::from_array(v.pos);
            min_v = min_v.min(vp);
            max_v = max_v.max(vp);
        }
    }
    if !min_v.is_finite() || !max_v.is_finite() {
        return LoadedGlbAsset {
            primitives,
            size_m: [0.05, 0.05, 0.05],
        };
    }
    let cx = 0.5 * (min_v.x + max_v.x);
    let cy = 0.5 * (min_v.y + max_v.y);
    let z0 = min_v.z;
    for prim in &mut primitives {
        for v in &mut prim.vertices {
            v.pos[0] -= cx;
            v.pos[1] -= cy;
            v.pos[2] -= z0;
        }
    }
    let ext = (max_v - min_v).max(Vec3::splat(0.05));
    LoadedGlbAsset {
        primitives,
        size_m: [ext.x, ext.y, ext.z],
    }
}

/// Parse binary `.glb` bytes into normalized Z-up primitives.
pub fn parse_glb_bytes(raw: &[u8]) -> Result<LoadedGlbAsset, String> {
    if raw.len() < 20 {
        return Err("GLB header truncated".to_string());
    }
    let magic = read_u32_le(raw, 0).ok_or("Missing GLB magic")?;
    let version = read_u32_le(raw, 4).ok_or("Missing GLB version")?;
    if magic != GLB_MAGIC || version != 2 {
        return Err(format!(
            "Unsupported GLB header magic={magic:#x} version={version}"
        ));
    }

    let mut pos = 12usize;
    let mut json_slice: Option<&[u8]> = None;
    let mut bin_slice: Option<&[u8]> = None;
    while pos + 8 <= raw.len() {
        let chunk_len = read_u32_le(raw, pos).ok_or("Bad chunk len")? as usize;
        let chunk_type = read_u32_le(raw, pos + 4).ok_or("Bad chunk type")?;
        let data_start = pos + 8;
        let data_end = data_start + chunk_len;
        if data_end > raw.len() {
            return Err("GLB chunk exceeds file length".to_string());
        }
        if chunk_type == CHUNK_JSON {
            json_slice = Some(&raw[data_start..data_end]);
        } else if chunk_type == CHUNK_BIN {
            bin_slice = Some(&raw[data_start..data_end]);
        }
        pos = data_end;
    }

    let doc: Value = serde_json::from_slice(json_slice.ok_or("Missing GLB JSON chunk")?)
        .map_err(|e| format!("Invalid GLB JSON: {e}"))?;
    let bin = bin_slice.unwrap_or(&[]);
    decode_gltf_doc(&doc, bin)
}

fn decode_gltf_doc(doc: &Value, bin: &[u8]) -> Result<LoadedGlbAsset, String> {
    let meshes = doc
        .get("meshes")
        .and_then(Value::as_array)
        .ok_or("GLB has no meshes")?;
    let mats = doc.get("materials").and_then(Value::as_array);

    let mut primitives = Vec::new();
    let mut min_v = Vec3::splat(f32::INFINITY);
    let mut max_v = Vec3::splat(f32::NEG_INFINITY);

    for mesh in meshes {
        let Some(prims) = mesh.get("primitives").and_then(Value::as_array) else {
            continue;
        };
        for prim in prims {
            let attrs = prim.get("attributes").and_then(Value::as_object);
            let Some(pos_idx) = attrs
                .and_then(|a| a.get("POSITION"))
                .and_then(Value::as_u64)
                .map(|v| v as usize)
            else {
                continue;
            };
            let Some((pos_bytes, count, pos_stride, 5126)) = accessor_slice(doc, bin, pos_idx)
            else {
                continue;
            };

            let norm_info = attrs
                .and_then(|a| a.get("NORMAL"))
                .and_then(Value::as_u64)
                .and_then(|i| accessor_slice(doc, bin, i as usize));
            let uv_info = attrs
                .and_then(|a| a.get("TEXCOORD_0"))
                .and_then(Value::as_u64)
                .and_then(|i| accessor_slice(doc, bin, i as usize));

            let mut verts = Vec::with_capacity(count);
            for i in 0..count {
                let po = i * pos_stride;
                let gx = read_f32_le(pos_bytes, po).unwrap_or(0.0);
                let gy = read_f32_le(pos_bytes, po + 4).unwrap_or(0.0);
                let gz = read_f32_le(pos_bytes, po + 8).unwrap_or(0.0);
                let zp = gltf_to_zup([gx, gy, gz]);
                let vp = Vec3::from_array(zp);
                min_v = min_v.min(vp);
                max_v = max_v.max(vp);

                let zn = if let Some((nb, n_cnt, ns, 5126)) = norm_info {
                    if i < n_cnt {
                        let no = i * ns;
                        gltf_to_zup([
                            read_f32_le(nb, no).unwrap_or(0.0),
                            read_f32_le(nb, no + 4).unwrap_or(1.0),
                            read_f32_le(nb, no + 8).unwrap_or(0.0),
                        ])
                    } else {
                        [0.0, 0.0, 1.0]
                    }
                } else {
                    [0.0, 0.0, 1.0]
                };

                let uv = if let Some((ub, u_cnt, us, 5126)) = uv_info {
                    if i < u_cnt {
                        let uo = i * us;
                        [
                            read_f32_le(ub, uo).unwrap_or(0.0),
                            read_f32_le(ub, uo + 4).unwrap_or(0.0),
                        ]
                    } else {
                        [zp[0], zp[1]]
                    }
                } else {
                    [zp[0], zp[1]]
                };

                verts.push(Vertex {
                    pos: zp,
                    normal: zn,
                    uv,
                });
            }

            let indices: Vec<u32> = if let Some(idx_acc) = prim
                .get("indices")
                .and_then(Value::as_u64)
                .map(|v| v as usize)
            {
                if let Some((ib, icnt, istride, comp)) = accessor_slice(doc, bin, idx_acc) {
                    let mut out_idx = Vec::with_capacity(icnt);
                    for k in 0..icnt {
                        let off = k * istride;
                        let val = match comp {
                            5125 => read_u32_le(ib, off).unwrap_or(0),
                            5123 => ib
                                .get(off..off + 2)
                                .and_then(|s| s.try_into().ok())
                                .map_or(0, |arr: [u8; 2]| u16::from_le_bytes(arr) as u32),
                            5121 => ib.get(off).copied().unwrap_or(0) as u32,
                            _ => 0,
                        };
                        out_idx.push(val);
                    }
                    out_idx
                } else {
                    (0..count as u32).collect()
                }
            } else {
                (0..count as u32).collect()
            };

            let material = extract_gltf_material(mats, prim);
            primitives.push(LoadedGlbPrimitive {
                material,
                vertices: verts,
                indices,
            });
        }
    }

    if primitives.is_empty() {
        return Err("GLB contained no valid mesh primitives".to_string());
    }

    Ok(normalize_asset_primitives(primitives))
}

fn extract_gltf_material(mats: Option<&Vec<Value>>, prim: &Value) -> MaterialDef {
    let mat_json = prim
        .get("material")
        .and_then(Value::as_u64)
        .and_then(|i| mats.and_then(|m| m.get(i as usize)));
    let Some(mj) = mat_json else {
        return MaterialDef {
            name: "AssetDefault".to_string(),
            base_color: [0.85, 0.85, 0.85, 1.0],
            roughness: 0.6,
            metallic: 0.0,
            style: MaterialStyle::Solid,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        };
    };
    let name = mj
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or("AssetMat")
        .to_string();
    let pbr = mj.get("pbrMetallicRoughness");
    let mut base_color = [0.85f32, 0.85, 0.85, 1.0];
    if let Some(arr) = pbr
        .and_then(|p| p.get("baseColorFactor"))
        .and_then(Value::as_array)
    {
        for (i, v) in arr.iter().take(4).enumerate() {
            if let Some(f) = v.as_f64() {
                base_color[i] = f as f32;
            }
        }
    }
    let roughness = pbr
        .and_then(|p| p.get("roughnessFactor"))
        .and_then(Value::as_f64)
        .unwrap_or(0.6) as f32;
    let metallic = pbr
        .and_then(|p| p.get("metallicFactor"))
        .and_then(Value::as_f64)
        .unwrap_or(0.0) as f32;
    let transparent =
        mj.get("alphaMode").and_then(Value::as_str) == Some("BLEND") || base_color[3] < 0.99;

    MaterialDef {
        name,
        base_color,
        roughness,
        metallic,
        style: if transparent {
            MaterialStyle::Glass
        } else {
            MaterialStyle::Solid
        },
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::SceneState;
    use crate::glb_export::export_scene_mesh_to_glb;
    use crate::mesher::build_scene_mesh;
    use crate::scene_ir::{FixtureIR, SceneIR, SunIR, SCENE_IR_SCHEMA_VERSION};

    #[test]
    fn glb_round_trip_loads_primitives() {
        let mut state = SceneState::new();
        let fx = FixtureIR {
            id: "fx_toilet".into(),
            level_id: "lvl_0".into(),
            symbol_type: "toilet".into(),
            category: "bathroom_fixture".into(),
            loc_m: [0.0, 0.0, 0.0],
            rot_z_rad: 0.0,
            width_m: 0.46,
            depth_m: 0.71,
            height_m: 0.74,
            has_countertop: false,
            countertop_overhang_m: 0.0,
            countertop_thickness_m: 0.038,
            countertop_material: "quartz".into(),
            has_backsplash: false,
            fill_color: None,
            countertop_color: None,
        };
        state
            .load_scene(SceneIR {
                schema_version: SCENE_IR_SCHEMA_VERSION,
                plan_center_in: [0.0, 0.0],
                sun: SunIR::default(),
                levels: vec![],
                walls: vec![],
                openings: vec![],
                rooms: vec![],
                roofs: vec![],
                footers: vec![],
                rim_bands: vec![],
                stairs: vec![],
                fixtures: vec![fx],
                custom_assets: vec![],
            })
            .unwrap();
        let built = build_scene_mesh(&state);
        let bytes = export_scene_mesh_to_glb(&built, &SunIR::default()).unwrap();
        let loaded = parse_glb_bytes(&bytes).expect("parse glb");
        assert!(!loaded.primitives.is_empty());
        assert!(loaded.size_m[0] > 0.2 && loaded.size_m[2] > 0.4);
    }

    #[test]
    fn missing_manifest_dir_returns_empty_library_without_panic() {
        let mut lib = AssetLibrary::load_from_dir(Path::new("/nonexistent/assets_dir")).unwrap();
        assert_eq!(lib.manifest_len(), 0);
        let fx = FixtureIR {
            id: "f1".into(),
            level_id: "l1".into(),
            symbol_type: "sofa".into(),
            category: "living".into(),
            loc_m: [0.0, 0.0, 0.0],
            rot_z_rad: 0.0,
            width_m: 2.0,
            depth_m: 0.9,
            height_m: 0.85,
            has_countertop: false,
            countertop_overhang_m: 0.0,
            countertop_thickness_m: 0.0,
            countertop_material: "".into(),
            has_backsplash: false,
            fill_color: None,
            countertop_color: None,
        };
        assert!(lib.instantiate_fixture_parts(&fx).is_none());
    }

    #[test]
    fn obj_import_silhouette_hash_and_glb_conversion() {
        let obj = b"v 0 0 0\nv 2 0 0\nv 2 1 1\nv 0 1 1\nf 1 2 3 4\n";
        let asset = load_obj_bytes(obj).expect("parse obj");
        assert_eq!(asset.primitives.len(), 1);
        assert!((asset.size_m[0] - 2.0).abs() < 1e-4);
        assert!((asset.size_m[1] - 1.0).abs() < 1e-4);
        assert!((asset.size_m[2] - 1.0).abs() < 1e-4);

        let info = inspect_loaded_asset(&asset);
        assert_eq!(info.triangle_count, 2);
        assert!(info.silhouette_2d_m.len() >= 3);
        assert_eq!(info.mesh_hash.len(), 16);
        assert_eq!(info.mesh_hash, inspect_loaded_asset(&asset).mesh_hash);

        let glb = export_loaded_asset_to_glb(&asset, "pergola").expect("export obj->glb");
        let reparsed = parse_glb_bytes(&glb).expect("reparse glb");
        assert_eq!(info.mesh_hash, compute_asset_mesh_hash(&reparsed));
    }
}
