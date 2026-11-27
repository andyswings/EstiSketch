//! Parametric multi-part 3D generators for EstiSketch doors, garage doors, and windows.

use glam::{Vec2, Vec3};

use crate::materials::{door_leaf_material, glass_material, hardware_material, trim_material};
use crate::mesh::{MeshBuilder, MeshPart, PartFlags};
use crate::scene_ir::{OpeningIR, WallIR, WallSegmentIR};

struct OpeningDims {
    origin: Vec3,
    rot_z: f32,
    w: f32,
    h: f32,
    depth: f32,
}

struct OpeningBuilders<'a> {
    frame: &'a mut MeshBuilder,
    leaf: &'a mut MeshBuilder,
    glass: &'a mut MeshBuilder,
    hw: &'a mut MeshBuilder,
}

/// Emit frame, casing, sill nose, door leaf / window sashes, hardware, and glazing.
pub fn emit_opening_meshes(
    opening: &OpeningIR,
    wall: &WallIR,
    seg: &WallSegmentIR,
    z_base: f32,
    parts: &mut Vec<MeshPart>,
) {
    let p0 = Vec2::new(seg.start_m[0] as f32, seg.start_m[1] as f32);
    let p1 = Vec2::new(seg.end_m[0] as f32, seg.end_m[1] as f32);
    let delta = p1 - p0;
    let seg_len = delta.length();
    if seg_len <= 1e-4 {
        return;
    }
    let d = delta / seg_len;
    let n = Vec2::new(-d.y, d.x);
    let rot_z = d.y.atan2(d.x);

    let w = (opening.width_m as f32).max(0.18);
    let h = (opening.height_m as f32).max(0.24);
    let depth = (opening.depth_m as f32).max(0.06);
    let x_start = opening.x_local_m as f32;
    let z0 = z_base + opening.z_local_m as f32;
    let origin_xy = p0 + d * (x_start + w * 0.5) + n * (depth * 0.5);
    let dims = OpeningDims {
        origin: Vec3::new(origin_xy.x, origin_xy.y, z0),
        rot_z,
        w,
        h,
        depth,
    };

    let mut frame_mb = MeshBuilder::new();
    let mut leaf_mb = MeshBuilder::new();
    let mut glass_mb = MeshBuilder::new();
    let mut hw_mb = MeshBuilder::new();
    let mut mb = OpeningBuilders {
        frame: &mut frame_mb,
        leaf: &mut leaf_mb,
        glass: &mut glass_mb,
        hw: &mut hw_mb,
    };

    if opening.kind == "door" {
        build_door(opening, &dims, &mut mb);
    } else {
        build_window(opening, &dims, &mut mb);
    }

    let flags = PartFlags::default();
    if let Some(p) = frame_mb.into_part(
        &opening.id,
        "opening",
        &wall.level_id,
        "Frame",
        flags,
        trim_material(),
    ) {
        parts.push(p);
    }
    if let Some(p) = leaf_mb.into_part(
        &opening.id,
        "opening",
        &wall.level_id,
        "Leaf",
        flags,
        door_leaf_material(&opening.style),
    ) {
        parts.push(p);
    }
    if let Some(p) = hw_mb.into_part(
        &opening.id,
        "opening",
        &wall.level_id,
        "Hardware",
        flags,
        hardware_material(),
    ) {
        parts.push(p);
    }
    if let Some(p) = glass_mb.into_part(
        &opening.id,
        "opening",
        &wall.level_id,
        "Glass",
        flags,
        glass_material(),
    ) {
        parts.push(p);
    }
}

fn emit_door_casing_and_jambs(frame_mb: &mut MeshBuilder, dims: &OpeningDims, jamb_w: f32) {
    let OpeningDims {
        origin,
        rot_z,
        w,
        h,
        depth,
    } = *dims;
    let frame_d = depth + 0.016;
    frame_mb.push_oriented_box(
        origin,
        rot_z,
        Vec3::new(-w * 0.5 + jamb_w * 0.5, 0.0, h * 0.5),
        Vec3::new(jamb_w, frame_d, h),
    );
    frame_mb.push_oriented_box(
        origin,
        rot_z,
        Vec3::new(w * 0.5 - jamb_w * 0.5, 0.0, h * 0.5),
        Vec3::new(jamb_w, frame_d, h),
    );
    frame_mb.push_oriented_box(
        origin,
        rot_z,
        Vec3::new(0.0, 0.0, h - jamb_w * 0.5),
        Vec3::new(w, frame_d, jamb_w),
    );

    let casing_w = 0.064f32;
    let casing_t = 0.016f32;
    for side_y in [
        -(depth * 0.5 + casing_t * 0.5),
        depth * 0.5 + casing_t * 0.5,
    ] {
        frame_mb.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(-w * 0.5 - casing_w * 0.2, side_y, h * 0.5),
            Vec3::new(casing_w, casing_t, h + casing_w),
        );
        frame_mb.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(w * 0.5 + casing_w * 0.2, side_y, h * 0.5),
            Vec3::new(casing_w, casing_t, h + casing_w),
        );
        frame_mb.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, side_y, h + casing_w * 0.35),
            Vec3::new(w + casing_w * 1.4, casing_t, casing_w),
        );
    }
}

struct LeafPlacement {
    origin: Vec3,
    rot_z: f32,
    center_x: f32,
    center_y: f32,
    leaf_w: f32,
    leaf_h: f32,
    handle_on_right: bool,
    with_handle: bool,
}

fn push_shaker_door_leaf(leaf_mb: &mut MeshBuilder, hw_mb: &mut MeshBuilder, lp: &LeafPlacement) {
    let t = 0.044f32;
    let stile = (lp.leaf_w * 0.14).clamp(0.06, 0.11);
    let rail = 0.11f32;
    let mid_h = (lp.leaf_h - 2.0 * rail).max(0.1);
    let panel_inner_w = (lp.leaf_w - 2.0 * stile).max(0.04);

    leaf_mb.push_oriented_box(
        lp.origin,
        lp.rot_z,
        Vec3::new(
            lp.center_x - lp.leaf_w * 0.5 + stile * 0.5,
            lp.center_y,
            lp.leaf_h * 0.5,
        ),
        Vec3::new(stile, t, lp.leaf_h),
    );
    leaf_mb.push_oriented_box(
        lp.origin,
        lp.rot_z,
        Vec3::new(
            lp.center_x + lp.leaf_w * 0.5 - stile * 0.5,
            lp.center_y,
            lp.leaf_h * 0.5,
        ),
        Vec3::new(stile, t, lp.leaf_h),
    );
    leaf_mb.push_oriented_box(
        lp.origin,
        lp.rot_z,
        Vec3::new(lp.center_x, lp.center_y, rail * 0.5),
        Vec3::new(panel_inner_w, t, rail),
    );
    leaf_mb.push_oriented_box(
        lp.origin,
        lp.rot_z,
        Vec3::new(lp.center_x, lp.center_y, lp.leaf_h * 0.42),
        Vec3::new(panel_inner_w, t, 0.08),
    );
    leaf_mb.push_oriented_box(
        lp.origin,
        lp.rot_z,
        Vec3::new(lp.center_x, lp.center_y, lp.leaf_h - rail * 0.5),
        Vec3::new(panel_inner_w, t, rail),
    );
    leaf_mb.push_oriented_box(
        lp.origin,
        lp.rot_z,
        Vec3::new(lp.center_x, lp.center_y, rail + mid_h * 0.5),
        Vec3::new((panel_inner_w + 0.01).max(0.04), 0.022, mid_h),
    );

    if lp.with_handle {
        let hx = if lp.handle_on_right {
            lp.center_x + lp.leaf_w * 0.5 - stile * 0.6
        } else {
            lp.center_x - lp.leaf_w * 0.5 + stile * 0.6
        };
        let dir_x = if lp.handle_on_right { -0.055 } else { 0.055 };
        for sy in [-(t * 0.5 + 0.025), t * 0.5 + 0.025] {
            hw_mb.push_oriented_box(
                lp.origin,
                lp.rot_z,
                Vec3::new(hx, lp.center_y + sy * 0.5, 0.92),
                Vec3::new(0.028, 0.05, 0.052),
            );
            hw_mb.push_oriented_box(
                lp.origin,
                lp.rot_z,
                Vec3::new(hx + dir_x * 0.5, lp.center_y + sy, 0.92),
                Vec3::new(0.11, 0.018, 0.022),
            );
        }
    }
}

fn build_door(opening: &OpeningIR, dims: &OpeningDims, mb: &mut OpeningBuilders<'_>) {
    let jamb_w = 0.042f32;
    emit_door_casing_and_jambs(mb.frame, dims, jamb_w);

    let OpeningDims {
        origin,
        rot_z,
        w,
        h,
        depth,
    } = *dims;
    let inner_w = (w - 2.0 * jamb_w).max(0.10);
    let inner_h = (h - jamb_w).max(0.12);
    let style = opening.style.to_lowercase();

    if style.contains("frame") || style.contains("open") || style.contains("arch") {
        return;
    }

    if style.contains("garage") {
        mb.frame.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.0, 0.015),
            Vec3::new(w, depth, 0.03),
        );
        let rows = 4usize;
        let row_h = inner_h / (rows as f32);
        let cols = ((inner_w / 0.85).round() as usize).clamp(2, 6);
        let col_w = inner_w / (cols as f32);

        for r in 0..rows {
            let cz = (r as f32 + 0.5) * row_h;
            if r == rows - 1 {
                mb.leaf.push_oriented_box(
                    origin,
                    rot_z,
                    Vec3::new(0.0, 0.0, cz - row_h * 0.36),
                    Vec3::new(inner_w, 0.048, row_h * 0.28),
                );
                mb.leaf.push_oriented_box(
                    origin,
                    rot_z,
                    Vec3::new(0.0, 0.0, cz + row_h * 0.36),
                    Vec3::new(inner_w, 0.048, row_h * 0.28),
                );
                for c in 0..=cols {
                    let mx = -inner_w * 0.5 + (c as f32) * col_w;
                    mb.leaf.push_oriented_box(
                        origin,
                        rot_z,
                        Vec3::new(mx, 0.0, cz),
                        Vec3::new(0.055, 0.048, row_h - 0.01),
                    );
                }
                mb.glass.push_oriented_box(
                    origin,
                    rot_z,
                    Vec3::new(0.0, 0.0, cz),
                    Vec3::new((inner_w - 0.08).max(0.1), 0.016, (row_h * 0.44).max(0.08)),
                );
            } else {
                mb.leaf.push_oriented_box(
                    origin,
                    rot_z,
                    Vec3::new(0.0, 0.0, cz),
                    Vec3::new(inner_w, 0.038, row_h - 0.012),
                );
                for c in 0..=cols {
                    let sx = -inner_w * 0.5 + (c as f32) * col_w;
                    mb.leaf.push_oriented_box(
                        origin,
                        rot_z,
                        Vec3::new(sx, 0.0, cz),
                        Vec3::new(0.055, 0.050, row_h - 0.012),
                    );
                }
            }
        }
        return;
    }

    mb.frame.push_oriented_box(
        origin,
        rot_z,
        Vec3::new(0.0, 0.0, 0.010),
        Vec3::new(inner_w, depth + 0.02, 0.020),
    );

    if style.contains("double") {
        let half_w = inner_w * 0.5 - 0.004;
        push_shaker_door_leaf(
            mb.leaf,
            mb.hw,
            &LeafPlacement {
                origin,
                rot_z,
                center_x: -inner_w * 0.25,
                center_y: 0.0,
                leaf_w: half_w,
                leaf_h: inner_h,
                handle_on_right: true,
                with_handle: true,
            },
        );
        push_shaker_door_leaf(
            mb.leaf,
            mb.hw,
            &LeafPlacement {
                origin,
                rot_z,
                center_x: inner_w * 0.25,
                center_y: 0.0,
                leaf_w: half_w,
                leaf_h: inner_h,
                handle_on_right: false,
                with_handle: true,
            },
        );
    } else if style.contains("sliding") {
        let panel_w = inner_w * 0.53;
        for (idx, (px, py)) in [(-inner_w * 0.23, -0.026), (inner_w * 0.23, 0.026)]
            .into_iter()
            .enumerate()
        {
            let sw = 0.065f32;
            mb.leaf.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(px - panel_w * 0.5 + sw * 0.5, py, inner_h * 0.5),
                Vec3::new(sw, 0.04, inner_h),
            );
            mb.leaf.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(px + panel_w * 0.5 - sw * 0.5, py, inner_h * 0.5),
                Vec3::new(sw, 0.04, inner_h),
            );
            mb.leaf.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(px, py, 0.06),
                Vec3::new(panel_w, 0.04, 0.12),
            );
            mb.leaf.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(px, py, inner_h - 0.06),
                Vec3::new(panel_w, 0.04, 0.12),
            );
            mb.glass.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(px, py, inner_h * 0.5),
                Vec3::new(
                    (panel_w - 2.0 * sw).max(0.08),
                    0.014,
                    (inner_h - 0.24).max(0.1),
                ),
            );
            let pull_x = if idx == 0 {
                px + panel_w * 0.5 - sw * 0.5
            } else {
                px - panel_w * 0.5 + sw * 0.5
            };
            mb.hw.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(pull_x, py - 0.035, 1.0),
                Vec3::new(0.022, 0.025, 0.22),
            );
        }
    } else if style.contains("pocket") {
        let panel_w = inner_w * 0.72;
        push_shaker_door_leaf(
            mb.leaf,
            mb.hw,
            &LeafPlacement {
                origin,
                rot_z,
                center_x: inner_w * 0.5 - panel_w * 0.5,
                center_y: 0.0,
                leaf_w: panel_w,
                leaf_h: inner_h,
                handle_on_right: false,
                with_handle: false,
            },
        );
        mb.hw.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(inner_w * 0.5 - panel_w + 0.045, 0.0, 0.94),
            Vec3::new(0.026, 0.05, 0.12),
        );
    } else if style.contains("bi-fold") || style.contains("bifold") {
        let panel_w = inner_w * 0.38;
        push_shaker_door_leaf(
            mb.leaf,
            mb.hw,
            &LeafPlacement {
                origin,
                rot_z: rot_z + 0.45,
                center_x: -inner_w * 0.28,
                center_y: -0.06,
                leaf_w: panel_w,
                leaf_h: inner_h,
                handle_on_right: true,
                with_handle: true,
            },
        );
        push_shaker_door_leaf(
            mb.leaf,
            mb.hw,
            &LeafPlacement {
                origin,
                rot_z: rot_z - 0.45,
                center_x: inner_w * 0.28,
                center_y: -0.06,
                leaf_w: panel_w,
                leaf_h: inner_h,
                handle_on_right: false,
                with_handle: true,
            },
        );
    } else if style.contains("lite") || style.contains("glass") {
        let is_full = style.contains("full");
        let bot_h = if is_full { 0.18 } else { inner_h * 0.42 };
        let glass_h = (inner_h - bot_h - 0.09).max(0.18);
        let glass_z = bot_h + glass_h * 0.5;
        let stile = 0.085f32;
        mb.leaf.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.0, bot_h * 0.5),
            Vec3::new(inner_w, 0.044, bot_h),
        );
        mb.leaf.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(-inner_w * 0.5 + stile * 0.5, 0.0, glass_z),
            Vec3::new(stile, 0.044, glass_h),
        );
        mb.leaf.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(inner_w * 0.5 - stile * 0.5, 0.0, glass_z),
            Vec3::new(stile, 0.044, glass_h),
        );
        mb.leaf.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.0, inner_h - 0.045),
            Vec3::new(inner_w, 0.044, 0.09),
        );
        mb.leaf.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.0, glass_z),
            Vec3::new(0.022, 0.032, glass_h),
        );
        mb.leaf.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.0, glass_z),
            Vec3::new((inner_w - 2.0 * stile).max(0.05), 0.032, 0.022),
        );
        mb.glass.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.0, glass_z),
            Vec3::new((inner_w - 2.0 * stile).max(0.05), 0.014, glass_h),
        );
        let handle_right = opening.swing != "right";
        let hx = if handle_right {
            inner_w * 0.5 - stile * 0.5
        } else {
            -inner_w * 0.5 + stile * 0.5
        };
        mb.hw.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(hx, 0.0, 0.92),
            Vec3::new(0.04, 0.11, 0.032),
        );
    } else {
        push_shaker_door_leaf(
            mb.leaf,
            mb.hw,
            &LeafPlacement {
                origin,
                rot_z,
                center_x: 0.0,
                center_y: 0.0,
                leaf_w: inner_w,
                leaf_h: inner_h,
                handle_on_right: opening.swing != "right",
                with_handle: true,
            },
        );
    }
}

fn build_window(opening: &OpeningIR, dims: &OpeningDims, mb: &mut OpeningBuilders<'_>) {
    let OpeningDims {
        origin,
        rot_z,
        w,
        h,
        depth,
    } = *dims;
    let jamb_w = 0.042f32;
    let frame_d = depth + 0.022;
    mb.frame.push_oriented_box(
        origin,
        rot_z,
        Vec3::new(-w * 0.5 + jamb_w * 0.5, 0.0, h * 0.5),
        Vec3::new(jamb_w, frame_d, h),
    );
    mb.frame.push_oriented_box(
        origin,
        rot_z,
        Vec3::new(w * 0.5 - jamb_w * 0.5, 0.0, h * 0.5),
        Vec3::new(jamb_w, frame_d, h),
    );
    mb.frame.push_oriented_box(
        origin,
        rot_z,
        Vec3::new(0.0, 0.0, h - jamb_w * 0.5),
        Vec3::new(w, frame_d, jamb_w),
    );
    mb.frame.push_oriented_box(
        origin,
        rot_z,
        Vec3::new(0.0, 0.0, jamb_w * 0.5),
        Vec3::new(w + 0.08, frame_d + 0.05, jamb_w * 1.15),
    );

    let casing_w = 0.056f32;
    let casing_t = 0.015f32;
    for side_y in [
        -(depth * 0.5 + casing_t * 0.5),
        depth * 0.5 + casing_t * 0.5,
    ] {
        mb.frame.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(-w * 0.5 - casing_w * 0.2, side_y, h * 0.5),
            Vec3::new(casing_w, casing_t, h + casing_w * 0.8),
        );
        mb.frame.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(w * 0.5 + casing_w * 0.2, side_y, h * 0.5),
            Vec3::new(casing_w, casing_t, h + casing_w * 0.8),
        );
        mb.frame.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, side_y, h + casing_w * 0.25),
            Vec3::new(w + casing_w * 1.4, casing_t, casing_w),
        );
    }

    let inner_w = (w - 2.0 * jamb_w).max(0.08);
    let inner_h = (h - 2.0 * jamb_w).max(0.08);
    let style = opening.style.to_lowercase();

    if style.contains("sliding") {
        let sw = inner_w * 0.52;
        for (px, py) in [(-inner_w * 0.24, -0.016), (inner_w * 0.24, 0.016)] {
            emit_sash_perimeter(mb.frame, dims, Vec3::new(px, py, h * 0.5), sw, inner_h);
            mb.glass.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(px, py, h * 0.5),
                Vec3::new((sw - 0.06).max(0.05), 0.012, (inner_h - 0.06).max(0.05)),
            );
        }
        mb.hw.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, -0.01, h * 0.5),
            Vec3::new(0.025, 0.04, 0.04),
        );
    } else if style.contains("double") {
        let sh = inner_h * 0.52;
        for (pz, py) in [(jamb_w + sh * 0.5, -0.016), (h - jamb_w - sh * 0.5, 0.016)] {
            emit_sash_perimeter(mb.frame, dims, Vec3::new(0.0, py, pz), inner_w, sh);
            mb.glass.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(0.0, py, pz),
                Vec3::new((inner_w - 0.06).max(0.05), 0.012, (sh - 0.06).max(0.05)),
            );
        }
        mb.hw.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.0, h * 0.5 + 0.015),
            Vec3::new(0.05, 0.04, 0.022),
        );
    } else if style.contains("casement") {
        emit_sash_perimeter(
            mb.frame,
            dims,
            Vec3::new(0.0, 0.0, h * 0.5),
            inner_w,
            inner_h,
        );
        if inner_w > 0.75 {
            mb.frame.push_oriented_box(
                origin,
                rot_z,
                Vec3::new(0.0, 0.0, h * 0.5),
                Vec3::new(0.034, 0.042, inner_h),
            );
        }
        mb.glass.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.0, h * 0.5),
            Vec3::new(
                (inner_w - 0.06).max(0.05),
                0.014,
                (inner_h - 0.06).max(0.05),
            ),
        );
        mb.hw.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, -0.035, jamb_w + 0.06),
            Vec3::new(0.065, 0.03, 0.025),
        );
    } else if style.contains("awning") {
        emit_sash_perimeter(
            mb.frame,
            dims,
            Vec3::new(0.0, 0.015, h * 0.5),
            inner_w,
            inner_h,
        );
        mb.frame.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.0, h * 0.5),
            Vec3::new(inner_w, 0.036, 0.028),
        );
        mb.glass.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.015, h * 0.5),
            Vec3::new(
                (inner_w - 0.06).max(0.05),
                0.014,
                (inner_h - 0.06).max(0.05),
            ),
        );
        mb.hw.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, -0.035, jamb_w + 0.05),
            Vec3::new(0.065, 0.03, 0.025),
        );
    } else {
        emit_sash_perimeter(
            mb.frame,
            dims,
            Vec3::new(0.0, 0.0, h * 0.5),
            inner_w,
            inner_h,
        );
        mb.glass.push_oriented_box(
            origin,
            rot_z,
            Vec3::new(0.0, 0.0, h * 0.5),
            Vec3::new(
                (inner_w - 0.06).max(0.05),
                0.014,
                (inner_h - 0.06).max(0.05),
            ),
        );
    }
}

fn emit_sash_perimeter(
    frame_mb: &mut MeshBuilder,
    dims: &OpeningDims,
    center: Vec3,
    sw: f32,
    sh: f32,
) {
    let b = 0.032f32;
    let t = 0.034f32;
    frame_mb.push_oriented_box(
        dims.origin,
        dims.rot_z,
        Vec3::new(center.x - sw * 0.5 + b * 0.5, center.y, center.z),
        Vec3::new(b, t, sh),
    );
    frame_mb.push_oriented_box(
        dims.origin,
        dims.rot_z,
        Vec3::new(center.x + sw * 0.5 - b * 0.5, center.y, center.z),
        Vec3::new(b, t, sh),
    );
    frame_mb.push_oriented_box(
        dims.origin,
        dims.rot_z,
        Vec3::new(center.x, center.y, center.z - sh * 0.5 + b * 0.5),
        Vec3::new(sw, t, b),
    );
    frame_mb.push_oriented_box(
        dims.origin,
        dims.rot_z,
        Vec3::new(center.x, center.y, center.z + sh * 0.5 - b * 0.5),
        Vec3::new(sw, t, b),
    );
}
