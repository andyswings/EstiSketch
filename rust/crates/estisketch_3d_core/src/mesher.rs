//! Procedural 3D architectural mesh generator converting [`SceneState`] to [`BuiltSceneMesh`].

use std::collections::{BTreeMap, HashMap};

use glam::{Vec2, Vec3};

use crate::assets::AssetLibrary;
use crate::cabinets::{emit_cabinet_meshes, is_cabinet_like};
use crate::engine::SceneState;
use crate::fixtures::emit_procedural_fixture;
use crate::materials::{
    ceiling_material, concrete_material, floor_material, railing_material, roof_material,
    stair_tread_material, trim_material, wall_finish_material,
};
use crate::mesh::{BuiltSceneMesh, LevelBounds, MeshBuilder, MeshPart, PartFlags};
use crate::openings::emit_opening_meshes;
use crate::scene_ir::{
    FixtureIR, FooterIR, LevelIR, RimBandIR, RoofIR, RoomIR, StairIR, WallIR, WallSegmentIR,
};

/// Build all structural and architectural 3D meshes from a validated [`SceneState`].
pub fn build_scene_mesh(state: &SceneState) -> BuiltSceneMesh {
    build_scene_mesh_with_assets(state, None)
}

/// Build all structural and architectural 3D meshes, resolving curated/custom `.glb` assets via `assets`.
pub fn build_scene_mesh_with_assets(
    state: &SceneState,
    mut assets: Option<&mut AssetLibrary>,
) -> BuiltSceneMesh {
    let mut parts: Vec<MeshPart> = Vec::new();
    let level_by_id: HashMap<&str, &LevelIR> =
        state.levels.values().map(|l| (l.id.as_str(), l)).collect();

    let mut ext_finish_name = String::new();
    for wall in state.walls.values() {
        for seg in &wall.segments {
            if seg.exterior && !seg.right_finish.is_empty() {
                ext_finish_name = seg.right_finish.clone();
                break;
            }
        }
        if !ext_finish_name.is_empty() {
            break;
        }
    }
    if ext_finish_name.is_empty() {
        ext_finish_name = "Siding".to_string();
    }

    for wall in state.walls.values() {
        if !wall.visible {
            continue;
        }
        let z_base = level_by_id
            .get(wall.level_id.as_str())
            .map_or(0.0, |l| l.elevation_m as f32);
        emit_wall_meshes(wall, z_base, &mut parts);
    }

    for opening in state.openings.values() {
        if let Some(wall) = state.walls.get(&opening.host_wall_id) {
            if !wall.visible {
                continue;
            }
            if let Some(seg) = wall.segments.get(opening.host_seg_index) {
                let z_base = level_by_id
                    .get(wall.level_id.as_str())
                    .map_or(0.0, |l| l.elevation_m as f32);
                emit_opening_meshes(opening, wall, seg, z_base, &mut parts);
            }
        }
    }

    for room in state.rooms.values() {
        emit_room_meshes(room, &mut parts);
    }

    for roof in state.roofs.values() {
        emit_roof_meshes(roof, &ext_finish_name, &mut parts);
    }

    for footer in state.footers.values() {
        emit_footer_mesh(footer, &mut parts);
    }

    for rim in state.rim_bands.values() {
        emit_rim_band_mesh(rim, &ext_finish_name, &mut parts);
    }

    for stair in state.stairs.values() {
        emit_stair_meshes(stair, &mut parts);
    }

    // Separate `.glb` manifest assets from procedural fixtures; cabinets always participate in runs.
    let mut run_eligible_fixtures: Vec<&FixtureIR> = Vec::new();
    let mut non_cabinet_procedural: Vec<&FixtureIR> = Vec::new();
    for fx in state.fixtures.values() {
        if is_cabinet_like(&fx.symbol_type) {
            run_eligible_fixtures.push(fx);
            continue;
        }
        if let Some(lib) = assets.as_deref_mut() {
            if let Some(mut loaded_parts) = lib.instantiate_fixture_parts(fx) {
                parts.append(&mut loaded_parts);
                if fx.has_countertop {
                    run_eligible_fixtures.push(fx);
                }
                continue;
            }
        }
        if fx.has_countertop {
            run_eligible_fixtures.push(fx);
        }
        non_cabinet_procedural.push(fx);
    }

    emit_cabinet_meshes(&run_eligible_fixtures, &mut parts);
    for fx in non_cabinet_procedural {
        emit_procedural_fixture(fx, &mut parts);
    }

    // Custom `.glb` assets from Sketch / Blender sync (graceful beveled box fallback if missing)
    for item in state.custom_assets.values() {
        let loaded = match assets.as_deref() {
            Some(lib) => lib.instantiate_custom_asset(item),
            None => AssetLibrary::default().instantiate_custom_asset(item),
        };
        if let Ok(mut loaded_parts) = loaded {
            parts.append(&mut loaded_parts);
            continue;
        }
        let mut fallback = MeshBuilder::new();
        fallback.push_beveled_box(
            Vec3::new(
                item.loc_m[0] as f32,
                item.loc_m[1] as f32,
                item.loc_m[2] as f32 + 0.5,
            ),
            item.rot_z_rad as f32,
            Vec3::ZERO,
            Vec3::new(
                (item.scale[0] as f32).abs().max(0.2),
                (item.scale[1] as f32).abs().max(0.2),
                (item.scale[2] as f32).abs().max(0.2),
            ),
            0.02,
        );
        if let Some(p) = fallback.into_part(
            &item.id,
            "custom_asset",
            "",
            "Fallback",
            PartFlags::default(),
            concrete_material(),
        ) {
            parts.push(p);
        }
    }

    let mut levels: Vec<LevelBounds> = state
        .levels
        .values()
        .map(|l| LevelBounds {
            id: l.id.clone(),
            name: l.name.clone(),
            elevation_m: l.elevation_m as f32,
            top_z_m: (l.elevation_m + l.height_m) as f32,
        })
        .collect();
    levels.sort_by(|a, b| a.elevation_m.total_cmp(&b.elevation_m));

    let mut built = BuiltSceneMesh {
        parts,
        bounds_min: [0.0; 3],
        bounds_max: [0.0; 3],
        levels,
    };
    built.recompute_bounds();
    built
}

struct MiterProfile {
    s_l0: f32,
    s_l1: f32,
    s_r0: f32,
    s_r1: f32,
}

fn segment_miter_profile(seg: &WallSegmentIR, len: f32) -> MiterProfile {
    let t = seg.thickness_m as f32;
    let max_shear = 4.0 * t;
    // Matches `solve_hb5_miter_angles` convention: right_a / left_b > 0 extends the outer face.
    let shear_l = ((seg.left_angle_rad as f32).tan() * t).clamp(-max_shear, max_shear);
    let shear_r = ((seg.right_angle_rad as f32).tan() * t).clamp(-max_shear, max_shear);

    let mut u_r0 = shear_l;
    let mut u_r1 = len + shear_r;
    if u_r1 - u_r0 <= 1e-4 {
        u_r0 = 0.0;
        u_r1 = len;
    }
    MiterProfile {
        s_l0: 0.0,
        s_l1: len,
        s_r0: u_r0,
        s_r1: u_r1,
    }
}

fn emit_wall_meshes(wall: &WallIR, z_base: f32, parts: &mut Vec<MeshPart>) {
    let mut left_mb = MeshBuilder::new();
    let mut right_mb = MeshBuilder::new();
    let mut reveal_mb = MeshBuilder::new();
    let mut top_mb = MeshBuilder::new();
    let mut trim_mb = MeshBuilder::new();

    for seg in &wall.segments {
        let p0 = Vec2::new(seg.start_m[0] as f32, seg.start_m[1] as f32);
        let p1 = Vec2::new(seg.end_m[0] as f32, seg.end_m[1] as f32);
        let delta = p1 - p0;
        let len = delta.length();
        if len <= 1e-4 {
            continue;
        }
        let d = delta / len;
        let n = Vec2::new(-d.y, d.x);
        let thick = seg.thickness_m.max(0.02) as f32;
        let h0 = seg.height_start_m as f32;
        let h1 = seg.height_end_m as f32;
        let miter = segment_miter_profile(seg, len);

        let pt_left = |u: f32, z: f32| -> Vec3 {
            let ul = u.clamp(miter.s_l0, miter.s_l1);
            let xy = p0 + d * ul;
            Vec3::new(xy.x, xy.y, z_base + z)
        };
        let pt_right = |u: f32, z: f32| -> Vec3 {
            let r_min = miter.s_r0.min(miter.s_r1);
            let r_max = miter.s_r0.max(miter.s_r1);
            let ur = if u <= 1e-4 {
                miter.s_r0
            } else if u >= len - 1e-4 {
                miter.s_r1
            } else {
                u.clamp(r_min, r_max)
            };
            let xy = p0 + d * ur + n * thick;
            Vec3::new(xy.x, xy.y, z_base + z)
        };
        let wall_h_at = |u: f32| -> f32 {
            let f = (u / len).clamp(0.0, 1.0);
            (h0 + (h1 - h0) * f).max(0.05)
        };

        // Partition [0, len] along U at opening boundaries.
        let mut splits: Vec<f32> = vec![0.0, len];
        let mut valid_cuts: Vec<(f32, f32, f32, f32)> = Vec::new();
        for cut in &seg.opening_cuts {
            let x0 = (cut.x0_m as f32).clamp(0.0, len);
            let x1 = (cut.x1_m as f32).clamp(0.0, len);
            if x1 - x0 <= 1e-4 {
                continue;
            }
            let z0 = (cut.z0_m as f32).max(0.0);
            let z1 = (cut.z1_m as f32).min(wall_h_at(x0).min(wall_h_at(x1)) - 0.005);
            if z1 - z0 <= 0.05 {
                continue;
            }
            splits.push(x0);
            splits.push(x1);
            valid_cuts.push((x0, x1, z0, z1));
        }
        splits.sort_by(|a, b| a.total_cmp(b));
        splits.dedup_by(|a, b| (*a - *b).abs() <= 1e-4);

        for win in splits.windows(2) {
            let ua = win[0];
            let ub = win[1];
            if ub - ua <= 1e-4 {
                continue;
            }
            let u_mid = 0.5 * (ua + ub);
            let ha = wall_h_at(ua);
            let hb = wall_h_at(ub);

            let mut cut_intervals: Vec<(f32, f32)> = valid_cuts
                .iter()
                .filter(|(cx0, cx1, _, _)| u_mid > *cx0 && u_mid < *cx1)
                .map(|(_, _, cz0, cz1)| (*cz0, *cz1))
                .collect();
            cut_intervals.sort_by(|a, b| a.0.total_cmp(&b.0));

            // Merge overlapping cut vertical intervals
            let mut merged_cuts: Vec<(f32, f32)> = Vec::new();
            for (cz0, cz1) in cut_intervals {
                if let Some(last) = merged_cuts.last_mut() {
                    if cz0 <= last.1 + 1e-4 {
                        last.1 = last.1.max(cz1);
                        continue;
                    }
                }
                merged_cuts.push((cz0, cz1));
            }

            // Solid vertical bands from Z=0 to wall top
            let mut z_cursor = 0.0f32;
            let mut bands: Vec<(f32, f32, bool)> = Vec::new();
            for (cz0, cz1) in &merged_cuts {
                if *cz0 - z_cursor > 1e-4 {
                    bands.push((z_cursor, *cz0, false));
                }
                z_cursor = z_cursor.max(*cz1);
            }
            bands.push((z_cursor, 1.0, true)); // top band extends to sloped wall top

            for (bz0, bz1_const, is_top_band) in bands {
                let z_top_a = if is_top_band { ha } else { bz1_const };
                let z_top_b = if is_top_band { hb } else { bz1_const };
                if z_top_a - bz0 <= 1e-4 || z_top_b - bz0 <= 1e-4 {
                    continue;
                }

                // Left face (y = 0, outward normal -n): CCW looking from -n is (ua,z0)->(ub,z0)->(ub,z1)->(ua,z1)
                left_mb.push_quad(
                    pt_left(ua, bz0),
                    pt_left(ub, bz0),
                    pt_left(ub, z_top_b),
                    pt_left(ua, z_top_a),
                );
                // Right face (y = thick, outward normal +n): opposite winding
                right_mb.push_quad(
                    pt_right(ub, bz0),
                    pt_right(ua, bz0),
                    pt_right(ua, z_top_a),
                    pt_right(ub, z_top_b),
                );

                // Top / reveal bottom horizontal cap
                if is_top_band {
                    top_mb.push_quad(
                        pt_left(ua, z_top_a),
                        pt_left(ub, z_top_b),
                        pt_right(ub, z_top_b),
                        pt_right(ua, z_top_a),
                    );
                } else {
                    // Window sill reveal (top of solid band beneath a cut)
                    reveal_mb.push_quad(
                        pt_left(ua, z_top_a),
                        pt_left(ub, z_top_b),
                        pt_right(ub, z_top_b),
                        pt_right(ua, z_top_a),
                    );
                }

                // Bottom / header reveal
                if bz0 <= 1e-4 {
                    top_mb.push_quad(
                        pt_right(ua, bz0),
                        pt_right(ub, bz0),
                        pt_left(ub, bz0),
                        pt_left(ua, bz0),
                    );
                } else {
                    reveal_mb.push_quad(
                        pt_right(ua, bz0),
                        pt_right(ub, bz0),
                        pt_left(ub, bz0),
                        pt_left(ua, bz0),
                    );
                }
            }
        }

        // Start cap (u = 0) & End cap (u = len)
        top_mb.push_quad(
            pt_right(0.0, 0.0),
            pt_left(0.0, 0.0),
            pt_left(0.0, h0.max(0.05)),
            pt_right(0.0, h0.max(0.05)),
        );
        top_mb.push_quad(
            pt_left(len, 0.0),
            pt_right(len, 0.0),
            pt_right(len, h1.max(0.05)),
            pt_left(len, h1.max(0.05)),
        );

        // Vertical reveal jambs for each opening cut
        for &(x0, x1, z0, z1) in &valid_cuts {
            if x0 > 1e-4 {
                reveal_mb.push_quad(
                    pt_left(x0, z0),
                    pt_right(x0, z0),
                    pt_right(x0, z1),
                    pt_left(x0, z1),
                );
            }
            if x1 < len - 1e-4 {
                reveal_mb.push_quad(
                    pt_right(x1, z0),
                    pt_left(x1, z0),
                    pt_left(x1, z1),
                    pt_right(x1, z1),
                );
            }
        }

        // Continuous baseboards along left / right wall faces skipping floor-touching cuts
        emit_baseboards_for_segment(
            seg,
            &valid_cuts,
            &BaseboardFrame {
                p0,
                d,
                n,
                thick,
                z_base,
            },
            &mut trim_mb,
        );
    }

    let first_seg = wall.segments.first();
    let left_mat = first_seg
        .map(|s| wall_finish_material(&s.left_finish, s.left_color))
        .unwrap_or_else(|| wall_finish_material("Drywall", None));
    let right_mat = first_seg
        .map(|s| wall_finish_material(&s.right_finish, s.right_color))
        .unwrap_or_else(|| wall_finish_material("Drywall", None));

    if let Some(p) = left_mb.into_part(
        &wall.id,
        "wall",
        &wall.level_id,
        "LeftFace",
        PartFlags {
            is_roof_or_ceiling: false,
            is_wall: true,
        },
        left_mat.clone(),
    ) {
        parts.push(p);
    }
    if let Some(p) = right_mb.into_part(
        &wall.id,
        "wall",
        &wall.level_id,
        "RightFace",
        PartFlags {
            is_roof_or_ceiling: false,
            is_wall: true,
        },
        right_mat,
    ) {
        parts.push(p);
    }
    if let Some(p) = reveal_mb.into_part(
        &wall.id,
        "wall",
        &wall.level_id,
        "Reveal",
        PartFlags {
            is_roof_or_ceiling: false,
            is_wall: true,
        },
        left_mat,
    ) {
        parts.push(p);
    }
    if let Some(p) = top_mb.into_part(
        &wall.id,
        "wall",
        &wall.level_id,
        "TopEdge",
        PartFlags {
            is_roof_or_ceiling: false,
            is_wall: true,
        },
        wall_finish_material("Drywall", None),
    ) {
        parts.push(p);
    }
    if let Some(p) = trim_mb.into_part(
        &wall.id,
        "wall",
        &wall.level_id,
        "Baseboard",
        PartFlags {
            is_roof_or_ceiling: false,
            is_wall: false,
        },
        trim_material(),
    ) {
        parts.push(p);
    }
}

struct BaseboardFrame {
    p0: Vec2,
    d: Vec2,
    n: Vec2,
    thick: f32,
    z_base: f32,
}

fn emit_baseboards_for_segment(
    seg: &WallSegmentIR,
    cuts: &[(f32, f32, f32, f32)],
    frame: &BaseboardFrame,
    trim_mb: &mut MeshBuilder,
) {
    let BaseboardFrame {
        p0,
        d,
        n,
        thick,
        z_base,
    } = *frame;
    if !seg.left_baseboard && !seg.right_baseboard {
        return;
    }
    let len = p0.distance(Vec2::new(seg.end_m[0] as f32, seg.end_m[1] as f32));
    if len <= 0.04 {
        return;
    }
    let mut blocked: Vec<(f32, f32)> = cuts
        .iter()
        .filter(|(_, _, z0, _)| *z0 <= 0.10)
        .map(|(x0, x1, _, _)| (*x0, *x1))
        .collect();
    blocked.sort_by(|a, b| a.0.total_cmp(&b.0));

    let mut spans: Vec<(f32, f32)> = Vec::new();
    let mut cursor = 0.0f32;
    for (a, b) in blocked {
        if a - cursor > 0.03 {
            spans.push((cursor, a));
        }
        cursor = cursor.max(b);
    }
    if len - cursor > 0.03 {
        spans.push((cursor, len));
    }

    let bb_h = 0.115f32;
    let bb_t = 0.018f32;
    let bevel_h = 0.018f32;
    let rot_z = d.y.atan2(d.x);
    let max_m = 4.0 * bb_t;
    let miter = segment_miter_profile(seg, len);
    let shift_l = ((seg.left_angle_rad as f32).tan() * bb_t).clamp(-max_m, max_m);
    let shift_r = ((seg.right_angle_rad as f32).tan() * bb_t).clamp(-max_m, max_m);

    for (s0, s1) in spans {
        if seg.left_baseboard {
            let m0 = if s0 <= 1e-3 { s0 - shift_l } else { s0 };
            let m1 = if s1 >= len - 1e-3 { s1 - shift_r } else { s1 };
            let span_len = (m1 - m0).max(0.02);
            let uc = 0.5 * (m0 + m1);
            let center = p0 + d * uc - n * (bb_t * 0.5);
            trim_mb.push_oriented_box(
                Vec3::new(center.x, center.y, z_base + (bb_h - bevel_h) * 0.5),
                rot_z,
                Vec3::ZERO,
                Vec3::new(span_len, bb_t, bb_h - bevel_h),
            );
            trim_mb.push_oriented_box(
                Vec3::new(center.x, center.y, z_base + bb_h - bevel_h * 0.5),
                rot_z,
                Vec3::new(0.0, bb_t * 0.18, 0.0),
                Vec3::new(span_len, bb_t * 0.64, bevel_h),
            );
        }
        if seg.right_baseboard {
            let m0 = if s0 <= 1e-3 { miter.s_r0 + shift_l } else { s0 };
            let m1 = if s1 >= len - 1e-3 {
                miter.s_r1 + shift_r
            } else {
                s1
            };
            let span_len = (m1 - m0).max(0.02);
            let uc = 0.5 * (m0 + m1);
            let center = p0 + d * uc + n * (thick + bb_t * 0.5);
            trim_mb.push_oriented_box(
                Vec3::new(center.x, center.y, z_base + (bb_h - bevel_h) * 0.5),
                rot_z,
                Vec3::ZERO,
                Vec3::new(span_len, bb_t, bb_h - bevel_h),
            );
            trim_mb.push_oriented_box(
                Vec3::new(center.x, center.y, z_base + bb_h - bevel_h * 0.5),
                rot_z,
                Vec3::new(0.0, -bb_t * 0.18, 0.0),
                Vec3::new(span_len, bb_t * 0.64, bevel_h),
            );
        }
    }
}

fn emit_room_meshes(room: &RoomIR, parts: &mut Vec<MeshPart>) {
    if room.outer_m.len() < 3 {
        return;
    }
    let mut floor_mb = MeshBuilder::new();
    let z_top = room.z_top_m as f32;
    let thick = (room.thickness_m as f32).max(0.02);
    floor_mb.push_extruded_polygon(&room.outer_m, &room.floor_holes_m, z_top - thick, z_top);
    if let Some(p) = floor_mb.into_part(
        &room.id,
        "room",
        &room.level_id,
        "Floor",
        PartFlags {
            is_roof_or_ceiling: false,
            is_wall: false,
        },
        floor_material(
            &room.floor_pattern,
            room.pattern_rotation_deg,
            room.pattern_scale,
        ),
    ) {
        parts.push(p);
    }

    let z_ceil = room.ceiling_z_m as f32;
    if z_ceil > z_top + 0.1 {
        let mut ceil_mb = MeshBuilder::new();
        ceil_mb.push_extruded_polygon(&room.outer_m, &room.ceiling_holes_m, z_ceil, z_ceil + 0.05);
        if let Some(p) = ceil_mb.into_part(
            &room.id,
            "room",
            &room.level_id,
            "Ceiling",
            PartFlags {
                is_roof_or_ceiling: true,
                is_wall: false,
            },
            ceiling_material(),
        ) {
            parts.push(p);
        }
    }
}

fn emit_roof_meshes(roof: &RoofIR, ext_finish: &str, parts: &mut Vec<MeshPart>) {
    let mut roof_mb = MeshBuilder::new();
    let thick = (roof.thickness_m as f32).max(0.04);

    for facet in &roof.facets {
        if facet.vertices_m.len() < 3 {
            continue;
        }
        let top_pts: Vec<Vec3> = facet
            .vertices_m
            .iter()
            .map(|p| Vec3::new(p[0] as f32, p[1] as f32, p[2] as f32))
            .collect();
        // Deduplicate very close consecutive points
        let mut clean: Vec<Vec3> = Vec::with_capacity(top_pts.len());
        for pt in top_pts {
            if clean.last().is_none_or(|prev| prev.distance(pt) > 1e-4) {
                clean.push(pt);
            }
        }
        if clean.len() >= 2 && clean[0].distance(*clean.last().unwrap_or(&clean[0])) <= 1e-4 {
            clean.pop();
        }
        if clean.len() < 3 {
            continue;
        }

        // Compute average polygon normal to orient top face upward (+Z)
        let mut avg_n = Vec3::ZERO;
        let centroid = clean.iter().copied().sum::<Vec3>() / (clean.len() as f32);
        for i in 0..clean.len() {
            let a = clean[i] - centroid;
            let b = clean[(i + 1) % clean.len()] - centroid;
            avg_n += a.cross(b);
        }
        if avg_n.z < 0.0 {
            clean.reverse();
        }
        // `clean` sits on the bearing plate / soffit plane; extrude roof deck upward matching HB5.
        let top: Vec<Vec3> = clean
            .iter()
            .map(|p| Vec3::new(p.x, p.y, p.z + thick))
            .collect();

        // Project onto horizontal plane for clean earcutr triangulation of polygon facet
        let xy_pts: Vec<[f64; 2]> = clean.iter().map(|p| [p.x as f64, p.y as f64]).collect();
        let coords: Vec<f64> = xy_pts.iter().flat_map(|p| [p[0], p[1]]).collect();
        let tris = earcutr::earcut(&coords, &[], 2).unwrap_or_default();
        if !tris.is_empty() {
            for &[i0, i1, i2] in tris.as_chunks::<3>().0 {
                let ta = top[i0];
                let tb = top[i1];
                let tc = top[i2];
                roof_mb.push_tri(ta, tb, tc, [[ta.x, ta.y], [tb.x, tb.y], [tc.x, tc.y]]);
                let ba = clean[i0];
                let bb = clean[i1];
                let bc = clean[i2];
                roof_mb.push_tri(ba, bc, bb, [[ba.x, ba.y], [bc.x, bc.y], [bb.x, bb.y]]);
            }
        } else {
            for i in 1..(clean.len() - 1) {
                let ta = top[0];
                let tb = top[i];
                let tc = top[i + 1];
                roof_mb.push_tri(ta, tb, tc, [[ta.x, ta.y], [tb.x, tb.y], [tc.x, tc.y]]);
                let ba = clean[0];
                let bb = clean[i];
                let bc = clean[i + 1];
                roof_mb.push_tri(ba, bc, bb, [[ba.x, ba.y], [bc.x, bc.y], [bb.x, bb.y]]);
            }
        }

        // Fascia perimeter quads
        for i in 0..clean.len() {
            let j = (i + 1) % clean.len();
            roof_mb.push_quad(clean[i], clean[j], top[j], top[i]);
        }
    }

    if let Some(p) = roof_mb.into_part(
        &roof.id,
        "roof",
        &roof.level_id,
        "RoofDeck",
        PartFlags {
            is_roof_or_ceiling: true,
            is_wall: false,
        },
        roof_material(&roof.material),
    ) {
        parts.push(p);
    }

    // Gable wall infills (stay visible when roofs are hidden since they belong to exterior walls)
    let mut gables_by_finish: BTreeMap<String, MeshBuilder> = BTreeMap::new();
    for g in &roof.gable_infills {
        let a = Vec2::new(g.p_start_m[0] as f32, g.p_start_m[1] as f32);
        let b = Vec2::new(g.p_end_m[0] as f32, g.p_end_m[1] as f32);
        let pk = Vec2::new(g.p_peak_m[0] as f32, g.p_peak_m[1] as f32);
        let dir = b - a;
        let len = dir.length();
        if len <= 1e-4 {
            continue;
        }
        let u = dir / len;
        let n = Vec2::new(-u.y, u.x);
        let t = (g.thickness_m as f32).max(0.02);
        let zb = g.z_base_m as f32;
        let zp = g.z_peak_m as f32;
        if zp <= zb + 0.02 {
            continue;
        }

        let finish = if g.finish.is_empty() {
            ext_finish.to_string()
        } else {
            g.finish.clone()
        };
        let mb = gables_by_finish.entry(finish).or_default();

        let l0 = Vec3::new(a.x, a.y, zb);
        let l1 = Vec3::new(b.x, b.y, zb);
        let lp = Vec3::new(pk.x, pk.y, zp);
        let r0 = Vec3::new(a.x + n.x * t, a.y + n.y * t, zb);
        let r1 = Vec3::new(b.x + n.x * t, b.y + n.y * t, zb);
        let rp = Vec3::new(pk.x + n.x * t, pk.y + n.y * t, zp);

        mb.push_tri(l0, l1, lp, [[0.0, 0.0], [len, 0.0], [len * 0.5, zp - zb]]);
        mb.push_tri(r1, r0, rp, [[len, 0.0], [0.0, 0.0], [len * 0.5, zp - zb]]);
        mb.push_quad(r0, l0, lp, rp);
        mb.push_quad(l1, r1, rp, lp);
        mb.push_quad(r0, r1, l1, l0);
    }

    for (finish, mb) in gables_by_finish {
        if let Some(p) = mb.into_part(
            &roof.id,
            "roof",
            &roof.level_id,
            "GableInfill",
            PartFlags {
                is_roof_or_ceiling: false,
                is_wall: true,
            },
            wall_finish_material(&finish, None),
        ) {
            parts.push(p);
        }
    }
}

fn emit_footer_mesh(footer: &FooterIR, parts: &mut Vec<MeshPart>) {
    let mut mb = MeshBuilder::new();
    let z_top = footer.z_top_m as f32;
    let z_bot = z_top - (footer.depth_m as f32).max(0.05);
    mb.push_extruded_polygon(&footer.footprint_m, &[], z_bot, z_top);
    if let Some(p) = mb.into_part(
        &footer.id,
        "footer",
        &footer.level_id,
        "Footer",
        PartFlags {
            is_roof_or_ceiling: false,
            is_wall: false,
        },
        concrete_material(),
    ) {
        parts.push(p);
    }
}

fn emit_rim_band_mesh(rim: &RimBandIR, ext_finish: &str, parts: &mut Vec<MeshPart>) {
    let mut mb = MeshBuilder::new();
    let z_bot = rim.z_bottom_m as f32;
    let z_top = z_bot + (rim.height_m as f32).max(0.02);
    mb.push_extruded_polygon(&rim.footprint_m, &[], z_bot, z_top);
    if let Some(p) = mb.into_part(
        &rim.id,
        "rim_band",
        &rim.level_id,
        "RimBand",
        PartFlags {
            is_roof_or_ceiling: false,
            is_wall: true,
        },
        wall_finish_material(ext_finish, None),
    ) {
        parts.push(p);
    }
}

fn emit_stair_meshes(stair: &StairIR, parts: &mut Vec<MeshPart>) {
    let mut tread_mb = MeshBuilder::new();
    let mut rail_mb = MeshBuilder::new();

    let w = (stair.width_m as f32).max(0.30);
    let rise = (stair.total_rise_m as f32).max(0.15);
    let n_steps = stair.num_steps.max(1) as usize;
    let riser_h = rise / (n_steps as f32);
    let tread_d = (stair.tread_depth_m as f32).max(0.18);
    let total_run = (stair.total_run_m as f32).max(tread_d);

    // Local stair coords match HB5 transform where origin is bottom-left corner `(loc_m, rot_z_rad)`,
    // flight advances along local +Y (`x in [0..w]`) after -PI/2 offset in SceneIR.
    let loc = Vec3::new(
        stair.loc_m[0] as f32,
        stair.loc_m[1] as f32,
        stair.loc_m[2] as f32,
    );
    let rot_z = stair.rot_z_rad as f32;

    let emit_flight =
        |mb: &mut MeshBuilder, f_orig: Vec3, f_rot: f32, steps: usize, z_start: f32, td: f32| {
            for s in 0..steps {
                let z_top = z_start + ((s + 1) as f32) * riser_h;
                let z_bot = (z_top - riser_h - 0.04).max(z_start);
                let yc = (s as f32 + 0.5) * td;
                mb.push_oriented_box(
                    f_orig,
                    f_rot,
                    Vec3::new(w * 0.5, yc, 0.5 * (z_top + z_bot)),
                    Vec3::new(w, td + 0.015, z_top - z_bot),
                );
            }
        };

    if stair.stair_type == "l-shaped" {
        let winders = stair
            .winder_count
            .clamp(0, 5)
            .min(n_steps.saturating_sub(2) as i32);
        let flight_total = (n_steps as i32 - winders).max(1) as usize;
        let sb = if stair.steps_before_landing > 0
            && (stair.steps_before_landing as usize) < flight_total
        {
            stair.steps_before_landing as usize
        } else {
            flight_total / 2
        };
        let sa = flight_total.saturating_sub(sb);
        let sb_treads = sb.saturating_sub(1);
        let rb = (sb_treads as f32) * tread_d;
        let ra = (sa.saturating_sub(1) as f32) * tread_d;
        let ld = (stair.landing_depth_m as f32).max(w);

        emit_flight(&mut tread_mb, loc, rot_z, sb_treads, 0.0, tread_d);
        let z_land = (sb as f32) * riser_h;
        tread_mb.push_oriented_box(
            loc,
            rot_z,
            Vec3::new(w * 0.5, rb + ld * 0.5, z_land - 0.08),
            Vec3::new(w, ld, 0.16),
        );

        let (sr, cr) = rot_z.sin_cos();
        let to_world = |lx: f32, ly: f32, lz: f32| -> Vec3 {
            loc + Vec3::new(lx * cr - ly * sr, lx * sr + ly * cr, lz)
        };
        let z_after = z_land + (winders as f32) * riser_h;
        let td2 = if sa > 1 && ra > 0.0 {
            ra / (sa as f32)
        } else {
            tread_d
        };
        if stair.turn_direction == "left" {
            let orig2 = to_world(0.0, rb + ld - w, z_after);
            emit_flight(
                &mut tread_mb,
                orig2,
                rot_z + std::f32::consts::FRAC_PI_2,
                sa,
                0.0,
                td2,
            );
        } else {
            let orig2 = to_world(w, rb + ld, z_after);
            emit_flight(
                &mut tread_mb,
                orig2,
                rot_z - std::f32::consts::FRAC_PI_2,
                sa,
                0.0,
                td2,
            );
        }
    } else if stair.stair_type == "u-shaped" {
        let sb =
            if stair.steps_before_landing > 0 && (stair.steps_before_landing as usize) < n_steps {
                stair.steps_before_landing as usize
            } else {
                n_steps / 2
            };
        let sa = n_steps.saturating_sub(sb);
        let sb_treads = sb.saturating_sub(1);
        let rb = (sb_treads as f32) * tread_d;
        let ra = (sa.saturating_sub(1) as f32) * tread_d;
        let ld = if stair.landing_depth_m > 0.0 {
            stair.landing_depth_m as f32
        } else {
            w
        };
        let ir = stair.inner_radius_m as f32;
        let well = if (ir - 0.1524).abs() < 1e-3 {
            0.0
        } else {
            ir.max(0.0)
        };
        let z_land = (sb as f32) * riser_h;

        emit_flight(&mut tread_mb, loc, rot_z, sb_treads, 0.0, tread_d);
        let (sr, cr) = rot_z.sin_cos();
        let to_world = |lx: f32, ly: f32, lz: f32| -> Vec3 {
            loc + Vec3::new(lx * cr - ly * sr, lx * sr + ly * cr, lz)
        };
        // Local +X is right of Flight 1; left turns advance into negative local X by (-well - w).
        let land_w = w * 2.0 + well;
        let lx_mid = if stair.turn_direction == "left" {
            -0.5 * well
        } else {
            w + 0.5 * well
        };
        tread_mb.push_oriented_box(
            loc,
            rot_z,
            Vec3::new(lx_mid, rb + ld * 0.5, z_land - 0.08),
            Vec3::new(land_w, ld, 0.16),
        );
        let orig2 = if stair.turn_direction == "left" {
            to_world(-well, rb, z_land)
        } else {
            to_world(w * 2.0 + well, rb, z_land)
        };
        let td2 = if sa > 1 && ra > 0.0 {
            ra / (sa as f32)
        } else {
            tread_d
        };
        emit_flight(
            &mut tread_mb,
            orig2,
            rot_z + std::f32::consts::PI,
            sa,
            0.0,
            td2,
        );
    } else if stair.stair_type == "spiral" {
        let inner_r = (stair.inner_radius_m as f32).max(0.08);
        let outer_r = inner_r + w;
        let center = Vec3::new(
            stair.loc_m[0] as f32,
            stair.loc_m[1] as f32,
            stair.loc_m[2] as f32,
        );
        let total_ang = stair.rotation_degrees.to_radians() as f32;
        let dir = if stair.turn_direction == "left" {
            -1.0
        } else {
            1.0
        };
        let base_ang = stair.rot_z_rad as f32 + std::f32::consts::FRAC_PI_2;
        for s in 0..n_steps {
            let f0 = (s as f32) / (n_steps as f32);
            let f1 = ((s + 1) as f32) / (n_steps as f32);
            let a0 = base_ang + f0 * total_ang * dir;
            let a1 = base_ang + f1 * total_ang * dir;
            let z_top = (s as f32 + 1.0) * riser_h;
            let p0 = [
                (center.x + inner_r * a0.cos()) as f64,
                (center.y + inner_r * a0.sin()) as f64,
            ];
            let p1 = [
                (center.x + outer_r * a0.cos()) as f64,
                (center.y + outer_r * a0.sin()) as f64,
            ];
            let p2 = [
                (center.x + outer_r * a1.cos()) as f64,
                (center.y + outer_r * a1.sin()) as f64,
            ];
            let p3 = [
                (center.x + inner_r * a1.cos()) as f64,
                (center.y + inner_r * a1.sin()) as f64,
            ];
            tread_mb.push_extruded_polygon(
                &[p0, p1, p2, p3],
                &[],
                center.z + z_top - 0.05,
                center.z + z_top,
            );
        }
    } else {
        let td = (total_run / (n_steps as f32)).max(0.18);
        emit_flight(&mut tread_mb, loc, rot_z, n_steps, 0.0, td);
    }

    // 3D handrails & vertical balusters along solved railing paths
    let rail_h = (stair.rail_height_m as f32).max(0.75);
    for path in &stair.railing_paths_m {
        if path.len() < 2 {
            continue;
        }
        for win in path.windows(2) {
            let a = Vec3::new(win[0][0] as f32, win[0][1] as f32, win[0][2] as f32);
            let b = Vec3::new(win[1][0] as f32, win[1][1] as f32, win[1][2] as f32);
            let span = b - a;
            let hlen = Vec2::new(span.x, span.y).length();
            if hlen <= 1e-4 {
                continue;
            }
            let hr = span.y.atan2(span.x);
            // Balusters spaced ~0.30 m + sloped handrail bar
            let posts = ((hlen / 0.30).ceil() as usize).max(1);
            for pi in 0..=posts {
                let t = (pi as f32) / (posts as f32);
                let p = a.lerp(b, t);
                rail_mb.push_oriented_box(
                    Vec3::new(p.x, p.y, p.z + rail_h * 0.5),
                    hr,
                    Vec3::ZERO,
                    Vec3::new(0.032, 0.032, rail_h),
                );
            }
            let mid = 0.5 * (a + b) + Vec3::new(0.0, 0.0, rail_h);
            let seg_len = span.length();
            let dir = span.normalize();
            let side = Vec3::new(-dir.y, dir.x, 0.0).normalize_or_zero();
            let up = side.cross(dir).normalize_or_zero();
            let hw = 0.025f32;
            let hh = 0.025f32;
            let half = dir * (seg_len * 0.5);
            let a0 = mid - half - side * hw - up * hh;
            let a1 = mid - half + side * hw - up * hh;
            let a2 = mid - half + side * hw + up * hh;
            let a3 = mid - half - side * hw + up * hh;
            let b0 = mid + half - side * hw - up * hh;
            let b1 = mid + half + side * hw - up * hh;
            let b2 = mid + half + side * hw + up * hh;
            let b3 = mid + half - side * hw + up * hh;
            rail_mb.push_quad(a0, a1, b1, b0);
            rail_mb.push_quad(a3, b3, b2, a2);
            rail_mb.push_quad(a0, b0, b3, a3);
            rail_mb.push_quad(a1, a2, b2, b1);
        }
    }

    if let Some(p) = tread_mb.into_part(
        &stair.id,
        "stair",
        &stair.level_id,
        "Treads",
        PartFlags {
            is_roof_or_ceiling: false,
            is_wall: false,
        },
        stair_tread_material(),
    ) {
        parts.push(p);
    }
    if let Some(p) = rail_mb.into_part(
        &stair.id,
        "stair",
        &stair.level_id,
        "Railings",
        PartFlags {
            is_roof_or_ceiling: false,
            is_wall: false,
        },
        railing_material(),
    ) {
        parts.push(p);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scene_ir::{
        GableInfillIR, LevelIR, OpeningCutIR, OpeningIR, RoofFacetIR, SceneIR, SunIR,
        SCENE_IR_SCHEMA_VERSION,
    };

    fn rich_scene() -> SceneIR {
        SceneIR {
            schema_version: SCENE_IR_SCHEMA_VERSION,
            plan_center_in: [120.0, 120.0],
            sun: SunIR::default(),
            levels: vec![LevelIR {
                id: "lvl_1".into(),
                name: "Level 1".into(),
                elevation_m: 0.0,
                height_m: 2.4384,
                floor_thickness_m: 0.254,
            }],
            walls: vec![WallIR {
                id: "w_south".into(),
                level_id: "lvl_1".into(),
                layer_id: "layer_0".into(),
                visible: true,
                locked: false,
                segments: vec![WallSegmentIR {
                    seg_index: 0,
                    start_m: [-3.0, -2.0],
                    end_m: [3.0, -2.0],
                    thickness_m: 0.14,
                    height_start_m: 2.4384,
                    height_end_m: 3.2,
                    left_angle_rad: std::f64::consts::FRAC_PI_4,
                    right_angle_rad: std::f64::consts::FRAC_PI_4,
                    exterior: true,
                    left_finish: "Drywall".into(),
                    right_finish: "Hardie Lap Siding".into(),
                    left_color: None,
                    right_color: None,
                    left_baseboard: true,
                    right_baseboard: false,
                    opening_cuts: vec![
                        OpeningCutIR {
                            opening_id: "door_1".into(),
                            x0_m: 1.0,
                            x1_m: 1.9144,
                            z0_m: 0.0,
                            z1_m: 2.032,
                        },
                        OpeningCutIR {
                            opening_id: "win_1".into(),
                            x0_m: 3.5,
                            x1_m: 4.5,
                            z0_m: 0.9,
                            z1_m: 2.0,
                        },
                    ],
                }],
                custom_3d_override: None,
            }],
            openings: vec![
                OpeningIR {
                    id: "door_1".into(),
                    kind: "door".into(),
                    host_wall_id: "w_south".into(),
                    host_seg_index: 0,
                    x_local_m: 1.0,
                    z_local_m: 0.0,
                    width_m: 0.9144,
                    depth_m: 0.14,
                    height_m: 2.032,
                    style: "entry_lite_half".into(),
                    swing: "left".into(),
                    orientation: "inswing".into(),
                },
                OpeningIR {
                    id: "win_1".into(),
                    kind: "window".into(),
                    host_wall_id: "w_south".into(),
                    host_seg_index: 0,
                    x_local_m: 3.5,
                    z_local_m: 0.9,
                    width_m: 1.0,
                    depth_m: 0.14,
                    height_m: 1.1,
                    style: "sliding".into(),
                    swing: "".into(),
                    orientation: "".into(),
                },
            ],
            rooms: vec![RoomIR {
                id: "room_1".into(),
                level_id: "lvl_1".into(),
                name: "Living".into(),
                outer_m: vec![[-3.0, -2.0], [3.0, -2.0], [3.0, 2.0], [-3.0, 2.0]],
                floor_holes_m: vec![vec![[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]],
                ceiling_holes_m: vec![],
                z_top_m: 0.0,
                thickness_m: 0.254,
                ceiling_z_m: 2.4384,
                floor_pattern: "wood_plank".into(),
                pattern_rotation_deg: 0.0,
                pattern_scale: 1.0,
            }],
            roofs: vec![RoofIR {
                id: "roof_1".into(),
                level_id: "lvl_1".into(),
                material: "asphalt_shingle".into(),
                thickness_m: 0.20,
                facets: vec![RoofFacetIR {
                    vertices_m: vec![
                        [-3.3, -2.3, 2.4384],
                        [3.3, -2.3, 2.4384],
                        [3.3, 0.0, 3.6],
                        [-3.3, 0.0, 3.6],
                    ],
                    pitch_rise: 6.0,
                }],
                gable_infills: vec![GableInfillIR {
                    p_start_m: [-3.0, -2.0],
                    p_end_m: [-3.0, 2.0],
                    p_peak_m: [-3.0, 0.0],
                    z_base_m: 2.4384,
                    z_peak_m: 3.6,
                    thickness_m: 0.14,
                    finish: "Siding".into(),
                }],
            }],
            footers: vec![FooterIR {
                id: "footer_1".into(),
                level_id: "lvl_1".into(),
                footprint_m: vec![[-3.2, -2.2], [3.2, -2.2], [3.2, -1.8], [-3.2, -1.8]],
                z_top_m: 0.0,
                depth_m: 0.20,
            }],
            rim_bands: vec![RimBandIR {
                id: "rim_1".into(),
                level_id: "lvl_1".into(),
                footprint_m: vec![[-3.0, -2.0], [3.0, -2.0], [3.0, -1.86], [-3.0, -1.86]],
                z_bottom_m: -0.25,
                height_m: 0.25,
            }],
            stairs: vec![StairIR {
                id: "stair_1".into(),
                level_id: "lvl_1".into(),
                stair_type: "straight".into(),
                loc_m: [0.0, 0.0, 0.0],
                rot_z_rad: 0.0,
                width_m: 0.9144,
                total_rise_m: 2.69,
                num_steps: 14,
                tread_depth_m: 0.2794,
                total_run_m: 3.63,
                turn_direction: "left".into(),
                landing_depth_m: 0.9144,
                steps_before_landing: 7,
                winder_count: 0,
                inner_radius_m: 0.15,
                rotation_degrees: 270.0,
                has_left_rail: true,
                has_right_rail: false,
                rail_height_m: 0.9144,
                railing_paths_m: vec![vec![[0.0, 0.0, 0.0], [0.0, 3.63, 2.69]]],
            }],
            fixtures: vec![crate::scene_ir::FixtureIR {
                id: "cab_1".into(),
                level_id: "lvl_1".into(),
                symbol_type: "base_cabinet".into(),
                category: "kitchen".into(),
                loc_m: [-2.0, 1.0, 0.0],
                rot_z_rad: 0.0,
                width_m: 0.76,
                depth_m: 0.61,
                height_m: 0.876,
                has_countertop: true,
                countertop_overhang_m: 0.038,
                countertop_thickness_m: 0.038,
                countertop_material: "quartz".into(),
                has_backsplash: true,
                fill_color: None,
                countertop_color: None,
            }],
            custom_assets: vec![],
        }
    }

    #[test]
    fn builds_structural_and_architectural_meshes() {
        let mut state = SceneState::new();
        state.load_scene(rich_scene()).expect("valid scene");
        let built = build_scene_mesh(&state);
        let stats = built.stats();
        assert!(stats.part_count >= 12);
        assert!(stats.vertex_count > 100);
        assert!(stats.triangle_count > 80);
        for p in &built.parts {
            assert_eq!(p.indices.len() % 3, 0);
            for &idx in &p.indices {
                assert!((idx as usize) < p.vertices.len());
            }
        }
        assert!(built
            .parts
            .iter()
            .any(|p| p.entity_kind == "wall" && p.sub_part == "Reveal"));
        assert!(built
            .parts
            .iter()
            .any(|p| p.entity_kind == "wall" && p.sub_part == "Baseboard"));
        assert!(built
            .parts
            .iter()
            .any(|p| p.entity_kind == "opening" && p.material.transparent));
        assert!(built
            .parts
            .iter()
            .any(|p| p.entity_kind == "roof" && p.sub_part == "GableInfill"));
    }

    #[test]
    fn wall_outside_corner_miters_to_exact_point() {
        let mut scene = rich_scene();
        scene.rooms.clear();
        scene.roofs.clear();
        scene.footers.clear();
        scene.rim_bands.clear();
        scene.stairs.clear();
        scene.fixtures.clear();
        scene.openings.clear();
        scene.walls = vec![
            WallIR {
                id: "w_a".into(),
                level_id: "lvl_1".into(),
                layer_id: "layer_0".into(),
                visible: true,
                locked: false,
                segments: vec![WallSegmentIR {
                    seg_index: 0,
                    start_m: [-3.0, 0.0],
                    end_m: [0.0, 0.0],
                    thickness_m: 0.15,
                    height_start_m: 2.4,
                    height_end_m: 2.4,
                    left_angle_rad: 0.0,
                    right_angle_rad: std::f64::consts::FRAC_PI_4,
                    exterior: true,
                    left_finish: "Drywall".into(),
                    right_finish: "Siding".into(),
                    left_color: None,
                    right_color: None,
                    left_baseboard: false,
                    right_baseboard: false,
                    opening_cuts: vec![],
                }],
                custom_3d_override: None,
            },
            WallIR {
                id: "w_b".into(),
                level_id: "lvl_1".into(),
                layer_id: "layer_0".into(),
                visible: true,
                locked: false,
                segments: vec![WallSegmentIR {
                    seg_index: 0,
                    start_m: [0.0, 0.0],
                    end_m: [0.0, -3.0],
                    thickness_m: 0.15,
                    height_start_m: 2.4,
                    height_end_m: 2.4,
                    left_angle_rad: -std::f64::consts::FRAC_PI_4,
                    right_angle_rad: 0.0,
                    exterior: true,
                    left_finish: "Drywall".into(),
                    right_finish: "Siding".into(),
                    left_color: None,
                    right_color: None,
                    left_baseboard: false,
                    right_baseboard: false,
                    opening_cuts: vec![],
                }],
                custom_3d_override: None,
            },
        ];

        let mut state = SceneState::new();
        state.load_scene(scene).unwrap();
        let built = build_scene_mesh(&state);

        let has_outer_corner = |wall_id: &str| {
            built.parts.iter().any(|p| {
                p.entity_id == wall_id
                    && p.sub_part == "RightFace"
                    && p.vertices
                        .iter()
                        .any(|v| (v.pos[0] - 0.15).abs() < 1e-4 && (v.pos[1] - 0.15).abs() < 1e-4)
            })
        };
        assert!(
            has_outer_corner("w_a"),
            "Wall A outer face missed miter point (0.15, 0.15)"
        );
        assert!(
            has_outer_corner("w_b"),
            "Wall B outer face missed miter point (0.15, 0.15)"
        );
    }

    #[test]
    fn roof_deck_extrudes_upward_above_eave_plate() {
        let mut state = SceneState::new();
        state.load_scene(rich_scene()).unwrap();
        let built = build_scene_mesh(&state);
        let roof_part = built
            .parts
            .iter()
            .find(|p| p.entity_kind == "roof" && p.sub_part == "RoofDeck")
            .expect("roof deck");
        assert!((roof_part.z_min_m - 2.4384).abs() < 1e-3);
        assert!(roof_part.z_max_m >= 3.6 + 0.19);
    }

    #[test]
    fn cabinet_run_merges_adjacent_countertops() {
        let mut scene = rich_scene();
        scene.fixtures = (0..3)
            .map(|i| crate::scene_ir::FixtureIR {
                id: format!("cab_{i}"),
                level_id: "lvl_1".into(),
                symbol_type: "base_cabinet".into(),
                category: "kitchen_cabinet".into(),
                loc_m: [(i as f64) * 0.61, 1.0, 0.0],
                rot_z_rad: 0.0,
                width_m: 0.61,
                depth_m: 0.61,
                height_m: 0.876,
                has_countertop: true,
                countertop_overhang_m: 0.038,
                countertop_thickness_m: 0.038,
                countertop_material: "quartz".into(),
                has_backsplash: true,
                fill_color: None,
                countertop_color: None,
            })
            .collect();
        let mut state = SceneState::new();
        state.load_scene(scene).unwrap();
        let built = build_scene_mesh(&state);
        let ct_parts: Vec<&MeshPart> = built
            .parts
            .iter()
            .filter(|p| p.sub_part == "RunCountertop")
            .collect();
        assert_eq!(ct_parts.len(), 1);
    }

    #[test]
    fn all_door_and_window_styles_emit_parts() {
        let styles = [
            ("door", "single"),
            ("door", "double"),
            ("door", "entry_lite_half"),
            ("door", "entry_lite_full"),
            ("door", "sliding"),
            ("door", "pocket"),
            ("door", "bi-fold"),
            ("door", "frame"),
            ("door", "garage"),
            ("window", "fixed"),
            ("window", "sliding"),
            ("window", "double-hung"),
            ("window", "casement"),
            ("window", "awning"),
        ];
        for (idx, (kind, style)) in styles.iter().enumerate() {
            let mut scene = rich_scene();
            scene.openings = vec![crate::scene_ir::OpeningIR {
                id: format!("op_{idx}"),
                kind: (*kind).into(),
                host_wall_id: "w_south".into(),
                host_seg_index: 0,
                x_local_m: 1.0,
                z_local_m: if *kind == "door" { 0.0 } else { 0.9 },
                width_m: if *style == "garage" { 2.4 } else { 1.0 },
                depth_m: 0.14,
                height_m: if *kind == "door" { 2.0 } else { 1.1 },
                style: (*style).into(),
                swing: "left".into(),
                orientation: "inswing".into(),
            }];
            let mut state = SceneState::new();
            state.load_scene(scene).unwrap();
            let built = build_scene_mesh(&state);
            assert!(
                built
                    .parts
                    .iter()
                    .any(|p| p.entity_kind == "opening" && p.sub_part == "Frame"),
                "Missing frame for {kind}:{style}"
            );
        }
    }

    #[test]
    fn all_fixture_symbols_produce_multi_part_geometry() {
        let symbols = [
            "base_cabinet",
            "base_drawer_cabinet",
            "sink_base_cabinet",
            "corner_base_cabinet",
            "upper_cabinet",
            "corner_upper_cabinet",
            "tall_pantry",
            "island_cabinet",
            "vanity_single",
            "vanity_double",
            "toilet",
            "bathtub",
            "shower_square",
            "shower_corner",
            "pedestal_sink",
            "kitchen_sink_single",
            "kitchen_sink_double",
            "utility_sink",
            "refrigerator",
            "range_stove",
            "cooktop",
            "wall_oven",
            "dishwasher",
            "range_hood",
            "microwave",
            "washer",
            "dryer",
            "water_heater",
            "furnace",
            "air_conditioner",
            "sofa",
            "loveseat",
            "armchair",
            "coffee_table",
            "end_table",
            "tv_console",
            "bed_king",
            "bed_queen",
            "bed_twin",
            "nightstand",
            "dresser",
            "dining_table",
            "dining_chair",
            "desk",
            "office_chair",
            "bookshelf",
        ];
        for (idx, sym) in symbols.iter().enumerate() {
            let mut scene = rich_scene();
            scene.walls.clear();
            scene.openings.clear();
            scene.rooms.clear();
            scene.roofs.clear();
            scene.footers.clear();
            scene.rim_bands.clear();
            scene.stairs.clear();
            scene.fixtures = vec![crate::scene_ir::FixtureIR {
                id: format!("fx_{idx}"),
                level_id: "lvl_1".into(),
                symbol_type: (*sym).into(),
                category: "test".into(),
                loc_m: [0.0, 0.0, 0.0],
                rot_z_rad: 0.0,
                width_m: 1.2,
                depth_m: 0.8,
                height_m: 0.9,
                has_countertop: *sym == "dishwasher"
                    || sym.contains("cabinet")
                    || sym.contains("vanity"),
                countertop_overhang_m: 0.03,
                countertop_thickness_m: 0.038,
                countertop_material: "quartz".into(),
                has_backsplash: true,
                fill_color: None,
                countertop_color: None,
            }];
            let mut state = SceneState::new();
            state.load_scene(scene).unwrap();
            let built = build_scene_mesh(&state);
            let tris = built.stats().triangle_count;
            assert!(
                tris > 12,
                "Symbol {sym} only produced {tris} triangles (placeholder box)"
            );
        }
    }

    #[test]
    fn corner_base_cabinet_countertop_is_notched_with_dual_backsplash() {
        let mut scene = rich_scene();
        scene.walls.clear();
        scene.openings.clear();
        scene.rooms.clear();
        scene.roofs.clear();
        scene.footers.clear();
        scene.rim_bands.clear();
        scene.stairs.clear();
        scene.fixtures = vec![crate::scene_ir::FixtureIR {
            id: "cab_corner_1".into(),
            level_id: "lvl_1".into(),
            symbol_type: "corner_base_cabinet".into(),
            category: "kitchen_cabinet".into(),
            loc_m: [0.0, 0.0, 0.0],
            rot_z_rad: 0.0,
            width_m: 0.9144,
            depth_m: 0.9144,
            height_m: 0.9144,
            has_countertop: true,
            countertop_overhang_m: 0.0381,
            countertop_thickness_m: 0.0381,
            countertop_material: "quartz".into(),
            has_backsplash: true,
            fill_color: None,
            countertop_color: None,
        }];
        let mut state = SceneState::new();
        state.load_scene(scene).unwrap();
        let built = build_scene_mesh(&state);

        let ct = built
            .parts
            .iter()
            .find(|p| p.sub_part == "CornerCountertop")
            .expect("expected CornerCountertop mesh part");

        let arm_ct = 0.6096f32 + 0.0381;
        let notch_x = -0.9144 * 0.5 + arm_ct + 0.005;
        let notch_y = 0.9144 * 0.5 - arm_ct - 0.005;
        assert!(
            ct.vertices
                .iter()
                .all(|v| !(v.pos[0] > notch_x && v.pos[1] < notch_y)),
            "countertop jutted into inside corner notch"
        );

        let has_top_wall_bs = ct
            .vertices
            .iter()
            .any(|v| v.pos[2] > 0.93 && v.pos[1] > 0.9144 * 0.5 - 0.03);
        let has_left_wall_bs = ct
            .vertices
            .iter()
            .any(|v| v.pos[2] > 0.93 && v.pos[0] < -0.9144 * 0.5 + 0.03);
        assert!(
            has_top_wall_bs,
            "missing +Y wall backsplash on corner sink/cabinet"
        );
        assert!(
            has_left_wall_bs,
            "missing -X wall backsplash on corner sink/cabinet"
        );
    }

    #[test]
    fn concrete_floor_uses_concrete_material_style_not_shingle_or_stone() {
        let mut scene = rich_scene();
        scene.walls.clear();
        scene.openings.clear();
        scene.roofs.clear();
        scene.footers.clear();
        scene.rim_bands.clear();
        scene.stairs.clear();
        scene.fixtures.clear();
        scene.rooms[0].floor_pattern = "concrete_stipple".into();

        let mut state = SceneState::new();
        state.load_scene(scene).unwrap();
        let built = build_scene_mesh(&state);
        let floor_part = built
            .parts
            .iter()
            .find(|p| p.sub_part == "Floor")
            .expect("expected Floor part");
        assert_eq!(
            floor_part.material.style,
            crate::mesh::MaterialStyle::Concrete
        );
    }

    #[test]
    fn u_shaped_stair_upper_flight_aligns_with_railing_bounds() {
        let mut scene = rich_scene();
        scene.walls.clear();
        scene.openings.clear();
        scene.rooms.clear();
        scene.roofs.clear();
        scene.footers.clear();
        scene.rim_bands.clear();
        scene.fixtures.clear();

        scene.stairs = vec![StairIR {
            id: "stair_u_left".into(),
            level_id: "lvl_1".into(),
            stair_type: "u-shaped".into(),
            loc_m: [-0.813, -3.048, 0.0],
            rot_z_rad: -std::f64::consts::FRAC_PI_2,
            width_m: 0.9144,
            total_rise_m: 2.6924,
            num_steps: 14,
            tread_depth_m: 0.254,
            total_run_m: 3.048,
            turn_direction: "left".into(),
            landing_depth_m: 0.9652,
            steps_before_landing: 7,
            winder_count: 0,
            inner_radius_m: 0.0508,
            rotation_degrees: 270.0,
            has_left_rail: true,
            has_right_rail: true,
            rail_height_m: 0.9144,
            railing_paths_m: vec![vec![
                [-0.813, -3.048, 0.0],
                [0.711, -3.048, 1.3462],
                [0.711, -2.9972, 1.3462],
                [-0.813, -2.9972, 2.6924],
            ]],
        }];

        let mut state = SceneState::new();
        state.load_scene(scene).unwrap();
        let built = build_scene_mesh(&state);
        let treads = built
            .parts
            .iter()
            .find(|p| p.sub_part == "Treads")
            .expect("expected Treads part");
        let upper_verts: Vec<_> = treads.vertices.iter().filter(|v| v.pos[2] > 1.40).collect();
        assert!(
            !upper_verts.is_empty(),
            "expected upper flight tread geometry"
        );
        for v in upper_verts {
            assert!(
                v.pos[0] >= -0.85 && v.pos[0] <= 0.74,
                "upper tread X={} outside railing bounds",
                v.pos[0]
            );
            assert!(
                v.pos[1] >= -3.03 && v.pos[1] <= -2.06,
                "upper tread Y={} outside left-turn U-stair railing bounds",
                v.pos[1]
            );
        }

        // Verify right-turn symmetry moves upper flight to +Y side
        let mut right_scene = rich_scene();
        right_scene.walls.clear();
        right_scene.openings.clear();
        right_scene.rooms.clear();
        right_scene.roofs.clear();
        right_scene.footers.clear();
        right_scene.rim_bands.clear();
        right_scene.fixtures.clear();
        right_scene.stairs = vec![StairIR {
            id: "stair_u_right".into(),
            level_id: "lvl_1".into(),
            stair_type: "u-shaped".into(),
            loc_m: [0.0, 0.0, 0.0],
            rot_z_rad: 0.0,
            width_m: 0.9144,
            total_rise_m: 2.6924,
            num_steps: 14,
            tread_depth_m: 0.254,
            total_run_m: 3.048,
            turn_direction: "right".into(),
            landing_depth_m: 0.9652,
            steps_before_landing: 7,
            winder_count: 0,
            inner_radius_m: 0.0508,
            rotation_degrees: 270.0,
            has_left_rail: false,
            has_right_rail: false,
            rail_height_m: 0.9144,
            railing_paths_m: vec![],
        }];
        let mut right_state = SceneState::new();
        right_state.load_scene(right_scene).unwrap();
        let right_built = build_scene_mesh(&right_state);
        let right_treads = right_built
            .parts
            .iter()
            .find(|p| p.sub_part == "Treads")
            .unwrap();
        assert!(
            right_treads
                .vertices
                .iter()
                .filter(|v| v.pos[2] > 1.40)
                .all(|v| v.pos[0] >= 0.94 && v.pos[0] <= 1.90),
            "right-turn U-stair upper flight X bounds misaligned"
        );
    }

    #[test]
    fn stair_cutout_flush_against_room_wall_is_clipped_not_dropped() {
        let mut scene = rich_scene();
        scene.walls.clear();
        scene.openings.clear();
        scene.roofs.clear();
        scene.footers.clear();
        scene.rim_bands.clear();
        scene.stairs.clear();
        scene.fixtures.clear();

        // 4m x 4m room with a 1m x 1.2m cutout overhanging the y=2.0 wall edge by 0.2m
        scene.rooms[0].outer_m = vec![[-2.0, -2.0], [2.0, -2.0], [2.0, 2.0], [-2.0, 2.0]];
        scene.rooms[0].floor_holes_m = vec![vec![[-0.5, 1.0], [0.5, 1.0], [0.5, 2.2], [-0.5, 2.2]]];

        let mut state = SceneState::new();
        state.load_scene(scene).unwrap();
        let built = build_scene_mesh(&state);
        let floor_part = built
            .parts
            .iter()
            .find(|p| p.sub_part == "Floor")
            .expect("expected Floor part");
        let top_z = floor_part.z_max_m;
        let mut top_area = 0.0f32;
        for &tri in floor_part.indices.as_chunks::<3>().0 {
            let a = floor_part.vertices[tri[0] as usize].pos;
            let b = floor_part.vertices[tri[1] as usize].pos;
            let c = floor_part.vertices[tri[2] as usize].pos;
            if (a[2] - top_z).abs() < 1e-4
                && (b[2] - top_z).abs() < 1e-4
                && (c[2] - top_z).abs() < 1e-4
            {
                let abx = b[0] - a[0];
                let aby = b[1] - a[1];
                let acx = c[0] - a[0];
                let acy = c[1] - a[1];
                top_area += 0.5 * (abx * acy - aby * acx).abs();
            }
        }
        // Expected area = 16.0 - 1.0 * 1.0 = 15.0 m^2
        assert!(
            (top_area - 15.0).abs() < 0.05,
            "expected clipped cutout floor area ~15.0 m^2, got {top_area}"
        );
    }
}
