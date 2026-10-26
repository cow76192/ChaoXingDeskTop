"""Synthetic regressions for the 2026-10-26 repair matrix. Zero live writes."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import requests
from bs4 import BeautifulSoup
from PySide6.QtWidgets import QApplication
from api.base import Chaoxing, SessionManager, StudyResult
from api.decode import _process_question
from api.responses import PlatformResponseError
from chaoxing_desktop.answers import AIClient, AIError, AnswerRouter
from chaoxing_desktop.completion import completion_parts
from chaoxing_desktop.config import defaults, to_payload
from chaoxing_desktop.controller import Controller
from chaoxing_desktop.control import RunControl, Cancelled
from chaoxing_desktop.declarative import DeclarativeBank, TEMPLATE, validate_definition
from chaoxing_desktop.qml_backend import Backend
from chaoxing_desktop.verification import Progress, read_cards, verify_chapters, verify_records
from chaoxing_desktop.worker import Channel
from test_performance_regressions import OutputProcess
from test_workbench_continuation import activity_record, discussion_record


def channel():
    return Channel(io.StringIO(), io.StringIO(), lambda s: s)


def events(ch, kind=None):
    rows = list(map(json.loads, ch.output.getvalue().splitlines()))
    return [r for r in rows if kind is None or r['type'] == kind]


def question(fields, qid='9'):
    return _process_question(BeautifulSoup(f'<div data="{qid}"><div class="TiMu" data="2"></div><div class="Zy_TItle">Synthetic</div>{fields}</div>', 'lxml').div)


def response(text):
    r = requests.Response(); r.status_code = 200
    r.url = 'https://mooc1.chaoxing.com/mooc-ans/knowledge/cards'; r._content = text.encode()
    return r


class Repairs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, CHAOXING_DESKTOP_DATA=self.tmp.name); self.env.start()
        self.net = patch('requests.sessions.Session.request', side_effect=AssertionError('offline only')); self.net.start()
        self.course = dict(courseId='c', clazzId='l', cpi='fixture')
        self.target = dict(id='t', courseId='c', clazzId='l', pointId='p')

    def tearDown(self):
        self.net.stop(); self.env.stop(); self.tmp.cleanup()

    def router(self, **extra):
        return AnswerRouter(to_payload(defaults()), channel(), **extra)

    def save(self, qs, answers, submit=False, result=None):
        router = self.router(); router.SUBMIT = submit; router.DISABLE = False
        router.query_all = Mock(return_value=answers)
        client = Chaoxing(tiku=router)
        session = Mock(); session.get.return_value = SimpleNamespace(status_code=200, text='fixture')
        session.post.return_value = Mock(status_code=200, json=Mock(return_value=result or dict(status=True, msg='fixture')))
        with patch.object(SessionManager, 'get_session', return_value=session), patch('api.base.decode_questions_info', return_value=dict(questions=qs)), patch.object(client, '_check_work_result', return_value=None):
            outcome = client.study_work(self.course, dict(jobid='w', enc='fixture'), dict(knowledgeid='p', ktoken='fixture', cpi='fixture'))
        return session.post.call_args.kwargs['data'], outcome

    def test_named_layout_order_existing_and_actual_payload(self):
        q = question('<textarea id="e2" name="answer9_2">old</textarea><input name="answer9_1" value="previous">')
        self.assertTrue(q['completion_layout']['supported']); self.assertEqual(q['blank_count'], 2)
        self.assertEqual(q['completion_layout']['blanks'][0]['existing'], 'old')
        form, _ = self.save([q], ['["second","first"]'])
        self.assertEqual((form['answer9_2'], form['answer9_1']), ('second', 'first'))
        self.assertNotIn('answer9', form); self.assertEqual(form['pyFlag'], '1')

    def test_unsupported_variants_cannot_be_adopted_or_invent_fields(self):
        for fields in ('<textarea id="answer9"></textarea>', '<input type="hidden" name="answer9"><div contenteditable="true"></div>',
                       '<script type="text/plain" id="editor9"></script>', '<textarea name="answer9"></textarea>' * 2,
                       '<textarea name="answer9"></textarea><textarea id="unmapped"></textarea>'):
            q = question(fields)
            self.assertFalse(q['completion_layout']['supported']); self.assertTrue(q['completion_layout']['reason'])
            self.assertIsNone(self.router().normalize('value', q))
            form, _ = self.save([q], ['value'], submit=True)
            self.assertNotIn('answer9', form); self.assertEqual(form['pyFlag'], '1')

    def test_single_text_formulas_and_json_array_compatibility(self):
        for text in ('[0,1]', '[0,1)', '[x,y]', 'a;b', 'a,b', 'line1\nline2', 'a|b'):
            self.assertEqual(completion_parts(text, 1), [text])
        self.assertEqual(completion_parts('["x"]', 1), ['x'])
        self.assertEqual(completion_parts('["x","y"]', 2), ['x', 'y'])
        for value in ('x#y', 'x|y', 'x\ny', '[0,1]'):
            self.assertIsNone(completion_parts(value, 2))

    def test_source_separator_explicit_only_and_validated(self):
        for separator in ('#', '|', '\n'):
            definition = dict(copy.deepcopy(TEMPLATE), completion_separator=separator, results_path='', title_path='', options_path='')
            bank = DeclarativeBank(dict(declarative_definition=json.dumps(definition)))
            with patch('api.answer.Tiku.request', return_value=Mock(status_code=200, json=lambda: [dict(answer='first'+separator+'second')])):
                answer = bank._query(dict(type='completion', blank_count=2))
            self.assertEqual(completion_parts(answer, 2), ['first', 'second'])
            definition['completion_separator'] = ' ' * 2
            with self.assertRaises(ValueError): validate_definition(json.dumps(definition))
        for value in (None, [], 3, '#' * 17):
            with self.assertRaises(ValueError): validate_definition(json.dumps(dict(TEMPLATE, completion_separator=value)))

    def test_ai_contract_rejects_wrong_counts_empty_and_objects(self):
        ai = AIClient(dict(defaults()['ai']))
        q = question('<textarea name="answer9_1"></textarea><textarea name="answer9_2"></textarea>')
        self.assertIn('blank_count=2', json.dumps(ai.messages(q), ensure_ascii=False))
        for answer, reason in [(['x'], '返回 1 段'), (['x','y','z'], '返回 3 段'), (['x',''], '空项'), ({'a':'x'}, '数组'), ('x', '数组')]:
            with patch.object(ai, 'complete', return_value=json.dumps(dict(Answer=answer))), self.assertRaises(AIError) as raised:
                ai.query(q)
            self.assertIn(reason, str(raised.exception))
        with patch.object(ai, 'complete', return_value='{"Answer":["x","y"]}'):
            self.assertEqual(completion_parts(ai.query(q), 2), ['x', 'y'])

    def test_unknown_layout_skips_ai_and_manual_without_spending_requests(self):
        cfg = to_payload(defaults()); cfg['desktop']['manual_fallback'] = 'true'; cfg['ai']['check_connection'] = 'false'
        ch = channel(); ch.ask = Mock(side_effect=AssertionError('no writable layout'))
        ai = Mock(); router = AnswerRouter(cfg, ch, ai=ai)
        self.assertEqual(router.query_all([question('<textarea id="x"></textarea>')]), [None])
        ai.query.assert_not_called(); ch.ask.assert_not_called()
        self.assertIn('提交', events(ch, 'question_result')[-1]['record']['reason'])

    def test_ai_rejection_reason_survives_router(self):
        cfg = to_payload(defaults()); cfg['ai']['check_connection'] = 'false'; cfg['desktop']['manual_fallback'] = 'false'
        ai = AIClient(dict(defaults()['ai'])); ch = channel()
        with patch.object(ai, 'complete', return_value='{"Answer":["x"]}'):
            self.assertEqual(AnswerRouter(cfg, ch, ai=ai).query_all([dict(type='completion', blank_count=2, title='test')]), [None])
        self.assertIn('预期 2 空／返回 1 段', events(ch, 'question_result')[-1]['record']['reason'])

    def test_multiple_questions_stale_values_and_incomplete_submit(self):
        a = question('<textarea name="answer9_1"></textarea><textarea name="answer9_2"></textarea>')
        b = question('<textarea name="answer10"></textarea>', '10')
        a['answerField'].update(answer9_1='old1', answer9_2='old2')
        form, _ = self.save([a, b], ['["one"]', '[0,1]'], submit=True)
        self.assertEqual((form['answer9_1'], form['answer9_2'], form['answer10']), ('', '', '[0,1]'))
        self.assertEqual(form['pyFlag'], '1')
        form, _ = self.save([a, b], ['["new1","new2"]', 'new3'], submit=True)
        self.assertEqual(form['pyFlag'], ''); self.assertEqual(form['answer9_2'], 'new2')

    def test_save_failure_and_unreadable_response_are_not_success(self):
        q = question('<textarea name="answer9"></textarea>')
        for result in (dict(status=False, msg='rejected'), dict(status='true'), dict(other=True)):
            _, outcome = self.save([copy.deepcopy(q)], ['x'], result=result)
            self.assertEqual(outcome, StudyResult.ERROR)

    def test_statistics_replace_evict_clear_and_no_hot_summary_scans(self):
        b = Backend()
        try:
            model = b._activity_model; model.MAX_ROWS = 2
            a = activity_record(); model.upsert(a)
            model.upsert(dict(a, stage='submitted', task_status='confirmed'))
            self.assertEqual(model.stats.stages['draft'], 0); self.assertEqual(model.stats.confirmed, 1)
            for i in range(2): model.upsert(dict(a, id=str(i)))
            self.assertEqual(model.stats.confirmed, 0); self.assertEqual(model.stats.stages['draft'], 2)
            self.assertEqual(sum(model.stats.sources.values()), sum(len(r['answers']) for r in model.rows))
            d = b._discussion_model; d.MAX_ROWS = 1
            d.upsert(discussion_record()); d.upsert(discussion_record(id='next', stage='existing', task_status='confirmed'))
            self.assertEqual(d.stats.stages['draft'], 0); self.assertEqual(d.stats.confirmed, 1)
            class NoIter(list):
                def __iter__(self): raise AssertionError('summary scanned records')
            model.rows = NoIter(model.rows); d.rows = NoIter(d.rows)
            with patch.object(Path, 'exists', side_effect=AssertionError('summary disk access')):
                for _ in range(10): self.assertEqual(b.summary['activityStats']['draft'], 2)
            model.clear(); d.clear(); self.assertFalse(sum(model.stats.sources.values())); self.assertEqual(d.stats.confirmed, 0)
        finally: b.close()

    def test_notifications_coalesce_final_event_stale_run_and_account(self):
        b = Backend()
        try:
            b.operation = 'verify'; b.operation_account = 'a'; b.account_store = SimpleNamespace(active='a', rows=[])
            b._task_model.reset([dict(id=str(i), title='test', course='test', status='pending') for i in range(1000)])
            changed=[]; b.changed.connect(lambda: changed.append(1))
            for i in range(1000): b.on_event(dict(type='verification', id=str(i), confirmed=True, checked_at='fixture', reason='fixture'))
            self.assertFalse(changed); self.assertTrue(b._progress_timer.isActive()); self.assertEqual(b.summary['success'], 1000)
            b.on_event(dict(type='verification_done', message='finished')); self.assertEqual(len(changed), 1)
            b.on_event(dict(type='verification', run_id='old-run', id='0', confirmed=False, checked_at='', reason=''))
            b.account_store.active='other'; b.on_event(dict(type='verification', id='0', confirmed=False, checked_at='', reason=''))
            self.assertEqual(b.summary['success'], 1000)
        finally: b.close()

    def test_thousand_targets_dedup_and_one_read_per_course(self):
        ch = channel(); client = Mock(spec_set=['get_course_point'])
        client.get_course_point.return_value = dict(points=[dict(id=str(i), has_finished=True) for i in range(1000)])
        targets=[dict(self.target, id=str(i), pointId=str(i)) for i in range(1000)]
        verify_chapters(client, ch, [self.course], targets + targets)
        self.assertEqual(client.get_course_point.call_count, 1); self.assertEqual(len(events(ch, 'verification')), 1000)
        self.assertTrue(all(Controller._valid_event(e) for e in events(ch)))
        self.assertEqual(events(ch, 'verification_progress')[-1]['completed'], 1000)

    def test_record_button_scope_hints_and_explicit_full_discovery(self):
        b=Backend()
        try:
            cookie=Path(self.tmp.name)/'fixture-cookie'; cookie.write_bytes(b'fixture')
            b.account_store=SimpleNamespace(active='a',rows=[],cookie_path=lambda _:cookie,get=lambda _:dict(uid='u'))
            b.course_identity=('fixture',); b._record_cards={'0':[2]}
            b._task_model.reset([dict(id=str(i),title='test',course='test',status='pending' if i==0 else 'success',
                                     courseId='c',clazzId='l',pointId=str(i)) for i in range(3)])
            b._discussion_model.upsert(discussion_record(task_id='1'))
            with patch.object(b,'identity',return_value=('fixture',)),patch('chaoxing_desktop.qml_backend.validate'),patch.object(b.controller,'start') as start:
                b.verifyRecords(); args=start.call_args.args[0]
                self.assertEqual([t['id'] for t in args['targets']],['0','1']); self.assertEqual(args['targets'][0]['record_cards'],[2])
                b.verifyAllRecords(); args=start.call_args.args[0]
                self.assertEqual(len(args['targets']),3); self.assertTrue(all('record_cards' not in t for t in args['targets']))
                b.verifyPending(); self.assertEqual([t['id'] for t in start.call_args.args[0]['targets']],['0'])
        finally: b.close()

    def test_runtime_hints_use_observed_card_positions(self):
        from chaoxing_desktop.runtime import _process_chapter, ChapterResult
        client=SimpleNamespace(get_job_list=Mock(return_value=([dict(type='discussion',mid='m',_job_info=dict(card_index='2'))],{})),
                               desktop_media_context=SimpleNamespace(task_id='t'),desktop_record_cards=Mock())
        with patch('chaoxing_desktop.runtime.process_job',return_value=StudyResult.SUCCESS):
            self.assertEqual(_process_chapter(client,self.course,dict(id='p'),1),ChapterResult.SUCCESS)
        client.desktop_record_cards.assert_called_once_with(id='t',indices=[2])

    def test_course_network_failure_local_auth_identity_and_cancel_global(self):
        other=dict(self.course, courseId='other'); targets=[self.target, dict(self.target, id='u', courseId='other')]
        client=Mock(spec_set=['get_course_point']); ch=channel()
        client.get_course_point.side_effect=[requests.Timeout('fixture'), dict(points=[dict(id='p',has_finished=True)])]
        verify_chapters(client,ch,[self.course,other],targets)
        self.assertEqual(len(events(ch,'verification_failed')),1); self.assertEqual(events(ch,'verification')[0]['id'],'u')
        for kind in ('auth_error','verification_required','identity_error'):
            client.get_course_point.reset_mock(); client.get_course_point.side_effect=PlatformResponseError('fixture',kind)
            with self.assertRaises(PlatformResponseError): verify_chapters(client,channel(),[self.course,other],targets)
            self.assertEqual(client.get_course_point.call_count,1)
        ch=channel(); ch.control=RunControl(ch.send)
        def cancel(*args): ch.control.cancelled.set(); return dict(points=[])
        client.get_course_point.side_effect=cancel; client.get_course_point.reset_mock()
        with self.assertRaises(Cancelled): verify_chapters(client,ch,[self.course,other],targets)
        self.assertEqual(client.get_course_point.call_count,1); self.assertFalse(events(ch,'verification'))

    def test_card_plan_dedup_cap_fallback_empty_first_and_native_dedup(self):
        ch=channel(); session=Mock(spec_set=['get'])
        session.get.return_value=response('<script>mArg={"attachments":[],"defaults":{"knowledgeid":"p"}};</script>')
        with patch.object(SessionManager,'get_session',return_value=session):
            read_cards(Mock(spec_set=[]),ch,self.course,dict(id='p'),indices=[3,3])
            self.assertEqual(session.get.call_count,1)
            for invalid in ([],[64],[-1],[True],list(range(65))):
                with self.assertRaises(ValueError): read_cards(Mock(spec_set=[]),ch,self.course,dict(id='p'),indices=invalid)
            session.get.reset_mock()
            rows=[([],dict(knowledgeid='p')),([dict(type='discussion',mid='m')],dict(knowledgeid='p',cardid='card'))]
            with patch('api.decode.decode_course_card',side_effect=rows+[rows[1]]*5):
                jobs=read_cards(Mock(spec_set=[]),ch,self.course,dict(id='p'))
            self.assertEqual(session.get.call_count,7); self.assertEqual(len(jobs),1)

    def test_card_transport_failure_continues_without_claiming_absent(self):
        ch=channel(); progress=Progress(ch,1); session=Mock(spec_set=['get'])
        session.get.side_effect=[requests.Timeout('fixture'),response('<script>mArg={"attachments":[],"defaults":{"knowledgeid":"p"}};</script>')]
        with patch.object(SessionManager,'get_session',return_value=session):
            self.assertEqual(read_cards(Mock(spec_set=[]),ch,self.course,dict(id='p'),indices=[0,1],progress=progress),[])
        self.assertEqual(progress.failures,1); self.assertEqual(session.get.call_count,2)
        self.assertFalse(events(ch,'record_verification'))

    def test_personal_failure_never_retains_partial_success_and_intents_unchanged(self):
        ch=channel(); adapter=Mock(spec_set=['resolve','own_reply','task_status'])
        adapter.resolve.return_value=SimpleNamespace(); adapter.own_reply.return_value=SimpleNamespace(reply_id='mine',known=True)
        adapter.task_status.side_effect=requests.Timeout('fixture')
        paths=[]
        for folder in ('activities','discussions'):
            path=Path(self.tmp.name)/folder/'intent.json'; path.parent.mkdir(); path.write_bytes(b'{"state":"intent"}'); paths.append(path)
        with patch('chaoxing_desktop.verification.read_cards',return_value=[(dict(type='discussion',mid='m'),dict(cardid=str(i))) for i in range(2)]),patch('api.discussion.DiscussionAdapter',return_value=adapter):
            verify_records(Mock(spec_set=[]),ch,self.course,self.target,dict(id='p'))
        self.assertEqual(adapter.resolve.call_count,1)
        self.assertEqual(events(ch,'record_verification')[0]['participation'],'unknown')
        self.assertTrue(all(p.read_bytes()==b'{"state":"intent"}' for p in paths))

    def test_real_worker_personal_branch_allowlists_gets_and_preserves_intent_bytes(self):
        from chaoxing_desktop.worker import real
        cookie=Path(self.tmp.name)/'cookie'; cookie.write_bytes(b'fixture-session')
        store=SimpleNamespace(get=lambda _:dict(username='fixture',uid='u'),cookie_path=lambda _:cookie)
        client=Mock(spec_set=['login','get_course_list','get_course_point'])
        client.login.return_value=dict(status=True); client.get_course_list.return_value=[self.course]
        client.get_course_point.return_value=dict(points=[dict(id='p',has_finished=False)])
        core=SimpleNamespace(create_client=Mock(return_value=client))
        cfg=to_payload(defaults()); cfg['common'].update(username='fixture',password='',use_cookies=True)
        command=dict(action='verify',account_id='a'*32,account_uid='u',data_dir=self.tmp.name,
                     cookie_mtime_ns=cookie.stat().st_mtime_ns,config=cfg,verify_records=True,
                     targets=[dict(self.target,record_cards=[2,2])])
        attachments=[dict(job=True,jobid='job-'+str(i),property=dict(module=module,mid='mid-'+str(i)))
                     for i,module in enumerate(('insertbbs','insertvote'))]
        html='<script>mArg='+json.dumps(dict(attachments=attachments,defaults=dict(knowledgeid='p',cardid='card')))+';</script>'
        session=Mock(spec_set=['get','cookies']); session.cookies=SimpleNamespace(get_dict=lambda:dict(_uid='u'))
        session.get.return_value=response(html)
        discussion=Mock(spec_set=['resolve','own_reply','task_status']); discussion.resolve.return_value=SimpleNamespace()
        discussion.own_reply.return_value=SimpleNamespace(reply_id='mine',known=True); discussion.task_status.return_value='pending'
        activity=Mock(spec_set=['resolve','task_status']); activity.resolve.return_value=SimpleNamespace(participation='existing'); activity.task_status.return_value='pending'
        paths=[]
        for folder in ('discussions','activities'):
            path=Path(self.tmp.name)/folder/'fixture.json'; path.parent.mkdir(); path.write_bytes(b'{"state":"intent"}'); paths.append(path)
        ch=channel()
        with patch('chaoxing_desktop.worker.load_core',return_value=core),patch('chaoxing_desktop.accounts.AccountStore',return_value=store), \
             patch('api.cookies.configure_account'),patch('api.cookies.save_cookies',side_effect=AssertionError('no session writes')), \
             patch.object(SessionManager,'get_session',return_value=session),patch('api.discussion.DiscussionAdapter',return_value=discussion), \
             patch('api.activity.ActivityAdapter',return_value=activity):
            real(ch,command)
        self.assertTrue(core.create_client.call_args.kwargs['courses_only']); self.assertEqual(session.get.call_count,1)
        self.assertEqual(len(events(ch,'record_verification')),2)
        self.assertTrue(all(e['participation']=='existing' for e in events(ch,'record_verification')))
        self.assertTrue(all(p.read_bytes()==b'{"state":"intent"}' for p in paths)); self.assertEqual(cookie.read_bytes(),b'fixture-session')

    def test_controller_time_budget_preserves_utf8_final_and_rejects_bad_progress(self):
        controller=Controller(); controller.EVENT_BUDGET_SECONDS=.001; controller.active=True
        frame=(json.dumps(dict(type='log',message='中文'),ensure_ascii=False)+'\n').encode()
        controller.process=OutputProcess(frame*200+b'{"type":"verification_done","message":"last"}\n')
        received=[]
        def slow(e): received.append(e); time.sleep(.001)
        controller.event.connect(slow); controller.on_finished(0,None)
        self.assertTrue(controller.active); self.assertLess(len(received),10)
        for _ in range(220):
            if not controller.active: break
            controller._drain_timer.stop(); controller.read_output()
        self.assertFalse(controller.active); self.assertEqual(len(received),201); self.assertEqual(received[-1]['message'],'last')
        self.assertFalse(Controller._valid_event(dict(type='verification_progress',phase='cards',message='x',completed=2,total=1,reads=0,failures=0,elapsed_ms=0)))


if __name__=='__main__': unittest.main()
