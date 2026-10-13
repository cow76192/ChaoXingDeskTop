"""Package only public source and built artifacts; never include user data."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

root = Path(__file__).resolve().parents[2]
desktop = root / "desktop"
import sys
sys.path.insert(0, str(desktop))
from chaoxing_desktop import __version__
release = root / "release"
release.mkdir(parents=True, exist_ok=True)
app = desktop / "dist/ChaoxingDesktop"
for filename in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "requirements-lock.txt"):
    shutil.copy2(desktop / filename, app / filename)
shutil.copy2(desktop / "THIRD_PARTY_NOTICES.md", app / "_internal/THIRD_PARTY_NOTICES.md")
shutil.copy2(desktop / "vendor/chaoxing/api/README.md", app / "_internal/vendor/chaoxing/api/README.md")
source = release / f"ChaoxingDesktop-{__version__}-source.zip"
skip = {".venv", "build", "dist", "__pycache__", ".git", ".pytest_cache"}
with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for file in sorted(desktop.rglob("*")):
        rel = file.relative_to(desktop)
        if file.is_file() and not (set(rel.parts) & skip) and file.suffix not in (".pyc", ".log") and file.name not in ("settings.ini", "cookies.txt", "config.ini"):
            archive.write(file, "ChaoxingDesktop-source/desktop/" + rel.as_posix())
    archive.write(root / "plans/Windows桌面版开发计划书.md", "ChaoxingDesktop-source/plans/Windows桌面版开发计划书.md")
    archive.write(root / "plans/Windows桌面版验收记录.md", "ChaoxingDesktop-source/plans/Windows桌面版验收记录.md")
    for record in sorted((root / "plans").glob("桌面端*验收.md")):
        archive.write(record, "ChaoxingDesktop-source/plans/" + record.name)
portable = release / f"ChaoxingDesktop-{__version__}-win-x64.zip"
with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for file in sorted(app.rglob("*")):
        if file.is_file():
            archive.write(file, "ChaoxingDesktop/" + file.relative_to(app).as_posix())
    archive.write(source, f"ChaoxingDesktop/ChaoxingDesktop-{__version__}-source.zip")
manifest = {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in (source, portable)}
(release / "SHA256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest, indent=2))
