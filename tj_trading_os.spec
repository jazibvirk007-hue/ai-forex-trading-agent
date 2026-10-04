from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
hidden = collect_submodules("uvicorn") + collect_submodules("pydantic")

a = Analysis(
    ["run_tj.py"],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "app" / "static"), "app/static")],
    hiddenimports=hidden + ["MetaTrader5"],
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
    a.binaries,
    a.datas,
    [],
    name="TJ-Trading-OS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
