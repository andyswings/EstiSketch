import os
import sys

from .version import __version__

_WINDOWS_DLL_DIR_HANDLES = []


def _prepend_env_path(var_name: str, path: str) -> None:
    """Prepend ``path`` to an environment path variable if not already present."""
    existing = os.environ.get(var_name, "")
    parts = [p for p in existing.split(os.pathsep) if p] if existing else []
    norm_target = os.path.normcase(os.path.normpath(path))
    if any(os.path.normcase(os.path.normpath(p)) == norm_target for p in parts):
        return
    os.environ[var_name] = os.pathsep.join([path, *parts]) if parts else path


def _configure_windows_gtk_runtime() -> None:
    """Ensure Conda GTK4 DLLs, GI typelibs, and XDG data dirs are discoverable on Windows."""
    if sys.platform != "win32":
        return

    lib_dir = os.path.join(sys.prefix, "Library")
    lib_bin = os.path.join(lib_dir, "bin")
    if os.path.isdir(lib_bin):
        _prepend_env_path("PATH", lib_bin)
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is not None:
            try:
                _WINDOWS_DLL_DIR_HANDLES.append(add_dll_directory(lib_bin))
            except OSError:
                pass

    typelib_dir = os.path.join(lib_dir, "lib", "girepository-1.0")
    if os.path.isdir(typelib_dir):
        _prepend_env_path("GI_TYPELIB_PATH", typelib_dir)

    share_dir = os.path.join(lib_dir, "share")
    if os.path.isdir(share_dir):
        _prepend_env_path("XDG_DATA_DIRS", share_dir)


_configure_windows_gtk_runtime()
