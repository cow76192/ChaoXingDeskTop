"""One desktop owner per resolved profile, with local-window activation."""
import hashlib
import os
from pathlib import Path

from PySide6.QtCore import QObject, QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class InstanceGuard(QObject):
    def __init__(self, directory, parent=None):
        super().__init__(parent)
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(os.path.normcase(str(directory)).encode('utf-8')).hexdigest()[:32]
        self.name = 'ChaoxingDesktop-' + digest
        self.lock = QLockFile(str(directory / 'desktop.lock'))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.activate = None
        self.owned = False
        self.server.newConnection.connect(self._accept)

    def acquire(self):
        self.owned = self.lock.tryLock(0)
        if not self.owned:
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(500):
                socket.write(b'activate\n')
                socket.waitForBytesWritten(300)
                socket.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            self.close()
            raise OSError('无法建立本机窗口连接，请检查数据目录权限。')
        return True

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.disconnectFromServer()
            socket.deleteLater()
            if self.activate:
                self.activate()

    def close(self):
        if self.owned:
            self.server.close()
            self.lock.unlock()
            self.owned = False
