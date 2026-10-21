"""Offline protocol regressions based on the supplied Yanxi v2 wrapper."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing'))
from api.answer import TikuYanxi, TikuLike, TikuAdapter
from chaoxing_desktop.answers import build_answers
from chaoxing_desktop.config import defaults, parse_text, serialize, to_payload, validate


def response(body=None, status=200):
    return Mock(status_code=status, json=Mock(return_value=body))


class BankProtocolTests(unittest.TestCase):
    def yanxi(self, tokens='first, second', **extra):
        bank = TikuYanxi()
        bank.config_set(dict(tokens=tokens, request_retries='0', **extra))
        bank.init_tiku()
        return bank

    def test_yanxi_v2_post_json_and_option_images(self):
        bank = self.yanxi(request_timeout='45', request_endpoint='https://example.test/query')
        question = dict(title='题干', type='single', options='A <img src="https://example.test/a.png">\nB 文本')
        with patch('chaoxing_desktop.bank_question.ImageEncoder.encode', return_value='data:image/png;base64,ZmFrZQ=='), patch('api.answer.requests.Session.get') as get, patch('api.answer.requests.Session.post', return_value=response(dict(code=1, data=dict(question='题干', answer='B', ai=False, tags=[])))) as post:
            self.assertEqual(bank._query(question), 'B')
        get.assert_not_called()
        self.assertEqual(post.call_args.args, ('https://example.test/query',))
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs['headers'], {'Content-Type': 'application/json'})
        self.assertEqual(kwargs['timeout'], (10, 45))
        self.assertEqual(kwargs['json'], dict(token='first', title='题干', options='https://example.test/a.png\n文本', type='single', images=['data:image/png;base64,ZmFrZQ=='], v='2', suggestion_title='题干', suggestion_options=' [图片1] \n文本'))

    def test_live_v2_miss_shows_detail_instead_of_generic_request_failure(self):
        bank = self.yanxi()
        body = dict(code=0, message='请求失败', data=dict(question='Q', answer='非常抱歉，题库没有该题的答案（<a href="https://example.test">AI人工智能自动搜题</a>）', tags=[dict(text='搜不到答案', color='gray')]))
        with patch('api.answer.requests.Session.post', return_value=response(body)) as post, patch('api.answer.logger') as log:
            self.assertIsNone(bank._query(dict(title='Q')))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(bank.last_query_status, 'miss')
        self.assertIn('题库没有该题的答案', bank.last_query_reason)
        log.warning.assert_not_called()
        self.assertIn('未命中', log.info.call_args.args[0])
        self.assertNotIn('请求失败', log.info.call_args.args[0])
        self.assertNotIn('<a', log.info.call_args.args[0])

    def test_equivalent_query_fallback_only_after_a_miss(self):
        bank = self.yanxi(yanxi_query_variants='true', yanxi_variant_limit='2')
        with patch('api.answer.requests.Session.post', side_effect=[response(dict(code=0, data=dict(answer='题库没有该题的答案'))), response(dict(code=1, data=dict(answer='B'))) ]) as post:
            self.assertEqual(bank._query(dict(title='2026年是（ ）开局之年。', type='single')), 'B')
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs['json']['title'], '2026年是()开局之年')

    def test_equivalent_query_fallback_stops_on_credentials_or_disabled(self):
        for setting, body in [('true', dict(code=0, data=dict(answer='Token 无效'))), ('false', dict(code=0, data=dict(answer='题库没有该题的答案')))]:
            bank = self.yanxi(yanxi_query_variants=setting)
            with patch('api.answer.requests.Session.post', return_value=response(body)) as post:
                self.assertIsNone(bank._query(dict(title='2026年是（ ）开局之年。')))
            self.assertEqual(post.call_count, 1)

    def test_generic_message_does_not_hide_balance_error_or_token_rotation(self):
        bank = self.yanxi()
        with patch('api.answer.requests.Session.post', side_effect=[response(dict(code=0, message='请求失败', data=dict(answer='余额不足'))), response(dict(code=1, data=dict(answer='B'))) ]):
            self.assertEqual(bank._query(dict(title='Q')), 'B')
        self.assertEqual(bank._token, 'second')
        self.assertEqual(bank.last_query_status, 'hit')

    def test_auth_diagnostic_is_preserved_even_without_data_object(self):
        bank = self.yanxi()
        with patch('api.answer.requests.Session.post', return_value=response(dict(code=0, message='Token 无效', data=None))), patch('api.answer.logger') as log:
            self.assertIsNone(bank._query(dict(title='Q')))
        self.assertEqual(bank.last_query_status, 'error')
        self.assertIn('Token 无效', log.warning.call_args.args[0])

    def test_user_example_has_no_image_suggestions_and_normalizes_lowercase_options(self):
        from chaoxing_desktop.answers import AnswerRouter
        bank = self.yanxi()
        question = dict(title='1+1=？', type='single', options='a.1 b.2 c.3 d.4')
        with patch('api.answer.requests.Session.post', return_value=response(dict(code=1, data=dict(answer='2')))) as post:
            router = AnswerRouter(to_payload(defaults()), Mock(), [('Yanxi', bank)])
            self.assertEqual(router.query(question), '2')
            self.assertEqual(router.choice_letters('2', question), 'B')
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['options'], '1\n2\n3\n4')
        self.assertEqual(payload['title'], '1+1=？')
        self.assertEqual(payload['images'], [])
        self.assertEqual(payload['suggestion_title'], '')
        self.assertEqual(payload['suggestion_options'], '')

    def test_router_reports_misses_errors_and_unusable_answers_separately(self):
        from chaoxing_desktop.answers import AnswerRouter
        bank = self.yanxi()
        channel = Mock()
        bodies = [dict(code=0, message='请求失败', data=dict(answer='题库没有该题的答案')),
                  dict(code=0, message='请求失败', data=dict(answer='服务暂时繁忙')),
                  dict(code=1, data=dict(answer='不属于当前选项')),
                  dict(code=1, data=dict(answer='2'))]
        questions = [dict(title=str(i), type='single', options='A.1\nB.2') for i in range(4)]
        with patch('api.answer.requests.Session.post', side_effect=[response(body) for body in bodies]):
            self.assertEqual(AnswerRouter(to_payload(defaults()), channel, [('Yanxi', bank)]).query_all(questions), [None, None, None, '2'])
        summary = [c.kwargs['message'] for c in channel.send.call_args_list if c.args[0] == 'log'][-1]
        for phrase in ('命中 1', '未命中 1', '请求错误 1', '答案不匹配 1'):
            self.assertIn(phrase, summary)

    def test_error_answer_is_not_used_as_a_real_answer(self):
        for body in (dict(code=0, data=dict(answer='Token 无效')), dict(code=0, data=dict(answer='未找到答案')), dict(code=0, data=None), []):
            with self.subTest(body=body), patch('api.answer.requests.Session.post', return_value=response(body)):
                self.assertIsNone(self.yanxi()._query(dict(title='Q')))

    def test_exhausted_token_rotates_without_recursion(self):
        bank = self.yanxi()
        with patch('api.answer.requests.Session.post', side_effect=[response(dict(code=0, data=dict(answer='次数不足'))), response(dict(code=1, data=dict(answer=['A', 'B'])))]) as post:
            self.assertEqual(bank._query(dict(title='Q')), 'A\nB')
        self.assertEqual([c.kwargs['json']['token'] for c in post.call_args_list], ['first', 'second'])
        with patch('api.answer.requests.Session.post', return_value=response(dict(code=0, data=dict(answer='次数不足')))) as post:
            self.assertIsNone(bank._query(dict(title='Q')))
            self.assertIsNone(bank._query(dict(title='Q')))
        self.assertEqual(post.call_count, 1)

    def test_zero_remaining_balance_does_not_discard_current_answer(self):
        with patch('api.answer.requests.Session.post', return_value=response(dict(code=1, data=dict(answer='A', times=0)))):
            self.assertEqual(self.yanxi()._query(dict(title='Q')), 'A')

    def test_invalid_json_and_http_auth_failure_return_no_answer(self):
        invalid = response()
        invalid.json.side_effect = ValueError('invalid json')
        for res in (invalid, response(status=401)):
            with self.subTest(status=res.status_code), patch('api.answer.requests.Session.post', return_value=res) as post:
                bank = self.yanxi()
                bank._conf['request_retries'] = '3'
                self.assertIsNone(bank._query(dict(title='Q')))
                self.assertEqual(post.call_count, 1)

    def test_transient_errors_retry_with_bounded_attempts(self):
        bank = self.yanxi()
        bank._conf['request_retries'] = '2'
        with patch('api.answer.time.sleep'), patch('api.answer.requests.Session.post', side_effect=[requests.Timeout(), response(status=429), response(dict(code=1, data=dict(answer='A')))]) as post:
            self.assertEqual(bank._query(dict(title='Q')), 'A')
        self.assertEqual(post.call_count, 3)

    def test_token_rotation_also_respects_minimum_request_interval(self):
        bank = self.yanxi(request_interval='5')
        clock = [100.0]
        def tick():
            clock[0] += .25
            return clock[0]
        def advance(seconds):clock[0] += seconds
        with patch('api.answer.time.monotonic', side_effect=tick), \
                patch('api.answer.time.sleep', side_effect=advance) as sleep, \
                patch('api.answer.requests.Session.post', side_effect=[response(dict(code=0, data=dict(answer='次数不足'))), response(dict(code=1, data=dict(answer='A'))) ]):
            self.assertEqual(bank._query(dict(title='Q')), 'A')
        self.assertEqual(sleep.call_count, 1)
        self.assertGreater(sleep.call_args.args[0], 0)
        self.assertLessEqual(sleep.call_args.args[0], 5)

    def test_like_disable_retries_still_queries_once(self):
        bank = TikuLike()
        bank.config_set(dict(tokens='token', likeapi_retry='false', likeapi_retry_times='0', request_timeout='12'))
        with patch.object(bank, 'get_api_balance', return_value=5):
            bank.init_tiku()
        with patch.object(bank, '_query_single', return_value='A') as query:
            self.assertEqual(bank._query(dict(title='Q', options='A x\nB y', type='single')), 'A')
        query.assert_called_once()
        self.assertEqual(bank._timeout, 12)

    def test_adapter_uses_its_own_timeout_and_retries(self):
        bank = TikuAdapter()
        bank.config_set(dict(url='https://example.test/adapter', request_timeout='18', request_retries='1'))
        bank.init_tiku()
        with patch('api.answer.time.sleep'), patch('api.answer.requests.Session.post', side_effect=[response(status=503), response(dict(answer=dict(bestAnswer=['x'])))]) as post:
            self.assertEqual(bank._query(dict(title='Q', type='single', options='A x\nB y')), 'x')
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs['timeout'], (10, 18))

    def test_bank_parameters_are_independent_and_survive_import(self):
        config = defaults()
        config['question_bank'].update(providers='TikuYanxi,TikuLike,TikuAdapter,TikuGo', yanxi_tokens='y', like_tokens='l', adapter_url='https://example.test/a', yanxi_timeout='22', like_timeout='33', adapter_timeout='44', go_timeout='55', yanxi_min_interval='2', like_min_interval='3', adapter_min_interval='4')
        restored = parse_text(serialize(config))
        validate(restored, services=True)
        captured = []
        def bank(conf):
            captured.append(conf)
            return SimpleNamespace(init_tiku=lambda: None, DISABLE=False, _query=lambda q: 'A')
        with patch('api.answer.Tiku.get_tiku_from_config', side_effect=bank):
            build_answers(to_payload(restored), Mock())
        self.assertEqual([c['request_timeout'] for c in captured], ['22', '33', '44', '55'])
        self.assertEqual([c['tokens'] for c in captured[:2]], ['y', 'l'])
        self.assertEqual([c['request_interval'] for c in captured[:3]], ['2', '3', '4'])

    def test_legacy_interval_is_migrated_without_overwriting_new_values(self):
        conf = parse_text('[tiku]\ndelay=7\n[question_bank]\nlike_min_interval=3\n')
        self.assertEqual(conf['question_bank']['yanxi_min_interval'], '7')
        self.assertEqual(conf['question_bank']['like_min_interval'], '3')
        self.assertEqual(conf['question_bank']['adapter_min_interval'], '7')


if __name__ == '__main__':
    unittest.main()
