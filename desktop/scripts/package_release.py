"""Package only public source and built artifacts; never include user data."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
import tempfile
import atexit

root = Path(__file__).resolve().parents[2]
desktop = root / "desktop"
import sys
sys.path.insert(0, str(desktop))
from chaoxing_desktop import __version__
from scripts.source_bundle import write_source_archive
from scripts.release_support import validate_app_tree
from scripts.provenance import verify_build, digest
release = root / "release"
release.mkdir(parents=True, exist_ok=True)
app = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else desktop / "dist/ChaoxingDesktop"
validate_app_tree(app)
verify_build(desktop, app)
staging_root = desktop / 'build'
staging_root.mkdir(exist_ok=True)
if not staging_root.resolve().is_relative_to(desktop.resolve()):
    raise ValueError('Release staging must stay inside the workspace')
stage = tempfile.TemporaryDirectory(prefix='portable-stage-', dir=staging_root)
atexit.register(stage.cleanup)
original_app = app
app = Path(stage.name) / 'ChaoxingDesktop'
shutil.copytree(original_app, app)
verify_build(desktop, app)
from PyInstaller.utils.win32.versioninfo import read_version_info_from_executable
expected = tuple(int(part) for part in __version__.split('.')) + (0,)
for executable in ("ChaoxingDesktop.exe", "ChaoxingWorker.exe"):
    info = read_version_info_from_executable(str(app / executable))
    actual = None if info is None else (info.ffi.fileVersionMS >> 16, info.ffi.fileVersionMS & 0xffff,
                                      info.ffi.fileVersionLS >> 16, info.ffi.fileVersionLS & 0xffff)
    if actual != expected:
        raise RuntimeError(f"{executable} does not match source version {__version__}; rebuild before packaging")
for filename in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "requirements-lock.txt"):
    shutil.copy2(desktop / filename, app / filename)
shutil.copy2(desktop / "THIRD_PARTY_NOTICES.md", app / "_internal/THIRD_PARTY_NOTICES.md")
source = release / f"ChaoxingDesktop-{__version__}-source.zip"
write_source_archive(root, source)
portable = release / f"ChaoxingDesktop-{__version__}-win-x64.zip"
with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for file in validate_app_tree(app):
        archive.write(file, "ChaoxingDesktop/" + file.relative_to(app).as_posix())
    archive.write(source, f"ChaoxingDesktop/ChaoxingDesktop-{__version__}-source.zip")
manifest = {p.name: {"bytes": p.stat().st_size, "sha256": digest(p)} for p in (source, portable)}
(release / "SHA256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
# Keep previous releases recoverable, with a separate checksum index.
archive_dir = release / "archive"
archive_dir.mkdir(exist_ok=True)
import re
for old in release.glob("ChaoxingDesktop-*.zip"):
    if old.name in manifest or not re.fullmatch(r"ChaoxingDesktop-\d+\.\d+\.\d+-(?:source|win-x64)\.zip", old.name):
        continue
    target = archive_dir / old.name
    if target.exists():
        # Do not overwrite an archived release, even if it has the same name.
        raise FileExistsError(f"Already archived: {target}")
    old.rename(target)
history = {p.name: {"bytes": p.stat().st_size, "sha256": digest(p)}
           for p in sorted(archive_dir.glob("ChaoxingDesktop-*.zip"))}
(archive_dir / "SHA256.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
print(json.dumps(manifest, indent=2))
