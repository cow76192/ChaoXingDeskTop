"""Review policies select bank/AI flow without weakening option mapping."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing'))
from api.answer import TikuYanxi
from chaoxing_desktop.answers import AnswerRouter
from chaoxing_desktop.config import BANK_REVIEW_POLICIES, defaults, parse_text, serialize, to_payload, validate


def question():
    return dict(title='2026年该产业占比约多少', type='single', options='A.70%\nB.80%\nC.90%')


def setup(policy='strict', enabled=False):
    config = to_payload(defaults())
    config['matching']['bank_review_policy'] = policy
    config['ai'].update(enabled=str(enabled).lower(), check_connection='false')
    ai = Mock(query=Mock(return_value='90%')) if enabled else None
    bank = SimpleNamespace(_query=Mock(return_value='80%'), last_result_question='2025年该产业占比约多少')
    return AnswerRouter(config, Mock(), [('bank', bank)], ai), bank, ai


class BankReviewPolicyTests(unittest.TestCase):
    def test_legacy_config_defaults_to_strict_and_rejects_changed_year(self):
        config = parse_text('[matching]\nfuzzy_options=true\n')
        self.assertEqual(config['matching']['bank_review_policy'], 'strict')
        r, _, _ = setup()
        self.assertIsNone(r.query(question()))

    def test_follow_ai_rejects_bank_and_passes_question_to_enabled_ai(self):
        r, bank, ai = setup('ai_dependent', True)
        q = question()
        self.assertEqual(r.query(q), '90%')
        self.assertEqual(r.choice_letters('90%', q), 'C')
        bank._query.assert_called_once()
        ai.query.assert_called_once()

    def test_follow_ai_accepts_mappable_bank_content_when_ai_disabled(self):
        r, _, ai = setup('ai_dependent', False)
        q = question()
        self.assertEqual(r.query(q), '80%')
        self.assertEqual(r.choice_letters('80%', q), 'B')
        self.assertEqual(q['desktop_bank_review'], 'relaxed')
        self.assertIsNone(ai)
        self.assertTrue(any('AI 已关闭' in c.kwargs.get('message', '') for c in r.channel.send.call_args_list))

    def test_options_only_can_accept_bank_content_with_ai_enabled(self):
        r, _, ai = setup('options_only', True)
        self.assertEqual(r.query(question()), '80%')
        ai.query.assert_not_called()
        self.assertFalse(r.memory.rows)

    def test_explicit_strict_still_rejects_without_ai(self):
        r, _, _ = setup('strict', False)
        self.assertIsNone(r.query(question()))

    def test_ai_connection_failure_never_silently_relaxes_review(self):
        r, _, ai = setup('ai_dependent', True)
        r.config['ai']['check_connection'] = 'true'
        ai.check_connection.side_effect = RuntimeError('offline')
        self.assertIsNone(r.query(question()))
        ai.query.assert_not_called()

    def test_matching_bank_answer_is_used_before_ai_even_in_strict_mode(self):
        r, bank, ai = setup('ai_dependent', True)
        q = question()
        bank.last_result_question = q['title']
        self.assertEqual(r.query(q), '80%')
        ai.query.assert_not_called()

    def test_relaxed_policy_does_not_accept_absent_ambiguous_or_invalid_option(self):
        for answer, options in [('81%', 'A.70%\nB.80%'), ('80%', 'A.80%\nB.80%'), ('D', 'A.70%\nB.80%')]:
            with self.subTest(answer=answer, options=options):
                r, bank, _ = setup('options_only')
                bank._query.return_value = answer
                q = dict(question(), options=options)
                self.assertIsNone(r.query(q))
                self.assertNotIn('desktop_answer_letters', q)

    def test_relaxed_policy_still_remaps_returned_letters_by_option_content(self):
        r, bank, _ = setup('options_only')
        bank._query.return_value = 'A'
        bank.last_result_options = ['80%', '70%', '90%']
        q = question()
        self.assertEqual(r.query(q), '80%')
        self.assertEqual(r.choice_letters('80%', q), 'B')

    def test_relaxed_policy_allows_current_letter_if_bank_has_no_original_options(self):
        r, bank, _ = setup('ai_dependent')
        bank._query.return_value = 'B'
        q = question()
        self.assertEqual(r.query(q), '80%')
        self.assertEqual(r.choice_letters('80%', q), 'B')

    def test_invalid_bank_original_options_do_not_become_current_letters(self):
        r, bank, _ = setup('options_only')
        bank._query.return_value = 'A'
        bank.last_result_options = ['不属于当前题的选项']
        self.assertIsNone(r.query(question()))

    def test_relaxed_results_do_not_seed_cache_and_ai_switch_clears_metadata(self):
        r, bank, _ = setup('ai_dependent')
        q = question()
        self.assertEqual(r.query(q), '80%')
        self.assertEqual(r.query(q), '80%')
        self.assertFalse(r.memory.rows)
        self.assertEqual(bank._query.call_count, 2)
        r.config['ai']['enabled'] = 'true'
        r.ai = Mock(query=Mock(return_value='90%'))
        self.assertEqual(r.query(q), '90%')
        self.assertNotIn('desktop_bank_review', q)
        self.assertEqual(r.choice_letters('90%', q), 'C')

    def test_error_diagnostic_cannot_be_adopted_by_relaxed_policy(self):
        bank = TikuYanxi()
        bank.config_set(dict(tokens='TEST_ONLY', request_retries='0'))
        bank.init_tiku()
        r, _, _ = setup('options_only')
        r.banks = [('言溪', bank)]
        payload = dict(code=0, data=dict(answer='Token 无效'))
        with patch('api.answer.requests.Session.post', return_value=Mock(status_code=200, json=Mock(return_value=payload))):
            self.assertIsNone(r.query(question()))
        self.assertEqual(bank.last_query_status, 'error')

    def test_policy_round_trip_and_invalid_value_validation(self):
        for _, policy in BANK_REVIEW_POLICIES:
            config = defaults()
            config['matching']['bank_review_policy'] = policy
            loaded = parse_text(serialize(config))
            validate(loaded)
            self.assertEqual(to_payload(loaded)['matching']['bank_review_policy'], policy)
        config['matching']['bank_review_policy'] = 'ignore_everything'
        with self.assertRaises(ValueError):
            validate(config)


if __name__ == '__main__':
    unittest.main()
