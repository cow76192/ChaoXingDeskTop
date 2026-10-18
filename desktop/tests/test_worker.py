from enum import Enum
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from chaoxing_desktop.config import Redactor, defaults, to_payload
from chaoxing_desktop.worker import Channel, run_tasks


class Result(Enum):
    SUCCESS = 0
    ERROR = 1
    NOT_OPEN = 2


class WorkerTests(unittest.TestCase):
    def test_input_protocol(self):
        output = io.StringIO()
        channel = Channel(output, io.StringIO('{"answer":"选项A"}\n'), Redactor({}))
        self.assertEqual(channel.ask("题目", kind='question'), "选项A")
        self.assertEqual(json.loads(output.getvalue())["type"], "input")
        self.assertEqual(json.loads(output.getvalue())["kind"], "question")

    def test_retry_and_failure_and_closed_stats(self):
        channel = Channel(io.StringIO(), io.StringIO(), Redactor({}))
        calls = {}
        def process(task):
            key = task["id"]
            calls[key] = calls.get(key, 0) + 1
            if key == "eventual" and calls[key] >= 2:
                return Result.SUCCESS
            return Result.NOT_OPEN if key == "closed" else Result.ERROR
        tasks = [dict(id=key, title=key) for key in ("eventual", "closed", "failure")]
        with patch("chaoxing_desktop.worker.time.sleep"):
            statuses = run_tasks(channel, tasks, process, {"jobs": 2, "retry_interval": 0.1, "notopen_action": "continue"}, Result)
        self.assertEqual(statuses, {"eventual": "processed", "closed": "skipped", "failure": "failed"})
        self.assertEqual(calls["failure"], 5)
        self.assertEqual(calls["closed"], 1)

    def worker(self, action, selected=None):
        with tempfile.TemporaryDirectory() as directory:
            command = dict(action=action, demo=True, selected=selected or [], config=to_payload(defaults()), data_dir=directory)
            result = subprocess.run([sys.executable, "run.py", "--worker"], input=json.dumps(command),
                                    capture_output=True, encoding="utf-8", timeout=20)
            return result, [json.loads(line) for line in result.stdout.splitlines()]

    def test_subprocess_demo_and_no_credentials(self):
        result, events = self.worker("courses")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events[-1]["type"], "courses")
        self.assertEqual(len(events[-1]["courses"]), 3)
        result, events = self.worker("run", [["demo-101", "01"]])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["success"], 3)

    def test_demo_selection_does_not_fallback_to_all(self):
        result, events = self.worker("run", [["no-such-course", "01"]])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(events[-1]["type"], "error")

    def test_core_can_import_and_load_bundled_font(self):
        # Isolate global stdout/input and vendor monkey patches in a subprocess.
        code = """
import io, sys, tempfile, os
from chaoxing_desktop.worker import Channel, load_core
from chaoxing_desktop.config import Redactor
output = sys.stdout
original_cwd = os.getcwd()
with tempfile.TemporaryDirectory() as folder:
    os.chdir(folder)
    core = load_core(Channel(output, io.StringIO(), Redactor({})))
    from api.cxsecret_font import fonthash_dao
    assert len(fonthash_dao.char_map) > 100
    assert not os.path.exists('chaoxing.log')
    assert core.ChapterResult.SUCCESS is not None
    os.chdir(original_cwd)
"""
        result = subprocess.run([sys.executable, "-X", "utf8", "-c", code], capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_worker_rejects_missing_or_corrupt_font_before_network(self):
        # Exercise the real entry point, including optimized Python where
        # assertions are disabled, without changing the bundled resource.
        code = r'''
import io, json, sys
from pathlib import Path
from unittest.mock import patch
import requests
from chaoxing_desktop.worker import main
original_open = open
original_read = Path.read_bytes
mode = sys.argv[1]
def font_open(file, *args, **kwargs):
    if str(file).endswith('font_map_table.json'):
        if mode == 'missing':
            raise FileNotFoundError('simulated missing font')
        if mode == 'invalid':
            return io.StringIO('{')
    return original_open(file, *args, **kwargs)
def font_read(path):
    content = original_read(path)
    return content + b' ' if path.name == 'font_map_table.json' else content
sys.stdin = io.StringIO(json.dumps({'action': 'courses', 'config': {}, 'data_dir': sys.argv[2]}) + '\n')
with patch('builtins.open', side_effect=font_open), \
     patch.object(Path, 'read_bytes', font_read if mode == 'modified' else original_read), \
     patch.object(requests.sessions.Session, 'request', side_effect=RuntimeError('network request attempted')):
    status = main()
raise SystemExit(status)
'''
        with tempfile.TemporaryDirectory() as directory:
            for mode in ("missing", "invalid", "modified"):
                with self.subTest(mode=mode):
                    result = subprocess.run([sys.executable, "-O", "-X", "utf8", "-c", code, mode, directory],
                                            capture_output=True, encoding="utf-8", timeout=30)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    events = [json.loads(line) for line in result.stdout.splitlines()]
                    self.assertEqual(events[-1]["type"], "error")
                    self.assertIn("字体资源缺失或损坏", events[-1]["message"])
                    self.assertNotIn("network request attempted", result.stdout)


if __name__ == "__main__":
    unittest.main()
