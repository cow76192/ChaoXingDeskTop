"""One stdin reader for worker commands and correlated manual replies."""
import json
import queue
import threading
import time


class Cancelled(BaseException):
    """Bypass provider/platform Exception handlers during cooperative shutdown."""


class ResumeFailed(BaseException):
    pass


class RunControl:
    def __init__(self, send):
        self.send = send
        self.cancelled = threading.Event()
        self.condition = threading.Condition()
        self.paused = False
        self.replies = queue.Queue()
        self.eof = False
        self.epoch = 0
        self.validated_epoch = 0
        self.resume_failed = False
        self.resume_check = None
        self.resume_lock = threading.Lock()
        self.resume_local = threading.local()

    def command(self, value):
        kind = value.get('command')
        with self.condition:
            if kind == 'cancel' or value.get('cancel'):
                self.cancelled.set()
                self.paused = False
            elif kind == 'pause':
                self.paused = True
            elif kind == 'resume':
                self.paused = False
                self.epoch += 1
            elif kind == 'reply':
                self.replies.put(value)
            else:
                return
            self.condition.notify_all()
        if kind in ('pause', 'resume'):
            self.send('control', paused=self.paused)

    def read(self, stream):
        try:
            for line in stream:
                if len(line) > 1024 * 1024:
                    self.command({'command': 'cancel'})
                    break
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        self.command(value)
                except ValueError:
                    continue
        finally:
            self.eof = True

    def checkpoint(self, cancel_only=False):
        with self.condition:
            while self.paused and not self.cancelled.is_set() and not cancel_only:
                self.condition.wait(.1)
            if self.cancelled.is_set():
                raise Cancelled()
        if (not cancel_only and self.resume_check and self.validated_epoch != self.epoch
                and not getattr(self.resume_local, 'checking', False)):
            with self.resume_lock:
                if self.validated_epoch != self.epoch:
                    try:
                        self.resume_local.checking = True
                        self.resume_check()
                    except Exception:
                        self.resume_failed = True
                        self.cancelled.set()
                        with self.condition:
                            self.paused = False
                            self.condition.notify_all()
                        raise ResumeFailed() from None
                    finally:
                        self.resume_local.checking = False
                    self.validated_epoch = self.epoch
        if self.cancelled.is_set():
            raise Cancelled()

    def wait(self, seconds, cancel_only=False):
        deadline = time.monotonic() + max(0, seconds)
        while True:
            self.checkpoint(cancel_only)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.cancelled.wait(min(.1, remaining))


def control_of(owner):
    control = vars(owner).get('control')
    return control if isinstance(control, RunControl) else None


def checkpoint(owner, cancel_only=False):
    control = control_of(owner)
    if control:
        control.checkpoint(cancel_only)


def wait(owner, seconds, cancel_only=False):
    control = control_of(owner)
    if control:
        control.wait(seconds, cancel_only)
    elif seconds > 0:
        time.sleep(seconds)
