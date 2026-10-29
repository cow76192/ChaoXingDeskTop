"""User-driven login in an isolated installed Chromium browser, via local CDP."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket, QNetworkProxy
from PySide6.QtWebSockets import QWebSocket


LOGIN_URL = 'https://i.chaoxing.com/base'


def find_browser():
    """Prefer Edge shipped with Windows; never use the user's existing profile."""
    for relative in ('Microsoft/Edge/Application/msedge.exe', 'Google/Chrome/Application/chrome.exe'):
        for variable in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
            root = os.environ.get(variable)
            if root:
                candidate = Path(root) / relative
                if candidate.is_file():
                    return str(candidate)
    raise ValueError('未找到 Microsoft Edge 或 Google Chrome，请安装其中一个浏览器后重试，或手动导入 Cookie。')


def personal_space(url):
    parsed = urlsplit(url)
    return parsed.scheme == 'https' and parsed.hostname == 'i.chaoxing.com' and parsed.path.rstrip('/') == '/base'


def platform_cookies(rows, now=None):
    """Convert only Chaoxing cookies to the existing flat session format."""
    now = time.time() if now is None else now
    result = {}
    # Prefer parent-domain cookies if host-only duplicates exist, consistently.
    for row in sorted(rows, key=lambda item: len(str(item.get('domain', ''))), reverse=True):
        domain = str(row.get('domain', '')).lower().lstrip('.')
        if domain != 'chaoxing.com' and not domain.endswith('.chaoxing.com'):
            continue
        expires = row.get('expires', -1)
        if expires > 0 and expires <= now:
            continue
        name, value = row.get('name', ''), row.get('value', '')
        if not name or any(c in name for c in '=;\r\n') or any(c in value for c in ';\r\n'):
            continue
        result[name] = value
    return result


class BrowserLogin(QObject):
    succeeded = Signal(object)
    finished = Signal(str)
    released = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False
        self.profile = None
        self.started_at = 0
        self.pending = None
        self.serial = 0
        self.socket = QWebSocket(parent=self)
        self.socket.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.socket.connected.connect(self._poll)
        self.socket.textMessageReceived.connect(self._message)
        self.socket.disconnected.connect(self._disconnected)
        self.process = QProcess(self)
        self.process.setStandardOutputFile(QProcess.nullDevice())
        self.process.setStandardErrorFile(QProcess.nullDevice())
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._process_finished)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._poll)
        self.kill_timer = QTimer(self)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.setInterval(1500)
        self.kill_timer.timeout.connect(self.process.kill)

    def start(self):
        executable = find_browser()
        self.profile = tempfile.TemporaryDirectory(prefix='chaoxing-login-', ignore_cleanup_errors=True)
        self.active = True
        self.started_at = time.monotonic()
        self.process.start(executable, [
            '--user-data-dir=' + self.profile.name,
            '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
            '--no-first-run', '--no-default-browser-check', '--disable-extensions',
            '--disable-background-mode', '--incognito', '--new-window', LOGIN_URL,
        ])
        self.timer.start()

    def cancel(self):
        self._finish('已取消浏览器登录。')

    def _send(self, method, params=None):
        self.serial += 1
        self.pending = (self.serial, method, time.monotonic())
        self.socket.sendTextMessage(json.dumps(dict(id=self.serial, method=method, params=params or {})))

    def _poll(self):
        if not self.active:
            return
        elapsed = time.monotonic() - self.started_at
        if elapsed > 300:
            self._finish('浏览器登录已超时，请重试。')
            return
        state = self.socket.state()
        if state == QAbstractSocket.SocketState.UnconnectedState:
            try:
                lines = (Path(self.profile.name) / 'DevToolsActivePort').read_text().splitlines()
                port = int(lines[0])
                endpoint = lines[1]
                if not 0 < port < 65536 or not endpoint.startswith('/devtools/browser/'):
                    raise ValueError()
            except (OSError, ValueError, IndexError):
                if elapsed > 30:
                    self._finish('无法连接登录浏览器，浏览器策略可能禁用了本地调试。可重试或手动导入 Cookie。')
                return
            self.socket.open(QUrl(f'ws://127.0.0.1:{port}{endpoint}'))
        elif state == QAbstractSocket.SocketState.ConnectedState:
            if self.pending:
                if time.monotonic() - self.pending[2] > 15:
                    self._finish('登录浏览器响应超时，请重试。')
            else:
                self._send('Target.getTargets')
        elif elapsed > 30:
            self._finish('连接登录浏览器超时，请重试。')

    def _message(self, text):
        if not self.active or not self.pending:
            return
        try:
            message = json.loads(text)
            if message.get('id') != self.pending[0]:
                return
            method = self.pending[1]
            self.pending = None
            if 'error' in message:
                self._finish('浏览器不支持自动获取 Cookie，请更新 Edge / Chrome，或手动导入 Cookie。')
                return
            result = message.get('result', {})
            if method == 'Target.getTargets':
                pages = [p for p in result.get('targetInfos', []) if p.get('type') == 'page']
                if not pages:
                    self._finish('登录窗口已关闭，未导入 Cookie。')
                else:
                    page = next((p for p in pages if personal_space(p.get('url', ''))), None)
                    if page:
                        # Incognito has its own cookie store, separate from the
                        # default context even inside our temporary profile.
                        context = page.get('browserContextId')
                        self._send('Storage.getCookies', {'browserContextId': context} if context else {})
            elif method == 'Storage.getCookies':
                cookies = platform_cookies(result.get('cookies', []))
                if (cookies.get('_uid') or cookies.get('UID')) and cookies.get('_d'):
                    self._finish('')
                    self.succeeded.emit(cookies)
        except (ValueError, TypeError, KeyError):
            self._finish('无法解析登录浏览器响应，请重试。')

    def _disconnected(self):
        if self.active:
            self._finish('登录窗口已关闭或连接断开，未导入 Cookie。')

    def _process_error(self, _error):
        if self.active:
            self._finish('登录浏览器启动失败，请重试或手动导入 Cookie。')

    def _process_finished(self, *_args):
        if self.active:
            self._finish('登录窗口已关闭，未导入 Cookie。')
        self.kill_timer.stop()
        self.socket.abort()
        if self.profile:
            self.profile.cleanup()
            self.profile = None
        self.released.emit()

    def _finish(self, reason):
        if not self.active:
            return
        self.active = False
        self.timer.stop()
        self.pending = None
        if self.socket.state() == QAbstractSocket.SocketState.ConnectedState:
            self.serial += 1
            self.socket.sendTextMessage(json.dumps(dict(id=self.serial, method='Browser.close')))
            self.socket.flush()
        # Only the process launched with our unique temporary profile is stopped.
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            self.kill_timer.start()
        else:
            self._process_finished()
        self.finished.emit(reason)

    def shutdown(self):
        """Bounded cleanup when the application itself is closing."""
        self.cancel()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            if not self.process.waitForFinished(1500):
                self.process.kill()
                self.process.waitForFinished(1000)
