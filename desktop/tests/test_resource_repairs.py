"""Slow-storage, response bounds, AI accounting and release provenance."""
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from PySide6.QtWidgets import QApplication
from chaoxing_desktop.answers import AIClient, AnswerRouter
from chaoxing_desktop.config import Redactor, defaults, to_payload
from chaoxing_desktop.http import service_request
from chaoxing_desktop.log_store import AsyncLogStore, LogStore
from chaoxing_desktop.models import LogModel, LogFilter
from chaoxing_desktop.worker import Channel
from scripts.provenance import record_build, verify_build


class ResourceRepairs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_archived_font_adapter_uses_bundled_vendor_resources(self):
        import sys
        from api.cxsecret_font import resource_path
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', folder, create=True):
                self.assertEqual(Path(resource_path('resource/font_map_table.json')),
                                 Path(folder) / 'vendor/chaoxing/resource/font_map_table.json')

    def test_slow_disk_does_not_block_append_and_queue_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            writer=AsyncLogStore()
            entered,release=threading.Event(),threading.Event()
            def slow(*args):entered.set();release.wait(2)
            writer.MAX_PENDING_BYTES=80
            try:
                with patch.object(writer.sink,'append_many',side_effect=slow):
                    start=time.perf_counter()
                    writer.append(folder,'x'*40)
                    self.assertLess(time.perf_counter()-start,.1)
                    self.assertTrue(entered.wait(1))
                    with self.assertRaises(OSError):writer.append(folder,'y'*80)
                    release.set()
                    self.assertTrue(writer.flush())
            finally:release.set();writer.close();writer.deleteLater()

    def test_rotation_retains_newest_logs_and_preserves_unrelated_file(self):
        with tempfile.TemporaryDirectory() as folder:
            sink=LogStore();sink.MAX_FILE_BYTES=120;sink.MAX_TOTAL_BYTES=250
            unrelated=Path(folder)/'important.log';unrelated.write_text('preserve')
            for i in range(20):sink.append(folder,str(i)+':'+'x'*30)
            logs=list(Path(folder).glob('chaoxing-*.log'))
            self.assertLessEqual(sum(p.stat().st_size for p in logs),250)
            self.assertTrue(all(p.stat().st_size<=120 for p in logs))
            self.assertIn('19:',sink.path.read_text('utf-8'))
            self.assertEqual(unrelated.read_text(),'preserve')

    def test_retention_removes_expired_application_logs_only(self):
        with tempfile.TemporaryDirectory() as folder:
            expired=Path(folder)/'chaoxing-20200101-000000-aaaaaaaaaaaa.log'
            expired.write_text('old');os.utime(expired,(1,1))
            other=Path(folder)/'keep.txt';other.write_text('other')
            sink=LogStore();sink.append(folder,'new')
            self.assertFalse(expired.exists());self.assertTrue(other.exists())

    def test_log_filter_tracks_level_and_query_without_copying_source(self):
        source=LogModel();proxy=LogFilter(source)
        for line in ('12:00:00 INFO ERROR inside message','12:00:01 WARNING retry','12:00:02 ERROR retry'):
            source.append(line)
        source.flush();proxy.set_filter('ERROR','retry')
        self.assertEqual(proxy.rowCount(),1)
        proxy.set_filter('WARNING','retry');self.assertEqual(proxy.rowCount(),2)
        self.assertEqual(source.rowCount(),3)

    def test_service_pool_is_reused_but_never_inherits_another_service_cookie(self):
        first,second=SimpleNamespace(),SimpleNamespace()
        with patch('requests.Session.post',return_value=SimpleNamespace()):
            service_request(first,'post','https://example.test')
            session=first._http_local.session
            session.cookies.set('synthetic','one')
            service_request(first,'post','https://example.test')
            service_request(second,'post','https://example.test')
        self.assertIs(first._http_local.session,session)
        self.assertFalse(second._http_local.session.cookies)

    def test_streamed_response_size_and_expired_budget_stop_requests(self):
        reply=requests.Response();reply.status_code=200;reply._content=b'x'*100;reply._content_consumed=True
        with patch('requests.Session.post',return_value=reply):
            with self.assertRaises(ValueError):service_request(SimpleNamespace(),'post','https://example.test',max_bytes=50)
        with patch('requests.Session.post') as post:
            with self.assertRaises(requests.Timeout):
                service_request(SimpleNamespace(_http_deadline=0),'post','https://example.test')
            post.assert_not_called()

    def test_ai_requests_and_elapsed_are_in_question_results(self):
        config=to_payload(defaults());config['ai'].update(enabled='true',check_connection='false',endpoint='https://example.test',key='synthetic',model='test')
        output=io.StringIO();channel=Channel(output,io.StringIO(),Redactor({}))
        reply=Mock();reply.json.return_value={'choices':[{'message':{'content':'{"Answer":["second"]}'}}]}
        router=AnswerRouter(config,channel,ai=AIClient(config['ai']))
        with patch('requests.Session.post',return_value=reply):
            self.assertEqual(router.query(dict(id='q',type='single',title='Test',options='A.first\nB.second')),'second')
        record=[json.loads(line)['record'] for line in output.getvalue().splitlines() if json.loads(line)['type']=='question_result'][-1]
        self.assertEqual(record['ai_requests'],1)
        self.assertGreaterEqual(record['ai_elapsed_ms'],0)
        self.assertEqual(record['requests'],0)

    def test_publish_record_rejects_missing_gui_and_changed_source_or_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'source';app=Path(folder)/'app';root.mkdir();app.mkdir()
            code=root/'run.py';code.write_text('original')
            binary=app/'ChaoxingDesktop.exe';binary.write_bytes(b'synthetic')
            record_build(root,app,False)
            with self.assertRaises(ValueError):verify_build(root,app)
            record_build(root,app,True);verify_build(root,app)
            code.write_text('changed')
            with self.assertRaises(ValueError):verify_build(root,app)
            code.write_text('original');binary.write_bytes(b'changed')
            with self.assertRaises(ValueError):verify_build(root,app)


if __name__=='__main__':unittest.main()
