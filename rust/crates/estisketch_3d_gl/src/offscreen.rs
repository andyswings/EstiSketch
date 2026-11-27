//! Headless OpenGL 3.3 offscreen rendering using Linux EGL (Mesa / hardware GPU) for tests and snapshots.

use std::ffi::{c_char, c_int, c_uint, c_void, CString};

use glow::HasContext;

use crate::GlRenderer;

/// Rendered offscreen RGBA8 image buffer with top-left pixel origin.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OffscreenImage {
    /// Image width in pixels.
    pub width: u32,
    /// Image height in pixels.
    pub height: u32,
    /// Tightly packed RGBA8 pixel rows (length `width * height * 4`), row 0 at top.
    pub rgba: Vec<u8>,
}

/// Render `renderer`'s current compiled scene headlessly to an RGBA8 image of size `(width, height)`.
///
/// Uses a temporary offscreen EGL context and FBO on Linux without requiring X11/GTK4 windows, and
/// leaves `renderer`'s GL resource state clean upon return.
pub fn render_offscreen(
    renderer: &mut GlRenderer,
    width: u32,
    height: u32,
) -> Result<OffscreenImage, String> {
    #[cfg(target_os = "linux")]
    {
        render_offscreen_linux_egl(renderer, width.max(1), height.max(1))
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = (renderer, width, height);
        Err("Headless offscreen EGL rendering is currently supported on Linux only".to_string())
    }
}

#[cfg(target_os = "linux")]
fn render_offscreen_linux_egl(
    renderer: &mut GlRenderer,
    width: u32,
    height: u32,
) -> Result<OffscreenImage, String> {
    type EglDisplay = *mut c_void;
    type EglConfig = *mut c_void;
    type EglSurface = *mut c_void;
    type EglContext = *mut c_void;

    const EGL_OPENGL_API: c_uint = 0x30A2;
    const EGL_PLATFORM_SURFACELESS_MESA: c_uint = 0x31DD;
    const EGL_NONE: c_int = 0x3038;
    const EGL_TRUE: c_uint = 1;
    const EGL_SURFACE_TYPE: c_int = 0x3033;
    const EGL_PBUFFER_BIT: c_int = 0x0001;
    const EGL_RENDERABLE_TYPE: c_int = 0x3040;
    const EGL_OPENGL_BIT: c_int = 0x0008;
    const EGL_RED_SIZE: c_int = 0x3024;
    const EGL_GREEN_SIZE: c_int = 0x3023;
    const EGL_BLUE_SIZE: c_int = 0x3022;
    const EGL_ALPHA_SIZE: c_int = 0x3021;
    const EGL_DEPTH_SIZE: c_int = 0x3025;
    const EGL_WIDTH: c_int = 0x3057;
    const EGL_HEIGHT: c_int = 0x3056;
    const EGL_CONTEXT_MAJOR_VERSION: c_int = 0x3098;
    const EGL_CONTEXT_MINOR_VERSION: c_int = 0x30FB;
    const EGL_CONTEXT_OPENGL_PROFILE_MASK: c_int = 0x30FD;
    const EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT: c_int = 0x0000_0001;

    type FnEglGetDisplay = unsafe extern "C" fn(*mut c_void) -> EglDisplay;
    type FnEglGetPlatformDisplay =
        unsafe extern "C" fn(c_uint, *mut c_void, *const isize) -> EglDisplay;
    type FnEglInitialize = unsafe extern "C" fn(EglDisplay, *mut c_int, *mut c_int) -> c_uint;
    type FnEglTerminate = unsafe extern "C" fn(EglDisplay) -> c_uint;
    type FnEglBindApi = unsafe extern "C" fn(c_uint) -> c_uint;
    type FnEglChooseConfig =
        unsafe extern "C" fn(EglDisplay, *const c_int, *mut EglConfig, c_int, *mut c_int) -> c_uint;
    type FnEglCreatePbufferSurface =
        unsafe extern "C" fn(EglDisplay, EglConfig, *const c_int) -> EglSurface;
    type FnEglDestroySurface = unsafe extern "C" fn(EglDisplay, EglSurface) -> c_uint;
    type FnEglCreateContext =
        unsafe extern "C" fn(EglDisplay, EglConfig, EglContext, *const c_int) -> EglContext;
    type FnEglDestroyContext = unsafe extern "C" fn(EglDisplay, EglContext) -> c_uint;
    type FnEglMakeCurrent =
        unsafe extern "C" fn(EglDisplay, EglSurface, EglSurface, EglContext) -> c_uint;
    type FnEglGetProcAddress = unsafe extern "C" fn(*const c_char) -> *const c_void;
    type FnEglGetError = unsafe extern "C" fn() -> c_int;

    struct EglGuard {
        dpy: EglDisplay,
        surf: EglSurface,
        ctx: EglContext,
        destroy_surf: FnEglDestroySurface,
        destroy_ctx: FnEglDestroyContext,
        make_current: FnEglMakeCurrent,
        terminate: FnEglTerminate,
    }

    impl Drop for EglGuard {
        fn drop(&mut self) {
            // SAFETY: Valid initialized EGL display/context/surface handles acquired in parent scope.
            unsafe {
                (self.make_current)(
                    self.dpy,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                );
                if !self.ctx.is_null() {
                    (self.destroy_ctx)(self.dpy, self.ctx);
                }
                if !self.surf.is_null() {
                    (self.destroy_surf)(self.dpy, self.surf);
                }
                if !self.dpy.is_null() {
                    (self.terminate)(self.dpy);
                }
            }
        }
    }

    // SAFETY: Standard Linux EGL dynamic library lookup; cleaned up via EglGuard before return.
    let egl_lib = unsafe { libloading::Library::new("libEGL.so.1") }
        .map_err(|e| format!("Failed to load libEGL.so.1: {e}"))?;

    // SAFETY: Resolving standard EGL 1.4/1.5 symbols from loaded `libEGL.so.1`.
    let (
        egl_get_display,
        egl_get_platform_display,
        egl_initialize,
        egl_terminate,
        egl_bind_api,
        egl_choose_config,
        egl_create_pbuffer,
        egl_destroy_surface,
        egl_create_context,
        egl_destroy_context,
        egl_make_current,
        egl_get_proc,
        egl_get_error,
    ) = unsafe {
        let sym_get_display = *egl_lib
            .get::<FnEglGetDisplay>(b"eglGetDisplay\0")
            .map_err(|e| format!("eglGetDisplay: {e}"))?;
        let sym_get_platform = egl_lib
            .get::<FnEglGetPlatformDisplay>(b"eglGetPlatformDisplay\0")
            .ok()
            .map(|s| *s);
        let sym_init = *egl_lib
            .get::<FnEglInitialize>(b"eglInitialize\0")
            .map_err(|e| format!("eglInitialize: {e}"))?;
        let sym_term = *egl_lib
            .get::<FnEglTerminate>(b"eglTerminate\0")
            .map_err(|e| format!("eglTerminate: {e}"))?;
        let sym_bind = *egl_lib
            .get::<FnEglBindApi>(b"eglBindAPI\0")
            .map_err(|e| format!("eglBindAPI: {e}"))?;
        let sym_choose = *egl_lib
            .get::<FnEglChooseConfig>(b"eglChooseConfig\0")
            .map_err(|e| format!("eglChooseConfig: {e}"))?;
        let sym_pbuf = *egl_lib
            .get::<FnEglCreatePbufferSurface>(b"eglCreatePbufferSurface\0")
            .map_err(|e| format!("eglCreatePbufferSurface: {e}"))?;
        let sym_dsurf = *egl_lib
            .get::<FnEglDestroySurface>(b"eglDestroySurface\0")
            .map_err(|e| format!("eglDestroySurface: {e}"))?;
        let sym_ctx = *egl_lib
            .get::<FnEglCreateContext>(b"eglCreateContext\0")
            .map_err(|e| format!("eglCreateContext: {e}"))?;
        let sym_dctx = *egl_lib
            .get::<FnEglDestroyContext>(b"eglDestroyContext\0")
            .map_err(|e| format!("eglDestroyContext: {e}"))?;
        let sym_mk = *egl_lib
            .get::<FnEglMakeCurrent>(b"eglMakeCurrent\0")
            .map_err(|e| format!("eglMakeCurrent: {e}"))?;
        let sym_proc = *egl_lib
            .get::<FnEglGetProcAddress>(b"eglGetProcAddress\0")
            .map_err(|e| format!("eglGetProcAddress: {e}"))?;
        let sym_err = *egl_lib
            .get::<FnEglGetError>(b"eglGetError\0")
            .map_err(|e| format!("eglGetError: {e}"))?;
        (
            sym_get_display,
            sym_get_platform,
            sym_init,
            sym_term,
            sym_bind,
            sym_choose,
            sym_pbuf,
            sym_dsurf,
            sym_ctx,
            sym_dctx,
            sym_mk,
            sym_proc,
            sym_err,
        )
    };

    // Prefer surfaceless Mesa display when available, otherwise default display.
    // SAFETY: Standard EGL display creation with valid constants/null arguments.
    let mut dpy = unsafe {
        if let Some(get_plat) = egl_get_platform_display {
            get_plat(
                EGL_PLATFORM_SURFACELESS_MESA,
                std::ptr::null_mut(),
                std::ptr::null(),
            )
        } else {
            std::ptr::null_mut()
        }
    };
    let mut major = 0;
    let mut minor = 0;
    // SAFETY: Initialize EGL display; fallback cleanly to default display if surfaceless unavailable.
    let mut ok =
        !dpy.is_null() && unsafe { egl_initialize(dpy, &mut major, &mut minor) } == EGL_TRUE;
    if !ok {
        // SAFETY: Fallback to EGL_DEFAULT_DISPLAY (NULL).
        dpy = unsafe { egl_get_display(std::ptr::null_mut()) };
        if dpy.is_null() {
            return Err("No EGL display available for offscreen rendering".to_string());
        }
        // SAFETY: Initializing default EGL display.
        if unsafe { egl_initialize(dpy, &mut major, &mut minor) } != EGL_TRUE {
            let code = unsafe { egl_get_error() };
            return Err(format!("eglInitialize failed (0x{code:x})"));
        }
        ok = true;
    }
    let _ = ok;

    let mut guard = EglGuard {
        dpy,
        surf: std::ptr::null_mut(),
        ctx: std::ptr::null_mut(),
        destroy_surf: egl_destroy_surface,
        destroy_ctx: egl_destroy_context,
        make_current: egl_make_current,
        terminate: egl_terminate,
    };

    // SAFETY: Binding desktop OpenGL API on initialized EGL display.
    if unsafe { egl_bind_api(EGL_OPENGL_API) } != EGL_TRUE {
        return Err(format!("eglBindAPI(OPENGL) failed (0x{:x})", unsafe {
            egl_get_error()
        }));
    }

    let cfg_attribs = [
        EGL_SURFACE_TYPE,
        EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE,
        EGL_OPENGL_BIT,
        EGL_RED_SIZE,
        8,
        EGL_GREEN_SIZE,
        8,
        EGL_BLUE_SIZE,
        8,
        EGL_ALPHA_SIZE,
        8,
        EGL_DEPTH_SIZE,
        24,
        EGL_NONE,
    ];
    let mut cfg: EglConfig = std::ptr::null_mut();
    let mut num_cfg: c_int = 0;
    // SAFETY: Config attributes terminated with EGL_NONE.
    if unsafe { egl_choose_config(dpy, cfg_attribs.as_ptr(), &mut cfg, 1, &mut num_cfg) }
        != EGL_TRUE
        || num_cfg < 1
    {
        return Err("eglChooseConfig found no OpenGL 3.3 RGBA8/Depth24 config".to_string());
    }

    let ctx_attribs = [
        EGL_CONTEXT_MAJOR_VERSION,
        3,
        EGL_CONTEXT_MINOR_VERSION,
        3,
        EGL_CONTEXT_OPENGL_PROFILE_MASK,
        EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT,
        EGL_NONE,
    ];
    // SAFETY: Context attributes terminated with EGL_NONE.
    let ctx = unsafe { egl_create_context(dpy, cfg, std::ptr::null_mut(), ctx_attribs.as_ptr()) };
    if ctx.is_null() {
        return Err(format!(
            "eglCreateContext (GL 3.3 Core) failed (0x{:x})",
            unsafe { egl_get_error() }
        ));
    }
    guard.ctx = ctx;

    // Try surfaceless make_current first (KHR_surfaceless_context), else fall back to a 1x1 pbuffer.
    // SAFETY: Valid display + OpenGL context handles.
    if unsafe { egl_make_current(dpy, std::ptr::null_mut(), std::ptr::null_mut(), ctx) } != EGL_TRUE
    {
        let pbuf_attribs = [EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE];
        // SAFETY: Valid config + EGL_NONE terminated pbuffer attribs.
        let surf = unsafe { egl_create_pbuffer(dpy, cfg, pbuf_attribs.as_ptr()) };
        if surf.is_null() {
            return Err("eglMakeCurrent(NO_SURFACE) and pbuffer fallback failed".to_string());
        }
        guard.surf = surf;
        // SAFETY: Valid surface + context handles.
        if unsafe { egl_make_current(dpy, surf, surf, ctx) } != EGL_TRUE {
            return Err(format!("eglMakeCurrent(pbuffer) failed (0x{:x})", unsafe {
                egl_get_error()
            }));
        }
    }

    // Load a separate glow context for temporary offscreen FBO setup & pixel readback.
    // SAFETY: Active current EGL OpenGL 3.3 context; `egl_lib` stays alive past this scope.
    let outer_gl = unsafe {
        glow::Context::from_loader_function(|name| {
            let Ok(cname) = CString::new(name) else {
                return std::ptr::null();
            };
            egl_get_proc(cname.as_ptr())
        })
    };

    let prev_w = renderer.viewport_width;
    let prev_h = renderer.viewport_height;

    // SAFETY: Active GL 3.3 context; all temporary offscreen FBO/RBOs and renderer GL objects are
    // destroyed before dropping `guard`.
    unsafe {
        let color_rbo = outer_gl
            .create_renderbuffer()
            .map_err(|e| format!("create offscreen color rbo: {e}"))?;
        outer_gl.bind_renderbuffer(glow::RENDERBUFFER, Some(color_rbo));
        outer_gl.renderbuffer_storage(glow::RENDERBUFFER, glow::RGBA8, width as i32, height as i32);

        let depth_rbo = outer_gl
            .create_renderbuffer()
            .map_err(|e| format!("create offscreen depth rbo: {e}"))?;
        outer_gl.bind_renderbuffer(glow::RENDERBUFFER, Some(depth_rbo));
        outer_gl.renderbuffer_storage(
            glow::RENDERBUFFER,
            glow::DEPTH_COMPONENT24,
            width as i32,
            height as i32,
        );
        outer_gl.bind_renderbuffer(glow::RENDERBUFFER, None);

        let target_fbo = outer_gl
            .create_framebuffer()
            .map_err(|e| format!("create offscreen fbo: {e}"))?;
        outer_gl.bind_framebuffer(glow::FRAMEBUFFER, Some(target_fbo));
        outer_gl.framebuffer_renderbuffer(
            glow::FRAMEBUFFER,
            glow::COLOR_ATTACHMENT0,
            glow::RENDERBUFFER,
            Some(color_rbo),
        );
        outer_gl.framebuffer_renderbuffer(
            glow::FRAMEBUFFER,
            glow::DEPTH_ATTACHMENT,
            glow::RENDERBUFFER,
            Some(depth_rbo),
        );
        if outer_gl.check_framebuffer_status(glow::FRAMEBUFFER) != glow::FRAMEBUFFER_COMPLETE {
            outer_gl.bind_framebuffer(glow::FRAMEBUFFER, None);
            outer_gl.delete_framebuffer(target_fbo);
            outer_gl.delete_renderbuffer(color_rbo);
            outer_gl.delete_renderbuffer(depth_rbo);
            return Err("Offscreen target framebuffer is incomplete".to_string());
        }

        let render_result = (|| -> Result<Vec<u8>, String> {
            renderer.resize(width, height);
            renderer.init_gl()?;
            outer_gl.bind_framebuffer(glow::FRAMEBUFFER, Some(target_fbo));
            let res = renderer.render_gl();
            if res.is_ok() {
                outer_gl.bind_framebuffer(glow::READ_FRAMEBUFFER, Some(target_fbo));
                outer_gl.pixel_store_i32(glow::PACK_ALIGNMENT, 1);
                let row_bytes = (width as usize) * 4;
                let mut raw = vec![0u8; row_bytes * (height as usize)];
                outer_gl.read_pixels(
                    0,
                    0,
                    width as i32,
                    height as i32,
                    glow::RGBA,
                    glow::UNSIGNED_BYTE,
                    glow::PixelPackData::Slice(&mut raw),
                );
                // Flip Y so row 0 corresponds to top-left of screen.
                let mut flipped = vec![0u8; raw.len()];
                for row in 0..(height as usize) {
                    let src_start = (height as usize - 1 - row) * row_bytes;
                    let dst_start = row * row_bytes;
                    flipped[dst_start..dst_start + row_bytes]
                        .copy_from_slice(&raw[src_start..src_start + row_bytes]);
                }
                renderer.destroy_gl();
                Ok(flipped)
            } else {
                renderer.destroy_gl();
                Err(res.err().unwrap_or_else(|| "render_gl failed".to_string()))
            }
        })();

        outer_gl.bind_framebuffer(glow::FRAMEBUFFER, None);
        outer_gl.delete_framebuffer(target_fbo);
        outer_gl.delete_renderbuffer(color_rbo);
        outer_gl.delete_renderbuffer(depth_rbo);
        renderer.resize(prev_w, prev_h);

        let rgba = render_result?;
        drop(guard);
        drop(egl_lib);
        Ok(OffscreenImage {
            width,
            height,
            rgba,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use estisketch_3d_core::{
        BuiltSceneMesh, MaterialDef, MaterialStyle, MeshBuilder, PartFlags, SunIR,
    };
    use glam::Vec3;

    #[test]
    fn headless_egl_smoke_render_when_supported() {
        let mut mb = MeshBuilder::new();
        mb.push_oriented_box(
            Vec3::new(0.0, 0.0, 1.0),
            0.25,
            Vec3::ZERO,
            Vec3::new(3.0, 0.25, 2.2),
        );
        let part = mb
            .into_part(
                "w1",
                "wall",
                "lvl_0",
                "LeftFace",
                PartFlags {
                    is_roof_or_ceiling: false,
                    is_wall: true,
                },
                MaterialDef {
                    name: "Drywall".to_string(),
                    base_color: [0.92, 0.90, 0.86, 1.0],
                    roughness: 0.75,
                    metallic: 0.0,
                    style: MaterialStyle::Solid,
                    pattern_scale: 1.0,
                    pattern_rotation_deg: 0.0,
                    transparent: false,
                },
            )
            .unwrap();
        let mut built = BuiltSceneMesh {
            parts: vec![part],
            ..BuiltSceneMesh::default()
        };
        built.recompute_bounds();

        let mut renderer = GlRenderer::new(160, 120);
        renderer.set_scene_mesh(built, SunIR::default(), true);
        match render_offscreen(&mut renderer, 160, 120) {
            Ok(img) => {
                assert_eq!(img.rgba.len(), 160 * 120 * 4);
                let first_px = &img.rgba[0..4];
                assert!(
                    img.rgba.as_chunks::<4>().0.iter().any(|px| px != first_px),
                    "offscreen image was uniform {first_px:?}"
                );
            }
            Err(err) => {
                // Skip gracefully on headless build hosts lacking any EGL/Mesa driver.
                eprintln!("Skipping offscreen EGL test (driver unavailable): {err}");
            }
        }
    }
}
