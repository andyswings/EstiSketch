//! Cross-platform OpenGL 3.3 Core function pointer loader for an active `Gtk.GLArea` context.

use std::ffi::{c_void, CString};

/// Load a `glow::Context` bound to the caller's currently active OpenGL context.
pub fn load_gl_context() -> Result<glow::Context, String> {
    #[cfg(target_os = "linux")]
    {
        load_linux_gl_context()
    }
    #[cfg(target_os = "windows")]
    {
        load_windows_gl_context()
    }
    #[cfg(target_os = "macos")]
    {
        load_macos_gl_context()
    }
}

#[cfg(target_os = "linux")]
fn load_linux_gl_context() -> Result<glow::Context, String> {
    type GetProcFn = unsafe extern "C" fn(*const i8) -> *const c_void;
    type EglGetCurrentContextFn = unsafe extern "C" fn() -> *const c_void;

    // SAFETY: Loading standard system shared libraries (`libEGL.so.1` / `libGL.so.1`) on Linux
    // to resolve OpenGL 3.3 symbols already active inside GTK4's GLArea make_current() scope.
    let egl_lib = unsafe { libloading::Library::new("libEGL.so.1") }.ok();
    let gl_lib = unsafe { libloading::Library::new("libGL.so.1") }
        .map_err(|e| format!("Failed to open libGL.so.1: {e}"))?;

    let use_egl = egl_lib.as_ref().is_some_and(|lib| {
        // SAFETY: `eglGetCurrentContext` takes no arguments and returns a handle or null.
        let sym = unsafe { lib.get::<EglGetCurrentContextFn>(b"eglGetCurrentContext\0") };
        sym.is_ok_and(|f| !unsafe { f() }.is_null())
    });

    let egl_get_proc: Option<GetProcFn> = if use_egl {
        egl_lib.as_ref().and_then(|lib| {
            // SAFETY: Standard EGL symbol signature `void* (*)(const char*)`.
            unsafe {
                lib.get::<GetProcFn>(b"eglGetProcAddress\0")
                    .ok()
                    .map(|s| *s)
            }
        })
    } else {
        None
    };

    let glx_get_proc: Option<GetProcFn> = if egl_get_proc.is_none() {
        // SAFETY: Standard GLX symbol signature `void* (*)(const char*)`.
        unsafe {
            gl_lib
                .get::<GetProcFn>(b"glXGetProcAddressARB\0")
                .ok()
                .map(|s| *s)
        }
    } else {
        None
    };

    // SAFETY: Loader closure stays valid for all OpenGL calls because `gl_lib`/`egl_lib` remain
    // loaded in process memory when leaked intentionally for process lifetime (standard OS loader).
    let ctx = unsafe {
        glow::Context::from_loader_function(|name| {
            let Ok(cname) = CString::new(name) else {
                return std::ptr::null();
            };
            if let Some(get_proc) = egl_get_proc {
                let ptr = get_proc(cname.as_ptr());
                if !ptr.is_null() {
                    return ptr;
                }
            }
            if let Some(get_proc) = glx_get_proc {
                let ptr = get_proc(cname.as_ptr());
                if !ptr.is_null() {
                    return ptr;
                }
            }
            gl_lib
                .get::<*const c_void>(cname.to_bytes_with_nul())
                .map_or(std::ptr::null(), |s| *s)
        })
    };

    // Keep system GL library handles alive for cached function pointer lifetime.
    if let Some(lib) = egl_lib {
        std::mem::forget(lib);
    }
    std::mem::forget(gl_lib);
    Ok(ctx)
}

#[cfg(target_os = "windows")]
fn load_windows_gl_context() -> Result<glow::Context, String> {
    type WglGetProcFn = unsafe extern "system" fn(*const i8) -> *const c_void;

    // SAFETY: Loading `opengl32.dll` on Windows inside an active GtkGLArea context.
    let gl_lib = unsafe { libloading::Library::new("opengl32.dll") }
        .map_err(|e| format!("Failed to open opengl32.dll: {e}"))?;

    // SAFETY: Standard Win32 WGL function signature.
    let wgl_get_proc: Option<WglGetProcFn> = unsafe {
        gl_lib
            .get::<WglGetProcFn>(b"wglGetProcAddress\0")
            .ok()
            .map(|s| *s)
    };

    // SAFETY: Context is active; resolved GL pointers remain valid while opengl32.dll is loaded.
    let ctx = unsafe {
        glow::Context::from_loader_function(|name| {
            let Ok(cname) = CString::new(name) else {
                return std::ptr::null();
            };
            if let Some(get_proc) = wgl_get_proc {
                let ptr = get_proc(cname.as_ptr());
                if !ptr.is_null() {
                    return ptr;
                }
            }
            gl_lib
                .get::<*const c_void>(cname.to_bytes_with_nul())
                .map_or(std::ptr::null(), |s| *s)
        })
    };
    std::mem::forget(gl_lib);
    Ok(ctx)
}

#[cfg(target_os = "macos")]
fn load_macos_gl_context() -> Result<glow::Context, String> {
    // SAFETY: Loading Apple OpenGL framework inside an active GtkGLArea context.
    let gl_lib =
        unsafe { libloading::Library::new("/System/Library/Frameworks/OpenGL.framework/OpenGL") }
            .map_err(|e| format!("Failed to open OpenGL.framework: {e}"))?;

    // SAFETY: OpenGL framework stays resident via mem::forget while context uses its symbols.
    let ctx = unsafe {
        glow::Context::from_loader_function(|name| {
            let Ok(cname) = CString::new(name) else {
                return std::ptr::null();
            };
            gl_lib
                .get::<*const c_void>(cname.to_bytes_with_nul())
                .map_or(std::ptr::null(), |s| *s)
        })
    };
    std::mem::forget(gl_lib);
    Ok(ctx)
}
