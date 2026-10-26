"""Rendered QML + real QProcess/Controller synthetic verification benchmark.

Uses no platform session, login, HTTP or write endpoints. --product-root can
point at an archived baseline, while this exact harness remains unchanged.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def emit(mode, count):
    import threading
    cancelled = threading.Event()
    payload = json.loads(sys.stdin.readline())
    run_id = payload['run_id']
    def commands():
        for line in sys.stdin:
            if json.loads(line).get('command') == 'cancel':
                cancelled.set()
    threading.Thread(target=commands, daemon=True).start()
    for i in range(count):
        if cancelled.is_set():
            print(json.dumps(dict(type='cancelled', run_id=run_id, message='synthetic cancellation')), flush=True)
            return
        if mode.startswith('chapters'):
            e = dict(type='verification', id=str(i % 1000), confirmed=True, checked_at='synthetic', reason='synthetic completion')
        else:
            e = dict(type='record_verification', id='record-'+str(i), task_id=str(i % 1000), kind='activity',
                     participation='existing', task_status='pending', checked_at='synthetic', reason='synthetic evidence')
        print(json.dumps(dict(e, run_id=run_id), ensure_ascii=False), flush=True)
        if mode.endswith('stop'):
            time.sleep(.0005)
    print(json.dumps(dict(type='verification_done', run_id=run_id, message='synthetic final event')), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--product-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--emit', choices=['chapters', 'records', 'chapters-stop', 'records-stop'])
    parser.add_argument('--count', type=int, default=1000)
    parser.add_argument('--chapter-events', type=int, default=1000)
    parser.add_argument('--record-events', type=int, default=2400)
    parser.add_argument('--modes', default='chapters,records,chapters-stop,records-stop')
    parser.add_argument('--max-heartbeat-p95-ms', type=float, default=0)
    parser.add_argument('--max-heartbeat-ms', type=float, default=0)
    parser.add_argument('--max-stop-gui-ms', type=float, default=0)
    args = parser.parse_args()
    if args.emit:
        emit(args.emit, args.count); return
    sys.path[:0] = [str(args.product_root.resolve()), str(args.product_root.resolve() / 'vendor/chaoxing')]
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    os.environ.setdefault('QSG_RHI_BACKEND', 'software')
    from PySide6.QtCore import QObject, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from shiboken6 import delete
    from types import SimpleNamespace
    from unittest.mock import patch
    from chaoxing_desktop.qml_app import configure_app, create_engine
    from chaoxing_desktop.qml_backend import Backend
    from chaoxing_desktop.activity_model import safe_record
    from chaoxing_desktop.attention_model import chapter_issue

    app = QApplication([]); configure_app(app)
    results=[]; callback_errors=[]
    sys.excepthook=lambda kind,value,tb: callback_errors.append(f'{kind.__name__}: {value}')
    with patch('requests.sessions.Session.request', side_effect=AssertionError('offline benchmark')):
        for mode in args.modes.split(','):
            with tempfile.TemporaryDirectory() as directory:
                os.environ['CHAOXING_DESKTOP_DATA']=directory
                b=Backend(); b.operation='verify'; b.operation_account='synthetic'
                b.account_store=SimpleNamespace(active='synthetic', rows=[], cookie_path=lambda _:Path(directory)/'absent-cookie', get=lambda _:None)
                b._task_model.reset([dict(id=str(i), title=f'合成章节 {i}', course='离线压力测试', status='pending') for i in range(1000)])
                for task in b.tasks:
                    b._attention_model.upsert('章节:'+task['id'], chapter_issue(task))
                questions=[dict(id='q'+str(i), type='text', title='合成问卷题', required=True, options=[],
                                minimum=0, maximum=0, min_length=0, max_length=1000, reason='') for i in range(10)]
                answers=[dict(question_id=q['id'], text='合成答案', source='ai', valid=True, reason='') for q in questions]
                r=safe_record(dict(id='a', run_id='synthetic', task_id='0', course='合成课程', chapter='合成章节', title='合成问卷',
                                   kind='survey', stage='draft', submit_status='draft', task_status='pending', reason='',
                                   elapsed_ms=0, questions=questions, answers=answers), lambda s:s)
                for i in range(1000): b._activity_model.upsert(dict(r,id='activity-'+str(i)))
                # These files must remain byte-for-byte unchanged in both modes.
                paths=[]
                for folder in ('discussions','activities'):
                    path=Path(directory)/folder/'intent.json'; path.parent.mkdir(); path.write_bytes(b'{"state":"intent","fixture":true}'); paths.append(path)
                engine=create_engine(b); assert engine.rootObjects(), engine.load_warnings
                window=engine.rootObjects()[0]; window.setProperty('pageIndex',4)
                window.findChild(QObject,'resultTabs').setProperty('currentIndex',4)
                QTest.qWait(150)
                pulses=[]; last=[time.perf_counter()]; changes=[0]; delivered=[0]; stop_click=[None]; stop_gui=[None]; stop_scheduled=[False]
                timer=QTimer(); timer.setInterval(20)
                def pulse():
                    now=time.perf_counter(); pulses.append((now-last[0])*1000); last[0]=now
                timer.timeout.connect(pulse)
                def changed():
                    changes[0]+=1
                    if stop_click[0] is not None and b.controller.stopping and stop_gui[0] is None:
                        stop_gui[0]=(time.perf_counter()-stop_click[0])*1000
                b.changed.connect(changed)
                def observe(e):
                    delivered[0]+=1
                    if mode.endswith('stop') and delivered[0]>=50 and not stop_scheduled[0]:
                        stop_scheduled[0]=True
                        QTimer.singleShot(0,stop)
                b.controller.event.connect(observe)
                b.controller.run_id='synthetic-run'; b.controller.payload=dict(run_id=b.controller.run_id)
                b.controller.active=True; b.controller.busy_changed.emit(True)
                count=args.record_events if mode.startswith('records') else args.chapter_events
                def stop():
                    stop_click[0]=time.perf_counter(); b.stop()
                timer.start(); started=time.perf_counter()
                b.controller.process.start(sys.executable,['-u',str(Path(__file__).resolve()),'--emit',mode,'--count',str(count)])
                while b.controller.active and time.perf_counter()-started<60:
                    QTest.qWait(10)
                elapsed=time.perf_counter()-started
                if b.controller.active:
                    b.controller.process.kill(); b.controller.process.waitForFinished(3000)
                    raise AssertionError('benchmark timed out')
                QTest.qWait(150); timer.stop()
                # Ensure the actual Qt Quick scene produced pixels.
                shot=window.grabWindow(); assert not shot.isNull()
                if args.output:
                    args.output.parent.mkdir(parents=True,exist_ok=True)
                    shot.save(str(args.output.with_name(args.output.stem+'-'+mode+'.png')))
                result=dict(mode=mode,seconds=round(elapsed,4),events=delivered[0],changed=changes[0],
                            heartbeat_p95_ms=round(sorted(pulses)[max(0,int(len(pulses)*.95)-1)],2),
                            heartbeat_max_ms=round(max(pulses),2),heartbeat_samples=len(pulses),stop_gui_ms=round(stop_gui[0],2) if stop_gui[0] is not None else None,
                            task_success=b.summary['success'],attention_rows=b._attention_model.rowCount(),attention_evicted=b._attention_model.evicted,
                            final_received=b.outcome,stopped=b.controller.stopping,qml_warnings=list(engine.load_warnings),
                            intents_unchanged=all(p.read_bytes()==b'{"state":"intent","fixture":true}' for p in paths))
                assert result['intents_unchanged']; assert not result['qml_warnings'],result['qml_warnings']
                assert not callback_errors,callback_errors
                if not mode.endswith('stop'):
                    assert b.outcome and delivered[0]==count+1
                    if mode=='chapters': assert result['task_success']==min(count,1000) and result['attention_rows']==1000-min(count,1000)
                    else: assert result['attention_evicted']==max(0,count-1000) and result['attention_rows']==min(1000+count,2000)
                else:
                    assert result['stopped'] and stop_gui[0] is not None and delivered[0]>=50
                results.append(result)
                delete(engine); b.close(); b.deleteLater(); app.processEvents()
    report=dict(scope='Synthetic offline, actual QML scene and QProcess/Controller; no platform traffic.',product_root=str(args.product_root.resolve()),
                activity_records=1000,answers_per_record=10,results=results)
    if args.output: args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    for result in results:
        if args.max_heartbeat_p95_ms:
            assert result['heartbeat_p95_ms'] <= args.max_heartbeat_p95_ms, result
        if args.max_heartbeat_ms:
            assert result['heartbeat_max_ms'] <= args.max_heartbeat_ms, result
        if args.max_stop_gui_ms and result['stop_gui_ms'] is not None:
            assert result['stop_gui_ms'] <= args.max_stop_gui_ms, result


if __name__=='__main__': main()
