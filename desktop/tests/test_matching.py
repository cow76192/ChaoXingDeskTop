"""Positive matching cases and confusable answers that must stay unresolved."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from chaoxing_desktop.answers import AnswerRouter
from chaoxing_desktop.bank_question import query_title_variants
from chaoxing_desktop.config import defaults, parse_text, serialize, to_payload, validate
from chaoxing_desktop.matching import AnswerMemory, canonical, similarity


def router(**settings):
    conf = to_payload(defaults())
    conf['matching'].update(settings)
    return AnswerRouter(conf, Mock())


def question(title='请选择正确选项', kind='single', options='A.需求牵引\nB.改革攻坚\nC.科技赋能\nD.开放合作'):
    return dict(title=title, type=kind, options=options)


class MatchingTests(unittest.TestCase):
    def test_fullwidth_quote_and_answer_prefix(self):
        r, q = router(), question()
        self.assertEqual(r.normalize('正确答案： “需求牵引” ', q), '需求牵引')
        self.assertEqual(r.choice_letters('需求牵引', q), 'A')

    def test_literal_text_answer_is_not_mistaken_for_an_empty_prefix(self):
        r = router()
        self.assertEqual(r.normalize('答案', dict(question(kind='completion'), blank_count=1)), '答案')
        self.assertIsNone(r.normalize('答案：', dict(question(kind='completion'), blank_count=1)))

    def test_numeric_units_are_equivalent_but_different_amounts_are_not(self):
        r = router()
        q = question(options='A.10000亿元\nB.8000亿元')
        self.assertEqual(r.normalize('1万亿元', q), '10000亿元')
        self.assertIsNone(r.normalize('9000亿元', q))
        self.assertEqual(canonical('GDP比重为57.70%'), canonical('GDP比重为57.7%'))

    def test_percent_expression_maps_to_content(self):
        q = question(options='A.57.7%\nB.57.8%')
        self.assertEqual(router().normalize('百分之57.70', q), '57.7%')

    def test_live_multiple_answer_hash_newline_is_accepted(self):
        q = question(kind='multiple')
        answer = router().normalize('需求牵引#\n改革攻坚#\n科技赋能#\n开放合作#', q)
        self.assertEqual(answer, '需求牵引\n改革攻坚\n科技赋能\n开放合作')
        self.assertEqual(q['desktop_answer_letters'], 'ABCD')

    def test_lowercase_separated_letters_and_duplicate_delimiters(self):
        q = question(kind='multiple')
        self.assertEqual(router().normalize('答案：(a、c)', q), '需求牵引\n科技赋能')
        self.assertEqual(q['desktop_answer_letters'], 'AC')

    def test_partial_multiple_answer_never_claims_success(self):
        q = question(kind='multiple')
        self.assertIsNone(router().normalize('需求牵引#未提供的答案', q))
        self.assertNotIn('desktop_answer_letters', q)

    def test_punctuation_inside_a_whole_option_is_preserved(self):
        q = question(kind='multiple', options='A.改革、创新\nB.改革\nC.创新')
        self.assertEqual(router().normalize('改革、创新', q), '改革、创新')
        self.assertEqual(q['desktop_answer_letters'], 'A')

    def test_high_confidence_wording_variation_maps_to_unique_option(self):
        text = '坚持创新驱动发展战略，加快科技成果转化，促进经济实现高质量发展'
        q = question(options='A.' + text + '\nB.坚持扩大对外贸易规模，提高进口产品市场份额')
        answer = text.replace('促进', '推动')
        self.assertEqual(router().normalize(answer, q), text)
        self.assertEqual(q['desktop_match_mode'], 'fuzzy')
        self.assertGreaterEqual(q['desktop_match_score'], .92)

    def test_similar_competing_options_are_ambiguous(self):
        text = '坚持创新驱动发展战略加快科技成果转化促进经济实现高质量发展'
        q = question(options='A.' + text + '\nB.' + text.replace('促进', '推动'))
        self.assertIsNone(router().normalize(text.replace('促进', '带动'), q))

    def test_disable_fuzzy_preserves_format_matching(self):
        text = '坚持创新驱动发展战略加快科技成果转化促进经济实现高质量发展'
        q = question(options='A.' + text + '\nB.别的政策')
        self.assertIsNone(router(fuzzy_options='false').normalize(text.replace('促进', '推动'), q))
        self.assertEqual(router(fuzzy_options='false').normalize('“' + text + '”', q), text)

    def test_different_numbers_polarity_direction_and_images_block_fuzzy(self):
        cases = [
            ('2025年我国服务业增加值占比达到57.7%', '2026年我国服务业增加值占比达到57.7%'),
            ('应当坚持创新驱动发展战略促进经济实现高质量发展', '不应当坚持创新驱动发展战略促进经济实现高质量发展'),
            ('扩大生产性服务业促进经济实现高质量发展', '扩大生活性服务业促进经济实现高质量发展'),
            ('the policy must increase economic productivity', 'the policy must decrease economic productivity'),
            ('the policy is correct under these conditions', 'the policy is not correct under these conditions'),
            ('x >= 100', 'x <= 100'),
            ('x != 100', 'x = 100'),
            ('2*(3+4)', '2*3+4'),
            ('x−100', 'x100'),
            ('x-(y+z)', 'x-y+z'),
            ('X+Y', 'x+y'),
            ('按照第十五个五年规划部署推进经济社会高质量发展', '按照第十四个五年规划部署推进经济社会高质量发展'),
            ('根据有关政策美国企业应当采取的措施', '根据有关政策中国企业应当采取的措施'),
            ('<img src="https://example.test/a.png">', '<img src="https://example.test/b.png">'),
            ('字符串="abc"的长度', '字符串=abc的长度'),
        ]
        for a, b in cases:
            with self.subTest(a=a, b=b):
                self.assertEqual(similarity(a, b), 0)

    def test_short_words_are_not_guessed(self):
        self.assertEqual(similarity('内需', '外需'), 0)
        self.assertIsNone(router().normalize('扩展需求', question(options='A.扩大内需\nB.扩大外需')))

    def test_duplicate_formatted_contents_remain_ambiguous(self):
        self.assertIsNone(router().normalize('“需求牵引”', question(options='A.需求牵引\nB. 需求牵引 ')))

    def test_bank_letters_are_remapped_using_returned_option_contents(self):
        r, q = router(), question(options='A.改革攻坚\nB.需求牵引')
        bank = SimpleNamespace(last_result_question=q['title'], last_result_options=['需求牵引', '改革攻坚'])
        self.assertEqual(r.normalize_bank_answer('A', q, bank), '需求牵引')
        self.assertEqual(q['desktop_answer_letters'], 'B')

    def test_substantively_different_returned_question_is_rejected(self):
        q = question(title='2026年哪些措施能够促进经济增长')
        bank = SimpleNamespace(last_result_question='2025年哪些措施能够促进经济增长')
        self.assertIsNone(router().normalize_bank_answer('需求牵引', q, bank))

    def test_bank_letter_literal_ambiguity_is_rejected(self):
        q = question(options='A.A\nB.B')
        bank = SimpleNamespace(last_result_options=['B', 'A'])
        self.assertIsNone(router().normalize_bank_answer('A', q, bank))

    def test_equivalent_math_operators_and_sentence_punctuation(self):
        self.assertEqual(canonical('x >= 100'), canonical('x ≥ 100'))
        self.assertEqual(similarity('x >= 100', 'x ≥ 100'), 1)
        self.assertEqual(canonical('需求牵引.'), canonical('需求牵引'))

    def test_fuzzy_option_results_do_not_seed_further_reuse(self):
        text = '坚持创新驱动发展战略加快科技成果转化促进经济实现高质量发展'
        bank = SimpleNamespace(_query=Mock(return_value=text.replace('促进', '推动')))
        r = AnswerRouter(to_payload(defaults()), Mock(), [('bank', bank)])
        q = question(options='A.' + text + '\nB.坚持扩大进口市场份额')
        self.assertEqual(r.query(q), text)
        self.assertFalse(r.memory.rows)

    def test_similar_returned_title_without_options_cannot_remap_letters(self):
        title = '根据本年度政府工作报告要求推进服务业扩能提质要突出以下哪些方面'
        q = question(title=title)
        bank = SimpleNamespace(last_result_question=title.replace('要突出', '应突出'))
        self.assertIsNone(router().normalize_bank_answer('A', q, bank))
        self.assertEqual(router().normalize_bank_answer('需求牵引', q, bank), '需求牵引')

    def test_cache_reuses_similar_question_with_reordered_options(self):
        title = '根据本年度政府工作报告要求推进服务业扩能提质要突出以下哪些方面'
        conf = to_payload(defaults())
        bank = SimpleNamespace(_query=Mock(return_value='需求牵引#\n科技赋能'))
        r = AnswerRouter(conf, Mock(), [('bank', bank)])
        first = question(title=title, kind='multiple')
        second = question(title=title.replace('要突出', '应突出'), kind='multiple', options='A.改革攻坚\nB.需求牵引\nC.开放合作\nD.科技赋能')
        self.assertEqual(r.query(first), '需求牵引\n科技赋能')
        self.assertEqual(r.query(second), '需求牵引\n科技赋能')
        self.assertEqual(second['desktop_answer_letters'], 'BD')
        self.assertEqual(second['desktop_match_mode'], 'memory')
        self.assertEqual(bank._query.call_count, 1)

    def test_cache_refuses_conflicts_and_changed_options(self):
        q = question(title='根据本年度政府工作报告要求推进服务业扩能提质要突出以下哪些方面')
        memory = AnswerMemory()
        memory.remember(q, [('A', '需求牵引')])
        memory.remember(q, [('B', '改革攻坚')])
        self.assertIsNone(memory.find(q))
        memory.clear()
        memory.remember(q, [('A', '需求牵引')])
        self.assertIsNone(memory.find(dict(q, options='A.扩大内需\nB.改革攻坚')))

    def test_feedback_clears_memory_and_memory_is_bounded(self):
        r, q = router(), question()
        for _ in range(300):
            r.memory.remember(q, [('A', '需求牵引')])
        self.assertEqual(len(r.memory.rows), 200)
        r.set_work_feedback('上次答案有误')
        self.assertFalse(r.memory.rows)

    def test_cache_does_not_reuse_ai_or_random_answers(self):
        conf = to_payload(defaults())
        ai = Mock()
        ai.query.return_value = 'A'
        r = AnswerRouter(conf, Mock(), ai=ai)
        r.query(question())
        self.assertFalse(r.memory.rows)
        bank = SimpleNamespace(_query=Mock(return_value='A'), last_result_ai=True)
        r = AnswerRouter(conf, Mock(), [('bank', bank)])
        r.query(question())
        self.assertFalse(r.memory.rows)

    def test_equivalent_queries_keep_numbers_and_negation_and_are_bounded(self):
        title = '2026年“不正确”的说法是（ ）。'
        variants = query_title_variants(title)
        self.assertTrue(variants)
        self.assertLessEqual(len(variants), 2)
        for candidate in variants:
            self.assertIn('2026', candidate)
            self.assertIn('不正确', candidate)
        self.assertEqual(query_title_variants('1+1=？'), ['1+1=?'])
        for candidate in query_title_variants('字符串="abc"的长度是（）。'):
            self.assertIn('"abc"', candidate)
        self.assertEqual(query_title_variants('<img src="https://example.test/q.png">'), [])

    def test_matching_settings_round_trip_and_validate(self):
        conf = parse_text(serialize(defaults()))
        validate(conf)
        for section, key, invalid in [('matching', 'min_similarity', '.1'), ('matching', 'min_margin', '0'), ('matching', 'title_similarity', '.5'), ('question_bank', 'yanxi_variant_limit', '3')]:
            changed = parse_text(serialize(conf))
            changed[section][key] = invalid
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(changed)


if __name__ == '__main__':
    unittest.main()
