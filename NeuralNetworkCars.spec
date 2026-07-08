# -*- mode: python ; coding: utf-8 -*-

import json
from pathlib import Path


project_root = Path(SPECPATH)
client_defaults = json.loads(
    (project_root / "configs" / "client_defaults.json").read_text(encoding="utf-8")
)
generated_config_dir = project_root / "build" / "generated-config"
generated_config_dir.mkdir(parents=True, exist_ok=True)
generated_client_defaults = generated_config_dir / "client_defaults.json"
generated_client_defaults.write_text(
    json.dumps(client_defaults, indent=2),
    encoding="utf-8",
)

datas = [
    (str(project_root / "Images"), "Images"),
    (str(project_root / "fonts"), "fonts"),
    (str(project_root / "maps"), "maps"),
    (str(project_root / "configs" / "beginner_mix.json"), "configs"),
    (str(generated_client_defaults), "configs"),
]

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "mypy"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NeuralNetworkCars",
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
)
