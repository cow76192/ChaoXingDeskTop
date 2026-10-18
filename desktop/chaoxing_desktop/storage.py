"""Atomic, conflict-aware local writes, independent of UI state."""
from contextlib import contextmanager
from pathlib import Path
import uuid

from PySide6.QtCore import QLockFile


@contextmanager
def file_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path) + '.write.lock')
    lock.setStaleLockTime(0)
    if not lock.tryLock(500):
        raise OSError('文件正被其他进程使用，请稍后重试。')
    try:
        yield
    finally:
        lock.unlock()


def atomic_write(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def revision(path):
    path = Path(path)
    return path.read_bytes() if path.exists() else None


def write_if_unchanged(path, content, expected):
    with file_lock(path):
        current = revision(path)
        if current != expected:
            raise ValueError('文件已被另一个实例修改，原文件已保留。请重新打开程序后重试。')
        atomic_write(Path(path), content)
    return content
