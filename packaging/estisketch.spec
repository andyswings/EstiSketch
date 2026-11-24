# -*- mode: python ; coding: utf-8 -*-
import importlib.util
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = [
    'gi',
    'gi.repository',
    'gi.repository.Gtk',
    'gi.repository.Gdk',
    'gi.repository.GdkPixbuf',
    'gi.repository.Gio',
    'gi.repository.GLib',
    'gi.repository.GObject',
    'gi.repository.Pango',
    'gi.repository.PangoCairo',
    'cairo',
    'numpy',
]
hiddenimports.extend(collect_submodules('EstiSketch'))
if importlib.util.find_spec('reportlab') is not None:
    hiddenimports.extend(collect_submodules('reportlab'))

a = Analysis(
    ['../run_estisketch.py'],
    pathex=['../src'],
    binaries=[],
    datas=[
        ('../src/EstiSketch/Icons', 'EstiSketch/Icons'),
        ('../src/EstiSketch/Resources', 'EstiSketch/Resources'),
        ('../src/EstiSketch/settings.json', 'EstiSketch'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
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
