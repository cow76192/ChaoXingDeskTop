# Build two launchers sharing dependencies; the worker needs redirected stdio.
from pathlib import Path
import sys
from importlib.metadata import distributions
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(SPECPATH)
sys.path.insert(0, str(root / 'vendor/chaoxing'))
hidden = collect_submodules('api') + ['chaoxing_desktop.runtime', 'lxml.etree', 'lxml._elementpath', 'pyaes']
metadata = []
locked_names = {line.split('==')[0].lower().replace('_', '-') for line in (root / 'requirements-lock.txt').read_text().splitlines()}
for dist in distributions():
    name = dist.metadata['Name']
    if name.lower().replace('_', '-') in locked_names and name.lower() not in ('pyinstaller', 'pyinstaller-hooks-contrib', 'pyside6-webengine', 'pyside6-pdf', 'pefile', 'pywin32-ctypes', 'altgraph', 'pip'):
        metadata.extend(copy_metadata(name))
a = Analysis(
    [str(root / 'run.py')],
    pathex=[str(root), str(root / 'vendor/chaoxing')],
    binaries=[],
    datas=[(str(file), 'vendor/chaoxing/' + file.relative_to(root / 'vendor/chaoxing').parent.as_posix())
           for folder in ('api', 'resource') for file in (root / 'vendor/chaoxing' / folder).rglob('*')
           if file.is_file() and '__pycache__' not in file.parts and file.suffix in ('.py', '.json', '.md')]
          + [(str(root / 'assets'), 'assets'), (str(root / 'LICENSE'), '.'),
           (str(root / 'THIRD_PARTY_NOTICES.md'), '.')] + metadata,
    hiddenimports=hidden,
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtPdf', 'tkinter', 'celery', 'flask', 'ddddocr', 'openai', 'httpx', 'httpx2', 'tqdm'],
    noarchive=False,
)
# Qt uses the ICU API supplied by supported Windows releases. The build host
# may have unrelated Poppler/Conda ICU DLLs in PATH with incompatible exports.
# Never shadow the Windows API with those generic DLL names.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in ('icuuc.dll', 'icuin.dll', 'icu.dll')]
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ChaoxingDesktop', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
worker = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ChaoxingWorker', debug=False,
             bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(gui, worker, a.binaries, a.datas, strip=False, upx=False, name='ChaoxingDesktop')
