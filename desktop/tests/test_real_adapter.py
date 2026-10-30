"""Validate real adapter orchestration with fake service, without network."""
from enum import Enum
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from chaoxing_desktop.config import Redactor, defaults, to_payload
from chaoxing_desktop.worker import real


class Result(Enum):
    SUCCESS = 0
    ERROR = 1
    NOT_OPEN = 2


class FakeCX:
    def login(self, **kwargs):
        return {"status": True}

    def get_course_list(self):
        return [dict(courseId="1", clazzId="a", cpi="a", title="A"),
                dict(courseId="1", clazzId="b", cpi="b", title="B")]

    def get_course_point(self, course_id, class_id, cpi):
        assert class_id == "b", "Should not access unchecked class A"
        return {"points": [dict(id="done", title="Done", has_finished=True),
                           dict(id="saved", title="Saved exercise", has_finished=False)]}


class RealAdapterTests(unittest.TestCase):
    def run_adapter(self, selected):
        from chaoxing_desktop.worker import Channel
        output = io.StringIO()
        channel = Channel(output, io.StringIO(), Redactor({}))
        cx = FakeCX()
        core = SimpleNamespace(create_client=lambda *args, **kwargs: cx,
                               process_chapter=lambda *args: Result.SUCCESS,
                               ChapterResult=Result)
        command = dict(action="run", config=to_payload(defaults()), selected=selected)
        with patch("chaoxing_desktop.worker.load_core", return_value=core):
            real(channel, command)
        return [json.loads(line) for line in output.getvalue().splitlines()]

    def test_saved_exercise_is_pending_and_only_selected_class_runs(self):
        events = self.run_adapter([["1", "b"]])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["success"], 1)
        self.assertEqual(events[-1]["pending"], 1)
        task_events = [event for event in events if event['type'] == 'tasks']
        self.assertEqual(len(task_events), 1)
        self.assertEqual(len(task_events[0]['tasks']), 2)
        self.assertEqual({task['clazzId'] for task in task_events[0]['tasks']}, {'b'})

    def test_stale_selection_is_rejected(self):
        with self.assertRaises(ValueError):
            self.run_adapter([["1", "z"]])


if __name__ == "__main__":
    unittest.main()
