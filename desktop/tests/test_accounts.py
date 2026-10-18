"""Account switching and session persistence, without platform network access."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from chaoxing_desktop.accounts import AccountStore, read_cookie, write_cookie
from chaoxing_desktop.config import defaults, Redactor, to_payload
from chaoxing_desktop.qml_backend import Backend
from chaoxing_desktop.worker import Channel, real


@unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
class AccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.env = patch.dict(os.environ, CHAOXING_DESKTOP_DATA=self.directory.name)
        self.env.start()
        self.backends = []

    def tearDown(self):
        for backend in self.backends:
            backend.controller.active = False
            backend.close()
            backend.deleteLater()
        self.app.processEvents()
        self.env.stop()
        self.directory.cleanup()

    def backend(self):
        backend = Backend()
        self.backends.append(backend)
        return backend

    def login(self, backend, username, uid):
        backend.setValue('common', 'username', username)
        backend.setValue('common', 'password', 'PASSWORD_SECRET')
        with patch.object(backend.controller, 'start') as start:
            backend.fetchCourses()
        self.assertTrue(start.called, backend.message)
        account_id = start.call_args.args[0]['account_id']
        write_cookie(backend.cookie_path(), {'_uid': uid, 'session': 'SESSION_' + uid})
        backend.on_event(dict(type='session_ready', account_id=account_id, uid=uid))
        backend.on_event(dict(type='courses', demo=False, courses=[dict(courseId=uid, clazzId='a', title=username)]))
        return account_id

    def test_two_sessions_switch_restart_and_task_payload(self):
        b = self.backend()
        first = self.login(b, 'account-a', 'uid-a')
        b.addAccount()
        second = self.login(b, 'account-b', 'uid-b')
        b.renameAccount('第二个账号')
        b.selectVisible(True)
        b.on_event(dict(type='tasks', tasks=[dict(id='old-task', course='b', title='old')]))
        b.switchAccount(first)
        self.assertEqual(b.config['common']['password'], '')
        self.assertEqual((b.courses, b.selected, b.tasks), ([], set(), []))
        self.assertIsNone(b.course_identity)
        with patch.object(b.controller, 'start') as start:
            b.fetchCourses()
        command = start.call_args.args[0]
        self.assertEqual(command['account_id'], first)
        self.assertTrue(command['config']['common']['use_cookies'])
        self.assertEqual(command['account_uid'], 'uid-a')
        self.assertEqual(read_cookie(b.cookie_path())['session'], 'SESSION_uid-a')
        b.on_event(dict(type='courses', demo=False, courses=[dict(courseId='a', clazzId='1', title='a')]))
        b.selectVisible(True)
        with patch.object(b.controller, 'start') as start:
            b.startTasks()
        self.assertEqual(start.call_args.args[0]['account_id'], first)
        reopened = self.backend()
        self.assertEqual(reopened.summary['activeAccount'], first)
        self.assertTrue(reopened.summary['cookie'])
        self.assertEqual(reopened.config['common']['username'], 'account-a')
        self.assertEqual(reopened.config['common']['password'], '')
        self.assertEqual(len(reopened.accountRows), 2)
        self.assertEqual(reopened.account_store.get(second)['label'], '第二个账号')
        for path in self.root.rglob('*'):
            if path.is_file():
                contents = path.read_bytes()
                self.assertNotIn(b'PASSWORD_SECRET', contents)
                self.assertNotIn(b'SESSION_uid-', contents)

    def test_running_lock_and_stale_session_events(self):
        b = self.backend()
        first = self.login(b, 'a', 'uid-a')
        b.addAccount()
        second = self.login(b, 'b', 'uid-b')
        b.controller.active = True
        b.switchAccount(first)
        b.addAccount()
        b.removeAccount()
        b.renameAccount('blocked')
        b.fileAction('clear_cookie')
        self.assertEqual(b.summary['activeAccount'], second)
        self.assertEqual(b.account_store.get(second)['label'], 'b')
        self.assertTrue(b.summary['cookie'])
        b.on_event(dict(type='session_ready', account_id=first, uid='wrong'))
        b.on_event(dict(type='session_ready', account_id=second, uid='wrong', run_id='stale'))
        self.assertEqual(b.account_store.get(second)['uid'], 'uid-b')

    def test_import_mismatch_clear_and_delete_are_scoped(self):
        b = self.backend()
        first = self.login(b, 'a', 'uid-a')
        b.addAccount()
        second = self.login(b, 'b', 'uid-b')
        previous = b.cookie_path().read_bytes()
        source = self.root / 'import.txt'
        source.write_text('_uid=uid-a; session=WRONG', encoding='utf-8')
        with patch('chaoxing_desktop.qml_backend.QFileDialog.getOpenFileName', return_value=(str(source), '')):
            b.fileAction('import_cookie')
        self.assertEqual(b.tone, 'danger')
        self.assertEqual(b.cookie_path().read_bytes(), previous)
        b.fileAction('clear_cookie')
        self.assertFalse(b.summary['cookie'])
        self.assertTrue(b.account_store.cookie_path(first).exists())
        b.removeAccount()
        self.assertIsNone(b.account_store.get(second))
        b.switchAccount(first)
        self.assertEqual(read_cookie(b.cookie_path())['_uid'], 'uid-a')

    def test_legacy_migration_and_corruption_preservation(self):
        (self.root / 'settings.ini').write_text('[common]\nusername=old\n', encoding='utf-8')
        legacy = self.root / 'cookies.txt'
        legacy.write_text('_uid=legacy; session=LEGACY_SECRET', encoding='utf-8')
        b = self.backend()
        self.assertFalse(legacy.exists())
        self.assertEqual(read_cookie(b.cookie_path())['session'], 'LEGACY_SECRET')
        path = self.root / 'accounts.json'
        path.write_text('{broken', encoding='utf-8')
        reopened = self.backend()
        self.assertTrue(reopened.summary['accountError'])
        reopened.addAccount()
        reopened.fetchCourses()
        self.assertEqual(path.read_text(encoding='utf-8'), '{broken')

    def test_failed_migration_retains_plaintext_for_retry(self):
        legacy = self.root / 'cookies.txt'
        legacy.write_text('_uid=old; session=SECRET', encoding='utf-8')
        with patch('chaoxing_desktop.accounts.credentials.protect', side_effect=OSError('DPAPI failed')):
            b = self.backend()
        self.assertTrue(b.account_error)
        self.assertTrue(legacy.exists())
        self.assertFalse((self.root / 'accounts.json').exists())

    def test_failed_account_switch_keeps_current_identity_and_courses(self):
        b = self.backend()
        first = self.login(b, 'a', 'uid-a')
        b.addAccount()
        second = self.login(b, 'b', 'uid-b')
        previous = (self.root / 'accounts.json').read_bytes()
        with patch('chaoxing_desktop.accounts.atomic_write', side_effect=OSError('disk unavailable')):
            b.switchAccount(first)
        self.assertEqual(b.summary['activeAccount'], second)
        self.assertEqual(b.config['common']['username'], 'b')
        self.assertEqual(b.courses[0]['courseId'], 'uid-b')
        self.assertEqual((self.root / 'accounts.json').read_bytes(), previous)

    def test_worker_uses_selected_session_before_listing_courses(self):
        from api import cookies
        from api.base import SessionManager
        store = AccountStore(self.root)
        first = store.add('a')
        store.update(first['id'], uid='uid-a')
        second = store.add('b')
        for row, uid in [(first, 'uid-a'), (second, 'uid-b')]:
            write_cookie(store.cookie_path(row['id']), {'_uid': uid, 'session': 'SESSION_' + uid})
        second_bytes = store.cookie_path(second['id']).read_bytes()
        config = to_payload(defaults())
        config['common'].update(username='a', use_cookies=True)
        output = io.StringIO()
        channel = Channel(output, io.StringIO(), Redactor({}))
        def create_client(*args, **kwargs):
            self.assertEqual(SessionManager.get_session().cookies.get('_uid'), 'uid-a')
            return SimpleNamespace(login=lambda **kw: {'status': True}, get_course_list=lambda: [])
        with patch.object(SessionManager, '_instance', None), \
             patch.object(cookies.gc, 'COOKIES_PATH', cookies.gc.COOKIES_PATH), \
             patch.object(cookies, '_expected_uid', ''), patch.object(cookies, '_load_existing', True), \
             patch('chaoxing_desktop.worker.load_core', return_value=SimpleNamespace(create_client=create_client)), \
             patch('requests.sessions.Session.request', side_effect=AssertionError('unexpected network')):
            real(channel, dict(action='courses', account_id=first['id'], config=config, data_dir=str(self.root)))
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[0]['type'], 'session_ready')
        self.assertEqual(events[0]['uid'], 'uid-a')
        self.assertEqual(events[-1]['type'], 'courses')
        self.assertNotIn('SESSION_', output.getvalue())
        self.assertEqual(store.cookie_path(second['id']).read_bytes(), second_bytes)

    def test_expired_or_wrong_session_cannot_read_courses(self):
        from api import cookies
        from api.base import SessionManager
        import requests
        store = AccountStore(self.root)
        row = store.add('a')
        store.update(row['id'], uid='uid-a')
        config = to_payload(defaults())
        config['common'].update(username='a', use_cookies=True)
        for status, uid in [(False, 'uid-a'), (True, 'uid-other')]:
            with self.subTest(status=status, uid=uid):
                session = requests.Session()
                session.cookies.set('_uid', uid)
                output = io.StringIO()
                channel = Channel(output, io.StringIO(), Redactor({}))
                cx = SimpleNamespace(login=lambda **kw: {'status': status, 'msg': '会话已失效'},
                                     get_course_list=lambda: self.fail('invalid account read courses'))
                with patch.object(cookies.gc, 'COOKIES_PATH', cookies.gc.COOKIES_PATH), \
                     patch.object(cookies, '_expected_uid', ''), patch.object(cookies, '_load_existing', True), \
                     patch.object(SessionManager, 'get_session', return_value=session), \
                     patch('chaoxing_desktop.worker.load_core', return_value=SimpleNamespace(create_client=lambda *a, **k: cx)):
                    with self.assertRaises((RuntimeError, ValueError)):
                        real(channel, dict(action='courses', account_id=row['id'], config=config, data_dir=str(self.root)))
                self.assertNotIn('session_ready', output.getvalue())

    def test_cookie_adapter_rejects_other_uid_and_password_can_replace_corruption(self):
        from api import cookies
        import requests
        store = AccountStore(self.root)
        row = store.add('a')
        path = store.cookie_path(row['id'])
        path.parent.mkdir(parents=True)
        path.write_bytes(b'corrupt')
        with patch.object(cookies.gc, 'COOKIES_PATH', cookies.gc.COOKIES_PATH), \
             patch.object(cookies, '_expected_uid', ''), patch.object(cookies, '_load_existing', True):
            cookies.configure_account(path, 'uid-a', load_existing=False)
            self.assertEqual(cookies.use_cookies(), {})
            session = requests.Session()
            session.cookies.update({'_uid': 'wrong', 'session': 'WRONG'})
            with self.assertRaises(ValueError):
                cookies.save_cookies(session)
            self.assertEqual(path.read_bytes(), b'corrupt')
            session.cookies.set('_uid', 'uid-a')
            cookies.save_cookies(session)
            self.assertEqual(cookies.use_cookies()['_uid'], 'uid-a')


if __name__ == '__main__':
    unittest.main()
