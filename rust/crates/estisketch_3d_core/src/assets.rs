//! Pure-Rust binary glTF 2.0 (`.glb`) asset loader and cached [`AssetLibrary`].
//!
//! Parses bundled `CC0-1.0` architectural asset packs defined in `manifest.json`
//! and converts glTF Y-up meters `(x, y, z)` back to EstiSketch Z-up meters
//! `(x, -z, y)`, scaling cleanly to the placed fixture's `(width, depth, height)`.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use glam::Vec3;
use serde::Deserialize;
use serde_json::Value;

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
            let Some((pos_bytes, count, pos_stride, 5126)) = accessor_slice(&doc, bin, pos_idx)
            else {
                continue;
            };

            let norm_info = attrs
                .and_then(|a| a.get("NORMAL"))
                .and_then(Value::as_u64)
                .and_then(|i| accessor_slice(&doc, bin, i as usize));
            let uv_info = attrs
                .and_then(|a| a.get("TEXCOORD_0"))
                .and_then(Value::as_u64)
                .and_then(|i| accessor_slice(&doc, bin, i as usize));

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
                if let Some((ib, icnt, istride, comp)) = accessor_slice(&doc, bin, idx_acc) {
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

    // Recenter XY at 0 and ground bottom at z = 0
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
    Ok(LoadedGlbAsset {
        primitives,
        size_m: [ext.x, ext.y, ext.z],
    })
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
}
