"""Bounded incremental question models and strict worker protocol."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QSignalSpy
from chaoxing_desktop.question_model import QuestionModel, QuestionFilter, valid_record
from chaoxing_desktop.controller import Controller
from chaoxing_desktop.qml_backend import Backend
from chaoxing_desktop.worker import Channel
from chaoxing_desktop.config import Redactor, defaults, to_payload
from chaoxing_desktop.answers import AnswerRouter
from types import SimpleNamespace


def record():
    output = io.StringIO()
    channel = Channel(output, io.StringIO(), Redactor({}))
    router = AnswerRouter(to_payload(defaults()), channel, [('bank', SimpleNamespace(_query=lambda q: '乙'))])
    router.query({'id': 'q', 'title': '测试题', 'type': 'single', 'options': 'A.甲\nB.乙'})
    return [json.loads(line)['record'] for line in output.getvalue().splitlines() if json.loads(line)['type'] == 'question_result'][-1]


class QuestionResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_updates_do_not_reset_the_model(self):
        model = QuestionModel()
        row = record()
        model.upsert(row)
        resets, updates = QSignalSpy(model.modelReset), QSignalSpy(model.dataChanged)
        row['reason'] = '更新'
        model.upsert(row)
        self.assertEqual(resets.count(), 0)
        self.assertEqual(updates.count(), 1)
        self.assertEqual(model.rowCount(), 1)
        self.assertEqual(model.stats['query_attempts'], 1)

    def test_model_owns_nested_snapshot_and_keeps_serialized_size(self):
        model = QuestionModel()
        row = record()
        row['attempts'] = [dict(provider='bank', status='hit', reason='ok',
                                candidate='甲', returned_title='原题', elapsed_ms=1)]
        self.assertTrue(model.upsert(row))
        expected_size = len(json.dumps(row, ensure_ascii=False))
        row['title'] = 'changed'
        row['attempts'][0]['candidate'] = 'changed'
        row['attempts'].clear()
        stored = model.rows[0]
        self.assertNotEqual(stored['title'], 'changed')
        self.assertEqual(stored['attempts'][0]['candidate'], '甲')
        self.assertEqual(model.characters, expected_size)

    def test_nested_result_refreshes_credentials_once_and_redacts_every_field(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, CHAOXING_DESKTOP_DATA=directory):
            backend = Backend()
            try:
                backend.config['ai']['key'] = 'TEST_PRIVATE_KEY'
                row = record()
                row['title'] = 'TEST_PRIVATE_KEY'
                row['attempts'] = [dict(provider='bank', status='hit', reason='TEST_PRIVATE_KEY',
                                        candidate='TEST_PRIVATE_KEY', returned_title='TEST_PRIVATE_KEY', elapsed_ms=1)]
                with patch.object(backend, 'secret_signature', wraps=backend.secret_signature) as signature:
                    backend.on_event(dict(type='question_result', record=row))
                self.assertLessEqual(signature.call_count, 2)
                stored = json.dumps(backend._question_model.rows, ensure_ascii=False)
                self.assertNotIn('TEST_PRIVATE_KEY', stored)
                self.assertIn('已隐藏', stored)
            finally:
                backend.close()
                backend.deleteLater()

    def test_capacity_and_characters_remain_bounded_under_3000_events(self):
        model = QuestionModel()
        row = record()
        for i in range(3000):
            model.upsert(dict(row, id=str(i), title='x' * 1200))
        self.assertEqual(model.rowCount(), model.MAX_ROWS)
        self.assertEqual(model.evicted, 1000)
        self.assertLessEqual(model.characters, model.MAX_CHARS)
        self.assertEqual(model.characters, sum(model.sizes.values()))
        self.assertEqual(model.stats['resolved'], model.MAX_ROWS)
        self.assertEqual(model.rows[-1]['id'], '2999')

    def test_text_limit_can_evict_before_row_limit(self):
        model = QuestionModel()
        model.MAX_CHARS = 7000
        row = record()
        for i in range(12):
            model.upsert(dict(row, id=str(i), title='x' * 1200, options='y' * 1200))
        self.assertLessEqual(model.characters, model.MAX_CHARS)
        self.assertGreater(model.evicted, 0)

    def test_filters_use_current_status_and_chapter(self):
        model = QuestionModel()
        proxy = QuestionFilter(model)
        row = record()
        model.upsert(dict(row, id='1', task_id='chapter1'))
        model.upsert(dict(row, id='2', task_id='chapter2', stage='pending'))
        proxy.set_filter(True, '')
        self.assertEqual(proxy.rowCount(), 1)
        proxy.set_filter(False, 'chapter1')
        self.assertEqual(proxy.rowCount(), 1)
        model.upsert(dict(row, id='1', task_id='chapter1', stage='error'))
        proxy.set_filter(True, 'chapter1')
        self.assertEqual(proxy.rowCount(), 1)

    def test_invalid_or_unbounded_worker_fields_are_rejected(self):
        row = record()
        self.assertTrue(valid_record(row))
        for changes in ({'score': float('nan')}, {'stage': 'invalid'}, {'requests': -1},
                        {'title': 'x' * 1201}, {'attempts': [{}]}, {'raw_response': 'secret'}, {'requests': True}):
            with self.subTest(changes=changes):
                invalid = dict(row, **changes)
                self.assertFalse(Controller._valid_event({'type': 'question_result', 'record': invalid}))

    def test_backend_rejects_late_run_and_redacts_nested_results(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, CHAOXING_DESKTOP_DATA=directory):
            backend = Backend()
            try:
                backend.controller.run_id = 'current'
                row = record()
                backend.on_event({'type': 'question_result', 'run_id': 'old', 'record': row})
                self.assertEqual(backend.questionModel.rowCount(), 0)
                backend.config['ai']['key'] = 'EXAMPLE_SECRET'
                row['title'] = 'EXAMPLE_SECRET https://user:pass@example.test/path'
                backend.on_event({'type': 'question_result', 'run_id': 'current', 'record': row})
                text = json.dumps(backend._question_model.rows)
                self.assertNotIn('EXAMPLE_SECRET', text)
                self.assertNotIn('user:pass', text)
            finally:
                backend.close()
                backend.deleteLater()


if __name__ == '__main__':
    unittest.main()
