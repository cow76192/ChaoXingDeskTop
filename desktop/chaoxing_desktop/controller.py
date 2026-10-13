import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QProcess, Signal


class Controller(QObject):
    event = Signal(dict)
    finished = Signal(int)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_errors)
        self.process.finished.connect(self.on_finished)
        self.process.errorOccurred.connect(self.on_error)
        self.process.started.connect(self.on_started)
        self.buffer = b""
        self.payload = {}
        self.active = False
        self.stopping = False

    def start(self, payload):
        if self.active:
            raise RuntimeError("已有后台任务正在运行。")
        self.payload = payload
        self.buffer = b""
        self.stopping = False
        self.active = True
        self.busy_changed.emit(True)
        if getattr(sys, "frozen", False):
            # Console worker companion preserves redirected stdio on Windows.
            executable = str(Path(sys.executable).with_name("ChaoxingWorker.exe"))
            args = ["--worker"]
        else:
            executable = sys.executable
            args = ["-u", str(Path(__file__).resolve().parents[1] / "run.py"), "--worker"]
        self.process.start(executable, args)

    def on_started(self):
        self.process.write((json.dumps(self.payload, ensure_ascii=False) + "\n").encode("utf-8"))
        self.payload = {}  # do not retain secrets after transmission

    def read_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if line.strip():
                try:
                    self.event.emit(json.loads(line.decode("utf-8")))
                except (ValueError, UnicodeDecodeError):
                    self.event.emit({"type": "error", "message": "后台事件格式错误，请停止并重试。"})

    def read_errors(self):
        # Raw stderr can contain unredacted traces. Report without displaying it.
        data = bytes(self.process.readAllStandardError())
        if data:
            self.event.emit({"type": "log", "level": "WARNING", "message": "后台产生诊断输出；若任务失败，请检查依赖安装。"})

    def reply(self, answer="", cancel=False):
        if self.active and not self.stopping:
            self.process.write((json.dumps({"answer": answer, "cancel": cancel}, ensure_ascii=False) + "\n").encode("utf-8"))

    def stop(self):
        if self.active:
            self.stopping = True
            self.process.kill()

    def on_finished(self, code, _status):
        self.read_output()
        self.active = False
        self.payload = {}
        self.busy_changed.emit(False)
        self.finished.emit(code)

    def on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.active = False
            self.payload = {}
            self.event.emit({"type": "error", "message": "后台无法启动，请确认软件目录完整且未被隔离。"})
            self.busy_changed.emit(False)
            self.finished.emit(-1)
