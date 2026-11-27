//! Wall-aware shaker cabinets, vanities, and automatic cabinet-run merging.
//!
//! Coordinate invariant in 3D local fixture space (`origin = fx.loc_m`, `rot_z = fx.rot_z_rad`):
//! - `-Y` faces forward into the room (doors, drawer fronts, countertop front overhang).
//! - `+Y` faces backward toward the host wall (backsplash, rear carcass).
//! - `-X` / `+X` are left and right ends respectively.

use glam::{Vec2, Vec3};

use crate::materials::{
    chrome_material, countertop_material, fixture_material, hardware_material, porcelain_material,
    stainless_material,
};
use crate::mesh::{MeshBuilder, MeshPart, PartFlags};
use crate::scene_ir::FixtureIR;

/// True when `symbol_type` uses the shaker cabinetry / vanity builder.
pub fn is_cabinet_like(symbol_type: &str) -> bool {
    matches!(
        symbol_type.to_lowercase().as_str(),
        "base_cabinet"
            | "base_drawer_cabinet"
            | "sink_base_cabinet"
            | "corner_base_cabinet"
            | "upper_cabinet"
            | "corner_upper_cabinet"
            | "tall_pantry"
            | "island_cabinet"
            | "vanity_single"
            | "vanity_double"
    )
}

#[derive(Clone)]
struct RunItem<'a> {
    fx: &'a FixtureIR,
    origin: Vec2,
    u: Vec2,
    v: Vec2,
    w: f32,
    d: f32,
    z_top: f32,
}

/// Emit all cabinet/vanity bodies, shaker doors/drawers, basins/faucets, and merged run countertops.
pub fn emit_cabinet_meshes(all_fixtures: &[&FixtureIR], parts: &mut Vec<MeshPart>) {
    let run_items: Vec<RunItem<'_>> = all_fixtures
        .iter()
        .copied()
        .filter(|fx| fx.has_countertop)
        .map(|fx| {
            let rz = fx.rot_z_rad as f32;
            let (sr, cr) = rz.sin_cos();
            RunItem {
                fx,
                origin: Vec2::new(fx.loc_m[0] as f32, fx.loc_m[1] as f32),
                u: Vec2::new(cr, sr),
                v: Vec2::new(-sr, cr),
                w: (fx.width_m as f32).max(0.10),
                d: (fx.depth_m as f32).max(0.10),
                z_top: (fx.loc_m[2] + fx.height_m) as f32,
            }
        })
        .collect();

    // Detect abutted left/right neighbors and group collinear countertop runs via union-find.
    let n = run_items.len();
    let mut left_abutted = vec![false; n];
    let mut right_abutted = vec![false; n];
    let mut parent: Vec<usize> = (0..n).collect();

    fn find(p: &mut [usize], mut x: usize) -> usize {
        while p[x] != x {
            p[x] = p[p[x]];
            x = p[x];
        }
        x
    }

    for i in 0..n {
        for j in (i + 1)..n {
            if run_items[i].fx.level_id != run_items[j].fx.level_id {
                continue;
            }
            if (run_items[i].z_top - run_items[j].z_top).abs() > 0.035 {
                continue;
            }
            let diff = run_items[j].origin - run_items[i].origin;
            let same_dir = run_items[i].u.dot(run_items[j].u) > 0.99
                && run_items[i].v.dot(run_items[j].v) > 0.99;

            if same_dir {
                let du = diff.dot(run_items[i].u);
                let dv = diff.dot(run_items[i].v).abs();
                let target_span = 0.5 * (run_items[i].w + run_items[j].w);
                if dv <= 0.045 && (du.abs() - target_span).abs() <= 0.035 {
                    if du > 0.0 {
                        right_abutted[i] = true;
                        left_abutted[j] = true;
                    } else {
                        left_abutted[i] = true;
                        right_abutted[j] = true;
                    }
                    let ra = find(&mut parent, i);
                    let rb = find(&mut parent, j);
                    if ra != rb {
                        parent[rb] = ra;
                    }
                }
            } else if run_items[i].u.dot(run_items[j].v).abs() > 0.95 {
                // Perpendicular L-corner touch check suppresses exposed end panel styling
                let dist_center = diff.length();
                let max_touch = 0.5 * (run_items[i].w + run_items[j].d + 0.10);
                if dist_center <= max_touch {
                    let du_i = diff.dot(run_items[i].u);
                    if du_i > 0.0 {
                        right_abutted[i] = true;
                    } else {
                        left_abutted[i] = true;
                    }
                }
            }
        }
    }

    // Group run items by root index and emit one continuous countertop + backsplash per run.
    let mut groups: std::collections::BTreeMap<usize, Vec<usize>> = Default::default();
    for idx in 0..n {
        let root = find(&mut parent, idx);
        groups.entry(root).or_default().push(idx);
    }

    for members in groups.values() {
        emit_merged_run_countertop(&run_items, members, parts);
    }

    // Emit each shaker cabinet carcass, doors/drawers, hardware, and basins.
    let mut abut_by_id: std::collections::HashMap<&str, (bool, bool)> = Default::default();
    for (idx, item) in run_items.iter().enumerate() {
        abut_by_id.insert(item.fx.id.as_str(), (left_abutted[idx], right_abutted[idx]));
    }

    for &fx in all_fixtures {
        if !is_cabinet_like(&fx.symbol_type) {
            continue;
        }
        let (l_ab, r_ab) = abut_by_id
            .get(fx.id.as_str())
            .copied()
            .unwrap_or((false, false));
        emit_single_cabinet(fx, l_ab, r_ab, parts);
    }
}

fn emit_merged_run_countertop(items: &[RunItem<'_>], members: &[usize], parts: &mut Vec<MeshPart>) {
    let first = &items[members[0]];
    let mut u_min = f32::INFINITY;
    let mut u_max = f32::NEG_INFINITY;
    let mut v_min = f32::INFINITY;
    let mut v_max = f32::NEG_INFINITY;
    let mut z_top = first.z_top;
    let mut ct_thick = (first.fx.countertop_thickness_m as f32).clamp(0.02, 0.08);
    let mut any_backsplash = false;
    let mut all_island = true;

    for &idx in members {
        let it = &items[idx];
        let rel = it.origin - first.origin;
        let cu = rel.dot(first.u);
        let cv = rel.dot(first.v);
        let oh = (it.fx.countertop_overhang_m as f32).max(0.0);
        let end_oh = if members.len() == 1 { oh * 0.35 } else { 0.012 };
        u_min = u_min.min(cu - it.w * 0.5 - end_oh);
        u_max = u_max.max(cu + it.w * 0.5 + end_oh);
        v_min = v_min.min(cv - it.d * 0.5 - oh);
        v_max = v_max.max(cv + it.d * 0.5);
        z_top = z_top.max(it.z_top);
        ct_thick = ct_thick.max((it.fx.countertop_thickness_m as f32).clamp(0.02, 0.08));
        if it.fx.has_backsplash {
            any_backsplash = true;
        }
        if !it.fx.symbol_type.contains("island") {
            all_island = false;
        }
    }

    let span_u = (u_max - u_min).max(0.08);
    let span_v = (v_max - v_min).max(0.08);
    let center_xy =
        first.origin + first.u * (0.5 * (u_min + u_max)) + first.v * (0.5 * (v_min + v_max));
    let rot_z = first.u.y.atan2(first.u.x);

    let mut ct_mb = MeshBuilder::new();
    ct_mb.push_beveled_box(
        Vec3::new(center_xy.x, center_xy.y, z_top - ct_thick * 0.5),
        rot_z,
        Vec3::ZERO,
        Vec3::new(span_u, span_v, ct_thick),
        0.004,
    );

    if any_backsplash && !all_island {
        let bs_h = 0.10f32;
        let bs_d = 0.020f32;
        let bs_xy =
            first.origin + first.u * (0.5 * (u_min + u_max)) + first.v * (v_max - bs_d * 0.5);
        ct_mb.push_oriented_box(
            Vec3::new(bs_xy.x, bs_xy.y, z_top + bs_h * 0.5),
            rot_z,
            Vec3::ZERO,
            Vec3::new(span_u, bs_d, bs_h),
        );
    }

    if let Some(p) = ct_mb.into_part(
        &first.fx.id,
        "fixture",
        &first.fx.level_id,
        "RunCountertop",
        PartFlags::default(),
        countertop_material(&first.fx.countertop_material, first.fx.countertop_color),
    ) {
        parts.push(p);
    }
}

fn emit_single_cabinet(
    fx: &FixtureIR,
    left_abutted: bool,
    right_abutted: bool,
    parts: &mut Vec<MeshPart>,
) {
    let mut body_mb = MeshBuilder::new();
    let mut hw_mb = MeshBuilder::new();
    let mut basin_mb = MeshBuilder::new();
    let mut chrome_mb = MeshBuilder::new();

    let origin = Vec3::new(fx.loc_m[0] as f32, fx.loc_m[1] as f32, fx.loc_m[2] as f32);
    let rot_z = fx.rot_z_rad as f32;
    let w = (fx.width_m as f32).max(0.15);
    let d = (fx.depth_m as f32).max(0.15);
    let h = (fx.height_m as f32).max(0.20);
    let sym = fx.symbol_type.to_lowercase();

    let is_upper = sym.contains("upper");
    let is_corner = sym.contains("corner");
    let is_island = sym.contains("island");
    let ct_thick = if fx.has_countertop {
        (fx.countertop_thickness_m as f32).clamp(0.02, 0.08)
    } else {
        0.0
    };
    let toe_h = if is_upper {
        0.0
    } else {
        (0.10f32).min(h * 0.16)
    };
    let box_h = (h - ct_thick - toe_h).max(0.12);
    let box_cz = toe_h + box_h * 0.5;

    if is_corner {
        // L-shaped corner carcass with diagonal front shaker face
        let arm_d = (d * 0.52).max(0.28);
        body_mb.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, d * 0.5 - arm_d * 0.5, box_cz),
            Vec3::new(w, arm_d, box_h),
        );
        body_mb.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(-w * 0.5 + arm_d * 0.5, 0.0, box_cz),
            Vec3::new(arm_d, d, box_h),
        );
        if toe_h > 0.0 {
            body_mb.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(0.0, d * 0.5 - arm_d * 0.5, toe_h * 0.5),
                Vec3::new(w - 0.02, arm_d - 0.04, toe_h),
            );
            body_mb.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(-w * 0.5 + arm_d * 0.5, 0.0, toe_h * 0.5),
                Vec3::new(arm_d - 0.04, d - 0.02, toe_h),
            );
        }
        push_shaker_door(
            &mut body_mb,
            &mut hw_mb,
            origin,
            rot_z + std::f32::consts::FRAC_PI_4,
            Vec3::new(0.04, 0.02, box_cz),
            (w * 0.55).max(0.32),
            box_h - 0.02,
            false,
        );
    } else {
        if toe_h > 0.0 {
            body_mb.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(0.0, 0.03, toe_h * 0.5),
                Vec3::new((w - 0.02).max(0.08), (d - 0.06).max(0.08), toe_h),
            );
        }
        body_mb.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.0, box_cz),
            Vec3::new(w, d, box_h),
        );

        // Exposed shaker end panels on un-abutted left (-X) and right (+X) ends
        if !left_abutted {
            body_mb.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(-w * 0.5 - 0.006, 0.0, box_cz),
                Vec3::new(0.012, d - 0.02, box_h - 0.02),
            );
        }
        if !right_abutted {
            body_mb.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(w * 0.5 + 0.006, 0.0, box_cz),
                Vec3::new(0.012, d - 0.02, box_h - 0.02),
            );
        }

        let front_y = -d * 0.5 - 0.010;
        if sym == "base_drawer_cabinet" {
            let dh = (box_h - 0.03) / 3.0;
            for r in 0..3 {
                let dz = toe_h + 0.01 + (r as f32 + 0.5) * dh;
                push_shaker_drawer(
                    &mut body_mb,
                    &mut hw_mb,
                    origin,
                    rot_z,
                    Vec3::new(0.0, front_y, dz),
                    w - 0.02,
                    dh - 0.012,
                );
            }
        } else if is_upper {
            let cols = if w >= 0.65 { 2 } else { 1 };
            let dw = (w - 0.02) / (cols as f32);
            for c in 0..cols {
                let dx = -w * 0.5 + 0.01 + (c as f32 + 0.5) * dw;
                push_shaker_door(
                    &mut body_mb,
                    &mut hw_mb,
                    origin,
                    rot_z,
                    Vec3::new(dx, front_y, box_cz),
                    dw - 0.010,
                    box_h - 0.02,
                    c == 0 && cols == 2,
                );
            }
        } else if sym == "tall_pantry" {
            let lower_h = box_h * 0.42;
            let upper_h = box_h - lower_h - 0.02;
            let cols = if w >= 0.72 { 2 } else { 1 };
            let dw = (w - 0.02) / (cols as f32);
            for c in 0..cols {
                let dx = -w * 0.5 + 0.01 + (c as f32 + 0.5) * dw;
                push_shaker_door(
                    &mut body_mb,
                    &mut hw_mb,
                    origin,
                    rot_z,
                    Vec3::new(dx, front_y, toe_h + lower_h * 0.5),
                    dw - 0.01,
                    lower_h - 0.01,
                    c == 0 && cols == 2,
                );
                push_shaker_door(
                    &mut body_mb,
                    &mut hw_mb,
                    origin,
                    rot_z,
                    Vec3::new(dx, front_y, toe_h + lower_h + 0.015 + upper_h * 0.5),
                    dw - 0.01,
                    upper_h - 0.01,
                    c == 0 && cols == 2,
                );
            }
        } else {
            // Base / sink base / island / vanity: upper drawer(s) + lower doors
            let top_h = (0.16f32).min(box_h * 0.25);
            let door_h = (box_h - top_h - 0.02).max(0.10);
            let door_cz = toe_h + door_h * 0.5 + 0.008;
            let top_cz = toe_h + door_h + 0.016 + top_h * 0.5;
            let cols = if w >= 1.15 {
                3
            } else if w >= 0.58 {
                2
            } else {
                1
            };
            let dw = (w - 0.02) / (cols as f32);
            for c in 0..cols {
                let dx = -w * 0.5 + 0.01 + (c as f32 + 0.5) * dw;
                push_shaker_drawer(
                    &mut body_mb,
                    &mut hw_mb,
                    origin,
                    rot_z,
                    Vec3::new(dx, front_y, top_cz),
                    dw - 0.010,
                    top_h - 0.010,
                );
                push_shaker_door(
                    &mut body_mb,
                    &mut hw_mb,
                    origin,
                    rot_z,
                    Vec3::new(dx, front_y, door_cz),
                    dw - 0.010,
                    door_h,
                    c % 2 == 0,
                );
            }
            if is_island {
                // Decorative shaker panel across island rear (+Y)
                let back_y = d * 0.5 + 0.008;
                body_mb.push_oriented_box(
                    origin,
                    rot_z,
                    Vec3::new(0.0, back_y, box_cz),
                    Vec3::new(w - 0.03, 0.014, box_h - 0.03),
                );
            }
        }
    }

    // Add sink rims + chrome gooseneck faucets for sink_base_cabinet & vanities
    if sym == "sink_base_cabinet" || sym == "vanity_single" || sym == "vanity_double" {
        let z_ct = h;
        let is_double = sym == "vanity_double";
        let bowl_centers: &[f32] = if is_double {
            &[-w * 0.24, w * 0.24]
        } else {
            &[0.0]
        };
        let bw = if is_double {
            (w * 0.34).min(0.48)
        } else {
            (w * 0.56).min(0.56)
        };
        let bd = (d * 0.60).min(0.40);
        for &bx in bowl_centers {
            basin_mb.push_beveled_box(
                origin,
                rot_z,
                Vec3::new(bx, -0.02, z_ct + 0.008),
                Vec3::new(bw, bd, 0.020),
                0.006,
            );
            // Chrome gooseneck faucet near rear edge (+Y)
            chrome_mb.push_cylinder(
                origin,
                rot_z,
                Vec3::new(bx, bd * 0.5 + 0.02, z_ct),
                [0.016, 0.014],
                0.18,
                12,
            );
            chrome_mb.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(bx, bd * 0.5 - 0.04, z_ct + 0.17),
                Vec3::new(0.022, 0.13, 0.022),
            );
            chrome_mb.push_cylinder(
                origin,
                rot_z,
                Vec3::new(bx, -0.02, z_ct + 0.019),
                [0.026, 0.026],
                0.004,
                12,
            );
        }
    }

    let flags = PartFlags::default();
    if let Some(p) = body_mb.into_part(
        &fx.id,
        "fixture",
        &fx.level_id,
        "CabinetBody",
        flags,
        fixture_material(&fx.symbol_type, fx.fill_color),
    ) {
        parts.push(p);
    }
    if let Some(p) = hw_mb.into_part(
        &fx.id,
        "fixture",
        &fx.level_id,
        "Hardware",
        flags,
        hardware_material(),
    ) {
        parts.push(p);
    }
    if let Some(p) = basin_mb.into_part(
        &fx.id,
        "fixture",
        &fx.level_id,
        "Basin",
        flags,
        if sym.contains("sink_base") {
            stainless_material(None)
        } else {
            porcelain_material(None)
        },
    ) {
        parts.push(p);
    }
    if let Some(p) = chrome_mb.into_part(
        &fx.id,
        "fixture",
        &fx.level_id,
        "Faucet",
        flags,
        chrome_material(),
    ) {
        parts.push(p);
    }
}

#[allow(clippy::too_many_arguments)]
fn push_shaker_door(
    mb: &mut MeshBuilder,
    hw_mb: &mut MeshBuilder,
    origin: Vec3,
    rot_z: f32,
    center: Vec3,
    w: f32,
    h: f32,
    pull_right: bool,
) {
    let t = 0.018f32;
    let frame = 0.045f32.min(w * 0.22).min(h * 0.2);
    // Shaker stiles & rails + recessed panel
    mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(-w * 0.5 + frame * 0.5, 0.0, 0.0),
        Vec3::new(frame, t, h),
    );
    mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(w * 0.5 - frame * 0.5, 0.0, 0.0),
        Vec3::new(frame, t, h),
    );
    mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(0.0, 0.0, -h * 0.5 + frame * 0.5),
        Vec3::new((w - 2.0 * frame).max(0.02), t, frame),
    );
    mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(0.0, 0.0, h * 0.5 - frame * 0.5),
        Vec3::new((w - 2.0 * frame).max(0.02), t, frame),
    );
    mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(0.0, 0.004, 0.0),
        Vec3::new(
            (w - 2.0 * frame).max(0.02),
            0.010,
            (h - 2.0 * frame).max(0.02),
        ),
    );

    let px = if pull_right {
        w * 0.5 - frame * 0.65
    } else {
        -w * 0.5 + frame * 0.65
    };
    hw_mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(px, -0.020, h * 0.22),
        Vec3::new(0.014, 0.022, (h * 0.28).clamp(0.08, 0.16)),
    );
}

fn push_shaker_drawer(
    mb: &mut MeshBuilder,
    hw_mb: &mut MeshBuilder,
    origin: Vec3,
    rot_z: f32,
    center: Vec3,
    w: f32,
    h: f32,
) {
    let t = 0.018f32;
    let b = 0.032f32.min(w * 0.15).min(h * 0.25);
    mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(0.0, 0.004, 0.0),
        Vec3::new(w, 0.010, h),
    );
    mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(-w * 0.5 + b * 0.5, 0.0, 0.0),
        Vec3::new(b, t, h),
    );
    mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(w * 0.5 - b * 0.5, 0.0, 0.0),
        Vec3::new(b, t, h),
    );
    mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(0.0, 0.0, h * 0.5 - b * 0.5),
        Vec3::new(w, t, b),
    );
    mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(0.0, 0.0, -h * 0.5 + b * 0.5),
        Vec3::new(w, t, b),
    );
    hw_mb.push_oriented_box(
        origin,
        rot_z,
        center + Vec3::new(0.0, -0.020, 0.0),
        Vec3::new((w * 0.36).clamp(0.09, 0.22), 0.022, 0.014),
    );
}
