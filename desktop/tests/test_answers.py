import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from chaoxing_desktop.answers import AIClient, AnswerRouter, build_answers, question_images
from chaoxing_desktop.config import Redactor, defaults, parse_text, serialize, to_payload, validate
from chaoxing_desktop.worker import Channel


def question(title, kind="single"):
    return dict(title=title, type=kind, options="A 第一项\nB 第二项")


class AnswerTests(unittest.TestCase):
    def router(self, banks=(), ai=None, config=None):
        config = config or to_payload(defaults())
        channel = Channel(io.StringIO(), io.StringIO(), Redactor({}))
        return AnswerRouter(config, channel, banks, ai)

    def test_all_banks_finish_before_ai_and_only_unresolved_questions_reach_ai(self):
        calls = []
        first = SimpleNamespace(_query=lambda q: calls.append(("bank1", q["title"])) or ("A" if q["title"] == "hit" else None))
        second = SimpleNamespace(_query=lambda q: calls.append(("bank2", q["title"])) or ("B" if q["title"] == "second" else None))
        ai = SimpleNamespace(check_connection=lambda: calls.append(("check", "")),
                             query=lambda q: calls.append(("ai", q["title"])) or "B")
        router = self.router([("first", first), ("second", second)], ai)
        self.assertEqual(router.query_all([question("hit"), question("second"), question("missing")]),
                         ["第一项", "第二项", "第二项"])
        self.assertEqual(calls, [("bank1", "hit"), ("bank1", "second"), ("bank1", "missing"),
                                 ("bank2", "second"), ("bank2", "missing"), ("check", ""), ("ai", "missing")])

    def test_full_bank_coverage_does_not_check_or_call_ai(self):
        ai = Mock()
        router = self.router([("bank", SimpleNamespace(_query=lambda q: "A"))], ai)
        self.assertEqual(router.query_all([question("all")]), ["第一项"])
        ai.check_connection.assert_not_called()
        ai.query.assert_not_called()

    def test_invalid_answers_and_service_failure_continue_to_next_provider(self):
        failed = Mock(_query=Mock(side_effect=RuntimeError("offline")))
        bad = SimpleNamespace(_query=lambda q: "不属于任何选项")
        ai = SimpleNamespace(check_connection=lambda: None, query=lambda q: "A")
        self.assertEqual(self.router([("offline", failed), ("invalid", bad)], ai).query(question("q")), "第一项")

    def test_ai_failure_preserves_bank_answers_and_unresolved_stay_empty(self):
        bank = SimpleNamespace(_query=lambda q: "A" if q["title"] == "hit" else None)
        ai = Mock(check_connection=Mock(side_effect=RuntimeError("offline")))
        self.assertEqual(self.router([("bank", bank)], ai).query_all([question("hit"), question("miss")]), ["第一项", None])
        ai.query.assert_not_called()
        self.assertEqual(self.router().query(question("miss")), None)

    def test_disabled_vision_never_calls_ai_for_image_question(self):
        ai = Mock()
        q = question('<img src="https://example.test/q.png">')
        self.assertEqual(self.router(ai=ai).query(q), None)
        ai.query.assert_not_called()
        ai.check_connection.assert_not_called()

    def test_multimodal_messages_include_title_and_option_images(self):
        config = dict(defaults()["ai"], vision="true")
        q = question('图片题<img src="//example.test/q.png?a=1&amp;b=2">')
        q["options"] += '\nC <img src="https://example.test/option.png">'
        images = question_images(q)
        self.assertEqual(images, ["https://example.test/q.png?a=1&b=2", "https://example.test/option.png"])
        messages = AIClient(config).messages(q)
        self.assertEqual([x["image_url"]["url"] for x in messages[-1]["content"] if x["type"] == "image_url"], images)

    def test_ai_http_payload_and_response_parsing(self):
        config = dict(defaults()["ai"], endpoint="https://example.test/v1", key="sk-test", model="model-test", vision="true")
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": '```json\n{"Answer":["第一项"]}\n```'}}]}
        with patch("requests.Session.post", return_value=response) as post:
            answer = AIClient(config).query(question('<img src="https://example.test/q.png">'))
        self.assertEqual(answer, "第一项")
        self.assertEqual(post.call_args.args[0], "https://example.test/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "model-test")
        self.assertEqual(post.call_args.kwargs["timeout"], (10, 60))
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer sk-test")

    def test_ai_auth_failure_is_not_retried_and_error_omits_secret(self):
        import requests
        config = dict(defaults()["ai"], endpoint="https://example.test/v1/chat/completions", key="sk-secret", model="test")
        response = Mock(status_code=401)
        response.raise_for_status.side_effect = requests.HTTPError("sk-secret", response=response)
        with patch("requests.Session.post", return_value=response) as post:
            with self.assertRaisesRegex(RuntimeError, "HTTP 401") as error:
                AIClient(config).check_connection()
        self.assertEqual(post.call_count, 1)
        self.assertNotIn("sk-secret", str(error.exception))

    def test_manual_question_is_structured_and_normalized(self):
        config = to_payload(defaults())
        config["desktop"]["manual_fallback"] = "true"
        channel = Mock(ask=Mock(return_value="B"))
        router = AnswerRouter(config, channel)
        q = question("人工题")
        self.assertEqual(router.query(q), "第二项")
        self.assertEqual(channel.ask.call_args.kwargs, {"kind": "question", "question": q})

    def test_migration_splits_services_reorders_ai_after_banks_and_round_trips(self):
        c = parse_text('[tiku]\nprovider=AI,TikuYanxi,TikuGo,TikuManual\ntokens=OLD_SECRET\nkey=AI_SECRET\nendpoint=https://example.test/v1\nmodel=test\nmin_interval_seconds=2.5\n')
        self.assertEqual(c["question_bank"]["providers"], "TikuYanxi,TikuGo")
        self.assertEqual(c["question_bank"]["yanxi_tokens"], "OLD_SECRET")
        self.assertEqual(c["ai"]["key"], "AI_SECRET")
        self.assertEqual(c["ai"]["enabled"], "true")
        self.assertEqual(c["desktop"]["manual_fallback"], "true")
        self.assertNotIn("key", c["tiku"])
        self.assertEqual(serialize(parse_text(serialize(c))), serialize(c))
        self.assertNotIn("OLD_SECRET", serialize(c, include_secrets=False))
        self.assertNotIn("AI_SECRET", serialize(c, include_secrets=False))
        validate(c)

    def test_new_sections_override_legacy_ai(self):
        c = parse_text('[tiku]\nprovider=AI\nkey=old\n[ai]\nenabled=false\nkey=new\n')
        self.assertEqual(c["ai"]["key"], "new")
        self.assertEqual(c["ai"]["enabled"], "false")

    def test_siliconflow_migration(self):
        c = parse_text('[tiku]\nprovider=SiliconFlow\nsiliconflow_key=sk-test\nsiliconflow_model=test-model\n')
        self.assertEqual(c["ai"]["provider"], "SiliconFlow")
        self.assertEqual(c["ai"]["key"], "sk-test")
        self.assertEqual(c["ai"]["model"], "test-model")
        self.assertEqual(c["ai"]["endpoint"], "https://api.siliconflow.cn/v1")

    def test_imported_provider_whitespace_is_normalized(self):
        c = parse_text('[question_bank]\nproviders= TikuGo, TikuYanxi \nyanxi_tokens= first , second \n[tiku]\nfuture_option=preserved\n')
        validate(c)
        p = to_payload(c)
        self.assertEqual(p["question_bank"]["providers"], "TikuGo,TikuYanxi")
        self.assertEqual(p["question_bank"]["yanxi_tokens"], "first,second")
        self.assertEqual(c["tiku"]["future_option"], "preserved")

    def test_random_option_defaults_off_and_round_trips(self):
        c = parse_text('[desktop]\nmanual_fallback=false\n')
        self.assertEqual(c["desktop"]["random_fallback"], "false")
        c["desktop"]["random_fallback"] = "true"
        validate(c)
        self.assertEqual(parse_text(serialize(c))["desktop"]["random_fallback"], "true")
        c["desktop"]["random_fallback"] = "sometimes"
        with self.assertRaises(ValueError):
            validate(c)

    def test_random_only_runs_after_services_and_manual_skip(self):
        c = to_payload(defaults())
        c["desktop"].update(random_fallback="true", manual_fallback="true")
        calls = []
        bank = SimpleNamespace(_query=lambda q: calls.append(("bank", q["title"])) or ("A" if q["title"] == "hit" else None))
        ai = SimpleNamespace(check_connection=lambda: None, query=lambda q: calls.append(("ai", q["title"])) or None)
        channel = Mock(ask=Mock(side_effect=lambda *a, **kw: calls.append(("manual", kw["question"]["title"])) or ""))
        router = AnswerRouter(c, channel, [("bank", bank)], ai)
        questions = [question("hit"), question("miss")]
        with patch("chaoxing_desktop.answers.random.choice", side_effect=lambda values: calls.append(("random", "miss")) or values[-1]):
            self.assertEqual(router.query_all(questions), ["第一项", "第二项"])
        self.assertEqual(calls, [("bank", "hit"), ("bank", "miss"), ("ai", "miss"), ("manual", "miss"), ("random", "miss")])
        self.assertNotIn("desktop_answer_source", questions[0])
        self.assertEqual(questions[1]["desktop_answer_source"], "random")
        self.assertTrue(channel.ask.call_args.kwargs["random_fallback"])

    def test_random_can_run_alone_and_only_supports_real_choices_and_judgement(self):
        c = to_payload(defaults())
        c["desktop"]["random_fallback"] = "true"
        router = self.router(config=c)
        self.assertFalse(router.DISABLE)
        questions = [question("single"), question("multiple", "multiple"), question("judge", "judgement"),
                     question("fill", "completion"), question("short", "shortanswer"),
                     dict(title="no options", type="single", options="")]
        answers = router.query_all(questions)
        self.assertIn(answers[0], ("第一项", "第二项"))
        self.assertEqual(set(answers[1].splitlines()), {"第一项", "第二项"})
        self.assertIn(answers[2], ("正确", "错误"))
        self.assertEqual(answers[3:], [None, None, None])
        for q in questions[:3]:
            self.assertEqual(q["desktop_answer_source"], "random")

    def test_old_random_provenance_does_not_affect_next_successful_query(self):
        q = dict(question("hit"), desktop_answer_source="random")
        router = self.router([("bank", SimpleNamespace(_query=lambda q: "A"))])
        self.assertEqual(router.query(q), "第一项")
        self.assertNotIn("desktop_answer_source", q)


class PlatformAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor/chaoxing"))

    def test_per_bank_tokens_are_isolated(self):
        c = to_payload(defaults())
        c["question_bank"].update(providers="TikuYanxi,TikuLike", yanxi_tokens="YANXI", like_tokens="LIKE")
        observed = []
        def factory(conf):
            observed.append(conf)
            return SimpleNamespace(init_tiku=lambda: None, DISABLE=False)
        with patch("api.answer.Tiku.get_tiku_from_config", side_effect=factory):
            build_answers(c, Mock())
        self.assertEqual([x["tokens"] for x in observed], ["YANXI", "LIKE"])

    def test_like_false_settings_are_real_booleans(self):
        from api.answer import TikuLike
        bank = TikuLike()
        bank.config_set(dict(defaults()["question_bank"], likeapi_search="false", likeapi_vision="false", likeapi_retry="false"))
        bank.load_config()
        self.assertFalse(bank._search)
        self.assertFalse(bank._vision)
        self.assertFalse(bank._retry)

    def test_unresolved_answers_never_randomize_or_force_submit_after_rollback(self):
        from api.base import Chaoxing, SessionManager, StudyResult
        c = to_payload(defaults())
        c["tiku"]["submit"] = "true"
        router = AnswerRouter(c, Mock(), [("bank", SimpleNamespace(_query=lambda q: "B" if q["title"] == "hit" else None))])
        client = Chaoxing(tiku=router)
        client.rollback_times = 10
        questions = [dict(question("hit"), id="1", answerField={"answertype1": "0"}),
                     dict(question("miss"), id="2", answerField={"answertype2": "0"})]
        session = Mock()
        session.get.return_value = SimpleNamespace(status_code=200, text="exercise")
        session.post.return_value = SimpleNamespace(status_code=200, json=lambda: {"status": True, "msg": "saved"})
        with patch.object(SessionManager, "get_session", return_value=session), patch("api.base.decode_questions_info", return_value={"questions": questions}):
            result = client.study_work({"courseId": "c", "clazzId": "class"}, {"jobid": "work-1", "enc": "enc"},
                                       {"knowledgeid": "k", "ktoken": "t", "cpi": "cpi"})
        self.assertEqual(result, StudyResult.SUCCESS)
        sent = session.post.call_args.kwargs["data"]
        self.assertEqual(sent["pyFlag"], "1")
        self.assertEqual(sent["answer1"], "B")
        self.assertEqual(sent["answer2"], "")

    def test_random_answers_are_saved_and_only_submitted_when_requested(self):
        from api.base import Chaoxing, SessionManager
        for submit in ("false", "true"):
            with self.subTest(submit=submit):
                c = to_payload(defaults())
                c["desktop"]["random_fallback"] = "true"
                c["tiku"]["submit"] = submit
                router = AnswerRouter(c, Mock())
                client = Chaoxing(tiku=router)
                client._check_work_result = Mock(return_value={"score": 100, "all_correct": True})
                questions = [dict(question("single"), id="1", answerField={"answertype1": "0"})]
                session = Mock()
                session.get.return_value = SimpleNamespace(status_code=200, text="exercise")
                session.post.return_value = SimpleNamespace(status_code=200, json=lambda: {"status": True, "msg": "ok"})
                with patch.object(SessionManager, "get_session", return_value=session), patch("api.base.decode_questions_info", return_value={"questions": questions}):
                    client.study_work({"courseId": "c", "clazzId": "class"}, {"jobid": "work-1", "enc": "enc"},
                                      {"knowledgeid": "k", "ktoken": "t", "cpi": "cpi"})
                sent = session.post.call_args.kwargs["data"]
                self.assertEqual(sent["pyFlag"], "1" if submit == "false" else "")
                self.assertIn(sent["answer1"], ("A", "B"))
                self.assertEqual(questions[0]["answerSource1"], "random")

    def test_random_setting_never_submits_if_text_question_is_still_unresolved(self):
        from api.base import Chaoxing, SessionManager
        c = to_payload(defaults())
        c["desktop"]["random_fallback"] = "true"
        c["tiku"]["submit"] = "true"
        client = Chaoxing(tiku=AnswerRouter(c, Mock()))
        questions = [dict(question("fill", "completion"), id="1", answerField={"answertype1": "2"})]
        session = Mock()
        session.get.return_value = SimpleNamespace(status_code=200, text="exercise")
        session.post.return_value = SimpleNamespace(status_code=200, json=lambda: {"status": True, "msg": "saved"})
        with patch.object(SessionManager, "get_session", return_value=session), patch("api.base.decode_questions_info", return_value={"questions": questions}):
            client.study_work({"courseId": "c", "clazzId": "class"}, {"jobid": "work-1", "enc": "enc"},
                              {"knowledgeid": "k", "ktoken": "t", "cpi": "cpi"})
        sent = session.post.call_args.kwargs["data"]
        self.assertEqual(sent["pyFlag"], "1")
        self.assertEqual(sent["answer1"], "")


if __name__ == "__main__":
    unittest.main()
