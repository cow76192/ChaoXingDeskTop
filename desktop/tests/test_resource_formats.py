"""Resource routing and protocol failures, without contacting the platform."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import requests

sys.path[:0] = [str(Path(__file__).resolve().parents[1]),
               str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing')]
from api.base import Chaoxing, SessionManager, StudyResult
from api.config import GlobalConst as gc
from api.decode import _process_attachment_cards, decode_course_card
from chaoxing_desktop.runtime import process_job


COURSE = dict(courseId='course', clazzId='class', cpi='cpi')


def response(body=None, status=200, text=None):
    reply = Mock(status_code=status, url='https://mooc1.chaoxing.com/ananas/status/object')
    reply.text = json.dumps(body) if text is None else text
    reply.json.side_effect = ValueError if text is not None else None
    reply.json.return_value = body
    return reply


def card(name, **extra):
    return dict(dict(type='video', job=True, jobid='job', objectId='object',
                     property=dict(name=name)), **extra)


class ResourceFormatTests(unittest.TestCase):
    def test_legacy_mp3_uses_audio_before_any_report(self):
        job = _process_attachment_cards([card('xcITyyzhjc-U1-Partone.mp3')])[0]
        self.assertEqual(job['type'], 'audio')
        client = Mock()
        client.study_video.return_value = StudyResult.SUCCESS
        self.assertEqual(process_job(client, COURSE, job, {}, 1), StudyResult.SUCCESS)
        self.assertEqual(client.study_video.call_args.kwargs['_type'], 'Audio')

    def test_audio_extensions_and_module_only_cards(self):
        for name in ('Track.MP3', 'Track.m4a', 'Track.aac', 'Track.wav', 'Track.flac',
                     'Track.ogg', 'Track.opus', 'Track.wma', 'Track.amr', 'Track%20One.mp3?x=1'):
            with self.subTest(name=name):
                self.assertEqual(_process_attachment_cards([card(name)])[0]['type'], 'audio')
        for key, value in (('module', 'insertaudio'), ('type', 'audio'), ('resourceType', 'Audio')):
            item = card('No extension')
            item['property'][key] = value
            self.assertEqual(_process_attachment_cards([item])[0]['type'], 'audio')
        item = card('No extension', type='')
        item['property']['module'] = 'insertaudio'
        self.assertEqual(_process_attachment_cards([item])[0]['type'], 'audio')

    def test_video_module_has_priority_and_video_formats_stay_video(self):
        for name in ('lesson.mp4', 'lesson.webm', 'lesson.mov', 'lesson.m3u8', 'lesson.mp3'):
            item = card(name)
            item['property']['module'] = 'insertvideo'
            job = _process_attachment_cards([item])[0]
            self.assertEqual(job['type'], 'video')
            client = Mock(study_video=Mock(return_value=StudyResult.ERROR))
            self.assertEqual(process_job(client, COURSE, job, {}, 1), StudyResult.ERROR)
            self.assertEqual(client.study_video.call_count, 1)
            self.assertEqual(client.study_video.call_args.kwargs['_type'], 'Video')

    def test_flat_legacy_job_is_also_routed_as_audio(self):
        client = Mock(study_video=Mock(return_value=StudyResult.SUCCESS))
        process_job(client, COURSE, dict(type='video', name='lesson.mp3'), {}, 1)
        self.assertEqual(client.study_video.call_args.kwargs['_type'], 'Audio')

    def test_mp3_full_pipeline_sends_audio_dtype_and_referer(self):
        item = card('xcITyyzhjc-U1-Partone.mp3')
        item['otherInfo'] = 'nodeId_node-cpi_cpi-rt_1'
        job = _process_attachment_cards([item])[0]
        client = Chaoxing()
        client.video_log_limiter = Mock()
        session = Mock(get=Mock(side_effect=[
            response(dict(status='success', dtoken='token', duration=141)),
            response(dict(isPassed=True))]))
        with patch.object(SessionManager, 'get_session', return_value=session), \
                patch.object(client, 'get_fid', return_value='f'), \
                patch.object(client, 'get_uid', return_value='u'):
            self.assertEqual(process_job(client, COURSE, job, {}, 1), StudyResult.SUCCESS)
        request = session.get.call_args_list[-1]
        self.assertEqual(request.kwargs['params']['dtype'], 'Audio')
        self.assertEqual(request.kwargs['params']['playingTime'], 0)
        self.assertEqual(request.kwargs['headers'], gc.AUDIO_HEADERS)

    def test_nested_resource_identifiers_are_preserved(self):
        for kind, module in (('audio', 'insertaudio'), ('document', 'insertdoc')):
            item = dict(type=kind, job=True, property=dict(module=module, _jobid='nested-job',
                                                        objectid='nested-object', name='resource'))
            job = _process_attachment_cards([item])[0]
            self.assertEqual(job['jobid'], 'nested-job')
            self.assertEqual(job['objectid'], 'nested-object')

    def test_card_json_preserves_spaces_multiline_and_embedded_braces(self):
        item = card('New Soul }; 中文 .mp3')
        raw = dict(attachments=[item], defaults={'knowledgeid': 'node'})
        jobs, info = decode_course_card('var mArg = ' + json.dumps(raw, indent=2) + ';')
        self.assertEqual(jobs[0]['name'], 'New Soul }; 中文 .mp3')
        self.assertEqual(jobs[0]['type'], 'audio')
        self.assertEqual(info['knowledgeid'], 'node')

    def test_document_module_and_unsupported_tasks_are_retained(self):
        for name in ('slides.ppt', 'slides.pptx', 'notes.pdf', 'notes.docx'):
            item = card(name, type='')
            item['property']['module'] = 'insertdoc'
            self.assertEqual(_process_attachment_cards([item])[0]['type'], 'document')
        jobs = _process_attachment_cards([card('legacy.swf', type='flash')])
        self.assertEqual(jobs[0]['type'], 'unsupported')
        self.assertEqual(process_job(Mock(), COURSE, jobs[0], {}, 1), StudyResult.ERROR)

    def test_each_card_retains_its_own_defaults(self):
        pages = []
        for n in range(2):
            pages.append(response(text='mArg=' + json.dumps(dict(
                attachments=[card(f'audio{n}.mp3')],
                defaults=dict(knowledgeid=str(n), reportTimeInterval=30 + n))) + ';'))
        pages += [response(text='mArg={};') for _ in range(5)]
        client = Chaoxing()
        client.rate_limiter = Mock()
        with patch.object(SessionManager, 'get_session', return_value=Mock(get=Mock(side_effect=pages))):
            jobs, info = client.get_job_list(COURSE, {'id': 'node'})
        study = Mock(study_video=Mock(return_value=StudyResult.SUCCESS))
        for n, job in enumerate(jobs):
            process_job(study, COURSE, job, info, 1)
            self.assertEqual(study.study_video.call_args.args[2]['knowledgeid'], str(n))
            self.assertEqual(study.study_video.call_args.args[2]['reportTimeInterval'], 30 + n)

    def run_resource(self, kind, reply, otherinfo='', info=None, token='token'):
        client = Chaoxing()
        session = Mock(get=Mock(return_value=reply))
        job = dict(jobid='job', jtoken=token, otherinfo=otherinfo)
        with patch.object(SessionManager, 'get_session', return_value=session):
            result = (client.study_document(COURSE, job, info) if kind == 'document' else
                      client.study_read(COURSE, job, info or {}))
        return result, session

    def test_document_and_read_require_explicit_platform_success(self):
        cases = [(dict(status=True), StudyResult.SUCCESS),
                 (dict(status=False, msg='denied'), StudyResult.ERROR),
                 (dict(status='false'), StudyResult.ERROR),
                 ({}, StudyResult.ERROR), ([], StudyResult.ERROR)]
        for kind in ('document', 'read'):
            for body, expected in cases:
                with self.subTest(kind=kind, body=body):
                    reply = response(body)
                    result, _ = self.run_resource(kind, reply, info={'knowledgeid': 'node'})
                    self.assertEqual(result, expected)
                    reply.close.assert_called_once()

    def test_document_and_read_reject_login_verification_and_http_errors(self):
        cases = [(200, '<form><input type="password"></form>', StudyResult.FORBIDDEN),
                 (200, '<html>captcha 验证码</html>', StudyResult.VERIFICATION_REQUIRED),
                 (200, '<html>maintenance</html>', StudyResult.ERROR),
                 (403, 'Forbidden', StudyResult.FORBIDDEN),
                 (503, 'Unavailable', StudyResult.ERROR)]
        for kind in ('document', 'read'):
            for status, text, expected in cases:
                with self.subTest(kind=kind, status=status, text=text):
                    reply = response(status=status, text=text)
                    result, _ = self.run_resource(kind, reply, info={'knowledgeid': 'node'})
                    self.assertEqual(result, expected)
                    reply.close.assert_called_once()

    def test_document_uses_defaults_or_node_and_encodes_parameters(self):
        for otherinfo, info in (('', {'knowledgeid': 'node'}), ('nodeId_node-cpi_x', None)):
            result, session = self.run_resource('document', response({'status': True}),
                                                otherinfo, info, token='a&b+c=')
            self.assertEqual(result, StudyResult.SUCCESS)
            self.assertEqual(session.get.call_args.kwargs['params']['knowledgeid'], 'node')
            self.assertEqual(session.get.call_args.kwargs['params']['jtoken'], 'a&b+c=')
        result, session = self.run_resource('document', response({'status': True}))
        self.assertEqual(result, StudyResult.ERROR)
        session.get.assert_not_called()

    def test_invalid_media_status_never_starts_progress(self):
        cases = [(response(status=403, text='Forbidden'), StudyResult.FORBIDDEN),
                 (response(text='<html>captcha</html>'), StudyResult.VERIFICATION_REQUIRED),
                 (response(text='<form><input type="password"></form>'), StudyResult.FORBIDDEN),
                 (response(text='maintenance'), StudyResult.ERROR),
                 (response([]), StudyResult.ERROR),
                 (response({'status': 'failed'}), StudyResult.ERROR)]
        for duration in (None, 0, -1, 'NaN', 'Infinity', True):
            cases.append((response(dict(status='success', dtoken='t', duration=duration)), StudyResult.ERROR))
        cases.append((response(dict(status='success', duration=60)), StudyResult.ERROR))
        for reply, expected in cases:
            client = Chaoxing()
            client.video_progress_log = Mock()
            with patch.object(SessionManager, 'get_session', return_value=Mock(get=Mock(return_value=reply))), \
                    patch.object(client, 'get_fid', return_value='f'):
                self.assertEqual(client.study_video(COURSE, dict(objectid='o'), {}), expected)
            client.video_progress_log.assert_not_called()
            reply.close.assert_called_once()

    def test_audio_status_and_progress_both_use_audio_headers(self):
        client = Chaoxing()
        client.desktop_media_progress = Mock()
        session = Mock(get=Mock(return_value=response(dict(status='success', dtoken='t', duration=60))))
        with patch.object(SessionManager, 'get_session', return_value=session), \
                patch.object(client, 'get_fid', return_value='f'), \
                patch.object(client, 'video_progress_log', return_value=(True, 200)) as progress:
            result = client.study_video(COURSE, dict(objectid='o', name='lesson.mp3', playTime=15000), {}, _type='Audio')
        self.assertEqual(result, StudyResult.SUCCESS)
        self.assertEqual(session.get.call_args.kwargs['headers'], gc.AUDIO_HEADERS)
        self.assertEqual(progress.call_args.kwargs['headers'], gc.AUDIO_HEADERS)
        self.assertEqual(progress.call_args.args[7], 'Audio')
        self.assertEqual(client.desktop_media_progress.call_args.kwargs['kind'], 'Audio')

    def test_media_network_error_is_reported_without_type_fallback(self):
        client = Chaoxing()
        session = Mock(get=Mock(side_effect=requests.Timeout))
        with patch.object(SessionManager, 'get_session', return_value=session), \
                patch.object(client, 'get_fid', return_value='f'):
            result = process_job(client, COURSE, dict(type='video', objectid='o'), {}, 1)
        self.assertEqual(result, StudyResult.ERROR)
        self.assertEqual(session.get.call_count, 1)

    def test_media_refresh_validates_and_closes_error_responses(self):
        for reply in (response([]), response(status=403, text='Forbidden'),
                      response(dict(status='success', duration=60))):
            client = Chaoxing()
            client.rate_limiter = Mock()
            with patch.object(client, 'get_fid', return_value='f'):
                self.assertIsNone(client._refresh_video_status(Mock(get=Mock(return_value=reply)),
                                                               dict(objectid='o'), 'Audio'))
            reply.close.assert_called_once()

    def test_rt_probe_closes_failed_response_and_reuses_selected_value(self):
        client = Chaoxing()
        client.video_log_limiter = Mock()
        denied = response(status=403, text='Forbidden')
        session = Mock(get=Mock(side_effect=[denied, response(dict(isPassed=False)),
                                             response(dict(isPassed=True))]))
        job = dict(jobid='j', objectid='o', otherinfo='', name='audio')
        with patch.object(client, 'get_uid', return_value='u'):
            self.assertEqual(client.video_progress_log(session, COURSE, job, {}, 't', 60, 0,
                                                       'Audio', headers=gc.AUDIO_HEADERS), (False, 200))
            self.assertEqual(job['rt'], 1)
            self.assertEqual(client.video_progress_log(session, COURSE, job, {}, 't', 60, 60,
                                                       'Audio', headers=gc.AUDIO_HEADERS), (True, 200))
        self.assertEqual(session.get.call_count, 3)
        denied.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
