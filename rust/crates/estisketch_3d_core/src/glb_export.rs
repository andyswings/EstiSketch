//! Spec-compliant glTF 2.0 binary (`.glb`) exporter for compiled EstiSketch meshes.
//!
//! Converts EstiSketch **Z-up** meters `(x, y, z)` to glTF **Y-up** meters
//! `(x, z, -y)` on vertices and normals, preserving right-handed triangle winding.

use std::collections::HashMap;
use std::fs::File;
use std::io::Write;
use std::path::Path;

use serde_json::{json, Value};

use crate::assets::LoadedGlbAsset;
use crate::mesh::{BuiltSceneMesh, MaterialKey, MeshPart};
use crate::scene_ir::SunIR;

const GLB_MAGIC: u32 = 0x4654_6C67; // "glTF"
const GLB_VERSION: u32 = 2;
const CHUNK_JSON: u32 = 0x4E4F_534A; // "JSON"
const CHUNK_BIN: u32 = 0x004E_4942; // "BIN\0"

fn to_gltf_vec3(v: [f32; 3]) -> [f32; 3] {
    [v[0], v[2], -v[1]]
}

/// Export a compiled [`BuiltSceneMesh`] and sun metadata into a glTF 2.0 `.glb` byte buffer.
pub fn export_scene_mesh_to_glb(mesh: &BuiltSceneMesh, sun: &SunIR) -> Result<Vec<u8>, String> {
    let mut bin: Vec<u8> = Vec::new();
    let mut buffer_views: Vec<Value> = Vec::new();
    let mut accessors: Vec<Value> = Vec::new();
    let mut materials_json: Vec<Value> = Vec::new();
    let mut mat_map: HashMap<MaterialKey, usize> = HashMap::new();
    let mut meshes_json: Vec<Value> = Vec::new();
    let mut nodes_json: Vec<Value> = Vec::new();
    let mut root_children: Vec<usize> = Vec::new();

    for part in &mesh.parts {
        if part.vertices.is_empty() || part.indices.is_empty() {
            continue;
        }

        let mat_key = part.material.quant_key();
        let mat_idx = if let Some(&idx) = mat_map.get(&mat_key) {
            idx
        } else {
            let idx = materials_json.len();
            mat_map.insert(mat_key, idx);
            let mut m = json!({
                "name": part.material.name,
                "pbrMetallicRoughness": {
                    "baseColorFactor": part.material.base_color,
                    "metallicFactor": part.material.metallic,
                    "roughnessFactor": part.material.roughness
                },
                "doubleSided": part.material.transparent
            });
            if part.material.transparent {
                m["alphaMode"] = json!("BLEND");
            }
            materials_json.push(m);
            idx
        };

        // Pack interleaved/separate tightly aligned attribute slices into BIN chunk
        let v_count = part.vertices.len();
        let pos_offset = bin.len();
        let mut p_min = [f32::INFINITY; 3];
        let mut p_max = [f32::NEG_INFINITY; 3];
        for v in &part.vertices {
            let gp = to_gltf_vec3(v.pos);
            for axis in 0..3 {
                p_min[axis] = p_min[axis].min(gp[axis]);
                p_max[axis] = p_max[axis].max(gp[axis]);
                bin.extend_from_slice(&gp[axis].to_le_bytes());
            }
        }
        let pos_len = bin.len() - pos_offset;

        let norm_offset = bin.len();
        for v in &part.vertices {
            let gn = to_gltf_vec3(v.normal);
            for val in gn {
                bin.extend_from_slice(&val.to_le_bytes());
            }
        }
        let norm_len = bin.len() - norm_offset;

        let uv_offset = bin.len();
        for v in &part.vertices {
            bin.extend_from_slice(&v.uv[0].to_le_bytes());
            bin.extend_from_slice(&v.uv[1].to_le_bytes());
        }
        let uv_len = bin.len() - uv_offset;

        let idx_offset = bin.len();
        for &idx in &part.indices {
            bin.extend_from_slice(&idx.to_le_bytes());
        }
        let idx_len = bin.len() - idx_offset;

        let bv_pos = buffer_views.len();
        buffer_views.push(json!({
            "buffer": 0, "byteOffset": pos_offset, "byteLength": pos_len, "target": 34962
        }));
        let bv_norm = buffer_views.len();
        buffer_views.push(json!({
            "buffer": 0, "byteOffset": norm_offset, "byteLength": norm_len, "target": 34962
        }));
        let bv_uv = buffer_views.len();
        buffer_views.push(json!({
            "buffer": 0, "byteOffset": uv_offset, "byteLength": uv_len, "target": 34962
        }));
        let bv_idx = buffer_views.len();
        buffer_views.push(json!({
            "buffer": 0, "byteOffset": idx_offset, "byteLength": idx_len, "target": 34963
        }));

        let acc_pos = accessors.len();
        accessors.push(json!({
            "bufferView": bv_pos,
            "componentType": 5126, // FLOAT
            "count": v_count,
            "type": "VEC3",
            "min": p_min,
            "max": p_max
        }));
        let acc_norm = accessors.len();
        accessors.push(json!({
            "bufferView": bv_norm,
            "componentType": 5126,
            "count": v_count,
            "type": "VEC3"
        }));
        let acc_uv = accessors.len();
        accessors.push(json!({
            "bufferView": bv_uv,
            "componentType": 5126,
            "count": v_count,
            "type": "VEC2"
        }));
        let acc_idx = accessors.len();
        accessors.push(json!({
            "bufferView": bv_idx,
            "componentType": 5125, // UNSIGNED_INT
            "count": part.indices.len(),
            "type": "SCALAR"
        }));

        let mesh_idx = meshes_json.len();
        meshes_json.push(json!({
            "name": format!("{}:{}", part.entity_id, part.sub_part),
            "primitives": [{
                "attributes": {
                    "POSITION": acc_pos,
                    "NORMAL": acc_norm,
                    "TEXCOORD_0": acc_uv
                },
                "indices": acc_idx,
                "material": mat_idx
            }]
        }));

        let node_idx = nodes_json.len();
        nodes_json.push(json!({
            "name": format!("{}_{}", part.entity_id, part.sub_part),
            "mesh": mesh_idx,
            "extras": {
                "estisketch_id": part.entity_id,
                "entity_kind": part.entity_kind,
                "level_id": part.level_id,
                "sub_part": part.sub_part
            }
        }));
        root_children.push(node_idx);
    }

    while !bin.len().is_multiple_of(4) {
        bin.push(0);
    }

    let doc = json!({
        "asset": {
            "version": "2.0",
            "generator": "EstiSketch estisketch_3d_core",
            "extras": {
                "north_angle_deg": sun.north_angle_deg,
                "sun_azimuth_deg": sun.azimuth_deg,
                "sun_elevation_deg": sun.elevation_deg
            }
        },
        "scene": 0,
        "scenes": [{
            "name": "EstiSketchScene",
            "nodes": root_children
        }],
        "nodes": nodes_json,
        "meshes": meshes_json,
        "materials": materials_json,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{ "byteLength": bin.len() }]
    });

    let mut json_bytes = serde_json::to_vec(&doc).map_err(|e| e.to_string())?;
    while !json_bytes.len().is_multiple_of(4) {
        json_bytes.push(b' ');
    }

    let total_len = 12 + 8 + json_bytes.len() + 8 + bin.len();
    let mut out = Vec::with_capacity(total_len);
    out.extend_from_slice(&GLB_MAGIC.to_le_bytes());
    out.extend_from_slice(&GLB_VERSION.to_le_bytes());
    out.extend_from_slice(&(total_len as u32).to_le_bytes());

    out.extend_from_slice(&(json_bytes.len() as u32).to_le_bytes());
    out.extend_from_slice(&CHUNK_JSON.to_le_bytes());
    out.extend_from_slice(&json_bytes);

    out.extend_from_slice(&(bin.len() as u32).to_le_bytes());
    out.extend_from_slice(&CHUNK_BIN.to_le_bytes());
    out.extend_from_slice(&bin);

    Ok(out)
}

/// Write a compiled scene mesh to `path` as a `.glb` binary and return bytes written.
pub fn write_glb_file(path: &Path, mesh: &BuiltSceneMesh, sun: &SunIR) -> Result<usize, String> {
    let bytes = export_scene_mesh_to_glb(mesh, sun)?;
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
    }
    let mut file = File::create(path).map_err(|e| e.to_string())?;
    file.write_all(&bytes).map_err(|e| e.to_string())?;
    Ok(bytes.len())
}

/// Serialize a decoded [`LoadedGlbAsset`] into normalized binary glTF 2.0 (`.glb`) bytes.
pub fn export_loaded_asset_to_glb(asset: &LoadedGlbAsset, name: &str) -> Result<Vec<u8>, String> {
    let entity_name = if name.trim().is_empty() {
        "custom_asset"
    } else {
        name.trim()
    };
    let mut parts: Vec<MeshPart> = Vec::with_capacity(asset.primitives.len());
    for (idx, prim) in asset.primitives.iter().enumerate() {
        if prim.vertices.is_empty() || prim.indices.is_empty() {
            continue;
        }
        let mut z_min = f32::INFINITY;
        let mut z_max = f32::NEG_INFINITY;
        for v in &prim.vertices {
            z_min = z_min.min(v.pos[2]);
            z_max = z_max.max(v.pos[2]);
        }
        parts.push(MeshPart {
            entity_id: entity_name.to_string(),
            entity_kind: "custom_asset".to_string(),
            level_id: String::new(),
            sub_part: format!("Primitive_{idx}"),
            is_roof_or_ceiling: false,
            is_wall: false,
            z_min_m: z_min,
            z_max_m: z_max,
            material: prim.material.clone(),
            vertices: prim.vertices.clone(),
            indices: prim.indices.clone(),
        });
    }
    let mut built = BuiltSceneMesh {
        parts,
        ..BuiltSceneMesh::default()
    };
    built.recompute_bounds();
    export_scene_mesh_to_glb(&built, &SunIR::default())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::materials::wall_finish_material;
    use crate::mesh::{MaterialStyle, MeshBuilder, PartFlags};
    use glam::Vec3;

    #[test]
    fn glb_header_and_json_chunk_valid() {
        let mut mb = MeshBuilder::new();
        mb.push_oriented_box(Vec3::new(0.0, 0.0, 0.5), 0.0, Vec3::ZERO, Vec3::ONE);
        let part = mb
            .into_part(
                "wall_1",
                "wall",
                "lvl_0",
                "LeftFace",
                PartFlags {
                    is_roof_or_ceiling: false,
                    is_wall: true,
                },
                wall_finish_material("Drywall", None),
            )
            .expect("box part");
        assert_ne!(part.material.style as u32, MaterialStyle::Glass as u32);
        let mut scene_mesh = BuiltSceneMesh {
            parts: vec![part],
            bounds_min: [0.0; 3],
            bounds_max: [0.0; 3],
            levels: vec![],
        };
        scene_mesh.recompute_bounds();
        let bytes = export_scene_mesh_to_glb(&scene_mesh, &SunIR::default()).expect("glb");
        assert!(bytes.len() > 20);
        let magic = u32::from_le_bytes(bytes[0..4].try_into().unwrap());
        let version = u32::from_le_bytes(bytes[4..8].try_into().unwrap());
        let declared_len = u32::from_le_bytes(bytes[8..12].try_into().unwrap()) as usize;
        assert_eq!(magic, GLB_MAGIC);
        assert_eq!(version, 2);
        assert_eq!(declared_len, bytes.len());

        let json_len = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let json_slice = &bytes[20..20 + json_len];
        let v: serde_json::Value = serde_json::from_slice(json_slice).expect("valid json");
        assert_eq!(v["asset"]["version"], "2.0");
        assert_eq!(v["nodes"][0]["extras"]["estisketch_id"], "wall_1");
    }
}
