"""Anonymized native web contracts plus failure-injected activity integration."""
import copy
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing'))
from api.activity import ActivityAdapter, ActivityContext, parse_questions, trusted_url
from api.decode import decode_course_card
from api.responses import PlatformResponseError
from chaoxing_desktop.activity import (ActivityGenerator, ActivityRunner, ActivityOutcome, preview_context,
                                      random_options, validate_answer, structure_digest)
from chaoxing_desktop.activity_model import ActivityModel, safe_record, valid_record
from chaoxing_desktop.activity_store import ActivityStore, activity_key
from chaoxing_desktop.answers import AnswerRouter, AIError
from chaoxing_desktop.config import defaults, to_payload, Redactor, parse_text, serialize, validate
from chaoxing_desktop.control import Cancelled
from chaoxing_desktop.controller import Controller
from chaoxing_desktop.runtime import process_chapter, ChapterResult
from chaoxing_desktop.worker import Channel


def context():
    ctx = preview_context('提出一项课程建议。')
    return ActivityContext('student', 'course', 'class', 'mobilelearn:unit', 'activity', ctx.title,
                           copy.deepcopy(ctx.questions), can_submit=True, participation='absent')


def native_questions():
    # Actual observed schema; all identifiers, content and account data replaced.
    return dict(questioncount=3, questionlist=[
        dict(id='native-single', type=0, content='相同题干', ismust=1,
             options=json.dumps([dict(name='opt-10', content='支持'), dict(name='opt-19', content='不支持')]),
             jsonConfig={}, config=None, pageNum=0),
        dict(id='native-multiple', type=1, content='相同题干', ismust=1,
             options=json.dumps([dict(name='m-1', content='1'), dict(name='m-10', content='10'), dict(name='m-20', content='20')]),
             answerLimitMap=dict(min=1, max=2), jsonConfig={}, config=None, pageNum=0),
        dict(id='native-text', type=4, content='建议 / 逗号, [方括号]', ismust=1,
             options=None, jsonConfig={}, config=None, pageNum=0)])


def card_html(required=True, assignment=True, frame=True):
    prop = dict(module='insertvote', mid='mid-1', id='native-activity', title='章节活动', jobid='job-1')
    card = dict(property=prop, mid='mid-1', jobid='job-1', enc='TEMP-ENTRY', jtoken='TEMP-JOB', type='vote')
    if required is not None:
        card['job'] = required
    raw = dict(attachments=[card], defaults=dict(knowledgeid='chapter', ktoken='TEMP-KTOKEN', cardid='card'))
    return ('<script>mArg='+json.dumps(raw)+';</script>' if assignment else '') + (
        '<iframe module="insertvote" data=\''+json.dumps(dict(prop, id='old-clone-id'))+"'></iframe>" if frame else '')


class AIStub:
    def __init__(self, error=None, invalid=False):
        self.error, self.invalid, self.calls, self.checks = error, invalid, 0, 0
        self.budget_check = None
        self.messages = []

    def check_connection(self):
        self.checks += 1
        if self.budget_check:
            self.budget_check()

    def complete(self, messages):
        if self.budget_check:
            self.budget_check()
        self.calls += 1
        self.messages = copy.deepcopy(messages)
        if self.error:
            raise self.error
        if self.invalid:
            return '{"answers":[{"question_id":"unknown","option_ids":["BAD"]}]}'
        payload = json.loads(messages[1]['content'])
        return json.dumps(dict(answers=[dict(question_id=q['id'], **(
            dict(text='建议 / 保留逗号, 和 [括号]，不应拆分。') if q['type'] == 'text'
            else dict(option_ids=[q['options'][0]['id']]))) for q in payload['questions']]))


class FakeAdapter:
    def __init__(self):
        self.target = context()
        self.writes = self.resolves = self.callbacks = 0
        self.accepted = False
        self.confirmed = False
        self.unknown = self.cancel = self.reject = False
        self.after_resolve = None

    def resolve(self, *args):
        self.resolves += 1
        result = copy.deepcopy(self.target)
        if self.accepted and not self.unknown:
            result.participation, result.can_submit, result.receipt = 'existing', False, 'native-receipt'
        if self.after_resolve:
            self.after_resolve(result, self.resolves)
        return result

    def submit_once(self, ctx, answers):
        self.writes += 1
        self.submitted_answers = copy.deepcopy(answers)
        if self.cancel:
            raise Cancelled()
        if self.reject:
            raise PlatformResponseError('平台拒绝：长度不满足', 'business_error')
        self.accepted = True
        if self.unknown:
            raise TimeoutError('response lost')

    def finish_task_once(self, ctx):
        self.callbacks += 1

    def task_status(self, ctx):
        return 'confirmed' if self.confirmed else 'pending'


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = to_payload(defaults())
        self.config['activity'].update(enabled='true', auto_submit='true', choice_strategy='random', text_strategy='fixed_good')
        self.output = io.StringIO()
        self.channel = Channel(self.output, io.StringIO(), Redactor(self.config))
        self.router = AnswerRouter(self.config, self.channel)
        self.adapter = FakeAdapter()
        self.runner = ActivityRunner(self.config, self.channel, self.router, self.adapter, self.temp.name)
        self.course = dict(courseId='course', clazzId='class', title='课程')
        self.job = dict(type='activity', required=True, mid='mid', jobid='job')
        self.waiter = patch('chaoxing_desktop.activity.wait')
        self.waiter.start()

    def tearDown(self):
        self.waiter.stop()
        self.temp.cleanup()

    def run_activity(self):
        return self.runner.process(self.course, self.job, {}, 'task', '章节')

    def record(self):
        return json.loads(self.output.getvalue().splitlines()[-1])['record']

    def saved(self):
        return self.runner.store.load(activity_key(*self.adapter.target.identity))

    def test_config_migration_roundtrip_defaults_and_enums(self):
        cfg = parse_text('[ai]\nenabled=false\n')
        self.assertEqual(dict(cfg['activity']), dict(enabled='false', auto_submit='false', choice_strategy='ai', text_strategy='ai', reply_level='medium'))
        for key, value in [('choice_strategy', 'random'), ('text_strategy', 'fixed_good'), ('reply_level', 'detailed')]:
            cfg['activity'][key] = value
        validate(cfg)
        self.assertEqual(dict(cfg['activity']), dict(parse_text(serialize(cfg))['activity']))
        for key in ('enabled', 'auto_submit', 'choice_strategy', 'text_strategy', 'reply_level'):
            bad = defaults(); bad['activity'][key] = 'invalid'
            with self.assertRaises(ValueError):
                validate(bad)

    def test_cards_preserve_native_clone_ids_and_unknown_qualification(self):
        for value in (True, False, None):
            jobs, _ = decode_course_card(card_html(value))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]['type'], 'activity')
            self.assertEqual(jobs[0]['required'], value)
            self.assertEqual(jobs[0]['property']['id'], 'native-activity')
            self.assertEqual(jobs[0]['entry_property']['id'], 'old-clone-id')
        for text in (card_html(assignment=False), '<iframe module="insertvote" data="bad"></iframe>'):
            jobs, _ = decode_course_card(text)
            self.assertEqual(jobs[0]['type'], 'activity')
            self.assertIsNone(jobs[0]['required'])
        jobs, _ = decode_course_card(card_html(frame=False))
        self.assertEqual(jobs[0]['page_variant'], 'insertvote-v2')

    def test_module_versions_and_malicious_external_urls(self):
        html = card_html().replace('module="insertvote"', 'src="https://evil.test/ananas/modules/zt/vote/index-pc-new.html"')
        jobs, _ = decode_course_card(html)
        self.assertTrue(any(j['type'] == 'activity' and j['required'] is None for j in jobs))
        for suffix in ('?v=1', '?v=2'):
            text = card_html(assignment=False).replace('module="insertvote"', 'module="insertvote" src="/ananas/modules/zt/vote/index-pc-new.html'+suffix+'"')
            self.assertEqual(decode_course_card(text)[0][0]['type'], 'activity')
        for url in ('http://mobilelearn.chaoxing.com/a', 'https://evil.test/?x=https://mobilelearn.chaoxing.com',
                    'https://mobilelearn.chaoxing.com.evil.test/', 'https://u@mobilelearn.chaoxing.com/'):
            with self.assertRaises(PlatformResponseError):
                trusted_url(url)

    def test_parse_mixed_native_ids_same_titles_and_constraints(self):
        qs = parse_questions(native_questions())
        self.assertEqual([q['type'] for q in qs], ['single', 'multiple', 'text'])
        self.assertEqual(qs[0]['options'][1]['id'], 'opt-19')
        self.assertEqual((qs[1]['minimum'], qs[1]['maximum']), (1, 2))
        self.assertEqual(len({q['id'] for q in qs}), 3)
        for field, value in [('questioncount', 4), ('questionlist', []), ('questioncount', True)]:
            bad = native_questions(); bad[field] = value
            with self.assertRaises(PlatformResponseError):
                parse_questions(bad)

    def test_unknown_logic_media_and_matrix_fail_closed(self):
        for changes in (dict(type=99), dict(jsonConfig={'jumpTo': 'other'}), dict(pageNum=1),
                        dict(content='<img src="x">题干')):
            data = native_questions(); data['questionlist'][0].update(changes)
            self.assertEqual(parse_questions(data)[0]['type'], 'unsupported')
        self.adapter.target.questions[1].update(type='unsupported', reason='矩阵题未适配')
        result = self.run_activity()
        self.assertEqual(result.stage, 'pending')
        self.assertEqual(self.adapter.writes, 0)
        self.assertEqual(self.saved()['state'], 'draft')

    def test_local_modes_make_zero_ai_calls_and_fixed_is_exact(self):
        self.router.ai = Mock(side_effect=AssertionError('AI must not be used'))
        self.adapter.confirmed = True
        result = self.run_activity()
        self.assertEqual((result.stage, result.task_status), ('submitted', 'confirmed'))
        self.assertEqual(self.saved()['answers'][-1]['text'], '好')
        self.assertEqual(len(self.saved()['answers'][-1]['text']), 1)
        self.assertEqual(self.adapter.writes, 1)
        self.assertEqual(self.adapter.callbacks, 1)
        self.router.ai.complete.assert_not_called()
        self.router.ai.check_connection.assert_not_called()

    def test_disabled_nonrequired_unknown_and_passed_never_write(self):
        for required, enabled in [(True, 'false'), (False, 'true'), (None, 'true')]:
            self.job['required'] = required; self.config['activity']['enabled'] = enabled
            self.run_activity()
        self.job.update(required=True, isPassed=True)
        self.run_activity()
        self.assertEqual(self.adapter.resolves, 0)
        self.assertEqual(self.adapter.writes, 0)

    def test_passed_task_does_not_invent_own_participation(self):
        self.job['server_finished'] = True
        self.assertEqual(self.run_activity().stage, 'skipped')
        self.assertEqual(self.record()['task_status'], 'confirmed')
        self.assertEqual(self.record()['submit_status'], 'none')
        self.assertEqual(self.adapter.resolves, 0)

    def test_draft_reused_across_restart_and_not_marked_complete(self):
        self.config['activity']['auto_submit'] = 'false'
        self.assertEqual(self.run_activity().stage, 'draft')
        answers = self.saved()['answers']
        restarted = ActivityRunner(self.config, self.channel, self.router, self.adapter, self.temp.name)
        with patch('chaoxing_desktop.activity.random_options', side_effect=AssertionError('rerolled')):
            restarted.process(self.course, self.job, {}, 'other-chapter')
        self.assertEqual(self.saved()['answers'], answers)
        self.assertEqual(self.adapter.writes, 0)
        self.assertEqual(self.record()['task_status'], 'pending')

    def test_unknown_and_cancellation_preserve_intent_without_second_post(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel), tempfile.TemporaryDirectory() as directory:
                adapter = FakeAdapter(); adapter.unknown = True; adapter.cancel = cancel
                runner = ActivityRunner(self.config, self.channel, self.router, adapter, directory)
                if cancel:
                    with self.assertRaises(Cancelled):
                        runner.process(self.course, self.job, {})
                else:
                    self.assertEqual(runner.process(self.course, self.job, {}).stage, 'submit_unknown')
                restarted = ActivityRunner(self.config, self.channel, self.router, adapter, directory)
                self.config['activity']['reply_level'] = 'detailed'
                restarted.process(self.course, self.job, {}, 'other-task')
                self.assertEqual(adapter.writes, 1)
                record = restarted.store.load(activity_key(*adapter.target.identity))
                self.assertIn(record['state'], ('intent', 'submit_unknown'))

    def test_existing_and_explicit_rejection_do_not_retry(self):
        self.adapter.target.participation = 'existing'
        self.assertEqual(self.run_activity().stage, 'existing')
        self.assertEqual(self.adapter.writes, 0)
        with tempfile.TemporaryDirectory() as directory:
            self.adapter.target.participation = 'absent'; self.adapter.reject = True
            runner = ActivityRunner(self.config, self.channel, self.router, self.adapter, directory)
            self.assertEqual(runner.process(self.course, self.job, {}).stage, 'rejected')
            runner.process(self.course, self.job, {})
            self.assertEqual(self.adapter.writes, 1)

    def test_generation_constraints_and_mutation_before_submit(self):
        self.adapter.target.questions[-1]['min_length'] = 10
        self.assertEqual(self.run_activity().stage, 'pending')
        self.assertEqual(self.saved()['answers'][-1]['text'], '好')
        self.assertEqual(self.adapter.writes, 0)
        self.adapter.target.questions[-1]['min_length'] = 0
        self.adapter.after_resolve = lambda ctx, n: ctx.questions[0].update(title='changed') if n >= 3 else None
        self.run_activity()
        self.assertEqual(self.adapter.writes, 0)

    def test_random_constraints_disabled_exclusive_and_unknown_max(self):
        q = context().questions[1]
        for lo, hi in ((1, 1), (1, 2), (2, 3)):
            q.update(minimum=lo, maximum=hi)
            for _ in range(100):
                values = random_options(q)
                self.assertTrue(lo <= len(values) <= hi)
                self.assertEqual(len(values), len(set(values)))
        q['options'][0]['exclusive'] = True
        q.update(minimum=1, maximum=3)
        for _ in range(100):
            values = random_options(q)
            self.assertFalse('m-12' in values and len(values) > 1)
        q['options'] = [dict(id='none', text='不可选', disabled=True)]
        with self.assertRaises(ValueError):
            random_options(q)

    def test_ai_mixed_id_mapping_separator_text_and_budget_restoration(self):
        self.config['activity'].update(choice_strategy='ai', text_strategy='ai')
        ai = AIStub(); previous = Mock(); ai.budget_check = previous; self.router.ai = ai
        result = self.run_activity()
        self.assertEqual(result.stage, 'submitted')
        self.assertIn('/ 保留逗号, 和 [括号]', self.saved()['answers'][-1]['text'])
        self.assertIs(ai.budget_check, previous)
        self.assertEqual(ai.calls, 1)
        sent = ai.messages[1]['content']
        for secret in ('student', 'mobilelearn:unit', 'Cookie', 'TEMP-'):
            self.assertNotIn(secret, sent)

    def test_ai_error_only_explicit_choice_fallback_and_text_never_fixed(self):
        for choice, expected in [('ai', 0), ('ai_then_random', 2)]:
            ai = AIStub(error=AIError('network_error', 'network failed'))
            router = AnswerRouter(self.config, self.channel, ai=ai)
            cfg = dict(choice_strategy=choice, text_strategy='ai', reply_level='medium')
            result = ActivityGenerator(router).generate(context(), cfg)
            self.assertEqual(sum(a['valid'] for a in result), expected)
            self.assertEqual(result[-1]['text'], '')
        result = ActivityGenerator(self.router).generate(context(), dict(choice_strategy='ai_then_random', text_strategy='fixed_good', reply_level='medium'))
        self.assertFalse(result[0]['valid'])
        self.assertEqual(result[0]['source'], '')

    def test_ai_invalid_json_repairs_once_and_never_submits(self):
        self.config['activity'].update(choice_strategy='ai', text_strategy='ai')
        ai = AIStub(invalid=True); self.router.ai = ai
        self.assertEqual(self.run_activity().stage, 'pending')
        self.assertEqual(ai.calls, 2)
        self.assertEqual(self.adapter.writes, 0)
        self.assertTrue(all(not a['valid'] for a in self.saved()['answers']))

    def test_ai_reply_targets_and_twelve_request_activity_budget(self):
        for level, target in [('concise', '50–100'), ('medium', '150–250'), ('detailed', '350–600')]:
            ai = AIStub(); router = AnswerRouter(self.config, self.channel, ai=ai)
            ActivityGenerator(router).generate(context(), dict(choice_strategy='ai', text_strategy='ai', reply_level=level))
            self.assertIn(target, ai.messages[0]['content'])
        ai = AIStub(invalid=True); router = AnswerRouter(self.config, self.channel, ai=ai)
        ctx = context(); ctx.questions = [dict(ctx.questions[-1], id='text-'+str(i)) for i in range(100)]
        result = ActivityGenerator(router).generate(ctx, dict(choice_strategy='ai', text_strategy='ai', reply_level='medium'))
        self.assertLessEqual(ai.calls+ai.checks, 12)
        self.assertTrue(all(not a['valid'] for a in result))

    def test_store_corruption_and_capacity_keep_original_and_block_writes(self):
        key = activity_key(*self.adapter.target.identity)
        path = self.runner.store.path(key); path.parent.mkdir(parents=True)
        path.write_text('{damaged', encoding='utf-8')
        self.assertEqual(self.run_activity().stage, 'pending')
        self.assertEqual(path.read_text(), '{damaged')
        self.assertEqual(self.adapter.writes, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = ActivityStore(directory); store.MAX_TOTAL = 1
            with self.assertRaises(ValueError):
                store.save(key, state='draft', digest='d', strategy='s', answers=[])
        self.assertNotEqual(activity_key('another', *self.adapter.target.identity[1:]), key)

    def test_digest_order_independent_and_semantic_change_invalidates(self):
        ctx = context(); original = structure_digest(ctx)
        ctx.questions.reverse(); ctx.questions[-1]['options'].reverse()
        self.assertEqual(structure_digest(ctx), original)
        ctx.questions[-1]['options'][0]['text'] = 'changed'
        self.assertNotEqual(structure_digest(ctx), original)

    def test_ui_event_contract_snapshot_and_redaction(self):
        self.run_activity(); record = self.record()
        self.assertTrue(valid_record(record)); self.assertTrue(Controller._valid_event(dict(type='activity_result', record=record)))
        bad = copy.deepcopy(record); bad['answers'][0]['source'] = 'untrusted'
        self.assertFalse(valid_record(bad))
        model = ActivityModel(); self.assertTrue(model.upsert(record))
        record['answers'][-1]['text'] = 'mutated'
        self.assertEqual(model.rows[0]['answers'][-1]['text'], '好')
        self.assertIn('好', model.detail(record['id'])['detailText'])
        clean = safe_record(dict(self.record(), title='SECRET TITLE'), lambda t: t.replace('SECRET', '[redacted]'))
        self.assertNotIn('SECRET', clean['title'])

    def test_activity_pending_continues_independent_chapter_tasks(self):
        client = SimpleNamespace(get_job_list=lambda *args: ([dict(type='activity'), dict(type='read')], {}))
        from api.base import StudyResult
        with patch('chaoxing_desktop.runtime.process_job', side_effect=[ActivityOutcome('draft'), StudyResult.SUCCESS]) as process:
            self.assertEqual(process_chapter(client, {}, {}, 1), ChapterResult.PENDING)
            self.assertEqual(process.call_count, 2)

    def test_native_transport_encodes_values_once_and_never_redirects_or_retries(self):
        adapter = ActivityAdapter.__new__(ActivityAdapter)
        adapter.control = None
        adapter.session = SimpleNamespace(headers={}, cookies={})
        ctx = context(); ctx.form = dict(activeId='activity', courseId='course', classId='class', puid='student')
        ctx.detail_url = 'https://mobilelearn.chaoxing.com/page/questionnaire/answerQuestionChapter'
        answers = ActivityGenerator(self.router).generate(ctx, self.config['activity'])
        response = Mock(status_code=200, text='{"result":1}', url='https://mobilelearn.chaoxing.com/v2/apis/studentQuestion/doQuestion')
        response.json.return_value = dict(result=1)
        transport = Mock(); transport.headers = {}; transport.cookies = {}
        transport.request.return_value = response
        with patch('api.activity.requests.Session') as session:
            session.return_value.__enter__.return_value = transport
            adapter.submit_once(ctx, answers)
        call = transport.request.call_args
        self.assertFalse(call.kwargs['allow_redirects'])
        self.assertEqual(call.args[0], 'post')
        self.assertEqual([v for k, v in call.kwargs['data'] if k == 'questionId'], [q['id'] for q in ctx.questions])
        self.assertEqual([v for k, v in call.kwargs['data'] if k == 'answerdemo-text'], ['好'])
        self.assertEqual(transport.request.call_count, 1)
        self.assertEqual(transport.mount.call_args.args[1].max_retries.total, 0)

    def test_native_resolve_checks_actor_context_and_fid_zero_placeholder(self):
        adapter = ActivityAdapter.__new__(ActivityAdapter)
        adapter.client = SimpleNamespace(get_uid=lambda: 'student')
        adapter.control = None
        data = dict(native_questions(), fid=42, puid='student', pptActive=dict(id='native-activity', activeType=14, status=1, name='问卷'), pptUserAttend=None)
        adapter.data = Mock(return_value=data)
        url = 'https://mobilelearn.chaoxing.com/page/questionnaire/answerQuestionChapter?activeId=native-activity&courseId=course&classId=class&fid=0'
        adapter.read = Mock(return_value=('<input name="puid" value="student">', url))
        job = dict(page_variant='insertvote-v2', mid='mid', jobid='job', enc='TEMP', property=dict(id='native-activity'))
        info = dict(knowledgeid='chapter', ktoken='TEMP', cardid='card')
        ctx = adapter.resolve(self.course, job, info)
        self.assertEqual(ctx.namespace, 'mobilelearn:42')
        self.assertTrue(ctx.can_submit)
        self.assertNotIn('puid', ctx.form)
        self.assertEqual(ctx.form['preventsubmit'], '1')
        data['pptUserAttend'] = dict(status=3, id='receipt')
        self.assertEqual(adapter.resolve(self.course, job, info).participation, 'existing')
        for changes in (dict(puid='other'), dict(pptUserAttend=dict(status=3, uid='other')),
                        dict(pptUserAttend=dict(status=3, activeId='other'))):
            bad = copy.deepcopy(data); bad.update(changes); adapter.data.return_value = bad
            with self.assertRaises(PlatformResponseError):
                adapter.resolve(self.course, job, info)
        adapter.data.return_value = data
        adapter.read.return_value = ('<input name="puid" value="student">', url.replace('fid=0', 'fid=99'))
        with self.assertRaises(PlatformResponseError):
            adapter.resolve(self.course, job, info)

    def test_crash_after_intent_before_post_and_store_failure_never_write(self):
        original_send = self.channel.send
        def crash(kind, **values):
            if values.get('record', {}).get('stage') == 'submitting':
                raise Cancelled()
            original_send(kind, **values)
        self.channel.send = crash
        with self.assertRaises(Cancelled):
            self.run_activity()
        self.assertEqual(self.saved()['state'], 'intent')
        self.assertEqual(self.adapter.writes, 0)
        self.channel.send = original_send
        self.assertEqual(self.run_activity().stage, 'submit_unknown')
        self.assertEqual(self.adapter.writes, 0)
        with tempfile.TemporaryDirectory() as directory:
            runner = ActivityRunner(self.config, self.channel, self.router, self.adapter, directory)
            with patch.object(runner.store, 'save', side_effect=OSError('disk full')):
                self.assertEqual(runner.process(self.course, self.job, {}).stage, 'pending')
            self.assertEqual(self.adapter.writes, 0)

    def test_concurrent_chapters_share_lock_and_never_vote_twice(self):
        threads = [threading.Thread(target=self.run_activity) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(3)
            self.assertFalse(t.is_alive())
        self.assertEqual(self.adapter.writes, 1)

    def test_fallback_applies_to_all_batches_after_ai_auth_failure(self):
        ai = AIStub(error=AIError('auth_error', 'auth rejected'))
        router = AnswerRouter(self.config, self.channel, ai=ai)
        ctx = context(); ctx.questions = [dict(ctx.questions[0], id='q-'+str(i)) for i in range(11)]
        results = ActivityGenerator(router).generate(ctx, dict(choice_strategy='ai_then_random', text_strategy='fixed_good', reply_level='medium'))
        self.assertTrue(all(a['valid'] and a['source'] == 'random' for a in results))
        self.assertEqual(ai.calls, 1)


if __name__ == '__main__':
    unittest.main()
