"""Synthetic contracts for the workbench upgrade; no account or service access."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from chaoxing_desktop.config import defaults, to_payload
from chaoxing_desktop.diagnostic_export import diagnostic_config
from chaoxing_desktop.qml_backend import Backend
from chaoxing_desktop.verification import verify_chapters
from chaoxing_desktop.worker import Channel, real
from chaoxing_desktop.control import RunControl, Cancelled
from chaoxing_desktop.run_history import RunHistory
from chaoxing_desktop.ai_usage import AIUsage, AIBudgetExceeded
from chaoxing_desktop.answers import AIClient, AIError, AnswerRouter
from chaoxing_desktop.attention_model import AttentionModel, AttentionFilter, chapter_issue, record_issue, ROLE


class UpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, CHAOXING_DESKTOP_DATA=self.tmp.name)
        self.env.start()
        self.b = Backend()

    def tearDown(self):
        self.b.discardAndClose()
        self.b.deleteLater()
        self.app.processEvents()
        self.env.stop()
        self.tmp.cleanup()

    def test_diagnostics_drop_secrets_urls_identity_and_unknown_fields(self):
        config = defaults()
        samples = ['SYNTH_USERNAME', 'SYNTH_PASSWORD', 'SYNTH_KEY', 'SYNTH_TOKEN', 'SYNTH_PROXY', 'SYNTH_EXTENSION']
        config['common'].update(username=samples[0], password=samples[1])
        config['ai'].update(key=samples[2], endpoint='https://example.invalid/private?auth=' + samples[3],
                            http_proxy='http://user:' + samples[4] + '@example.invalid', model=samples[5])
        config['unknown'] = dict(arbitrary=samples[5])
        config['question_bank'].update(declarative_definition=json.dumps(dict(secret=samples[3])),
                                       providers='TikuGo,TikuLike', adapter_url='https://example.invalid/' + samples[3])
        config['tiku']['submit'] = 'true'
        text = diagnostic_config(config)
        self.assertTrue(all(sample not in text for sample in samples))
        self.assertNotIn('https://', text)
        self.assertIn('submit = true', text)
        self.assertIn('providers = TikuGo,TikuLike', text)
        self.assertIn('pyside', text)

    def test_failed_diagnostic_export_preserves_destination(self):
        path = Path(self.tmp.name) / 'diagnostics.ini'
        path.write_text('original', encoding='utf-8')
        with patch('chaoxing_desktop.qml_backend.QFileDialog.getSaveFileName', return_value=(str(path), '')), \
                patch.object(Path, 'replace', side_effect=OSError('synthetic disk error')):
            self.b.fileAction('export_diagnostics')
        self.assertEqual(path.read_text(encoding='utf-8'), 'original')
        self.assertIn('synthetic disk error', self.b.message)

    def prepare_courses(self):
        self.b.courses = [dict(courseId='course', clazzId='class', title='Synthetic', cpi='fixture')]
        self.b.selected = {('course', 'class')}

    def test_summary_all_submission_combinations_and_hidden_selection(self):
        self.prepare_courses()
        self.b.searchCourses('no match')
        for mask in range(8):
            self.b.config['tiku']['submit'] = str(bool(mask & 1)).lower()
            for section, flag in [('discussion', 2), ('activity', 4)]:
                self.b.config[section].update(enabled='true', auto_submit=str(bool(mask & flag)).lower())
            text = self.b.strategySummary
            self.assertIn('搜索隐藏 1 门', text)
            self.assertIn('测验：' + ('完整作答后自动提交' if mask & 1 else '仅保存'), text)
            self.assertIn('讨论：' + ('自动发布' if mask & 2 else '仅本地草稿'), text)
            self.assertIn('投票／问卷：' + ('自动提交' if mask & 4 else '仅本地草稿'), text)
        self.b.demo_mode = True
        self.assertIn('零平台写入', self.b.strategySummary)
        self.assertIn('测验：仅保存', self.b.strategySummary)

    def test_write_confirmation_cancels_and_invalidates_without_worker(self):
        self.prepare_courses()
        self.b.config['tiku']['submit'] = 'true'
        requested = []
        self.b.startConfirmationRequested.connect(requested.append)
        with patch.object(self.b, 'begin') as begin:
            self.b.startTasks()
            self.assertEqual(len(requested), 1)
            begin.assert_not_called()
            self.b.cancelStartTasks()
            self.b.confirmStartTasks()
            begin.assert_not_called()
            self.b.startTasks()
            self.b.config['common']['jobs'] = '5'
            self.b.confirmStartTasks()
            begin.assert_not_called()
            self.b.startTasks()
            self.b.confirmStartTasks()
            begin.assert_called_once()
            self.b.startTasks()
            self.assertEqual(begin.call_count, 2)

    def test_save_only_does_not_request_confirmation(self):
        self.prepare_courses()
        with patch.object(self.b, 'begin') as begin:
            self.b.startTasks()
            begin.assert_called_once()

    def test_save_failure_locates_numeric_field_without_changing_values(self):
        requested = []
        self.b.fieldRequested.connect(lambda s, k: requested.append((s, k)))
        self.b.setValue('common', 'speed', '9')
        self.assertFalse(self.b.save())
        self.assertEqual(requested, [('common', 'speed')])
        self.assertEqual(self.b.config['common']['speed'], '9')

    def test_service_result_expires_after_edit(self):
        self.b.remember_check('ai', '连接可用')
        self.assertIn('连接可用', self.b.serviceHealth['ai'])
        self.b.setValue('ai', 'model', 'new-synthetic-model')
        self.assertIn('已过期', self.b.serviceHealth['ai'])

    def test_readonly_verification_uses_only_chapter_reads(self):
        course = dict(courseId='c', clazzId='l', cpi='fixture')
        targets = [dict(id='t', courseId='c', clazzId='l', pointId='p')]
        # Every operation outside this explicit read allowlist fails immediately.
        client = Mock(spec_set=['get_course_point'])
        output = io.StringIO()
        channel = Channel(output, io.StringIO(), lambda text: text)
        for flag in (True, False, 'true', None):
            output.seek(0); output.truncate()
            client.get_course_point.return_value = dict(points=[dict(id='p', has_finished=flag)])
            verify_chapters(client, channel, [course], targets)
            event = json.loads(output.getvalue().splitlines()[0])
            self.assertEqual(event['confirmed'], flag is True)
        client.get_course_point.return_value = dict(unexpected=[])
        with self.assertRaises(ValueError):
            verify_chapters(client, channel, [course], targets)
        channel.control = RunControl(channel.send)
        channel.control.cancelled.set()
        client.get_course_point.reset_mock()
        with self.assertRaises(Cancelled):
            verify_chapters(client, channel, [course], targets)
        client.get_course_point.assert_not_called()

    def test_readonly_fixture_matrix_rejects_unknown_login_and_business_failure(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/verification_cases.json').read_text(encoding='utf-8'))
        self.assertTrue(fixture['source'].startswith('synthetic'))
        course = dict(courseId='fixture-course', clazzId='fixture-class', cpi='fixture')
        targets = [dict(id='fixture', courseId='fixture-course', clazzId='fixture-class', pointId='fixture-point')]
        for case in fixture['cases']:
            with self.subTest(variant=case['variant']):
                client = Mock(spec_set=['get_course_point'])
                client.get_course_point.return_value = case['response']
                output = io.StringIO()
                channel = Channel(output, io.StringIO(), lambda text: text)
                if case.get('error'):
                    with self.assertRaises(ValueError):
                        verify_chapters(client, channel, [course], targets)
                    self.assertEqual(output.getvalue(), '')
                else:
                    verify_chapters(client, channel, [course], targets)
                    self.assertEqual(json.loads(output.getvalue().splitlines()[0])['confirmed'], case['expected'])

    def test_worker_readonly_branch_never_initializes_or_calls_write_routes(self):
        account = 'a' * 32
        cookie = Path(self.tmp.name) / 'synthetic-cookie.dat'
        cookie.write_bytes(b'synthetic-only')
        store = SimpleNamespace(get=lambda _: dict(username='fixture', uid='fixture-uid'), cookie_path=lambda _: cookie)
        client = Mock(spec_set=['login', 'get_course_list', 'get_course_point'])
        client.login.return_value = dict(status=True)
        client.get_course_list.return_value = [dict(courseId='c', clazzId='l', cpi='fixture')]
        client.get_course_point.return_value = dict(points=[dict(id='p', has_finished=True)])
        core = SimpleNamespace(create_client=Mock(return_value=client))
        config = to_payload(defaults())
        config['common'].update(username='fixture', password='', use_cookies=True)
        command = dict(action='verify', account_id=account, account_uid='fixture-uid', data_dir=self.tmp.name,
                       cookie_mtime_ns=cookie.stat().st_mtime_ns,
                       config=config, targets=[dict(id='t', courseId='c', clazzId='l', pointId='p')])
        paths = [Path(self.tmp.name) / folder / 'synthetic-intent.json' for folder in ('discussions', 'activities')]
        for path in paths:
            path.parent.mkdir(); path.write_bytes(b'{"state":"intent","synthetic":true}')
        output = io.StringIO()
        with patch('chaoxing_desktop.worker.load_core', return_value=core), \
                patch('chaoxing_desktop.accounts.AccountStore', return_value=store), \
                patch('api.cookies.configure_account'), \
                patch('api.cookies.save_cookies', side_effect=AssertionError('verification must not refresh local session')) as save, \
                patch('api.base.SessionManager.get_session', return_value=SimpleNamespace(cookies=SimpleNamespace(get_dict=lambda: {'_uid': 'fixture-uid'}))):
            real(Channel(output, io.StringIO(), lambda text: text), command)
        self.assertTrue(core.create_client.call_args.kwargs['courses_only'])
        save.assert_not_called()
        self.assertEqual([event['type'] for event in map(json.loads, output.getvalue().splitlines())], ['verification', 'verification_done'])
        self.assertTrue(all(path.read_bytes() == b'{"state":"intent","synthetic":true}' for path in paths))

    def test_readonly_cancel_after_inflight_read_prevents_next_course(self):
        courses = [dict(courseId=str(i), clazzId='l', cpi='fixture') for i in range(2)]
        targets = [dict(id=str(i), courseId=str(i), clazzId='l', pointId='p') for i in range(2)]
        channel = Channel(io.StringIO(), io.StringIO(), lambda text: text)
        channel.control = RunControl(channel.send)
        def read(*args):
            channel.control.cancelled.set()
            return dict(points=[dict(id='p', has_finished=True)])
        client = SimpleNamespace(get_course_point=Mock(side_effect=read))
        with self.assertRaises(Cancelled):
            verify_chapters(client, channel, courses, targets)
        self.assertEqual(client.get_course_point.call_count, 1)
        self.assertEqual(channel.output.getvalue(), '')

    def test_verification_cannot_clear_unknown_records_or_replace_failure_with_success(self):
        self.b.operation = 'verify'
        self.b.on_event(dict(type='tasks', tasks=[dict(id='t', title='Synthetic', course='Fixture')]))
        self.b._task_model.update_status('t', 'pending')
        # No authenticated operation account: ignore the evidence entirely.
        self.b.on_event(dict(type='verification', id='t', confirmed=True, checked_at='fixture', reason='fixture'))
        self.assertEqual(self.b.tasks[0]['status'], 'pending')
        self.b.on_finished(1)
        self.assertEqual(self.b.tasks[0]['status'], 'pending')

    def test_history_isolated_bounded_and_corruption_preserved(self):
        a, b = RunHistory(self.tmp.name, 'fixture-a'), RunHistory(self.tmp.name, 'fixture-b')
        for i in range(23):
            a.save(dict(id=str(i), time='fixture', state='stopped', counts={'pending': 1}, tasks=[]))
        self.assertEqual(len(a.read()[0]), 20)
        self.assertEqual(b.read()[0], [])
        a.path.write_bytes(b'broken-fixture')
        with self.assertRaises(ValueError):
            a.save(dict(id='next', time='fixture', state='stopped', counts={}, tasks=[]))
        self.assertEqual(a.path.read_bytes(), b'broken-fixture')

    def test_history_write_failure_remains_visible_after_worker_exit(self):
        self.b.operation = 'run'
        self.b.outcome = True
        self.b._history_run = 'synthetic-run'
        self.b._history_account = 'synthetic-account'
        with patch.object(RunHistory, 'save', side_effect=OSError('synthetic disk full')):
            self.b.on_finished(0)
        self.assertIn('synthetic disk full', self.b.historyError)

    def test_history_final_snapshot_can_be_read_after_restart_without_replay(self):
        self.prepare_courses()
        self.b.operation = 'run'
        self.b.outcome = True
        self.b.demo_mode = True
        self.b._history_account = 'offline-demo'
        self.b._history_run = 'synthetic-run'
        self.b._history_time = '2026-10-24T00:00:00+08:00'
        self.b.on_event(dict(type='tasks', tasks=[dict(id='t', title='fixture', course='fixture')]))
        self.b._task_model.update_status('t', 'pending')
        self.b.on_finished(0)
        reopened = Backend()
        reopened.demo_mode = True
        try:
            with patch.object(reopened.controller, 'start') as start:
                reopened.loadRunHistory()
                start.assert_not_called()
            self.assertEqual(reopened.runHistory[0]['tasks'][0]['status'], 'pending')
            self.assertEqual(reopened.runHistory[0]['courses'][0]['title'], 'Synthetic')
        finally:
            reopened.discardAndClose(); reopened.deleteLater()

    def test_ai_limit_shared_across_clients_retries_and_usage_unknown(self):
        config = to_payload(defaults())
        config['ai'].update(request_limit='2', min_interval_seconds='0', retries='0')
        channel = SimpleNamespace(send=lambda *args, **kwargs: None)
        clients = [AIClient(config['ai']) for _ in range(3)]
        for ai in clients:
            AnswerRouter(config, channel, ai=ai)
        response = Mock()
        response.json.return_value = dict(choices=[dict(message=dict(content='OK'))], usage=dict(input_tokens=3, output_tokens=2))
        with patch('chaoxing_desktop.answers.service_request', return_value=response) as request:
            self.assertEqual(clients[0].complete([]), 'OK')
            response.json.return_value = dict(choices=[dict(message=dict(content='OK'))])
            self.assertEqual(clients[1].complete([]), 'OK')
            with self.assertRaises(AIError):
                clients[2].complete([])
            self.assertEqual(request.call_count, 2)
        self.assertEqual(channel.ai_usage.snapshot(), dict(requests=2, limit=2, known=1, unknown=1, tokens=5))

    def test_ai_limit_concurrent_reservations_never_exceed_budget(self):
        usage = AIUsage(7)
        def reserve(_):
            try:
                usage.reserve()
                return True
            except AIBudgetExceeded:
                return False
        with ThreadPoolExecutor(max_workers=16) as pool:
            self.assertEqual(sum(pool.map(reserve, range(100))), 7)
        self.assertEqual(usage.snapshot()['requests'], 7)

    def test_ai_retries_consume_hard_limit_and_bad_usage_remains_unknown(self):
        import requests
        cfg = dict(to_payload(defaults())['ai'], request_limit='1', min_interval_seconds='0', retries='2')
        ai = AIClient(cfg)
        with patch('chaoxing_desktop.answers.service_request', side_effect=requests.Timeout('fixture')) as request, \
                patch('chaoxing_desktop.answers.wait'):
            with self.assertRaises(AIError) as error:
                ai.complete([])
        self.assertEqual(error.exception.kind, 'budget_exhausted')
        self.assertEqual(request.call_count, 1)
        self.assertEqual(ai.usage.snapshot()['unknown'], 1)
        for usage in (None, {}, {'total_tokens': True}, {'total_tokens': -1}, {'prompt_tokens': '3', 'completion_tokens': 2}):
            ai.usage.record({'usage': usage})
        self.assertEqual(ai.usage.snapshot()['known'], 0)

    def test_usage_event_failure_does_not_discard_ai_answer(self):
        config = dict(to_payload(defaults())['ai'], min_interval_seconds='0', retries='0')
        ai = AIClient(config)
        ai.usage.emit = Mock(side_effect=OSError('synthetic metrics failure'))
        response = Mock()
        response.json.return_value = dict(choices=[dict(message=dict(content='retained answer'))], usage=dict(total_tokens=5))
        with patch('chaoxing_desktop.answers.service_request', return_value=response):
            self.assertEqual(ai.complete([]), 'retained answer')

    def test_attention_five_reasons_incremental_filter_and_capacity(self):
        model = AttentionModel()
        proxy = AttentionFilter(model)
        resets = []
        model.modelReset.connect(lambda: resets.append(True))
        cases = [
            chapter_issue(dict(id='closed', status='skipped', title='未开放', course='fixture')),
            chapter_issue(dict(id='delay', status='pending', title='平台延迟', course='fixture')),
            record_issue('题目', dict(id='auth', stage='error', title='会话验证', reason='登录验证要求', task_id='auth')),
            record_issue('题目', dict(id='blank', stage='pending', title='答案不全', reason='空答案不自动提交', task_id='blank')),
            record_issue('讨论', dict(id='unknown', stage='publish_unknown', title='发布未知', task_status='pending', reason='结果未知')),
        ]
        for case in cases:
            model.upsert(case['id'], case)
        self.assertEqual(proxy.rowCount(), 5)
        proxy.set_filter('', 'unknown')
        self.assertEqual(proxy.rowCount(), 1)
        self.assertIn('禁止重复发送', proxy.data(proxy.index(0, 0), ROLE)['next'])
        self.assertIsNotNone(record_issue('讨论', dict(id='unknown', stage='publish_unknown', title='fixture', task_status='confirmed')))
        model.upsert('unknown', None)
        self.assertEqual(proxy.rowCount(), 0)
        self.assertEqual(resets, [])
        model.MAX_ROWS = 3
        for i in range(8):
            model.upsert(str(i), dict(cases[1], id=str(i)))
        self.assertEqual(model.rowCount(), 3)
        self.assertLessEqual(model.bytes, model.MAX_BYTES)
        self.assertGreater(model.evicted, 0)


if __name__ == '__main__':
    unittest.main()
