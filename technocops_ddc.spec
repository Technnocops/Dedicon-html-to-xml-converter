# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

project_root = Path(SPECPATH)
src_root = project_root / "src"
icon_path = project_root / "assets" / "branding" / "technocops_app_icon.ico"
version_info_path = project_root / "packaging" / "windows_version_info.txt"
bundle_name = "Technocops_DDC_Converter_HTML_to_XML_Pro"

datas = [
    (str(project_root / "assets"), "assets"),
]
hiddenimports = collect_submodules("PyQt6.QtSvgWidgets")

a = Analysis(
    [str(src_root / "technocops_ddc" / "__main__.py")],
    pathex=[str(src_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=bundle_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(icon_path) if icon_path.exists() else None,
    version=str(version_info_path),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=bundle_name,
)
