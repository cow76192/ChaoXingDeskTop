"""Interactive, read-only real login check. Never put credentials in files/argv."""
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chaoxing_desktop.config import defaults, to_payload, Redactor

root = Path(__file__).resolve().parents[1]
username = getpass.getpass("Account (hidden): ")
password = getpass.getpass("Password (hidden): ")
config = defaults()
config["common"]["username"] = username
config["common"]["password"] = password
payload = to_payload(config)
redact = Redactor(payload)
with tempfile.TemporaryDirectory(prefix="cx-login-check-") as data:
    command = dict(action="courses", demo=False, config=payload, selected=[], data_dir=data)
    process = subprocess.run([str(root / "dist/ChaoxingDesktop/ChaoxingWorker.exe"), "--worker"],
                             input=json.dumps(command), capture_output=True, encoding="utf-8", timeout=100)
    events = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
    result = next((e for e in events if e.get("type") == "courses"), None)
    if result is None:
        errors = [redact(e.get("message", "")).replace(username, "[account]") for e in events if e.get("type") == "error"]
        print(json.dumps({"success": False, "errors": errors, "exit_code": process.returncode}, ensure_ascii=True))
        raise SystemExit(1)
    cookie_exists = (Path(data) / "cookies.txt").exists()
    # Recheck cookie login with password removed, still read-only.
    command["config"]["common"]["password"] = ""
    command["config"]["common"]["use_cookies"] = True
    cookie = subprocess.run([str(root / "dist/ChaoxingDesktop/ChaoxingWorker.exe"), "--worker"],
                            input=json.dumps(command), capture_output=True, encoding="utf-8", timeout=100)
    cookie_events = [json.loads(line) for line in cookie.stdout.splitlines() if line.strip()]
    cookie_result = next((e for e in cookie_events if e.get("type") == "courses"), None)
    report = dict(success=True, course_count=len(result["courses"]), cookie_saved=cookie_exists,
                  cookie_login=bool(cookie_result), cookie_course_count=len(cookie_result["courses"]) if cookie_result else None)
    print(json.dumps(report))
    report_path = root.parent / "plans/account-check.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # TemporaryDirectory removes the login Cookie after both subprocesses exit.
username = password = ""
