//! Orbit/Dollhouse and First-Person Walkthrough cameras in centered Z-up meters.

use glam::{Mat4, Vec3};

/// Navigation mode for the 3D viewport camera.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum CameraMode {
    Orbit,
    Walkthrough,
}

/// Standard architectural viewing angle presets.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum CameraPreset {
    Iso,
    Top,
    Front,
    Back,
    Left,
    Right,
}

impl CameraPreset {
    /// Parse a UI preset string case-insensitively.
    pub fn parse(name: &str) -> Result<Self, String> {
        match name.trim().to_lowercase().as_str() {
            "iso" => Ok(Self::Iso),
            "top" => Ok(Self::Top),
            "front" => Ok(Self::Front),
            "back" => Ok(Self::Back),
            "left" => Ok(Self::Left),
            "right" => Ok(Self::Right),
            other => Err(format!("Unknown camera preset '{other}'")),
        }
    }
}

/// Interactive Z-up 3D camera supporting Orbit/Dollhouse and Walkthrough modes.
#[derive(Clone, Debug)]
pub struct Camera3D {
    /// Current navigation mode.
    pub mode: CameraMode,
    /// Orbit pivot target in meters (Z-up).
    pub target: Vec3,
    /// Orbit azimuth around +Z in **radians**.
    pub yaw_rad: f32,
    /// Orbit elevation angle above horizontal XY plane in **radians** (`+` = looking down).
    pub pitch_rad: f32,
    /// Distance from eye to orbit target in **meters**.
    pub distance_m: f32,
    /// First-person walkthrough eye world coordinates in **meters** (Z-up).
    pub walk_eye: Vec3,
    /// First-person look azimuth in **radians** (`0` looks along `+X`).
    pub walk_yaw_rad: f32,
    /// First-person look pitch in **radians** (`0` horizontal).
    pub walk_pitch_rad: f32,
    /// Vertical field of view in **degrees**.
    pub fov_deg: f32,
}

impl Default for Camera3D {
    fn default() -> Self {
        Self {
            mode: CameraMode::Orbit,
            target: Vec3::new(0.0, 0.0, 1.2),
            yaw_rad: -0.95,
            pitch_rad: 0.58,
            distance_m: 16.0,
            walk_eye: Vec3::new(0.0, -4.0, 1.676),
            walk_yaw_rad: std::f32::consts::FRAC_PI_2,
            walk_pitch_rad: 0.0,
            fov_deg: 45.0,
        }
    }
}

impl Camera3D {
    /// Switch between Orbit and Walkthrough navigation modes smoothly.
    pub fn set_mode(&mut self, mode: CameraMode) {
        if self.mode == mode {
            return;
        }
        if mode == CameraMode::Walkthrough {
            let eye = self.eye_pos();
            let dir = (self.target - eye).normalize_or_zero();
            self.walk_eye = Vec3::new(eye.x, eye.y, 1.676);
            if dir.length_squared() > 1e-4 {
                self.walk_yaw_rad = dir.y.atan2(dir.x);
                self.walk_pitch_rad = dir.z.clamp(-0.6, 0.6).asin();
            }
        } else {
            let fwd = self.walk_forward();
            self.target = self.walk_eye + fwd * 4.0;
            let rel = -fwd;
            self.yaw_rad = rel.y.atan2(rel.x);
            self.pitch_rad = (-self.walk_pitch_rad).clamp(-1.4, 1.52);
            self.distance_m = self.distance_m.clamp(4.0, 30.0);
        }
        self.mode = mode;
    }

    fn walk_forward(&self) -> Vec3 {
        let (sp, cp) = self.walk_pitch_rad.sin_cos();
        let (sy, cy) = self.walk_yaw_rad.sin_cos();
        Vec3::new(cp * cy, cp * sy, sp).normalize_or_zero()
    }

    /// Return current camera eye world coordinates in **meters**.
    pub fn eye_pos(&self) -> Vec3 {
        match self.mode {
            CameraMode::Orbit => {
                let (sp, cp) = self.pitch_rad.sin_cos();
                let (sy, cy) = self.yaw_rad.sin_cos();
                self.target + Vec3::new(cp * cy, cp * sy, sp) * self.distance_m
            }
            CameraMode::Walkthrough => self.walk_eye,
        }
    }

    /// Return true when orbiting from a steep downward dollhouse perspective.
    pub fn is_looking_down(&self) -> bool {
        self.mode == CameraMode::Orbit && self.pitch_rad > 0.55
    }

    /// Compute the Z-up right-handed view matrix.
    pub fn view_matrix(&self) -> Mat4 {
        let eye = self.eye_pos();
        match self.mode {
            CameraMode::Orbit => {
                let up = if self.pitch_rad.abs() > 1.48 {
                    let (sy, cy) = self.yaw_rad.sin_cos();
                    Vec3::new(-cy, -sy, 0.0)
                } else {
                    Vec3::Z
                };
                Mat4::look_at_rh(eye, self.target, up)
            }
            CameraMode::Walkthrough => {
                let fwd = self.walk_forward();
                Mat4::look_at_rh(eye, eye + fwd, Vec3::Z)
            }
        }
    }

    /// Compute the perspective projection matrix for OpenGL clip space (`-1..1`).
    pub fn proj_matrix(&self, aspect: f32) -> Mat4 {
        Mat4::perspective_rh_gl(self.fov_deg.to_radians(), aspect.max(0.05), 0.05, 500.0)
    }

    /// Rotate orbit camera (or walkthrough head) from mouse pixel delta `(dx, dy)`.
    pub fn orbit_drag(&mut self, dx: f32, dy: f32) {
        let sens = 0.0065;
        match self.mode {
            CameraMode::Orbit => {
                self.yaw_rad -= dx * sens;
                self.pitch_rad = (self.pitch_rad + dy * sens).clamp(-1.45, 1.54);
            }
            CameraMode::Walkthrough => {
                self.walk_yaw_rad -= dx * sens;
                self.walk_pitch_rad = (self.walk_pitch_rad - dy * sens).clamp(-1.35, 1.35);
            }
        }
    }

    /// Pan target parallel to ground/camera plane from mouse pixel delta `(dx, dy)`.
    pub fn pan_drag(&mut self, dx: f32, dy: f32) {
        let view = self.view_matrix();
        let right = Vec3::new(view.x_axis.x, view.y_axis.x, view.z_axis.x).normalize_or_zero();
        let cam_up = Vec3::new(view.x_axis.y, view.y_axis.y, view.z_axis.y).normalize_or_zero();
        let scale = match self.mode {
            CameraMode::Orbit => self.distance_m * 0.0016,
            CameraMode::Walkthrough => 0.015,
        };
        let shift = (-right * dx + cam_up * dy) * scale;
        match self.mode {
            CameraMode::Orbit => self.target += shift,
            CameraMode::Walkthrough => self.walk_eye += shift,
        }
    }

    /// Zoom toward target on scroll wheel delta (`+` zooms in).
    pub fn zoom_scroll(&mut self, delta: f32) {
        match self.mode {
            CameraMode::Orbit => {
                let factor = (1.0 - delta * 0.12).clamp(0.55, 1.45);
                self.distance_m = (self.distance_m * factor).clamp(0.6, 220.0);
            }
            CameraMode::Walkthrough => {
                let flat_fwd = Vec3::new(self.walk_yaw_rad.cos(), self.walk_yaw_rad.sin(), 0.0);
                self.walk_eye += flat_fwd * (delta * 0.6);
            }
        }
    }

    /// Translate eye/target incrementally in meters (used by keyboard `W/A/S/D/Q/E`).
    pub fn walk_move(&mut self, forward_m: f32, right_m: f32, up_m: f32) {
        match self.mode {
            CameraMode::Walkthrough => {
                let fwd = Vec3::new(self.walk_yaw_rad.cos(), self.walk_yaw_rad.sin(), 0.0);
                let right = Vec3::new(fwd.y, -fwd.x, 0.0);
                self.walk_eye += fwd * forward_m + right * right_m + Vec3::Z * up_m;
            }
            CameraMode::Orbit => {
                let yaw = self.yaw_rad + std::f32::consts::PI;
                let fwd = Vec3::new(yaw.cos(), yaw.sin(), 0.0);
                let right = Vec3::new(fwd.y, -fwd.x, 0.0);
                self.target += fwd * forward_m + right * right_m + Vec3::Z * up_m;
            }
        }
    }

    /// Frame the entire scene bounding box `[min, max]` in meters.
    pub fn fit_bounds(&mut self, min: [f32; 3], max: [f32; 3]) {
        let vmin = Vec3::from_array(min);
        let vmax = Vec3::from_array(max);
        let center = 0.5 * (vmin + vmax);
        let extent = (vmax - vmin).max(Vec3::splat(2.0));
        let radius = extent.length() * 0.5;
        self.mode = CameraMode::Orbit;
        self.target = center;
        self.distance_m =
            (radius / (0.5 * self.fov_deg.to_radians()).tan() * 1.15).clamp(3.0, 220.0);
    }

    /// Jump into first-person Walkthrough eye height (`1.676 m`) above a point.
    pub fn jump_to_point(&mut self, x_m: f32, y_m: f32, floor_z_m: f32) {
        self.mode = CameraMode::Walkthrough;
        self.walk_eye = Vec3::new(x_m, y_m, floor_z_m + 1.676);
        self.walk_pitch_rad = 0.0;
    }

    /// Apply a standard architectural viewing angle preset framed to scene bounds.
    pub fn set_preset(&mut self, preset: CameraPreset, min: [f32; 3], max: [f32; 3]) {
        self.fit_bounds(min, max);
        match preset {
            CameraPreset::Iso => {
                self.yaw_rad = -0.95;
                self.pitch_rad = 0.58;
            }
            CameraPreset::Top => {
                self.yaw_rad = -std::f32::consts::FRAC_PI_2;
                self.pitch_rad = 1.54;
            }
            CameraPreset::Front => {
                self.yaw_rad = -std::f32::consts::FRAC_PI_2;
                self.pitch_rad = 0.14;
            }
            CameraPreset::Back => {
                self.yaw_rad = std::f32::consts::FRAC_PI_2;
                self.pitch_rad = 0.14;
            }
            CameraPreset::Left => {
                self.yaw_rad = std::f32::consts::PI;
                self.pitch_rad = 0.14;
            }
            CameraPreset::Right => {
                self.yaw_rad = 0.0;
                self.pitch_rad = 0.14;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn camera_presets_and_fit_stay_finite() {
        let mut cam = Camera3D::default();
        for preset in [
            CameraPreset::Iso,
            CameraPreset::Top,
            CameraPreset::Front,
            CameraPreset::Back,
            CameraPreset::Left,
            CameraPreset::Right,
        ] {
            cam.set_preset(preset, [-6.0, -5.0, 0.0], [6.0, 5.0, 4.5]);
            let v = cam.view_matrix();
            let p = cam.proj_matrix(16.0 / 9.0);
            assert!(v.is_finite());
            assert!(p.is_finite());
        }
        assert!(cam.distance_m >= 3.0);
    }

    #[test]
    fn walkthrough_jump_sets_eye_height() {
        let mut cam = Camera3D::default();
        cam.jump_to_point(1.5, -2.0, 2.7);
        assert_eq!(cam.mode, CameraMode::Walkthrough);
        assert!((cam.eye_pos().z - 4.376).abs() < 1e-4);
    }
}
