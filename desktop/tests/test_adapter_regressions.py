"""Regressions at the real page parser and answer submission boundary."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor/chaoxing"))

from bs4 import BeautifulSoup
from api.base import Chaoxing, SessionManager
from api.decode import _process_question
from chaoxing_desktop.answers import AnswerRouter, question_images
from chaoxing_desktop.config import defaults, to_payload


class AdapterRegressions(unittest.TestCase):
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
                client = Chaoxing(tiku=router, desktop_mode=True)
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
