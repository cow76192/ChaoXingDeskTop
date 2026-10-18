"""OCS v2 compatibility and the observed live-result false rejection (offline)."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing'))
from api.answer import TikuYanxi
from chaoxing_desktop.answers import AnswerRouter
from chaoxing_desktop.bank_question import build_yanxi_environment, restore_image_placeholders
from chaoxing_desktop.config import defaults, to_payload


def router(**settings):
    config = to_payload(defaults())
    config['matching'].update(settings)
    return AnswerRouter(config, Mock())


def bank():
    instance = TikuYanxi()
    instance.config_set(dict(tokens='TEST_ONLY', request_retries='0'))
    instance.init_tiku()
    return instance


class OcsCompatibilityTests(unittest.TestCase):
    def test_observed_percent_answer_maps_despite_country_modifier_position(self):
        q = dict(title='我国传统产业占制造业增加值约（），是我国经济的“基本盘”。',
                 options='A.60%\nB.70%\nC.80%\nD.90%', type='single')
        b = SimpleNamespace(last_result_question='传统产业占我国制造业增加值约(        )，是我国经济的“基本盘”。')
        r = router(title_similarity='0.99')
        self.assertEqual(r.normalize_bank_answer('80%', q, b), '80%')
        self.assertEqual(r.choice_letters('80%', q), 'C')
        self.assertIn('唯一匹配', r.channel.send.call_args.kwargs['message'])

    def test_cache_threshold_still_applies_to_memory(self):
        q = dict(title='我国传统产业占制造业增加值约（），是我国经济的“基本盘”。',
                 options='A.60%\nB.70%\nC.80%\nD.90%', type='single')
        r = router()
        r.memory.remember(q, [('C', '80%')])
        reordered_title = dict(q, title='传统产业占我国制造业增加值约（），是我国经济的“基本盘”。')
        self.assertIsNone(r.memory.find(reordered_title, .96))

    def test_near_title_does_not_authorize_letters_fuzzy_or_duplicate_contents(self):
        title = '我国传统产业占制造业增加值约（），是我国经济的“基本盘”。'
        b = SimpleNamespace(last_result_question='传统产业占我国制造业增加值约（），是我国经济的“基本盘”。')
        for answer, options in [('C', 'A.60%\nB.70%\nC.80%'),
                                ('80%', 'A.80%\nB.80%'),
                                ('约80%', 'A.80%\nB.90%')]:
            with self.subTest(answer=answer, options=options):
                q = dict(title=title, options=options, type='single')
                self.assertIsNone(router().normalize_bank_answer(answer, q, b))
                self.assertNotIn('desktop_answer_letters', q)

    def test_protected_title_difference_cannot_be_overridden_by_exact_option(self):
        cases = [('2026年哪些措施促进经济增长', '2025年哪些措施促进经济增长'),
                 ('下列哪些措施能够促进经济增长', '下列哪些措施不能促进经济增长'),
                 ('我国传统产业占制造业增加值约多少', '我国新兴产业占制造业增加值约多少'),
                 ('我国传统产业占制造业增加值约多少', '我国下一年度教育财政支出增长约多少')]
        for title, returned in cases:
            with self.subTest(title=title, returned=returned):
                q = dict(title=title, type='single', options='A.80%\nB.90%')
                self.assertIsNone(router().normalize_bank_answer('80%', q, SimpleNamespace(last_result_question=returned)))

    def test_single_fragmented_compound_answer_matches_whole_option(self):
        q = dict(title='军队建设要求', type='single', options='A.听党指挥、能打胜仗、作风优良\nB.听党指挥')
        r = router()
        self.assertEqual(r.normalize('听党指挥#\n能打胜仗#\n作风优良', q), '听党指挥、能打胜仗、作风优良')
        self.assertEqual(r.choice_letters('听党指挥、能打胜仗、作风优良', q), 'A')
        self.assertIsNone(router().normalize('听党指挥#未知内容', q))
        self.assertIsNone(router().normalize('A#B', q))

    def test_uploaded_url_map_filters_failures_without_deduplicating_image_bytes(self):
        encoder = Mock()
        encoder.encode.side_effect = [ValueError('unavailable'), 'data:image/png;base64,AA==', 'data:image/png;base64,AA==']
        q = dict(title='<img src="https://example.test/failed.png">',
                 options=['A.<img src="https://example.test/a.png">', 'B.<img src="https://example.test/b.png">'])
        env, urls = build_yanxi_environment(q, encoder)
        self.assertEqual(urls, ['https://example.test/a.png', 'https://example.test/b.png'])
        self.assertEqual(len(env['images']), 2)
        self.assertEqual(restore_image_placeholders('[图片1]#[图片2]', urls), '#'.join(urls))
        self.assertEqual(restore_image_placeholders('[图片0] [图片3]', urls), '[图片0] [图片3]')
        self.assertNotIn('image_urls', env)

    def test_image_answer_restores_before_option_matching_and_preserves_metadata(self):
        q = dict(title='请选择图片', type='single', options='A.<img src="https://example.test/a.png">\nB.<img src="https://example.test/b.png">')
        b = bank()
        tags = [dict(text='AI答案', color='blue')]
        payload = dict(code=1, data=dict(question='请选择图片', answer='[图片2]', ai=True, tags=tags))
        with patch('chaoxing_desktop.bank_question.ImageEncoder.encode', return_value='data:image/png;base64,AA=='), patch('api.answer.requests.Session.post', return_value=Mock(status_code=200, json=Mock(return_value=payload))) as post:
            r = AnswerRouter(to_payload(defaults()), Mock(), [('言溪', b)])
            answer = r.query(q)
        self.assertEqual(answer, '<img src="https://example.test/b.png">')
        self.assertEqual(r.choice_letters(answer, q), 'B')
        self.assertEqual(b.last_result_tags, tags)
        self.assertTrue(b.last_result_ai)
        self.assertFalse(r.memory.rows)
        self.assertEqual(set(post.call_args.kwargs['json']), {'title', 'options', 'type', 'images', 'suggestion_title', 'suggestion_options', 'token', 'v'})

    def test_title_and_returned_options_restore_and_next_question_cannot_reuse_old_map(self):
        b = bank()
        first = dict(code=1, data=dict(question='选择[图片1]', answer=['[图片2]'], options={'A': '[图片2]'}, tags=[]))
        second = dict(code=1, data=dict(question='纯文本', answer='[图片1]'))
        with patch('chaoxing_desktop.bank_question.ImageEncoder.encode', return_value='data:image/png;base64,AA=='), patch('api.answer.requests.Session.post', side_effect=[Mock(status_code=200, json=Mock(return_value=first)), Mock(status_code=200, json=Mock(return_value=second))]):
            self.assertEqual(b._query(dict(title='选择<img src="https://example.test/a.png">', options='A.<img src="https://example.test/b.png">')), 'https://example.test/b.png')
            self.assertEqual(b.last_result_question, '选择https://example.test/a.png')
            self.assertEqual(b.last_result_options, {'A': 'https://example.test/b.png'})
            self.assertEqual(b._query(dict(title='纯文本')), '[图片1]')

    def test_code_zero_diagnostic_is_never_an_answer_and_retains_tags(self):
        b = bank()
        tags = [dict(text='搜不到答案')]
        payload = dict(code=0, data=dict(answer='题库没有该题的答案', tags=tags))
        with patch('api.answer.requests.Session.post', return_value=Mock(status_code=200, json=Mock(return_value=payload))):
            self.assertIsNone(b._query(dict(title='Q')))
        self.assertEqual(b.last_result_tags, tags)
        self.assertEqual(b.last_query_status, 'miss')


if __name__ == '__main__':
    unittest.main()
