"""Render the new results, detail dialog and diagnostics in isolated data."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QSG_RHI_BACKEND', 'software')
from PySide6.QtCore import QPointF, Qt, QObject
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from chaoxing_desktop.qml_app import configure_app, create_engine
from chaoxing_desktop.qml_backend import Backend
from chaoxing_desktop.answers import AnswerRouter
from chaoxing_desktop.config import Redactor, to_payload, defaults
from chaoxing_desktop.worker import Channel


def main():
    destination = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/ocs-ui-smoke').resolve()
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    configure_app(app)
    with tempfile.TemporaryDirectory() as folder:
        os.environ['CHAOXING_DESKTOP_DATA'] = folder
        backend = Backend()
        engine = create_engine(backend)
        assert engine.rootObjects(), engine.load_warnings
        window = engine.rootObjects()[0]
        def find(name, item=None):
            item = item or window.contentItem()
            if item.objectName() == name:
                return item
            for child in item.childItems():
                found = find(name, child)
                if found is not None:
                    return found
        try:
            backend.controller.run_id = 'ui-smoke'
            output = io.StringIO()
            channel = Channel(output, io.StringIO(), Redactor({}))
            channel.run_id = 'ui-smoke'
            config = to_payload(defaults())
            config['ai']['check_connection'] = 'false'
            router = AnswerRouter(config, channel, [('离线模拟题库', SimpleNamespace(_query=lambda q: '乙' if q['id'] == '1' else '不匹配的候选'))])
            router.set_context(task_id='chapter', work_id='exercise')
            router.query_all([dict(id='1', title='这是一道已核验的演示题', type='single', options='A.甲\nB.乙'),
                              dict(id='2', title='候选未通过核验的演示题', type='single', options='A.甲\nB.乙')])
            for line in output.getvalue().splitlines():
                backend.on_event(json.loads(line))
            window.setProperty('pageIndex', 4)
            QTest.qWait(180)
            tabs = find('resultTabs')
            assert tabs is not None
            tabs.setProperty('currentIndex', 1)
            QTest.qWait(180)
            assert backend.questionModel.rowCount() == 2
            for width in (1280, 980):
                window.setWidth(width)
                QTest.qWait(160)
                assert window.grabWindow().save(str(destination / f'逐题结果-{width}.png'))
            results = find('questionResults')
            position = results.mapToScene(QPointF(80, 30)).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, position)
            QTest.qWait(160)
            assert window.findChild(QObject, 'questionDetail').property('visible')
            assert window.grabWindow().save(str(destination / '逐题详情.png'))
            QTest.keyClick(window, Qt.Key.Key_Escape)
            backend.filterQuestions(True, '')
            assert backend.questionModel.rowCount() == 1
            backend.filterQuestions(False, 'different-chapter')
            assert backend.questionModel.rowCount() == 0
            backend.offlineCheck()
            assert '未连接真实服务' in backend.bank_status
            window.setProperty('pageIndex', 2)
            window.setWidth(1280)
            QTest.qWait(160)
            assert len(backend.providers) == 5
            assert window.grabWindow().save(str(destination / '题库诊断.png'))
            assert not engine.load_warnings, engine.load_warnings
            (destination / 'result.json').write_text(json.dumps(dict(success=True, rows=2, warnings=engine.load_warnings), ensure_ascii=False), encoding='utf-8')
            print('Question results, detail dialog, chapter/pending filters and offline diagnostics passed; no QML warnings.')
        finally:
            backend.close()
            delete(engine)
            app.processEvents()
            delete(backend)


if __name__ == '__main__':
    main()
