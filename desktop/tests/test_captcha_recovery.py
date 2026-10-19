"""Verification redirects, shared session recovery and bounded media retries."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing'))
from api.base import Chaoxing, SessionManager, StudyResult
from api.captcha import CaptchaRecovery, CxCaptcha, is_captcha_response
from chaoxing_desktop.runtime import ChapterResult, process_chapter, process_job
from chaoxing_desktop.worker import run_tasks


def response(status=200, text='', mime='', content=b'', location='', data=None):
    if status == 403 and not text:
        text = '<html>验证码 processVerify</html>'
    return Mock(status_code=status, text=text, content=content,
                headers={'Content-Type': mime, 'Location': location}, json=Mock(return_value=data))


class CaptchaRecoveryTests(unittest.TestCase):
    def test_302_verification_is_observed_without_following_redirects(self):
        session = Mock()
        session.get.return_value = response(status=302, location='/')
        solver = CxCaptcha('UA', source_session=session, ocr=Mock())
        self.assertTrue(solver.submitCaptcha('1234'))
        self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
        self.assertEqual(session.get.call_args.kwargs['timeout'], (5, 15))
        session.get.return_value.close.assert_called_once()

    def test_login_external_redirect_and_200_are_not_verification_success(self):
        for status, location in [(302, '/login'), (302, '/html/processVerify.ac'),
                                 (302, 'https://example.test/'), (302, ''), (200, '/')]:
            with self.subTest(status=status, location=location):
                session = Mock()
                session.get.return_value = response(status=status, location=location)
                self.assertFalse(CxCaptcha('UA', source_session=session, ocr=Mock()).submitCaptcha('1234'))

    def test_content_type_parameters_and_session_cookies_are_preserved(self):
        session = requests.Session()
        session.cookies.set('verification', 'updated', domain='mooc1.chaoxing.com', path='/')
        session.proxies = {'https': 'http://127.0.0.1:1'}
        solver = CxCaptcha('UA', cookies='verification=stale', source_session=session, ocr=Mock())
        self.assertIs(solver.s, session)
        self.assertEqual(session.cookies.get('verification'), 'updated')
        self.assertNotIn('Cookie', session.headers)
        self.assertTrue(session.verify)
        with patch.object(session, 'get', return_value=response(mime='image/png; charset=UTF-8', content=b'png')) as get:
            self.assertEqual(solver.getCaptcha(), b'png')
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        self.assertEqual(session.proxies['https'], 'http://127.0.0.1:1')

    def test_missing_ocr_does_not_fetch_or_submit_a_captcha(self):
        session = Mock()
        solver = CxCaptcha('UA', source_session=session, ocr=None)
        self.assertFalse(solver.try_pass())
        session.get.assert_not_called()
        recovery = CaptchaRecovery()
        with patch('api.captcha.ocr_init', return_value=None) as init:
            for _ in range(3):
                self.assertTrue(recovery.recover(session, 'UA', response(status=403), Mock())[1])
        init.assert_called_once()
        session.get.assert_not_called()
        self.assertTrue(recovery.blocked)

    def test_timeout_and_non_image_response_stop_without_ocr(self):
        for result in [requests.Timeout(), response(mime='text/html', content=b'<html>login</html>')]:
            with self.subTest(result=type(result).__name__):
                session, ocr = Mock(), Mock()
                if isinstance(result, Exception):
                    session.get.side_effect = result
                else:
                    session.get.return_value = result
                solver = CxCaptcha('UA', source_session=session, ocr=ocr)
                self.assertFalse(solver.try_pass())
                ocr.classification.assert_not_called()
                self.assertEqual(session.get.call_count, 1)

    def test_recovery_retries_progress_only_after_successful_verification(self):
        session = Mock()
        session.get.side_effect = [response(mime='image/png', content=b'png'), response(status=302, location='/')]
        original, retried = response(status=403), response(data={'isPassed': False})
        retry = Mock(return_value=retried)
        recovery = CaptchaRecovery()
        with patch('api.captcha.ocr_init', return_value=Mock(classification=Mock(return_value='1234'))) as init:
            result, required = recovery.recover(session, 'UA', original, retry)
        self.assertIs(result, retried)
        self.assertFalse(required)
        self.assertFalse(recovery.blocked)
        retry.assert_called_once()
        original.close.assert_called_once()
        init.assert_called_once()

    def test_three_rejections_are_shared_and_never_repeat_for_next_chapter(self):
        session = Mock()
        session.get.side_effect = [item for _ in range(3) for item in (response(mime='image/png', content=b'png'), response(status=200))]
        recovery = CaptchaRecovery()
        retry = Mock()
        with patch('api.captcha.ocr_init', return_value=Mock(classification=Mock(return_value='1234'))), patch('api.captcha.time.sleep'):
            for _ in range(4):
                self.assertTrue(recovery.recover(session, 'UA', response(status=403), retry)[1])
        self.assertEqual(session.get.call_count, 6)
        retry.assert_not_called()

    def test_successful_redirect_with_persistent_403_requires_manual_verification(self):
        recovery = CaptchaRecovery()
        with patch('api.captcha.ocr_init', return_value=Mock()), patch('api.captcha.CxCaptcha') as solver:
            solver.return_value.try_pass.return_value = True
            retry = Mock(return_value=response(status=403))
            self.assertTrue(recovery.recover(Mock(), 'UA', response(status=403), retry)[1])
        self.assertTrue(recovery.blocked)
        retry.assert_called_once()

    def test_concurrent_stale_challenges_share_one_model_and_one_verification(self):
        recovery, barrier = CaptchaRecovery(), threading.Barrier(2)
        results = []
        def recover():
            barrier.wait(timeout=5)
            results.append(recovery.recover(Mock(), 'UA', response(status=403),
                                           Mock(return_value=response(data={'isPassed': False})), observed_generation=0))
        with patch('api.captcha.ocr_init', return_value=Mock()) as init, patch('api.captcha.CxCaptcha') as solver:
            solver.return_value.try_pass.return_value = True
            with ThreadPoolExecutor(max_workers=2) as pool:
                for future in [pool.submit(recover), pool.submit(recover)]:
                    future.result(timeout=5)
        init.assert_called_once()
        solver.return_value.try_pass.assert_called_once()
        self.assertTrue(all(not required for _, required in results))

    def test_verification_redirect_followed_by_plain_403_is_not_recovered(self):
        recovery = CaptchaRecovery()
        with patch('api.captcha.ocr_init', return_value=Mock()), patch('api.captcha.CxCaptcha') as solver:
            solver.return_value.try_pass.return_value = True
            retry = Mock(return_value=response(status=403, text='<html>403 Forbidden</html>'))
            self.assertTrue(recovery.recover(Mock(), 'UA', response(status=403), retry)[1])
        self.assertTrue(recovery.blocked)
        retry.assert_called_once()

    def test_json_validation_field_is_not_a_captcha_page(self):
        self.assertFalse(is_captcha_response(response(text='{"isPassed":false,"validate":true}')))
        self.assertTrue(is_captcha_response(response(text='<html>验证码 processVerify</html>')))
        self.assertFalse(is_captcha_response(response(status=403, text='<html>403 Forbidden</html>')))

    def test_current_challenge_form_supplies_its_own_same_origin_endpoints(self):
        challenge = response(status=403, text='<form action="/current/verify" method="get"><img src="/current/captcha.png"><input name="verifycode"><input type="hidden" name="challenge" value="example"></form>')
        challenge.url = 'https://mooc1.chaoxing.com/mooc-ans/multimedia/log/a/example'
        session = Mock()
        session.get.side_effect = [response(mime='image/png', content=b'png'), response(status=302, location='/')]
        solver = CxCaptcha('UA', ocr=Mock(classification=Mock(return_value='1234')), source_session=session, challenge_response=challenge)
        self.assertTrue(solver.try_pass())
        self.assertEqual(session.get.call_args_list[0].args[0], 'https://mooc1.chaoxing.com/current/captcha.png')
        self.assertEqual(session.get.call_args_list[1].args[0], 'https://mooc1.chaoxing.com/current/verify')
        self.assertEqual(session.get.call_args_list[1].kwargs['params'], {'verifycode': '1234', 'challenge': 'example'})

    def test_unsupported_or_external_image_challenges_do_not_probe_old_endpoint(self):
        for html in ['<html>captcha slider</html>',
                     '<form action="https://example.test/verify"><img src="/captcha.png"><input name="verifycode"></form>',
                     '<form action="/verify" method="post"><img src="/captcha.png"><input name="verifycode"></form>']:
            with self.subTest(html=html):
                challenge = response(status=403, text=html)
                challenge.url = 'https://mooc1.chaoxing.com/mooc-ans/example'
                session = Mock()
                solver = CxCaptcha('UA', ocr=Mock(), source_session=session, challenge_response=challenge)
                self.assertFalse(solver.try_pass())
                session.get.assert_not_called()

    def test_plain_forbidden_does_not_invoke_ocr(self):
        client, session = Chaoxing(), Mock()
        client.video_log_limiter = Mock()
        session.get.return_value = response(status=403, text='<html>403 Forbidden</html>')
        with patch.object(client, 'get_uid', return_value='u'), patch('api.captcha.ocr_init') as init:
            self.assertEqual(self.progress(client, session), (False, 403))
        init.assert_not_called()

    def progress(self, client, session):
        return client.video_progress_log(session, dict(clazzId='c', courseId='course', cpi='p'),
                                         dict(jobid='j', objectid='o', otherinfo='-rt_1', rt='1',
                                              videoFaceCaptureEnc='', attDuration='', attDurationEnc=''),
                                         {}, 'TOKEN', 60, 15, headers={'User-Agent': 'UA'})

    def test_real_media_boundary_returns_pending_without_repeating_requests(self):
        client, session = Chaoxing(), Mock()
        client.video_log_limiter = Mock()
        session.get.return_value = response(status=403)
        with patch.object(client, 'get_uid', return_value='u'), patch('api.captcha.ocr_init', return_value=None):
            self.assertEqual(self.progress(client, session), (False, 428))
            self.assertEqual(self.progress(client, session), (False, 428))
        self.assertEqual(session.get.call_count, 1)

    def test_progress_recovery_can_confirm_platform_success(self):
        client, session = Chaoxing(), Mock()
        client.video_log_limiter = Mock()
        session.get.side_effect = [response(status=403), response(mime='image/png', content=b'png'),
                                   response(status=302, location='/'), response(data={'isPassed': True})]
        with patch.object(client, 'get_uid', return_value='u'), patch('api.captcha.ocr_init', return_value=Mock(classification=Mock(return_value='1234'))):
            self.assertEqual(self.progress(client, session), (True, 200))
        self.assertEqual(session.get.call_count, 4)

    def test_html_or_missing_progress_flag_cannot_mark_media_complete(self):
        for data in (None, {}, {'isPassed': 'false'}):
            with self.subTest(data=data):
                client, session = Chaoxing(), Mock()
                client.video_log_limiter = Mock()
                session.get.return_value = response(data=data)
                with patch.object(client, 'get_uid', return_value='u'):
                    self.assertEqual(self.progress(client, session), (False, 502))

    def test_initial_media_report_uses_recorded_position_and_stops_on_verification(self):
        client, session = Chaoxing(), Mock()
        session.get.return_value.status_code = 200
        session.get.return_value.text = '{}'
        session.get.return_value.url = 'https://mooc1.chaoxing.com/ananas/status/o'
        session.get.return_value.json.return_value = dict(status='success', dtoken='t', crc='c', key='k', duration=60)
        with patch.object(SessionManager, 'get_session', return_value=session), patch.object(client, 'get_fid', return_value='f'), patch.object(client, 'video_progress_log', return_value=(False, 428)) as progress:
            self.assertEqual(client.study_video({}, dict(objectid='o', playTime=15000, name='video'), {}), StudyResult.VERIFICATION_REQUIRED)
        progress.assert_called_once()
        self.assertEqual(progress.call_args.args[5:7], (60, 15))
        self.assertEqual(progress.call_args.kwargs['_isdrag'], 3)

    def test_video_does_not_fallback_to_audio_when_session_needs_verification(self):
        client = Mock(study_video=Mock(return_value=StudyResult.VERIFICATION_REQUIRED))
        self.assertEqual(process_job(client, {}, {'type': 'video'}, {}, 1), StudyResult.VERIFICATION_REQUIRED)
        client.study_video.assert_called_once()

    def test_chapter_and_scheduler_preserve_pending_without_five_retry_rounds(self):
        client = Mock()
        client.get_job_list.return_value = ([{'type': 'video'}], {})
        with patch('chaoxing_desktop.runtime.process_job', return_value=StudyResult.VERIFICATION_REQUIRED):
            self.assertEqual(process_chapter(client, {}, {}, 1), ChapterResult.PENDING)
        process = Mock(return_value=ChapterResult.PENDING)
        statuses = run_tasks(Mock(), [dict(id='c', title='chapter')], process,
                             dict(jobs=1, retry_interval=.1, notopen_action='retry'), ChapterResult)
        self.assertEqual(statuses, {'c': 'pending'})
        process.assert_called_once()
        with patch('chaoxing_desktop.runtime.process_job', return_value=StudyResult.FORBIDDEN):
            self.assertEqual(process_chapter(client, {}, {}, 1), ChapterResult.PENDING)


if __name__ == '__main__':
    unittest.main()
