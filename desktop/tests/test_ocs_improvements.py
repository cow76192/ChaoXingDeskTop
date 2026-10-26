"""Contracts for OCS-inspired desktop improvements; all requests are mocked."""
import io
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing'))
from api.answer import Tiku, TikuYanxi, TikuGo, TikuLike, TikuAdapter
from chaoxing_desktop.answers import AnswerRouter
from chaoxing_desktop.completion import completion_parts
from chaoxing_desktop.config import defaults, to_payload, parse_text, serialize, Redactor
from chaoxing_desktop.control import RunControl, Cancelled, ResumeFailed
from chaoxing_desktop.declarative import DeclarativeBank, TEMPLATE
from chaoxing_desktop.diagnostics import offline_check
from chaoxing_desktop.query_result import query_bank, safe_record
from chaoxing_desktop.worker import Channel


def response(body=None, status=200, headers=None):
    return SimpleNamespace(status_code=status, json=lambda: body, text='', headers=headers or {})


def question(**extra):
    return dict(dict(id='q', title='测试题', type='single', options='A.甲\nB.乙'), **extra)


class QueryContractTests(unittest.TestCase):
    def adapters(self):
        config = dict(defaults()['question_bank'], tokens='TEST_ONLY', request_interval='0',
                      request_timeout='5', request_retries='0', url='https://example.test', go_retry_times='1', go_min_interval='0')
        for cls in (TikuYanxi, TikuGo, TikuLike, TikuAdapter):
            bank = cls()
            bank.config_set(config)
            if cls is TikuLike:
                bank.load_config()
                bank._tokens, bank._balance = ['TEST_ONLY'], {'TEST_ONLY': 100}
            else:
                bank.init_tiku()
            yield bank

    def test_all_four_adapters_classify_http_auth_and_rate_errors(self):
        for bank in self.adapters():
            for http, expected in ((401, 'auth_error'), (403, 'auth_error'), (429, 'rate_limited'), (503, 'service_error')):
                with self.subTest(provider=type(bank).__name__, http=http), patch('api.answer.requests.Session.post', return_value=response(status=http)), patch('api.answer.time.sleep'):
                    result = query_bank('test', bank, question())
                    self.assertEqual(result.status, expected)
                    self.assertFalse(result.candidates)
                    self.assertGreaterEqual(result.requests, 1)

    def test_all_four_adapters_reject_malformed_json(self):
        for bank in self.adapters():
            broken = Mock(status_code=200, text='', headers={})
            broken.json.side_effect = ValueError('not JSON')
            with self.subTest(provider=type(bank).__name__), patch('api.answer.requests.Session.post', return_value=broken), patch('api.answer.time.sleep'):
                self.assertEqual(query_bank('test', bank, question()).status, 'protocol_error')

    def test_all_four_adapters_classify_explicit_quota_errors(self):
        bodies = {
            TikuYanxi: dict(code=0, data=dict(answer='余额不足')),
            TikuGo: dict(code=0, data='', msg='余额不足'),
            TikuLike: dict(message='余额不足'),
            TikuAdapter: dict(answer=dict(bestAnswer=[]), message='余额不足'),
        }
        for bank in self.adapters():
            with self.subTest(provider=type(bank).__name__), patch('api.answer.requests.Session.post', return_value=response(bodies[type(bank)])), patch('api.answer.time.sleep'):
                self.assertEqual(query_bank('test', bank, question()).status, 'quota_error')

    def test_timeout_is_not_a_miss(self):
        for bank in self.adapters():
            with self.subTest(provider=type(bank).__name__), patch('api.answer.requests.Session.post', side_effect=requests.Timeout()), patch('api.answer.time.sleep'):
                self.assertEqual(query_bank('test', bank, question()).status, 'timeout')

    def test_yanxi_snapshot_does_not_retain_previous_metadata(self):
        bank = next(self.adapters())
        bodies = [response(dict(code=1, data=dict(answer='乙', question='原题', ai=True, tags=[{'text': '测试'}]))),
                  response(dict(code=0, data=dict(answer='题库没有该题的答案')))]
        with patch('api.answer.requests.Session.post', side_effect=bodies):
            first = query_bank('yanxi', bank, question())
            second = query_bank('yanxi', bank, question())
        self.assertTrue(first.candidates[0].ai)
        self.assertEqual(first.candidates[0].title, '原题')
        self.assertEqual(second.status, 'miss')
        self.assertFalse(second.candidates)
        self.assertEqual(bank.last_result_question, '')

    def test_auth_error_disables_provider_for_remaining_questions(self):
        bank = next(self.adapters())
        router = AnswerRouter(to_payload(defaults()), Mock(), [('yanxi', bank)])
        with patch('api.answer.requests.Session.post', return_value=response(dict(code=0, data=dict(answer='Token 无效')))) as post:
            self.assertEqual(router.query_all([question(), question(id='q2')]), [None, None])
            self.assertEqual(post.call_count, 1)

    def test_budget_counts_actual_calls_across_repeated_work_attempts(self):
        config = to_payload(defaults())
        config['question_bank']['request_budget'] = '2'
        bank = next(self.adapters())
        bank._conf['request_retries'] = '5'
        router = AnswerRouter(config, Mock(), [('yanxi', bank)])
        with patch('api.answer.requests.Session.post', return_value=response(status=503)) as post, patch('api.answer.time.sleep'):
            router.query(question())
            router.query(question())
            self.assertEqual(post.call_count, 2)

    def test_retry_after_is_respected_and_budgeted(self):
        bank = Tiku()
        bank.api = 'https://example.test'
        bank.config_set({'request_retries': '1'})
        with patch('api.answer.requests.Session.post', side_effect=[response(status=429, headers={'Retry-After': '4'}), response()]), patch('chaoxing_desktop.control.time.sleep') as sleep:
            bank.request('post')
        sleep.assert_called_once_with(4)
        self.assertEqual(bank.query_requests, 2)

    def test_question_events_capture_rejection_then_ai_and_distinct_attempts(self):
        output = io.StringIO()
        channel = Channel(output, io.StringIO(), Redactor({}))
        config = to_payload(defaults())
        config['ai']['check_connection'] = 'false'
        bank = SimpleNamespace(_query=lambda q: '丙')
        router = AnswerRouter(config, channel, [('bank', bank)], SimpleNamespace(query=lambda q: '乙'))
        self.assertEqual(router.query(question()), '乙')
        self.assertEqual(router.query(question()), '乙')
        events = [json.loads(line) for line in output.getvalue().splitlines() if json.loads(line)['type'] == 'question_result']
        self.assertTrue(any(e['record']['stage'] == 'rejected' for e in events))
        self.assertEqual(events[-1]['record']['source'], 'ai')
        self.assertEqual(events[-1]['record']['query_attempts'], 1)
        self.assertNotEqual(events[0]['record']['id'], events[-1]['record']['id'])

    def test_credentials_equal_to_state_or_identifiers_do_not_corrupt_protocol(self):
        redactor = Redactor({'common': {'password': 'pending'}})
        row = safe_record({'stage': 'pending', 'task_id': 'pending', 'reason': 'pending',
                           'attempts': [{'status': 'miss', 'candidate': 'pending'}]}, redactor)
        self.assertEqual(row['stage'], 'pending')
        self.assertEqual(row['task_id'], 'pending')
        self.assertNotEqual(row['reason'], 'pending')
        self.assertNotEqual(row['attempts'][0]['candidate'], 'pending')

    def test_nested_results_strip_credentials_urls_and_base64(self):
        result = safe_record({'title': 'SECRET https://user:pass@example.test/key data:image/png;base64,AAAA',
                              'attempts': [{'candidate': 'SECRET', 'reason': 'x' * 9000}]}, Redactor({'ai': {'key': 'SECRET'}}))
        text = json.dumps(result)
        for value in ('SECRET', 'user:pass', 'example.test', 'AAAA'):
            self.assertNotIn(value, text)
        self.assertLessEqual(len(result['attempts'][0]['reason']), 1200)


class DeclarativeTests(unittest.TestCase):
    def bank(self, **definition):
        value = dict(TEMPLATE, **definition)
        config = dict(declarative_definition=json.dumps(value), declarative_token='TEST_TOKEN', request_retries='0')
        return DeclarativeBank(config)

    def test_credential_reference_and_multiple_candidates_are_snapshot_data(self):
        bank = self.bank(options_path='')
        with patch('api.answer.requests.Session.post', return_value=response({'data': [{'question': '测试题', 'answer': '丙'}, {'question': '测试题', 'answer': '乙'}]})) as post:
            channel = Mock()
            router = AnswerRouter(to_payload(defaults()), channel, [('json', bank)])
            self.assertEqual(router.query(question()), '乙')
            final = [call.kwargs['record'] for call in channel.send.call_args_list if call.args[0] == 'question_result'][-1]
            self.assertEqual(final['attempts'][0]['candidate'], '乙')
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer TEST_TOKEN')
        self.assertIs(post.call_args.kwargs['allow_redirects'], False)
        self.assertNotIn('cookies', post.call_args.kwargs)

    def test_redirect_is_not_followed_with_credentials(self):
        bank = self.bank(options_path='')
        with patch('api.answer.requests.Session.post', return_value=response(status=302)) as post:
            result = query_bank('json', bank, question())
        self.assertFalse(result.candidates)
        self.assertIs(post.call_args.kwargs['allow_redirects'], False)
        self.assertEqual(post.call_count, 1)

    def test_get_uses_query_parameters(self):
        bank = self.bank(method='GET', options_path='')
        with patch('api.answer.requests.Session.get', return_value=response({'data': []})) as get:
            self.assertEqual(query_bank('json', bank, question()).status, 'miss')
        self.assertEqual(get.call_args.kwargs['params']['question'], '测试题')

    def test_scripts_nested_handlers_and_bad_paths_are_rejected(self):
        changes = [{'handler': 'return fetch("https://example.test")'},
                   {'data': {'q': {'handler': 'return ()=>1'}}}, {'answer_path': 'data[0].answer'},
                   {'headers': {'Cookie': 'SESSION'}}, {'headers': {'Authorization': 'Bearer literal'}},
                   {'data': {'q': '${title.constructor}'}}, {'url': 'https://secret@example.test'},
                   {'data': {'q': '${title'}}, {'results_path': 5}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                self.bank(**change)

    def test_invalid_candidate_shape_is_protocol_error(self):
        bank = self.bank(options_path='')
        with patch('api.answer.requests.Session.post', return_value=response({'data': [{'answer': {'a': 1}}]})):
            self.assertEqual(query_bank('json', bank, question()).status, 'protocol_error')


class CompletionAndMigrationTests(unittest.TestCase):
    def test_offline_fixture_cases(self):
        cases = json.loads((Path(__file__).parent / 'fixtures/ocs_protocol_cases.json').read_text(encoding='utf-8'))
        router = AnswerRouter(to_payload(defaults()), Mock())
        for case in cases:
            with self.subTest(case=case['name']):
                self.assertEqual(router.normalize(case['answer'], case), case['expected'])

    def test_named_blanks_decode_and_serialize_without_concatenation(self):
        from bs4 import BeautifulSoup
        from api.decode import _process_question
        from api.base import Chaoxing, SessionManager
        html = '<div data="9"><div class="TiMu" data="2"></div><div class="Zy_TItle">填写两空</div><textarea name="answer9_1"></textarea><textarea name="answer9_2"></textarea></div>'
        parsed = _process_question(BeautifulSoup(html, 'lxml').div)
        self.assertEqual(parsed['blank_count'], 2)
        config = to_payload(defaults())
        router = AnswerRouter(config, Mock(), [('bank', SimpleNamespace(_query=lambda q: '["甲","乙"]'))])
        client = Chaoxing(tiku=router)
        session = Mock()
        session.get.return_value = response()
        session.get.return_value.text = html
        session.post.return_value = response({'status': True, 'msg': 'saved'})
        with patch.object(SessionManager, 'get_session', return_value=session), patch('api.base.decode_questions_info', return_value={'questions': [parsed]}):
            client.study_work({'courseId': 'c', 'clazzId': 'class'}, {'jobid': 'w', 'enc': 'test'}, {'knowledgeid': 'k', 'ktoken': 't', 'cpi': 'p'})
        form = session.post.call_args.kwargs['data']
        self.assertEqual(form['answer9_1'], '甲')
        self.assertEqual(form['answer9_2'], '乙')
        self.assertNotIn('已按空位填写', form.values())
        self.assertEqual(form['pyFlag'], '1')

    def test_unknown_blank_count_cannot_be_marked_complete(self):
        self.assertIsNone(completion_parts('甲；乙', None))
        self.assertIsNone(completion_parts('["甲"]', 2))
        self.assertEqual(completion_parts('甲；乙', 1), ['甲；乙'])

    def test_versioned_migration_is_idempotent_and_new_values_win(self):
        text = '[tiku]\ndelay=9\n[question_bank]\nyanxi_min_interval=2\n[extra]\nunknown=preserved\n'
        first = parse_text(text)
        self.assertEqual(first['question_bank']['yanxi_min_interval'], '2')
        self.assertEqual(first['format']['version'], '1')
        self.assertEqual(serialize(parse_text(serialize(first))), serialize(first))
        self.assertEqual(first['extra']['unknown'], 'preserved')
        for version in ('2', '-1', 'broken'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                parse_text('[format]\nversion=' + version)

    def test_declarative_secret_is_encrypted_cleared_and_not_in_public_template(self):
        from chaoxing_desktop.settings import serialize_settings, restore_credentials
        config = defaults()
        config['question_bank']['declarative_token'] = 'TEST_ONLY_SECRET'
        stored = serialize_settings(config)
        self.assertNotIn('TEST_ONLY_SECRET', stored)
        restored = parse_text(stored)
        restore_credentials(restored)
        self.assertEqual(restored['question_bank']['declarative_token'], 'TEST_ONLY_SECRET')
        restored['question_bank']['declarative_token'] = ''
        cleared = parse_text(serialize_settings(restored))
        restore_credentials(cleared)
        self.assertEqual(cleared['question_bank']['declarative_token'], '')
        self.assertNotIn('TEST_ONLY_SECRET', json.dumps(TEMPLATE))

    def test_offline_diagnostic_never_uses_network(self):
        with patch('requests.sessions.Session.request', side_effect=AssertionError('network')):
            self.assertIn('未连接真实服务', offline_check())


class ControlTests(unittest.TestCase):
    def test_resume_revalidates_once_and_blocks_on_expired_session(self):
        control = RunControl(Mock())
        control.resume_check = Mock()
        control.command({'command': 'pause'})
        control.command({'command': 'resume'})
        control.checkpoint()
        control.checkpoint()
        control.resume_check.assert_called_once()
        control.command({'command': 'resume'})
        control.resume_check.side_effect = ValueError('expired')
        with self.assertRaises(ResumeFailed):
            control.checkpoint()
        self.assertTrue(control.cancelled.is_set())
        with self.assertRaises(Cancelled):
            control.checkpoint(cancel_only=True)

    def test_cancel_before_platform_work_cannot_save_or_submit(self):
        from api.base import Chaoxing, SessionManager
        control = RunControl(Mock())
        control.command({'command': 'cancel'})
        client = Chaoxing(tiku=AnswerRouter(to_payload(defaults()), Mock()))
        client.control = control
        session = Mock()
        with patch.object(SessionManager, 'get_session', return_value=session), self.assertRaises(Cancelled):
            client.study_work({'courseId': 'c', 'clazzId': 'class'}, {'jobid': 'w', 'enc': 'e'}, {'knowledgeid': 'k', 'ktoken': 't', 'cpi': 'p'})
        session.post.assert_not_called()

    def test_cancel_interrupts_long_wait(self):
        control = RunControl(Mock())
        ended = threading.Event()
        def run():
            try:
                control.wait(60)
            except Cancelled:
                ended.set()
        thread = threading.Thread(target=run)
        thread.start()
        control.command({'command': 'cancel'})
        thread.join(1)
        self.assertTrue(ended.is_set())

    def test_pause_blocks_new_work_and_resume_releases_it(self):
        control = RunControl(Mock())
        control.command({'command': 'pause'})
        done = threading.Event()
        thread = threading.Thread(target=lambda: (control.checkpoint(), done.set()))
        thread.start()
        self.assertFalse(done.wait(.05))
        control.checkpoint(cancel_only=True)  # Current media may continue.
        control.command({'command': 'resume'})
        thread.join(1)
        self.assertTrue(done.is_set())
        self.assertEqual(control.epoch, 1)

    def test_manual_reply_is_correlated_and_cancel_is_not_an_answer(self):
        output = io.StringIO()
        channel = Channel(output, io.StringIO(), Redactor({}))
        channel.control = RunControl(channel.send)
        result = queue.Queue()
        thread = threading.Thread(target=lambda: result.put(channel.ask('测试')))
        thread.start()
        deadline = time.monotonic() + 1
        while not output.getvalue() and time.monotonic() < deadline:
            time.sleep(.005)
        request = json.loads(output.getvalue())
        channel.control.command({'command': 'reply', 'request_id': 'old-request', 'answer': 'stale'})
        channel.control.command({'command': 'reply', 'request_id': request['request_id'], 'answer': '乙'})
        thread.join(1)
        self.assertEqual(result.get_nowait(), '乙')

    def test_worker_pause_and_cooperative_cancel_use_real_subprocess(self):
        with tempfile.TemporaryDirectory() as data:
            process = subprocess.Popen([sys.executable, '-u', 'run.py', '--worker'], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
            try:
                command = dict(action='run', demo=True, selected=[['demo-101', '01']], config=to_payload(defaults()), data_dir=data)
                process.stdin.write(json.dumps(command) + '\n')
                process.stdin.flush()
                process.stdin.write('{"command":"pause"}\n')
                process.stdin.flush()
                # Resume and cancel share the same reader as manual replies.
                process.stdin.write('{"command":"resume"}\n{"command":"cancel"}\n')
                process.stdin.flush()
                output, errors = process.communicate(timeout=5)
                events = [json.loads(line) for line in output.splitlines()]
                self.assertEqual(process.returncode, 2, errors)
                self.assertEqual(events[-1]['type'], 'cancelled')
                self.assertTrue(any(e['type'] == 'control' for e in events))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == '__main__':
    unittest.main()
