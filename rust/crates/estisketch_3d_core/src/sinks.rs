//! Procedural sink bowls and the countertop / cabinet cutouts that expose them.
//!
//! Coordinate invariant (fixture-local space, meters): origin at the fixture center, `-Y` faces
//! the room, `+Y` faces the host wall, `+Z` up. For countertop sinks the local `z_top` is the
//! countertop surface height relative to the fixture origin.

use glam::{Vec2, Vec3};

use crate::mesh::MeshBuilder;
use crate::scene_ir::FixtureIR;

/// Sink bowl placement in fixture-local space (meters).
#[derive(Clone, Copy, Debug)]
pub struct SinkSpec {
    /// Bowl center X in fixture-local space.
    pub lx: f32,
    /// Bowl center Y in fixture-local space.
    pub ly: f32,
    /// Opening width along local X.
    pub w: f32,
    /// Opening depth along local Y.
    pub d: f32,
    /// Bowl depth below the countertop surface.
    pub depth: f32,
}

/// Sink opening in world space (meters, Z-up) used to cut countertops and cabinet carcasses.
#[derive(Clone, Copy, Debug)]
pub struct SinkCut {
    /// Opening center in world XY.
    pub center: Vec2,
    /// Rotation about Z in radians.
    pub rot_z: f32,
    /// Opening width along the rotated X axis.
    pub w: f32,
    /// Opening depth along the rotated Y axis.
    pub d: f32,
}

impl SinkCut {
    /// Opening corners in world XY, counter-clockwise.
    pub fn corners(&self) -> Vec<[f64; 2]> {
        rect_world(self.center, self.rot_z, self.w, self.d)
    }

    /// True when world point `p` lies inside this opening grown by `margin` meters.
    pub fn contains(&self, p: Vec2, margin: f32) -> bool {
        let (sr, cr) = self.rot_z.sin_cos();
        let rel = p - self.center;
        let lx = rel.x * cr + rel.y * sr;
        let ly = -rel.x * sr + rel.y * cr;
        lx.abs() <= self.w * 0.5 + margin && ly.abs() <= self.d * 0.5 + margin
    }
}

/// Counter-clockwise rectangle (`w` x `d`) centered at `center`, rotated by `rot_z`.
pub fn rect_world(center: Vec2, rot_z: f32, w: f32, d: f32) -> Vec<[f64; 2]> {
    let (sr, cr) = rot_z.sin_cos();
    [(-1.0f32, -1.0f32), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        .iter()
        .map(|&(sx, sy)| {
            let lx = sx * w * 0.5;
            let ly = sy * d * 0.5;
            [
                (center.x + lx * cr - ly * sr) as f64,
                (center.y + lx * sr + ly * cr) as f64,
            ]
        })
        .collect()
}

/// Sink bowls built into a cabinet (`sink_base_cabinet`, vanities); empty for other symbols.
pub fn cabinet_sink_specs(symbol_type: &str, w: f32, d: f32) -> Vec<SinkSpec> {
    let sym = symbol_type.to_lowercase();
    let bd = (d * 0.60).min(0.42);
    match sym.as_str() {
        "sink_base_cabinet" if w >= 0.838 => {
            let bw = (w * 0.38).min(0.40);
            [-w * 0.22, w * 0.22]
                .iter()
                .map(|&lx| SinkSpec {
                    lx,
                    ly: -0.02,
                    w: bw,
                    d: bd,
                    depth: 0.20,
                })
                .collect()
        }
        "sink_base_cabinet" => vec![SinkSpec {
            lx: 0.0,
            ly: -0.02,
            w: (w * 0.78).min(0.76),
            d: bd,
            depth: 0.20,
        }],
        "vanity_single" => vec![SinkSpec {
            lx: 0.0,
            ly: -0.02,
            w: (w * 0.56).min(0.56),
            d: bd.min(0.40),
            depth: 0.13,
        }],
        "vanity_double" => {
            let bw = (w * 0.34).min(0.48);
            [-w * 0.24, w * 0.24]
                .iter()
                .map(|&lx| SinkSpec {
                    lx,
                    ly: -0.02,
                    w: bw,
                    d: bd.min(0.40),
                    depth: 0.13,
                })
                .collect()
        }
        _ => Vec::new(),
    }
}

/// Bowls of a drop-in `kitchen_sink_single` / `kitchen_sink_double` (origin at counter top).
pub fn kitchen_sink_specs(symbol_type: &str, w: f32, d: f32, h: f32) -> Vec<SinkSpec> {
    let sym = symbol_type.to_lowercase();
    let depth = (h - 0.02).clamp(0.12, 0.25);
    let bd = (d - 0.14).max(0.20);
    match sym.as_str() {
        "kitchen_sink_single" => vec![SinkSpec {
            lx: 0.0,
            ly: -0.03,
            w: (w - 0.08).max(0.25),
            d: bd,
            depth,
        }],
        "kitchen_sink_double" => {
            let bw = ((w - 0.12) * 0.5).max(0.22);
            [-(bw * 0.5 + 0.02), bw * 0.5 + 0.02]
                .iter()
                .map(|&lx| SinkSpec {
                    lx,
                    ly: -0.03,
                    w: bw,
                    d: bd,
                    depth,
                })
                .collect()
        }
        _ => Vec::new(),
    }
}

/// World-space sink openings contributed by `fx` (cabinet-built-in or drop-in kitchen sinks).
pub fn fixture_sink_cuts(fx: &FixtureIR) -> Vec<SinkCut> {
    let w = fx.width_m as f32;
    let d = fx.depth_m as f32;
    let mut specs = cabinet_sink_specs(&fx.symbol_type, w, d);
    if specs.is_empty() {
        specs = kitchen_sink_specs(&fx.symbol_type, w, d, fx.height_m as f32);
    }
    let rot = fx.rot_z_rad as f32;
    let (sr, cr) = rot.sin_cos();
    let origin = Vec2::new(fx.loc_m[0] as f32, fx.loc_m[1] as f32);
    specs
        .iter()
        .map(|s| SinkCut {
            center: origin + Vec2::new(s.lx * cr - s.ly * sr, s.lx * sr + s.ly * cr),
            rot_z: rot,
            w: s.w,
            d: s.d,
        })
        .collect()
}

fn push_facing(mb: &mut MeshBuilder, p: [Vec3; 4], toward: Vec3) {
    let normal = (p[1] - p[0]).cross(p[2] - p[0]);
    if normal.dot(toward - p[0]) >= 0.0 {
        mb.push_quad(p[0], p[1], p[2], p[3]);
    } else {
        mb.push_quad(p[3], p[2], p[1], p[0]);
    }
}

/// Emit a tapered sink bowl (sloped walls, flat floor, raised rim flange).
///
/// `z_top` is the countertop surface height in fixture-local space; the bowl extends `depth`
/// meters below it. Returns the local floor center so callers can place a drain there.
#[allow(clippy::too_many_arguments)]
pub fn push_sink_bowl(
    basin: &mut MeshBuilder,
    origin: Vec3,
    rot_z: f32,
    center: Vec2,
    z_top: f32,
    w: f32,
    d: f32,
    depth: f32,
) -> Vec3 {
    let (sr, cr) = rot_z.sin_cos();
    let to_world = |lx: f32, ly: f32, lz: f32| -> Vec3 {
        origin + Vec3::new(lx * cr - ly * sr, lx * sr + ly * cr, lz)
    };
    let ow = w * 0.5;
    let od = d * 0.5;
    let fw = ow * 0.76;
    let fd = od * 0.72;
    let z_bot = z_top - depth;
    let signs = [(-1.0f32, -1.0f32), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)];
    let top: Vec<Vec3> = signs
        .iter()
        .map(|&(sx, sy)| to_world(center.x + sx * ow, center.y + sy * od, z_top))
        .collect();
    let floor: Vec<Vec3> = signs
        .iter()
        .map(|&(sx, sy)| to_world(center.x + sx * fw, center.y + sy * fd, z_bot))
        .collect();
    let inside = to_world(center.x, center.y, z_bot + depth * 0.5);
    for i in 0..4 {
        let j = (i + 1) % 4;
        push_facing(basin, [top[i], top[j], floor[j], floor[i]], inside);
    }
    push_facing(
        basin,
        [floor[0], floor[1], floor[2], floor[3]],
        inside + Vec3::Z,
    );

    // Raised rim flange resting on the countertop around the opening.
    let rw = 0.022f32;
    let rh = 0.006f32;
    let zc = z_top + rh * 0.5;
    let off = |x: f32, y: f32| Vec3::new(center.x + x, center.y + y, zc);
    basin.push_oriented_box(
        origin,
        rot_z,
        off(0.0, -(od + rw * 0.5)),
        Vec3::new(w + 2.0 * rw, rw, rh),
    );
    basin.push_oriented_box(
        origin,
        rot_z,
        off(0.0, od + rw * 0.5),
        Vec3::new(w + 2.0 * rw, rw, rh),
    );
    basin.push_oriented_box(
        origin,
        rot_z,
        off(-(ow + rw * 0.5), 0.0),
        Vec3::new(rw, d, rh),
    );
    basin.push_oriented_box(origin, rot_z, off(ow + rw * 0.5, 0.0), Vec3::new(rw, d, rh));
    Vec3::new(center.x, center.y, z_bot)
}

/// Emit a recessed basin slab: a thick rectangular slab with a rectangular cavity and a floor.
///
/// Used by pedestal and utility sinks whose bowl is carved into the visible top block.
#[allow(clippy::too_many_arguments)]
pub fn push_recessed_basin(
    mb: &mut MeshBuilder,
    origin: Vec3,
    rot_z: f32,
    w: f32,
    d: f32,
    z_bot: f32,
    z_top: f32,
    wall: f32,
    floor_thick: f32,
) -> Vec3 {
    let center = Vec2::new(origin.x, origin.y);
    let outer = rect_world(center, rot_z, w, d);
    let hole = rect_world(
        center,
        rot_z,
        (w - 2.0 * wall).max(0.05),
        (d - 2.0 * wall).max(0.05),
    );
    mb.push_extruded_polygon(&outer, &[hole], origin.z + z_bot, origin.z + z_top);
    let (sr, cr) = rot_z.sin_cos();
    let hw = ((w - 2.0 * wall) * 0.5).max(0.025);
    let hd = ((d - 2.0 * wall) * 0.5).max(0.025);
    let zf = origin.z + z_bot + floor_thick;
    let corners: Vec<Vec3> = [(-1.0f32, -1.0f32), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        .iter()
        .map(|&(sx, sy)| {
            let lx = sx * hw;
            let ly = sy * hd;
            Vec3::new(
                center.x + lx * cr - ly * sr,
                center.y + lx * sr + ly * cr,
                zf,
            )
        })
        .collect();
    push_facing(
        mb,
        [corners[0], corners[1], corners[2], corners[3]],
        Vec3::new(center.x, center.y, zf + 1.0),
    );
    Vec3::new(0.0, 0.0, z_bot + floor_thick)
}
