# INSITEVA - Windows deployment build
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = collect_submodules('core') + collect_submodules('desktop')
datas = []
for pkg in ['matplotlib', 'openpyxl', 'reportlab', 'pptx']:
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

datas.append(('assets', 'assets'))

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='INSITEVA',
    icon='assets/insiteva.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
