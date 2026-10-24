"""Offline, rendered workload benchmark; no account or network is required."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")
from PySide6.QtTest import QTest
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from chaoxing_desktop.qml_app import configure_app, create_engine
from chaoxing_desktop.qml_backend import Backend


def memory_mb():
    if sys.platform != "win32":
        return None
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"working_set": round(counters.WorkingSetSize / 2**20, 2),
            "peak_working_set": round(counters.PeakWorkingSetSize / 2**20, 2),
            "private": round(counters.PrivateUsage / 2**20, 2)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=1000)
    parser.add_argument("--events", type=int, default=300)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument('--questions',type=int,default=0)
    parser.add_argument('--max-round-seconds',type=float,default=0)
    parser.add_argument('--max-heartbeat-p95-ms',type=float,default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument('--attention', action='store_true', help='Render the aggregated pending-items view during the workload')
    args = parser.parse_args()
    if args.output:
        args.output = args.output.resolve()
    app = QApplication([])
    configure_app(app)
    with tempfile.TemporaryDirectory() as directory:
        os.environ["CHAOXING_DESKTOP_DATA"] = directory
        backend = Backend()
        engine = create_engine(backend)
        assert engine.rootObjects(), engine.load_warnings
        window = engine.rootObjects()[0]
        window.setProperty("pageIndex", 4)
        if args.attention:
            window.findChild(QObject, 'resultTabs').setProperty('currentIndex', 4)
        QTest.qWait(150)
        samples = [{"phase": "startup", "memory_mb": memory_mb()}]
        heartbeats=[];previous=[time.perf_counter()]
        timer=QTimer();timer.setInterval(20)
        def tick():
            now=time.perf_counter();heartbeats.append((now-previous[0])*1000);previous[0]=now
        timer.timeout.connect(tick);timer.start()
        from chaoxing_desktop.question_model import STRINGS,NUMBERS
        record={key:'' for key in STRINGS};record.update({key:0 for key in NUMBERS})
        record.update(stage='pending',attempts=[],score=0.0,title='Synthetic load question')
        for round_index in range(args.rounds):
            backend.on_event(dict(type="tasks", tasks=[dict(id=str(i), course="Test course", title=f"Chapter {i}") for i in range(args.tasks)]))
            start = time.perf_counter()
            for i in range(args.events):
                backend.on_event(dict(type="task", id=str(i % args.tasks), status="running"))
                backend.on_event(dict(type="log", message=f"Round {round_index}, event {i}: " + "x" * 180))
                if i % 10 == 0:
                    app.processEvents()
            for i in range(args.questions):
                backend.on_event(dict(type='question_result',record=dict(record,id=f'{round_index}:{i}')))
                if i%10==0:app.processEvents()
            QTest.qWait(150)
            samples.append({"phase": f"round_{round_index + 1}", "seconds": round(time.perf_counter() - start, 3), "memory_mb": memory_mb()})
        assert not engine.load_warnings, engine.load_warnings[:5]
        timer.stop()
        heartbeat_p95=round(sorted(heartbeats)[max(0,int(len(heartbeats)*.95)-1)],2) if heartbeats else 0
        result = {"tasks": args.tasks, "events_per_round": args.events, 'questions_per_round':args.questions,
                  'heartbeat_p95_ms':heartbeat_p95,'question_rows':backend.questionModel.rowCount(),
                  'question_evicted':backend.summary['questionEvicted'],"samples": samples, "qml_warnings": engine.load_warnings}
        window.close()
        delete(engine)
        backend.close()
        text = json.dumps(result, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        print(text)
        if args.max_round_seconds:assert all(sample['seconds']<=args.max_round_seconds for sample in samples[1:]),'Round time budget exceeded'
        if args.max_heartbeat_p95_ms:assert heartbeat_p95<=args.max_heartbeat_p95_ms,'UI heartbeat budget exceeded'


if __name__ == "__main__":
    main()
