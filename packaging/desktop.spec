# Build on the target OS; this is not a cross-compiler.
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
from pathlib import Path
import sys

root = Path(SPECPATH).parent
hidden = collect_submodules('firmavex') + collect_submodules('src.firmavex')
data = collect_data_files('firmavex.product') + collect_data_files('firmware.benchmarks.cortex_m')
data += [(str(root / 'LICENSE'), 'notices'), (str(root / 'packaging' / 'THIRD_PARTY_NOTICES.md'), 'notices')]
data += [(str(path), 'notices') for path in (root / 'packaging' / 'licenses').glob('*')]
a = Analysis([str(root / 'packaging' / 'desktop_entry.py')], pathex=[str(root)],
             binaries=[], datas=data, hiddenimports=hidden, excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets'])
pyz = PYZ(a.pure)
# Console subsystem is intentional: the same executable hosts a piped worker.
# A future GUI-only launcher can wrap this without breaking worker stdout.
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FIRMAVEX', console=True)
collection = COLLECT(exe, a.binaries, a.datas, name='FIRMAVEX')
if sys.platform == 'darwin':
    app = BUNDLE(collection, name='FIRMAVEX.app', bundle_identifier='org.firmavex.desktop')
