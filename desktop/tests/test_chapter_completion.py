"""Chapter totals and all jobs remain accurate when media is unconfirmed."""
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/chaoxing'))
from api.base import StudyResult
from chaoxing_desktop import runtime
from chaoxing_desktop.config import Redactor, defaults, to_payload
from chaoxing_desktop.control import Cancelled
from chaoxing_desktop.worker import Channel, real


class ChapterCompletionTests(unittest.TestCase):
    def test_timeout_does_not_reclassify_video_as_audio(self):
        client = Mock()
        client.study_video.return_value = StudyResult.TIMEOUT
        result = runtime.process_job(client, {}, {'type': 'video'}, {}, 1)
        self.assertEqual(result, StudyResult.TIMEOUT)
        client.study_video.assert_called_once_with({}, {'type': 'video'}, {}, _speed=1, _type='Video')

    def test_independent_jobs_are_processed_after_failure(self):
        jobs = [dict(type='video', name='first'), dict(type='video', name='unwatched')]
        for first, expected in ((StudyResult.FORBIDDEN, runtime.ChapterResult.PENDING),
                                (StudyResult.TIMEOUT, runtime.ChapterResult.PENDING),
                                (StudyResult.ERROR, runtime.ChapterResult.ERROR),
                                (RuntimeError('metadata unavailable'), runtime.ChapterResult.ERROR)):
            with self.subTest(first=first):
                client = SimpleNamespace(get_job_list=lambda *args: (jobs, {}))
                with patch.object(runtime, 'process_job', side_effect=[first, StudyResult.SUCCESS]) as process:
                    self.assertEqual(runtime.process_chapter(client, {}, {}, 1), expected)
                self.assertEqual([call.args[2]['name'] for call in process.call_args_list], ['first', 'unwatched'])

    def test_verification_and_cancellation_still_stop_requests(self):
        jobs = [dict(type='video'), dict(type='video')]
        client = SimpleNamespace(get_job_list=lambda *args: (jobs, {}))
        with patch.object(runtime, 'process_job', return_value=StudyResult.VERIFICATION_REQUIRED) as process:
            self.assertEqual(runtime.process_chapter(client, {}, {}, 1), runtime.ChapterResult.PENDING)
            process.assert_called_once()
        with patch.object(runtime, 'process_job', side_effect=Cancelled):
            with self.assertRaises(Cancelled):
                runtime.process_chapter(client, {}, {}, 1)

    def test_two_pending_chapters_do_not_hide_four_media_jobs(self):
        # The screenshots count 158 chapters, with four remaining jobs in two
        # chapters. Two media have full recorded duration but are not passed.
        course = dict(courseId='course', clazzId='class', cpi='cpi', title='course')
        points = [dict(id=str(i), title=f'chapter {i}', has_finished=i >= 2) for i in range(158)]
        jobs = {'0': [dict(type='video', name='full-0')],
                '1': [dict(type='video', name='full-1'), dict(type='video', name='unwatched-1'),
                      dict(type='video', name='unwatched-2')]}
        client = Mock()
        client.login.return_value = {'status': True}
        client.get_course_list.return_value = [course]
        client.get_course_point.return_value = {'points': points}
        client.get_job_list.side_effect = lambda c, p: (jobs[p['id']], {})
        client.study_video.side_effect = lambda c, j, info, **kw: (
            StudyResult.FORBIDDEN if kw['_type'] == 'Audio' else
            StudyResult.TIMEOUT if j['name'].startswith('full-') else StudyResult.SUCCESS)
        core = SimpleNamespace(create_client=lambda *args, **kwargs: client,
                               process_chapter=runtime.process_chapter, ChapterResult=runtime.ChapterResult)
        output = io.StringIO()
        channel = Channel(output, io.StringIO(), Redactor({}))
        config = to_payload(defaults())
        with patch('chaoxing_desktop.worker.load_core', return_value=core):
            real(channel, dict(action='run', config=config, selected=[['course', 'class']]))
        self.assertEqual({call.args[1]['name'] for call in client.study_video.call_args_list},
                         {'full-0', 'full-1', 'unwatched-1', 'unwatched-2'})
        self.assertTrue(all(call.kwargs['_type'] == 'Video' for call in client.study_video.call_args_list))
        done = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual({key: done[key] for key in ('success', 'pending', 'failed', 'skipped')},
                         dict(success=156, pending=2, failed=0, skipped=0))

    def test_success_requires_platform_chapter_confirmation(self):
        self.check_final_confirmation(StudyResult.SUCCESS)

    def test_each_chapter_is_verified_before_starting_next_chapter(self):
        course = dict(courseId='course', clazzId='class', cpi='cpi', title='course')
        points = [dict(id=str(i), title=f'chapter {i}', has_finished=False) for i in range(2)]
        for evidence, expected in ((True, 'success'), (False, 'pending'), (None, 'pending')):
            with self.subTest(evidence=evidence):
                client = Mock()
                client.login.return_value = {'status': True}
                client.get_course_list.return_value = [course]
                client.get_course_point.side_effect = [
                    {'points': points},
                    RuntimeError('unavailable') if evidence is None else
                    {'points': [dict(points[0], has_finished=evidence), points[1]]},
                    {'points': [dict(p, has_finished=True) for p in points]},
                ]
                output = io.StringIO()
                channel = Channel(output, io.StringIO(), Redactor({}))

                def process(client, course, point, speed, task_id):
                    if point['id'] == '1':
                        events = [json.loads(line) for line in output.getvalue().splitlines()]
                        first_statuses = [e['status'] for e in events
                                          if e['type'] == 'task' and e['id'] == 'course:class:0:0']
                        self.assertEqual(first_statuses, ['running', 'processed', expected])
                        progress = [e for e in events if e['type'] == 'course_progress']
                        self.assertEqual(len(progress), 1 if evidence is None else 2)
                        self.assertEqual(progress[-1]['completed'], 1 if evidence else 0)
                        self.assertEqual(progress[-1]['total'], 2)
                        self.assertEqual(client.get_course_point.call_count, 2)
                    return runtime.ChapterResult.SUCCESS

                core = SimpleNamespace(create_client=lambda *args, **kw: client,
                                       process_chapter=process, ChapterResult=runtime.ChapterResult)
                config = to_payload(defaults())
                config['common']['jobs'] = 1
                with patch('chaoxing_desktop.worker.load_core', return_value=core):
                    real(channel, dict(action='run', config=config, selected=[['course', 'class']]))
                done = json.loads(output.getvalue().splitlines()[-1])
                self.assertEqual(done['success'], 2 if evidence else 1)
                self.assertEqual(done['pending'], 0 if evidence else 1)
                self.assertEqual(done['failed'], 0)
                self.assertEqual(client.get_course_point.call_count, 3)

    def test_timed_out_media_can_be_confirmed_by_final_platform_read(self):
        self.check_final_confirmation(StudyResult.TIMEOUT)

    def check_final_confirmation(self, media_result):
        course = dict(courseId='course', clazzId='class', cpi='cpi', title='course')
        point = dict(id='0', title='chapter', has_finished=False)
        for confirmed in (True, False, None):
            with self.subTest(confirmed=confirmed):
                client = Mock()
                client.login.return_value = {'status': True}
                client.get_course_list.return_value = [course]
                final = {'points': [dict(point, has_finished=confirmed)]}
                client.get_course_point.side_effect = [
                    {'points': [point]}, RuntimeError('unavailable') if confirmed is None else final]
                client.get_job_list.return_value = ([dict(type='video', name='video')], {})
                client.study_video.return_value = media_result
                core = SimpleNamespace(create_client=lambda *args, **kw: client,
                                       process_chapter=runtime.process_chapter, ChapterResult=runtime.ChapterResult)
                output = io.StringIO()
                channel = Channel(output, io.StringIO(), Redactor({}))
                with patch('chaoxing_desktop.worker.load_core', return_value=core):
                    real(channel, dict(action='run', config=to_payload(defaults()), selected=[['course', 'class']]))
                done = json.loads(output.getvalue().splitlines()[-1])
                self.assertEqual((done['success'], done['pending']), (1, 0) if confirmed else (0, 1))


if __name__ == '__main__':
    unittest.main()
