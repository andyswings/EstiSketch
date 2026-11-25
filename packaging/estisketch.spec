# -*- mode: python ; coding: utf-8 -*-
import importlib.util
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

ROOT_DIR = os.path.abspath(os.path.join(SPECPATH, '..'))
SRC_DIR = os.path.join(ROOT_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

block_cipher = None

estisketch_modules = collect_submodules('EstiSketch')
assert 'EstiSketch.main' in estisketch_modules, (
    f"Failed to collect EstiSketch submodules from {SRC_DIR}"
)

hiddenimports = [
    'gi',
    'gi.repository',
    'gi.repository.Gtk',
    'gi.repository.Gdk',
    'gi.repository.Gsk',
    'gi.repository.Graphene',
    'gi.repository.GdkPixbuf',
    'gi.repository.Gio',
    'gi.repository.GLib',
    'gi.repository.GObject',
    'gi.repository.Pango',
    'gi.repository.PangoCairo',
    'cairo',
    'numpy',
]
hiddenimports.extend(estisketch_modules)
if importlib.util.find_spec('reportlab') is not None:
    hiddenimports.extend(collect_submodules('reportlab'))

a = Analysis(
    [os.path.join(ROOT_DIR, 'run_estisketch.py')],
    pathex=[SRC_DIR],
    binaries=[],
    datas=[
        (os.path.join(SRC_DIR, 'EstiSketch', 'Icons'), os.path.join('EstiSketch', 'Icons')),
        (os.path.join(SRC_DIR, 'EstiSketch', 'Resources'), os.path.join('EstiSketch', 'Resources')),
        (os.path.join(SRC_DIR, 'EstiSketch', 'settings.json'), 'EstiSketch'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={
        'gi': {
            'module-versions': {
                'Gtk': '4.0',
                'Gdk': '4.0',
                'Gsk': '4.0',
            },
        },
    },
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='estisketch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='estisketch',
)
