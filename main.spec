# -*- mode: python ; coding: utf-8 -*-

# PyInstaller spec for kobo-highlights-extractor
# Builds a single-file executable from src/kobo_highlights_extractor/__main__.py

from pathlib import Path

block_cipher = None

# PyInstaller executes the spec without setting __file__ in some versions.
# Use CWD (we expect to run from the repo root where this spec resides).
REPO_ROOT = Path.cwd()
SRC_DIR = str(REPO_ROOT / "src")
# Use a small entry that imports the CLI via absolute import to satisfy PyInstaller
ENTRY_SCRIPT = str(REPO_ROOT / "scripts" / "pyi_entry.py")


a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[SRC_DIR, str(REPO_ROOT)],
    binaries=[],
    datas=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='kobo-highlights-extractor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
