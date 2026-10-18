"""Persist only the redacted desktop log, and delete only our session files."""
from datetime import datetime
from pathlib import Path
from collections import deque
import re
import stat
import threading
import time
import uuid
from PySide6.QtCore import QObject, Signal

from .config import data_dir


class LogStore:
    PATTERN = re.compile(r"^chaoxing-\d{8}-\d{6}-[0-9a-f]{12}\.log$")
    MAX_FILE_BYTES = 10 * 1024 * 1024
    MAX_TOTAL_BYTES = 100 * 1024 * 1024
    MAX_AGE_SECONDS = 14 * 24 * 3600

    def __init__(self):
        self.directory = None
        self.path = None

    @staticmethod
    def resolve(directory):
        return Path(directory).expanduser().absolute() if directory.strip() else data_dir() / "logs"

    def append(self, directory, line):
        self.append_many(directory, [line])

    @staticmethod
    def regular(path):
        info = path.lstat()
        return stat.S_ISREG(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)

    def prune(self, directory):
        files = [(path, path.stat()) for path in directory.iterdir()
                 if self.PATTERN.fullmatch(path.name) and self.regular(path)]
        total = sum(info.st_size for _, info in files)
        for path, info in sorted(files, key=lambda item: item[1].st_mtime):
            if path != self.path and (total > self.MAX_TOTAL_BYTES or time.time() - info.st_mtime > self.MAX_AGE_SECONDS):
                path.unlink()
                total -= info.st_size

    def append_many(self, directory, lines):
        directory = self.resolve(directory)
        directory.mkdir(parents=True, exist_ok=True)
        batch, size = [], 0
        def write():
            if not batch:
                return
            if directory != self.directory or self.path is None or (self.path.exists() and self.path.stat().st_size + size > self.MAX_FILE_BYTES):
                self.directory = directory
                self.path = directory / f"chaoxing-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:12]}.log"
                self.prune(directory)
            if self.path.exists() and not self.regular(self.path):
                raise OSError('日志文件不能是链接或特殊文件')
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(''.join(batch))
            self.prune(directory)
        for line in lines:
            text = line + '\n'
            length = len(text.encode('utf-8'))
            if batch and size + length > self.MAX_FILE_BYTES:
                write();batch=[];size=0
            batch.append(text);size+=length
        write()

    def delete(self, directory):
        directory = self.resolve(directory)
        count = 0
        if directory.exists():
            for path in directory.iterdir():
                if self.PATTERN.fullmatch(path.name) and self.regular(path):
                    path.unlink()
                    count += 1
        if self.directory == directory:
            self.path = None
        return count


class AsyncLogStore(QObject):
    """A bounded single-writer queue; only already-redacted lines enter it."""
    failed = Signal(str)
    written = Signal()
    MAX_PENDING_BYTES = 2 * 1024 * 1024

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sink = LogStore()
        self.condition = threading.Condition()
        self.sink_lock = threading.Lock()
        self.queue = deque()
        self.pending_bytes = 0
        self.thread = None
        self.closing = False

    def append(self, directory, line):
        # Resolve default profile before the worker starts; tests may change env.
        directory = str(LogStore.resolve(directory))
        size = len(line.encode('utf-8')) + 1
        with self.condition:
            if self.closing:
                raise OSError('日志写入已关闭')
            if self.pending_bytes + size > self.MAX_PENDING_BYTES:
                raise OSError('日志写入队列已满，界面记录仍保留')
            self.queue.append(('line', directory, line, size))
            self.pending_bytes += size
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name='chaoxing-log-writer', daemon=True)
                self.thread.start()
            self.condition.notify_all()

    def _run(self):
        while True:
            with self.condition:
                while not self.queue and not self.closing:
                    self.condition.wait()
                if not self.queue:
                    return
                item = self.queue.popleft()
                if item[0] == 'barrier':
                    item[1].set()
                    continue
                _, directory, line, size = item
                lines = [line]
                while self.queue and self.queue[0][0] == 'line' and self.queue[0][1] == directory and len(lines) < 128:
                    _, _, line, extra = self.queue.popleft()
                    lines.append(line);size += extra
            try:
                with self.sink_lock:
                    self.sink.append_many(directory, lines)
                self.written.emit()
            except RuntimeError:
                return
            except (OSError, ValueError) as exc:
                try:self.failed.emit(str(exc))
                except RuntimeError:return  # QObject has already been disposed.
            finally:
                with self.condition:
                    self.pending_bytes -= size

    def flush(self, timeout=3):
        with self.condition:
            if self.thread is None or not self.thread.is_alive():
                return not self.queue
            event = threading.Event()
            self.queue.append(('barrier', event))
            self.condition.notify_all()
        return event.wait(timeout)

    def delete(self, directory):
        if not self.flush():
            raise OSError('日志仍在写入，请稍后再删除')
        with self.sink_lock:
            return self.sink.delete(directory)

    def close(self, timeout=3, force=False):
        completed = self.flush(timeout)
        if not completed and not force:
            return False
        with self.condition:
            self.closing = True
            self.condition.notify_all()
        if self.thread is not None:
            self.thread.join(.1)
        return completed
