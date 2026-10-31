"""Launch the native frontend; never silently fall back to another UI."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    candidates = [root / "winui/publish/ChaoxingDesktop.exe",
                  root / "winui/bin/x64/Release/net8.0-windows10.0.19041.0/win-x64/ChaoxingDesktop.exe"]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).with_name("ChaoxingDesktop.exe"))
    executable = next((path for path in candidates if path.is_file()), None)
    if executable is None:
        raise RuntimeError("尚未构建 WinUI 3 界面，请运行 desktop/scripts/build-winui.ps1。")
    environment = dict(os.environ, CHAOXING_PYTHON=sys.executable, CHAOXING_BACKEND_ROOT=str(root))
    return subprocess.call([str(executable), *sys.argv[1:]], env=environment, cwd=root)
