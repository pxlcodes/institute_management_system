# -*- mode: python ; coding: utf-8 -*-
"""Reproducible Windows one-folder build for ELH Management System."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH).resolve().parent
datas = []
binaries = []
hiddenimports = []

# These packages contain data files and/or load modules dynamically. Collecting
# them explicitly keeps MySQL, PDF, Nepali-date, and ZKTeco support functional.
for package_name in ("mysql.connector", "reportlab", "nepali_datetime", "lxml", "zk"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

analysis = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas + [
        (
            str(project_root / "elh" / "assets" / "certificate_template.docx"),
            "elh/assets",
        )
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "unittest.mock"],
    noarchive=False,
    optimize=1,
)

python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ELH Management System",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(project_root / "packaging" / "windows_version_info.txt"),
)

distribution = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ELH Management System",
)
