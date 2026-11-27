//! Multi-part procedural 3D builders for all 36 non-cabinet plumbing, appliance, and furniture symbols.
//!
//! Local fixture coordinate convention (`origin = fx.loc_m`, `rot_z = fx.rot_z_rad`):
//! - `-Y` faces forward into the room.
//! - `+Y` faces backward toward the host wall.
//! - `-X` / `+X` are left/right; bathtub drain end is at `-X`.

use glam::{Vec2, Vec3};

use crate::materials::{
    appliance_glass_material, chrome_material, concrete_material, fabric_linen_material,
    fixture_material, glass_material, hardware_material, porcelain_material, stainless_material,
    trim_material, upholstery_material, wood_furniture_material,
};
use crate::mesh::{MaterialDef, MeshBuilder, MeshPart, PartFlags};
use crate::scene_ir::FixtureIR;
use crate::sinks::{kitchen_sink_specs, push_recessed_basin, push_sink_bowl};

struct PartBag {
    primary: MeshBuilder,
    accent: MeshBuilder,
    metal: MeshBuilder,
    dark_glass: MeshBuilder,
    clear_glass: MeshBuilder,
    soft: MeshBuilder,
    primary_mat: MaterialDef,
    accent_mat: MaterialDef,
    metal_mat: MaterialDef,
    soft_mat: MaterialDef,
}

impl PartBag {
    fn new(fx: &FixtureIR) -> Self {
        Self {
            primary: MeshBuilder::new(),
            accent: MeshBuilder::new(),
            metal: MeshBuilder::new(),
            dark_glass: MeshBuilder::new(),
            clear_glass: MeshBuilder::new(),
            soft: MeshBuilder::new(),
            primary_mat: fixture_material(&fx.symbol_type, fx.fill_color),
            accent_mat: trim_material(),
            metal_mat: chrome_material(),
            soft_mat: fabric_linen_material(),
        }
    }

    fn flush(self, fx: &FixtureIR, parts: &mut Vec<MeshPart>) {
        let flags = PartFlags::default();
        if let Some(p) = self.primary.into_part(
            &fx.id,
            "fixture",
            &fx.level_id,
            "Body",
            flags,
            self.primary_mat,
        ) {
            parts.push(p);
        }
        if let Some(p) = self.accent.into_part(
            &fx.id,
            "fixture",
            &fx.level_id,
            "Trim",
            flags,
            self.accent_mat,
        ) {
            parts.push(p);
        }
        if let Some(p) = self.metal.into_part(
            &fx.id,
            "fixture",
            &fx.level_id,
            "Hardware",
            flags,
            self.metal_mat,
        ) {
            parts.push(p);
        }
        if let Some(p) = self.dark_glass.into_part(
            &fx.id,
            "fixture",
            &fx.level_id,
            "DarkGlass",
            flags,
            appliance_glass_material(),
        ) {
            parts.push(p);
        }
        if let Some(p) = self.clear_glass.into_part(
            &fx.id,
            "fixture",
            &fx.level_id,
            "Glass",
            flags,
            glass_material(),
        ) {
            parts.push(p);
        }
        if let Some(p) = self.soft.into_part(
            &fx.id,
            "fixture",
            &fx.level_id,
            "Soft",
            flags,
            self.soft_mat,
        ) {
            parts.push(p);
        }
    }
}

/// Emit detailed multi-part geometry for any non-cabinet `FixtureIR`.
pub fn emit_procedural_fixture(fx: &FixtureIR, parts: &mut Vec<MeshPart>) {
    let origin = Vec3::new(fx.loc_m[0] as f32, fx.loc_m[1] as f32, fx.loc_m[2] as f32);
    let rot = fx.rot_z_rad as f32;
    let w = (fx.width_m as f32).max(0.10);
    let d = (fx.depth_m as f32).max(0.10);
    let h = (fx.height_m as f32).max(0.08);
    let sym = fx.symbol_type.to_lowercase();

    let mut bag = PartBag::new(fx);
    match sym.as_str() {
        "toilet" => build_toilet(&mut bag, fx, origin, rot, w, d, h),
        "bathtub" => build_bathtub(&mut bag, fx, origin, rot, w, d, h),
        "shower_square" | "shower_corner" => {
            build_shower(&mut bag, origin, rot, w, d, h, sym == "shower_corner")
        }
        "pedestal_sink" => build_pedestal_sink(&mut bag, fx, origin, rot, w, d, h),
        "kitchen_sink_single" | "kitchen_sink_double" | "utility_sink" => {
            build_utility_or_kitchen_sink(&mut bag, origin, rot, w, d, h, &sym)
        }
        "refrigerator" => build_refrigerator(&mut bag, fx, origin, rot, w, d, h),
        "range_stove" => build_range_stove(&mut bag, fx, origin, rot, w, d, h),
        "cooktop" => build_cooktop(&mut bag, origin, rot, w, d, h),
        "wall_oven" => build_wall_oven(&mut bag, fx, origin, rot, w, d, h),
        "dishwasher" => build_dishwasher(&mut bag, fx, origin, rot, w, d, h),
        "range_hood" => build_range_hood(&mut bag, origin, rot, w, d, h),
        "microwave" => build_microwave(&mut bag, origin, rot, w, d, h),
        "washer" | "dryer" => build_laundry(&mut bag, fx, origin, rot, w, d, h, sym == "washer"),
        "water_heater" => build_water_heater(&mut bag, origin, rot, w, d, h),
        "furnace" => build_furnace(&mut bag, origin, rot, w, d, h),
        "air_conditioner" => build_ac_unit(&mut bag, origin, rot, w, d, h),
        "sofa" | "loveseat" | "armchair" => build_seating(&mut bag, fx, origin, rot, w, d, h),
        "coffee_table" | "end_table" | "dining_table" => {
            build_table(&mut bag, fx, origin, rot, w, d, h, sym != "dining_table")
        }
        "tv_console" => build_tv_console(&mut bag, fx, origin, rot, w, d, h),
        "bed_king" | "bed_queen" | "bed_twin" => build_bed(&mut bag, fx, origin, rot, w, d, h),
        "nightstand" | "dresser" => {
            build_casework(&mut bag, fx, origin, rot, w, d, h, sym == "dresser")
        }
        "dining_chair" => build_dining_chair(&mut bag, fx, origin, rot, w, d, h),
        "desk" => build_desk(&mut bag, fx, origin, rot, w, d, h),
        "office_chair" => build_office_chair(&mut bag, fx, origin, rot, w, d, h),
        "bookshelf" => build_bookshelf(&mut bag, fx, origin, rot, w, d, h),
        _ => {
            bag.primary.push_beveled_box(
                origin,
                rot,
                Vec3::new(0.0, 0.0, h * 0.5),
                Vec3::new(w, d, h),
                0.015,
            );
        }
    }
    bag.flush(fx, parts);
}

fn build_toilet(bag: &mut PartBag, fx: &FixtureIR, origin: Vec3, rot: f32, w: f32, d: f32, h: f32) {
    bag.primary_mat = porcelain_material(fx.fill_color);
    let tank_d = (d * 0.30).clamp(0.16, 0.24);
    let tank_h = h;
    let bowl_h = (h * 0.54).clamp(0.36, 0.43);
    // Tank against back (+Y)
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - tank_d * 0.5, tank_h * 0.5),
        Vec3::new(w * 0.92, tank_d, tank_h),
        0.015,
    );
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - tank_d * 0.5, tank_h + 0.012),
        Vec3::new(w * 0.98, tank_d + 0.02, 0.028),
        0.008,
    );
    // Pedestal base & tapered bowl toward front (-Y)
    let bowl_cy = -d * 0.5 + (d - tank_d) * 0.46;
    bag.primary.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, bowl_cy, 0.0),
        [w * 0.30, w * 0.24],
        bowl_h * 0.55,
        14,
    );
    bag.primary.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, bowl_cy, bowl_h * 0.52),
        [w * 0.24, w * 0.44],
        bowl_h * 0.48,
        16,
    );
    bag.accent.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, bowl_cy, bowl_h + 0.002),
        [w * 0.43, w * 0.41],
        0.022,
        16,
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(-w * 0.40, d * 0.5 - tank_d - 0.012, tank_h - 0.06),
        Vec3::new(0.055, 0.016, 0.016),
    );
}

fn build_bathtub(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
) {
    bag.primary_mat = porcelain_material(fx.fill_color);
    let rim = 0.075f32;
    let floor_t = 0.07f32;
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, floor_t * 0.5),
        Vec3::new(w, d, floor_t),
    );
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, -d * 0.5 + rim * 0.5, h * 0.5),
        Vec3::new(w, rim, h),
    );
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - rim * 0.5, h * 0.5),
        Vec3::new(w, rim, h),
    );
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(-w * 0.5 + rim * 0.5, 0.0, h * 0.5),
        Vec3::new(rim, d, h),
    );
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(w * 0.5 - rim * 0.5, 0.0, h * 0.5),
        Vec3::new(rim, d, h),
    );
    // Chrome spout & drain at -X plumbing end
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(-w * 0.5 + rim + 0.09, 0.0, floor_t),
        [0.028, 0.028],
        0.008,
        12,
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(-w * 0.5 + rim + 0.07, 0.0, h + 0.08),
        Vec3::new(0.14, 0.032, 0.032),
    );
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(-w * 0.5 + rim * 0.5, -0.09, h + 0.02),
        [0.022, 0.022],
        0.04,
        10,
    );
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(-w * 0.5 + rim * 0.5, 0.09, h + 0.02),
        [0.022, 0.022],
        0.04,
        10,
    );
}

fn build_shower(
    bag: &mut PartBag,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
    is_corner: bool,
) {
    bag.primary_mat = porcelain_material(None);
    let curb = 0.11f32;
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, curb * 0.5),
        Vec3::new(w, d, curb),
        0.008,
    );
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, 0.0, curb),
        [0.038, 0.038],
        0.006,
        12,
    );

    // Corner mullions + translucent shower glass walls
    let glass_h = (h - curb).max(1.2);
    let cz = curb + glass_h * 0.5;
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(-w * 0.5 + 0.018, -d * 0.5 + 0.018, cz),
        Vec3::new(0.036, 0.036, glass_h),
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(w * 0.5 - 0.018, -d * 0.5 + 0.018, cz),
        Vec3::new(0.036, 0.036, glass_h),
    );
    bag.clear_glass.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, -d * 0.5 + 0.016, cz),
        Vec3::new(w - 0.04, 0.012, glass_h),
    );
    if is_corner {
        bag.clear_glass.push_oriented_box(
            origin,
            rot,
            Vec3::new(w * 0.5 - 0.016, 0.0, cz),
            Vec3::new(0.012, d - 0.04, glass_h),
        );
    }
    // Shower arm & head near back (+Y)
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - 0.10, h - 0.12),
        Vec3::new(0.025, 0.18, 0.025),
    );
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - 0.18, h - 0.16),
        [0.06, 0.03],
        0.035,
        12,
    );
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - 0.03, 1.10),
        [0.045, 0.045],
        0.03,
        12,
    );
}

fn build_pedestal_sink(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
) {
    bag.primary_mat = porcelain_material(fx.fill_color);
    let ped_h = (h - 0.16).max(0.40);
    bag.primary.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, 0.02, 0.0),
        [w * 0.24, w * 0.17],
        ped_h,
        14,
    );
    let floor = push_recessed_basin(
        &mut bag.primary,
        Vec3::new(origin.x, origin.y, origin.z),
        rot,
        w,
        d,
        h - 0.16,
        h,
        0.06,
        0.05,
    );
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, -0.01, floor.z),
        [0.028, 0.028],
        0.005,
        12,
    );
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - 0.03, h),
        [0.018, 0.015],
        0.14,
        12,
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - 0.07, h + 0.13),
        Vec3::new(0.022, 0.08, 0.022),
    );
}

fn build_utility_or_kitchen_sink(
    bag: &mut PartBag,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
    sym: &str,
) {
    let is_util = sym == "utility_sink";
    bag.primary_mat = if is_util {
        porcelain_material(None)
    } else {
        stainless_material(None)
    };
    if is_util {
        let leg_h = (h - 0.28).max(0.25);
        for sx in [-w * 0.42, w * 0.42] {
            for sy in [-d * 0.40, d * 0.40] {
                bag.metal.push_cylinder(
                    origin,
                    rot,
                    Vec3::new(sx, sy, 0.0),
                    [0.018, 0.018],
                    leg_h,
                    8,
                );
            }
        }
        let floor =
            push_recessed_basin(&mut bag.primary, origin, rot, w, d, h - 0.28, h, 0.04, 0.04);
        bag.metal.push_cylinder(
            origin,
            rot,
            Vec3::new(0.0, -0.01, floor.z),
            [0.032, 0.032],
            0.005,
            12,
        );
        bag.metal.push_cylinder(
            origin,
            rot,
            Vec3::new(0.0, d * 0.5 - 0.02, h),
            [0.018, 0.015],
            0.20,
            12,
        );
        bag.metal.push_oriented_box(
            origin,
            rot,
            Vec3::new(0.0, d * 0.5 - 0.07, h + 0.19),
            Vec3::new(0.024, 0.10, 0.024),
        );
        return;
    }

    // Drop-in kitchen sink: origin sits on the countertop surface, bowls hang below it.
    for spec in kitchen_sink_specs(sym, w, d, h) {
        let floor = push_sink_bowl(
            &mut bag.primary,
            origin,
            rot,
            Vec2::new(spec.lx, spec.ly),
            0.0,
            spec.w,
            spec.d,
            spec.depth,
        );
        bag.metal.push_cylinder(
            origin,
            rot,
            Vec3::new(floor.x, floor.y, floor.z),
            [0.032, 0.032],
            0.006,
            12,
        );
    }
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - 0.06, 0.0),
        [0.018, 0.015],
        0.20,
        12,
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - 0.11, 0.19),
        Vec3::new(0.024, 0.12, 0.024),
    );
}

fn build_refrigerator(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
) {
    bag.primary_mat = stainless_material(fx.fill_color);
    bag.metal_mat = chrome_material();
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.03, h * 0.5),
        Vec3::new(w, d - 0.06, h),
        0.008,
    );
    let fy = -d * 0.5 + 0.025;
    let fz_h = h * 0.30;
    let top_h = h - fz_h - 0.025;
    let top_cz = fz_h + 0.02 + top_h * 0.5;
    // Lower freezer drawer + French doors
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, fy, fz_h * 0.5 + 0.01),
        Vec3::new(w - 0.015, 0.05, fz_h - 0.015),
        0.005,
    );
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(-w * 0.25, fy, top_cz),
        Vec3::new(w * 0.485, 0.05, top_h),
        0.005,
    );
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(w * 0.25, fy, top_cz),
        Vec3::new(w * 0.485, 0.05, top_h),
        0.005,
    );
    // Dispenser recess + vertical/horizontal chrome handles
    bag.dark_glass.push_oriented_box(
        origin,
        rot,
        Vec3::new(-w * 0.25, fy - 0.022, top_cz + 0.05),
        Vec3::new(0.18, 0.012, 0.30),
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(-0.04, fy - 0.045, top_cz),
        Vec3::new(0.018, 0.028, top_h * 0.55),
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.04, fy - 0.045, top_cz),
        Vec3::new(0.018, 0.028, top_h * 0.55),
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, fy - 0.045, fz_h - 0.07),
        Vec3::new(w * 0.65, 0.028, 0.018),
    );
}

fn build_range_stove(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
) {
    bag.primary_mat = stainless_material(fx.fill_color);
    bag.metal_mat = hardware_material();
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h * 0.5),
        Vec3::new(w, d, h),
    );
    // Rear backsplash control hood + knobs
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - 0.04, h + 0.08),
        Vec3::new(w, 0.08, 0.16),
    );
    for i in 0..4 {
        let kx = -w * 0.34 + (i as f32) * (w * 0.22);
        bag.metal.push_cylinder(
            origin,
            rot,
            Vec3::new(kx, -d * 0.5 - 0.015, h - 0.06),
            [0.018, 0.018],
            0.02,
            10,
        );
    }
    // Dark cooktop surface + 4 burner grates
    bag.dark_glass.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, -0.02, h + 0.004),
        Vec3::new(w - 0.04, d - 0.10, 0.012),
    );
    for bx in [-w * 0.23, w * 0.23] {
        for by in [-d * 0.20, d * 0.14] {
            bag.metal.push_cylinder(
                origin,
                rot,
                Vec3::new(bx, by, h + 0.010),
                [0.08, 0.07],
                0.016,
                12,
            );
        }
    }
    // Oven glass window & handle at front (-Y)
    bag.dark_glass.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, -d * 0.5 - 0.006, h * 0.52),
        Vec3::new(w * 0.72, 0.016, h * 0.36),
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, -d * 0.5 - 0.036, h * 0.76),
        Vec3::new(w * 0.78, 0.025, 0.022),
    );
}

fn build_cooktop(bag: &mut PartBag, origin: Vec3, rot: f32, w: f32, d: f32, h: f32) {
    bag.dark_glass.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h * 0.5),
        Vec3::new(w, d, h.max(0.04)),
        0.008,
    );
    for bx in [-w * 0.26, w * 0.26] {
        for by in [-d * 0.22, d * 0.20] {
            bag.metal.push_cylinder(
                origin,
                rot,
                Vec3::new(bx, by, h.max(0.04)),
                [0.085, 0.075],
                0.012,
                14,
            );
        }
    }
}

fn build_wall_oven(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
) {
    bag.primary_mat = stainless_material(fx.fill_color);
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h * 0.5),
        Vec3::new(w, d, h),
    );
    for oz in [h * 0.30, h * 0.70] {
        bag.dark_glass.push_oriented_box(
            origin,
            rot,
            Vec3::new(0.0, -d * 0.5 - 0.006, oz),
            Vec3::new(w * 0.76, 0.016, h * 0.26),
        );
        bag.metal.push_oriented_box(
            origin,
            rot,
            Vec3::new(0.0, -d * 0.5 - 0.032, oz + h * 0.14),
            Vec3::new(w * 0.80, 0.022, 0.018),
        );
    }
}

fn build_dishwasher(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
) {
    bag.primary_mat = stainless_material(fx.fill_color);
    let body_h = (h - 0.038).max(0.50);
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, body_h * 0.5),
        Vec3::new(w, d, body_h),
    );
    bag.dark_glass.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, -d * 0.5 - 0.006, body_h - 0.045),
        Vec3::new(w - 0.02, 0.014, 0.05),
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, -d * 0.5 - 0.030, body_h - 0.12),
        Vec3::new(w * 0.76, 0.022, 0.018),
    );
}

fn build_range_hood(bag: &mut PartBag, origin: Vec3, rot: f32, w: f32, d: f32, h: f32) {
    bag.primary_mat = stainless_material(None);
    let canopy_h = h * 0.36;
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, canopy_h * 0.5),
        Vec3::new(w, d, canopy_h),
        canopy_h * 0.22,
    );
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.18, canopy_h + (h - canopy_h) * 0.5),
        Vec3::new(w * 0.38, d * 0.52, h - canopy_h),
    );
}

fn build_microwave(bag: &mut PartBag, origin: Vec3, rot: f32, w: f32, d: f32, h: f32) {
    bag.primary_mat = stainless_material(None);
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h * 0.5),
        Vec3::new(w, d, h),
        0.008,
    );
    bag.dark_glass.push_oriented_box(
        origin,
        rot,
        Vec3::new(-w * 0.10, -d * 0.5 - 0.006, h * 0.5),
        Vec3::new(w * 0.66, 0.012, h * 0.72),
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(w * 0.25, -d * 0.5 - 0.024, h * 0.5),
        Vec3::new(0.016, 0.022, h * 0.55),
    );
}

#[allow(clippy::too_many_arguments)]
fn build_laundry(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
    is_washer: bool,
) {
    bag.primary_mat = porcelain_material(fx.fill_color);
    let body_h = h * 0.90;
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, body_h * 0.5),
        Vec3::new(w, d, body_h),
        0.010,
    );
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - 0.06, body_h + h * 0.05),
        Vec3::new(w, 0.12, h * 0.10),
    );
    bag.dark_glass.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, -d * 0.5 + 0.01, h * 0.48),
        [w * 0.28, w * 0.28],
        0.02,
        16,
    );
    if is_washer {
        bag.metal.push_cylinder(
            origin,
            rot,
            Vec3::new(0.0, -d * 0.5, h * 0.48),
            [w * 0.31, w * 0.31],
            0.015,
            16,
        );
    } else {
        bag.metal.push_oriented_box(
            origin,
            rot,
            Vec3::new(w * 0.22, -d * 0.5 - 0.01, h * 0.50),
            Vec3::new(0.025, 0.018, 0.12),
        );
    }
}

fn build_water_heater(bag: &mut PartBag, origin: Vec3, rot: f32, w: f32, d: f32, h: f32) {
    bag.primary_mat = stainless_material(Some([0.78, 0.80, 0.82]));
    let r = (w.min(d) * 0.46).max(0.18);
    bag.primary
        .push_cylinder(origin, rot, Vec3::ZERO, [r, r], h * 0.90, 18);
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h * 0.90),
        [r * 0.22, r * 0.18],
        h * 0.10,
        12,
    );
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(-r * 0.45, 0.0, h * 0.90),
        [0.016, 0.016],
        0.12,
        8,
    );
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(r * 0.45, 0.0, h * 0.90),
        [0.016, 0.016],
        0.12,
        8,
    );
}

fn build_furnace(bag: &mut PartBag, origin: Vec3, rot: f32, w: f32, d: f32, h: f32) {
    bag.primary_mat = stainless_material(Some([0.55, 0.58, 0.62]));
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h * 0.42),
        Vec3::new(w, d, h * 0.84),
    );
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h * 0.92),
        Vec3::new(w * 0.78, d * 0.78, h * 0.16),
    );
    for lz in [0.18, 0.26, 0.34] {
        bag.dark_glass.push_oriented_box(
            origin,
            rot,
            Vec3::new(0.0, -d * 0.5 - 0.005, h * lz),
            Vec3::new(w * 0.72, 0.01, 0.025),
        );
    }
}

fn build_ac_unit(bag: &mut PartBag, origin: Vec3, rot: f32, w: f32, d: f32, h: f32) {
    bag.primary_mat = concrete_material();
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h * 0.5),
        Vec3::new(w, d, h),
        0.015,
    );
    bag.dark_glass.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h),
        [w * 0.34, w * 0.34],
        0.016,
        18,
    );
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h + 0.016),
        [w * 0.10, w * 0.08],
        0.018,
        12,
    );
}

fn build_seating(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
) {
    bag.primary_mat = upholstery_material(fx.fill_color);
    bag.accent_mat = wood_furniture_material(None);
    let leg_h = 0.12f32;
    for sx in [-w * 0.44, w * 0.44] {
        for sy in [-d * 0.40, d * 0.40] {
            bag.accent.push_cylinder(
                origin,
                rot,
                Vec3::new(sx, sy, 0.0),
                [0.022, 0.014],
                leg_h,
                8,
            );
        }
    }
    let seat_h = 0.24f32;
    let arm_w = (w * 0.11).clamp(0.10, 0.18);
    let back_d = (d * 0.20).clamp(0.14, 0.24);
    // Base deck + armrests + backrest (+Y)
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, leg_h + 0.08),
        Vec3::new(w, d, 0.16),
        0.015,
    );
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(-w * 0.5 + arm_w * 0.5, 0.0, leg_h + seat_h * 1.15),
        Vec3::new(arm_w, d, h * 0.56),
        0.025,
    );
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(w * 0.5 - arm_w * 0.5, 0.0, leg_h + seat_h * 1.15),
        Vec3::new(arm_w, d, h * 0.56),
        0.025,
    );
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - back_d * 0.5, leg_h + (h - leg_h) * 0.5),
        Vec3::new(w, back_d, h - leg_h),
        0.025,
    );

    // Individual seat & back cushions
    let inner_w = (w - 2.0 * arm_w - 0.02).max(0.30);
    let cushions = if w > 1.75 {
        3
    } else if w > 1.15 {
        2
    } else {
        1
    };
    let cw = inner_w / (cushions as f32);
    for c in 0..cushions {
        let cx = -inner_w * 0.5 + (c as f32 + 0.5) * cw;
        bag.primary.push_beveled_box(
            origin,
            rot,
            Vec3::new(cx, -back_d * 0.35, leg_h + 0.21),
            Vec3::new(cw - 0.02, d - back_d - 0.02, 0.14),
            0.025,
        );
        bag.primary.push_beveled_box(
            origin,
            rot,
            Vec3::new(cx, d * 0.5 - back_d - 0.09, h - 0.20),
            Vec3::new(cw - 0.03, 0.16, 0.36),
            0.025,
        );
    }
}

#[allow(clippy::too_many_arguments)]
fn build_table(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
    has_shelf: bool,
) {
    bag.primary_mat = wood_furniture_material(fx.fill_color);
    let top_t = 0.038f32;
    let leg_h = (h - top_t).max(0.20);
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h - top_t * 0.5),
        Vec3::new(w, d, top_t),
        0.008,
    );
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h - top_t - 0.035),
        Vec3::new(w * 0.88, d * 0.84, 0.06),
    );
    for sx in [-w * 0.42, w * 0.42] {
        for sy in [-d * 0.40, d * 0.40] {
            bag.primary.push_cylinder(
                origin,
                rot,
                Vec3::new(sx, sy, 0.0),
                [0.024, 0.034],
                leg_h,
                8,
            );
        }
    }
    if has_shelf {
        bag.primary.push_oriented_box(
            origin,
            rot,
            Vec3::new(0.0, 0.0, h * 0.26),
            Vec3::new(w * 0.84, d * 0.80, 0.024),
        );
    }
}

fn build_tv_console(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
) {
    bag.primary_mat = wood_furniture_material(fx.fill_color);
    let leg_h = 0.12f32;
    let cab_h = (h - leg_h).max(0.30);
    for sx in [-w * 0.44, w * 0.44] {
        for sy in [-d * 0.38, d * 0.38] {
            bag.metal.push_cylinder(
                origin,
                rot,
                Vec3::new(sx, sy, 0.0),
                [0.018, 0.018],
                leg_h,
                8,
            );
        }
    }
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, leg_h + cab_h * 0.5),
        Vec3::new(w, d, cab_h),
        0.01,
    );
    // Flat-screen TV mounted toward rear (+Y)
    let tv_w = (w * 0.78).max(0.65);
    let tv_h = tv_w * 0.56;
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.14, h + 0.08),
        Vec3::new(0.08, 0.04, 0.16),
    );
    bag.metal.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.14, h + 0.01),
        Vec3::new(0.35, 0.18, 0.02),
    );
    bag.dark_glass.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.14, h + 0.10 + tv_h * 0.5),
        Vec3::new(tv_w, 0.032, tv_h),
    );
}

fn build_bed(bag: &mut PartBag, fx: &FixtureIR, origin: Vec3, rot: f32, w: f32, d: f32, h: f32) {
    bag.primary_mat = wood_furniture_material(fx.fill_color);
    let frame_z = 0.14f32;
    let matt_h = 0.24f32;
    let hb_h = (h * 1.65).max(1.05);
    for sx in [-w * 0.45, w * 0.45] {
        for sy in [-d * 0.45, d * 0.45] {
            bag.primary.push_cylinder(
                origin,
                rot,
                Vec3::new(sx, sy, 0.0),
                [0.03, 0.035],
                frame_z,
                8,
            );
        }
    }
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, frame_z + 0.09),
        Vec3::new(w, d, 0.18),
        0.01,
    );
    // Tall paneled headboard at +Y back
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - 0.04, hb_h * 0.5),
        Vec3::new(w + 0.04, 0.08, hb_h),
        0.015,
    );
    // Mattress + duvet + pillows
    bag.soft.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, -0.02, frame_z + 0.18 + matt_h * 0.5),
        Vec3::new(w - 0.06, d - 0.10, matt_h),
        0.03,
    );
    bag.accent_mat = upholstery_material(Some([0.78, 0.80, 0.83]));
    bag.accent.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, -d * 0.12, frame_z + 0.18 + matt_h + 0.025),
        Vec3::new(w - 0.02, d * 0.68, 0.055),
        0.02,
    );
    let pillows = if w > 1.25 { 2 } else { 1 };
    let pw = (w - 0.24) / (pillows as f32);
    for p in 0..pillows {
        let px = -(w - 0.24) * 0.5 + (p as f32 + 0.5) * pw;
        bag.soft.push_beveled_box(
            origin,
            rot,
            Vec3::new(px, d * 0.5 - 0.28, frame_z + 0.18 + matt_h + 0.055),
            Vec3::new(pw - 0.06, 0.34, 0.11),
            0.03,
        );
    }
}

#[allow(clippy::too_many_arguments)]
fn build_casework(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
    is_dresser: bool,
) {
    bag.primary_mat = wood_furniture_material(fx.fill_color);
    bag.metal_mat = hardware_material();
    let leg_h = 0.08f32;
    let cab_h = (h - leg_h).max(0.24);
    for sx in [-w * 0.42, w * 0.42] {
        for sy in [-d * 0.38, d * 0.38] {
            bag.primary
                .push_cylinder(origin, rot, Vec3::new(sx, sy, 0.0), [0.02, 0.025], leg_h, 8);
        }
    }
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, leg_h + cab_h * 0.5),
        Vec3::new(w, d, cab_h),
        0.01,
    );
    let cols = if is_dresser && w > 0.90 { 2 } else { 1 };
    let rows = if is_dresser { 3 } else { 2 };
    let cw = (w - 0.04) / (cols as f32);
    let rh = (cab_h - 0.04) / (rows as f32);
    for c in 0..cols {
        let cx = -(w - 0.04) * 0.5 + (c as f32 + 0.5) * cw;
        for r in 0..rows {
            let cz = leg_h + 0.02 + (r as f32 + 0.5) * rh;
            bag.primary.push_beveled_box(
                origin,
                rot,
                Vec3::new(cx, -d * 0.5 - 0.008, cz),
                Vec3::new(cw - 0.02, 0.018, rh - 0.016),
                0.004,
            );
            bag.metal.push_oriented_box(
                origin,
                rot,
                Vec3::new(cx, -d * 0.5 - 0.024, cz),
                Vec3::new(cw * 0.30, 0.016, 0.014),
            );
        }
    }
}

fn build_dining_chair(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
) {
    bag.primary_mat = wood_furniture_material(fx.fill_color);
    bag.soft_mat = upholstery_material(Some([0.74, 0.72, 0.68]));
    let seat_z = 0.45f32;
    for sx in [-w * 0.40, w * 0.40] {
        for sy in [-d * 0.38, d * 0.38] {
            let lh = if sy > 0.0 { h } else { seat_z };
            bag.primary
                .push_cylinder(origin, rot, Vec3::new(sx, sy, 0.0), [0.018, 0.022], lh, 8);
        }
    }
    bag.soft.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, seat_z),
        Vec3::new(w * 0.92, d * 0.90, 0.06),
        0.015,
    );
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.38, h - 0.14),
        Vec3::new(w * 0.84, 0.03, 0.22),
    );
}

fn build_desk(bag: &mut PartBag, fx: &FixtureIR, origin: Vec3, rot: f32, w: f32, d: f32, h: f32) {
    bag.primary_mat = wood_furniture_material(fx.fill_color);
    bag.metal_mat = hardware_material();
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, h - 0.02),
        Vec3::new(w, d, 0.04),
        0.008,
    );
    // Left side panel + right 3-drawer pedestal
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(-w * 0.5 + 0.02, 0.0, (h - 0.04) * 0.5),
        Vec3::new(0.04, d - 0.04, h - 0.04),
    );
    let ped_w = (w * 0.28).clamp(0.32, 0.45);
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(w * 0.5 - ped_w * 0.5, 0.0, (h - 0.04) * 0.5),
        Vec3::new(ped_w, d - 0.02, h - 0.04),
    );
    for r in 0..3 {
        let dz = 0.12 + (r as f32) * ((h - 0.16) / 3.0);
        bag.metal.push_oriented_box(
            origin,
            rot,
            Vec3::new(w * 0.5 - ped_w * 0.5, -d * 0.5 - 0.01, dz),
            Vec3::new(ped_w * 0.45, 0.016, 0.014),
        );
    }
}

fn build_office_chair(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
) {
    bag.primary_mat = upholstery_material(fx.fill_color);
    bag.metal_mat = hardware_material();
    let seat_z = 0.46f32;
    // 5-star base + gas lift cylinder
    for i in 0..5 {
        let ang = (i as f32) * std::f32::consts::TAU / 5.0;
        let lx = (w * 0.24) * ang.cos();
        let ly = (d * 0.24) * ang.sin();
        bag.metal.push_oriented_box(
            origin,
            rot + ang,
            Vec3::new(lx * 0.5, ly * 0.5, 0.05),
            Vec3::new(w * 0.46, 0.036, 0.036),
        );
    }
    bag.metal.push_cylinder(
        origin,
        rot,
        Vec3::new(0.0, 0.0, 0.05),
        [0.026, 0.026],
        seat_z - 0.05,
        10,
    );
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, 0.0, seat_z),
        Vec3::new(w * 0.80, d * 0.80, 0.09),
        0.02,
    );
    bag.primary.push_beveled_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.34, seat_z + (h - seat_z) * 0.5),
        Vec3::new(w * 0.72, 0.08, h - seat_z),
        0.02,
    );
    for sx in [-w * 0.40, w * 0.40] {
        bag.metal.push_oriented_box(
            origin,
            rot,
            Vec3::new(sx, 0.0, seat_z + 0.16),
            Vec3::new(0.04, d * 0.52, 0.03),
        );
    }
}

fn build_bookshelf(
    bag: &mut PartBag,
    fx: &FixtureIR,
    origin: Vec3,
    rot: f32,
    w: f32,
    d: f32,
    h: f32,
) {
    bag.primary_mat = wood_furniture_material(fx.fill_color);
    bag.accent_mat = upholstery_material(Some([0.44, 0.52, 0.62]));
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(-w * 0.5 + 0.015, 0.0, h * 0.5),
        Vec3::new(0.03, d, h),
    );
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(w * 0.5 - 0.015, 0.0, h * 0.5),
        Vec3::new(0.03, d, h),
    );
    bag.primary.push_oriented_box(
        origin,
        rot,
        Vec3::new(0.0, d * 0.5 - 0.01, h * 0.5),
        Vec3::new(w, 0.02, h),
    );
    let shelves = 5;
    for s in 0..=shelves {
        let sz = 0.06 + (s as f32) * ((h - 0.09) / shelves as f32);
        bag.primary.push_oriented_box(
            origin,
            rot,
            Vec3::new(0.0, 0.0, sz),
            Vec3::new(w - 0.04, d - 0.02, 0.028),
        );
        if s < shelves - 1 {
            let bw = (w * 0.42).max(0.18);
            let xoff = if s % 2 == 0 { -w * 0.16 } else { w * 0.14 };
            bag.accent.push_oriented_box(
                origin,
                rot,
                Vec3::new(xoff, -0.02, sz + 0.13),
                Vec3::new(bw, d * 0.68, 0.22),
            );
        }
    }
}
