"""Resource and lifecycle contracts under sustained offline load."""
from concurrent.futures import wait as real_wait
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication
from chaoxing_desktop.controller import Controller
from chaoxing_desktop.models import DATA_ROLE, LogModel, TaskModel
from chaoxing_desktop.qml_backend import Backend
from chaoxing_desktop.config import Redactor
from chaoxing_desktop.worker import Channel, run_tasks
from test_worker import Result


class OutputProcess:
    def __init__(self, output=b""):
        self.output = bytearray(output)
        self.killed = False

    def read(self, size):
        data = bytes(self.output[:size])
        del self.output[:size]
        return data

    def readAllStandardOutput(self):
        return self.read(len(self.output))

    def bytesAvailable(self):
        return len(self.output)

    def kill(self):
        self.killed = True


class PerformanceRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_task_updates_preserve_model_and_other_rows(self):
        model = TaskModel()
        model.reset([dict(id=str(i), title=str(i), status="waiting") for i in range(10000)])
        resets, updates = QSignalSpy(model.modelReset), QSignalSpy(model.dataChanged)
        unchanged = model.rows[9999]
        self.assertTrue(model.update_status("1234", "success"))
        self.assertEqual(resets.count(), 0)
        self.assertEqual(updates.count(), 1)
        self.assertEqual(updates.at(0)[0].row(), 1234)
        self.assertIs(model.rows[9999], unchanged)
        self.assertEqual(model.counts["waiting"], 9999)
        self.assertEqual(model.counts["success"], 1)
        self.assertEqual(model.data(model.index(1234), DATA_ROLE)["statusText"], "已完成")

    def test_log_burst_and_continuous_logging_remain_bounded(self):
        model = LogModel()
        for batch in range(8):
            for i in range(4000):
                model.append(f"{batch}:{i}:" + "x" * 2000)
            self.assertLessEqual(model.pending_characters, model.MAX_CHARS)
            model.flush()
            self.assertLessEqual(model.characters, model.MAX_CHARS)
            self.assertLessEqual(model.rowCount(), model.MAX_ROWS)
            self.assertEqual(model.characters, sum(map(len, model.rows)))
            self.assertTrue(model.rows[-1].startswith(f"{batch}:3999:"))
        model.append("y" * 1000000)
        self.assertLessEqual(len(model.snapshot()[-1]), model.MAX_LINE_CHARS)
        self.assertIn("已截断", model.snapshot()[-1])
        model.clear()
        self.assertFalse(model.rows)
        self.assertFalse(model.pending)
        self.assertFalse(model.timer.isActive())

    def test_log_row_limit_retains_newest_lines_across_batches(self):
        model = LogModel()
        for i in range(4000):
            model.append(str(i))
            if i % 50 == 0:
                model.flush()
        model.flush()
        self.assertEqual(model.rowCount(), model.MAX_ROWS)
        self.assertEqual(model.rows[0], "1500")
        self.assertEqual(model.rows[-1], "3999")

    def test_log_events_do_not_rebuild_courses_or_summary(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, CHAOXING_DESKTOP_DATA=directory):
            backend = Backend()
            updates = QSignalSpy(backend.changed)
            courses = QSignalSpy(backend.coursesChanged)
            for i in range(1000):
                backend.on_event(dict(type="log", message=f"line {i}"))
            self.assertEqual(updates.count(), 0)
            self.assertEqual(courses.count(), 0)
            self.assertNotIn("tasks", backend.summary)
            self.assertNotIn("logs", backend.summary)
            self.assertNotIn("courses", backend.summary)
            self.assertIn("line 999", backend.logs[-1])
            backend.close()
            backend.deleteLater()

    def test_select_all_notifies_once_and_preserves_hidden_selection(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, CHAOXING_DESKTOP_DATA=directory):
            backend = Backend()
            backend.courses = [dict(courseId=str(i), clazzId="a", title=str(i)) for i in range(2000)]
            courses, summary = QSignalSpy(backend.coursesChanged), QSignalSpy(backend.changed)
            backend.selectVisible(True)
            self.assertEqual(len(backend.selected), 2000)
            self.assertEqual(courses.count(), 1)
            self.assertEqual(summary.count(), 1)
            backend.searchCourses("1999")
            backend.selectVisible(False)
            self.assertEqual(len(backend.selected), 1999)
            backend.close()
            backend.deleteLater()

    def test_scheduler_bounds_submitted_futures_for_large_course(self):
        tasks = [dict(id=str(i), title=str(i)) for i in range(5000)]
        batches = []
        def bounded_wait(futures, **kwargs):
            batches.append(len(futures))
            self.assertLessEqual(len(futures), 4)
            return real_wait(futures, **kwargs)
        channel = Channel(io.StringIO(), io.StringIO(), Redactor({}))
        with patch("chaoxing_desktop.worker.wait", side_effect=bounded_wait):
            statuses = run_tasks(channel, tasks, lambda _: Result.SUCCESS,
                                 dict(jobs=4, retry_interval=0, notopen_action="continue"), Result)
        self.assertTrue(batches)
        self.assertEqual(len(statuses), 5000)
        self.assertEqual(set(statuses.values()), {"processed"})

    def test_protocol_handles_split_unicode_and_multiple_frames(self):
        controller = Controller()
        controller.process = OutputProcess()
        events = []
        controller.event.connect(events.append)
        frame = (json.dumps(dict(type="log", message="中文"), ensure_ascii=False) + "\n").encode()
        cut = frame.index("中".encode()) + 1
        controller.process.output.extend(frame[:cut])
        controller.read_output()
        self.assertFalse(events)
        controller.process.output.extend(frame[cut:] + frame)
        controller.read_output()
        self.assertEqual([e["message"] for e in events], ["中文", "中文"])
        self.assertFalse(controller.buffer)

    def test_exit_drains_done_after_large_event_batch_before_finished(self):
        output = b'{"type":"log","message":"line"}\n' * 1000 + b'{"type":"done","success":0,"pending":0,"failed":0,"skipped":0}\n'
        controller = Controller()
        controller.process = OutputProcess(output)
        controller.active = True
        sequence = []
        controller.event.connect(lambda event: sequence.append(event["type"]))
        controller.finished.connect(lambda code: sequence.append(f"exit:{code}"))
        controller.on_finished(0, None)
        self.assertTrue(controller.active)
        for _ in range(20):
            if not controller.active:
                break
            controller._drain_timer.stop()
            controller.read_output()
        self.assertFalse(controller.active)
        self.assertEqual(sequence[-2:], ["done", "exit:0"])
        self.assertEqual(sequence.count("log"), 1000)

    def test_malformed_and_oversized_protocol_stops_worker(self):
        for output in (b'[]\n', b'not-json\n', b'{}\n', b'{"type":"log"', b'x' * 300,
                       b'{"type":"tasks","tasks":null}\n', b'{"type":"task","id":[]}\n',
                       b'{"type":"done"}\n', b'{"type":"input","choices":[null]}\n'):
            with self.subTest(output=output[:20]):
                controller = Controller()
                controller.MAX_FRAME_BYTES = 256
                controller.process = OutputProcess(output)
                events = []
                controller.event.connect(events.append)
                controller.on_finished(1, None)
                self.assertTrue(controller.process.killed)
                self.assertFalse(controller.buffer)
                self.assertFalse(controller.active)
                self.assertEqual([e["type"] for e in events], ["error"])

    def test_worker_truncates_logs_after_redacting_secrets(self):
        output = io.StringIO()
        channel = Channel(output, io.StringIO(), Redactor({"ai": {"key": "PRIVATE"}}))
        channel.send("log", message="PRIVATE " + "x" * 1000000)
        event = json.loads(output.getvalue())
        self.assertNotIn("PRIVATE", event["message"])
        self.assertIn("已隐藏", event["message"])
        self.assertIn("已截断", event["message"])
        self.assertLessEqual(len(event["message"]), 4096)


if __name__ == "__main__":
    unittest.main()
