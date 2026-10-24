"""Synthetic continuation contracts; no real account, session, course or service."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QGuiApplication
import requests
from chaoxing_desktop.qml_backend import Backend
from chaoxing_desktop.config import defaults, validate, ConfigValidationError, serialize, parse_text
from chaoxing_desktop.declarative import TEMPLATE, preview_definition
from chaoxing_desktop.verification import read_cards, verify_records
from chaoxing_desktop.worker import Channel
from chaoxing_desktop.control import RunControl, Cancelled
from chaoxing_desktop.controller import Controller
from chaoxing_desktop.run_history import RunHistory
from chaoxing_desktop.ai_usage import AIUsage
from chaoxing_desktop.activity import preview_context
from chaoxing_desktop.activity_model import safe_record as safe_activity
from chaoxing_desktop.discussion_model import safe_record as safe_discussion
from chaoxing_desktop.draft_copies import DraftCopies, make_copy, constraints, export_text
from chaoxing_desktop.log_store import AsyncLogStore
from chaoxing_desktop.models import LogModel
from chaoxing_desktop.release_info import RELEASE_URLS, verification_info
from chaoxing_desktop.ai_profiles import AIProfiles


def discussion_record(**extra):
    return safe_discussion(dict(dict(id='synthetic-discussion', run_id='synthetic-run', task_id='synthetic-task',
                       title='合成讨论', course='合成课程', chapter='合成章节', level='medium', source='ai',
                       stage='draft', content='合成草稿', task_status='pending', reason='', elapsed_ms=0), **extra), lambda s: s)


def activity_record():
    ctx = preview_context('合成文本题')
    answers = [dict(question_id=q['id'], source='fixed' if q['type'] == 'text' else 'random', valid=True, reason='',
                    **(dict(text='好') if q['type'] == 'text' else dict(option_ids=[q['options'][0]['id']]))) for q in ctx.questions]
    return safe_activity(dict(id='synthetic-activity', run_id='synthetic-run', task_id='synthetic-task',
                        title=ctx.title, course='合成课程', chapter='合成章节', kind='survey', stage='draft',
                        submit_status='draft', task_status='pending', reason='', elapsed_ms=0,
                        questions=ctx.questions, answers=answers), lambda s: s)


class ContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, CHAOXING_DESKTOP_DATA=self.tmp.name)
        self.env.start()
        self.network = patch('requests.sessions.Session.request', side_effect=AssertionError('offline only'))
        self.network.start()
        self.b = Backend()

    def tearDown(self):
        self.b.discardAndClose(); self.b.deleteLater(); self.app.processEvents()
        self.network.stop(); self.env.stop(); self.tmp.cleanup()

    def channel(self):
        return Channel(io.StringIO(), io.StringIO(), lambda s: s)

    def test_read_cards_never_uses_empty_chapter_completion(self):
        response = requests.Response()
        response.status_code = 200
        response.url = 'https://mooc1.chaoxing.com/mooc-ans/knowledge/cards'
        response._content = b'<script>mArg={"attachments":[],"defaults":{"knowledgeid":"synthetic-point"}};</script>'
        session = Mock(spec_set=['get'])
        session.get.return_value = response
        client = Mock(spec_set=[])  # No get_job_list/study_emptypage can be called.
        with patch('api.base.SessionManager.get_session', return_value=session):
            self.assertEqual(read_cards(client, self.channel(), dict(courseId='c', clazzId='l', cpi='fixture'), dict(id='synthetic-point')), [])
        self.assertEqual(session.get.call_count, 7)
        self.assertTrue(all(c.kwargs['allow_redirects'] is False for c in session.get.call_args_list))

    def test_card_identity_unknown_login_and_business_failure_fail_closed(self):
        for text in ('<html>unknown synthetic page</html>', '<html><input name="uname"><input name="password"></html>',
                     '{"status":false,"msg":"synthetic failure"}',
                     '<script>mArg={"attachments":[],"defaults":{"knowledgeid":"other"}};</script>'):
            response = requests.Response(); response.status_code = 200; response._content = text.encode()
            response.url = 'https://mooc1.chaoxing.com/mooc-ans/knowledge/cards'
            session = Mock(spec_set=['get']); session.get.return_value = response
            with patch('api.base.SessionManager.get_session', return_value=session), self.assertRaises(Exception):
                read_cards(Mock(spec_set=[]), self.channel(), dict(courseId='c', clazzId='l', cpi='fixture'), dict(id='p'))
            self.assertEqual(session.get.call_count, 1)

    def test_readonly_personal_evidence_matrix_zero_write_and_intents_unchanged(self):
        course = dict(courseId='c', clazzId='l', cpi='fixture')
        target = dict(id='t'); point = dict(id='p')
        for kind in ('discussion', 'activity'):
            for state in ('existing', 'absent', 'unknown', 'error'):
                ch = self.channel()
                adapter = Mock(spec_set=['resolve', 'own_reply', 'task_status'])
                adapter.resolve.return_value = SimpleNamespace(participation=state)
                adapter.own_reply.return_value = SimpleNamespace(reply_id='synthetic-own' if state == 'existing' else '', known=state != 'unknown')
                adapter.task_status.return_value = 'pending'
                if state == 'error':
                    adapter.resolve.side_effect = ValueError('synthetic identity error')
                folder = Path(self.tmp.name) / ('discussions' if kind == 'discussion' else 'activities')
                folder.mkdir(exist_ok=True); intent = folder / 'synthetic.json'; intent.write_bytes(b'{"state":"intent"}')
                with patch('chaoxing_desktop.verification.read_cards', return_value=[(dict(type=kind, mid='m'), dict(cardid='card'))]), \
                        patch('api.discussion.DiscussionAdapter', return_value=adapter), patch('api.activity.ActivityAdapter', return_value=adapter):
                    verify_records(Mock(spec_set=[]), ch, course, target, point)
                event = json.loads(ch.output.getvalue())
                self.assertTrue(Controller._valid_event(event))
                self.assertEqual(event['participation'], 'unknown' if state == 'error' else state)
                self.assertEqual(intent.read_bytes(), b'{"state":"intent"}')
                self.assertNotIn('content', event)

    def test_readonly_cancel_stops_personal_lookup(self):
        ch = self.channel(); ch.control = RunControl(ch.send)
        adapter = Mock(spec_set=['resolve', 'own_reply', 'task_status'])
        def resolve(*args):
            ch.control.cancelled.set()
            return SimpleNamespace()
        adapter.resolve.side_effect = resolve
        with patch('chaoxing_desktop.verification.read_cards', return_value=[(dict(type='discussion', mid='m'), {})]), \
                patch('api.discussion.DiscussionAdapter', return_value=adapter), self.assertRaises(Cancelled):
            verify_records(Mock(spec_set=[]), ch, dict(courseId='c', clazzId='l'), dict(id='t'), dict(id='p'))
        adapter.own_reply.assert_not_called(); adapter.task_status.assert_not_called()
        self.assertEqual(ch.output.getvalue(), '')

    def test_invalid_readonly_event_rejected(self):
        self.assertFalse(Controller._valid_event(dict(type='record_verification', kind='activity', participation='absent')))
        self.b.operation = 'verify'; self.b.operation_account = 'synthetic-account'
        self.b._task_model.reset([dict(id='t', title='fixture', course='fixture', status='success')])
        with patch.object(self.b, 'account_store', SimpleNamespace(active='synthetic-account')):
            self.b.on_event(dict(type='verification', id='t', confirmed=False, checked_at='fixture', reason='fresh pending'))
            self.assertEqual(self.b.tasks[0]['status'], 'pending')
            self.b.on_event(dict(type='verification', id='t', confirmed=True, checked_at='fixture', reason='fresh positive'))
            self.assertEqual(self.b.tasks[0]['status'], 'success')

    def test_template_preview_routing_mapping_rejected_scripts_and_no_literals(self):
        raw = copy.deepcopy(TEMPLATE)
        raw['headers']['X-Extra'] = 'SYNTHETIC_PRIVATE_LITERAL'
        definition, text = preview_definition(json.dumps(raw))
        self.assertIsNotNone(definition)
        self.assertIn('example.test', text); self.assertIn('POST', text); self.assertIn('answer_path', text)
        self.assertNotIn('SYNTHETIC_PRIVATE_LITERAL', text)
        raw['handler'] = 'SYNTHETIC_SCRIPT_BODY'
        definition, text = preview_definition(json.dumps(raw))
        self.assertIsNone(definition); self.assertIn('handler', text); self.assertNotIn('SYNTHETIC_SCRIPT_BODY', text)

    def test_template_import_confirmation_cancel_stale_invalid_and_accept(self):
        path = Path(self.tmp.name) / 'template.json'; path.write_text(json.dumps(TEMPLATE), encoding='utf-8')
        events = []; self.b.definitionPreviewRequested.connect(lambda text, valid: events.append((text, valid)))
        original = self.b.config['question_bank']['declarative_definition']
        with patch('chaoxing_desktop.qml_backend.QFileDialog.getOpenFileName', return_value=(str(path), '')):
            self.b.definitionAction('import'); self.assertEqual(self.b.config['question_bank']['declarative_definition'], original)
            self.b.finishDefinitionImport(False); self.assertEqual(self.b.config['question_bank']['declarative_definition'], original)
            self.b.definitionAction('import'); self.b.config['question_bank']['declarative_definition'] = 'changed'
            self.b.finishDefinitionImport(True); self.assertEqual(self.b.config['question_bank']['declarative_definition'], 'changed')
            self.b.config['question_bank']['declarative_definition'] = original
            self.b.definitionAction('import'); self.b.finishDefinitionImport(True)
            self.assertEqual(json.loads(self.b.config['question_bank']['declarative_definition']), TEMPLATE)
            path.write_text(json.dumps(dict(TEMPLATE, handler='x')), encoding='utf-8')
            self.b.definitionAction('import'); self.assertFalse(events[-1][1]); self.assertIsNone(self.b._definition_import)

    def test_non_numeric_validation_locates_choice_and_multiline(self):
        targets = []; self.b.fieldRequested.connect(lambda section, key: targets.append((section, key)))
        for section, key, value in [('discussion', 'reply_level', 'invalid'), ('activity', 'choice_strategy', 'invalid'),
                                    ('notification', 'provider', 'invalid'), ('question_bank', 'declarative_definition', '{')]:
            previous = self.b.config[section][key]; self.b.config[section][key] = value
            self.assertFalse(self.b.save()); self.assertEqual(targets[-1], (section, key))
            self.b.config[section][key] = previous
        config = defaults(); config['ai'].update(enabled='true', endpoint='invalid', key='synthetic', model='synthetic')
        with self.assertRaises(ConfigValidationError) as raised:
            validate(config, services=True)
        self.assertEqual((raised.exception.section, raised.exception.key), ('ai', 'endpoint'))

    def test_history_optional_corruption_and_duplicates_preserve_file(self):
        history = RunHistory(self.tmp.name, 'synthetic')
        good = dict(id='r', time='fixture', state='running', counts={}, tasks=[])
        for bad in [dict(good, ai={'tokens': -1}), dict(good, total=True), dict(good, courses=[dict(title='x', courseId=3)])]:
            raw = json.dumps(dict(version=1, runs=[bad])).encode(); history.path.parent.mkdir(exist_ok=True); history.path.write_bytes(raw)
            with self.assertRaises(ValueError): history.save(good)
            self.assertEqual(history.path.read_bytes(), raw)
        history.path.write_text(json.dumps(dict(version=1, runs=[good, good])), encoding='utf-8')
        with self.assertRaises(ValueError): history.read()

    def test_history_snapshot_exhaustion_atomic_failure_conflict_and_restart(self):
        history = RunHistory(self.tmp.name, 'synthetic')
        summary = dict(id='r', time='fixture', state='running', counts={'pending': 1}, tasks=[])
        history.save(summary); raw = history.path.read_bytes()
        with patch.object(history, 'MAX_BYTES', len(raw) - 1), self.assertRaises(ValueError): history.save(summary)
        self.assertEqual(history.path.read_bytes(), raw)
        with patch.object(Path, 'replace', side_effect=OSError('synthetic disk full')), self.assertRaises(OSError): history.save(dict(summary, state='stopped'))
        self.assertEqual(history.path.read_bytes(), raw)
        from chaoxing_desktop.storage import write_if_unchanged
        with self.assertRaises(ValueError): write_if_unchanged(history.path, b'new', b'wrong revision')
        self.assertEqual(RunHistory(self.tmp.name, 'synthetic').read()[0][0]['state'], 'running')

    def test_recovery_reloads_before_selection_never_starts_run(self):
        self.b.demo_mode = True
        RunHistory(self.tmp.name, 'offline-demo').save(dict(id='r', time='fixture', state='stopped', counts={},
            tasks=[dict(title='t', course='c', status='pending', courseId='c', clazzId='l')]))
        with patch.object(self.b, 'begin') as begin, patch.object(self.b.controller, 'start') as start:
            self.b.prepareRecovery('r'); begin.assert_called_once_with('courses', True); start.assert_not_called()
            self.b.on_event(dict(type='courses', demo=True, courses=[dict(courseId='c', clazzId='l', title='fresh')]))
            self.assertEqual(self.b.selected, {('c', 'l')}); self.assertIsNone(self.b._recovery); start.assert_not_called()
        self.assertIn('手动开始', self.b.message)

    def test_recovery_identity_change_and_legacy_cannot_select(self):
        self.b.demo_mode = True
        history = RunHistory(self.tmp.name, 'offline-demo')
        history.save(dict(id='r', time='fixture', state='stopped', counts={}, tasks=[dict(title='t', course='c', status='pending')]))
        with patch.object(self.b, 'begin') as begin:
            self.b.prepareRecovery('r'); begin.assert_not_called()
        self.b._recovery = dict(account='old', uid='old', wanted={('c', 'l')}, demo=False)
        self.b.on_event(dict(type='courses', demo=False, courses=[dict(courseId='c', clazzId='l', title='fresh')]))
        self.assertEqual(self.b.selected, set()); self.assertIn('身份已变化', self.b.message)

    def test_abnormal_exit_saves_stopped_tasks_and_no_replay(self):
        self.b.operation = 'run'; self.b.demo_mode = True
        self.b._history_account = 'offline-demo'; self.b._history_run = 'r'; self.b._history_time = 'fixture'
        self.b.on_event(dict(type='tasks', tasks=[dict(id='t', title='fixture', course='fixture', courseId='c', clazzId='l', pointId='p')]))
        with patch.object(self.b.controller, 'start') as start:
            self.b.on_finished(7); start.assert_not_called()
        row = RunHistory(self.tmp.name, 'offline-demo').read()[0][0]
        self.assertEqual(row['state'], '后台异常退出'); self.assertEqual(row['tasks'][0]['status'], 'stopped')
        self.assertEqual(row['tasks'][0]['pointId'], 'p')

    def test_token_alert_once_missing_usage_unknown_and_persistence(self):
        events = []; usage = AIUsage(0, lambda kind, **kw: events.append((kind, kw)), token_warning=5)
        for body in ({}, {'usage': {'input_tokens': 3, 'output_tokens': 2}}, {'usage': {'total_tokens': 4}}):
            usage.reserve(); usage.record(body)
        self.assertEqual(usage.snapshot()['unknown'], 1); self.assertEqual(usage.snapshot()['tokens'], 9)
        self.assertEqual(sum(kind == 'log' for kind, _ in events), 1)
        self.b.config['ai']['token_warning'] = '123'; self.assertTrue(self.b.save())
        self.assertEqual(parse_text(serialize(self.b.config, include_secrets=False))['ai']['token_warning'], '123')

    def test_draft_constraints_native_ids_counts_text_and_unknown_readonly(self):
        row = make_copy('activity', activity_record()); self.assertEqual(constraints(row), [])
        row['answers'].pop(); self.assertTrue(constraints(row))
        row = make_copy('activity', activity_record()); row['answers'][0]['option_ids'] = ['unknown']; self.assertTrue(constraints(row))
        row = make_copy('activity', activity_record()); row['answers'][0]['option_ids'] *= 2; self.assertTrue(constraints(row))
        row = make_copy('discussion', discussion_record()); row['content'] = 'x'*1001; self.assertTrue(constraints(row))
        for stage in ('publish_unknown', 'submitting', 'existing', 'published'):
            with self.assertRaises(ValueError): make_copy('discussion', discussion_record(stage=stage))
        pending = activity_record(); pending.update(stage='pending', submit_status='draft'); pending['answers'][0]['option_ids'] = []
        self.assertTrue(constraints(make_copy('activity', pending)))
        pending['submit_status'] = 'unknown'
        with self.assertRaises(ValueError): make_copy('activity', pending)

    def test_crash_or_stop_blocks_editing_stale_draft_events(self):
        self.b.demo_mode = True; source = discussion_record(); self.b._discussion_model.upsert(source)
        self.b.openDraftCopy('discussion', source['id']); self.assertTrue(self.b.draftEditable)
        self.b.operation = 'run'; self.b.on_finished(9)
        self.assertFalse(self.b.draftEditable)
        self.b.openDraftCopy('discussion', source['id']); self.assertIn('早于已保存意图', self.b.message)

    def test_draft_versions_account_isolation_corruption_capacity_and_atomicity(self):
        store = DraftCopies(self.tmp.name, 'a'); row = make_copy('discussion', discussion_record())
        updated = store.save(row); self.assertEqual(updated['version'], 1)
        self.assertEqual(DraftCopies(self.tmp.name, 'b').read()[0], [])
        with self.assertRaises(ValueError): store.save(row)
        raw = store.path.read_bytes()
        with patch.object(store, 'MAX_ROWS', 1), self.assertRaises(ValueError): store.save(make_copy('discussion', discussion_record(id='other')))
        with patch.object(store, 'MAX_BYTES', len(raw) - 1), self.assertRaises(ValueError): store.save(updated)
        with patch.object(Path, 'replace', side_effect=OSError('synthetic disk full')), self.assertRaises(OSError): store.save(updated)
        self.assertEqual(store.path.read_bytes(), raw)
        store.path.write_bytes(b'broken');
        with self.assertRaises(ValueError): store.save(updated)
        self.assertEqual(store.path.read_bytes(), b'broken')

    def test_draft_copy_edits_do_not_touch_source_or_intents_and_lock_on_change(self):
        self.b.demo_mode = True; source = discussion_record(); self.b._discussion_model.upsert(source)
        self.b.openDraftCopy('discussion', source['id']); self.assertTrue(self.b.draftEditable)
        self.b.setDraftContent('人工意见'); self.b.saveDraftCopy()
        self.assertEqual(self.b._discussion_model.rows[0], source)
        self.assertEqual(self.b._draft['version'], 1); self.assertIn('人工意见', export_text(self.b._draft))
        self.b._discussion_model.upsert(discussion_record(stage='publish_unknown'))
        self.assertFalse(self.b.draftEditable); self.b.setDraftContent('should not apply')
        self.assertEqual(self.b._draft['content'], '人工意见')
        self.b.saveDraftCopy(); self.assertIn('只读', self.b.message)
        self.assertFalse((Path(self.tmp.name) / 'discussions').exists()); self.assertFalse((Path(self.tmp.name) / 'activities').exists())

    def test_draft_100_questions_100_options_bounded_and_roundtrip(self):
        source = activity_record(); q = source['questions'][0]
        source['questions'] = [dict(q, id=f'synthetic-{i}', title=f'合成第 {i} 题', options=[dict(id=f'option-{j}', text=f'合成选项 {j}') for j in range(100)]) for i in range(100)]
        source['answers'] = [dict(question_id=q['id'], option_ids=['option-99'], source='random', valid=True, reason='') for q in source['questions']]
        row = make_copy('activity', source); self.assertEqual(constraints(row), [])
        store = DraftCopies(self.tmp.name, 'synthetic'); store.save(row)
        self.assertEqual(len(store.read()[0][0]['source']['questions']), 100)

    def test_draft_oversized_input_cannot_silently_save_or_export_old_text(self):
        self.b.demo_mode = True; source = discussion_record(); self.b._discussion_model.upsert(source)
        self.b.openDraftCopy('discussion', source['id']); self.b.setDraftContent('x'*12001)
        self.assertIn('未进入副本', self.b.draftFeedback)
        self.b.saveDraftCopy(); self.assertFalse(DraftCopies(self.tmp.name, 'offline-demo').path.exists())
        with patch('chaoxing_desktop.qml_backend.QFileDialog.getSaveFileName') as dialog:
            self.b.exportDraftCopy(False); dialog.assert_not_called()
        self.b.setDraftContent('已修正'); self.b.saveDraftCopy()
        self.assertEqual(self.b._draft['version'], 1); self.assertFalse(self.b._draft_input_errors)

    def test_delete_copy_checks_version_and_keeps_unknown_intents(self):
        store = DraftCopies(self.tmp.name, 'synthetic')
        first = store.save(make_copy('discussion', discussion_record()))
        second = store.save(make_copy('discussion', discussion_record(id='other')))
        for name in ('discussions', 'activities'):
            path = Path(self.tmp.name) / name / 'synthetic.json'; path.parent.mkdir(); path.write_bytes(b'{"state":"intent"}')
        with self.assertRaises(ValueError): store.delete(first['id'], first['version'] - 1)
        store.delete(first['id'], first['version'])
        self.assertEqual([r['id'] for r in store.read()[0]], [second['id']])
        self.assertTrue(all((Path(self.tmp.name) / name / 'synthetic.json').read_bytes() == b'{"state":"intent"}' for name in ('discussions', 'activities')))

    def test_log_capacity_eviction_queue_rejection_and_write_failure_visible(self):
        model = LogModel(); model.MAX_ROWS = 2
        for i in range(3): model.append(str(i))
        model.flush(); model.append('3'); model.flush()
        self.assertEqual(model.evicted, 2); self.assertEqual(model.snapshot(), ['2', '3']); model.clear()
        sink = AsyncLogStore(); sink.MAX_PENDING_BYTES = 1
        with self.assertRaises(OSError): sink.append('', 'synthetic')
        self.assertEqual(sink.metrics()['dropped_lines'], 1); sink.close()
        with patch.object(self.b.log_store.sink, 'append_many', side_effect=OSError('synthetic disk full')):
            self.b.append_log('synthetic'); self.assertTrue(self.b._progress_timer.isActive())
            self.assertTrue(self.b.log_store.flush())
        self.app.processEvents()
        self.assertEqual(self.b.log_store.metrics()['failed_batches'], 1)
        self.assertIn('失败批次 1', self.b.capacityInfo); self.assertIn('synthetic disk full', self.b.log_save_error)

    def test_release_fixed_manual_destinations_copy_has_no_profile_or_credentials(self):
        self.b.config['common']['username'] = 'SYNTHETIC_PRIVATE_ACCOUNT'
        with patch('PySide6.QtGui.QDesktopServices.openUrl', return_value=True) as open_url:
            self.b.releaseAction('untrusted-url'); open_url.assert_not_called()
            self.b.releaseAction('latest'); self.assertEqual(open_url.call_args.args[0].toString(), RELEASE_URLS['latest'])
        self.b.releaseAction('copy'); text = QGuiApplication.clipboard().text()
        self.assertEqual(text, verification_info()); self.assertNotIn(self.tmp.name, text)
        self.assertNotIn('SYNTHETIC_PRIVATE_ACCOUNT', text); self.assertIn('未执行安装包校验', text)

    def test_ai_profiles_encrypt_switch_without_key_crossover_or_network(self):
        self.b.config['ai'].update(endpoint='https://synthetic-a.invalid/v1', key='SYNTHETIC_KEY_A', model='fixture-a', vision='false')
        self.b.aiProfileAction('save', '默认档案')
        a = self.b.listAiProfiles()[0]['id']
        self.b.config['ai'].update(endpoint='https://synthetic-b.invalid/v1', key='SYNTHETIC_KEY_B', model='fixture-b', vision='true')
        self.b.aiProfileAction('save', '视觉档案')
        b = self.b.listAiProfiles()[0]['id']
        path = AIProfiles(self.tmp.name).path; raw = path.read_bytes()
        for secret in (b'SYNTHETIC_KEY_A', b'SYNTHETIC_KEY_B', b'synthetic-a.invalid', b'fixture-a'):
            self.assertNotIn(secret, raw)
        self.b.aiProfileAction('load', a); self.assertEqual(self.b.config['ai']['key'], 'SYNTHETIC_KEY_A')
        self.assertEqual(self.b.config['ai']['vision'], 'false')
        self.b.aiProfileAction('load', b); self.assertEqual(self.b.config['ai']['key'], 'SYNTHETIC_KEY_B')
        self.assertEqual(self.b.config['ai']['vision'], 'true')
        self.b.aiProfileAction('delete', b); self.assertEqual(self.b.config['ai']['key'], 'SYNTHETIC_KEY_B')
        self.assertEqual(len(self.b.listAiProfiles()), 1)

    def test_ai_profiles_busy_decryption_failure_corruption_and_capacity_preserve_data(self):
        store = AIProfiles(self.tmp.name); config = defaults()
        key = store.save('默认档案', config); raw = store.path.read_bytes()
        self.b.controller.active = True
        self.b.aiProfileAction('load', key); self.assertEqual(self.b.config['ai']['model'], config['ai']['model'])
        self.assertIn('锁定', self.b.message); self.b.controller.active = False
        with patch('chaoxing_desktop.credentials.unprotect', side_effect=OSError('synthetic DPAPI failure')):
            with self.assertRaises(ValueError): store.load(key)
            with self.assertRaises(ValueError): store.save('默认档案', config)
        self.assertEqual(store.path.read_bytes(), raw)
        with patch.object(store, 'MAX_ROWS', 1), self.assertRaises(ValueError): store.save('other', config)
        with patch('chaoxing_desktop.credentials.protect', side_effect=OSError('synthetic DPAPI failure')), self.assertRaises(ValueError): store.save('other', config)
        self.assertEqual(store.path.read_bytes(), raw)
        store.path.write_bytes(b'broken')
        with self.assertRaises(ValueError): store.save('new', config)
        self.assertEqual(store.path.read_bytes(), b'broken')

    def test_ai_profile_switch_invalidates_service_health_without_changing_other_policy(self):
        self.b.config['ai']['model'] = 'fixture-a'; self.b.aiProfileAction('save', 'a')
        a = self.b.listAiProfiles()[0]['id']
        self.b.config['ai']['model'] = 'fixture-b'; self.b.remember_check('ai', 'synthetic test')
        self.b.config['activity']['auto_submit'] = 'false'
        self.b.aiProfileAction('load', a)
        self.assertIn('过期', self.b.serviceHealth['ai'])
        self.assertEqual(self.b.config['activity']['auto_submit'], 'false')
        self.assertIn('视觉', self.b.ai_status)


if __name__ == '__main__':
    unittest.main()
