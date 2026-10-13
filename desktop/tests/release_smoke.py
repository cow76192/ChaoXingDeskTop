"""Validate a packaged release, without relying on installed Python packages."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "dist/ChaoxingDesktop"
destination = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else root.parent / "plans/release-smoke"
destination.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
# No developer venv or Python directory in PATH.
env["PATH"] = os.path.join(env.get("WINDIR", "C:/Windows"), "System32")
with tempfile.TemporaryDirectory() as data:
    command = dict(action="probe", config={}, data_dir=data)
    probe = subprocess.run([str(target / "ChaoxingWorker.exe"), "--worker"], input=json.dumps(command),
                           capture_output=True, encoding="utf-8", timeout=30, env=env)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    events = [json.loads(line) for line in probe.stdout.splitlines()]
    assert events[-1]["type"] == "probe", events
    print("Frozen core imports and font resources passed.")
result = subprocess.run([str(target / "ChaoxingDesktop.exe"), "--smoke-test", str(destination)],
                        capture_output=True, timeout=55, env=env)
assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
report = json.loads((destination / "result.json").read_text(encoding="utf-8"))
assert report["success"], report
print(report["message"])
