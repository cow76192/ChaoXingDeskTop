"""Default Qt Quick launcher."""
import os
from pathlib import Path
import sys
import tempfile
import json

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from .config import resource_root, data_dir
from .qml_backend import Backend


def create_engine(backend):
    engine = QQmlApplicationEngine()
    engine.load_warnings = []
    def record_warnings(errors):
        engine.load_warnings.extend(e.toString() for e in errors)
        del engine.load_warnings[:-200]
    engine.warnings.connect(record_warnings)
    engine.rootContext().setContextProperty("bridge", backend)
    engine.load(QUrl.fromLocalFile(str(resource_root() / "chaoxing_desktop/qml/Main.qml")))
    return engine


def configure_app(app):
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "consola.ttf"):
        if (fonts / name).exists():
            QFontDatabase.addApplicationFont(str(fonts / name))
    app.setApplicationName("ChaoxingDesktop")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setWindowIcon(QIcon(str(resource_root() / "assets/app.svg")))
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    QQuickStyle.setStyle("FluentWinUI3" if sys.platform == "win32" else "Fusion")


def main():
    smoke_path = None
    smoke_data = None
    if "--smoke-test" in sys.argv:
        smoke_path = Path(sys.argv[sys.argv.index("--smoke-test") + 1]).resolve()
        smoke_data = tempfile.TemporaryDirectory(prefix="chaoxing-qml-smoke-")
        os.environ["CHAOXING_DESKTOP_DATA"] = smoke_data.name

    def stage(name):
        if smoke_path:
            smoke_path.mkdir(parents=True, exist_ok=True)
            (smoke_path / "startup.json").write_text(json.dumps({"stage": name}), encoding="utf-8")

    stage("create_application")
    app = QApplication(sys.argv)
    stage("configure_application")
    configure_app(app)
    from .instance import InstanceGuard
    guard = InstanceGuard(data_dir(), app)
    if not guard.acquire():
        if smoke_data:
            smoke_data.cleanup()
        return 0
    stage("load_settings")
    backend = Backend()
    stage("load_qml")
    engine = create_engine(backend)
    stage("qml_loaded")
    if not engine.rootObjects():
        if smoke_path:
            (smoke_path / 'result.json').write_text(json.dumps(
                dict(success=False, message='QML 加载失败', warnings=engine.load_warnings),
                ensure_ascii=False), encoding='utf-8')
        backend.close()
        guard.close()
        return 1
    def activate():
        root = engine.rootObjects()[0]
        root.showNormal()
        root.raise_()
        root.requestActivate()
    guard.activate = activate
    if smoke_path:
        from .qml_selftest import start_smoke
        start_smoke(app, engine, backend, smoke_path)
    stage("event_loop")
    try:
        return app.exec()
    finally:
        # Destroy bindings before their Python context object during shutdown.
        from shiboken6 import delete
        delete(engine)
        backend.close()
        guard.close()
        if smoke_data:
            smoke_data.cleanup()
