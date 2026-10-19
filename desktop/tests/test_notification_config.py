"""Notification selection uses the desktop configuration, without legacy INI reads."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing'))
from api.notification import Notification, ServerChan, Qmsg, Bark, Telegram


class NotificationConfigTests(unittest.TestCase):
    def test_desktop_configuration_selects_and_initializes_each_service(self):
        for service in (ServerChan, Qmsg, Bark, Telegram):
            with self.subTest(service=service.__name__):
                config = dict(provider=service.__name__, url='https://example.test/notify', tg_chat_id='123')
                factory = Notification()
                factory.config_set(config)
                selected = factory.get_notification_from_config()
                self.assertIsInstance(selected, service)
                selected.init_notification()
                self.assertFalse(selected.disabled)
                self.assertEqual(selected.url, config['url'])

    def test_missing_configuration_does_not_read_an_unrelated_ini(self):
        with patch('builtins.open', side_effect=AssertionError('unexpected legacy configuration read')):
            factory = Notification()
            self.assertIs(factory.get_notification_from_config(), factory)
            factory.init_notification()
            factory.send('No external notification')
            self.assertTrue(factory.disabled)

    def test_disabled_or_unknown_provider_does_not_send(self):
        for provider in ('', 'Unknown'):
            with self.subTest(provider=provider), patch('requests.post') as post:
                factory = Notification()
                factory.config_set(dict(provider=provider))
                selected = factory.get_notification_from_config()
                selected.init_notification()
                selected.send('No external notification')
                post.assert_not_called()

    def test_incomplete_service_configuration_disables_delivery(self):
        for service in (ServerChan, Qmsg, Bark, Telegram):
            with self.subTest(service=service.__name__), patch('requests.post') as post:
                selected = service()
                selected.config_set(dict(provider=service.__name__, url='', tg_chat_id=''))
                selected.init_notification()
                selected.send('No external notification')
                self.assertTrue(selected.disabled)
                post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
