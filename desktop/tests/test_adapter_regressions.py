"""Regressions at the real page parser and answer submission boundary."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor/chaoxing"))

from bs4 import BeautifulSoup
from api.base import Chaoxing, SessionManager, StudyResult
from api.decode import _process_question
from chaoxing_desktop.answers import AnswerRouter, question_images
from chaoxing_desktop.config import defaults, to_payload


class AdapterRegressions(unittest.TestCase):
    def test_question_number_does_not_merge_with_body_year(self):
        from chaoxing_desktop.bank_question import ImageEncoder, yanxi_environment
        for number, body in ((2, '2026年是（）开局之年。'), (5, '2025年服务业占比（）'),
                             (11, '2026年《政府工作报告》明确（）'), (1, '1+1=？')):
            with self.subTest(number=number):
                html = f'''<div data="q"><div class="TiMu" data="0"></div>
                <div class="Zy_TItle"><div class="clearfix"><span>{number}</span><span>【单选题】</span>{body}</div></div></div>'''
                question = _process_question(BeautifulSoup(html, 'html.parser').div)
                self.assertEqual(question['title'], body)
                self.assertEqual(yanxi_environment(question, ImageEncoder())['title'], body)

    def test_parser_preserves_unlabelled_year_number_and_math(self):
        for body in ('2026年是（）开局之年。', '1+1=？', '1.5+2.5=( )'):
            with self.subTest(body=body):
                html = f'<div data="q"><div class="TiMu" data="0"></div><div class="Zy_TItle">{body}</div></div>'
                self.assertEqual(_process_question(BeautifulSoup(html, 'html.parser').div)['title'], body)

    def test_audio_card_is_parsed_and_dispatched_as_audio(self):
        from api.decode import _process_attachment_cards
        from chaoxing_desktop.runtime import process_job
        jobs = _process_attachment_cards([dict(type='audio', job=True, jobid='j', objectId='o', property={'name': 'sample audio'})])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['type'], 'audio')
        client = Mock()
        client.study_video.return_value = StudyResult.SUCCESS
        self.assertEqual(process_job(client, {}, jobs[0], {}, 1.5), StudyResult.SUCCESS)
        self.assertEqual(client.study_video.call_args.kwargs, dict(_speed=1.5, _type='Audio'))

    def test_actual_media_loop_reports_resume_and_verification(self):
        client = Chaoxing()
        client.desktop_media_progress = Mock()
        session = Mock()
        session.get.return_value.status_code = 200
        session.get.return_value.text = '{}'
        session.get.return_value.url = 'https://mooc1.chaoxing.com/ananas/status/o'
        session.get.return_value.json.return_value = dict(status='success', dtoken='t', crc='c', key='k', duration=60)
        with patch.object(SessionManager, 'get_session', return_value=session), \
                patch.object(client, 'get_fid', return_value='f'), \
                patch.object(client, 'video_progress_log', return_value=(True, 200)):
            self.assertEqual(client.study_video({}, dict(objectid='o', playTime=15000, name='audio'), {}, _type='Audio'), StudyResult.SUCCESS)
        values = [call.kwargs for call in client.desktop_media_progress.call_args_list]
        self.assertEqual(values[0], dict(name='audio', kind='Audio', duration=60, position=15, verified=False))
        self.assertEqual(values[-1]['position'], 60)
        self.assertTrue(values[-1]['verified'])

    def test_concurrent_chapters_keep_media_task_identity(self):
        import threading
        from chaoxing_desktop.runtime import process_chapter, ChapterResult
        context = threading.local()
        barrier = threading.Barrier(2)
        seen = []
        def jobs(course, point):
            barrier.wait(timeout=5)
            seen.append((point['id'], context.task_id))
            return [], {}
        client = SimpleNamespace(desktop_media_context=context, get_job_list=jobs)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(process_chapter, client, {}, {'id': key}, 1, key) for key in ('video', 'audio')]
            self.assertEqual([f.result() for f in futures], [ChapterResult.SUCCESS] * 2)
        self.assertEqual(set(seen), {('video', 'video'), ('audio', 'audio')})

    def test_video_unconfirmed_completion_is_bounded(self):
        from test_media_completion import MediaClock
        clock = MediaClock()
        client = Chaoxing()
        session = Mock()
        session.get.return_value.status_code = 200
        session.get.return_value.text = '{}'
        session.get.return_value.url = 'https://mooc1.chaoxing.com/ananas/status/o'
        session.get.return_value.json.return_value = dict(status="success", dtoken="t", crc="c", key="k", duration=1)
        with patch.object(SessionManager, "get_session", return_value=session), \
                patch.object(client, "get_fid", return_value="f"), \
                patch.object(client, "video_progress_log", return_value=(False, 200)) as progress, \
                patch("api.base.time.monotonic", side_effect=clock.monotonic), \
                patch("api.base.controlled_wait", side_effect=lambda owner, seconds, **kw: clock.sleep(seconds)):
            result = client.study_video({}, dict(objectid="o", playTime=1000, name="video"), {})
        self.assertEqual(result, StudyResult.TIMEOUT)
        self.assertEqual(progress.call_count, 6)  # initial check + five completion confirmations
        self.assertEqual(clock.now, 300)

    def test_video_completion_can_succeed_after_several_confirmations(self):
        from test_media_completion import MediaClock
        clock = MediaClock()
        client = Chaoxing()
        session = Mock()
        session.get.return_value.status_code = 200
        session.get.return_value.text = '{}'
        session.get.return_value.url = 'https://mooc1.chaoxing.com/ananas/status/o'
        session.get.return_value.json.return_value = dict(status="success", dtoken="t", crc="c", key="k", duration=1)
        with patch.object(SessionManager, "get_session", return_value=session), \
                patch.object(client, "get_fid", return_value="f"), \
                patch.object(client, "video_progress_log", side_effect=[(False, 200), (False, 200), (True, 200)]), \
                patch("api.base.time.monotonic", side_effect=clock.monotonic), \
                patch("api.base.controlled_wait", side_effect=lambda owner, seconds, **kw: clock.sleep(seconds)):
            result = client.study_video({}, dict(objectid="o", playTime=2000, name="video"), {})
        self.assertEqual(result, StudyResult.SUCCESS)

    def test_live_submission_failure_does_not_report_success(self):
        from api.live_process import LiveProcessor
        live = Mock()
        live.get_status.return_value = {"temp": {"data": {"duration": 60}}}
        live.do_finish.return_value = False
        with patch("api.live_process.wait"):
            self.assertFalse(LiveProcessor.run_live(live))
        self.assertEqual(live.do_finish.call_count, 2)

    def test_session_is_initialized_once_and_shared_across_threads(self):
        original = SessionManager._instance
        SessionManager._instance = None
        session = Mock()
        try:
            with patch("api.base.requests.Session", return_value=session) as factory, \
                    patch("api.base.use_cookies", return_value={}):
                with ThreadPoolExecutor(max_workers=8) as executor:
                    sessions = list(executor.map(lambda _: SessionManager.get_session(), range(32)))
                self.assertTrue(all(s is session for s in sessions))
                self.assertEqual(factory.call_count, 1)
        finally:
            SessionManager._instance = original

    def test_parser_preserves_images_in_choices_with_and_without_aria_labels(self):
        html = '''<div data="1"><div class="TiMu" data="0"></div>
        <div class="Zy_TItle">题目</div><ul>
        <li aria-label="A 选择"><img src="https://example.test/a.png"></li>
        <li>B <img src="https://example.test/b.png"></li></ul></div>'''
        question = _process_question(BeautifulSoup(html, "html.parser").div)
        self.assertEqual(question_images(question), ["https://example.test/a.png", "https://example.test/b.png"])

    def test_selected_choices_survive_submission_without_fuzzy_rematching(self):
        cases = [("single", "A 上海市\nB 上海", "B", "B"),
                 ("multiple", "A 上海市\nB 上海\nC 北京", "BC", "BC"),
                 ("single", "A Alpha\nB Beta", "B", "B"),
                 ("single", 'A <img src="https://example.test/a.png">\nB <img src="https://example.test/b.png">', "B", "B"),
                 ("single", "A 相同文本\nB 相同文本", "B", "B")]
        for kind, options, supplied, expected in cases:
            with self.subTest(kind=kind, options=options):
                config = to_payload(defaults())
                router = AnswerRouter(config, Mock(), [("bank", SimpleNamespace(_query=lambda q: supplied))])
                client = Chaoxing(tiku=router)
                q = dict(id="1", title="题目", type=kind, options=options, answerField={"answertype1": "0"})
                session = Mock()
                session.get.return_value = SimpleNamespace(status_code=200, text="exercise")
                session.post.return_value = SimpleNamespace(status_code=200, json=lambda: {"status": True, "msg": "saved"})
                with patch.object(SessionManager, "get_session", return_value=session), \
                        patch("api.base.decode_questions_info", return_value={"questions": [q]}):
                    client.study_work({"courseId": "c", "clazzId": "class"}, {"jobid": "w", "enc": "e"},
                                      {"knowledgeid": "k", "ktoken": "t", "cpi": "cpi"})
                self.assertEqual(session.post.call_args.kwargs["data"]["answer1"], expected)

    def test_image_and_uppercase_option_contents_normalize_correctly(self):
        router = AnswerRouter(to_payload(defaults()), Mock())
        question = dict(type="single", options='A <img src="https://example.test/a.png">\nB <img src="https://example.test/b.png">')
        self.assertEqual(router.normalize('<img src="https://example.test/b.png">', question), '<img src="https://example.test/b.png">')
        self.assertEqual(router.normalize("DNA", dict(type="single", options="A RNA\nB DNA")), "DNA")

    def test_choice_provenance_is_cleared_between_queries(self):
        router = AnswerRouter(to_payload(defaults()), Mock(), [("bank", SimpleNamespace(_query=lambda q: "B"))])
        question = dict(type="single", options="A 第一项\nB 第二项")
        self.assertEqual(router.query(question), "第二项")
        self.assertEqual(router.choice_letters("第二项", question), "B")
        router.banks = []
        self.assertIsNone(router.query(question))
        self.assertNotIn("desktop_answer_letters", question)

    def test_choice_order_and_ambiguous_text(self):
        router = AnswerRouter(to_payload(defaults()), Mock())
        question = dict(type="multiple", options="B 第二项\nA 第一项")
        answer = router.normalize("B\nA", question)
        self.assertEqual(router.choice_letters(answer, question), "AB")
        self.assertIsNone(router.normalize("相同文本", dict(type="single", options="A 相同文本\nB 相同文本")))

    def test_random_selection_preserves_letter_for_duplicate_contents(self):
        config = to_payload(defaults())
        config["desktop"]["random_fallback"] = "true"
        router = AnswerRouter(config, Mock())
        question = dict(type="single", options="A 相同文本\nB 相同文本")
        with patch("chaoxing_desktop.answers.random.choice", side_effect=lambda choices: choices[-1]):
            answer = router.query(question)
        self.assertEqual(router.choice_letters(answer, question), "B")

    def test_real_option_images_are_not_sent_to_text_only_ai(self):
        html = '''<div data="1"><div class="TiMu" data="0"></div>
        <div class="Zy_TItle">题目</div><ul>
        <li aria-label="A 选择"><img src="https://example.test/a.png"></li></ul></div>'''
        question = _process_question(BeautifulSoup(html, "html.parser").div)
        ai = Mock()
        router = AnswerRouter(to_payload(defaults()), Mock(), ai=ai)
        self.assertIsNone(router.query(question))
        ai.check_connection.assert_not_called()
        ai.query.assert_not_called()

    def test_custom_judgement_rules_ignore_surrounding_spaces(self):
        config = to_payload(defaults())
        config["tiku"].update(true_list=" 正确 , yes ", false_list=" 错误 , no ")
        router = AnswerRouter(config, Mock())
        self.assertEqual(router.normalize("错误", {"type": "judgement"}), "错误")


if __name__ == "__main__":
    unittest.main()
