//! OpenGL 3.3 Core stylized architectural renderer cleanly decoupled from Python/PyO3.

pub mod camera;
pub mod loader;
pub mod offscreen;
pub mod shaders;

use std::num::NonZeroU32;

use estisketch_3d_core::{
    is_part_visible, BuiltSceneMesh, LevelBounds, MaterialDef, MaterialStyle, PickFilter,
    SceneSummary, SunIR,
};
use glam::{Mat4, Vec3};
use glow::HasContext;

pub use camera::{Camera3D, CameraMode, CameraPreset};
pub use offscreen::{render_offscreen, OffscreenImage};

const SHADOW_MAP_SIZE: i32 = 2048;

/// Visual presentation style selectable from the 3D viewport overlay bar.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum RenderStyle {
    Textured = 0,
    Clay = 1,
    Sketch = 2,
    XRay = 3,
}

impl RenderStyle {
    /// Parse a style identifier (`textured`, `clay`, `sketch`, `xray`).
    pub fn parse(name: &str) -> Result<Self, String> {
        match name.trim().to_lowercase().as_str() {
            "textured" | "default" => Ok(Self::Textured),
            "clay" | "white_model" => Ok(Self::Clay),
            "sketch" | "blueprint" => Ok(Self::Sketch),
            "xray" | "x-ray" | "ghosted" => Ok(Self::XRay),
            other => Err(format!("Unknown render style '{other}'")),
        }
    }
}

/// Lightweight renderer state snapshot usable without a live GL context.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RendererStatus {
    pub backend: &'static str,
    pub viewport_width: u32,
    pub viewport_height: u32,
    pub entity_count: usize,
    pub gl_initialized: bool,
}

/// Live GPU-side model matrix override used during 60 FPS drag/rotation previews.
#[derive(Clone, Debug, PartialEq)]
pub struct TransformPreview {
    /// Target `SceneIR` entity identifier being transformed.
    pub entity_id: String,
    /// Rotation pivot in world **meters** (Z-up).
    pub pivot_m: Vec3,
    /// Translation offset from initial state in **meters**.
    pub delta_pos_m: Vec3,
    /// Rotation delta around Z axis in **radians**.
    pub delta_rot_z_rad: f32,
}

impl TransformPreview {
    /// Compute the world model matrix applying rotation around `pivot_m` followed by translation.
    pub fn model_matrix(&self) -> Mat4 {
        Mat4::from_translation(self.pivot_m + self.delta_pos_m)
            * Mat4::from_rotation_z(self.delta_rot_z_rad)
            * Mat4::from_translation(-self.pivot_m)
    }
}

struct GpuPart {
    vao: glow::VertexArray,
    vbo: glow::Buffer,
    ebo: glow::Buffer,
    index_count: i32,
    entity_id: String,
    sub_part: String,
    level_id: String,
    is_roof_or_ceiling: bool,
    is_wall: bool,
    z_min_m: f32,
    z_max_m: f32,
    material: MaterialDef,
}

struct PostTargets {
    width: u32,
    height: u32,
    scene_fbo: glow::Framebuffer,
    scene_color_tex: glow::Texture,
    scene_normal_tex: glow::Texture,
    scene_depth_tex: glow::Texture,
    ssao_fbo: glow::Framebuffer,
    ssao_tex: glow::Texture,
    ssao_blur_fbo: glow::Framebuffer,
    ssao_blur_tex: glow::Texture,
}

unsafe fn create_tex_2d(
    gl: &glow::Context,
    internal_fmt: i32,
    width: i32,
    height: i32,
    format: u32,
    ty: u32,
    filter: i32,
) -> Result<glow::Texture, String> {
    let tex = gl
        .create_texture()
        .map_err(|e| format!("create post texture: {e}"))?;
    gl.bind_texture(glow::TEXTURE_2D, Some(tex));
    gl.tex_image_2d(
        glow::TEXTURE_2D,
        0,
        internal_fmt,
        width,
        height,
        0,
        format,
        ty,
        None,
    );
    gl.tex_parameter_i32(glow::TEXTURE_2D, glow::TEXTURE_MIN_FILTER, filter);
    gl.tex_parameter_i32(glow::TEXTURE_2D, glow::TEXTURE_MAG_FILTER, filter);
    gl.tex_parameter_i32(
        glow::TEXTURE_2D,
        glow::TEXTURE_WRAP_S,
        glow::CLAMP_TO_EDGE as i32,
    );
    gl.tex_parameter_i32(
        glow::TEXTURE_2D,
        glow::TEXTURE_WRAP_T,
        glow::CLAMP_TO_EDGE as i32,
    );
    gl.bind_texture(glow::TEXTURE_2D, None);
    Ok(tex)
}

impl PostTargets {
    fn create(gl: &glow::Context, width: u32, height: u32) -> Result<Self, String> {
        let w = width.max(1);
        let h = height.max(1);
        let hw = (w / 2).max(1);
        let hh = (h / 2).max(1);

        // SAFETY: Valid active OpenGL 3.3 context; all FBOs/textures are tracked in `PostTargets`
        // and explicitly destroyed on resize or GL teardown.
        unsafe {
            let raw_prev_fbo = gl.get_parameter_i32(glow::FRAMEBUFFER_BINDING) as u32;
            let prev_fbo = NonZeroU32::new(raw_prev_fbo).map(glow::NativeFramebuffer);

            let scene_color_tex = create_tex_2d(
                gl,
                glow::RGBA8 as i32,
                w as i32,
                h as i32,
                glow::RGBA,
                glow::UNSIGNED_BYTE,
                glow::LINEAR as i32,
            )?;
            let scene_normal_tex = create_tex_2d(
                gl,
                glow::RGBA16F as i32,
                w as i32,
                h as i32,
                glow::RGBA,
                glow::HALF_FLOAT,
                glow::NEAREST as i32,
            )?;
            let scene_depth_tex = create_tex_2d(
                gl,
                glow::DEPTH_COMPONENT24 as i32,
                w as i32,
                h as i32,
                glow::DEPTH_COMPONENT,
                glow::UNSIGNED_INT,
                glow::NEAREST as i32,
            )?;
            let scene_fbo = gl
                .create_framebuffer()
                .map_err(|e| format!("create scene fbo: {e}"))?;
            gl.bind_framebuffer(glow::FRAMEBUFFER, Some(scene_fbo));
            gl.framebuffer_texture_2d(
                glow::FRAMEBUFFER,
                glow::COLOR_ATTACHMENT0,
                glow::TEXTURE_2D,
                Some(scene_color_tex),
                0,
            );
            gl.framebuffer_texture_2d(
                glow::FRAMEBUFFER,
                glow::COLOR_ATTACHMENT1,
                glow::TEXTURE_2D,
                Some(scene_normal_tex),
                0,
            );
            gl.framebuffer_texture_2d(
                glow::FRAMEBUFFER,
                glow::DEPTH_ATTACHMENT,
                glow::TEXTURE_2D,
                Some(scene_depth_tex),
                0,
            );
            gl.draw_buffers(&[glow::COLOR_ATTACHMENT0, glow::COLOR_ATTACHMENT1]);
            let scene_status = gl.check_framebuffer_status(glow::FRAMEBUFFER);

            let ssao_tex = create_tex_2d(
                gl,
                glow::R8 as i32,
                hw as i32,
                hh as i32,
                glow::RED,
                glow::UNSIGNED_BYTE,
                glow::LINEAR as i32,
            )?;
            let ssao_fbo = gl
                .create_framebuffer()
                .map_err(|e| format!("create ssao fbo: {e}"))?;
            gl.bind_framebuffer(glow::FRAMEBUFFER, Some(ssao_fbo));
            gl.framebuffer_texture_2d(
                glow::FRAMEBUFFER,
                glow::COLOR_ATTACHMENT0,
                glow::TEXTURE_2D,
                Some(ssao_tex),
                0,
            );
            let ssao_status = gl.check_framebuffer_status(glow::FRAMEBUFFER);

            let ssao_blur_tex = create_tex_2d(
                gl,
                glow::R8 as i32,
                hw as i32,
                hh as i32,
                glow::RED,
                glow::UNSIGNED_BYTE,
                glow::LINEAR as i32,
            )?;
            let ssao_blur_fbo = gl
                .create_framebuffer()
                .map_err(|e| format!("create ssao blur fbo: {e}"))?;
            gl.bind_framebuffer(glow::FRAMEBUFFER, Some(ssao_blur_fbo));
            gl.framebuffer_texture_2d(
                glow::FRAMEBUFFER,
                glow::COLOR_ATTACHMENT0,
                glow::TEXTURE_2D,
                Some(ssao_blur_tex),
                0,
            );
            let blur_status = gl.check_framebuffer_status(glow::FRAMEBUFFER);
            gl.bind_framebuffer(glow::FRAMEBUFFER, prev_fbo);

            let out = Self {
                width: w,
                height: h,
                scene_fbo,
                scene_color_tex,
                scene_normal_tex,
                scene_depth_tex,
                ssao_fbo,
                ssao_tex,
                ssao_blur_fbo,
                ssao_blur_tex,
            };
            if scene_status != glow::FRAMEBUFFER_COMPLETE
                || ssao_status != glow::FRAMEBUFFER_COMPLETE
                || blur_status != glow::FRAMEBUFFER_COMPLETE
            {
                out.destroy(gl);
                return Err(format!(
                    "Incomplete post-process framebuffer (scene=0x{scene_status:x}, ssao=0x{ssao_status:x}, blur=0x{blur_status:x})"
                ));
            }
            Ok(out)
        }
    }

    fn destroy(self, gl: &glow::Context) {
        // SAFETY: Valid GL context owns all FBOs and textures stored in `PostTargets`.
        unsafe {
            gl.delete_framebuffer(self.scene_fbo);
            gl.delete_framebuffer(self.ssao_fbo);
            gl.delete_framebuffer(self.ssao_blur_fbo);
            gl.delete_texture(self.scene_color_tex);
            gl.delete_texture(self.scene_normal_tex);
            gl.delete_texture(self.scene_depth_tex);
            gl.delete_texture(self.ssao_tex);
            gl.delete_texture(self.ssao_blur_tex);
        }
    }
}

struct GlGpuState {
    gl: glow::Context,
    shadow_prog: glow::Program,
    sky_prog: glow::Program,
    scene_prog: glow::Program,
    ssao_prog: glow::Program,
    ssao_blur_prog: glow::Program,
    composite_prog: glow::Program,
    shadow_fbo: glow::Framebuffer,
    shadow_tex: glow::Texture,
    sky_vao: glow::VertexArray,
    post: Option<PostTargets>,
    parts: Vec<GpuPart>,
}

impl GlGpuState {
    fn init() -> Result<Self, String> {
        let gl = loader::load_gl_context()?;
        let shadow_prog = compile_program(&gl, shaders::SHADOW_VERT, shaders::SHADOW_FRAG)?;
        let sky_prog = compile_program(&gl, shaders::SKY_VERT, shaders::SKY_FRAG)?;
        let scene_prog = compile_program(&gl, shaders::SCENE_VERT, shaders::SCENE_FRAG)?;
        let ssao_prog = compile_program(&gl, shaders::POST_VERT, shaders::SSAO_FRAG)?;
        let ssao_blur_prog = compile_program(&gl, shaders::POST_VERT, shaders::SSAO_BLUR_FRAG)?;
        let composite_prog = compile_program(&gl, shaders::POST_VERT, shaders::COMPOSITE_FRAG)?;

        // SAFETY: Active GL 3.3 context is current inside Gtk.GLArea realize; resources are
        // explicitly released in `Self::destroy` on unrealize.
        unsafe {
            let raw_prev_fbo = gl.get_parameter_i32(glow::FRAMEBUFFER_BINDING) as u32;
            let prev_fbo = NonZeroU32::new(raw_prev_fbo).map(glow::NativeFramebuffer);

            let shadow_tex = gl
                .create_texture()
                .map_err(|e| format!("create shadow tex: {e}"))?;
            gl.bind_texture(glow::TEXTURE_2D, Some(shadow_tex));
            gl.tex_image_2d(
                glow::TEXTURE_2D,
                0,
                glow::DEPTH_COMPONENT24 as i32,
                SHADOW_MAP_SIZE,
                SHADOW_MAP_SIZE,
                0,
                glow::DEPTH_COMPONENT,
                glow::UNSIGNED_INT,
                None,
            );
            gl.tex_parameter_i32(
                glow::TEXTURE_2D,
                glow::TEXTURE_MIN_FILTER,
                glow::NEAREST as i32,
            );
            gl.tex_parameter_i32(
                glow::TEXTURE_2D,
                glow::TEXTURE_MAG_FILTER,
                glow::NEAREST as i32,
            );
            gl.tex_parameter_i32(
                glow::TEXTURE_2D,
                glow::TEXTURE_WRAP_S,
                glow::CLAMP_TO_BORDER as i32,
            );
            gl.tex_parameter_i32(
                glow::TEXTURE_2D,
                glow::TEXTURE_WRAP_T,
                glow::CLAMP_TO_BORDER as i32,
            );
            gl.tex_parameter_f32_slice(
                glow::TEXTURE_2D,
                glow::TEXTURE_BORDER_COLOR,
                &[1.0, 1.0, 1.0, 1.0],
            );

            let shadow_fbo = gl
                .create_framebuffer()
                .map_err(|e| format!("create shadow fbo: {e}"))?;
            gl.bind_framebuffer(glow::FRAMEBUFFER, Some(shadow_fbo));
            gl.framebuffer_texture_2d(
                glow::FRAMEBUFFER,
                glow::DEPTH_ATTACHMENT,
                glow::TEXTURE_2D,
                Some(shadow_tex),
                0,
            );
            gl.draw_buffer(glow::NONE);
            gl.read_buffer(glow::NONE);
            gl.bind_framebuffer(glow::FRAMEBUFFER, prev_fbo);
            gl.bind_texture(glow::TEXTURE_2D, None);

            let sky_vao = gl
                .create_vertex_array()
                .map_err(|e| format!("create sky vao: {e}"))?;

            Ok(Self {
                gl,
                shadow_prog,
                sky_prog,
                scene_prog,
                ssao_prog,
                ssao_blur_prog,
                composite_prog,
                shadow_fbo,
                shadow_tex,
                sky_vao,
                post: None,
                parts: Vec::new(),
            })
        }
    }

    fn upload_mesh(&mut self, mesh: &BuiltSceneMesh) -> Result<(), String> {
        self.clear_parts();
        let stride = std::mem::size_of::<estisketch_3d_core::Vertex>() as i32;
        for part in &mesh.parts {
            if part.vertices.is_empty() || part.indices.is_empty() {
                continue;
            }
            // SAFETY: Valid current GL context; vertex/index byte slices match POD structs.
            unsafe {
                let vao = self
                    .gl
                    .create_vertex_array()
                    .map_err(|e| format!("create vao: {e}"))?;
                let vbo = self
                    .gl
                    .create_buffer()
                    .map_err(|e| format!("create vbo: {e}"))?;
                let ebo = self
                    .gl
                    .create_buffer()
                    .map_err(|e| format!("create ebo: {e}"))?;

                self.gl.bind_vertex_array(Some(vao));
                self.gl.bind_buffer(glow::ARRAY_BUFFER, Some(vbo));
                self.gl.buffer_data_u8_slice(
                    glow::ARRAY_BUFFER,
                    bytemuck::cast_slice(&part.vertices),
                    glow::STATIC_DRAW,
                );

                self.gl.bind_buffer(glow::ELEMENT_ARRAY_BUFFER, Some(ebo));
                self.gl.buffer_data_u8_slice(
                    glow::ELEMENT_ARRAY_BUFFER,
                    bytemuck::cast_slice(&part.indices),
                    glow::STATIC_DRAW,
                );

                self.gl.enable_vertex_attrib_array(0);
                self.gl
                    .vertex_attrib_pointer_f32(0, 3, glow::FLOAT, false, stride, 0);
                self.gl.enable_vertex_attrib_array(1);
                self.gl
                    .vertex_attrib_pointer_f32(1, 3, glow::FLOAT, false, stride, 12);
                self.gl.enable_vertex_attrib_array(2);
                self.gl
                    .vertex_attrib_pointer_f32(2, 2, glow::FLOAT, false, stride, 24);
                self.gl.bind_vertex_array(None);

                self.parts.push(GpuPart {
                    vao,
                    vbo,
                    ebo,
                    index_count: part.indices.len() as i32,
                    entity_id: part.entity_id.clone(),
                    sub_part: part.sub_part.clone(),
                    level_id: part.level_id.clone(),
                    is_roof_or_ceiling: part.is_roof_or_ceiling,
                    is_wall: part.is_wall,
                    z_min_m: part.z_min_m,
                    z_max_m: part.z_max_m,
                    material: part.material.clone(),
                });
            }
        }
        Ok(())
    }

    fn clear_parts(&mut self) {
        // SAFETY: Current GL context owns all VAOs/VBOs/EBOs stored in `self.parts`.
        unsafe {
            self.gl.bind_vertex_array(None);
            for p in self.parts.drain(..) {
                self.gl.delete_vertex_array(p.vao);
                self.gl.delete_buffer(p.vbo);
                self.gl.delete_buffer(p.ebo);
            }
        }
    }

    fn destroy(mut self) {
        self.clear_parts();
        if let Some(post) = self.post.take() {
            post.destroy(&self.gl);
        }
        // SAFETY: Tearing down all GPU resources allocated in `init()` while GL context is current.
        unsafe {
            self.gl.delete_vertex_array(self.sky_vao);
            self.gl.delete_framebuffer(self.shadow_fbo);
            self.gl.delete_texture(self.shadow_tex);
            self.gl.delete_program(self.shadow_prog);
            self.gl.delete_program(self.sky_prog);
            self.gl.delete_program(self.scene_prog);
            self.gl.delete_program(self.ssao_prog);
            self.gl.delete_program(self.ssao_blur_prog);
            self.gl.delete_program(self.composite_prog);
        }
    }
}

/// Pure-Rust OpenGL 3.3 renderer controller paired with a `Gtk.GLArea` viewport.
pub struct GlRenderer {
    viewport_width: u32,
    viewport_height: u32,
    last_entity_count: usize,
    gpu: Option<GlGpuState>,
    scene_mesh: Option<BuiltSceneMesh>,
    mesh_dirty: bool,
    /// Interactive orbit / walkthrough camera.
    pub camera: Camera3D,
    /// Active presentation style.
    pub render_style: RenderStyle,
    /// Daylight hour (`6.0..=20.0`) modulating sun position.
    pub time_of_day_hour: f32,
    /// Optional Dollhouse active level ID hiding stories above that level.
    pub dollhouse_level_id: Option<String>,
    /// Automatically hide roofs & ceilings when viewing from above or slicing levels.
    pub auto_hide_roofs: bool,
    /// Latest world AABB minimum `[x, y, z]` in meters.
    pub bounds_min: [f32; 3],
    /// Latest world AABB maximum `[x, y, z]` in meters.
    pub bounds_max: [f32; 3],
    /// Level bounds sorted ascending for Dollhouse filtering.
    pub levels: Vec<LevelBounds>,
    /// Sun/north orientation from SceneIR.
    pub sun: SunIR,
    /// Entity IDs currently highlighted as selected in the 3D viewport.
    pub selected_entity_ids: Vec<String>,
    /// Hovered entity ID under the pointer in 3D view.
    pub hovered_entity_id: Option<String>,
    /// Hovered sub-part label (used by Paint Brush face-only hover tinting).
    pub hovered_sub_part: Option<String>,
    /// When true, only highlight the hovered sub-part rather than the whole entity.
    pub hover_sub_part_only: bool,
    /// Active 60 FPS GPU transform preview override for dragged/rotated fixtures.
    pub transform_preview: Option<TransformPreview>,
    /// Enable multi-pass Screen-Space Ambient Occlusion & bilateral blur post-processing.
    pub ssao_enabled: bool,
}

impl Default for GlRenderer {
    fn default() -> Self {
        Self::new(1, 1)
    }
}

impl GlRenderer {
    /// Construct a new uninitialized renderer with fallback dimensions `(w, h)`.
    pub fn new(viewport_width: u32, viewport_height: u32) -> Self {
        Self {
            viewport_width: viewport_width.max(1),
            viewport_height: viewport_height.max(1),
            last_entity_count: 0,
            gpu: None,
            scene_mesh: None,
            mesh_dirty: false,
            camera: Camera3D::default(),
            render_style: RenderStyle::Textured,
            time_of_day_hour: 13.5,
            dollhouse_level_id: None,
            auto_hide_roofs: true,
            bounds_min: [-4.0, -4.0, 0.0],
            bounds_max: [4.0, 4.0, 3.5],
            levels: Vec::new(),
            sun: SunIR::default(),
            selected_entity_ids: Vec::new(),
            hovered_entity_id: None,
            hovered_sub_part: None,
            hover_sub_part_only: false,
            transform_preview: None,
            ssao_enabled: true,
        }
    }

    /// Render the current scene headlessly via EGL to tightly packed RGBA8 pixels.
    pub fn render_offscreen_rgba(
        &mut self,
        width: u32,
        height: u32,
    ) -> Result<OffscreenImage, String> {
        render_offscreen(self, width, height)
    }

    /// Update viewport framebuffer dimensions in physical pixels.
    pub fn resize(&mut self, width: u32, height: u32) {
        self.viewport_width = width.max(1);
        self.viewport_height = height.max(1);
    }

    /// Record summary entity count metadata.
    pub fn sync_summary(&mut self, summary: &SceneSummary) {
        self.last_entity_count = summary.total_entities;
    }

    /// Queue a newly compiled [`BuiltSceneMesh`] for GPU upload on the next render frame.
    pub fn set_scene_mesh(&mut self, mesh: BuiltSceneMesh, sun: SunIR, auto_fit: bool) {
        self.bounds_min = mesh.bounds_min;
        self.bounds_max = mesh.bounds_max;
        self.levels = mesh.levels.clone();
        self.sun = sun;
        if auto_fit {
            self.camera.fit_bounds(self.bounds_min, self.bounds_max);
        }
        self.scene_mesh = Some(mesh);
        self.mesh_dirty = true;
    }

    /// Initialize OpenGL 3.3 Core shaders and shadow buffers inside active GL context.
    pub fn init_gl(&mut self) -> Result<(), String> {
        if let Some(old) = self.gpu.take() {
            old.destroy();
        }
        let mut gpu = GlGpuState::init()?;
        if let Some(ref mesh) = self.scene_mesh {
            gpu.upload_mesh(mesh)?;
        }
        self.mesh_dirty = false;
        self.gpu = Some(gpu);
        Ok(())
    }

    /// Release all GPU objects cleanly before destroying the OpenGL context.
    pub fn destroy_gl(&mut self) {
        if let Some(gpu) = self.gpu.take() {
            gpu.destroy();
        }
    }

    /// Reframe camera smoothly around the current scene bounding box.
    pub fn fit_scene(&mut self) {
        self.camera.fit_bounds(self.bounds_min, self.bounds_max);
    }

    /// Apply a standard architectural camera angle preset.
    pub fn set_camera_preset(&mut self, preset: CameraPreset) {
        self.camera
            .set_preset(preset, self.bounds_min, self.bounds_max);
    }

    /// Return current renderer status without requiring an active GL context.
    pub fn status(&self) -> RendererStatus {
        RendererStatus {
            backend: concat!("glow-", env!("CARGO_PKG_VERSION")),
            viewport_width: self.viewport_width,
            viewport_height: self.viewport_height,
            entity_count: self.last_entity_count,
            gl_initialized: self.gpu.is_some(),
        }
    }

    /// Compute normalized sun direction vector `[x, y, z]` toward sun from north angle + hour.
    pub fn active_sun_direction(&self) -> Vec3 {
        let h = self.time_of_day_hour.clamp(6.0, 20.0);
        let t = (h - 6.0) / 14.0; // 0 morning -> 1 evening
        let elev = (std::f32::consts::PI * t).sin() * 0.92 + 0.22; // 12 deg .. 65 deg
        let az = (-self.sun.north_angle_deg as f32).to_radians() + (-2.2 + t * 4.4);
        Vec3::new(elev.cos() * az.cos(), elev.cos() * az.sin(), elev.sin()).normalize_or_zero()
    }

    /// Compute active viewport aspect ratio (`width / height`).
    pub fn aspect_ratio(&self) -> f32 {
        (self.viewport_width as f32) / (self.viewport_height.max(1) as f32)
    }

    /// Unproject OpenGL NDC coordinates `(ndc_x, ndc_y)` into `(origin_m, dir_m)`.
    pub fn screen_ray(&self, ndc_x: f32, ndc_y: f32) -> (Vec3, Vec3) {
        self.camera.screen_ray(ndc_x, ndc_y, self.aspect_ratio())
    }

    /// Apply a zero-rebuild GPU model matrix offset for smooth 60 FPS interactive drags.
    pub fn set_transform_preview(
        &mut self,
        entity_id: String,
        pivot_m: [f32; 3],
        delta_pos_m: [f32; 3],
        delta_rot_z_rad: f32,
    ) {
        self.transform_preview = Some(TransformPreview {
            entity_id,
            pivot_m: Vec3::from_array(pivot_m),
            delta_pos_m: Vec3::from_array(delta_pos_m),
            delta_rot_z_rad,
        });
    }

    /// Build the active visibility filter matching Dollhouse & Auto-Hide Roofs state.
    pub fn active_pick_filter(&self) -> PickFilter {
        let hide_roofs = self.auto_hide_roofs
            && (self.camera.is_looking_down() || self.dollhouse_level_id.is_some());
        let level_cutoff_z_m = self.dollhouse_level_id.as_ref().and_then(|id| {
            self.levels
                .iter()
                .find(|lvl| lvl.id == *id)
                .map(|lvl| lvl.top_z_m)
        });
        PickFilter {
            hide_roofs,
            dollhouse_level_id: self.dollhouse_level_id.clone(),
            level_cutoff_z_m,
        }
    }

    fn part_visible(&self, part: &GpuPart, filter: &PickFilter) -> bool {
        is_part_visible(
            &part.level_id,
            part.is_roof_or_ceiling,
            part.z_min_m,
            part.z_max_m,
            filter,
        )
    }

    fn part_model_matrix(&self, entity_id: &str) -> Mat4 {
        if let Some(ref preview) = self.transform_preview {
            if preview.entity_id == entity_id {
                return preview.model_matrix();
            }
        }
        Mat4::IDENTITY
    }

    fn part_highlight_mode(&self, part: &GpuPart) -> i32 {
        if self
            .selected_entity_ids
            .iter()
            .any(|id| id == &part.entity_id)
        {
            return 2;
        }
        if self.hovered_entity_id.as_deref() == Some(part.entity_id.as_str())
            && (!self.hover_sub_part_only
                || self.hovered_sub_part.as_deref() == Some(part.sub_part.as_str()))
        {
            return 1;
        }
        0
    }

    /// Render shadow pass, backdrop, opaque geometry, and transparent glass into `Gtk.GLArea` FBO.
    pub fn render_gl(&mut self) -> Result<(), String> {
        let Some(mut gpu) = self.gpu.take() else {
            return Err("OpenGL renderer not initialized (call init_gl first)".to_string());
        };
        if self.mesh_dirty {
            if let Some(ref mesh) = self.scene_mesh {
                if let Err(err) = gpu.upload_mesh(mesh) {
                    self.gpu = Some(gpu);
                    return Err(err);
                }
            }
            self.mesh_dirty = false;
        }

        let sun_dir = self.active_sun_direction();
        let light_vp = compute_light_vp(self.bounds_min, self.bounds_max, sun_dir);
        let aspect = self.aspect_ratio();
        let view = self.camera.view_matrix();
        let proj = self.camera.proj_matrix(aspect);
        let vp = proj * view;
        let inv_vp = vp.inverse();
        let cam_pos = self.camera.eye_pos();

        let filter = self.active_pick_filter();
        let style_int = self.render_style as i32;

        // SAFETY: Valid current Gtk.GLArea OpenGL context; restore caller's DRAW_FRAMEBUFFER before
        // drawing final composited image so GTK4 or offscreen FBO readback works reliably.
        let need_rebuild_post = match gpu.post.as_ref() {
            Some(p) => p.width != self.viewport_width || p.height != self.viewport_height,
            None => true,
        };
        if need_rebuild_post {
            if let Some(old_post) = gpu.post.take() {
                old_post.destroy(&gpu.gl);
            }
            match PostTargets::create(&gpu.gl, self.viewport_width, self.viewport_height) {
                Ok(p) => gpu.post = Some(p),
                Err(err) => {
                    self.gpu = Some(gpu);
                    return Err(err);
                }
            }
        }
        let Some(ref post) = gpu.post else {
            self.gpu = Some(gpu);
            return Err("Post-processing targets missing".to_string());
        };

        let vp_w = self.viewport_width as i32;
        let vp_h = self.viewport_height as i32;
        let half_w = (self.viewport_width / 2).max(1) as i32;
        let half_h = (self.viewport_height / 2).max(1) as i32;

        unsafe {
            let gl = &gpu.gl;
            let raw_prev_fbo = gl.get_parameter_i32(glow::DRAW_FRAMEBUFFER_BINDING) as u32;
            let target_fbo = NonZeroU32::new(raw_prev_fbo).map(glow::NativeFramebuffer);

            // 1. Directional sun shadow pass
            gl.bind_framebuffer(glow::FRAMEBUFFER, Some(gpu.shadow_fbo));
            gl.viewport(0, 0, SHADOW_MAP_SIZE, SHADOW_MAP_SIZE);
            gl.enable(glow::DEPTH_TEST);
            gl.depth_mask(true);
            gl.disable(glow::BLEND);
            gl.clear(glow::DEPTH_BUFFER_BIT);
            gl.use_program(Some(gpu.shadow_prog));
            set_uniform_mat4(gl, gpu.shadow_prog, "u_light_vp", &light_vp);
            for part in &gpu.parts {
                if part.material.transparent || !self.part_visible(part, &filter) {
                    continue;
                }
                let model_mat = self.part_model_matrix(&part.entity_id);
                set_uniform_mat4(gl, gpu.shadow_prog, "u_model", &model_mat);
                gl.bind_vertex_array(Some(part.vao));
                gl.draw_elements(glow::TRIANGLES, part.index_count, glow::UNSIGNED_INT, 0);
            }

            // 2. MRT offscreen scene pass (Color + World Normal + Depth)
            gl.bind_framebuffer(glow::FRAMEBUFFER, Some(post.scene_fbo));
            gl.draw_buffers(&[glow::COLOR_ATTACHMENT0, glow::COLOR_ATTACHMENT1]);
            gl.viewport(0, 0, vp_w, vp_h);
            gl.clear_color(0.89, 0.91, 0.93, 1.0);
            gl.clear(glow::COLOR_BUFFER_BIT | glow::DEPTH_BUFFER_BIT);

            // 3. Sky & procedural architectural horizon backdrop
            gl.depth_mask(false);
            gl.disable(glow::DEPTH_TEST);
            gl.disable(glow::CULL_FACE);
            gl.use_program(Some(gpu.sky_prog));
            set_uniform_mat4(gl, gpu.sky_prog, "u_inv_vp", &inv_vp);
            if let Some(loc) = gl.get_uniform_location(gpu.sky_prog, "u_cam_pos") {
                gl.uniform_3_f32(Some(&loc), cam_pos.x, cam_pos.y, cam_pos.z);
            }
            if let Some(loc) = gl.get_uniform_location(gpu.sky_prog, "u_sun_dir") {
                gl.uniform_3_f32(Some(&loc), sun_dir.x, sun_dir.y, sun_dir.z);
            }
            if let Some(loc) = gl.get_uniform_location(gpu.sky_prog, "u_render_style") {
                gl.uniform_1_i32(Some(&loc), style_int);
            }
            gl.bind_vertex_array(Some(gpu.sky_vao));
            gl.draw_arrays(glow::TRIANGLES, 0, 3);

            // 4. Opaque stylized PBR pass
            gl.enable(glow::DEPTH_TEST);
            gl.depth_mask(true);
            gl.use_program(Some(gpu.scene_prog));
            set_uniform_mat4(gl, gpu.scene_prog, "u_vp", &vp);
            set_uniform_mat4(gl, gpu.scene_prog, "u_light_vp", &light_vp);
            if let Some(loc) = gl.get_uniform_location(gpu.scene_prog, "u_cam_pos") {
                gl.uniform_3_f32(Some(&loc), cam_pos.x, cam_pos.y, cam_pos.z);
            }
            if let Some(loc) = gl.get_uniform_location(gpu.scene_prog, "u_sun_dir") {
                gl.uniform_3_f32(Some(&loc), sun_dir.x, sun_dir.y, sun_dir.z);
            }
            if let Some(loc) = gl.get_uniform_location(gpu.scene_prog, "u_render_style") {
                gl.uniform_1_i32(Some(&loc), style_int);
            }
            gl.active_texture(glow::TEXTURE0);
            gl.bind_texture(glow::TEXTURE_2D, Some(gpu.shadow_tex));
            if let Some(loc) = gl.get_uniform_location(gpu.scene_prog, "u_shadow_map") {
                gl.uniform_1_i32(Some(&loc), 0);
            }

            let is_xray = self.render_style == RenderStyle::XRay;
            for part in &gpu.parts {
                if !self.part_visible(part, &filter) {
                    continue;
                }
                let is_trans = part.material.transparent
                    || part.material.style == MaterialStyle::Glass
                    || (is_xray && part.is_wall);
                if is_trans {
                    continue;
                }
                let model_mat = self.part_model_matrix(&part.entity_id);
                let hl_mode = self.part_highlight_mode(part);
                draw_gpu_part(gl, gpu.scene_prog, part, 1.0, &model_mat, hl_mode);
            }

            // 5. Transparent glass & X-Ray walls pass (write color only, preserve opaque normals)
            gl.draw_buffers(&[glow::COLOR_ATTACHMENT0]);
            gl.enable(glow::BLEND);
            gl.blend_func(glow::SRC_ALPHA, glow::ONE_MINUS_SRC_ALPHA);
            gl.depth_mask(false);
            for part in &gpu.parts {
                if !self.part_visible(part, &filter) {
                    continue;
                }
                let is_xray_wall = is_xray && part.is_wall;
                let is_glass =
                    part.material.transparent || part.material.style == MaterialStyle::Glass;
                if !is_xray_wall && !is_glass {
                    continue;
                }
                let alpha_ovr = if is_xray_wall { 0.25 } else { 1.0 };
                let model_mat = self.part_model_matrix(&part.entity_id);
                let hl_mode = self.part_highlight_mode(part);
                draw_gpu_part(gl, gpu.scene_prog, part, alpha_ovr, &model_mat, hl_mode);
            }
            gl.disable(glow::BLEND);
            gl.disable(glow::DEPTH_TEST);

            // 6. Half-resolution SSAO + Depth-aware bilateral blur
            if self.ssao_enabled {
                gl.bind_framebuffer(glow::FRAMEBUFFER, Some(post.ssao_fbo));
                gl.viewport(0, 0, half_w, half_h);
                gl.use_program(Some(gpu.ssao_prog));
                gl.active_texture(glow::TEXTURE0);
                gl.bind_texture(glow::TEXTURE_2D, Some(post.scene_depth_tex));
                if let Some(loc) = gl.get_uniform_location(gpu.ssao_prog, "u_depth_tex") {
                    gl.uniform_1_i32(Some(&loc), 0);
                }
                gl.active_texture(glow::TEXTURE1);
                gl.bind_texture(glow::TEXTURE_2D, Some(post.scene_normal_tex));
                if let Some(loc) = gl.get_uniform_location(gpu.ssao_prog, "u_normal_tex") {
                    gl.uniform_1_i32(Some(&loc), 1);
                }
                set_uniform_mat4(gl, gpu.ssao_prog, "u_vp", &vp);
                set_uniform_mat4(gl, gpu.ssao_prog, "u_inv_vp", &inv_vp);
                if let Some(loc) = gl.get_uniform_location(gpu.ssao_prog, "u_radius_m") {
                    gl.uniform_1_f32(Some(&loc), 0.55);
                }
                if let Some(loc) = gl.get_uniform_location(gpu.ssao_prog, "u_bias_m") {
                    gl.uniform_1_f32(Some(&loc), 0.025);
                }
                gl.bind_vertex_array(Some(gpu.sky_vao));
                gl.draw_arrays(glow::TRIANGLES, 0, 3);

                gl.bind_framebuffer(glow::FRAMEBUFFER, Some(post.ssao_blur_fbo));
                gl.use_program(Some(gpu.ssao_blur_prog));
                gl.active_texture(glow::TEXTURE0);
                gl.bind_texture(glow::TEXTURE_2D, Some(post.ssao_tex));
                if let Some(loc) = gl.get_uniform_location(gpu.ssao_blur_prog, "u_ssao_tex") {
                    gl.uniform_1_i32(Some(&loc), 0);
                }
                gl.active_texture(glow::TEXTURE1);
                gl.bind_texture(glow::TEXTURE_2D, Some(post.scene_depth_tex));
                if let Some(loc) = gl.get_uniform_location(gpu.ssao_blur_prog, "u_depth_tex") {
                    gl.uniform_1_i32(Some(&loc), 1);
                }
                if let Some(loc) = gl.get_uniform_location(gpu.ssao_blur_prog, "u_texel_size") {
                    gl.uniform_2_f32(Some(&loc), 1.0 / (half_w as f32), 1.0 / (half_h as f32));
                }
                gl.draw_arrays(glow::TRIANGLES, 0, 3);
            }

            // 7. Composite SSAO + silhouette crease outlines into caller's target FBO
            gl.bind_framebuffer(glow::FRAMEBUFFER, target_fbo);
            gl.viewport(0, 0, vp_w, vp_h);
            gl.use_program(Some(gpu.composite_prog));
            gl.active_texture(glow::TEXTURE0);
            gl.bind_texture(glow::TEXTURE_2D, Some(post.scene_color_tex));
            if let Some(loc) = gl.get_uniform_location(gpu.composite_prog, "u_color_tex") {
                gl.uniform_1_i32(Some(&loc), 0);
            }
            gl.active_texture(glow::TEXTURE1);
            gl.bind_texture(glow::TEXTURE_2D, Some(post.ssao_blur_tex));
            if let Some(loc) = gl.get_uniform_location(gpu.composite_prog, "u_ssao_tex") {
                gl.uniform_1_i32(Some(&loc), 1);
            }
            gl.active_texture(glow::TEXTURE2);
            gl.bind_texture(glow::TEXTURE_2D, Some(post.scene_normal_tex));
            if let Some(loc) = gl.get_uniform_location(gpu.composite_prog, "u_normal_tex") {
                gl.uniform_1_i32(Some(&loc), 2);
            }
            gl.active_texture(glow::TEXTURE3);
            gl.bind_texture(glow::TEXTURE_2D, Some(post.scene_depth_tex));
            if let Some(loc) = gl.get_uniform_location(gpu.composite_prog, "u_depth_tex") {
                gl.uniform_1_i32(Some(&loc), 3);
            }
            if let Some(loc) = gl.get_uniform_location(gpu.composite_prog, "u_texel_size") {
                gl.uniform_2_f32(Some(&loc), 1.0 / (vp_w as f32), 1.0 / (vp_h as f32));
            }
            if let Some(loc) = gl.get_uniform_location(gpu.composite_prog, "u_render_style") {
                gl.uniform_1_i32(Some(&loc), style_int);
            }
            if let Some(loc) = gl.get_uniform_location(gpu.composite_prog, "u_ssao_enabled") {
                gl.uniform_1_i32(Some(&loc), i32::from(self.ssao_enabled));
            }
            gl.bind_vertex_array(Some(gpu.sky_vao));
            gl.draw_arrays(glow::TRIANGLES, 0, 3);

            gl.active_texture(glow::TEXTURE0);
            gl.bind_texture(glow::TEXTURE_2D, None);
            gl.depth_mask(true);
            gl.enable(glow::DEPTH_TEST);
            gl.bind_vertex_array(None);
            gl.use_program(None);
        }

        self.gpu = Some(gpu);
        Ok(())
    }
}

unsafe fn draw_gpu_part(
    gl: &glow::Context,
    prog: glow::Program,
    part: &GpuPart,
    alpha_ovr: f32,
    model_mat: &Mat4,
    highlight_mode: i32,
) {
    set_uniform_mat4(gl, prog, "u_model", model_mat);
    if let Some(loc) = gl.get_uniform_location(prog, "u_highlight_mode") {
        gl.uniform_1_i32(Some(&loc), highlight_mode);
    }
    if let Some(loc) = gl.get_uniform_location(prog, "u_base_color") {
        let c = part.material.base_color;
        gl.uniform_4_f32(Some(&loc), c[0], c[1], c[2], c[3]);
    }
    if let Some(loc) = gl.get_uniform_location(prog, "u_roughness") {
        gl.uniform_1_f32(Some(&loc), part.material.roughness);
    }
    if let Some(loc) = gl.get_uniform_location(prog, "u_metallic") {
        gl.uniform_1_f32(Some(&loc), part.material.metallic);
    }
    if let Some(loc) = gl.get_uniform_location(prog, "u_mat_style") {
        gl.uniform_1_i32(Some(&loc), part.material.style as i32);
    }
    if let Some(loc) = gl.get_uniform_location(prog, "u_pattern_scale") {
        gl.uniform_1_f32(Some(&loc), part.material.pattern_scale);
    }
    if let Some(loc) = gl.get_uniform_location(prog, "u_pattern_rot_deg") {
        gl.uniform_1_f32(Some(&loc), part.material.pattern_rotation_deg);
    }
    if let Some(loc) = gl.get_uniform_location(prog, "u_alpha_override") {
        gl.uniform_1_f32(Some(&loc), alpha_ovr);
    }
    gl.bind_vertex_array(Some(part.vao));
    gl.draw_elements(glow::TRIANGLES, part.index_count, glow::UNSIGNED_INT, 0);
}

unsafe fn set_uniform_mat4(gl: &glow::Context, prog: glow::Program, name: &str, mat: &Mat4) {
    if let Some(loc) = gl.get_uniform_location(prog, name) {
        gl.uniform_matrix_4_f32_slice(Some(&loc), false, &mat.to_cols_array());
    }
}

fn compute_light_vp(min: [f32; 3], max: [f32; 3], sun_dir: Vec3) -> Mat4 {
    let vmin = Vec3::from_array(min);
    let vmax = Vec3::from_array(max);
    let center = 0.5 * (vmin + vmax);
    let radius = ((vmax - vmin).length() * 0.5).max(5.0);
    let eye = center + sun_dir * (radius * 2.5);
    let up = if sun_dir.z.abs() > 0.97 {
        Vec3::Y
    } else {
        Vec3::Z
    };
    let light_view = Mat4::look_at_rh(eye, center, up);
    let r = radius * 1.15;
    let light_proj = Mat4::orthographic_rh_gl(-r, r, -r, r, 0.2, radius * 5.5);
    light_proj * light_view
}

fn compile_program(
    gl: &glow::Context,
    vs_src: &str,
    fs_src: &str,
) -> Result<glow::Program, String> {
    // SAFETY: Caller has active OpenGL 3.3 Core context; handles deleted on error.
    unsafe {
        let prog = gl
            .create_program()
            .map_err(|e| format!("create program: {e}"))?;
        let vs = compile_shader(gl, glow::VERTEX_SHADER, vs_src)?;
        let fs = match compile_shader(gl, glow::FRAGMENT_SHADER, fs_src) {
            Ok(s) => s,
            Err(e) => {
                gl.delete_shader(vs);
                gl.delete_program(prog);
                return Err(e);
            }
        };
        gl.attach_shader(prog, vs);
        gl.attach_shader(prog, fs);
        gl.link_program(prog);
        gl.detach_shader(prog, vs);
        gl.detach_shader(prog, fs);
        gl.delete_shader(vs);
        gl.delete_shader(fs);
        if !gl.get_program_link_status(prog) {
            let log = gl.get_program_info_log(prog);
            gl.delete_program(prog);
            return Err(format!("Shader link error: {log}"));
        }
        Ok(prog)
    }
}

unsafe fn compile_shader(
    gl: &glow::Context,
    shader_type: u32,
    src: &str,
) -> Result<glow::Shader, String> {
    let shader = gl
        .create_shader(shader_type)
        .map_err(|e| format!("create shader: {e}"))?;
    gl.shader_source(shader, src);
    gl.compile_shader(shader);
    if !gl.get_shader_compile_status(shader) {
        let log = gl.get_shader_info_log(shader);
        gl.delete_shader(shader);
        return Err(format!("Shader compile error: {log}"));
    }
    Ok(shader)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn renderer_resize_and_sun_math() {
        let mut r = GlRenderer::new(0, 0);
        assert_eq!(r.status().viewport_width, 1);
        r.resize(1280, 720);
        assert_eq!(r.status().viewport_width, 1280);
        assert_eq!(r.status().viewport_height, 720);
        let sun_dir = r.active_sun_direction();
        assert!((sun_dir.length() - 1.0).abs() < 1e-4);
        assert!(sun_dir.z > 0.1);
    }

    #[test]
    fn render_style_parser() {
        assert_eq!(RenderStyle::parse("Clay").unwrap(), RenderStyle::Clay);
        assert_eq!(RenderStyle::parse("X-Ray").unwrap(), RenderStyle::XRay);
        assert!(RenderStyle::parse("unknown_mode").is_err());
    }
}
